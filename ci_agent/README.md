# AI Code Review Agent (PoC / In-House Version)

Hệ thống Agent tự động review code cho Pull Request tích hợp vào CI/CD (GitHub Actions), vận hành theo mô hình 2 tầng (2-Tier Pipeline) tinh gọn và an toàn bảo mật.

---

## 🌟 Cấu trúc Thư mục

```
ci_agent/
├── AI_REVIEW_GUIDELINES.md   # Bộ quy tắc review nội bộ (Rules, Bad/Good examples)
├── config.py                 # Quản lý cấu hình & environment variables
├── tier1_linter.py           # Tầng 1: Deterministic Gate (Syntax, Secret scan, Ruff)
├── git_diff_extractor.py     # Trích xuất & parse diff, xác định các dòng code sửa đổi
├── gemini_reviewer.py        # Tầng 2: Gọi Gemini API & tạo structured review comments
├── github_poster.py          # Format Markdown report & post inline comments lên GitHub PR
├── main.py                   # Entrypoint CLI điều phối toàn bộ workflow
└── README.md                 # Tài liệu hướng dẫn sử dụng
```

---

## 🚀 Hướng dẫn Sử dụng

### 1. Kiểm tra Cục bộ (Local Dry-run)

Bạn có thể chạy thử nghiệm ngay trên máy local mà không cần đẩy code lên GitHub PR. Kết quả sẽ được in ra Terminal và lưu vào file `review_report.md`:

```bash
# 1. Thiết lập Gemini API Key (nếu chạy Tầng 2 AI Review)
export GEMINI_API_KEY="your-gemini-api-key"
# Trên Windows PowerShell:
# $env:GEMINI_API_KEY="your-gemini-api-key"

# 2. Chạy dry-run so sánh với nhánh main:
python -m ci_agent.main --dry-run --base origin/main
```

Nếu chưa có Gemini API Key, bạn vẫn có thể chạy để test **Tầng 1 (Linter & Syntax check)**:
```bash
python -m ci_agent.main --dry-run
```

---

### 2. Thiết lập trên GitHub Actions

1. Vào repository trên GitHub: **Settings** -> **Secrets and variables** -> **Actions**.
2. Nhấn **New repository secret**:
   - Name: `GEMINI_API_KEY`
   - Value: `<API Key Google Gemini của bạn>`
3. File workflow `.github/workflows/ai_code_review.yml` đã được cấu hình sẵn. Khi có Pull Request mở vào nhánh `main`, bot sẽ tự động phân tích và post inline comments vào đúng các dòng vi phạm.

---

## ⚙️ Tùy biến Quy tắc Review

Để bổ sung thêm luật review của team/công ty, bạn chỉ cần chỉnh sửa file [ci_agent/AI_REVIEW_GUIDELINES.md](AI_REVIEW_GUIDELINES.md). Agent sẽ tự động nạp các luật mới vào System Prompt trong các lần review tiếp theo mà không cần sửa code Python.
