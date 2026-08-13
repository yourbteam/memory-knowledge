#!/usr/bin/env python3
"""Deterministically inspect and render the visible pages of one frozen PDF."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile


ADAPTER_VERSION = 1
MAX_PAGES = 100
MAX_RENDER_DIMENSION = 2400
TOOL_TIMEOUT_SECONDS = 30
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


class PDFProjectionError(ValueError):
    """The PDF cannot be safely or completely converted by this adapter."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise PDFProjectionError(f"required PDF tool unavailable: {name}")
    return path


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=TOOL_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise PDFProjectionError(f"PDF tool failed: {command[0]}: {error}") from error


def _version(tool: str) -> str:
    completed = _run([tool, "-v"])
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part).strip()
    first_line = output.splitlines()[0] if output else ""
    if completed.returncode != 0 or not first_line:
        raise PDFProjectionError(f"PDF tool version unavailable: {tool}")
    return first_line


def _pdfinfo(source: Path) -> dict[str, str]:
    tool = _tool("pdfinfo")
    completed = _run([tool, str(source)])
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        if "incorrect password" in detail.lower():
            raise PDFProjectionError("encrypted PDFs require conversion before intake")
        raise PDFProjectionError(f"PDF inspection failed: {detail}")
    fields: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        fields[name.strip()] = value.strip()
    return fields


def _page_count(fields: dict[str, str]) -> int:
    raw = fields.get("Pages", "")
    try:
        pages = int(raw)
    except ValueError as error:
        raise PDFProjectionError("PDF page count is missing or invalid") from error
    if pages < 1:
        raise PDFProjectionError("PDF has no visible pages")
    if pages > MAX_PAGES:
        raise PDFProjectionError(
            f"PDF has {pages} pages; the visible-page limit is {MAX_PAGES}"
        )
    return pages


def _reject_unsupported_features(source: Path, fields: dict[str, str]) -> None:
    if fields.get("Encrypted", "").lower().startswith("yes"):
        raise PDFProjectionError("encrypted PDFs require conversion before intake")
    if fields.get("Form", "none").lower() != "none":
        raise PDFProjectionError("PDF forms require conversion before intake")
    if fields.get("JavaScript", "no").lower() != "no":
        raise PDFProjectionError("PDF JavaScript requires conversion before intake")
    tool = _tool("pdfdetach")
    completed = _run([tool, "-list", str(source)])
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
        raise PDFProjectionError(f"PDF attachment inspection failed: {detail}")
    match = re.search(r"^\s*(\d+)\s+embedded files?\s*$", completed.stdout, re.MULTILINE)
    if match is None:
        raise PDFProjectionError("PDF attachment inventory is invalid")
    if int(match.group(1)) != 0:
        raise PDFProjectionError("PDF attachments require conversion before intake")


def _png_dimensions(path: Path) -> tuple[int, int]:
    try:
        header = path.read_bytes()[:24]
    except OSError as error:
        raise PDFProjectionError(f"rendered page unavailable: {path}") from error
    if len(header) != 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise PDFProjectionError(f"rendered page is not a valid PNG: {path}")
    width, height = struct.unpack(">II", header[16:24])
    if width < 1 or height < 1 or width > MAX_RENDER_DIMENSION or height > MAX_RENDER_DIMENSION:
        raise PDFProjectionError(f"rendered page dimensions are outside the adapter limit: {path}")
    return width, height


def prepare(
    source: Path,
    output_root: Path,
    *,
    source_id: str,
    source_sha256: str,
) -> dict[str, object]:
    """Inspect and atomically preserve one bounded PNG rendering per visible page."""
    if output_root.exists():
        raise PDFProjectionError(f"unbound PDF projection artifacts already exist: {output_root}")
    if not source.is_file() or _sha256(source) != source_sha256:
        raise PDFProjectionError("the frozen PDF is unavailable or changed")
    fields = _pdfinfo(source)
    pages = _page_count(fields)
    _reject_unsupported_features(source, fields)
    renderer = _tool("pdftoppm")
    renderer_version = _version(renderer)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix=f".{output_root.name}-", dir=output_root.parent))
    page_records: list[dict[str, object]] = []
    try:
        rendered_dir = stage / "rendered-pages"
        rendered_dir.mkdir()
        for page in range(1, pages + 1):
            basename = f"page-{page:06d}"
            prefix = rendered_dir / basename
            completed = _run([
                renderer,
                "-f", str(page),
                "-l", str(page),
                "-singlefile",
                "-scale-to", str(MAX_RENDER_DIMENSION),
                "-png",
                str(source),
                str(prefix),
            ])
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip() or "unknown error"
                raise PDFProjectionError(f"PDF page {page} rendering failed: {detail}")
            rendered = prefix.with_suffix(".png")
            width, height = _png_dimensions(rendered)
            page_records.append({
                "page": page,
                "render_path": (
                    f"pdf-projections/{source_id}-v1/rendered-pages/{basename}.png"
                ),
                "render_sha256": _sha256(rendered),
                "width": width,
                "height": height,
                "media_type": "image/png",
            })
        stage.rename(output_root)
    except Exception:
        if stage.exists():
            shutil.rmtree(stage)
        raise
    return {
        "adapter": {"name": "pdf_visible_pages", "version": ADAPTER_VERSION},
        "source_id": source_id,
        "source_sha256": source_sha256,
        "page_count": pages,
        "renderer": {
            "name": "pdftoppm",
            "version": renderer_version,
            "max_dimension": MAX_RENDER_DIMENSION,
            "format": "png",
        },
        "pages": page_records,
    }


def validate_prepared(work: Path, prepared: object) -> None:
    """Fail closed if a prepared rendering record or artifact has changed."""
    if not isinstance(prepared, dict):
        raise PDFProjectionError("the prepared PDF projection record is missing")
    source_id = prepared.get("source_id")
    page_count = prepared.get("page_count")
    pages = prepared.get("pages")
    renderer = prepared.get("renderer")
    if (
        prepared.get("adapter") != {"name": "pdf_visible_pages", "version": ADAPTER_VERSION}
        or not isinstance(source_id, str)
        or not isinstance(prepared.get("source_sha256"), str)
        or not isinstance(page_count, int)
        or page_count < 1
        or page_count > MAX_PAGES
        or not isinstance(pages, list)
        or len(pages) != page_count
        or not isinstance(renderer, dict)
        or renderer.get("name") != "pdftoppm"
        or not isinstance(renderer.get("version"), str)
        or not str(renderer["version"]).strip()
        or renderer.get("max_dimension") != MAX_RENDER_DIMENSION
        or renderer.get("format") != "png"
    ):
        raise PDFProjectionError("the prepared PDF projection record has an invalid shape")
    for index, page in enumerate(pages, start=1):
        expected_path = (
            f"pdf-projections/{source_id}-v1/rendered-pages/page-{index:06d}.png"
        )
        if (
            not isinstance(page, dict)
            or page.get("page") != index
            or page.get("render_path") != expected_path
            or page.get("media_type") != "image/png"
            or not isinstance(page.get("render_sha256"), str)
            or len(str(page["render_sha256"])) != 64
        ):
            raise PDFProjectionError(f"prepared PDF page {index} changed")
        artifact = work / expected_path
        width, height = _png_dimensions(artifact)
        if (
            _sha256(artifact) != page["render_sha256"]
            or page.get("width") != width
            or page.get("height") != height
        ):
            raise PDFProjectionError(f"rendered PDF page {index} changed")
