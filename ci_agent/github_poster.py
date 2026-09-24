"""GitHub Poster & Local Report Generator.
Handles posting inline comments and review summary to GitHub PR API,
or rendering a formatted markdown report in dry-run mode.
"""
import logging
from pathlib import Path
import requests

from .gemini_reviewer import ReviewComment, ReviewResult
from .tier1_linter import LinterResult

logger = logging.getLogger(__name__)


class GitHubPoster:
    def __init__(self, repo: str = "", pr_number: int | None = None, token: str = ""):
        self.repo = repo
        self.pr_number = pr_number
        self.token = token

    def format_markdown_report(self, linter_res: LinterResult, review_res: ReviewResult | None) -> str:
        """Constructs a consolidated Markdown report."""
        lines = [
            "# 🤖 Báo Cáo Đánh Giá Tự Động (AI Code Review Report)",
            "",
            "## 1. Tầng 1: Deterministic Check (Linter & Syntax)",
        ]

        if linter_res.passed:
            lines.append("✅ **Trạng thái:** PASS (Không phát hiện lỗi cú pháp hoặc secret cơ bản).")
        else:
            lines.append(f"❌ **Trạng thái:** FAILED ({len(linter_res.issues)} vấn đề).")
            for issue in linter_res.issues:
                lines.append(f"- `[{issue.severity}]` **{issue.file_path}:{issue.line}**: {issue.message}")

        lines.append("")
        lines.append("## 2. Tầng 2: Semantic & Logic Review (Gemini AI)")

        if not review_res:
            lines.append("⏭️ *Bỏ qua do Tầng 1 không vượt qua (Fail-fast trigger).*")
            return "\n".join(lines)

        status_emoji = {
            "APPROVED": "✅ APPROVE",
            "CHANGES_REQUESTED": "❌ CHANGES REQUESTED",
            "COMMENT": "💬 COMMENT",
        }.get(review_res.status, "ℹ️ NOTE")

        lines.append(f"**Kết luận:** {status_emoji}")
        lines.append(f"**Tóm tắt:** {review_res.summary}")
        lines.append("")

        if review_res.is_error:
            lines.append("⚠️ **Thông báo:** Quá trình AI Review không thể hoàn thành do sự cố từ dịch vụ LLM.")
            if review_res.error_message:
                lines.append(f"```text\n{review_res.error_message}\n```")
            lines.append("👉 *Gợi ý: Lỗi 503 (High Demand) thường là tạm thời do Google API nghẽn tải. Bạn có thể nhấn 'Re-run all jobs' trên GitHub Actions sau 1–2 phút.*")
        elif review_res.comments:
            lines.append(f"### Chi tiết các nhận xét ({len(review_res.comments)} vị trí):")
            for c in review_res.comments:
                lines.append(f"#### 📍 `{c.file_path}` (Dòng {c.line_number})")
                lines.append(c.to_markdown())
        else:
            lines.append("✨ *Không phát hiện vi phạm logic hoặc kiến trúc đáng kể nào!*")


        return "\n".join(lines)

    def print_dry_run(self, linter_res: LinterResult, review_res: ReviewResult | None, output_file: Path | None = None):
        """Prints formatted report to stdout and writes to markdown file."""
        report = self.format_markdown_report(linter_res, review_res)
        print("\n" + "=" * 60)
        print(report)
        print("=" * 60 + "\n")

        if output_file:
            output_file.write_text(report, encoding="utf-8")
            print(f"📄 Báo cáo review đã được lưu tại: {output_file.resolve()}")

    def post_to_github(self, linter_res: LinterResult, review_res: ReviewResult | None) -> bool:
        """Submits a Pull Request Review via GitHub REST API."""
        if not self.repo or not self.pr_number or not self.token:
            logger.error("Thiếu thông tin GITHUB_REPOSITORY, PR_NUMBER hoặc GITHUB_TOKEN để post comment.")
            return False

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "AI-Code-Review-Agent",
        }

        # 1. Fetch latest commit SHA of PR
        pr_url = f"https://api.github.com/repos/{self.repo}/pulls/{self.pr_number}"
        pr_resp = requests.get(pr_url, headers=headers, timeout=20)
        if pr_resp.status_code != 200:
            logger.error("Không thể lấy thông tin PR từ GitHub: %s", pr_resp.text)
            return False

        head_sha = pr_resp.json().get("head", {}).get("sha", "")
        if not head_sha:
            logger.error("Không tìm thấy commit head_sha của PR.")
            return False

        # 2. Build review payload
        overall_report = self.format_markdown_report(linter_res, review_res)

        inline_comments = []
        if review_res and review_res.comments:
            for c in review_res.comments:
                if c.line_number > 0:
                    inline_comments.append({
                        "path": c.file_path,
                        "line": c.line_number,
                        "body": c.to_markdown(),
                    })


        # GitHub Actions (GITHUB_TOKEN) is not allowed to submit "APPROVE" reviews by default.
        # Standard industry bots (CodeRabbit, etc.) always submit reviews with event="COMMENT"
        # and display the approval status clearly in the markdown body.
        event = "COMMENT"

        reviews_url = f"https://api.github.com/repos/{self.repo}/pulls/{self.pr_number}/reviews"
        payload = {
            "commit_id": head_sha,
            "body": overall_report,
            "event": event,
            "comments": inline_comments,
        }

        resp = requests.post(reviews_url, headers=headers, json=payload, timeout=30)
        if resp.status_code in (200, 201):
            logger.info("Đã gửi GitHub Review thành công lên PR #%s!", self.pr_number)
            return True

        # Fallback: If inline comments cause validation errors, post general review comment
        logger.warning("Post inline comments thất bại (%s), thử gửi review không kèm inline comments...", resp.text)
        fallback_payload = {
            "commit_id": head_sha,
            "body": overall_report,
            "event": "COMMENT",
        }
        fb_resp = requests.post(reviews_url, headers=headers, json=fallback_payload, timeout=30)
        if fb_resp.status_code in (200, 201):
            logger.info("Đã gửi fallback review summary thành công!")
            return True

        # Final fallback: post as a normal issue comment if pull request reviews are restricted
        logger.warning("Post review thất bại (%s), thử gửi dưới dạng Issue Comment thông thường...", fb_resp.text)
        issue_comments_url = f"https://api.github.com/repos/{self.repo}/issues/{self.pr_number}/comments"
        issue_resp = requests.post(issue_comments_url, headers=headers, json={"body": overall_report}, timeout=30)
        return issue_resp.status_code in (200, 201)

