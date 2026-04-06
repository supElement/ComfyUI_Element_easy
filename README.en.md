<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenient use. Since I'm too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph,Element ImageCurve,Element HueSat,Element HueBright,Element HueHue,LoadImage_Preview,Frame Calculator,ImageSize Div,Smart merge images


## Installation

- **Manual Installation** <br>
Navigate to the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager** <br>

  Search for ComfyUI_Element_easy in the ComfyUI manager and then install.


## Update

## v1.4.3
  
  Added node Smart merge images.
  - Merges images intelligently when there are sufficient common features between the two.
  - Corrects pixel offset and color difference after image editing by editing models (Flux2 Klein, Qwen Edit, etc.). Usage method in this case: connect the original image and the edited crop_B to the input ports original_image and edited_crop_B, respectively.
  - When merging cropped images into the original image, if conditions permit, the most reliable merging scheme is: original_image + edited_crop_B + original_crop_A. Where original_crop_A is the unmodified and untransformed image cut from original_image.
  - Optimizes the merging method of the Smart merge images node, which has better correction for pixel offset generated after editing by editing models (Flux2 Klein, Qwen Edit, etc.).
  - Adds color matching mode Adaptive Local (strong), which can better repair the color difference after images are edited. Two new parameters are added specifically for this mode: adapt_thresh (color difference threshold) and adapt_align (pre-matching strength - corrects local color spots that may occur after image merging, the higher the value, the more obvious the correction, but it may have a negative impact on the overall color correction of the image).
  - Adds adapt_local_match parameter, providing more options for mask fusion in the color matching mode Adaptive Local (strong), originally the node only had None mode. Merges feature_amount and adapt_kernel into one parameter feather_kernel.

  ![Untitled-2](https://github.com/user-attachments/assets/8b5f4167-9529-4cdc-8df8-9b26f5355688)


## v1.4.0

  - Added an optional image input port to LoadImage_Preview, which can be used for bridging the preview of editing; optimized the layout of the editing panel.
  - Optimized the loading preview logic of Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.8 
Important Update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numeric display box for graph_data.
- Added a mode switch button "C" Smooth Curve mode and Linear mode in the Element_SigmaGraph node.
- Fixed the issue where the sigma output does not match the curve in the Element_SigmaGraph node in curve mode.
- Fixed the issue where the Element_SigmaGraph node gets stuck and blocked when quickly reducing its height.
- Fixed the issue where the LoadImage_Preview node may not be able to be deleted in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v1.4.0）
  
  Added LoadImage_Preview node, where the image browsing feature references part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: browse image files in the specified path, select one after which enter the editing panel (draw mask or draw rectangles, circles, etc. on the image).
  - Shift+left click: draw lines, squares, or circles.
  - L-alpha: used to load image alpha to the canvas.
  - Return: return to the image browsing panel.

  ![image](https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16)


## v1.3.1
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, curve adjustment, real-time preview supports single images and sequence frame images. Double-click to add points, right-click to remove points.

## v1.3.0
  
  Added Element HueSat node, curve adjustment (Hue vs Saturation), real-time preview supports single images and sequence frame images. Double-click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, although it will not cause an error, it will make the other point invalid. A single endpoint on the top curve is sufficient to complete the color adjustment, because the curves at both ends are closed loops.

  ![Image](https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8)

## v1.2.7
  
  Added Element ImageCurve node, curve color adjustment, real-time preview supports single images and sequence frame images. Double-click to add points, right-click to remove points.

  ![Image](https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62)

## v1.2.4 （fix in V1.3.8）
  
  Added Element_SigmaGraph node with custom sigma, original code from the author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph , modified, optimized, and added a lot of content.

  - Added an optional latent input port to synchronize the loading and unloading order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, adding a separate execution function, which is convenient for storing existing sigma sequences as presets<br>
  - Click the position on the curve with the mouse to add or remove control points (double-click to add, right-click to delete), and maintain other control points unchanged when adding or removing points. Release the control point X-axis movement restriction

  
  ![image](https://github.com/user-attachments/assets/c3c362a8-fdb3-47c6-b7b6-159639a3a172)

## v1.2.3
  
  Added ImageSize Div node.

![image](https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9483-9da984d193ef)


## v1.2.2
  
  Added Frame Calculator node, calculates the result as "rounded" + 1, and can be selected in Seconds or frame mode.

  ![image](https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03)


## v1.1.3
  
  Added Black White Color node, the mask input port will be added with the mask generated by the node through ADD operation.

  Initially, the purpose of the ChessboardPattern node was to suppress the pixel offset problem after style conversion in qwenEdit, first convert the style of the mask area, then convert the invert mask area (but it needs two samplings, this method does not work in the Klein model), and then it was found that this kind of mask affects the recognition of objects by the model, so the Black White Color node was created. Try to make the area of the black and white areas average to reduce the problem of inconsistent hue.

  ![image](https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df)


## v0.0.9

  Added ChessboardPattern node, creates a black and white chessboard image, and can be selected in "by_grid_size" or "by_rows_and_cols" two modes to determine the size of the unit cell.

  ![image](https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482)


## v0.0.8

  Added Image Noise Using Mask node, easily adds random noise to the mask area of the image, and can adjust the noise size, opacity, and can choose whether to be in grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, automatically calculates the expansion when there is input (when the parameter is less than the original image, it is in clip mode), at this time, the alignment parameter takes effect, and you can choose the alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, bottom-left alignment, top-right alignment, bottom-right alignment).
  Pad mode can be selected as constant, reflect, edge, another one is the same as reflect. When selecting the constant mode, feathering controls the overall blurring degree, content_blur controls the blurring degree of the expanded area of the original image. When in constant mode, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

![screen shot 2026-01-17 134457](https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266)
![screen shot 2026-01-17 134251](https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158)

  

  
## v0.0.7

  Added Mask Stroke node, mask outline, supports independent control of outline width and blur for inner and outer strokes, and supports adding weight to the non-outlined area as a whole (so that the output mask does not have an area with weight of 0).

  ![node screenshot 2025-12-05 011534](https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d)

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node will automatically identify the color information color_code. Outputs a pure color image, with an image size output port, the image size will be approximated according to divisible_by (integer division).

Text Line Break： Breaks the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation avoidance at the beginning and end. Convenient to connect prompts and generated images together, which requires other nodes, such as the Add Label node in Kjnode.

Random Chars (Append)：Adds invalid special characters to the input text (characters and number can be customized), mainly to make the generated image have greater changes without destroying the intention of the prompt (whether it is effective), because the random changes in the composition of the generated image by qwen_image and Z_image models are small. Here "invalid" is relative.
                       Simple settings can be set for insertion position (before, end, insert), where the insertion method is to evenly distribute the number of characters inserted after the original text punctuation, from the end to the front distribution.




![node screenshot 2025-12-04 164008](https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab)