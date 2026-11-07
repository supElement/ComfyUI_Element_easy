# -*- coding: utf-8 -*-
# Smart Merge 调参常量 / tuning constants
# 从 Smart_merge_images.py 移出, 供 element_easy 内各纯函数模块共用。

# 光流最大位移限幅(px)
MAX_FLOW_PX = 15.0
# TPS/评分类整画布算子只在该块掩码区域外扩这么多像素内计算, 结果回贴
REGION_MARGIN_PX = 200
# 光流估流长边上限: 更高分辨率只会线性变慢, 场最终被二次曲面约束+平滑, 不保留细节
FLOW_MAX_DIM = 1536
# 二阶段精校: 逐块光流之后再跑一次小幅逐块光流的位移上限(px)
SECOND_PASS_FLOW_PX = 4.0
BRIDGE_MAX_MEDIAN_DIFF = 60  # 桥接光度一致性阈值(0-255灰度中位差), 超过视为桥接H不可靠

# 光流降噪阈值(px): 小于该值的位移突变视为毛刺并平滑, 调大更平滑
FLOW_DENOISE_PX = 1.5

# split_grid 融合策略:
#   True  = 按 grid 权重覆盖式(over)融合: 边缘渐变/圆角与 ETM 一致,
#           但 overlap 区只保留一个来源, 不把多次 AI 重绘平均成雾状
#   False = grid 仅提供 alpha 与对齐锚点, 融合走节点原生逻辑
GRID_ACCUM_BLEND = True

GLOBAL_COLOR_STRENGTH = 0.35
GLOBAL_COLOR_MAX_SHIFT = (10.0, 4.0, 4.0)

# patch 色彩校正的 patch 边长 = 裁块短边 * 该比例(夹在 MIN..MAX), 与 feather 解耦
PATCH_COLOR_PATCH_FRAC = 0.12
PATCH_COLOR_PATCH_MIN = 48
PATCH_COLOR_PATCH_MAX = 160

# Patch_based_color: 单通道校正上限(L, a, b), 只修低幅色偏, 不把重绘的结构差异当色差涂抹
PATCH_COLOR_MAX_SHIFT = (12.0, 7.0, 7.0)
# 每块至少这么多比例的可信(未编辑)像素才参与统计
PATCH_COLOR_MIN_COVERAGE = 0.15
# 块内色差离散度(MAD)超过该值视为内容不一致(而非色偏), 置信度指数衰减
PATCH_COLOR_MAD_TAU = (8.0, 6.0, 6.0)
# 整图粗校正(全局光照对齐)在已编辑内容内保留的比例
PATCH_COLOR_EDITED_SCALE = 0.25
# 逐块局部校正在已编辑内容内保留的比例: 编辑区目标不同, 默认完全不施加
COLOR_LOCAL_EDITED_SCALE = 0.0

# 低频 LAB 差场上限(L, a, b): 只补缓变的整体/局部色偏, 不替代重绘
LOWFREQ_COLOR_MAX_SHIFT = (24.0, 10.0, 10.0)

# 无桥接 A 时, 特征匹配允许偏离 grid 坐标的最大比例与像素上限; grid 只作布局参考
GRID_ANCHOR_TOLERANCE = 0.12
GRID_ANCHOR_MAX_PX = 64.0
# 自动匹配被采纳所需的最少内点数(低于此值视为特征不足, 直接用 grid)
GRID_AUTO_MIN_INLIERS = 30

# ---- B→BG 模式(既无 split_grid 也无 original_crop_A) ----
# 特征 H 的几何残差中位数超过该值即视为不可信, 触发模板匹配/布局先验候选竞争
B2BG_TRUST_RESID = 2.5
# 有像素证据(特征/模板)的候选, 残差超过该值即弃用
B2BG_MAX_RESID = 12.0
# 内点在 4x4 网格中至少要占据的格数(低于该值只提示, 是否采用交给残差竞争)
B2BG_MIN_SPREAD_CELLS = 4
# 模板匹配放置的最低(边缘+亮度)归一化相关
B2BG_MIN_MATCH_NCC = 0.22
# DISK 失败时用 LoFTR 半稠密匹配兜底(低纹理/大面积改色块)
B2BG_USE_LOFTR = True
# 纯布局推断(无像素证据)的残差上限, 比实测候选宽
B2BG_LAYOUT_MAX_RESID = 40.0
# 布局放置还要过的结构相关下限; 且本格必须明显高于其它格子
B2BG_LAYOUT_MIN_NCC = 0.06
B2BG_LAYOUT_NCC_MARGIN = 0.02
