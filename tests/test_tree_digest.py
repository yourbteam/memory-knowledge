import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location(
    "tree_digest", ROOT / "skills/_shared/tree_digest.py"
)
tree_digest = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tree_digest)


class TreeDigestTests(unittest.TestCase):
    def test_canonical_fixture_digest(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "z.txt").write_bytes(b"last\n")
            (root / "nested").mkdir()
            (root / "nested" / "binary.bin").write_bytes(b"\x00\xff\x10")
            (root / "unicode-λ.txt").write_text("λ", encoding="utf-8")
            (root / ".DS_Store").write_bytes(b"ignored")

            records = [
                {"path": "nested/binary.bin", "sha256": hashlib.sha256(b"\x00\xff\x10").hexdigest()},
                {"path": "unicode-λ.txt", "sha256": hashlib.sha256("λ".encode()).hexdigest()},
                {"path": "z.txt", "sha256": hashlib.sha256(b"last\n").hexdigest()},
            ]
            canonical = json.dumps(
                records, sort_keys=True, separators=(",", ":"), ensure_ascii=True
            ).encode("utf-8")
            expected = hashlib.sha256(canonical).hexdigest()

            self.assertEqual(tree_digest.TREE_SHA256_V1(root), expected)
            (root / ".DS_Store").write_bytes(b"changed but still ignored")
            self.assertEqual(tree_digest.TREE_SHA256_V1(root), expected)

    def test_empty_tree_hashes_canonical_empty_array(self):
        with tempfile.TemporaryDirectory() as raw:
            (Path(raw) / "empty-directory").mkdir()
            expected = hashlib.sha256(b"[]").hexdigest()
            self.assertEqual(tree_digest.TREE_SHA256_V1(raw), expected)

    def test_rejects_symlinks_and_non_regular_entries(self):
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            target = root / "target.txt"
            target.write_text("target")
            (root / "link.txt").symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                tree_digest.TREE_SHA256_V1(root)
            (root / "link.txt").unlink()

            fifo = root / "pipe"
            os.mkfifo(fifo)
            with self.assertRaisesRegex(ValueError, "non-regular"):
                tree_digest.TREE_SHA256_V1(root)

    def test_rejects_symlink_root_missing_root_and_file_root(self):
        with tempfile.TemporaryDirectory() as raw:
            parent = Path(raw)
            real_root = parent / "real"
            real_root.mkdir()
            linked_root = parent / "linked"
            linked_root.symlink_to(real_root, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "must not be a symlink"):
                tree_digest.TREE_SHA256_V1(linked_root)
            with self.assertRaisesRegex(ValueError, "cannot be resolved"):
                tree_digest.TREE_SHA256_V1(parent / "missing")
            file_root = parent / "file"
            file_root.write_text("not a directory")
            with self.assertRaisesRegex(ValueError, "must be a directory"):
                tree_digest.TREE_SHA256_V1(file_root)


if __name__ == "__main__":
    unittest.main()
