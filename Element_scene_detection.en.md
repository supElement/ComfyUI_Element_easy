# Element Scene Detection User Guide

## 📦 Node Group Overview

This node group provides **video scene detection + visual timeline editing** capabilities, consisting of 3 nodes:

| Node | Purpose |
|---|---|
| **Element Scene Detection** | Main node: import video, auto/manual scene splitting, timeline editing |
| **Element Video Clip** | Downstream node: outputs images/audio/frame count/duration of selected clips |
| **Element Video Info** | Downstream node: outputs video FPS, width, height |

---

## 🚀 Quick Start

1. Add the **Element Scene Detection** node, click **Import** in the top-left corner to load a local video
2. Click **Auto Split** to detect scene cuts automatically (or edit manually as described in "Timeline Operations" below)
3. Connect the main node's **info** output to the info input of **Element Video Clip**
4. Run the workflow — Element Video Clip will output the clip frames and audio

---

## 🎛 Main Node Toolbar

| Control | Description |
|---|---|
| **Import** | Upload a local video file |
| **Auto Split** | Run PySceneDetect scene detection immediately using the Threshold value |
| **Threshold** | Detection sensitivity (5–50); lower values produce finer cuts |
| **Manual** | Manual marking mode: when enabled, click/drag on the track to add cuts |
| **Force 2** | Force-split the video into two parts when no cuts exist |
| **Auto Run** | ★ When checked, **scene splitting runs automatically on workflow execution** if the timeline has no manual edits |
| **Sync Cuts** | Fetch auto cuts cached on the backend (use together with Auto Run) |
| **Clear** | Clear all cuts and restore the full video as a single clip |

Main node parameters:

- **force_rate**: Force output FPS; 0 = keep the source frame rate
- **subsampling**: Keep every Nth frame (e.g. 2 = half the frames); downstream frame_count/seconds will change accordingly

---

## ✂️ Timeline Operations

| Action | Effect |
|---|---|
| **Click a clip** | Select it (Ctrl+click to add, Shift+click for range selection) |
| **Drag a clip** | Change playback order |
| **Drag a clip edge** | Trim the clip; hold **Alt/Ctrl** while dragging = roll trim (the split point moves as one unit) |
| **Drag the ruler / red playhead** | Scrub the preview |
| **Right-click a boundary** | Merge two adjacent clips |
| **Fit / arrows / Select All** | Fit to width, move selected clips, select all |

Transport bar below the preview: jump to timeline start/end, jump to current clip start/end, **play current clip**, **play all clips in sequence** (with audio sync).

**Export** at the bottom: export selected clips (or all clips when Export All is checked) as mp4 files with audio to the **Out Dir** directory.

---

## 🔗 Downstream Nodes

### Element Video Clip

- **clip_select** modes:
  - `select clip`: outputs the clip currently **selected** on the timeline
  - `segnum`: select by **SegNum** index (1-based, timeline order)
  - `first clip` / `last clip` / `all`: first / last / all segments
- Outputs: `images`, `audio`, `frame_count`, `seconds`, `first_image`, `last_image`

### Element Video Info

- Outputs the effective `FPS` (accounting for force_rate/subsampling), `Width`, and `Height`

---

## ⚠️ Notes

1. **Dependencies**:
   - Required: `av` (PyAV)
   - For scene detection: `pip install scenedetect`
   - For audio playback / export with audio: **ffmpeg** must be installed on the system (without it, clips export without audio)
2. **Temporary files**: Uploaded videos are saved to ComfyUI/input/element_scene_detection/ and persist with the workflow; re-import only if the file was manually moved or deleted
3. **Manual edits take priority**: Once you have trimmed/reordered the timeline, Auto Run will not overwrite your manual decisions
4. The info output is a JSON bundle (containing video path, segment ranges, FPS, etc.) designed for this node group's downstream nodes, and can be parsed by Element Video Clip / Element Video Info
