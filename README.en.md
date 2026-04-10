<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for convenient use. Since I was too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph,Element ImageCurve,Element HueSat,Element HueBright,Element HueHue,LoadImage_Preview,Frame Calculator,ImageSize Div,Smart merge images


## Installation

- **Manual Installation**<br>
Enter the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager**<br>

  Search for ComfyUI_Element_easy in the ComfyUI manager and then install.


## Update

## v1.4.3
  
  Added node Smart merge images.
  - Merges images intelligently when there are sufficient common features.
  - Corrects pixel offset and color difference after image editing by editing models (Flux2 Klein, Qwen Edit, etc.). Usage method in this case: connect the original image and the edited crop_B to the input ports of original_image and edited_crop_B, respectively.
  - When merging the cropped image back into the original image, if conditions allow, the most reliable merging scheme is: original_image + edited_crop_B + original_crop_A. Here, original_crop_A is the unmodified or deformed image cut from original_image.
  - Optimizes the merging method of the Smart merge images node, and has better correction for pixel offset generated after editing by editing models (Flux2 Klein, Qwen Edit, etc.).
  - Adds color matching mode Adaptive Local (strong), which can better fix the color difference generated after image editing. Two new parameters are added specifically for this mode: adapt_thresh (color difference threshold), adapt_align (pre-matching strength - corrects color spots locally generated after image merging, the higher the value, the more obvious the correction, but it may have a negative impact on the overall color correction of the image).
  - Adds adapt_local_match parameter, providing more options for mask blending in the color matching mode Adaptive Local (strong), originally the node only had None mode. Merges feature_amount and adapt_kernel into a single parameter feather_kernel.

  ![Untitled-2](https://github.com/user-attachments/assets/8b5f4167-9529-4cdc-8df8-9b26f5355688)


## v1.4.0

  - Added an optional image input port to the LoadImage_Preview node, which can be used to bridge the editing in the preview; optimized the layout of the editing panel.
  - Optimized the loading preview logic of Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.8 
Important update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numeric display box for graph_data.
- Added a mode switch button "C" for smooth curve mode and linear mode in the Element_SigmaGraph node.
- Fixed the issue where the sigma output of the Element_SigmaGraph node does not match the curve in curve mode.
- Fixed the issue where the Element_SigmaGraph node is unresponsive when quickly reducing its height.
- Fixed the issue where the LoadImage_Preview node may not be able to be deleted in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v1.4.0）
  
  Added LoadImage_Preview node, where the image browsing function refers to part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: Browses image files in the specified path, selects one and enters the editing panel (draw mask or draw rectangles, circles, etc. on the image).
  - Shift+left click: Draw straight lines, squares, or circles.
  - L-alpha: Used to load image alpha to the canvas.
  - Return: Return to the image browsing panel.

  ![image](https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16)


## v1.3.1
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, curve adjustment, real-time preview supports single images and sequence frame images. Double-click to add points, right-click to remove points.

## v1.3.0
  
  Added Element HueSat node, curve adjustment (Hue vs Saturation), real-time preview supports single images and sequence frame images. Double-click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause an error, but will make the other point invalid. One endpoint at the top can complete the color adjustment in real-time, because the curves at both ends are closed loops.

  ![Image](https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8)

## v1.2.7
  
  Added Element ImageCurve node, curve coloring, real-time preview supports single images and sequence frame images. Double-click to add points, right-click to remove points.

  ![Image](https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62)

## v1.2.4 （fix in V1.3.8）
  
  Added Element_SigmaGraph node with custom sigma, original code from author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph, modified, optimized, and added a lot of content.

  - Added an optional latent input port to synchronize the load and unload order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added separate execution function, convenient for storing existing sigma sequences as presets<br>
  - Clicking on the curve with the mouse adds or removes control points (double-click to add, right-click to delete), and when adding or removing points, the other control points remain unchanged. Release the control point X axis movement restriction

  
  ![image](https://github.com/user-attachments/assets/c3c362a8-fdb3-47c6-b7b6-159639a3a172)

## v1.2.3
  
  Added ImageSize Div node.

![image](https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef)


## v1.2.2
  
  Added Frame Calculator node, calculates the result as "rounded up" + 1, and can be selected in Seconds or frame mode.

  ![image](https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03)


## v1.1.3
  
  Added Black White Color node, the mask input port will be added with the mask generated by the node in ADD operation.

  Initially, the purpose of the ChessboardPattern node was to suppress the pixel offset problem after style transformation in qwenEdit, first transform the mask area style, then transform the invert mask area (but it needs to be sampled twice, this method does not work in Klein model), later found that this mask affects the recognition of objects by the model, so there was a Black White Color node. Try to make the area of black and white regions even to reduce the problem of inconsistent color tones.
  
  ![image](https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df)


## v0.0.9

  Added ChessboardPattern node, creating a black and white chessboard image, and can be selected in "by_grid_size" or "by_rows_and_cols" two modes to determine the size of the unit cell.

  ![image](https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482)


## v0.0.8

  Added Image Noise Using Mask node, convenient for adding random noise in the mask area of the image, can adjust the size of the noise, transparency, and can choose whether to be grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, will automatically calculate the expansion when input is present (when the parameter is smaller than the original image, it is in clip mode), at this time, the alignment parameter takes effect, can choose the alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, bottom-left alignment, top-right alignment, bottom-right alignment).
  pad mode can be selected as constant, reflect, edge, another one is the same as reflect. When the constant mode is selected, the feathering controls the overall blurring degree, the content_blur controls the blurring degree of the expanded area of the original image. When the constant mode is selected, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

![screen shot 2026-01-17 134457](https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266)
![screen shot 2026-01-17 134251](https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158)

  

  
## v0.0.7

  Added Mask Stroke node, mask outlining, supports independent control of inner and outer stroke width and blur, supports the addition of weight to the non-stroke area as a whole (so that the output mask does not have an area with weight of 0).
  
  ![node screenshot 2025-12-05 011534](https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d)

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node will automatically identify color information color_code. Outputs a pure color image, with an image size output port, the image size will be approximated according to divisible_by (integer division).

Text Line Break： Breaks the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation avoidance at the beginning and end. Convenient to connect prompts and generated images together, which requires other nodes, such as the Add Label node in Kjnode.

Random Chars (Append)：Adds invalid special characters to the input text (characters and number can be customized), mainly to make the generated image have more changes without destroying the intention of the prompt (whether it works or not), because the random changes in the composition of the image generated by qwen_image and Z_image models are small. Here "invalid" is relative.
                       Can simply set the insertion position (before, end, insert), among which insert inserts the number of characters evenly into the end of the original text after each punctuation mark, from the back to the front.




![node screenshot 2025-12-04 164008](https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab)