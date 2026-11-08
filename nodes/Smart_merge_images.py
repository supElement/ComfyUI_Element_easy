import os
import sys
import time

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
    apply_flow_stage,
    apply_second_pass_stage,
    apply_tps_stage,
    perform_placement,
    perform_sift_alignment,
    profile_snapshot,
)
from ..element_easy.sm_flow import global_flow_polish
from ..element_easy.sm_compose import (
    _blend_pads,
    _grid_tile_weight,
    _overlap_bands,
    _overlap_crossfade_weight,
    make_edge_safe_soft_mask,
    pad_canvas_edges,
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

    _align_cache = _LRUCache(5)
    _polish_cache = _LRUCache(2)
    
    DESCRIPTION = (
        "智能局部重绘回贴节点: 将 AI 编辑后的局部裁块(B)自动对齐、畸变校正(TPS)、色彩统一后融合回原图。\n"
        "--------------------------------------------------\n"
        "Smart local-inpaint re-composite node: aligns the AI-edited crop (B), corrects its deformation via TPS,\n"
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
    def _make_stage_keys(cls, original_items, edited_items, cropA_items, split_grid,
                         use_tps, warp_method, second_pass):
        """链式阶段键: 后一阶段只依赖前一阶段, 任一开关变化只让自身及之后的阶段失效。

        use_gpu 只影响设备: 不改变放置几何, 放进键里会让"只切换设备"也整轮重算对齐。
        """
        base = "|".join([
            cls._items_fingerprint(original_items),
            cls._items_fingerprint(edited_items),
            cls._items_fingerprint(cropA_items),
            cls._grid_fingerprint(split_grid),
        ])
        place_key = base + "|P"
        tps_key = place_key + f"|T{int(bool(use_tps))}"
        flow_key = tps_key + f"|F{int(bool(warp_method))}"
        pass2_key = flow_key + f"|S{int(bool(second_pass))}"
        return place_key, tps_key, flow_key, pass2_key

    @classmethod
    def _make_polish_key(cls, stage_key, color_match, color_protection,
                         Color_p_threshold, feather_kernel, warp_smooth):
        """整图光流精修的键: 合成参数 + 最终对齐阶段。"""
        return "|".join([
            stage_key,
            str(color_match),
            str(bool(color_protection)),
            f"{float(Color_p_threshold):.3f}",
            str(int(feather_kernel)),
            f"{float(warp_smooth):.3f}",
            "POLISH",
        ])

    @classmethod
    def _resolve_cache_hit(cls, keys, *, force_recompute, warp_method, second_pass):
        """按链路从最深阶段向上找命中点; 返回 (stage_start, pass2, flow, tps, place)。"""
        place_key, tps_key, flow_key, pass2_key = keys
        if force_recompute:
            return "place", None, None, None, None
        pass2_cached = cls._align_cache.get(pass2_key) if second_pass else None
        if pass2_cached is not None:
            return "done", pass2_cached, None, None, None
        flow_cached = cls._align_cache.get(flow_key) if warp_method else None
        if flow_cached is not None:
            return "after_flow", None, flow_cached, None, None
        tps_cached = cls._align_cache.get(tps_key)
        if tps_cached is not None:
            return "after_tps", None, None, tps_cached, None
        place_cached = cls._align_cache.get(place_key)
        if place_cached is not None:
            return "after_place", None, None, None, place_cached
        return "place", None, None, None, None

    @classmethod
    def _cache_stage(cls, key, entries, label):
        if entries is None or not any(e is not None for e in entries):
            return
        cls._align_cache[key] = entries
        n_ok = sum(1 for e in entries if e is not None)
        _sm_note(f"[Smart Merge] 💾 已缓存 {n_ok}/{len(entries)} 个{label}结果 | cached {label}")

    @classmethod
    def _clear_cache(cls):
        cls._align_cache.clear()
        cls._polish_cache.clear()

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "original_image": ("IMAGE", {
                    "tooltip": "原始背景图(未编辑), 只用第一张。支持 List / Batch / 单张。\n"
                               "Original background image; only the first is used. Accepts list / batch / single."
                }),
                "edited_crop_B": ("IMAGE", {
                    "tooltip": "AI 编辑后的局部裁块, 将对齐并贴回背景。支持 List / Batch / 单张, 尺寸可不同。\n"
                               "AI-edited crop(s) to align and composite back. Accepts list / batch / single; sizes may differ."
                }),
                "use_tps": ("BOOLEAN", {
                    "default": True,
                    "label_on": "TPS", "label_off": "Homography Only",
                    "tooltip": "TPS 非刚性畸变校正: 开 = LoFTR/TPS 校正(推荐); 关 = 仅单应性定位, 最快。\n"
                               "TPS non-rigid correction: ON = LoFTR/TPS (recommended); OFF = homography-only placement, fastest."
                }),
                "Optical_Flow": ("BOOLEAN", {
                    "default": False,
                    "label_on": "on",
                    "label_off": "off",
                    "tooltip": "逐块光流精修: 开 = 在定位/TPS 上叠加逐块光流。整图精修由 Full_Optical_Flow 单独控制。\n"
                               "Per-crop optical-flow refinement: ON = per-crop flow on top of placement/TPS. Full-image polish is controlled by Full_Optical_Flow."
                }),

                "second_pass": ("BOOLEAN", {
                    "default": False,
                    "label_on": "on",
                    "label_off": "off",
                    "tooltip": "二阶段精校: 逐块光流之后再跑一次小幅逐块光流(位移上限 4px), 不依赖 TPS。\n"
                               "Second-pass refinement: one extra small-amplitude per-crop flow pass (4px cap) after the first flow; independent of TPS."
                }),

                "Full_Optical_Flow": ("BOOLEAN", {
                    "default": False,
                    "label_on": "on",
                    "label_off": "off",
                    "tooltip": "整图光流精修: 开 = 合成后对整张成品再做一次低幅光流修正(位移上限 12px), 与逐块光流相互独立。\n"
                               "Full-image flow polish: ON = one extra low-amplitude flow pass on the whole merged image (12px cap); independent of per-crop flow."
                }),
                "warp_smooth": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 4.0, "step": 0.05,
                    "tooltip": "整图光流场的平滑强度(仅 Full_Optical_Flow 开时生效)。\n"
                               "Smoothing strength of the full-image flow field (Full_Optical_Flow ON only)."
                }),

                "color_match": ([
                    "Patch_based_color",
                    "LAB_Mean",
                    "Laplacian Pyramid Blend",
                    "SeamlessClone (PS Auto Blend)",
                    "Alpha Soft Blend"
                ], {
                    "tooltip": "色彩/融合策略。\n"
                               "Color / blend strategy."
                }),

                "color_protection": ("BOOLEAN", {
                    "default": False,
                    "label_on": "true",
                    "label_off": "false",
                    "tooltip": "保护分块内的 AI 改色。阈值见 Color_p_threshold。\n"
                               "Protect AI recolors. See Color_p_threshold."
                }),

                "Color_p_threshold": ("FLOAT", {
                    "default": 20.0, "min": 3.0, "max": 120.0, "step": 1.0,
                    "tooltip": "改色判定阈值(仅 color_protection 开时生效), 越小保护范围越大, 默认 20。\n"
                               "Recolor threshold (color_protection ON only); smaller = wider protection; default 20."
                }),

                "feather_kernel": ("INT", {
                    "default": 20, "min": 0, "max": 256, "step": 1,
                    "tooltip": "羽化半径(px), 越大过渡越柔, 一般 15~40。连接 split_grid 时 0~100 对应其 feather 0~1.0。\n"
                               "Feather radius (px); larger = softer, typical 15~40. With split_grid, 0~100 maps to its feather 0~1.0."
                }),

                "use_gpu": ("BOOLEAN", {
                    "default": True,
                    "tooltip": "GPU 加速特征匹配与色彩匹配; 光流/TPS/无缝克隆仍在 CPU。\n"
                               "Use GPU for feature and color matching; optical flow / TPS / seamless clone stay on CPU."
                }),
                "force_recompute": ("BOOLEAN", {
                    "default": False,
                    "tooltip": "清空对齐缓存并重新计算。\n"
                               "Clear the alignment cache and recompute."
                }),
            },
            "optional": {
                "original_crop_A": ("IMAGE", {
                    "tooltip": "可选: 编辑前裁块, 与 B 同视角。提供后走 B→A→BG 桥接对齐, 更稳; 按索引配对。\n"
                               "Optional: pre-edit crop with the same view as B. Enables bridge alignment B→A→BG (more reliable); paired by index."
                }),
                
                "split_grid": (GRID_TYPE, {
                    "tooltip": "可选: ElementTileSplit 的 grid, 启用渐变/圆角羽化与逐 tile 合成。\n"
                               "Optional: grid from ElementTileSplit; enables fade/rounded feathering and per-tile compositing."
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
                    color_protection=False, Color_p_threshold=20.0, use_tps=True,
                    Full_Optical_Flow=False, warp_smooth=1.0,
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
        full_optical_flow = self._unwrap_scalar(Full_Optical_Flow, False)
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

        device = _sm_pick_device(use_gpu)
        print(f"[Smart Merge] 使用设备: {device} (use_gpu={bool(use_gpu)}) | "
              f"device: {device}, use_gpu={bool(use_gpu)}")

        if force_recompute:
            self._clear_cache()
            print("[Smart Merge] 🗑 强制重算,缓存已清空 | Force recompute: cache cleared")

        place_key, tps_key, flow_key, pass2_key = self._make_stage_keys(
            items_orig, items_B, items_A, split_grid,
            use_tps, warp_method, second_pass
        )

        # 进度步数只计本次实际执行的阶段; 命中缓存的阶段不占步
        stage_hint = self._resolve_cache_hit(
            (place_key, tps_key, flow_key, pass2_key),
            force_recompute=force_recompute, warp_method=warp_method,
            second_pass=second_pass)[0]
        steps_per_crop = 1  # 合成/校色
        if stage_hint == "place":
            steps_per_crop += 1
        if use_tps and stage_hint in ("place", "after_place"):
            steps_per_crop += 1
        if warp_method and stage_hint in ("place", "after_place", "after_tps"):
            steps_per_crop += 1
        if second_pass and stage_hint in ("place", "after_place", "after_tps", "after_flow"):
            steps_per_crop += 1
        polish_step = 1 if full_optical_flow else 0
        total_steps = B_orig_loop * crops_per_bg * steps_per_crop + polish_step

        result_images = []
        stage_times = {}
        profile_snapshot(reset=True)

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
                
                compositor = _GridCompositor(img_bg.shape)

                img_result = img_bg.copy()
                prepared_crops = {}
                color_prot_masks = {}

                # ---- 分阶段对齐(定位 H → TPS → 逐块光流 → 二阶段); 每阶段独立缓存 ----
                stage_start, pass2_entries, flow_entries, tps_entries, place_entries = \
                    self._resolve_cache_hit(
                        (place_key, tps_key, flow_key, pass2_key),
                        force_recompute=force_recompute, warp_method=warp_method,
                        second_pass=second_pass)

                if stage_start == "done":
                    _sm_note("[Smart Merge] ✅ 命中全流程缓存: 定位 H + TPS + 逐块光流 + 二阶段 | full pipeline cache hit")
                elif stage_start == "after_flow":
                    _sm_note("[Smart Merge] ✅ 命中定位 H + TPS + 逐块光流缓存, 只补二阶段 | reuse placement/TPS/flow")
                elif stage_start == "after_tps":
                    _sm_note("[Smart Merge] ✅ 命中定位 H + TPS 缓存, 继续逐块光流/二阶段 | reuse placement/TPS")
                elif stage_start == "after_place":
                    _sm_note("[Smart Merge] ✅ 命中定位 H 缓存, 继续 TPS/光流/二阶段 | reuse placement")
                else:
                    _sm_note("[Smart Merge] ⏳ 未命中缓存, 执行完整对齐计算 | Cache miss, running full alignment computation")

                # 阶段 1: 定位 H (桥接/grid/自动)
                if stage_start == "place":
                    _t0 = time.perf_counter()
                    place_entries = [None] * B_crop
                    n_stage = end_idx - start_idx
                    _sm_note(f"[Smart Merge] ▶ 阶段 1/4 定位 H: {n_stage} 个分块 | "
                             f"stage 1/4 placement: {n_stage} crops")
                    for crop_idx in range(end_idx - 1, start_idx - 1, -1):
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

                        img_bridge_A = None
                        if items_A is not None and crop_idx < len(items_A):
                            img_bridge_A = self._item_to_uint8_rgb(items_A[crop_idx])

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

                        place = None
                        if H_grid is not None:
                            # grid 只提供布局/保底。有原始裁块 A 时, 先实测 A→BG 的放置,
                            H_bridge = None
                            align_state.bridge_A = img_bridge_A
                            align_state.bridge_H_A2BG = None
                            if img_bridge_A is not None:
                                h_A, w_A = img_bridge_A.shape[:2]
                                H_A_to_BG = perform_sift_alignment(img_bridge_A, original_bg)
                                if (H_A_to_BG is not None and h_A > 0 and w_A > 0
                                        and np.all(np.isfinite(H_A_to_BG))):
                                    # 实测 A→BG 始终留给 TPS 当目标; 光度校验只决定能否直接用于放置
                                    align_state.bridge_H_A2BG = H_A_to_BG
                                    if _bridge_photometric_ok(
                                            H_A_to_BG, img_bridge_A, original_bg):
                                        sx, sy = w_A / float(w_fg), h_A / float(h_fg)
                                        H_FG_to_A = np.array([
                                            [sx, 0, 0],
                                            [0, sy, 0],
                                            [0, 0, 1]
                                        ], dtype=np.float64)
                                        H_bridge = np.dot(H_A_to_BG, H_FG_to_A)
                                    else:
                                        _sm_log("[Smart Merge] 桥接 A→BG 光度校验未通过, 放置退化到 grid 锚定 (TPS 仍使用该实测H) | bridge A→BG failed photometric check, grid anchor for placement")

                            place = perform_placement(
                                align_state, img_fg, original_bg, device=device,
                                preset_H=H_grid,
                                base_mask=crop_idx_mask,
                                is_grid_preset=True,
                                bridge_H=H_bridge,
                                crop_index=crop_idx - start_idx,
                                crop_total=end_idx - start_idx,
                                bridge_A=getattr(align_state, 'bridge_A', None)
                            )
                            if place is not None:
                                _sm_log("[Smart Merge] split_grid 对齐完成 | Grid alignment done")

                        # 桥接对齐: B → A → BG
                        elif img_bridge_A is not None:
                            h_A, w_A = img_bridge_A.shape[:2]
                            if h_A > 0 and w_A > 0:
                                H_A_to_BG = perform_sift_alignment(img_bridge_A, original_bg)
                                if H_A_to_BG is not None:
                                    sx, sy = w_A / float(w_fg), h_A / float(h_fg)
                                    H_FG_to_A = np.array([
                                        [sx, 0, 0],
                                        [0, sy, 0],
                                        [0, 0, 1]
                                    ], dtype=np.float64)
                                    H_Total = np.dot(H_A_to_BG, H_FG_to_A)
                                    align_state.bridge_A = img_bridge_A
                                    align_state.bridge_H_A2BG = H_A_to_BG
                                    place = perform_placement(
                                        align_state, img_fg, original_bg, device=device,
                                        preset_H=H_Total,
                                        base_mask=crop_idx_mask,
                                        crop_index=crop_idx - start_idx,
                                        crop_total=end_idx - start_idx,
                                        bridge_A=img_bridge_A
                                    )
                                    if place is not None:
                                        _sm_log("[Smart Merge] 桥接对齐 B→A→BG 完成 (含畸变校正) | Bridge alignment B→A→BG done (with deformation correction)")

                        if place is None:
                            place = perform_placement(
                                align_state, img_fg, original_bg, device=device,
                                base_mask=crop_idx_mask,
                                crop_index=crop_idx - start_idx,
                                crop_total=end_idx - start_idx,
                                bridge_A=getattr(align_state, 'bridge_A', None)
                            )
                        if place is None:
                            _sm_log(f"[Smart Merge] 分块 {crop_idx} 无可靠放置, 跳过以保护整图 | "
                                  f"tile {crop_idx} skipped: no reliable placement")
                            skipped_tiles.append(crop_idx)
                            pbar.step(desc="Smart Merge · H")
                            continue
                        place_entries[crop_idx] = place
                        pbar.step(desc="Smart Merge · H")
                    self._cache_stage(place_key, place_entries, "定位 H | placement")
                    stage_times["place"] = stage_times.get("place", 0.0) + (time.perf_counter() - _t0)
                    stage_start = "after_place"

                # 阶段 2: 趋势 TPS
                if stage_start == "after_place":
                    _t0 = time.perf_counter()
                    tps_entries = [None] * B_crop
                    n_stage = end_idx - start_idx
                    if use_tps:
                        _sm_note(f"[Smart Merge] ▶ 阶段 2/4 趋势 TPS: {n_stage} 个分块 | "
                                 f"stage 2/4 TPS: {n_stage} crops")
                    for crop_idx in range(end_idx - 1, start_idx - 1, -1):
                        pe = place_entries[crop_idx]
                        if pe is None:
                            continue
                        img_fg = self._item_to_uint8_rgb(items_B[crop_idx])
                        img_bridge_A = None
                        if items_A is not None and crop_idx < len(items_A):
                            img_bridge_A = self._item_to_uint8_rgb(items_A[crop_idx])
                        tps_entries[crop_idx] = apply_tps_stage(
                            align_state, pe, img_fg, original_bg, device=device,
                            use_tps=use_tps, bridge_A=img_bridge_A)
                        if use_tps:
                            pbar.step(desc="Smart Merge · TPS")
                    self._cache_stage(tps_key, tps_entries, "TPS")
                    stage_times["tps"] = stage_times.get("tps", 0.0) + (time.perf_counter() - _t0)
                    stage_start = "after_tps"

                # 阶段 3: 逐块光流
                if stage_start == "after_tps":
                    if warp_method:
                        _t0 = time.perf_counter()
                        flow_entries = [None] * B_crop
                        n_stage = end_idx - start_idx
                        _sm_note(f"[Smart Merge] ▶ 阶段 3/4 逐块光流: {n_stage} 个分块 | "
                                 f"stage 3/4 per-crop flow: {n_stage} crops")
                        for crop_idx in range(end_idx - 1, start_idx - 1, -1):
                            te = tps_entries[crop_idx]
                            if te is None:
                                continue
                            flow_entries[crop_idx] = apply_flow_stage(
                                align_state, te["warped_fg"], te["warped_mask"], original_bg,
                                device=device, flow_scale=te.get("flow_scale", 1.0),
                                style=te.get("flow_style", "generic"),
                                g_base=te.get("g_base"), edit_mask=te.get("edit_mask"))
                            pbar.step(desc="Smart Merge · FLOW")
                        self._cache_stage(flow_key, flow_entries, "逐块光流 | per-crop flow")
                        stage_times["flow"] = stage_times.get("flow", 0.0) + (time.perf_counter() - _t0)
                    else:
                        flow_entries = tps_entries
                    stage_start = "after_flow"

                # 阶段 4: 二阶段逐块光流
                if stage_start == "after_flow":
                    if second_pass:
                        _t0 = time.perf_counter()
                        pass2_entries = [None] * B_crop
                        n_stage = end_idx - start_idx
                        _sm_note(f"[Smart Merge] ▶ 阶段 4/4 二阶段逐块光流: {n_stage} 个分块 | "
                                 f"stage 4/4 pass2 flow: {n_stage} crops")
                        for crop_idx in range(end_idx - 1, start_idx - 1, -1):
                            fe = flow_entries[crop_idx]
                            if fe is None:
                                continue
                            refresh_mask = (fe.get("flow_style", "generic") == "generic"
                                            and not warp_method)
                            pass2_entries[crop_idx] = apply_second_pass_stage(
                                align_state, fe["warped_fg"], fe["warped_mask"], original_bg,
                                device=device, flow_scale=fe.get("flow_scale", 1.0),
                                edit_mask=fe.get("edit_mask"), refresh_mask=refresh_mask)
                            pbar.step(desc="Smart Merge · PASS2")
                        self._cache_stage(pass2_key, pass2_entries, "二阶段逐块光流 | pass2 flow")
                        stage_times["pass2"] = stage_times.get("pass2", 0.0) + (time.perf_counter() - _t0)
                    else:
                        pass2_entries = flow_entries
                    stage_start = "done"

                final_entries = pass2_entries if second_pass else flow_entries

                _tc = time.perf_counter()
                for crop_idx in range(end_idx - 1, start_idx - 1, -1):
                    pbar.step(desc="Smart Merge · COMPOSE")
                    fe = (final_entries[crop_idx]
                          if final_entries is not None and crop_idx < len(final_entries) else None)
                    if fe is None:
                        if crop_idx not in skipped_tiles:
                            skipped_tiles.append(crop_idx)
                        continue

                    warped_fg = fe["warped_fg"].copy()
                    warped_mask = fe["warped_mask"].copy()
                    edit_mask = fe.get("edit_mask")
                    if edit_mask is not None and edit_mask.shape == original_bg.shape[:2]:
                        edit_mask = edit_mask.copy()
                    else:
                        edit_mask = _compute_edit_mask(
                            original_bg, warped_fg, valid_mask=warped_mask, device=device
                        )
                    align_state.last_edit_mask = edit_mask
                    align_state.last_residual_px = fe.get("residual")
                    # 命中缓存时跳过各阶段, 仍需还原最终 flow_scale 供整图精修使用
                    align_state.flow_scale = fe.get("flow_scale", align_state.flow_scale)

                    prepared_crops[crop_idx] = (warped_fg, warped_mask, edit_mask)
                    if color_protection:
                        thr = max(1.0, float(Color_p_threshold))
                        if abs(thr - 20.0) < 1e-6:
                            color_prot_masks[crop_idx] = edit_mask
                        else:
                            color_prot_masks[crop_idx] = _compute_edit_mask(
                                original_bg, warped_fg, d_lo=thr, d_hi=thr * 3.0,
                                valid_mask=warped_mask, device=device)

                _sm_note(f"[Smart Merge] ▶ 合成/校色: {len(prepared_crops)} 个分块 | "
                         f"compose: {len(prepared_crops)} crops")
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

                # 非 grid: 重叠区的过渡带由各块 mask bbox 相交反推
                compose_boxes = {}
                for _k, (_fg, _m, _em) in prepared_crops.items():
                    _x, _y, _w, _h = cv2.boundingRect((_m > 0.5).astype(np.uint8))
                    if _w > 0 and _h > 0:
                        compose_boxes[_k] = (_x, _y, _x + _w, _y + _h)
                _order = sorted(compose_boxes)
                band_by_idx = dict(zip(_order, _overlap_bands(
                    [compose_boxes[k] for k in _order], float(feather_kernel))))

                for crop_idx in range(end_idx - 1, start_idx - 1, -1):
                    if crop_idx not in prepared_crops:
                        continue
                    warped_fg, warped_mask, crop_edit_mask_full = prepared_crops[crop_idx]

                    h_bg, w_bg = img_bg.shape[:2]
                    bounds_mask_float = warped_mask.copy()
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
                    prot_full = color_prot_masks.get(crop_idx)
                    color_edit_mask = (prot_full[ymin:ymax, xmin:xmax]
                                       if prot_full is not None else None)
                    if global_lab_shift is not None:
                        crop_fg = _apply_global_lab_shift(
                            crop_fg, global_lab_shift, edit_mask=color_edit_mask,
                            device=device)

                    tile_info = (grid_tiles[crop_idx]
                                 if (use_grid_alpha and crop_idx < len(grid_tiles)) else None)
                    canvas_sides = (xmin <= 0, ymin <= 0, xmax >= w_bg, ymax >= h_bg)
                    pad_canvas_edges(crop_mask_float, canvas_sides)
                    weight_local = None
                    if tile_info is not None:
                        grid_overlap = int((split_grid or {}).get("overlap", 0))
                        weight_local = _grid_tile_weight(
                            tile_info, (xmin, ymin, xmax, ymax), crop_mask_float,
                            h_bg, w_bg, grid_overlap, feather_kernel)
                    else:
                        soft = make_edge_safe_soft_mask(
                            crop_mask_float, feather_kernel)
                        bands = band_by_idx.get(crop_idx)
                        weight_local = (_overlap_crossfade_weight(
                            soft, (xmin, ymin), bands) if bands is not None else soft)

                    # 羽化只进合成权重, 色彩匹配用整块 B / grid 的连续校正场。
                    crop_fg = _apply_color_match(
                        crop_fg, crop_bg, crop_mask_float, color_match,
                        feather_kernel, color_edit_mask,
                        grid_weight=tile_info is not None,
                        canvas_sides=canvas_sides, device=device)

                    if tile_info is not None:
                        layer = int(tile_info.get("layer") or 0)
                        is_bg = (tile_info.get("kind", "layer") in {"gap", "fallback", "unified"}
                                 or layer < 0)
                        compositor.add(crop_fg, weight_local, (xmin, ymin, xmax, ymax),
                                       None if is_bg else layer)
                    else:
                        compositor.add(crop_fg, weight_local,
                                       (xmin, ymin, xmax, ymax), None)

                    union_mask = np.maximum(union_mask, warped_mask)
                    if crop_edit_mask_full is not None and crop_edit_mask_full.shape == union_edit_mask.shape:
                        union_edit_mask = np.minimum(union_edit_mask, crop_edit_mask_full)

                if skipped_tiles:
                    _sm_note(f"[Smart Merge] 本次跳过 {len(skipped_tiles)} 个分块 {skipped_tiles}: "
                             f"对应的 AI 编辑不会出现在成品中, 这些区域保留原图 | "
                             f"tiles {skipped_tiles} not merged (original content kept)")

                img_result = compositor.finish(original_bg)
                img_bg = img_result.copy()
                stage_times["compose"] = stage_times.get("compose", 0.0) + (time.perf_counter() - _tc)

                if union_mask.max() > 0.5 and full_optical_flow:
                    polish_key = self._make_polish_key(
                        pass2_key, color_match, color_protection,
                        Color_p_threshold, feather_kernel, warp_smooth)
                    polished = None if force_recompute else self._polish_cache.get(polish_key)
                    if polished is not None:
                        img_result = polished.copy()
                        _sm_note("[Smart Merge] ✅ 命中整图光流精修缓存 | polish cache hit")
                    else:
                        _sm_note("[Smart Merge] ▶ 整图光流精修 | global polish")
                        _tp = time.perf_counter()
                        try:
                            polish_edit_mask = union_edit_mask if union_edit_mask.min() < 0.99 else None
                            img_result = global_flow_polish(
                                img_result, original_bg, union_mask, edit_mask=polish_edit_mask,
                                warp_smooth=warp_smooth,
                                flow_scale=align_state.flow_scale)
                            self._polish_cache[polish_key] = img_result.copy()
                        except Exception as e:
                            _sm_note(f"[Smart Merge] 整图精修失败: {e} | global polish failed")
                        stage_times["polish"] = stage_times.get("polish", 0.0) + (time.perf_counter() - _tp)
                elif union_mask.max() > 0.5:
                    _sm_log("[Smart Merge] 整图光流已关闭 (Full_Optical_Flow=off) | "
                            "global polish disabled")
                if polish_step:
                    pbar.step(desc="Smart Merge · POLISH")

                result_images.append(torch.from_numpy(img_result.astype(np.float32) / 255.0))

            except Exception as e:
                import traceback
                print(f"[Smart Merge 致命错误 | Fatal error] {e}")
                traceback.print_exc()
                result_images.append(items_orig[i])

        pbar.close()
        set_active_progress(None)

        if stage_times:
            _names = {"place": "定位", "tps": "TPS", "flow": "光流",
                      "pass2": "二阶段", "compose": "合成", "polish": "整图精修"}
            _parts = [f"{_names[k]} {stage_times[k]:.1f}s" for k in _names if k in stage_times]
            _prof = profile_snapshot()
            if _prof and "place" in stage_times:
                _sub = [f"{lab} {_prof[k]:.1f}s" for k, lab in
                        (("sift", "桥接"), ("photo", "光度"),
                         ("place_warp", "变形"), ("place_mask", "掩码")) if k in _prof]
                if _sub:
                    _parts[0] += " (" + " / ".join(_sub) + ")"
            _sm_log("[Smart Merge] 分阶段耗时: " + " / ".join(_parts) + " | stage timings")


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
