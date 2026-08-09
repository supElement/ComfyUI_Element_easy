<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Simplified%20Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenient use. Due to laziness, the code has not been merged. Includes: Minimax_H3-LatentUpscaler, Smart merge images, LoadImage_Preview, Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, Frame Calculator, ImageSize Div, black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break.


## Installation

- **Manual Installation** <br>
Enter the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager** <br>

  Search for ComfyUI_Element_easy in the ComfyUI manager, then install.
 


## Update
## v1.5.0
  
Added Minimax_H3-LatentUpscaler node for latent space upscaling of videos, which does not process audio and outputs to Minimax H3 latent.
Fixed some bugs.


## v1.4.8
  
Enhanced the Smart merge images node's algorithm for minor image distortion correction and color matching.
  - The model used is not required. If the relevant options are selected, the model will be automatically downloaded to the \ComfyUI\models\elementEasy directory when running the node. You can also copy the elementEasy folder from the models folder of this repository to the \ComfyUI\models\elementEasy directory in advance, so there is no need to download the model again.

## v1.4.7
  
Added support for block merging in the Smart merge images node. That is, when multiple images are input to the edited_crop_B port, the output is a single merged image.
  - Note: The images input to the edited_crop_B port must be Batch rather than list. If it is a list, it must be converted to Batch through the Image List To Batch node.

## v1.4.6
  
Added preview button support for KJnode's GetNode node for Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes; modified the curve type of Element ImageCurve node.

## v1.4.5
  
Modified the interaction logic of Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes, changed to single-click to add points with the left mouse button, and new points can be directly dragged; Enhanced the influence of Element HueBright node on low saturation colors, improving the brightness adjustment range.

## v1.4.4
  
Fixed the output bug of linear mode "L" in Element_SigmaGraph node, added output max value parameter, and added forced correction output.

## v1.4.3（Optimized in V1.4.8）
  
  Added Smart merge images node.
  - Smartly merge images when there are sufficient common features between two images.
  - Correct the pixel offset and color difference after editing images with editing models (Flux2 Klein, Qwen Edit, etc.). The usage method in this case is: connect the original image and the edited image to the original_image and edited_crop_B input ports, respectively.
  - Merge the cropped image back to the original image when conditions allow, the most reliable merging scheme: original_image + edited_crop_B + original_crop_A. Among them, original_crop_A is the unmodified or deformed image cut from original_image.
  - Added color matching mode Adaptive Local (strong), which can better correct the color difference after images are edited. Two new parameters are added specifically for this mode: adapt_thresh (color difference threshold).
  - Added adapt_local_match parameter, providing more options for mask blending in color matching mode Adaptive Local (strong).
  - Optimized the fusion method of Smart merge images node, which has better correction for pixel offset and color offset after images are edited with editing models (Flux2 Klein, Qwen Edit, etc.). 
  - Added support for block merging in Smart merge images node. That is, when multiple images are input to the edited_crop_B port, the output is a single merged image. Note: The images input to the edited_crop_B port must be Batch rather than list. If it is a list, it must be converted to Batch through the Image List To Batch node.

  <img width="2121" height="963" alt="image" src="https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4" />


## v1.4.0

  - Added an optional image input port to LoadImage_Preview node, which can be used for bridging editing in the preview; optimized the layout of the editing panel.
  - Optimized the loading preview logic of Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.8 
Important update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numeric display box for graph_data.
- Added a mode switch button "C" for smooth curve mode and linear mode in the Element_SigmaGraph node.
- Fixed the problem that the sigma output of Element_SigmaGraph node does not match the curve in curve mode.
- Fixed the problem of lag and blocking when quickly reducing the height of Element_SigmaGraph node.
- Fixed the problem that it may not be possible to delete the LoadImage_Preview node in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v.1.4.0）
  
  Added LoadImage_Preview node, where the image browsing function references part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: browse image files in the specified path, select one and enter the editing panel (draw mask or draw rectangles, circles, etc. on the image).
  - Shift+left click: draw lines, squares, or circles.
  - L-alpha: used to load image alpha to the canvas.
  - Return: return to the image browsing panel.

  <img width="989" height="783" alt="image" src="https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16" />


## v1.3.1 （Optimized in V1.4.5）
  
  Added Element HueBright (hue vs. brightness) and Element HueHue (hue vs. hue) nodes, curve adjustment, real-time preview supports single images and sequence frames. Click to add points, right-click to remove points.

## v1.3.0 （Optimized in V1.4.5）
  
  Added Element HueSat node, curve adjustment (hue vs. saturation), real-time preview supports single images and sequence frames. Click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause an error, but will make the other point invalid. A real-time top point can complete the color adjustment because the curves at both ends are closed loops.

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7 （Optimized in V1.4.5）
  
  Added Element ImageCurve node, curve color adjustment, real-time preview supports single images and sequence frames. Click to add points, right-click to remove points.

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （fix in V1.4.4，Optimized in V1.4.5）
  
  Added custom sigma, Element_SigmaGraph node, original code from author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph , modified, optimized, and added a lot of content.

  - Added an optional latent input port to synchronize the loading and unloading order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added separate execution function, convenient to store existing sigma sequences as presets<br>
  - Click to add control points at the position of the curve with the mouse, and right-click to delete. When adding or deleting points, keep other control points unchanged. Release the control point X-axis movement restriction
  - Added output max value max value parameter, added output forced correction.

  <img width="922" height="714" alt="image" src="https://github.com/user-attachments/assets/dce72d55-41a6-4a2e-9f6c-4350ef229dcd" />

## v1.2.3
  
  Added ImageSize Div node.

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />


## v1.2.2
  
  Added Frame Calculator node, calculates the result as "rounded" + 1, and can be selected in Seconds or frame mode.

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  Added Black White Color node, the mask input port will be added with the mask generated by the node through ADD operation.

  The initial purpose of ChessboardPattern node was to suppress the pixel offset problem after style transformation in qwenEdit, first transform the style of the mask area, then transform the invert mask area (but it needs two samplings, this method does not work in Klein model), later found that the mask of ChessboardPattern would affect the model's recognition of objects, so the Black White Color node was created. Try to make the area of black and white regions average to reduce the problem of inconsistent hue.
  
  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  Added ChessboardPattern node, which creates a black and white checkerboard image and can be selected in "by_grid_size" or "by_rows_and_cols" modes to determine the size of the unit cell.

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  Added Image Noise Using Mask node, which is convenient to add random noise to the mask area of the image, can adjust the size and transparency of the noise, and can choose whether to be grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, automatically calculate expansion when input is present (clip mode when parameter is less than original image), at this time alignment parameter takes effect, can choose alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, bottom-left alignment, top-right alignment, bottom-right alignment). Pad mode can be constant, reflect, edge, and another one is the same as reflect. When the constant mode is selected, feathering controls the overall blurring degree, content_blur controls the blurring degree of the expanded area of the original image. When the constant mode is selected, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

<img width="1724" height="878" alt="screen shot 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="screen shot 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  Added Mask Stroke node, mask outline, supports separate control of inner and outer stroke width and blur, supports adding weight to the non-stroked area as a whole (so that the output mask does not have a weight of 0 area).
  
  <img width="1295" height="731" alt="node screenshot 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node will automatically identify color information color_code. Outputs a solid color image, with an image size output port, the image size will be approximated according to divisible_by (integer division).

Text Line Break： Breaks the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation avoidance at the beginning and end. Convenient to connect prompts and generated images together, which requires other nodes, such as the Add Label node in Kjnode. Random Chars (Append)：Appending invalid special characters to the input text (characters and number can be customized), mainly to make the generated image have more changes without destroying the prompt intention (whether it is effective is not known), because the random changes in the image composition generated by qwen_image and Z_image models are small. Here "invalid" is relatively speaking.
                       Can simply set the insertion position (before, end, insert), where insert is to evenly distribute the number of characters inserted into the original text after each punctuation symbol, from the end to the front.