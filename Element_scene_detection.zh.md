# Element Scene Detection 使用说明

## 📦 节点组简介

本节点组提供**视频场景检测 + 可视化时间线剪辑**能力，包含 3 个节点：

| 节点 | 作用 |
|---|---|
| **Element Scene Detection** | 主节点：导入视频、自动/手动分镜、时间线编辑 |
| **Element Video Clip** | 下游节点：输出选中片段的图像/音频/帧数/时长，以及描述本次实际输出的 info |
| **Element Video Info** | 下游节点：输出 FPS、宽、高（兼容两种 info 来源） |

---

## 🚀 快速上手

1. 添加 **Element Scene Detection** 节点，点击左上角 **Import** 导入本地视频
2. 点击 **Auto Split** 自动检测镜头切点（或按下面"时间线操作"手动剪辑）
3. 将主节点的 **info** 输出连接到 **Element Video Clip** 的 info 输入
4. 运行工作流，Element Video Clip 即可输出片段画面和音频
5. （可选）需要 FPS/宽高信息时：把 **Element Video Clip 的 info 输出**接入 **Element Video Info**，即可得到**缩放后实际输出**的尺寸

---

## 🎛 主节点工具栏

| 控件 | 说明 |
|---|---|
| **Import** | 上传本地视频文件 |
| **Auto Split** | 按 Threshold 立即执行 PySceneDetect 场景检测 |
| **Threshold** | 检测灵敏度（5–50），值越小切分越细 |
| **Manual** | 手动标记模式：开启后在轨道上点击/拖拽即可添加切点 |
| **Force 2** | 无切点时强制将视频分为两段 |
| **Auto Run** | ★ 勾选后，若时间线无手动编辑，**执行工作流时自动做场景分割** |
| **Sync Cuts** | 拉取后端缓存的自动切点（配合 Auto Run 使用） |
| **Clear** | 清空所有切点，恢复为完整单片段 |

主节点参数：

- **force_rate**：强制输出帧率，0 = 保持源帧率
- **subsampling**：隔 N 帧取 1 帧（如 2 = 输出帧数减半），下游 frame_count/seconds 会随之变化

---

## ✂️ 时间线操作

| 操作 | 效果 |
|---|---|
| **单击片段** | 选中（Ctrl+点击 加选，Shift+点击 范围连选） |
| **拖动片段** | 调整播放顺序 |
| **拖动片段边缘** | 修剪片段；按住 **Alt/Ctrl** 拖动 = 联动修剪（分割点整体移动） |
| **拖动标尺 / 红色游标** | 拖动预览画面 |
| **右键两片段交界** | 合并相邻片段 |
| **Fit / 左右箭头 / Select All** | 缩放适配、移动选中片段、全选 |

预览区下方控制条：跳到全片首/尾、跳到当前片段首/尾、**播放当前片段**、**连播全部片段**（带音频同步）。

底部 **Export**：将选中片段（或勾选 Export All 时全部片段）导出为带音频的 mp4 文件到 **Out Dir** 目录。

---

## 🔗 下游节点

### Element Video Clip

**clip_select** 选择模式：

- `select clip`：输出时间线上当前**选中的片段**
- `segnum`：按 **SegNum** 序号选择（1 起，时间线顺序）
- `first clip` / `last clip` / `all`：首段 / 末段 / 全部（`all` 按时间线顺序拼接）

**参数**：

| 参数 | 说明 |
|---|---|
| **target_long_edge** | ★ 将帧的**长边**缩放到指定值（保持宽高比）。小于源分辨率 = 缩小；大于源分辨率 = 放大；**0 = 保持源分辨率**。默认 1366（约 768P/16:9）。影响 `images`（开启 `scale_first_last` 时也影响首尾帧） |
| **scale_first_last** | ★ 开关：**ON** — `first_image`/`last_image` 跟随 `target_long_edge`（与 images 同尺寸）；**OFF**（默认）— 首尾帧始终保持**源分辨率**，不随缩放变化 |

**输出**：

| 输出 | 说明 |
|---|---|
| `images` | 选中片段的帧序列（尺寸受 `target_long_edge` 影响） |
| `audio` | 精确对应所选片段区间的音频（按片段解码，不带相邻片段的杂音） |
| `frame_count` / `seconds` | 帧数 / 时长（跟随 force_rate/subsampling） |
| `first_image` / `last_image` | 首帧 / 末帧（默认源分辨率，见 `scale_first_last`） |
| `info` | ★ 描述本次**实际输出**的信息包（真实 FPS、缩放后宽高、片段区间等），**可直接接入 Element Video Info** |

### Element Video Info

兼容**两种 info 来源**，自动识别：

| 接法 | FPS | Width / Height |
|---|---|---|
| 接 **Element Scene Detection** | force_rate/subsampling 换算后的有效帧率 | **源视频**分辨率 |
| 接 **Element Video Clip** | images 的真实播放帧率 | **缩放后实际输出**尺寸（直接取自输出张量） |

> 推荐：需要输出尺寸时用 Video Clip → Video Info 的接法，无需手动同步 `target_long_edge` 设置。

---

## 💡 长视频内存建议

`images` 以 float32 张量一次性输出，内存占用 ≈ `帧数 × 宽 × 高 × 12 字节`。长视频建议：

1. **每次只输出一个片段**（clip_select = select clip / segnum），多次执行替代一次 all
2. **用 `target_long_edge` 控制分辨率**（如下游只需 768P 参考视频，无需输出 4K）
3. 用 **subsampling / force_rate** 把帧率压到实际需要的值（如 24fps）
4. ComfyUI 启动参数可加 `--cache-lru`，缓解执行后节点缓存对 images 的占用

---

## ⚠️ 注意事项

1. **依赖**：
   - 必需：`av` (PyAV)
   - 自动分镜：`pip install scenedetect`
   - 音轨播放/带音频导出：需系统安装 **ffmpeg**（缺失时导出为无声视频）
2. **临时文件**：上传的视频保存至 ComfyUI/input/element_scene_detection/ 目录，随工作流持久保留；若文件被手动移动或删除，需重新导入
3. **手动编辑优先**：一旦你修剪/重排过时间线，Auto Run 不会覆盖你的手动决定
4. **info 输出**：两种 info 均为 JSON 包（含视频路径、片段区间、帧率等）。Scene Detection 的 info 描述**源视频**；Video Clip 的 info 描述**实际输出**，可被 Element Video Info 解析（也可回接 Element Video Clip）
5. **首尾帧尺寸**：默认保持源分辨率，保证随时有全质量参考帧；需要与 images 同尺寸时开启 `scale_first_last`
