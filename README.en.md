<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenience. Since I was too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, LoadImage_Preview, Frame Calculator, ImageSize Div, Smart merge images


## Installation

- **Manual Installation**<br>
Go to the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager**<br>
Search for ComfyUI_Element_easy in the ComfyUI manager and then install.


## Update
## v1.4.4
  
Fixed the output bug of Element_SigmaGraph node in linear mode "L", added the output max value parameter, and added forced correction output.

## v1.4.3
  
  Added the Smart merge images node.
  - Smartly merge images when there are sufficient common features between the two images.
  - Correct the pixel offset and color difference that may occur after editing the image with editing models (Flux2 Klein, Qwen Edit, etc.). The usage method in this case is: connect the original image and the edited crop_B image to the original_image and edited_crop_B input ports, respectively.
  - When merging the cropped image back to the original image, if the conditions allow, the most reliable merging scheme is: original_image + edited_crop_B + original_crop_A. Here, original_crop_A is the unmodified or deformed image cut from the original_image.
  - Optimized the fusion method of the Smart merge images node, which has better correction for the pixel offset generated after editing with editing models (Flux2 Klein, Qwen Edit, etc.).
  - Added the color matching mode Adaptive Local (strong), which can better repair the color difference generated after the image is edited. Two new parameters are added specifically for this mode: adapt_thresh (color difference threshold), adapt_align (pre-matching strength - corrects the local spots that may be generated after the image is merged, the higher the value, the more obvious the correction, but it may have a negative impact on the overall color correction of the image).
  - Added the adapt_local_match parameter, which provides more choices for the mask fusion of the color matching mode Adaptive Local (strong). The original node only had the None mode. The feature_amount and adapt_kernel are merged into a single parameter feather_kernel.

  ![Untitled-2](https://github.com/user-attachments/assets/8b5f4167-9529-4cdc-8df8-9b26f5355688)

## v1.4.0

  - Added an optional image input port to the LoadImage_Preview node, which can be used for bridging editing in the preview; optimized the layout of the editing panel.
  - Optimized the load preview logic of the Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.8 
Important Update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numeric display box for graph_data.
- Added a mode switch button "C" for smooth curve mode and linear mode in the Element_SigmaGraph node.
- Fixed the problem that the sigma output of the Element_SigmaGraph node does not match the curve in curve mode.
- Fixed the problem that the Element_SigmaGraph node is blocked when it is quickly reduced in height.
- Fixed the problem that the LoadImage_Preview node may not be able to be deleted in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v1.4.0）
  
  Added LoadImage_Preview node, where the image browsing function refers to some code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: browse the image files in the specified path, select one after entering the editing panel (drawing mask or drawing rectangles, circles, etc. on the image).
  - Shift+left click: draw straight lines, squares, or circles.
  - L-alpha: used to load the alpha of the image into the canvas.
  - Return: return to the image browsing panel.

  ![image](https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16)

## v1.3.1
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, with curve adjustment and real-time preview support for single and sequence frame images. Double-click to add points, right-click to remove points.

## v1.3.0
  
  Added Element HueSat node, with curve adjustment (Hue vs Saturation), real-time preview support for single and sequence frame images. Double-click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause an error, but it will make the other point invalid. The top end point of the real-time adjustment can complete the color adjustment, because the curves at both ends are closed loops.

  ![Image](https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8)

## v1.2.7
  
  Added Element ImageCurve node, with curve coloring, real-time preview support for single and sequence frame images. Double-click to add points, right-click to remove points.

  ![Image](https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62)

## v1.2.4 （fix in V1.4.4）
  
  Added Element_SigmaGraph with custom sigma, original code from the author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph, modified, optimized, and added many contents.

  - Added an optional latent input port to synchronize the load and unload order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added a separate execution function, which is convenient for storing existing sigma sequences as presets.<br>
  - Click the position of the curve with the mouse to add or remove control points (double-click to add, right-click to delete), and maintain the other control points unchanged when adding or removing points. Remove the X-axis movement restriction of the control point.
  - Added the output max value max value parameter, and added the output forced correction.

  ![image](https://github.com/user-attachments/assets/dce72d55-41a6-4a2e-9f6c-4350ef229dcd)

## v1.2.3
  
  Added ImageSize Div node.

![image](https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef)


## v1.2.2
  
  Added Frame Calculator node, which calculates the result as "rounded up" + 1 and can be selected in Seconds or frame mode.

  ![image](https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03)


## v1.1.3
  
  Added Black White Color node, where the mask at the input port will be added to the mask generated by the node by ADD operation.

  The original purpose of the ChessboardPattern node was to suppress the pixel offset problem after style transformation in qwenEdit, first transform the style of the mask area, then transform the invert mask area (but it needs two samplings, this method does not work in the Klein model), and then it was found that the ChessboardPattern mask affects the model's recognition of objects, so the Black White Color node was created. Try to make the area of the black and white regions average to reduce the problem of inconsistent color tones.
  
  ![image](https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df)


## v0.0.9

  Added ChessboardPattern node, which creates a black and white chessboard image. You can choose "by_grid_size" or "by_rows_and_cols" modes to determine the size of the unit cell.

  ![image](https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482)


## v0.0.8

  Added Image Noise Using Mask node, which is convenient to add random noise in the mask area of the image, and can adjust the size and opacity of the noise, and can choose whether to be in grayscale mode.
  
  Added Image Pad & Blur node, with target width and target height. If there is an input, it will automatically calculate the expansion (when the parameter is less than the original image, it is in clip mode), at this time, the alignment parameter takes effect, and you can choose the alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, top-right alignment, bottom-left alignment, bottom-right alignment). The pad mode can be chosen as constant, reflect, or edge, and the other one is the same as reflect. When choosing the constant mode, the feathering controls the overall blurring degree, and the content_blur controls the blurring degree of the expanded area of the original image. When the constant mode is chosen, the background_color parameter takes effect, and is compatible with rgb color and HEX color code (16-bit color code).

![screen shot 2026-01-17 134457](https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266)
![screen shot 2026-01-17 134251](https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158)

  

  
## v0.0.7

  Added Mask Stroke node, which supports stroke width and blur degree for both inner and outer strokes, and supports adding weight to the non-stroked area as a whole (so that the output mask does not have a weight of 0 area).
  
  ![node screenshot 2025-12-05 011534](https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d)

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, and the node will automatically recognize the color information color_code. Outputs a pure color image, with an output port for image size, and the image size will be approximated according to divisible_by (integer division).

Text Line Break： Breaks the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, and supports punctuation symbols to avoid the beginning and end. It is convenient to connect prompts and generated images together, which requires other nodes, such as the Add Label node in Kjnode. Random Chars (Append)：Adds invalid special characters to the input text (characters and number can be customized), mainly to make the generated image have greater changes without destroying the intention of the prompt (it is unknown whether it is effective), because the qwen_image and Z_image models have little random changes in the image composition. The "invalid" here is relative.
                       Simple settings for insertion position (before, end, insert), where insert is to evenly distribute the number of characters inserted into the punctuation symbols after the original text, from the back to the front distributed.