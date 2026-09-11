<div align="center">

[![中文](https://img.shields.io/badge/语言-简体中文-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


一些方便使用的节点，可视化UI界面，便于交互是这个扩展的主要方向。包括：Element Multi REF, Element Load and Edit Video，Minimax_H3-LatentUpscaler, Smart merge images,LoadImage_Preview,Element_SigmaGraph,Element ImageCurve,Element HueSat,Element HueBright,Element HueHue,Frame Calculator,ImageSize Div,black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break.


## Installation

### 手动安装（Manual Installation）<br>

   进入 ./ComfyUI/custom_nodes目录，运行以下代码：<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git
      cd ComfyUI_Element_easy
      pip install -r requirements.txt
  可选：ffmpeg
  节点的**视频导出（带音频）**功能需要系统安装 ffmpeg，Windows从 <a href="https://www.gyan.dev/ffmpeg/builds/">ffmpeg</a>下载，解压后将 bin 目录加入 PATH
  未安装 ffmpeg 时其余功能均正常，仅导出为无声视频



### 管理器中安装（Install using Manager）<br>

  - 在comfyUI manager 中搜索 ComfyUI_Element_easy, --然后install。
 


## Update

## v1.5.5

- 增加Element Multi REF和辅助节点Element ref convert。
- 为 MiniMax-H3 等需要多路参考输入的视频生成模型设计的素材管理方案；配有简易图像编辑器和音视频编辑器，每个参考卡片的编辑器参数独立。
- [中文版详细说明](Element_multi_ref_zh.md)
- [英文版详细说明](Element_multi_ref_en.md)

<img width="1520" height="1083" alt="image" src="https://github.com/user-attachments/assets/a25dd0eb-77b2-4111-a60e-5ab787dac767" />


## v1.5.4

- 增加 Element Load and Edit Video 视频载入、简单单轨编辑节点，和相关辅助节点Element Video Clip 和 Element Video Info。
- "可视化单轨视频剪辑器"节点：在交互式时间线上手动修剪、重排、预览片段。
- [中文版详细说明](Element_scene_detection.zh.md)
- [英文版详细说明](Element_scene_detection.en.md)

<img width="2147" height="1104" alt="image" src="https://github.com/user-attachments/assets/5ba547a7-31c8-4323-bf40-7ec58f1b548e" />

## v1.5.0
  
添加 Minimax_H3-LatentUpscaler 潜空间缩放节点，只缩放视频的潜空间，没有对音频做任何处理，输出端口为Minimax H3 latent。
添加 Minimax_H3-LatentUpscaler_Adv  带校验的潜空间缩放节点。引入条件缩放模式，可选择忽略（pass_through）、只对齐不缩放（NO_refs）、缩放(refs)三种模式，质量最好的是缩放(refs)模式。

## v1.4.3（Optimized in V1.4.8）
  
  添加节点 Smart merge images; 两张图像有足够的共同特征时，智能合并图像。
  - 最优方案：original_image + edited_crop_B + original_crop_A。其中 original_crop_A 是从original_image中剪切的没有修改或变形的图像，edited_crop_B是经过编辑或重绘的图像。
  - 增对分块合并的支持。即edited_crop_B端口输入多张图像时，输出为最终合并后的单张图像。注意：要求输入到edited_crop_B端口的图像是 Batch 而非 list，如果是list，要经过 Image List To Batch 节点转换。

  <img width="2121" height="963" alt="image" src="https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4" />

## v1.3.5 （Optimized in v1.5.6）
  
  添加 LoadImage_Preview 节点。
  - 主要功能：浏览指定路径下的图像文件，选择其中一张后进入编辑面板进行简单编辑。包括：自由绘制线条、mask、方框、圆，裁剪图像。
  - shift+左键：画直线、正方形或正圆。
  - L-alpha：用于载入图像alpha到画布。
  - Return：在缩略图面板和编辑面板之间切换。
  - 图像编辑模式下，支持ctrl+v 粘贴图像，支持鼠标拖入图像（例如：从网页或资源管理器拖入）。
  - ComfyUI的input目录常驻节点中，folder path的指定做为增加的目录。

  <img width="1453" height="913" alt="image" src="https://github.com/user-attachments/assets/ed8d3d43-b18d-482b-84f1-6c0f6b87add5" />



## v1.3.1 （Optimized in V1.4.5）
  
  添加 Element HueBright（色相 VS 亮度）和 Element HueHue（色相 VS 色相）节点, 曲线调整，实时预览支持单张和序列帧图像。单击加点，右键减点。

## v1.3.0 （Optimized in V1.4.5）
  
  添加 Element HueSat 节点, 曲线调整（色相 VS 饱和度），实时预览支持单张和序列帧图像。单击加点，右键减点。<br>
  - 注意：不要在曲线两端同时加点，虽然不会发生错误，但会使另一个点无效，实时上端点有一个就能完成调色了,因为两端的曲线是闭环的。

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7 （Optimized in V1.4.5）
  
  添加 Element ImageCurve 节点, 曲线调色，实时预览支持单张和序列帧图像。单击加点，右键减点。

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （add "P" button in V1.5.3）
  
  添加自定义sigma，Element_SigmaGraph 节点。
  - 鼠标点击曲线的位置增减控制点（单击加点，右键删除）
  - P 按钮行为：当点数少于 steps+1 时，前 n-1 个点的 x 重排为 0, 1/steps, 2/steps, ..., (n-2)/steps，y 不变；最后一个点（x, y）原样保留。当点数不少于 steps+1 时，取前 steps+1 个点，x 均匀分布为 0, 1/steps, ..., 1，y 不变。PS：有什么用？在不改变前面步数的步幅时，为后面增加采样步数（增加细节）。

  <img width="1176" height="794" alt="image" src="https://github.com/user-attachments/assets/a8741609-cbe7-4ec8-a88d-5cae79b031a8" />

## v1.2.3
  
  添加 ImageSize Div 节点。

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />


## v1.2.2
  
  添加帧数计算节点 Frame Calculator，计算结果为“取整”后+1。

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  添加 Black White Color 节点,输入端口的mask会与由节点生成的mask做 ADD 运算。
  为了在qwenEdit中风格转换时，抑制转换后的像素偏移问题，先转换mask区域风格，再转换invert mask区域。尽量使黑白区域的面积平均，以减少色调不一致的问题。
  
  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  添加 ChessboardPattern 节点，创建黑白棋盘格图像。

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  添加Image Noise Using Mask节点，方便在图像的mask区域添加随机噪点。
  添加Image Pad & Blur节点， target width 和 target height，可选择对齐模式（中心对齐、左对齐、右对齐、上对齐、下对齐、左上对齐、左下对齐、右上对齐、右下对齐）。
  pad模式可选择constant、reflect、edge，另一个和reflect效果相同。当选择constant模式时，feathering控制整体模糊程度，content_blur控制原图像扩展出的区域模糊度。constant模式时，background_color参数生效，兼容rgb色和HEX色码（16位色码）。

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="屏幕截图 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  添加Mask Stroke节点，mask描边，支持内外描边宽度和模糊度单独控制,支持非描边区域整体添加权重（使输出的mask没有权重为0的区域）。
  
  <img width="1295" height="731" alt="节点截图 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB：支持RGB和16位色彩信息输入。
Text Line Break： 将输入的文本按字符数量换行，支持标点符号避首尾。
Random Chars (Append)：为输入的文本添加无效的特殊字符（可以自定义字符和个数），
                       
<img width="1590" height="1080" alt="节点截图 2025-12-04 164008" src="https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab" />


