#!/usr/bin/env python3
"""Run one source-bound, profile-specific startup observation for Atlas."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from typing import Callable, Sequence


class LaunchError(ValueError):
    pass


class LaunchCancelled(Exception):
    pass


PROFILE_INPUTS = {
    "local-storage": ("empty", None),
    "cloud-storage": ("probe", "atlasprobe"),
}
SOURCE_SUFFIXES = {".cs", ".csproj", ".props", ".targets", ".sln", ".slnx", ".resx",
                   ".razor", ".cshtml", ".tt", ".png", ".jpg", ".jpeg", ".svg", ".ttf",
                   ".woff", ".woff2", ".xml", ".txt"}
SOURCE_BASENAMES = {"global.json", ".editorconfig"}
ACCOUNT_NAME_ENV = "AdminTourManagement__Storage__TourImage__AccountName"
OBSERVATION_SCHEMA = 1


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def _safe_relative(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or "\\" in value or value.startswith("/"):
        raise LaunchError(f"{label} must be a safe relative path")
    parts = value.split("/")
    if any(part in {"", ".", ".."} for part in parts) or PurePosixPath(value).is_absolute():
        raise LaunchError(f"{label} must be a safe relative path")
    return value


def _inside(root: Path, value: str, label: str) -> Path:
    relative = _safe_relative(value, label)
    root = root.resolve(strict=True)
    path = root.joinpath(*relative.split("/"))
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LaunchError(f"{label} does not exist: {relative}") from exc
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise LaunchError(f"{label} resolves outside its declared root: {relative}") from exc
    if path.is_symlink() or not resolved.is_file():
        raise LaunchError(f"{label} must be a regular file: {relative}")
    return resolved


def _copy_manifest(root: Path, mirror: Path, records: object, *, generated: bool) -> list[dict[str, object]]:
    if not isinstance(records, list) or any(not isinstance(item, dict) for item in records):
        raise LaunchError("compiler input manifest must be an array of records")
    copied: list[dict[str, object]] = []
    seen: set[str] = set()
    for item in records:
        logical = _safe_relative(item.get("logical_path"), "compiler input logical path")
        if logical in seen:
            raise LaunchError(f"compiler input manifest repeats {logical}")
        seen.add(logical)
        if not generated:
            if not logical.startswith("tracked/"):
                raise LaunchError("tracked compiler input has an invalid logical path")
            relative = _safe_relative(item.get("path"), "tracked compiler input path")
            if logical != f"tracked/{relative}":
                raise LaunchError("tracked compiler input logical path disagrees with its saved path")
            if item.get("presence") != "present" or item.get("type") != "file":
                continue
            basename = Path(relative).name.lower()
            suffix = Path(relative).suffix.lower()
            if (suffix not in SOURCE_SUFFIXES and basename not in SOURCE_BASENAMES
                    and not basename.startswith("directory.build.")):
                continue
            if "appsettings" in basename or "secret" in basename or "credential" in basename:
                continue
        else:
            relative = logical
        expected = item.get("sha256")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise LaunchError(f"compiler input has an invalid saved hash: {logical}")
        source = _inside(root, relative, "compiler input")
        actual = _digest(source)
        if actual != expected:
            raise LaunchError(f"compiler input changed since capture: {relative}")
        destination = mirror.joinpath(*relative.split("/"))
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination, follow_symlinks=False)
        if _digest(destination) != expected:
            raise LaunchError(f"compiler input copy failed integrity check: {relative}")
        copied.append({"logical_path": logical, "sha256": expected, "size_bytes": destination.stat().st_size})
    return sorted(copied, key=lambda item: os.fsencode(str(item["logical_path"])))


def _dotnet(value: str | None = None) -> Path:
    configured = value or os.environ.get("ATLAS_DOTNET") or shutil.which("dotnet")
    if not configured:
        raise LaunchError("runtime-index requires a local dotnet SDK host; set ATLAS_DOTNET to its absolute path")
    path = Path(configured).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except OSError as exc:
        raise LaunchError("dotnet SDK host does not exist") from exc
    if not resolved.is_file() or not os.access(resolved, os.X_OK):
        raise LaunchError("dotnet SDK host must be an executable regular file")
    return resolved


def _tool_env(dotnet: Path, temporary: Path) -> dict[str, str]:
    env = {key: os.environ[key] for key in ("PATH", "HOME", "TMPDIR", "TEMP", "TMP") if key in os.environ}
    env.update({
        "DOTNET_ROOT": dotnet.parent.as_posix(),
        "DOTNET_CLI_HOME": (temporary / "dotnet-home").as_posix(),
        "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
        "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
        "DOTNET_NOLOGO": "1",
        "DOTNET_MULTILEVEL_LOOKUP": "0",
        "NUGET_PACKAGES": (Path.home() / ".nuget" / "packages").as_posix(),
        "NUGET_HTTP_CACHE_PATH": (temporary / "empty-http-cache").as_posix(),
        "RestoreIgnoreFailedSources": "true",
        "DOTNET_HOST_PATH": dotnet.as_posix(),
    })
    sdk = subprocess.run([dotnet.as_posix(), "--version"], stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, timeout=15, env=env, check=False)
    version = sdk.stdout.strip()
    sdk_root = dotnet.parent / "sdk" / version
    if sdk.returncode != 0 or not version or not (sdk_root / "MSBuild.dll").is_file():
        raise LaunchError("installed dotnet SDK could not be identified for offline build")
    env["MSBUILD_EXE_PATH"] = (sdk_root / "MSBuild.dll").as_posix()
    env["MSBuildSDKsPath"] = (sdk_root / "Sdks").as_posix()
    return env


def _require_object(value: object, label: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise LaunchError(f"{label} must be an object")
    return value


def _identity_projection(value: object, replacements: list[tuple[str, str]]) -> object:
    """Normalize only per-observation output roots; retain installed tool identities."""
    if isinstance(value, str):
        normalized = value
        for prefix, token in replacements:
            if normalized == prefix:
                return token
            if normalized.startswith(prefix.rstrip("/") + "/"):
                normalized = token + normalized[len(prefix.rstrip("/")):]
        return normalized
    if isinstance(value, list):
        return [_identity_projection(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _identity_projection(item, replacements) for key, item in value.items()}
    return value


def _validate_producer_identity(value: object) -> dict[str, dict[str, str]]:
    identity = _require_object(value, "runtime producer identity")
    if set(identity) != {"atlas_source", "runtime_launcher_source"}:
        raise LaunchError("runtime producer identity has an unsupported or open schema")
    verified: dict[str, dict[str, str]] = {}
    for key in ("atlas_source", "runtime_launcher_source"):
        record = _require_object(identity.get(key), f"runtime producer identity {key}")
        if set(record) != {"path", "sha256"}:
            raise LaunchError(f"runtime producer identity {key} has an unsupported or open schema")
        path_value, expected_hash = record.get("path"), record.get("sha256")
        if (not isinstance(path_value, str) or not path_value or "\n" in path_value
                or not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash)):
            raise LaunchError(f"runtime producer identity {key} has an invalid file identity")
        path = Path(path_value)
        if (not path.is_absolute() or any(component.is_symlink() for component in (path, *path.parents))
                or not path.is_file()):
            raise LaunchError(f"runtime producer identity {key} path is not a regular absolute file")
        resolved = path.resolve(strict=True)
        if resolved.as_posix() != path.as_posix() or _digest(resolved) != expected_hash:
            raise LaunchError(f"runtime producer source changed or is not canonical: {key}")
        verified[key] = {"path": resolved.as_posix(), "sha256": expected_hash}
    return verified


def _validate_request(request: dict[str, object]) -> tuple[Path, Path, Path, Path, str, str, str, dict[str, dict[str, str]]]:
    if request.get("schema_version") != 1:
        raise LaunchError("runtime observation request schema version is unsupported")
    producer_identity = _validate_producer_identity(request.get("producer_identity"))
    profile = request.get("profile")
    if profile not in PROFILE_INPUTS:
        raise LaunchError("runtime observation profile must be local-storage or cloud-storage")
    state, probe = PROFILE_INPUTS[str(profile)]
    if request.get("account_name_state") != state or request.get("account_name_probe") != probe:
        raise LaunchError("runtime observation profile inputs do not match the closed profile configuration")
    for key in ("snapshot_id", "compiler_supplement_sha256"):
        value = request.get(key)
        if not isinstance(value, str) or not value:
            raise LaunchError(f"runtime observation request is missing {key}")
    if not re.fullmatch(r"[0-9a-f]{64}", str(request["compiler_supplement_sha256"])):
        raise LaunchError("runtime observation compiler supplement hash is invalid")
    tracked_inputs = request.get("tracked_inputs")
    generated_inputs = request.get("generated_inputs")
    source_snapshot_files = request.get("source_snapshot_files")
    compiler_identity = request.get("compiler_input_identity")
    if not isinstance(tracked_inputs, list) or not isinstance(generated_inputs, list):
        raise LaunchError("runtime observation request lacks saved compiler input manifests")
    if not isinstance(source_snapshot_files, list) or not isinstance(compiler_identity, dict):
        raise LaunchError("runtime observation request lacks its saved source snapshot/compiler identity")
    if (compiler_identity.get("tracked_inputs") != tracked_inputs
            or compiler_identity.get("generated_inputs") != generated_inputs):
        raise LaunchError("runtime observation compiler manifests disagree with the saved supplement")
    root_value = request.get("repo_root")
    if not isinstance(root_value, str):
        raise LaunchError("runtime observation repository root is missing")
    root = Path(root_value).resolve(strict=True)
    if not root.is_dir():
        raise LaunchError("runtime observation repository root is not a directory")
    project = _safe_relative(request.get("project_path"), "project path")
    if not project.endswith(".csproj"):
        raise LaunchError("project path must name a .csproj file")
    project_source = _inside(root, project, "project file")
    framework = request.get("framework")
    if not isinstance(framework, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", framework):
        raise LaunchError("target framework moniker is invalid")
    entry_name = request.get("entry_assembly_name")
    interface_name = request.get("interface_type_name")
    expected_name = request.get("expected_runtime_type_name")
    if not all(isinstance(value, str) and value and "\n" not in value for value in (entry_name, interface_name, expected_name)):
        raise LaunchError("source-bound assembly and type identities must be nonempty strings")
    if Path(str(entry_name)).name != entry_name or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", str(entry_name)):
        raise LaunchError("entry assembly name is invalid")
    observer_root = Path(str(request.get("observer_source_root", ""))).resolve(strict=True)
    observer_project = _inside(observer_root, "Atlas.RuntimeStartupObserver.csproj", "startup observer project")
    observer_source = _inside(observer_root, "StartupHook.cs", "startup observer source")
    artifact_value = request.get("artifact_dir")
    if not isinstance(artifact_value, str) or not artifact_value:
        raise LaunchError("runtime observation artifact directory is missing")
    artifacts = Path(artifact_value).expanduser().absolute()
    artifacts.mkdir(parents=True, exist_ok=True)
    if artifacts.is_symlink() or not artifacts.is_dir():
        raise LaunchError("runtime observation artifact directory must be a real directory")
    if artifacts.resolve() == root or root in artifacts.resolve().parents:
        raise LaunchError("runtime observation artifacts must be stored outside the target repository")
    return root, project_source, observer_project, artifacts, str(profile), str(framework), str(entry_name), producer_identity


def launch(request: dict[str, object]) -> dict[str, object]:
    """Build a protected source mirror and return one verified startup observation."""
    request = _require_object(request, "runtime observation request")
    root, project_source, observer_project, artifacts, profile, framework, entry_name, producer_identity = _validate_request(request)
    project_relative = str(request["project_path"])
    state, probe = PROFILE_INPUTS[profile]
    dotnet = _dotnet()
    nonce = str(uuid.uuid4())
    record_dir = artifacts / f"{profile}-{nonce}"
    record_dir.mkdir(mode=0o700)
    with tempfile.TemporaryDirectory(prefix="atlas-runtime-build-", dir=artifacts) as temporary_name:
        temporary = Path(temporary_name)
        mirror = temporary / "mirror"
        mirror.mkdir()
        copied_sources = _copy_manifest(root, mirror, request.get("tracked_inputs"), generated=False)
        generated = _copy_manifest(root, mirror, request.get("generated_inputs"), generated=True)
        project = mirror / project_relative
        if not project.is_file():
            raise LaunchError("source-bound project was not present in the tracked input mirror")
        project_obj = project.parent / "obj" / "project.assets.json"
        if not project_obj.is_file():
            raise LaunchError("offline project assets are absent from the saved generated inputs")
        env = _tool_env(dotnet, temporary)
        observer_source_root = Path(str(request["observer_source_root"])).resolve(strict=True)
        observer_build = temporary / "observer-build"
        observer_build.mkdir()
        observer_output = record_dir / "observer-output"
        observer_output.mkdir()
        empty_feed = observer_build / "empty-feed"
        empty_feed.mkdir()
        nuget_config = observer_build / "NuGet.Config"
        nuget_config.write_text(
            '<?xml version="1.0" encoding="utf-8"?><configuration><packageSources><clear/><add key="empty" value="'
            + empty_feed.as_posix() + '"/></packageSources></configuration>', encoding="utf-8")
        observer_copy = observer_build / "source"
        observer_copy.mkdir()
        shutil.copyfile(observer_source_root / "StartupHook.cs", observer_copy / "StartupHook.cs")
        shutil.copyfile(observer_source_root / "Atlas.RuntimeStartupObserver.csproj",
                        observer_copy / "Atlas.RuntimeStartupObserver.csproj")
        restore = subprocess.run([dotnet.as_posix(), "restore", (observer_copy / "Atlas.RuntimeStartupObserver.csproj").as_posix(),
                                  "--configfile", nuget_config.as_posix(), "--ignore-failed-sources"],
                                 cwd=observer_copy, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 text=True, timeout=60, check=False)
        if restore.returncode:
            raise LaunchError(f"offline startup observer restore failed: {(restore.stderr or restore.stdout).strip()[:1000]}")
        observer_run = subprocess.run([dotnet.as_posix(), "build", (observer_copy / "Atlas.RuntimeStartupObserver.csproj").as_posix(),
                                       "--no-restore", "--configuration", "Release", "--output", observer_output.as_posix(),
                                       "-p:ContinuousIntegrationBuild=true", "-p:Deterministic=true",
                                       f"-p:PathMap={observer_copy.as_posix()}=/atlas/observer"],
                                      cwd=observer_copy, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                      text=True, timeout=90, check=False)
        if observer_run.returncode:
            raise LaunchError(f"startup observer build failed: {(observer_run.stderr or observer_run.stdout).strip()[:1500]}")
        build_output = record_dir / "application-output"
        build_output.mkdir()
        app_env = dict(env)
        app_env["DOTNET_STARTUP_HOOKS"] = ""
        app_build = subprocess.run([dotnet.as_posix(), "build", project.as_posix(), "--no-restore", "--configuration", "Release",
                                    "--framework", framework, "--output", build_output.as_posix(),
                                    "-p:ContinuousIntegrationBuild=true", "-p:Deterministic=true",
                                    f"-p:PathMap={mirror.as_posix()}=/atlas/source"],
                                   cwd=mirror, env=app_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, timeout=240, check=False)
        if app_build.returncode:
            raise LaunchError(f"offline target project build failed: {(app_build.stderr or app_build.stdout).strip()[:2000]}")
        app_dll = build_output / f"{entry_name}.dll"
        observer_dll = observer_output / "Atlas.RuntimeStartupObserver.dll"
        if not app_dll.is_file() or not observer_dll.is_file():
            raise LaunchError("startup observation build did not produce the entry or observer assembly")
        output_manifest = []
        for path in sorted(build_output.rglob("*"), key=lambda item: os.fsencode(item.relative_to(build_output).as_posix())):
            if path.is_symlink():
                raise LaunchError("target build output contains a symbolic link")
            if path.is_file():
                output_manifest.append({"path": path.relative_to(build_output).as_posix(),
                                        "sha256": _digest(path), "size_bytes": path.stat().st_size})
        content_root = temporary / "empty-content-root"
        content_root.mkdir()
        capture_path = record_dir / "capture.json"
        termination_path = record_dir / "termination.json"
        host_trace = record_dir / "native-host.log"
        profile_key = ACCOUNT_NAME_ENV.replace("__", ":")
        profile_environment_key = ACCOUNT_NAME_ENV
        profile_expected_value = "" if state == "empty" else str(probe)
        process_env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "DOTNET_ROOT": dotnet.parent.as_posix(),
            "DOTNET_STARTUP_HOOKS": observer_dll.as_posix(),
            "DOTNET_ENVIRONMENT": "AtlasRuntimeProbe",
            "ASPNETCORE_ENVIRONMENT": "AtlasRuntimeProbe",
            ACCOUNT_NAME_ENV: "" if state == "empty" else str(probe),
            "ATLAS_RUNTIME_PROBE_OPERATION_NONCE": nonce,
            "ATLAS_RUNTIME_PROBE_OUTPUT": capture_path.as_posix(),
            "ATLAS_RUNTIME_PROBE_TERMINATION_OUTPUT": termination_path.as_posix(),
            "ATLAS_RUNTIME_PROBE_PROFILE": profile,
            "ATLAS_RUNTIME_PROBE_ENTRY_ASSEMBLY_NAME": entry_name,
            "ATLAS_RUNTIME_PROBE_INTERFACE_TYPE_NAME": str(request["interface_type_name"]),
            "ATLAS_RUNTIME_PROBE_EXPECTED_RUNTIME_TYPE_NAME": str(request["expected_runtime_type_name"]),
            "ATLAS_RUNTIME_PROBE_PROFILE_INPUT_KEY": profile_environment_key,
            "ATLAS_RUNTIME_PROBE_PROFILE_INPUT_EXPECTED_VALUE": profile_expected_value,
            "COREHOST_TRACE": "1",
            "COREHOST_TRACE_VERBOSITY": "4",
            "COREHOST_TRACEFILE": host_trace.as_posix(),
        }
        preexec = None
        if os.name == "posix":
            import resource
            preexec = lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if _validate_producer_identity(request.get("producer_identity")) != producer_identity:
            raise LaunchError("runtime producer source identity changed before host execution")
        started = time.monotonic()
        process = subprocess.Popen([dotnet.as_posix(), app_dll.as_posix(), "--contentRoot", content_root.as_posix(),
                                    "--applicationName", entry_name, "--environment", "AtlasRuntimeProbe"],
                                   cwd=content_root, env=process_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=(os.name == "posix"), preexec_fn=preexec)
        try:
            stdout, stderr = process.communicate(timeout=20)
        except subprocess.TimeoutExpired as exc:
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            else:
                process.kill()
            process.communicate()
            raise LaunchError("runtime startup observer timed out; no observation was accepted") from exc
        duration_seconds = time.monotonic() - started
        if process.returncode not in {-signal.SIGABRT, 128 + signal.SIGABRT}:
            raise LaunchError(f"runtime observer exited without the expected intentional host abort: {process.returncode}; no observation accepted")
        if not capture_path.is_file() or capture_path.is_symlink() or not termination_path.is_file() or termination_path.is_symlink():
            raise LaunchError("runtime observer did not produce both capture and termination records")
        capture = json.loads(capture_path.read_text(encoding="utf-8"))
        termination = json.loads(termination_path.read_text(encoding="utf-8"))
        if not isinstance(capture, dict) or not isinstance(termination, dict):
            raise LaunchError("runtime observer records must be JSON objects")
        expected = {
            "schema_version": 1, "operation_nonce": nonce, "profile": profile,
            "profile_input_key": ACCOUNT_NAME_ENV,
            "profile_input_state": "empty" if state == "empty" else "nonempty",
            "profile_input_matches": True, "interface_full_name": request["interface_type_name"],
            "expected_runtime_type": request["expected_runtime_type_name"],
            "observed_runtime_type": request["expected_runtime_type_name"],
            "selection_matches": True, "host_built_observed": True,
            "host_disposed": True, "scope_disposed": True,
            "failure_code": None, "failure_message": None,
        }
        for key, value in expected.items():
            if capture.get(key) != value:
                raise LaunchError(f"runtime capture failed the exact profile/type check: {key}")
        for key, value in {"schema_version": 1, "operation_nonce": nonce, "profile": profile,
                           "process_id": process.pid, "host_built_observed": True,
                           "intentional_host_abort": True, "process_terminating": True}.items():
            if termination.get(key) != value:
                raise LaunchError(f"runtime termination receipt failed its process join: {key}")
        if capture.get("process_id") != process.pid or termination.get("entry_assembly_identity") != capture.get("entry_assembly_identity"):
            raise LaunchError("runtime capture and termination records do not identify the same process and entry assembly")
        if capture.get("entry_assembly_name") not in (None, entry_name):
            raise LaunchError("runtime capture entry assembly name disagrees with the source-bound project")
        if capture.get("interface_assembly_identity") != capture.get("entry_assembly_identity"):
            raise LaunchError("observed interface was not loaded from the source-bound entry assembly")
        if capture.get("observed_runtime_assembly_identity") != capture.get("entry_assembly_identity"):
            raise LaunchError("selected implementation was not loaded from the source-bound entry assembly")
        if termination.get("entry_assembly_location") != capture.get("entry_assembly_location"):
            raise LaunchError("runtime termination receipt entry assembly path disagrees with the capture")
        if termination.get("unhandled_exception_type") != "Microsoft.Extensions.Hosting.HostAbortedException":
            raise LaunchError("runtime termination receipt does not identify the intentional public host-abort exception")
        if Path(str(capture.get("entry_assembly_location", ""))).resolve() != app_dll.resolve():
            raise LaunchError("runtime observer loaded an entry assembly outside the protected build output")
        if Path(str(capture.get("observed_runtime_assembly_location", ""))).resolve() != app_dll.resolve():
            raise LaunchError("selected runtime service did not come from the protected entry assembly")
        content_files = [path.relative_to(content_root).as_posix() for path in content_root.rglob("*")]
        if content_files:
            raise LaunchError("application wrote files under the isolated empty content root after host construction")
        loaded_assemblies = capture.get("loaded_assemblies")
        if not isinstance(loaded_assemblies, list) or any(not isinstance(item, dict) for item in loaded_assemblies):
            raise LaunchError("runtime capture lacks its loaded assembly identity list")
        loaded_manifest = []
        for item in loaded_assemblies:
            location = item.get("location")
            if not isinstance(location, str):
                raise LaunchError("runtime capture contains a loaded assembly without a file location")
            path = Path(location).resolve(strict=True)
            in_application = False
            try:
                path.relative_to(build_output.resolve())
                in_application = True
            except ValueError:
                pass
            allowed_roots = [build_output.resolve(), observer_output.resolve()]
            for framework_name in ("Microsoft.NETCore.App", "Microsoft.AspNetCore.App"):
                allowed_roots.append((dotnet.parent / "shared" / framework_name).resolve())
            in_runtime = False
            for allowed_root in allowed_roots:
                try:
                    path.relative_to(allowed_root)
                    in_runtime = True
                    break
                except ValueError:
                    pass
            if not (in_application or in_runtime):
                raise LaunchError("runtime capture loaded an assembly outside the protected application/runtime outputs")
            if not path.is_file():
                raise LaunchError("runtime capture loaded an assembly that is not a regular file")
            loaded_manifest.append({**item, "sha256": _digest(path), "size_bytes": path.stat().st_size})
        app_root_hash = hashlib.sha256(json.dumps(output_manifest, ensure_ascii=True, sort_keys=True,
                                                   separators=(",", ":")).encode("ascii")).hexdigest()
        observer_hash = _digest(observer_dll)
        native_manifest = [{"path": dotnet.as_posix(), "sha256": _digest(dotnet), "size_bytes": dotnet.stat().st_size}]
        host_dir = dotnet.parent / "host"
        fxr_dir = host_dir / "fxr"
        runtime_dirs = {Path(str(item["location"])).resolve().parent for item in loaded_assemblies
                        if isinstance(item.get("location"), str) and
                        ("Microsoft.NETCore.App" in item["location"] or "Microsoft.AspNetCore.App" in item["location"])}
        for base in (host_dir, fxr_dir, *sorted(runtime_dirs, key=lambda item: os.fsencode(item.as_posix()))):
            if base.exists():
                for path in sorted(base.rglob("*"), key=lambda item: os.fsencode(item.as_posix())):
                    if path.is_symlink():
                        raise LaunchError("dotnet native host manifest contains a symbolic link")
                    if path.is_file():
                        native_manifest.append({"path": path.resolve().as_posix(), "sha256": _digest(path),
                                                "size_bytes": path.stat().st_size})
        input_identity = {
            "schema_version": 1,
            "producer_identity": producer_identity,
            "binding": {key: request.get(key) for key in (
                "snapshot_id", "project_path", "framework", "profile", "interface_type_name",
                "entry_assembly_name", "expected_runtime_type_name", "account_name_state", "account_name_probe")},
            "snapshot_id": request.get("snapshot_id"),
            "compiler_supplement_sha256": request.get("compiler_supplement_sha256"),
            "compiler_input_identity": request.get("compiler_input_identity"),
            "compiler_input_identity_sha256": hashlib.sha256(json.dumps(
                request.get("compiler_input_identity"), ensure_ascii=True, sort_keys=True,
                separators=(",", ":")).encode("ascii")).hexdigest(),
            "source_snapshot_files": request.get("source_snapshot_files"),
            "tracked_inputs": request.get("tracked_inputs"),
            "generated_inputs": generated,
            "copied_source_inputs": copied_sources,
            "observer_source": {"path": (observer_source_root / "StartupHook.cs").as_posix(),
                                "sha256": _digest(observer_source_root / "StartupHook.cs")},
            "observer_project": {"path": observer_project.as_posix(), "sha256": _digest(observer_project)},
            "observer_assembly": {"path": observer_dll.as_posix(), "sha256": observer_hash},
            "observer_outputs": [{"path": path.relative_to(observer_output).as_posix(), "sha256": _digest(path),
                                  "size_bytes": path.stat().st_size}
                                 for path in sorted(observer_output.rglob("*"), key=lambda item: os.fsencode(item.relative_to(observer_output).as_posix()))
                                 if path.is_file()],
            "application_output_root": build_output.as_posix(),
            "application_entry_assembly_path": app_dll.as_posix(),
            "application_outputs": output_manifest,
            "application_output_manifest_sha256": app_root_hash,
            "dotnet_host": {"path": dotnet.as_posix(), "sha256": _digest(dotnet)},
            "native_runtime_files": native_manifest,
            "loaded_runtime_assemblies": loaded_manifest,
            "project": project_relative,
            "framework": framework,
        }
        projection = _identity_projection(input_identity, [
            (build_output.resolve().as_posix(), "$APPLICATION_OUTPUT"),
            (observer_output.resolve().as_posix(), "$OBSERVER_OUTPUT"),
        ])
        input_sha = hashlib.sha256(json.dumps(projection, ensure_ascii=True, sort_keys=True,
                                               separators=(",", ":")).encode("ascii")).hexdigest()
        input_identity_path = record_dir / "input-identity.json"
        input_identity_path.write_text(json.dumps(input_identity, ensure_ascii=True, sort_keys=True,
                                                  separators=(",", ":")) + "\n", encoding="ascii")
        projection_path = record_dir / "input-identity-projection.json"
        projection_path.write_text(json.dumps(projection, ensure_ascii=True, sort_keys=True,
                                               separators=(",", ":")) + "\n", encoding="ascii")
        process_record = {"exit_code": process.returncode, "intentional_abort_verified": True,
                          "timed_out": False, "duration_seconds": duration_seconds,
                          "stdout_sha256": hashlib.sha256(stdout).hexdigest(),
                          "stderr_sha256": hashlib.sha256(stderr).hexdigest(),
                          "capture_path": capture_path.as_posix(), "termination_path": termination_path.as_posix(),
                          "artifact_dir": record_dir.as_posix()}
        (record_dir / "process-result.json").write_text(json.dumps(process_record, ensure_ascii=True,
                                                                    sort_keys=True, separators=(",", ":")) + "\n",
                                                        encoding="ascii")
        shutil.copyfile(capture_path, artifacts / f"{profile}-{nonce}-capture.json")
        shutil.copyfile(termination_path, artifacts / f"{profile}-{nonce}-termination.json")
        if host_trace.is_file():
            shutil.copyfile(host_trace, artifacts / f"{profile}-{nonce}-native-host.log")
        return {
            "schema_version": OBSERVATION_SCHEMA,
            "operation_nonce": nonce,
            "profile": profile,
            "profile_inputs": {"key": profile_key, "state": state, "probe": probe},
            "capture": capture,
            "termination": termination,
            "process": process_record,
            "input_identity": input_identity,
            "input_identity_projection": projection,
            "input_sha256": input_sha,
        }


def _prompt(label: str, input_fn: Callable[[str], str]) -> str:
    try:
        value = input_fn(label).strip()
    except (EOFError, KeyboardInterrupt) as exc:
        raise LaunchCancelled from exc
    if not value:
        raise LaunchCancelled
    return value


def _existing_checkout(value: str) -> Path:
    path = Path(value).expanduser()
    try:
        root = path.resolve(strict=True)
    except OSError as exc:
        raise LaunchError(f"checkout path does not exist: {value!r}") from exc
    if not root.is_dir() or not (root / ".git").exists():
        raise LaunchError(f"checkout must be an existing Git worktree: {value!r}")
    return root


def _existing_database(value: str) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink():
        raise LaunchError("database path must not be a symbolic link")
    try:
        result = path.resolve(strict=True)
    except OSError as exc:
        raise LaunchError("database path must name an existing Atlas database") from exc
    if not result.is_file():
        raise LaunchError("database path must name an existing regular file")
    return result


def _project_path(checkout: Path, value: str) -> str:
    relative = _safe_relative(value, "project path")
    if not relative.endswith(".csproj"):
        raise LaunchError("project path must name a repository-relative .csproj file")
    _inside(checkout, relative, "project file")
    return relative


def _framework(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_.-]*", value):
        raise LaunchError("framework must be a target-framework moniker such as net8.0")
    return value


def _interface_name(value: str) -> str:
    if not re.fullmatch(r"(?:global::)?[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+", value):
        raise LaunchError("interface must be an exact fully qualified source type name")
    return value.removeprefix("global::")


def _sdk(value: str | None, environment: dict[str, str]) -> Path | None:
    configured = value or environment.get("ATLAS_DOTNET") or shutil.which("dotnet", path=environment.get("PATH"))
    if not configured:
        return None
    path = Path(configured).expanduser()
    try:
        resolved = path.resolve(strict=True)
    except OSError:
        return None
    if resolved.is_file() and os.access(resolved, os.X_OK):
        return resolved
    return None


def main(argv: Sequence[str] | None = None, *, input_fn: Callable[[str], str] = input,
         runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
         environment: dict[str, str] | None = None, atlas_script: Path | None = None) -> int:
    """Prompt for the bounded runtime-index request and delegate validation to Atlas."""
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments:
        print("runtime_index_launch.py accepts no command-line arguments", file=sys.stderr)
        return 2
    env = dict(os.environ if environment is None else environment)
    try:
        checkout = _existing_checkout(_prompt("Repository checkout path: ", input_fn))
        database = _existing_database(_prompt("Atlas database path: ", input_fn))
        project = _project_path(checkout, _prompt("Repository-relative project path: ", input_fn))
        framework = _framework(_prompt("Target framework moniker: ", input_fn))
        interface = _interface_name(_prompt("Exact source interface type (fully qualified): ", input_fn))
        profile = _prompt("Startup profile (local-storage, cloud-storage, or both): ", input_fn)
        if profile not in {*PROFILE_INPUTS, "both"}:
            raise LaunchError("profile must be local-storage, cloud-storage, or both")
        dotnet = _sdk(None, env)
        if dotnet is None:
            dotnet = _sdk(_prompt("Path to executable dotnet SDK host: ", input_fn), env)
            if dotnet is None:
                raise LaunchError("SDK host must be an existing executable file")
        script = (atlas_script or Path(__file__).resolve().with_name("atlas.py")).resolve(strict=True)
        if not script.is_file():
            raise LaunchError("Atlas CLI script is missing")
        env["ATLAS_DOTNET"] = dotnet.as_posix()
        command = [sys.executable, script.as_posix(), "runtime-index", "--repo", checkout.as_posix(),
                   "--db", database.as_posix(), "--project", project, "--framework", framework,
                   "--interface", interface, "--profile", profile]
        result = runner(command, env=env, check=False)
        return int(result.returncode)
    except LaunchCancelled:
        print("Cancelled; runtime observation was not started.", file=sys.stderr)
        return 130
    except LaunchError as exc:
        print(f"runtime-index launch refused: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"runtime-index launch failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
