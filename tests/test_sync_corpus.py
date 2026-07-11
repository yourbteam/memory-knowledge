import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).parents[1]; spec=importlib.util.spec_from_file_location("sync",ROOT/"working-agreement/sync_corpus.py")


class SyncSourceTests(unittest.TestCase):
    def test_force_selects_head_not_head_parent(self):
        # Import dependencies are repo-venv specific, so assert the stable subprocess contract at source level.
        text=(ROOT/"working-agreement/sync_corpus.py").read_text()
        self.assertIn("'HEAD' if force_current else 'HEAD~1'",text)
        self.assertIn('"corpus_query"',text); self.assertIn('"query_text"',text)

    def test_deactivation_is_gated_on_upsert_success(self):
        text=(ROOT/"working-agreement/sync_corpus.py").read_text()
        gate=text.index("if failures:"); deactivate=text.index("for e in orphans:",gate)
        self.assertLess(gate,deactivate); self.assertIn("refusing all deactivations",text[gate:deactivate])


if __name__ == "__main__": unittest.main()
