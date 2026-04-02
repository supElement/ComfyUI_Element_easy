<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenience. Since I was too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, LoadImage_Preview, Frame Calculator, ImageSize Div


## Installation

- **Manual Installation**<br>
Navigate to the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager**<br>

  Search for ComfyUI_Element_easy in the ComfyUI manager and then install.


## Update

## v1.3.9
  
  Added node Smart merge images, which intelligently merges two images if they have sufficient common features.<br>
  - The most reliable merging solution if conditions allow: original_image + edited_crop_B + original_crop_A. Here, original_crop_A is the unmodified or deformed image cropped from original_image.

  <img width="1011" height="970" alt="image" src="https://github.com/user-attachments/assets/49b79f5b-4468-4656-ba6a-f9dbdf319ac0" />


## v1.3.8 
Important update!!!<br>
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numerical display box for graph_data.
- Added a mode switch button "C" in the Element_SigmaGraph node for smooth curve mode and linear mode.
- Fixed the issue where the sigma output in the Element_SigmaGraph node did not match the curve in curve mode.
- Fixed the issue where the Element_SigmaGraph node would freeze when quickly resizing its height.
- Fixed the issue where the LoadImage_Preview node could not be deleted in some cases; optimized the LoadImage_Preview node.

## v1.3.5
  
  Added LoadImage_Preview node, which references part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: browse image files in the specified path, select one, and enter the editing panel (drawing mask or drawing rectangles, circles, etc. on the image).
  - Shift+left click: draw lines, squares, or circles.
  - L-alpha: used to load the alpha of the image onto the canvas.
  - Return: return to the image browsing panel.

  <img width="1364" height="1016" alt="image" src="https://github.com/user-attachments/assets/4ff0c960-3e0b-4403-ac7e-74f143e3d1b3" />

## v1.3.1
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, curve adjustment, real-time preview supports single images and sequence frame images. Double-click to add points, right-click to remove points.

## v1.3.0
  
  Added Element HueSat node, curve adjustment (Hue vs Saturation), real-time preview supports single images and sequence frame images. Double-click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause an error, but will make the other point invalid. A single endpoint at the top of the curve is enough to complete the color adjustment, as the curves at both ends are closed loops.

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7
  
  Added Element ImageCurve node, curve coloring, real-time preview supports single images and sequence frame images. Double-click to add points, right-click to remove points.

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （fixed in V1.3.8）
  
  Added custom sigma, Element_SigmaGraph node, original code from author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph , modified, optimized, and added a lot of content.

  - Added an optional latent input port to synchronize the load and unload order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added a separate execution function, convenient to store existing sigma sequences as presets<br>
  - Click the position on the curve with the mouse to add or remove control points (double-click to add, right-click to delete), keep other control points unchanged when adding or removing points. Remove the X-axis movement restriction for control points.

  
  <img width="1021" height="797" alt="image" src="https://github.com/user-attachments/assets/c3c362a8-fdb3-47c6-b7b6-159639a3a172" />

## v1.2.3
  
  Added ImageSize Div node.

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />


## v1.2.2
  
  Added Frame Calculator node, calculates the result as "rounded" and +1, with options for Seconds or frame.

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  Added Black White Color node, the mask input port will perform an ADD operation with the mask generated by the node.

  Initially, the purpose of the ChessboardPattern node was to suppress the pixel offset problem after the style transformation in qwenEdit, first transform the mask area style, then transform the invert mask area (however, this method does not work in the Klein model), later found that the ChessboardPattern mask would affect the model's recognition of objects, so the Black White Color node was created. Try to make the area of black and white regions as even as possible to reduce the problem of inconsistent hue.
  
  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  Added ChessboardPattern node, creates a black and white checkerboard image, and can be selected in "by_grid_size" or "by_rows_and_cols" modes to determine the size of the unit cells.

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  Added Image Noise Using Mask node, easily add random noise to the mask area of the image, adjustable noise size, transparency, and can be selected for grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, automatically calculate expansion when there is input (clip mode when parameters are less than the original image), at this time, alignment parameters take effect, can be selected for alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, upper left alignment, lower left alignment, upper right alignment, lower right alignment). Pad mode can be selected as constant, reflect, edge, another one with the same effect as reflect. When constant mode is selected, feathering controls the overall blurring degree, content_blur controls the blurring degree of the expanded area of the original image. When in constant mode, background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="屏幕截图 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  Added Mask Stroke node, mask outlining, supports independent control of stroke width and blur for inside and outside, supports the overall addition of weight to non-stroked areas (making the output mask have no area with weight of 0).
  
  <img width="1295" height="731" alt="节点截图 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node automatically identifies the color information color_code. Outputs a solid color image, with an output port for image size, and the image size will be approximated according to divisible_by (divisible). 

Text Line Break：Breaks the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation symbols to avoid the beginning and end. Convenient for connecting prompts and generated images together, which requires the help of other nodes, such as the Add Label node in Kjnode.

Random Chars (Append)：Appending invalid special characters (characters and number can be customized) to the input text, mainly to make the generated image have greater changes without destroying the intent of the prompt (unknown whether it is effective), because the random changes in the composition of the images generated by qwen_image and Z_image models are small. Here, "invalid" is relative.
                       Can be simply set to insert position (before, end, insert), where the insert method is to evenly distribute the number of characters to be inserted behind the punctuation symbols of the original text, from the end to the front.




<img width="1590" height="1080" alt="节点截图 2025-12-04 164008" src="https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab" />