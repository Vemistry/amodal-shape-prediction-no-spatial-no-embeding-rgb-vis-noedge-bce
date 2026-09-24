"""Main entrypoint for AI Code Review Agent."""
import argparse
import logging
import sys
from pathlib import Path

from .config import AgentConfig
from .gemini_reviewer import GeminiReviewer
from .git_diff_extractor import GitDiffExtractor
from .github_poster import GitHubPoster
from .tier1_linter import Tier1Linter

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("ci_agent")


def main() -> int:
    parser = argparse.ArgumentParser(description="AI Code Review Agent (In-house & GitHub Actions PoC)")
    parser.add_argument("--base", default=None, help="Base branch/ref to compare diff against (default: origin/main)")
    parser.add_argument("--pr", type=int, default=None, help="Pull Request number (GitHub)")
    parser.add_argument("--repo", default=None, help="GitHub repository (owner/repo)")
    parser.add_argument("--model", default=None, help="Gemini Model (default: gemini-3.6-flash)")
    parser.add_argument("--api-key", default=None, help="Gemini API Key (default: $GEMINI_API_KEY)")
    parser.add_argument("--github-token", default=None, help="GitHub Token (default: $GITHUB_TOKEN)")
    parser.add_argument("--dry-run", action="store_true", help="Print report locally without posting to GitHub")
    parser.add_argument("--output", default="review_report.md", help="Output file path for local review report")
    parser.add_argument("--fail-on-changes", action="store_true", help="Exit code 1 if changes are requested or linter fails")

    args = parser.parse_args()

    config = AgentConfig.from_env(
        gemini_api_key=args.api_key,
        github_token=args.github_token,
        github_repository=args.repo,
        pr_number=args.pr,
        base_ref=args.base,
        dry_run=args.dry_run,
        gemini_model=args.model,
    )

    logger.info("Khởi động AI Code Review Agent...")
    logger.info(f"Chế độ: {'DRY RUN (Cục bộ)' if config.dry_run else 'GitHub Actions / Online'}")
    logger.info(f"Mô hình LLM: {config.gemini_model}")

    # 1. Trích xuất Git Diff
    extractor = GitDiffExtractor()
    raw_diff = ""

    if not config.dry_run and config.pr_number and config.github_token and config.github_repository:
        logger.info(f"Đang lấy diff từ GitHub PR #{config.pr_number} ({config.github_repository})...")
        try:
            raw_diff = extractor.get_diff_from_github(config.github_repository, config.pr_number, config.github_token)
        except Exception as e:
            logger.warning(f"Lấy diff qua GitHub API thất bại ({e}), chuyển sang đọc Git CLI cục bộ...")
            raw_diff = extractor.get_diff_from_cli(base_ref=config.base_ref, head_ref=config.head_ref)
    else:
        logger.info(f"Đang lấy diff từ Git CLI cục bộ (so với {config.base_ref})...")
        raw_diff = extractor.get_diff_from_cli(base_ref=config.base_ref, head_ref=config.head_ref)

    if not raw_diff.strip():
        logger.info("Không phát hiện thay đổi mã nguồn nào giữa nhánh hiện tại và nhánh cơ sở.")
        return 0

    file_diffs = extractor.parse_diff(raw_diff)
    changed_files = [fd.file_path for fd in file_diffs if not fd.is_deleted]
    logger.info(f"Phát hiện {len(file_diffs)} file thay đổi ({len(changed_files)} file hiện hữu).")

    # 2. Tầng 1: Deterministic Gate (Linter, Syntax & Secret Scan)
    logger.info("Đang chạy Tầng 1: Deterministic Gate (Linter & Syntax check)...")
    linter = Tier1Linter()
    linter_res = linter.check_files(changed_files)

    poster = GitHubPoster(repo=config.github_repository, pr_number=config.pr_number, token=config.github_token)

    if not linter_res.passed:
        logger.error(linter_res.summary())
        logger.info("Dừng pipeline (Fail-fast trigger). Bỏ qua Tầng 2 để tiết kiệm LLM token.")
        if config.dry_run or not config.github_token:
            poster.print_dry_run(linter_res, review_res=None, output_file=Path(args.output))
        else:
            poster.post_to_github(linter_res, review_res=None)
        return 1 if args.fail_on_changes else 0

    logger.info("Tầng 1 PASS! Bắt đầu Tầng 2: Semantic AI Review...")

    if not config.gemini_api_key:
        logger.error(
            "\n" + "=" * 70 + "\n"
            "LỖI: GEMINI_API_KEY chưa được thiết lập hoặc đang bị rỗng!\n\n"
            "Các nguyên nhân phổ biến trên GitHub Actions:\n"
            "1. Nhầm tab: Bạn đã tạo trong mục 'Variables' thay vì 'Secrets'.\n"
            "   -> Kiểm tra: Settings > Secrets and variables > Actions > tab 'Secrets'.\n"
            "2. Nhầm phạm vi: Bạn đã tạo trong 'Environment secrets' thay vì 'Repository secrets'.\n"
            "   -> Cần tạo ở mục 'Repository secrets' (phía dưới của trang).\n"
            "3. Sai tên chính xác: Tên Secret phải là chính xác 'GEMINI_API_KEY'.\n"
            "4. PR từ Fork: Nếu PR tạo từ tài khoản fork, GitHub sẽ ẩn secret vì bảo mật.\n"
            + "=" * 70 + "\n"
        )
        return 1

    # 3. Tầng 2: Semantic Review bằng Gemini LLM
    reviewer = GeminiReviewer(
        api_key=config.gemini_api_key,
        model=config.gemini_model,
        guidelines_path=config.guidelines_path,
    )


    review_res = reviewer.review_diffs(file_diffs)
    logger.info(f"Hoàn thành review: {review_res.status} ({len(review_res.comments)} nhận xét).")

    # 4. Xuất kết quả
    if config.dry_run or not config.github_token or not config.pr_number:
        poster.print_dry_run(linter_res, review_res=review_res, output_file=Path(args.output))
    else:
        logger.info("Đang gửi kết quả review lên GitHub PR...")
        poster.post_to_github(linter_res, review_res=review_res)

    if args.fail_on_changes and review_res.status == "CHANGES_REQUESTED":
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
