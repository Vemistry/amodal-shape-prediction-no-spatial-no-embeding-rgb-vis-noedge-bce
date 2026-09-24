"""Configuration manager for the AI Code Review Agent."""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentConfig:
    gemini_api_key: str
    gemini_model: str
    github_token: str
    github_repository: str
    pr_number: int | None
    base_ref: str
    head_ref: str
    dry_run: bool
    guidelines_path: Path

    @classmethod
    def from_env(
        cls,
        gemini_api_key: str | None = None,
        github_token: str | None = None,
        github_repository: str | None = None,
        pr_number: int | None = None,
        base_ref: str | None = None,
        dry_run: bool = False,
        gemini_model: str | None = None,
    ) -> "AgentConfig":
        root_dir = Path(__file__).resolve().parent
        default_guidelines = root_dir / "AI_REVIEW_GUIDELINES.md"

        env_pr = os.getenv("PR_NUMBER")
        parsed_pr = pr_number if pr_number is not None else (int(env_pr) if env_pr and env_pr.isdigit() else None)

        return cls(
            gemini_api_key=gemini_api_key or os.getenv("GEMINI_API_KEY", ""),
            gemini_model=gemini_model or os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
            github_token=github_token or os.getenv("GITHUB_TOKEN", ""),
            github_repository=github_repository or os.getenv("GITHUB_REPOSITORY", ""),
            pr_number=parsed_pr,
            base_ref=base_ref or os.getenv("BASE_REF", "origin/main"),
            head_ref=os.getenv("HEAD_REF", "HEAD"),
            dry_run=dry_run or os.getenv("DRY_RUN", "false").lower() in ("true", "1", "yes"),
            guidelines_path=Path(os.getenv("GUIDELINES_PATH", str(default_guidelines))),
        )
