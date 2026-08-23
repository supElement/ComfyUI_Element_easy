<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Simplified%20Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenient use. Due to laziness, the code has not been merged. Includes: Minimax_H3-LatentUpscaler, Smart merge images, LoadImage_Preview, Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, Frame Calculator, ImageSize Div, black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break.


## Installation

- **Manual Installation**<br>
Enter the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager**<br>

  Search for ComfyUI_Element_easy in the ComfyUI manager, then install with --.


## Update

## v1.5.3

- Added "P" button for Element_SigmaGraph node.
- The behavior of the "P" button: When the number of points is less than steps+1, the x of the first n-1 points is rearranged to 0, 1/steps, 2/steps, ..., (n-2)/steps, and y remains unchanged; the last point (x, y) is retained as is. When the number of points is not less than steps+1, take the first steps+1 points, x is uniformly distributed as 0, 1/steps, ..., 1, and y remains unchanged. Undo support: The operation will be pushed into the undo stack, and can be undone with Ctrl+Z.
- PS: What is the use? It can increase the sampling steps (increase details) for the later part without changing the step size of the previous steps.

## v1.5.2

  - The Minimax_H3-LatentUpscaler_Adv node introduces conditional scaling mode, which can be selected to ignore (pass_through), only align without scaling (NO_refs), or scale (refs), with the quality of the scaling (refs) mode being the best.

## v1.5.0
  
Added Minimax_H3-LatentUpscaler latent space scaling node, which only scales the latent space of videos without any processing of audio, and the output port is Minimax H3 latent.
  - Added Minimax_H3-LatentUpscaler_Adv verified latent space scaling node.
Fixed some bugs.


## v1.4.8
  
Enhanced the algorithm for correcting slight image distortion and color matching in the Smart merge images node.
  - The model used is not necessary. If the relevant options are selected, the model will be automatically downloaded to the \ComfyUI\models\elementEasy directory when the node is run. You can also copy the elementEasy folder from the models folder of this repository to the \ComfyUI\models\elementEasy directory in advance, so there is no need to download the model again.

## v1.4.7
  
Added support for block merging in the Smart merge images node. That is, when multiple images are input to the edited_crop_B port, the output is a single merged image.
  - Note: The images input to the edited_crop_B port must be Batch rather than list. If it is a list, it must be converted through the Image List To Batch node.

## v1.4.6
  
Added preview button support for KJnode's GetNode node to Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes; modified the curve type of Element ImageCurve node.

## v1.4.5
  
Modified the interaction logic of Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes, changed to click the left mouse button to add points, and points can be directly dragged to add points; Enhanced the influence of Element HueBright node on low saturation colors, and improved the adjustment range of brightness.

## v1.4.4
  
Fixed the output bug of linear mode "L" in Element_SigmaGraph node, added output maximum value max value parameter, and added output forced correction.

## v1.4.3（Optimized in V1.4.8）
  
  Added Smart merge images node.
  - Smartly merge images when there are sufficient common features between the two images.
  - Correct the pixel offset and color difference after editing the image with the editing model (Flux2 Klein, Qwen Edit, etc.). The usage method in this case: connect the original image and the edited image to the original_image and edited_crop_B input ports, respectively.
  - When merging the cropped image into the original image, if the conditions allow, the most reliable merging scheme: original_image + edited_crop_B + original_crop_A. Among them, original_crop_A is the unmodified or deformed image cut from the original_image.
  - Added color matching mode Adaptive Local (strong), which can better correct the color difference after the image is edited. Two new parameters are added for this mode: adapt_thresh (color difference threshold).
  - Added adapt_local_match parameter, providing more options for mask fusion in the color matching mode Adaptive Local (strong).
  - Optimized the fusion method of Smart merge images node, which has better correction for pixel offset and color offset after editing with the editing model (Flux2 Klein, Qwen Edit, etc.).
  - Added support for block merging in Smart merge images node. That is, when multiple images are input to the edited_crop_B port, the output is a single merged image. Note: The images input to the edited_crop_B port must be Batch rather than list. If it is a list, it must be converted through the Image List To Batch node.

  ![image](https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4)


## v1.4.0

  - Added an optional image input port to LoadImage_Preview node, which can be used for bridging preview editing; optimized the layout of the editing panel.
  - Optimized the loading preview logic of Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.8 
Important update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numerical display box of graph_data.
- Added mode switch button "C" Smooth Curve mode and Linear mode in the Element_SigmaGraph node.
- Fixed the problem that the sigma output of Element_SigmaGraph node does not match the curve in curve mode.
- Fixed the problem of freezing and blocking when quickly reducing the height of Element_SigmaGraph node.
- Fixed the problem that it may not be possible to delete the LoadImage_Preview node in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v1.4.0）
  
  Added LoadImage_Preview node, where the image browsing function refers to part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: Browses image files in the specified path, selects one image, and enters the editing panel (drawing mask or drawing rectangles, circles, etc. on the image).
  - Shift+left click: Draw lines, squares, or circles.
  - L-alpha: Used to load image alpha to the canvas.
  - Return: Return to the image browsing panel.

  ![image](https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16)


## v1.3.1 （Optimized in V1.4.5）
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, curve adjustment, real-time preview supports single images and sequence frame images. Click to add points, right-click to remove points.

## v1.3.0 （Optimized in V1.4.5）
  
  Added Element HueSat node, curve adjustment (Hue vs Saturation), real-time preview supports single images and sequence frame images. Click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause an error, but will make the other point invalid. The upper end point of the real-time adjustment can complete the color adjustment with one point, because the curves at both ends are closed loops.

  ![Image](https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8)

## v1.2.7 （Optimized in V1.4.5）
  
  Added Element ImageCurve node, curve coloring, real-time preview supports single images and sequence frame images. Click to add points, right-click to remove points.

  ![Image](https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62)

## v1.2.4 （fix in V1.4.4，Optimized in V1.4.5，add "P" button in V1.5.3）
  
  Added custom sigma, Element_SigmaGraph node, original code from author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph , modified, optimized, and added a lot of content.

  - Added an optional latent input port to synchronize the loading and unloading order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added separate execution function, convenient to store existing sigma sequences as presets<br>
  - Click on the curve position to add control points (click to add points, right-click to delete), and keep other control points unchanged when adding or removing points. Release the control point X axis movement restriction
  - Added output maximum value max value parameter, and added output forced correction.
  - The behavior of the "P" button: When the number of points is less than steps+1, the x of the first n-1 points is rearranged to 0, 1/steps, 2/steps, ..., (n-2)/steps, and y remains unchanged; the last point (x, y) is retained as is. When the number of points is not less than steps+1, take the first steps+1 points, x is uniformly distributed as 0, 1/steps, ..., 1, and y remains unchanged. Undo support: The operation will be pushed into the undo stack, and can be undone with Ctrl+Z.

  ![image](https://github.com/user-attachments/assets/a8741609-cbe7-4ec8-a88d-5cae79b031a8)
  The above image shows the comparison before and after clicking the "P" button. PS: What is the use? It can increase the sampling steps (increase details) for the later part without changing the step size of the previous steps.


## v1.2.3
  
  Added ImageSize Div node.

![image](https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef)


## v1.2.2
  
  Added Frame Calculator node, calculates the result as "rounded up" + 1, and can be selected in Seconds or frame mode.

  ![image](https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03)


## v1.1.3
  
  Added Black White Color node, the mask input port will be added with the mask generated by the node through ADD operation.

  The initial purpose of the ChessboardPattern node was to suppress the pixel offset problem after the style conversion in qwenEdit, first convert the style of the mask area, and then convert the invert mask area (but it needs two samplings, this method does not work in the Klein model), and then it was found that the ChessboardPattern mask would affect the model's recognition of objects, so the Black White Color node was created. Try to make the area of the black and white regions average to reduce the problem of inconsistent hue.
  
  ![image](https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df)


## v0.0.9

  Added ChessboardPattern node, creates a black and white chessboard image, and can be selected in "by_grid_size" or "by_rows_and_cols" modes to determine the size of the unit cell.

  ![image](https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482)


## v0.0.8

  Added Image Noise Using Mask node, which is convenient to add random noise in the mask area of the image, and can adjust the noise size, opacity, and can choose whether to be grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, will automatically calculate the expansion when there is input (when the parameter is less than the original image, it is clip mode), at this time, the alignment parameter takes effect, and the alignment mode can be selected (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, top-right alignment, bottom-left alignment, bottom-right alignment). The pad mode can be selected as constant, reflect, edge, and another one with the same effect as reflect. When the constant mode is selected, feathering controls the overall blurring degree, and content_blur controls the blurring degree of the expanded area of the original image. When the constant mode is selected, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

![screen shot 2026-01-17 134457](https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266)
![screen shot 2026-01-17 134251](https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158)

  

  
## v0.0.7

  Added Mask Stroke node, mask outlining, supports separate control of inner and outer stroke width and blur, and supports adding overall weight to non-stroked areas (making the output mask have no weight area of 0).
  
  ![node screenshot 2025-12-05 011534](https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d)

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node will automatically identify color information color_code. Outputs a pure color image, with an image size output port, and the image size will be approximated according to divisible_by (integer division).

Text Line Break： Breaks the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation symbols to avoid the beginning and end. Convenient to connect prompts and generated images together, which requires other nodes, such as the Add Label node in Kjnode.

Random Chars (Append)：Adds invalid special characters to the input text (characters and number can be customized), mainly to make the generated image have more changes without destroying the prompt intention (whether it works is unknown), because the qwen_image and Z_image models have small random changes in image composition. Here "invalid" is relative.
                       Can simply set the insertion position (before, end, insert), where insert is to average the number of characters into the position behind each punctuation symbol in the original text, from the back to the front.




![node screenshot 2025-12-04 164008](https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab)