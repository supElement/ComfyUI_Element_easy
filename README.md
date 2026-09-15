<div align="center">

[![中文](https://img.shields.io/badge/语言-简体中文-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy

一个以**可视化界面、方便交互**为主要方向的 ComfyUI 扩展。这个包里的节点不太一样：不是一个滑杆配一个数字，而是把完整的小工具直接搬进了节点里。

## 你能得到什么

**🎬 视频剪辑（Element Load and Edit Video）**
不用离开 ComfyUI 就能在节点上剪视频：自动检测镜头切换点，也可以手动切、剪短、调顺序，边剪边看，剪完直接输出画面和声音。

**🗂 多参考素材面板（Element Multi REF）**
给需要"参考图 + 首尾帧 + 参考视频 + 音频"一起输入的视频模型（MiniMax-H3、LTXV、Wan 等）用的素材台。每个素材都能裁剪、涂刷标注、掐时间段，还能存成预设——配合队列可以一次跑完多套素材和提示词，不用来回换图。

**🎛 曲线调色（HueSat / HueBright / HueHue / ImageCurve）**
像修图软件里的曲线一样调色，曲线直接画在图像上，拖一下立刻看到效果，视频也一样实时预览。

**📐 自定义采样曲线（Element_SigmaGraph）**
手动画采样器的 sigma 曲线，想在前段少花步数、后段多加细节时特别方便。

**🧩 还有 20 多个实用小节点**
图像智能合并、遮罩描边、图像加边模糊、帧数计算等等。

## 需要说明的劣势

- **上手需要一点时间**：面板式节点功能多，第一次打开会有"这按钮是干嘛的"的时刻，建议配合各节点的详细说明文档使用；
- **部分功能依赖外部程序**：视频导出带声音需要系统装 ffmpeg，自动分镜建议装 scenedetect，不装也能用，只是相应功能受限；
- **兼容性依赖较新的 ComfyUI 版本**（Multi REF 用了新版节点 API），老版本 ComfyUI 可能装不上；
- **节点多但彼此独立**：如果你只需要一两个功能，这个包对你来说可能偏大。

## 📦 节点导航

**🎬 视频与素材管理**

- [Element Multi REF](#element-multi-ref)（含辅助节点 Element ref convert）
- [Element Load and Edit Video](#element-load-and-edit-video)（含辅助节点 Element Video Clip / Element Video Info）
- [Minimax_H3-LatentUpscaler](#minimax_h3-latentupscaler)（含 Adv 版本）

**🎛 曲线调色**

- [Element ImageCurve](#element-imagecurve) · [Element HueSat](#element-huesat) · [Element HueBright](#element-huebright) · [Element HueHue](#element-huehue)

**🖌 图像编辑与遮罩**

- [LoadImage_Preview](#loadimage_preview) · [Smart merge images](#smart-merge-images) · [black_white_color](#black_white_color) · [mask_noise_element](#mask_noise_element) · [mask_stroke](#mask_stroke) · [image_pad_blur](#image_pad_blur)

**📐 图像生成与采样控制**

- [Element_SigmaGraph](#element_sigmagraph) · [chessboard](#chessboard) · [empty_image_rgb](#empty_image_rgb)

**🔧 数值与文本小工具**

- [Frame Calculator](#frame-calculator) · [ImageSize Div](#imagesize-div) · [random_chars](#random_chars) · [text_line_break](#text_line_break)

---

<a id="element-multi-ref"></a>
## Element Multi REF

<sub>v1.5.7 新增

详细说明：[中文](subMd/Element_multi_ref_zh.md) | [English](subMd/Element_multi_ref_en.md)</sub>

为 MiniMax-H3、LTXV、Wan、Klein、Qwen 等需要多路参考输入的视频/图像模型设计的素材及提示词管理方案：

- 21 个类型化槽位：参考图 ×9、参考视频 ×3，以及首尾帧、各类音频和 Prompt 卡片；
- 每个卡片配有独立的简易图像编辑器（裁剪、笔刷标注）和音视频时间线编辑器（按 17n+5、8n+1 等规则量化对齐）；
- 支持多个预设的存储、调用、载入、导出，以及收集归类所有参考和提示词；
- `run_preset_NUM` 参数对应预设列表中的序号，接收随提示词队列变化的输入时，配合采样推理节点可实现连续生成或编辑多张图像/视频；
- 面板底栏左下角有 4 个区域开关图标（参考图、首尾帧、音视频、Prompt），可自由组合面板以应对不同需求，甚至可以当作提示词预设节点使用。

辅助节点 **Element ref convert** 用于参考数据的格式转换。

<img width="1691" height="874" alt="Element Multi REF" src="https://github.com/user-attachments/assets/e8c32036-3a21-4864-93eb-228ffce3c82b" />

---

<a id="element-load-and-edit-video"></a>
## Element Load and Edit Video

<sub>v1.5.4 新增 · 

详细说明：[中文](subMd/Element_scene_detection.zh.md) | [English](subMd/Element_scene_detection.en.md)</sub>

可视化的单轨视频剪辑器节点：

- PySceneDetect 自动检测镜头切换点，也可在交互式时间线上手动切分、修剪、重排片段；
- 画面与音频同步预览；
- 直接输出片段帧序列与精确对应的音频，支持导出带音频的 mp4（需要 ffmpeg）。

辅助节点 **Element Video Clip**、**Element Video Info** 配合使用。

<img width="2147" height="1104" alt="Element Load and Edit Video" src="https://github.com/user-attachments/assets/5ba547a7-31c8-4323-bf40-7ec58f1b548e" />

---

<a id="minimax_h3-latentupscaler"></a>
## Minimax_H3-LatentUpscaler

<sub>v1.5.0 新增 · Adv 版本同期添加</sub>

只缩放视频潜空间的专用节点，不处理音频，输出端口为 Minimax H3 latent。

**Adv 版本**带校验，引入三种条件缩放模式：

| 模式 | 行为 |
|---|---|
| pass_through | 忽略校验直接通过 |
| NO_refs | 只对齐，不缩放 |
| refs | 缩放（质量最好） |

---

<a id="element-imagecurve"></a>
<a id="element-huesat"></a>
<a id="element-huebright"></a>
<a id="element-huehue"></a>
## 曲线调色系列

<sub>v1.2.7 ~ v1.3.1 陆续添加 · v1.6.0 优化</sub>

四个节点都是同一种交互方式：**曲线直接画在图像上实时预览，单击加点、右键减点**，支持单张和序列帧图像。

| 节点 | 曲线类型 |
|---|---|
| Element ImageCurve | RGB / R / G / B 通道曲线 |
| Element HueSat | 色相 → 饱和度 |
| Element HueBright | 色相 → 亮度 |
| Element HueHue | 色相 → 色相 |

> ⚠️ 除了Element ImageCurve以外，不要在曲线两端同时加点：两端的曲线是闭环的，同时加点会使其中一个点无效，实际上一个端点就足够完成调色。

<img width="1695" height="891" alt="Element HueSat" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />
<img width="1767" height="1008" alt="Element ImageCurve" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

---

<a id="loadimage_preview"></a>
## LoadImage_Preview

<sub>v1.3.5 新增 · v1.6.0 优化</sub>

浏览指定路径下的图像文件，选中后进入编辑面板进行简单编辑：自由绘制线条、mask、方框、圆，以及裁剪图像。

- `Shift + 左键`：画直线、正方形或正圆
- `L-alpha`：载入图像 alpha 通道到画布
- `Return`：在缩放面板和编辑面板之间切换
- 编辑模式下支持 `Ctrl+V` 粘贴图像，支持从网页或资源管理器直接拖入
- ComfyUI 的 input 目录常驻节点中，folder path 指定的目录作为额外增加的目录

<img width="1453" height="913" alt="LoadImage_Preview" src="https://github.com/user-attachments/assets/ed8d3d43-b18d-482b-84f1-6c0f6b87add5" />

---

<a id="smart-merge-images"></a>
## Smart merge images

<sub>v1.4.3 新增 · v1.4.8 优化</sub>

两张图像有足够的共同特征时，智能合并图像，适合把局部重绘的结果拼回原图：

- **最优输入方案**：original_image + edited_crop_B + original_crop_A。其中 original_crop_A 是从原图中剪切的没有修改或变形的图像，edited_crop_B 是经过编辑或重绘的图像；
- 支持分块合并：edited_crop_B 端口输入多张图像时，输出为最终合并后的单张图像。注意输入必须是 **Batch 而非 list**，如果是 list，要经过 Image List To Batch 节点转换。

<img width="2121" height="963" alt="image" src="https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4" />

---

<a id="black_white_color"></a>
## black_white_color

<sub>v1.1.3 新增</sub>

黑白分区的风格转换节点，用于在 qwenEdit 风格转换时抑制转换后的像素偏移问题：先转换 mask 区域风格，再转换 invert mask 区域；尽量使黑白区域面积平均，以减少色调不一致的问题。

输入端口的 mask 会与节点生成的 mask 做 ADD 运算。

<img width="1596" height="1084" alt="black_white_color" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />

---

<a id="mask_noise_element"></a>
## mask_noise_element

<sub>v0.0.8 新增（Image Noise Using Mask）</sub>

方便在图像的 mask 区域添加随机噪点。

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />

---

<a id="mask_stroke"></a>
## mask_stroke

<sub>v0.0.7 新增</sub>

mask 描边：内外描边宽度和模糊度单独控制，支持非描边区域整体添加权重（使输出的 mask 没有权重为 0 的区域）。

<img width="1295" height="731" alt="mask_stroke" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

---

<a id="image_pad_blur"></a>
## image_pad_blur

<sub>v0.0.8 新增 · v1.6.0 重构</sub>

可视化交互的图像扩展边缘节点（画布内直接用鼠标拖拽图像）。原图像的边缘均可单独指定是否羽化（共用同一羽化值），自定义背景，画布内自由或等比例缩放图像，指定背景颜色。

- 节点属性参数保留 target width / target height参数，添加div参数，辅助设置合法分辨率。
- 九宫格按钮组分别对应 9 种对齐模式（中心、左、右、上、下、左上、左下、右上、右下）
- pad 模式：constant / reflect / edge / stretch
  
详细说明：[中文](subMd/image_pad_blur_zh.md) | [English](subMd/image_pad_blur_en.md)</sub>

<img width="1510" height="855" alt="image" src="https://github.com/user-attachments/assets/e436ca37-d37e-4947-8b13-7a00c9721e7a" />

---

<a id="element_sigmagraph"></a>
## Element_SigmaGraph

<sub>v1.2.4 新增 · v1.5.3 增加 P 按钮</sub>

在节点上直接绘制自定义 sigma 曲线：单击加点、右键删点。

**P 按钮**：重排控制点的 x 坐标——当点数少于 steps+1 时，前 n-1 个点的 x 重排为 0, 1/steps, ..., (n-2)/steps，y 不变，最后一个点原样保留；当点数不少于 steps+1 时，取前 steps+1 个点均匀分布。简单说：**在不改变前面步数步幅的前提下，为后段增加采样步数（增加细节）**。

<img width="1176" height="794" alt="Element_SigmaGraph" src="https://github.com/user-attachments/assets/a8741609-cbe7-4ec8-a88d-5cae79b031a8" />

---

<a id="chessboard"></a>
## chessboard

<sub>v0.0.9 新增（ChessboardPattern）</sub>

创建黑白棋盘格图像。

<img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />

---

<a id="empty_image_rgb"></a>
## empty_image_rgb

<sub>v0.0.6 新增，v1.5.9优化 </sub>

创建单色图像，色彩从色轮上选择，明度滑条控制亮度；吸管可在屏幕任意位置取色，如果浏览器非 Chrome / Edge 96+，吸管可能不可用，可改用旁边的调色板按钮中的吸管。

<img width="1329" height="904" alt="image" src="https://github.com/user-attachments/assets/9dd2957b-e261-40ce-8041-87a83df33880" />

---

<a id="frame-calculator"></a>
## Frame Calculator

<sub>v1.2.2 新增，v1.5.9优化 </sub>

帧数计算节点，提供minimax H3、ltx2、wan合法预设，可通过div_by和offset自定义。

<img width="1154" height="655" alt="image" src="https://github.com/user-attachments/assets/9a99acc7-96b3-43e8-a3c7-1b4fd2ab93f4" />

---

<a id="imagesize-div"></a>
## ImageSize Div

<sub>v1.2.3 新增</sub>

尺寸对齐计算。

<img width="1317" height="596" alt="ImageSize Div" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />

---

<a id="random_chars"></a>
## random_chars

<sub>v0.0.6 新增（Random Chars Append）</sub>

为输入的文本追加无效的特殊字符（可以自定义字符和个数）。

---

<a id="text_line_break"></a>
## text_line_break

<sub>v0.0.6 新增，v1.5.9优化</sub>

将输入的文本按字符数量换行，支持标点符号避首尾，标点挤压、悬挂。最终效果取决于输出载体。

<img width="1693" height="981" alt="image" src="https://github.com/user-attachments/assets/62b3f66a-6cec-4d10-904a-5a33a102ba92" />

---

## Installation

### Manager 安装

在 ComfyUI Manager 中搜索 **ComfyUI_Element_easy**，然后 Install。

### 手动安装

进入 `./ComfyUI/custom_nodes` 目录，运行：

    git clone https://github.com/supElement/ComfyUI_Element_easy.git
    cd ComfyUI_Element_easy
    pip install -r requirements.txt
### 可选依赖：ffmpeg

节点的**视频导出（带音频）**功能需要系统安装 ffmpeg。Windows 用户从 [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) 下载，解压后将 bin 目录加入 PATH。

未安装 ffmpeg 时其余功能均正常，仅视频导出为无声视频。
