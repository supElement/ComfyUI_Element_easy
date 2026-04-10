<div align="center">

[![中文](https://img.shields.io/badge/语言-简体中文-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


一些方便使用的小节点。因为太懒没有合并代码。包括：black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph,Element ImageCurve,Element HueSat,Element HueBright,Element HueHue,LoadImage_Preview,Frame Calculator,ImageSize Div,Smart merge images


## Installation

- 手动安装（Manual Installation）<br>
进入 ./ComfyUI/custom_nodes目录，运行以下代码：<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- 在manager管理器中安装（Install using Manager）<br>

  在comfyUI manager 中搜索 ComfyUI_Element_easy ，然后install。
 


## Update

## v1.4.3
  
  添加节点 Smart merge images。
  - 两张图像有足够的共同特征时，智能合并图像。
  - 纠正编辑模型（Flux2 Klein、Qwen Edit等）编辑图像后产生的像素偏移和色差。这种情况下的使用方法：将原图与编辑后的图像分别连接到 original_image 和 edited_crop_B 输入端口。
  - 合并剪切的图像到原图时，如果条件允许，最可靠的合并方案：original_image + edited_crop_B + original_crop_A。其中 original_crop_A 是从original_image中剪切的没有修改或变形的图像。
  - 优化 Smart merge images 节点的融合方法，对通过编辑模型（Flux2 Klein、Qwen Edit等）编辑后产生的像素偏移，有更好的纠正。 
  - 增加色彩匹配模式 Adaptive Local (strong), 可以更好的修复图像经过编辑后产生的色差。新增仅用于此模式下的两个参数：adapt_thresh（色彩差异阈值）, adapt_align (预匹配强度 - 修正某些情况下图像合并后，局部产生的色斑，值越高修正越明显，但对整体画面的色彩修正可能有负面影响)。
  - 增加 adapt_local_match 参数，为色彩匹配模式 Adaptive Local (strong) 的掩码融合提供更多选择，原来节点只有None模式。将feature_amount 与 adapt_kernel 合并为一个参数feather_kernel。

  <img width="1670" height="981" alt="Untitled-2" src="https://github.com/user-attachments/assets/8b5f4167-9529-4cdc-8df8-9b26f5355688" />


## v1.4.0

  - 在 LoadImage_Preview 节点上增加可选图像输入端口，可用于桥接预览中的编辑; 优化编辑面板布局。
  - 优化Element ImageCurve、Element HueSat、Element HueBright 和 Element HueHue 节点的载入预览逻辑。

## v1.3.8 
重要更新！！！
- 合并Element_SigmaGraph 与 Element_SigmaGraph(curve)节点为Element_SigmaGraph；去除graph_data的数值显示框。
- 在节点Element_SigmaGraph 中新增模式切换按钮 “C” 平滑曲线模式 和 线性模式。
- 修复Element_SigmaGraph 节点曲线模式下，sigma输出与曲线不匹配的问题。
- 修复快速缩小Element_SigmaGraph 节点高度时卡顿阻塞的问题。
- 修复某些情况下可能无法删除LoadImage_Preview节点的问题；优化 LoadImage_Preview 节点。

## v1.3.5 （Optimized in v1.4.0）
  
  添加 LoadImage_Preview 节点,其中浏览图像功能引用了作者Enashka的ComfyUI-nhknodes扩展image_loader_with_previews节点中的部分代码。<br>
  - 主要功能：浏览指定路径下的图像文件，选择其中一张后进入编辑面板（绘制mask或在图像上绘制方框、圆等）。
  - shift+左键：画直线、正方形或正圆。
  - L-alpha：用于载入图像alpha到画布。
  - Return：返回浏览图像面板。

  <img width="989" height="783" alt="image" src="https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16" />


## v1.3.1
  
  添加 Element HueBright（色相 VS 亮度）和 Element HueHue（色相 VS 色相）节点, 曲线调整，实时预览支持单张和序列帧图像。双击加点，右键减点。

## v1.3.0
  
  添加 Element HueSat 节点, 曲线调整（色相 VS 饱和度），实时预览支持单张和序列帧图像。双击加点，右键减点。<br>
  - 注意：不要在曲线两端同时加点，虽然不会发生错误，但会使另一个点无效，实时上端点有一个就能完成调色了,因为两端的曲线是闭环的。

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7
  
  添加 Element ImageCurve 节点, 曲线调色，实时预览支持单张和序列帧图像。双击加点，右键减点。

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （fix in V1.4.4）
  
  添加自定义sigma，Element_SigmaGraph 节点, 原始代码来自作者Temult 的 TWanSigmaGraph节点https://github.com/Temult/TWanSigmaGraph , 修改、优化、添加了很多内容。

  - 添加可选latent 输入端口以同步ltx audio vae 载入与卸载顺序。<br>
  - 添加可选custom_sigmas 输入端口，添加单独执行功能，方便将现有的sigma数列存储为预设<br>
  - 鼠标点击曲线的位置增减控制点（双击添加，右键删除），增减点时，保持其它控制点不变。 解除控制点 X 轴方向移动限制
  - 添加输出最大值 max value 参数，添加输出强制纠正。

  <img width="922" height="714" alt="image" src="https://github.com/user-attachments/assets/dce72d55-41a6-4a2e-9f6c-4350ef229dcd" />

## v1.2.3
  
  添加 ImageSize Div 节点。

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />


## v1.2.2
  
  添加帧数计算节点 Frame Calculator，计算结果为“取整”后+1，可选择Seconds或frame方式。

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  添加 Black White Color 节点,输入端口的mask会与由节点生成的mask做 ADD 运算。

  起初 ChessboardPattern 节点的 目的是为了在qwenEdit中风格转换时，抑制转换后的像素偏移问题，先转换mask区域风格，再转换invert mask区域（不过需要两次采样，这种方法在Klein模型中不起作用），后来发现ChessboardPattern这种遮罩会影响模型对物体的识别，所以才有了 Black White Color 节点。尽量使黑白区域的面积平均，以减少色调不一致的问题。
  
  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  添加 ChessboardPattern 节点，创建黑白棋盘格图像，可选择"by_grid_size"或"by_rows_and_cols"两种模式确定单位格子的尺寸。

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  添加Image Noise Using Mask节点，方便在图像的mask区域添加随机噪点，可调整噪点大小，透明度，可选择是否为灰度模式。
  
  添加Image Pad & Blur节点， target width 和 target height，有输入时会自动计算扩展（当参数小于原图像时为clip模式），此时aligment参数生效，可选择对齐模式（中心对齐、左对齐、右对齐、上对齐、下对齐、左上对齐、左下对齐、右上对齐、右下对齐）。
  pad模式可选择constant、reflect、edge，另一个和reflect效果相同。当选择constant模式时，feathering控制整体模糊程度，content_blur控制原图像扩展出的区域模糊度。constant模式时，background_color参数生效，兼容rgb色和HEX色码（16位色码）。

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="屏幕截图 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  添加Mask Stroke节点，mask描边，支持内外描边宽度和模糊度单独控制,支持非描边区域整体添加权重（使输出的mask没有权重为0的区域）。
  
  <img width="1295" height="731" alt="节点截图 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB：支持RGB和16位色彩信息输入，节点会自动识别色彩信息color_code。输出纯色图像，附带图像尺寸输出端口,图像尺寸会根据divisibale_by（整除）取近似值。

Text Line Break： 将输入的文本按字符数量换行，支持中文、英文和中英文混搭，支持标点符号避首尾。方便将提示词与生成的图像连接到一起，这要借助其它的节点，例如：Kjnode中的Add Label节点。

Random Chars (Append)：为输入的文本添加无效的特殊字符（可以自定义字符和个数），主要是为了不破坏提示词意图的前提下使生成的图像有更大的变化（不知是否起作用），因为qwen_image 和Z_image模型生成的图像构图的随机变化小。这里的“无效”是相对的。
                       可简单设置插入位置（before,end,insert）,其中insert的插入方式是将字符个数平均分配插入到原文本的每个标点符号后面，从后向前分配。




<img width="1590" height="1080" alt="节点截图 2025-12-04 164008" src="https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab" />


