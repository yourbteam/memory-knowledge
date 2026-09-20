"""Connect proven verification to the existing candidate builder's prepare-only path.

No model calls, product writes, admission grants, or driver execution. The supplied
historical creation template contributes dependency context, never old authorization.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import xml.etree.ElementTree as ET


def read(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Required regular preparation input missing: ' + str(path))
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def ref(path):
    return {'path': str(Path(path).absolute()), 'sha256': sha(path)}


def save(path, data):
    path = Path(path)
    raw = (json.dumps(data, indent=2, ensure_ascii=False) + '\n').encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != raw:
            raise ValueError('Prepared output changed: ' + str(path))
    else:
        path.write_bytes(raw)


def verify(reference):
    path = Path(reference['path'])
    if not path.is_absolute() or path.is_symlink() or not path.is_file() or sha(path) != reference['sha256']:
        raise ValueError('Changed preparation evidence: ' + str(path))
    return path
