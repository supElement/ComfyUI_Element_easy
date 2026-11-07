import os
import sys

import torch
import torch.nn.functional as F
import numpy as np
import cv2

from ..element_easy.sm_common import (
    _sm_note,
    _sm_log,
    _sm_debug_write,
    _MergeProgress,
    _LRUCache,
    _GridCompositor,
    _sm_pick_device,
    ensure_hub_dir,
    set_active_progress, set_log_hook,
)
from ..element_easy.sm_color_sync import (
    _apply_color_match,
    _apply_global_lab_shift,
    _estimate_global_lab_shift,
)
from ..element_easy.sm_align import (
    AlignState,
    _bridge_photometric_ok,
    _compute_edit_mask,
    perform_kornia_alignment,
    perform_sift_alignment,
)
from ..element_easy.sm_flow import global_flow_polish
from ..element_easy.sm_compose import (
    _alpha_blend_crop,
    _blend_pads,
    _grid_tile_weight,
    make_edge_safe_soft_mask,
)

try:
    from server import PromptServer
    HAS_PROMPT_SERVER = True
except ImportError:
    PromptServer = None
    HAS_PROMPT_SERVER = False

GRID_TYPE = "ELEMENT_TILE_GRID"

class SmartMergeImages:
    
    DEBUG = False

    @classmethod
    def _dlog(cls, *args, **kwargs):
        """调试日志: 仅当 DEBUG=True 时输出, 调用方式与 print 一致"""
        if not cls.DEBUG:
            return
        _sm_debug_write(*args, **kwargs)

    _align_cache = _LRUCache(4)
    
    DESCRIPTION = (
        "智能局部重绘回贴节点: 将 AI 编辑后的局部裁块(B)自动对齐、畸变校正(TPS)、色彩统一后融合回原图。\n"
        "· 接入 original_crop_A(编辑前裁块)→ 桥接对齐 B→A→BG + LoFTR/TPS 非刚性畸变校正 + 可选二阶段精校(second_pass); Optical_Flow 开时再做逐块光流 + 整图光流精修;\n"
        "· Optical_Flow 开: 在 TPS 之上叠加光流精修(优先 DIS, 环境不支持时自动降级 Farneback);\n"
        "· second_pass 开: 桥接对齐后每块都用 LoFTR 求一次残余位移并直接做 TPS 微调(默认关);\n"
        "· color_protection 开: 保护分块内的 AI 改色(仅用未编辑像素估计色差); 关(默认): 全强度色彩校正;\n"
        "· 三个图像端口原生支持 List / Batch / 单张输入(节点已声明 INPUT_IS_LIST), 无需外接 'Image List To Image Batch' 节点; 各裁块尺寸可不同。\n"
        "推荐: Optical_Flow 开, use_tps 开, use_gpu=True。\n"
        "--------------------------------------------------\n"
        "Smart local-inpaint re-composite node: aligns the AI-edited crop (B), corrects its deformation via TPS,\n"
        "harmonizes color, then blends it back into the original image.\n"
        "· With original_crop_A connected → bridge alignment B→A→BG with LoFTR/TPS non-rigid correction and optional second-pass refinement (second_pass);\n"
        "  when Optical_Flow is ON, per-crop optical flow plus global flow polish are added;\n"
        "· Optical_Flow ON: adds optical-flow refinement on top of TPS (DIS first, auto-fallback to Farneback);\n"
        "· second_pass ON: after bridge alignment, every crop gets a LoFTR residual match and a direct TPS tweak (default OFF);\n"
        "· color_protection ON: keeps AI recolors (color shift estimated from un-edited pixels only); OFF (default): full-strength color matching;\n"
        "· All three image ports natively accept list / batch / single images (INPUT_IS_LIST declared).\n"
        "Recommended: Optical_Flow ON, use_tps ON, use_gpu=True."
    )

    OUTPUT_TOOLTIPS = ("融合后的完整图像(batch) | Merged image(s) as a standard batch",)

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
                    _collect(e)
                return
            if isinstance(x, np.ndarray):
                try:
                    x = torch.from_numpy(x)
                except Exception:
                    return
            if not isinstance(x, torch.Tensor):
                return
            t = x.detach().cpu().float()
            if t.dim() == 2:
                t = t.unsqueeze(-1)
            if t.dim() == 3:
                if t.shape[-1] == 1:
                    t = t.repeat(1, 1, 3)
                items.append(t)
            elif t.dim() == 4:
                if t.shape[-1] == 1:
                    t = t.repeat(1, 1, 1, 3)
                for j in range(t.shape[0]):
                    items.append(t[j])

        _collect(image_input)

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
        """INPUT_IS_LIST 模式下控件参数可能以单元素 list 到达 → 解包为标量。"""
        if isinstance(v, (list, tuple)):
            if len(v) == 0:
                return default
            return v[0]
        return v

    @staticmethod
    def _mask_to_hw(m):
        """grid 里的分块 mask (1,H,W,1 / H,W,1 / 1,H,W) → (H,W) float32 numpy。"""
        if m is None:
            return None
        if torch.is_tensor(m):
            m = m.detach().cpu().numpy()
        m = np.asarray(m)
        if m.ndim == 4:
            m = m[0, :, :, 0]
        elif m.ndim == 3:
            m = m[0] if m.shape[0] == 1 else m[:, :, 0]
        if m.ndim != 2 or m.size == 0:
            return None
        return m.astype(np.float32, copy=False)

    @classmethod
    def _grid_fingerprint(cls, split_grid):
        if not isinstance(split_grid, dict):
            return "none"
        import hashlib
        parts = [repr(split_grid.get(k)) for k in (
            "work_w", "work_h", "img_w", "img_h", "unified_upscale", "overlap"
        )]
        tile_keys = (
            "x", "y", "width", "height", "gen_w", "gen_h", "kind", "layer",
            "fade_top", "fade_bottom", "fade_left", "fade_right",
            "radius_tl", "radius_tr", "radius_bl", "radius_br", "layer_region"
        )
        for tile in split_grid.get("tiles", []) or []:
            parts.extend(repr(tile.get(k)) for k in tile_keys)
            parts.append(cls._tensor_fingerprint(tile.get("mask")))
        return hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()[:24]

    @classmethod
    def _make_align_key(cls, original_items, edited_items, cropA_items, warp_method,
                        second_pass, use_gpu, use_tps=True, split_grid=None):
        # use_gpu 只影响设备: 不改变放置几何, 放进键里会让"只切换设备"也整轮重算对齐。
        # second_pass 会改变放置几何, 必须参与键。
        return "|".join([
            cls._items_fingerprint(original_items),
            cls._items_fingerprint(edited_items),
            cls._items_fingerprint(cropA_items),
            cls._grid_fingerprint(split_grid),
            str(bool(warp_method)),
            str(bool(second_pass)),
            str(bool(use_tps)),
        ])

    @classmethod
    def _clear_cache(cls):
        cls._align_cache.clear()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {
                    "tooltip": "原始背景图(未编辑的完整图像)。只有第一张会被使用。\n"
                               "原生支持 List / Batch / 单张输入(节点已声明 INPUT_IS_LIST, 引擎不会逐项展开), 无需外接 Image List To Image Batch。\n"
                               "--------------------------------------------------\n"
                               "Original background image(s) before editing; only the first one is used.\n"
                               "Natively accepts list / batch / single image (INPUT_IS_LIST declared, no per-item expansion) — "
                               "no external 'Image List To Image Batch' node needed."
                }),
                "edited_crop_B": ("IMAGE", {
                    "tooltip": "AI 编辑后的局部裁块(B), 将被对齐、畸变校正并贴回背景。可批量; 各裁块尺寸可不同(保持各自原始分辨率)。\n"
                               "原生支持 List / Batch / 单张输入, 多个裁块在单次执行中全部处理, 输出一张合成图。\n"
                               "--------------------------------------------------\n"
                               "AI-edited local crop (B). It will be aligned, de-warped and re-composited onto the background. "
                               "Crops may have different sizes (each keeps its native resolution).\n"
                               "Natively accepts list / batch / single image — all crops are processed in ONE execution, producing a single merged image."
                }),
                "Optical_Flow": ("BOOLEAN", {
                    "default": False,
                    "label_on": "on",
                    "label_off": "off",
                    "tooltip": "光流精修开关(TPS 由 use_tps 单独控制, 与这里无关):\n"
                               "· 关: 不跑光流; 保持定位 + TPS(use_tps 开时)\n"
                               "· 开: 在定位/TPS 之上再叠加逐块光流 + 整图光流精修\n"
                               "--------------------------------------------------\n"
                               "Optical-flow refinement switch (TPS is controlled separately by use_tps):\n"
                               "· OFF: no optical flow; placement + TPS (if use_tps ON)\n"
                               "· ON: adds per-crop optical flow and the global flow polish on top"
                }),

                "second_pass": ("BOOLEAN", {
                    "default": False,
                    "label_on": "on",
                    "label_off": "off",
                    "tooltip": "二阶段精校(桥接对齐且 use_tps 开时生效):\n"
                               "· 开: 每块都执行并直接应用(TPS 后再匹配一次残余位移, 用小位移 TPS 微调), 不做评分判定\n"
                               "· 关(默认): 不执行, 省一次 LoFTR 匹配\n"
                               "适合对齐/TPS 后仍有轻微局部错位(边缘、细线、文字)时开启; 每块约多 4~8s\n"
                               "--------------------------------------------------\n"
                               "Second-pass refinement (bridge alignment, requires use_tps ON):\n"
                               "· ON: always executed and applied per crop (no residual pre-check, no score-based rejection): after TPS, matches residual displacement once more and applies a small-displacement TPS tweak\n"
                               "· OFF (default): not executed, saves one LoFTR match\n"
                               "Use when slight local misalignment remains after alignment/TPS (edges, thin lines, text); about +4~8s per crop"
                }),

                "use_tps": ("BOOLEAN", {
                    "default": True,
                    "label_on": "TPS", "label_off": "Homography Only",
                    "tooltip": "TPS 非刚性畸变校正(推荐开启):\n· 开: 桥接定位 + LoFTR/TPS 畸变校正\n· 关: 仅桥接H定位(必要时+光流精修), 最快\n"
                               "--------------------------------------------------\n"
                               "TPS non-rigid deformation correction (recommended ON). OFF: bridge-H placement only, fastest."
                }),
                "warp_smooth": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 4.0, "step": 0.05,
                    "tooltip": "整图精修光流场的平滑强度(仅 Optical_Flow 开时生效)\n"
                               "--------------------------------------------------\n"
                               "Smoothing strength of the global-flow polish field (only when Optical_Flow is ON)"
                }),

                "color_match": ([
                    "Patch_based_color",
                    "LAB_Mean",
                    "Laplacian Pyramid Blend",
                    "SeamlessClone (PS Auto Blend)",
                    "Alpha Soft Blend"
                ], {
                    "tooltip": "色彩迁移/融合策略(消除局部编辑与背景的色差)。除 Alpha Soft Blend 外，统一先做轻度整图 LAB 粗校正，再执行所选分块匹配:\n"
                               "· Patch_based_color 分块LAB色差同步(推荐, 色差大/不均匀时效果好)\n"
                               "· LAB_Mean 整块均值/方差匹配(轻量快速)\n"
                               "· Laplacian Pyramid 金字塔融合(先匹配整体亮度, 再多频带消接缝)\n"
                               "· SeamlessClone 泊松融合(先匹配亮度; 内容大改区域慎用, 易褪色)\n"
                               "· Alpha Soft Blend 仅羽化混合, 不做任何色彩/亮度校正\n"
                               "--------------------------------------------------\n"
                               "Color transfer / blending strategy. Except Alpha Soft Blend, all modes use gentle global LAB correction before per-tile matching:\n"
                               "· Patch_based_color: patch-wise LAB color sync (recommended for casts)\n"
                               "· LAB_Mean: per-block mean/std matching in LAB (lightweight)\n"
                               "· Laplacian Pyramid: luminance matching followed by multi-band blending\n"
                               "· SeamlessClone: luminance matching followed by Poisson blending\n"
                               "· Alpha Soft Blend: feathering only, with no color/luminance correction"
                }),

                "color_protection": ("BOOLEAN", {
                    "default": False,
                    "label_on": "true",
                    "label_off": "false",
                    "tooltip": "是否保护分块内的 AI 改色(如把衣服改成红色):\n"
                               "· 关(默认): 色彩匹配不区分编辑/未编辑像素, 整块按背景色调统一 → 普通分块合并的校正最强\n"
                               "· 开: 只用未编辑像素估计色差, 且编辑区内校正减弱 → 保留 AI 改色, 但普通合并的校正会变弱\n"
                               "编辑色的判定阈值见下方 Color_p_threshold。仅影响色彩匹配; 对齐/TPS/光流/羽化不受影响。\n"
                               "--------------------------------------------------\n"
                               "Protect AI recolored areas inside the crop:\n"
                               "· OFF (default): color matching ignores edited/un-edited distinction → full-strength correction for normal tile merging\n"
                               "· ON: estimate color shift from un-edited pixels only, and attenuate correction inside edited areas → keeps intentional recolors\n"
                               "Affects color matching only; alignment / TPS / optical flow / feathering are unchanged."
                }),

                "Color_p_threshold": ("FLOAT", {
                    "default": 20.0, "min": 3.0, "max": 120.0, "step": 1.0,
                    "tooltip": "色差阈值(仅 color_protection 开时生效): crop B 与 A/原图的色差大于该值即判为编辑色, 由 color_protection 保护。\n"
                               "阈值到 3 倍阈值之间平滑过渡; 越小保护范围越大, 越大只有明显改色才保护。默认 20 = 原行为。\n"
                               "--------------------------------------------------\n"
                               "Color-difference threshold (only when color_protection is ON): pixels whose color difference between crop B and A/original "
                               "exceeds this value count as edited and are protected (transition up to 3x the value). "
                               "Smaller = wider protection; default 20 = previous behavior."
                }),

                "feather_kernel": ("INT", {
                    "default": 20, "min": 0, "max": 256, "step": 1,
                    "tooltip": "羽化半径(px): 贴图边缘柔化宽度。色相保护关闭时兼作 Patch 色彩同步的块尺寸基准(块尺寸≈2×羽化); 色相保护开启时块尺寸改为按裁块短边 12%(夹在 48~160), 不再跟随羽化。一般 15~40; 越大过渡越柔但可能侵入更多原始内容。连接 split_grid 时改为 0~100 对应 Element Tile Merge 节点的 feather 0~1.0, 100 即最大值(超过按 1.0)。\n"
                               "--------------------------------------------------\n"
                               "Feather radius (px): edge-softening width of the pasted crop. With color_protection OFF it also sets the Patch color-sync block size (~2×feather); with protection ON the block size becomes 12% of the crop short side (clamped 48~160) instead. "
                               "Typical 15~40; larger = softer transition but may eat into more original content. With split_grid connected, 0~100 maps linearly to Element Tile Merge's feather 0~1.0 (100 = maximum, values above are clamped)."
                }),

                "use_gpu": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "GPU 加速特征匹配(DISK/LoFTR)与色彩匹配。光流、TPS/warp、无缝克隆等 OpenCV 步骤仍在 CPU 运行。无显卡或显存不足时关闭。\n"
                               "--------------------------------------------------\n"
                               "Use GPU for feature matching (DISK/LoFTR) and color matching. OpenCV steps (optical flow, TPS/warp, seamless clone) stay on CPU. Turn off if no GPU or VRAM is insufficient."
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
                    "tooltip": "可选: 编辑前的局部裁块(A), 与 B 同视角同内容。提供后启用桥接对齐 B→(等比)→A→(SIFT)→BG, 对位比自动匹配更稳, 且 Optical_Flow 开时仍执行光流精修; 不提供则直接在背景上自动特征匹配。\n"
                               "原生支持 List / Batch / 单张输入; A 与 B 数量/尺寸不必严格一致(自动按索引配对)。\n"
                               "--------------------------------------------------\n"
                               "Optional: pre-edit local crop (A), same viewpoint/content as B. When provided, bridge alignment B→(scale)→A→(SIFT)→BG is used — "
                               "more reliable placement than auto-matching, and optical-flow refinement still applies when Optical_Flow is ON.\n"
                               "Natively accepts list / batch / single image; A and B counts/sizes need not match exactly (paired by index)."
                }),
                
                "split_grid": (GRID_TYPE, {
                    "tooltip": "可选: ElementTileSplit 的 grid 信息。连接后使用 fade_top/bottom/left/right 平滑 S 形渐变 + 圆角 mask 高斯羽化，逐 tile 覆盖式合成。\n"
                               "grid 里带锁边 edit_mask 时会一并剔除未重绘的锁定带（与 ElementTileMerge 行为一致）。\n"
                               "grid 坐标作为布局锚点与保底; 有桥接A或可靠特征匹配时仍走 TPS/光流, 找不到可靠对应时直接按 grid 坐标放置。\n"
                               "色彩匹配顺序与非 grid 模式一致。\n"
                               "--------------------------------------------------\n"
                               "Optional: grid from ElementTileSplit. Uses smoothstep fades, gaussian mask feathering and alpha-over compositing. "
                               "If the grid carries an edge-lock edit_mask, the un-repainted locked band is excluded as well (same as ElementTileMerge). "
                               "Grid coordinates act as the layout anchor and fallback; TPS / optical flow still run when bridge-A or reliable features are available, otherwise the grid placement is used as-is. "
                               "Color-matching order is identical to non-grid mode."
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("Merged_Image",)
    FUNCTION = "smart_merge"
    CATEGORY = "Element_easy/image"

    # 声明接受 List 输入, 阻止 ComfyUI 对 List 输入做隐式"逐项展开"
    INPUT_IS_LIST = True

    






























    













































    def smart_merge(self, original_image, edited_crop_B, Optical_Flow, color_match, second_pass, feather_kernel,
                    color_protection=False, Color_p_threshold=20.0, use_tps=True, warp_smooth=1.0,
                    use_gpu=False, force_recompute=False,
                    original_crop_A=None, split_grid=None, unique_id=None, prompt=None, extra_pnginfo=None):

        ensure_hub_dir()

        # INPUT_IS_LIST 模式下, 所有输入(含控件/隐藏参数)都可能以 list 形式到达 → 解包为标量
        warp_method = self._unwrap_scalar(Optical_Flow, False)
        color_match = self._unwrap_scalar(color_match, "Alpha Soft Blend")
        color_protection = self._unwrap_scalar(color_protection, False)
        Color_p_threshold = self._unwrap_scalar(Color_p_threshold, 20.0)
        second_pass = self._unwrap_scalar(second_pass, False)
        use_tps = self._unwrap_scalar(use_tps, True)
        warp_smooth = self._unwrap_scalar(warp_smooth, 1.0)
        feather_kernel = self._unwrap_scalar(feather_kernel, 20)
        use_gpu = self._unwrap_scalar(use_gpu, False)
        force_recompute = self._unwrap_scalar(force_recompute, False)
        unique_id = self._unwrap_scalar(unique_id)
        prompt = self._unwrap_scalar(prompt)
        extra_pnginfo = self._unwrap_scalar(extra_pnginfo)
        split_grid = self._unwrap_scalar(split_grid)

        items_orig = self._normalize_image_items(original_image)
        items_B = self._normalize_image_items(edited_crop_B)
        items_A = (self._normalize_image_items(original_crop_A)
                   if original_crop_A is not None else None)

        # 估流尺度: 原始裁块 A / 编辑分块 B 的宽度比 = 内容原生分辨率相对画布的比例。
        # 光流在缩放到这个比例的图上计算, 精度跟随内容分辨率而不是画布分辨率。
        align_state = AlignState()
        if items_A and items_B:
            w_a0, w_b0 = int(items_A[0].shape[1]), int(items_B[0].shape[1])
            if w_a0 > 0 and w_b0 > 0:
                align_state.flow_scale = min(1.0, w_a0 / float(w_b0))

        B_orig = len(items_orig)
        B_crop = len(items_B)

        if B_orig == 0 or B_crop == 0:
            if B_orig > 0:
                try:
                    return (torch.stack(items_orig),)
                except Exception:
                    return (items_orig[0].unsqueeze(0),)
            return (torch.zeros((0, 8, 8, 3), dtype=torch.float32),)

        B_orig_loop = 1
        crops_per_bg = B_crop

        polish_step = 1 if warp_method else 0
        total_steps = B_orig_loop * (crops_per_bg + polish_step)

        device = _sm_pick_device(use_gpu)
        print(f"[Smart Merge] 使用设备: {device} (use_gpu={bool(use_gpu)}) | "
              f"device: {device}, use_gpu={bool(use_gpu)}")

        if force_recompute:
            self._clear_cache()
            print("[Smart Merge] 🗑 强制重算,缓存已清空 | Force recompute: cache cleared")

        align_key = self._make_align_key(
            items_orig, items_B, items_A, warp_method, second_pass,
            use_gpu, use_tps, split_grid=split_grid
        )

        cached_aligns = None if force_recompute else self._align_cache.get(align_key)
        align_cache_hit = cached_aligns is not None

        if align_cache_hit:
            print(f"[Smart Merge] ✅ 命中对齐缓存,跳过特征匹配 (共 {len(cached_aligns)} 组) | Alignment cache hit, skipping feature matching ({len(cached_aligns)} entries)")
        else:
            print("[Smart Merge] ⏳ 未命中缓存,执行完整对齐计算 | Cache miss, running full alignment computation")

        result_images = []
        total_crops = B_orig_loop * crops_per_bg
        new_aligns_to_save = [None] * total_crops if not align_cache_hit else None

        use_grid_alpha = split_grid is not None
        
        try:
            GRID_U_UP = float((split_grid or {}).get("unified_upscale", 1.0) or 1.0)
        except Exception:
            GRID_U_UP = 1.0
        if GRID_U_UP <= 0:
            GRID_U_UP = 1.0
        
        try:
            WORK_W = int((split_grid or {}).get("work_w", 0) or 0)
            WORK_H = int((split_grid or {}).get("work_h", 0) or 0)
            EXACT_W = int((split_grid or {}).get("exact_w", 0) or 0)
            EXACT_H = int((split_grid or {}).get("exact_h", 0) or 0)
        except Exception:
            WORK_W = WORK_H = EXACT_W = EXACT_H = 0
        
        USE_WORK_CANVAS = (split_grid is not None) and WORK_W > 0 and WORK_H > 0
        
        if USE_WORK_CANVAS:
            _inv_scale = 1.0
            if EXACT_W > 0 and EXACT_H > 0:
                # 用真实输出尺寸作画布：分块已向内平移，整幅单块补边超出的部分
                # 由该画布裁掉，输出不会多出 div 对齐产生的边缘条带。
                _sm_log(f"[SmartMerge] 使用真实输出画布: {EXACT_W}x{EXACT_H} "
                        f"(split work 画布 {WORK_W}x{WORK_H})")
                WORK_W, WORK_H = EXACT_W, EXACT_H
            else:
                _sm_log(f"[SmartMerge] 使用 split_grid work 画布: {WORK_W}x{WORK_H} (tile 坐标保持 out 空间) | using work canvas")
        else:
            _inv_scale = 1.0 / GRID_U_UP
            _sm_log(f"[SmartMerge] 回退到原行为: tile 坐标反变换 (1/unified_upscale={_inv_scale:.3f}), 原图尺寸保持不变")

        def _scaled_bands(value):
            if not value:
                return value
            try:
                return tuple(float(v) * _inv_scale for v in value)
            except (TypeError, ValueError):
                return value

        def _tile_info_to_src(ti):
            """把 grid tile 的坐标从输出空间缩放到源空间（SmartMerge 的 original_bg 尺寸）。"""
            if ti is None:
                return None
            lr = ti.get("layer_region")
            return {
                "x":           float(ti.get("x", 0))           * _inv_scale,
                "y":           float(ti.get("y", 0))           * _inv_scale,
                "width":       float(ti.get("width", 1))       * _inv_scale,
                "height":      float(ti.get("height", 1))      * _inv_scale,
                "fade_top":    float(ti.get("fade_top", 0))    * _inv_scale,
                "fade_bottom": float(ti.get("fade_bottom", 0)) * _inv_scale,
                "fade_left":   float(ti.get("fade_left", 0))   * _inv_scale,
                "fade_right":  float(ti.get("fade_right", 0))  * _inv_scale,
                "radius_tl":   float(ti.get("radius_tl", 0))   * _inv_scale,
                "radius_tr":   float(ti.get("radius_tr", 0))   * _inv_scale,
                "radius_bl":   float(ti.get("radius_bl", 0))   * _inv_scale,
                "radius_br":   float(ti.get("radius_br", 0))   * _inv_scale,
                "layer_region": ([float(v) * _inv_scale for v in lr] if lr else None),
                "edit_bands":  _scaled_bands(ti.get("edit_bands")),
                "lock_bands":  _scaled_bands(ti.get("lock_bands")),
                "corner_feather": float(ti.get("corner_feather", 0) or 0) * _inv_scale,
                "mask":        ti.get("mask"),          
                "edit_mask":   self._mask_to_hw(ti.get("edit_mask")),  # 锁边带=0, 合成时剔除
                "kind":        ti.get("kind", "layer"), 
                "layer":       ti.get("layer", 0),      
            }

        _sm_log(f"[SmartMerge] grid coordinate scale: unified_upscale={GRID_U_UP:.3f}")
        
        grid_tiles = []
        if use_grid_alpha:
            try:
                raw_tiles = (split_grid or {}).get("tiles", []) or []
                grid_tiles = [_tile_info_to_src(t) for t in raw_tiles]  
            except Exception:
                grid_tiles = []
            if not grid_tiles:
                print("[Smart Merge] split_grid 已连接但没有 tiles, 回退到默认 alpha | split_grid has no tiles, falling back")
                use_grid_alpha = False
            else:
                pads = _blend_pads(grid_tiles)
                for ti, pad in zip(grid_tiles, pads):
                    ti["blend_pads"] = pad

        pbar = _MergeProgress(total_steps)
        set_active_progress(pbar)

        for i in range(B_orig_loop):
            try:
                img_bg = self._item_to_uint8_rgb(items_orig[i])

                # split_grid: 原图 resize 到 work 画布 (与 ElementTileMerge 一致)
                if USE_WORK_CANVAS and (img_bg.shape[1] != WORK_W or img_bg.shape[0] != WORK_H):
                    _sm_log(f"[Smart Merge] original_image {img_bg.shape[1]}x{img_bg.shape[0]} → "
                          f"{WORK_W}x{WORK_H} (match split_grid work canvas)")
                    img_bg = cv2.resize(img_bg, (WORK_W, WORK_H), interpolation=cv2.INTER_LANCZOS4)
                
                start_idx = i * crops_per_bg
                end_idx = min(start_idx + crops_per_bg, B_crop)
                if start_idx >= B_crop:
                    result_images.append(torch.from_numpy(img_bg.astype(np.float32) / 255.0))
                    continue

                original_bg = img_bg.copy()
                # 布局观测只对同一张图有效(B→BG 模式下用于反推格子步长)
                align_state.b2bg_layout_obs = {}
                skipped_tiles = []
                union_mask = np.zeros(img_bg.shape[:2], dtype=np.float32)
                union_edit_mask = np.ones(img_bg.shape[:2], dtype=np.float32)
                
                compositor = _GridCompositor(img_bg.shape) if use_grid_alpha else None

                img_result = img_bg.copy()
                prepared_crops = {}
                color_prot_masks = {}

                # 第一遍：倒序对齐所有分块，全局统计完成前不做局部校色或合成。
                for crop_idx in range(end_idx - 1, start_idx - 1, -1):
                    pbar.step()

                    img_fg = self._item_to_uint8_rgb(items_B[crop_idx])
                    h_fg, w_fg = img_fg.shape[:2]

                    crop_idx_mask = None
                    if use_grid_alpha and crop_idx < len(grid_tiles):
                        m_tensor = grid_tiles[crop_idx].get("mask")
                        if m_tensor is not None:
                            if hasattr(m_tensor, "cpu"):
                                crop_idx_mask = m_tensor.cpu().numpy()
                                if crop_idx_mask.ndim == 4:
                                    crop_idx_mask = crop_idx_mask[0, :, :, 0]
                            elif isinstance(m_tensor, np.ndarray):
                                crop_idx_mask = m_tensor
                                if crop_idx_mask.ndim == 3:
                                    crop_idx_mask = crop_idx_mask[..., 0]
                            if crop_idx_mask is not None and crop_idx_mask.shape[:2] != (h_fg, w_fg):
                                crop_idx_mask = cv2.resize(crop_idx_mask, (w_fg, h_fg), interpolation=cv2.INTER_LINEAR)

                    cached_edit_mask = None
                    cached_residual = None
                    if align_cache_hit and crop_idx < len(cached_aligns) and cached_aligns[crop_idx] is not None:
                        cached = cached_aligns[crop_idx]
                        warped_fg = cached["warped_fg"].copy()
                        warped_mask = cached["warped_mask"].copy()
                        cached_edit_mask = cached.get("edit_mask")
                        cached_residual = cached.get("residual")
                        align_state.last_residual_px = cached_residual
                    
                    else:
                        img_bridge_A = None
                        if items_A is not None and crop_idx < len(items_A):
                            img_bridge_A = self._item_to_uint8_rgb(items_A[crop_idx])

                        success_align = False
                        warped_fg = None
                        warped_mask = None

                        # split_grid 坐标可给出绝对正确的 H, 优先使用
                        H_grid = None
                        if use_grid_alpha and crop_idx < len(grid_tiles):
                            tile = grid_tiles[crop_idx]
                            tx = float(tile.get("x", 0))
                            ty = float(tile.get("y", 0))
                            tw = float(tile.get("width", 1))
                            th = float(tile.get("height", 1))
                            if tw > 0 and th > 0:
                                sx = tw / float(w_fg)
                                sy = th / float(h_fg)
                                H_grid = np.array([[sx, 0, tx], [0, sy, ty], [0, 0, 1]], dtype=np.float64)
                                self._dlog(f"[Smart Merge] split_grid 坐标将作为对齐锚点+保底 (Tile {crop_idx}) | grid coords used as anchor & fallback")

                        if H_grid is not None:
                            # grid 只提供布局/保底。有原始裁块 A 时, 先实测 A→BG 的放置,
                            H_bridge = None
                            align_state.bridge_A = img_bridge_A
                            align_state.bridge_H_A2BG = None
                            if img_bridge_A is not None:
                                h_A, w_A = img_bridge_A.shape[:2]
                                H_A_to_BG = perform_sift_alignment(img_bridge_A, original_bg)
                                if (H_A_to_BG is not None and h_A > 0 and w_A > 0
                                        and _bridge_photometric_ok(
                                            H_A_to_BG, img_bridge_A, original_bg)):
                                    sx, sy = w_A / float(w_fg), h_A / float(h_fg)
                                    H_FG_to_A = np.array([
                                        [sx, 0, 0],
                                        [0, sy, 0],
                                        [0, 0, 1]
                                    ], dtype=np.float64)
                                    H_bridge = np.dot(H_A_to_BG, H_FG_to_A)
                                    align_state.bridge_H_A2BG = H_A_to_BG
                                elif H_A_to_BG is not None:
                                    _sm_log("[Smart Merge] 桥接 A→BG 光度校验未通过, 本轮退化到 grid 锚定 | bridge A→BG failed photometric check, using grid anchor")

                            warped_fg, warped_mask, success_align = perform_kornia_alignment(
                                align_state,
                                img_fg, original_bg,
                                warp_method=warp_method,
                                second_pass=second_pass, device=device,
                                preset_H=H_grid,
                                use_tps=use_tps,
                                base_mask=crop_idx_mask,
                                is_grid_preset=True,
                                bridge_H=H_bridge
                            )
                            if success_align:
                                _sm_log("[Smart Merge] split_grid 对齐完成 | Grid alignment done")
                                
                        # 桥接对齐: B → A → BG
                        elif img_bridge_A is not None:
                            h_A, w_A = img_bridge_A.shape[:2]
                            if h_A > 0 and w_A > 0:
                                H_A_to_BG = perform_sift_alignment(img_bridge_A, original_bg)
                                if H_A_to_BG is not None:
                                    h_bg, w_bg = img_bg.shape[:2]
                                    sx, sy = w_A / float(w_fg), h_A / float(h_fg)
                                    H_FG_to_A = np.array([
                                        [sx, 0, 0],
                                        [0, sy, 0],
                                        [0, 0, 1]
                                    ], dtype=np.float64)
                                    H_Total = np.dot(H_A_to_BG, H_FG_to_A)
                                    align_state.bridge_A = img_bridge_A  
                                    align_state.bridge_H_A2BG = H_A_to_BG
                                    warped_fg, warped_mask, success_align = perform_kornia_alignment(
                                        align_state,
                                        img_fg, original_bg,
                                        warp_method=warp_method,
                                        second_pass=second_pass, device=device,
                                        preset_H=H_Total,
                                        use_tps=use_tps,
                                        base_mask=crop_idx_mask,
                                        crop_index=crop_idx - start_idx,
                                        crop_total=end_idx - start_idx
                                    )
                                    if success_align:
                                        _sm_log("[Smart Merge] 桥接对齐 B→A→BG 完成 (含畸变校正) | Bridge alignment B→A→BG done (with deformation correction)")


                        if not success_align:
                            warped_fg, warped_mask, ok = perform_kornia_alignment(
                                align_state,
                                img_fg, original_bg,
                                warp_method=warp_method,
                                second_pass=second_pass, use_tps=use_tps, device=device,
                                base_mask=crop_idx_mask,
                                crop_index=crop_idx - start_idx,
                                crop_total=end_idx - start_idx
                            )
                            if ok:
                                success_align = True
                            else:
                                _sm_log(f"[Smart Merge] 分块 {crop_idx} 无可靠放置, 跳过以保护整图 | "
                                      f"tile {crop_idx} skipped: no reliable placement")
                                skipped_tiles.append(crop_idx)
                                continue

                    if cached_edit_mask is not None and cached_edit_mask.shape == original_bg.shape[:2]:
                        align_state.last_edit_mask = cached_edit_mask.copy()
                    else:
                        align_state.last_edit_mask = _compute_edit_mask(
                            original_bg, warped_fg, valid_mask=warped_mask, device=device
                        )
                    if cached_residual is not None:
                        align_state.last_residual_px = cached_residual

                    if new_aligns_to_save is not None:
                        new_aligns_to_save[crop_idx] = {
                            "warped_fg": warped_fg.copy(),
                            "warped_mask": warped_mask.copy(),
                            "edit_mask": align_state.last_edit_mask.copy() if align_state.last_edit_mask is not None else None,
                            "residual": align_state.last_residual_px,
                        }

                    prepared_crops[crop_idx] = (warped_fg, warped_mask, align_state.last_edit_mask)
                    if color_protection:
                        thr = max(1.0, float(Color_p_threshold))
                        if abs(thr - 20.0) < 1e-6:
                            color_prot_masks[crop_idx] = align_state.last_edit_mask
                        else:
                            color_prot_masks[crop_idx] = _compute_edit_mask(
                                original_bg, warped_fg, d_lo=thr, d_hi=thr * 3.0,
                                valid_mask=warped_mask, device=device)

                global_lab_shift = None
                if color_match != "Alpha Soft Blend":
                    shift_crops = prepared_crops
                    if color_prot_masks:
                        shift_crops = {k: (v[0], v[1], color_prot_masks.get(k))
                                       for k, v in prepared_crops.items()}
                    global_lab_shift = _estimate_global_lab_shift(
                        original_bg, shift_crops, protect_edits=color_protection)
                    if global_lab_shift is not None:
                        _sm_log(f"[Smart Merge] 轻度整图 LAB 前置校正: {global_lab_shift.round(2).tolist()} | "
                              f"global coarse LAB shift")

                for crop_idx in range(end_idx - 1, start_idx - 1, -1):
                    if crop_idx not in prepared_crops:
                        continue
                    warped_fg, warped_mask, crop_edit_mask_full = prepared_crops[crop_idx]

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
                    prot_full = color_prot_masks.get(crop_idx)
                    color_edit_mask = (prot_full[ymin:ymax, xmin:xmax]
                                       if prot_full is not None else None)
                    if global_lab_shift is not None:
                        crop_fg = _apply_global_lab_shift(
                            crop_fg, global_lab_shift, edit_mask=color_edit_mask,
                            device=device)

                    tile_info = (grid_tiles[crop_idx]
                                 if (use_grid_alpha and crop_idx < len(grid_tiles)) else None)
                    weight_local = None
                    if tile_info is not None:
                        grid_overlap = int((split_grid or {}).get("overlap", 0))
                        weight_local = _grid_tile_weight(
                            tile_info, (xmin, ymin, xmax, ymax), crop_mask_float,
                            h_bg, w_bg, grid_overlap, feather_kernel)

                    # grid 的校正场连续外推，alpha 只在最终合成时施加一次。
                    if weight_local is None and color_edit_mask is not None:
                        color_apply_mask = make_edge_safe_soft_mask(
                            crop_mask_float, int(max(0, feather_kernel)))
                    else:
                        color_apply_mask = None

                    # 裁块哪一侧正好是画布边: 只给 Laplacian 最粗层做边界条件, 不动 alpha。
                    canvas_sides = (xmin <= 0, ymin <= 0, xmax >= w_bg, ymax >= h_bg)
                    crop_fg, color_done = _apply_color_match(
                        crop_fg, crop_bg, crop_mask_float, color_match,
                        feather_kernel, color_edit_mask, color_apply_mask,
                        grid_weight=weight_local is not None,
                        canvas_sides=canvas_sides, device=device)

                    if tile_info is not None:
                        layer = int(tile_info.get("layer") or 0)
                        is_bg = (tile_info.get("kind", "layer") in {"gap", "fallback", "unified"}
                                 or layer < 0)
                        compositor.add(crop_fg, weight_local, (xmin, ymin, xmax, ymax),
                                       None if is_bg else layer)
                    else:
                        crop_result = crop_fg if color_done else _alpha_blend_crop(
                            crop_fg, crop_bg, crop_mask_float, feather_kernel)

                        # 画布边缘 5px 渐变, 避免硬边
                        edge_blend = np.zeros_like(crop_mask_float)
                        edge_width = 5
                        if ymin == 0:
                            wgt = np.linspace(1, 0, edge_width)[:, None]
                            edge_blend[:edge_width, :] = wgt * crop_mask_float[:edge_width, :]
                        if ymax == h_bg:
                            wgt = np.linspace(0, 1, edge_width)[:, None]
                            edge_blend[-edge_width:, :] = wgt * crop_mask_float[-edge_width:, :]
                        if xmin == 0:
                            wgt = np.linspace(1, 0, edge_width)[None, :]
                            edge_blend[:, :edge_width] = np.maximum(
                                edge_blend[:, :edge_width], wgt * crop_mask_float[:, :edge_width])
                        if xmax == w_bg:
                            wgt = np.linspace(0, 1, edge_width)[None, :]
                            edge_blend[:, -edge_width:] = np.maximum(
                                edge_blend[:, -edge_width:], wgt * crop_mask_float[:, -edge_width:])

                        if edge_blend.max() > 0.01:
                            eb3 = edge_blend[:, :, np.newaxis]
                            crop_result = (crop_fg.astype(np.float32) * eb3
                                           + crop_result.astype(np.float32) * (1.0 - eb3))
                            crop_result = np.clip(crop_result, 0, 255).astype(np.uint8)

                        img_result[ymin:ymax, xmin:xmax] = crop_result
                        img_bg = img_result.copy()

                    union_mask = np.maximum(union_mask, warped_mask)
                    if crop_edit_mask_full is not None and crop_edit_mask_full.shape == union_edit_mask.shape:
                        union_edit_mask = np.minimum(union_edit_mask, crop_edit_mask_full)

                if skipped_tiles:
                    _sm_note(f"[Smart Merge] 本次跳过 {len(skipped_tiles)} 个分块 {skipped_tiles}: "
                             f"对应的 AI 编辑不会出现在成品中, 这些区域保留原图 | "
                             f"tiles {skipped_tiles} not merged (original content kept)")

                if compositor is not None:
                    img_result = compositor.finish(original_bg)
                    img_bg = img_result.copy()
                
                if union_mask.max() > 0.5 and warp_method:
                    try:
                        polish_edit_mask = union_edit_mask if union_edit_mask.min() < 0.99 else None
                        img_result = global_flow_polish(
                            img_result, original_bg, union_mask, edit_mask=polish_edit_mask,
                            warp_smooth=warp_smooth,
                            flow_scale=align_state.flow_scale)
                    except Exception as e:
                        _sm_note(f"[Smart Merge] 整图精修失败: {e} | global polish failed")
                if polish_step:
                    pbar.step(desc="Smart Merge · polish")

                result_images.append(torch.from_numpy(img_result.astype(np.float32) / 255.0))

            except Exception as e:
                import traceback
                print(f"[Smart Merge 致命错误 | Fatal error] {e}")
                traceback.print_exc()
                result_images.append(items_orig[i])

        pbar.close()
        set_active_progress(None)

        if new_aligns_to_save is not None and any(x is not None for x in new_aligns_to_save):
            self._align_cache[align_key] = new_aligns_to_save
            _n_ok = sum(1 for x in new_aligns_to_save if x is not None)
            print(f"[Smart Merge] 💾 已缓存 {_n_ok}/{len(new_aligns_to_save)} 个对齐结果 | "
                  f"Cached {_n_ok}/{len(new_aligns_to_save)} alignments")


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


# 让 _sm_log 与 _dlog 共用同一个 DEBUG 开关和输出通道
set_log_hook(SmartMergeImages._dlog)
