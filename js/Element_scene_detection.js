import { app } from "../../../scripts/app.js";

// const NODE_NAME = "ElementSceneDetection";
const STYLE_ID = "esd-style";
const MIN_SEG_FRAMES = 2; // ★ 修剪后每个片段保留的最小帧数
const EXPORT_DIR_MAX_W = 420; // ★ Out Dir 字段

/* =====================================================
   说明：下方 SVG 里的 xmlns="http://www.w3.org/2000/svg" 只是 XML 命名空间"标识字符串"
   ===================================================== */
function svgToCursor(svg, x, y) {
  return `url("data:image/svg+xml;charset=utf8,${encodeURIComponent(svg)}") ${x} ${y}, auto`;
}

const CURSOR_HAND = svgToCursor(
  '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M22 14a8 8 0 0 1-8 8"/><path d="M18 11v-1a2 2 0 0 0-2-2a2 2 0 0 0-2 2"/><path d="M14 10V9a2 2 0 0 0-2-2a2 2 0 0 0-2 2v1"/><path d="M10 9.5V4a2 2 0 0 0-2-2a2 2 0 0 0-2 2v10"/><path d="M18 11a2 2 0 1 1 4 0v3a8 8 0 0 1-8 8h-2c-2.8 0-4.5-.86-5.99-2.34l-3.6-3.6a2 2 0 0 1 2.83-2.82L7 15"/></svg>',
  8, 2);

const CURSOR_EW = svgToCursor(
  '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="16" viewBox="0 0 24 16"><path fill="white" d="M7 4 2 8l5 4v-2.5h10V12l5-4-5-4v2.5H7V4z"/></svg>',
  12, 8);

const CURSOR_SCISSORS = svgToCursor(
  '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="6" cy="6" r="3"/><circle cx="6" cy="18" r="3"/><line x1="20" y1="4" x2="8.12" y2="15.88"/><line x1="14.47" y1="14.48" x2="20" y2="20"/><line x1="8.12" y1="8.12" x2="12" y2="12"/></svg>',
  12, 12);

const CURSOR_TRIM = svgToCursor(
  '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"><path d="M8 4H4v16h4"/><path d="M16 4h4v16h-4"/><path d="M7 12h10"/><path d="m14 9 3 3-3 3"/><path d="m10 9-3 3 3 3"/></svg>',
  12, 12);

const svgIcon = (paths, size = 13) =>
  `<svg class="esd-ico" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="#ffffff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${paths}</svg>`;

const ICONS = {
  film: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M7 3v18"/><path d="M3 7.5h4"/><path d="M3 12h18"/><path d="M3 16.5h4"/><path d="M17 3v18"/><path d="M17 7.5h4"/><path d="M17 16.5h4"/>',
  folder: '<path d="M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"/>',
  zap: '<path d="M4 14a1 1 0 0 1-.78-1.63l9.9-10.2a.5.5 0 0 1 .86.46l-1.92 6.02A1 1 0 0 0 13 10h7a1 1 0 0 1 .78 1.63l-9.9 10.2a.5.5 0 0 1-.86-.46l1.92-6.02A1 1 0 0 0 11 14z"/>',
  checkAll: '<path d="M18 6 7 17l-5-5"/><path d="m22 10-7.5 7.5L13 16"/>',
  trash: '<path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" y1="11" x2="10" y2="17"/><line x1="14" y1="11" x2="14" y2="17"/>',
  fit: '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
  save: '<path d="M15.2 3a2 2 0 0 1 1.4.6l3.8 3.8a2 2 0 0 1 .6 1.4V19a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2z"/><path d="M17 21v-7a1 1 0 0 0-1-1H8a1 1 0 0 0-1 1v7"/><path d="M7 3v4a1 1 0 0 0 1 1h7"/>',
  chevronLeft: '<path d="m15 18-6-6 6-6"/>',
  chevronRight: '<path d="m9 18 6-6-6-6"/>',
  music: '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
  play: '<path d="M7 4.5v15l13-7.5z" fill="#ffffff" stroke="none"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1.5" fill="#ffffff" stroke="none"/>',
  playAll: '<path d="M3 6h10"/><path d="M3 12h10"/><path d="M3 18h10"/><path d="M16 4.5v15l7.5-7.5z" fill="#ffffff" stroke="none"/>',
  segStart: '<path d="M19 5v14L8.5 12z" fill="#ffffff" stroke="none"/><line x1="6" y1="5" x2="6" y2="19"/>',
  segEnd: '<path d="M5 5v14l10.5-7z" fill="#ffffff" stroke="none"/><line x1="18" y1="5" x2="18" y2="19"/>',
  allStart: '<line x1="3" y1="5" x2="3" y2="19"/><path d="M21 5v14l-7-7z" fill="#ffffff" stroke="none"/><path d="M13 5v14l-7-7z" fill="#ffffff" stroke="none"/>',
  allEnd: '<line x1="21" y1="5" x2="21" y2="19"/><path d="M3 5v14l7-7z" fill="#ffffff" stroke="none"/><path d="M11 5v14l7-7z" fill="#ffffff" stroke="none"/>'

};

const PREVIEW_SIZE = 384;

function installStyles() {
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement("style");
  style.id = STYLE_ID;
  style.textContent = `
    .esd {
      --bg: #11141b; --panel: #191e28; --line: #30384a;
      --text: #e9eef8; --muted: #919bad;
      --cyan: #43d9d1; --blue: #477ff0; --amber: #f3af4e; --red: #ef6a77;
      box-sizing: border-box;
      display: flex; flex-direction: column;
      width: 100%; height: 100%; min-height: 540px;
      color: var(--text); background: var(--bg);
      border-radius: 9px; overflow: hidden;
      font: 12px/1.35 Inter, Segoe UI, Arial, sans-serif;
      user-select: none;
    }
    .esd * { box-sizing: border-box; }
    .esd img { pointer-events: none; -webkit-user-drag: none; } 
    .esd button { font: inherit; }
    .esd-head {
      display: flex; align-items: center; gap: 6px; padding: 8px;
      background: #1c222d; border-bottom: 1px solid var(--line);
      flex-wrap: nowrap; white-space: nowrap; flex-shrink: 0;
    }
	.esd-vinfo {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 3px 10px;
      flex-shrink: 0;
      color: var(--muted);
      background: #141922;
      border-bottom: 1px solid var(--line);
      font-size: 11px;
      white-space: nowrap;
    }
    .esd-vinfo-main {
      overflow: hidden;
      text-overflow: ellipsis;
      min-width: 0;          
    }


    .esd-btn {
      height: 28px; border: 1px solid #3b4558; color: #dce5f5; background: #252d3a;
      border-radius: 5px; padding: 0 9px; cursor: pointer;
      display: inline-flex; align-items: center; gap: 5px; flex-shrink: 0;
    }
    .esd-btn:hover { background: #303a4b; border-color: #516079; }
    .esd-btn.danger:hover { color: #fff; background: #6d2833; border-color: #a64250; }
    .esd-btn.primary { background: #2a4b7a; border-color: #4e7fc0; }
    .esd-btn.primary:hover { background: #3a6a9a; }
    .esd-spacer { flex: 1; }
    .esd-status {
      margin-left: auto;    
      flex-shrink: 0;
      color: var(--muted);
      max-width: 180px;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .esd-field.grow {
      flex: 1 1 auto;
      flex-shrink: 1;              
      min-width: 150px;
      max-width: ${EXPORT_DIR_MAX_W}px;
    }
    .esd-field.grow input[type="text"] {
      width: auto;                
      flex: 1 1 auto;
      min-width: 90px;
    }
    
	
    .esd-preview-container {
      display: flex; flex-direction: column; align-items: center; justify-content: center;
      padding: 4px 12px; background: #0d1118; border-bottom: 1px solid var(--line);
      height: 308px; min-height: 308px; 
      flex-shrink: 0; gap: 4px; position: relative;
    }
    .esd-preview-container img {
      height: 264px; width: auto; max-width: 100%;
      object-fit: contain; border-radius: 4px; background: #000;
      flex-shrink: 0; display: block;
    }
    .esd-preview-wrap { display: flex; flex-direction: column; align-items: center; gap: 2px; max-width: 100%; min-width: 250px; }
    .esd-preview-bar { display: flex; align-items: center; gap: 6px; align-self: stretch; flex-shrink: 0; }
    .esd-transport { display: flex; align-items: center; gap: 4px; flex-shrink: 0; }
    .esd-tbtn { width: 30px; padding: 0; justify-content: center; }
    .esd-tbtn.playing { background: #2a4b7a; border-color: #4e7fc0; }
    .esd-preview-info { margin-left: auto; text-align: right; font-size: 12px; color: var(--muted); white-space: nowrap; }
    .esd-field { display: flex; align-items: center; gap: 4px; color: var(--muted); white-space: nowrap; flex-shrink: 0; }
    .esd-field input[type="number"] { width: 60px; height: 24px; padding: 2px 4px; color: var(--text); background: #0d1118; border: 1px solid #333d50; border-radius: 4px; outline: none; }
    .esd-field input[type="text"] { width: 130px; height: 24px; padding: 2px 4px; color: var(--text); background: #0d1118; border: 1px solid #333d50; border-radius: 4px; outline: none; }
    .esd-field input[type="checkbox"] { accent-color: var(--cyan); width: 16px; height: 16px; cursor: pointer; flex-shrink: 0; }
    .esd-timeline-shell { flex: 0 0 auto; height: 166px; display: flex; flex-direction: column; min-height: 0px; border-bottom: 1px solid var(--line); overflow: hidden; }
    .esd-viewport {
      flex: 0 0 auto;
      height: 309px;          
      overflow: auto;
      overflow-y: hidden;
      background: #0e1219;
      scrollbar-color: #49556a #171c25;
      position: relative;
    }
    .esd-stage { position: relative; min-width: 100%; height: auto; padding-bottom: 5px; }
    .esd-ruler { position: relative; height: 26px; border-bottom: 1px solid #2c3443; background: #131821; }
    .esd-tick { position: absolute; bottom: 0; width: 1px; height: 8px; background: #556074; color: #8490a4; }
    .esd-tick.major { height: 13px; background: #78849a; }
    .esd-tick span { position: absolute; left: 4px; top: -11px; white-space: nowrap; font-size: 10px; }
    .esd-track { position: relative; height: 94px; border-bottom: 1px solid #262d3a; background-image: linear-gradient(90deg, rgba(255,255,255,.027) 1px, transparent 1px); }
    .esd-track.audio { height: 40px; background-color: #111720; position: relative; border-bottom: none; }
    .esd-seg {
      position: absolute; top: 8px; height: 78px;
      border: 1px solid #5688ec; border-radius: 5px; background: #223c6e; overflow: hidden;
    }
    .esd-seg.selected { border: 2px solid #b9ddff; box-shadow: 0 0 0 2px #328bff99; }
    .esd-seg-label { position: absolute; left: 9px; top: 50%; transform: translateY(-50%); color: #fff; font-weight: 600; text-shadow: 0 1px 2px #000; z-index: 2; pointer-events: none; }
    .esd-seg-thumbs { display: flex; width: 100%; height: 100%; overflow: hidden; }
    .esd-seg-thumb {
      flex-shrink: 0; height: 100%; object-fit: contain; background: #000;
      color: transparent; font-size: 0; line-height: 0;
      background-image: linear-gradient(45deg, #1a2330 25%, #232d3d 25%, #232d3d 50%, #1a2330 50%, #1a2330 75%, #232d3d 75%, #232d3d 100%);
      background-size: 20px 20px;
      opacity: 0; transition: opacity 0.2s ease-in;
    }
    .esd-seg-thumb.loaded { opacity: 1; }
    .esd-cut { position: absolute; top: 0; width: 2px; height: 100%; background: #ff9900; z-index: 5; cursor: pointer; }
    .esd-cut::before { content: ""; position: absolute; top: 0; left: -4px; border-left: 4px solid transparent; border-right: 4px solid transparent; border-top: 6px solid #ff9900; }
    .esd-drag-cut { position: absolute; top: 0; width: 2px; height: 100%; background: #ffaa00; z-index: 4; pointer-events: none; border-left: 2px dashed #ffaa00; }
    .esd-playhead { position: absolute; top: 0; bottom: 0; width: 2px; z-index: 11; background: #ff737d; cursor: ew-resize; pointer-events: none; }
    .esd-playhead::before { content: ""; position: absolute; left: -5px; top: 0; border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 8px solid #ff737d; }
    .esd-wave { position: absolute; top: 50%; transform: translateY(-50%); left: 0; }
    .esd-wave-seg { position: absolute; top: 0; bottom: 0; overflow: hidden; border: 1px solid rgba(86,136,236,.35); border-radius: 3px; }
    .esd-wave-seg.selected { border-color: var(--cyan); box-shadow: 0 0 0 1px #43d9d166; }
    .esd-audio-placeholder { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #556; font-size: 10px; }
    .esd-foot {
      display: flex; align-items: center; gap: 9px; min-height: 31px; padding: 5px 8px;
      color: #8f9bad; background: #141922; flex-wrap: nowrap; white-space: nowrap; flex-shrink: 0;
    }
    .esd-foot .btn-group { display: flex; gap: 5px; }
    .esd-hint { color: #718096; overflow: hidden; text-overflow: ellipsis; }
    /* ===================== 鼠标指针样式 ===================== */
    .esd-seg { cursor: ${CURSOR_HAND}; }
    .esd-ruler { cursor: ${CURSOR_EW}; }
    .esd-playhead { cursor: ${CURSOR_EW}; pointer-events: auto; }
    .esd-playhead::after { content: ""; position: absolute; top: 0; bottom: 0; left: -7px; width: 16px; }
    .esd.marking .esd-track, .esd.marking .esd-track .esd-seg, .esd.marking .esd-track .esd-cut { cursor: ${CURSOR_SCISSORS}; }
    .esd-stage.trim-hover .esd-seg, .esd-stage.trimming .esd-seg { cursor: ${CURSOR_TRIM} !important; }
    .esd-stage.trim-hover .esd-track, .esd-stage.trimming .esd-track, .esd-stage.trim-hover .esd-cut, .esd-stage.trimming .esd-cut { cursor: ${CURSOR_TRIM}; }
    .esd-stage.reordering, .esd-stage.reordering .esd-seg { cursor: grabbing !important; }
    .esd-insert-line { position: absolute; top: 0; width: 2px; height: 100%; background: var(--cyan); box-shadow: 0 0 6px var(--cyan); z-index: 12; pointer-events: none; }
    .esd-ico { display: inline-block; vertical-align: -2px; flex-shrink: 0; }
  `;
  document.head.appendChild(style);
}

class SceneDetectionUI {
  constructor(node, root, clipsWidget) {
    this.node = node;
    this.root = root;
    this.clipsWidget = clipsWidget;
    this.state = this.readState();
    this.zoom = 64;
    this.totalFrames = 0;
    this.cuts = [];
    this.selections = [];
    this.waveform = null;
    this.dragging = false;
    this.dragCut = null;
    this.draggingPlayhead = false;
    this.playheadFrame = 0;
    this._selAnchor = null;              
    this._renderSig = "";                
    this._lastPreviewFrame = -1;
    this._previewSeq = 0;                
    this._probe = null;                  
    this._previewThrottleTimer = null;   
    this._lastPreviewAt = 0;            
    this._playing = false;
    this._playRaf = 0;
    this._playAcc = 0;
    this._playQueue = [];
    this._playAllMode = false;
    this._playLastT = 0;
    this._playTickBound = this._playTick.bind(this);
    this._audioEl = null;
    this._audioPath = "";
    this._audioUnavailable = false;
    this.playBtn = null;
    this.playAllBtn = null;
    this.order = [];      
    this.reordered = false;
    this._layout = [];    
    this._drag = null;    
    this._pending = null; 
    this.insertEl = null; 
    this.cutThreshold = 40.0;
    this.segMarker = false;
    this.forceTwoParts = false;
    this.autoExec = false; 
    this.localVideoPath = "";
    this.fps = 24;
    this.videoWidth = 0;   
    this.videoHeight = 0;
    this.exportDir = "./ComfyUI/output/video";
    this.exportAll = false;
    this.build();
    this.render();
    this.attachEvents();
    this._resizeObserver = new ResizeObserver(() => {
      this.node.onResize?.();
      this.node.setDirtyCanvas(true, true);
    });
    setTimeout(() => {
      if (this.root) this._resizeObserver.observe(this.root);
    }, 100);
    this._initCalled = false;
    setTimeout(() => this.init(), 100);
  }


  init() {
    if (this._initCalled) return;
    this._initCalled = true;
    if (this.node.id === -1) { setTimeout(() => this.init(), 300); return; }
    this.loadInitialData();
  }

  getEffectiveNodeId() {
    if (this.node.__nodeId !== undefined && this.node.__nodeId !== -1) return this.node.__nodeId;
    if (this.node.id !== undefined && this.node.id !== -1) return this.node.id;
    if (app.graph && app.graph._nodes) {
      for (const n of app.graph._nodes) {
        if (n === this.node) { this.node.id = n.id; this.node.__nodeId = n.id; return n.id; }
      }
    }
    return -1;
  }

  readState() {
    try { return JSON.parse(this.clipsWidget?.value || "{}"); } catch (_) { return {}; }
  }

  saveState(newState) {
    const nodeId = this.getEffectiveNodeId();
    newState._node_id = nodeId;
    newState.local_video_path = this.localVideoPath;
    newState.force_two_parts = this.forceTwoParts;
    newState.auto_detect_exec = this.autoExec;    
    newState.cut_threshold = this.cutThreshold;
    newState.SegMarker = this.segMarker;
    newState.total_frames = this.totalFrames;
    newState.waveform = this.waveform;
    newState.fps = this.fps;
    newState.video_width = this.videoWidth || 0;  
    newState.video_height = this.videoHeight || 0;
    newState.export_dir = this.exportDir;
    newState.export_all = this.exportAll;
    newState.playhead_frame = this.playheadFrame || 0;
    const trivial = !this.reordered && this.cuts.length === 0 && this.order.length === 1
      && this.order[0].start === 0 && this.order[0].end === this.totalFrames;
    newState.segments = trivial ? [] : this.order;
    newState.reordered = trivial ? false : this.reordered;
    this._suppressLoadOnce = true;
    this.clipsWidget.value = JSON.stringify(newState);
    this.clipsWidget.callback?.(this.clipsWidget.value);
    this.node.setDirtyCanvas?.(true, true);
  }

  
  loadInitialData() {
    if (this._suppressLoadOnce) { this._suppressLoadOnce = false; return; }
    this.state = this.readState();
    this.cuts = this.state.cuts || [];
    if (this.state.local_video_path !== this.localVideoPath) {
      this.stopPlayback(true);
      this._audioUnavailable = false;
      this._lastPreviewFrame = -1;
      this._cancelScheduledPreview();
    }
    this.selections = this.state.selected_indices || [];
    this.localVideoPath = this.state.local_video_path || "";
    this.forceTwoParts = this.state.force_two_parts || false;
    this.autoExec = this.state.auto_detect_exec || false;
    this.cutThreshold = this.state.cut_threshold || 40.0;
    this.segMarker = this.state.SegMarker || false;
    if (this.state.total_frames !== undefined) this.totalFrames = this.state.total_frames;
    if (this.state.waveform) this.waveform = this.state.waveform;
    this.fps = this.state.fps || 24;
    this.videoWidth = this.state.video_width || this.videoWidth || 0;    
    this.videoHeight = this.state.video_height || this.videoHeight || 0; 
    this.exportDir = this.state.export_dir || "./ComfyUI/output/video";
    this.exportAll = this.state.export_all || false;
    if (this.state.playhead_frame !== undefined) this.playheadFrame = this.state.playhead_frame || 0;
    if (Array.isArray(this.state.segments) && this.state.segments.length) {
      this.order = this.state.segments
        .map(s => ({ start: Math.max(0, s.start | 0), end: s.end | 0 }))
        .filter(s => s.end > s.start);
      this.reordered = !!this.state.reordered;
    } else {
      this.rebuildOrderFromCuts();
      this.reordered = false;
    }
    if (this.totalFrames > 0) {
      this.order = this.order
        .map(s => ({ start: s.start, end: Math.min(s.end, this.totalFrames) }))
        .filter(s => s.end > s.start);
    }
    this.root.classList.toggle("marking", this.segMarker);
    this._syncDomFromState();
    this.render();
    this._updateVideoInfoWidget(); 
    if (this.totalFrames > 0) this.updatePreview(this.playheadFrame);
  }


  _syncDomFromState() {
    const q = (s) => this.root.querySelector(s);
    if (q("#esd-segmarker")) q("#esd-segmarker").checked = this.segMarker;
    if (q("#esd-force-two")) q("#esd-force-two").checked = this.forceTwoParts;
    if (q("#esd-auto-exec")) q("#esd-auto-exec").checked = this.autoExec;
    if (q("#esd-export-all")) q("#esd-export-all").checked = this.exportAll;
    if (q("#esd-threshold")) q("#esd-threshold").value = this.cutThreshold;
    if (q("#esd-export-dir")) q("#esd-export-dir").value = this.exportDir;
  }
  
  _updateVideoInfoWidget() {
    const el = this.root?.querySelector("#esd-vinfo-main");
    if (!el) return;
    if (!this.localVideoPath || !this.fps) { el.textContent = "no video"; return; }
    const q = (n) => this.node?.widgets?.find(x => x.name === n);
    const ss = Math.max(1, parseInt(q("subsampling")?.value) || 1);
    const fr = parseInt(q("force_rate")?.value) || 0;
    const outFps = fr > 0 ? fr : this.fps / ss;
    const wh = (this.videoWidth && this.videoHeight) ? ` · ${this.videoWidth}x${this.videoHeight}` : "";
    el.textContent = `${this.fps.toFixed(2)} fps →${outFps.toFixed(2)} fps${ss > 1 ? ` (1/${ss} frames)` : ""}${wh}`
      + ` · Frames: ${this.totalFrames}`
      + ` · Cuts: ${this.cuts.length}`
      + ` · Clips: ${this.getSegments().length}`
      + ` · Zoom: ${this.zoom.toFixed(1)} px/s`;
  }


  build() {
    this.root.className = "esd";
    this.root.innerHTML = `
      <div class="esd-head">
        <button class="esd-btn" data-action="upload">${svgIcon(ICONS.folder)} Import</button>
        <button class="esd-btn" data-action="auto">${svgIcon(ICONS.zap)} Auto Split</button>
        <label class="esd-field"><span>Threshold</span><input type="number" id="esd-threshold" value="${this.cutThreshold}" min="5" max="50" step="0.5"></label>
        <label class="esd-field"><span>Manual</span><input type="checkbox" id="esd-segmarker" ${this.segMarker ? "checked" : ""}></label>
        <label class="esd-field"><span>Force 2</span><input type="checkbox" id="esd-force-two" ${this.forceTwoParts ? "checked" : ""}></label>
        <label class="esd-field" title="Auto scene split on run when timeline has no manual edits"><span>Auto Run</span><input type="checkbox" id="esd-auto-exec" ${this.autoExec ? "checked" : ""}></label>
        <span class="esd-spacer"></span>
        <button class="esd-btn" data-action="refresh-cuts">${svgIcon(ICONS.zap)} Sync Cuts</button>
        <button class="esd-btn danger" data-action="clear">${svgIcon(ICONS.trash)} Clear</button>
      </div>
	  <div class="esd-vinfo">
        <span class="esd-vinfo-main" id="esd-vinfo-main">no video</span>
        <span class="esd-status">Ready</span>
      </div>
      <div class="esd-preview-container">
        <div class="esd-preview-wrap">
          <img id="esd-preview-img" alt="Preview" decoding="async" style="display:none;">
          <div class="esd-preview-bar">
            <div class="esd-transport">
              <button class="esd-btn esd-tbtn" data-action="jump-all-start" title="Timeline start">${svgIcon(ICONS.allStart)}</button>
              <button class="esd-btn esd-tbtn" data-action="jump-clip-start" title="Clip start">${svgIcon(ICONS.segStart)}</button>
              <button class="esd-btn esd-tbtn" id="esd-play-btn" data-action="play-toggle" title="Play/Stop clip">${svgIcon(ICONS.play)}</button>
              <button class="esd-btn esd-tbtn" id="esd-playall-btn" data-action="playall-toggle" title="Play/Stop all clips">${svgIcon(ICONS.playAll)}</button>
              <button class="esd-btn esd-tbtn" data-action="jump-clip-end" title="Clip end">${svgIcon(ICONS.segEnd)}</button>
              <button class="esd-btn esd-tbtn" data-action="jump-all-end" title="Timeline end">${svgIcon(ICONS.allEnd)}</button>
            </div>
            <div class="esd-preview-info" id="esd-preview-time">Frame: 0 / 0</div>
          </div>
        </div>
      </div>
      <div class="esd-timeline-shell">
        <div class="esd-viewport"><div class="esd-stage"></div></div>
      </div>
      <div class="esd-foot" title="Click: select (Ctrl add / Shift range) · Drag clip: reorder · Drag edge: trim (Alt/Ctrl: roll) · Manual mode: click track to add cut · Drag ruler/playhead: scrub · Right-click boundary: merge">
        <button class="esd-btn" data-action="fit">${svgIcon(ICONS.fit)} Fit</button>
        <div class="btn-group">
          <button class="esd-btn" data-action="move-left">${svgIcon(ICONS.chevronLeft)}</button>
          <button class="esd-btn" data-action="move-right">${svgIcon(ICONS.chevronRight)}</button>
        </div>
        <button class="esd-btn" data-action="selectall">${svgIcon(ICONS.checkAll)} Select All</button>
        <span class="esd-spacer"></span>
		<label class="esd-field grow"><span>Out Dir</span><input type="text" id="esd-export-dir" value="${this.exportDir}"></label>
        <label class="esd-field"><span>Export All</span><input type="checkbox" id="esd-export-all" ${this.exportAll ? "checked" : ""}></label>
        <button class="esd-btn primary" data-action="export">${svgIcon(ICONS.save)} Export</button>
      </div>
      <input hidden id="esd-upload" type="file" accept="video/*">
    `;

    this.stage = this.root.querySelector(".esd-stage");
    this.viewport = this.root.querySelector(".esd-viewport");
    this.status = this.root.querySelector(".esd-status");
    this.previewImg = this.root.querySelector("#esd-preview-img");
    this.previewTime = this.root.querySelector("#esd-preview-time");

    this.playheadEl = document.createElement("div");
    this.playheadEl.className = "esd-playhead";
    this.playheadEl.style.display = "none";
    this.stage.appendChild(this.playheadEl);
    this.playheadEl.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      e.preventDefault();
      this.draggingPlayhead = true;
      try { this.playheadEl.setPointerCapture(e.pointerId); } catch (_) {}
    });

    this.dragCutEl = document.createElement("div");
    this.dragCutEl.className = "esd-drag-cut";
    this.dragCutEl.style.display = "none";
    this.stage.appendChild(this.dragCutEl);

    this.root.querySelector('[data-action="upload"]').onclick = () => this.root.querySelector("#esd-upload").click();
    this.root.querySelector('[data-action="auto"]').onclick = () => this.autoSplit();

    this.root.querySelector('[data-action="refresh-cuts"]').onclick = async () => {
      const before = this.cuts.length;
      this.status.textContent = "Syncing cuts...";
      await this._fetchAutoCuts();
      const gained = this.cuts.length - before;
      this.status.textContent = gained > 0
        ? `Synced ${gained} cuts`
        : (before > 0 ? "Cuts up to date" : "No cached cuts yet (enable Auto Run and queue once)");
    };

    this.root.querySelector('[data-action="selectall"]').onclick = () => this.selectAll();
    this.root.querySelector('[data-action="clear"]').onclick = () => {
      this.cuts = [];
      this.rebuildOrderFromCuts();
      this.reordered = false;
      this.selections = [];
      this._selAnchor = null;
      this.updateState();
      this.render();
    };
    this.root.querySelector('[data-action="export"]').onclick = () => this.exportClips();
    this.root.querySelector('[data-action="move-left"]').onclick = () => this.moveSelected(-1);
    this.root.querySelector('[data-action="move-right"]').onclick = () => this.moveSelected(1);
    this.root.querySelector('[data-action="fit"]').onclick = () => this.fitToWidth();

    this.playBtn = this.root.querySelector("#esd-play-btn");
    this.playAllBtn = this.root.querySelector("#esd-playall-btn");
    this.root.querySelector('[data-action="play-toggle"]').onclick = () => this.togglePlay();
    this.root.querySelector('[data-action="playall-toggle"]').onclick = () => this.togglePlayAll();
    this.root.querySelector('[data-action="jump-clip-start"]').onclick = () => this.jumpClipStart();
    this.root.querySelector('[data-action="jump-clip-end"]').onclick = () => this.jumpClipEnd();
    this.root.querySelector('[data-action="jump-all-start"]').onclick = () => this.jumpAllStart();
    this.root.querySelector('[data-action="jump-all-end"]').onclick = () => this.jumpAllEnd();

    this.root.querySelector("#esd-segmarker").onchange = (e) => {
      this.segMarker = e.target.checked;
      this.root.classList.toggle("marking", this.segMarker);
      this.updateState();
    };
    this.root.querySelector("#esd-threshold").onchange = (e) => {
      this.cutThreshold = parseFloat(e.target.value) || 15.0;
    };
    this.root.querySelector("#esd-force-two").onchange = (e) => {
      this.forceTwoParts = e.target.checked;
      this.updateState();
    };
    this.root.querySelector("#esd-auto-exec").onchange = (e) => {
      this.autoExec = e.target.checked;
      this.updateState();
    };
    this.root.querySelector("#esd-export-dir").onchange = (e) => {
      this.exportDir = e.target.value.trim() || "./ComfyUI/output/video";
      this.updateState();
    };
    this.root.querySelector("#esd-export-all").onchange = (e) => {
      this.exportAll = e.target.checked;
      this.updateState();
    };

    this.root.querySelector("#esd-upload").onchange = async (e) => {
      if (!e.target.files?.[0]) return;
      const file = e.target.files[0];
      const formData = new FormData();
      formData.append("video_file", file);
      try {
        this.status.textContent = "Uploading...";
        const resp = await fetch("/element_scene_detection/upload_video", { method: "POST", body: formData });
        const data = await resp.json();
        if (data.file_path) {
          this.stopPlayback(true);
          this._audioUnavailable = false; 
          this.localVideoPath = data.file_path;
          this.totalFrames = data.total_frames || 0;
          this.waveform = data.waveform || [];
          this.fps = data.fps || 24;
          this.videoWidth = data.width || 0;   
          this.videoHeight = data.height || 0; 
          this.playheadFrame = 0;
          this.cuts = [];
          this.selections = [];
          this._selAnchor = null;
          this.order = [{ start: 0, end: this.totalFrames }];
          this.reordered = false;
          this._drag = null;
          this._pending = null;
          this._lastPreviewFrame = -1;
          this._cancelScheduledPreview();
          this._renderSig = "";
          this.dragging = false;
          this.dragCut = null;
          this._updateTransportButtons();
          this._updateVideoInfoWidget(); 
          this.updateState();
          this.status.textContent = "Uploaded";
          this.render();
          if (this.totalFrames > 0) this.updatePreview(0);
        } else {
          this.status.textContent = "Upload failed: " + (data.error || "unknown");
        }
      } catch (err) {
        this.status.textContent = "Upload error: " + err.message;
      }
      e.target.value = "";
    };

    this.stage.addEventListener("pointerdown", e => this.onPointerDown(e));
    this.stage.addEventListener("pointermove", e => this.onPointerMove(e));
    this.stage.addEventListener("pointerup", e => this.onPointerUp(e));
    this.stage.addEventListener("pointercancel", () => this.onPointerLeave());
    this.stage.addEventListener("pointerleave", () => this.onPointerLeave());
    this.stage.addEventListener("contextmenu", e => e.preventDefault());
    this.stage.addEventListener("dragstart", e => e.preventDefault()); 

    this.stage.addEventListener("load", (e) => {
      const img = e.target;
      if (img && img.tagName === "IMG" && img.classList.contains("esd-seg-thumb")) {
        delete img.dataset.loading;
        img.dataset.loaded = "1";
        img.classList.add("loaded");
      }
    }, true);
    this.stage.addEventListener("error", (e) => {
      const img = e.target;
      if (img && img.tagName === "IMG" && img.classList.contains("esd-seg-thumb")) {
        img.classList.remove("loaded");
        delete img.dataset.loaded;
        delete img.dataset.loading;
        const retries = (parseInt(img.dataset.retries) || 0) + 1;
        img.dataset.retries = String(retries);
        if (retries <= 2) this.loadSingleThumbnail(img);
        else img.dataset.failed = "1";
      }
    }, true);

    this._thumbObserver = new IntersectionObserver((entries) => {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          const img = entry.target;
          if (!img.dataset.loaded && !img.dataset.loading && !img.dataset.failed && img.dataset.frame)
            this.loadSingleThumbnail(img);
        }
      });
    }, { root: this.viewport, threshold: 0.1 });

    this.root.classList.toggle("marking", this.segMarker);
  }


  stageX(e) {
    const rect = this.stage.getBoundingClientRect();
    const visual = rect.width || 1;
    const content = this.stage.offsetWidth || visual;
    return (e.clientX - rect.left) / (visual / content);
  }

  rebuildOrderFromCuts() {
    const segs = [];
    let start = 0;
    for (const cut of this.cuts) {
      if (cut > start) segs.push({ start, end: cut });
      start = cut;
    }
    if (start < this.totalFrames) segs.push({ start, end: this.totalFrames });
    this.order = segs;
  }

  syncCutsFromOrder() {
    this.cuts = [...new Set(this.order.slice(1).map(s => s.start))].sort((a, b) => a - b);
  }

  getSegments() {
    if (!this.order || !this.order.length) this.rebuildOrderFromCuts();
    return this.order;
  }

  segmentIndexAt(x) {
    for (let i = 0; i < this._layout.length; i++) {
      const L = this._layout[i];
      if (x >= L.x && x < L.x + L.w) return i;
    }
    return -1;
  }

  boundaryAt(x) {
    const TH = 6, L = this._layout;
    if (!L.length) return null;
    if (Math.abs(x - L[0].x) <= TH) return { leftIdx: null, rightIdx: 0 };
    for (let i = 1; i < L.length; i++) {
      if (Math.abs(x - L[i].x) <= TH) return { leftIdx: i - 1, rightIdx: i };
    }
    const last = L[L.length - 1];
    if (Math.abs(x - (last.x + last.w)) <= TH) return { leftIdx: L.length - 1, rightIdx: null };
    return null;
  }

  frameAtX(x) {
    for (let i = 0; i < this._layout.length; i++) {
      const L = this._layout[i];
      if (x >= L.x && x <= L.x + L.w)
        return Math.round(this.order[i].start + (x - L.x) / this.zoom * this.fps);
    }
    return Math.round(x / this.zoom * this.fps);
  }

  xAtFrame(frame) {
    for (let i = 0; i < this._layout.length; i++) {
      const seg = this.order[i], L = this._layout[i];
      if (frame >= seg.start && frame <= seg.end)
        return L.x + (frame - seg.start) / this.fps * this.zoom;
    }
    return frame / this.fps * this.zoom;
  }

  setSlotGeom(i, x, w) {
    const el = this.stage.querySelector(`.esd-seg[data-segi="${i}"]`);
    if (el) {
      el.style.left = x + "px";
      el.style.width = w + "px";
      const imgs = el.querySelectorAll(".esd-seg-thumb");
      const n = imgs.length || 1;
      imgs.forEach(im => (im.style.width = (w / n) + "px"));
    }
    const wv = this.stage.querySelector(`.esd-wave-seg[data-segi="${i}"]`);
    if (wv) {
      wv.style.left = x + "px";
      wv.style.width = w + "px";
    }
  }

  setCutPos(i, x) {
    const cut = this.stage.querySelector(`.esd-cut[data-cutidx="${i}"]`);
    if (cut) cut.style.left = x + "px";
  }

  setFloatGeom(i, x, w) {
    this._layout[i] = { x, w };
    this.setSlotGeom(i, x, w);
  }

  applyCompactGeom() {
    const fps = this.fps || 24;
    let cx = 0;
    for (let i = 0; i < this.order.length; i++) {
      const s = this.order[i];
      const w = Math.max(4, (s.end - s.start) / fps * this.zoom);
      this._layout[i] = { x: cx, w };
      this.setSlotGeom(i, cx, w);
      if (i > 0) this.setCutPos(i, cx);
      cx += w;
    }
    const containerWidth = this.viewport?.clientWidth || this.root?.clientWidth || 400;
    this.stage.style.width = Math.max(containerWidth, Math.ceil(cx)) + "px";
    this.updatePlayhead();
  }

  maxEndFor(i, preSegs) {
    const si = preSegs[i].start;
    let hi = this.totalFrames;
    for (let j = 0; j < this.order.length; j++) {
      if (j === i) continue;
      if (preSegs[j].end > si && preSegs[j].start < hi) hi = preSegs[j].start;
    }
    return hi;
  }

  minStartFor(i, preSegs) {
    const ei = preSegs[i].end;
    let lo = 0;
    for (let j = 0; j < this.order.length; j++) {
      if (j === i) continue;
      if (preSegs[j].start < ei && preSegs[j].end > lo) lo = preSegs[j].end;
    }
    return lo;
  }

  trimHint(msg) {
    if (this._drag && !this._drag.hinted) { this._drag.hinted = true; this.status.textContent = msg; }
  }

  updatePlayhead() {
    if (!this.playheadEl) return;
    if (this.playheadEl.parentElement !== this.stage) this.stage.appendChild(this.playheadEl);
    if (this.totalFrames > 0 && this.playheadFrame >= 0 && this.playheadFrame <= this.totalFrames) {
      this.playheadEl.style.left = this.xAtFrame(this.playheadFrame) + "px";
      this.playheadEl.style.display = "block";
      this.playheadEl.style.height = ""; 
    } else {
      this.playheadEl.style.display = "none";
    }
  }

  updateDragCut() {
    if (!this.dragCutEl) return;
    if (this.dragging && this.dragCut !== null && this.segMarker) {
      this.dragCutEl.style.left = this.xAtFrame(this.dragCut) + "px";
      this.dragCutEl.style.display = "block";
      this.dragCutEl.style.height = "";
    } else {
      this.dragCutEl.style.display = "none";
    }
  }

  fitToWidth() {
    const containerWidth = this.viewport?.clientWidth || this.root?.clientWidth || 400;
    const duration = this.totalDuration;
    if (duration <= 0) return;
    const newZoom = (containerWidth - 20) / duration;
    this.zoom = Math.min(200, Math.max(0.5, newZoom));
    this.render();
    this._updateVideoInfoWidget();
  }

  /* ===================== 预览（节流 + 取消过期请求） ===================== */
  _previewQuality() { return PREVIEW_SIZE; } 

  previewUrl(frame, size) {
    return `/esd/preview?p=${encodeURIComponent(this.localVideoPath)}&f=${frame}&s=${size}`;
  }

  _schedulePreview(frame) {
    const INTERVAL = 66; // ~15fps，可按手感在 50~100 之间调
    const now = performance.now();
    const since = now - this._lastPreviewAt;
    if (since >= INTERVAL) {
      this._lastPreviewAt = now;
      this.updatePreview(frame);
      return;
    }
    if (this._previewThrottleTimer) return; 
    this._previewThrottleTimer = setTimeout(() => {
      this._previewThrottleTimer = null;
      this._lastPreviewAt = performance.now();
      this.updatePreview(this.playheadFrame);
    }, INTERVAL - since);
  }

  _cancelScheduledPreview() {
    if (this._previewThrottleTimer) { clearTimeout(this._previewThrottleTimer); this._previewThrottleTimer = null; }
  }

  updatePreview(frame, force = false) {
    frame = Math.round(frame);
    if (frame < 0 || frame >= this.totalFrames || !this.localVideoPath) {
      this.previewImg.style.display = 'none';
      this.previewImg.removeAttribute('src');
      this.previewTime.textContent = 'No preview';
      this._lastPreviewFrame = -1;
      return;
    }
    if (!force && frame === this._lastPreviewFrame) return;
    const size = this._previewQuality();
    const seq = ++this._previewSeq;
    const url = this.previewUrl(frame, size);
    if (this._probe) {
      this._probe.onload = null;
      this._probe.onerror = null;
      try { this._probe.src = ""; } catch (_) {}
    }
    const probe = new Image();
    probe.decoding = "async";
    this._probe = probe;
    probe.onload = () => {
      if (seq !== this._previewSeq) return; 
      this.previewImg.src = url;
      this.previewImg.style.display = 'block';
      this._lastPreviewFrame = frame;
      this._updatePreviewTimeText(frame);
    };
    probe.onerror = () => {};
    probe.src = url;
  }

  _canTransport() {
    return !!(this.localVideoPath && this.totalFrames > 0 && this.order && this.order.length);
  }

  _segIndexAtFrame(f) {
    const o = this.getSegments();
    if (!o || !o.length) return -1;
    for (let i = 0; i < o.length; i++) if (f >= o[i].start && f < o[i].end) return i;
    let idx = 0;
    for (let i = 0; i < o.length; i++) if (o[i].start <= f) idx = i;  
    return idx;
  }

  _setPlayhead(f, save = false) {
    f = Math.max(0, Math.min(this.totalFrames - 1, Math.round(f)));
    this.playheadFrame = f; this._playAcc = 0;
    this.updatePlayhead();
    this._updatePreviewTimeText(f);
    this.updatePreview(f);
    if (save) this.updateState();
  }

  _updatePreviewTimeText(frame) {
    if (!this.previewTime) return;
    this.previewTime.textContent = `Frame: ${frame} /${this.totalFrames} (${(frame / this.fps).toFixed(2)}s)`;
  }

  _updateTransportButtons() {
    if (!this.playBtn) return;
    const segPlaying = this._playing && !this._playAllMode;
    const allPlaying = this._playing && this._playAllMode;
    this.playBtn.classList.toggle("playing", segPlaying);
    this.playBtn.innerHTML = svgIcon(segPlaying ? ICONS.stop : ICONS.play);
    if (this.playAllBtn) {
      this.playAllBtn.classList.toggle("playing", allPlaying);
      this.playAllBtn.innerHTML = svgIcon(allPlaying ? ICONS.stop : ICONS.playAll);
    }
  }

  togglePlay() { 
    if (!this._canTransport()) return;
    if (this._playing && !this._playAllMode) { this.stopPlayback(); return; }
    if (this._playing && this._playAllMode) { 
      this._playAllMode = false;
      this._rebasePlayback();
      this.status.textContent = "Playing";
      this._updateTransportButtons();
      return;
    }
    this.startPlayback(false);
  }

  togglePlayAll() { 
    if (!this._canTransport()) return;
    if (this._playing && this._playAllMode) { this.stopPlayback(); return; }
    if (this._playing && !this._playAllMode) { 
      this._playAllMode = true;
      this._rebasePlayback();
      this.status.textContent = "Playing (all)";
      this._updateTransportButtons();
      return;
    }
    this.startPlayback(true);
  }

  startPlayback(playAll = false) {
    const i = this._segIndexAtFrame(this.playheadFrame);
    if (i < 0) return;
    const cur = this.order[i];
    let from = this.playheadFrame;
    if (from >= cur.end - 1) from = cur.start; 
    from = Math.max(cur.start, Math.min(cur.end - 1, from));
    this._playAllMode = !!playAll;
    this._playQueue = [{ start: from, end: cur.end }];
    if (this._playAllMode)
      for (let j = i + 1; j < this.order.length; j++)
        this._playQueue.push({ start: this.order[j].start, end: this.order[j].end });
    this._playing = true;
    this._playAcc = 0;
    this._playLastT = performance.now();
    this._ensureAudio();
    this._syncAudio(from, true);
    const p = this._audioEl?.play?.();
    if (p && p.catch) p.catch(() => {});
    this._updateTransportButtons();
    this.status.textContent = this._playAllMode ? "Playing (all)" : "Playing";
    if (this._playRaf) cancelAnimationFrame(this._playRaf);
    this._playRaf = requestAnimationFrame(this._playTickBound);
  }

  stopPlayback(silent = false) {
    this._playing = false;
    if (this._playRaf) { cancelAnimationFrame(this._playRaf); this._playRaf = 0; }
    this._playQueue = [];
    try { this._audioEl?.pause?.(); } catch (_) {}
    this._updateTransportButtons();
    if (!silent) {
      this.status.textContent = "Stopped";
      this.updatePreview(this.playheadFrame, true);
      this.updateState();
    }
  }


  _playTick(now) {
    this._playRaf = 0;
    if (!this._playing) return;
    const dt = Math.min(0.25, (now - this._playLastT) / 1000); 
    this._playLastT = now;
    this._playAcc += dt * (this.fps || 24);
    const range = this._playQueue[0];
    if (!range) { this.stopPlayback(); return; }
    let f = Math.max(this.playheadFrame, range.start);
    if (this._playAcc >= 1) {
      const adv = Math.floor(this._playAcc);
      this._playAcc -= adv;
      f += adv;
    }
    if (f >= range.end) {
      this._playQueue.shift();
      const nxt = this._playQueue[0];
      if (!nxt) {   
        this.playheadFrame = Math.max(0, Math.min(this.totalFrames - 1, range.end - 1));
        this._playAcc = 0;
        this.updatePlayhead();
        this._updatePreviewTimeText(this.playheadFrame);
        this.stopPlayback();
        return;
      }
      f = nxt.start; this._playAcc = 0; this._syncAudio(f, true); 
    }
    this.playheadFrame = f;
    this.updatePlayhead();
    this._updatePreviewTimeText(f);
    this._schedulePreview(f);   
    this._syncAudio(f, false);  
    this._playRaf = requestAnimationFrame(this._playTickBound);
  }

  _rebasePlayback(seek = true) {   
    if (!this._playing) return;
    const i = this._segIndexAtFrame(this.playheadFrame);
    if (i < 0) { this.stopPlayback(); return; }
    const cur = this.order[i];
    const from = Math.max(cur.start, Math.min(cur.end - 1, this.playheadFrame));
    this._playQueue = [{ start: from, end: cur.end }];
    if (this._playAllMode)
      for (let j = i + 1; j < this.order.length; j++)
        this._playQueue.push({ start: this.order[j].start, end: this.order[j].end });
    this._playAcc = 0;
    this._syncAudio(from, seek);
  }

  jumpClipStart() {
    if (!this._canTransport()) return;
    const i = this._segIndexAtFrame(this.playheadFrame);
    if (i < 0) return;
    const seg = this.order[i];
    if (this.playheadFrame > seg.start) this._setPlayhead(seg.start, true);
    else if (i > 0) this._setPlayhead(this.order[i - 1].start, true);
    this._rebasePlayback();
  }

  jumpClipEnd() {
    if (!this._canTransport()) return;
    const i = this._segIndexAtFrame(this.playheadFrame);
    if (i < 0) return;
    const seg = this.order[i];
    const endF = Math.max(seg.start, seg.end - 1);
    if (this.playheadFrame < endF) this._setPlayhead(endF, true);
    else if (i < this.order.length - 1) {
      const nx = this.order[i + 1];
      this._setPlayhead(Math.max(nx.start, nx.end - 1), true);
    }
    this._rebasePlayback();
  }

  jumpAllStart() {
    if (!this._canTransport()) return;
    this._setPlayhead(this.order[0].start, true);
    this._rebasePlayback();
  }

  jumpAllEnd() {
    if (!this._canTransport()) return;
    const last = this.order[this.order.length - 1];
    this._setPlayhead(Math.max(last.start, last.end - 1), true);
    this._rebasePlayback();
  }

  _ensureAudio() {
    if (this._audioUnavailable) return;
    if (!this._audioEl || this._audioPath !== this.localVideoPath) {
      try { this._audioEl?.pause?.(); } catch (_) {}
      const el = new Audio(`/esd/audio?p=${encodeURIComponent(this.localVideoPath)}`);
      el.preload = "auto";
      el.addEventListener("error", () => { this._audioUnavailable = true; }); 
      el.addEventListener("loadedmetadata", () => {
        if (this._playing) this._syncAudio(this.playheadFrame, true); 
      });
      this._audioEl = el;
      this._audioPath = this.localVideoPath;
    }
  }

  _syncAudio(frame, seek) {
    const el = this._audioEl;
    if (!el || this._audioUnavailable) return;
    const t = frame / (this.fps || 24);
    try {
      if (el.readyState >= 1 && (seek || Math.abs(el.currentTime - t) > 0.15)) {
        const d = el.duration;
        el.currentTime = (d && isFinite(d)) ? Math.min(Math.max(0, t), Math.max(0, d - 0.01)) : t;
      }
    } catch (_) {}
  }

  _destroyPlayback() {
    this._playing = false;
    if (this._playRaf) { cancelAnimationFrame(this._playRaf); this._playRaf = 0; }
    try { this._audioEl?.pause?.(); } catch (_) {}
    this._audioEl = null;
  }

  /* ===================== 指针事件 ===================== */
  updateTrimCursor(e) {
    if (this._drag || this._pending) { this.stage.classList.remove("trim-hover"); return; }
    if (e.target?.closest?.(".esd-ruler")) { this.stage.classList.remove("trim-hover"); return; }
    const hit = this.boundaryAt(this.stageX(e));
    this.stage.classList.toggle("trim-hover", !!hit && !this.segMarker);
  }

  onPointerDown(e) {
    const x = this.stageX(e);
    if (e.button === 2) { this.deleteBoundaryAt(x); return; } 
    if (e.button !== 0) return;
    if (e.target?.closest?.(".esd-ruler")) {
      this.draggingPlayhead = true;
      this._cancelScheduledPreview(); 
      this.playheadFrame = Math.max(0, Math.min(this.totalFrames - 1, this.frameAtX(x)));
      this.updatePlayhead();
      this.updatePreview(this.playheadFrame);
      this._lastPreviewAt = performance.now(); 
      if (this._playing) this._rebasePlayback(); 
      try { this.stage.setPointerCapture(e.pointerId); } catch (_) {}
      return;
    }

    if (this.segMarker) {
      this.dragging = true;
      this.dragCut = Math.max(1, Math.min(this.totalFrames - 1, this.frameAtX(x)));
      this.updateDragCut();
      return;
    }

    const b = this.boundaryAt(x);
    if (b) {
      const roll = e.altKey || e.ctrlKey || e.metaKey;
      let side;
      if (b.leftIdx == null) side = "right";           
      else if (b.rightIdx == null) side = "left";      
      else side = (x < this._layout[b.rightIdx].x) ? "left" : "right";
      this._drag = {
        type: "trim", mode: roll ? "roll" : "side",
        leftIdx: b.leftIdx, rightIdx: b.rightIdx, side, startX: x,
        pre: {
          lay: this._layout.map(o => ({ x: o.x, w: o.w })),
          segs: this.order.map(o => ({ start: o.start, end: o.end }))
        }
      };
      this.stage.classList.add("trimming");
      try { this.stage.setPointerCapture(e.pointerId); } catch (_) {}
      return;
    }

    const idx = this.segmentIndexAt(x);
    if (idx < 0) return;
    this._pending = { idx, x, shift: e.shiftKey, ctrl: e.ctrlKey || e.metaKey };
    try { this.stage.setPointerCapture(e.pointerId); } catch (_) {}
  }

  onPointerMove(e) {
    const x = this.stageX(e);
    if (this.draggingPlayhead) {
      const f = Math.max(0, Math.min(this.totalFrames - 1, this.frameAtX(x)));
      if (f !== this.playheadFrame) {
        this.playheadFrame = f;
        this.updatePlayhead();
        this._schedulePreview(f); 
        if (this._playing) this._rebasePlayback(false); 
      }
      return;
    }
    if (this.dragging && this.segMarker) {
      this.dragCut = Math.max(1, Math.min(this.totalFrames - 1, this.frameAtX(x)));
      this.updateDragCut();
      return;
    }
    if (this._drag?.type === "trim") { this.applyTrimLive(x); return; }
    if (this._drag?.type === "move") { this.updateInsertLine(x); return; }
    if (this._pending) {
      if (Math.abs(x - this._pending.x) > 4) {
        this.beginReorderDrag();
        this.updateInsertLine(x);
      }
      return;
    }
    this.updateTrimCursor(e); 
  }

  onPointerUp(e) {
    this._cancelScheduledPreview(); 
    if (e.button !== 0) return;
    if (this.draggingPlayhead) {
      this.draggingPlayhead = false;
      if (this._playing) this._rebasePlayback(false); 
      this.updatePreview(this.playheadFrame, true);   
      this.updateState();
    } else if (this.dragging && this.segMarker) {
      const frame = this.dragCut;
      const idx = this.order.findIndex(s => frame > s.start && frame < s.end);
      if (idx >= 0) {
        const s = this.order[idx];
        this.order.splice(idx, 1, { start: s.start, end: frame }, { start: frame, end: s.end });
        this.syncCutsFromOrder();
        this.selections = [];
        this._selAnchor = null;
        this.updateState();
      }
      this.dragging = false;
      this.dragCut = null;
      this.updateDragCut();
      this.render();
    } else if (this._drag?.type === "trim") {
      this.commitTrim();
    } else if (this._drag?.type === "move") {
      this.commitReorder();
    } else if (this._pending) {

      const { idx, shift, ctrl } = this._pending;
      if (shift) {
        const anchor = this._selAnchor != null ? this._selAnchor : (this.selections.length ? this.selections[this.selections.length - 1] : 0);
        const a = Math.min(anchor, idx), b = Math.max(anchor, idx);
        this.selections = [];
        for (let i = a; i <= b; i++) this.selections.push(i);
      } else if (ctrl) {
        const pos = this.selections.indexOf(idx);
        if (pos >= 0) this.selections.splice(pos, 1);
        else this.selections.push(idx);
        this._selAnchor = idx;
      } else {
        this.selections = [idx];
        this._selAnchor = idx;
      }
      this.selections.sort((a, b) => a - b);
      this.updateState();
      this.syncSelections();
      this._pending = null;
    }
  }

  onPointerLeave() {
    this._cancelScheduledPreview(); 
    if (this.draggingPlayhead) {
      this.draggingPlayhead = false;
      if (this._playing) this._rebasePlayback(false); 
      this.updatePreview(this.playheadFrame, true);   
      this.updateState();
    }
    if (this.dragging) {
      this.dragging = false;
      this.dragCut = null;
      this.updateDragCut();
    }
    if (this._drag?.type === "trim") {
      this.commitTrim(); 
    } else if (this._drag?.type === "move") {
      if (this.insertEl) { this.insertEl.remove(); this.insertEl = null; }
      this.stage.classList.remove("reordering");
      this._drag = null;
    }
    this._pending = null;
    this.stage?.classList.remove("trim-hover");
  }

  /* ===================== 修剪核心（偏向感知 + 联动两种模式） ===================== */

  applyTrimLive(x) {
    const d = this._drag;
    if (!d || d.type !== "trim") return;
    const fps = this.fps || 24;
    const MIN_F = MIN_SEG_FRAMES;
    const df = Math.round((x - d.startX) / this.zoom * fps); 
    const pre = d.pre;

    if (d.leftIdx == null) {
      const i = d.rightIdx;
      const p = pre.segs[i];
      const lo = this.minStartFor(i, pre.segs), hi = p.end - MIN_F;
      if (lo > hi) { this.trimHint("No trim range"); return; }
      const raw = p.start + df;
      const ns = Math.max(lo, Math.min(hi, raw));
      if (ns === this.order[i].start) return;
      if (raw !== ns) this.trimHint(raw > ns ? "Min clip length reached" : "No earlier source frames");
      this.order[i].start = ns;
      const L = pre.lay[i];
      const dxPx = (ns - p.start) / fps * this.zoom;
      this.setFloatGeom(i, L.x + dxPx, Math.max(4, (p.end - ns) / fps * this.zoom));
      return;
    }

    if (d.rightIdx == null) {
      const i = d.leftIdx;
      const p = pre.segs[i];
      const lo = p.start + MIN_F, hi = this.maxEndFor(i, pre.segs);
      if (lo > hi) { this.trimHint("No trim range"); return; }
      const raw = p.end + df;
      const ne = Math.max(lo, Math.min(hi, raw));
      if (ne === this.order[i].end) return;
      if (raw !== ne) this.trimHint(raw < ne ? "Min clip length reached" : "No later source frames");
      this.order[i].end = ne;
      this.applyCompactGeom();
      return;
    }

    const li = d.leftIdx, ri = d.rightIdx;
    if (d.mode === "roll") {
      const pl = pre.segs[li], pr = pre.segs[ri];
      let lo, hi;
      if (pl.end === pr.start) { lo = pl.start + MIN_F; hi = pr.end - MIN_F; }   
      else { lo = Math.max(pl.start, pr.start) + MIN_F; hi = Math.min(pl.end, pr.end) - MIN_F; } 
      if (lo > hi) { this.trimHint("No trim range on this boundary"); return; }
      const frame = Math.max(lo, Math.min(hi, pl.end + df));
      if (frame === this.order[li].end && frame === this.order[ri].start) return;
      this.order[li].end = frame;
      this.order[ri].start = frame;
      this.applyCompactGeom();
      return;
    }

    if (d.side === "left") {
      const p = pre.segs[li];
      const lo = p.start + MIN_F, hi = this.maxEndFor(li, pre.segs);
      if (lo > hi) { this.trimHint("No trim range"); return; }
      const raw = p.end + df;
      const ne = Math.max(lo, Math.min(hi, raw));
      if (ne === this.order[li].end) return;
      if (raw !== ne) this.trimHint(raw < ne ? "Min clip length reached" : "Blocked by next clip (Alt/Ctrl+drag to roll)");
      this.order[li].end = ne;
      this.applyCompactGeom();
      return;
    }

    const p = pre.segs[ri];
    const lo = this.minStartFor(ri, pre.segs), hi = p.end - MIN_F;
    if (lo > hi) { this.trimHint("No trim range"); return; }
    const raw = p.start + df;
    const ns = Math.max(lo, Math.min(hi, raw));
    if (ns === this.order[ri].start) return;
    if (raw !== ns) this.trimHint(raw > ns ? "Min clip length reached" : "Blocked by prev clip (Alt/Ctrl+drag to roll)");
    this.order[ri].start = ns;
    const L = pre.lay[ri];
    const dxPx = (ns - p.start) / fps * this.zoom;
    this.setFloatGeom(ri, L.x + dxPx, Math.max(4, (p.end - ns) / fps * this.zoom));
  }

  commitTrim() {
    const d = this._drag;
    this._drag = null;
    this.stage.classList.remove("trimming");
    const changed = !!(d && JSON.stringify(d.pre.segs) !== JSON.stringify(this.order.map(o => ({ start: o.start, end: o.end }))));
    this.reordered = true; 
    this.syncCutsFromOrder();
    this.updateState();
    this.render(); 
    if (changed) this.status.textContent = "Trim applied";
  }

  deleteBoundaryAt(x) { 
    const hit = this.boundaryAt(x);
    if (!hit || hit.leftIdx == null || hit.rightIdx == null) return;
    const l = this.order[hit.leftIdx], r = this.order[hit.rightIdx];
    if (l.end !== r.start) {
      this.status.textContent = "Clips not adjacent, cannot merge";
      return;
    }
    l.end = r.end;
    this.order.splice(hit.rightIdx, 1);
    this.selections = [];
    this._selAnchor = null;
    this.syncCutsFromOrder();
    this.updateState();
    this.render();
  }


  /* ===================== 拖拽排序 ===================== */
  beginReorderDrag() {
    const idx = this._pending.idx;
    if (!this.selections.includes(idx)) {
      this.selections = [idx];
      this._selAnchor = idx;
      this.syncSelections();
    }
    this._drag = { type: "move", k: idx };
    if (!this.insertEl) {
      this.insertEl = document.createElement("div");
      this.insertEl.className = "esd-insert-line";
      this.stage.appendChild(this.insertEl);
    }
    this.insertEl.style.display = "block";
    this.stage.classList.add("reordering");
  }

  updateInsertLine(x) {
    const L = this._layout;
    if (!L.length || !this.insertEl) return;
    let k = L.length;
    for (let i = 0; i < L.length; i++) {
      if (x < L[i].x + L[i].w / 2) { k = i; break; }
    }
    this._drag.k = k;
    const edgeX = k < L.length ? L[k].x : L[L.length - 1].x + L[L.length - 1].w;
    this.insertEl.style.left = edgeX + "px";
  }

  commitReorder() {
    const k = this._drag.k;
    const sel = [...this.selections].sort((a, b) => a - b);
    const moved = sel.map(i => this.order[i]);
    const rest = this.order.filter((_, i) => !this.selections.includes(i));
    const pos = Math.max(0, Math.min(rest.length, k - sel.filter(i => i < k).length));
    rest.splice(pos, 0, ...moved);
    this.order = rest;
    this.reordered = true;
    this.selections = moved.map((_, j) => pos + j).sort((a, b) => a - b);
    this._selAnchor = null;
    if (this.insertEl) { this.insertEl.remove(); this.insertEl = null; }
    this.stage.classList.remove("reordering");
    this._drag = null;
    this._pending = null;
    this.syncCutsFromOrder();
    this.updateState();
    this.render();
  }

  get totalDuration() {
    if (!this.fps) return 0;
    const segs = this.getSegments();
    if (!segs.length) return this.totalFrames ? this.totalFrames / this.fps : 0;
    return segs.reduce((a, s) => a + (s.end - s.start), 0) / this.fps; 
  }

  computeRenderSig() {
    return JSON.stringify([
      this.zoom, this.totalFrames, this.fps,
      this.order, this.reordered ? 1 : 0,
      this.waveform ? this.waveform.length : 0,
      this.localVideoPath, this.segMarker ? 1 : 0
    ]);
  }

  syncSelections() {
    if (!this.stage) return;
    this.stage.querySelectorAll(".esd-seg").forEach((el, i) => el.classList.toggle("selected", this.selections.includes(i)));
    this.stage.querySelectorAll(".esd-wave-seg").forEach((el, i) => el.classList.toggle("selected", this.selections.includes(i)));
  }

  render() {
    if (this._playing) this.stopPlayback(true); 
    const sig = this.computeRenderSig();
    if (sig === this._renderSig) {
      this.syncSelections();
      this.updatePlayhead();
      this.updateDragCut();
      return;
    }
    this._renderSig = sig;
    const containerWidth = this.viewport?.clientWidth || this.root?.clientWidth || 400;
    const duration = this.totalDuration;
    const width = Math.max(containerWidth, Math.ceil(duration * this.zoom));
    this.stage.style.width = width + "px";
    const rulerDuration = width / this.zoom;
    let html = '<div class="esd-ruler">';
    const tickStep = this.zoom >= 100 ? 0.5 : this.zoom >= 48 ? 1 : 2;
    for (let t = 0; t <= rulerDuration; t += tickStep) {
      const major = Math.abs(t - Math.round(t)) < 0.001;
      html += `<i class="esd-tick ${major ? "major" : ""}" style="left:${t * this.zoom}px">${major ? `<span>${t.toFixed(0)}s</span>` : ""}</i>`;
    }
    html += '</div><div class="esd-track">';
    const segs = this.getSegments();
    this._layout = [];
    let cx = 0;
    for (let i = 0; i < segs.length; i++) {
      const w = Math.max(4, (segs[i].end - segs[i].start) / this.fps * this.zoom);
      this._layout.push({ x: cx, w });
      cx += w;
    }
    for (let i = 0; i < segs.length; i++) {
      const seg = segs[i], L = this._layout[i];
      const sel = this.selections.includes(i);
      const numThumbs = Math.min(8, Math.max(1, Math.floor(L.w / 30)));
      const denom = Math.max(1, numThumbs - 1);
      let thumbsHtml = "";
      for (let j = 0; j < numThumbs; j++) {
        let frame = Math.round(seg.start + (seg.end - seg.start) * (j / denom));
        if (j === numThumbs - 1) frame = seg.end - 1;
        frame = Math.max(seg.start, Math.min(seg.end - 1, frame));
        thumbsHtml += `<img class="esd-seg-thumb" draggable="false" decoding="async" data-frame="${frame}" style="width:${L.w / numThumbs}px;">`;
      }
      html += `<div class="esd-seg ${sel ? "selected" : ""}" data-segi="${i}" style="left:${L.x}px;width:${L.w}px" title="Source ${seg.start}–${seg.end} frames (${(seg.start / this.fps).toFixed(2)}s–${(seg.end / this.fps).toFixed(2)}s)"><div class="esd-seg-thumbs">${thumbsHtml}</div><span class="esd-seg-label">${i + 1}</span></div>`;
    }
    for (let i = 1; i < segs.length; i++) {
      html += `<div class="esd-cut" data-cutidx="${i}" style="left:${this._layout[i].x}px"></div>`;
    }
    html += '</div>';
    html += `<div class="esd-track audio" style="width: ${width}px;">`;
    if (this.waveform && this.waveform.length > 0) {
      for (let i = 0; i < segs.length; i++) {
        const L = this._layout[i];
        const sel = this.selections.includes(i);
        html += `<div class="esd-wave-seg ${sel ? "selected" : ""}" data-segi="${i}" style="left:${L.x}px;width:${L.w}px"><canvas class="esd-wave" data-wave data-segi="${i}"></canvas><span class="esd-seg-label">${i + 1}</span></div>`;
      }
    } else {
      html += `<div class="esd-audio-placeholder">${svgIcon(ICONS.music, 12)} no audio</div>`;
    }
    html += '</div>';

    this.stage.innerHTML = html;
    this.stage.appendChild(this.playheadEl);
    this.stage.appendChild(this.dragCutEl);

    if (this.waveform && this.waveform.length > 0) {
      this.stage.querySelectorAll(".esd-wave").forEach(cv => {
        const i = parseInt(cv.dataset.segi);
        if (this.order[i] && this._layout[i]) this.drawWaveSlice(cv, this.order[i], this._layout[i]);
      });
    }
    this._updateVideoInfoWidget();
    this.setupThumbnailObservers();
    this.updatePlayhead();
    this.updateDragCut();
    setTimeout(() => {
      this.node.onResize?.();
      this.node.setDirtyCanvas(true, true);
    }, 50);
  }


  drawWaveSlice(canvas, seg, L) {
    const dpr = window.devicePixelRatio || 1;
    const cw = Math.max(1, Math.round(L.w)), ch = 35;
    canvas.width = Math.round(cw * dpr);
    canvas.height = Math.round(ch * dpr);
    canvas.style.width = cw + "px";
    canvas.style.height = ch + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, cw, ch);
    const data = this.waveform, len = data.length;
    const total = Math.max(1, this.totalFrames);
    const a = Math.max(0, Math.min(len - 1, Math.floor(seg.start / total * len)));
    const b = Math.max(a + 1, Math.min(len, Math.ceil(seg.end / total * len)));
    const step = cw / (b - a), yCenter = ch / 2, maxAmp = yCenter - 2;
    ctx.beginPath();
    for (let i = a; i < b; i++) {
      const x = (i - a) * step, amp = data[i] || 0;
      if (i === a) ctx.moveTo(x, yCenter - amp * maxAmp);
      else ctx.lineTo(x, yCenter - amp * maxAmp);
    }
    for (let i = b - 1; i >= a; i--) {
      const x = (i - a) * step, amp = data[i] || 0;
      ctx.lineTo(x, yCenter + amp * maxAmp);
    }
    ctx.closePath();
    ctx.fillStyle = "rgba(90, 173, 90, 0.4)";
    ctx.fill();
    ctx.strokeStyle = "#5aad5a";
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  setupThumbnailObservers() {
    if (this._thumbObserver) this._thumbObserver.disconnect();
    this.stage.querySelectorAll(".esd-seg-thumb").forEach(img => this._thumbObserver.observe(img));
  }

  /* 缩略图：直接指向 GET URL，交给浏览器加载与缓存 */
  loadSingleThumbnail(img) {
    if (img.dataset.loaded || img.dataset.loading || img.dataset.failed) return;
    const frame = parseInt(img.dataset.frame);
    if (isNaN(frame) || !this.localVideoPath) { img.dataset.failed = "1"; return; }
    img.dataset.loading = "1";
    img.src = `/esd/preview?p=${encodeURIComponent(this.localVideoPath)}&f=${frame}&s=64`;
  }

  updateState() {
    this.saveState({
      cuts: this.cuts,
      selected_indices: this.selections,
      total_frames: this.totalFrames,
      waveform: this.waveform,
      fps: this.fps,
      force_two_parts: this.forceTwoParts,
      auto_detect_exec: this.autoExec,
      cut_threshold: this.cutThreshold,
      SegMarker: this.segMarker,
      export_dir: this.exportDir,
      export_all: this.exportAll,
      segments: this.order,
      reordered: this.reordered,
    });
  }

  selectAll() {
    const segs = this.getSegments();
    this.selections = (this.selections.length === segs.length && segs.length > 0) ? [] : segs.map((_, i) => i);
    this._selAnchor = null;
    this.updateState();
    this.syncSelections();
  }

  moveSelected(direction) {
    if (!this.selections.length) return;
    const order = this.getSegments();
    const sel = [...this.selections].sort((a, b) => a - b);
    const selRefs = sel.map(i => order[i]); 
    const n = order.length;
    if (direction < 0) {
      for (const i of sel) {
        const j = i - 1;
        if (j < 0 || sel.includes(j)) continue;
        [order[i], order[j]] = [order[j], order[i]];
      }
    } else {
      for (let m = sel.length - 1; m >= 0; m--) {
        const i = sel[m], j = i + 1;
        if (j >= n || sel.includes(j)) continue;
        [order[i], order[j]] = [order[j], order[i]];
      }
    }
    this.selections = selRefs.map(ref => order.indexOf(ref)).filter(i => i >= 0).sort((a, b) => a - b);
    this._selAnchor = null;
    this.reordered = true;
    this.syncCutsFromOrder();
    this.updateState();
    this.render();
  }

  async autoSplit() {
    const nodeId = this.getEffectiveNodeId();
    if (nodeId === -1 || !this.localVideoPath) return;
    this.status.textContent = "Detecting...";
    try {
      const resp = await fetch("/element_scene_detection/detect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: nodeId, video_path: this.localVideoPath, threshold: this.cutThreshold })
      });
      const data = await resp.json();
      if (data.cuts) {
        this.cuts = data.cuts;
        this.rebuildOrderFromCuts();
        this.reordered = false;
        this.selections = [];
        this._selAnchor = null;
        this.updateState();
        this.render();
        this.status.textContent = `Detected ${data.cuts.length} cuts`;
      }
    } catch (err) {
      console.error(err);
      this.status.textContent = "Detect failed";
    }
  }

  async exportClips() {
    if (!this.localVideoPath) return;
    const data = {
      node_id: this.getEffectiveNodeId(),
      video_path: this.localVideoPath,
      cuts: this.cuts,
      segments: this.getSegments().map(s => ({ start: s.start, end: s.end })),
      total_frames: this.totalFrames,
      fps: this.fps,
      export_all: this.exportAll,
      selected_indices: this.selections,
      output_dir: this.exportDir,
    };
    try {
      this.status.textContent = "Exporting...";
      const resp = await fetch("/element_scene_detection/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(data)
      });
      const result = await resp.json();
      this.status.textContent = result.exported
        ? `Exported ${result.exported.length} file(s)`
        : "Export failed";
    } catch (err) {
      this.status.textContent = "Export error";
    }
  }

  _applyAutoCuts(cuts, source) {
    if (!Array.isArray(cuts) || !cuts.length) return;
    const isWholeClip = this.order.length === 1 && this.order[0].start === 0 && this.order[0].end === this.totalFrames;
    const noManualEdits = !this.reordered && (this.cuts?.length || 0) === 0;
    if (!(isWholeClip && noManualEdits)) {
      console.log("[ESD] received cuts but timeline already has manual edits, skip", source);
      return;
    }
    this.cuts = cuts;
    this.rebuildOrderFromCuts();
    this.reordered = false;
    this.selections = [];
    this._selAnchor = null;
    this.updateState();
    this.render();
    this.status.textContent = `Auto-detected ${cuts.length} cuts`;
    console.log(`[ESD] auto cuts applied (${source}): ${cuts.length}`);
  }


  async _fetchAutoCuts() {
    const myId = this.getEffectiveNodeId();
    if (myId === -1) return;
    try {
      const data = await fetch(`/esd/auto_cuts?node_id=${myId}`).then(r => r.json());
      // console.log("[ESD] fetch cuts myId=", myId, "resp=", data); 
      if (data && Array.isArray(data.cuts)) this._applyAutoCuts(data.cuts, "http");
    } catch (err) {
      console.warn("[ESD] auto cuts fetch failed:", err);
    }
  }

  attachEvents() {
    const origCallback = this.clipsWidget?.callback;
    if (this.clipsWidget) {
      this.clipsWidget.callback = (v) => {
        origCallback?.call(this.clipsWidget, v);
        this.loadInitialData();
      };
    }
    this._onAutoCuts = ({ detail }) => {
      try {
        if (!detail) return;
        const payload = detail.data ? detail.data : detail;
        if (!payload || !Array.isArray(payload.cuts)) return;
        const myId = this.getEffectiveNodeId();
        if (myId !== -1 && parseInt(payload.node_id) !== myId) return;
        this._applyAutoCuts(payload.cuts, "ws");
      } catch (err) {
        console.error("[ESD] auto-cuts ws handler error:", err);
      }
    };
    app.api?.addEventListener?.("esd_auto_cuts", this._onAutoCuts);

    this._onExecuted = ({ detail }) => {
      if (!detail) return;
      if (parseInt(detail.node) !== this.getEffectiveNodeId()) return;
      this._fetchAutoCuts();
    };
    app.api?.addEventListener?.("executed", this._onExecuted);

    this._queueWasBusy = false;
    this._onStatus = ({ detail }) => {
      try {
        const qr = Number(detail?.exec_info?.queue_remaining ?? 0);
        if (qr > 0) { this._queueWasBusy = true; return; } 
        if (!this._queueWasBusy) return;                   
        this._queueWasBusy = false;                        
        [200, 600, 1500].forEach(delay => setTimeout(() => this._fetchAutoCuts(), delay));
      } catch (err) { /* 静默 */ }
    };
    app.api?.addEventListener?.("status", this._onStatus);
  }
}

app.registerExtension({
  name: "Element.SceneDetection",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "ElementSceneDetection") return;
    installStyles();

    const BODY_PAD = 8; // ★ 0 → 4 → 8 → 12 
    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function() {
      const result = origCreated?.apply(this, arguments);
      this.__nodeId = this.id;

      const hideWidget = (w) => {
        if (!w) return;
        w.hidden = true;
        if (!w.options) w.options = {};
        w.options.hidden = true;
        if (w.computeSize) w.computeSize = () => [0, -4];
        w.draw = function () {};
        const el = w.element || w.inputEl;
        if (el) {
          el.style.display = "none";
          if (el.parentElement) el.parentElement.style.display = "none";
        }
      };
      hideWidget(this.widgets?.find(w => w.name === "clips_data"));

      const root = document.createElement("div");
      const domWidget = this.addDOMWidget("scene_detection_ui", "div", root,
                                          { serialize: false, hideOnZoom: false });
      const clipsWidget = this.widgets?.find(w => w.name === "clips_data");
      this.__esd = new SceneDetectionUI(this, root, clipsWidget);

      const FALLBACK_H = 595;
      let panelH = FALLBACK_H;
      const measureNatural = () => {
        const p = root.firstElementChild;
        if (!p || !root.isConnected) return 0;
        const prev = p.style.height;
        p.style.height = "auto";                 
        const h = Math.ceil(p.offsetHeight);     
        p.style.height = prev;
        return h > 100 ? h : 0;
      };
      panelH = measureNatural() || FALLBACK_H;

      domWidget.computeSize = (w) =>
        [Math.max(100, (this.size?.[0] || w || 860) - 20), panelH];

      this.size = [Math.max(this.size?.[0] || 0, 860), this.computeSize()[1] - BODY_PAD];
	  
      const lockHeight = () => { this.size[1] = this.computeSize()[1] - BODY_PAD; };
      this.resizable = true;
      this.onResize = () => lockHeight();


      requestAnimationFrame(() => {
        const h = measureNatural();
        if (h && Math.abs(h - panelH) > 2) {
          panelH = h;
          this.size[1] = this.computeSize()[1] - BODY_PAD;
          this.setDirtyCanvas?.(true, true);
        }
      });

      for (const nm of ["force_rate", "subsampling"]) {
        const w2 = this.widgets?.find(x => x.name === nm);
        if (w2) {
          const oc = w2.callback;
          w2.callback = (v) => { oc?.call(w2, v); this.__esd?._updateVideoInfoWidget?.(); };
        }
      }

      return result;
    };

    const origConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function() {
      const r = origConfigure?.apply(this, arguments);
      this.__nodeId = this.id;
      const h = this.computeSize()[1] - BODY_PAD;
      if (Math.abs((this.size?.[1] || 0) - h) > 2) this.size[1] = h;
      if (this.__esd) this.__esd.loadInitialData();
      return r;
    };

    const origRemoved = nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved = function() {
      if (this.__esd) {
        if (this.__esd._resizeObserver) this.__esd._resizeObserver.disconnect();
        if (this.__esd._thumbObserver) this.__esd._thumbObserver.disconnect();
        if (this.__esd._previewThrottleTimer) clearTimeout(this.__esd._previewThrottleTimer);
        if (this.__esd._destroyPlayback) this.__esd._destroyPlayback();
        if (this.__esd._onAutoCuts) app.api?.removeEventListener?.("esd_auto_cuts", this.__esd._onAutoCuts);
        if (this.__esd._onExecuted) app.api?.removeEventListener?.("executed", this.__esd._onExecuted);
        if (this.__esd._onStatus) app.api?.removeEventListener?.("status", this.__esd._onStatus);
        this.__esd = null;
      }
      return origRemoved?.apply(this, arguments);
    };
  }
});
