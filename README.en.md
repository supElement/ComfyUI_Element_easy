<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Simplified%20Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for easy use. Since I was too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, LoadImage_Preview, Frame Calculator, ImageSize Div, Smart merge images


## Installation

- **Manual Installation**<br>
Go to the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager**<br>

  Search for ComfyUI_Element_easy in the ComfyUI manager and then install.
 


## Update

## v1.3.9
  
  Added node Smart merge images, which intelligently merges images when there are sufficient common features between the two images.<br>
  - The most reliable merging scheme when conditions allow: original_image + edited_crop_B + original_crop_A. Here, original_crop_A is the unmodified or deformed image cropped from the original_image.

  ![image](https://github.com/user-attachments/assets/49b79f5b-4468-4656-ba6a-f9dbdf319ac0)


## v1.3.8 
Important update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numeric display box for graph_data.
- Added a mode switch button "C" for smooth curve mode and linear mode in the Element_SigmaGraph node.
- Fixed the issue where the sigma output of the Element_SigmaGraph node did not match the curve in curve mode.
- Fixed the issue where the Element_SigmaGraph node would freeze and block when quickly shrinking the node height.
- Fixed the issue where it may not be possible to delete the LoadImage_Preview node in some cases; optimized the LoadImage_Preview node.

## v1.3.5
  
  Added LoadImage_Preview node, which uses part of the code from the image_loader_with_previews node in the author Enashka's ComfyUI-nhknodes extension.<br>
  - Main function: browse image files in the specified path, select one, and then enter the editing panel (draw a mask or draw rectangles, circles, etc. on the image).
  - Shift+left click: draw straight lines, squares, or perfect circles.
  - L-alpha: used to load the alpha of the image to the canvas.
  - Return: return to the image browsing panel.

  ![image](https://github.com/user-attachments/assets/4ff0c960-3e0b-4403-ac7e-74f143e3d1b3)

## v1.3.1
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, with curve adjustment and real-time preview support for single images and sequence frames. Double-click to add points, right-click to remove points.

## v1.3.0
  
  Added Element HueSat node, with curve adjustment (Hue vs Saturation) and real-time preview support for single images and sequence frames. Double-click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause an error, but will make the other point invalid. One point on the top end of the curve is sufficient to complete the color correction, as the curves at both ends are closed loops.

  ![Image](https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8)

## v1.2.7
  
  Added Element ImageCurve node, with curve color adjustment and real-time preview support for single images and sequence frames. Double-click to add points, right-click to remove points.

  ![Image](https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62)

## v1.2.4 （fix in V1.3.8）
  
  Added custom sigma, Element_SigmaGraph node, with original code from the author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph, modified, optimized, and added many contents.

  - Added an optional latent input port to synchronize the load and unload order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, with a separate execution function, making it convenient to store existing sigma sequences as presets<br>
  - Clicking on the curve with the mouse adds control points at the location (double-click to add, right-click to delete), and the other control points remain unchanged. Lift the control point X-axis movement restriction

  
  ![image](https://github.com/user-attachments/assets/c3c362a8-fdb3-47c6-b7b6-159639a3a172)

## v1.2.3
  
  Added ImageSize Div node.

![image](https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef)


## v1.2.2
  
  Added Frame Calculator node, which calculates the result as "rounded up" + 1, and can be selected in Seconds or frame mode.

  ![image](https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03)


## v1.1.3
  
  Added Black White Color node, where the mask at the input port will be ADD-operators with the mask generated by the node.

  The initial purpose of the ChessboardPattern node was to suppress the pixel offset problem after the style transformation in qwenEdit, first transform the mask area style, and then transform the invert mask area (however, it requires two samplings, this method does not work in the Klein model), later it was found that the ChessboardPattern mask would affect the model's recognition of objects, so the Black White Color node was created. Try to make the area of black and white regions average to reduce the problem of inconsistent tones.
  
  ![image](https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df)


## v0.0.9

  Added ChessboardPattern node, which creates a black and white chessboard image. You can choose "by_grid_size" or "by_rows_and_cols" modes to determine the size of the unit cells.

  ![image](https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482)


## v0.0.8

  Added Image Noise Using Mask node, which is convenient to add random noise in the mask area of the image, and you can adjust the size, transparency, and choose whether it is grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, it will automatically calculate the expansion when there is input (when the parameter is less than the original image, it is clip mode), at this time the alignment parameter takes effect, you can choose the alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, left-top alignment, left-bottom alignment, right-top alignment, right-bottom alignment).
  Pad mode can be chosen as constant, reflect, edge, and the other is the same as reflect. When the constant mode is selected, feathering controls the overall blur degree, content_blur controls the blur degree of the original image extended out of the region. When the constant mode is selected, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

![screen shot 2026-01-17 134457](https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266)
![screen shot 2026-01-17 134251](https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158)

  

  
## v0.0.7

  Added Mask Stroke node, mask edge, which supports separate control of the edge width and blur for the inner and outer edges, and supports adding weights to the non-edges area as a whole (so that the output mask does not have a weight of 0 area).
  
  ![node screenshot 2025-12-05 011534](https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d)

  
## v0.0.6

Empty Image RGB: Supports RGB and 16-bit color information input, and the node will automatically recognize color information color_code. Outputs a solid color image with an image size output port, and the image size will be approximated by divisible_by (divisible by).

Text Line Break: Breaks the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation symbols avoiding the beginning and end. It is convenient to connect prompts and generated images together, which needs to be helped by other nodes, such as the Add Label node in Kjnode. Random Chars (Append): Adds invalid special characters to the input text (characters and quantity can be customized), mainly to make the generated image have more changes under the premise of not destroying the intention of the prompt word (whether it works is unknown), because the random changes in the composition of the images generated by the qwen_image and Z_image models are small. The "invalid" here is relative.
                       You can simply set the insertion position (before, end, insert), where insert's insertion method is to distribute the number of characters evenly between the original text's punctuation marks, distributing from the end.