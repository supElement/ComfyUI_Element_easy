<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenient use. Since I was too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, LoadImage_Preview, Frame Calculator, ImageSize Div, Smart merge images


## Installation

- **Manual Installation**<br>
Navigate to the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager**<br>

  Search for ComfyUI_Element_easy in the ComfyUI manager, then install.


## Update

## v1.3.9
  
  Added the node Smart merge images, which intelligently merges images when there are sufficient common features between the two images.<br>
  - The most reliable merging scheme when conditions allow: original_image + edited_crop_B + original_crop_A. Here, original_crop_A is the unmodified or deformed image cut from the original_image.

  <img width="1011" height="970" alt="image" src="https://github.com/user-attachments/assets/49b79f5b-4468-4656-ba6a-f9dbdf319ac0" />


## v1.3.8 
Important update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numeric display box for graph_data.
- Added a mode switch button "C" in the Element_SigmaGraph node for smooth curve mode and linear mode.
- Fixed the issue where the sigma output of the Element_SigmaGraph node did not match the curve in curve mode.
- Fixed the issue where the Element_SigmaGraph node became unresponsive when resized quickly.
- Fixed the issue where the LoadImage_Preview node might not be deletable in certain cases; optimized the LoadImage_Preview node.

## v1.3.5
  
  Added LoadImage_Preview node, which uses part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: browse image files in the specified path, select one, and enter the editing panel (draw a mask or draw a rectangle, circle, etc. on the image).
  - Shift+left click: draw a straight line, square, or circle.
  - L-alpha: used to load image alpha to the canvas.
  - Return: return to the image browsing panel.

  <img width="1364" height="1016" alt="image" src="https://github.com/user-attachments/assets/4ff0c960-3e0b-4403-ac7e-74f143e3d1b3" />

## v1.3.1
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, with curve adjustment and real-time preview support for single images and sequence frames. Double-click to add points, right-click to remove points.

## v1.3.0
  
  Added Element HueSat node, with curve adjustment (Hue vs Saturation), real-time preview support for single images and sequence frames. Double-click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause an error, but will make the other point invalid. A single endpoint on the real-time top end is enough to complete the color correction, because the curves at both ends are closed loops.

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7
  
  Added Element ImageCurve node, with curve color adjustment, real-time preview support for single images and sequence frames. Double-click to add points, right-click to remove points.

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （fixed in V1.3.8）
  
  Added custom sigma, Element_SigmaGraph node, original code from the author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph, modified, optimized, and added many contents.

  - Added an optional latent input port to synchronize the loading and unloading sequence of ltx audio vae.<br>
  - Added an optional custom_sigmas input port to add separate execution function, convenient to store existing sigma sequences as presets<br>
  - Click on the curve at the position to increase or decrease control points (double-click to add, right-click to delete), and keep other control points unchanged when increasing or decreasing points. Release the control point X-axis movement restriction

  
  <img width="1021" height="797" alt="image" src="https://github.com/user-attachments/assets/c3c362a8-fdb3-47c6-b7b6-159639a3a172" />

## v1.2.3
  
  Added ImageSize Div node.

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9483-9da984d193ef" />


## v1.2.2
  
  Added Frame Calculator node, which calculates the result as "round up" + 1, and can be selected in Seconds or frame mode.

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  Added Black White Color node, where the input port's mask will be added to the mask generated by the node through ADD operation.

  The original purpose of the ChessboardPattern node was to suppress the pixel shift problem after style transformation in qwenEdit, first transform the mask area style, then transform the invert mask area (however, this method does not work in Klein model), later it was found that the ChessboardPattern mask would affect the model's recognition of objects, so the Black White Color node was born. Try to make the area of black and white regions average to reduce the problem of inconsistent hue.

  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  Added ChessboardPattern node, which creates a black and white chessboard image and can be selected in "by_grid_size" or "by_rows_and_cols" modes to determine the size of the unit cell.

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  Added Image Noise Using Mask node, which is convenient to add random noise in the mask area of the image, can adjust the size and transparency of the noise, and can choose whether it is grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, when input is present, it will automatically calculate the expansion (when the parameter is less than the original image, it is clip mode), at this time the alignment parameter takes effect, and alignment mode can be selected (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, top-right alignment, bottom-left alignment, bottom-right alignment).
  pad mode can be selected as constant, reflect, edge, another one is the same as reflect. When the constant mode is selected, feathering controls the overall blurring degree, content_blur controls the blurring degree of the expanded area of the original image. When the constant mode is selected, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-digit color code).

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="屏幕截图 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  Added Mask Stroke node, mask outline, supports independent control of inner and outer outline width and blur, supports the overall addition of weight to the non-outline area (so that the output mask has no area with weight of 0).
  
  <img width="1295" height="731" alt="节点截图 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node automatically identifies color information color_code. Outputs a solid color image with image size output port, the image size will be approximated according to divisible_by (integer division).

Text Line Break： Breaks the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation avoidance at the beginning and end. Convenient to connect prompts with generated images, which requires other nodes, such as the Add Label node in Kjnode.

Random Chars (Append)：Adds invalid special characters to the input text (characters and number can be customized), mainly to make the generated image have more changes without destroying the intention of the prompt (whether it is effective), because the random changes in the composition of the generated image by qwen_image and Z_image models are small. The "invalid" here is relative.
                       Can simply set the insertion position (before, end, insert), where insert mode is to evenly distribute the number of characters to the end of the original text after each punctuation mark, from the end forward.