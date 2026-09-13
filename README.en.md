<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy

A ComfyUI extension primarily focused on **visual interfaces and convenient interaction**. The nodes in this package are different: instead of a slider paired with a number, the entire tool is moved directly into the node.

## What You Can Get

**🎬 Video Editing (Element Load and Edit Video)**
Edit videos directly on the node without leaving ComfyUI: automatically detects scene cut points, or manually cut, trim, and reorder segments; preview while editing, and output both video and audio directly after finishing.

**🗂 Multi Reference Material Panel (Element Multi REF)**
A material panel for video models (MiniMax-H3, LTXV, Wan, etc.) that require "reference images + start/end frames + reference video + audio" input. Each material can be cropped, annotated with brushes, and timed; presets can be saved—paired with queues, multiple sets of materials and prompts can be run at once without switching images.

**🎛 Curve Color Grading (HueSat / HueBright / HueHue / ImageCurve)**
Like adjusting colors in photo editing software, the curve is drawn directly on the image, and the effect is immediately visible by dragging; the same real-time preview for videos.

**📐 Custom Sampling Curves (Element_SigmaGraph)**
Draw the sigma curve of the sampler by hand, especially useful when you want fewer steps in the beginning and more details in the end.

**🧩 Over 20 Practical Nodes**
Image smart merging, mask stroke, image edge blur, frame count calculation, etc.

## Points to Note as Disadvantages

- **Requires some time to get started**: The panel-style nodes have many functions, and the first time you open them, you might wonder what each button does; it is recommended to use the detailed documentation for each node;
- **Some functions depend on external programs**: Video export with audio requires the system to have ffmpeg installed, and automatic scene detection suggests installing scenedetect; they can still be used, but the corresponding functions will be limited;
- **Compatibility depends on a newer version of ComfyUI** (Multi REF uses the new node API), older versions of ComfyUI may not be installable;
- **Nodes are numerous but independent**: If you only need one or two functions, this package might be too large for you.

## 📦 Node Navigation

**🎬 Video and Material Management**

- [Element Multi REF](#element-multi-ref) (including auxiliary node Element ref convert)
- [Element Load and Edit Video](#element-load-and-edit-video) (including auxiliary nodes Element Video Clip / Element Video Info)
- [Minimax_H3-LatentUpscaler](#minimax_h3-latentupscaler) (including Adv version)

**🎛 Curve Color Grading**

- [Element ImageCurve] · [Element HueSat] · [Element HueBright] · [Element HueHue]

**🖌 Image Editing and Masking**

- [LoadImage_Preview] · [Smart merge images] · [black_white_color] · [mask_noise_element] · [mask_stroke] · [image_pad_blur]

**📐 Image Generation and Sampling Control**

- [Element_SigmaGraph] · [chessboard] · [empty_image_rgb]

**🔧 Number and Text Tools**

- [Frame Calculator] · [ImageSize Div] · [random_chars] · [text_line_break]

---

<a id="element-multi-ref"></a>
## Element Multi REF

<sub>New in v1.5.7

Detailed documentation: [Chinese](Element_multi_ref_zh.md) | [English](Element_multi_ref_en.md)</sub>

A material and prompt management solution designed for video/image models (MiniMax-H3, LTXV, Wan, Klein, Qwen, etc.) that require multiple reference inputs:

- 21 typed slots: reference images ×9, reference videos ×3, as well as start/end frames, various audio, and Prompt cards;
- Each card has an independent simple image editor (crop, brush annotation) and audio/video timeline editor (quantized alignment according to rules like 17n+5, 8n+1);
- Supports storage, loading, and exporting of multiple presets, as well as organizing all references and prompts;
- `run_preset_NUM` parameter corresponds to the preset list index; when receiving inputs that change with prompts, paired with sampling inference nodes, it can achieve continuous generation or editing of multiple images/videos;
- The bottom bar of the panel has four area switch icons (reference images, start/end frames, audio/video, Prompt), which can be freely combined to meet different needs, and can even be used as a prompt preset node.

The auxiliary node **Element ref convert** is used for reference data format conversion.

<img width="1691" height="874" alt="Element Multi REF" src="https://github.com/user-attachments/assets/e8c32036-3a21-4864-93eb-228ffce3c82b" />

---

<a id="element-load-and-edit-video"></a>
## Element Load and Edit Video

<sub>New in v1.5.4 · 

Detailed documentation: [Chinese](Element_scene_detection.zh.md) | [English](Element_scene_detection.en.md)</sub>

A visual single-track video editor node:

- PySceneDetect automatically detects scene cut points, or manually split, trim, and reorder segments on an interactive timeline;
- Synchronous preview of video and audio;
- Directly outputs segment frame sequences and corresponding audio, supports exporting mp4 with audio (requires ffmpeg).

Auxiliary nodes **Element Video Clip**, **Element Video Info** are used together.

<img width="2147" height="1104" alt="Element Load and Edit Video" src="https://github.com/user-attachments/assets/5ba547a7-31c8-4323-bf40-7ec58f1b548e" />

---

<a id="minimax_h3-latentupscaler"></a>
## Minimax_H3-LatentUpscaler

<sub>New in v1.5.0 · Added concurrently with Adv version</sub>

A dedicated node that only scales the video latent space, does not process audio, and outputs Minimax H3 latent.

**Adv version** includes validation and introduces three conditional scaling modes:

| Mode | Behavior |
|---|---|
| pass_through | Ignores validation and passes through directly |
| NO_refs | Aligns but does not scale |
| refs | Scales (best quality) |

---

<a id="element-imagecurve"></a>
<a id="element-huesat"></a>
<a id="element-huebright"></a>
<a id="element-huehue"></a>
## Curve Color Grading Series

<sub>Added陆续 from v1.2.7 to v1.3.1 · Optimized in v1.4.5</sub>

All four nodes use the same interaction method: **draw the curve directly on the image for real-time preview, single-click to add points, right-click to remove points**, supporting both single and sequence-frame images.

| Node | Curve Type |
|---|---|
| Element ImageCurve | RGB / R / G / B channel curves |
| Element HueSat | Hue → Saturation |
| Element HueBright | Hue → Brightness |
| Element HueHue | Hue → Hue |

> ⚠️ Except for Element ImageCurve, do not add points at both ends of the curve simultaneously: the curves at both ends are closed loops, adding points at both ends will make one point invalid, in fact, one endpoint is sufficient to complete the color grading.

<img width="1695" height="891" alt="Element HueSat" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />
<img width="1767" height="1008" alt="Element ImageCurve" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

---

<a id="loadimage_preview"></a>
## LoadImage_Preview

<sub>New in v1.3.5 · Optimized in v1.5.6</sub>

Browse image files under a specified path, select, and enter the editing panel for simple editing: freely draw lines, masks, squares, circles, and crop images.

- `Shift + Left click`: Draw straight lines, squares, or circles
- `L-alpha`: Load the image's alpha channel to the canvas
- `Return`: Switch between the zoom panel and the editing panel
- In edit mode, supports `Ctrl+V` to paste images, and supports dragging directly from the web or file explorer
- The ComfyUI input directory is permanently resident in the node, and the folder path specified as an additional directory

<img width="1453" height="913" alt="LoadImage_Preview" src="https://github.com/user-attachments/assets/ed8d3d43-b18d-482b-84f1-6c0f6b87add5" />

---

<a id="smart-merge-images"></a>
## Smart merge images

<sub>New in v1.4.3 · Optimized in v1.4.8</sub>

Smartly merge two images when they have enough common features, suitable for stitching the results of local redraws back into the original image:

- **Optimal input scheme**: original_image + edited_crop_B + original_crop_A. Among them, original_crop_A is the image cropped from the original without modification or deformation, and edited_crop_B is the edited or redrawn image;
- Supports block merging: when the edited_crop_B port inputs multiple images, the output is a single image of the final merged result. Note that the input must be **Batch and not list**, if it is a list, it needs to be converted by the Image List To Batch node.

<img width="2121" height="963" alt="image" src="https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4" />

---

<a id="black_white_color"></a>
## black_white_color

<sub>New in v1.1.3</sub>

A black-and-white partition style conversion node, used to suppress pixel offset issues after style conversion in qwenEdit: first convert the style of the mask area, then convert the invert mask area; try to make the black-and-white areas evenly sized to reduce hue inconsistency issues.

The mask at the input port will be added to the mask generated by the node.

<img width="1596" height="1084" alt="black_white_color" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />

---

<a id="mask_noise_element"></a>
## mask_noise_element

<sub>New in v0.0.8 (Image Noise Using Mask)</sub>

Conveniently add random noise to the mask area of an image.

<img width="1724" height="878" alt="Screenshot 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />

---

<a id="mask_stroke"></a>
## mask_stroke

<sub>New in v0.0.7</sub>

Mask stroke: individual control of inner and outer stroke widths and blur, supports adding overall weight to non-stroke areas (ensuring that the output mask has no areas with a weight of 0).

<img width="1295" height="731" alt="mask_stroke" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

---

<a id="image_pad_blur"></a>
## image_pad_blur

<sub>New in v0.0.8</sub>

Add borders to images with optional blur:

- target width / target height, 9 alignment modes (center, left, right, top, bottom, top-left, top-right, bottom-left, bottom-right)
- pad mode: constant / reflect / edge (the other option has the same effect as reflect)
- In constant mode: feathering controls the overall blur, content_blur controls the blur of the original image extension area, background_color parameter takes effect (compatible with RGB color and HEX color code)

<img width="2147" height="1092" alt="image_pad_blur alignment mode" src="https://github.com/user-attachments/assets/e864a294-c70c-4409-9573-c357b6437158" />

---

<a id="element_sigmagraph"></a>
## Element_SigmaGraph

<sub>New in v1.2.4 · Added P button in v1.5.3</sub>

Draw custom sigma curves directly on the node: single-click to add points, right-click to delete points.

**P button**: Rearrange the x-coordinates of control points—when the number of points is less than steps+1, the first n-1 points are reordered to 0, 1/steps, ..., (n-2)/steps, y remains unchanged, and the last point is kept as is; when the number of points is at least steps+1, take the first steps+1 points evenly distributed. Simply put: **Without changing the step size in the first part, add more sampling steps (add details) in the later part**.

<img width="1176" height="794" alt="Element_SigmaGraph" src="https://github.com/user-attachments/assets/a8741609-cbe7-4ec8-a88d-5cae79b031a8" />

---

<a id="chessboard"></a>
## chessboard

<sub>New in v0.0.9 (ChessboardPattern)</sub>

Create a black-and-white checkerboard image.

<img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />

---

<a id="empty_image_rgb"></a>
## empty_image_rgb

<sub>New in v0.0.6, optimized in v1.5.9 </sub>

Create a monochrome image, with color selected from the color wheel, brightness controlled by a slider; the eyedropper can pick color from any position on the screen, but if the browser is not Chrome / Edge 96+, the eyedropper may not be available, and the color palette button next to it can be used instead.

<img width="1329" height="904" alt="image" src="https://github.com/user-attachments/assets/9dd2957b-e261-40ce-8041-87a83df33880" />

---

<a id="frame-calculator"></a>
## Frame Calculator

<sub>New in v1.2.2, optimized in v1.5.9 </sub>

A frame count calculation node, providing minimax H3, ltx2, wan presets, and can be customized with div_by and offset.

<img width="1154" height="655" alt="image" src="https://github.com/user-attachments/assets/9a99acc7-96b3-43e8-a3c7-1b4fd2ab93f4" />

---

<a id="imagesize-div"></a>
## ImageSize Div

<sub>New in v1.2.3</sub>

Size alignment calculation.

<img width="1317" height="596" alt="ImageSize Div" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />

---

<a id="random_chars"></a>
## random_chars

<sub>New in v0.0.6 (Random Chars Append)</sub>

Append invalid special characters to the input text (characters and counts can be customized).

---

<a id="text_line_break"></a>
## text_line_break

<sub>New in v0.0.6, optimized in v1.5.9</sub>

Break the input text into lines by character count, supporting punctuation avoidance at the beginning and end, punctuation squeezing, and hanging. The final effect depends on the output carrier.

<img width="1693" height="981" alt="image" src="https://github.com/user-attachments/assets/62b3f66a-6cec-4d10-904a-5a33a102ba92" />

---

## Installation

### Manager Installation

Search for **ComfyUI_Element_easy** in the ComfyUI Manager and then Install.

### Manual Installation

Enter the `./ComfyUI/custom_nodes` directory and run:

    git clone https://github.com/supElement/ComfyUI_Element_easy.git
    cd ComfyUI_Element_easy
    pip install -r requirements.txt
### Optional Dependency: ffmpeg

The node's **video export (with audio)** feature requires the system to have ffmpeg installed. Windows users can download from [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) and add the bin directory to PATH after extracting.

When ffmpeg is not installed, all other functions work normally, only the video export is silent.