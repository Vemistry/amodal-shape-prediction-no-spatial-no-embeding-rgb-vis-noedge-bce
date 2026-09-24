# BỘ QUY TẮC CODE REVIEW NỘI BỘ (AI_REVIEW_GUIDELINES.md)

Tài liệu này chứa các quy tắc chuẩn hóa của dự án. AI Code Review Agent sẽ dựa vào các quy tắc này để phân tích và đánh giá các Pull Request.

---

## 1. BẢO MẬT & DỮ LIỆU (SECURITY & DATA PRIVACY)

### [RULE-SEC-01] Không Hardcode Thông Tin Nhạy Cảm (Secrets & Credentials)
- **Mức độ:** `CRITICAL`
- **Mô tả:** Tuyệt đối không lưu API Key, Password, Token, Database URI, hoặc Secret Key trực tiếp trong mã nguồn. Mọi cấu hình phải lấy từ Environment Variables hoặc Config file được `.gitignore`.
- **Bad:**
  ```python
  GEMINI_API_KEY = "AIzaSyD-sample-fake-key-12345"
  DB_URL = "postgresql://admin:secret123@localhost:5432/app_db"
  ```
- **Good:**
  ```python
  import os
  GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
  if not GEMINI_API_KEY:
      raise ValueError("GEMINI_API_KEY environment variable is not set")
  ```

### [RULE-SEC-02] Ngăn Ngừa Lỗ Hổng Command/SQL/Path Injection
- **Mức độ:** `CRITICAL`
- **Mô tả:** Không sử dụng chuỗi nội suy (f-string, format) trực tiếp vào các hàm thực thi hệ thống (`os.system`, `subprocess.Popen(..., shell=True)`) hoặc SQL raw queries. Luôn validate và sanitize dữ liệu đầu vào.
- **Bad:**
  ```python
  import os
  os.system(f"rm -rf {user_provided_dir}")
  ```
- **Good:**
  ```python
  import subprocess
  from pathlib import Path
  safe_dir = Path(user_provided_dir).resolve()
  subprocess.run(["rm", "-rf", str(safe_dir)], check=True)
  ```

---

## 2. KIẾN TRÚC & TÍNH TOÀN VẸN LOGIC (ARCHITECTURE & LOGIC)

### [RULE-ARCH-01] Xử Lý Ngoại Lệ Cụ Thể (Avoid Bare Except)
- **Mức độ:** `WARNING`
- **Mô tả:** Không bao giờ sử dụng `except:` trần trụi hoặc `except Exception: pass` mà không ghi log hay re-raise. Việc nuốt lỗi này sẽ che giấu các bug nghiêm trọng (như `KeyboardInterrupt`, `MemoryError`, lỗi logic).
- **Bad:**
  ```python
  try:
      model.load_weights(weights_path)
  except:
      pass
  ```
- **Good:**
  ```python
  import logging
  try:
      model.load_weights(weights_path)
  except FileNotFoundError as e:
      logging.error(f"Weights file not found at {weights_path}: {e}")
      raise
  except Exception as e:
      logging.exception(f"Unexpected error loading weights: {e}")
      raise
  ```

### [RULE-ARCH-02] Đảm Bảo Giải Phóng Tài Nguyên (Resource Management)
- **Mức độ:** `WARNING`
- **Mô tả:** Khi mở file, kết nối mạng, hoặc tài nguyên GPU/Thread, luôn sử dụng Context Manager (`with` statement) để đảm bảo tài nguyên được giải phóng ngay cả khi xảy ra Exception.
- **Bad:**
  ```python
  f = open("results.txt", "w")
  f.write(data)
  f.close() # Sẽ bị leak nếu write() sinh lỗi
  ```
- **Good:**
  ```python
  with open("results.txt", "w", encoding="utf-8") as f:
      f.write(data)
  ```

### [RULE-ARCH-03] Kiểm Soát Tác Vụ Tính Toán Lớn & GPU Memory
- **Mức độ:** `WARNING`
- **Mô tả:** Đối với code PyTorch/Machine Learning, khi thực hiện inference/evaluation, bắt buộc phải sử dụng `torch.no_grad()` hoặc `@torch.inference_mode()` để tránh lưu computational graph gây OOM (Out Of Memory) GPU.
- **Bad:**
  ```python
  def evaluate(model, loader):
      model.eval()
      for images, masks in loader:
          outputs = model(images)
  ```
- **Good:**
  ```python
  import torch
  @torch.inference_mode()
  def evaluate(model, loader):
      model.eval()
      for images, masks in loader:
          outputs = model(images)
  ```

---

## 3. HIỆU NĂNG & ĐỘ ỔN ĐỊNH (PERFORMANCE & RELIABILITY)

### [RULE-PERF-01] Tránh Vòng Lặp Không Cần Thiết Trên Dữ Liệu Lớn
- **Mức độ:** `INFO`
- **Mô tả:** Trong Python/NumPy, hạn chế dùng vòng lặp Python thuần (`for`) duyệt qua từng pixel hoặc từng phần tử mảng khi có thể dùng vectorization của NumPy hoặc PyTorch.
- **Bad:**
  ```python
  for i in range(h):
      for j in range(w):
          mask[i, j] = 1 if mask[i, j] > 0.5 else 0
  ```
- **Good:**
  ```python
  mask = (mask > 0.5).astype(np.uint8)
  ```

---

## 4. QUY ƯỚC CHUẨN ĐOÁN & PHẢN HỒI (REVIEW OUTPUT RULES)

Khi AI phát hiện vi phạm:
1. **Chỉ nhận xét trên các dòng code có thay đổi trong PR** (không comment vào code cũ không liên quan).
2. **Cung cấp gợi ý sửa cụ thể (Code Suggestion)** đi kèm giải thích ngắn gọn, súc tích.
3. **Phân loại Severity chính xác:**
   - `CRITICAL`: Lỗi bảo mật, leak secret, bug logic làm crash hệ thống, phá vỡ hợp đồng dữ liệu.
   - `WARNING`: Code smell, thiếu try-catch, leak tài nguyên, có nguy cơ gây lỗi ở edge cases.
   - `INFO`: Tối ưu hiệu năng, clean code, giải pháp thay thế thanh lịch hơn.
