"""Durable, exact-input checkpoints for independent comparison votes."""
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile

CACHE_FIELDS = {"votes", "identity"}
POLICY = "exact-comparison-v1"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@contextlib.contextmanager
def checkpoint(directory, identity):
    """Hold the pair lock while reusing or extending its vote prefix."""
    if directory is None:
        yield [], lambda votes: None
        return
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(canonical(identity).encode()).hexdigest()
    path = directory / f"{key}.json"
    with (directory / f"{key}.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        votes = []
        if path.exists():
            record = json.loads(path.read_text())
            if (record.get("policy") != POLICY or record.get("identity") != identity
                    or not isinstance(record.get("votes"), list)
                    or any(vote not in ("YES", "NO", None) for vote in record["votes"])
                    or len(record["votes"]) > identity["asks"]):
                raise ValueError("comparison checkpoint does not match its exact input contract")
            votes = record["votes"]
        def save(values):
            payload = {"policy": POLICY, "identity": identity, "votes": list(values)}
            temporary = None
            try:
                with tempfile.NamedTemporaryFile(mode="w", dir=directory, delete=False) as stream:
                    temporary = Path(stream.name)
                    stream.write(canonical(payload) + "\n")
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(temporary, path)
                descriptor = os.open(directory, os.O_RDONLY)
                try:
                    os.fsync(descriptor)
                finally:
                    os.close(descriptor)
            finally:
                if temporary is not None and temporary.exists():
                    temporary.unlink()
        yield list(votes), save
