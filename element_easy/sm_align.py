# -*- coding: utf-8 -*-
# 对齐与形变 / alignment & warping

import cv2
import numpy as np
import torch
import kornia.feature as KF

from dataclasses import dataclass, field

from .sm_common import (
    _sm_log,
    _LRUCache,
    ensure_model_files,
    _parse_lightglue_output,
    _sm_as_float,
    _sm_numpy,
    _sm_rgb_to_lab,
    _sm_fast_blur,
    _sm_median,
)
from .sm_config import (
    B2BG_LAYOUT_MAX_RESID,
    B2BG_LAYOUT_MIN_NCC,
    B2BG_LAYOUT_NCC_MARGIN,
    B2BG_MAX_RESID,
    B2BG_MIN_MATCH_NCC,
    B2BG_MIN_SPREAD_CELLS,
    B2BG_TRUST_RESID,
    B2BG_USE_LOFTR,
    BRIDGE_MAX_MEDIAN_DIFF,
    GRID_ANCHOR_MAX_PX,
    GRID_ANCHOR_TOLERANCE,
    GRID_AUTO_MIN_INLIERS,
)
from .sm_flow import (
    _brighten_for_match,
    _flow_acceptable,
    _match_histogram,
    _match_histogram_rgb,
    _to_flow_luma,
    refine_second_pass,
    refine_with_optical_flow,
)


@dataclass
class AlignState:
    """perform_kornia_alignment 的逐块瞬态状态。"""

    flow_scale: float = 1.0
    bridge_A: object = None
    bridge_H_A2BG: object = None
    disk_pts_q: object = None
    disk_pts_t: object = None
    match_level: object = None
    last_edit_mask: object = None
    last_residual_px: object = None
    b2bg_layout_obs: dict = field(default_factory=dict)


# SIFT/DISK 背景特征缓存: 同一背景只检测一次, 多个 crop / 多轮执行共享。
_SIFT_TRAIN_CACHE = _LRUCache(4)
_DISK_TRAIN_CACHE = _LRUCache(4)

# LoFTR 与 DISK 模型权重: 进程级缓存, 避免每轮执行重载。
_LOFTR_MODEL = None
_LOFTR_CACHED_DEVICE = None
_DISK_MODEL = None
_LG_MATCHER_DISK = None
_CACHED_DEVICE = None


def get_kornia_models(device):
    global _DISK_MODEL, _LG_MATCHER_DISK, _CACHED_DEVICE
    ensure_model_files()
    if _CACHED_DEVICE != device:
        _DISK_MODEL = None
        _LG_MATCHER_DISK = None
        _CACHED_DEVICE = device
    if _DISK_MODEL is None:
        try:
            _DISK_MODEL = KF.DISK.from_pretrained("depth").eval().to(device)
            _LG_MATCHER_DISK = KF.LightGlueMatcher("disk").eval().to(device)
            _sm_log(f"[Smart Merge] DISK & LightGlue 模型已就绪 (设备: {device}) | DISK & LightGlue models ready (device: {device})")
        except Exception as e:
            print(f"[Smart Merge] 初始化 DISK 权重失败: {e} | Failed to initialize DISK weights: {e}")
    return _DISK_MODEL, _LG_MATCHER_DISK


def _arr_fingerprint(arr, tag=""): 
    import hashlib
    flat = np.ascontiguousarray(arr.reshape(-1))
    step = max(1, flat.size // 65536)
    return hashlib.md5(flat[::step].tobytes() + tag.encode()).hexdigest()[:16] \
           + "_" + "x".join(map(str, arr.shape))

def perform_sift_alignment( query_img, train_img):
    H, info = _sift_bridge_homography(query_img, train_img, max_dim=1536,
                                           nfeatures=5000, contrast=0.04,
                                           cache_tag="bg_sift")
    if H is not None:
        return H
    # 大面积天空/纯色的低纹理分块: A 与 BG 同倍缩到 1536 长边后 A 只剩几十个
    # 特征点, 桥接必然失败并降级到 B→BG。提高匹配分辨率重试; 成功的分块不经过这里,
    # 结果逐像素不变。
    H, info = _sift_bridge_homography(query_img, train_img, max_dim=2048,
                                           nfeatures=8000, contrast=0.02,
                                           cache_tag="bg_sift_hi")
    if H is not None:
        _sm_log("[Smart Merge] 低纹理分块 SIFT 桥接: 提高匹配分辨率重试成功 | "
              "bridge retry at higher resolution succeeded")
        return H
    _sm_log(f"[Smart Merge] A→BG 桥接失败({info}), 降级 B→BG | "
          f"bridge failed, falling back: {info}")
    return None

def _sift_bridge_homography( query_img, train_img, max_dim, nfeatures,
                            contrast, cache_tag):
    h_q, w_q = query_img.shape[:2]
    h_t, w_t = train_img.shape[:2]
    max_bg_dim = max(h_t, w_t)
    scale = 1.0
    if max_bg_dim > max_dim:
        scale = max_dim / float(max_bg_dim)
    if scale < 1.0:
        query_sift_img = cv2.resize(query_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
        train_sift_img = cv2.resize(train_img, None, fx=scale, fy=scale, interpolation=cv2.INTER_LANCZOS4)
    else:
        query_sift_img = query_img
        train_sift_img = train_img

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray_query = cv2.cvtColor(query_sift_img, cv2.COLOR_RGB2GRAY)
    gray_train = cv2.cvtColor(train_sift_img, cv2.COLOR_RGB2GRAY)

    train_key = _arr_fingerprint(train_sift_img, cache_tag)
    cached = _SIFT_TRAIN_CACHE.get(train_key)
    if cached is not None:
        kp_t, des_t = cached
    else:
        sift_bg = cv2.SIFT_create(nfeatures=nfeatures, contrastThreshold=contrast)
        kp_t, des_t = sift_bg.detectAndCompute(clahe.apply(gray_train), None)
        _SIFT_TRAIN_CACHE[train_key] = (kp_t, des_t)

    sift = cv2.SIFT_create(nfeatures=nfeatures, contrastThreshold=contrast)
    kp_q, des_q = sift.detectAndCompute(clahe.apply(gray_query), None)
    n_q = 0 if des_q is None else len(des_q)
    n_t = 0 if des_t is None else len(des_t)
    if des_q is None or des_t is None or n_q < 10 or n_t < 10:
        return None, f"特征点不足 A{n_q}/BG{n_t}"

    try:
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
        return None, f"良匹配 {len(good_matches)}<10 (A关键点{n_q})"
    src_pts = np.float32([kp_q[m.queryIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    dst_pts = np.float32([kp_t[m.trainIdx].pt for m in good_matches]).reshape(-1, 1, 2)
    H, mask = cv2.findHomography(src_pts, dst_pts, cv2.USAC_MAGSAC, 3.0)
    
    n_inl = 0 if mask is None else int(np.sum(mask))
    if H is None or mask is None or n_inl < 8:
        return None, f"单应内点 {n_inl}<8 (良匹配{len(good_matches)})"
    if scale < 1.0:
        S = np.array([[scale, 0, 0], [0, scale, 0], [0, 0, 1]], dtype=np.float64)
        S_inv = np.array([[1.0/scale, 0, 0], [0, 1.0/scale, 0], [0, 0, 1]], dtype=np.float64)
        H = S_inv @ H @ S

    # 裁块 A 可以按内容原生分辨率送入, 此时它比 BG 小好几倍, 合法的 H 面积比也会远大于 1;
    # 上界放宽到"A 铺满整张 BG", 透视/边长比/凸性仍能拦住退化 H, 放置的正确性由随后的光度校验把关。
    max_area_ratio = max(6.0, float(w_t * h_t) / float(max(w_q * h_q, 1)))
    if not _homography_is_sane(H, h_q, w_q, h_t, w_t,
                                    max_area_ratio=max_area_ratio):
        _sm_log("[Smart Merge] A→BG 单应性未通过体检(透视/形状/凸性), 弃用桥接 | A→BG homography failed sanity check, discarding bridge")
        return None, "单应性体检未过"
    return H, "OK"

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

def _homography_deviation(H1, H2, w_q, h_q, n=8):
    """两个单应性在源图范围内映射结果的最大偏差(px), 用于 grid 锚定容差判断"""
    xs = np.linspace(0, w_q, n)
    ys = np.linspace(0, h_q, n)
    gx, gy = np.meshgrid(xs, ys)
    pts = np.stack([gx.ravel(), gy.ravel(), np.ones(gx.size)], axis=1).T
    p1 = (H1 @ pts).T; p1 = p1[:, :2] / (p1[:, 2:3] + 1e-9)
    p2 = (H2 @ pts).T; p2 = p2[:, :2] / (p2[:, 2:3] + 1e-9)
    return float(np.linalg.norm(p1 - p2, axis=1).max())

def _anchor_refit_homography(state, H_auto, H_grid, w_q, h_q, h_t, w_t, tol_px,
                             min_area_ratio=0.01, max_area_ratio=100.0,
                             min_edge_ratio=0.30, max_persp=0.35):
    """Grid 锚定重估: 只保留 grid 预测位置 tol_px 邻域内的 DISK 内点重新估计 H。
    校正限制在 grid 附近, 同时部分吸收真实漂移。失败返回 None(调用方回退 grid)。"""
    pts_q = getattr(state, 'disk_pts_q', None)
    pts_t = getattr(state, 'disk_pts_t', None)
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
    if not np.all(np.isfinite(H_new)) or not _homography_is_sane(
            H_new, h_q, w_q, h_t, w_t,
            max_persp=max_persp,
            min_edge_ratio=min_edge_ratio,
            min_area_ratio=min_area_ratio,
            max_area_ratio=max_area_ratio):
        return None
    return H_new

def _grid_anchor_tol_px( H_grid, w_q, h_q):
    """grid 锚定容差: 相对 tile 尺寸, 但设绝对上限。
    H 级别只需要吸收几像素~几十像素的漂移; 更大的偏差属于匹配失败。"""
    corners = np.array([[0, 0], [w_q, 0], [w_q, h_q], [0, h_q]], dtype=np.float64)
    pc = np.hstack([corners, np.ones((4, 1))]) @ np.asarray(H_grid, np.float64).T
    pc = pc[:, :2] / pc[:, 2:3]
    size = float(max(np.ptp(pc[:, 0]), np.ptp(pc[:, 1]), 1.0))
    return float(max(6.0, min(GRID_ANCHOR_MAX_PX, GRID_ANCHOR_TOLERANCE * size)))

def _grid_warp_scores( query_img, train_img, base_mask, H):
    """候选 H 的结构评分: 直方图归一化后的灰度中位差 + 光流残差中位数。
    只在几何掩码内统计, 与颜色编辑无关。"""
    h_t, w_t = train_img.shape[:2]
    if base_mask is None:
        base_mask = np.ones(query_img.shape[:2], dtype=np.float32)
    wf = cv2.warpPerspective(query_img, H, (w_t, h_t), flags=cv2.INTER_LINEAR,
                             borderMode=cv2.BORDER_REFLECT101)
    wm = cv2.warpPerspective(base_mask, H, (w_t, h_t), flags=cv2.INTER_LINEAR)
    photo = _photometric_score(wf, wm, train_img, edit_mask=None)
    resid, _ = _flow_residual_score(wf, wm, train_img, edit_mask=None)
    return float(photo), float(resid)

def _grid_candidate_ok( query_img, train_img, base_mask, H_cand, H_grid,
                       photo_slack=2.0, resid_slack=0.5):
    """候选 H 必须不劣于 grid 保底, 才允许替换。避免"更贴合 grid"之外
    的低置信匹配把整块搬走。"""
    p_c, r_c = _grid_warp_scores(query_img, train_img, base_mask, H_cand)
    p_g, r_g = _grid_warp_scores(query_img, train_img, base_mask, H_grid)
    if p_c >= 1e8 or r_c >= 1e8:
        return False
    if p_g >= 1e8 or r_g >= 1e8:
        return True
    ok = (p_c <= p_g + photo_slack) and (r_c <= r_g + resid_slack)
    _sm_log(f"[Smart Merge] Grid候选评分: 光度 {p_c:.1f}/残差 {r_c:.2f}px "
               f"vs grid {p_g:.1f}/{r_g:.2f}px → {'采纳' if ok else '弃用'}")
    return ok

def _resolve_grid_alignment(state, query_img, train_img, base_mask, H_grid, H_bridge, device):
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

    if H_bridge is not None and _homography_is_sane(
            H_bridge, h_q, w_q, h_t, w_t,
            min_area_ratio=0.01, max_area_ratio=100.0,
            min_edge_ratio=0.20, max_persp=0.60):
        dev = _homography_deviation(H_bridge, H_grid, w_q, h_q)
        if dev <= max(96.0, 0.45 * max(w_t, h_t)):
            _sm_log(f"[Smart Merge] Grid锚定: 采用桥接 A→BG 实测放置 "
                       f"(偏离grid {dev:.1f}px) | bridge placement used")
            return H_bridge, "Grid_Bridge", -1
        _sm_log(f"[Smart Merge] Grid锚定: 桥接H偏离grid {dev:.1f}px 过大, "
              f"改用特征匹配 | bridge H too far from grid, using feature match")

    H_auto, _inl, n_inl, m_auto = estimate_homography(state, 
        query_img, train_img, device=device,
        min_area_ratio=1e-4, max_area_ratio=1e4,
        min_edge_ratio=0.08, max_persp=0.90
    )
    if H_auto is None:
        _sm_log("[Smart Merge] Grid锚定: 特征匹配失败, 使用grid保底 | auto-match failed, grid fallback")
        return H_grid, "Grid_Base", -1

    tol = _grid_anchor_tol_px(H_grid, w_q, h_q)
    dev = _homography_deviation(H_auto, H_grid, w_q, h_q)
    if n_inl >= GRID_AUTO_MIN_INLIERS and dev <= tol \
            and _grid_candidate_ok(query_img, train_img, base_mask, H_auto, H_grid):
        _sm_log(f"[Smart Merge] Grid锚定: 特征匹配偏离grid {dev:.1f}px ≤ 容差{tol:.1f}px, "
                   f"内点{n_inl}, 采用特征精修 | auto-match accepted")
        return H_auto, (m_auto or "Grid_Auto"), n_inl

    _sm_log(f"[Smart Merge] Grid锚定: 自动匹配不可信(内点{n_inl}, 偏离{dev:.1f}px/容差{tol:.1f}px), "
               f"尝试邻域重估 | auto-match rejected, trying anchored refit")
    H_anch = _anchor_refit_homography(state, 
        H_auto, H_grid, w_q, h_q, h_t, w_t, tol,
        min_area_ratio=1e-4, max_area_ratio=1e4,
        min_edge_ratio=0.08, max_persp=0.90)
    if H_anch is not None and _grid_candidate_ok(
            query_img, train_img, base_mask, H_anch, H_grid):
        _sm_log("[Smart Merge] Grid锚定: 已用grid邻域内点重估 | anchored refit accepted")
        return H_anch, "Grid_Anchored", -1

    _sm_log("[Smart Merge] Grid锚定: 回退grid保底 | fallback to grid base")
    return H_grid, "Grid_Base", -1

def _points_spread_cells(pts, w, h, n=4):
    """内点在 n×n 网格里占据的格数。簇状假匹配的格数会远小于真实匹配。"""
    if pts is None or len(pts) < 4 or w <= 0 or h <= 0:
        return 0
    cx = np.clip((pts[:, 0] / float(w) * n).astype(int), 0, n - 1)
    cy = np.clip((pts[:, 1] / float(h) * n).astype(int), 0, n - 1)
    return int(len(set(zip(cx.tolist(), cy.tolist()))))

def _edge_map( img, size):
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

def _coarse_placement_h( query_img, train_img):
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
        _edge_map(train_img, (bw, bh)).astype(np.float32), (0, 0), 1.0)

    crop_gray = cv2.cvtColor(query_img, cv2.COLOR_RGB2GRAY).astype(np.float32)
    crop_edge = _edge_map(query_img, (w_q, h_q)).astype(np.float32)

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
            _edge_map(query_img, (tw, th)).astype(np.float32), (0, 0), 1.0)
        r_gray = cv2.matchTemplate(bg_gray, t_gray, cv2.TM_CCOEFF_NORMED)
        r_edge = cv2.matchTemplate(bg_edge, t_edge, cv2.TM_CCOEFF_NORMED)
        _, max_v, _, max_loc = cv2.minMaxLoc(0.5 * r_gray + 0.5 * r_edge)
        if best is None or max_v > best[0]:
            best = (float(max_v), float(rel), float(max_loc[0]), float(max_loc[1]))
    if best is None or best[0] < B2BG_MIN_MATCH_NCC:
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
    if ncc < B2BG_MIN_MATCH_NCC:
        return None, 0.0

    H = np.array([[rel, 0.0, tx / s], [0.0, rel, ty / s], [0.0, 0.0, 1.0]], np.float64)
    if not _homography_is_sane(H, h_q, w_q, h_t, w_t,
                                    min_area_ratio=0.05, max_area_ratio=20.0,
                                    min_edge_ratio=0.25, max_persp=0.50):
        return None, 0.0
    _sm_log(f"[Smart Merge] 模板匹配放置: 缩放{rel:.3f} 平移({tx / s:.1f},{ty / s:.1f}) "
               f"NCC={ncc:.2f} | template placement")
    return H, float(ncc)

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

def _layout_candidates( crop_index, crop_total, w_q, h_q, w_t, h_t):
    """无像素证据时的布局推断候选: 分块序号 → 均匀格子。

    LayoutFill: 整块各向异性铺满格子(重采样的分块也能落位);
    LayoutFit : 保持分块宽高比居中放入格子(AI 按新比例重绘、带留白的情况)。
    两者都必须通过单应性体检; 是否采用由残差竞争决定, 不会单独决定放置。
    """
    if crop_index is None:
        return []
    shape = _grid_shape(crop_total, w_t, h_t)
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
        if _homography_is_sane(H, h_q, w_q, h_t, w_t,
                                    min_area_ratio=0.01, max_area_ratio=100.0,
                                    min_edge_ratio=0.20, max_persp=0.50):
            cands.append((name, H))
    return cands

def _record_layout_obs(state, crop_index, H, w_q, h_q):
    """记下已成功放置的分块, 供同一张图内后续失败块反推格子步长。"""
    try:
        obs = getattr(state, 'b2bg_layout_obs', None)
        if obs is None:
            obs = state.b2bg_layout_obs = {}
        obs[int(crop_index)] = (np.array(H, np.float64).copy(), float(w_q), float(h_q))
    except Exception:
        pass

def _layout_fit_candidates(state, crop_index, crop_total, w_q, h_q, w_t, h_t):
    """用本图已成功放置的分块反推格子步长(可吸收 overlap), 预测本块中心。

    只平移 LayoutFill 候选, 不改缩放。至少需要 2 行 2 列的观测。
    """
    obs = getattr(state, 'b2bg_layout_obs', None)
    shape = _grid_shape(crop_total, w_t, h_t)
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
    if not _homography_is_sane(H, h_q, w_q, h_t, w_t,
                                    min_area_ratio=0.01, max_area_ratio=100.0,
                                    min_edge_ratio=0.20, max_persp=0.50):
        return []
    return [("LayoutFit", H)]

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

def _loftr_homography(state, query_img, train_img, device):
    """LoFTR 半稠密匹配 → H。低纹理/大面积改色块上 DISK 拿不到足够特征时兜底。"""
    try:
        q, t = match_with_loftr(query_img, train_img, device)
    except Exception as e:
        print(f"[Smart Merge] LoFTR 兜底匹配失败: {e}")
        return None
    if q is None or t is None or len(q) < 8:
        return None
    if len(q) > 1200:
        step = int(np.ceil(len(q) / 1200.0))
        q, t = q[::step], t[::step]
    q, t = filter_correspondences_local_affine(q, t)
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
    if not _homography_is_sane(H, h_q, w_q, h_t, w_t,
                                    min_area_ratio=0.01, max_area_ratio=100.0,
                                    min_edge_ratio=0.30, max_persp=0.35):
        return None
    try:
        ones = np.hstack([q, np.ones((len(q), 1))])
        p = (H @ ones.T).T
        p = p[:, :2] / p[:, 2:]
        keep = np.linalg.norm(p - t, axis=1) < 10.0
        if int(keep.sum()) >= 8:
            state.disk_pts_q = q[keep]
            state.disk_pts_t = t[keep]
    except Exception:
        pass
    state.match_level = "LoFTR"
    _sm_log(f"[Smart Merge] DISK 特征不足, 启用 LoFTR 半稠密兜底 ({len(q)} 对) | "
          f"LoFTR fallback ({len(q)} matches)")
    return H

def _select_b2bg_homography(state, query_img, train_img, base_mask, device,
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
            _p, r = _grid_warp_scores(query_img, train_img, base_mask, H)
        except Exception:
            return None
        return None if r is None or r >= 1e8 else float(r)

    def _accept(name, H, r, approx=False, note=""):
        if name not in ("B2BG_Feat", "DISK", "LoFTR"):
            # 放置不是来自特征 H → 特征点与当前基准不一致, 不让它们参与 TPS
            state.disk_pts_q = None
            state.disk_pts_t = None
        if not approx:
            _record_layout_obs(state, crop_index, H, w_q, h_q)
        suffix = f", {note}" if note else ""
        _sm_log(f"[Smart Merge] B→BG 对齐: {name} (残差 {r:.2f}px"
              f"{', 布局近似放置' if approx else ''}{suffix}) | B→BG alignment via {name}")
        return H, name, float(r)

    def _match(q):
        H, _inl, _n, m = estimate_homography(state, 
            q, train_img, device=device,
            min_area_ratio=0.01, max_area_ratio=100.0,
            min_edge_ratio=0.30, max_persp=0.35,
            min_cells=B2BG_MIN_SPREAD_CELLS)
        return H, _resid(H), m

    H_feat, feat_r, m_feat = _match(query_img)
    query_for_match = query_img

    # 暗部/低对比块: 曲线提亮后重试一次特征匹配(失败时)
    if feat_r is None or feat_r > B2BG_MAX_RESID:
        q_b = _brighten_for_match(query_img)
        if q_b is not None:
            pts_q0, pts_t0 = state.disk_pts_q, state.disk_pts_t
            H_b, r_b, m_b = _match(q_b)
            if r_b is not None and (feat_r is None or r_b < feat_r - 0.2):
                _sm_log(f"[Smart Merge] 暗部分块曲线提亮后匹配成功 (残差 {r_b:.2f}px) | "
                      f"brightened retry matched")
                H_feat, feat_r, m_feat = H_b, r_b, m_b
                query_for_match = q_b
            else:
                state.disk_pts_q, state.disk_pts_t = pts_q0, pts_t0
                _sm_log("[Smart Merge] 曲线提亮后仍未改善, 继续降级 | brightened retry no gain")

    if feat_r is not None and feat_r <= B2BG_TRUST_RESID:
        return _accept(m_feat or "B2BG_Feat", H_feat, feat_r)

    evid = []
    if feat_r is not None:
        evid.append((m_feat or "B2BG_Feat", H_feat, feat_r))

    # 模板放置: 全图多尺度结构+灰度相关, ~0.1s 且与颜色/亮度编辑无关。
    H_coarse, ncc = _coarse_placement_h(query_img, train_img)
    tm_r = _resid(H_coarse)
    if tm_r is not None:
        evid.append(("TemplateMatch", H_coarse, tm_r))

    if (B2BG_USE_LOFTR and (feat_r is None or feat_r > B2BG_MAX_RESID)
            and ncc < 0.55):
        H_lo = _loftr_homography(state, query_for_match, train_img, device)
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
    layout_raw = (_layout_candidates(crop_index, crop_total, w_q, h_q, w_t, h_t)
                  + _layout_fit_candidates(state, crop_index, crop_total, w_q, h_q, w_t, h_t))
    if layout_raw:
        s_e = min(1.0, 512.0 / float(max(h_t, w_t)))
        bw = max(64, int(round(w_t * s_e)))
        bh = max(64, int(round(h_t * s_e)))
        qe = _edge_map(query_img, (w_q, h_q)).astype(np.float32)
        te = _edge_map(train_img, (bw, bh)).astype(np.float32)
        H_scale = np.diag([s_e, s_e, 1.0])

        def _ncc_at(H):
            return _edge_ncc(qe, te, H_scale @ H, h_q, w_q)

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
            _c = _layout_candidates(_i, crop_total, w_q, h_q, w_t, h_t)
            if _c:
                others.append(_ncc_at(_c[0][1]))
        ncc_other = max(others) if others else 0.0
        for name, H in layout_raw:
            r = _resid(H)
            if r is not None:
                layout.append((name, H, r, _ncc_at(H)))

    evid_ok = [c for c in evid if c[2] <= B2BG_MAX_RESID]
    if evid_ok:
        name, H, r = min(evid_ok, key=lambda c: c[2])
        return _accept(name, H, r)

    layout_ok = [c for c in layout
                 if c[2] <= B2BG_LAYOUT_MAX_RESID
                 and c[3] >= B2BG_LAYOUT_MIN_NCC
                 and c[3] >= ncc_other + B2BG_LAYOUT_NCC_MARGIN]
    if layout_ok:
        name, H, r, ncc_l = min(layout_ok, key=lambda c: (-c[3], c[2]))
        return _accept(name, H, r, approx=True,
                       note=f"结构相关 {ncc_l:.2f} > 对照 {ncc_other:.2f}")

    detail = ", ".join(f"{n}={r:.1f}px" for n, _H, r in evid) or "无实测候选"
    if layout:
        detail += " | 布局: " + ", ".join(
            f"{nm}={r:.1f}px/ncc{c:.2f}" for nm, _H, r, c in layout) \
            + f" (对照 {ncc_other:.2f})"
    _sm_log(f"[Smart Merge] B→BG 放置失败({detail}), 跳过该块以保护整图 | "
          f"no reliable placement, tile skipped")
    return None, None, None

def _filter_reliable_correspondences( q, t, h_t, w_t, edit_mask):
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
    q3, t3 = filter_correspondences_local_affine(q2, t2)
    if len(q3) < 8:
        q3, t3 = q2, t2
    if (np.ptp(q3[:, 0]) < 0.30 * np.ptp(q[:, 0])
            or np.ptp(q3[:, 1]) < 0.30 * np.ptp(q[:, 1])):
        return q, t, False          # 剩余点太集中, 不能代表整块
    _sm_log(f"[Smart Merge] 可靠对应点: {len(q3)}/{len(q)} "
               f"(改色区剔除 {len(q) - n_keep} 点) | reliable correspondences")
    return q3, t3, True

def _bridge_photometric_ok( H, query_img, train_img):
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

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    g1 = clahe.apply(cv2.cvtColor(warped, cv2.COLOR_RGB2GRAY)).astype(np.float32)
    g2 = clahe.apply(cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)).astype(np.float32)

    med = float(np.median(np.abs(g1[m] - g2[m])))
    if med > BRIDGE_MAX_MEDIAN_DIFF:
        _sm_log(f"[Smart Merge] 桥接H光度一致性差(CLAHE后中位差 {med:.1f} > {BRIDGE_MAX_MEDIAN_DIFF}), 降级自动对齐 | Bridge H unreliable (median {med:.1f}), falling back")
        return False

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
            _sm_log(f"[Smart Merge] 桥接H梯度方向不匹配(平均|cos|={mean_cos:.2f} < 0.5), 降级自动对齐 | Bridge H gradient mismatch, falling back")
            return False
    return True

def _photometric_score( warped_fg, warped_mask, train_img, edit_mask=None):
    """对齐质量评分: 掩码内灰度绝对差中位数。有 edit_mask 时剔除改色区。"""
    if warped_fg.shape[:2] != train_img.shape[:2]:
        return 1e9
    m_geo = cv2.erode((warped_mask > 0.5).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
    m = m_geo
    if edit_mask is not None:
        m = m_geo & (edit_mask > 0.5)
        if float(m.sum()) < 100.0:
            # 改色/低置信区过大时不能直接判废，否则正确的对齐也会被拒绝
            m = m_geo
    if float(m.sum()) < 100.0:
        return 1e9
    g1 = cv2.cvtColor(warped_fg, cv2.COLOR_RGB2GRAY)
    g2 = cv2.cvtColor(train_img, cv2.COLOR_RGB2GRAY)
    # 打分前先对齐明暗, 偏色区只要结构对齐分数就合格
    g1 = _match_histogram(g1, g2).astype(np.float32)
    g2 = g2.astype(np.float32)
    return float(np.median(np.abs(g1[m] - g2[m])))

def _align_score( warped_fg, warped_mask, train_img, edit_mask=None):
    """对齐评分(边缘加权): 有 edit_mask 时剔除改色区。"""
    if warped_fg.shape[:2] != train_img.shape[:2]:
        return 1e9
    m = cv2.erode((warped_mask > 0.5).astype(np.uint8), np.ones((15, 15), np.uint8)) > 0
    if edit_mask is not None:
        m = m & (edit_mask > 0.5)
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

def _flow_residual_score( warped_fg, warped_mask, train_img, edit_mask=None):
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
    
    g1 = _to_flow_luma(warped_fg[y0:y1, x0:x1])
    g2 = _to_flow_luma(train_img[y0:y1, x0:x1])
    # 几何打分前先对齐明暗结构
    g1 = _match_histogram(g1, g2)
    
    m = cv2.erode(mask_u8[y0:y1, x0:x1], np.ones((15, 15), np.uint8)) > 0
    m_geo = m
    
    if edit_mask is not None:
        em_sub = edit_mask[y0:y1, x0:x1]
        m = m_geo & (em_sub > 0.5)
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

def match_with_loftr( query_img, train_img, device="cpu"):
    """LoFTR 半稠密匹配: 输入必须是 (N,1,H,W) 灰度图"""
    try:
        global _LOFTR_MODEL, _LOFTR_CACHED_DEVICE
        from kornia.feature import LoFTR
        ensure_model_files()
        if _LOFTR_MODEL is None or _LOFTR_CACHED_DEVICE != device:
            _LOFTR_MODEL = LoFTR(pretrained="outdoor").eval().to(device)
            _LOFTR_CACHED_DEVICE = device

        def _to_tensor(img):
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
            d = _LOFTR_MODEL({"image0": img_q, "image1": img_t})
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

def filter_correspondences_local_affine( pts_q, pts_t, k=8, inlier_thresh=4.0):
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

def warp_tps( warped_fg_src, warped_mask_src, train_img, pts_src, pts_dst,
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
        _sm_log(f"[Smart Merge] TPS 拒绝: 中位位移{med_mag:.1f}px 覆盖{cov}/256 | rejected")
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
            _sm_log(f"[Smart Merge] TPS 离群剔除: 保留 {_keep.sum()}/{n} 点 (阈值 {_thr:.2f}px) | outliers removed")
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
            _sm_log(f"[Smart Merge] TPS 拒绝: 留出残差{smooth_err:.1f}px>6 (匹配混乱) | chaotic")
            return None, None
    else:
        smooth_err = 0.0

    # 按位移分布自适应收紧限幅 (固定 64px 对小残差场景太宽松, 尖峰可存活)
    _p95 = float(np.percentile(mag, 95)) if len(mag) else 0.0
    _cap = float(min(max_disp, max(12.0, 4.0 * _p95))) 
    if _cap < max_disp:
        _sm_log(f"[Smart Merge] TPS 限幅收紧: {max_disp:.0f}→{_cap:.1f}px | cap tightened")
    max_disp = _cap

    disp = disp * np.clip(max_disp / np.maximum(mag, 1e-6), 0.0, 1.0)[:, None]
    rbf = RBFInterpolator(src, src + disp, kernel="thin_plate_spline",
                          smoothing=reg_lambda)
    h, w = train_img.shape[:2]
    step = max(8, int(np.ceil(np.sqrt(w * h / 120000.0)))) 
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
    # 只放大位移场, 不能放大绝对采样坐标。
    fg_full = cv2.resize(fg2, (w, h), interpolation=cv2.INTER_LINEAR)
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    map_x = xx - fg_full[:, :, 0]
    map_y = yy - fg_full[:, :, 1]
    warped_fg = cv2.remap(warped_fg_src, map_x, map_y, interpolation=cv2.INTER_LANCZOS4,
                          borderMode=cv2.BORDER_REPLICATE)
    warped_mask = cv2.remap(warped_mask_src, map_x, map_y, interpolation=cv2.INTER_LINEAR,
                            borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    _sm_log(f"[Smart Merge] TPS 场生效: {n}/{n_raw}点(保留/原始) 中位位移{med_mag:.1f}px "
          f"CV残差{smooth_err:.1f}px 覆盖{cov}/256")
    return warped_fg, warped_mask

def estimate_homography(state, query_img, train_img, device="cpu",
                        min_area_ratio=0.01, max_area_ratio=100.0,
                        min_edge_ratio=0.30, max_persp=0.35, min_cells=0):
    h_q, w_q = query_img.shape[:2]
    h_t, w_t = train_img.shape[:2]
    pts_q, pts_t = None, None
    state.match_level = None
    state.disk_pts_q = None
    state.disk_pts_t = None
    
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
    _sm_log(f"[Smart Merge] 匹配降采样: crop {w_q}x{h_q}→{query_m.shape[1]}x{query_m.shape[0]}, "
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
    query_p = _match_histogram_rgb(query_p, train_p)
    img_q_tensor = torch.from_numpy(np.ascontiguousarray(query_p)).permute(2, 0, 1).float().to(device)[None] / 255.0
    img_t_tensor = torch.from_numpy(np.ascontiguousarray(train_p)).permute(2, 0, 1).float().to(device)[None] / 255.0

    features_q = features_t = None
    train_key = _arr_fingerprint(train_p, "bg_disk")
    cached_t = _DISK_TRAIN_CACHE.get(train_key)
    try:
        disk, lg_matcher = get_kornia_models(device)
        if disk is not None and lg_matcher is not None:
            with torch.inference_mode():
                features_q = disk(img_q_tensor, n=2048, pad_if_not_divisible=True)[0]
                if cached_t is not None:
                    # 同一背景的 DISK 特征只算一次, 多分块复用
                    kps_t_t, desc_t = cached_t
                    kps_t_t = torch.from_numpy(kps_t_t).to(device)
                    desc_t = torch.from_numpy(desc_t).to(device)
                else:
                    features_t = disk(img_t_tensor, n=2048, pad_if_not_divisible=True)[0]
                    kps_t_t = features_t.keypoints
                    desc_t = features_t.descriptors
                    _DISK_TRAIN_CACHE[train_key] = (
                        kps_t_t.detach().cpu().numpy(), desc_t.detach().cpu().numpy())
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
                        state.match_level = "DISK"
            if state.match_level is None:
                _sm_log("[Smart Merge] DISK+LightGlue 匹配点数不足 | DISK+LightGlue matched too few points")
    except Exception as e:
        print(f"[Smart Merge] DISK + LightGlue 匹配运行失败: {e} | DISK+LightGlue matching failed: {e}")
        pts_q, pts_t = None, None

    try:
        del img_q_tensor, img_t_tensor, features_q, features_t
    except Exception:
        pass
    if getattr(device, "type", "") == "cuda":
        torch.cuda.empty_cache()

    if pts_q is None or pts_t is None or len(pts_q) < 4:
        return None, None, 0, None

    magsac_flag = getattr(cv2, 'USAC_MAGSAC', cv2.RANSAC)
    H, inliers = cv2.findHomography(pts_q, pts_t, magsac_flag, 4.0)
    if H is None or inliers is None or int(np.sum(inliers)) < 8:
        return None, None, 0, None

    # 用内点最小二乘重算 H, 减小重投影误差
    inl_mask = inliers.ravel().astype(bool)
    try:
        H_refit, _ = cv2.findHomography(pts_q[inl_mask], pts_t[inl_mask], 0)
        if H_refit is not None and np.all(np.isfinite(H_refit)):
            H = H_refit
    except Exception:
        pass

    try:
        _ones = np.hstack([pts_q, np.ones((len(pts_q), 1))])
        _proj = (H @ _ones.T).T
        _proj = _proj[:, :2] / _proj[:, 2:]
        _err = np.linalg.norm(_proj - pts_t, axis=1)
        _keep = _err < 10.0
        if int(_keep.sum()) >= 8:
            state.disk_pts_q = pts_q[_keep]
            state.disk_pts_t = pts_t[_keep]
    except Exception:
        state.disk_pts_q = None

    if H is None or inliers is None or np.sum(inliers) < 4:
        return None, None, 0, None
    if not _homography_is_sane(
            H, h_q, w_q, h_t, w_t,
            max_persp=max_persp,
            min_edge_ratio=min_edge_ratio,
            min_area_ratio=min_area_ratio,
            max_area_ratio=max_area_ratio):
        _sm_log("[Smart Merge] 单应性矩阵异常(退化/镜像/过度形变), 放弃并降级 | Homography invalid (degenerate/mirrored/over-deformed), rejected and falling back")
        return None, None, 0, None
    if min_cells > 0:
        cells = _points_spread_cells(state.disk_pts_q, w_q, h_q, n=4)
        if cells < min_cells:
            _sm_log(f"[Smart Merge] 特征内点空间扩散不足({cells}/16 格 < {min_cells}), "
                  f"视为局部假匹配 | inliers too clustered, rejected")
            state.disk_pts_q = None
            state.disk_pts_t = None
            return None, None, 0, None
    num_inliers = int(np.sum(inliers))
    method_used = state.match_level or "DISK"
    return H, inliers, num_inliers, method_used

def perform_kornia_alignment(state, query_img, train_img, warp_method=False, second_pass=False,
                             device="cpu", preset_H=None, max_flow_px=None, use_tps=True, base_mask=None,
                             is_grid_preset=False, bridge_H=None, crop_index=0, crop_total=1):

    h_q, w_q = query_img.shape[:2]
    h_t, w_t = train_img.shape[:2]

    # 估流尺度: 桥接 A 与编辑分块 B 的尺度比。A 由上游缩放到内容原生分辨率时,
    # 光流就在原生分辨率上估, 不再被画布分辨率拖着走。
    flow_scale = getattr(state, 'flow_scale', 1.0)
    _bridge_a = getattr(state, 'bridge_A', None)
    if _bridge_a is not None and _bridge_a.shape[1] > 0 and w_q > 0:
        flow_scale = min(1.0, _bridge_a.shape[1] / float(w_q))
    state.flow_scale = flow_scale
    
    state.last_edit_mask = None
    state.last_residual_px = None

    H = None
    method_used = None
    num_inliers = 0
    is_bridge = False
    
    preset_valid = preset_H is not None and _homography_is_sane(
        preset_H, h_q, w_q, h_t, w_t,
        min_area_ratio=1e-4 if is_grid_preset else 0.01,
        max_area_ratio=1e4 if is_grid_preset else 100.0,
        min_edge_ratio=0.08 if is_grid_preset else 0.30,
        max_persp=0.90 if is_grid_preset else 0.35
    )
    if preset_valid:
        if is_grid_preset:
            # grid 坐标只是布局参考。有桥接 A 时优先用 A→BG 的实测放置;
            H, method_used, num_inliers = _resolve_grid_alignment(state, 
                query_img, train_img, base_mask, preset_H, bridge_H, device)
            is_bridge = True
        elif _bridge_photometric_ok(preset_H, query_img, train_img):
            H = preset_H
            method_used = "Bridge(B→A→BG)"
            num_inliers = -1
            is_bridge = True
    

    if is_bridge:
        try:
            fg_pre = cv2.warpPerspective(query_img, H, (w_t, h_t), flags=cv2.INTER_LANCZOS4)
            pre_base = base_mask if base_mask is not None else np.ones((h_q, w_q), dtype=np.float32)
            mask_pre = cv2.warpPerspective(pre_base, H, (w_t, h_t), flags=cv2.INTER_LINEAR)
            state.last_edit_mask = _compute_edit_mask(train_img, fg_pre, valid_mask=mask_pre, device=device)
            _sm_log(f"[Smart Merge] 预生成结构掩码: 阻断面积占比 {(state.last_edit_mask < 0.5).mean()*100:.1f}%")
        except Exception as e:
            print(f"[Smart Merge] 预生成掩码失败: {e}")
            state.last_edit_mask = None
    
    use_tps_path = (use_tps and preset_H is not None and is_bridge
                    and getattr(state, 'bridge_A', None) is not None
                    and getattr(state, 'bridge_H_A2BG', None) is not None)
    if use_tps_path:
        # LoFTR 内部把每张图各自缩到长边 1024, 所以 B 是重绘分块、A 是原生小图时会留下
        # 相对尺度差(A 原样 356 vs B 缩到 1024)。这里把小的 A 放大到 B 的像素尺寸再匹配,
        # 匹配点随后按 (w_A/w_q, h_A/h_q) 换算回 A 原生坐标, TPS 拿到的仍是 A 坐标。
        # 反方向(缩 B)会丢掉重绘细节, 匹配精度受限于小图, 实测更差。
        bridge_a = state.bridge_A
        if bridge_a.shape[:2] != (h_q, w_q):
            h_a, w_a = bridge_a.shape[:2]
            a_norm = cv2.resize(bridge_a, (w_q, h_q),
                                interpolation=cv2.INTER_AREA if w_a > w_q else cv2.INTER_CUBIC)
            pts_b, pts_a = match_with_loftr(query_img, a_norm, device)
            if pts_a is not None and len(pts_a) > 0:
                pts_a = pts_a * np.array([w_a / float(w_q), h_a / float(h_q)], dtype=np.float32)
        else:
            pts_b, pts_a = match_with_loftr(query_img, bridge_a, device)
        if pts_b is not None and len(pts_b) >= 8:
            pts_b, pts_a = filter_correspondences_local_affine(pts_b, pts_a)
            n_pts = len(pts_b)
            if n_pts < 8:
                _sm_log(f"[Smart Merge] TPS: B↔A匹配不足({n_pts}点), 跳过 | too few matches")
            else:
                ones_b = np.hstack([pts_b, np.ones((n_pts, 1))])
                q = (H @ ones_b.T).T; q = q[:, :2] / q[:, 2:]
                ones_a = np.hstack([pts_a, np.ones((n_pts, 1))])
                t = (state.bridge_H_A2BG @ ones_a.T).T; t = t[:, :2] / t[:, 2:]
                
                base_mask_inner = base_mask if base_mask is not None else np.ones(query_img.shape[:2], dtype=np.float32)
                warped_fg0 = cv2.warpPerspective(query_img, H, (w_t, h_t), flags=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REFLECT101)
                warped_mask0 = cv2.warpPerspective(base_mask_inner, H, (w_t, h_t), flags=cv2.INTER_LINEAR)
                warped_fg, warped_mask = warped_fg0, warped_mask0

                em_for_score = getattr(state, 'last_edit_mask', None)

    # TPS 点只做几何有效性筛选: 用 edit_mask 会把未校正的畸变误判为有意编辑, 丢掉正确点。
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
                        _sm_log(f"[Smart Merge] TPS 匹配点过滤(几何): 保留 {len(keep_idx)}/{n_pts} 点")

    # 执行 TPS; 前后候选用同一份基础 edit_mask 评分
                tps_used = False
                g_base = None
                g_base_p85 = None
                if len(q_tps) >= 4:
                    tps_fg, tps_mask = warp_tps(
                        warped_fg0, warped_mask0, train_img, q_tps, t_tps, reg_lambda=1.5)
                    if tps_fg is not None:
                        g0_med, g0_p85 = _flow_residual_score(warped_fg0, warped_mask0, train_img, edit_mask=em_for_score)
                        g1_med, g1_p85 = _flow_residual_score(tps_fg, tps_mask, train_img, edit_mask=em_for_score)
                        p0t = _photometric_score(warped_fg0, warped_mask0, train_img, edit_mask=em_for_score)
                        p1t = _photometric_score(tps_fg, tps_mask, train_img, edit_mask=em_for_score)
                        scores_valid = max(g0_med, g0_p85, g1_med, g1_p85, p0t, p1t) < 1e8
                        # 基础单应已经把残差中位数压到 0.0–0.2px 时, TPS 的中位增益几乎为 0,
                        # 却可以在 p85 上放大 1px 左右——而 p85 变差正是长直边被拉成波浪/台阶的来源。
                        # 只接受"尾部也不变差"的结果; 真实的局部畸变修正是成片的, 一定伴随 p85 下降。
                        if scores_valid and g1_med <= g0_med + 0.10 and g1_p85 <= g0_p85 + 0.15 and p1t <= p0t + 2.0:
                            warped_fg, warped_mask = tps_fg, tps_mask
                            tps_used = True
                            _sm_log(f"[Smart Merge] TPS 验收通过: 几何残差 {g0_med:.2f}px→{g1_med:.2f}px "
                                  f"(p85 {g0_p85:.2f}→{g1_p85:.2f}) | TPS accepted")
                        else:
                            g_base = g0_med
                            g_base_p85 = g0_p85
                            _sm_log(f"[Smart Merge] TPS 拒绝: 几何残差 {g0_med:.2f}px→{g1_med:.2f}px "
                                  f"(p85 {g0_p85:.2f}→{g1_p85:.2f}), 光度 {p0t:.1f}→{p1t:.1f} | TPS rejected")
                else:
                    _sm_log(f"[Smart Merge] TPS 跳过，仅使用基础对齐 | TPS skipped, using base alignment")

    # 二阶段精校: 开关打开就执行, 不做残差评分判定(细节尺度评分不可靠)
                pass2_used = False
                if second_pass:
                    fg2, mask2 = refine_second_pass(
                        warped_fg, warped_mask, train_img, device, max_disp=16.0)
                    if fg2 is not None:
                        warped_fg, warped_mask = fg2, mask2
                        pass2_used = True
                        _sm_log("[Smart Merge] 二阶段精校已应用 | pass2 applied")
                if pass2_used:
                    # 对齐结果已变, 逐块光流必须重新量当前基线
                    g_base = g_base_p85 = None

                if tps_used or pass2_used or state.last_edit_mask is None:
                    state.last_edit_mask = _compute_edit_mask(
                        train_img, warped_fg, valid_mask=warped_mask
                    , device=device)
                em_for_score = state.last_edit_mask

                if warp_method:
                    if g_base is None:
                        g0m, g0p = _flow_residual_score(
                            warped_fg, warped_mask, train_img, edit_mask=em_for_score)
                    else:
                        g0m, g0p = g_base, g_base_p85
                    fg_r, mask_r = refine_with_optical_flow(
                        warped_fg, warped_mask, train_img,
                        device=device, max_flow_px=10.0, edit_mask=em_for_score,
                        flow_scale=flow_scale)
                    # 前后同口径: 用同一份 edit_mask 评分
                    g1m, g1p = _flow_residual_score(
                        fg_r, mask_r, train_img, edit_mask=em_for_score)
                    if _flow_acceptable(g0m, g0p, g1m, g1p):
                        warped_fg, warped_mask = fg_r, mask_r
                        state.last_residual_px = g1m
                        _sm_log(f"[Smart Merge] 逐块光流生效: {g0m:.2f}px→{g1m:.2f}px "
                              f"(p85 {g0p:.2f}→{g1p:.2f}) | per-crop flow accepted")
                    else:
                        state.last_residual_px = g0m
                        _sm_log(f"[Smart Merge] 逐块光流拒绝: {g0m:.2f}px→{g1m:.2f}px "
                              f"(p85 {g0p:.2f}→{g1p:.2f}) | per-crop flow rejected")
                state.match_level = "TPS+LoFTR"
                return warped_fg, warped_mask, True

    if H is None:
        H, b2bg_method, b2bg_resid = _select_b2bg_homography(state, 
            query_img, train_img, base_mask, device,
            crop_index=crop_index, crop_total=crop_total)
        if H is None:
            return None, None, False
        method_used = b2bg_method
        _sm_log(f"[Smart Merge] B→BG 对齐: {method_used} (残差 {b2bg_resid:.2f}px) | "
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
    state.last_edit_mask = _compute_edit_mask(
        train_img, warped_fg, valid_mask=warped_mask
    , device=device)

    if use_tps and getattr(state, 'disk_pts_q', None) is not None and len(state.disk_pts_q) >= 8:
        try:
            _ones = np.hstack([state.disk_pts_q, np.ones((len(state.disk_pts_q), 1))])
            q = (H @ _ones.T).T
            q = q[:, :2] / q[:, 2:]
            t = state.disk_pts_t
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

    # 可靠区外推: 只用未改色且局部一致的点建 TPS, 其余区域由平滑场外推。
            q, t, extrapolated = _filter_reliable_correspondences(
                q, t, h_t, w_t, state.last_edit_mask)
            if extrapolated:
                _sm_log(f"[Smart Merge] 可靠区外推: 仅用 {len(q)} 个未改色区对应点建场 | "
                      f"reliable-region TPS")

            tps_fg, tps_mask = warp_tps(
                warped_fg, warped_mask, train_img, q, t, reg_lambda=1.5)
            if tps_fg is not None:
                g0_med, g0_p85 = _flow_residual_score(
                    warped_fg, warped_mask, train_img, edit_mask=state.last_edit_mask)
                g1_med, g1_p85 = _flow_residual_score(
                    tps_fg, tps_mask, train_img, edit_mask=state.last_edit_mask)
                scores_valid = max(g0_med, g0_p85, g1_med, g1_p85) < 1e8
                # 外推时全图统计里必然包含“改色区”的残差, 门槛需与基线同等严格
                slack_med = 0.1 if extrapolated else 0.5
                slack_p85 = 0.4 if extrapolated else 1.0
                if (scores_valid and g1_med <= g0_med + slack_med
                        and g1_p85 <= g0_p85 + slack_p85):
                    warped_fg, warped_mask = tps_fg, tps_mask
                    _sm_log(f"[Smart Merge] TPS(DISK内点) 通过: {g0_med:.2f}px→{g1_med:.2f}px"
                          f"{' (可靠区外推)' if extrapolated else ''} | TPS accepted")
                else:
                    _sm_log(f"[Smart Merge] TPS(DISK内点) 拒绝: {g0_med:.2f}px→{g1_med:.2f}px | TPS rejected")
        except Exception as e:
            print(f"[Smart Merge] TPS(DISK内点) 失败: {e} | TPS failed")

    if warp_method:
        state.last_edit_mask = _compute_edit_mask(
            train_img, warped_fg, valid_mask=warped_mask
        , device=device)
        em_for_score = state.last_edit_mask
        g0m, g0p = _flow_residual_score(warped_fg, warped_mask, train_img, edit_mask=em_for_score)
        state.last_residual_px = g0m
        if g0m < 1.2:
            _sm_log(f"[Smart Merge] H后残差已很小({g0m:.2f}px), 跳过光流精修 | residual tiny, flow skipped")
            return warped_fg, warped_mask, True
            
        refined_fg, refined_mask = refine_with_optical_flow(
            warped_fg, warped_mask, train_img, device,
            edit_mask=em_for_score, flow_scale=flow_scale
        )
        em_refined = _compute_edit_mask(train_img, refined_fg, valid_mask=refined_mask, device=device)
        g1m, g1p = _flow_residual_score(refined_fg, refined_mask, train_img, edit_mask=em_refined)

        if _flow_acceptable(g0m, g0p, g1m, g1p):
            state.last_residual_px = g1m
            _sm_log(f"[Smart Merge] H+光流精修生效: {g0m:.2f}px→{g1m:.2f}px "
                  f"(p85 {g0p:.2f}→{g1p:.2f}) | H+flow accepted")
            return refined_fg, refined_mask, True
        _sm_log(f"[Smart Merge] H+光流精修拒绝: {g0m:.2f}px→{g1m:.2f}px "
              f"(p85 {g0p:.2f}→{g1p:.2f}) | H+flow rejected")
        return warped_fg, warped_mask, True
    return warped_fg, warped_mask, True

@torch.no_grad()
def _compute_edit_mask( warped_A, warped_B, d_lo=20.0, d_hi=60.0, valid_mask=None, *, device):
    """返回未编辑置信度；强色度和强亮度改变都会降低置信度。"""
    h, w = warped_A.shape[:2]
    dev = device
    if warped_B.shape[:2] != (h, w):
        warped_B = cv2.resize(np.ascontiguousarray(warped_B), (w, h),
                              interpolation=cv2.INTER_LINEAR)

    # 只算有效区 bbox: 全图中值/大核模糊比整块计算贵一个数量级。
    # 64px 边距覆盖中值核半径 7 + 模糊支撑 ~27, 有效区内结果与全图逐像素一致。
    bbox = None
    valid_np = None
    if valid_mask is not None:
        vm = valid_mask
        if not isinstance(vm, np.ndarray):
            vm = np.asarray(vm.detach().cpu() if hasattr(vm, "detach") else vm)
        if vm.ndim == 3:
            vm = vm[..., 0]
        if vm.shape == (h, w):
            ys, xs = np.where(vm > 0.0)
            if len(ys) == 0:
                return np.ones((h, w), dtype=np.float32)
            pad = 64
            y0, y1 = max(0, int(ys.min()) - pad), min(h, int(ys.max()) + pad + 1)
            x0, x1 = max(0, int(xs.min()) - pad), min(w, int(xs.max()) + pad + 1)
            if (y0, y1, x0, x1) != (0, h, 0, w):
                bbox = (y0, y1, x0, x1)
                warped_A = warped_A[y0:y1, x0:x1]
                warped_B = warped_B[y0:y1, x0:x1]
                vm = vm[y0:y1, x0:x1]
            valid_np = vm

    hh, ww = warped_A.shape[:2]
    la = _sm_rgb_to_lab(warped_A, dev)
    lb = _sm_rgb_to_lab(warped_B, dev)

    vb_a, vb_b = la[..., 1:3] - 128.0, lb[..., 1:3] - 128.0
    d_ab = (vb_a - vb_b).norm(dim=-1, keepdim=True)
    d_l = (la[..., 0:1] - lb[..., 0:1]).abs()
    # 暗部绝对色差不可靠, 补一个与亮度无关的色相角判据。
    c_a = vb_a.norm(dim=-1, keepdim=True)
    c_b = vb_b.norm(dim=-1, keepdim=True)
    cos_hue = (vb_a * vb_b).sum(dim=-1, keepdim=True) / (c_a * c_b).clamp_min(1e-3)
    d_hue = torch.rad2deg(torch.acos(cos_hue.clamp(-1.0, 1.0)))
    d_hue = d_hue * (torch.minimum(c_a, c_b) / 6.0).clamp(0.0, 1.0)
    # 近黑区再补按亮度归一化的色度差(分母 +16 抑制量化噪声); 否则阴影里的改色会被判成未编辑。
    lum_mean = (la[..., 0:1] + lb[..., 0:1]) * 0.5
    c_norm = torch.maximum(c_a, c_b)
    d_norm = d_ab * 255.0 / (lum_mean + 16.0)
    # 无改色证据(色差≈0 或双方接近中性)时不参与判定。
    d_norm = d_norm * ((d_ab - 1.5) / 3.0).clamp(0.0, 1.0)
    d_norm = d_norm * ((c_norm - 5.0) / 5.0).clamp(0.0, 1.0)

    def _confidence(diff, lo, hi):
        d = diff.clamp(0.0, 255.0).floor()          # 对齐 uint8 截断
        median_size = min(15, hh if hh % 2 else hh - 1, ww if ww % 2 else ww - 1)
        if median_size >= 3:
            d = _sm_median(d, median_size)
        d = _sm_fast_blur(d, 6.2)
        return ((hi - d) / max(hi - lo, 1e-6)).clamp(0.0, 1.0)

    # 四个判据随 d_hi 等比缩放: d_hi=60 时与原来的阈值完全一致
    k = max(float(d_hi), 1e-6) / 60.0
    conf = torch.minimum(_confidence(d_ab, d_lo, d_hi), _confidence(d_l, 25.0 * k, 60.0 * k))
    conf = torch.minimum(conf, _confidence(d_hue, 10.0 * k, 35.0 * k))
    # 归一化色度判据只补暗部: 亮部原来三个判据已经可靠, 放宽会误伤正常的亮度对齐。
    dark_w = ((70.0 - lum_mean) / 30.0).clamp(0.0, 1.0)
    conf = torch.minimum(conf, 1.0 - dark_w * (1.0 - _confidence(d_norm, 12.0 * k, 35.0 * k)))
    if valid_np is not None and valid_np.shape == (hh, ww):
        valid = _sm_as_float(valid_np, dev).clamp(0.0, 1.0)
        conf = conf * valid + (1.0 - valid)
    out = _sm_numpy(conf[..., 0]).astype(np.float32)
    if bbox is not None:
        full = np.ones((h, w), dtype=np.float32)
        full[bbox[0]:bbox[1], bbox[2]:bbox[3]] = out
        return full
    return out

