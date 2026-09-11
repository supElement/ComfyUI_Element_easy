# Element Multi REF 使用说明

适用于 ComfyUI 的多参考素材面板节点，为 MiniMax-H3 / LTXV 等视频生成模型提供 首尾帧、参考图、参考视频、驱动音频等多路输入的可视化管理与剪辑能力，内置 prompt 输入、预设快照（批量播放）与素材收集导出。

## 一、依赖

pip install av opencv-python numpy   # 必需
pip install scenedetect              # 可选：Auto Split 镜头检测更准更快

- 需要较新的 ComfyUI（comfy_api.latest 新版节点 API）。
- 系统安装 ffmpeg/ffprobe 可作为特殊音频格式（flac/alac 等）的解码兜底。

## 二、节点总览

| 节点 | 作用 |
|---|---|
| Element Multi REF | 可视化素材面板：导入 → 编辑 → 输出 REF_ALL_IN_ONE 信息包（+ prompt）；内置预设快照，run_preset_NUM 决定每次运行输出什么 |
| Element ref convert | 将信息包转换为 21 个类型化输出端口 + prompt + info 清单，供下游使用 |

### 2.1 run_preset_NUM（按次输出开关）

| 取值 | 行为 |
|---|---|
| 0（默认）| 输出当前面板状态（面板上已编辑的素材/槽位/prompt）|
| ≥ 1 | 输出第 n 个预设（1 起序）；越界自动取到最后一个预设 |

- 上游接一个每次运行数值变化的 Int 节点（计数器 / 列表 / 批次序号…）即可在一次批量任务中按顺序连播预设。
- 直接在节点 widget 上输入数字也会把对应预设应用到面板（约 0.2s 防抖；工作区当前已关联的预设会跳过）。
- info 包中会记录本次应用的预设（preset_index）与原始输入（run_preset_NUM）。

## 三、Element Multi REF（素材面板）

### 3.1 槽位一览（共 21 个）

| 分组 | 槽位 ID | 类型 |
|---|---|---|
| 首尾帧 | first_frame / last_frame | 图像 |
| 参考图 | ref_image_0 ~ ref_image_8 | 图像 ×9 |
| 参考视频 | ref_video_0 ~ ref_video_2 | 视频 ×3 |
| 视频配乐 | ref_video_audio_0 ~ _2 | 音频（可与视频联动）×3 |
| 参考音频 | ref_audio_0 ~ ref_audio_2 | 音频 ×3 |
| 驱动音频 | drive_audio | 音频 ×1 |

支持格式：

- 图像：.png .jpg .jpeg .webp .bmp
- 视频：.mp4 .mov .avi .mkv .webm .m4v
- 音频：.mp3 .wav .flac .ogg .oga .m4a .m4b .aac .opus .wma .aif .aiff .aifc .mka .weba .caf

### 3.2 Prompt

槽位网格下方是 prompt 输入框：

- 随工作流保存，并经 convert 节点的 prompt 端口输出；
- 每个预设快照各存一份 prompt —— 应用预设即切换 prompt；
- 在别处做文本条件时可以留空。

### 3.3 导入素材

- **拖拽**：把文件拖到任意槽位（或面板空白处，自动寻找同类空槽）。
- **点击**：点击空槽位打开文件选择框（按槽位类型过滤）。
- 批量拖入多文件时按槽位顺序自动分配。
- 上传按 SHA-256 去重，文件保存在 ComfyUI/input/element_multi_ref/。

### 3.4 槽位基本操作

- 悬停槽位显示按钮：✎ 编辑 / ✕ 移除。
- **拖拽互换**：把已填充槽位拖到另一个同类型槽位即交换内容。
- **右键菜单**：清空此槽位 / 重置编辑；空联动音频槽：打开关联视频编辑器 / 替换为独立音频。
- **点击**空联动音频槽会直接打开关联视频编辑器。
- 顶栏 Clear All：清空全部素材、编辑与 prompt —— **预设保留**。

### 3.5 图像编辑器

点击图像槽位 ✎ 打开：

**Crop 裁剪**：

- 拖拽画框、框内拖动移动；
- **边缘/角落调整**：指针移到框边缘显示 ↔/↕ 光标、四角显示斜向光标，按住拖动即可改尺寸，步进与 div by 一致；
- **div by**（默认 32）：尺寸对齐倍数（模型友好）；
- 顶行右侧 **W × H** 实时显示当前裁剪框尺寸（无裁剪框时为原图尺寸）；
- Clear crop 取消裁剪。

**Out W / Out H（输出分辨率）**：

- 画出裁剪框后自动跟随裁剪框尺寸；手动修改可为裁剪区域指定输出分辨率；
- **Lock ratio**：按裁剪框（无裁剪框则按原图）宽高比联动 W/H；仅当裁剪框宽高比变化时 Out 自动更新——移动或等比缩放裁剪框会保留手动值；
- **⟳ 重置**：有裁剪框回到裁剪框尺寸，无裁剪框回到源分辨率。

**Paint 笔刷标注**（可作 mask/inpaint 提示，工具栏固定在第二行）：

- 颜色、笔刷大小 2–80；指针为与笔刷等大的**圆环**（橡皮时为虚线圆环）；
- **Box / Circle**：拖拽绘制矩形/椭圆；**Outline** 勾选 = 描边（Box 四角为直角），取消 = 实心填充；形状激活时指针为十字；
- **Shift 快捷键**：Box/Circle 模式下按住 Shift = 正方形/正圆；自由画笔模式下按住 Shift = 从笔画起点画直线，松开 Shift 确定终点；
- **Eraser** 橡皮（与形状工具同用时为按形状擦除）、**Undo**（15 步）、**Clear paint** 清空；
- 笔迹以透明 PNG 叠加保存；paint 模式下裁剪框与压暗区域仍然可见。

### 3.6 音视频编辑器（时间线）

**蓝色选区或选择分段 = 最终输出范围**：

- 勾选 Use selection：以蓝框为准输出；
- 取消勾选：以点选的高亮分段为输出（Shift 范围选 / Ctrl 加减选；点选分段会自动取消 Use selection；一个都没选时输出播放头所在分段）；
- 拖蓝框两边缘调整、拖中间整体平移（视频可勾 Snap 吸附切点）；
- **Full** 全选（0 → 末尾）；**Fit** 适配窗口；**Zoom** 手动缩放。

**分段操作**：

- **Auto Split**：自动镜头切分（阈值 Thr；优先 PySceneDetect，未装则回退内置 HSV 直方图差分）；
- **Manual（快捷键 M）**：点击轨道任意位置切一刀；
- **右键分段边界**：合并相邻两段；
- **拖动边界**：默认 Roll（两侧同时伸缩）；按住 Alt/Ctrl = 单侧修剪/延长；
- **拖动分段本体**：重排顺序（青色插入线指示落点；多选段一起移动）；
- **Clear**：恢复默认时间线（清除切分与分段选择、播放头归零，Apply 后保存）。

**播放与走带**：

- 传输条：|◀（片头）、◀|（段头）、▶（播当前段）、▶▶（顺序播全部段）、|▶（段尾）、▶|（片尾）；
- 点击标尺/音频轨/蓝框中部：拖动播放头预览（画面+音频同步）。

**量化（输出长度 = a + n × div）**：

| Preset | div | a |
|---|---|---|
| MiniMax H3 (17n+5) | 17 | 5 |
| LTXV (8n+1) | 8 | 1 |
| 4n | 4 | 0 |
| Custom | 自定义 | 自定义 |

- 信息栏实时显示，如 [seg 1] Out: 107 = 17×6+5；
- 音频勾选 Quantize 后按 Ref FPS（默认 24）对齐。

**视频专属**：FPS（0 = 源帧率）输出重采样、Out W/H 缩放（锁比例、⟳ 重置）。

**音频专属**：Quantize / Ref FPS。

**快捷键**：

| 键 | 功能 |
|---|---|
| 空格 | 播放/停止全部段 |
| ← / → | 后退/前进 1 帧（音频 0.05s）；Shift = 1 秒 |
| I / O | 播放头位置设为入点/出点 |
| Home / End | 选区回片头/片尾 |
| M | 切换手动切分模式 |

### 3.7 视频音频联动（ref_video_audio_N）

- 导入带音频的视频到 ref_video_N 后，对应空槽 ref_video_audio_N 自动显示该视频波形（标注 from ref_video_N），无需单独导入；
- 输出时自动取该视频当前剪辑范围的音频；
- 点击/右键联动槽可：打开关联视频编辑器 / 替换为独立音频。

### 3.8 预设（快照与批量播放）

每个预设保存一份完整快照（素材 + 槽位编辑 + prompt）和一张面板缩略图。

- **Save Preset**：工作区当前来自某预设（青色关联）时原位覆盖（序号 / run_preset_NUM 不变），否则新建（覆盖弹窗中也可 Save as New）；可自选缩略图。
- **Presets 弹窗**：卡片网格，拖拽排序、点选、直接改名；卡片宽度/字号滑杆（记忆）；全屏切换；窗口尺寸记忆。
  - **Load…**：从 JSON 导出或 Collect 包（ZIP / 文件夹）导入；重复项（相同 pid 或内容相同）自动跳过。
  - **Export…**：全部预设导出为 JSON（缩略图转 data URL 内嵌）。
  - **Num / A-Z / Z-A**：按名称中数字或名称重排。
  - **Delete / Clear all**：删除所选 / 全部预设（Clear all 需二次确认）。
  - **Apply**：把所选预设应用到工作区。
- 徽章：青色卡片 = 工作区当前关联的预设；黄色数字 = 预设序号1基（即 run_preset_NUM 应填的值）。
- prompt 下方的 首/上一个/下一个/末 四个按钮可直接切换并应用预设。

### 3.9 Collect and Export

把当前工作区与所有预设打包为一个文件夹树：

    00_workspace/            ← 当前工作区（有素材或 prompt 时才导出）
      media/  extra/  thumbs/
    01_预设名/               ← 每个预设一个文件夹
      media/  extra/  thumbs/
    emr_package.json         ← 清单，可用 Presets → Load… 重新导入

- media/ = 槽位素材，extra/ = 笔刷/涂刷层，thumbs/ = 预设缩略图。
- 目标目录：已记住的文件夹静默写入（File System Access API）；否则询问一次并记住。底栏文件夹图标打开 **Export folder** 设置（查看 / 忘记 / 重新选择）。
- 兜底路径：服务端写盘到你输入的任意路径（默认 ComfyUI output 目录，路径可记忆）；再失败则回退为 ZIP 下载。
- 之后用 **Presets → Load… → Collect folder… / JSON / ZIP 文件** 重新导入（媒体文件自动重新上传并重映射路径）。

### 3.10 状态保存

- 全部素材、编辑、prompt 与预设自动序列化进隐藏 refs_data 字段，随工作流保存/加载；
- 素材以绝对路径记录，移动/删除源文件或换机需重新导入（提示 Material missing）。

## 四、Element ref convert（端口转换）

把 REF_ALL_IN_ONE 连到 info 输入即可。

### 4.1 输出端口（21 + prompt + info）

| 端口 | 类型 | 内容 |
|---|---|---|
| first_frame / last_frame | IMAGE | 首尾帧（应用裁剪/笔刷/缩放后） |
| ref_image_0 ~ _8 | IMAGE | 参考图 ×9 |
| ref_video_0 ~ _2 | IMAGE | 帧序列 [T,H,W,3]（0–1 浮点，按输出 FPS 重采样，空洞沿用前一帧） |
| ref_video_audio_0 ~ _2 | AUDIO | 视频联动音频或独立音频 |
| ref_audio_0 ~ _2 | AUDIO | 参考音频 |
| drive_audio | AUDIO | 驱动音频 |
| prompt | STRING | 面板中的 prompt 文本（或已应用预设的 prompt） |
| info | STRING | 每槽位清单 JSON |

### 4.2 空槽位占位行为

- 图像端口 → 64×64 黑图；
- 音频端口 → 1 秒 44100Hz 静音；
- 出错槽位同样返回占位，终端打印 [ElementRefConvert] slot ... → placeholder。

### 4.3 info 清单格式

{
  "version": 2,
  "producer": "ElementRefConvert",
  "slots": {
    "first_frame": {"has": true, "kind": "image", "w": 512, "h": 512},
    "ref_video_0": {"has": true, "kind": "video", "frames": 107, "w": 832, "h": 480},
    "drive_audio": {"has": true, "kind": "audio", "seconds": 5.0}
  },
  "missing": ["ref_image_0", "ref_audio_2"],
  "prompt": "..."
}

## 五、典型工作流

[Element Multi REF]
 ├─ first_frame  ← 首帧图（可裁剪/涂刷）
 ├─ ref_image_*  ← 角色/场景参考图
 ├─ ref_video_0  ← 参考视频（Auto Split → 选段 → 17n+5 对齐）
 ├─ drive_audio  ← 驱动音频（可选 Quantize）
 └─ prompt       ← 文本提示词（或用 run_preset_NUM 预设切换）
        │ REF_ALL_IN_ONE
        ▼
[Element ref convert]
 ├── first/last frame ──▶ 视频模型首尾帧条件
 ├── ref_image_*     ──▶ 参考图编码器
 ├── ref_video_0     ──▶ VAE Encode / 视频参考
 ├── ref_video_audio ──▶ 音频条件
 ├── drive_audio     ──▶ 音频驱动（S2V/口型等）
 └── prompt          ──▶ 文本条件

批量连播：run_preset_NUM 接计数器/列表，保存预设 #1…#n，队列跑 n 次——每次运行输出对应预设的素材与 prompt。

## 六、常见问题

**Q：音频槽位没有波形？**
依赖 /element_multi_ref/media_info 解码；PyAV 解不出时回退 ffmpeg CLI，请确认系统装有 ffmpeg。

**Q：终端出现 fps mismatch？**
标称帧率与帧数/时长偏差超 2% 时自动改用真实帧率，属正常修正，避免越播越偏。

**Q：Auto Split 提示 fallback？**
未安装 scenedetect，已回退内置 HSV 差分，建议 pip install scenedetect。

**Q：大视频编辑卡顿？**
帧预览（LRU 400 条）与解码帧缓存（约 600MB）已内置；用 Fit/Zoom 控制可视范围。

**Q：加载旧工作流提示 Material missing？**
源文件被移动/删除，重新拖入即可（上传去重不会重复存储）。

**Q：预设怎么搬到别的机器？**
预设保存在工作流（refs_data）里；用 Collect and Export（或 Presets → Export…）连同媒体一起导出，再到另一台机器 Presets → Load… 导入——只导 JSON 不带媒体时会提示改用 Collect folder…。

**Q：run_preset_NUM 超出预设数量？**
自动取到最后一个预设；0 始终输出当前面板状态。

**Q：文件存在哪？**
输入素材：ComfyUI/input/element_multi_ref/（含 _index.json 去重索引）；笔刷层：ComfyUI/output/element_multi_ref/paint/。
