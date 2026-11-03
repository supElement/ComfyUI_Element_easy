# -*- coding: utf-8 -*-
# Smart Merge 公共工具: 进度条/日志/缓存/设备与张量基础操作

import os
import sys

import torch
import torch.nn.functional as F
import numpy as np
import cv2

try:
    from comfy.utils import ProgressBar
    HAS_PROGRESS_BAR = True
except ImportError:
    HAS_PROGRESS_BAR = False

try:
    from tqdm.auto import tqdm as _tqdm
except Exception:
    _tqdm = None

# 当前运行中的进度条: 调试日志与状态行通过它写入, 避免打断单行进度显示
_ACTIVE_PROGRESS = None
# 由 Smart_merge_images 在类定义后注册为 SmartMergeImages._dlog
_LOG_HOOK = None


def set_active_progress(pbar):
    global _ACTIVE_PROGRESS
    _ACTIVE_PROGRESS = pbar


def set_log_hook(fn):
    global _LOG_HOOK
    _LOG_HOOK = fn


def _sm_note(msg):
    """状态行: 有条时写到进度条上方, 否则直接打印。"""
    if _ACTIVE_PROGRESS is not None:
        _ACTIVE_PROGRESS.write(msg)
    else:
        print(msg)


def _sm_debug_write(*args, **kwargs):
    """DEBUG 日志落地: 有条时写到进度条上方, 否则直接 print。"""
    if _ACTIVE_PROGRESS is not None:
        _ACTIVE_PROGRESS.write(" ".join(str(a) for a in args))
    else:
        print(*args, **kwargs)


def _sm_log(*args, **kwargs):
    """调试日志: 交给 SmartMergeImages._dlog, 由它的 DEBUG 开关决定是否输出。"""
    hook = _LOG_HOOK
    if hook is not None:
        hook(*args, **kwargs)


class _MergeProgress:
    """单行进度条: 每个分块的匹配+合成算一步, 整图精修算一步。

    同时驱动 ComfyUI 前端进度(ProgressBar hook)与后台单行进度条(tqdm)。
    输出的条数 = 分块数 + (Optical_Flow 开时 1 步整图精修)。
    """

    def __init__(self, total):
        self.total = max(1, int(total))
        self.current = 0
        self._hook = ProgressBar(self.total) if HAS_PROGRESS_BAR else None
        self._bar = None
        if _tqdm is not None:
            self._bar = _tqdm(total=self.total, desc="Smart Merge", unit="step",
                              dynamic_ncols=True, file=sys.stdout)

    def step(self, desc=None):
        if desc is not None and self._bar is not None:
            self._bar.set_description(desc)
        self.current = min(self.total, self.current + 1)
        if self._hook is not None:
            self._hook.update_absolute(self.current, self.total)
        if self._bar is not None:
            self._bar.n = self.current
            self._bar.refresh()

    def write(self, msg):
        if self._bar is not None:
            self._bar.write(msg)
        else:
            print(msg)

    def close(self):
        if self._bar is not None:
            self._bar.close()


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


class _LRUCache:
    """dict 接口的定长 LRU: 读/写都会刷新最近使用顺序。
    对齐结果、SIFT 背景特征、DISK 背景特征三处共用这一份实现。"""

    def __init__(self, max_items):
        self._max = int(max_items)
        self._data = {}
        self._order = []

    def _touch(self, key):
        if key in self._order:
            self._order.remove(key)
        self._order.append(key)

    def get(self, key, default=None):
        if key in self._data:
            self._touch(key)
            return self._data[key]
        return default

    def __getitem__(self, key):
        val = self.get(key, _MISSING)
        if val is _MISSING:
            raise KeyError(key)
        return val

    def __setitem__(self, key, value):
        self._data[key] = value
        self._touch(key)
        while len(self._order) > self._max:
            self._data.pop(self._order.pop(0), None)

    def __contains__(self, key):
        return key in self._data

    def __len__(self):
        return len(self._data)

    def keys(self):
        return self._data.keys()

    def clear(self):
        self._data.clear()
        self._order.clear()


_MISSING = object()


class _GridCompositor:
    """split_grid 分块融合: 同一画布内按覆盖式(alpha over)累加, 不做加权平均。

    各分块是**独立 AI 编辑**的结果, overlap 区里两块内容并不相同; 求和归一化
    会在整条 overlap 带里把两个版本平均成雾状/重影, 且 feather 只影响两端 ramp,
    中间平台越宽(overlap - 2*feather)重影越明显。覆盖式合成只保留一个来源,
    过渡带宽度完全由权重(羽化)决定。
    """

    def __init__(self, shape):
        self._shape = tuple(shape[:2])
        self._bg_rgb = None
        self._bg_alpha = None
        self._layers = {}   # layer_idx -> (预乘颜色(H,W,3), 覆盖度(H,W,1))

    def _slot(self, layer):
        if layer is None:
            if self._bg_rgb is None:
                self._bg_rgb = np.zeros(self._shape + (3,), np.float32)
                self._bg_alpha = np.zeros(self._shape + (1,), np.float32)
            return self._bg_rgb, self._bg_alpha
        if layer not in self._layers:
            self._layers[layer] = (np.zeros(self._shape + (3,), np.float32),
                                   np.zeros(self._shape + (1,), np.float32))
        return self._layers[layer]

    def add(self, fg, weight, bbox, layer=None):
        """预乘 alpha-over: 后加入的分块只在权重大处压过先加入的, 互补 ramp 覆盖度累加到 1。"""
        xmin, ymin, xmax, ymax = bbox
        rgb, alpha = self._slot(layer)
        w = weight if weight.ndim == 3 else weight[:, :, None]
        w = np.clip(w.astype(np.float32, copy=False), 0.0, 1.0)
        region = rgb[ymin:ymax, xmin:xmax]
        region *= (1.0 - w)
        region += fg.astype(np.float32) * w
        a = alpha[ymin:ymax, xmin:xmax]
        a *= (1.0 - w)
        a += w

    @staticmethod
    def _composite_over(dst, src_rgb, src_alpha):
        a = np.clip(src_alpha, 0.0, 1.0)
        return src_rgb + dst * (1.0 - a)

    def finish(self, original_bg):
        """背景画布先与原图按覆盖度混合, 再按 layer 从大到小覆盖上去。"""
        bg = original_bg.astype(np.float32)
        if self._bg_rgb is not None:
            a = np.clip(self._bg_alpha, 0.0, 1.0)
            bg = self._bg_rgb + bg * (1.0 - a)
        for layer_idx in sorted(self._layers.keys(), reverse=True):
            rgb, alpha = self._layers[layer_idx]
            bg = self._composite_over(bg, rgb, alpha)
        return np.clip(bg, 0, 255).astype(np.uint8)


# 色彩链统一走 torch: GPU 可用时跑 GPU, 否则跑 CPU(torch)。
# RGB↔LAB 与大核中值必须留在 cv2 —— 只有 8bit 定点实现能保证逐值一致,
# 偏差会被方差比/改色置信度放大成可见色差。


def _sm_pick_device(use_gpu):
    """use_gpu 且 ComfyUI 选中 CUDA/XPU 时用 GPU; 关闭或 --cpu 时用 CPU。"""
    if not use_gpu:
        return torch.device("cpu")
    try:
        import comfy.model_management as mm
        dev = mm.get_torch_device()
    except Exception:
        dev = torch.device("cuda") if torch.cuda.is_available() else torch.device("cpu")
    return dev if dev is not None and dev.type in ("cuda", "xpu") else torch.device("cpu")


def _sm_as_float(img, device):
    """numpy 标量图(0..1) → (1,H,W,1) float32, 不做 255 归一。"""
    t = torch.from_numpy(np.ascontiguousarray(img)).to(device=device, dtype=torch.float32)
    return (t[..., None] if t.ndim == 2 else t).unsqueeze(0)


def _sm_numpy(x):
    return x[0].detach().cpu().numpy()


def _sm_rgb_to_lab(rgb, device):
    """uint8 RGB(HWC) → cv2 8bit LAB(0..255) 的 (1,H,W,3) float32。
    OpenCV 的 LAB 是定点近似实现, 自算 float 版会有 1~2 级偏差; 旧实现全程经 cv2,
    这里保持同源以保证统计量(方差比/改色置信度)逐值一致。"""
    lab = cv2.cvtColor(np.ascontiguousarray(rgb), cv2.COLOR_RGB2LAB).astype(np.float32)
    return torch.from_numpy(lab).to(device).unsqueeze(0)


def _sm_lab_to_u8(lab):
    """LAB(0..255) → uint8 RGB, 与旧实现 clip→uint8→cv2 逐值一致。"""
    a = lab[0].detach().cpu().numpy()
    a = np.clip(a, 0.0, 255.0).astype(np.uint8)
    return cv2.cvtColor(a, cv2.COLOR_LAB2RGB)


def _sm_fit(x, h, w, mode="bilinear"):
    if x.shape[1:3] == (h, w):
        return x
    return F.interpolate(x.permute(0, 3, 1, 2), size=(h, w), mode=mode,
                         align_corners=False if mode == "bilinear" else None).permute(0, 2, 3, 1)


def _sm_gauss_kernel(ksize, sigma, device, dtype):
    coords = torch.arange(ksize, dtype=dtype, device=device) - (ksize - 1) * 0.5
    k = torch.exp(-(coords ** 2) / (2.0 * sigma ** 2))
    return k / k.sum()


def _sm_blur_bchw(x, kernel):
    b, c, h, w = x.shape
    radius = kernel.numel() // 2
    mode = "reflect" if radius < min(h, w) else "replicate"
    kw = kernel.view(1, 1, 1, -1).expand(c, 1, 1, -1).contiguous()
    y = F.conv2d(F.pad(x, (radius, radius, 0, 0), mode=mode), kw, groups=c)
    kh = kernel.view(1, 1, -1, 1).expand(c, 1, -1, 1).contiguous()
    return F.conv2d(F.pad(y, (0, 0, radius, radius), mode=mode), kh, groups=c)


def _sm_auto_ksize(sigma):
    """cv2.GaussianBlur(src, (0,0), sigma) 对 float32 的核长反推: 8*sigma+1 取奇。"""
    return max(1, int(round(sigma * 8.0 + 1.0)) | 1)


def _sm_blur(x, sigma):
    """sigma 驱动的各向同性高斯(HWC), 核长/边界(REFLECT_101)对齐 cv2。"""
    sigma = float(max(sigma, 0.0))
    if sigma < 0.5:
        return x
    k = _sm_gauss_kernel(_sm_auto_ksize(sigma), sigma, x.device, x.dtype)
    return _sm_blur_bchw(x.permute(0, 3, 1, 2), k).permute(0, 2, 3, 1)


def _sm_blur_ksize(x, ksize, sigma=None):
    """固定核长高斯, 对齐 cv2.GaussianBlur((k,k),0)。"""
    ksize = int(ksize) | 1
    if ksize <= 1:
        return x
    if sigma is None:
        sigma = 0.3 * ((ksize - 1) * 0.5 - 1.0) + 0.8     # cv2 由核长反推 sigma
    k = _sm_gauss_kernel(ksize, max(sigma, 0.1), x.device, x.dtype)
    return _sm_blur_bchw(x.permute(0, 3, 1, 2), k).permute(0, 2, 3, 1)


def _sm_area_weights(n_out, n_in, device, dtype):
    """INTER_AREA 一维权重: 每个输出格覆盖源像素的占比。torch 的 area 模式在
    非整数缩放时与 cv2 不一致(实测低至 0.1 级), 这里显式构造面积权重。"""
    scale = float(n_in) / float(n_out)
    src = torch.arange(n_in, device=device, dtype=dtype)
    start = torch.arange(n_out, device=device, dtype=dtype) * scale
    w = (torch.minimum(start[:, None] + scale, src[None, :] + 1.0)
         - torch.maximum(start[:, None], src[None, :])).clamp_min(0.0)
    return w / w.sum(dim=1, keepdim=True)


def _sm_area_resize(x, sh, sw):
    """HWC 张量缩放到 (sh, sw): 缩小走面积平均(对齐 cv2.INTER_AREA), 放大走双线性。"""
    h, w = x.shape[1:3]
    if (sh, sw) == (h, w):
        return x
    if sh >= h or sw >= w:
        return F.interpolate(x.permute(0, 3, 1, 2), size=(sh, sw), mode="bilinear",
                             align_corners=False).permute(0, 2, 3, 1)
    wy = _sm_area_weights(sh, h, x.device, x.dtype)
    wx = _sm_area_weights(sw, w, x.device, x.dtype)
    bchw = x.permute(0, 3, 1, 2)
    bchw = torch.matmul(wy, bchw)
    bchw = torch.matmul(bchw, wx.t())
    return bchw.permute(0, 2, 3, 1)


def _sm_fast_blur(x, sigma):
    """大 sigma: 降采样→模糊→上采样, 与原 _fast_blur 同结构。"""
    sigma = float(max(sigma, 0.0))
    if sigma <= 6.0:
        return _sm_blur(x, sigma)
    h, w = x.shape[1:3]
    ds = int(min(4, max(2, round(sigma / 4.0))))
    sh, sw = max(8, h // ds), max(8, w // ds)
    inner = max(0.5, sigma / ds)
    small = _sm_area_resize(x, sh, sw).permute(0, 3, 1, 2)
    small = _sm_blur_bchw(small, _sm_gauss_kernel(
        _sm_auto_ksize(inner), inner, x.device, x.dtype))
    return F.interpolate(small, size=(h, w), mode="bilinear",
                         align_corners=False).permute(0, 2, 3, 1)


def _sm_median_bchw(x, k):
    """精确中值(BCHW), 按行分块控制显存。"""
    k = int(k) | 1
    if k <= 1:
        return x
    pad = k // 2
    b, c, h, w = x.shape
    out = torch.empty_like(x)
    block = max(1, 4_000_000 // max(1, w * k * k))
    for y in range(0, h, block):
        y2 = min(h, y + block)
        y0s, y1s = max(0, y - pad), min(h, y2 + pad)
        tile = F.pad(x[:, :, y0s:y1s, :],
                     (pad, pad, pad - (y - y0s), pad - (y1s - y2)), mode="replicate")
        win = tile.unfold(2, k, 1).unfold(3, k, 1).reshape(b, c, y2 - y, w, k * k)
        out[:, :, y:y2, :] = torch.median(win, dim=-1).values
    return out


def _sm_np_median(v, dim=0):
    """np.median 语义: 偶数样本取中间两值的均值(torch.median 只取较小者)。"""
    n = v.shape[dim]
    if n % 2 == 1:
        return torch.median(v, dim=dim).values
    lo = torch.kthvalue(v, n // 2, dim=dim).values
    hi = torch.kthvalue(v, n // 2 + 1, dim=dim).values
    return 0.5 * (lo + hi)


def _sm_median(x, k):
    k = int(k) | 1
    if k <= 1:
        return x
    return _sm_median_bchw(x.permute(0, 3, 1, 2), k).permute(0, 2, 3, 1)


def _sm_u8_median(x, k):
    """全分辨率 8bit 中值(cv2 直方图)。输入已 floor 到整数, 结果与精确中值一致,
    比 unfold+torch.median 快两个数量级。"""
    k = int(k) | 1
    if k <= 1:
        return x
    img = np.clip(_sm_numpy(x), 0.0, 255.0).astype(np.uint8)
    out = np.stack([cv2.medianBlur(np.ascontiguousarray(img[..., c]), k)
                    for c in range(img.shape[2])], axis=-1)
    return torch.from_numpy(out.astype(np.float32)).to(x.device).unsqueeze(0)


def _sm_fast_median(x, k):
    """大核中值: 半分辨率执行, 等效半径不变。
    走 cv2 的 8bit 定点实现: 中值结果的 1 级偏差会被可靠性的方差比(分母下限 1e-6)
    在强边界处放大成可见色块, 这里必须与原实现逐值一致; 每次调用只有两次半分辨率
    中值, CPU 往返开销可忽略。"""
    k = int(k) | 1
    if k <= 5:
        return _sm_median(x, k)
    h, w = x.shape[1:3]
    img8 = np.clip(_sm_numpy(x), 0.0, 255.0).astype(np.uint8)
    sh, sw = max(8, h // 2), max(8, w // 2)
    small = cv2.resize(img8, (sw, sh), interpolation=cv2.INTER_AREA)
    kk = max(3, (k // 2) | 1)
    kk = min(kk, (min(sh, sw) - 1) | 1)
    small = cv2.medianBlur(small, kk)
    out = cv2.resize(small, (w, h), interpolation=cv2.INTER_LINEAR)
    return torch.from_numpy(out.astype(np.float32)).to(x.device).unsqueeze(0)
