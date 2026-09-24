"""Tier 2: Gemini LLM Reviewer.
Interacts with Google Gemini REST API to analyze diffs against project guidelines
and returns validated structured review comments.
"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path
import requests

from .git_diff_extractor import FileDiff

logger = logging.getLogger(__name__)


@dataclass
class ReviewComment:
    file_path: str
    line_number: int
    severity: str  # CRITICAL, WARNING, INFO
    rule_id: str
    comment: str
    suggestion: str = ""

    def to_markdown(self) -> str:
        badge = {
            "CRITICAL": "🚨 **[CRITICAL]**",
            "WARNING": "⚠️ **[WARNING]**",
            "INFO": "💡 **[INFO]**",
        }.get(self.severity, "🔍 **[NOTE]**")

        md = f"{badge} **{self.rule_id}**: {self.comment}\n"
        if self.suggestion:
            md += f"\n```suggestion\n{self.suggestion}\n```\n"
        return md


@dataclass
class ReviewResult:
    status: str  # "APPROVED", "CHANGES_REQUESTED", "COMMENT"
    summary: str
    comments: list[ReviewComment]


class GeminiReviewer:
    GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str, model: str = "gemini-3.6-flash", guidelines_path: Path | None = None):
        self.api_key = api_key
        self.model = model
        self.guidelines_content = ""
        if guidelines_path and guidelines_path.is_file():
            self.guidelines_content = guidelines_path.read_text(encoding="utf-8")

    def review_diffs(self, file_diffs: list[FileDiff]) -> ReviewResult:
        if not file_diffs:
            return ReviewResult(status="APPROVED", summary="Không có thay đổi mã nguồn nào cần review.", comments=[])

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY chưa được thiết lập. Vui lòng cung cấp API key để chạy Tier 2 Review.")

        # Build prompt payload
        system_instruction = (
            "Bạn là Antigravity Senior Staff Engineer và Tech Lead đang thực hiện Code Review trên Git Pull Request.\n"
            "Nhiệm vụ của bạn là phát hiện các lỗi nghiêm trọng về logic nghiệp vụ, bảo mật, leak tài nguyên, "
            "và vi phạm quy chuẩn nội bộ.\n\n"
            "BỘ QUY TẮC NỘI BỘ THAM CHIẾU (AI_REVIEW_GUIDELINES.md):\n"
            f"{self.guidelines_content}\n\n"
            "NGUYÊN TẮC REVIEW QUAN TRỌNG:\n"
            "1. CHỈ đưa ra nhận xét trên các dòng code ĐƯỢC THÊM MỚI HOẶC CHỈNH SỬA (dòng bắt đầu bằng dấu +).\n"
            "2. Tuyệt đối không nhận xét các vấn đề formatting/style vụn vặt (đã có linter tự động xử lý).\n"
            "3. line_number BẮT BUỘC phải nằm trong danh sách `valid_lines` được cung cấp cho từng file.\n"
            "4. Đưa ra gợi ý code cụ thể trong trường `suggestion` nếu có thể.\n"
            "5. Phải trả về JSON đúng cấu trúc được yêu cầu."
        )

        # Prepare diff context for each file
        diff_payload = []
        for fd in file_diffs:
            # Skip pure deletes or non-code files if desired
            if fd.is_deleted or not fd.valid_new_lines:
                continue

            diff_payload.append({
                "file_path": fd.file_path,
                "valid_lines": sorted(list(fd.valid_new_lines)),
                "raw_diff": fd.raw_diff,
            })

        if not diff_payload:
            return ReviewResult(status="APPROVED", summary="Các file thay đổi là xóa file hoặc không có dòng thêm mới.", comments=[])

        user_content = (
            "Hãy phân tích các file diff sau đây và trả về danh sách nhận xét review dưới dạng JSON array:\n\n"
            f"{json.dumps(diff_payload, indent=2, ensure_ascii=False)}\n\n"
            "Định dạng JSON yêu cầu:\n"
            "{\n"
            '  "summary": "Tóm tắt ngắn gọn 1-2 câu về chất lượng PR",\n'
            '  "status": "APPROVED" | "CHANGES_REQUESTED" | "COMMENT",\n'
            '  "comments": [\n'
            "    {\n"
            '      "file_path": "đường_dẫn_file",\n'
            '      "line_number": 123,\n'
            '      "severity": "CRITICAL" | "WARNING" | "INFO",\n'
            '      "rule_id": "RULE-SEC-01",\n'
            '      "comment": "Giải thích lỗi cụ thể và lý do vi phạm",\n'
            '      "suggestion": "Đoạn code sửa đổi khuyến nghị (nếu có)"\n'
            "    }\n"
            "  ]\n"
            "}"
        )

        url = f"{self.GEMINI_API_URL.format(model=self.model)}?key={self.api_key}"
        headers = {"Content-Type": "application/json"}
        body = {
            "contents": [{"role": "user", "parts": [{"text": user_content}]}],
            "systemInstruction": {"parts": [{"text": system_instruction}]},
            "generationConfig": {
                "temperature": 0.1,
                "responseMimeType": "application/json",
            },
        }

        try:
            resp = requests.post(url, headers=headers, json=body, timeout=60)
            if resp.status_code != 200:
                raise RuntimeError(f"Gemini API Error [{resp.status_code}]: {resp.text}")

            result_json = resp.json()
            candidates = result_json.get("candidates", [])
            if not candidates:
                return ReviewResult(status="COMMENT", summary="LLM không trả về kết quả đánh giá.", comments=[])

            raw_text = candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "{}")
            parsed = json.loads(raw_text)

            # Build line validator lookup: {file_path: set(valid_lines)}
            valid_lines_map = {fd.file_path: fd.valid_new_lines for fd in file_diffs}

            validated_comments: list[ReviewComment] = []
            for item in parsed.get("comments", []):
                fp = item.get("file_path", "")
                line = int(item.get("line_number", 0))
                severity = item.get("severity", "INFO").upper()

                # Validate line number
                if fp in valid_lines_map and valid_lines_map[fp]:
                    valid_set = valid_lines_map[fp]
                    if line not in valid_set:
                        # Find closest line in valid_set
                        line = min(valid_set, key=lambda x: abs(x - line))

                validated_comments.append(
                    ReviewComment(
                        file_path=fp,
                        line_number=line,
                        severity=severity,
                        rule_id=item.get("rule_id", "GENERAL"),
                        comment=item.get("comment", ""),
                        suggestion=item.get("suggestion", ""),
                    )
                )

            # Determine final status
            has_critical = any(c.severity == "CRITICAL" for c in validated_comments)
            has_warning = any(c.severity == "WARNING" for c in validated_comments)

            status = "CHANGES_REQUESTED" if has_critical else ("COMMENT" if has_warning else "APPROVED")
            summary = parsed.get("summary", "Đã hoàn thành đánh giá mã nguồn.")

            return ReviewResult(status=status, summary=summary, comments=validated_comments)

        except Exception as e:
            logger.exception("Lỗi trong quá trình gọi Gemini Reviewer: %s", e)
            return ReviewResult(
                status="COMMENT",
                summary=f"Không thể hoàn thành review do lỗi: {str(e)}",
                comments=[],
            )
