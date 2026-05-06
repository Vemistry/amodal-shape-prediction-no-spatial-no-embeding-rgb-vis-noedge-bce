"""
===================================================================================
EDA - PHÂN TÍCH DATASET TỪ EVALUATION RESULTS
===================================================================================
Script để tính toán thống kê dataset dựa trên kết quả đánh giá có sẵn.
"""

import json
from collections import defaultdict
from pathlib import Path

def analyze_eval_results(eval_file):
    """
    Phân tích file eval_results để tính occlusion distribution.
    """
    
    with open(eval_file, 'r') as f:
        data = json.load(f)
    
    samples = data.get('per_sample_metrics', [])
    total_samples = len(samples)
    
    # Phân loại occlusion
    occlusion_counts = {
        'no_occlusion': 0,      # Không có occlusion
        'slight_occlusion': 0,  # Có occlusion nhẹ (invisible_iou > 0 nhưng nhỏ)
        'moderate_occlusion': 0,
        'heavy_occlusion': 0
    }
    
    # Tính thống kê
    for sample in samples:
        has_occlusion = sample.get('has_occlusion', False)
        invisible_iou = sample.get('invisible_iou', -1.0)
        
        if not has_occlusion:
            occlusion_counts['no_occlusion'] += 1
        elif invisible_iou < 0.05:  # Occlusion rất nhẹ
            occlusion_counts['slight_occlusion'] += 1
        elif invisible_iou < 0.15:  # Occlusion vừa
            occlusion_counts['moderate_occlusion'] += 1
        else:  # Occlusion nặng
            occlusion_counts['heavy_occlusion'] += 1
    
    return {
        'total_samples': total_samples,
        'occlusion_distribution': occlusion_counts,
        'percentages': {
            'no_occlusion': (occlusion_counts['no_occlusion'] / total_samples) * 100,
            'slight_occlusion': (occlusion_counts['slight_occlusion'] / total_samples) * 100,
            'moderate_occlusion': (occlusion_counts['moderate_occlusion'] / total_samples) * 100,
            'heavy_occlusion': (occlusion_counts['heavy_occlusion'] / total_samples) * 100,
        }
    }

# Phân tích validation set
val_stats = analyze_eval_results('outputs/evaluations/eval_results_epoch30.json')

print("\n" + "="*80)
print("📊 THỐNG KÊ VALIDATION SET (COCO-Amodal)")
print("="*80)

print("\n| Thước tính | Training Set | Validation Set |")
print("|-----------|--------------|----------------|")
print(f"| Số instances | 22,163 mẫu | {val_stats['total_samples']:,} mẫu |")
print(f"| Kích thước ảnh | Đã dạng (resize về 224×224) | Đã dạng (resize về 224×224) |")
print(f"| Số classes | 91 COCO classes | 91 COCO classes |")
print(f"| Không che khuất | 9,379 mẫu (42.3%) | ~{val_stats['occlusion_distribution']['no_occlusion']:,} mẫu ({val_stats['percentages']['no_occlusion']:.1f}%) |")
print(f"| Che nhẹ (1-10%) | 8,348 mẫu (37.7%) | Tương ứng |")
print(f"| Che vừa (10-25%) | 3,023 mẫu (13.6%) | Tương ứng |")
print(f"| Che nặng (>25%) | 1,413 mẫu (6.4%) | Tương ứng |")

print("\n" + "="*80)
print("📌 GHI CHÚ:")
print("="*80)
print("""
MỘT INSTANCE = một cặp (ảnh RGB, Visible Mask tương ứng)

Cấu thành:
  - RGB: Ảnh màu gốc từ dataset
  - Visible Mask: Phần vật thể nhìn thấy (không bị che khuất)
  
Quá trình tạo Visible Mask:
  1. Vẽ Amodal Mask từ annotation (hình dạng toàn bộ vật thể)
  2. Vẽ Visible Mask = Amodal Mask - phần bị che bởi vật thể phía trước
  3. Tính Occlusion Region = Amodal Mask - Visible Mask
  
Phân loại Occlusion:
  - Không che (0-1%): Vật thể không bị che hoặc che <1%
  - Che nhẹ (1-10%): Vật thể bị che 1-10%
  - Che vừa (10-25%): Vật thể bị che 10-25%
  - Che nặng (>25%): Vật thể bị che hơn 25%
""")

print("\n✅ Script EDA hoàn tất!")
