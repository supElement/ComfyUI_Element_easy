<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenience. Since I was too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph,Element ImageCurve,Element HueSat,Element HueBright,Element HueHue,LoadImage_Preview,Frame Calculator,ImageSize Div,Smart merge images


## Installation

- **Manual Installation** <br>
Enter the ./ComfyUI/custom_nodes directory and run the following code: <br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager** <br>

  Search for ComfyUI_Element_easy in the comfyUI manager and then install.


## Update
## v1.4.8
  
Enhanced the algorithm for minor distortion correction and color matching in the Smart merge images node.
  - The model used is not required. If the related option is selected, the model will be automatically downloaded to \ComfyUI\models\elementEasy when the node is run.

## v1.4.7
  
Added support for block merging in the Smart merge images node. That is, when multiple images are input to the edited_crop_B port, the output is a single image after merging.
  - Note: The images input to the edited_crop_B port must be a Batch rather than a list. If it is a list, it must be converted through the Image List To Batch node.

## v1.4.6
  
Added preview button support for KJnode's GetNode node to Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes; modified the curve type of Element ImageCurve node.

## v1.4.5
  
Modified the interaction logic of Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes, changing it to add points by clicking the left mouse button, and the newly added points can be directly dragged; enhanced the influence degree of Element HueBright node on low saturation colors, improving the adjustment range of brightness.

## v1.4.4
  
Fixed the bug in the linear mode "L" of the Element_SigmaGraph node, added the output max value parameter, and added the forced correction output.

## v1.4.3（Optimized in V1.4.8）
  
  Added the Smart merge images node.
  - Merge images intelligently when two images have enough common features.
  - Correct the pixel offset and color difference caused by editing models (Flux2 Klein, Qwen Edit, etc.) after editing images. The usage method in this case is to connect the original image and the edited image to the original_image and edited_crop_B input ports, respectively.
  - When merging the cut image into the original image, if conditions allow, the most reliable merging scheme: original_image + edited_crop_B + original_crop_A. Where original_crop_A is the image cut from the original_image without modification or deformation.
  - Optimized the merging method of the Smart merge images node, with better correction for the pixel offset caused by the editing models (Flux2 Klein, Qwen Edit, etc.).
  - Added color matching mode Adaptive Local (strong), which can better repair the color difference caused by the editing of the image.
  - Added two parameters for this mode only: adapt_thresh (color difference threshold), adapt_align (pre-matching strength - correct the local color spots produced after the image is merged, the higher the value, the more obvious the correction, but it may have a negative impact on the color correction of the overall picture).
  - Added adapt_local_match parameter, providing more choices for the mask merging of the color matching mode Adaptive Local (strong). The node only had None mode before. The feather_kernel is combined into one parameter with feature_amount and adapt_kernel.
  - Added support for block merging in the Smart merge images node. That is, when multiple images are input to the edited_crop_B port, the output is a single image after merging. Note: The images input to the edited_crop_B port must be a Batch rather than a list. If it is a list, it must be converted through the Image List To Batch node.

  <img width="1670" height="981" alt="Untitled-2" src="https://github.com/user-attachments/assets/8b5f4167-9529-4cdc-8df8-9b26f5355688" />


## v1.4.0

  - Added an optional image input port to the LoadImage_Preview node, which can be used to bridge the editing in the preview; optimized the layout of the editing panel.
  - Optimized the loading preview logic of Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.8 
Important update！！！
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes to Element_SigmaGraph; removed the value display box for graph_data.
- Added a mode switch button "C" Smooth curve mode and Linear mode in the Element_SigmaGraph node.
- Fixed the problem of the sigma output not matching the curve in the Element_SigmaGraph node in the curve mode.
- Fixed the problem of screen freezing and blocking when the height of the Element_SigmaGraph node was quickly reduced.
- Fixed the problem that the LoadImage_Preview node might not be able to be deleted in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v1.4.0）
  
  Added LoadImage_Preview node, which references part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: Browse image files in the specified path, select one to enter the editing panel (draw a mask or draw rectangles, circles, etc. on the image).
  - Shift+left click: draw straight lines, squares, or circles.
  - L-alpha: used to load the image alpha to the canvas.
  - Return: return to the image browsing panel.

  <img width="989" height="783" alt="image" src="https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16" />


## v1.3.1 （Optimized in V1.4.5）
  
  Added Element HueBright (Hue VS Brightness) and Element HueHue (Hue VS Hue) nodes, with curve adjustment and real-time preview support for single images and sequence frames. Click to add points, right-click to subtract points.

## v1.3.0 （Optimized in V1.4.5）
  
  Added Element HueSat node, with curve adjustment (Hue VS Saturation), real-time preview support for single images and sequence frames. Click to add points, right-click to subtract points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause errors, but will make the other point invalid. A single end point on the upper end of the curve can complete the coloring, because the curves at both ends are closed loops.

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7 （Optimized in V1.4.5）
  
  Added Element ImageCurve node, with curve coloring, real-time preview support for single images and sequence frames. Click to add points, right-click to subtract points.

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （fix in V1.4.4，Optimized in V1.4.5）
  
  Added Element_SigmaGraph node with custom sigma, the original code is from the author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph , modified, optimized, and added many contents.

  - Added an optional latent input port to synchronize the load and unload order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added separate execution function, convenient to store existing sigma sequences as presets<br>
  - Click to add points at the position of the curve, click to delete, while keeping other control points unchanged. Remove the control point X axis movement limit
  - Added output max value parameter, added forced correction output.

  <img width="922" height="714" alt="image" src="https://github.com/user-attachments/assets/dce72d55-41a6-4a2e-9f6c-4350ef229dcd" />

## v1.2.3
  
  Added ImageSize Div node.

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />


## v1.2.2
  
  Added Frame Calculator node, calculates the result as "rounded" + 1, and can be selected in Seconds or frame mode.

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  Added Black White Color node, the input port's mask will be added to the mask generated by the node through ADD operation.

  The initial purpose of the ChessboardPattern node was to suppress the pixel offset problem after the style transformation in qwenEdit, first transform the mask area style, and then transform the invert mask area (but it needs two samplings, this method does not work in Klein models), and then find that the ChessboardPattern mask will affect the model's recognition of objects, so the Black White Color node was born. Try to make the area of black and white regions as even as possible to reduce the problem of inconsistent tone.
  
  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  Added ChessboardPattern node, creating a black and white checkerboard image, with two modes to determine the size of the unit cell: "by_grid_size" or "by_rows_and_cols".

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  Added Image Noise Using Mask node, which is convenient to add random noise to the mask area of the image, can adjust the noise size, opacity, and can choose whether to be grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, if there is an input, it will automatically calculate the expansion (when the parameter is less than the original image, it is clip mode), at this time, the alignment parameter takes effect, and you can choose the alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, bottom-left alignment, top-right alignment, bottom-right alignment).
  Pad mode can be selected as constant, reflect, edge, another one is the same as reflect. When choosing the constant mode, the feathering controls the overall blurring degree, and content_blur controls the blurring degree of the extended area of the original image. When in the constant mode, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="屏幕截图 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  Added Mask Stroke node, mask stroke, supports independent control of inside and outside stroke width and blur, and supports the addition of overall weight to non-stroked areas (so that the output mask does not have any area with weight of 0).
  
  <img width="1295" height="731" alt="节点截图 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node will automatically identify color information color_code. Output pure color images, with output ports for image size, the image size will be approximated based on divisible_by (integer division).

Text Line Break： Break the input text into lines by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation avoidance at the beginning and end. Convenient to connect the prompt words and generated images together, which requires the help of other nodes, such as the Add Label node in Kjnode.

Random Chars (Append)： Add invalid special characters (can be customized characters and quantity) to the input text, mainly to make the generated image have greater changes without destroying the prompt intention (unknown whether it is effective), because the qwen_image and Z_image models have little random changes in image composition. Here "invalid" is relative.
                       Can simply set the insertion position (before, end, insert), where insert is to insert the number of characters evenly into the punctuation mark after the original text, from back to front distribution.




<img width="1590" height="1080" alt="节点截图 2025-12-04 164008" src="https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab" />