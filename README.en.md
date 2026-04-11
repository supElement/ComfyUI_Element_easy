<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenient use. Since I'm too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, LoadImage_Preview, Frame Calculator, ImageSize Div, Smart merge images


## Installation

- **Manual Installation**<br>
Enter the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager**<br>

  Search for ComfyUI_Element_easy in the ComfyUI manager and then install.


## Update
## v1.4.4
  
Fixed the output bug of Element_SigmaGraph node in linear mode "L", added output max value parameter, and added forced correction output.

## v1.4.3
  
  Added the Smart merge images node.
  - Smartly merge images when two images have sufficient common features.
  - Corrects pixel offset and color difference after editing images with editing models (Flux2 Klein, Qwen Edit, etc.). The usage method in this case: connect the original image and the edited image to the original_image and edited_crop_B input ports respectively.
  - When merging the cropped image back into the original image, if conditions allow, the most reliable merging scheme: original_image + edited_crop_B + original_crop_A. Where original_crop_A is the unmodified or deformed image cut from original_image.
  - Optimized the fusion method of the Smart merge images node, with better correction for pixel offset after editing with editing models (Flux2 Klein, Qwen Edit, etc.).
  - Added color matching mode Adaptive Local (strong), which can better correct the color difference after editing the image. Two new parameters are added specifically for this mode: adapt_thresh (color difference threshold), adapt_align (pre-matching strength - corrects the local color spots generated after image merging, the higher the value, the more obvious the correction, but it may have a negative impact on the overall color correction of the image).
  - Added adapt_local_match parameter, providing more options for mask fusion in the color matching mode Adaptive Local (strong). The original node only had None mode. Merge feature_amount and adapt_kernel into one parameter feather_kernel.

  ![Untitled-2](https://github.com/user-attachments/assets/8b5f4167-9529-4cdc-8df8-9b26f5355688)

## v1.4.0

  - Added an optional image input port to the LoadImage_Preview node, which can be used for bridging the preview in the editor; optimized the layout of the editing panel.
  - Optimized the loading preview logic of Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.8 
Important Update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numeric display box for graph_data.
- Added a mode switch button "C" for smooth curve mode and linear mode in the Element_SigmaGraph node.
- Fixed the issue where the sigma output of the Element_SigmaGraph node does not match the curve in curve mode.
- Fixed the issue where the Element_SigmaGraph node becomes unresponsive when quickly resizing its height.
- Fixed the issue where it may not be possible to delete the LoadImage_Preview node in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v1.4.0）
  
  Added LoadImage_Preview node, which uses part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: browse image files in the specified path, select one after entering the editing panel (draw mask or draw rectangles, circles, etc. on the image).
  - Shift+left click: draw straight lines, squares, or circles.
  - L-alpha: used to load image alpha to the canvas.
  - Return: return to the image browsing panel.

  ![image](https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16)

## v1.3.1
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, curve adjustment, real-time preview supports single images and sequence frames. Double-click to add points, right-click to remove points.

## v1.3.0
  
  Added Element HueSat node, curve adjustment (Hue vs Saturation), real-time preview supports single images and sequence frames. Double-click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause an error, but will make the other point invalid. A single point at the top end of the curve is enough to complete the color adjustment, because the curves at both ends are closed loops.

  ![Image](https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8)

## v1.2.7
  
  Added Element ImageCurve node, curve color adjustment, real-time preview supports single images and sequence frames. Double-click to add points, right-click to remove points.

  ![Image](https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62)

## v1.2.4 （fix in V1.4.4）
  
  Added custom sigma, Element_SigmaGraph node, original code from author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph, modified, optimized, and added many contents.

  - Added an optional latent input port to synchronize the loading and unloading order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added separate execution function, convenient to store existing sigma sequences as presets<br>
  - Click the position of the curve with the mouse to add or remove control points (double-click to add, right-click to delete), and keep other control points unchanged when adding or removing points. Release the X-axis movement restriction of control points.
  - Added output max value max value parameter, added forced correction output.

  ![image](https://github.com/user-attachments/assets/dce72d55-41a6-4a2e-9f6c-4350ef229dcd)

## v1.2.3
  
  Added ImageSize Div node.

![image](https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef)


## v1.2.2
  
  Added Frame Calculator node, calculates the result as "rounded up" + 1, can choose Seconds or frame mode.

  ![image](https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03)


## v1.1.3
  
  Added Black White Color node, the mask input port will be added with the mask generated by the node using ADD operation.

  Initially, the purpose of the ChessboardPattern node was to suppress the pixel offset problem after style conversion in qwenEdit, first convert the style of the mask area, then convert the invert mask area (but it needs to be sampled twice, this method does not work in Klein models), and then it was found that the ChessboardPattern mask affects the model's recognition of objects, so the Black White Color node was created. Try to make the area of the black and white regions average to reduce the problem of inconsistent hue.
  
  ![image](https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df)


## v0.0.9

  Added ChessboardPattern node, creates a black and white chessboard image, and can choose "by_grid_size" or "by_rows_and_cols" modes to determine the size of the unit cells.

  ![image](https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482)


## v0.0.8

  Added Image Noise Using Mask node, convenient to add random noise in the mask area of the image, can adjust the size of the noise, transparency, and can choose whether to be grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, automatically calculates expansion when input is present (when the parameter is less than the original image, it is clip mode), at this time, the alignment parameter takes effect, can choose alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, bottom-left alignment, top-right alignment, bottom-right alignment).
  pad mode can be selected as constant, reflect, edge, another and reflect effect is the same. When the constant mode is selected, feathering controls the overall blurring degree, content_blur controls the blurring degree of the expanded area of the original image. When the constant mode is selected, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

![screen shot 2026-01-17 134457](https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266)
![screen shot 2026-01-17 134251](https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158)

  

  
## v0.0.7

  Added Mask Stroke node, mask outline, supports separate control of inner and outer stroke width and blur, supports adding weight to the non-stroked area as a whole (making the output mask have no area with weight of 0).
  
  ![node screenshot 2025-12-05 011534](https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d)

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node will automatically recognize color information color_code. Outputs a solid color image, with an image size output port, the image size will be approximated according to divisible_by (divisible by).

Text Line Break： Breaks the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation avoidance at the beginning and end. Convenient to connect prompts and generated images together, which requires other nodes, such as the Add Label node in Kjnode.

Random Chars (Append)：Adds invalid special characters to the input text (characters and number of characters can be customized), mainly to make the generated image have more changes without destroying the intention of the prompt word (not sure if it works), because the random changes in the composition of the generated image by qwen_image and Z_image models are small. Here "invalid" is relative.
                       Can simply set the insertion position (before, end, insert), where insert inserts the number of characters evenly between the punctuation marks of the original text, from the end to the front.