# Element Multi REF — Usage Guide

A multi-reference material panel node for ComfyUI, providing visual management and editing of first/last frames, reference images, reference videos, driving audio and other multi-channel inputs for video generation models (MiniMax-H3 / LTXV style) — with a built-in prompt, preset snapshots (batch playback) and material collect/export.

## 1. Dependencies

pip install av opencv-python numpy   # required
pip install scenedetect              # optional: better/faster Auto Split scene detection

- Requires a recent ComfyUI build (comfy_api.latest node API).
- ffmpeg/ffprobe on the system PATH serves as a decode fallback for exotic audio formats (flac/alac etc.).

## 2. Node Overview

| Node | Purpose |
|---|---|
| Element Multi REF | Visual material panel: import → edit → outputs a REF_ALL_IN_ONE info bundle (+ prompt); holds preset snapshots, run_preset_NUM decides what each run outputs |
| Element ref convert | Converts the bundle into 21 typed output ports + prompt + info manifest for downstream use |

### 2.1 run_preset_NUM (per-run output switch)

| Value | Behavior |
|---|---|
| 0 (default) | Output the CURRENT panel state (materials/slots/prompt as edited on the panel) |
| ≥ 1 | Output preset #n (1-based); out-of-range values clamp to the last preset |

- Connect an upstream Int node whose value changes per queue run (counter / list / batch index…) to play back presets in order within a single batch job.
- Typing a number into the on-node widget also applies that preset to the panel (~0.2s debounce; the preset currently linked to the workspace is skipped).
- The info bundle records the applied preset (preset_index) and the raw input (run_preset_NUM).

## 3. Element Multi REF (Material Panel)

### 3.1 Slots (21 total)

| Group | Slot IDs | Kind |
|---|---|---|
| First/Last frame | first_frame / last_frame | image |
| Reference images | ref_image_0 ~ ref_image_8 | image ×9 |
| Reference videos | ref_video_0 ~ ref_video_2 | video ×3 |
| Video audio | ref_video_audio_0 ~ _2 | audio (can pair with videos) ×3 |
| Reference audio | ref_audio_0 ~ ref_audio_2 | audio ×3 |
| Driving audio | drive_audio | audio ×1 |

Supported formats:

- Image: .png .jpg .jpeg .webp .bmp
- Video: .mp4 .mov .avi .mkv .webm .m4v
- Audio: .mp3 .wav .flac .ogg .oga .m4a .m4b .aac .opus .wma .aif .aiff .aifc .mka .weba .caf


<img width="959" height="1018" alt="image" src="https://github.com/user-attachments/assets/bca44ef0-954f-4e9a-bea0-5ee5e771be69" />


### 3.2 Prompt

Below the slot grid is a prompt textarea:

- Saved with the workflow and output through the convert node's prompt port;
- Every preset snapshot stores its own prompt — applying a preset switches the prompt;
- Leave it empty if you do text conditioning elsewhere.

### 3.3 Importing Files

- **Drag & drop** files onto any slot (or empty panel area → auto-assigned to the next free slot of the matching kind).
- **Click** an empty slot to open a file browser (filtered by slot kind).
- Multi-file drops are distributed across slots in order.
- Uploads are deduplicated by SHA-256; files are stored in ComfyUI/input/element_multi_ref/.

### 3.4 Slot Operations

- Hover a slot for ✎ Edit / ✕ Remove buttons.
- **Drag to swap**: drag a filled slot onto another slot of the same kind to swap contents.
- **Right-click menu**: clear slot / reset edits; on an empty paired audio slot: open the paired video editor / replace with an independent audio file.
- **Click** an empty paired audio slot opens the paired video editor directly.
- Top bar **Clear All**: wipes all materials, edits and the prompt — **presets are kept**.

### 3.5 Image Editor


<img width="999" height="900" alt="image" src="https://github.com/user-attachments/assets/5de32290-4068-4ab5-b53c-61179d25c8b3" />


Open via ✎ on an image slot:

**Crop**:

- Drag to draw a box, drag inside the box to move;
- **Edge/corner resize**: hover an edge for a ↔/↕ cursor or a corner for a diagonal cursor, then drag to resize; stepping follows div by;
- **div by** (default 32): size snapping multiple (model-friendly);
- **W × H** readout at the right of the top bar shows the current crop box size (source size when there is no crop box);
- **Clear crop** removes the box.

**Out W / Out H (output resolution)**:

- Auto-follows the crop box once drawn; type custom values to set the output resolution for the cropped area;
- **Lock ratio**: couples W/H by the crop box's aspect ratio (source ratio when no crop box); Out auto-updates only when the crop aspect ratio changes — moving or uniformly scaling the box keeps your manual values;
- **⟳ reset**: back to the crop box size (source resolution when no crop box).

**Paint** (brush annotation, usable as mask/inpaint hints; toolbar fixed on the second row):

- Color, brush size 2–80; the cursor is a **ring** matching the brush size (dashed ring for the eraser);
- **Box / Circle**: drag to draw a rectangle/ellipse; **Outline** checked = stroked (Box corners are square), unchecked = filled; cursor becomes a crosshair while a shape tool is active;
- **Shift shortcuts**: in Box/Circle mode hold Shift = square/circle; in free brush mode hold Shift = draw a straight line from the stroke start, release Shift to set the endpoint;
- **Eraser** (with a shape tool active it erases that shape's area), **Undo** (15 steps), **Clear paint**;
- Strokes are saved as a transparent PNG overlay; the crop box and dimming remain visible in paint mode.

### 3.6 Audio/Video Editor (Timeline)


<img width="1085" height="814" alt="image" src="https://github.com/user-attachments/assets/a5349cb9-7d6d-46e0-afa2-18629a14e9ba" />


**Blue selection area or selected segments = final output range**:

- Use selection checked → the blue box defines the output;
- Unchecked → the highlighted segments define the output (Shift = range select / Ctrl = toggle; picking a segment auto-unchecks Use selection; with none selected the segment under the playhead is output);
- Drag the blue box edges to trim, drag its body to move (video: check Snap to snap to cut points);
- **Full** selects everything (0 → end); **Fit** zoom-to-fit; **Zoom** manual scale.

**Segment operations**:

- **Auto Split**: automatic scene detection (threshold Thr; PySceneDetect first, falls back to a built-in HSV histogram diff if not installed);
- **Manual (key M)**: click anywhere on the track to slice;
- **Right-click a boundary**: merge the two adjacent segments;
- **Drag a boundary**: default = roll trim (both sides move); hold Alt/Ctrl = one-sided trim/extend;
- **Drag a segment body**: reorder (a cyan insert line shows the drop point; multi-selected segments move together);
- **Clear**: restore the default timeline (clears cuts & segment selection, playhead back to zero; saved on Apply).

**Playback & transport**:

- Transport bar: |◀ (start), ◀| (segment start), ▶ (play current segment), ▶▶ (play all segments in order), |▶ (segment end), ▶| (end);
- Click the ruler / audio track / middle of the blue box: drag the playhead to scrub (frame preview + synced audio).

**Quantization (output length = a + n × div)**:

| Preset | div | a |
|---|---|---|
| MiniMax H3 (17n+5) | 17 | 5 |
| LTXV (8n+1) | 8 | 1 |
| 4n | 4 | 0 |
| Custom | custom | custom |

- Live info, e.g. [seg 1] Out: 107 = 17×6+5;
- Audio: check Quantize to align seconds to frames via Ref FPS (default 24).

**Video extras**: FPS (0 = source fps) output resampling, Out W/H scaling (lock ratio, ⟳ reset).

**Audio extras**: Quantize / Ref FPS.

**Keyboard shortcuts**:

| Key | Action |
|---|---|
| Space | Play/stop all segments |
| ← / → | Step back/forward 1 frame (audio: 0.05s); Shift = 1 second |
| I / O | Set in/out point at the playhead |
| Home / End | Selection to start/end |
| M | Toggle manual split mode |

### 3.7 Video–Audio Pairing (ref_video_audio_N)

- Importing a video with audio into ref_video_N automatically shows that video's waveform in the matching empty ref_video_audio_N slot (tagged from ref_video_N), no separate import needed;
- At output it takes the audio of the video's current edit range;
- Click / right-click the paired slot to: open the paired video editor / replace with an independent audio file.

### 3.8 Presets (snapshots & batch playback)


<img width="1272" height="802" alt="image" src="https://github.com/user-attachments/assets/7663b2ad-c531-447f-9780-d4c6f868fe66" />


Each preset stores a full snapshot (materials + slot edits + prompt) and a panel thumbnail.

- **Save Preset**: if the workspace currently comes from a preset (teal link) it is overwritten in place (index / run_preset_NUM unchanged), otherwise a new one is created (Save as New is also available in the overwrite dialog); a custom thumbnail can be picked.
- **Presets modal**: card grid with drag-to-reorder, click-to-select, inline rename; card width / font size sliders (remembered); fullscreen toggle; window size remembered.
- **Load…**: import from a JSON export or a Collect package (ZIP / folder); duplicates (same pid or identical content) are skipped automatically.
- **Export…**: export all presets to a JSON file (thumbnails embedded as data URLs).
- **Num / A-Z / Z-A**: re-sort by the number in the name or by name.
- **Delete / Clear all**: delete the selected / all presets (Clear all needs a second confirming click).
- **Apply**: apply the selected preset to the workspace.
- Badges: teal card = preset currently linked to the workspace; yellow number = the preset's 1-based index (the value run_preset_NUM expects).
- The four buttons below the prompt (first / previous / next / last) switch and apply presets directly.

### 3.9 Collect and Export

Packs the current workspace plus all presets into one folder tree:

00_workspace/            ← current workspace (exported only if it has materials or a prompt)
  media/  extra/  thumbs/
01_<preset name>/        ← one folder per preset
  media/  extra/  thumbs/
emr_package.json         ← manifest, re-importable via Presets → Load…

- media/ = slot materials, extra/ = brush/stroke overlays, thumbs/ = preset thumbnails.
- Destination: a remembered folder is written to silently (File System Access API); otherwise you are asked once and it is remembered. The folder icon in the bottom bar opens the **Export folder** settings (view / forget / re-pick).
- Fallback path: server-side write to any path you type (default = ComfyUI output dir, path remembered); if that also fails, falls back to a ZIP download.
- Re-import later with **Presets → Load… → Collect folder… / JSON / ZIP file** (media files are re-uploaded and paths remapped automatically).

### 3.10 State Persistence

- All materials, edits, prompt and presets are serialized into the hidden refs_data field and saved/loaded with the workflow;
- Materials are referenced by absolute path — moving/deleting source files or switching machines requires re-import (shows Material missing).

## 4. Element ref convert (Port Conversion)

Just connect REF_ALL_IN_ONE to the info input.

### 4.1 Outputs (21 + prompt + info)

| Port | Type | Content |
|---|---|---|
| first_frame / last_frame | IMAGE | First/last frame (after crop/paint/scaling) |
| ref_image_0 ~ _8 | IMAGE | Reference images ×9 |
| ref_video_0 ~ _2 | IMAGE | Frame sequence [T,H,W,3] (float 0–1, resampled to output FPS, gaps forward-filled from the previous frame) |
| ref_video_audio_0 ~ _2 | AUDIO | Paired video audio or standalone audio |
| ref_audio_0 ~ _2 | AUDIO | Reference audio |
| drive_audio | AUDIO | Driving audio |
| prompt | STRING | Prompt text from the panel (or the applied preset's prompt) |
| info | STRING | Per-slot manifest JSON |

### 4.2 Empty-Slot Placeholder Behavior

- Image ports → 64×64 black image;
- Audio ports → 1 second of 44100 Hz silence;
- Failed slots also return placeholders; the terminal prints [ElementRefConvert] slot ... → placeholder.

### 4.3 info Manifest Format

{
  "version": 2,
  "producer": "ElementRefConvert",
  "slots": {
    "first_frame": {"has": true, "kind": "image", "w": 512, "h": 512},
    "ref_video_0": {"has": true, "kind": "video", "frames": 107, "w": 832, "h": 480},
    "drive_audio": {"has": true, "kind": "audio", "seconds": 5.0}
  },
  "missing": ["ref_image_0", "ref_audio_2"],
  "prompt": "..."
}

## 5. Typical Workflow

[Element Multi REF]
 ├─ first_frame  ← first frame image (crop / paint)
 ├─ ref_image_*  ← character / scene reference images
 ├─ ref_video_0  ← reference video (Auto Split → select segments → 17n+5 aligned)
 ├─ drive_audio  ← driving audio (optional Quantize)
 └─ prompt       ← text prompt (or switch via run_preset_NUM presets)
        │ REF_ALL_IN_ONE
        ▼
[Element ref convert]
 ├── first/last frame ──▶ video model first/last frame conditioning
 ├── ref_image_*     ──▶ reference image encoders
 ├── ref_video_0     ──▶ VAE Encode / video reference
 ├── ref_video_audio ──▶ audio conditioning
 ├── drive_audio     ──▶ audio-driven models (S2V / lip-sync etc.)
 └── prompt          ──▶ text conditioning

Batch playback: connect a counter/list to run_preset_NUM, save presets #1…#n, queue n runs — each run outputs the corresponding preset's materials and prompt.

## 6. FAQ

**Q: No waveform on audio slots?**
Decoding relies on /element_multi_ref/media_info; when PyAV cannot decode it falls back to the ffmpeg CLI — make sure ffmpeg is installed.

**Q: fps mismatch log in the terminal?**
When the nominal fps deviates >2% from frames/duration, the real fps is used automatically — a normal correction that prevents drift over playback.

**Q: Auto Split shows "fallback"?**
scenedetect isn't installed; the built-in HSV diff is used instead. Recommend pip install scenedetect.

**Q: Timeline laggy with big videos?**
Frame previews (LRU 400 entries) and a decoded-frame cache (~600MB) are built in; use Fit/Zoom to keep the visible range small.

**Q: Old workflow reports Material missing?**
Source files were moved/deleted — just re-drop them (upload dedup will not store duplicates).

**Q: How to move presets to another machine?**
Presets live in the workflow (refs_data); use Collect and Export (or Presets → Export…) to export them together with the media, then Presets → Load… on the other machine — importing a JSON without media will warn you to use Collect folder… instead.

**Q: run_preset_NUM beyond the preset count?**
It clamps to the last preset; 0 always outputs the current panel state.

**Q: Where are files stored?**
Input materials: ComfyUI/input/element_multi_ref/ (with an _index.json dedup index); paint overlays: ComfyUI/output/element_multi_ref/paint/.
