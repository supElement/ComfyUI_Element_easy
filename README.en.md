<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for easy use. Since I'm too lazy to merge the code, it includes: black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break. Element_SigmaGraph,Element ImageCurve,Element HueSat,Element HueBright,Element HueHue,LoadImage_Preview,Frame Calculator,ImageSize Div,Smart merge images


## Installation

- **Manual Installation**<br>
Enter the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git

- **Install using Manager**<br>

  In the ComfyUI manager, search for ComfyUI_Element_easy and then install.


## Update

## v1.4.1

  - Optimized the fusion method of the Smart merge images node, providing better correction for pixel offsets generated after editing models (Flux2 Klein, Qwen Edit, etc.). 
  - Optimized the UI interface and functional comments of the LoadImage_Preview node.

## v1.4.0

  - Added an optional image input port to the LoadImage_Preview node, which can be used to bridge the editing in the preview; optimized the layout of the editing panel.
  - Optimized the loading preview logic of the Element ImageCurve, Element HueSat, Element HueBright, and Element HueHue nodes.

## v1.3.9
  
  Added the Smart merge images node.
  - Merges images intelligently when there are sufficient common features between the two images.
  - Corrects pixel offsets and color offsets generated after editing images with editing models (Flux2 Klein, Qwen Edit, etc.). In this case, the usage method is: connect the original image and the edited image to the original_image and edited_crop_B input ports, respectively.
  - When merging the cropped image into the original image, if conditions permit, the most reliable merging scheme is: original_image + edited_crop_B + original_crop_A. Here, original_crop_A is the unmodified or deformed image cut from original_image.

  <img width="1011" height="970" alt="image" src="https://github.com/user-attachments/assets/49b79f5b-4468-4656-ba6a-f9dbdf319ac0" />


## v1.3.8 
Important Update!!!
- Merged Element_SigmaGraph and Element_SigmaGraph(curve) nodes into Element_SigmaGraph; removed the numerical display box for graph_data.
- Added a mode switch button "C" for smooth curve mode and linear mode in the Element_SigmaGraph node.
- Fixed the issue where the sigma output of the Element_SigmaGraph node does not match the curve in curve mode.
- Fixed the issue where the Element_SigmaGraph node is stuck and blocked when quickly reducing its height.
- Fixed the issue where it may not be possible to delete the LoadImage_Preview node in some cases; optimized the LoadImage_Preview node.

## v1.3.5 （Optimized in v1.4.0）
  
  Added the LoadImage_Preview node, where the image browsing function references part of the code from the author Enashka's ComfyUI-nhknodes extension image_loader_with_previews node.<br>
  - Main function: browse image files in the specified path, select one after entering the editing panel (drawing mask or drawing rectangles, circles, etc. on the image).
  - Shift+left click: draw straight lines, squares, or circles.
  - L-alpha: used to load image alpha to the canvas.
  - Return: return to the image browsing panel.

  <img width="989" height="783" alt="image" src="https://github.com/user-attachments/assets/f5d64913-2980-493c-b70a-a60855f2ae16" />


## v1.3.1
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, curve adjustment, real-time preview supports single image and sequence frame images. Double-click to add points, right-click to remove points.

## v1.3.0
  
  Added Element HueSat node, curve adjustment (Hue vs Saturation), real-time preview supports single image and sequence frame images. Double-click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause an error, but will make the other point invalid. A single top point on the real-time end is enough to complete the color adjustment, because the curves at both ends are closed loops.

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7
  
  Added Element ImageCurve node, curve color adjustment, real-time preview supports single image and sequence frame images. Double-click to add points, right-click to remove points.

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （fix in V1.3.8）
  
  Added custom sigma, Element_SigmaGraph node, original code from the author Temult's TWanSigmaGraph node https://github.com/Temult/TWanSigmaGraph , modified, optimized, and added a lot of content.

  - Added an optional latent input port to synchronize the loading and unloading order of ltx audio vae.<br>
  - Added an optional custom_sigmas input port, added a separate execution function, which is convenient to store existing sigma series as presets<br>
  - Click on the position of the curve with the mouse to add or remove control points (double-click to add, right-click to delete), and keep other control points unchanged when adding or removing points. Release the control point X-axis movement restriction

  
  <img width="1021" height="797" alt="image" src="https://github.com/user-attachments/assets/c3c362a8-fdb3-47c6-b7b6-159639a3a172" />

## v1.2.3
  
  Added ImageSize Div node.

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />


## v1.2.2
  
  Added Frame Calculator node, calculating the result as "rounded" + 1, with the option to choose Seconds or frame.

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  Added Black White Color node, the mask input port will be added to the mask generated by the node through ADD operation.

  The initial purpose of the ChessboardPattern node was to suppress the pixel offset problem after style conversion in qwenEdit, first convert the style of the mask area, then convert the invert mask area (but it needs two samplings, this method does not work in the Klein model), and then it was found that the ChessboardPattern mask affects the model's recognition of objects, so the Black White Color node was created. Try to make the area of the black and white regions as average as possible to reduce the problem of inconsistent color tones.
  
  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  Added ChessboardPattern node, creating a black and white chessboard image, with two modes to determine the size of the unit cell: "by_grid_size" or "by_rows_and_cols".

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  Added Image Noise Using Mask node, easily add random noise in the mask area of the image, can adjust the size and opacity of the noise, and can choose whether to be grayscale mode.
  
  Added Image Pad & Blur node, target width and target height, automatically calculate expansion when input is present (clip mode when parameters are smaller than the original image), at this time, alignment parameter takes effect, can choose alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, top-right alignment, bottom-left alignment, bottom-right alignment). pad mode can be selected as constant, reflect, edge, another one is the same as reflect. When the constant mode is selected, feathering controls the overall blurring degree, content_blur controls the blurring degree of the expanded area of the original image. When the constant mode is selected, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="屏幕截图 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  Added Mask Stroke node, mask outline, supports separate control of outline width and blur for inner and outer strokes, and supports adding weight to the non-outlined area as a whole (so that the output mask does not have an area with weight of 0).
  
  <img width="1295" height="731" alt="节点截图 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB：Supports RGB and 16-bit color information input, the node will automatically identify the color information color_code. Outputs a solid color image, with an image size output port, the image size will be approximated based on divisible_by (integer division).

Text Line Break： Breaks the input text by the number of characters, supports Chinese, English, and mixed Chinese and English, supports punctuation avoidance at the beginning and end. Conveniently connect prompts and generated images together, which requires other nodes, such as the Add Label node in Kjnode.

Random Chars (Append)：Adds invalid special characters (can customize characters and number of characters) to the input text, mainly to make the generated image have greater changes (whether it works or not) without destroying the prompt intention, because the random changes in the image composition generated by qwen_image and Z_image models are small. Here, "invalid" is relative.
                       Can simply set the insertion position (before, end, insert), where insert is to average the number of characters inserted into the punctuation marks behind the original text, from the end to the front.




<img width="1590" height="1080" alt="节点截图 2025-12-04 164008" src="https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab" />