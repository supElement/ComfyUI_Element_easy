/*
# 原始代码来自 TWanSigmaGraph (https://github.com/Temult/TWanSigmaGraph)
# 原作者: Temult
# 许可证: MIT License
# 
# 修改说明:
# - 修复了曲线调整无效的问题
# - 【新增】加入 WebSocket 监听功能，当连接外部输入时自动更新UI界面
#
# 修改者: [supElement]
# 修改日期: 2026-02-28
——*/

import { app } from "/../scripts/app.js";
import { $el } from "/../scripts/ui.js";
import { api } from "/../scripts/api.js";

/*—— Constants ——*/
const NODE_CLASS      = "Element_SigmaGraph";
const GRAPH_DATA_NAME = "graph_data";
const STEPS_NAME      = "steps";
const CANVAS_TYPE     = "SIGMA_GRAPH_CANVAS";
const MIN_POINTS      = 3;
const NUM_SLOTS       = 8;
const LS_KEY          = "sigma_graph_saveSlots";
const UNDO_LIMIT      = 1;
const MIN_NODE_WIDTH  = 200;
const GRAB_THRESHOLD  = 0.08;
const POINT_RADIUS    = 4;
const POINT_COLOR     = "#1E88E5";

function calcSigmas(pts, steps) {
  steps = Math.max(1, steps | 0);
  const p = (pts ||[]).slice().sort((a, b) => a.x - b.x);
  
  if (p.length < 2) return Array(steps + 1).fill(1.0);

  if (!p.some((pt) => Math.abs(pt.x) < 1e-6))
    p.unshift({ x: 0, y: p[0].y });
  if (!p.some((pt) => Math.abs(pt.x - 1) < 1e-6))
    p.push({ x: 1, y: p[p.length - 1].y });

  const out =[];
  let idx = 0;
  
  for (let i = 0; i < steps + 1; i++) {
    const t = i / steps;
    while (idx < p.length - 2 && p[idx + 1].x < t) idx++;
    const [p1, p2] = [p[idx], p[idx + 1]];
    const dx = p2.x - p1.x;
    let y = dx < 1e-6
      ? (Math.abs(t - p2.x) < Math.abs(t - p1.x) ? p2.y : p1.y)
      : p1.y + ((t - p1.x) / dx) * (p2.y - p1.y);
	
    out.push(Math.max(0.0, Math.round(y * 100000) / 100000)); 
  }
  return out;
}

function strToPts(str) {
  try {
    const arr = JSON.parse(str);
    if (
      Array.isArray(arr) &&
      arr.every((o) => typeof o.x === "number" && typeof o.y === "number")
    ) return arr;
  } catch { /* ignore */ }

  const nums = str
    .split(/[^0-9.+-]+/)
    .map(parseFloat)
    .filter((n) => !isNaN(n));
  if (nums.length < 2) {
    const y = nums[0] || 1;
    return [{ x: 0, y }, { x: 1, y: nums[0] != null ? y : 0 }];
  }
  return nums.map((y, i) => ({ x: i / (nums.length - 1), y: Math.round(y * 100000) / 100000 }));
}

function setup(node) {
  if (node._sigmaSetupDone) return;
  node._sigmaSetupDone = true;
  
  const DEFAULT_SIZE = [240, 280];
  
  if (node.size[0] < 200 || node.size[1] < 150) {
    node.size = [...DEFAULT_SIZE];
  }

  const gw = node.widgets.find((w) => w.name === GRAPH_DATA_NAME);
  if (!gw || !gw.element) return;
  const ta = gw.element;

  ta.style.minHeight = "10px";
  ta.style.boxSizing = "border-box";
  ta.style.resize = "vertical";

  let initialPts = null;
  if (gw.value && gw.value.trim() !== "") {
    try {
      initialPts = strToPts(gw.value);
    } catch {
      initialPts = null;
    }
  }

  if (!initialPts || initialPts.length === 0) {
    initialPts = [{x: 0, y: 1}, {x: 0.5, y: 0.5}, {x: 1, y: 0}];
    const defaultJson = JSON.stringify(initialPts);
    ta.value = defaultJson;
    gw.value = defaultJson;
  } else {
    ta.value = JSON.stringify(initialPts);
  }


  const wrap = $el("div", {
    style: {
      width: "100%", position: "relative", display: "flex",
      flexDirection: "column", flexGrow: "1", minHeight: "180px",
      paddingBottom: "20px" //, minWidth: `${MIN_NODE_WIDTH}px`
    }
  });
  const canvas = $el("canvas", {
    style: {
      width: "100%", flexGrow: "1", minHeight: "125px",
      background: "#282828", border: "1px solid #555",
      borderRadius: "4px", cursor: "crosshair"
    }
  });
  wrap.appendChild(canvas);

  const preview = $el("textarea", {
    placeholder: "Sigmas preview…",
    readOnly: true,
    style: {
      width: "100%", height: '55px', fontFamily: "monospace",
      background: "#181818", color: "#ccc",
      border: "1px solid #555", borderRadius: "4px",
      boxSizing: "border-box", padding: "4px", resize: "none",
      marginTop: "4px"
    }
  });
  wrap.appendChild(preview);

  node.addDOMWidget(CANVAS_TYPE, "custom", wrap, {
    getHeight: () => Math.max(180, wrap.scrollHeight)
  });

  if (node.size[0] < MIN_NODE_WIDTH) {
    node.setSize([MIN_NODE_WIDTH, node.size[1]]);
  }
  const prevOnResize = node.onResize;
  node.onResize = function() {
    prevOnResize?.apply(this, arguments);
    if (this.size[0] < MIN_NODE_WIDTH) {
      this.setSize([MIN_NODE_WIDTH, this.size[1]]);
    }
  };

  const addBtn = $el("button", {
    textContent: "+", title: "Double density",
    style: { position: "absolute", top: "4px", right: "32px", width: "24px", height: "24px", borderRadius: "50%", border: "1px solid #555", background: "#505050", color: "#fff", cursor: "pointer" } //1e85e5
  });
  const delBtn = $el("button", {
    textContent: "−", title: "Halve density",
    style: { position: "absolute", top: "4px", right: "4px", width: "24px", height: "24px", borderRadius: "50%", border: "1px solid #555", background: "#353535", color: "#fff", cursor: "pointer" }  //ff6666
  });
  wrap.appendChild(addBtn);
  wrap.appendChild(delBtn);

  const slotBar = $el("div", {
    style: { display: "flex", gap: "4px", marginTop: "4px", alignItems: "center" }
  });
  wrap.appendChild(slotBar);
 
  // 改为读取 JSON 文件
  let slotsData =[]; 
  let recordMode = false;
  
  const recBtn = $el("button", { 
    textContent: "💾", 
    title: "Toggle save mode", 
    style: { 
      minWidth: "24px", 
      height: "24px", 
      cursor: "pointer", 
      display: "flex", 
      alignItems: "center", 
      justifyContent: "center", 
      padding: "0",
      lineHeight: "1",
      background: "none",  
      color: "#fff", 
      border: "none", 
      borderRadius: "5px", 
      fontSize: "20px" 
    } 
  });
  
  slotBar.appendChild(recBtn);

  const slotBtns =[];
  
  for (let i = 0; i < NUM_SLOTS; i++) {
    const b = $el("button", {
      textContent: `${i + 1}`,
      disabled: true, 
      style: { 
        flex: "1", 
        minWidth: "16px", 
        height: "24px",
        opacity: "0.3", 
        cursor: "not-allowed", 
        display: "flex", 
        alignItems: "center", 
        justifyContent: "center", 
        padding: "0", 
        fontSize: "14px",
        background: "#888",
        color: "#fff",
        border: "none",
        borderRadius: "5px"
      }
    });
    slotBar.appendChild(b);
    slotBtns.push(b);

    b.onclick = async () => {
      if (recordMode) {
        slotsData[i] = gw.value;
        b.style.opacity = "0.5"; 
        try {
            await fetch('/element_easy/sigma_presets', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(slotsData)
            });
        } catch (e) {
            console.error("[Element_SigmaGraph] 保存预设失败", e);
        }
        recBtn.click(); // 自动退出录制模式
      } else if (slotsData[i]) {
        let pts;
        try { pts = JSON.parse(slotsData[i]); }
        catch { pts = strToPts(slotsData[i]); }
        applyPoints(pts);
      }
    };
  }
  
  function updateSlotUI() {
    slotBtns.forEach((b, i) => {
      const hasData = slotsData[i];
      const ok = hasData || recordMode;
      
      b.disabled = !ok;
      
      if (recordMode && hasData) {
        // 录制模式 + 有预设：蓝色高亮
        b.style.opacity = "1";
        b.style.cursor = "pointer";
        b.style.background = "#1E88E5";

      } else {
        b.style.opacity = ok ? "1" : "0.3";
        b.style.cursor = ok ? "pointer" : "not-allowed";
        b.style.background = "#888";  

      }
    });
  }
   
  recBtn.onclick = () => {
    recordMode = !recordMode;
    if (recordMode) {
      recBtn.style.background = "#ff4444";  // 红色表示录制中
      recBtn.style.border = "1px solid #ff4444";
    } else {
      recBtn.style.background = "none";  // 恢复默认
      recBtn.style.border = "none";
    }
    updateSlotUI();
  };

  async function loadPresetsFromFile() {
    try {
        const response = await fetch('/element_easy/sigma_presets');
        if (response.ok) {
            const data = await response.json();
            if (Array.isArray(data)) {
                slotsData = data;
                updateSlotUI(); // 获得数据后，刷新按钮高亮状态
            }
        }
    } catch (e) {
        console.error("[Element_SigmaGraph] 读取预设文件失败", e);
    }
  }
  
  // 节点创建时立刻加载
  loadPresetsFromFile();

  let undoStack =[];
  function pushUndo(state) {
    undoStack.unshift(state);
    if (undoStack.length > UNDO_LIMIT) undoStack.pop();
  }

  function applyPoints(pts) {
    pushUndo(gw.value);
    const clean = pts.map((p) => ({
      x: Math.round(p.x * 100000) / 100000,  
      y: Math.round(p.y * 100000) / 100000   
    }));
    const jsonStr = JSON.stringify(clean);
    gw.value = jsonStr;
    ta.value = jsonStr;
    draw(clean);
  }

  node._applyPoints = applyPoints;
  node._updateSteps = (newSteps) => {
    const sw = node.widgets.find((w) => w.name === STEPS_NAME);
    if (sw) sw.value = newSteps;
  };

  const ctx = canvas.getContext("2d");
  function draw(overridePts) {
    const pts = overridePts || strToPts(gw.value);
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    ctx.strokeStyle = "#444";
    ctx.lineWidth = 0.5;
    ctx.beginPath();
    for (let i = 1; i < 10; i++) {
      const x = (i * w) / 10, y = (i * h) / 10;
      ctx.moveTo(x, 0); ctx.lineTo(x, h);
      ctx.moveTo(0, y); ctx.lineTo(w, y);
    }
    ctx.stroke();

    if (pts.length >= 2) {
      ctx.strokeStyle = "#fff";
      ctx.lineWidth = 1.0; //曲线宽度
      ctx.beginPath();
      pts.forEach((p, i) => {
        const px = p.x * w, py = (1 - p.y) * h;
        i ? ctx.lineTo(px, py) : ctx.moveTo(px, py);
      });
      ctx.stroke();

      pts.forEach((p) => {
        const px = p.x * w, py = (1 - p.y) * h;
        ctx.fillStyle = POINT_COLOR;
        ctx.beginPath();
        ctx.arc(px, py, POINT_RADIUS, 0, 2 * Math.PI);
        ctx.fill();
      });
    }

    const stepsW = node.widgets.find((w) => w.name === STEPS_NAME).value | 0;
    preview.value = calcSigmas(pts, stepsW)
      .map((v) => parseFloat(v.toFixed(5)))  //精确到小数点后5位，去除多余的0
      .join(", ");
  }

  let debounce;
  ta.addEventListener("input", () => {
    clearTimeout(debounce);
    debounce = setTimeout(() => {
      if (ta.value.trim()) draw(strToPts(ta.value));
    }, 200);
  });
  ta.addEventListener("blur", () => {
    if (ta.value.trim()) applyPoints(strToPts(ta.value));
  });
  ta.addEventListener("keydown", (e) => {
    if ((e.ctrlKey||e.metaKey) && e.key==="z" && undoStack.length) {
      e.preventDefault();
      const prev = undoStack.shift();
      gw.value = prev;
      const pts = strToPts(prev);
      ta.value = prev; 
      draw(pts);
    }
  });
  
  addBtn.onclick = () => {
    const pts = strToPts(gw.value);
    const new_len = pts.length + 1; 
    const steps = new_len - 1;      
    applyPoints(calcSigmas(pts, steps).map((y, i) => ({ x: i / steps, y })));
  };
  delBtn.onclick = () => {
    const pts = strToPts(gw.value);
    if (pts.length > MIN_POINTS) {
      const new_len = pts.length - 1; 
      const steps = new_len - 1;      
      applyPoints(calcSigmas(pts, steps).map((y, i) => ({ x: i / steps, y })));
    }
  };

  let dragIdx = -1;
  canvas.onpointerdown = (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX-rect.left)/rect.width;
    const y = 1 - (e.clientY-rect.top)/rect.height;
    const pts = strToPts(gw.value);

    if (e.button===2) {
      const idx = pts.findIndex(p=>Math.hypot(p.x-x,p.y-y)<GRAB_THRESHOLD);
      if (idx>0 && idx<pts.length-1 && pts.length>MIN_POINTS) {
        pushUndo(gw.value);
        pts.splice(idx,1);
        applyPoints(pts);
      }
      e.preventDefault();
      return;
    }

    if (e.detail===2) {
      pushUndo(gw.value);
      pts.push({ x, y });
      pts.sort((a,b)=>a.x-b.x);
      applyPoints(pts);
      return;
    }

    dragIdx = pts.findIndex(p=>Math.hypot(p.x-x,p.y-y)<GRAB_THRESHOLD);
    if (dragIdx>=0) e.target.setPointerCapture(e.pointerId);
  };
  canvas.onpointermove = (e) => {
    const rect = canvas.getBoundingClientRect();
    const x = (e.clientX-rect.left)/rect.width;
    const y = 1 - (e.clientY-rect.top)/rect.height;
    const pts = strToPts(gw.value);

    if (dragIdx>=0) {
      const ny = Math.min(1, Math.max(0, y));
      pts[dragIdx] = { x:pts[dragIdx].x, y:ny };
      applyPoints(pts);
    }

    const over = pts.some(p=>Math.hypot(p.x-x,p.y-y)<GRAB_THRESHOLD);
    canvas.style.cursor = dragIdx>=0||over ? "pointer":"crosshair";
  };
  canvas.onpointerup = (e) => {
    if (dragIdx>=0) {
      e.target.releasePointerCapture(e.pointerId);
      dragIdx = -1;
    }
  };
  canvas.oncontextmenu = (e) => e.preventDefault();

  const sw = node.widgets.find((w) => w.name === STEPS_NAME);
  if (sw) sw.callback = () => applyPoints(strToPts(ta.value));

  applyPoints(strToPts(ta.value));
  new ResizeObserver(() => draw()).observe(canvas);
}

/*—— Registration ——*/
app.registerExtension({
  name: "Element_SigmaGraph.widget",
  beforeRegisterNodeDef(nt, nd) {
    if (nd.name === NODE_CLASS) {
      
      const origConfigure = nt.prototype.onConfigure;
      nt.prototype.onConfigure = function(info) {
        origConfigure?.apply(this, arguments);
        setup(this);
      };

      const origNodeCreated = nt.prototype.onNodeCreated;
      nt.prototype.onNodeCreated = function() {
        origNodeCreated?.apply(this, arguments);
        
        this.setSize([280, 420]); 
        
        setup(this);
      };      
    }
  },
    
  setup() {
    api.addEventListener("element_sigma_graph_update", (event) => {
        const data = event.detail;
        if (!data || !data.node_id) return;
        
        const node = app.graph.getNodeById(data.node_id);
        
        if (node && node.type === NODE_CLASS) {
            const sw = node.widgets.find((w) => w.name === STEPS_NAME);
            if (sw) sw.value = data.steps;
            
            if (node._applyPoints) {
                node._applyPoints(data.points);
            }
            
            node.setDirtyCanvas(true, true);
        }
    });
  }
});

if (app.on) {
  app.on("nodeAdded", (n) => { if (n.type === NODE_CLASS) setup(n); });
} else {
  setInterval(() => {
    (app.graph?._nodes||[]).forEach((n) => {
      if (n.type === NODE_CLASS) setup(n);
    });
  }, 100);
}

