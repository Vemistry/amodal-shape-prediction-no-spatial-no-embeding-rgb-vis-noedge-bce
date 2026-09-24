"""Tier 1: Deterministic Gate (Linter, Syntax & Offline Security Check).
Runs fast, 100% offline, costs 0$ tokens. Fails fast if code has syntax errors.
"""
import ast
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class LintIssue:
    file_path: str
    line: int
    message: str
    severity: str = "ERROR"


@dataclass
class LinterResult:
    passed: bool
    issues: list[LintIssue]

    def summary(self) -> str:
        if self.passed:
            return "Tier 1: Deterministic checks passed. No syntax or critical static errors."
        msg = f"Tier 1 FAILED: Found {len(self.issues)} issue(s):\n"
        for issue in self.issues:
            msg += f"  [{issue.severity}] {issue.file_path}:{issue.line} - {issue.message}\n"
        return msg


class Tier1Linter:
    # Basic patterns to catch obvious leaked secrets offline
    SECRET_PATTERNS = [
        (re.compile(r"""(?i)(?:api_key|secret|password|token)\s*=\s*['"][a-zA-Z0-9_\-]{16,}['"]"""), "Hardcoded potential secret/token detected"),
        (re.compile(r"""-----BEGIN (?:RSA )?PRIVATE KEY-----"""), "Private Key block detected in source code"),
    ]

    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = workspace_root or Path.cwd()

    def check_files(self, changed_files: list[str]) -> LinterResult:
        issues: list[LintIssue] = []

        # Filter only existing files
        valid_files = [f for f in changed_files if (self.workspace_root / f).is_file()]

        # 1. Quick regex secret scanning across all modified files
        for rel_path in valid_files:
            abs_path = self.workspace_root / rel_path
            try:
                content = abs_path.read_text(encoding="utf-8", errors="ignore")
                for line_idx, line in enumerate(content.splitlines(), start=1):
                    for pattern, desc in self.SECRET_PATTERNS:
                        if pattern.search(line):
                            issues.append(LintIssue(file_path=rel_path, line=line_idx, message=desc, severity="CRITICAL"))
            except Exception as e:
                issues.append(LintIssue(file_path=rel_path, line=1, message=f"Failed to read file: {e}", severity="WARNING"))

        # 2. Python syntax check
        python_files = [f for f in valid_files if f.endswith(".py")]
        
        # Check if ruff is available
        has_ruff = shutil.which("ruff") is not None
        if has_ruff and python_files:
            try:
                cmd = ["ruff", "check", "--select", "E9,F63,F7,F82", *python_files]
                res = subprocess.run(cmd, cwd=self.workspace_root, capture_output=True, text=True)
                if res.returncode != 0:
                    for line in res.stdout.splitlines():
                        if ":" in line:
                            parts = line.split(":", 3)
                            if len(parts) >= 3:
                                issues.append(
                                    LintIssue(
                                        file_path=parts[0].strip(),
                                        line=int(parts[1]) if parts[1].isdigit() else 1,
                                        message=parts[2].strip() if len(parts) == 3 else parts[3].strip(),
                                        severity="ERROR",
                                    )
                                )
            except Exception as e:
                # Fallback to ast parsing below
                pass

        # If ruff not present or to double check syntax: ast.parse
        for py_file in python_files:
            abs_path = self.workspace_root / py_file
            try:
                code = abs_path.read_text(encoding="utf-8", errors="ignore")
                ast.parse(code, filename=str(abs_path))
            except SyntaxError as e:
                issues.append(
                    LintIssue(
                        file_path=py_file,
                        line=e.lineno or 1,
                        message=f"Python SyntaxError: {e.msg}",
                        severity="ERROR",
                    )
                )

        has_critical = any(issue.severity in ("CRITICAL", "ERROR") for issue in issues)
        return LinterResult(passed=not has_critical, issues=issues)
