<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenient use. Due to laziness, the code has not been merged. Includes: Element Load and Edit Video, Minimax_H3-LatentUpscaler, Smart merge images, LoadImage_Preview, Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, Frame Calculator, ImageSize Div, black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break.


## Installation

- **Manual Installation (Manual Installation)**<br>
Enter the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager (Install using Manager)**<br>

  Search for ComfyUI_Element_easy in the ComfyUI manager and then install with --.


## Update

## v1.5.4

- Added the "Element Load and Edit Video" node—which supports video loading and basic single-track editing—along with the associated helper nodes "Element Video Clip" and "Element Video Info."
- "Element Load and Edit Video" functions as a visual single-track video editor: after importing a video, it automatically detects shot cuts (using PySceneDetect) and provides an interactive timeline for manually trimming, rearranging, and previewing clips; the edited results can then be passed to downstream nodes with a single click to output video frames and audio based on the selected segments.
- Its core value lies in integrating the workflow traditionally requiring professional editing software—specifically storyboarding, rough cutting, and clip selection—directly into the ComfyUI workflow. This allows for source material segmentation within the canvas itself, facilitating workflows such as batch video processing and segment-based generation.
- In most cases, it can serve as a replacement for the standard "Load Video" node.
- Note: The node was originally named "Element Scene Detection," but following multiple functional updates, that name no longer accurately reflected its capabilities; it has therefore been renamed "Element Load and Edit Video."
- Chinese description: https://github.com/supElement/ComfyUI_Element_easy/blob/main/Element_scene_detection.zh.md
- English description: https://github.com/supElement/ComfyUI_Element_easy/blob/main/Element_scene_detection.en.md

<img width="2147" height="1104" alt="image" src="https://github.com/user-attachments/assets/5ba547a7-31c8-4323-bf40-7ec58f1b548e" />

## v1.5.3

- Added "P" button for Element_SigmaGraph node.
- The behavior of the "P" button: When the number of points is less than steps+1, the x of the first n-1 points is rearranged as 0, 1/steps, 2/steps, ..., (n-2)/steps, and y remains unchanged; the last point (x, y) is retained as is. When the number of points is not less than steps+1, take the first steps+1 points, x is evenly distributed as 0, 1/steps, ..., 1, and y remains unchanged. Undo support: operations will be pushed into the undo stack, and can be undone with Ctrl+Z.
- PS: What is the use? It can increase the sampling steps (increase details) for the later steps without changing the step size of the previous steps.

## v1.5.2

  - Minimax_H3-LatentUpscaler_Adv node introduces conditional scaling mode, which can be selected to ignore (pass_through), only align without scaling (NO_refs), or scale (refs) three modes, and the best quality is the scale (refs) mode.

## v1.5.0
  
Added Minimax_H3-LatentUpscaler latent space scaling node, which only scales the latent space of the video and does not do any processing to the audio, and the output port is Minimax H3 latent.
  - Added Minimax_H3-LatentUpscaler_Adv verified latent space scaling node.
Fixed some bugs.


## v1.4.8
  
Enhanced the algorithm of Smart merge images node for slight image distortion correction and color matching.
  - The model used is not required. If the relevant options are selected, the model will be automatically downloaded to \ComfyUI\models\elementEasy directory when running the node. You can also copy the elementEasy folder under the models folder of this repository to \ComfyUI\models\elementEasy directory in advance, then no need to download the model again.

## v1.4.7
  
Added support for block merging in Smart merge images node. That is, when multiple images are input to the edited_crop_B port, the output is a single merged image.
  - Note: The images input to the edited_crop_B port must be Batch rather than list. If it is list, it must be converted by Image List To Batch node.

## v1.4.6
  
Added preview button support for KJnode GetNode node for Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes; modified the curve type of Element ImageCurve node.

## v1.4.5
  
Modified the interaction logic of Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes, changed to click the left mouse button to add points, and the new added points can be directly dragged; enhanced the impact of Element HueBright node on low saturation colors, and improved the brightness adjustment range.

## v1.4.4
  
Fixed the output bug of linear mode "L" of Element_SigmaGraph node, added output max value parameter, and added forced correction output.

## v1.4.3（Optimized in V1.4.8）
  
  Added Smart merge images node.
  - Smartly merge images when there are enough common features between the two images.
  - Correct the pixel offset and color difference after editing the image with the correction model (Flux2 Klein, Qwen Edit, etc.). The usage method in this case: connect the original image and the edited image to the original_image and edited_crop_B input ports respectively.
  - When merging the cropped image into the original image, if the conditions allow, the most reliable merging scheme is: original_image + edited_crop_B + original_crop_A. Among them, original_crop_A is the unmodified or deformed image cut from the original_image.
  - Added color matching mode Adaptive Local (strong), which can better correct the color difference after the image is edited. Two new parameters are added for this mode: adapt_thresh (color difference threshold).
  - Added adapt_local_match parameter, which provides more choices for mask fusion in color matching mode Adaptive Local (strong).
  - Optimized the fusion method of Smart merge images node, which has better correction for pixel offset and color offset after editing with the editing model (Flux2 Klein, Qwen Edit, etc.). 
  - Added support for block merging in Smart merge images node. That is, when multiple images are input to the edited_crop_B port, the output is a single merged image. Note: The images input to the edited_crop_B port must be Batch rather than list. If it is list, it must be converted by Image List To Batch node.

  <img width="2121" height="963" alt="image" src="https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4" />


## v1.4.0

  - Added an optional image input port to LoadImage_Preview node, which can be used to bridge preview editing; optimized the layout of the editing panel.
  - Optimized the loading preview logic of Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.8 
Important update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numerical display box of graph_data.
- Added a mode switch button "C" for smooth curve mode and linear mode in the Element_SigmaGraph node.
- Fixed the problem that the sigma output of Element_SigmaGraph node does not match the curve in curve mode.
- Fixed the problem of jamb and blocking when quickly reducing the height of Element_SigmaGraph node.
- Fixed the problem that it may not be possible to delete the LoadImage_Preview node in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v1.4.0）
  
  Added LoadImage_Preview node, where the image browsing function refers to part of the code of the image_loader_with_previews node of the author Enashka's ComfyUI-nhknodes extension.<br>
  - Main function: browse image files in the specified path, select one after entering the editing panel (draw mask or draw boxes, circles, etc. on the image).
  - Shift+left click: draw straight lines, squares, or circles.
  - L-alpha: used to load image alpha to the canvas.
  - Return: return to the image browsing panel.

  <img width="989" height="783" alt="image" src="https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16" />


## v1.3.1 （Optimized in V1.4.5）
  
  Added Element HueBright (hue vs brightness) and Element HueHue (hue vs hue) nodes, curve adjustment, real-time preview support single image and sequence frame images. Click to add points, right-click to delete points.

## v1.3.0 （Optimized in V1.4.5）
  
  Added Element HueSat node, curve adjustment (hue vs saturation), real-time preview support single image and sequence frame images. Click to add points, right-click to delete points.<br>
  - Note: Do not add points at both ends of the curve at the same time, although there will be no error, it will make the other point invalid, and the upper end point can complete the color adjustment in real time because the curves at both ends are closed loops.

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7 （Optimized in V1.4.5）
  
  Added Element ImageCurve node, curve color adjustment, real-time preview support single image and sequence frame images. Click to add points, right-click to delete points.

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （fix in V1.4.4，Optimized in V1.4.5，add "P" button in V1.5.3）
  
  Added Element_SigmaGraph node with custom sigma, the original code comes from the author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph ,  modified, optimized, and added a lot of content.

  - Added an optional latent input port to synchronize the loading and unloading order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added separate execution function, which is convenient to store existing sigma series as presets<br>
  - Click the position of the curve to add control points (click to add points, right-click to delete), and keep other control points unchanged when adding or deleting points. Remove the X-axis movement restriction of control points
  - Added output max value max value parameter, added output forced correction.
  - The behavior of the "P" button: When the number of points is less than steps+1, the x of the first n-1 points is rearranged as 0, 1/steps, 2/steps, ..., (n-2)/steps, and y remains unchanged; the last point (x, y) is retained as is. When the number of points is not less than steps+1, take the first steps+1 points, x is evenly distributed as 0, 1/steps, ..., 1, and y remains unchanged. Undo support: operations will be pushed into the undo stack, and can be undone with Ctrl+Z.

  <img width="1176" height="794" alt="image" src="https://github.com/user-attachments/assets/a8741609-cbe7-4ec8-a88d-5cae79b031a8" />
  The image above shows the comparison before and after clicking the "P" button. PS: What is the use? It can increase the sampling steps (increase details) for the later steps without changing the step size of the previous steps.


## v1.2.3
  
  Added ImageSize Div node.

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />


## v1.2.2
  
  Added Frame Calculator node, which calculates the result as "rounded" + 1, and can be selected in Seconds or frame mode.

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  Added Black White Color node, the mask input port will be added with the mask generated by the node through ADD operation.

  The initial purpose of the ChessboardPattern node was to suppress the pixel offset problem after the style conversion in qwenEdit, first convert the style of the mask area, and then convert the invert mask area (but it needs two sampling, this method does not work in the Klein model), and then it was found that the ChessboardPattern mask would affect the recognition of objects by the model, so the Black White Color node was born. Try to make the area of black and white regions average to reduce the problem of color inconsistency.
  
  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  Added ChessboardPattern node, which creates a black and white chessboard image, and can be selected in "by_grid_size" or "by_rows_and_cols" two modes to determine the size of the unit cell.

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  Added Image Noise Using Mask node, which is convenient to add random noise in the mask area of the image, can adjust the size of the noise, opacity, and can choose whether to be grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, will automatically calculate the expansion when input is available (when the parameter is less than the original image, it is clip mode), at this time, alignment parameter takes effect, can choose alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top left alignment, bottom left alignment, top right alignment, bottom right alignment).
  pad mode can be constant, reflect, edge, and another one is the same as reflect. When the constant mode is selected, feathering controls the overall blurring degree, content_blur controls the blurring degree of the expanded area of the original image. When the constant mode is selected, background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

<img width="1724" height="878" alt="screen shot 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="screen shot 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  Added Mask Stroke node, mask outline, supports separate control of inner and outer outline width and blur, and supports adding weight to the non-outlined area as a whole (so that the output mask does not have an area with weight of 0).
  
  <img width="1295" height="731" alt="node screenshot 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node will automatically recognize color information color_code. Output pure color image, with image size output port, image size will be approximated according to divisible_by (integer division).

Text Line Break： Break the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation avoidance at the beginning and end. Convenient to connect prompts and generated images together, which needs to be helped by other nodes, such as the Add Label node in Kjnode.
                       Can simply set the insertion position (before, end, insert), where insert inserts the number of characters evenly into the position behind each punctuation in the original text, from back to front allocation.




<img width="1590" height="1080" alt="node screenshot 2025-12-04 164008" src="https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab" />
