import torch
import numpy as np
import cv2
import os

import kornia as K
import kornia.feature as KF

try:
    from comfy.utils import ProgressBar
    HAS_PROGRESS_BAR = True
except ImportError:
    HAS_PROGRESS_BAR = False

try:
    from server import PromptServer
    HAS_PROMPT_SERVER = True
except ImportError:
    PromptServer = None
    HAS_PROMPT_SERVER = False

# 重定向缓存目录到 ComfyUI/models/elementEasy
try:
    import folder_paths
    models_dir = folder_paths.models_dir
    element_easy_dir = os.path.join(models_dir, "elementEasy")
    os.makedirs(element_easy_dir, exist_ok=True)
    torch.hub.set_dir(element_easy_dir)
    print(f"[Smart Merge] 成功将模型下载和缓存目录重定向至: {element_easy_dir} | Redirected model/cache dir to: {element_easy_dir}")
except Exception:
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

    # 光流最大位移限幅(px)
    MAX_FLOW_PX = 15.0

    DESCRIPTION = (
        "智能局部重绘回贴节点: 将 AI 编辑后的局部裁块(B)自动对齐、畸变校正、色彩统一后融合回原图。\n"
        "· 接入 original_crop_A(编辑前裁块)→ 桥接对齐 B→A→BG, 对位最稳, 且同样执行光流畸变校正;\n"
        "· 不接 crop_A → 背景上自动特征匹配(DISK/SIFT+LightGlue), 失败自动逐级降级至 OpenCV SIFT / 光流兜底。\n"
        "· 三个图像端口原生支持 List / Batch / 单张输入(节点已声明 INPUT_IS_LIST, 引擎不会逐项展开), "
        "无需外接 'Image List To Image Batch' 节点; 各裁块尺寸可不同。\n"
        "推荐: warp_method=Homography + Optical Flow, match_method=DISK + LightGlue, use_gpu=True。\n"
        "--------------------------------------------------\n"
        "Smart local-inpaint re-composite node: aligns the AI-edited crop (B), corrects its deformation, "
        "harmonizes color, then blends it back into the original image.\n"
        "· With original_crop_A (pre-edit crop) connected → bridge alignment B→A→BG, most reliable placement, "
        "optical-flow deformation correction still applies;\n"
        "· Without crop_A → automatic feature matching on the background (DISK/SIFT+LightGlue) with graceful "
        "fallback to OpenCV SIFT / optical flow.\n"
        "· All three image ports natively accept list / batch / single images (INPUT_IS_LIST declared, so the "
        "engine will NOT expand the node per item) — no external 'Image List To Image Batch' node needed; "
        "crops may have different sizes.\n"
        "Recommended: warp_method=Homography + Optical Flow, match_method=DISK + LightGlue, use_gpu=True."
    )
    OUTPUT_TOOLTIPS = ("融合后的完整图像(batch) | Merged image(s) as a standard batch",)

    @staticmethod
    def _send_progress(value, total, node_id=None):
        """发送进度条更新到 ComfyUI 前端 / Push progress-bar updates to the ComfyUI frontend"""
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

    @staticmethod
    def _items_fingerprint(items):
        """list 输入的整体指纹, 用于对齐缓存 / Fingerprint of an item list (for the alignment cache)"""
        import hashlib
        if items is None:
            return "none"
        joined = ";".join(SmartMergeImages._tensor_fingerprint(t) for t in items)
        return hashlib.md5(joined.encode("utf-8")).hexdigest()[:24]

    # ================= 输入归一化 / Input normalization =================
    # 配合 INPUT_IS_LIST=True: 引擎会把 List 原样传入, 这里统一展平为条目列表。

    @staticmethod
    def _normalize_image_items(image_input):
        """
        将任意形态的 IMAGE 输入统一为 list[(H, W, C) float32 tensor, 值域 [0,1]]。
        Normalize any IMAGE input into a list of (H,W,C) float tensors in [0,1].
        支持 / Supports:
          · List / tuple (可嵌套 / nested) — INPUT_IS_LIST 下 List 原样到达这里
          · batch 张量 / batched tensor (N, H, W, C)
          · 单张 / single (H, W, C) 或灰度
          · numpy 数组 / numpy arrays
          · uint8 或 0-255 浮点自动归一化到 [0,1] / auto-normalize 0-255 to [0,1]
        """
        items = []

        def _collect(x):
            if x is None:
                return
            if isinstance(x, (list, tuple)):
                for e in x:
                    _collect(e)          # 递归展平
                return
            if isinstance(x, np.ndarray):
                try:
                    x = torch.from_numpy(x)
                except Exception:
                    return
            if not isinstance(x, torch.Tensor):
                return
            t = x.detach().cpu().float()
            if t.dim() == 2:                       # (H, W) 灰度 → (H, W, 1)
                t = t.unsqueeze(-1)
            if t.dim() == 3:                       # (H, W, C) 单张
                if t.shape[-1] == 1:
                    t = t.repeat(1, 1, 3)
                items.append(t)
            elif t.dim() == 4:                     # (N, H, W, C) → 拆为 N 个条目
                if t.shape[-1] == 1:
                    t = t.repeat(1, 1, 1, 3)
                for j in range(t.shape[0]):
                    items.append(t[j])
            # 其他维度忽略 / other dims ignored

        _collect(image_input)

        # 0-255 → [0,1] 自动归一化
        for idx, t in enumerate(items):
            if t.numel() > 0 and float(t.max()) > 1.0 + 1e-4:
                items[idx] = t / 255.0
        return items

    @staticmethod
    def _item_to_uint8_rgb(t):
        """单张 [0,1] float tensor → (H, W, 3) uint8 numpy (丢弃 alpha / drop alpha)"""
        arr = t.detach().cpu().numpy() if hasattr(t, "detach") else np.asarray(t)
        arr = np.clip(arr * 255.0, 0, 255).astype(np.uint8)
        if arr.ndim == 3 and arr.shape[-1] == 4:
            arr = arr[:, :, :3]
        return arr

    @staticmethod
    def _unwrap_scalar(v, default=None):
        """★ 本轮修复: INPUT_IS_LIST 模式下控件参数可能以单元素 list 传入 → 解包为标量
        ★ This round's fix: under INPUT_IS_LIST, widget params may arrive as single-element lists → unwrap"""
        if isinstance(v, (list, tuple)):
            if len(v) == 0:
                return default
            return v[0]
        return v

    @classmethod
    def _make_align_key(cls, original_items, edited_items, cropA_items,
                        match_method, warp_method, optical_flow, merge_mode, use_gpu):
        return "|".join([
            cls._items_fingerprint(original_items),
            cls._items_fingerprint(edited_items),
            cls._items_fingerprint(cropA_items),
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
                    print(f"[Smart Merge] DISK & LightGlue 模型已就绪 (设备: {device}) | DISK & LightGlue models ready (device: {device})")
                except Exception as e:
                    print(f"[Smart Merge] 初始化 DISK 权重失败: {e} | Failed to initialize DISK weights: {e}")
            return cls._disk_model, cls._lg_matcher_disk
        elif "SIFT" in method:
            if cls._lg_matcher_sift is None:
                try:
                    cls._lg_matcher_sift = KF.LightGlueMatcher("sift").eval().to(device)
                    print(f"[Smart Merge] SIFT-LightGlue 模型已就绪 (设备: {device}) | SIFT-LightGlue model ready (device: {device})")
                except Exception as e:
                    print(f"[Smart Merge] 初始化 SIFT-LightGlue 权重失败: {e} | Failed to initialize SIFT-LightGlue weights: {e}")
            return None, cls._lg_matcher_sift
        return None, None

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {
                    "tooltip": "原始背景图(未编辑的完整图像)。All to One 模式下只有第一张会被使用。\n"
                               "原生支持 List / Batch / 单张输入(节点已声明 INPUT_IS_LIST, 引擎不会逐项展开), 无需外接 Image List To Image Batch。\n"
                               "--------------------------------------------------\n"
                               "Original background image(s) before editing. In 'All to One' mode only the first one is used.\n"
                               "Natively accepts list / batch / single image (INPUT_IS_LIST declared, no per-item expansion) — "
                               "no external 'Image List To Image Batch' node needed."
                }),
                "edited_crop_B": ("IMAGE", {
                    "tooltip": "AI 编辑后的局部裁块(B), 将被对齐、畸变校正并贴回背景。可批量; 各裁块尺寸可不同(保持各自原始分辨率)。\n"
                               "原生支持 List / Batch / 单张输入, 多个裁块在单次执行中全部处理, 只输出一张合成图。\n"
                               "--------------------------------------------------\n"
                               "AI-edited local crop (B). It will be aligned, de-warped and re-composited onto the background. "
                               "Crops may have different sizes (each keeps its native resolution).\n"
                               "Natively accepts list / batch / single image — all crops are processed in ONE execution, producing one merged image."
                }),
                "match_method": ([
                    "DISK + LightGlue",
                    "SIFT + LightGlue",
                    "SIFT (OpenCV)"
                ], {
                    "tooltip": "粗对齐的特征匹配算法:\n"
                               "· DISK+LightGlue 精度最高(首次运行自动下载权重)\n"
                               "· SIFT+LightGlue 次之\n"
                               "· SIFT(OpenCV) 纯传统算法, 无需权重\n"
                               "高级算法失败时会自动逐级降级, 最终保底为光流。\n"
                               "--------------------------------------------------\n"
                               "Feature-matching method for coarse alignment:\n"
                               "· DISK+LightGlue: highest accuracy (weights auto-downloaded on first run)\n"
                               "· SIFT+LightGlue: second best\n"
                               "· SIFT (OpenCV): pure classic algorithm, no weights needed\n"
                               "If a high-level method fails, it automatically falls back step-by-step, ending at optical flow."
                }),
                "warp_method": ([
                    "Homography",
                    "Homography + Optical Flow",
                    "Optical Flow"
                ], {
                    "tooltip": "形变(畸变)校正方式:\n"
                               "· Homography 仅整体透视/旋转/缩放校正\n"
                               "· Homography + Optical Flow 在其上叠加非刚性光流细化, 可校正局部畸变(推荐)\n"
                               "· Optical Flow 实际仍会先做单应性再光流\n"
                               "注: 接了 crop_A 的桥接对齐同样会执行光流校正。\n"
                               "--------------------------------------------------\n"
                               "Deformation-correction strategy:\n"
                               "· Homography: global perspective/rotation/scale correction only\n"
                               "· Homography + Optical Flow: adds non-rigid optical-flow refinement on top, fixes local distortion (recommended)\n"
                               "· Optical Flow: internally still does a homography first, then flow\n"
                               "Note: bridge alignment (with crop_A) also applies optical-flow correction."
                }),
                "optical_flow": ([
                    "Farneback",
                    "DIS",
                    "RAFT-Small",
                    "RAFT-Large"
                ], {
                    "tooltip": "光流算法:\n"
                               "· RAFT 质量最好(首次运行自动下载权重)\n"
                               "· DIS 速度快效果好\n"
                               "· Farneback 最快最弱\n"
                               "所选算法不可用时自动降级为 Farneback。\n"
                               "--------------------------------------------------\n"
                               "Optical-flow algorithm:\n"
                               "· RAFT: best quality (weights auto-downloaded on first run)\n"
                               "· DIS: fast with good quality\n"
                               "· Farneback: fastest but weakest\n"
                               "Auto-falls back to Farneback if the chosen one is unavailable."
                }),
                "color_match": ([
                    "Patch_based_color",
                    "Boundary-Aware Color",
                    "Laplacian Pyramid Blend",
                    "SeamlessClone (PS Auto Blend)",
                    "Adaptive Local (strong)",
                    "Histogram",
                    "LAB_Mean",
                    "Alpha Soft Blend",
                    "None"
                ], {
                    "tooltip": "色彩迁移/融合策略(消除局部编辑与背景的色差):\n"
                               "· Patch_based_color 分块LAB色差同步(推荐, 色差大时效果好)\n"
                               "· Boundary-Aware 边界感知色彩\n"
                               "· Laplacian Pyramid 金字塔融合\n"
                               "· SeamlessClone 泊松融合(PS自动混合)\n"
                               "· Adaptive Local 仅校正差异区域(配合 adapt_thresh)\n"
                               "· Histogram 严格直方图匹配\n"
                               "· LAB_Mean 均值方差匹配\n"
                               "· Alpha Soft Blend 仅羽化混合\n"
                               "· None 等同于 Alpha 混合。\n"
                               "--------------------------------------------------\n"
                               "Color transfer / blending strategy (removes color cast between the edited crop and background):\n"
                               "· Patch_based_color: patch-wise LAB color sync (recommended for strong casts)\n"
                               "· Boundary-Aware: boundary-aware color correction\n"
                               "· Laplacian Pyramid: multi-band pyramid blending\n"
                               "· SeamlessClone: Poisson blending (PS-style auto blend)\n"
                               "· Adaptive Local: corrects only differing regions (uses adapt_thresh)\n"
                               "· Histogram: strict histogram matching\n"
                               "· LAB_Mean: mean/std matching in LAB\n"
                               "· Alpha Soft Blend: feathered alpha blending only\n"
                               "· None: same as Alpha Soft Blend"
                }),
                "feather_kernel": ("INT", {
                    "default": 20, "min": 0, "max": 256, "step": 1,
                    "tooltip": "羽化半径(px): 贴图边缘柔化宽度, 兼作 Patch/Boundary 色彩同步的块尺寸基准。一般 15~40; 越大过渡越柔但可能侵入更多原始内容。\n"
                               "--------------------------------------------------\n"
                               "Feather radius (px): edge-softening width of the pasted crop; also used as the patch-size basis for Patch/Boundary color sync. "
                               "Typical 15~40; larger = softer transition but may eat into more original content."
                }),
                "adapt_thresh": ("INT", {
                    "default": 25, "min": 0, "max": 255, "step": 1,
                    "tooltip": "仅 Adaptive Local (strong) 模式使用: 判定'差异区域'的阈值(0-255), 低于该值的区域保持背景原样。值越小, 参与校正的像素越多。\n"
                               "--------------------------------------------------\n"
                               "Only used by 'Adaptive Local (strong)': threshold (0-255) defining 'differing regions'; pixels below it keep the original background. "
                               "Lower value = more pixels get corrected."
                }),
                "adapt_local_match": ([
                    "Histogram",
                    "LAB_Mean",
                    "Reinhard",
                    "Adaptive Histogram",
                    "None"
                ], {
                    "tooltip": "仅 Adaptive Local (strong) 模式使用: 对差异区域施加的局部色彩匹配算法; None 表示直接用背景原色覆盖差异区。\n"
                               "--------------------------------------------------\n"
                               "Only used by 'Adaptive Local (strong)': local color-matching algorithm applied to differing regions; "
                               "None means those regions are overwritten with the original background color."
                }),
                "merge_mode": (["All to One", "One to One"], {
                    "tooltip": "· All to One: 所有 B 裁块按顺序贴回第一张背景图(多元素拼贴, 输出 1 张)\n"
                               "· One to One: 背景与裁块一一对应(输出与背景数量相同的 batch)。\n"
                               "--------------------------------------------------\n"
                               "· All to One: paste all B crops sequentially onto the first background (multi-element collage, 1 output)\n"
                               "· One to One: background-crop pairs matched one by one (outputs a batch with the same count as backgrounds)"
                }),
                "use_gpu": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "使用 CUDA 加速特征匹配/光流/混合。无显卡或显存不足时可关闭。\n"
                               "--------------------------------------------------\n"
                               "Use CUDA acceleration for matching / optical flow / blending. Turn off if no GPU or VRAM is insufficient."
                }),
                "force_recompute": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "强制清空对齐缓存并重新计算(缓存容量 4 组, LRU)。输入未变但想重跑对齐时开启。\n"
                               "--------------------------------------------------\n"
                               "Force-clear the alignment cache (LRU, 4 entries) and recompute. Enable when inputs are unchanged but you want alignment re-run."
                }),
            },
            "optional": {
                "original_crop_A": ("IMAGE", {
                    "tooltip": "可选: 编辑前的局部裁块(A), 与 B 同视角同内容。提供后启用桥接对齐 B→(等比)→A→(SIFT)→BG, 对位比自动匹配更稳, 且仍执行光流畸变校正; 不提供则直接在背景上自动特征匹配。\n"
                               "原生支持 List / Batch / 单张输入; A 与 B 数量/尺寸不必严格一致(自动按索引配对)。\n"
                               "--------------------------------------------------\n"
                               "Optional: pre-edit local crop (A), same viewpoint/content as B. When provided, bridge alignment B→(scale)→A→(SIFT)→BG is used — "
                               "more reliable placement than auto-matching, and optical-flow deformation correction still applies.\n"
                               "Natively accepts list / batch / single image; A and B counts/sizes need not match exactly (paired by index)."
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("Merged_Image",)
    FUNCTION = "smart_merge"
    CATEGORY = "Element_easy/image"

    # 声明接受 List 输入, 阻止 ComfyUI 对 List 输入做隐式"逐项展开"
    INPUT_IS_LIST = True

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
                        trim = int(len(sorted_diff) * 0.1)  # 去掉 10% / trim 10%
                        if trim > 0:
                            trimmed_diff = sorted_diff[trim:-trim]
                        else:
                            trimmed_diff = sorted_diff
                        diff = np.mean(trimmed_diff)
                        diff_std = np.std(sorted_diff)
                        diff_max = abs(diff) + 2 * diff_std
                        diff = np.clip(diff, -diff_max, diff_max)
                    patch_correction[:, :, c] = diff

                hann_y = np.hanning(patch_size)[:, np.newaxis]
                hann_x = np.hanning(patch_size)[np.newaxis, :]
                patch_weight = hann_y * hann_x
                patch_weight = patch_weight * patch_mask.astype(np.float32)

                for c in range(3):
                    correction_sum[y:y2, x:x2, c] += patch_correction[:, :, c] * patch_weight
                weight_map[y:y2, x:x2] += patch_weight
                valid_patches += 1

        if valid_patches == 0:
            print("[Patch Sync] 无有效 patch，回退到全局均值 | No valid patch found, falling back to global mean")
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
                correction_field[:, :, c].astype(np.float32), 5  # 5x5 中值滤波
            )
        for c in range(3):
            correction_field[:, :, c] = cv2.GaussianBlur(
                correction_field[:, :, c],
                (overlap // 2 * 2 + 1, overlap // 2 * 2 + 1), 0
            )

        mask_3d = mask_bool.astype(np.float32)[:, :, np.newaxis]
        correction_field = correction_field * mask_3d

        result = lab_fg + correction_field
        result = np.clip(result, 0, 255).astype(np.uint8)
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

            pos = variance[variance > 0]
            denom = np.median(pos) if pos.size > 0 else 1.0
            reliability = np.exp(-variance / (denom + 1e-6))
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
                print(f"[Smart Merge] RAFT 不可用 ({e}) | RAFT unavailable ({e})")

        # DIS
        if "DIS" in optical_flow:
            try:
                gray_warped = cv2.cvtColor(warped_fg, cv2.COLOR_RGB2GRAY)
                gray_target = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)
                return self._refine_with_dis(gray_warped, gray_target, warped_fg, warped_mask, train_img)
            except Exception as e:
                print(f"[Smart Merge] DIS 不可用 ({e}) | DIS unavailable ({e})")

        gray_warped = cv2.cvtColor(warped_fg, cv2.COLOR_RGB2GRAY)
        gray_target = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)
        return self._refine_with_farneback(gray_warped, gray_target, warped_fg, warped_mask, train_img)

    def _refine_with_raft(self, warped_fg, warped_mask, train_img, device, use_large=False):
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
                print("[Smart Merge] RAFT-large 模型已加载 | RAFT-large model loaded")
            else:
                self._raft_model = raft.raft_small(pretrained=True).eval().to(device)
                print("[Smart Merge] RAFT-small 模型已加载 | RAFT-small model loaded")
            self._raft_device = device
            self._raft_large = use_large

        with torch.no_grad():
            flow_list = self._raft_model(t1, t2)
            flow_full = flow_list[-1][0].cpu().numpy().transpose(1, 2, 0)

        flow = flow_full[:h_t, :w_t].copy()

        flow[:, :, 0] = cv2.medianBlur(flow[:, :, 0].astype(np.float32), 3)
        flow[:, :, 1] = cv2.medianBlur(flow[:, :, 1].astype(np.float32), 3)

        max_flow = self.MAX_FLOW_PX
        flow_mag = np.linalg.norm(flow, axis=2)
        scale_factor = np.minimum(flow_mag, max_flow) / (flow_mag + 1e-8)
        flow[:, :, 0] *= scale_factor
        flow[:, :, 1] *= scale_factor

        grid_x, grid_y = np.meshgrid(np.arange(w_t), np.arange(h_t))
        map_x = (grid_x + flow[:, :, 0]).astype(np.float32)
        map_y = (grid_y + flow[:, :, 1]).astype(np.float32)

        refined_fg = cv2.remap(warped_fg, map_x, map_y,
                               interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
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

        max_flow = self.MAX_FLOW_PX
        flow_mag = np.linalg.norm(flow, axis=2)
        scale_factor = np.minimum(flow_mag, max_flow) / (flow_mag + 1e-8)
        flow[:, :, 0] *= scale_factor
        flow[:, :, 1] *= scale_factor

        grid_x, grid_y = np.meshgrid(np.arange(w_t), np.arange(h_t))
        map_x = (grid_x + flow[:, :, 0]).astype(np.float32)
        map_y = (grid_y + flow[:, :, 1]).astype(np.float32)

        refined_fg = cv2.remap(warped_fg, map_x, map_y,
                               interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
        return refined_fg, warped_mask.copy()

    def _refine_with_farneback(self, gray_warped, gray_target, warped_fg, warped_mask, train_img):
        h_t, w_t = train_img.shape[:2]

        mask_8u = (warped_mask * 255).astype(np.uint8)
        erode_size = min(25, min(h_t, w_t) // 4)
        erode_size = max(3, erode_size)
        erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erode_size, erode_size))
        inner_mask = cv2.erode(mask_8u, erode_kernel, iterations=1)
        inner_mask_f = inner_mask.astype(np.float32) / 255.0

        flow_fwd = cv2.calcOpticalFlowFarneback(
            gray_warped, gray_target, None,
            0.5, 2, 7, 5, 5, 1.1, cv2.OPTFLOW_FARNEBACK_GAUSSIAN
        )
        flow_bwd = cv2.calcOpticalFlowFarneback(
            gray_target, gray_warped, None,
            0.5, 2, 7, 5, 5, 1.1, cv2.OPTFLOW_FARNEBACK_GAUSSIAN
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
            print("[Smart Merge] 警告：低纹理图像，纹理检测失效 | Warning: low-texture image, texture detection ineffective")

        reliability = inner_mask_f * consistency_mask * texture_mask
        reliability = np.clip(reliability, 0.2, 1.0)

        flow = flow_fwd.copy()
        max_flow = self.MAX_FLOW_PX
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
        return refined_fg, warped_mask.copy()

    def optical_flow_only_align(self, query_img, train_img, optical_flow="RAFT-Small", device="cpu"):
        h_t, w_t = train_img.shape[:2]
        h_q, w_q = query_img.shape[:2]

        if (h_q, w_q) == (h_t, w_t):
            query_resized = query_img
            valid = np.ones((h_t, w_t), dtype=np.float32)
        else:

            scale = min(w_t / float(w_q), h_t / float(h_q))
            new_w = max(1, int(round(w_q * scale)))
            new_h = max(1, int(round(h_q * scale)))
            resized = cv2.resize(query_img, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

            query_resized = np.zeros((h_t, w_t, 3), dtype=query_img.dtype)
            x_off = (w_t - new_w) // 2
            y_off = (h_t - new_h) // 2
            query_resized[y_off:y_off + new_h, x_off:x_off + new_w] = resized

            valid = np.zeros((h_t, w_t), dtype=np.float32)
            valid[y_off:y_off + new_h, x_off:x_off + new_w] = 1.0

        full_mask = valid
        border = 10
        full_mask[:border, :] = 0
        full_mask[-border:, :] = 0
        full_mask[:, :border] = 0
        full_mask[:, -border:] = 0
        full_mask = cv2.GaussianBlur(full_mask, (21, 21), 0)

        return self.refine_with_optical_flow(query_resized, full_mask, train_img, optical_flow, device)

    @staticmethod
    def _homography_is_sane(H, h_q, w_q, h_t, w_t):
        """校验单应性矩阵是否退化/镜像/过度形变 / Validate homography: degenerate, mirrored or over-deformed"""
        if H is None:
            return False
        H = np.asarray(H, dtype=np.float64)
        if not np.all(np.isfinite(H)):
            return False
        det = np.linalg.det(H[:2, :2])
        if abs(det) < 1e-8:      # 奇异/退化
            return False
        if det < 0:              # 镜像翻转
            return False
        corners = np.array([[0, 0], [w_q, 0], [w_q, h_q], [0, h_q]], dtype=np.float64)
        ones = np.ones((4, 1))
        pts = np.hstack([corners, ones]) @ H.T
        wcol = pts[:, 2]
        if np.any(np.abs(wcol) < 1e-9):
            return False
        pts = pts[:, :2] / wcol[:, None]
        x, y = pts[:, 0], pts[:, 1]
        area_dst = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
        area_src = max(float(w_q) * float(h_q), 1.0)
        ratio = area_dst / area_src
        if ratio < 0.02 or ratio > 30.0:   # 缩成一点 / 疯狂放大都视为异常
            return False
        if pts[:, 0].min() < -2 * w_t or pts[:, 0].max() > 3 * w_t:
            return False
        if pts[:, 1].min() < -2 * h_t or pts[:, 1].max() > 3 * h_t:
            return False
        return True

    def estimate_homography(self, query_img, train_img, method="DISK + LightGlue", device="cpu"):
        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]
        pts_q, pts_t = None, None
        self._match_level = None

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
                                kps_q_t[None], torch.ones(1, len(kps_q_t), 1, 1, device=device))
                            lafs_t = KF.laf_from_center_scale_ori(
                                kps_t_t[None], torch.ones(1, len(kps_t_t), 1, 1, device=device))
                            hw_q = torch.tensor([h_q, w_q], device=device)
                            hw_t = torch.tensor([h_t, w_t], device=device)
                            match_res = lg_matcher(
                                features_q.descriptors, features_t.descriptors,
                                lafs_q, lafs_t, hw1=hw_q, hw2=hw_t,
                            )
                            idxs = _parse_lightglue_output(match_res)
                            if idxs is not None and idxs.shape[0] >= 4:
                                pts_q = kps_q_t[idxs[:, 0]].detach().cpu().numpy()
                                pts_t = kps_t_t[idxs[:, 1]].detach().cpu().numpy()
                                self._match_level = "DISK"
                        if self._match_level is None:
                            print("[Smart Merge] DISK+LightGlue 匹配点数不足 | DISK+LightGlue matched too few points")
            except Exception as e:
                print(f"[Smart Merge] DISK + LightGlue 匹配运行失败: {e}，将尝试降级 | DISK+LightGlue matching failed: {e}, will try fallback")
                pts_q, pts_t = None, None

        # ========== SIFT + LightGlue ==========
        # (DISK 模式下 DISK 失败时自动降级到这里; 用户明确选 SIFT(OpenCV) 时跳过)
        if (pts_q is None) and method in ("DISK + LightGlue", "SIFT + LightGlue"):
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
                            match_res = lg_matcher(t_des_q, t_des_t, lafs_q, lafs_t, hw1=hw_q, hw2=hw_t)
                        idxs = _parse_lightglue_output(match_res)
                        if idxs is not None and idxs.shape[0] >= 4:
                            kps_q = KF.get_laf_center(lafs_q).squeeze(0)
                            kps_t = KF.get_laf_center(lafs_t).squeeze(0)
                            pts_q = kps_q[idxs[:, 0]].detach().cpu().numpy()
                            pts_t = kps_t[idxs[:, 1]].detach().cpu().numpy()
                            self._match_level = "SIFT-LightGlue"
                        else:
                            print("[Smart Merge] SIFT+LightGlue 匹配点数不足 | SIFT+LightGlue matched too few points")
            except Exception as e:
                print(f"[Smart Merge] SIFT + LightGlue 匹配失败: {e} | SIFT+LightGlue matching failed: {e}")
                pts_q, pts_t = None, None

        # ========== OpenCV SIFT (保底) ==========
        if pts_q is None:
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
                        self._match_level = "SIFT-OpenCV"
            except Exception as e:
                print(f"[Smart Merge] OpenCV SIFT 匹配失败: {e} | OpenCV SIFT matching failed: {e}")

        # ========== Homography ==========
        if pts_q is None or pts_t is None or len(pts_q) < 4:
            return None, None, 0, None

        magsac_flag = getattr(cv2, 'USAC_MAGSAC', cv2.RANSAC)
        H, inliers = cv2.findHomography(pts_q, pts_t, magsac_flag, 4.0)
        if H is None or inliers is None or np.sum(inliers) < 4:
            return None, None, 0, None

        if not self._homography_is_sane(H, h_q, w_q, h_t, w_t):
            print("[Smart Merge] 单应性矩阵异常(退化/镜像/过度形变), 放弃并降级 | Homography invalid (degenerate/mirrored/over-deformed), rejected and falling back")
            return None, None, 0, None

        num_inliers = int(np.sum(inliers))
        method_used = self._match_level or method
        return H, inliers, num_inliers, method_used

    def perform_kornia_alignment(self, query_img, train_img, method="DISK + LightGlue",
                                 warp_method="Homography + Optical Flow", optical_flow="RAFT-Small",
                                 device="cpu", preset_H=None):
        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]

        # ========== 粗对齐 ==========
        H = None
        method_used = None
        num_inliers = 0

        if preset_H is not None:
            if self._homography_is_sane(preset_H, h_q, w_q, h_t, w_t):
                H = preset_H
                method_used = "Bridge(B→A→BG)"
                num_inliers = -1
            else:
                print("[Smart Merge] 桥接单应性异常, 降级为自动特征对齐 | Bridge homography invalid, falling back to automatic feature alignment")

        if H is None:
            H, inliers, num_inliers, method_used = self.estimate_homography(
                query_img, train_img, method=method, device=device
            )

        if H is None:
            if warp_method in ("Homography + Optical Flow", "Optical Flow"):
                print("[Smart Merge] 粗对齐失败，回退到直接光流(等比适配) | Coarse alignment failed, falling back to direct optical flow (aspect-ratio preserved)")
                return self.optical_flow_only_align(query_img, train_img, optical_flow, device)
            return None, None, False

        base_mask = np.ones((h_q, w_q), dtype=np.float32)
        warped_fg = cv2.warpPerspective(
            query_img, H, (w_t, h_t),
            flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT101
        )
        warped_mask = cv2.warpPerspective(
            base_mask, H, (w_t, h_t),
            flags=cv2.INTER_LINEAR
        )

        if warp_method in ("Homography + Optical Flow", "Optical Flow"):
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
            m = cv2.resize(mask, (l1.shape[1], l1.shape[0]))
            if i == 0:
                if m.ndim == 2:
                    m = m[:, :, np.newaxis]
                blended = l1 * m + l2 * (1.0 - m)
            else:
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

    def smart_merge(self, original_image, edited_crop_B, match_method, warp_method, color_match,
                    optical_flow, feather_kernel, adapt_thresh, adapt_local_match,
                    merge_mode="All to One", use_gpu=False, force_recompute=False,
                    original_crop_A=None, unique_id=None, prompt=None, extra_pnginfo=None):

        # INPUT_IS_LIST 模式下, 所有输入(含控件/隐藏参数)都可能以 list 形式到达 → 解包为标量
        match_method = self._unwrap_scalar(match_method, "DISK + LightGlue")
        warp_method = self._unwrap_scalar(warp_method, "Homography + Optical Flow")
        color_match = self._unwrap_scalar(color_match, "Alpha Soft Blend")
        optical_flow = self._unwrap_scalar(optical_flow, "RAFT-Small")
        feather_kernel = self._unwrap_scalar(feather_kernel, 20)
        adapt_thresh = self._unwrap_scalar(adapt_thresh, 25)
        adapt_local_match = self._unwrap_scalar(adapt_local_match, "Reinhard")
        merge_mode = self._unwrap_scalar(merge_mode, "All to One")
        use_gpu = self._unwrap_scalar(use_gpu, False)
        force_recompute = self._unwrap_scalar(force_recompute, False)
        unique_id = self._unwrap_scalar(unique_id)
        prompt = self._unwrap_scalar(prompt)
        extra_pnginfo = self._unwrap_scalar(extra_pnginfo)

        # ================= 输入归一化 =================
        # INPUT_IS_LIST=True 时 List 会原样到达这里; batch/单张也统一展开为条目列表。
        items_orig = self._normalize_image_items(original_image)
        items_B = self._normalize_image_items(edited_crop_B)
        items_A = (self._normalize_image_items(original_crop_A)
                   if original_crop_A is not None else None)

        B_orig = len(items_orig)
        B_crop = len(items_B)

        if B_orig == 0 or B_crop == 0:
            if B_orig > 0:
                try:
                    return (torch.stack(items_orig),)
                except Exception:
                    return (items_orig[0].unsqueeze(0),)
            return (torch.zeros((0, 8, 8, 3), dtype=torch.float32),)

        if merge_mode == "All to One":
            B_orig_loop = 1
            crops_per_bg = B_crop
        else:
            B_orig_loop = B_orig
            crops_per_bg = max(1, B_crop // B_orig)

        # 总进度 = 背景图数量 × 每背景的 crop 数量
        total_steps = B_orig_loop * crops_per_bg
        pbar = ProgressBar(total_steps) if HAS_PROGRESS_BAR else None

        device = torch.device("cuda" if torch.cuda.is_available() and use_gpu else "cpu")

        # === 缓存查询 ===
        if force_recompute:
            self._clear_cache()
            print("[Smart Merge] 🗑 强制重算,缓存已清空 | Force recompute: cache cleared")

        align_key = self._make_align_key(
            items_orig, items_B, items_A,
            match_method, warp_method, optical_flow, merge_mode, use_gpu
        )

        cached_aligns = None if force_recompute else self._cache_get(align_key)
        align_cache_hit = cached_aligns is not None
        new_aligns_to_save = [] if not align_cache_hit else None

        if align_cache_hit:
            print(f"[Smart Merge] ✅ 命中对齐缓存,跳过特征匹配 (共 {len(cached_aligns)} 组) | Alignment cache hit, skipping feature matching ({len(cached_aligns)} entries)")
        else:
            print("[Smart Merge] ⏳ 未命中缓存,执行完整对齐计算 | Cache miss, running full alignment computation")

        result_images = []
        global_crop_counter = 0

        for i in range(B_orig_loop):
            try:
                img_bg = self._item_to_uint8_rgb(items_orig[i])

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

                    img_fg = self._item_to_uint8_rgb(items_B[crop_idx])
                    h_fg, w_fg = img_fg.shape[:2]

                    # ===== 对齐  =====
                    if align_cache_hit and align_idx < len(cached_aligns):
                        cached = cached_aligns[align_idx]
                        warped_fg = cached["warped_fg"].copy()
                        warped_mask = cached["warped_mask"].copy()
                    else:
                        img_bridge_A = None
                        if items_A is not None and crop_idx < len(items_A):
                            img_bridge_A = self._item_to_uint8_rgb(items_A[crop_idx])

                        success_align = False
                        warped_fg = None
                        warped_mask = None

                        # 桥接对齐: B → A → BG / Bridge alignment: B → A → BG
                        if img_bridge_A is not None:
                            h_A, w_A = img_bridge_A.shape[:2]
                            if h_A > 0 and w_A > 0:
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
                                    warped_fg, warped_mask, success_align = self.perform_kornia_alignment(
                                        img_fg, original_bg,
                                        method=match_method, warp_method=warp_method,
                                        optical_flow=optical_flow, device=device,
                                        preset_H=H_Total,
                                    )
                                    if success_align:
                                        print("[Smart Merge] 桥接对齐 B→A→BG 完成 (含畸变校正) | Bridge alignment B→A→BG done (with deformation correction)")


                        if not success_align:
                            warped_fg, warped_mask, ok = self.perform_kornia_alignment(
                                img_fg, original_bg,
                                method=match_method, warp_method=warp_method,
                                optical_flow=optical_flow, device=device
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

                    if len(y_idx) == 0:
                        continue

                    ymin, ymax = y_idx.min(), y_idx.max()
                    xmin, xmax = x_idx.min(), x_idx.max()
                    pad = max(100, int(feather_kernel) * 2)
                    ymin = max(0, ymin - pad)
                    ymax = min(h_bg, ymax + pad)
                    xmin = max(0, xmin - pad)
                    xmax = min(w_bg, xmax + pad)

                    crop_bg = img_bg[ymin:ymax, xmin:xmax]
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
                                print(f"[Smart Merge] Patch 色彩匹配失败: {e}, 降级 Alpha | Patch color sync failed: {e}, downgraded to Alpha")
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
                            if feather_kernel < 16:
                                num_levels = 3
                            elif feather_kernel > 64:
                                num_levels = 5
                            soft_mask = self.make_edge_safe_soft_mask(crop_mask_float, feather_kernel)
                            crop_result = self.laplacian_pyramid_blend(crop_fg, crop_bg, soft_mask, num_levels=num_levels)
                            current_color_match = "__DONE__"
                        except Exception as e:
                            print(f"[Smart Merge] 拉普拉斯金字塔融合失败: {e}, 降级 Alpha | Laplacian pyramid blend failed: {e}, downgraded to Alpha")
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
                                print(f"[Smart Merge] 泊松融合失败: {e} | Poisson seamless clone failed: {e}")
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
                        edge_blend[:, :edge_width] = np.maximum(edge_blend[:, :edge_width], weight * crop_mask_float[:, :edge_width])
                    if xmax == w_bg:
                        weight = np.linspace(0, 1, edge_width)[None, :]
                        edge_blend[:, -edge_width:] = np.maximum(edge_blend[:, -edge_width:], weight * crop_mask_float[:, -edge_width:])

                    if edge_blend.max() > 0.01:
                        eb3 = edge_blend[:, :, np.newaxis]
                        crop_result = (crop_fg.astype(np.float32) * eb3 + crop_result.astype(np.float32) * (1.0 - eb3))
                        crop_result = np.clip(crop_result, 0, 255).astype(np.uint8)

                    img_result[ymin:ymax, xmin:xmax] = crop_result
                    img_bg = img_result.copy()

                result_images.append(torch.from_numpy(img_result.astype(np.float32) / 255.0))

            except Exception as e:
                import traceback
                print(f"[Smart Merge 致命错误 | Fatal error] {e}")
                traceback.print_exc()
                result_images.append(items_orig[i])

        # 完成进度条
        if pbar is not None:
            pbar.update_absolute(total_steps, total_steps)

        if new_aligns_to_save is not None and len(new_aligns_to_save) > 0:
            self._cache_put(align_key, new_aligns_to_save)
            print(f"[Smart Merge] 💾 已缓存 {len(new_aligns_to_save)} 个对齐结果 | Cached {len(new_aligns_to_save)} alignment results")


        if len(result_images) == 1:
            return (result_images[0].unsqueeze(0),)
        shapes = {tuple(t.shape) for t in result_images}
        if len(shapes) == 1:
            return (torch.stack(result_images),)
        max_h = max(t.shape[0] for t in result_images)
        max_w = max(t.shape[1] for t in result_images)
        padded = []
        for t in result_images:
            dh, dw = max_h - t.shape[0], max_w - t.shape[1]
            if dh > 0 or dw > 0:
                t = torch.nn.functional.pad(t, (0, 0, 0, dw, 0, dh), mode="constant", value=0)
            padded.append(t)
        return (torch.stack(padded),)
