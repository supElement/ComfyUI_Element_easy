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
                        "Histogram", 
                        "LAB_Mean", 
                        "SeamlessClone", 
                        "None"
                    ],
                ),
                "feather_amount": ("INT", {"default": 20, "min": 0, "max": 256, "step": 1}),
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

    def smart_merge(self, original_image, edited_crop_B, alignment_mode, color_match, feather_amount, original_crop_A=None):
        batch_size = min(original_image.shape[0], edited_crop_B.shape[0])
        result_images = []

        for i in range(batch_size):
            img_B = (original_image[i].numpy() * 255).astype(np.uint8)
            img_C = (edited_crop_B[i].numpy() * 255).astype(np.uint8)
            
            h_B, w_B = img_B.shape[:2]
            h_C, w_C = img_C.shape[:2]

            img_D = img_B.copy()
            
            warped_C = np.zeros_like(img_B)
            warped_mask = np.zeros((h_B, w_B), dtype=np.float32)

            use_bridge = False
            if alignment_mode == "Force Bridge(Ref A & B)" and original_crop_A is not None:
                use_bridge = True
            elif alignment_mode == "Auto" and original_crop_A is not None:
                use_bridge = True

            success_align = False

            if use_bridge:
                img_A = (original_crop_A[i].numpy() * 255).astype(np.uint8)
                h_A, w_A = img_A.shape[:2]

                res = cv2.matchTemplate(cv2.cvtColor(img_B, cv2.COLOR_RGB2GRAY), cv2.cvtColor(img_A, cv2.COLOR_RGB2GRAY), cv2.TM_CCOEFF_NORMED)
                _, _, _, max_loc = cv2.minMaxLoc(res)
                x, y = max_loc
                
                img_C_resized = cv2.resize(img_C, (w_A, h_A), interpolation=cv2.INTER_LANCZOS4)
                
                warped_C[y:y+h_A, x:x+w_A] = img_C_resized
                warped_mask[y:y+h_A, x:x+w_A] = 1.0
                success_align = True

            if not success_align:
                gray_B = cv2.cvtColor(img_B, cv2.COLOR_RGB2GRAY)
                gray_C = cv2.cvtColor(img_C, cv2.COLOR_RGB2GRAY)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
                gray_B_eq = clahe.apply(gray_B)
                gray_C_eq = clahe.apply(gray_C)

                sift = cv2.SIFT_create()
                kp_C, des_C = sift.detectAndCompute(gray_C_eq, None)
                kp_B, des_B = sift.detectAndCompute(gray_B_eq, None)

                if des_C is not None and des_B is not None:
                    flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=50))
                    matches = flann.knnMatch(des_C, des_B, k=2)

                    good_matches = [m for m, n in matches if m.distance < 0.75 * n.distance]

                    if len(good_matches) >= 10:
                        src_pts = np.float32([kp_C[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
                        dst_pts = np.float32([kp_B[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

                        H, _ = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)

                        if H is not None:
                            warped_C = cv2.warpPerspective(img_C, H, (w_B, h_B), flags=cv2.INTER_LINEAR)
                            mask_C = np.ones((h_C, w_C), dtype=np.float32)
                            warped_mask = cv2.warpPerspective(mask_C, H, (w_B, h_B), flags=cv2.INTER_LINEAR)
                            success_align = True

                if not success_align:
                    y_off = max(0, (h_B - h_C) // 2)
                    x_off = max(0, (w_B - w_C) // 2)
                    warped_C[y_off:y_off+h_C, x_off:x_off+w_C] = img_C
                    warped_mask[y_off:y_off+h_C, x_off:x_off+w_C] = 1.0

            mask_8u = (warped_mask * 255).astype(np.uint8)
            mask_8u = cv2.erode(mask_8u, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7)), iterations=1)

            if color_match == "Histogram":
                warped_C = self.exact_histogram_match(warped_C, img_B, mask_8u.astype(np.float32)/255.0)
            elif color_match == "LAB_Mean":
                lab_B = cv2.cvtColor(img_B, cv2.COLOR_RGB2LAB).astype(np.float32)
                lab_C = cv2.cvtColor(warped_C, cv2.COLOR_RGB2LAB).astype(np.float32)
                mean_B, std_B = cv2.meanStdDev(lab_B, mask=mask_8u)
                mean_C, std_C = cv2.meanStdDev(lab_C, mask=mask_8u)
                std_C[std_C == 0] = 1.0
                lab_C = (lab_C - mean_C.flatten()) * (std_B.flatten() / std_C.flatten()) + mean_B.flatten()
                lab_C = np.clip(lab_C, 0, 255).astype(np.uint8)
                matched_C = cv2.cvtColor(lab_C, cv2.COLOR_LAB2RGB)
                warped_C = np.where(mask_8u[:, :, np.newaxis] > 127, matched_C, warped_C)

            if color_match == "SeamlessClone":
                shrink_radius = max(5, feather_amount)
                k_size = (shrink_radius * 2) + 1
                clone_mask = cv2.erode(mask_8u, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size)), iterations=1)
                
                x_r, y_r, w_r, h_r = cv2.boundingRect(clone_mask)
                if w_r > 0 and h_r > 0:
                    pad = 10
                    x1, y1 = max(0, x_r - pad), max(0, y_r - pad)
                    x2, y2 = min(w_B, x_r + w_r + pad), min(h_B, y_r + h_r + pad)
                    
                    src_crop = warped_C[y1:y2, x1:x2]
                    dst_crop = img_B[y1:y2, x1:x2]
                    mask_crop = clone_mask[y1:y2, x1:x2]
                    
                    center = ((x2 - x1) // 2, (y2 - y1) // 2)
                    
                    try:
                        cloned_crop = cv2.seamlessClone(src_crop, dst_crop, mask_crop, center, cv2.NORMAL_CLONE)
                        img_D[y1:y2, x1:x2] = cloned_crop
                    except Exception as e:
                        print(f"[Smart Merge] Seamless Clone failed: {e}. Falling back to normal blend.")
                        color_match = "None" 

            if color_match != "SeamlessClone":
                if feather_amount > 0:
                    k_size = (feather_amount * 2) + 1
                    erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
                    mask_eroded = cv2.erode(mask_8u, erode_kernel, iterations=1)
                    
                    blur_size = (feather_amount * 2) | 1
                    soft_mask = cv2.GaussianBlur(mask_eroded.astype(np.float32) / 255.0, (blur_size, blur_size), 0)
                else:
                    soft_mask = mask_8u.astype(np.float32) / 255.0
                    
                soft_mask = soft_mask[:, :, np.newaxis]
                blended = (warped_C * soft_mask) + (img_B * (1.0 - soft_mask))
                img_D = np.clip(blended, 0, 255).astype(np.uint8)

            out_tensor = torch.from_numpy(img_D.astype(np.float32) / 255.0)
            result_images.append(out_tensor)

        return (torch.stack(result_images),)