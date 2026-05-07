<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenience. Since I'm too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, LoadImage_Preview, Frame Calculator, ImageSize Div, Smart merge images


## Installation

- **Manual Installation** <br>
Go to the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager** <br>

  Search for ComfyUI_Element_easy in the ComfyUI manager and then install.


## Update
## v1.4.6
  
Added preview button support for Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes to KJnode's GetNode node; modified the curve type of Element ImageCurve node.

## v1.4.5
  
Modified the interaction logic of Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes to add points by clicking the left mouse button and directly drag the new added points; enhanced the impact of Element HueBright node on low saturation colors, improving the range of brightness adjustment.

## v1.4.4
  
Fixed the output bug of Element_SigmaGraph node linear mode "L", added output max value parameter, and added output forced correction.

## v1.4.3
  
  Added Smart merge images node.
  - Merges images intelligently when there are enough common features between the two images.
  - Corrects pixel offset and color difference in images after editing by editing models (Flux2 Klein, Qwen Edit, etc.). The usage method in this case: connect the original image and the edited image to the original_image and edited_crop_B input ports, respectively.
  - When merging the cropped image into the original image, if the conditions allow, the most reliable merging scheme is: original_image + edited_crop_B + original_crop_A. Among them, original_crop_A is the unmodified or deformed image cut from original_image.
  - Optimized the merging method of Smart merge images node, which has better correction for pixel offset generated after editing by editing models (Flux2 Klein, Qwen Edit, etc.).
  - Added color matching mode Adaptive Local (strong), which can better repair the color difference generated after editing the image. Two new parameters are added specifically for this mode: adapt_thresh (color difference threshold), adapt_align (pre-matching strength - corrects local color spots generated after image merging, the higher the value, the more obvious the correction, but it may have a negative impact on the overall color correction of the image).
  - Added adapt_local_match parameter, providing more options for mask fusion in color matching mode Adaptive Local (strong). The original node only had None mode. The feature_amount and adapt_kernel are merged into one parameter feather_kernel.

  <img width="1670" height="981" alt="Untitled-2" src="https://github.com/user-attachments/assets/8b5f4167-9529-4cdc-8df8-9b26f5355688" />


## v1.4.0

  - Added an optional image input port to LoadImage_Preview node, which can be used for bridging the preview of editing; optimized the layout of the editing panel.
  - Optimized the loading preview logic of Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.8 
Important Update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numeric display box for graph_data.
- Added a mode switch button "C" for smooth curve mode and linear mode in the Element_SigmaGraph node.
- Fixed the problem that the sigma output of Element_SigmaGraph node does not match the curve under the curve mode.
- Fixed the problem that the Element_SigmaGraph node is stuck when the height is quickly reduced.
- Fixed the problem that it may not be possible to delete the LoadImage_Preview node in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v1.4.0）
  
  Added LoadImage_Preview node, where the image browsing function references part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: browse image files in the specified path, select one after entering the editing panel (draw mask or draw rectangles, circles, etc. on the image).
  - Shift+left click: draw straight lines, squares, or circles.
  - L-alpha: used to load image alpha to the canvas.
  - Return: return to the image browsing panel.

  <img width="989" height="783" alt="image" src="https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16" />


## v1.3.1 （Optimized in V1.4.5）
  
  Added Element HueBright (hue vs brightness) and Element HueHue (hue vs hue) nodes, curve adjustment, real-time preview supports single images and sequence frames. Click to add points, right-click to remove points.

## v1.3.0 （Optimized in V1.4.5）
  
  Added Element HueSat node, curve adjustment (hue vs saturation), real-time preview supports single images and sequence frames. Click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause an error, but will make the other point invalid. A single endpoint at the top can complete the color adjustment in real time, because the curves at both ends are closed loops.

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7 （Optimized in V1.4.5）
  
  Added Element ImageCurve node, curve coloring, real-time preview supports single images and sequence frames. Click to add points, right-click to remove points.

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （fix in V1.4.4，Optimized in V1.4.5）
  
  Added custom sigma, Element_SigmaGraph node, original code from author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph , modified, optimized, and added a lot of content.

  - Added an optional latent input port to synchronize the loading and unloading order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added a separate execution function, which is convenient for storing existing sigma sequences as presets<br>
  - Click on the curve position to add or remove control points (click to add, right-click to delete), when adding or removing points, keep other control points unchanged. Remove the X-axis movement restriction of control points.
  - Added output max value max value parameter, added output forced correction.

  <img width="922" height="714" alt="image" src="https://github.com/user-attachments/assets/dce72d55-41a6-4a2e-9f6c-4350ef229dcd" />

## v1.2.3
  
  Added ImageSize Div node.

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />


## v1.2.2
  
  Added Frame Calculator node, calculates the result as "rounded" + 1, and can choose Seconds or frame mode.

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  Added Black White Color node, the mask input port will be added to the mask generated by the node by ADD operation.

  The initial purpose of ChessboardPattern node was to suppress the pixel offset problem after style transformation in qwenEdit, first transform the style of the mask area, then transform the invert mask area (but it needs two samplings, this method does not work in Klein model), later found that ChessboardPattern this kind of mask will affect the recognition of the model for objects, so there was Black White Color node. Try to make the area of black and white regions as average as possible to reduce the problem of color inconsistency.
  
  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  Added ChessboardPattern node, creating a black and white chessboard image, which can be selected in "by_grid_size" or "by_rows_and_cols" two modes to determine the size of the unit cell.

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  Added Image Noise Using Mask node, which is convenient to add random noise in the mask area of the image, and can adjust the size, opacity, and can choose whether to be grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, will automatically calculate the expansion when there is input (when the parameter is less than the original image, it is clip mode), at this time, the alignment parameter takes effect, and the alignment mode can be selected (center alignment, left alignment, right alignment, top alignment, bottom alignment, left top alignment, left bottom alignment, right top alignment, right bottom alignment). The pad mode can be selected as constant, reflect, edge, and another one with the same effect as reflect. When the constant mode is selected, feathering controls the overall blurring degree, content_blur controls the blurring degree of the expanded area of the original image. When the constant mode is selected, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="屏幕截图 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  Added Mask Stroke node, mask outline, supports separate control of inner and outer stroke width and blur, supports adding overall weight to non-stroked areas (making the output mask have no weight of 0 area).
  
  <img width="1295" height="731" alt="节点截图 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node will automatically identify color information color_code. Outputs a solid color image, with an image size output port, the image size will be approximated based on divisible_by (divisible). 

Text Line Break： Breaks the input text by character count, supports Chinese, English, and mixed Chinese and English, supports punctuation avoidance at the beginning and end. Convenient for connecting prompts and generated images together, which needs to be assisted by other nodes, such as the Add Label node in Kjnode.

Random Chars (Append)：Adds invalid special characters to the input text (characters and number can be customized), mainly to make the generated image have greater changes without destroying the intention of the prompt (it is not known whether it works), because the random changes in the image composition generated by qwen_image and Z_image models are small. Here "invalid" is relatively speaking.
                       Can be simply set to insert position (before, end, insert), where insert is to average the number of characters and insert them behind the punctuation marks of the original text, from the end to the front.