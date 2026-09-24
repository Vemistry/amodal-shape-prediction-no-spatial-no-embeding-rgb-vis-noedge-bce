"""Unit tests for CI Agent modules."""
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import unittest
from ci_agent.git_diff_extractor import GitDiffExtractor
from ci_agent.tier1_linter import Tier1Linter
from ci_agent.gemini_reviewer import ReviewComment, ReviewResult
from ci_agent.github_poster import GitHubPoster


class TestCIAgent(unittest.TestCase):
    def test_parse_diff_hunk_lines(self):
        sample_diff = """diff --git a/src/app.py b/src/app.py
index 1234567..89abcdef 100644
--- a/src/app.py
+++ b/src/app.py
@@ -10,3 +10,4 @@ def old_func():
     line1
+    new_line2
     line3
+    new_line4
"""
        parsed = GitDiffExtractor.parse_diff(sample_diff)
        self.assertEqual(len(parsed), 1)
        file_diff = parsed[0]
        self.assertEqual(file_diff.file_path, "src/app.py")
        # Lines 11 and 13 should be valid new lines
        self.assertIn(11, file_diff.valid_new_lines)
        self.assertIn(13, file_diff.valid_new_lines)

    def test_tier1_linter_syntax_error(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            bad_py = tmppath / "bad.py"
            bad_py.write_text("def broken_syntax(:\n    pass\n", encoding="utf-8")

            linter = Tier1Linter(workspace_root=tmppath)
            result = linter.check_files(["bad.py"])
            self.assertFalse(result.passed)
            self.assertTrue(any("SyntaxError" in issue.message for issue in result.issues))

    def test_tier1_linter_secret_detection(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            tmppath = Path(tmpdir)
            secret_py = tmppath / "secrets.py"
            secret_py.write_text('API_KEY = "AIzaSyD-fake-key-1234567890"\n', encoding="utf-8")

            linter = Tier1Linter(workspace_root=tmppath)
            result = linter.check_files(["secrets.py"])
            self.assertFalse(result.passed)
            self.assertTrue(any(issue.severity == "CRITICAL" for issue in result.issues))

    def test_format_markdown_report(self):
        poster = GitHubPoster()
        from ci_agent.tier1_linter import LinterResult
        l_res = LinterResult(passed=True, issues=[])
        c = ReviewComment(
            file_path="src/calc.py",
            line_number=25,
            severity="WARNING",
            rule_id="RULE-ARCH-01",
            comment="Nên dùng exception cụ thể thay vì bare except.",
            suggestion="except ValueError as e:",
        )
        r_res = ReviewResult(status="COMMENT", summary="Code ổn nhưng cần chỉnh sửa nhỏ.", comments=[c])
        report = poster.format_markdown_report(l_res, r_res)
        self.assertIn("RULE-ARCH-01", report)
        self.assertIn("src/calc.py", report)
        self.assertIn("```suggestion", report)


if __name__ == "__main__":
    unittest.main()
