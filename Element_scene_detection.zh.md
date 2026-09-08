# Element Scene Detection 使用说明

## 📦 节点组简介

本节点组提供**视频场景检测 + 可视化时间线剪辑**能力，包含 3 个节点：

| 节点 | 作用 |
|---|---|
| **Element Scene Detection** | 主节点：导入视频、自动/手动分镜、时间线编辑 |
| **Element Video Clip** | 下游节点：输出选中片段的图像/音频/帧数/时长 |
| **Element Video Info** | 下游节点：输出视频 FPS、宽、高 |

---

## 🚀 快速上手

1. 添加 **Element Scene Detection** 节点，点击左上角 **Import** 导入本地视频
2. 点击 **Auto Split** 自动检测镜头切点（或按下面"时间线操作"手动剪辑）
3. 将主节点的 **info** 输出连接到 **Element Video Clip** 的 info 输入
4. 运行工作流，Element Video Clip 即可输出片段画面和音频

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

- **clip_select** 选择模式：
  - `select clip`：输出时间线上当前**选中的片段**
  - `segnum`：按 **SegNum** 序号选择（1 起，时间线顺序）
  - `first clip` / `last clip` / `all`：首段 / 末段 / 全部
- 输出：`images`、`audio`、`frame_count`、`seconds`、`first_image`、`last_image`

### Element Video Info

- 输出实际生效的 `FPS`（考虑 force_rate/subsampling）、`Width`、`Height`

---

## ⚠️ 注意事项

1. **依赖**：
   - 必需：`av` (PyAV)
   - 自动分镜：`pip install scenedetect`
   - 音轨播放/带音频导出：需系统安装 **ffmpeg**（缺失时导出为无声视频）
2. **临时文件**：上传的视频保存在系统临时目录，若被清理，需重新导入
3. **手动编辑优先**：一旦你修剪/重排过时间线，Auto Run 不会覆盖你的手动决定
4. info 输出是一个 JSON 包（含视频路径、片段区间、帧率等），专门对接本节点组下游，也可被 Element Video Clip / Element Video Info 解析
