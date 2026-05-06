"""
===================================================================================
THỐNG KÊ DATASET - Tính toán trực tiếp từ COCO-Amodal Annotation
===================================================================================
Script này phân tích dataset thực và tính ra các thống kê:
- Số instances
- Phân bố occlusion (không che, che nhẹ, che vừa, che nặng)
- Kích thước ảnh
- Số classes
"""

import json
import os
import numpy as np
import cv2
from collections import defaultdict
from pycocotools.coco import COCO


def calculate_occlusion_ratio(amodal_mask, visible_mask):
    """Tính tỷ lệ che khuất (occlusion ratio)"""
    amodal_area = np.sum(amodal_mask)
    if amodal_area == 0:
        return 0.0
    
    occluded_area = amodal_area - np.sum(visible_mask)
    return float(occluded_area / amodal_area)


def create_visible_mask(ann, target_region, height, width):
    """Tạo visible mask từ amodal mask và các vật thể phía trước"""
    # Vẽ amodal mask
    amodal_mask = np.zeros((height, width), dtype=np.uint8)
    segs = target_region["segmentation"]
    if isinstance(segs, list) and len(segs) > 0:
        if isinstance(segs[0], (int, float)):
            segs = [segs]
        for poly in segs:
            if len(poly) >= 6:
                poly_2d = np.array(poly).reshape(-1, 2).astype(np.int32)
                cv2.fillPoly(amodal_mask, [poly_2d], 1)
    
    # Vẽ visible mask (xóa phần bị che)
    visible_mask = amodal_mask.copy()
    target_order = target_region.get("order", 0)
    
    for other_region in ann["regions"]:
        other_order = other_region.get("order", 0)
        if other_order < target_order and "segmentation" in other_region:
            segs = other_region["segmentation"]
            if isinstance(segs, list) and len(segs) > 0:
                if isinstance(segs[0], (int, float)):
                    segs = [segs]
                for poly in segs:
                    if len(poly) >= 6:
                        poly_2d = np.array(poly).reshape(-1, 2).astype(np.int32)
                        cv2.fillPoly(visible_mask, [poly_2d], 0)
    
    return amodal_mask, visible_mask


def analyze_dataset(img_dir, ann_file):
    """Phân tích dataset và tính thống kê"""
    
    print(f"\n{'='*70}")
    print(f"📊 PHÂN TÍCH DATASET COCO-AMODAL")
    print(f"{'='*70}\n")
    
    # Kiểm tra file annotation
    if not os.path.exists(ann_file):
        print(f"❌ Lỗi: File annotation không tìm thấy: {ann_file}")
        print(f"Hãy đảm bảo dataset đã được download.")
        return
    
    print(f"📂 Đang nạp annotation file: {ann_file}")
    coco = COCO(ann_file)
    
    # ─────────────────────────────────────────────────────────────────
    # BƯỚC 1: Bóc tách instances
    # ─────────────────────────────────────────────────────────────────
    instances = []
    for ann_id, ann in coco.anns.items():
        if "regions" in ann:
            for region_idx, region in enumerate(ann["regions"]):
                if "segmentation" in region:
                    instances.append((ann_id, region_idx))
    
    total_samples = len(instances)
    print(f"✅ Đã bóc tách {total_samples} instances từ annotation")
    
    # ─────────────────────────────────────────────────────────────────
    # BƯỚC 2: Tính toán thống kê cho từng instance
    # ─────────────────────────────────────────────────────────────────
    occlusion_ratios = []
    img_sizes = []
    class_counts = defaultdict(int)
    
    # Lấy tên classes
    cat_id_to_name = {cat['id']: cat['name'] for cat in coco.dataset['categories']}
    
    print(f"\n🔍 Đang phân tích {total_samples} instances...")
    print("   (Điều này có thể mất một chút thời gian..)\n")
    
    for idx, (ann_id, region_idx) in enumerate(instances):
        if (idx + 1) % 5000 == 0:
            print(f"   Đã xử lý: {idx + 1}/{total_samples}")
        
        ann = coco.anns[ann_id]
        target_region = ann["regions"][region_idx]
        
        # Lấy class ID
        cat_id = target_region.get("category_id", ann.get("category_id"))
        class_counts[cat_id] += 1
        
        # Lấy thông tin ảnh
        img_id = ann["image_id"]
        img_info = coco.loadImgs([img_id])[0]
        img_h, img_w = img_info["height"], img_info["width"]
        img_sizes.append((img_h, img_w))
        
        # Tính occlusion ratio
        # (Chỉ tính từ masks, không cần đọc file ảnh)
        amodal_mask, visible_mask = create_visible_mask(ann, target_region, img_h, img_w)
        occlusion_ratio = calculate_occlusion_ratio(amodal_mask, visible_mask)
        occlusion_ratios.append(occlusion_ratio)
    
    # ─────────────────────────────────────────────────────────────────
    # BƯỚC 3: Phân loại theo mức độ che khuất
    # ─────────────────────────────────────────────────────────────────
    occlusion_ratios = np.array(occlusion_ratios)
    
    no_occlusion = np.sum(occlusion_ratios == 0)
    light_occlusion = np.sum((occlusion_ratios > 0) & (occlusion_ratios <= 0.1))
    medium_occlusion = np.sum((occlusion_ratios > 0.1) & (occlusion_ratios <= 0.25))
    heavy_occlusion = np.sum(occlusion_ratios > 0.25)
    
    # ─────────────────────────────────────────────────────────────────
    # BƯỚC 4: Hiển thị kết quả
    # ─────────────────────────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"📈 THỐNG KÊ DATASET")
    print(f"{'='*70}\n")
    
    print(f"🔢 Số instances: {total_samples:,} mẫu\n")
    
    # Kích thước ảnh
    unique_sizes = set(img_sizes)
    print(f"📐 Kích thước ảnh:")
    for size in sorted(unique_sizes):
        count = img_sizes.count(size)
        pct = 100 * count / len(img_sizes)
        print(f"   - {size[0]}×{size[1]}: {count:,} ảnh ({pct:.1f}%)")
    
    print(f"\n🎨 Số classes: {len(class_counts)} COCO classes\n")
    
    # Phân bố occlusion
    print(f"🚫 Phân bố mức độ che khuất:\n")
    print(f"   Không che khuất (occlusion = 0%):")
    print(f"      {no_occlusion:,} mẫu ({100*no_occlusion/total_samples:.1f}%)\n")
    
    print(f"   Che nhẹ (0% < occlusion ≤ 10%):")
    print(f"      {light_occlusion:,} mẫu ({100*light_occlusion/total_samples:.1f}%)\n")
    
    print(f"   Che vừa (10% < occlusion ≤ 25%):")
    print(f"      {medium_occlusion:,} mẫu ({100*medium_occlusion/total_samples:.1f}%)\n")
    
    print(f"   Che nặng (occlusion > 25%):")
    print(f"      {heavy_occlusion:,} mẫu ({100*heavy_occlusion/total_samples:.1f}%)\n")
    
    # Thống kê occlusion ratio
    print(f"📊 Thống kê Occlusion Ratio:\n")
    print(f"   Mean: {np.mean(occlusion_ratios):.4f} ({100*np.mean(occlusion_ratios):.1f}%)")
    print(f"   Median: {np.median(occlusion_ratios):.4f} ({100*np.median(occlusion_ratios):.1f}%)")
    print(f"   Std: {np.std(occlusion_ratios):.4f} ({100*np.std(occlusion_ratios):.1f}%)")
    print(f"   Min: {np.min(occlusion_ratios):.4f}")
    print(f"   Max: {np.max(occlusion_ratios):.4f}\n")
    
    # Top classes
    print(f"🏆 Top 10 COCO Classes:\n")
    top_classes = sorted(class_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    for rank, (cat_id, count) in enumerate(top_classes, 1):
        class_name = cat_id_to_name.get(cat_id, f"Class {cat_id}")
        pct = 100 * count / total_samples
        print(f"   {rank:2d}. {class_name:20s}: {count:6,} mẫu ({pct:5.1f}%)")
    
    print(f"\n{'='*70}\n")


if __name__ == "__main__":
    # Đường dẫn từ thư mục scripts
    base_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Cố gắng tìm annotation files
    train_ann = os.path.join(base_dir, "../data/annotations/COCO_amodal_train2014.json")
    val_ann = os.path.join(base_dir, "../data/annotations/COCO_amodal_val2014.json")
    
    train_img = os.path.join(base_dir, "../data/train2014")
    val_img = os.path.join(base_dir, "../data/val2014")
    
    # Phân tích Training Set
    print("\n" + "="*70)
    print("🎯 TRAINING SET")
    print("="*70)
    analyze_dataset(train_img, train_ann)
    
    # Phân tích Validation Set
    print("\n" + "="*70)
    print("✅ VALIDATION SET")
    print("="*70)
    analyze_dataset(val_img, val_ann)
