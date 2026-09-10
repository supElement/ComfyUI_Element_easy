<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Simplified%20Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy


A collection of small nodes for easy use. Since I'm too lazy to merge the code, it includes: Element Multi REF, Element Load and Edit Video, Minimax_H3-LatentUpscaler, Smart merge images, LoadImage_Preview, Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, Frame Calculator, ImageSize Div, black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break.


## Installation

### Manual Installation

   Go to the ./ComfyUI/custom_nodes directory and run the following code:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git
      cd ComfyUI_Element_easy
      pip install -r requirements.txt
  Optional: ffmpeg
  The video export (with audio) feature of the node requires ffmpeg to be installed on the system. Download from <a href="https://www.gyan.dev/ffmpeg/builds/">ffmpeg</a>, unzip, and add the bin directory to PATH
  All other features will work normally without ffmpeg installed, but only export as silent video



### Install using Manager

  - Search for ComfyUI_Element_easy in the ComfyUI manager, then install.
 


## Update

## v1.5.5

- Added Element Multi REF and auxiliary node Element ref convert.
- Designed a material management plan for video generation models that require multi-reference input for MiniMax-H3, etc.; equipped with a simple image editor and audio-video editor, with independent parameters for each reference card editor.
- [Detailed description in Chinese](Element_multi_ref_zh.md)
- [Detailed description in English](Element_multi_ref_en.md)

<img width="1520" height="1083" alt="image" src="https://github.com/user-attachments/assets/a25dd0eb-77b2-4111-a60e-5ab787dac767" />


## v1.5.4

- Added Element Load and Edit Video video loading, simple single-track editing node, and related auxiliary nodes Element Video Clip and Element Video Info.
- "Visual single-track video clipper" node: manually trim, rearrange, and preview clips on the interactive timeline.
- [Detailed description in Chinese](Element_scene_detection.zh.md)
- [Detailed description in English](Element_scene_detection.en.md)

<img width="2147" height="1104" alt="image" src="https://github.com/user-attachments/assets/5ba547a7-31c8-4323-bf40-7ec58f1b548e" />

## v1.5.0
  
Added Minimax_H3-LatentUpscaler latent space scaling node, which only scales the latent space of the video without any audio processing, and the output port is Minimax H3 latent.
Added Minimax_H3-LatentUpscaler_Adv  verified latent space scaling node. Conditional scaling mode is introduced, which can be selected as ignore (pass_through), only align without scaling (NO_refs), or scale (refs). The quality is best with the scale (refs) mode.

## v1.4.3（Optimized in V1.4.8）
  
  Added Smart merge images node; intelligently merge images when there are sufficient common features between the two images.
  - Optimal solution: original_image + edited_crop_B + original_crop_A. Here, original_crop_A is the image cut from original_image without modification or deformation, and edited_crop_B is the image that has been edited or redrawn.
  - Support for block merging. That is, when multiple images are input to the edited_crop_B port, the output is a single merged image. Note: The images input to the edited_crop_B port must be Batch rather than list. If it is a list, it must be converted through the Image List To Batch node.

  <img width="2121" height="963" alt="image" src="https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4" />

## v1.3.5 （Optimized in v1.5.6）
  
  Added LoadImage_Preview node.
  - Main function: browse image files in the specified path, select one and enter the editing panel for simple editing. Including: freehand drawing lines, masks, boxes, circles, cropping images.
  - Shift+left click: draw straight lines, squares, or circles.
  - L-alpha: used to load image alpha to the canvas.
  - Return: switch between the thumbnail panel and the editing panel.
  - In image editing mode, support ctrl+v paste image, support mouse drag to import image (such as: drag from the web or file explorer).
  - \ComfyUI\input directory is permanently resident in the node, and the folder path is specified as an additional directory.

  <img width="1453" height="913" alt="image" src="https://github.com/user-attachments/assets/ed8d3d43-b18d-482b-84f1-6c0f6b87add5" />



## v1.3.1 （Optimized in V1.4.5）
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, curve adjustment, real-time preview supports single images and sequence frame images. Click to add points, right-click to remove points.

## v1.3.0 （Optimized in V1.4.5）
  
  Added Element HueSat node, curve adjustment (Hue vs Saturation), real-time preview supports single images and sequence frame images. Click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve at the same time, as this will not cause any errors, but it will make the other point invalid. A single top point is enough for color grading in real-time, because the curves at both ends are closed loops.

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7 （Optimized in V1.4.5）
  
  Added Element ImageCurve node, curve color adjustment, real-time preview supports single images and sequence frame images. Click to add points, right-click to remove points.

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （add "P" button in V1.5.3）
  
  Added Element_SigmaGraph node with custom sigma.
  - Mouse click to add control points at the position of the curve (click to add points, right-click to delete).
  - P button behavior: When the number of points is less than steps+1, the x of the first n-1 points is rearranged to 0, 1/steps, 2/steps, ..., (n-2)/steps, and y remains unchanged; the last point (x, y) is retained as is. When the number of points is not less than steps+1, take the first steps+1 points, and x is evenly distributed to 0, 1/steps, ..., 1, and y remains unchanged. PS: What is it used for? To increase the sampling steps (increase detail) for the later part without changing the step size of the previous steps.

  <img width="1176" height="794" alt="image" src="https://github.com/user-attachments/assets/a8741609-cbe7-4ec8-a88d-5cae79b031a8" />

## v1.2.3
  
  Added ImageSize Div node.

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />


## v1.2.2
  
  Added Frame Calculator node, which calculates the result as "rounded up" + 1.

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  Added Black White Color node, the mask at the input port will be added to the mask generated by the node through ADD operation.
  In order to suppress the pixel offset problem after style conversion in qwenEdit, first convert the style of the mask area, and then convert the invert mask area. Try to make the area of black and white regions average to reduce the problem of inconsistent color tones.
  
  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  Added ChessboardPattern node, which creates a black and white chessboard image.

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  Added Image Noise Using Mask node, which makes it easy to add random noise in the mask area of the image.
  Added Image Pad & Blur node, target width and target height, can choose alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, bottom-left alignment, top-right alignment, bottom-right alignment).
  Pad mode can be constant, reflect, edge, and the other one is the same as reflect. When the constant mode is selected, feathering controls the overall blurring degree, and content_blur controls the blurring degree of the extended area of the original image. When the constant mode is selected, the background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="屏幕截图 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  Added Mask Stroke node, mask stroke, supports separate control of stroke width and blur for inner and outer strokes, and supports adding weight to the non-stroked area as a whole (so that the output mask does not have a weight of 0 area).
  
  <img width="1295" height="731" alt="节点截图 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB: supports RGB and 16-bit color information input.
Text Line Break: breaks the input text by the number of characters, supports punctuation avoidance at the beginning and end.
Random Chars (Append): adds invalid special characters to the input text (characters and number can be customized),
                       
<img width="1590" height="1080" alt="节点截图 2025-12-04 164008" src="https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab" />