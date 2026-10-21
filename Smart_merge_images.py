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

# ================= 模型自动下载 =================
HF_MODEL_REPO = "https://huggingface.co/cglearned/Smart_merge_images/resolve/main"

MODEL_FILES = {
    "depth-save.pth":                "depth-save.pth",                # DISK 关键点权重
    "disk_lightglue_v0-1_arxiv-pth": "disk_lightglue_v0-1_arxiv-pth", # LightGlue-DISK 权重
    "loftr_outdoor.ckpt":            "loftr_outdoor.ckpt",            # LoFTR 半稠密匹配
}

_failed_once = set()  

def ensure_model_files():
    """文件已存在 → 跳过(本地命中, 零请求); 缺失 → 从 HF 下载到 kornia 的缓存名。"""
    import urllib.request
    ckpt_dir = os.path.join(torch.hub.get_dir(), "checkpoints")
    os.makedirs(ckpt_dir, exist_ok=True)
    for cache_name, hf_name in MODEL_FILES.items():
        dst = os.path.join(ckpt_dir, cache_name)
        if os.path.exists(dst) and os.path.getsize(dst) > 1_000_000:  # >1MB 防半截文件
            continue
        if cache_name in _failed_once:
            continue  
        url = f"{HF_MODEL_REPO}/{hf_name}"
        tmp = dst + ".download"
        try:
            print(f"[Smart Merge] ⬇ 下载 {hf_name} ← HuggingFace | downloading model")
            urllib.request.urlretrieve(url, tmp)
            os.replace(tmp, dst)
            print(f"[Smart Merge] ✅ {cache_name} 已就位 | model ready")
        except Exception as e:
            _failed_once.add(cache_name)
            print(f"[Smart Merge] ❌ {hf_name} 下载失败: {e}\n"
                  f"    请手动下载: {url}\n"
                  f"    放置到:     {dst}\n"
                  f"    (本会话不再重试)")
        finally:
            if os.path.exists(tmp):
                try: os.remove(tmp)
                except Exception: pass

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
    _cached_device = None

    _align_cache = {}
    _align_cache_order = []
    _align_cache_max = 4

    _sift_train_cache = {}          
    _sift_train_cache_order = []
    _sift_train_cache_max = 4
    
    # 光流最大位移限幅(px)
    MAX_FLOW_PX = 15.0
    BRIDGE_MAX_MEDIAN_DIFF = 45.0  # 桥接光度一致性阈值(0-255灰度中位差), 超过视为桥接H不可靠
    
    DESCRIPTION = (
        "智能局部重绘回贴节点: 将 AI 编辑后的局部裁块(B)自动对齐、畸变校正(TPS)、色彩统一后融合回原图。\n"
        "· 接入 original_crop_A(编辑前裁块)→ 桥接对齐 B→A→BG + LoFTR/TPS 非刚性畸变校正 + 二阶段精校 + 整图光流精修;\n"
        "· warp_method 开: 在 TPS 之上叠加光流精修; optical_flow 开: 使用 DIS(关为 Farneback);\n"
        "· 三个图像端口原生支持 List / Batch / 单张输入(节点已声明 INPUT_IS_LIST), 无需外接 'Image List To Image Batch' 节点; 各裁块尺寸可不同。\n"
        "推荐: warp_method 开, optical_flow 开, use_gpu=True。\n"
        "--------------------------------------------------\n"
        "Smart local-inpaint re-composite node: aligns the AI-edited crop (B), corrects its deformation via TPS,\n"
        "harmonizes color, then blends it back into the original image.\n"
        "· With original_crop_A connected → bridge alignment B→A→BG with LoFTR/TPS non-rigid correction,\n"
        "  second-pass refinement and global flow polish;\n"
        "· warp_method ON: adds optical-flow refinement on top of TPS; optical_flow ON: DIS (OFF: Farneback);\n"
        "· All three image ports natively accept list / batch / single images (INPUT_IS_LIST declared).\n"
        "Recommended: warp_method ON, optical_flow ON, use_gpu=True."
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
    def _make_align_key(cls, original_items, edited_items, cropA_items, warp_method,
                        optical_flow, merge_mode, use_gpu, use_tps=True, second_pass=False):
        return "|".join([
            cls._items_fingerprint(original_items),
            cls._items_fingerprint(edited_items),
            cls._items_fingerprint(cropA_items),
            str(bool(warp_method)),
            str(bool(optical_flow)),
            str(merge_mode),
            str(bool(use_gpu)),
            str(bool(use_tps)),      
            str(bool(second_pass)),  
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
    def get_kornia_models(cls, device):
        ensure_model_files()
        if cls._cached_device != device:
            cls._disk_model = None
            cls._lg_matcher_disk = None
            cls._cached_device = device
        if cls._disk_model is None:
            try:
                cls._disk_model = KF.DISK.from_pretrained("depth").eval().to(device)
                cls._lg_matcher_disk = KF.LightGlueMatcher("disk").eval().to(device)
                print(f"[Smart Merge] DISK & LightGlue 模型已就绪 (设备: {device}) | DISK & LightGlue models ready (device: {device})")
            except Exception as e:
                print(f"[Smart Merge] 初始化 DISK 权重失败: {e} | Failed to initialize DISK weights: {e}")
        return cls._disk_model, cls._lg_matcher_disk

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
                "warp_method": ("BOOLEAN", {
                    "default": False,
                    "label_on": "Homography + Optical Flow",
                    "label_off": "Homography",
                    "tooltip": "形变(畸变)校正方式:\n"
                               "· 关(Homography): 桥接H定位 + TPS非刚性畸变校正, 纯几何, 最快最稳\n"
                               "· 开: 在 TPS 之上叠加光流精修, 修正高频局部残差\n"
                               "--------------------------------------------------\n"
                               "Deformation-correction strategy:\n"
                               "· OFF (Homography): bridge-H placement + TPS non-rigid correction, pure geometry\n"
                               "· ON: adds optical-flow refinement on top of TPS"
                }),

                "optical_flow": ("BOOLEAN", {
                    "default": False,
                    "label_on": "DIS",
                    "label_off": "Farneback",
                    "tooltip": "光流算法(仅 warp_method 开启时生效):\n"
                               "· 关(Farneback): 最快, 纯 CPU\n"
                               "· 开(DIS): 质量更好, 贴边缘\n"
                               "--------------------------------------------------\n"
                               "Optical-flow algorithm (only when warp_method is ON):\n"
                               "· OFF (Farneback): fastest, CPU only\n"
                               "· ON (DIS): better quality, edge-preserving"
                }),

                "use_tps": ("BOOLEAN", {
                    "default": True,
                    "label_on": "TPS", "label_off": "Homography Only",
                    "tooltip": "TPS 非刚性畸变校正(推荐开启):\n· 开: 桥接定位 + LoFTR/TPS 畸变校正\n· 关: 仅桥接H定位(必要时+光流精修), 最快\n"
                               "--------------------------------------------------\n"
                               "TPS non-rigid deformation correction (recommended ON). OFF: bridge-H placement only, fastest."
                }),
                "second_pass": ("BOOLEAN", {
                    "default": False,
                    "label_on": "On", "label_off": "Off",
                    "tooltip": "二阶段精校(默认关, 仅在 TPS 路径生效):\n· 开: TPS 之后再做一次 LoFTR 残差精校, 慢, 少数图有改善\n· 关: 跳过\n"
                               "--------------------------------------------------\n"
                               "Second-pass LoFTR residual refinement (default OFF, works only within TPS path). Slower; marginal gains."
                }),

                "color_match": ([
                    "Patch_based_color",
                    "Edge_Weighted_Color",
                    "LAB_Mean",
                    "Laplacian Pyramid Blend",
                    "SeamlessClone (PS Auto Blend)",
                    "Alpha Soft Blend"
                ], {
                    "tooltip": "色彩迁移/融合策略(消除局部编辑与背景的色差):\n"
                               "· Patch_based_color 分块LAB色差同步(推荐, 色差大/不均匀时效果好)\n"
                               "· Edge_Weighted_Color 边缘加权色彩匹配(推荐: 保护改色物体, 纠正全图偏色)\n"
                               "· LAB_Mean 全局均值方差匹配(轻量快速)\n"
                               "· Laplacian Pyramid 金字塔融合(接缝最隐形, 不做色彩校正)\n"
                               "· SeamlessClone 泊松融合(内容基本未变时消接缝; 内容大改区域慎用, 易褪色)\n"
                               "· Alpha Soft Blend 仅羽化混合(色差已很小时用)\n"
                               "--------------------------------------------------\n"
                               "Color transfer / blending strategy:\n"
                               "· Patch_based_color: patch-wise LAB color sync (recommended for casts)\n"
                               "· Edge_Weighted_Color: edge-aware LAB matching (protects modified areas & fixes global casts)\n"
                               "· LAB_Mean: global mean/std matching in LAB (lightweight)\n"
                               "· Laplacian Pyramid: multi-band blending (best seams, no color correction)\n"
                               "· SeamlessClone: Poisson blending (seams only; avoid on heavily-edited content)\n"
                               "· Alpha Soft Blend: feathered alpha blending only"
                }),

                "feather_kernel": ("INT", {
                    "default": 20, "min": 0, "max": 256, "step": 1,
                    "tooltip": "羽化半径(px): 贴图边缘柔化宽度, 兼作 Patch 色彩同步的块尺寸基准。一般 15~40; 越大过渡越柔但可能侵入更多原始内容。\n"
                               "--------------------------------------------------\n"
                               "Feather radius (px): edge-softening width of the pasted crop; also used as the patch-size basis for Patch/Boundary color sync. "
                               "Typical 15~40; larger = softer transition but may eat into more original content."
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

    def edge_weighted_color_sync(self, fg, bg, mask_float):
        """
        边缘加权色彩匹配（与 ElementTileMerge 的算法完全一致）。
        在 RGB 空间进行均值方差匹配，保护中心改色区域，并施加硬截断防止溢出。
        """
        if mask_float.max() <= 0.01:
            return fg

        g = fg.astype(np.float32) / 255.0
        r = bg.astype(np.float32) / 255.0
        
        edge_mask = ((mask_float > 0.1) & (mask_float < 0.8)).astype(np.float32)
        
        if edge_mask.sum() < 500:
            edge_mask = (mask_float > 0.5).astype(np.float32)
            if edge_mask.sum() < 500:
                return fg
        
        mask_3d = edge_mask[:, :, np.newaxis]
        sum_mask = np.maximum(mask_3d.sum(), 1e-6)
        
        g_mean = (g * mask_3d).sum(axis=(0, 1), keepdims=True) / sum_mask
        r_mean = (r * mask_3d).sum(axis=(0, 1), keepdims=True) / sum_mask
        
        g_var = (((g - g_mean) ** 2) * mask_3d).sum(axis=(0, 1), keepdims=True) / sum_mask
        r_var = (((r - r_mean) ** 2) * mask_3d).sum(axis=(0, 1), keepdims=True) / sum_mask
        
        g_std = np.maximum(np.sqrt(g_var), 0.05)
        r_std = np.maximum(np.sqrt(r_var), 0.05)
        
        matched = (g - g_mean) / g_std * r_std + r_mean
        
        out = np.clip(matched * 255.0, 0, 255).astype(np.uint8)
        return out

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

    @staticmethod
    def _arr_fingerprint(arr, tag=""):
        import hashlib
        flat = np.ascontiguousarray(arr.reshape(-1))
        step = max(1, flat.size // 65536)
        return hashlib.md5(flat[::step].tobytes() + tag.encode()).hexdigest()[:16] \
               + "_" + "x".join(map(str, arr.shape))

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

        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_query = cv2.cvtColor(query_sift_img, cv2.COLOR_RGB2GRAY)
        gray_train = cv2.cvtColor(train_sift_img, cv2.COLOR_RGB2GRAY)

        # 背景侧 SIFT 缓存: 同一背景只检测一次 crop共享
        train_key = self._arr_fingerprint(train_sift_img, "bg_sift")
        cached = self._sift_train_cache.get(train_key)
        if cached is not None:
            kp_t, des_t = cached
            if train_key in self._sift_train_cache_order:
                self._sift_train_cache_order.remove(train_key)
            self._sift_train_cache_order.append(train_key)
        else:
            sift_bg = cv2.SIFT_create(nfeatures=5000)
            kp_t, des_t = sift_bg.detectAndCompute(clahe.apply(gray_train), None)
            self._sift_train_cache[train_key] = (kp_t, des_t)
            self._sift_train_cache_order.append(train_key)
            while len(self._sift_train_cache_order) > self._sift_train_cache_max:
                old = self._sift_train_cache_order.pop(0)
                self._sift_train_cache.pop(old, None)

        sift = cv2.SIFT_create(nfeatures=5000)
        kp_q, des_q = sift.detectAndCompute(clahe.apply(gray_query), None)
        if des_q is None or des_t is None or len(des_q) < 10 or len(des_t) < 10:
            return None

        try:  # ★ FLANN 近似最近邻
            flann = cv2.FlannBasedMatcher(dict(algorithm=1, trees=4), dict(checks=32))
            matches = flann.knnMatch(des_q, des_t, k=2)
        except Exception:
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

    def refine_with_optical_flow(self, warped_fg, warped_mask, train_img, optical_flow=False, device="cpu", max_flow_px=None):
        """optical_flow: False=Farneback, True=DIS (布尔开关)
        ★ 只在掩码 bbox(+边距) 内计算光流 —— 全帧 Farneback 是大图卡顿主因,
          bbox 外区域本来流场就≈0, 原样保留即可。"""
        if max_flow_px is None:
            max_flow_px = self.MAX_FLOW_PX
        h_t, w_t = train_img.shape[:2]
        mask_u8 = (warped_mask > 0.5).astype(np.uint8)
        ys, xs = np.where(mask_u8 > 0)
        if len(ys) < 100:
            return warped_fg, warped_mask
        margin = 64
        y0 = max(0, int(ys.min()) - margin)
        y1 = min(h_t, int(ys.max()) + margin)
        x0 = max(0, int(xs.min()) - margin)
        x1 = min(w_t, int(xs.max()) + margin)
        sub_fg = warped_fg[y0:y1, x0:x1]
        sub_mask = warped_mask[y0:y1, x0:x1]
        sub_bg = train_img[y0:y1, x0:x1]
        gray_warped = cv2.cvtColor(sub_fg, cv2.COLOR_RGB2GRAY)
        gray_target = cv2.cvtColor(sub_bg, cv2.COLOR_RGB2GRAY)
        if optical_flow:
            try:
                r_fg, _ = self._refine_with_dis(gray_warped, gray_target, sub_fg, sub_mask, sub_bg,
                                                max_flow_px=max_flow_px)
            except Exception as e:
                print(f"[Smart Merge] DIS 不可用 ({e}), 降级 Farneback | DIS unavailable, falling back to Farneback")
                r_fg, _ = self._refine_with_farneback(gray_warped, gray_target, sub_fg, sub_mask, sub_bg,
                                                      max_flow_px=max_flow_px)
        else:
            r_fg, _ = self._refine_with_farneback(gray_warped, gray_target, sub_fg, sub_mask, sub_bg,
                                                  max_flow_px=max_flow_px)
        out_fg = warped_fg.copy()
        out_fg[y0:y1, x0:x1] = r_fg
        return out_fg, warped_mask.copy()



    def _refine_with_dis(self, gray_warped, gray_target, warped_fg, warped_mask, train_img, max_flow_px=15.0):
        h_t, w_t = train_img.shape[:2]
        try:
            dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        except AttributeError:
            dis = cv2.DISOpticalFlow.create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)

        flow = dis.calc(gray_warped, gray_target, None)
        flow[:, :, 0] = cv2.medianBlur(flow[:, :, 0].astype(np.float32), 3)
        flow[:, :, 1] = cv2.medianBlur(flow[:, :, 1].astype(np.float32), 3)

        max_flow = float(max_flow_px)
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

    def _refine_with_farneback(self, gray_warped, gray_target, warped_fg, warped_mask, train_img, max_flow_px=15.0):
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
        # reliability = np.clip(reliability, 0.2, 1.0)
        reliability = np.clip(reliability, 0.0, 1.0)

        flow = flow_fwd.copy()
        max_flow = float(max_flow_px)
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

    def optical_flow_only_align(self, query_img, train_img, optical_flow=False, device="cpu"):
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

    @classmethod
    def _bridge_photometric_ok(cls, H, query_img, train_img):
        """桥接H质量粗检: 变形后的B与背景在掩码内做灰度中位差, 过大说明A→BG对错了"""
        h_t, w_t = train_img.shape[:2]
        h_q, w_q = query_img.shape[:2]
        mask = cv2.warpPerspective(np.ones((h_q, w_q), np.float32), H, (w_t, h_t), flags=cv2.INTER_LINEAR)
        if float(mask.sum()) < 100.0:
            return False
        warped = cv2.warpPerspective(query_img, H, (w_t, h_t), flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_REFLECT101)
        g1 = cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY).astype(np.float32)
        g2 = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY).astype(np.float32)
        m = cv2.erode((mask > 0.5).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        if not np.any(m):
            m = mask > 0.5
        med = float(np.median(np.abs(g1[m] - g2[m])))
        if med > cls.BRIDGE_MAX_MEDIAN_DIFF:
            print(f"[Smart Merge] 桥接单应性光度一致性差(中位差 {med:.1f} > {cls.BRIDGE_MAX_MEDIAN_DIFF}), 弃用并降级自动特征对齐 | Bridge H unreliable (median diff {med:.1f}), falling back")
            return False
        return True

    @classmethod
    def _photometric_score(cls, warped_fg, warped_mask, train_img):
        """对齐质量评分: 掩码内灰度绝对差中位数, 越小越好"""
        if warped_fg.shape[:2] != train_img.shape[:2]:
            return 1e9
        m = cv2.erode((warped_mask > 0.5).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        if float(m.sum()) < 100.0:
            return 1e9
        g1 = cv2.cvtColor(warped_fg, cv2.COLOR_RGB2GRAY).astype(np.float32)
        g2 = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY).astype(np.float32)
        return float(np.median(np.abs(g1[m] - g2[m])))

    @classmethod
    def _align_score(cls, warped_fg, warped_mask, train_img):
        """对齐评分(边缘加权): 结构错位大幅拉高分数, 远比全图中位差敏感"""
        if warped_fg.shape[:2] != train_img.shape[:2]:
            return 1e9
        m = cv2.erode((warped_mask > 0.5).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        if float(m.sum()) < 100.0:
            return 1e9
        g1 = cv2.cvtColor(warped_fg, cv2.COLOR_RGB2GRAY).astype(np.float32)
        g2 = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY).astype(np.float32)
        err = np.abs(g1 - g2)
        gx = cv2.Sobel(g2, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g2, cv2.CV_32F, 0, 1, ksize=3)
        wgt = np.sqrt(gx * gx + gy * gy) + 1.0
        wgt[~m] = 0.0
        ws = float(wgt.sum())
        return float((err * wgt).sum() / ws) if ws > 1.0 else 1e9

    @classmethod
    def _flow_residual_score(cls, warped_fg, warped_mask, train_img):
        """几何残差评分(单位: px): 掩码内稠密光流幅值的中位数/p85, 只度量"还错位多少像素",
        与内容差异(编辑本身)、Lanczos重采样无关 —— 用于 TPS 验收, 替代被污染的 _align_score。
        Geometric residual in px (median & p85 of dense-flow magnitude inside the mask),
        independent of content/photometric changes."""
        if warped_fg.shape[:2] != train_img.shape[:2]:
            return 1e9, 1e9
        mask_u8 = (warped_mask > 0.5).astype(np.uint8)
        ys, xs = np.where(mask_u8 > 0)
        if len(ys) < 400:
            return 1e9, 1e9
        pad = 32
        y0, y1 = max(0, int(ys.min()) - pad), min(warped_fg.shape[0], int(ys.max()) + pad)
        x0, x1 = max(0, int(xs.min()) - pad), min(warped_fg.shape[1], int(xs.max()) + pad)
        g1 = cv2.cvtColor(warped_fg[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY)
        g2 = cv2.cvtColor(train_img[y0:y1, x0:x1], cv2.COLOR_RGB2GRAY)
        m = cv2.erode(mask_u8[y0:y1, x0:x1], np.ones((15, 15), np.uint8)) > 0
        if float(m.sum()) < 400.0:
            return 1e9, 1e9
        flow = cv2.calcOpticalFlowFarneback(g1, g2, None, 0.5, 2, 11, 2, 5, 1.2, 0)
        flow_b = cv2.calcOpticalFlowFarneback(g2, g1, None, 0.5, 2, 11, 2, 5, 1.2, 0)

        h, w = g1.shape
        gx, gy = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        fb = cv2.remap(flow_b, gx + flow[..., 0], gy + flow[..., 1], interpolation=cv2.INTER_LINEAR)
        fb_err = np.linalg.norm(flow + fb, axis=2)
        mag = np.linalg.norm(flow, axis=2)
        valid = m & (fb_err < 2.0)          
        if int(valid.sum()) < 200:
            valid = m                        
        if int(valid.sum()) < 100:
            return 1e9, 1e9
        med = float(np.median(mag[valid]))
        p85 = float(np.percentile(mag[valid], 85))   # p85 抓"局部尖峰"
        return med, p85



    def match_with_loftr(self, query_img, train_img, device="cpu"):
        """LoFTR 半稠密匹配: 输入必须是 (N,1,H,W) 灰度图"""
        try:
            from kornia.feature import LoFTR
            ensure_model_files()
            if not hasattr(self, '_loftr') or self._loftr_device != device:
                self._loftr = LoFTR(pretrained="outdoor").eval().to(device)  
                self._loftr_device = device

            def _to_tensor(img):
                # LoFTR 仅接受 1 通道灰度图: 先转灰度, 再组 (1,1,H,W)
                if img.ndim == 3:
                    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY) if img.shape[2] == 3 else img[..., 0]
                else:
                    gray = img
                t = torch.from_numpy(np.ascontiguousarray(gray)).float().to(device)[None, None] / 255.0
                h, w = t.shape[-2:]
                if max(h, w) > 1024:
                    s = 1024.0 / max(h, w)
                    t = torch.nn.functional.interpolate(
                        t, size=(max(64, int(h * s) // 8 * 8), max(64, int(w * s) // 8 * 8)),
                        mode="bilinear", align_corners=False)
                return t

            img_q, img_t = _to_tensor(query_img), _to_tensor(train_img)
            with torch.inference_mode():
                d = self._loftr({"image0": img_q, "image1": img_t})
            s_q = np.array([query_img.shape[1] / img_q.shape[-1],
                            query_img.shape[0] / img_q.shape[-2]], dtype=np.float32)
            s_t = np.array([train_img.shape[1] / img_t.shape[-1],
                            train_img.shape[0] / img_t.shape[-2]], dtype=np.float32)
            conf = d['confidence'].cpu().numpy()
            keep = conf > 0.5
            pts_q = d['keypoints0'].cpu().numpy()[keep] * s_q[None, :]
            pts_t = d['keypoints1'].cpu().numpy()[keep] * s_t[None, :]
            return pts_q, pts_t
        except Exception as e:
            print(f"[Smart Merge] LoFTR 匹配失败: {e}")
            return None, None


    def filter_correspondences_local_affine(self, pts_q, pts_t, k=8, inlier_thresh=4.0):
        """局部仿射一致性滤波: 每个点用k近邻估局部仿射, 该点自身误差>inlier_thresh则剔除
        这是APAP/局部投影思想的滤波版, 无需分块即可剔除坏点"""
        if len(pts_q) < k + 1:
            return pts_q, pts_t
        from scipy.spatial import cKDTree
        tree = cKDTree(pts_q)
        keep_mask = np.zeros(len(pts_q), dtype=bool)
        for i in range(len(pts_q)):
            _, idx = tree.query(pts_q[i], k=k+1) 
            src = pts_q[idx].astype(np.float64)
            dst = pts_t[idx].astype(np.float64)
            try:
                A = np.hstack([src - src[0], np.ones((k+1,1))])
                sol, *_ = np.linalg.lstsq(A, dst - dst[0], rcond=None)
                pred = (A @ sol) + dst[0]
                err = np.linalg.norm(pred - dst, axis=1)
                if err[0] < inlier_thresh:
                    keep_mask[i] = True
            except np.linalg.LinAlgError:
                pass
        if keep_mask.sum() < len(pts_q) // 2:
            keep_mask = np.ones(len(pts_q), dtype=bool)
        return pts_q[keep_mask], pts_t[keep_mask]

    def warp_tps(self, warped_fg_src, warped_mask_src, train_img, pts_src, pts_dst,
                 reg_lambda=5, max_disp=64.0, max_points=1500):
        """TPS 全局薄板样条: 均匀降采样→全局平滑场(数学保证无波浪)→粗网格评估→场高斯平滑"""
        from scipy.interpolate import RBFInterpolator
        from scipy.spatial import cKDTree
        src = pts_src.astype(np.float64)
        dst = pts_dst.astype(np.float64)
        n_raw = len(src)
        n = n_raw
        if n < 8:
            return None, None
        disp = dst - src
        mag = np.linalg.norm(disp, axis=1)
        med_mag = float(np.median(mag))
        x0, y0 = src.min(axis=0); x1, y1 = src.max(axis=0)
        cw = max((x1 - x0) / 16.0, 1.0); ch = max((y1 - y0) / 16.0, 1.0)
        cells = set(zip(((src[:, 0] - x0) // cw).astype(int),
                        ((src[:, 1] - y0) // ch).astype(int)))
        cov = len(cells)
        if med_mag > 96.0 or cov < 24:
            print(f"[Smart Merge] TPS 拒绝: 中位位移{med_mag:.1f}px 覆盖{cov}/256 | rejected")
            return None, None

        if n > max_points:
            side = int(np.ceil(np.sqrt(max_points)))
            cx = np.clip(((src[:, 0] - x0) / max(x1 - x0, 1e-6) * side).astype(int), 0, side - 1)
            cy = np.clip(((src[:, 1] - y0) / max(y1 - y0, 1e-6) * side).astype(int), 0, side - 1)
            buckets = {}
            for i in range(n):
                buckets.setdefault((cx[i], cy[i]), []).append(i)
            idx = []
            for lst in buckets.values():
                lst = np.asarray(lst)
                m = np.linalg.norm(disp[lst], axis=1)
                idx.append(lst[np.argsort(m)[len(lst) // 2]])
            idx = np.asarray(idx)
            src, dst = src[idx], dst[idx]
            n = len(src)
            disp = dst - src
            mag = np.linalg.norm(disp, axis=1)
            med_mag = float(np.median(mag))

        # 邻域中值一致性离群剔除
        if n >= 12:
            from scipy.spatial import cKDTree
            _t = cKDTree(src)
            _k = int(min(9, n))
            _, _idx = _t.query(src, k=_k)            
            _loc = np.median(disp[_idx], axis=1)      
            _dev = np.linalg.norm(disp - _loc, axis=1)
            _mad = float(np.median(_dev))
            _thr = max(2.0, 3.0 * _mad)
            _keep = _dev <= _thr
            if int(_keep.sum()) < max(8, n // 4):     
                _keep = _dev <= float(np.median(_dev))
            if int(_keep.sum()) < n:
                print(f"[Smart Merge] TPS 离群剔除: 保留 {_keep.sum()}/{n} 点 (阈值 {_thr:.2f}px) | outliers removed")
                src, dst = src[_keep], dst[_keep]
                n = len(src)
                disp = dst - src
                mag = np.linalg.norm(disp, axis=1)
                med_mag = float(np.median(mag))


        rng = np.random.default_rng(0)
        perm = rng.permutation(n)
        n_fit = max(8, int(n * 0.8))
        if n - n_fit >= 4:
            rbf_cv = RBFInterpolator(src[perm[:n_fit]], dst[perm[:n_fit]],
                                     kernel="thin_plate_spline",
                                     smoothing=max(reg_lambda * 2.0, 4.0))
            resid = dst[perm[n_fit:]] - rbf_cv(src[perm[n_fit:]])
            smooth_err = float(np.median(np.linalg.norm(resid, axis=1)))
            if smooth_err > 6.0:
                print(f"[Smart Merge] TPS 拒绝: 留出残差{smooth_err:.1f}px>6 (匹配混乱) | chaotic")
                return None, None
        else:
            smooth_err = 0.0

        # 按位移分布自适应收紧限幅 (固定 64px 对小残差场景太宽松, 尖峰可存活)
        _p95 = float(np.percentile(mag, 95)) if len(mag) else 0.0
        _cap = float(min(max_disp, max(12.0, 4.0 * _p95)))
        if _cap < max_disp:
            print(f"[Smart Merge] TPS 限幅收紧: {max_disp:.0f}→{_cap:.1f}px | cap tightened")
        max_disp = _cap

        disp = disp * np.clip(max_disp / np.maximum(mag, 1e-6), 0.0, 1.0)[:, None]
        rbf = RBFInterpolator(src, src + disp, kernel="thin_plate_spline",
                              smoothing=reg_lambda)
        h, w = train_img.shape[:2]
        step = max(8, int(np.ceil(np.sqrt(w * h / 120000.0))))   # 查询点总数≈12万, 控内存与耗时
        gx, gy = np.meshgrid(np.arange(0, w, step), np.arange(0, h, step))
        gp = np.stack([gx.ravel(), gy.ravel()], axis=1)
        fg = rbf(gp) - gp
        tree = cKDTree(src)
        dnn, _ = tree.query(gp, k=1)
        ref = max(float(np.median(tree.query(src, k=2)[0][:, 1])), 12.0)
        decay = 0.20 + 0.80 * np.exp(-((dnn / (3.0 * ref)) ** 2))
        fg = fg * decay[:, None]
        fmag = np.linalg.norm(fg, axis=1)
        fg = fg * np.clip(max_disp / np.maximum(fmag, 1e-6), 0.0, 1.0)[:, None]
        gh, gw = gx.shape
        k = int(max(5, step)) | 1
        fg2 = fg.reshape(gh, gw, 2).astype(np.float32)
        fg2[:, :, 0] = cv2.GaussianBlur(fg2[:, :, 0], (k, k), 0)
        fg2[:, :, 1] = cv2.GaussianBlur(fg2[:, :, 1], (k, k), 0)
        fg = fg2.reshape(-1, 2)
        map_x = (gx - fg[:, 0].reshape(gx.shape)).astype(np.float32)
        map_y = (gy - fg[:, 1].reshape(gy.shape)).astype(np.float32)
        map_x = cv2.resize(map_x, (w, h), interpolation=cv2.INTER_LINEAR)
        map_y = cv2.resize(map_y, (w, h), interpolation=cv2.INTER_LINEAR)
        warped_fg = cv2.remap(warped_fg_src, map_x, map_y, interpolation=cv2.INTER_LANCZOS4,
                              borderMode=cv2.BORDER_REPLICATE)
        warped_mask = cv2.remap(warped_mask_src, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        print(f"[Smart Merge] TPS 场生效: {n}/{n_raw}点(保留/原始) 中位位移{med_mag:.1f}px "
              f"CV残差{smooth_err:.1f}px 覆盖{cov}/256")
        return warped_fg, warped_mask

    def refine_second_pass(self, warped_fg, warped_mask, train_img, device, max_disp=64.0):
        """二阶段精校: 已warp的块与BG同坐标系、小位移, 再做一次LoFTR稀疏匹配求残差场"""
        try:
            h_t, w_t = train_img.shape[:2]
            ys, xs = np.where(warped_mask > 0.5)
            if len(ys) < 100:
                return None, None
            pad = 48
            y0, y1 = max(0, ys.min() - pad), min(h_t, ys.max() + pad)
            x0, x1 = max(0, xs.min() - pad), min(w_t, xs.max() + pad)
            if (y1 - y0) < 64 or (x1 - x0) < 64:
                return None, None
            roi_fg = warped_fg[y0:y1, x0:x1]
            roi_bg = train_img[y0:y1, x0:x1]
            pts_w, pts_b = self.match_with_loftr(roi_fg, roi_bg, device)
            if pts_w is None or len(pts_w) < 12:
                return None, None
            pts_w, pts_b = self.filter_correspondences_local_affine(pts_w, pts_b)
            if len(pts_w) < 12:
                return None, None
            off = np.array([x0, y0], dtype=np.float32)
            pts_w = pts_w + off[None, :]
            pts_b = pts_b + off[None, :]
            return self.warp_tps(warped_fg, warped_mask, train_img,
                                 pts_w, pts_b, reg_lambda=1.5,
                                 max_disp=max_disp, max_points=1500)
        except Exception as e:
            print(f"[Smart Merge] 二阶段精校失败: {e}")
            return None, None

    def global_flow_polish(self, merged_img, original_bg, union_mask, max_disp=12.0):
        """整图光流精修: 合成图 vs 原图, 补低纹理区(TPS稀疏匹配盲区)的残余位移。
        块外流场自然≈0; 平滑区流场置零(防涂抹); 双向探测自动选方向; 光度否决票"""
        h, w = original_bg.shape[:2]
        gm = cv2.cvtColor(merged_img, cv2.COLOR_RGB2GRAY)
        go = cv2.cvtColor(original_bg, cv2.COLOR_RGB2GRAY)
        try:
            dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        except AttributeError:
            dis = cv2.DISOpticalFlow.create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        flow = dis.calc(gm, go, None).astype(np.float32)
        flow[:, :, 0] = cv2.GaussianBlur(flow[:, :, 0], (25, 25), 0)
        flow[:, :, 1] = cv2.GaussianBlur(flow[:, :, 1], (25, 25), 0)
        mag = np.linalg.norm(flow, axis=2)
        sel = union_mask > 0.5
        if not np.any(sel) or float(np.median(mag[sel])) < 0.6:
            print("[Smart Merge] 整图精修: 块内残余位移<0.6px, 跳过 | polish skipped")
            return merged_img
        scale = np.minimum(mag, max_disp) / (mag + 1e-8)
        flow[:, :, 0] *= scale
        flow[:, :, 1] *= scale
        um = cv2.GaussianBlur(sel.astype(np.float32), (31, 31), 0)[..., None]
        sobx = cv2.Sobel(gm, cv2.CV_32F, 1, 0, ksize=3)
        soby = cv2.Sobel(gm, cv2.CV_32F, 0, 1, ksize=3)
        tex = cv2.GaussianBlur(np.sqrt(sobx * sobx + soby * soby), (21, 21), 0)
        tex_gate = np.clip(tex / 8.0, 0.0, 1.0)[..., None]
        flow = flow * um * tex_gate
        grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        s0 = self._align_score(merged_img, union_mask, original_bg)
        p0 = self._photometric_score(merged_img, union_mask, original_bg)
        best_out, best_s, best_dir = merged_img, s0, 0
        for sign in (1.0, -1.0):
            out = cv2.remap(merged_img, grid_x + sign * flow[:, :, 0], grid_y + sign * flow[:, :, 1],
                            interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
            sc = self._align_score(out, union_mask, original_bg)
            pc = self._photometric_score(out, union_mask, original_bg)
            if sc < best_s and pc <= p0 + 0.5:  
                best_out, best_s, best_dir = out, sc, sign
        if best_dir != 0:
            print(f"[Smart Merge] 整图精修: 方向{best_dir:+.0f} {s0:.1f}→{best_s:.1f} | polish accepted")
            return best_out
        print(f"[Smart Merge] 整图精修: 两方向均无改善 ({s0:.1f}) | polish rejected")
        return merged_img


    def estimate_homography(self, query_img, train_img, device="cpu"):
        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]
        pts_q, pts_t = None, None
        self._match_level = None
        self._disk_pts_q = None
        self._disk_pts_t = None
        
        # 匹配降采样: DISK 显存/耗时与像素数成正比, 全尺寸大背景可吃掉 10GB+ 显存。
        # 匹配只需 ~1280px, 关键点坐标最后按各自缩放比除回原尺度, 精度损失 <1px。
        MATCH_MAX_DIM = 1280
        s_q = min(1.0, MATCH_MAX_DIM / float(max(h_q, w_q)))
        s_t = min(1.0, MATCH_MAX_DIM / float(max(h_t, w_t)))
        if s_q < 1.0:
            query_m = cv2.resize(query_img, (int(round(w_q * s_q)), int(round(h_q * s_q))),
                                 interpolation=cv2.INTER_AREA)
        else:
            query_m = query_img
        if s_t < 1.0:
            train_m = cv2.resize(train_img, (int(round(w_t * s_t)), int(round(h_t * s_t))),
                                 interpolation=cv2.INTER_AREA)
        else:
            train_m = train_img
        print(f"[Smart Merge] 匹配降采样: crop {w_q}x{h_q}→{query_m.shape[1]}x{query_m.shape[0]}, "
              f"BG {w_t}x{h_t}→{train_m.shape[1]}x{train_m.shape[0]} | matching downscale")

        img_q_tensor = torch.from_numpy(np.ascontiguousarray(query_m)).permute(2, 0, 1).float().to(device)[None] / 255.0
        img_t_tensor = torch.from_numpy(np.ascontiguousarray(train_m)).permute(2, 0, 1).float().to(device)[None] / 255.0

        # ========== DISK + LightGlue (唯一特征匹配方案) ==========
        try:
            disk, lg_matcher = self.get_kornia_models(device)
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
                        hw_q = torch.tensor(query_m.shape[:2], device=device)
                        hw_t = torch.tensor(train_m.shape[:2], device=device)
                        match_res = lg_matcher(
                            features_q.descriptors, features_t.descriptors,
                            lafs_q, lafs_t, hw1=hw_q, hw2=hw_t,
                        )
                        idxs = _parse_lightglue_output(match_res)
                        if idxs is not None and idxs.shape[0] >= 4:
                            pts_q = kps_q_t[idxs[:, 0]].detach().cpu().numpy() / s_q
                            pts_t = kps_t_t[idxs[:, 1]].detach().cpu().numpy() / s_t
                            self._match_level = "DISK"
                if self._match_level is None:
                    print("[Smart Merge] DISK+LightGlue 匹配点数不足 | DISK+LightGlue matched too few points")
        except Exception as e:
            print(f"[Smart Merge] DISK + LightGlue 匹配运行失败: {e} | DISK+LightGlue matching failed: {e}")
            pts_q, pts_t = None, None

        # 释放匹配显存
        try:
            del img_q_tensor, img_t_tensor, features_q, features_t
        except Exception:
            pass
        if getattr(device, "type", "") == "cuda":
            torch.cuda.empty_cache()

        # ========== Homography ==========
        if pts_q is None or pts_t is None or len(pts_q) < 4:
            return None, None, 0, None
        magsac_flag = getattr(cv2, 'USAC_MAGSAC', cv2.RANSAC)
        H, inliers = cv2.findHomography(pts_q, pts_t, magsac_flag, 4.0)
        
        try:
            _ones = np.hstack([pts_q, np.ones((len(pts_q), 1))])
            _proj = (H @ _ones.T).T
            _proj = _proj[:, :2] / _proj[:, 2:]
            _err = np.linalg.norm(_proj - pts_t, axis=1)
            _keep = _err < 15.0
            if int(_keep.sum()) >= 8:
                self._disk_pts_q = pts_q[_keep]
                self._disk_pts_t = pts_t[_keep]
        except Exception:
            self._disk_pts_q = None

        if H is None or inliers is None or np.sum(inliers) < 4:
            return None, None, 0, None
        if not self._homography_is_sane(H, h_q, w_q, h_t, w_t):
            print("[Smart Merge] 单应性矩阵异常(退化/镜像/过度形变), 放弃并降级 | Homography invalid (degenerate/mirrored/over-deformed), rejected and falling back")
            return None, None, 0, None
        num_inliers = int(np.sum(inliers))
        method_used = self._match_level or "DISK"
        return H, inliers, num_inliers, method_used

    def perform_kornia_alignment(self, query_img, train_img, warp_method=False, optical_flow=False,
                                 device="cpu", preset_H=None, max_flow_px=None, use_tps=True, second_pass=False):

        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]

        # ========== 粗对齐 ==========
        H = None
        method_used = None
        num_inliers = 0

        is_bridge = False
        if preset_H is not None:
            if self._homography_is_sane(preset_H, h_q, w_q, h_t, w_t) and \
               self._bridge_photometric_ok(preset_H, query_img, train_img):
                H = preset_H
                method_used = "Bridge(B→A→BG)"
                num_inliers = -1
                is_bridge = True
            else:


                print("[Smart Merge] 桥接单应性异常, 降级为自动特征对齐 | Bridge homography invalid, falling back to automatic feature alignment")
        # === TPS 非刚性对齐路径（推荐主路径）===
        use_tps_path = (use_tps and preset_H is not None and is_bridge
                        and hasattr(self, '_bridge_H_A2BG'))
        if use_tps_path:
            pts_b, pts_a = self.match_with_loftr(query_img, self._bridge_A_cached, device)
            if pts_b is not None and len(pts_b) >= 8:
                pts_b, pts_a = self.filter_correspondences_local_affine(pts_b, pts_a)
                n_pts = len(pts_b)
                if n_pts < 8:
                    print(f"[Smart Merge] TPS: B↔A匹配不足({n_pts}点), 跳过 | too few matches")
                else:
                    ones_b = np.hstack([pts_b, np.ones((n_pts, 1))])
                    q = (preset_H @ ones_b.T).T;  q = q[:, :2] / q[:, 2:]
                    ones_a = np.hstack([pts_a, np.ones((n_pts, 1))])
                    t = (self._bridge_H_A2BG @ ones_a.T).T;  t = t[:, :2] / t[:, 2:]
                    base_mask = np.ones(query_img.shape[:2], dtype=np.float32)
                    warped_fg0 = cv2.warpPerspective(query_img, preset_H, (w_t, h_t),
                                                     flags=cv2.INTER_LANCZOS4,
                                                     borderMode=cv2.BORDER_REFLECT101)
                    warped_mask0 = cv2.warpPerspective(base_mask, preset_H, (w_t, h_t),
                                                       flags=cv2.INTER_LINEAR)
                    warped_fg, warped_mask = warped_fg0, warped_mask0
                    tps_fg, tps_mask = self.warp_tps(
                        warped_fg0, warped_mask0, train_img, q, t, reg_lambda=1.5)
                    if tps_fg is not None:
                        g0_med, g0_p85 = self._flow_residual_score(warped_fg0, warped_mask0, train_img)
                        g1_med, g1_p85 = self._flow_residual_score(tps_fg, tps_mask, train_img)
                        p0t = self._photometric_score(warped_fg0, warped_mask0, train_img)
                        p1t = self._photometric_score(tps_fg, tps_mask, train_img)
                        if g1_med <= g0_med + 0.5 and g1_p85 <= g0_p85 + 1.0 and p1t <= p0t + 2.0:
                            warped_fg, warped_mask = tps_fg, tps_mask
                            print(f"[Smart Merge] TPS 验收通过: 几何残差 {g0_med:.2f}px→{g1_med:.2f}px "
                                  f"(p85 {g0_p85:.2f}→{g1_p85:.2f}) | TPS accepted")
                        else:
                            print(f"[Smart Merge] TPS 拒绝: 几何残差 {g0_med:.2f}px→{g1_med:.2f}px "
                                  f"(p85 {g0_p85:.2f}→{g1_p85:.2f}), 光度 {p0t:.1f}→{p1t:.1f} | TPS rejected")

                    # ★ 二阶段精校(ENABLE_SECOND_PASS 可关): BG坐标系内小位移残差校正
                    if second_pass:
                        fg2, mask2 = self.refine_second_pass(
                            warped_fg, warped_mask, train_img, device, max_disp=16.0)
                        if fg2 is not None:
                            g2a, _ = self._flow_residual_score(warped_fg, warped_mask, train_img)
                            g2b, _ = self._flow_residual_score(fg2, mask2, train_img)
                            p2a = self._photometric_score(warped_fg, warped_mask, train_img)
                            p2b = self._photometric_score(fg2, mask2, train_img)
                            if g2b <= g2a - 0.2 and p2b <= p2a + 0.5:
                                warped_fg, warped_mask = fg2, mask2
                                print(f"[Smart Merge] 二阶段精校通过 ({g2a:.2f}px→{g2b:.2f}px) | pass2 accepted")
                            else:
                                print(f"[Smart Merge] 二阶段精校无改善 ({g2a:.2f}px→{g2b:.2f}px) | pass2 rejected")

                    if warp_method:
                        fg_r, mask_r = self.refine_with_optical_flow(
                            warped_fg, warped_mask, train_img, optical_flow=optical_flow,
                            device=device, max_flow_px=10.0)
                        g0m, _ = self._flow_residual_score(warped_fg, warped_mask, train_img)
                        g1m, _ = self._flow_residual_score(fg_r, mask_r, train_img)
                        if g1m < g0m - 0.05:
                            warped_fg, warped_mask = fg_r, mask_r
                            print(f"[Smart Merge] 逐块光流生效: {g0m:.2f}px→{g1m:.2f}px | per-crop flow accepted")
                        else:
                            print(f"[Smart Merge] 逐块光流拒绝: {g0m:.2f}px→{g1m:.2f}px | per-crop flow rejected")
                    self._match_level = "TPS+LoFTR"
                    return warped_fg, warped_mask, True

        # B↔A匹配失败 → 落回下方原有桥接H+光流路径, 安全兜底
        if H is None:
            H, inliers, num_inliers, method_used = self.estimate_homography(
                query_img, train_img, device=device
            )

        if H is None:
            if warp_method:
                print("[Smart Merge] 特征匹配彻底失败, 纯光流对齐 | pure optical-flow alignment")
                refined_fg, refined_mask = self.optical_flow_only_align(
                    query_img, train_img, optical_flow, device)
                return refined_fg, refined_mask, True
            wf = np.zeros_like(train_img)
            wm = np.zeros((h_t, w_t), dtype=np.float32)
            sc = min(w_t / float(w_q), h_t / float(h_q))
            nw, nh = max(1, int(round(w_q * sc))), max(1, int(round(h_q * sc)))
            rz = cv2.resize(query_img, (nw, nh), interpolation=cv2.INTER_LANCZOS4)
            yo, xo = max(0, (h_t - nh) // 2), max(0, (w_t - nw) // 2)
            wf[yo:yo + nh, xo:xo + nw] = rz
            wm[yo:yo + nh, xo:xo + nw] = 1.0
            return wf, wm, True

        base_mask = np.ones((h_q, w_q), dtype=np.float32)
        warped_fg = cv2.warpPerspective(
            query_img, H, (w_t, h_t),
            flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT101
        )
        warped_mask = cv2.warpPerspective(
            base_mask, H, (w_t, h_t),
            flags=cv2.INTER_LINEAR
        )

        if use_tps and getattr(self, "_disk_pts_q", None) is not None and len(self._disk_pts_q) >= 8:
            try:
                _ones = np.hstack([self._disk_pts_q, np.ones((len(self._disk_pts_q), 1))])
                q = (H @ _ones.T).T
                q = q[:, :2] / q[:, 2:]
                tps_fg, tps_mask = self.warp_tps(
                    warped_fg, warped_mask, train_img, q, self._disk_pts_t, reg_lambda=1.5)
                if tps_fg is not None:
                    g0_med, g0_p85 = self._flow_residual_score(warped_fg, warped_mask, train_img)
                    g1_med, g1_p85 = self._flow_residual_score(tps_fg, tps_mask, train_img)
                    if g1_med <= g0_med + 0.5 and g1_p85 <= g0_p85 + 1.0:
                        warped_fg, warped_mask = tps_fg, tps_mask
                        print(f"[Smart Merge] TPS(DISK内点) 通过: {g0_med:.2f}px→{g1_med:.2f}px | TPS accepted")
                    else:
                        print(f"[Smart Merge] TPS(DISK内点) 拒绝: {g0_med:.2f}px→{g1_med:.2f}px | TPS rejected")
            except Exception as e:
                print(f"[Smart Merge] TPS(DISK内点) 失败: {e} | TPS failed")

        if warp_method:
            g0m, g0p = self._flow_residual_score(warped_fg, warped_mask, train_img)
            if g0m < 1.2:
                print(f"[Smart Merge] H后残差已很小({g0m:.2f}px), 跳过光流精修 | residual tiny, flow skipped")
                return warped_fg, warped_mask, True
            refined_fg, refined_mask = self.refine_with_optical_flow(
                warped_fg, warped_mask, train_img, optical_flow, device
            )
            g1m, g1p = self._flow_residual_score(refined_fg, refined_mask, train_img)
            if g1m < g0m - 0.3 and g1p <= g0p + 0.5:
                print(f"[Smart Merge] H+光流精修生效: {g0m:.2f}px→{g1m:.2f}px "
                      f"(p85 {g0p:.2f}→{g1p:.2f}) | H+flow accepted")
                return refined_fg, refined_mask, True
            print(f"[Smart Merge] H+光流精修拒绝: {g0m:.2f}px→{g1m:.2f}px "
                  f"(p85 {g0p:.2f}→{g1p:.2f}) | H+flow rejected")
            return warped_fg, warped_mask, True
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

    def smart_merge(self, original_image, edited_crop_B, warp_method, color_match, optical_flow, feather_kernel,
                    use_tps=True, second_pass=False, merge_mode="All to One", use_gpu=False, force_recompute=False,
                    original_crop_A=None, unique_id=None, prompt=None, extra_pnginfo=None):

        # INPUT_IS_LIST 模式下, 所有输入(含控件/隐藏参数)都可能以 list 形式到达 → 解包为标量
        warp_method = self._unwrap_scalar(warp_method, False)
        color_match = self._unwrap_scalar(color_match, "Alpha Soft Blend")
        optical_flow = self._unwrap_scalar(optical_flow, False)
        use_tps = self._unwrap_scalar(use_tps, True)
        second_pass = self._unwrap_scalar(second_pass, False)
        feather_kernel = self._unwrap_scalar(feather_kernel, 20)
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
            items_orig, items_B, items_A, warp_method, optical_flow,
            merge_mode, use_gpu, use_tps, second_pass
        )

        cached_aligns = None if force_recompute else self._cache_get(align_key)
        align_cache_hit = cached_aligns is not None
        # new_aligns_to_save = [] if not align_cache_hit else None

        if align_cache_hit:
            print(f"[Smart Merge] ✅ 命中对齐缓存,跳过特征匹配 (共 {len(cached_aligns)} 组) | Alignment cache hit, skipping feature matching ({len(cached_aligns)} entries)")
        else:
            print("[Smart Merge] ⏳ 未命中缓存,执行完整对齐计算 | Cache miss, running full alignment computation")

        result_images = []
        total_crops = B_orig_loop * crops_per_bg
        new_aligns_to_save = [None] * total_crops if not align_cache_hit else None

        for i in range(B_orig_loop):
            try:
                img_bg = self._item_to_uint8_rgb(items_orig[i])

                start_idx = i * crops_per_bg
                end_idx = min(start_idx + crops_per_bg, B_crop)
                if start_idx >= B_crop:
                    result_images.append(torch.from_numpy(img_bg.astype(np.float32) / 255.0))
                    continue

                original_bg = img_bg.copy()
                union_mask = np.zeros(img_bg.shape[:2], dtype=np.float32)
                img_result = img_bg.copy()

                # 倒序循环贴
                for crop_idx in range(end_idx - 1, start_idx - 1, -1):
                    if pbar is not None:
                        pbar.update(1)

                    img_fg = self._item_to_uint8_rgb(items_B[crop_idx])
                    h_fg, w_fg = img_fg.shape[:2]

                    if align_cache_hit and crop_idx < len(cached_aligns) and cached_aligns[crop_idx] is not None:
                        cached = cached_aligns[crop_idx]
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
                                    self._bridge_A_cached = img_bridge_A  
                                    self._bridge_H_A2BG = H_A_to_BG
                                    warped_fg, warped_mask, success_align = self.perform_kornia_alignment(
                                        img_fg, original_bg,
                                        warp_method=warp_method,
                                        optical_flow=optical_flow, device=device,
                                        preset_H=H_Total,
                                        use_tps=use_tps, second_pass=second_pass,
                                    )
                                    if success_align:
                                        print("[Smart Merge] 桥接对齐 B→A→BG 完成 (含畸变校正) | Bridge alignment B→A→BG done (with deformation correction)")


                        if not success_align:
                            warped_fg, warped_mask, ok = self.perform_kornia_alignment(
                                img_fg, original_bg,
                                warp_method=warp_method,
                                optical_flow=optical_flow, use_tps=use_tps, second_pass=second_pass, device=device
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
                            new_aligns_to_save[crop_idx] = {
                                "warped_fg": warped_fg.copy(),
                                "warped_mask": warped_mask.copy(),
                            }

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
                    if current_color_match == "Patch_based_color":
                        band_width = max(15, int(feather_kernel))
                        crop_fg = self.boundary_aware_color_sync(
                            crop_fg, crop_bg, crop_mask_float, band_width=band_width
                        )
                        try:
                            crop_fg = self.patch_based_color_sync(
                                crop_fg, crop_bg, crop_mask_float,
                                patch_size=max(32, int(feather_kernel) * 2),
                                overlap=max(16, int(feather_kernel))
                            )
                        except Exception as e:
                            print(f"[Smart Merge] Patch 色彩匹配失败: {e}, 降级 Alpha | Patch color sync failed: {e}, downgraded to Alpha")
                        current_color_match = "Alpha Soft Blend"
                    
                    elif current_color_match == "Edge_Weighted_Color":
                        crop_fg = self.edge_weighted_color_sync(crop_fg, crop_bg, crop_mask_float)
                        current_color_match = "Alpha Soft Blend"  
                    
                    elif current_color_match == "LAB_Mean":
                        lab_bg = cv2.cvtColor(crop_bg, cv2.COLOR_RGB2LAB).astype(np.float32)
                        lab_fg = cv2.cvtColor(crop_fg, cv2.COLOR_RGB2LAB).astype(np.float32)
                        mean_bg, std_bg = cv2.meanStdDev(lab_bg, mask=crop_mask_8u)
                        mean_fg, std_fg = cv2.meanStdDev(lab_fg, mask=crop_mask_8u)
                        
                        std_fg = np.maximum(std_fg, 1.0)
                        std_bg = np.maximum(std_bg, 1.0)
                        
                        scale = std_bg.flatten() / std_fg.flatten()
                        scale[0] = np.clip(scale[0], 0.5, 2.0)
                        scale[1] = np.clip(scale[1], 0.8, 1.25)
                        scale[2] = np.clip(scale[2], 0.8, 1.25)
                        
                        lab_fg = (lab_fg - mean_fg.flatten()) * scale + mean_bg.flatten()
                        lab_fg = np.clip(lab_fg, 0, 255).astype(np.uint8)
                        crop_fg = cv2.cvtColor(lab_fg, cv2.COLOR_LAB2RGB)

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
                    union_mask = np.maximum(union_mask, warped_mask)
                    img_bg = img_result.copy()
                
                # 整图光流精修
                if union_mask.max() > 0.5 and (use_tps or warp_method):
                    try:
                        img_result = self.global_flow_polish(img_result, original_bg, union_mask)
                    except Exception as e:
                        print(f"[Smart Merge] 整图精修失败: {e} | global polish failed")

                result_images.append(torch.from_numpy(img_result.astype(np.float32) / 255.0))

            except Exception as e:
                import traceback
                print(f"[Smart Merge 致命错误 | Fatal error] {e}")
                traceback.print_exc()
                result_images.append(items_orig[i])

        # 完成进度条
        if pbar is not None:
            pbar.update_absolute(total_steps, total_steps)

        if new_aligns_to_save is not None and any(x is not None for x in new_aligns_to_save):
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
