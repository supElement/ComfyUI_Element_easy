import torch
import numpy as np
import cv2
import os
import kornia as K
import kornia.feature as KF

# ComfyUI 进度条支持
try:
    from comfy.utils import ProgressBar
    HAS_PROGRESS_BAR = True
except ImportError:
    HAS_PROGRESS_BAR = False

# 重定向缓存目录到 ComfyUI/models/elementEasy
try:
    import folder_paths
    models_dir = folder_paths.models_dir
    element_easy_dir = os.path.join(models_dir, "elementEasy")
    os.makedirs(element_easy_dir, exist_ok=True)
    torch.hub.set_dir(element_easy_dir)
    print(f"[Smart Merge] 成功将模型下载和缓存目录重定向至: {element_easy_dir}")
except Exception as e:
    element_easy_dir = os.path.join(os.path.dirname(__file__), "models")
    os.makedirs(element_easy_dir, exist_ok=True)
    torch.hub.set_dir(element_easy_dir)


def _parse_lightglue_output(match_res):

    if match_res is None:
        return None

    if isinstance(match_res, (tuple, list)):
        idxs = None
        for item in match_res:
            if isinstance(item, torch.Tensor) and item.dtype in (torch.long, torch.int32, torch.int64):
                idxs = item
        if idxs is None and len(match_res) >= 2:
            idxs = match_res[1]
    else:
        idxs = match_res

    if not isinstance(idxs, torch.Tensor):
        return None

    while idxs.dim() > 2:
        idxs = idxs.squeeze(0)

    if idxs.dim() != 2 or idxs.shape[-1] != 2:
        return None

    return idxs


class SmartMergeImages:
    _disk_model = None
    _lg_matcher_disk = None
    _lg_matcher_sift = None
    _cached_device = None

    _align_cache = {}
    _align_cache_order = []
    _align_cache_max = 4
    
    
    @staticmethod
    def _send_progress(value, total, node_id=None):
        """发送进度条更新到 ComfyUI 前端"""
        if not HAS_PROMPT_SERVER:
            return
        try:
            PromptServer.instance.send_sync("progress", {
                "value": int(value),
                "max": int(total),
                "node_id": node_id,
            })
        except Exception:
            pass
    
    @staticmethod
    def _tensor_fingerprint(t):
        if t is None:
            return "none"
        import hashlib
        arr = t.detach().cpu().numpy() if hasattr(t, "detach") else np.asarray(t)
        shape_str = "x".join(map(str, arr.shape))
        flat = arr.reshape(-1)
        if flat.size == 0:
            return f"empty_{shape_str}"
        idx = np.linspace(0, flat.size - 1, min(512, flat.size)).astype(np.int64)
        sig = hashlib.md5(flat[idx].tobytes()).hexdigest()[:16]
        stat = f"{float(arr.mean()):.6f}_{float(arr.std()):.6f}"
        return f"{shape_str}_{sig}_{stat}"
    
    @classmethod
    def _make_align_key(cls, original_image, edited_crop_B, original_crop_A,
                        match_method, warp_method, optical_flow, merge_mode, use_gpu):
        return "|".join([
            cls._tensor_fingerprint(original_image),
            cls._tensor_fingerprint(edited_crop_B),
            cls._tensor_fingerprint(original_crop_A),
            str(match_method), str(warp_method), str(optical_flow),
            str(merge_mode), str(bool(use_gpu)),
        ])
    
    @classmethod
    def _cache_get(cls, key):
        if key in cls._align_cache:
            if key in cls._align_cache_order:
                cls._align_cache_order.remove(key)
            cls._align_cache_order.append(key)
            return cls._align_cache[key]
        return None
    
    @classmethod
    def _cache_put(cls, key, value):
        cls._align_cache[key] = value
        if key in cls._align_cache_order:
            cls._align_cache_order.remove(key)
        cls._align_cache_order.append(key)
        while len(cls._align_cache_order) > cls._align_cache_max:
            old = cls._align_cache_order.pop(0)
            cls._align_cache.pop(old, None)

    @classmethod
    def _clear_cache(cls):
        cls._align_cache.clear()
        cls._align_cache_order.clear()
    
    @classmethod
    def get_kornia_models(cls, device, method):
        if cls._cached_device != device:
            cls._disk_model = None
            cls._lg_matcher_disk = None
            cls._lg_matcher_sift = None
            cls._cached_device = device
    
        if "DISK" in method:
            if cls._disk_model is None:
                try:
                    cls._disk_model = KF.DISK.from_pretrained("depth").eval().to(device)
                    cls._lg_matcher_disk = KF.LightGlueMatcher("disk").eval().to(device)
                    print(f"[Smart Merge] DISK & LightGlue 模型已就绪 (设备: {device})")
                except Exception as e:
                    print(f"[Smart Merge] 初始化 DISK 权重失败: {e}")
            return cls._disk_model, cls._lg_matcher_disk
    
        elif "SIFT" in method:
            if cls._lg_matcher_sift is None:
                try:
                    cls._lg_matcher_sift = KF.LightGlueMatcher("sift").eval().to(device)
                    print(f"[Smart Merge] SIFT-LightGlue 模型已就绪 (设备: {device})")
                except Exception as e:
                    print(f"[Smart Merge] 初始化 SIFT-LightGlue 权重失败: {e}")
            return None, cls._lg_matcher_sift
    
        return None, None

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE",),
                "edited_crop_B": ("IMAGE",),
                "match_method": (
                    [
                        "DISK + LightGlue",
                        "SIFT + LightGlue",
                        "SIFT (OpenCV)"
                    ],
                ),
                "warp_method": (
                    [
                        "Homography",
                        "Homography + Optical Flow",
                        "Optical Flow"
                    ],
                ),
                "optical_flow": (  
                    [
                        "Farneback",
                        "DIS",
                        "RAFT-Small",
                        "RAFT-Large"
                    ],
                ),
                
                "color_match": (
                    [
                        "Patch_based_color",
                        "Boundary-Aware Color",
                        "Laplacian Pyramid Blend",
                        "SeamlessClone (PS Auto Blend)",
                        "Adaptive Local (strong)",
                        "Histogram",
                        "LAB_Mean",
                        "Alpha Soft Blend",
                        "None"
                    ],
                ),
                "feather_kernel": ("INT", {"default": 20, "min": 0, "max": 256, "step": 1}),
                "adapt_thresh": ("INT", {"default": 25, "min": 0, "max": 255, "step": 1}),
                "adapt_local_match": (
                    [
                        "Histogram",
                        "LAB_Mean",
                        "Reinhard",
                        "Adaptive Histogram",
                        "None"
                    ],
                ),
                "merge_mode": (["All to One", "One to One"],),
                "use_gpu": ("BOOLEAN", {"default": True}),
                "force_recompute": ("BOOLEAN", {"default": False}),
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
        if mask.ndim == 3:
            mask = mask[:, :, 0]
        mask_bool = mask > 0.5

        src_u8 = src if src.dtype == np.uint8 else np.clip(src, 0, 255).astype(np.uint8)
        ref_u8 = ref if ref.dtype == np.uint8 else np.clip(ref, 0, 255).astype(np.uint8)

        for c in range(src_u8.shape[-1]):
            src_channel = src_u8[:, :, c]
            ref_channel = ref_u8[:, :, c]
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
            lookup_table = np.zeros(256, dtype=np.uint8)
            j = 0
            for i in range(256):
                while j < 256 and ref_cdf[j] < src_cdf[i]:
                    j += 1
                lookup_table[i] = min(j, 255)
            src_matched = cv2.LUT(src_channel, lookup_table)
            matched[:, :, c] = np.where(mask_bool, src_matched, src_channel)
        return matched
        
    def patch_based_color_sync(self, fg, bg, mask_float, patch_size=64, overlap=32):
        h, w = fg.shape[:2]
        mask_bool = mask_float > 0.5
        
        lab_fg = cv2.cvtColor(fg, cv2.COLOR_RGB2LAB).astype(np.float32)
        lab_bg = cv2.cvtColor(bg, cv2.COLOR_RGB2LAB).astype(np.float32)
        
        result = lab_fg.copy()
        weight_map = np.zeros((h, w), dtype=np.float32)
        correction_sum = np.zeros_like(lab_fg)
        
        step = patch_size - overlap
        y_positions = list(range(0, h - patch_size + 1, step))
        x_positions = list(range(0, w - patch_size + 1, step))
        
        if not y_positions or y_positions[-1] + patch_size < h:
            y_positions.append(max(0, h - patch_size))
        if not x_positions or x_positions[-1] + patch_size < w:
            x_positions.append(max(0, w - patch_size))
        
        y_positions = sorted(set(y_positions))
        x_positions = sorted(set(x_positions))
        
        valid_patches = 0
        
        for y in y_positions:
            for x in x_positions:
                y2, x2 = min(y + patch_size, h), min(x + patch_size, w)
                y, x = y2 - patch_size, x2 - patch_size
                
                patch_mask = mask_bool[y:y2, x:x2]
                patch_mask_sum = patch_mask.sum()
                
                if patch_mask_sum < patch_size * patch_size * 0.1:
                    continue
                
                patch_fg = lab_fg[y:y2, x:x2]
                patch_bg = lab_bg[y:y2, x:x2]
                
                patch_correction = np.zeros((patch_size, patch_size, 3), dtype=np.float32)
                
                for c in range(3):
                    fg_vals = patch_fg[:, :, c][patch_mask]
                    bg_vals = patch_bg[:, :, c][patch_mask]
                    
                    if len(fg_vals) > 10:
                        sorted_diff = np.sort(bg_vals - fg_vals)
                        trim = int(len(sorted_diff) * 0.1)  # 去掉 10%
                        if trim > 0:
                            trimmed_diff = sorted_diff[trim:-trim]
                        else:
                            trimmed_diff = sorted_diff
                        
                        diff = np.mean(trimmed_diff)
                        
                        diff_std = np.std(sorted_diff)
                        diff_max = abs(diff) + 2 * diff_std
                        diff = np.clip(diff, -diff_max, diff_max)
                        
                        patch_correction[:, :, c] = diff
                
                # Hann 窗权重
                hann_y = np.hanning(patch_size)[:, np.newaxis]
                hann_x = np.hanning(patch_size)[np.newaxis, :]
                patch_weight = hann_y * hann_x
                patch_weight = patch_weight * patch_mask.astype(np.float32)
                
                for c in range(3):
                    correction_sum[y:y2, x:x2, c] += patch_correction[:, :, c] * patch_weight
                weight_map[y:y2, x:x2] += patch_weight
                
                valid_patches += 1
        
        if valid_patches == 0:
            print("[Patch Sync] 无有效 patch，回退到全局均值")
            for c in range(3):
                fg_vals = lab_fg[:, :, c][mask_bool]
                bg_vals = lab_bg[:, :, c][mask_bool]
                if len(fg_vals) > 0:
                    diff = np.median(bg_vals) - np.median(fg_vals)
                    result[:, :, c] += diff
            return cv2.cvtColor(np.clip(result, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
        
        # 加权平均
        weight_map = np.maximum(weight_map, 1e-6)
        weight_3d = weight_map[:, :, np.newaxis]
        correction_field = correction_sum / weight_3d
        
        for c in range(3):
            correction_field[:, :, c] = cv2.medianBlur(
                correction_field[:, :, c].astype(np.float32), 
                5  # 5x5 中值滤波
            )
        
        # 额外的高斯平滑
        for c in range(3):
            correction_field[:, :, c] = cv2.GaussianBlur(
                correction_field[:, :, c], 
                (overlap // 2 * 2 + 1, overlap // 2 * 2 + 1), 
                0
            )
        
        # 可选：双边滤波保持边缘的同时平滑内部
        # correction_field_rgb = cv2.cvtColor(correction_field.astype(np.uint8), cv2.COLOR_LAB2RGB)
        # correction_field_rgb = cv2.bilateralFilter(correction_field_rgb, 9, 75, 75)
        # correction_field = cv2.cvtColor(correction_field_rgb, cv2.COLOR_RGB2LAB).astype(np.float32)
        
        mask_3d = mask_bool.astype(np.float32)[:, :, np.newaxis]
        correction_field = correction_field * mask_3d
        
        result = lab_fg + correction_field
        result = np.clip(result, 0, 255).astype(np.uint8)
        
        #print(f"[Patch Sync] 完成，有效 patch: {valid_patches}")
        
        return cv2.cvtColor(result, cv2.COLOR_LAB2RGB)

    def boundary_aware_color_sync(self, fg, bg, mask_float, band_width=21, strength=1.0):

        h, w = fg.shape[:2]
        mask_8u = (np.clip(mask_float, 0, 1) * 255).astype(np.uint8)
        
        if np.sum(mask_8u > 128) < 100:
            return fg
        
        lab_fg = cv2.cvtColor(fg, cv2.COLOR_RGB2LAB).astype(np.float32)
        lab_bg = cv2.cvtColor(bg, cv2.COLOR_RGB2LAB).astype(np.float32)
        
        med_size = max(7, (band_width // 2) | 1)
        lab_fg_med = cv2.medianBlur(np.clip(lab_fg, 0, 255).astype(np.uint8), med_size).astype(np.float32)
        lab_bg_med = cv2.medianBlur(np.clip(lab_bg, 0, 255).astype(np.uint8), med_size).astype(np.float32)
        
        raw_diff = lab_bg_med - lab_fg_med  # shape: (h, w, 3)
        
        mask_3d = (mask_float > 0.5).astype(np.float32)[:, :, np.newaxis]
        masked_diff = raw_diff * mask_3d
        
        ksz = min(max(31, (band_width * 3) | 1), 151)
        
        correction_field = np.zeros_like(lab_fg)
        
        for c in range(3):
            diff_ch = masked_diff[:, :, c]
            
            diff_smooth = cv2.GaussianBlur(diff_ch, (ksz, ksz), 0)
            
            diff_sqr = diff_ch ** 2
            diff_sqr_smooth = cv2.GaussianBlur(diff_sqr, (ksz, ksz), 0)
            variance = diff_sqr_smooth - diff_smooth ** 2
            variance = np.maximum(variance, 0)
            
            reliability = np.exp(-variance / (np.median(variance[variance > 0]) + 1e-6))
            reliability = reliability * (mask_float > 0.5).astype(np.float32)
            
            weighted_num = cv2.GaussianBlur(diff_ch * reliability, (ksz, ksz), 0)
            weighted_den = cv2.GaussianBlur(reliability, (ksz, ksz), 0) + 1e-6
            correction_field[:, :, c] = weighted_num / weighted_den
        
        dist_from_boundary = cv2.distanceTransform((1 - (mask_float > 0.5).astype(np.uint8)), cv2.DIST_L2, 5)
        max_dist = dist_from_boundary.max() + 1e-6
        
        decay = np.clip(0.4 + 0.6 * (1.0 - dist_from_boundary / max_dist), 0.4, 1.0)
        
        decay_3d = decay[:, :, np.newaxis]
        
        strength_vec = np.array([0.6, 1.0, 1.0]) * strength
        
        soft_mask = cv2.GaussianBlur(mask_float.astype(np.float32), (band_width | 1, band_width | 1), 0)
        soft_mask_3d = soft_mask[:, :, np.newaxis]

        lab_corrected = lab_fg + correction_field * decay_3d * soft_mask_3d * strength_vec[None, None, :]
        lab_corrected = np.clip(lab_corrected, 0, 255).astype(np.uint8)
        
        return cv2.cvtColor(lab_corrected, cv2.COLOR_LAB2RGB)

    def perform_sift_alignment(self, query_img, train_img):

        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]

        max_bg_dim = max(h_t, w_t)
        scale = 1.0
        if max_bg_dim > 1536:
            scale = 1536.0 / float(max_bg_dim)

        if scale < 1.0:
            query_sift_img = cv2.resize(query_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
            train_sift_img = cv2.resize(train_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
        else:
            query_sift_img = query_img
            train_sift_img = train_img

        gray_query = cv2.cvtColor(query_sift_img, cv2.COLOR_RGB2GRAY)
        gray_train = cv2.cvtColor(train_sift_img, cv2.COLOR_RGB2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

        sift = cv2.SIFT_create(nfeatures=5000)
        kp_q, des_q = sift.detectAndCompute(clahe.apply(gray_query), None)
        kp_t, des_t = sift.detectAndCompute(clahe.apply(gray_train), None)

        if des_q is None or des_t is None or len(des_q) < 10 or len(des_t) < 10:
            return None

        bf = cv2.BFMatcher(cv2.NORM_L2)
        matches = bf.knnMatch(des_q, des_t, k=2)

        good_matches = []
        for m, n in matches:
            if m.distance < 0.7 * n.distance:
                good_matches.append(m)

        if len(good_matches) < 10:
            return None

        src_pts = np.float32([kp_q[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
        dst_pts = np.float32([kp_t[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)

        H, mask = cv2.findHomography(src_pts, dst_pts, cv2.USAC_MAGSAC, 3.0)

        if H is None or mask is None or np.sum(mask) < 8:
            return None

        if scale < 1.0:
            S = np.array([[scale, 0, 0], [0, scale, 0], [0, 0, 1]], dtype=np.float64)
            S_inv = np.array([[1.0/scale, 0, 0], [0, 1.0/scale, 0], [0, 0, 1]], dtype=np.float64)
            H = S_inv @ H @ S

        return H

    def laf_from_opencv_kpts(self, kpts, device):
        N = len(kpts)
        if N == 0:
            return torch.zeros((1, 0, 2, 3), device=device)
        pts = np.array([kp.pt for kp in kpts], dtype=np.float32)
        scales = np.array([kp.size for kp in kpts], dtype=np.float32)
        angles = np.array([kp.angle for kp in kpts], dtype=np.float32)

        t_pts = torch.from_numpy(pts).to(device)[None]
        t_scales = torch.from_numpy(scales).to(device)[None, :, None, None] * 6.0

        rad_angles = angles * (np.pi / 180.0)
        t_angles = torch.from_numpy(rad_angles).to(device)[None, :, None]

        lafs = KF.laf_from_center_scale_ori(t_pts, t_scales, t_angles)
        return lafs

    def refine_with_optical_flow(self, warped_fg, warped_mask, train_img, 
                                  optical_flow="RAFT-Small", device="cpu"):
        h_t, w_t = train_img.shape[:2]
        
        # RAFT
        if "RAFT" in optical_flow:
            try:
                return self._refine_with_raft(warped_fg, warped_mask, train_img, device, 
                                               use_large="Large" in optical_flow)
            except Exception as e:
                print(f"[Smart Merge] RAFT 不可用 ({e})")
        
        # DIS
        if "DIS" in optical_flow:
            try:
                gray_warped = cv2.cvtColor(warped_fg, cv2.COLOR_RGB2GRAY)
                gray_target = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)
                return self._refine_with_dis(gray_warped, gray_target, warped_fg, warped_mask, train_img)
            except Exception as e:
                print(f"[Smart Merge] DIS 不可用 ({e})")
        
        # Farneback 保底
        gray_warped = cv2.cvtColor(warped_fg, cv2.COLOR_RGB2GRAY)
        gray_target = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)
        return self._refine_with_farneback(gray_warped, gray_target, warped_fg, warped_mask, train_img)

    def _refine_with_raft(self, warped_fg, warped_mask, train_img, device, use_large=False):
        import torch
        import torchvision.models.optical_flow as raft
        
        h_t, w_t = train_img.shape[:2]
        img1 = warped_fg.copy()
        img2 = train_img.copy()
        
        h8 = ((h_t + 7) // 8) * 8
        w8 = ((w_t + 7) // 8) * 8
        
        img1_resized = np.zeros((h8, w8, 3), dtype=np.float32)
        img2_resized = np.zeros((h8, w8, 3), dtype=np.float32)
        img1_resized[:h_t, :w_t] = img1.astype(np.float32) / 255.0
        img2_resized[:h_t, :w_t] = img2.astype(np.float32) / 255.0
        
        t1 = torch.from_numpy(img1_resized).permute(2, 0, 1)[None].to(device)
        t2 = torch.from_numpy(img2_resized).permute(2, 0, 1)[None].to(device)
        
        if not hasattr(self, '_raft_model') or self._raft_device != device or getattr(self, '_raft_large', None) != use_large:
            if use_large:
                self._raft_model = raft.raft_large(pretrained=True).eval().to(device)
                print("[Smart Merge] RAFT-large 模型已加载")
            else:
                self._raft_model = raft.raft_small(pretrained=True).eval().to(device)
                print("[Smart Merge] RAFT-small 模型已加载")
            self._raft_device = device
            self._raft_large = use_large
        
        with torch.no_grad():
            flow_list = self._raft_model(t1, t2)
            flow_full = flow_list[-1][0].cpu().numpy().transpose(1, 2, 0)
        
        flow = flow_full[:h_t, :w_t].copy()
        
        flow[:, :, 0] = cv2.medianBlur(flow[:, :, 0].astype(np.float32), 3)
        flow[:, :, 1] = cv2.medianBlur(flow[:, :, 1].astype(np.float32), 3)
        
        max_flow = 15.0
        flow_mag = np.linalg.norm(flow, axis=2)
        scale_factor = np.minimum(flow_mag, max_flow) / (flow_mag + 1e-8)
        flow[:, :, 0] *= scale_factor
        flow[:, :, 1] *= scale_factor
        
        grid_x, grid_y = np.meshgrid(np.arange(w_t), np.arange(h_t))
        map_x = (grid_x + flow[:, :, 0]).astype(np.float32)
        map_y = (grid_y + flow[:, :, 1]).astype(np.float32)
        
        refined_fg = cv2.remap(warped_fg, map_x, map_y,
            interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
        
        flow_mean = float(np.mean(flow_mag))
        model_name = "RAFT-large" if use_large else "RAFT-small"
        #print(f"[Smart Merge] {model_name} 光流完成 (平均位移: {flow_mean:.2f}px)")
        return refined_fg, warped_mask.copy()

    def _refine_with_dis(self, gray_warped, gray_target, warped_fg, warped_mask, train_img):

        h_t, w_t = train_img.shape[:2]
        
        try:
            dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        except AttributeError:
            dis = cv2.DISOpticalFlow.create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        
        flow = dis.calc(gray_warped, gray_target, None)
        
        flow[:, :, 0] = cv2.medianBlur(flow[:, :, 0].astype(np.float32), 3)
        flow[:, :, 1] = cv2.medianBlur(flow[:, :, 1].astype(np.float32), 3)
        
        max_flow = 15.0
        flow_mag = np.linalg.norm(flow, axis=2)
        scale_factor = np.minimum(flow_mag, max_flow) / (flow_mag + 1e-8)
        flow[:, :, 0] *= scale_factor
        flow[:, :, 1] *= scale_factor
        
        grid_x, grid_y = np.meshgrid(np.arange(w_t), np.arange(h_t))
        map_x = (grid_x + flow[:, :, 0]).astype(np.float32)
        map_y = (grid_y + flow[:, :, 1]).astype(np.float32)
        
        refined_fg = cv2.remap(warped_fg, map_x, map_y,
            interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
        
        flow_mean = float(np.mean(flow_mag))
        #print(f"[Smart Merge] DIS 光流完成 (平均位移: {flow_mean:.2f}px)")
        return refined_fg, warped_mask.copy()
    
    def _refine_with_farneback(self, gray_warped, gray_target, warped_fg, warped_mask, train_img):
        h_t, w_t = train_img.shape[:2]
        
        mask_8u = (warped_mask * 255).astype(np.uint8)
        erode_size = min(25, min(h_t, w_t) // 4)
        erode_size = max(3, erode_size)
        erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erode_size, erode_size))
        inner_mask = cv2.erode(mask_8u, erode_kernel, iterations=1)
        inner_mask_f = inner_mask.astype(np.float32) / 255.0
    
        # 小位移优化
        flow_fwd = cv2.calcOpticalFlowFarneback(
            gray_warped, gray_target, None,
            0.5, 2, 7, 5, 5, 1.1,
            cv2.OPTFLOW_FARNEBACK_GAUSSIAN
        )
        flow_bwd = cv2.calcOpticalFlowFarneback(
            gray_target, gray_warped, None,
            0.5, 2, 7, 5, 5, 1.1,
            cv2.OPTFLOW_FARNEBACK_GAUSSIAN
        )
    
        grid_x, grid_y = np.meshgrid(np.arange(w_t), np.arange(h_t))
        map_x_fwd = (grid_x + flow_fwd[:, :, 0]).astype(np.float32)
        map_y_fwd = (grid_y + flow_fwd[:, :, 1]).astype(np.float32)
        bwd_at_fwd = cv2.remap(flow_bwd, map_x_fwd, map_y_fwd,
            interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        consistency_err = np.linalg.norm(flow_fwd + bwd_at_fwd, axis=2)
        consistency_mask = (consistency_err < 5.0).astype(np.float32)
    
        gx = cv2.Sobel(gray_warped, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gray_warped, cv2.CV_32F, 0, 1, ksize=3)
        grad_mag = np.sqrt(gx * gx + gy * gy)
        grad_local = cv2.boxFilter(grad_mag, -1, (21, 21))
        texture_mask = (grad_local > 2.0).astype(np.float32)
        
        if texture_mask.max() < 0.01:
            print("[Smart Merge] 警告：低纹理图像，纹理检测失效")
    
        reliability = inner_mask_f * consistency_mask * texture_mask
        reliability = np.clip(reliability, 0.2, 1.0)

        flow = flow_fwd.copy()
        max_flow = 15.0
        flow_mag = np.linalg.norm(flow, axis=2)
        scale_factor = np.minimum(flow_mag, max_flow) / (flow_mag + 1e-8)
        flow[:, :, 0] *= scale_factor
        flow[:, :, 1] *= scale_factor
    
        flow[:, :, 0] *= reliability
        flow[:, :, 1] *= reliability
        
        mean_flow = np.mean(flow_mag)
        
        if mean_flow < 0.5:
            return warped_fg, warped_mask
        elif mean_flow < 1.5:
            flow[:, :, 0] = cv2.bilateralFilter(flow[:, :, 0].astype(np.float32), 9, 5, 5)
            flow[:, :, 1] = cv2.bilateralFilter(flow[:, :, 1].astype(np.float32), 9, 5, 5)
        elif mean_flow < 3.0:
            flow[:, :, 0] = cv2.GaussianBlur(flow[:, :, 0], (7, 7), 0)
            flow[:, :, 1] = cv2.GaussianBlur(flow[:, :, 1], (7, 7), 0)
            flow[:, :, 0] = cv2.bilateralFilter(flow[:, :, 0].astype(np.float32), 5, 3, 3)
            flow[:, :, 1] = cv2.bilateralFilter(flow[:, :, 1].astype(np.float32), 5, 3, 3)
        else:
            flow[:, :, 0] = cv2.GaussianBlur(flow[:, :, 0], (21, 21), 0)
            flow[:, :, 1] = cv2.GaussianBlur(flow[:, :, 1], (21, 21), 0)

        map_x = (grid_x + flow[:, :, 0]).astype(np.float32)
        map_y = (grid_y + flow[:, :, 1]).astype(np.float32)
    
        refined_fg = cv2.remap(warped_fg, map_x, map_y,
            interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    
        affected = float(np.mean(reliability))
        return refined_fg, warped_mask.copy()

    def optical_flow_only_align(self, query_img, train_img, 
                                  optical_flow="RAFT-Small", device="cpu"):
        h_t, w_t = train_img.shape[:2]
        h_q, w_q = query_img.shape[:2]
        if (h_q, w_q) != (h_t, w_t):
            query_resized = cv2.resize(query_img, (w_t, h_t), interpolation=cv2.INTER_LANCZOS4)
        else:
            query_resized = query_img
        
        full_mask = np.ones((h_t, w_t), dtype=np.float32)
        border = 10
        full_mask[:border, :] = 0
        full_mask[-border:, :] = 0
        full_mask[:, :border] = 0
        full_mask[:, -border:] = 0
        full_mask = cv2.GaussianBlur(full_mask, (21, 21), 0)
        return self.refine_with_optical_flow(query_resized, full_mask, train_img, optical_flow, device)
        
    def estimate_homography(self, query_img, train_img,
                            method="DISK + LightGlue",
                            device="cpu"):
        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]
        pts_q, pts_t = None, None
        method_used = None

        img_q_tensor = torch.from_numpy(query_img).permute(2, 0, 1).float().to(device)[None] / 255.0
        img_t_tensor = torch.from_numpy(train_img).permute(2, 0, 1).float().to(device)[None] / 255.0

        # ========== DISK + LightGlue ==========
        if method == "DISK + LightGlue":
            try:
                disk, lg_matcher = self.get_kornia_models(device, "DISK")
                if disk is not None and lg_matcher is not None:
                    with torch.inference_mode():
                        features_q = disk(img_q_tensor, n=2048, pad_if_not_divisible=True)[0]
                        features_t = disk(img_t_tensor, n=2048, pad_if_not_divisible=True)[0]

                        kps_q_t = features_q.keypoints
                        kps_t_t = features_t.keypoints

                        if len(kps_q_t) >= 4 and len(kps_t_t) >= 4:
                            lafs_q = KF.laf_from_center_scale_ori(
                                kps_q_t[None],
                                torch.ones(1, len(kps_q_t), 1, 1, device=device)
                            )
                            lafs_t = KF.laf_from_center_scale_ori(
                                kps_t_t[None],
                                torch.ones(1, len(kps_t_t), 1, 1, device=device)
                            )

                            hw_q = torch.tensor([h_q, w_q], device=device)
                            hw_t = torch.tensor([h_t, w_t], device=device)

                            match_res = lg_matcher(
                                features_q.descriptors,
                                features_t.descriptors,
                                lafs_q,
                                lafs_t,
                                hw1=hw_q,
                                hw2=hw_t,
                            )

                            idxs = _parse_lightglue_output(match_res)

                            if idxs is not None and idxs.shape[0] >= 4:
                                pts_q = kps_q_t[idxs[:, 0]].detach().cpu().numpy()
                                pts_t = kps_t_t[idxs[:, 1]].detach().cpu().numpy()
                            else:
                                print(f"[Smart Merge] DISK+LightGlue 匹配点数不足")
            except Exception as e:
                print(f"[Smart Merge] DISK + LightGlue 匹配运行失败: {e}，将尝试降级")
                pts_q, pts_t = None, None

        # ========== SIFT + LightGlue ==========
        if method == "SIFT + LightGlue" or (pts_q is None and method != "SIFT (OpenCV)"):
            try:
                gray_q = cv2.cvtColor(query_img, cv2.COLOR_RGB2GRAY)
                gray_t = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))

                sift = cv2.SIFT_create(2048)
                kp_q, des_q = sift.detectAndCompute(clahe.apply(gray_q), None)
                kp_t, des_t = sift.detectAndCompute(clahe.apply(gray_t), None)

                if des_q is not None and des_t is not None and len(des_q) >= 4 and len(des_t) >= 4:
                    _, lg_matcher = self.get_kornia_models(device, "SIFT")

                    if lg_matcher is not None:
                        lafs_q = self.laf_from_opencv_kpts(kp_q, device)
                        lafs_t = self.laf_from_opencv_kpts(kp_t, device)

                        t_des_q = torch.from_numpy(des_q).to(device).float()
                        t_des_t = torch.from_numpy(des_t).to(device).float()

                        t_des_q = torch.nn.functional.normalize(t_des_q, p=1, dim=-1).sqrt()
                        t_des_t = torch.nn.functional.normalize(t_des_t, p=1, dim=-1).sqrt()

                        hw_q = torch.tensor([h_q, w_q], device=device)
                        hw_t = torch.tensor([h_t, w_t], device=device)

                        with torch.inference_mode():
                            match_res = lg_matcher(
                                t_des_q, t_des_t,
                                lafs_q, lafs_t,
                                hw1=hw_q, hw2=hw_t,
                            )

                            idxs = _parse_lightglue_output(match_res)

                            if idxs is not None and idxs.shape[0] >= 4:
                                kps_q = KF.get_laf_center(lafs_q).squeeze(0)
                                kps_t = KF.get_laf_center(lafs_t).squeeze(0)
                                pts_q = kps_q[idxs[:, 0]].detach().cpu().numpy()
                                pts_t = kps_t[idxs[:, 1]].detach().cpu().numpy()
                            else:
                                print(f"[Smart Merge] SIFT+LightGlue 匹配点数不足")
            except Exception as e:
                print(f"[Smart Merge] SIFT + LightGlue 匹配失败: {e}")
                pts_q, pts_t = None, None

        # ========== OpenCV SIFT (保底) ==========
        if pts_q is None and method == "SIFT (OpenCV)":
            try:
                gray_q = cv2.cvtColor(query_img, cv2.COLOR_RGB2GRAY)
                gray_t = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)
                clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
                sift = cv2.SIFT_create()

                kp_q, des_q = sift.detectAndCompute(clahe.apply(gray_q), None)
                kp_t, des_t = sift.detectAndCompute(clahe.apply(gray_t), None)

                if des_q is not None and des_t is not None and len(des_q) >= 4 and len(des_t) >= 4:
                    flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=5), dict(checks=50))
                    matches = flann.knnMatch(des_q, des_t, k=2)

                    good_matches = []
                    for match_pair in matches:
                        if len(match_pair) == 2:
                            m, n = match_pair
                            if m.distance < 0.75 * n.distance:
                                good_matches.append(m)

                    if len(good_matches) >= 6:
                        pts_q = np.float32([kp_q[m.queryIdx].pt for m in good_matches])
                        pts_t = np.float32([kp_t[m.trainIdx].pt for m in good_matches])
            except Exception as e:
                print(f"[Smart Merge] OpenCV SIFT 匹配失败: {e}")

        # ========== Homography ==========
        if pts_q is None or pts_t is None or len(pts_q) < 4:
            return None, None, 0, None

        magsac_flag = getattr(cv2, 'USAC_MAGSAC', cv2.RANSAC)
        H, inliers = cv2.findHomography(pts_q, pts_t, magsac_flag, 4.0)

        if H is None or inliers is None or np.sum(inliers) < 4:
            return None, None, 0, None

        num_inliers = int(np.sum(inliers))
        
        if method == "DISK + LightGlue" and pts_q is not None:
            method_used = "DISK" if pts_q is not None else "SIFT-LightGlue"
        elif method == "SIFT + LightGlue":
            method_used = "SIFT-LightGlue"
        else:
            method_used = "SIFT-OpenCV"
            
        return H, inliers, num_inliers, method_used
        
    def perform_kornia_alignment(self, query_img, train_img,
                                 method="DISK + LightGlue",
                                 warp_method="Homography + Optical Flow",
                                 optical_flow="RAFT-Small",
                                 device="cpu"):
        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]

        # ========== estimate_homography 粗对齐 ==========
        H, inliers, num_inliers, method_used = self.estimate_homography(
            query_img, train_img, method=method, device=device
        )

        if H is None:
            if warp_method == "Optical Flow":
                print("[Smart Merge] 粗对齐失败，回退到直接光流")
                return self.optical_flow_only_align(query_img, train_img, optical_flow, device)
            return None, None, False

        base_mask = np.ones((h_q, w_q), dtype=np.float32)

        warped_fg = cv2.warpPerspective(
            query_img, H, (w_t, h_t),
            flags=cv2.INTER_LANCZOS4,
            borderMode=cv2.BORDER_REFLECT101
        )
        warped_mask = cv2.warpPerspective(
            base_mask, H, (w_t, h_t),
            flags=cv2.INTER_LINEAR
        )

        if warp_method == "Optical Flow":
            refined_fg, refined_mask = self.refine_with_optical_flow(
                warped_fg, warped_mask, train_img, optical_flow, device
            )
            return refined_fg, refined_mask, True

        if warp_method == "Homography + Optical Flow":
            refined_fg, refined_mask = self.refine_with_optical_flow(
                warped_fg, warped_mask, train_img, optical_flow, device
            )
            return refined_fg, refined_mask, True

        return warped_fg, warped_mask, True
        
    def make_edge_safe_soft_mask(self, mask_float, feather_kernel):

        h, w = mask_float.shape[:2]
        mask_8u = (np.clip(mask_float, 0, 1) * 255).astype(np.uint8)
        
        if feather_kernel <= 0:
            return mask_float.astype(np.float32)
        
        pad = max(feather_kernel * 3, 30)
        padded = cv2.copyMakeBorder(mask_8u, pad, pad, pad, pad, cv2.BORDER_REPLICATE)
        
        erode_size = max(3, int(feather_kernel))
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erode_size, erode_size))
        eroded = cv2.erode(padded, kernel, iterations=1)
        
        blur_size = (int(feather_kernel) * 2) | 1
        blurred = cv2.GaussianBlur(eroded.astype(np.float32) / 255.0, (blur_size, blur_size), 0)
        
        soft = blurred[pad:pad + h, pad:pad + w]
        soft = np.minimum(soft, mask_float.astype(np.float32))  
        return soft
    
    
    def laplacian_pyramid_blend(self, img1, img2, mask, num_levels=4):

        h, w = img1.shape[:2]
        divisor = 2 ** num_levels
        pad_h = (divisor - h % divisor) % divisor
        pad_w = (divisor - w % divisor) % divisor

        if pad_h > 0 or pad_w > 0:
            img1 = cv2.copyMakeBorder(img1, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
            img2 = cv2.copyMakeBorder(img2, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
            mask = cv2.copyMakeBorder(mask, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)

        if mask.dtype != np.float32:
            mask = mask.astype(np.float32)
        if mask.max() > 1.0:
            mask = mask / 255.0
        if len(mask.shape) == 3:
            mask = mask[:, :, 0]

        img1_f = img1.astype(np.float32)
        img2_f = img2.astype(np.float32)

        gp1, gp2 = [img1_f], [img2_f]
        for i in range(num_levels):
            gp1.append(cv2.pyrDown(gp1[-1]))
            gp2.append(cv2.pyrDown(gp2[-1]))

        lp1 = [gp1[num_levels]]
        lp2 = [gp2[num_levels]]
        for i in range(num_levels, 0, -1):
            size = (gp1[i - 1].shape[1], gp1[i - 1].shape[0])
            G1_up = cv2.pyrUp(gp1[i], dstsize=size)
            G2_up = cv2.pyrUp(gp2[i], dstsize=size)
            lp1.append(gp1[i - 1] - G1_up)
            lp2.append(gp2[i - 1] - G2_up)

        lp_blend = []
        
        for i in range(num_levels + 1):
            l1 = lp1[i]
            l2 = lp2[i]
            
            if i == 0:
                m = cv2.resize(mask, (l1.shape[1], l1.shape[0]))
                if m.ndim == 2:
                    m = m[:, :, np.newaxis]
                blended = l1 * m + l2 * (1.0 - m)
            else:

                m = cv2.resize(mask, (l1.shape[1], l1.shape[0]))
                m_hard = (m > 0.5).astype(np.float32)
                if m_hard.ndim == 2:
                    m_hard = m_hard[:, :, np.newaxis]
                
                blended = np.where(m_hard > 0.5, l1, l2)
            
            lp_blend.append(blended)

        img_blend = lp_blend[0]
        for i in range(1, num_levels + 1):
            size = (lp_blend[i].shape[1], lp_blend[i].shape[0])
            img_blend = cv2.pyrUp(img_blend, dstsize=size) + lp_blend[i]

        img_blend = np.clip(img_blend, 0, 255).astype(np.uint8)

        if pad_h > 0 or pad_w > 0:
            img_blend = img_blend[:h, :w]

        return img_blend

    def smart_merge(self, original_image, edited_crop_B, match_method, warp_method, color_match, optical_flow,
                feather_kernel, adapt_thresh, adapt_local_match,
                merge_mode="All to One", use_gpu=False, force_recompute=False,
                original_crop_A=None, unique_id=None, prompt=None, extra_pnginfo=None):
        B_orig = original_image.shape[0]
        B_crop = edited_crop_B.shape[0]
        if B_orig == 0 or B_crop == 0:
            return (original_image,)
        
        if merge_mode == "All to One":
            B_orig_loop = 1
            crops_per_bg = B_crop
        else:
            B_orig_loop = B_orig
            crops_per_bg = max(1, B_crop // B_orig) if B_crop % B_orig == 0 else max(1, B_crop // B_orig)
        
        # 总进度 = 背景图数量 × 每背景的 crop 数量
        total_steps = B_orig_loop * crops_per_bg
        # 初始化进度条
        pbar = ProgressBar(total_steps) if HAS_PROGRESS_BAR else None
        
        device = torch.device("cuda" if torch.cuda.is_available() and use_gpu else "cpu")
        
        # === 缓存查询 ===
        if force_recompute:
            self._clear_cache()
            print("[Smart Merge] 🗑 强制重算,缓存已清空")
        
        align_key = self._make_align_key(
            original_image, edited_crop_B, original_crop_A,
            match_method, warp_method, optical_flow, merge_mode, use_gpu
        )
        cached_aligns = self._cache_get(align_key) if not force_recompute else None
        align_cache_hit = cached_aligns is not None
        if align_cache_hit:
            print(f"[Smart Merge] ✅ 命中对齐缓存,跳过特征匹配 (共 {len(cached_aligns)} 组)")
            new_aligns_to_save = None
        else:
            print("[Smart Merge] ⏳ 未命中缓存,执行完整对齐计算")
            new_aligns_to_save = []
        
        result_images = []
        global_crop_counter = 0
        
        for i in range(B_orig_loop):
            try:
                img_bg = (original_image[i].numpy() * 255).astype(np.uint8)
                if img_bg.shape[-1] == 4:
                    img_bg = img_bg[:, :, :3]
        
                start_idx = i * crops_per_bg
                end_idx = min(start_idx + crops_per_bg, B_crop)
                if start_idx >= B_crop:
                    result_images.append(torch.from_numpy(img_bg.astype(np.float32) / 255.0))
                    continue
                
                original_bg = img_bg.copy() 
                img_result = img_bg.copy()  
                
                for crop_idx in range(start_idx, end_idx):
                    
                    # 更新进度条
                    if pbar is not None:
                        pbar.update(1)
                    
                    align_idx = global_crop_counter
                    global_crop_counter += 1
        
                    img_fg = (edited_crop_B[crop_idx].numpy() * 255).astype(np.uint8)
                    if img_fg.shape[-1] == 4:
                        img_fg = img_fg[:, :, :3]
                    h_fg, w_fg = img_fg.shape[:2]
        
                    # ===== 对齐 =====
                    if align_cache_hit and align_idx < len(cached_aligns):
                        cached = cached_aligns[align_idx]
                        warped_fg = cached["warped_fg"].copy()
                        warped_mask = cached["warped_mask"].copy()
                    else:
                        img_bridge_A = None
                        if original_crop_A is not None and crop_idx < original_crop_A.shape[0]:
                            img_bridge_A = (original_crop_A[crop_idx].numpy() * 255).astype(np.uint8)
                            if img_bridge_A.shape[-1] == 4:
                                img_bridge_A = img_bridge_A[:, :, :3]
        
                        success_align = False
                        warped_fg = None
                        warped_mask = None
        
                        # 桥接对齐:B → A → BG 直接比例缩放
                        # if img_bridge_A is not None:
                            # h_A, w_A = img_bridge_A.shape[:2]
                            # if h_A > 0 and w_A > 0:
                                # H_A_to_BG = self.perform_sift_alignment(img_bridge_A, original_bg)
                                
                                # if H_A_to_BG is not None:
                                    # warped_fg_A, warped_mask_A, ok = self.perform_kornia_alignment(
                                        # img_fg, img_bridge_A,
                                        # method=match_method, warp_method=warp_method, 
                                        # optical_flow=optical_flow, device=device
                                    # )
                                    # h_bg, w_bg = img_bg.shape[:2]
                                    # if ok:
                                        # warped_fg = cv2.warpPerspective(warped_fg_A, H_A_to_BG, (w_bg, h_bg),
                                            # flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT101)
                                        # warped_mask = cv2.warpPerspective(warped_mask_A, H_A_to_BG, (w_bg, h_bg),
                                            # flags=cv2.INTER_LINEAR)
                                        # success_align = True
                                        # #print(f"[Smart Merge] 桥接对齐: B→A (kornia) → BG ({method_used}, 内点: {num_inliers})")
                                    # else:
                                        # print("[Smart Merge] B→A 对齐失败,使用等比映射保底")
                                        # sx, sy = w_A / float(w_fg), h_A / float(h_fg)
                                        # H_FG_to_A = np.array([[sx, 0, 0], [0, sy, 0], [0, 0, 1]], dtype=np.float64)
                                        # H_Total = np.dot(H_A_to_BG, H_FG_to_A)
                                        # warped_fg = cv2.warpPerspective(img_fg, H_Total, (w_bg, h_bg),
                                            # flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT101)
                                        # base_mask = np.ones((h_fg, w_fg), dtype=np.float32)
                                        # warped_mask = cv2.warpPerspective(base_mask, H_Total, (w_bg, h_bg),
                                            # flags=cv2.INTER_LINEAR)
                                        # success_align = True
                        # 桥接对齐:B → A → BG
                        if img_bridge_A is not None:
                            h_A, w_A = img_bridge_A.shape[:2]
                            if h_A > 0 and w_A > 0:
                                # A→BG: 用 SIFT 做粗对齐
                                H_A_to_BG = self.perform_sift_alignment(img_bridge_A, original_bg)
                                
                                if H_A_to_BG is not None:
                                    h_bg, w_bg = img_bg.shape[:2]
                                    
                                    sx, sy = w_A / float(w_fg), h_A / float(h_fg)
                                    H_FG_to_A = np.array([
                                        [sx, 0, 0],
                                        [0, sy, 0],
                                        [0, 0, 1]
                                    ], dtype=np.float64)
                                    
                                    H_Total = np.dot(H_A_to_BG, H_FG_to_A)
                                    
                                    warped_fg = cv2.warpPerspective(img_fg, H_Total, (w_bg, h_bg),
                                        flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT101)
                                    base_mask = np.ones((h_fg, w_fg), dtype=np.float32)
                                    warped_mask = cv2.warpPerspective(base_mask, H_Total, (w_bg, h_bg),
                                        flags=cv2.INTER_LINEAR)
                                    success_align = True
        
                        # 直接对齐
                        if not success_align:
                            warped_fg, warped_mask, ok = self.perform_kornia_alignment(
                                img_fg, original_bg,
                                method=match_method, warp_method=warp_method, optical_flow=optical_flow, device=device # img_bg --------------------
                            )
                            if ok:
                                success_align = True
                            else:
                                h_bg, w_bg = img_bg.shape[:2]
                                warped_fg = np.zeros_like(img_bg)
                                warped_mask = np.zeros((h_bg, w_bg), dtype=np.float32)
                                base_mask = np.ones((h_fg, w_fg), dtype=np.float32)
                                y_off = max(0, (h_bg - h_fg) // 2)
                                x_off = max(0, (w_bg - w_fg) // 2)
                                y1, y2 = y_off, min(y_off + h_fg, h_bg)
                                x1, x2 = x_off, min(x_off + w_fg, w_bg)
                                ch, cw = y2 - y1, x2 - x1
                                if ch > 0 and cw > 0:
                                    warped_fg[y1:y2, x1:x2] = img_fg[:ch, :cw]
                                    warped_mask[y1:y2, x1:x2] = base_mask[:ch, :cw]
        
                        if new_aligns_to_save is not None:
                            new_aligns_to_save.append({
                                "warped_fg": warped_fg.copy(),
                                "warped_mask": warped_mask.copy(),
                            })
        
                    # ===== bbox 裁切 =====
                    h_bg, w_bg = img_bg.shape[:2]
                    bounds_mask_float = warped_mask.copy()
                    bounds_mask_8u = (bounds_mask_float * 255).astype(np.uint8)
                    y_idx, x_idx = np.where(bounds_mask_float > 0.0)
        
                    #img_result = img_bg.copy()
                    if len(y_idx) == 0:
                        #img_bg = img_result
                        continue
        
                    ymin, ymax = y_idx.min(), y_idx.max()
                    xmin, xmax = x_idx.min(), x_idx.max()
                    pad = max(100, int(feather_kernel) * 2)
                    ymin = max(0, ymin - pad)
                    ymax = min(h_bg, ymax + pad)
                    xmin = max(0, xmin - pad)
                    xmax = min(w_bg, xmax + pad)
        
                    crop_bg = img_bg[ymin:ymax, xmin:xmax]                     # img_bg --------------------
                    crop_fg = warped_fg[ymin:ymax, xmin:xmax].copy()
                    crop_mask_float = bounds_mask_float[ymin:ymax, xmin:xmax]
                    crop_mask_8u = bounds_mask_8u[ymin:ymax, xmin:xmax]
                    h_crop, w_crop = crop_bg.shape[:2]
                    crop_result = crop_bg.copy()
                    current_color_match = color_match
        
                    # ===== 色彩迁移(以 crop_bg 为参考) =====

                    if current_color_match in ["Patch_based_color", "Boundary-Aware Color"]:
                        band_width = max(15, int(feather_kernel))
                        crop_fg = self.boundary_aware_color_sync(
                            crop_fg, crop_bg, crop_mask_float, band_width=band_width
                        )
                        
                        if current_color_match == "Patch_based_color":
                            try:
                                crop_fg = self.patch_based_color_sync(
                                    crop_fg, crop_bg, crop_mask_float,
                                    patch_size=max(32, int(feather_kernel) * 2),
                                    overlap=max(16, int(feather_kernel))
                                )
                                current_color_match = "Alpha Soft Blend"
                            except Exception as e:
                                print(f"[Smart Merge] Patch 色彩匹配失败: {e}, 降级 Alpha")
                                current_color_match = "Alpha Soft Blend"
                        else:
                            current_color_match = "Alpha Soft Blend"
        
                    elif current_color_match == "Histogram":
                        crop_fg = self.exact_histogram_match(crop_fg, crop_bg, crop_mask_float)
        
                    elif current_color_match == "LAB_Mean":
                        lab_bg = cv2.cvtColor(crop_bg, cv2.COLOR_RGB2LAB).astype(np.float32)
                        lab_fg = cv2.cvtColor(crop_fg, cv2.COLOR_RGB2LAB).astype(np.float32)
                        mean_bg, std_bg = cv2.meanStdDev(lab_bg, mask=crop_mask_8u)
                        mean_fg, std_fg = cv2.meanStdDev(lab_fg, mask=crop_mask_8u)
                        std_fg[std_fg == 0] = 1.0
                        lab_fg = (lab_fg - mean_fg.flatten()) * (std_bg.flatten() / std_fg.flatten()) + mean_bg.flatten()
                        lab_fg = np.clip(lab_fg, 0, 255).astype(np.uint8)
                        crop_fg = cv2.cvtColor(lab_fg, cv2.COLOR_LAB2RGB)
        
                    elif current_color_match == "Adaptive Local (strong)":
                        fg_float = crop_fg.astype(np.float32)
                        bg_float = crop_bg.astype(np.float32)
                        lab_bg = cv2.cvtColor(crop_bg, cv2.COLOR_RGB2LAB).astype(np.float32)
                        lab_fg = cv2.cvtColor(crop_fg, cv2.COLOR_RGB2LAB).astype(np.float32)
                        diff_lab = np.sqrt(np.sum((lab_bg - lab_fg) ** 2, axis=2))
                        diff_rgb = np.max(np.abs(bg_float - fg_float), axis=2)
                        diff_combined = np.maximum(diff_lab, diff_rgb)
                        diff_blur = cv2.GaussianBlur(diff_combined, (5, 5), 0)
                        _, thresh = cv2.threshold(diff_blur, float(adapt_thresh), 255.0, cv2.THRESH_BINARY)
                        thresh_8u = thresh.astype(np.uint8)
                        k_size = int(feather_kernel) | 1
                        kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k_size, k_size))
                        closed_mask = cv2.morphologyEx(thresh_8u, cv2.MORPH_CLOSE, kernel_close)
                        dilate_size = max(3, (k_size // 2) | 1)
                        kernel_dilate = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_size, dilate_size))
                        dilated_mask = cv2.dilate(closed_mask, kernel_dilate, iterations=1)
                        blur_size = max(3, (k_size // 2) | 1) * 2 - 1
                        final_diff_mask = cv2.GaussianBlur(dilated_mask.astype(np.float32) / 255.0, (blur_size, blur_size), 0)
                        diff_mask_3d = final_diff_mask[:, :, np.newaxis] * crop_mask_float[:, :, np.newaxis]
        
                        matched_fg = crop_fg.copy()
                        if adapt_local_match == "LAB_Mean":
                            mean_bg_lab = cv2.mean(lab_bg, mask=crop_mask_8u)[:3]
                            mean_fg_lab = cv2.mean(lab_fg, mask=crop_mask_8u)[:3]
                            lab_matched = lab_fg - np.array(mean_fg_lab) + np.array(mean_bg_lab)
                            matched_fg = cv2.cvtColor(np.clip(lab_matched, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
                        elif adapt_local_match == "Histogram":
                            matched_fg = self.exact_histogram_match(crop_fg, crop_bg, crop_mask_float)
                        elif adapt_local_match == "Reinhard":
                            mean_bg_v, std_bg_v = cv2.meanStdDev(lab_bg, mask=crop_mask_8u)
                            mean_fg_v, std_fg_v = cv2.meanStdDev(lab_fg, mask=crop_mask_8u)
                            
                            mean_bg_v = mean_bg_v.flatten()
                            std_bg_v = np.maximum(std_bg_v.flatten(), 1.0)
                            
                            mean_fg_v = mean_fg_v.flatten()
                            std_fg_v = np.maximum(std_fg_v.flatten(), 1.0)
                            
                            if np.mean(std_fg_v) < 8.0:
                                lab_matched = lab_fg - mean_fg_v + mean_bg_v
                            else:
                                lab_matched = (lab_fg - mean_fg_v) * (std_bg_v / std_fg_v) + mean_bg_v
                            matched_fg = cv2.cvtColor(np.clip(lab_matched, 0, 255).astype(np.uint8), cv2.COLOR_LAB2RGB)
                        elif adapt_local_match == "Adaptive Histogram":
                            lab_matched = lab_fg.copy()
                            for c in [1, 2]:
                                fg_ch = lab_fg[:, :, c].astype(np.uint8)
                                bg_ch = lab_bg[:, :, c].astype(np.uint8)
                                temp = self.exact_histogram_match(
                                    np.expand_dims(fg_ch, axis=2),
                                    np.expand_dims(bg_ch, axis=2),
                                    crop_mask_float
                                )
                                lab_matched[:, :, c] = temp[:, :, 0]
                            matched_fg = cv2.cvtColor(lab_matched.astype(np.uint8), cv2.COLOR_LAB2RGB)
        
                        adaptive_fg = (matched_fg.astype(np.float32) * diff_mask_3d) + (bg_float * (1.0 - diff_mask_3d))
                        crop_fg = np.clip(adaptive_fg, 0, 255).astype(np.uint8)
        
                    # ===== 融合 =====
                    if current_color_match == "Laplacian Pyramid Blend":
                        try:
                            num_levels = 4
                            if feather_kernel < 16: num_levels = 3
                            elif feather_kernel > 64: num_levels = 5
                            soft_mask = self.make_edge_safe_soft_mask(crop_mask_float, feather_kernel)
                            crop_result = self.laplacian_pyramid_blend(crop_fg, crop_bg, soft_mask, num_levels=num_levels)
                            current_color_match = "__DONE__"
                        except Exception as e:
                            print(f"[Smart Merge] 拉普拉斯金字塔融合失败: {e},降级 Alpha")
                            current_color_match = "Alpha Soft Blend"
        
                    elif current_color_match == "SeamlessClone (PS Auto Blend)":
                        clone_mask_8u = crop_mask_8u.copy()
                        shrink_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                        clone_mask_8u = cv2.erode(clone_mask_8u, shrink_kernel, iterations=1)
                        bx, by, bw, bh = cv2.boundingRect(clone_mask_8u)
                        safe_pad = 5
                        if (bw > 10 and bh > 10 and bx > safe_pad and by > safe_pad
                                and (bx + bw) < (w_crop - safe_pad) and (by + bh) < (h_crop - safe_pad)):
                            x1, y1 = bx - safe_pad, by - safe_pad
                            x2, y2 = bx + bw + safe_pad, by + bh + safe_pad
                            src_crop = crop_fg[y1:y2, x1:x2]
                            dst_crop = crop_bg[y1:y2, x1:x2]
                            mask_crop = clone_mask_8u[y1:y2, x1:x2]
                            center = ((x2 - x1) // 2, (y2 - y1) // 2)
                            try:
                                cloned_crop = cv2.seamlessClone(src_crop, dst_crop, mask_crop, center, cv2.NORMAL_CLONE)
                                crop_result[y1:y2, x1:x2] = cloned_crop
                                current_color_match = "__DONE__"
                            except Exception as e:
                                print(f"[Smart Merge] 泊松融合失败: {e}")
                                current_color_match = "Alpha Soft Blend"
                        else:
                            current_color_match = "Alpha Soft Blend"
        
                    # ===== Alpha 兜底融合 =====
                    if current_color_match != "__DONE__":
                        soft_mask = self.make_edge_safe_soft_mask(crop_mask_float, feather_kernel)
                        soft_mask_3d = soft_mask[:, :, np.newaxis]
                        fg_float = crop_fg.astype(np.float32)
                        bg_float = crop_bg.astype(np.float32)
        
                        if device.type == "cuda":
                            fg_gpu = torch.from_numpy(fg_float).to(device)
                            bg_gpu = torch.from_numpy(bg_float).to(device)
                            mask_gpu = torch.from_numpy(soft_mask_3d).to(device)
                            blended_gpu = (fg_gpu * mask_gpu) + (bg_gpu * (1.0 - mask_gpu))
                            crop_result = torch.clamp(blended_gpu, 0, 255).byte().cpu().numpy()
                        else:
                            blended = (fg_float * soft_mask_3d) + (bg_float * (1.0 - soft_mask_3d))
                            crop_result = np.clip(blended, 0, 255).astype(np.uint8)
        
                    # ===== Step 5: 渐变过渡，避免硬边 =====
                    edge_blend = np.zeros_like(crop_mask_float)
                    edge_width = 5  # 渐变宽度
                    
                    if ymin == 0:
                        weight = np.linspace(1, 0, edge_width)[:, None]
                        edge_blend[:edge_width, :] = weight * crop_mask_float[:edge_width, :]
                    if ymax == h_bg:
                        weight = np.linspace(0, 1, edge_width)[:, None]
                        edge_blend[-edge_width:, :] = weight * crop_mask_float[-edge_width:, :]
                    if xmin == 0:
                        weight = np.linspace(1, 0, edge_width)[None, :]
                        edge_blend[:, :edge_width] = np.maximum(edge_blend[:, :edge_width], 
                                                                 weight * crop_mask_float[:, :edge_width])
                    if xmax == w_bg:
                        weight = np.linspace(0, 1, edge_width)[None, :]
                        edge_blend[:, -edge_width:] = np.maximum(edge_blend[:, -edge_width:], 
                                                                  weight * crop_mask_float[:, -edge_width:])
                    
                    if edge_blend.max() > 0.01:
                        eb3 = edge_blend[:, :, np.newaxis]
                        crop_result = (crop_fg.astype(np.float32) * eb3 
                                       + crop_result.astype(np.float32) * (1.0 - eb3))
                        crop_result = np.clip(crop_result, 0, 255).astype(np.uint8)
        
                    img_result[ymin:ymax, xmin:xmax] = crop_result
                    img_bg = img_result.copy()  
        
                result_images.append(torch.from_numpy(img_result.astype(np.float32) / 255.0))   # img_bg --------------------
        
            except Exception as e:
                import traceback
                print(f"[Smart Merge 致命错误] {e}")
                traceback.print_exc()
                result_images.append(original_image[i])
                
        # 完成进度条
        if pbar is not None:
            pbar.update_absolute(total_steps, total_steps)
        
        if new_aligns_to_save is not None and len(new_aligns_to_save) > 0:
            self._cache_put(align_key, new_aligns_to_save)
            print(f"[Smart Merge] 💾 已缓存 {len(new_aligns_to_save)} 个对齐结果")
        
        return (torch.stack(result_images),)
