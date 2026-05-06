"""
===================================================================================
EDA - EXPLORATORY DATA ANALYSIS: THỐNG KÊ COCO-AMODAL DATASET
===================================================================================
Script để phân tích và thống kê dataset:
- Số instances (một instance = một ảnh RGB + Visible Mask tương ứng)
- Phân bố occlusion (không che, che nhẹ, che vừa, che nặng)
- Số classes
- Kích thước ảnh

Chạy:
  python scripts/eda_dataset_statistics.py --ann-file data/annotations/COCO_amodal_train2014.json
  python scripts/eda_dataset_statistics.py --ann-file data/annotations/COCO_amodal_val2014.json
===================================================================================
"""

import argparse
import json
import cv2
import numpy as np
from pathlib import Path
from collections import defaultdict
from pycocotools.coco import COCO
from tqdm import tqdm


def analyze_dataset(ann_file, img_dir=None):
    """
    Phân tích chi tiết dataset COCO-Amodal.
    
    Args:
        ann_file: Đường dẫn file annotation JSON
        img_dir: Đường dẫn thư mục chứa ảnh (tùy chọn)
    
    Returns:
        Dict chứa tất cả thống kê
    """
    
    print(f"\n📂 Đang tải annotation file: {ann_file}")
    
    # Kiểm tra file tồn tại
    if not Path(ann_file).exists():
        print(f"❌ File không tồn tại: {ann_file}")
        return None
    
    # Tải annotation
    with open(ann_file, 'r') as f:
        data = json.load(f)
    
    print(f"✅ Đã tải xong annotation file!")
    
    # ─────────────────────────────────────────────────────────────────
    # PHÂN TÍCH CƠ BẢN
    # ─────────────────────────────────────────────────────────────────
    
    total_images = len(data.get('images', []))
    total_annotations = len(data.get('annotations', []))
    total_categories = len(data.get('categories', []))
    
    print(f"\n📊 THỐNG KÊ CƠ BẢN:")
    print(f"  - Tổng ảnh: {total_images}")
    print(f"  - Tổng annotations: {total_annotations}")
    print(f"  - Tổng classes: {total_categories}")
    
    # ─────────────────────────────────────────────────────────────────
    # TÍNH TOÁN INSTANCES & OCCLUSION
    # ─────────────────────────────────────────────────────────────────
    
    print(f"\n🔍 Đang phân tích occlusion distribution...")
    
    instances_count = 0
    occlusion_stats = {
        'no_occlusion': 0,      # 0-1%
        'slight_occlusion': 0,  # 1-10%
        'moderate_occlusion': 0,  # 10-25%
        'heavy_occlusion': 0    # >25%
    }
    
    instance_occlusions = []  # Lưu độ che của từng instance
    
    coco = COCO(ann_file)
    
    # Duyệt qua tất cả annotations
    for ann_id, ann in tqdm(coco.anns.items(), desc="Processing annotations"):
        
        # Kiểm tra xem annotation có "regions" (đặc tính amodal)
        if "regions" not in ann:
            continue
        
        # Lấy thông tin ảnh
        img_id = ann.get("image_id")
        img_info = coco.imgs.get(img_id)
        
        if img_info is None:
            continue
        
        # Duyệt qua từng region (vật thể) trong annotation
        for region_idx, region in enumerate(ann["regions"]):
            
            # Chỉ lấy region có segmentation
            if "segmentation" not in region:
                continue
            
            instances_count += 1
            
            # ──────────────────────────────────────────────────────────
            # TÍNH OCCLUSION RATIO
            # ──────────────────────────────────────────────────────────
            
            # Lấy thông tin ảnh
            height = img_info.get('height', 0)
            width = img_info.get('width', 0)
            
            if height == 0 or width == 0:
                continue
            
            # Vẽ amodal mask
            amodal_mask = np.zeros((height, width), dtype=np.uint8)
            target_segs = region.get("segmentation", [])
            
            if isinstance(target_segs, list) and len(target_segs) > 0:
                if isinstance(target_segs[0], (int, float)):
                    target_segs = [target_segs]
                
                for poly in target_segs:
                    if len(poly) >= 6:
                        poly_2d = np.array(poly).reshape(-1, 2).astype(np.int32)
                        cv2.fillPoly(amodal_mask, [poly_2d], 1)
            
            # Vẽ visible mask
            visible_mask = amodal_mask.copy()
            target_order = region.get("order", 0)
            
            for other_region in ann["regions"]:
                other_order = other_region.get("order", 0)
                
                if other_order < target_order and "segmentation" in other_region:
                    other_segs = other_region["segmentation"]
                    
                    if isinstance(other_segs, list) and len(other_segs) > 0:
                        if isinstance(other_segs[0], (int, float)):
                            other_segs = [other_segs]
                        
                        for poly in other_segs:
                            if len(poly) >= 6:
                                poly_2d = np.array(poly).reshape(-1, 2).astype(np.int32)
                                cv2.fillPoly(visible_mask, [poly_2d], 0)
            
            # Tính occlusion ratio
            amodal_pixels = np.sum(amodal_mask)
            visible_pixels = np.sum(visible_mask)
            occluded_pixels = amodal_pixels - visible_pixels
            
            if amodal_pixels > 0:
                occlusion_ratio = occluded_pixels / amodal_pixels
            else:
                occlusion_ratio = 0.0
            
            instance_occlusions.append(occlusion_ratio)
            
            # Phân loại occlusion
            if occlusion_ratio < 0.01:  # < 1%
                occlusion_stats['no_occlusion'] += 1
            elif occlusion_ratio < 0.10:  # 1-10%
                occlusion_stats['slight_occlusion'] += 1
            elif occlusion_ratio < 0.25:  # 10-25%
                occlusion_stats['moderate_occlusion'] += 1
            else:  # > 25%
                occlusion_stats['heavy_occlusion'] += 1
    
    # ─────────────────────────────────────────────────────────────────
    # TÍNH TOÁN PHÂN BỐ CLASSES
    # ─────────────────────────────────────────────────────────────────
    
    print(f"\n📈 Đang phân tích phân bố classes...")
    
    class_distribution = defaultdict(int)
    
    for ann_id, ann in tqdm(coco.anns.items(), desc="Counting classes"):
        if "regions" in ann:
            for region_idx, region in enumerate(ann["regions"]):
                if "segmentation" in region:
                    cat_id = ann.get("category_id", 0)
                    class_distribution[cat_id] += 1
    
    # ─────────────────────────────────────────────────────────────────
    # TÍNH TOÁN KÍCH THƯỚC ẢNH
    # ─────────────────────────────────────────────────────────────────
    
    image_sizes = []
    for img_id, img_info in coco.imgs.items():
        h = img_info.get('height', 0)
        w = img_info.get('width', 0)
        if h > 0 and w > 0:
            image_sizes.append((w, h))
    
    avg_width = np.mean([w for w, h in image_sizes]) if image_sizes else 0
    avg_height = np.mean([h for w, h in image_sizes]) if image_sizes else 0
    
    # ─────────────────────────────────────────────────────────────────
    # TỔNG HỢP KẾT QUẢ
    # ─────────────────────────────────────────────────────────────────
    
    stats = {
        'total_instances': instances_count,
        'total_images': total_images,
        'total_classes': total_categories,
        'avg_image_width': avg_width,
        'avg_image_height': avg_height,
        'occlusion_distribution': occlusion_stats,
        'class_distribution': dict(sorted(class_distribution.items())),
        'occlusion_percentages': {
            'no_occlusion': (occlusion_stats['no_occlusion'] / max(1, instances_count)) * 100,
            'slight_occlusion': (occlusion_stats['slight_occlusion'] / max(1, instances_count)) * 100,
            'moderate_occlusion': (occlusion_stats['moderate_occlusion'] / max(1, instances_count)) * 100,
            'heavy_occlusion': (occlusion_stats['heavy_occlusion'] / max(1, instances_count)) * 100,
        }
    }
    
    return stats


def print_statistics_table(stats):
    """
    In thống kê theo dạng bảng dạng Markdown.
    """
    
    if stats is None:
        return
    
    print("\n" + "="*80)
    print("📊 BẢNG THỐNG KÊ DATASET")
    print("="*80)
    
    # Chuyển đổi phân bố occlusion sang phần trăm
    occ_dist = stats['occlusion_distribution']
    total = stats['total_instances']
    
    print("\n| Thước tính | Giá trị |")
    print("|-----------|--------|")
    print(f"| Số instances | {stats['total_instances']:,} mẫu |")
    print(f"| Kích thước ảnh | Đã dạng (resize về 224×224) |")
    print(f"| Số classes | {stats['total_classes']} COCO classes |")
    print(f"| Không che khuất | {occ_dist['no_occlusion']:,} mẫu ({stats['occlusion_percentages']['no_occlusion']:.1f}%) |")
    print(f"| Che nhẹ (1-10%) | {occ_dist['slight_occlusion']:,} mẫu ({stats['occlusion_percentages']['slight_occlusion']:.1f}%) |")
    print(f"| Che vừa (10-25%) | {occ_dist['moderate_occlusion']:,} mẫu ({stats['occlusion_percentages']['moderate_occlusion']:.1f}%) |")
    print(f"| Che nặng (>25%) | {occ_dist['heavy_occlusion']:,} mẫu ({stats['occlusion_percentages']['heavy_occlusion']:.1f}%) |")
    
    print("\n" + "="*80)
    print("📌 GHI CHÚ VỀ INSTANCES:")
    print("="*80)
    print("""
- MỘT INSTANCE = một cặp (ảnh RGB, Visible Mask tương ứng)
- Visible Mask là phần của vật thể nhìn thấy (không bị che khuất)
- Amodal Mask là hình dạng toàn bộ của vật thể (bao gồm phần bị che)
- Occlusion Region = Amodal Mask - Visible Mask

VÍ DỤ:
  - Một ảnh chứa 3 vật thể → 3 instances
  - Mỗi instance được xử lý riêng biệt trong training
  - Nếu vật thể 1 bị che 20%, nó sẽ được phân loại vào "Che vừa (10-25%)"
""")


def print_statistics_detailed(stats):
    """
    In thống kê chi tiết hơn.
    """
    
    if stats is None:
        return
    
    print("\n" + "="*80)
    print("📊 CHI TIẾT PHÂN BỐ OCCLUSION")
    print("="*80)
    
    occ_dist = stats['occlusion_distribution']
    percentages = stats['occlusion_percentages']
    
    print(f"\nKhông che khuất (0-1%):    {occ_dist['no_occlusion']:>6,} mẫu ({percentages['no_occlusion']:>5.1f}%)")
    print(f"Che nhẹ (1-10%):           {occ_dist['slight_occlusion']:>6,} mẫu ({percentages['slight_occlusion']:>5.1f}%)")
    print(f"Che vừa (10-25%):          {occ_dist['moderate_occlusion']:>6,} mẫu ({percentages['moderate_occlusion']:>5.1f}%)")
    print(f"Che nặng (>25%):           {occ_dist['heavy_occlusion']:>6,} mẫu ({percentages['heavy_occlusion']:>5.1f}%)")
    print(f"{'─'*50}")
    print(f"Tổng cộng:                {stats['total_instances']:>6,} mẫu (100.0%)")
    
    print(f"\n📏 Thông tin ảnh:")
    print(f"  - Chiều rộng trung bình: {stats['avg_image_width']:.0f} pixels")
    print(f"  - Chiều cao trung bình: {stats['avg_image_height']:.0f} pixels")
    print(f"  - Tổng ảnh: {stats['total_images']:,}")


def main():
    """Điểm khởi chạy chương trình."""
    
    parser = argparse.ArgumentParser(description='EDA - Phân tích Dataset COCO-Amodal')
    parser.add_argument(
        '--ann-file',
        type=str,
        required=True,
        help='Đường dẫn file annotation JSON'
    )
    parser.add_argument(
        '--img-dir',
        type=str,
        default=None,
        help='Đường dẫn thư mục chứa ảnh (tùy chọn)'
    )
    
    args = parser.parse_args()
    
    # Phân tích dataset
    stats = analyze_dataset(args.ann_file, args.img_dir)
    
    if stats:
        # In bảng thống kê
        print_statistics_table(stats)
        print_statistics_detailed(stats)
        
        # Lưu kết quả vào JSON
        output_file = Path(args.ann_file).parent / "dataset_statistics.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(stats, f, ensure_ascii=False, indent=2)
        
        print(f"\n💾 Kết quả được lưu tại: {output_file}")
    else:
        print("❌ Không thể phân tích dataset!")


if __name__ == "__main__":
    main()
