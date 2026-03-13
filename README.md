# ComfyUI_Element_easy


我自己使用的小节点，我不是程序员，所以可能不会继续更新。


## Installation

- 手动安装（Manual Installation）<br>
进入 ./ComfyUI/custom_nodes目录，运行以下代码（In the ./ComfyUI/custom_nodes directory, run the following）：<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- 在manager管理器中安装（Install using Manager）<br>

  在comfyUI manager 中搜索 ComfyUI_Element_easy ，然后install。（Search for "ComfyUI_Element_easy" in ComfyUI Manager, then click Install.）



## Update

## v1.2.4
  
  添加自定义sigma，Element_SigmaGraph 节点, 原始代码来自作者Temult 的 TWanSigmaGraph节点  https://github.com/Temult/TWanSigmaGraph ，感谢原作者Temult。
  因为Temult很久没有更新了，节点的sigma输出的值有bug，曲线调整无效。为了方便更新，我把它放到了这个仓库。

  - 添加可选latent 输入端口以同步ltx audio vae 载入与卸载顺序。<br>
  - 添加可选custom_sigmas 输入端口，添加单独执行功能，方便将现有的sigma数列存储为预设<br>
  - 新增平滑曲线模式节点 Element_SigmaGraph (Curve) 。保留直线模式节点 Element_SigmaGraph <br>
  - 鼠标点击曲线的位置增减控制点（双击添加，右键删除），增减点时，保持其它控制点不变。 解除控制点 X 轴方向移动限制<br>

  
  <img width="1114" height="857" alt="image" src="https://github.com/user-attachments/assets/c771ebd8-99f3-47bd-a41c-e4c8c0b46beb" />


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


