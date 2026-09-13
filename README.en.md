<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Simplified%20Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy

The main direction of this extension is to provide convenient nodes for visual UI interfaces and easy interaction. It includes: Element Multi REF, Element Load and Edit Video, Minimax_H3-LatentUpscaler, Smart merge images, LoadImage_Preview, Element_SigmaGraph, Element ImageCurve, Element HueSat, Element HueBright, Element HueHue, Frame Calculator, ImageSize Div, black_white_color, chessboard, empty_image_rgb, image_pad_blur, mask_noise_element, mask_stroke, random_chars, text_line_break.


## Installation

### Manual Installation<br>

   Navigate to the ./ComfyUI/custom_nodes directory and run the following commands:<br>

      git clone https://github.com/supElement/ComfyUI_Element_easy.git
      cd ComfyUI_Element_easy
      pip install -r requirements.txt
  Optional: ffmpeg
  The node's **video export (with audio)** feature requires the system to have ffmpeg installed. For Windows, download ffmpeg from <a href="https://www.gyan.dev/ffmpeg/builds/">ffmpeg</a>, extract it, and add the bin directory to PATH.
  All other features work normally without ffmpeg, but video export will be silent.

### Install using Manager<br>

  - Search for ComfyUI_Element_easy in the comfyUI manager, then install it.


## Update

## v1.5.7

Element Multi REF is a multi-modal reference material and prompt preset management node for multi-reference input models, accompanied by the auxiliary node Element ref convert.
It is suitable for image/video inference models like MiniMax-H3, LTX, Wan, Klein, Qwen that require multi-reference input, for centralized management of reference images, audio, video, and prompt presets.

Main features:
- Supports loading and editing images, audio, and video, unifying the management of reference materials and prompt presets.
- Built-in simple image and audio/video editors; each reference card's editing parameters are independently saved, not affecting each other.
- Supports saving, calling, loading, and exporting multiple presets, and can centrally categorize all reference materials and prompts.
- run_preset_NUM corresponds to the preset list index. When it receives input that changes with the prompt queue in ComfyUI and works with sampling/inference nodes, it can continuously generate or edit multiple images/videos.
- The bottom bar of the panel has four area switches: reference image, first and last frames, audio/video, Prompt. You can freely combine the panel to suit different needs; when only Prompt is retained, it can also be used as a prompt preset node.
- Auxiliary node Element ref convert: used for converting/connecting reference materials with the main node.

- [Chinese version details](Element_multi_ref_zh.md)
- [English version details](Element_multi_ref_en.md)

<img width="1691" height="874" alt="image" src="https://github.com/user-attachments/assets/e8c32036-3a21-4864-93eb-228ffce3c82b" />

## v1.5.4

- Added Element Load and Edit Video video loading and simple single-track editing node, and related auxiliary nodes Element Video Clip and Element Video Info.
- "Visual single-track video editor" node: manually trim, rearrange, and preview clips on an interactive timeline.
- [Chinese version details](Element_scene_detection.zh.md)
- [English version details](Element_scene_detection.en.md)

<img width="2147" height="1104" alt="image" src="https://github.com/user-attachments/assets/5ba547a7-31c8-4323-bf40-7ec58f1b548e" />

## v1.5.0
  
Added Minimax_H3-LatentUpscaler latent space upscaling node, which only upscals the video's latent space without any audio processing, with the output port being Minimax H3 latent.
Added Minimax_H3-LatentUpscaler_Adv  advanced latent space upscaling node with validation. Introduced conditional upscaling mode, with options to ignore (pass_through), align without upscaling (NO_refs), or upscale (refs), with the best quality being the upscale (refs) mode.

## v1.4.3（Optimized in V1.4.8）
  
  Added node Smart merge images; intelligently merges images when they have enough common features.
  - Optimal solution: original_image + edited_crop_B + original_crop_A. Here, original_crop_A is the unmodified or deformed image from original_image, and edited_crop_B is the edited or redrawn image.
  - Added support for block-based merging. That is, when multiple images are input to the edited_crop_B port, the output is a single final merged image. Note: Images input to the edited_crop_B port must be Batch, not list; if it's a list, it needs to be converted using the Image List To Batch node.

  <img width="2121" height="963" alt="image" src="https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4" />

## v1.3.5 （Optimized in v1.5.6）
  
  Added LoadImage_Preview node.
  - Main function: browse image files under a specified path, select one, and enter the editing panel to perform simple edits. Includes: freehand drawing lines, masks, boxes, circles, cropping images.
  - shift+left click: draw straight lines, squares, or perfect circles.
  - L-alpha: used to load the image alpha into the canvas.
  - Return: switch between the thumbnail panel and the editing panel.
  - In image editing mode, supports ctrl+v to paste images, and supports dragging images with the mouse (e.g., from a web page or file explorer).
  - ComfyUI's input directory resident node, folder path specification as added directory.

  <img width="1453" height="913" alt="image" src="https://github.com/user-attachments/assets/ed8d3d43-b18d-482b-84f1-6c0f6b87add5" />



## v1.3.1 （Optimized in V1.4.5）
  
  Added Element HueBright (Hue vs Brightness) and Element HueHue (Hue vs Hue) nodes, curve adjustment, real-time preview supports single and sequence frame images. Single-click to add points, right-click to remove points.

## v1.3.0 （Optimized in V1.4.5）
  
  Added Element HueSat node, curve adjustment (Hue vs Saturation), real-time preview supports single and sequence frame images. Single-click to add points, right-click to remove points.<br>
  - Note: Do not add points at both ends of the curve simultaneously, although it won't cause an error, it will make the other point invalid. Real-time, having one endpoint is enough to complete the color adjustment, as the two ends of the curve are closed.

  <img width="1695" height="891" alt="Image" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />

## v1.2.7 （Optimized in V1.4.5）
  
  Added Element ImageCurve node, curve color adjustment, real-time preview supports single and sequence frame images. Single-click to add points, right-click to remove points.

  <img width="1767" height="1008" alt="Image" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

## v1.2.4 （add "P" button in V1.5.3）
  
  Added custom sigma, Element_SigmaGraph node.
  - Click on the curve to add or remove control points (single-click to add, right-click to delete)
  - P button behavior: When the number of points is less than steps+1, the first n-1 points' x are reordered to 0, 1/steps, 2/steps, ..., (n-2)/steps, y remains unchanged; the last point (x, y) is kept as is. When the number of points is at least steps+1, take the first steps+1 points, x is evenly distributed as 0, 1/steps, ..., 1, y remains unchanged. PS: What's the use? Without changing the step size of the front steps, it adds sampling steps for the back (adds detail).

  <img width="1176" height="794" alt="image" src="https://github.com/user-attachments/assets/a8741609-cbe7-4ec8-a88d-5cae79b031a8" />

## v1.2.3
  
  Added ImageSize Div node.

<img width="1317" height="596" alt="image" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />


## v1.2.2
  
  Added frame calculator node Frame Calculator, the calculation result is rounded and incremented by 1.

  <img width="1043" height="578" alt="image" src="https://github.com/user-attachments/assets/0a922590-c3bb-4504-8708-443476c3ac03" />


## v1.1.3
  
  Added Black White Color node, the mask at the input port will perform ADD operation with the mask generated by the node.
  To suppress pixel offset issues during style conversion in qwenEdit, first convert the style of the mask area, then convert the invert mask area. Try to make the black and white areas evenly sized to reduce hue inconsistency issues.
  
  <img width="1596" height="1084" alt="image" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />


## v0.0.9

  Added ChessboardPattern node, creates black and white checkerboard images.

  <img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />


## v0.0.8

  Added Image Noise Using Mask node, easily add random noise to the mask area of an image.
  Added Image Pad & Blur node, target width and target height, can choose alignment mode (center alignment, left alignment, right alignment, top alignment, bottom alignment, top-left alignment, top-right alignment, bottom-left alignment, bottom-right alignment).
  pad mode can choose constant, reflect, edge, the other is the same as reflect effect. When choosing constant mode, feathering controls the overall blur level, content_blur controls the blur level of the original image's extended area. constant mode, background_color parameter takes effect, compatible with rgb color and HEX color code (16-bit color code).

<img width="1724" height="878" alt="Screenshot 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />
<img width="2147" height="1092" alt="Screenshot 2026-01-17 134251" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

  

  
## v0.0.7

  Added Mask Stroke node, mask stroke, supports independent control of inner and outer stroke width and blur, supports adding overall weight to non-stroke areas (making the output mask have no areas with weight 0).
  
  <img width="1295" height="731" alt="Node Screenshot 2025-12-05 011534" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

  
## v0.0.6

Empty Image RGB：supports RGB and 16-bit color information input.
Text Line Break： wraps input text by character count, supports punctuation avoidance at the beginning and end.
Random Chars (Append)：adds invalid special characters to the input text (customizable characters and count),

<img width="1590" height="1080" alt="Node Screenshot 2025-12-04 164008" src="https://github.com/user-attachments/assets/1cdacfe2-7c7a-4434-9f48-1ec571bb19ab" />