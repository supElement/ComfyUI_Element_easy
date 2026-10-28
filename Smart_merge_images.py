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

GRID_TYPE = "ELEMENT_TILE_GRID"

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
    
    DEBUG = False    # 调试日志开关

    @classmethod
    def _dlog(cls, *args, **kwargs):
        """调试日志: 仅当 DEBUG=True 时输出, 调用方式与 print 一致"""
        if cls.DEBUG:
            print(*args, **kwargs)

    _disk_model = None
    _lg_matcher_disk = None
    _cached_device = None
    # LoFTR 按类缓存: 每次执行都会新建节点实例, 放实例上会导致每次重载权重
    _loftr_model = None
    _loftr_cached_device = None

    _align_cache = {}
    _align_cache_order = []
    _align_cache_max = 4

    _sift_train_cache = {}          
    _sift_train_cache_order = []
    _sift_train_cache_max = 4

    # DISK 背景特征缓存: 多分块共用同一背景, 避免每块都重跑一次 DISK
    _disk_train_cache = {}
    _disk_train_cache_order = []
    _disk_train_cache_max = 4
    
    # 光流最大位移限幅(px)
    MAX_FLOW_PX = 15.0
    BRIDGE_MAX_MEDIAN_DIFF = 60  # 桥接光度一致性阈值(0-255灰度中位差), 超过视为桥接H不可靠
    
    # 光流降噪阈值(px)：位移差小于此值的突变会被视为计算毛刺并平滑掉，调大平滑越狠，调小保留的细节越多
    FLOW_DENOISE_PX = 1.5
    
    # ★ split_grid 融合策略:
    #   True  = grid fade×alpha 累加融合(旧行为)
    #   False = grid 仅提供 alpha 与对齐锚点, 融合走节点原生逻辑(推荐,
    #           与不接 grid 的融合行为完全一致)
    GRID_ACCUM_BLEND = True

    # Patch_based_color: 单通道校正上限(L, a, b)。色彩匹配只修低幅色偏,
    # 不负责重绘; 放开上限会把 AI 重绘的结构差异当色差涂抹成脏块。
    PATCH_COLOR_MAX_SHIFT = (12.0, 7.0, 7.0)
    # 每块至少这么多比例的可信(未编辑)像素才参与统计
    PATCH_COLOR_MIN_COVERAGE = 0.15
    # 块内色差离散度(MAD)超过该值视为内容不一致(而非色偏), 置信度指数衰减
    PATCH_COLOR_MAD_TAU = (8.0, 6.0, 6.0)
    # 已编辑内容内保留的校正比例: 采样已排除编辑像素, 但校正场仍会扩散进来。
    # 满强度施加会把 AI 有意画的颜色(红衬衫)拉向背景的灰蓝 → 灰斑。
    PATCH_COLOR_EDITED_SCALE = 0.25
    # 逐块对齐残差低于该值(px)时整图精修没有可修的位移, 直接跳过。
    POLISH_SKIP_RESID_PX = 0.8

    
    # 连接 split_grid 时, 没有桥接裁块 A 的情况下, 特征匹配校正允许偏离
    # grid 坐标的最大距离。grid 只是布局参考, 但 H 级别的放置误差通常是几像素
    # 到几十像素; 超过这个范围说明 B→BG 匹配本身不可信, 应回到 grid。
    GRID_ANCHOR_TOLERANCE = 0.12
    GRID_ANCHOR_MAX_PX = 64.0
    # 自动匹配被采纳所需的最少内点数(低于此值视为特征不足, 直接用 grid)
    GRID_AUTO_MIN_INLIERS = 30

    # ---- B→BG 模式(既无 split_grid 也无 original_crop_A) ----
    # 特征 H 的几何残差中位数超过该值即视为不可信, 触发模板匹配/布局先验候选竞争
    B2BG_TRUST_RESID = 2.5
    # 有像素证据(特征/模板)的候选, 残差超过该值即弃用
    B2BG_MAX_RESID = 12.0
    # 特征内点在 4x4 网格中至少要占据的格数。低于该值只提示, 是否采用交给残差竞争:
    # 低纹理块(大面积暗部/纯色)内点本来就集中, 硬性否决会把本可对齐的块丢掉。
    B2BG_MIN_SPREAD_CELLS = 4
    # 模板匹配放置的最低(边缘+亮度)归一化相关
    B2BG_MIN_MATCH_NCC = 0.22
    # DISK 失败时用 LoFTR 半稠密匹配兜底(低纹理/大面积改色块)
    B2BG_USE_LOFTR = True
    # 纯布局推断(无像素证据)只要求落在它所属的格子, 残差上限比实测候选宽
    B2BG_LAYOUT_MAX_RESID = 40.0
    # 布局放置还要过“结构相关”检查: 边缘图 NCC 太低说明这块内容和该位置无关
    # (例如完全不相干的分块), 直接贴上去只会毁图, 宁可不贴。
    B2BG_LAYOUT_MIN_NCC = 0.06
    # 本格的结构相关必须明显高于其它格子, 否则说明顺序/布局假设不成立
    B2BG_LAYOUT_NCC_MARGIN = 0.02
    
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
                        optical_flow, merge_mode, use_gpu, use_tps=True, split_grid=None):
        # optical_flow(DIS/Farneback) 只影响数值细节、use_gpu 只影响设备: 二者都不改变
        # 放置几何, 放进键里会让"只调光流模式"也整轮重算对齐。几何结果可跨二者复用。
        return "|".join([
            cls._items_fingerprint(original_items),
            cls._items_fingerprint(edited_items),
            cls._items_fingerprint(cropA_items),
            cls._grid_fingerprint(split_grid),
            str(bool(warp_method)),
            str(merge_mode),
            str(bool(use_tps)),
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
                "warp_smooth": ("FLOAT", {
                    "default": 1.0, "min": 0.0, "max": 4.0, "step": 0.05,
                    "tooltip": "整图精修光流场的平滑强度\n"
                               "--------------------------------------------------\n"
                               "Smoothing strength of the global-flow polish field"
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
                
                "split_grid": (GRID_TYPE, {
                    "tooltip": "可选: ElementTileSplit 的 grid 信息。连接后每个 crop 的 alpha/羽化处理改为 ElementTileMerge 的方式"
                               "(基于 fade_top/bottom/left/right 线性渐变 + 圆角 mask 高斯羽化, 逐 tile 加权累加再平均)。\n"
                               "色彩匹配、TPS、光流对齐逻辑保持不变。\n"
                               "--------------------------------------------------\n"
                               "Optional: grid from ElementTileSplit. When connected, per-tile alpha/feathering follows "
                               "ElementTileMerge (fade-based linear ramp + rounded-corner gaussian feather, accumulated "
                               "weighted average). Color match / TPS / optical-flow alignment remain unchanged."
                }),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("Merged_Image",)
    FUNCTION = "smart_merge"
    CATEGORY = "Element_easy/image"

    # 声明接受 List 输入, 阻止 ComfyUI 对 List 输入做隐式"逐项展开"
    INPUT_IS_LIST = True

    # ============================================================
    # ElementTileMerge 风格的 alpha / 羽化权重（split_grid 连接时启用）
    # ============================================================
    
    @staticmethod
    def _tile_weight_local(tile_info, bbox, feather_frac):
        """精确复刻 ElementTileMerge 的 _tile_weight (nodes_merge.py L293 调用)。
        fade 值先被 feather_frac(∈[0,1]) 缩放，再做线性渐变。
        返回 (bh, bw, 1) numpy float32。"""
        xmin, ymin, xmax, ymax = bbox
        bh, bw = ymax - ymin, xmax - xmin
    
        tx = int(tile_info.get("x", 0))
        ty = int(tile_info.get("y", 0))
        tw = int(tile_info.get("width", 1))
        th = int(tile_info.get("height", 1))
    
        ffr = float(max(0.0, min(1.0, feather_frac)))
        ft = float(tile_info.get("fade_top", 0))    * ffr
        fb = float(tile_info.get("fade_bottom", 0)) * ffr
        fl = float(tile_info.get("fade_left", 0))   * ffr
        fr = float(tile_info.get("fade_right", 0))  * ffr
    
        weight = np.ones((bh, bw), dtype=np.float32)
        ys = np.arange(ymin, ymax, dtype=np.float32)[:, None] + 0.5
        xs = np.arange(xmin, xmax, dtype=np.float32)[None, :] + 0.5
    
        if ft > 0:
            weight = np.minimum(weight, np.clip((ys - ty) / ft, 0.0, 1.0))
        if fb > 0:
            weight = np.minimum(weight, np.clip((ty + th - ys) / fb, 0.0, 1.0))
        if fl > 0:
            weight = np.minimum(weight, np.clip((xs - tx) / fl, 0.0, 1.0))
        if fr > 0:
            weight = np.minimum(weight, np.clip((tx + tw - xs) / fr, 0.0, 1.0))
    
        return weight[:, :, None]
    
    @staticmethod
    def _feather_tile_mask_like_etm(crop_mask_float, bbox, h_bg, w_bg,
                                     fade_t, fade_b, fade_l, fade_r,
                                     overlap, feather_frac):
        """精确复刻 ElementTileMerge 的 tile_mask 羽化 (nodes_merge.py L321-350)：
          1) 贴画布边侧 pad replicate (深度=overlap)
          2) 高斯模糊 (sigma = feather_px / 3)
          3) 切回 bbox 尺寸
        feather_px = max_fade * feather_frac if max_fade>0 else overlap * feather_frac
        返回 (h_crop, w_crop, 1) float32。"""
        xmin, ymin, xmax, ymax = bbox
        h_crop, w_crop = ymax - ymin, xmax - xmin
    
        max_fade = max(float(fade_t), float(fade_b), float(fade_l), float(fade_r))
        if max_fade > 0:
            feather_px = max(1.0, max_fade * feather_frac)
        else:
            feather_px = max(1.0, float(overlap) * feather_frac)
    
        # 贴画布边 pad（同 nodes_merge.py L325-328: x<=0 / x+w>=work_w 等条件）
        pad_l = int(overlap) if xmin <= 0    else 0
        pad_r = int(overlap) if xmax >= w_bg else 0
        pad_t = int(overlap) if ymin <= 0    else 0
        pad_b = int(overlap) if ymax >= h_bg else 0
    
        m = crop_mask_float.astype(np.float32)
        if pad_l or pad_r or pad_t or pad_b:
            m = cv2.copyMakeBorder(m, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REPLICATE)
    
        if feather_px > 1.0:
            sigma = feather_px / 3.0
            m = cv2.GaussianBlur(m, (0, 0), sigma)
    
        if pad_l or pad_r or pad_t or pad_b:
            m = m[pad_t:pad_t + h_crop, pad_l:pad_l + w_crop]
    
        return m[:, :, np.newaxis]
    

    @staticmethod
    def _tile_corner_mask_in_bbox(tile_info, bbox, feather_px):
        """在 bbox 内生成圆角硬 mask + 高斯羽化 (bh, bw, 1)。
        对应 ElementTileMerge._generate_tile_mask + _gaussian_blur_isotropic。"""
        xmin, ymin, xmax, ymax = bbox
        bh, bw = ymax - ymin, xmax - xmin
    
        rtl = int(tile_info.get("radius_tl", 0))
        rtr = int(tile_info.get("radius_tr", 0))
        rbl = int(tile_info.get("radius_bl", 0))
        rbr = int(tile_info.get("radius_br", 0))
    
        if rtl == 0 and rtr == 0 and rbl == 0 and rbr == 0:
            return None
    
        tx = int(tile_info.get("x", 0))
        ty = int(tile_info.get("y", 0))
        tw = int(tile_info.get("width", 1))
        th = int(tile_info.get("height", 1))
    
        ys = np.arange(ymin, ymax, dtype=np.float32)[:, None] + 0.5
        xs = np.arange(xmin, xmax, dtype=np.float32)[None, :] + 0.5
        ly = ys - ty
        lx = xs - tx
    
        mask = np.ones((bh, bw), dtype=bool)
        if rtl > 0:
            m = (lx < rtl) & (ly < rtl)
            dist = np.sqrt((lx - rtl) ** 2 + (ly - rtl) ** 2)
            mask &= ~(m & (dist > rtl))
        if rtr > 0:
            m = (lx > tw - rtr) & (ly < rtr)
            dist = np.sqrt((lx - (tw - rtr)) ** 2 + (ly - rtr) ** 2)
            mask &= ~(m & (dist > rtr))
        if rbl > 0:
            m = (lx < rbl) & (ly > th - rbl)
            dist = np.sqrt((lx - rbl) ** 2 + (ly - (th - rbl)) ** 2)
            mask &= ~(m & (dist > rbl))
        if rbr > 0:
            m = (lx > tw - rbr) & (ly > th - rbr)
            dist = np.sqrt((lx - (tw - rbr)) ** 2 + (ly - (th - rbr)) ** 2)
            mask &= ~(m & (dist > rbr))
    
        mask = mask.astype(np.float32)
    
        if feather_px > 1.0:
            sigma = max(0.5, feather_px / 3.0)
            mask = cv2.GaussianBlur(mask, (0, 0), sigma)
    
        return mask[:, :, None]


    @staticmethod
    def _color_sample_mask(mask_float, edit_mask=None):
        base = np.clip(mask_float.astype(np.float32), 0.0, 1.0)
        if edit_mask is None:
            return base
        if edit_mask.shape != base.shape:
            return None
        reliable = base * (edit_mask > 0.5).astype(np.float32)
        if float((reliable > 0.5).sum()) < 100.0:
            return None
        return reliable

    def edge_weighted_color_sync(self, fg, bg, mask_float, edit_mask=None):
        """在未编辑参考区域估计 RGB 均值方差，再把同一校正应用到整个裁块。"""
        sample_mask = self._color_sample_mask(mask_float, edit_mask)
        if sample_mask is None or sample_mask.max() <= 0.01:
            return fg
        mask_float = sample_mask

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

    @staticmethod
    def _fast_blur(img, sigma):
        """大 sigma 高斯: 先降采样再模糊、后上采样。
        色彩偏置/羽化场本身只含低频信息, 与全分辨率高斯差异 <0.1 LAB,
        代价约为 1/ds²。"""
        sigma = float(max(sigma, 0.0))
        if sigma <= 6.0:
            return cv2.GaussianBlur(img, (0, 0), sigma)
        h, w = img.shape[:2]
        ds = int(min(4, max(2, round(sigma / 4.0))))
        sw, sh = max(8, w // ds), max(8, h // ds)
        small = cv2.resize(img, (sw, sh), interpolation=cv2.INTER_AREA)
        small = cv2.GaussianBlur(small, (0, 0), max(0.5, sigma / ds))
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    def _edited_scale(self, edit_mask, shape, sigma=8.0):
        """未编辑置信度 → 校正强度系数: 未编辑处 1, 已编辑处 PATCH_COLOR_EDITED_SCALE。
        编辑区内的校正估计没有内容对应关系, 满强度施加会把 AI 有意的颜色拉向背景。"""
        if edit_mask is None:
            return None
        em = np.clip(np.asarray(edit_mask, dtype=np.float32), 0.0, 1.0)
        if em.shape != shape[:2]:
            em = cv2.resize(em, (shape[1], shape[0]), interpolation=cv2.INTER_LINEAR)
        em = self._fast_blur(em, sigma)
        base = float(self.PATCH_COLOR_EDITED_SCALE)
        return base + (1.0 - base) * em

    @staticmethod
    def _fast_median_blur(img8, ksize):
        """大核中值: 半分辨率执行, 等效半径不变。用于低频色偏估计, 不保留细节。"""
        ksize = int(ksize) | 1
        if ksize <= 5:
            return cv2.medianBlur(img8, ksize)
        h, w = img8.shape[:2]
        sw, sh = max(8, w // 2), max(8, h // 2)
        small = cv2.resize(img8, (sw, sh), interpolation=cv2.INTER_AREA)
        k = max(3, (ksize // 2) | 1)
        k = min(k, (min(sh, sw) - 1) | 1)
        small = cv2.medianBlur(small, k)
        return cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)

    def patch_based_color_sync(self, fg, bg, mask_float, patch_size=64, overlap=32,
                               edit_mask=None, apply_mask=None):
        """分块 LAB 色差同步: 低频色偏估计 + 鲁棒统计 + 随羽化衰减施加。

        AI 重绘会把内容(而不只是色调)改掉, 逐块直接对 bg-fg 求均值会把内容差
        当成色偏, 产生大块脏斑。因此:
          1) 先在块尺度低通 bg/fg, 只保留低频色偏, 内容/边缘差异被抹平;
          2) 每块只用"未编辑可信像素"的中位数色差, 并按离散度(MAD)置信度加权,
             内容不一致的块自动降权;
          3) 校正限幅 + 二次低通, 无可信样本的块只继承邻域低频趋势;
          4) 用 apply_mask(羽化权重)施加, 使校正在分块边界淡出。"""
        h, w = fg.shape[:2]
        sample_mask = self._color_sample_mask(mask_float, edit_mask)
        if sample_mask is None or float(sample_mask.max()) <= 0.01:
            return fg
        sample_bool = sample_mask > 0.5
        mask_bool = mask_float > 0.5
        if int(mask_bool.sum()) < 100 or int(sample_bool.sum()) < 100:
            return fg

        patch_size = max(16, min(int(patch_size), h, w))
        overlap = max(0, min(int(overlap), patch_size - 1))
        step = max(1, patch_size - overlap)

        lab_fg = cv2.cvtColor(fg, cv2.COLOR_RGB2LAB).astype(np.float32)
        lab_bg = cv2.cvtColor(bg, cv2.COLOR_RGB2LAB).astype(np.float32)
        lp_sigma = max(2.0, patch_size / 4.0)
        diff = (self._fast_blur(lab_bg, lp_sigma)
                - self._fast_blur(lab_fg, lp_sigma))

        y_positions = list(range(0, h - patch_size + 1, step))
        x_positions = list(range(0, w - patch_size + 1, step))
        if not y_positions or y_positions[-1] + patch_size < h:
            y_positions.append(max(0, h - patch_size))
        if not x_positions or x_positions[-1] + patch_size < w:
            x_positions.append(max(0, w - patch_size))
        y_positions = sorted(set(y_positions))
        x_positions = sorted(set(x_positions))

        hann = (np.hanning(patch_size)[:, None] * np.hanning(patch_size)[None, :]).astype(np.float32)
        weight_map = np.zeros((h, w), dtype=np.float32)
        correction_sum = np.zeros((h, w, 3), dtype=np.float32)
        max_shift = np.asarray(self.PATCH_COLOR_MAX_SHIFT, dtype=np.float32)
        tau = self.PATCH_COLOR_MAD_TAU
        min_cov = float(self.PATCH_COLOR_MIN_COVERAGE)
        valid_patches = 0

        for y in y_positions:
            for x in x_positions:
                y2, x2 = y + patch_size, x + patch_size
                patch_sel = sample_bool[y:y2, x:x2]
                if float(patch_sel.mean()) < min_cov:
                    continue
                # diff 已被 sigma≈patch/4 低通, 隔点采样不改变中位数/MAD 统计
                sel_small = patch_sel[::2, ::2]
                if int(sel_small.sum()) >= 30:
                    diff_patch = diff[y:y2:2, x:x2:2]
                    sel = sel_small
                else:
                    diff_patch = diff[y:y2, x:x2]
                    sel = patch_sel
                patch_correction = np.zeros(3, dtype=np.float32)
                conf = 1.0
                ok = True
                for c in range(3):
                    vals = diff_patch[:, :, c][sel]
                    if vals.size < 30:
                        ok = False
                        break
                    med = float(np.median(vals))
                    mad = float(np.median(np.abs(vals - med)))
                    patch_correction[c] = med
                    conf = min(conf, float(np.exp(-(mad / tau[c]) ** 2)))
                if not ok or conf < 0.02:
                    continue

                patch_weight = hann * patch_sel.astype(np.float32) * conf
                correction_sum[y:y2, x:x2] += patch_correction[None, None, :] * patch_weight[:, :, None]
                weight_map[y:y2, x:x2] += patch_weight
                valid_patches += 1

        if valid_patches == 0:
            self._dlog("[Smart Merge] Patch 色彩: 无可信分块, 跳过校正 | no reliable patch, color sync skipped")
            return fg

        valid = weight_map > 1e-8
        correction_field = correction_sum / np.maximum(weight_map[:, :, None], 1e-8)

        # 无可信样本的区域(如整块被 AI 重绘)只继承邻域低频校正趋势, 不引入内容
        fill_sigma = max(4.0, patch_size / 2.0)
        for c in range(3):
            num = self._fast_blur(correction_field[:, :, c] * valid, fill_sigma)
            den = self._fast_blur(valid.astype(np.float32), fill_sigma)
            filled = np.where(den > 1e-6, num / np.maximum(den, 1e-6), 0.0)
            correction_field[:, :, c] = np.where(valid, correction_field[:, :, c], filled)

        correction_field = self._fast_blur(correction_field, max(2.0, patch_size / 3.0))
        correction_field = np.clip(correction_field, -max_shift, max_shift)

        apply_w = apply_mask if apply_mask is not None else mask_float
        apply_w = np.clip(np.asarray(apply_w, dtype=np.float32), 0.0, 1.0)
        if apply_w.shape != mask_bool.shape:
            apply_w = mask_bool.astype(np.float32)
        edited_scale = self._edited_scale(edit_mask, fg.shape, sigma=max(4.0, patch_size / 4.0))
        if edited_scale is not None:
            apply_w = apply_w * edited_scale
        peak = float(apply_w.max())
        if peak > 1e-6:
            apply_w = apply_w / peak
        correction_field *= apply_w[:, :, None]

        self._dlog(f"[Smart Merge] Patch 色彩: {valid_patches} 有效块, "
                   f"L中位 {float(np.median(correction_field[:, :, 0])):.1f}, "
                   f"限幅 ±{max_shift.tolist()} | {valid_patches} valid patches")
        result = np.clip(lab_fg + correction_field, 0, 255).astype(np.uint8)
        return cv2.cvtColor(result, cv2.COLOR_LAB2RGB)

    def boundary_aware_color_sync(self, fg, bg, mask_float, band_width=21, strength=1.0, edit_mask=None):
        h, w = fg.shape[:2]
        sample_mask = self._color_sample_mask(mask_float, edit_mask)
        if sample_mask is None:
            return fg
        mask_8u = (np.clip(mask_float, 0, 1) * 255).astype(np.uint8)
        if np.sum(mask_8u > 128) < 100:
            return fg

        lab_fg = cv2.cvtColor(fg, cv2.COLOR_RGB2LAB).astype(np.float32)
        lab_bg = cv2.cvtColor(bg, cv2.COLOR_RGB2LAB).astype(np.float32)

        med_size = max(7, (band_width // 2) | 1)
        med_size = min(med_size, h if h % 2 else h - 1, w if w % 2 else w - 1)
        if med_size >= 3:
            lab_fg_med = self._fast_median_blur(
                np.clip(lab_fg, 0, 255).astype(np.uint8), med_size).astype(np.float32)
            lab_bg_med = self._fast_median_blur(
                np.clip(lab_bg, 0, 255).astype(np.uint8), med_size).astype(np.float32)
        else:
            lab_fg_med = lab_fg
            lab_bg_med = lab_bg

        raw_diff = lab_bg_med - lab_fg_med
        mask_3d = (sample_mask > 0.5).astype(np.float32)[:, :, np.newaxis]
        masked_diff = raw_diff * mask_3d

        ksz = min(max(31, (band_width * 3) | 1), 151)
        gsigma = max(2.0, 0.15 * ksz)
        correction_field = np.zeros_like(lab_fg)

        # 三通道同核同 sigma: 各自模糊与合并成一次多通道调用等价
        diff_smooth_all = self._fast_blur(masked_diff, gsigma)
        diff_sqr_all = self._fast_blur(masked_diff ** 2, gsigma)
        for c in range(3):
            diff_ch = masked_diff[:, :, c]
            diff_smooth = diff_smooth_all[:, :, c]
            diff_sqr_smooth = diff_sqr_all[:, :, c]
            variance = diff_sqr_smooth - diff_smooth ** 2
            variance = np.maximum(variance, 0)

            pos = variance[::4, ::4]
            pos = pos[pos > 0]
            denom = np.median(pos) if pos.size > 0 else 1.0
            reliability = np.exp(-variance / (denom + 1e-6))
            reliability = reliability * (sample_mask > 0.5).astype(np.float32)

            weighted_num = self._fast_blur(diff_ch * reliability, gsigma)
            weighted_den = self._fast_blur(reliability, gsigma) + 1e-6
            correction_field[:, :, c] = weighted_num / weighted_den

        dist_from_boundary = cv2.distanceTransform((mask_float > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
        decay = 0.4 + 0.6 * np.exp(-dist_from_boundary / max(float(band_width), 1.0))
        decay_3d = decay[:, :, np.newaxis]

        # 编辑区内校正估计没有内容对应, 只保留小比例, 避免把 AI 改色拉回背景色
        edited_scale = self._edited_scale(edit_mask, fg.shape, sigma=max(4.0, band_width / 4.0))
        if edited_scale is not None:
            correction_field *= edited_scale[:, :, None]

        strength_vec = np.array([0.6, 1.0, 1.0]) * strength
        soft_mask = self._fast_blur(mask_float.astype(np.float32), max(2.0, 0.15 * (band_width | 1)))
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

        # A→BG 单应性体检（透视/形状/凸性/面积/越界）
        if not SmartMergeImages._homography_is_sane(H, h_q, w_q, h_t, w_t):
            print("[Smart Merge] A→BG 单应性未通过体检(透视/形状/凸性), 弃用桥接 | A→BG homography failed sanity check, discarding bridge")
            return None
        return H


    @staticmethod
    def _fill_flow_from_reliable(flow, confidence, kernel_size=41):
        """低置信区域只继承邻域低频位移，不直接用颜色差驱动变形。"""
        confidence = np.clip(confidence.astype(np.float32), 0.0, 1.0)
        if float(confidence.max()) < 0.05:
            return np.zeros_like(flow)
        den = cv2.GaussianBlur(confidence, (kernel_size, kernel_size), 0)
        filled = np.zeros_like(flow)
        for c in range(2):
            num = cv2.GaussianBlur(flow[:, :, c] * confidence, (kernel_size, kernel_size), 0)
            filled[:, :, c] = num / np.maximum(den, 1e-6)
        fill_weight = np.clip((0.95 - confidence) / 0.95, 0.0, 1.0)
        filled[den <= 1e-6] = 0.0
        return flow * (1.0 - fill_weight[:, :, None]) + filled * fill_weight[:, :, None]

    def refine_with_optical_flow(self, warped_fg, warped_mask, train_img, optical_flow=False,
                                 device="cpu", max_flow_px=None, edit_mask=None):
        """optical_flow: False=Farneback, True=DIS (布尔开关)
        edit_mask 保留以兼容调用方, 但不再参与逐块光流门控:
        逐块光流只做几何校正, 改色区内部的畸变同样需要修正。
        ★ 只在掩码 bbox(+边距) 内计算光流。"""
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
        gray_warped = self._to_flow_luma(sub_fg)
        gray_target = self._to_flow_luma(sub_bg)

        # ★ 升级为与整图精修一致的"改色免疫"预处理:
        #   CLAHE 恢复改色区亮度结构 → 直方图匹配消除分布差 → 预平滑保宏观几何
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gray_warped = clahe.apply(gray_warped)
        gray_target = clahe.apply(gray_target)
        gray_warped = self._match_histogram(gray_warped, gray_target)
        # ★ 逐块路径同样做虚焦均衡(编辑块通常比原图实)
        gray_warped, _ = self._defocus_equalize(gray_warped, gray_target, sub_mask)
        gray_warped = cv2.GaussianBlur(gray_warped, (11, 11), 0)
        gray_target = cv2.GaussianBlur(gray_target, (11, 11), 0)

  
        sub_edit = edit_mask[y0:y1, x0:x1] if edit_mask is not None else None  
        if optical_flow:
            try:
                r_fg, r_mask = self._refine_with_dis(gray_warped, gray_target, sub_fg, sub_mask, sub_bg,
                                                max_flow_px=max_flow_px, edit_mask=sub_edit)
            except Exception as e:
                print(f"[Smart Merge] DIS 不可用 ({e}), 降级 Farneback | DIS unavailable, falling back to Farneback")
                r_fg, r_mask = self._refine_with_farneback(gray_warped, gray_target, sub_fg, sub_mask, sub_bg,
                                                      max_flow_px=max_flow_px, edit_mask=sub_edit)
        else:
            r_fg, r_mask = self._refine_with_farneback(gray_warped, gray_target, sub_fg, sub_mask, sub_bg,
                                                  max_flow_px=max_flow_px, edit_mask=sub_edit)
        out_fg = warped_fg.copy()
        out_mask = warped_mask.copy()
        out_fg[y0:y1, x0:x1] = r_fg
        out_mask[y0:y1, x0:x1] = r_mask
        return out_fg, out_mask


    def _refine_with_dis(self, gray_warped, gray_target, warped_fg, warped_mask, train_img,
                         max_flow_px=15.0, edit_mask=None):
        h_t, w_t = train_img.shape[:2]
        try:
            dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        except AttributeError:
            dis = cv2.DISOpticalFlow.create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)

        flow = dis.calc(gray_warped, gray_target, None).astype(np.float32)
        flow_b = dis.calc(gray_target, gray_warped, None).astype(np.float32)
        flow[:, :, 0] = cv2.medianBlur(flow[:, :, 0], 3)
        flow[:, :, 1] = cv2.medianBlur(flow[:, :, 1], 3)

        grid_x, grid_y = np.meshgrid(np.arange(w_t), np.arange(h_t))
        map_x_fwd = (grid_x + flow[:, :, 0]).astype(np.float32)
        map_y_fwd = (grid_y + flow[:, :, 1]).astype(np.float32)
        bwd_at_fwd = cv2.remap(flow_b, map_x_fwd, map_y_fwd,
                               interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        consistency = np.clip((3.0 - np.linalg.norm(flow + bwd_at_fwd, axis=2)) / 1.5, 0.0, 1.0)
        inner_mask = cv2.erode((warped_mask > 0.5).astype(np.uint8), np.ones((5, 5), np.uint8))
        reliability = inner_mask.astype(np.float32) * consistency
        # 逐块光流是几何阶段: 只用前后向一致性, 不读改色掩码。
        # 实测改色区内部的畸变同样需要校正, 一旦用改色置信度门控就会整块冻结。

        flow_mag = np.linalg.norm(flow, axis=2)
        scale_factor = np.minimum(flow_mag, float(max_flow_px)) / (flow_mag + 1e-8)
        flow *= (scale_factor * reliability)[:, :, None]
        flow[:, :, 0] = cv2.bilateralFilter(flow[:, :, 0], 7, self.FLOW_DENOISE_PX, 7)
        flow[:, :, 1] = cv2.bilateralFilter(flow[:, :, 1], 7, self.FLOW_DENOISE_PX, 7)
        flow = self._fill_flow_from_reliable(flow, reliability)

        map_x = (grid_x - flow[:, :, 0]).astype(np.float32)
        map_y = (grid_y - flow[:, :, 1]).astype(np.float32)
        refined_fg = cv2.remap(warped_fg, map_x, map_y,
                               interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
        refined_mask = cv2.remap(warped_mask, map_x, map_y,
                                 interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        return refined_fg, refined_mask

    def _refine_with_farneback(self, gray_warped, gray_target, warped_fg, warped_mask, train_img,
                               max_flow_px=15.0, edit_mask=None):
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
        consistency_mask = np.clip((3.0 - consistency_err) / 1.5, 0.0, 1.0).astype(np.float32)

        # ★ 满血门控：只依赖一致性，废除所有锐度或纹理惩罚
        reliability = inner_mask_f * consistency_mask
        reliability = np.clip(reliability, 0.0, 1.0)

        flow = flow_fwd.copy()
        max_flow = float(max_flow_px)
        flow_mag = np.linalg.norm(flow, axis=2)
        scale_factor = np.minimum(flow_mag, max_flow) / (flow_mag + 1e-8)
        flow[:, :, 0] *= scale_factor
        flow[:, :, 1] *= scale_factor
        
        # 乘上可靠性
        flow[:, :, 0] *= reliability
        flow[:, :, 1] *= reliability

        # 双边滤波保边平滑
        flow[:, :, 0] = cv2.bilateralFilter(flow[:, :, 0], 7, self.FLOW_DENOISE_PX, 7)
        flow[:, :, 1] = cv2.bilateralFilter(flow[:, :, 1], 7, self.FLOW_DENOISE_PX, 7)
        flow = self._fill_flow_from_reliable(flow, reliability)

        map_x = (grid_x - flow[:, :, 0]).astype(np.float32)
        map_y = (grid_y - flow[:, :, 1]).astype(np.float32)
        refined_fg = cv2.remap(warped_fg, map_x, map_y,
                               interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
        refined_mask = cv2.remap(warped_mask, map_x, map_y,
                                 interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        return refined_fg, refined_mask

    @staticmethod
    def _to_flow_luma(img):
        """光流输入：提取 Lab 的 L 通道（亮度），配合直方图匹配抵抗偏色。"""
        return cv2.cvtColor(img, cv2.COLOR_RGB2LAB)[:, :, 0]
    
    @staticmethod
    def _match_histogram(src, ref):
        """把 src 的直方图映射到 ref 的分布。用于消除偏色/改色对光流的结构破坏。"""
        src_vals, src_idx, src_cnt = np.unique(src.ravel(), return_inverse=True, return_counts=True)
        ref_vals, ref_cnt = np.unique(ref.ravel(), return_counts=True)
        src_q = np.cumsum(src_cnt).astype(np.float64); src_q /= src_q[-1]
        ref_q = np.cumsum(ref_cnt).astype(np.float64); ref_q /= ref_q[-1]
        interp = np.interp(src_q, ref_q, ref_vals)
        return interp[src_idx].reshape(src.shape).astype(np.uint8)

    @staticmethod
    def _match_histogram_masked(src, ref, mask):
        """★ 新增: 仅统计 mask 区域内的直方图并匹配。
        局部改色场景(白杯→红杯)下, 全局直方图会被大面积背景主导,
        只有统计编辑区内部像素, 才能精准恢复改色区的亮度结构。"""
        m = mask > 0.5
        if int(m.sum()) < 1000:
            return SmartMergeImages._match_histogram(src, ref)
        src_vals, src_cnt = np.unique(src[m], return_counts=True)
        ref_vals, ref_cnt = np.unique(ref[m], return_counts=True)
        src_q = np.cumsum(src_cnt).astype(np.float64); src_q /= src_q[-1]
        ref_q = np.cumsum(ref_cnt).astype(np.float64); ref_q /= ref_q[-1]
        interp = np.interp(src_q, ref_q, ref_vals)
        lut = np.arange(256, dtype=np.uint8)
        lut[src_vals.astype(np.int64)] = np.clip(np.round(interp), 0, 255).astype(np.uint8)
        return cv2.LUT(src, lut)

    @staticmethod
    def _brighten_for_match(img):
        """匹配前的曲线提亮: 分位拉伸 + gamma。只影响特征匹配, 不参与合成。

        大面积暗色重绘(暗衣服/暗背景)在 8bit 图里局部对比极低, 特征检测器
        几乎没有可用的采样点; 先把亮度曲线拉开再匹配一次, 往往能恢复结构。
        输入本身平坦(完全没有结构)时返回 None, 表示提亮也无济于事。
        """
        g = img.astype(np.float32).mean(axis=2)
        lo = float(np.percentile(g, 1.0))
        hi = float(np.percentile(g, 99.0))
        if hi - lo < 2.0:
            return None
        f = np.clip((img.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0.0, 255.0)
        if float(f.mean()) < 96.0:
            f = 255.0 * np.power(np.clip(f, 0.0, 255.0) / 255.0, 0.65)
        return np.clip(f, 0.0, 255.0).astype(np.uint8)

    @staticmethod
    def _match_histogram_rgb(src, ref):
        """逐通道直方图映射(src→ref)。只用于特征匹配前, 让改色/偏色分块的
        描述子分布靠近背景; 不参与最终像素合成。用 256 级 LUT 实现, 开销可忽略。"""
        out = np.empty_like(src)
        vals = np.arange(256, dtype=np.float64)
        for c in range(3):
            hs = np.bincount(np.ascontiguousarray(src[..., c]).ravel(), minlength=256).astype(np.float64)
            hr = np.bincount(np.ascontiguousarray(ref[..., c]).ravel(), minlength=256).astype(np.float64)
            qs = np.cumsum(hs); qs /= max(qs[-1], 1.0)
            qr = np.cumsum(hr); qr /= max(qr[-1], 1.0)
            lut = np.clip(np.round(np.interp(qs, qr, vals)), 0, 255).astype(np.uint8)
            out[..., c] = lut[src[..., c]]
        return out

    @staticmethod
    def _defocus_equalize(sharp_l, ref_l, mask):
        """★ 新增: 虚焦→实焦均衡。AI 重采样常把虚焦区变实焦, 两边边缘宽度
        (梯度尺度)严重失配, 光流在轮廓处产生【空间平滑的系统性位移】,
        能骗过一致性门控和低通滤波。本方法把较实的一侧模糊到与参考侧
        锐度相当, 只作用于光流输入, 不影响合成像素。
        返回 (均衡后图像, 实际使用的sigma)。编辑图不比原图实时返回 sigma=0。"""
        m = mask > 0.5
        if int(m.sum()) < 1000:
            return sharp_l, 0.0
        v_sharp = float(cv2.Laplacian(sharp_l, cv2.CV_32F)[m].var())
        v_ref = float(cv2.Laplacian(ref_l, cv2.CV_32F)[m].var())
        # 编辑图没有明显更实(普通改色/普通重绘) → 不干预, 保持原行为
        if v_ref < 1.0 or v_sharp <= v_ref * 1.15:
            return sharp_l, 0.0
        best_sigma, best_diff = 0.0, abs(np.log(v_sharp + 1.0) - np.log(v_ref + 1.0))
        for s in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0):
            cand = cv2.GaussianBlur(sharp_l, (0, 0), s)
            v = float(cv2.Laplacian(cand, cv2.CV_32F)[m].var())
            d = abs(np.log(v + 1.0) - np.log(v_ref + 1.0))
            if d < best_diff:
                best_sigma, best_diff = s, d
        if best_sigma <= 0.0:
            return sharp_l, 0.0
        SmartMergeImages._dlog(
            f"[Smart Merge] 虚焦→实焦均衡: 编辑图锐度{v_sharp:.0f} → 原图{v_ref:.0f}, "
            f"sigma={best_sigma} | defocus equalized (flow input only)")
        return cv2.GaussianBlur(sharp_l, (0, 0), best_sigma), best_sigma


    @staticmethod
    def _compute_edit_mask(warped_A, warped_B, d_lo=20.0, d_hi=60.0, valid_mask=None):
        """返回未编辑置信度；强色度和强亮度改变都会降低置信度。"""
        la = cv2.cvtColor(warped_A, cv2.COLOR_RGB2LAB).astype(np.float32)
        lb = cv2.cvtColor(warped_B, cv2.COLOR_RGB2LAB).astype(np.float32)

        d_ab = np.linalg.norm(la[:, :, 1:3] - lb[:, :, 1:3], axis=2)
        d_l = np.abs(la[:, :, 0] - lb[:, :, 0])

        def _confidence(diff, lo, hi):
            d_u8 = np.clip(diff, 0, 255).astype(np.uint8)
            h, w = d_u8.shape
            median_size = min(15, h if h % 2 else h - 1, w if w % 2 else w - 1)
            if median_size >= 3:
                d_u8 = cv2.medianBlur(d_u8, median_size)
            d = SmartMergeImages._fast_blur(d_u8.astype(np.float32), 6.2)
            return np.clip((hi - d) / max(hi - lo, 1e-6), 0.0, 1.0)

        chroma_conf = _confidence(d_ab, d_lo, d_hi)
        luma_conf = _confidence(d_l, 25.0, 60.0)
        confidence = np.minimum(chroma_conf, luma_conf).astype(np.float32)
        if valid_mask is not None and valid_mask.shape == confidence.shape:
            valid = np.clip(valid_mask.astype(np.float32), 0.0, 1.0)
            confidence = confidence * valid + (1.0 - valid)
        return confidence


    @staticmethod
    def _homography_is_sane(H, h_q, w_q, h_t, w_t,
                            max_persp: float = 0.35,
                            min_edge_ratio: float = 0.30,
                            min_area_ratio: float = 0.15,
                            max_area_ratio: float = 6.0):
        """校验单应性矩阵是否退化/镜像/过度形变/透视过强/四边形非凸。
        max_persp: 图像四角 w 值的极差上限 (0.35 = 边缘 w 偏离中心 35%，已属明显透视)"""
        if H is None:
            return False
        H = np.asarray(H, dtype=np.float64)
        if not np.all(np.isfinite(H)):
            return False
        det = np.linalg.det(H[:2, :2])
        if abs(det) < 1e-8 or det < 0:
            return False
    
        corners = np.array([[0, 0], [w_q, 0], [w_q, h_q], [0, h_q]], dtype=np.float64)
        ones = np.ones((4, 1))
        pts = np.hstack([corners, ones]) @ H.T
        wcol = pts[:, 2]
        if np.any(np.abs(wcol) < 1e-9):
            return False
    
        # ---- 1) 透视门限：四角 w 值极差 ----
        #   归一化到 H[2,2]=1 后，w = Hn[2,0]*x + Hn[2,1]*y + 1
        absH22 = abs(H[2, 2])
        if absH22 > 1e-12:
            Hn = H / H[2, 2]
            w_norm = Hn[2, 0] * corners[:, 0] + Hn[2, 1] * corners[:, 1] + 1.0
            if float(w_norm.max() - w_norm.min()) > max_persp:
                return False
            if float(w_norm.min()) <= 0.2:   
                return False
    
        pts = pts[:, :2] / wcol[:, None]
    
        # ---- 2) 对边长度比 ----
        edges = np.roll(pts, -1, axis=0) - pts
        L = np.linalg.norm(edges, axis=1) + 1e-9
        for a, b in [(0, 2), (1, 3)]:
            r = L[a] / L[b]
            if min(r, 1.0 / r) < min_edge_ratio:
                return False
    
        # ---- 3) 凸性 / 自交（叉积同号）----
        cross = edges[:, 0] * np.roll(edges[:, 1], -1) - \
                edges[:, 1] * np.roll(edges[:, 0], -1)
        if not (np.all(cross > 0) or np.all(cross < 0)):
            return False
    
        # ---- 4) 面积比 ----
        x, y = pts[:, 0], pts[:, 1]
        area_dst = 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))
        area_src = max(float(w_q) * float(h_q), 1.0)
        ratio = area_dst / area_src
        if ratio < min_area_ratio or ratio > max_area_ratio:
            return False
    
        # ---- 5) 角点越界 ----
        if pts[:, 0].min() < -0.5 * w_t or pts[:, 0].max() > 1.5 * w_t:
            return False
        if pts[:, 1].min() < -0.5 * h_t or pts[:, 1].max() > 1.5 * h_t:
            return False
        return True

    @staticmethod
    def _homography_deviation(H1, H2, w_q, h_q, n=8):
        """★ 新增: 两个单应性在源图范围内映射结果的最大偏差(px), 用于 grid 锚定容差判断"""
        xs = np.linspace(0, w_q, n)
        ys = np.linspace(0, h_q, n)
        gx, gy = np.meshgrid(xs, ys)
        pts = np.stack([gx.ravel(), gy.ravel(), np.ones(gx.size)], axis=1).T
        p1 = (H1 @ pts).T; p1 = p1[:, :2] / (p1[:, 2:3] + 1e-9)
        p2 = (H2 @ pts).T; p2 = p2[:, :2] / (p2[:, 2:3] + 1e-9)
        return float(np.linalg.norm(p1 - p2, axis=1).max())

    def _anchor_refit_homography(self, H_auto, H_grid, w_q, h_q, h_t, w_t, tol_px,
                                 min_area_ratio=0.01, max_area_ratio=100.0,
                                 min_edge_ratio=0.30, max_persp=0.35):
        """★ 新增: Grid 锚定重估。特征匹配整体偏离 grid 但局部仍可靠时,
        只保留落在 grid 预测位置 tol_px 邻域内的 DISK 内点, 重新估计单应性。
        校正被限制在 grid 附近, 同时部分吸收真实漂移。失败返回 None(调用方回退 grid)。"""
        pts_q = getattr(self, "_disk_pts_q", None)
        pts_t = getattr(self, "_disk_pts_t", None)
        if pts_q is None or pts_t is None or len(pts_q) < 8:
            return None
        ones = np.hstack([pts_q, np.ones((len(pts_q), 1))])
        p_grid = (H_grid @ ones.T).T; p_grid = p_grid[:, :2] / (p_grid[:, 2:3] + 1e-9)
        p_auto = (H_auto @ ones.T).T; p_auto = p_auto[:, :2] / (p_auto[:, 2:3] + 1e-9)
        keep = np.linalg.norm(p_auto - p_grid, axis=1) <= tol_px
        if int(keep.sum()) < 8:
            return None
        try:
            H_new, mask = cv2.findHomography(pts_q[keep], pts_t[keep], cv2.USAC_MAGSAC, 3.0)
        except Exception:
            return None
        if H_new is None or mask is None or int(np.sum(mask)) < 6:
            return None
        if not np.all(np.isfinite(H_new)) or not self._homography_is_sane(
                H_new, h_q, w_q, h_t, w_t,
                max_persp=max_persp,
                min_edge_ratio=min_edge_ratio,
                min_area_ratio=min_area_ratio,
                max_area_ratio=max_area_ratio):
            return None
        return H_new

    def _grid_anchor_tol_px(self, H_grid, w_q, h_q):
        """grid 锚定容差: 相对 tile 尺寸, 但设绝对上限。
        H 级别只需要吸收几像素~几十像素的漂移; 更大的偏差属于匹配失败。"""
        corners = np.array([[0, 0], [w_q, 0], [w_q, h_q], [0, h_q]], dtype=np.float64)
        pc = np.hstack([corners, np.ones((4, 1))]) @ np.asarray(H_grid, np.float64).T
        pc = pc[:, :2] / pc[:, 2:3]
        size = float(max(np.ptp(pc[:, 0]), np.ptp(pc[:, 1]), 1.0))
        return float(max(6.0, min(self.GRID_ANCHOR_MAX_PX, self.GRID_ANCHOR_TOLERANCE * size)))

    @classmethod
    def _grid_warp_scores(cls, query_img, train_img, base_mask, H):
        """候选 H 的结构评分: 直方图归一化后的灰度中位差 + 光流残差中位数。
        只在几何掩码内统计, 与颜色编辑无关。"""
        h_t, w_t = train_img.shape[:2]
        if base_mask is None:
            base_mask = np.ones(query_img.shape[:2], dtype=np.float32)
        wf = cv2.warpPerspective(query_img, H, (w_t, h_t), flags=cv2.INTER_LINEAR,
                                 borderMode=cv2.BORDER_REFLECT101)
        wm = cv2.warpPerspective(base_mask, H, (w_t, h_t), flags=cv2.INTER_LINEAR)
        photo = cls._photometric_score(wf, wm, train_img, edit_mask=None)
        resid, _ = cls._flow_residual_score(wf, wm, train_img, edit_mask=None)
        return float(photo), float(resid)

    def _grid_candidate_ok(self, query_img, train_img, base_mask, H_cand, H_grid,
                           photo_slack=2.0, resid_slack=0.5):
        """候选 H 必须不劣于 grid 保底, 才允许替换。避免"更贴合 grid"之外
        的低置信匹配把整块搬走。"""
        p_c, r_c = self._grid_warp_scores(query_img, train_img, base_mask, H_cand)
        p_g, r_g = self._grid_warp_scores(query_img, train_img, base_mask, H_grid)
        if p_c >= 1e8 or r_c >= 1e8:
            return False
        if p_g >= 1e8 or r_g >= 1e8:
            return True
        ok = (p_c <= p_g + photo_slack) and (r_c <= r_g + resid_slack)
        self._dlog(f"[Smart Merge] Grid候选评分: 光度 {p_c:.1f}/残差 {r_c:.2f}px "
                   f"vs grid {p_g:.1f}/{r_g:.2f}px → {'采纳' if ok else '弃用'}")
        return ok

    def _resolve_grid_alignment(self, query_img, train_img, base_mask, H_grid, H_bridge, device):
        """决定 grid 分块用哪个 H 做粗对齐。

        优先级:
          1) 桥接 H(A→BG): 来自未编辑原块与背景的实测, 是放置位置最可靠的证据;
             grid 坐标在这里只当布局参考, 不参与竞争。
          2) 无桥接时才做 B→BG 特征匹配, 且必须同时满足: 内点足够、偏离 grid 在
             容差内、结构评分不劣于 grid。
          3) 都不成立 → grid 保底。
        """
        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]

        if H_bridge is not None and self._homography_is_sane(
                H_bridge, h_q, w_q, h_t, w_t,
                min_area_ratio=0.01, max_area_ratio=100.0,
                min_edge_ratio=0.20, max_persp=0.60):
            dev = self._homography_deviation(H_bridge, H_grid, w_q, h_q)
            if dev <= max(96.0, 0.45 * max(w_t, h_t)):
                self._dlog(f"[Smart Merge] Grid锚定: 采用桥接 A→BG 实测放置 "
                           f"(偏离grid {dev:.1f}px) | bridge placement used")
                return H_bridge, "Grid_Bridge", -1
            print(f"[Smart Merge] Grid锚定: 桥接H偏离grid {dev:.1f}px 过大, "
                  f"改用特征匹配 | bridge H too far from grid, using feature match")

        H_auto, _inl, n_inl, m_auto = self.estimate_homography(
            query_img, train_img, device=device,
            min_area_ratio=1e-4, max_area_ratio=1e4,
            min_edge_ratio=0.08, max_persp=0.90
        )
        if H_auto is None:
            self._dlog("[Smart Merge] Grid锚定: 特征匹配失败, 使用grid保底 | auto-match failed, grid fallback")
            return H_grid, "Grid_Base", -1

        tol = self._grid_anchor_tol_px(H_grid, w_q, h_q)
        dev = self._homography_deviation(H_auto, H_grid, w_q, h_q)
        if n_inl >= self.GRID_AUTO_MIN_INLIERS and dev <= tol \
                and self._grid_candidate_ok(query_img, train_img, base_mask, H_auto, H_grid):
            self._dlog(f"[Smart Merge] Grid锚定: 特征匹配偏离grid {dev:.1f}px ≤ 容差{tol:.1f}px, "
                       f"内点{n_inl}, 采用特征精修 | auto-match accepted")
            return H_auto, (m_auto or "Grid_Auto"), n_inl

        self._dlog(f"[Smart Merge] Grid锚定: 自动匹配不可信(内点{n_inl}, 偏离{dev:.1f}px/容差{tol:.1f}px), "
                   f"尝试邻域重估 | auto-match rejected, trying anchored refit")
        H_anch = self._anchor_refit_homography(
            H_auto, H_grid, w_q, h_q, h_t, w_t, tol,
            min_area_ratio=1e-4, max_area_ratio=1e4,
            min_edge_ratio=0.08, max_persp=0.90)
        if H_anch is not None and self._grid_candidate_ok(
                query_img, train_img, base_mask, H_anch, H_grid):
            self._dlog("[Smart Merge] Grid锚定: 已用grid邻域内点重估 | anchored refit accepted")
            return H_anch, "Grid_Anchored", -1

        self._dlog("[Smart Merge] Grid锚定: 回退grid保底 | fallback to grid base")
        return H_grid, "Grid_Base", -1

    @staticmethod
    def _points_spread_cells(pts, w, h, n=4):
        """内点在 n×n 网格里占据的格数。簇状假匹配的格数会远小于真实匹配。"""
        if pts is None or len(pts) < 4 or w <= 0 or h <= 0:
            return 0
        cx = np.clip((pts[:, 0] / float(w) * n).astype(int), 0, n - 1)
        cy = np.clip((pts[:, 1] / float(h) * n).astype(int), 0, n - 1)
        return int(len(set(zip(cx.tolist(), cy.tolist()))))

    @classmethod
    def _edge_map(cls, img, size):
        """放置搜索用的边缘图: Sobel 幅值 → log → 分位数归一化。
        对改色与曝光差异不敏感, 只保留结构。"""
        g = cv2.resize(cv2.cvtColor(img, cv2.COLOR_RGB2GRAY), size, interpolation=cv2.INTER_AREA)
        g = cv2.GaussianBlur(g, (0, 0), 0.8)
        gx = cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3)
        mag = np.log1p(cv2.magnitude(gx, gy))
        hi = float(np.percentile(mag, 99.5))
        if hi <= 1e-6:
            return np.zeros((size[1], size[0]), dtype=np.uint8)
        return (np.clip(mag / hi, 0.0, 1.0) * 255).astype(np.uint8)

    def _coarse_placement_h(self, query_img, train_img):
        """特征匹配不可用时的放置兜底: 多尺度模板匹配(亮度+边缘) → 平移精调
        → 尺度微调。返回把分块坐标映射到背景坐标的相似变换 H 与 NCC 置信度。

        只做平移+等比缩放; 结果必须通过 NCC 门槛与单应性体检, 否则返回 None。
        """
        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]
        if min(h_q, w_q, h_t, w_t) < 32:
            return None, 0.0

        s = min(1.0, 512.0 / max(h_t, w_t))
        bw = max(64, int(round(w_t * s)))
        bh = max(64, int(round(h_t * s)))
        bg_gray = cv2.GaussianBlur(
            cv2.resize(cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY), (bw, bh),
                       interpolation=cv2.INTER_AREA).astype(np.float32), (0, 0), 1.0)
        bg_edge = cv2.GaussianBlur(
            self._edge_map(train_img, (bw, bh)).astype(np.float32), (0, 0), 1.0)

        crop_gray = cv2.cvtColor(query_img, cv2.COLOR_RGB2GRAY).astype(np.float32)
        crop_edge = self._edge_map(query_img, (w_q, h_q)).astype(np.float32)

        def _corr(a, b):
            a = a - a.mean()
            b = b - b.mean()
            den = float(np.sqrt(float((a * a).sum()) * float((b * b).sum()))) + 1e-9
            return float((a * b).sum() / den)

        def _warp(rel, tx, ty):
            # crop 是原分辨率, 搜索画布已按 s 缩小 → 缩放必须带上 s
            k = rel * s
            M = np.array([[k, 0, tx], [0, k, ty]], np.float32)
            g = cv2.warpAffine(crop_gray, M, (bw, bh), flags=cv2.INTER_LINEAR, borderValue=0)
            e = cv2.warpAffine(crop_edge, M, (bw, bh), flags=cv2.INTER_LINEAR, borderValue=0)
            v = cv2.warpAffine(np.ones(crop_gray.shape, np.uint8), M, (bw, bh),
                               flags=cv2.INTER_NEAREST, borderValue=0)
            v = cv2.erode(v, np.ones((7, 7), np.uint8)) > 0
            return g, e, v

        def _ncc(rel, tx, ty):
            g, e, v = _warp(rel, tx, ty)
            if int(v.sum()) < 400:
                return -1.0
            return 0.5 * _corr(bg_gray[v], g[v]) + 0.5 * _corr(bg_edge[v], e[v])

        # 粗搜(搜索坐标系, BG 最长边 512)
        best = None
        for rel in (1.0, 0.8, 1.25, 0.67, 1.5, 2.0, 0.5):
            tw, th = int(round(w_q * s * rel)), int(round(h_q * s * rel))
            if tw < 32 or th < 32 or tw > bw - 16 or th > bh - 16:
                continue
            t_gray = cv2.GaussianBlur(
                cv2.resize(crop_gray, (tw, th), interpolation=cv2.INTER_AREA), (0, 0), 1.0)
            t_edge = cv2.GaussianBlur(
                self._edge_map(query_img, (tw, th)).astype(np.float32), (0, 0), 1.0)
            r_gray = cv2.matchTemplate(bg_gray, t_gray, cv2.TM_CCOEFF_NORMED)
            r_edge = cv2.matchTemplate(bg_edge, t_edge, cv2.TM_CCOEFF_NORMED)
            _, max_v, _, max_loc = cv2.minMaxLoc(0.5 * r_gray + 0.5 * r_edge)
            if best is None or max_v > best[0]:
                best = (float(max_v), float(rel), float(max_loc[0]), float(max_loc[1]))
        if best is None or best[0] < self.B2BG_MIN_MATCH_NCC:
            return None, 0.0

        _, rel, tx, ty = best
        ncc = _ncc(rel, tx, ty)
        # 平移精调: 相位相关给出亚像素候选, 符号不确定, 用 NCC 择优
        for _ in range(2):
            g, e, v = _warp(rel, tx, ty)
            ys, xs = np.where(v)
            if len(ys) < 400:
                break
            y0, y1 = int(ys.min()), int(ys.max()) + 1
            x0, x1 = int(xs.min()), int(xs.max()) + 1
            try:
                (dx, dy), _resp = cv2.phaseCorrelate(bg_gray[y0:y1, x0:x1], g[y0:y1, x0:x1])
            except Exception:
                break
            if not (np.isfinite(dx) and np.isfinite(dy)) or max(abs(dx), abs(dy)) > 32.0:
                break
            improved = False
            for sgn in (1.0, -1.0):
                v_new = _ncc(rel, tx + sgn * dx, ty + sgn * dy)
                if v_new > ncc + 1e-4:
                    tx, ty, ncc = tx + sgn * dx, ty + sgn * dy, v_new
                    improved = True
                    break
            if not improved:
                break
        # 尺度微调(以 warp 区域中心为基准, 避免缩放同时平移)
        cx = tx + rel * w_q * s * 0.5
        cy = ty + rel * h_q * s * 0.5
        for k in (0.97, 1.03):
            r2 = rel * k
            tx2 = cx - r2 * w_q * s * 0.5
            ty2 = cy - r2 * h_q * s * 0.5
            v_new = _ncc(r2, tx2, ty2)
            if v_new > ncc + 1e-3:
                rel, tx, ty, ncc = r2, tx2, ty2, v_new
        if ncc < self.B2BG_MIN_MATCH_NCC:
            return None, 0.0

        H = np.array([[rel, 0.0, tx / s], [0.0, rel, ty / s], [0.0, 0.0, 1.0]], np.float64)
        if not self._homography_is_sane(H, h_q, w_q, h_t, w_t,
                                        min_area_ratio=0.05, max_area_ratio=20.0,
                                        min_edge_ratio=0.25, max_persp=0.50):
            return None, 0.0
        self._dlog(f"[Smart Merge] 模板匹配放置: 缩放{rel:.3f} 平移({tx / s:.1f},{ty / s:.1f}) "
                   f"NCC={ncc:.2f} | template placement")
        return H, float(ncc)

    @staticmethod
    def _grid_shape(crop_total, w_t, h_t):
        """由分块数推断行列数: 取因式分解中 cols/rows 最接近背景宽高比的一组。"""
        try:
            crop_total = int(crop_total)
        except Exception:
            return None
        if crop_total < 4:
            return None
        best = None
        for cols in range(2, crop_total + 1):
            if crop_total % cols:
                continue
            rows = crop_total // cols
            if rows < 2:
                continue
            score = abs(np.log((cols / float(rows)) / max(w_t / float(h_t), 1e-6)))
            if best is None or score < best[0]:
                best = (score, cols, rows)
        return None if best is None else (best[1], best[2])

    def _layout_candidates(self, crop_index, crop_total, w_q, h_q, w_t, h_t):
        """无像素证据时的布局推断候选: 分块序号 → 均匀格子。

        LayoutFill: 整块各向异性铺满格子(重采样的分块也能落位);
        LayoutFit : 保持分块宽高比居中放入格子(AI 按新比例重绘、带留白的情况)。
        两者都必须通过单应性体检; 是否采用由残差竞争决定, 不会单独决定放置。
        """
        if crop_index is None:
            return []
        shape = self._grid_shape(crop_total, w_t, h_t)
        try:
            idx = int(crop_index)
            total = int(crop_total)
        except Exception:
            return []
        if shape is None or idx < 0 or idx >= total:
            return []
        cols, rows = shape
        r, c = divmod(idx, cols)
        slot_w, slot_h = w_t / float(cols), h_t / float(rows)
        x0, y0 = c * slot_w, r * slot_h
        H_fill = np.array([[slot_w / float(w_q), 0.0, x0],
                           [0.0, slot_h / float(h_q), y0],
                           [0.0, 0.0, 1.0]], np.float64)
        k = min(slot_w / float(w_q), slot_h / float(h_q))
        H_fit = np.array([[k, 0.0, x0 + (slot_w - k * w_q) * 0.5],
                          [0.0, k, y0 + (slot_h - k * h_q) * 0.5],
                          [0.0, 0.0, 1.0]], np.float64)
        cands = []
        for name, H in (("LayoutFill", H_fill), ("LayoutFit", H_fit)):
            if self._homography_is_sane(H, h_q, w_q, h_t, w_t,
                                        min_area_ratio=0.01, max_area_ratio=100.0,
                                        min_edge_ratio=0.20, max_persp=0.50):
                cands.append((name, H))
        return cands

    def _record_layout_obs(self, crop_index, H, w_q, h_q):
        """记下已成功放置的分块, 供同一张图内后续失败块反推格子步长。"""
        try:
            obs = getattr(self, "_b2bg_layout_obs", None)
            if obs is None:
                obs = self._b2bg_layout_obs = {}
            obs[int(crop_index)] = (np.array(H, np.float64).copy(), float(w_q), float(h_q))
        except Exception:
            pass

    def _layout_fit_candidates(self, crop_index, crop_total, w_q, h_q, w_t, h_t):
        """用本图已成功放置的分块反推格子步长(可吸收 overlap), 预测本块中心。

        只平移 LayoutFill 候选, 不改缩放。至少需要 2 行 2 列的观测。
        """
        obs = getattr(self, "_b2bg_layout_obs", None)
        shape = self._grid_shape(crop_total, w_t, h_t)
        if not obs or len(obs) < 3 or shape is None:
            return []
        cols, rows = shape
        slot_w, slot_h = w_t / float(cols), h_t / float(rows)
        try:
            total = int(crop_total)
            idx_t = int(crop_index)
        except Exception:
            return []
        cx, cy, cs, rs = [], [], [], []
        for idx, item in obs.items():
            if not (0 <= idx < total):
                continue
            H_o, w_o, h_o = item
            p = (H_o @ np.array([[w_o * 0.5], [h_o * 0.5], [1.0]])).ravel()
            if abs(p[2]) < 1e-9:
                continue
            r_i, c_i = divmod(int(idx), cols)
            cx.append(p[0] / p[2]); cy.append(p[1] / p[2])
            cs.append(c_i); rs.append(r_i)
        if len(set(cs)) < 2 or len(set(rs)) < 2:
            return []
        try:
            (x0, stride_x), *_ = np.linalg.lstsq(
                np.stack([np.ones(len(cs)), np.array(cs, float)], 1),
                np.array(cx, float), rcond=None)
            (y0, stride_y), *_ = np.linalg.lstsq(
                np.stack([np.ones(len(rs)), np.array(rs, float)], 1),
                np.array(cy, float), rcond=None)
        except Exception:
            return []
        if not (np.isfinite(x0) and np.isfinite(y0)
                and np.isfinite(stride_x) and np.isfinite(stride_y)):
            return []
        r_t, c_t = divmod(idx_t, cols)
        kx, ky = slot_w / float(w_q), slot_h / float(h_q)
        H = np.array([[kx, 0.0, x0 + stride_x * c_t - kx * w_q * 0.5],
                      [0.0, ky, y0 + stride_y * r_t - ky * h_q * 0.5],
                      [0.0, 0.0, 1.0]], np.float64)
        if not self._homography_is_sane(H, h_q, w_q, h_t, w_t,
                                        min_area_ratio=0.01, max_area_ratio=100.0,
                                        min_edge_ratio=0.20, max_persp=0.50):
            return []
        return [("LayoutFit", H)]

    @staticmethod
    def _edge_ncc(query_edge, train_edge, H_scaled, h_q, w_q):
        """结构(边缘图)归一化相关: 与颜色/亮度编辑无关, 判断“这块内容是否真的
        对应这个位置”。0≈无关, 1≈完全一致。"""
        h_e, w_e = train_edge.shape[:2]
        we = cv2.warpPerspective(query_edge, H_scaled, (w_e, h_e),
                                 flags=cv2.INTER_LINEAR, borderValue=0)
        wv = cv2.warpPerspective(np.ones((h_q, w_q), np.uint8), H_scaled, (w_e, h_e),
                                 flags=cv2.INTER_NEAREST, borderValue=0)
        v = cv2.erode(wv, np.ones((9, 9), np.uint8)) > 0
        if int(v.sum()) < 500:
            return 0.0
        a = we[v].astype(np.float32)
        b = train_edge[v].astype(np.float32)
        a = a - a.mean()
        b = b - b.mean()
        den = float(np.sqrt(float((a * a).sum()) * float((b * b).sum()))) + 1e-9
        return float((a * b).sum() / den)

    def _loftr_homography(self, query_img, train_img, device):
        """LoFTR 半稠密匹配 → H。低纹理/大面积改色块上 DISK 拿不到足够特征时兜底。"""
        try:
            q, t = self.match_with_loftr(query_img, train_img, device)
        except Exception as e:
            print(f"[Smart Merge] LoFTR 兜底匹配失败: {e}")
            return None
        if q is None or t is None or len(q) < 8:
            return None
        if len(q) > 1200:
            step = int(np.ceil(len(q) / 1200.0))
            q, t = q[::step], t[::step]
        q, t = self.filter_correspondences_local_affine(q, t)
        if len(q) < 8:
            return None
        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]
        magsac_flag = getattr(cv2, 'USAC_MAGSAC', cv2.RANSAC)
        H, inliers = cv2.findHomography(q, t, magsac_flag, 4.0)
        if H is None or inliers is None or int(np.sum(inliers)) < 8:
            return None
        inl = inliers.ravel().astype(bool)
        try:
            H_refit, _ = cv2.findHomography(q[inl], t[inl], 0)
            if H_refit is not None and np.all(np.isfinite(H_refit)):
                H = H_refit
        except Exception:
            pass
        if not self._homography_is_sane(H, h_q, w_q, h_t, w_t,
                                        min_area_ratio=0.01, max_area_ratio=100.0,
                                        min_edge_ratio=0.30, max_persp=0.35):
            return None
        try:
            ones = np.hstack([q, np.ones((len(q), 1))])
            p = (H @ ones.T).T
            p = p[:, :2] / p[:, 2:]
            keep = np.linalg.norm(p - t, axis=1) < 10.0
            if int(keep.sum()) >= 8:
                self._disk_pts_q = q[keep]
                self._disk_pts_t = t[keep]
        except Exception:
            pass
        self._match_level = "LoFTR"
        print(f"[Smart Merge] DISK 特征不足, 启用 LoFTR 半稠密兜底 ({len(q)} 对) | "
              f"LoFTR fallback ({len(q)} matches)")
        return H

    def _select_b2bg_homography(self, query_img, train_img, base_mask, device,
                                crop_index=0, crop_total=1):
        """B→BG(无 grid、无 A) 的粗对齐决策。

        证据链: DISK+LightGlue → LoFTR 兜底 → 模板匹配 → 布局推断。
        实测候选(特征/模板)按结构残差竞争, 门槛 B2BG_MAX_RESID; 全部失败时用布局
        推断把分块放到它所属的格子(近似放置), 门槛 B2BG_LAYOUT_MAX_RESID; 仍不成立
        才返回 None 由调用方跳过(绝不居中硬贴)。
        """
        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]

        def _resid(H):
            if H is None:
                return None
            try:
                _p, r = self._grid_warp_scores(query_img, train_img, base_mask, H)
            except Exception:
                return None
            return None if r is None or r >= 1e8 else float(r)

        def _accept(name, H, r, approx=False, note=""):
            if name not in ("B2BG_Feat", "DISK", "LoFTR"):
                # 放置不是来自特征 H → 特征点与当前基准不一致, 不让它们参与 TPS
                self._disk_pts_q = None
                self._disk_pts_t = None
            if not approx:
                self._record_layout_obs(crop_index, H, w_q, h_q)
            suffix = f", {note}" if note else ""
            print(f"[Smart Merge] B→BG 对齐: {name} (残差 {r:.2f}px"
                  f"{', 布局近似放置' if approx else ''}{suffix}) | B→BG alignment via {name}")
            return H, name, float(r)

        def _match(q):
            H, _inl, _n, m = self.estimate_homography(
                q, train_img, device=device,
                min_area_ratio=0.01, max_area_ratio=100.0,
                min_edge_ratio=0.30, max_persp=0.35,
                min_cells=self.B2BG_MIN_SPREAD_CELLS)
            return H, _resid(H), m

        H_feat, feat_r, m_feat = _match(query_img)
        query_for_match = query_img

        # 暗部/低对比块: 曲线提亮后重试一次特征匹配(失败时)
        if feat_r is None or feat_r > self.B2BG_MAX_RESID:
            q_b = self._brighten_for_match(query_img)
            if q_b is not None:
                pts_q0, pts_t0 = self._disk_pts_q, self._disk_pts_t
                H_b, r_b, m_b = _match(q_b)
                if r_b is not None and (feat_r is None or r_b < feat_r - 0.2):
                    print(f"[Smart Merge] 暗部分块曲线提亮后匹配成功 (残差 {r_b:.2f}px) | "
                          f"brightened retry matched")
                    H_feat, feat_r, m_feat = H_b, r_b, m_b
                    query_for_match = q_b
                else:
                    # 没改善: 恢复第一次的特征点, 别让失败重试清空它们
                    self._disk_pts_q, self._disk_pts_t = pts_q0, pts_t0
                    print("[Smart Merge] 曲线提亮后仍未改善, 继续降级 | brightened retry no gain")

        if feat_r is not None and feat_r <= self.B2BG_TRUST_RESID:
            return _accept(m_feat or "B2BG_Feat", H_feat, feat_r)

        evid = []
        if feat_r is not None:
            evid.append((m_feat or "B2BG_Feat", H_feat, feat_r))

        # 模板放置: 全图多尺度结构+灰度相关, ~0.1s 且与颜色/亮度编辑无关。
        # 放在 LoFTR 之前: NCC 明显可信时直接采用, 省掉 LoFTR 的十几秒开销。
        H_coarse, ncc = self._coarse_placement_h(query_img, train_img)
        tm_r = _resid(H_coarse)
        if tm_r is not None:
            evid.append(("TemplateMatch", H_coarse, tm_r))

        if (self.B2BG_USE_LOFTR and (feat_r is None or feat_r > self.B2BG_MAX_RESID)
                and ncc < 0.55):
            H_lo = self._loftr_homography(query_for_match, train_img, device)
            lo_r = _resid(H_lo)
            if lo_r is not None:
                evid.append(("LoFTR", H_lo, lo_r))

        if abs(w_q - w_t) <= 2 and abs(h_q - h_t) <= 2:
            H_same = np.eye(3, dtype=np.float64)
            ss_r = _resid(H_same)
            if ss_r is not None:
                evid.append(("SameSize", H_same, ss_r))

        layout = []
        ncc_other = 0.0
        layout_raw = (self._layout_candidates(crop_index, crop_total, w_q, h_q, w_t, h_t)
                      + self._layout_fit_candidates(crop_index, crop_total, w_q, h_q, w_t, h_t))
        if layout_raw:
            s_e = min(1.0, 512.0 / float(max(h_t, w_t)))
            bw = max(64, int(round(w_t * s_e)))
            bh = max(64, int(round(h_t * s_e)))
            qe = self._edge_map(query_img, (w_q, h_q)).astype(np.float32)
            te = self._edge_map(train_img, (bw, bh)).astype(np.float32)
            H_scale = np.diag([s_e, s_e, 1.0])

            def _ncc_at(H):
                return self._edge_ncc(qe, te, H_scale @ H, h_q, w_q)

            # 对照: 同一块放到其它格子时的结构相关。不相关的内容(与整幅图无关的分块)
            # 在所有格子上 NCC 都≈0, 不该被硬塞进某格。
            others = []
            try:
                total_i = int(crop_total)
            except Exception:
                total_i = 0
            for _i in range(total_i):
                if _i == int(crop_index):
                    continue
                _c = self._layout_candidates(_i, crop_total, w_q, h_q, w_t, h_t)
                if _c:
                    others.append(_ncc_at(_c[0][1]))
            ncc_other = max(others) if others else 0.0
            for name, H in layout_raw:
                r = _resid(H)
                if r is not None:
                    layout.append((name, H, r, _ncc_at(H)))

        evid_ok = [c for c in evid if c[2] <= self.B2BG_MAX_RESID]
        if evid_ok:
            name, H, r = min(evid_ok, key=lambda c: c[2])
            return _accept(name, H, r)

        layout_ok = [c for c in layout
                     if c[2] <= self.B2BG_LAYOUT_MAX_RESID
                     and c[3] >= self.B2BG_LAYOUT_MIN_NCC
                     and c[3] >= ncc_other + self.B2BG_LAYOUT_NCC_MARGIN]
        if layout_ok:
            name, H, r, ncc_l = min(layout_ok, key=lambda c: (-c[3], c[2]))
            return _accept(name, H, r, approx=True,
                           note=f"结构相关 {ncc_l:.2f} > 对照 {ncc_other:.2f}")

        detail = ", ".join(f"{n}={r:.1f}px" for n, _H, r in evid) or "无实测候选"
        if layout:
            detail += " | 布局: " + ", ".join(
                f"{nm}={r:.1f}px/ncc{c:.2f}" for nm, _H, r, c in layout) \
                + f" (对照 {ncc_other:.2f})"
        print(f"[Smart Merge] B→BG 放置失败({detail}), 跳过该块以保护整图 | "
              f"no reliable placement, tile skipped")
        return None, None, None

    def _filter_reliable_correspondences(self, q, t, h_t, w_t, edit_mask):
        """挑出“证据可靠”的对应点: 目标点落在未改色区, 且通过局部仿射一致性检查。

        改色区内的特征描述子不可信(可能匹配到别处相似结构), 用它们建场会把
        局部错误扩散到整块; 剔除后由 TPS 的平滑场把可靠区的校正量外推到该区域,
        即“用正确区域的校正近似其余区域”。
        返回 (q, t, 是否启用外推)。
        """
        if q is None or t is None or len(q) < 8 or edit_mask is None:
            return q, t, False
        xi = np.clip(np.round(t[:, 0]).astype(int), 0, w_t - 1)
        yi = np.clip(np.round(t[:, 1]).astype(int), 0, h_t - 1)
        keep = edit_mask[yi, xi] > 0.5
        n_keep = int(keep.sum())
        if n_keep < 8 or n_keep >= len(q):
            return q, t, False          # 几乎没有改色区 → 不介入
        q2, t2 = q[keep], t[keep]
        q3, t3 = self.filter_correspondences_local_affine(q2, t2)
        if len(q3) < 8:
            q3, t3 = q2, t2
        if (np.ptp(q3[:, 0]) < 0.30 * np.ptp(q[:, 0])
                or np.ptp(q3[:, 1]) < 0.30 * np.ptp(q[:, 1])):
            return q, t, False          # 剩余点太集中, 不能代表整块
        self._dlog(f"[Smart Merge] 可靠对应点: {len(q3)}/{len(q)} "
                   f"(改色区剔除 {len(q) - n_keep} 点) | reliable correspondences")
        return q3, t3, True

    @classmethod
    def _bridge_photometric_ok(cls, H, query_img, train_img):
        """桥接H质量粗检: CLAHE 归一化后灰度中位差 + 高梯度区方向余弦一致性。
        对明暗差异鲁棒，同时能抓到局部结构错位。"""
        h_t, w_t = train_img.shape[:2]
        h_q, w_q = query_img.shape[:2]
        mask = cv2.warpPerspective(np.ones((h_q, w_q), np.float32), H, (w_t, h_t), flags=cv2.INTER_LINEAR)
        if float(mask.sum()) < 100.0:
            return False
        warped = cv2.warpPerspective(query_img, H, (w_t, h_t), flags=cv2.INTER_LINEAR,
                                     borderMode=cv2.BORDER_REFLECT101)
        m = cv2.erode((mask > 0.5).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        if not np.any(m):
            m = mask > 0.5
    
        # 光照归一化：CLAHE 
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        g1 = clahe.apply(cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)).astype(np.float32)
        g2 = clahe.apply(cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)).astype(np.float32)
    
        # (a) 中位差
        med = float(np.median(np.abs(g1[m] - g2[m])))
        if med > cls.BRIDGE_MAX_MEDIAN_DIFF:
            print(f"[Smart Merge] 桥接H光度一致性差(CLAHE后中位差 {med:.1f} > {cls.BRIDGE_MAX_MEDIAN_DIFF}), 降级自动对齐 | Bridge H unreliable (median {med:.1f}), falling back")
            return False
    
        # (b) 梯度方向一致性（只在高梯度区统计，对光照平移不变）
        gx1 = cv2.Sobel(g1, cv2.CV_32F, 1, 0, ksize=3)
        gy1 = cv2.Sobel(g1, cv2.CV_32F, 0, 1, ksize=3)
        gx2 = cv2.Sobel(g2, cv2.CV_32F, 1, 0, ksize=3)
        gy2 = cv2.Sobel(g2, cv2.CV_32F, 0, 1, ksize=3)
        mag1 = np.sqrt(gx1 * gx1 + gy1 * gy1)
        mag2 = np.sqrt(gx2 * gx2 + gy2 * gy2)
        strong = m & (mag1 > 20.0) & (mag2 > 20.0)
        if int(strong.sum()) >= 200:
            cos_sim = (gx1[strong] * gx2[strong] + gy1[strong] * gy2[strong]) / \
                      (mag1[strong] * mag2[strong] + 1e-6)
            mean_cos = float(np.mean(np.abs(cos_sim)))
            if mean_cos < 0.5:
                print(f"[Smart Merge] 桥接H梯度方向不匹配(平均|cos|={mean_cos:.2f} < 0.5), 降级自动对齐 | Bridge H gradient mismatch, falling back")
                return False
        return True

    @classmethod
    def _photometric_score(cls, warped_fg, warped_mask, train_img, edit_mask=None):
        """对齐质量评分: 掩码内灰度绝对差中位数。有 edit_mask 时剔除改色区。"""
        if warped_fg.shape[:2] != train_img.shape[:2]:
            return 1e9
        m_geo = cv2.erode((warped_mask > 0.5).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        m = m_geo
        if edit_mask is not None:
            m = m_geo & (edit_mask > 0.5)  # ★ 只在未改色的地方计算光度
            if float(m.sum()) < 100.0:
                # 改色/低置信区过大时不能直接判废，否则正确的对齐也会被拒绝
                m = m_geo
        if float(m.sum()) < 100.0:
            return 1e9
        g1 = cv2.cvtColor(warped_fg, cv2.COLOR_RGB2GRAY)
        g2 = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)
        # ★ 核心：打分前也强制对齐，这样偏色区只要结构对齐，分数就合格
        g1 = SmartMergeImages._match_histogram(g1, g2).astype(np.float32)
        g2 = g2.astype(np.float32)
        return float(np.median(np.abs(g1[m] - g2[m])))

    @classmethod
    def _align_score(cls, warped_fg, warped_mask, train_img, edit_mask=None):
        """对齐评分(边缘加权): 有 edit_mask 时剔除改色区。"""
        if warped_fg.shape[:2] != train_img.shape[:2]:
            return 1e9
        m = cv2.erode((warped_mask > 0.5).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
        if edit_mask is not None:
            m = m & (edit_mask > 0.5)  # ★ 剔除改色区
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
    def _flow_residual_score(cls, warped_fg, warped_mask, train_img, edit_mask=None):
        """几何残差评分(单位: px): 有 edit_mask 时剔除改色区。"""
        if warped_fg.shape[:2] != train_img.shape[:2]:
            return 1e9, 1e9
        mask_u8 = (warped_mask > 0.5).astype(np.uint8)
        ys, xs = np.where(mask_u8 > 0)
        if len(ys) < 400:
            return 1e9, 1e9
        pad = 32
        y0, y1 = max(0, int(ys.min()) - pad), min(warped_fg.shape[0], int(ys.max()) + pad)
        x0, x1 = max(0, int(xs.min()) - pad), min(warped_fg.shape[1], int(xs.max()) + pad)
        
        g1 = SmartMergeImages._to_flow_luma(warped_fg[y0:y1, x0:x1])
        g2 = SmartMergeImages._to_flow_luma(train_img[y0:y1, x0:x1])
        # ★ 核心：几何打分前也要对齐明暗结构
        g1 = SmartMergeImages._match_histogram(g1, g2)
        
        m = cv2.erode(mask_u8[y0:y1, x0:x1], np.ones((15, 15), np.uint8)) > 0
        m_geo = m
        
        if edit_mask is not None:
            em_sub = edit_mask[y0:y1, x0:x1]
            m = m_geo & (em_sub > 0.5)  # ★ 只在未改色的地方计算几何残差
            if float(m.sum()) < 400.0:
                # 改色/低置信区过大时回退到几何有效区，避免误判为不可评分
                m = m_geo
            
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
        p85 = float(np.percentile(mag[valid], 85))
        return med, p85



    def match_with_loftr(self, query_img, train_img, device="cpu"):
        """LoFTR 半稠密匹配: 输入必须是 (N,1,H,W) 灰度图"""
        try:
            from kornia.feature import LoFTR
            ensure_model_files()
            cls = SmartMergeImages
            if cls._loftr_model is None or cls._loftr_cached_device != device:
                cls._loftr_model = LoFTR(pretrained="outdoor").eval().to(device)
                cls._loftr_cached_device = device

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
                d = cls._loftr_model({"image0": img_q, "image1": img_t})
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
                self._dlog(f"[Smart Merge] TPS 离群剔除: 保留 {_keep.sum()}/{n} 点 (阈值 {_thr:.2f}px) | outliers removed")
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
            self._dlog(f"[Smart Merge] TPS 限幅收紧: {max_disp:.0f}→{_cap:.1f}px | cap tightened")
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
        # ★ 只放大位移场, 不能放大绝对采样坐标。
        # 旧写法 resize(map) 会把 0..w-step 的坐标域拉伸到 0..w,
        # 等效于对整块图做额外的缩放/偏移, TPS 反而破坏对齐。
        fg_full = cv2.resize(fg2, (w, h), interpolation=cv2.INTER_LINEAR)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        map_x = xx - fg_full[:, :, 0]
        map_y = yy - fg_full[:, :, 1]
        warped_fg = cv2.remap(warped_fg_src, map_x, map_y, interpolation=cv2.INTER_LANCZOS4,
                              borderMode=cv2.BORDER_REPLICATE)
        warped_mask = cv2.remap(warped_mask_src, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_CONSTANT, borderValue=0)
        self._dlog(f"[Smart Merge] TPS 场生效: {n}/{n_raw}点(保留/原始) 中位位移{med_mag:.1f}px "
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

    def global_flow_polish(self, merged_img, original_bg, union_mask, max_disp=12.0, edit_mask=None,
                           warp_smooth=1.0, optical_flow=False):
        """整图光流精修: 合成图 vs 原图, 补低纹理区残余位移。"""
        h, w = original_bg.shape[:2]
        gm_gray = cv2.cvtColor(merged_img, cv2.COLOR_RGB2GRAY)
        gm_l = self._to_flow_luma(merged_img)
        go_l = self._to_flow_luma(original_bg)

        # ★★★ 修复: 光流输入"改色免疫"预处理 ★★★
        # 根因: 改色(白杯→红杯)后 L 通道结构被彻底破坏, DIS 在改色物体边缘
        # 产生"对齐颜色边界"的虚假大位移 → 边缘拉伸。
        # CLAHE 局部对比归一化把红杯弱边缘增强到与白杯边缘形态对应,
        # 光流从此只看见几何结构 → 改色区内部的真实畸变依然可修。
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        gm_l = clahe.apply(gm_l)
        go_l = clahe.apply(go_l)
        # 仅在编辑区内做直方图匹配(全局会被背景主导), 消除残余分布差异
        gm_l = self._match_histogram_masked(gm_l, go_l, union_mask)
        # ★★★ 虚焦→实焦均衡: 把实焦编辑图模糊回原图虚焦尺度,
        #      恢复边缘宽度对应, 消除轮廓处系统性位移 ★★★
        gm_l, sigma_eq = self._defocus_equalize(gm_l, go_l, union_mask)
        # 预平滑: 去高频颜色纹理噪声, 保留宏观几何(真实畸变以低频为主)
        gm_l = cv2.GaussianBlur(gm_l, (11, 11), 0)
        go_l = cv2.GaussianBlur(go_l, (11, 11), 0)


        if optical_flow:
            try:
                dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
            except AttributeError:
                dis = cv2.DISOpticalFlow.create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
            flow = dis.calc(gm_l, go_l, None).astype(np.float32)
            flow_b = dis.calc(go_l, gm_l, None).astype(np.float32)
        else:
            flow = cv2.calcOpticalFlowFarneback(
                gm_l, go_l, None, 0.5, 3, 15, 5, 7, 1.5, cv2.OPTFLOW_FARNEBACK_GAUSSIAN
            ).astype(np.float32)
            flow_b = cv2.calcOpticalFlowFarneback(
                go_l, gm_l, None, 0.5, 3, 15, 5, 7, 1.5, cv2.OPTFLOW_FARNEBACK_GAUSSIAN
            ).astype(np.float32)
        
        grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
        map_x = (grid_x + flow[:, :, 0]).astype(np.float32)
        map_y = (grid_y + flow[:, :, 1]).astype(np.float32)
        bwd_at_fwd = cv2.remap(flow_b, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        fb_err = np.linalg.norm(flow + bwd_at_fwd, axis=2)
        # ★ 收紧前后向一致性: 真实几何位移场前后向自洽(fb_err很小);
        #   改色边缘的虚假位移不自洽 → 被此门槛抑制
        consistency_gate = np.clip((2.0 - fb_err) / 1.5, 0.0, 1.0)
        texture_m = np.sqrt(cv2.Sobel(gm_l, cv2.CV_32F, 1, 0) ** 2
                            + cv2.Sobel(gm_l, cv2.CV_32F, 0, 1) ** 2)
        texture_o = np.sqrt(cv2.Sobel(go_l, cv2.CV_32F, 1, 0) ** 2
                            + cv2.Sobel(go_l, cv2.CV_32F, 0, 1) ** 2)
        texture_hard = np.maximum(texture_m, texture_o) > 3.0
        texture_support = cv2.dilate(texture_hard.astype(np.uint8), np.ones((21, 21), np.uint8))
        texture_soft = cv2.GaussianBlur(texture_support.astype(np.float32), (21, 21), 0)

        reference_mask = np.ones((h, w), dtype=np.float32)
        if edit_mask is not None:
            reference_mask = cv2.erode(
                (edit_mask > 0.95).astype(np.uint8), np.ones((31, 31), np.uint8)
            ).astype(np.float32)

        mag = np.linalg.norm(flow, axis=2)
        sel = union_mask > 0.5
        reliable_sel = sel & (consistency_gate > 0.1) & (texture_support > 0) & (reference_mask > 0.5)
        if int(reliable_sel.sum()) < 100 or float(np.median(mag[reliable_sel])) < 0.6:
            print("[Smart Merge] 整图精修: 可靠区域残余位移<0.6px, 跳过 | polish skipped")
            return merged_img
        scale = np.minimum(mag, max_disp) / (mag + 1e-8)
        flow[:, :, 0] *= scale
        flow[:, :, 1] *= scale

        um = cv2.GaussianBlur(sel.astype(np.float32), (31, 31), 0)
        final_gate = um * consistency_gate * texture_soft
        if edit_mask is not None:
            smooth_edit_mask = cv2.GaussianBlur(reference_mask, (31, 31), 0)
            final_gate *= np.clip(smooth_edit_mask, 0.0, 1.0)
        flow *= final_gate[:, :, None]
        flow = self._fill_flow_from_reliable(flow, final_gate)
        flow *= um[:, :, None]
        # ★★★ 颜色改变"边界带": 用邻域平滑值【替换】, 而不是置零 ★★★
        # 置零(遮mask) → 轮廓处真实畸变不修; 保留 → 虚假高频位移拉伸边缘。
        # 平滑值替换 = 丢掉边界带高频虚假分量, 同时延续周围低频真实位移场, 两全。
        if edit_mask is not None:
            em_f = np.clip(edit_mask.astype(np.float32), 0.0, 1.0)
            band = np.abs(cv2.Laplacian(em_f, cv2.CV_32F, ksize=5))
            # ★ 边界带自适应加宽: sigma_eq 越大(虚焦差越大), 失配过渡区越宽
            _k1 = 9 + int(min(sigma_eq, 8.0) * 3)
            _k1 += (_k1 + 1) % 2  # 保持奇数
            _k2 = 11 + int(min(sigma_eq, 8.0) * 2)
            _k2 += (_k2 + 1) % 2
            band = cv2.dilate(band, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_k1, _k1)))
            band = cv2.GaussianBlur(band, (_k2, _k2), 0)
            band = np.clip(band * 4.0, 0.0, 1.0)
            if float(band.max()) > 0.05:
                _k3 = max(21, int(sigma_eq * 6) | 1)
                flow_smooth_x = cv2.blur(flow[:, :, 0], (_k3, _k3))
                flow_smooth_y = cv2.blur(flow[:, :, 1], (_k3, _k3))

                flow[:, :, 0] = flow[:, :, 0] * (1.0 - band) + flow_smooth_x * band
                flow[:, :, 1] = flow[:, :, 1] * (1.0 - band) + flow_smooth_y * band
        # ★ 光流场低频化: 真实畸变场空间连续, 高频残余(含改色噪声)直接抹平
        # warp_smooth 分级:
        #   0.0 ~ 1.0  → 温和层(双边 sigmaColor 缩放 + 小核高斯), 1.0 时等价旧行为
        #   1.0 ~ 2.0  → 强力层(大核高斯 + 多尺度下采样低通), 物理上强制 flow 只剩极低频
        try:
            ws = float(warp_smooth)
        except (TypeError, ValueError):
            ws = 1.0
        ws = max(0.0, min(4.0, ws))

        # ★ 三档分段:
        #   [0, 1]  温和档 — 与旧行为完全一致
        #   (1, 2]  强力档 — 与旧行为完全一致(2 = 旧版"最保守"端点)
        #   (2, 4]  极强档 — 新增, ws=4 = 旧 ws=2 的 2 倍强度
        if ws <= 1.0:
            # 温和: 0→0.75, 1→1.5(=FLOW_DENOISE_PX, 旧默认)
            bs_sigma = self.FLOW_DENOISE_PX * (0.5 + ws)
            gk = int(round(5 + ws * 4)) | 1            # 5,7,9
            gs = 0.0
            ds_exp = 0.0                                # 无下采样
        elif ws <= 2.0:
            # 强力(旧行为): 1→1.5, 2→4.5
            bs_sigma = self.FLOW_DENOISE_PX * (1.5 + 3.0 * (ws - 1.0))
            gk = int(round(9 + (ws - 1.0) * 20)) | 1   # 9,19,29
            gs = (ws - 1.0) * 8.0                       # 0,4,8
            ds_exp = (ws - 1.0) * 2.0                   # 0,1,2 → 1x,2x,4x
        else:
            # 极强(新增): 2→4.5(=旧), 3→6.75, 4→9.0(=旧 ws=2 的 2 倍)
            bs_sigma = self.FLOW_DENOISE_PX * (4.5 + 4.5 * (ws - 2.0))
            gk = int(round(29 + (ws - 2.0) * 20)) | 1   # 29,39,49
            gs = 8.0 + (ws - 2.0) * 8.0                 # 8,12,16
            ds_exp = 2.0 + (ws - 2.0) * 1.0             # 2,3,4 → 4x,8x,16x
        bs_sigma = max(0.5, bs_sigma)

        flow[:, :, 0] = cv2.bilateralFilter(flow[:, :, 0], 7, bs_sigma, 7)
        flow[:, :, 1] = cv2.bilateralFilter(flow[:, :, 1], 7, bs_sigma, 7)

        flow[:, :, 0] = cv2.GaussianBlur(flow[:, :, 0], (gk, gk), gs)
        flow[:, :, 1] = cv2.GaussianBlur(flow[:, :, 1], (gk, gk), gs)

        # 多尺度低通: ds_exp > 0 才生效
        if ds_exp > 0.01:
            ds = 2.0 ** ds_exp
            h_f, w_f = flow.shape[:2]
            nh = max(8, int(round(h_f / ds)))
            nw = max(8, int(round(w_f / ds)))
            if nh < h_f or nw < w_f:
                for c in (0, 1):
                    down = cv2.resize(flow[:, :, c], (nw, nh), interpolation=cv2.INTER_AREA)
                    flow[:, :, c] = cv2.resize(down, (w_f, h_f), interpolation=cv2.INTER_LINEAR)


        s0 = self._align_score(merged_img, union_mask, original_bg, edit_mask=edit_mask)
        p0 = self._photometric_score(merged_img, union_mask, original_bg, edit_mask=edit_mask)
        if s0 >= 1e8 or p0 >= 1e8:
            print("[Smart Merge] 整图精修: 可靠未编辑参考不足, 跳过 | insufficient reliable reference")
            return merged_img
        best_out, best_s, best_dir = merged_img, s0, 0

        # ws 越大(越保守) → 光度约束越宽松, 让强平滑版即使轻微降质也被接受
        photometric_slack = 0.5 + max(0.0, ws - 1.0) * 2.0
        for sign in (-1.0,):
            map_x = grid_x + sign * flow[:, :, 0]
            map_y = grid_y + sign * flow[:, :, 1]
            out = cv2.remap(merged_img, map_x, map_y,
                            interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
            out_union = cv2.remap(union_mask, map_x, map_y,
                                  interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            out_edit = None
            if edit_mask is not None:
                out_edit = cv2.remap(edit_mask, map_x, map_y,
                                     interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
            sc = self._align_score(out, out_union, original_bg, edit_mask=out_edit)
            pc = self._photometric_score(out, out_union, original_bg, edit_mask=out_edit)
            min_improvement = max(0.2, 0.02 * best_s)
            if sc < best_s - min_improvement and pc <= p0 + photometric_slack:
                best_out, best_s, best_dir = out, sc, sign
                
        if best_dir != 0:
            print(f"[Smart Merge] 整图精修: 对齐评分 {s0:.1f}→{best_s:.1f} | polish accepted")
            return best_out
        print("[Smart Merge] 整图精修: 无改善, 保留原结果 | polish rejected")
        return merged_img



    def estimate_homography(self, query_img, train_img, device="cpu",
                            min_area_ratio=0.01, max_area_ratio=100.0,
                            min_edge_ratio=0.30, max_persp=0.35, min_cells=0):
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
        self._dlog(f"[Smart Merge] 匹配降采样: crop {w_q}x{h_q}→{query_m.shape[1]}x{query_m.shape[0]}, "
              f"BG {w_t}x{h_t}→{train_m.shape[1]}x{train_m.shape[0]} | matching downscale")

        def _clahe_rgb(img):
            """LAB 的 L 通道做 CLAHE，保持色度不变。返回 uint8 RGB。"""
            lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB)
            l, a, b = cv2.split(lab)
            l = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8)).apply(l)
            return cv2.cvtColor(cv2.merge([l, a, b]), cv2.COLOR_LAB2RGB)

        query_p = _clahe_rgb(query_m)
        train_p = _clahe_rgb(train_m)
        # 匹配前把分块的颜色分布拉向背景(只影响特征, 不参与合成):
        # 改色/偏色块的关键点描述子因此更接近未编辑内容, 减少“改色区特征主导 H”。
        query_p = self._match_histogram_rgb(query_p, train_p)
        img_q_tensor = torch.from_numpy(np.ascontiguousarray(query_p)).permute(2, 0, 1).float().to(device)[None] / 255.0
        img_t_tensor = torch.from_numpy(np.ascontiguousarray(train_p)).permute(2, 0, 1).float().to(device)[None] / 255.0

        # ========== DISK + LightGlue (唯一特征匹配方案) ==========
        features_q = features_t = None
        train_key = self._arr_fingerprint(train_p, "bg_disk")
        cached_t = self._disk_train_cache.get(train_key)
        try:
            disk, lg_matcher = self.get_kornia_models(device)
            if disk is not None and lg_matcher is not None:
                with torch.inference_mode():
                    features_q = disk(img_q_tensor, n=2048, pad_if_not_divisible=True)[0]
                    if cached_t is not None:
                        # 同一背景的 DISK 特征只算一次, 多分块复用
                        kps_t_t, desc_t = cached_t
                        kps_t_t = torch.from_numpy(kps_t_t).to(device)
                        desc_t = torch.from_numpy(desc_t).to(device)
                        if train_key in self._disk_train_cache_order:
                            self._disk_train_cache_order.remove(train_key)
                        self._disk_train_cache_order.append(train_key)
                    else:
                        features_t = disk(img_t_tensor, n=2048, pad_if_not_divisible=True)[0]
                        kps_t_t = features_t.keypoints
                        desc_t = features_t.descriptors
                        self._disk_train_cache[train_key] = (
                            kps_t_t.detach().cpu().numpy(), desc_t.detach().cpu().numpy())
                        self._disk_train_cache_order.append(train_key)
                        while len(self._disk_train_cache_order) > self._disk_train_cache_max:
                            old = self._disk_train_cache_order.pop(0)
                            self._disk_train_cache.pop(old, None)
                    kps_q_t = features_q.keypoints
                    if len(kps_q_t) >= 4 and len(kps_t_t) >= 4:
                        lafs_q = KF.laf_from_center_scale_ori(
                            kps_q_t[None], torch.ones(1, len(kps_q_t), 1, 1, device=device))
                        lafs_t = KF.laf_from_center_scale_ori(
                            kps_t_t[None], torch.ones(1, len(kps_t_t), 1, 1, device=device))
                        hw_q = torch.tensor(query_m.shape[:2], device=device)
                        hw_t = torch.tensor(train_m.shape[:2], device=device)
                        match_res = lg_matcher(
                            features_q.descriptors, desc_t,
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
        if H is None or inliers is None or int(np.sum(inliers)) < 8:
            return None, None, 0, None

        # ★ 用内点最小二乘重算 H，提高精度、减小重投影误差
        inl_mask = inliers.ravel().astype(bool)
        try:
            H_refit, _ = cv2.findHomography(pts_q[inl_mask], pts_t[inl_mask], 0)  # method=0
            if H_refit is not None and np.all(np.isfinite(H_refit)):
                H = H_refit
        except Exception:
            pass

        try:
            _ones = np.hstack([pts_q, np.ones((len(pts_q), 1))])
            _proj = (H @ _ones.T).T
            _proj = _proj[:, :2] / _proj[:, 2:]
            _err = np.linalg.norm(_proj - pts_t, axis=1)
            _keep = _err < 10.0      # ★ 15 → 10，内点更干净
            if int(_keep.sum()) >= 8:
                self._disk_pts_q = pts_q[_keep]
                self._disk_pts_t = pts_t[_keep]
        except Exception:
            self._disk_pts_q = None

        if H is None or inliers is None or np.sum(inliers) < 4:
            return None, None, 0, None
        if not self._homography_is_sane(
                H, h_q, w_q, h_t, w_t,
                max_persp=max_persp,
                min_edge_ratio=min_edge_ratio,
                min_area_ratio=min_area_ratio,
                max_area_ratio=max_area_ratio):
            print("[Smart Merge] 单应性矩阵异常(退化/镜像/过度形变), 放弃并降级 | Homography invalid (degenerate/mirrored/over-deformed), rejected and falling back")
            return None, None, 0, None
        if min_cells > 0:
            cells = self._points_spread_cells(self._disk_pts_q, w_q, h_q, n=4)
            if cells < min_cells:
                print(f"[Smart Merge] 特征内点空间扩散不足({cells}/16 格 < {min_cells}), "
                      f"视为局部假匹配 | inliers too clustered, rejected")
                self._disk_pts_q = None
                self._disk_pts_t = None
                return None, None, 0, None
        num_inliers = int(np.sum(inliers))
        method_used = self._match_level or "DISK"
        return H, inliers, num_inliers, method_used

    def perform_kornia_alignment(self, query_img, train_img, warp_method=False, optical_flow=False,
                                 device="cpu", preset_H=None, max_flow_px=None, use_tps=True, base_mask=None,
                                 is_grid_preset=False, bridge_H=None, crop_index=0, crop_total=1):

        h_q, w_q = query_img.shape[:2]
        h_t, w_t = train_img.shape[:2]
        
        self._last_edit_mask = None
        self._last_residual_px = None

        # ========== 粗对齐 ==========
        H = None
        method_used = None
        num_inliers = 0
        is_bridge = False
        
        preset_valid = preset_H is not None and self._homography_is_sane(
            preset_H, h_q, w_q, h_t, w_t,
            min_area_ratio=1e-4 if is_grid_preset else 0.01,
            max_area_ratio=1e4 if is_grid_preset else 100.0,
            min_edge_ratio=0.08 if is_grid_preset else 0.30,
            max_persp=0.90 if is_grid_preset else 0.35
        )
        if preset_valid:
            if is_grid_preset:
                # grid 坐标只是布局参考。有桥接 A 时优先用 A→BG 的实测放置;
                # 没有才退回 B→BG 特征匹配(带内点/偏离/评分三重门槛), 最后才是 grid 保底。
                H, method_used, num_inliers = self._resolve_grid_alignment(
                    query_img, train_img, base_mask, preset_H, bridge_H, device)
                is_bridge = True
            elif self._bridge_photometric_ok(preset_H, query_img, train_img):
                # 桥接 B→A→BG 逻辑保持原样
                H = preset_H
                method_used = "Bridge(B→A→BG)"
                num_inliers = -1
                is_bridge = True
        

        # ★ 前置生成结构 Mask
        if is_bridge:
            try:
                fg_pre = cv2.warpPerspective(query_img, H, (w_t, h_t), flags=cv2.INTER_LANCZOS4)
                pre_base = base_mask if base_mask is not None else np.ones((h_q, w_q), dtype=np.float32)
                mask_pre = cv2.warpPerspective(pre_base, H, (w_t, h_t), flags=cv2.INTER_LINEAR)
                self._last_edit_mask = self._compute_edit_mask(train_img, fg_pre, valid_mask=mask_pre)
                self._dlog(f"[Smart Merge] 预生成结构掩码: 阻断面积占比 {(self._last_edit_mask < 0.5).mean()*100:.1f}%")
            except Exception as e:
                print(f"[Smart Merge] 预生成掩码失败: {e}")
                self._last_edit_mask = None
        
        # === TPS 非刚性对齐路径（推荐主路径）===
        use_tps_path = (use_tps and preset_H is not None and is_bridge
                        and getattr(self, '_bridge_A_cached', None) is not None
                        and getattr(self, '_bridge_H_A2BG', None) is not None)
        if use_tps_path:
            pts_b, pts_a = self.match_with_loftr(query_img, self._bridge_A_cached, device)
            if pts_b is not None and len(pts_b) >= 8:
                pts_b, pts_a = self.filter_correspondences_local_affine(pts_b, pts_a)
                n_pts = len(pts_b)
                if n_pts < 8:
                    print(f"[Smart Merge] TPS: B↔A匹配不足({n_pts}点), 跳过 | too few matches")
                else:
                    ones_b = np.hstack([pts_b, np.ones((n_pts, 1))])
                    q = (H @ ones_b.T).T; q = q[:, :2] / q[:, 2:]
                    ones_a = np.hstack([pts_a, np.ones((n_pts, 1))])
                    t = (self._bridge_H_A2BG @ ones_a.T).T; t = t[:, :2] / t[:, 2:]
                    
                    base_mask_inner = base_mask if base_mask is not None else np.ones(query_img.shape[:2], dtype=np.float32)
                    warped_fg0 = cv2.warpPerspective(query_img, H, (w_t, h_t), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT101)
                    warped_mask0 = cv2.warpPerspective(base_mask_inner, H, (w_t, h_t), flags=cv2.INTER_LINEAR)
                    warped_fg, warped_mask = warped_fg0, warped_mask0

                    em_for_score = getattr(self, '_last_edit_mask', None)

                    # ★ TPS 点只做几何有效性筛选(越界/无覆盖)。
                    # 颜色编辑不影响对应关系; 用 edit_mask 过滤会把“尚未校正的畸变”
                    # 误判为“有意编辑”, 丢掉正确特征点导致 TPS 被跳过。
                    q_tps, t_tps = q, t
                    if len(q) > 4:
                        keep_idx = []
                        for i in range(len(q)):
                            px, py = q[i]
                            ipx, ipy = int(round(px)), int(round(py))
                            if (0 <= ipx < w_t and 0 <= ipy < h_t
                                    and warped_mask0[ipy, ipx] > 0.05):
                                keep_idx.append(i)

                        if len(keep_idx) >= 8:
                            keep_idx = np.array(keep_idx)
                            q_tps = q[keep_idx]
                            t_tps = t[keep_idx]
                            self._dlog(f"[Smart Merge] TPS 匹配点过滤(几何): 保留 {len(keep_idx)}/{n_pts} 点")

                    # ★ 执行 TPS; 前后候选都用同一份基础 edit_mask 评分, 保证比较公平
                    tps_used = False
                    g_base = None
                    if len(q_tps) >= 4:
                        tps_fg, tps_mask = self.warp_tps(
                            warped_fg0, warped_mask0, train_img, q_tps, t_tps, reg_lambda=1.5)
                        if tps_fg is not None:
                            g0_med, g0_p85 = self._flow_residual_score(warped_fg0, warped_mask0, train_img, edit_mask=em_for_score)
                            g1_med, g1_p85 = self._flow_residual_score(tps_fg, tps_mask, train_img, edit_mask=em_for_score)
                            p0t = self._photometric_score(warped_fg0, warped_mask0, train_img, edit_mask=em_for_score)
                            p1t = self._photometric_score(tps_fg, tps_mask, train_img, edit_mask=em_for_score)
                            scores_valid = max(g0_med, g0_p85, g1_med, g1_p85, p0t, p1t) < 1e8
                            if scores_valid and g1_med <= g0_med + 0.5 and g1_p85 <= g0_p85 + 1.0 and p1t <= p0t + 2.0:
                                warped_fg, warped_mask = tps_fg, tps_mask
                                tps_used = True
                                print(f"[Smart Merge] TPS 验收通过: 几何残差 {g0_med:.2f}px→{g1_med:.2f}px "
                                      f"(p85 {g0_p85:.2f}→{g1_p85:.2f}) | TPS accepted")
                            else:
                                g_base = g0_med
                                print(f"[Smart Merge] TPS 拒绝: 几何残差 {g0_med:.2f}px→{g1_med:.2f}px "
                                      f"(p85 {g0_p85:.2f}→{g1_p85:.2f}), 光度 {p0t:.1f}→{p1t:.1f} | TPS rejected")
                    else:
                        print(f"[Smart Merge] TPS 跳过，仅使用基础对齐 | TPS skipped, using base alignment")

                    # ★ 二阶段精校
                    # if second_pass:
                        # fg2, mask2 = self.refine_second_pass(
                            # warped_fg, warped_mask, train_img, device, max_disp=16.0)
                        # if fg2 is not None:
                            # g2a, _ = self._flow_residual_score(warped_fg, warped_mask, train_img, edit_mask=em_for_score)
                            # g2b, _ = self._flow_residual_score(fg2, mask2, train_img, edit_mask=em_for_score)
                            # p2a = self._photometric_score(warped_fg, warped_mask, train_img, edit_mask=em_for_score)
                            # p2b = self._photometric_score(fg2, mask2, train_img, edit_mask=em_for_score)
                            # if g2b <= g2a - 0.2 and p2b <= p2a + 0.5:
                                # warped_fg, warped_mask = fg2, mask2
                                # print(f"[Smart Merge] 二阶段精校通过 ({g2a:.2f}px→{g2b:.2f}px) | pass2 accepted")
                            # else:
                                # print(f"[Smart Merge] 二阶段精校无改善 ({g2a:.2f}px→{g2b:.2f}px) | pass2 rejected")

                    if tps_used or self._last_edit_mask is None:
                        self._last_edit_mask = self._compute_edit_mask(
                            train_img, warped_fg, valid_mask=warped_mask
                        )
                    em_for_score = self._last_edit_mask

                    # ★ 逐块光流精修
                    if warp_method:
                        fg_r, mask_r = self.refine_with_optical_flow(
                            warped_fg, warped_mask, train_img, optical_flow=optical_flow,
                            device=device, max_flow_px=10.0, edit_mask=em_for_score)   
                        em_refined = self._compute_edit_mask(train_img, fg_r, valid_mask=mask_r)
                        # TPS 被拒时 warped_fg 未变, 基线残差直接复用, 不必重算
                        g0m = (self._flow_residual_score(
                            warped_fg, warped_mask, train_img, edit_mask=em_for_score)[0]
                            if g_base is None else g_base)
                        g1m, _ = self._flow_residual_score(fg_r, mask_r, train_img, edit_mask=em_refined)
                        if g1m < g0m - 0.05:
                            warped_fg, warped_mask = fg_r, mask_r
                            self._last_residual_px = g1m
                            print(f"[Smart Merge] 逐块光流生效: {g0m:.2f}px→{g1m:.2f}px | per-crop flow accepted")
                        else:
                            self._last_residual_px = g0m
                            print(f"[Smart Merge] 逐块光流拒绝: {g0m:.2f}px→{g1m:.2f}px | per-crop flow rejected")
                    self._match_level = "TPS+LoFTR"
                    return warped_fg, warped_mask, True


        # 无 grid / 桥接不可用 → B→BG 直配(带候选竞争与放置兜底)
        if H is None:
            H, b2bg_method, b2bg_resid = self._select_b2bg_homography(
                query_img, train_img, base_mask, device,
                crop_index=crop_index, crop_total=crop_total)
            if H is None:
                return None, None, False
            method_used = b2bg_method
            print(f"[Smart Merge] B→BG 对齐: {method_used} (残差 {b2bg_resid:.2f}px) | "
                  f"B→BG alignment via {method_used}")

        if base_mask is None:
            base_mask = np.ones((h_q, w_q), dtype=np.float32)
        warped_fg = cv2.warpPerspective(
            query_img, H, (w_t, h_t),
            flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT101
        )
        warped_mask = cv2.warpPerspective(
            base_mask, H, (w_t, h_t),
            flags=cv2.INTER_LINEAR
        )
        self._last_edit_mask = self._compute_edit_mask(
            train_img, warped_fg, valid_mask=warped_mask
        )

        if use_tps and getattr(self, "_disk_pts_q", None) is not None and len(self._disk_pts_q) >= 8:
            try:
                _ones = np.hstack([self._disk_pts_q, np.ones((len(self._disk_pts_q), 1))])
                q = (H @ _ones.T).T
                q = q[:, :2] / q[:, 2:]
                t = self._disk_pts_t
                reliable = []
                for idx, (px, py) in enumerate(q):
                    ix, iy = int(round(px)), int(round(py))
                    if (0 <= ix < w_t and 0 <= iy < h_t
                            and warped_mask[iy, ix] > 0.5):
                        reliable.append(idx)
                if len(reliable) < 8:
                    # 掩码覆盖不足时退回全部 H 内点; 颜色编辑不参与几何筛选
                    reliable = list(range(len(q)))
                q, t = q[reliable], t[reliable]

                # ★ 可靠区外推: 改色区内的特征不可信时, 只用未改色区(且局部一致)的点建 TPS,
                # 其余区域由薄板样条的平滑场外推, 继承正确区域的校正量。
                q, t, extrapolated = self._filter_reliable_correspondences(
                    q, t, h_t, w_t, self._last_edit_mask)
                if extrapolated:
                    print(f"[Smart Merge] 可靠区外推: 仅用 {len(q)} 个未改色区对应点建场 | "
                          f"reliable-region TPS")

                tps_fg, tps_mask = self.warp_tps(
                    warped_fg, warped_mask, train_img, q, t, reg_lambda=1.5)
                if tps_fg is not None:
                    g0_med, g0_p85 = self._flow_residual_score(
                        warped_fg, warped_mask, train_img, edit_mask=self._last_edit_mask)
                    g1_med, g1_p85 = self._flow_residual_score(
                        tps_fg, tps_mask, train_img, edit_mask=self._last_edit_mask)
                    scores_valid = max(g0_med, g0_p85, g1_med, g1_p85) < 1e8
                    # 外推时全图统计里必然包含“改色区”的残差, 门槛需与基线同等严格
                    slack_med = 0.1 if extrapolated else 0.5
                    slack_p85 = 0.4 if extrapolated else 1.0
                    if (scores_valid and g1_med <= g0_med + slack_med
                            and g1_p85 <= g0_p85 + slack_p85):
                        warped_fg, warped_mask = tps_fg, tps_mask
                        print(f"[Smart Merge] TPS(DISK内点) 通过: {g0_med:.2f}px→{g1_med:.2f}px"
                              f"{' (可靠区外推)' if extrapolated else ''} | TPS accepted")
                    else:
                        print(f"[Smart Merge] TPS(DISK内点) 拒绝: {g0_med:.2f}px→{g1_med:.2f}px | TPS rejected")
            except Exception as e:
                print(f"[Smart Merge] TPS(DISK内点) 失败: {e} | TPS failed")

        # ===== 兜底：H（或Grid）+ 光流精修 =====
        if warp_method:
            self._last_edit_mask = self._compute_edit_mask(
                train_img, warped_fg, valid_mask=warped_mask
            )
            em_for_score = self._last_edit_mask
            g0m, g0p = self._flow_residual_score(warped_fg, warped_mask, train_img, edit_mask=em_for_score)
            self._last_residual_px = g0m
            if g0m < 1.2:
                self._dlog(f"[Smart Merge] H后残差已很小({g0m:.2f}px), 跳过光流精修 | residual tiny, flow skipped")
                return warped_fg, warped_mask, True
                
            refined_fg, refined_mask = self.refine_with_optical_flow(
                warped_fg, warped_mask, train_img, optical_flow, device,
                edit_mask=em_for_score
            )
            em_refined = self._compute_edit_mask(train_img, refined_fg, valid_mask=refined_mask)
            g1m, g1p = self._flow_residual_score(refined_fg, refined_mask, train_img, edit_mask=em_refined)

            if g1m < g0m - 0.3 and g1p <= g0p + 0.5:
                self._last_residual_px = g1m
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

    @staticmethod
    def seamless_clone_crop(fg, bg, mask_float):
        mask_8u = (np.clip(mask_float, 0, 1) * 255).astype(np.uint8)
        mask_8u = cv2.erode(mask_8u, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        bx, by, bw, bh = cv2.boundingRect(mask_8u)
        h, w = mask_8u.shape
        safe_pad = 5
        if not (bw > 10 and bh > 10 and bx > safe_pad and by > safe_pad
                and bx + bw < w - safe_pad and by + bh < h - safe_pad):
            return fg, False
        x1, y1 = bx - safe_pad, by - safe_pad
        x2, y2 = bx + bw + safe_pad, by + bh + safe_pad
        center = ((x2 - x1) // 2, (y2 - y1) // 2)
        try:
            cloned = cv2.seamlessClone(
                fg[y1:y2, x1:x2], bg[y1:y2, x1:x2], mask_8u[y1:y2, x1:x2],
                center, cv2.NORMAL_CLONE
            )
        except Exception as e:
            print(f"[Smart Merge] 泊松融合失败: {e} | Poisson seamless clone failed: {e}")
            return fg, False
        result = bg.copy()
        result[y1:y2, x1:x2] = cloned
        return result, True

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
                    use_tps=True, warp_smooth=1.0, merge_mode="All to One", use_gpu=False, force_recompute=False,
                    original_crop_A=None, split_grid=None, unique_id=None, prompt=None, extra_pnginfo=None):

        # INPUT_IS_LIST 模式下, 所有输入(含控件/隐藏参数)都可能以 list 形式到达 → 解包为标量
        warp_method = self._unwrap_scalar(warp_method, False)
        color_match = self._unwrap_scalar(color_match, "Alpha Soft Blend")
        optical_flow = self._unwrap_scalar(optical_flow, False)
        use_tps = self._unwrap_scalar(use_tps, True)
        warp_smooth = self._unwrap_scalar(warp_smooth, 1.0)
        feather_kernel = self._unwrap_scalar(feather_kernel, 20)
        merge_mode = self._unwrap_scalar(merge_mode, "All to One")
        use_gpu = self._unwrap_scalar(use_gpu, False)
        force_recompute = self._unwrap_scalar(force_recompute, False)
        unique_id = self._unwrap_scalar(unique_id)
        prompt = self._unwrap_scalar(prompt)
        extra_pnginfo = self._unwrap_scalar(extra_pnginfo)
        split_grid = self._unwrap_scalar(split_grid)

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
            merge_mode, use_gpu, use_tps, split_grid=split_grid
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

        # ============================================================
        # 若连接 split_grid，启用 ElementTileMerge 式 alpha 累加
        # ============================================================
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
        except Exception:
            WORK_W = WORK_H = 0
        
        USE_WORK_CANVAS = (split_grid is not None) and WORK_W > 0 and WORK_H > 0
        
        if USE_WORK_CANVAS:
            _inv_scale = 1.0
            print(f"[SmartMerge] 使用 split_grid work 画布: {WORK_W}x{WORK_H} (tile 坐标保持 out 空间) | using work canvas")
        else:
            _inv_scale = 1.0 / GRID_U_UP
            print(f"[SmartMerge] 回退到原行为: tile 坐标反变换 (1/unified_upscale={_inv_scale:.3f}), 原图尺寸保持不变")

        def _tile_info_to_src(ti):
            """把 grid tile 的坐标从输出空间缩放到源空间（SmartMerge 的 original_bg 尺寸）。"""
            if ti is None:
                return None
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
                "mask":        ti.get("mask"),          
                "kind":        ti.get("kind", "layer"), 
                "layer":       ti.get("layer", 0),      
            }

        print(f"[SmartMerge] grid coordinate scale: unified_upscale={GRID_U_UP:.3f}")
        
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

        for i in range(B_orig_loop):
            try:
                img_bg = self._item_to_uint8_rgb(items_orig[i])

                # split_grid，原图 resize 到 work 画布，与 ElementTileMerge 行为一致
                if USE_WORK_CANVAS and (img_bg.shape[1] != WORK_W or img_bg.shape[0] != WORK_H):
                    print(f"[Smart Merge] original_image {img_bg.shape[1]}x{img_bg.shape[0]} → "
                          f"{WORK_W}x{WORK_H} (match split_grid work canvas)")
                    img_bg = cv2.resize(img_bg, (WORK_W, WORK_H), interpolation=cv2.INTER_LANCZOS4)
                
                start_idx = i * crops_per_bg
                end_idx = min(start_idx + crops_per_bg, B_crop)
                if start_idx >= B_crop:
                    result_images.append(torch.from_numpy(img_bg.astype(np.float32) / 255.0))
                    continue

                original_bg = img_bg.copy()
                # 布局观测只对同一张图有效(B→BG 模式下用于反推格子步长)
                self._b2bg_layout_obs = {}
                skipped_tiles = []
                crop_residuals = []
                union_mask = np.zeros(img_bg.shape[:2], dtype=np.float32)
                union_edit_mask = np.ones(img_bg.shape[:2], dtype=np.float32)
                
                # split_grid 时用累加器代替逐 crop 覆盖（保持色彩匹配与对齐逻辑不变）
                if use_grid_alpha:
                    grid_bg_canvas = np.zeros(img_bg.shape[:2] + (3,), dtype=np.float32)
                    grid_bg_weight = np.zeros(img_bg.shape[:2] + (1,), dtype=np.float32)
                    grid_layer_canvas = {}   # layer_idx -> (H,W,3) f32
                    grid_layer_weight = {}   # layer_idx -> (H,W,1) f32
                else:
                    grid_bg_canvas = grid_bg_weight = None
                    grid_layer_canvas = grid_layer_weight = None
                
                img_result = img_bg.copy()

                # 倒序循环贴
                for crop_idx in range(end_idx - 1, start_idx - 1, -1):
                    if pbar is not None:
                        pbar.update(1)

                    img_fg = self._item_to_uint8_rgb(items_B[crop_idx])
                    h_fg, w_fg = img_fg.shape[:2]

                    # === 提取 split 节点传来的像素级 mask ===
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
                        self._last_residual_px = cached_residual
                    
                    else:
                        img_bridge_A = None
                        if items_A is not None and crop_idx < len(items_A):
                            img_bridge_A = self._item_to_uint8_rgb(items_A[crop_idx])

                        success_align = False
                        warped_fg = None
                        warped_mask = None

                        # ★ 优先检查 split_grid：如果存在，直接用它的坐标生成绝对正确的 H
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
                            # 作为主对齐; grid 负责在没有 A 或桥接失败时兜底。
                            H_bridge = None
                            self._bridge_A_cached = img_bridge_A
                            self._bridge_H_A2BG = None
                            if img_bridge_A is not None:
                                h_A, w_A = img_bridge_A.shape[:2]
                                H_A_to_BG = self.perform_sift_alignment(img_bridge_A, original_bg)
                                if (H_A_to_BG is not None and h_A > 0 and w_A > 0
                                        and self._bridge_photometric_ok(
                                            H_A_to_BG, img_bridge_A, original_bg)):
                                    sx, sy = w_A / float(w_fg), h_A / float(h_fg)
                                    H_FG_to_A = np.array([
                                        [sx, 0, 0],
                                        [0, sy, 0],
                                        [0, 0, 1]
                                    ], dtype=np.float64)
                                    H_bridge = np.dot(H_A_to_BG, H_FG_to_A)
                                    self._bridge_H_A2BG = H_A_to_BG
                                elif H_A_to_BG is not None:
                                    print("[Smart Merge] 桥接 A→BG 光度校验未通过, 本轮退化到 grid 锚定 | bridge A→BG failed photometric check, using grid anchor")

                            warped_fg, warped_mask, success_align = self.perform_kornia_alignment(
                                img_fg, original_bg,
                                warp_method=warp_method,
                                optical_flow=optical_flow, device=device,
                                preset_H=H_grid,
                                use_tps=use_tps,
                                base_mask=crop_idx_mask,
                                is_grid_preset=True,
                                bridge_H=H_bridge
                            )
                            if success_align:
                                print("[Smart Merge] split_grid 对齐完成 | Grid alignment done")
                                
                        # 桥接对齐: B → A → BG / Bridge alignment: B → A → BG
                        elif img_bridge_A is not None:
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
                                        use_tps=use_tps,
                                        base_mask=crop_idx_mask,
                                        crop_index=crop_idx - start_idx,
                                        crop_total=end_idx - start_idx
                                    )
                                    if success_align:
                                        print("[Smart Merge] 桥接对齐 B→A→BG 完成 (含畸变校正) | Bridge alignment B→A→BG done (with deformation correction)")


                        if not success_align:
                            warped_fg, warped_mask, ok = self.perform_kornia_alignment(
                                img_fg, original_bg,
                                warp_method=warp_method,
                                optical_flow=optical_flow, use_tps=use_tps, device=device,
                                base_mask=crop_idx_mask,
                                crop_index=crop_idx - start_idx,
                                crop_total=end_idx - start_idx
                            )
                            if ok:
                                success_align = True
                            else:
                                # 没有任何可靠放置(特征/模板/布局先验全部不成立):
                                # 硬贴到画布中心会毁掉整图, 宁可跳过这一块。
                                print(f"[Smart Merge] 分块 {crop_idx} 无可靠放置, 跳过以保护整图 | "
                                      f"tile {crop_idx} skipped: no reliable placement")
                                skipped_tiles.append(crop_idx)
                                continue

                    # 编辑置信度只由 original_bg + warped_fg 决定, 命中缓存时直接复用。
                    if cached_edit_mask is not None and cached_edit_mask.shape == original_bg.shape[:2]:
                        self._last_edit_mask = cached_edit_mask.copy()
                    else:
                        self._last_edit_mask = self._compute_edit_mask(
                            original_bg, warped_fg, valid_mask=warped_mask
                        )
                    if cached_residual is not None:
                        self._last_residual_px = cached_residual

                    if new_aligns_to_save is not None:
                        new_aligns_to_save[crop_idx] = {
                            "warped_fg": warped_fg.copy(),
                            "warped_mask": warped_mask.copy(),
                            "edit_mask": self._last_edit_mask.copy() if self._last_edit_mask is not None else None,
                            "residual": getattr(self, "_last_residual_px", None),
                        }

                    # 逐块对齐残差(px): 整图精修只在残差确实存在时才有意义
                    resid = getattr(self, "_last_residual_px", None)
                    if resid is not None:
                        crop_residuals.append(float(resid))

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
                    crop_edit_mask = self._last_edit_mask[ymin:ymax, xmin:xmax]

                    h_crop, w_crop = crop_bg.shape[:2]
                    crop_result = crop_bg.copy()
                    current_color_match = color_match

                    # 色彩校正的施加权重: 随 feather_kernel 从 mask 边界(含倒角)向内衰减。
                    # 校正量若在边界硬切, 相邻分块的校正差会在接缝/倒角处暴露成台阶。
                    # 画布边缘侧因 crop 外扩 + replicate 填充, 不会误衰减。
                    color_apply_mask = self.make_edge_safe_soft_mask(
                        crop_mask_float, int(max(0, feather_kernel)))
                    color_weight_mask = color_apply_mask

                    # ===== 色彩迁移(以 crop_bg 为参考) =====
                    if current_color_match == "Patch_based_color":
                        band_width = max(15, int(feather_kernel))
                        crop_fg = self.boundary_aware_color_sync(
                            crop_fg, crop_bg, crop_mask_float, band_width=band_width,
                            edit_mask=crop_edit_mask
                        )
                        try:
                            crop_fg = self.patch_based_color_sync(
                                crop_fg, crop_bg, crop_mask_float,
                                patch_size=max(32, int(feather_kernel) * 2),
                                overlap=max(16, int(feather_kernel)),
                                edit_mask=crop_edit_mask,
                                apply_mask=color_apply_mask
                            )
                        except Exception as e:
                            print(f"[Smart Merge] Patch 色彩匹配失败: {e}, 降级 Alpha | Patch color sync failed: {e}, downgraded to Alpha")
                        current_color_match = "Alpha Soft Blend"
                    
                    elif current_color_match == "Edge_Weighted_Color":
                        # 【关键】改用 color_weight_mask 做边缘统计
                        crop_fg = self.edge_weighted_color_sync(
                            crop_fg, crop_bg, color_weight_mask, edit_mask=crop_edit_mask
                        )
                        current_color_match = "Alpha Soft Blend"
                    elif current_color_match == "LAB_Mean":
                        color_sample_mask = self._color_sample_mask(crop_mask_float, crop_edit_mask)
                        if color_sample_mask is not None:
                            lab_bg = cv2.cvtColor(crop_bg, cv2.COLOR_RGB2LAB).astype(np.float32)
                            lab_fg = cv2.cvtColor(crop_fg, cv2.COLOR_RGB2LAB).astype(np.float32)
                            stats_mask = color_sample_mask > 0.5
                            bg_values = lab_bg[stats_mask].astype(np.float64)
                            fg_values = lab_fg[stats_mask].astype(np.float64)
                            mean_bg = bg_values.mean(axis=0)
                            mean_fg = fg_values.mean(axis=0)
                            std_bg = (np.percentile(bg_values, 90, axis=0)
                                      - np.percentile(bg_values, 10, axis=0)) / 2.563103
                            std_fg = (np.percentile(fg_values, 90, axis=0)
                                      - np.percentile(fg_values, 10, axis=0)) / 2.563103

                            std_fg = np.maximum(std_fg, 1.0)
                            std_bg = np.maximum(std_bg, 1.0)
                            scale = std_bg.flatten() / std_fg.flatten()
                            scale[0] = np.clip(scale[0], 0.5, 2.0)
                            scale[1] = np.clip(scale[1], 0.8, 1.25)
                            scale[2] = np.clip(scale[2], 0.8, 1.25)

                            lab_fg = (lab_fg - mean_fg.flatten()) * scale + mean_bg.flatten()
                            lab_fg = np.clip(lab_fg, 0, 255).astype(np.uint8)
                            crop_fg = cv2.cvtColor(lab_fg, cv2.COLOR_LAB2RGB)
                        current_color_match = "Alpha Soft Blend"

                    if self.GRID_ACCUM_BLEND and use_grid_alpha:
                        if current_color_match == "Laplacian Pyramid Blend":
                            num_levels = 3 if feather_kernel < 16 else (5 if feather_kernel > 64 else 4)
                            soft_mask = self.make_edge_safe_soft_mask(crop_mask_float, feather_kernel)
                            crop_fg = self.laplacian_pyramid_blend(crop_fg, crop_bg, soft_mask, num_levels)
                            current_color_match = "Alpha Soft Blend"
                        elif current_color_match == "SeamlessClone (PS Auto Blend)":
                            crop_fg, _ = self.seamless_clone_crop(crop_fg, crop_bg, crop_mask_float)
                            current_color_match = "Alpha Soft Blend"

                    # ===== 融合：grid 累加 or 原生融合 =====
                    # ★ grid 只提供 alpha(mask)与对齐锚点；融合走原生覆盖式逻辑
                    use_grid_alpha_this = False
                    if self.GRID_ACCUM_BLEND and use_grid_alpha:
                        tile_info = grid_tiles[crop_idx] if crop_idx < len(grid_tiles) else None
                        if tile_info is not None:
                            use_grid_alpha_this = True
                    
                            # ===== 精确复刻 ElementTileMerge 的权重构造（nodes_merge.py L285-350） =====
                            grid_overlap = int((split_grid or {}).get("overlap", 0))
                    
                            # Step 1 (L285-291): 强制 fade = overlap（贴边 fade=0 保持 0 → 权重=1）
                            ti = dict(tile_info)
                            if grid_overlap > 0:
                                if ti.get("fade_top", 0)    > 0: ti["fade_top"]    = grid_overlap
                                if ti.get("fade_bottom", 0) > 0: ti["fade_bottom"] = grid_overlap
                                if ti.get("fade_left", 0)   > 0: ti["fade_left"]   = grid_overlap
                                if ti.get("fade_right", 0)  > 0: ti["fade_right"]  = grid_overlap
                    
                            # 参数桥接：feather_kernel(像素) → feather_frac(∈[0,1])
                            #   ETM 的 feather 默认 1.0 (对应 feather_kernel = overlap)
                            feather_frac = float(feather_kernel) / float(max(grid_overlap, 1))
                            feather_frac = max(0.0, min(1.0, feather_frac))
                    
                            bbox = (xmin, ymin, xmax, ymax)
                    
                            # Step 2 (L293): fade 权重 = _tile_weight(info, feather)
                            fade_w = self._tile_weight_local(ti, bbox, feather_frac)
                    
                            # Step 3+4 (L321-350): tile_mask pad replicate + 高斯羽化
                            mask_f = self._feather_tile_mask_like_etm(
                                crop_mask_float, bbox, h_bg, w_bg,
                                ti.get("fade_top", 0), ti.get("fade_bottom", 0),
                                ti.get("fade_left", 0), ti.get("fade_right", 0),
                                grid_overlap, feather_frac)
                    
                            # Step 5 (L350): 合成权重 = fade × tile_mask_feathered
                            weight_local = fade_w * mask_f
                    
                            # ===== 累加（与 ETM L380-400 完全一致）=====
                            tile_kind = ti.get("kind", "layer")
                            tile_layer = int(ti.get("layer") or 0)
                    
                            if tile_kind in {"gap", "fallback", "unified"} or tile_layer < 0:
                                grid_bg_canvas[ymin:ymax, xmin:xmax] += crop_fg.astype(np.float32) * weight_local
                                grid_bg_weight[ymin:ymax, xmin:xmax] += weight_local
                            else:
                                if tile_layer not in grid_layer_canvas:
                                    grid_layer_canvas[tile_layer] = np.zeros(img_bg.shape[:2] + (3,), dtype=np.float32)
                                    grid_layer_weight[tile_layer] = np.zeros(img_bg.shape[:2] + (1,), dtype=np.float32)
                                grid_layer_canvas[tile_layer][ymin:ymax, xmin:xmax] += crop_fg.astype(np.float32) * weight_local
                                grid_layer_weight[tile_layer][ymin:ymax, xmin:xmax] += weight_local

                    # 只有当没有走 grid 分支时，才执行原有的融合逻辑
                    if not use_grid_alpha_this:
                    
                    
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
                            crop_result, clone_ok = self.seamless_clone_crop(crop_fg, crop_bg, crop_mask_float)
                            current_color_match = "__DONE__" if clone_ok else "Alpha Soft Blend"
                        
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
                        em = getattr(self, '_last_edit_mask', None)
                        if em is not None and em.shape == union_edit_mask.shape:
                            union_edit_mask = np.minimum(union_edit_mask, em)
                        img_bg = img_result.copy()
                    else:
                        union_mask = np.maximum(union_mask, warped_mask)
                        em = getattr(self, '_last_edit_mask', None)
                        if em is not None and em.shape == union_edit_mask.shape:
                            union_edit_mask = np.minimum(union_edit_mask, em)
                
                # ===== 循环结束: split_grid 模式下把累加器归一化为最终图像 =====
                if skipped_tiles:
                    print(f"[Smart Merge] 本次跳过 {len(skipped_tiles)} 个分块 {skipped_tiles}: "
                          f"对应的 AI 编辑不会出现在成品中, 这些区域保留原图 | "
                          f"tiles {skipped_tiles} not merged (original content kept)")
                
                # ★ canvas 已不再填充(修改1短路了累加), 此段必须一并跳过;
                #   若只改融合不改这里, canvas/weight 全 0 → merged = original_bg, 编辑全部丢失!
                if self.GRID_ACCUM_BLEND and use_grid_alpha:
                    bg_alpha = np.clip(grid_bg_weight, 0.0, 1.0)

                    bg_img = grid_bg_canvas / np.maximum(grid_bg_weight, 1e-6)
                    merged_grid = bg_img * bg_alpha + original_bg.astype(np.float32) * (1.0 - bg_alpha)

                    # 2) 手绘层按 layer_idx 从大到小 alpha over（完全复刻 ElementTileMerge）
                    for layer_idx in sorted(grid_layer_canvas.keys(), reverse=True):
                        lc = grid_layer_canvas[layer_idx]
                        lw = grid_layer_weight[layer_idx]
                        layer_img = lc / np.maximum(lw, 1e-6)
                        layer_alpha = np.clip(lw, 0.0, 1.0)
                        merged_grid = layer_img * layer_alpha + merged_grid * (1.0 - layer_alpha)

                    img_result = np.clip(merged_grid, 0, 255).astype(np.uint8)
                    img_bg = img_result.copy()
                
                # 整图光流精修: 逐块对齐残差已足够小时没有可修的位移, 直接跳过
                skip_polish = False
                if crop_residuals:
                    max_resid = max(crop_residuals)
                    if max_resid < self.POLISH_SKIP_RESID_PX:
                        skip_polish = True
                        print(f"[Smart Merge] 逐块对齐残差 {max_resid:.2f}px < "
                              f"{self.POLISH_SKIP_RESID_PX}px, 跳过整图精修 | polish skipped (tile residuals tiny)")
                if union_mask.max() > 0.5 and warp_method and not skip_polish:
                    try:
                        polish_edit_mask = union_edit_mask if union_edit_mask.min() < 0.99 else None
                        img_result = self.global_flow_polish(
                            img_result, original_bg, union_mask, edit_mask=polish_edit_mask,
                            warp_smooth=warp_smooth, optical_flow=optical_flow)
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
