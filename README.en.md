<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenient use. Since I was too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, LoadImage_Preview, Frame Calculator, ImageSize Div, Smart merge images


## Installation

- **Manual Installation**<br>
Enter the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager**<br>

  Search for ComfyUI_Element_easy in the ComfyUI manager and then install.


## Update

## v1.4.1

  - Optimized the fusion method of the Smart merge images node, with better correction for pixel offset after editing models (Flux2 Klein, Qwen Edit, etc.).
  - Optimized the UI interface and functional comments of the LoadImage_Preview node.

## v1.4.0

  - Added an optional image input port to the LoadImage_Preview node, which can be used for bridging the preview of the edit; optimized the layout of the editing panel.
  - Optimized the loading preview logic of the Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.9
  
  Added the Smart merge images node.
  - Merges images intelligently when there are sufficient common features between the two images.
  - Corrects pixel offset and color shift after editing images with editing models (Flux2 Klein, Qwen Edit, etc.). In this case, the usage method is: connect the original image and the edited_crop_B to the original_image and edited_crop_B input ports, respectively.
  - When merging the cut image into the original image, if the conditions allow, the most reliable merging scheme is: original_image + edited_crop_B + original_crop_A. Among them, original_crop_A is the unmodified or deformed image cut from the original_image.

  ![image](https://github.com/user-attachments/assets/49b79f5b-4468-4656-ba6a-f9dbdf319ac0)

## v1.3.8 
Important Update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numerical display box for graph_data.
- Added a mode switch button "C" for smooth curve mode and linear mode in the Element_SigmaGraph node.
- Fixed the issue where the sigma output of the Element_SigmaGraph node does not match the curve in curve mode.
- Fixed the issue where the Element_SigmaGraph node is unresponsive when quickly reducing its height.
- Fixed the issue where the LoadImage_Preview node may not be deleted in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v1.4.0）
  
  Added the LoadImage_Preview node, where the image browsing feature references part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: browse image files in the specified path, select one to enter the editing panel (draw mask or draw rectangles, circles, etc. on the image).
  - Shift+left click: draw straight lines, squares, or circles.
  - L-alpha: used to load image alpha to the canvas.
  - Return: return to the image browsing panel.

  ![image](https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16)

## v1.3.1
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, with curve adjustment and real-time preview support for single and sequence frame images. Double-click to add points, right-click to remove points.

## v1.3.0
  
  Added Element HueSat node, curve adjustment (Hue vs Saturation), real-time preview support for single and sequence frame images. Double-click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will make the other point invalid, and a real-time top point can complete the color adjustment because the curves at both ends are closed loops.

  ![Image](https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8)

## v1.2.7
  
  Added Element ImageCurve node, curve color adjustment, real-time preview support for single and sequence frame images. Double-click to add points, right-click to remove points.

  ![Image](https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62)

## v1.2.4 （fix in V1.3.8）
  
  Added custom sigma, Element_SigmaGraph node, original code from the author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph , modified, optimized, and added a lot of content.

  - Added an optional latent input port to synchronize the load and unload order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added separate execution function, convenient to store existing sigma sequences as presets<br>
  - Click on the curve position to add or remove control points (double-click to add, right-click to delete), when adding or removing points, keep other control points unchanged. Release the X-axis movement restriction of control points

  ![image](https://github.com/user-attachments/assets/c3c362a8-fdb3-47c6-b7b6-159639a3a172)

## v1.2.3
  
  Added ImageSize Div node.

![image](https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9483-9da984d193ef)

## v1.2.2
  
  Added Frame Calculator node, calculates the result as "rounded" + 1, can choose Seconds or frame mode.

  ![image](https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03)

## v1.1.3
  
  Added Black White Color node, the input port's mask will be added to the mask generated by the node through ADD operation.

  The original purpose of the ChessboardPattern node was to suppress the pixel offset problem after style conversion in qwenEdit, first convert the style of the mask area, and then convert the invert mask area (however, this method does not work in the Klein model), and then it was found that the ChessboardPattern mask would affect the model's recognition of objects, so the Black White Color node was created. Try to make the area of the black and white regions as even as possible to reduce the problem of inconsistent hue.
  
  ![image](https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df)


## v0.0.9

  Added ChessboardPattern node, creates a black and white checkerboard image, with two modes to determine the size of the unit cell: "by_grid_size" or "by_rows_and_cols".

  ![image](https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482)


## v0.0.8

  Added Image Noise Using Mask node, convenient to add random noise in the mask area of the image, can adjust the size of the noise, transparency, and can choose whether to be grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, will automatically calculate the expansion when input is present (when the parameter is less than the original image, it is in clip mode), at this time, the alignment parameter takes effect, can choose alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, top-right alignment, bottom-left alignment, bottom-right alignment).
  pad mode can be constant, reflect, edge, another and reflect effect is the same. When choosing constant mode, feathering controls the overall blurring degree, content_blur controls the blurring degree of the expanded area of the original image. In constant mode, background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

![screen shot 2026-01-17 134457](https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266)
![screen shot 2026-01-17 134251](https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158)

  

  
## v0.0.7

  Added Mask Stroke node, mask outline, supports separate control of inner and outer stroke width and blur, supports overall weight addition to non-stroked areas (so that the output mask does not have a weight of 0 area).
  
  ![node screenshot 2025-12-05 011534](https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d)

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node will automatically identify color information color_code. Outputs pure color images, with image size output ports, image size will be approximated by divisible_by (divisible by).

Text Line Break： Breaks the input text into lines by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation avoidance at the beginning and end. Convenient to connect prompts and generated images together, which requires the help of other nodes, such as: Add Label node in Kjnode.

Random Chars (Append)：Adds invalid special characters to the input text (characters and number can be customized), mainly to make the generated image have greater changes without destroying the prompt intention, because the random changes in the image composition generated by qwen_image and Z_image models are small. Here "invalid" is relative.
                       Can simply set the insertion position (before, end, insert), where insert mode is to evenly distribute the number of characters inserted into the end of the original text after each punctuation mark, from the end to the front.




![node screenshot 2025-12-04 164008](https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab)