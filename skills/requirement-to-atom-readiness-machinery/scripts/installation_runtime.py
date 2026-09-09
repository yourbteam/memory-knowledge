"""Resolve managed client entrypoints to their byte-verified canonical runtime.

The runtime deliberately owns repository-relative dependencies and sealed histories.
Installing its operator instructions must not relocate those dependencies or histories.
No source location is accepted from a request, working directory, or environment.
"""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

NAME = 'requirement-to-atom-readiness-machinery'
ENTRYPOINTS = ('readiness_controller.py', 'run_canary.py')
SUPPORT = ('scripts/blocker_catalog.py', 'scripts/work_memory.py')
RECORD = '.managed-skills-source.json'


class InstallationRefused(ValueError):
    pass


def require(value, message):
    if not value:
        raise InstallationRefused(message + '; refresh this skill through the managed installer')


def regular(path):
    require(path.is_absolute() and '..' not in path.parts, f'{path}: require a canonical absolute path')
    require(not any(p.is_symlink() for p in (path, *path.parents)), f'{path}: linked source is forbidden')
    info = path.stat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1, f'{path}: require an unlinked regular file')
    require(info.st_size <= 32 * 1024 * 1024, f'{path}: source exceeds 32 MiB')
    return path.read_bytes()


def tree(root):
    result = {}
    require(root.is_dir() and not root.is_symlink(), f'{root}: missing or linked skill directory')
    for path in sorted(root.rglob('*')):
        if '__pycache__' in path.parts or path.suffix in ('.pyc', '.pyo'):
            continue
        require(not path.is_symlink(), f'{path}: linked skill member is forbidden')
        if path.is_dir():
            continue
        result[path.relative_to(root).as_posix()] = hashlib.sha256(regular(path)).hexdigest()
    return result


def canonical_entrypoint(entry):
    entry = Path(os.path.abspath(entry))
    require(entry.name in ENTRYPOINTS, f'{entry.name}: not a managed public entrypoint')
    regular(entry)
    installation_root = entry.parents[3]
    # Canonical operation stays exactly where it was. Client roots have no such
    # repository-owned manifest; they must carry installer-issued provenance.
    if (installation_root/'skills/managed-skills.txt').is_file():
        require(entry == installation_root/'skills'/NAME/'scripts'/entry.name,
                f'{entry}: unexpected canonical skill location')
        return entry
    record_path = installation_root/RECORD
    def unique(items):
        result = {}
        for key, value in items:
            require(key not in result, f'{record_path}: duplicate field {key}')
            result[key] = value
        return result
    record = json.loads(regular(record_path), object_pairs_hook=unique)
    require(type(record) is dict and set(record) == {'schema_version','source_repository_root','support_files'},
            f'{record_path}: require the complete managed source record')
    require(type(record['schema_version']) is int and record['schema_version'] == 1,
            f'{record_path}: unsupported source record version')
    require(type(record['source_repository_root']) is str, f'{record_path}: source root must be a path string')
    source = Path(record['source_repository_root'])
    target = source/'skills'/NAME/'scripts'/entry.name
    require(target != entry, f'{record_path}: source points back to the client installation')
    managed = regular(source/'skills/managed-skills.txt').decode().splitlines()
    require(sum(line.strip() == NAME for line in managed) == 1,
            f'{source}: recorded source must manage this skill exactly once')
    require(type(record['support_files']) is dict and set(record['support_files']) == set(SUPPORT),
            f'{record_path}: require both canonical support hashes')
    for relative in SUPPORT:
        actual = hashlib.sha256(regular(source/relative)).hexdigest()
        require(actual == record['support_files'][relative], f'{source/relative}: canonical support bytes changed')
    require(tree(entry.parent.parent) == tree(source/'skills'/NAME),
            f'{entry.parent.parent}: installed skill differs from its canonical source')
    regular(target)
    return target


def dispatch(entry):
    """Keep argv and Python unchanged; replace only the verified entrypoint path."""
    try:
        target = canonical_entrypoint(entry)
        if target != Path(os.path.abspath(entry)):
            os.execv(sys.executable, [sys.executable, str(target), *sys.argv[1:]])
    except (InstallationRefused, OSError, ValueError, TypeError, KeyError) as error:
        print(f'installation refused: {error}', file=sys.stderr)
        raise SystemExit(2) from error
