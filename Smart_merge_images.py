import torch
import numpy as np
import cv2

class SmartMergeImages:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE",), 
                "edited_crop_B": ("IMAGE",),    
                "alignment_mode": (
                    [
                        "Auto", 
                        "Force Pixel Snapping (Ref B)", 
                        "Force Bridge(Ref A & B)"
                    ],
                ),
                "color_match": (
                    [
                        "None",
                        "Histogram", 
                        "LAB_Mean", 
                        "SeamlessClone (PS Auto Blend)", 
                        "Adaptive Local", 
                        "Alpha Soft Blend"
                    ],
                ),
                "feather_amount": ("INT", {"default": 20, "min": 0, "max": 256, "step": 1}),
                "adapt_thresh": ("INT", {"default": 25, "min": 0, "max": 255, "step": 1}),
                "adapt_kernel": ("INT", {"default": 5, "min": 3, "max": 127, "step": 2}),
            },
            "optional": {
                "original_crop_A": ("IMAGE",),  
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("Merged_Image",)
    FUNCTION = "smart_merge"
    CATEGORY = "Element_easy/image"

    def exact_histogram_match(self, src, ref, mask):
        matched = np.copy(src)
        mask_bool = mask > 0.5
        for c in range(src.shape[-1]):
            src_channel = src[:, :, c]
            ref_channel = ref[:, :, c]
            src_pixels = src_channel[mask_bool]
            ref_pixels = ref_channel[mask_bool]
            if len(src_pixels) == 0 or len(ref_pixels) == 0:
                continue
            src_hist, _ = np.histogram(src_pixels, 256, [0, 256])
            ref_hist, _ = np.histogram(ref_pixels, 256, [0, 256])
            src_cdf = src_hist.cumsum()
            ref_cdf = ref_hist.cumsum()
            src_cdf = src_cdf / (src_cdf[-1] + 1e-8)
            ref_cdf = ref_cdf / (ref_cdf[-1] + 1e-8)
            lookup_table = np.zeros(256)
            j = 0
            for i in range(256):
                while j < 256 and ref_cdf[j] < src_cdf[i]:
                    j += 1
                lookup_table[i] = j
            src_matched = cv2.LUT(src_channel, lookup_table.astype(np.uint8))
            matched[:, :, c] = np.where(mask_bool, src_matched, src_channel)
        return matched

    def perform_sift_alignment(self, query_img, train_img):
        gray_query = cv2.cvtColor(query_img, cv2.COLOR_RGB2GRAY)
        gray_train = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        
        sift = cv2.SIFT_create()
        kp_q, des_q = sift.detectAndCompute(clahe.apply(gray_query), None)
        kp_t, des_t = sift.detectAndCompute(clahe.apply(gray_train), None)

        if des_q is None or des_t is None or len(des_q) < 4 or len(des_t) < 4:
            return None

        flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=50))
        matches = flann.knnMatch(des_q, des_t, k=2)

        good_matches = []
        for match_pair in matches:
            if len(match_pair) == 2:
                m, n = match_pair
                if m.distance < 0.75 * n.distance:
                    good_matches.append(m)

        if len(good_matches) >= 10:
            src_pts = np.float32([kp_q[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp_t[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
            H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            return H
        return None

    def smart_merge(self, original_image, edited_crop_B, alignment_mode, color_match, feather_amount, adapt_thresh, adapt_kernel, original_crop_A=None):
        batch_size = min(original_image.shape[0], edited_crop_B.shape[0])
        result_images = []

        for i in range(batch_size):
            try:
                img_bg = (original_image[i].numpy() * 255).astype(np.uint8)  
                img_fg = (edited_crop_B[i].numpy() * 255).astype(np.uint8)   
                
                h_bg, w_bg = img_bg.shape[:2]
                h_fg, w_fg = img_fg.shape[:2]
                
                if h_bg == 0 or w_bg == 0 or h_fg == 0 or w_fg == 0:
                    result_images.append(original_image[i])
                    continue

                img_result = img_bg.copy()
                warped_fg = np.zeros_like(img_bg)
                warped_mask = np.zeros((h_bg, w_bg), dtype=np.float32)

                success_align = False
                base_mask = np.ones((h_fg, w_fg), dtype=np.float32)

                if alignment_mode in ["Force Bridge(Ref A & B)", "Auto"] and original_crop_A is not None:
                    img_bridge_A = (original_crop_A[i].numpy() * 255).astype(np.uint8)
                    h_A, w_A = img_bridge_A.shape[:2]
                    if h_A > 0 and w_A > 0:
                        H_A_to_BG = self.perform_sift_alignment(img_bridge_A, img_bg)
                        if H_A_to_BG is not None:
                            scale_x = w_A / float(w_fg)
                            scale_y = h_A / float(h_fg)
                            H_FG_to_A = np.array([[scale_x, 0, 0], [0, scale_y, 0], [0, 0, 1]], dtype=np.float64)
                            H_Total = np.dot(H_A_to_BG, H_FG_to_A)
                            warped_fg = cv2.warpPerspective(img_fg, H_Total, (w_bg, h_bg), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT101)
                            warped_mask = cv2.warpPerspective(base_mask, H_Total, (w_bg, h_bg), flags=cv2.INTER_LINEAR)
                            success_align = True

                if not success_align:
                    H_FG_to_BG = self.perform_sift_alignment(img_fg, img_bg)
                    if H_FG_to_BG is not None:
                        warped_fg = cv2.warpPerspective(img_fg, H_FG_to_BG, (w_bg, h_bg), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REFLECT101)
                        warped_mask = cv2.warpPerspective(base_mask, H_FG_to_BG, (w_bg, h_bg), flags=cv2.INTER_LINEAR)
                        success_align = True

                if not success_align:
                    y_off = max(0, (h_bg - h_fg) // 2)
                    x_off = max(0, (w_bg - w_fg) // 2)
                    y1, y2 = y_off, min(y_off + h_fg, h_bg)
                    x1, x2 = x_off, min(x_off + w_fg, w_bg)
                    crop_h, crop_w = y2 - y1, x2 - x1
                    if crop_h > 0 and crop_w > 0:
                        warped_fg[y1:y2, x1:x2] = img_fg[:crop_h, :crop_w]
                        warped_mask[y1:y2, x1:x2] = base_mask[:crop_h, :crop_w]

                bounds_mask_float = warped_mask.copy()
                bounds_mask_8u = (bounds_mask_float * 255).astype(np.uint8)

                if color_match == "Histogram":
                    warped_fg = self.exact_histogram_match(warped_fg, img_bg, bounds_mask_float)
                    
                elif color_match == "LAB_Mean":
                    lab_bg = cv2.cvtColor(img_bg, cv2.COLOR_RGB2LAB).astype(np.float32)
                    lab_fg = cv2.cvtColor(warped_fg, cv2.COLOR_RGB2LAB).astype(np.float32)
                    mean_bg, std_bg = cv2.meanStdDev(lab_bg, mask=bounds_mask_8u)
                    mean_fg, std_fg = cv2.meanStdDev(lab_fg, mask=bounds_mask_8u)
                    std_fg[std_fg == 0] = 1.0
                    lab_fg = (lab_fg - mean_fg.flatten()) * (std_bg.flatten() / std_fg.flatten()) + mean_bg.flatten()
                    lab_fg = np.clip(lab_fg, 0, 255).astype(np.uint8)
                    matched_fg = cv2.cvtColor(lab_fg, cv2.COLOR_LAB2RGB)
                    mask_3d = bounds_mask_float[:, :, np.newaxis]
                    warped_fg = (matched_fg * mask_3d + warped_fg * (1 - mask_3d)).astype(np.uint8)
                    
                elif color_match == "Adaptive Local":
                    
                    temp_fg = warped_fg.astype(np.float32)
                    mean_bg = cv2.mean(img_bg, mask=bounds_mask_8u)[:3]
                    mean_fg = cv2.mean(warped_fg, mask=bounds_mask_8u)[:3]
                    
                    diff_offset = np.array(mean_bg) - np.array(mean_fg)
                    temp_fg[:, :, 0] += diff_offset[0]
                    temp_fg[:, :, 1] += diff_offset[1]
                    temp_fg[:, :, 2] += diff_offset[2]
                    temp_fg_aligned = np.clip(temp_fg, 0, 255).astype(np.uint8)
                    
                    diff_rgb = cv2.absdiff(img_bg, temp_fg_aligned)
                    diff_max = np.max(diff_rgb, axis=2).astype(np.float32)
                    diff_blur = cv2.GaussianBlur(diff_max, (5, 5), 0)
                    
                    _, thresh = cv2.threshold(diff_blur, float(adapt_thresh), 255.0, cv2.THRESH_BINARY)
                    thresh_8u = thresh.astype(np.uint8)
                    
                    k_size = int(adapt_kernel) | 1 
                    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
                    closed_mask = cv2.morphologyEx(thresh_8u, cv2.MORPH_CLOSE, kernel_close)
                    
                    dilate_size = max(3, (k_size // 2) | 1)
                    kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_size, dilate_size))
                    dilated_mask = cv2.dilate(closed_mask, kernel_dilate, iterations=1)
                    
                    blur_size = max(3, (k_size // 2) | 1) * 2 - 1
                    final_diff_mask = cv2.GaussianBlur(dilated_mask.astype(np.float32) / 255.0, (blur_size, blur_size), 0)
                    diff_mask_3d = final_diff_mask[:, :, np.newaxis] * bounds_mask_float[:, :, np.newaxis]
                    
                    fg_float = warped_fg.astype(np.float32)
                    bg_float = img_bg.astype(np.float32)
                    adaptive_fg = (fg_float * diff_mask_3d) + (bg_float * (1.0 - diff_mask_3d))
                    warped_fg = np.clip(adaptive_fg, 0, 255).astype(np.uint8)

                if color_match == "SeamlessClone (PS Auto Blend)":
                    shrink_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                    clone_mask_8u = cv2.erode(bounds_mask_8u, shrink_kernel, iterations=1)
                    x, y, w, h = cv2.boundingRect(clone_mask_8u)
                    safe_pad = 5
                    if w > 10 and h > 10 and x > safe_pad and y > safe_pad and (x + w) < (w_bg - safe_pad) and (y + h) < (h_bg - safe_pad):
                        x1, y1 = x - safe_pad, y - safe_pad
                        x2, y2 = x + w + safe_pad, y + h + safe_pad
                        src_crop = warped_fg[y1:y2, x1:x2]
                        dst_crop = img_bg[y1:y2, x1:x2]
                        mask_crop = clone_mask_8u[y1:y2, x1:x2]
                        center = ((x2 - x1) // 2, (y2 - y1) // 2)
                        try:
                            cloned_crop = cv2.seamlessClone(src_crop, dst_crop, mask_crop, center, cv2.NORMAL_CLONE)
                            img_result[y1:y2, x1:x2] = cloned_crop
                        except Exception as e:
                            print(f"[Smart Merge] 泊松融合失败: {e}")
                            color_match = "Alpha Soft Blend" 
                    else:
                        color_match = "Alpha Soft Blend"

                if color_match != "SeamlessClone (PS Auto Blend)":
                    if feather_amount > 0:
                        erode_size = max(3, feather_amount)
                        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erode_size, erode_size))
                        eroded_mask_8u = cv2.erode(bounds_mask_8u, kernel, iterations=1)
                        blur_size = (feather_amount * 2) | 1
                        soft_mask = cv2.GaussianBlur(eroded_mask_8u.astype(np.float32) / 255.0, (blur_size, blur_size), 0)
                        soft_mask = soft_mask * bounds_mask_float
                    else:
                        soft_mask = bounds_mask_float
                        
                    soft_mask_3d = soft_mask[:, :, np.newaxis]
                    fg_float = warped_fg.astype(np.float32)
                    bg_float = img_bg.astype(np.float32)
                    
                    blended = (fg_float * soft_mask_3d) + (bg_float * (1.0 - soft_mask_3d))
                    img_result = np.clip(blended, 0, 255).astype(np.uint8)

                out_tensor = torch.from_numpy(img_result.astype(np.float32) / 255.0)
                result_images.append(out_tensor)

            except Exception as e:
                import traceback
                print(f"[Smart Merge 致命错误] {e}")
                traceback.print_exc()
                result_images.append(original_image[i])

        return (torch.stack(result_images),)
