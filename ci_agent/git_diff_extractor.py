"""Git Diff Extractor & Parser.
Extracts diff from local git CLI or GitHub PR API, and parses line mappings
to ensure inline comments target valid modified lines.
"""
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
import requests


@dataclass
class DiffHunk:
    header: str
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str] = field(default_factory=list)


@dataclass
class FileDiff:
    file_path: str
    old_path: str
    is_new: bool = False
    is_deleted: bool = False
    valid_new_lines: set[int] = field(default_factory=set)
    hunks: list[DiffHunk] = field(default_factory=list)
    raw_diff: str = ""


class GitDiffExtractor:
    def __init__(self, workspace_root: Path | None = None):
        self.workspace_root = workspace_root or Path.cwd()

    def get_diff_from_cli(self, base_ref: str = "origin/main", head_ref: str = "HEAD") -> str:
        """Extract diff using git CLI.
        Tries base_ref...head_ref first, falls back to git diff HEAD or working tree.
        """
        # Try merge-base diff first
        cmd = ["git", "diff", f"{base_ref}...{head_ref}"]
        res = subprocess.run(cmd, cwd=self.workspace_root, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout

        # Fallback 1: git diff against base_ref directly
        cmd = ["git", "diff", base_ref]
        res = subprocess.run(cmd, cwd=self.workspace_root, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout

        # Fallback 2: git diff staged + unstaged changes
        cmd = ["git", "diff", "HEAD"]
        res = subprocess.run(cmd, cwd=self.workspace_root, capture_output=True, text=True)
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout

        # Fallback 3: unstaged changes only
        cmd = ["git", "diff"]
        res = subprocess.run(cmd, cwd=self.workspace_root, capture_output=True, text=True)
        return res.stdout or ""

    def get_diff_from_github(self, repo: str, pr_number: int, token: str) -> str:
        """Fetch unified diff from GitHub REST API."""
        url = f"https://api.github.com/repos/{repo}/pulls/{pr_number}"
        headers = {
            "Accept": "application/vnd.github.v3.diff",
            "User-Agent": "AI-Code-Review-Agent",
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        return response.text

    @staticmethod
    def parse_diff(raw_diff: str) -> list[FileDiff]:
        """Parses unified diff into structured FileDiff objects."""
        if not raw_diff:
            return []

        file_diffs: list[FileDiff] = []
        current_file: FileDiff | None = None
        current_hunk: DiffHunk | None = None
        current_new_line = 0

        hunk_header_re = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@(.*)$")

        for line in raw_diff.splitlines():
            if line.startswith("diff --git "):
                if current_file:
                    file_diffs.append(current_file)
                # diff --git a/path/to/file b/path/to/file
                parts = line.split(" ")
                old_p = parts[2][2:] if len(parts) > 2 and parts[2].startswith("a/") else ""
                new_p = parts[3][2:] if len(parts) > 3 and parts[3].startswith("b/") else ""
                current_file = FileDiff(file_path=new_p or old_p, old_path=old_p, raw_diff=line + "\n")
                current_hunk = None
                continue

            if not current_file:
                continue

            current_file.raw_diff += line + "\n"

            if line.startswith("new file mode"):
                current_file.is_new = True
                continue
            elif line.startswith("deleted file mode"):
                current_file.is_deleted = True
                continue

            match = hunk_header_re.match(line)
            if match:
                old_start = int(match.group(1))
                old_count = int(match.group(2) or "1")
                new_start = int(match.group(3))
                new_count = int(match.group(4) or "1")
                current_new_line = new_start
                current_hunk = DiffHunk(
                    header=line,
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                )
                current_file.hunks.append(current_hunk)
                continue

            if current_hunk:
                current_hunk.lines.append(line)
                if line.startswith("+") and not line.startswith("+++"):
                    current_file.valid_new_lines.add(current_new_line)
                    current_new_line += 1
                elif line.startswith("-") and not line.startswith("---"):
                    # Deleted line in old file, does not increment new file line counter
                    pass
                else:
                    # Context line (space)
                    current_new_line += 1

        if current_file:
            file_diffs.append(current_file)

        return file_diffs
