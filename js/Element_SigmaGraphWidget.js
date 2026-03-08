/*
# 原始代码来自 TWanSigmaGraph (https://github.com/Temult/TWanSigmaGraph)
# 原作者: Temult
# 许可证: MIT License
# 
# 修改说明:
# - 修复了曲线调整无效的问题
#
# 修改者: [supElement]
# 修改日期: 2026-02-28
——*/


// Element_SigmaGraphWidget.js – v0.1.2
// -------------------------------
// Companion widget for the Element_SigmaGraph node.

import { app } from "/../scripts/app.js";
import { $el } from "/../scripts/ui.js";

/*—— Constants ——*/
const NODE_CLASS      = "Element_SigmaGraph";
const GRAPH_DATA_NAME = "graph_data";
const STEPS_NAME      = "steps";
const CANVAS_TYPE     = "SIGMA_GRAPH_CANVAS";
const MIN_POINTS      = 3;
const NUM_SLOTS       = 8;
const LS_KEY          = "sigma_graph_saveSlots";
const UNDO_LIMIT      = 1;
const MIN_NODE_WIDTH  = 180;
const GRAB_THRESHOLD  = 0.08;
const POINT_RADIUS    = 6;
const POINT_COLOR     = "#1E88E5";

/*—— Helper Functions ——*/
function calcSigmas(pts, steps) {
  steps = Math.max(1, steps | 0);
  const p = (pts ||[]).slice().sort((a, b) => a.x - b.x);
  
  // 【修改点 1】：如果点数不够，默认返回的数组长度也要改成 steps + 1
  if (p.length < 2) return Array(steps + 1).fill(1.0);

  if (!p.some((pt) => Math.abs(pt.x) < 1e-6))
    p.unshift({ x: 0, y: p[0].y });
  if (!p.some((pt) => Math.abs(pt.x - 1) < 1e-6))
    p.push({ x: 1, y: p[p.length - 1].y });

  const out =[];
  let idx = 0;
  
  // 【修改点 2】：循环上限改为 steps + 1，生成 N+1 个数字
  for (let i = 0; i < steps + 1; i++) {
	  
	// 【修改点 3】：分母直接用 steps，且不需要特判 steps === 1 了
    const t = i / steps;
	
    while (idx < p.length - 2 && p[idx + 1].x < t) idx++;
    const [p1, p2] = [p[idx], p[idx + 1]];
    const dx = p2.x - p1.x;
    let y = dx < 1e-6
      ? (Math.abs(t - p2.x) < Math.abs(t - p1.x) ? p2.y : p1.y)
      : p1.y + ((t - p1.x) / dx) * (p2.y - p1.y);
	
	// 【修改点 4】：将 0.001 的下限限制改为 0.0，允许曲线彻底归零（保留了原作者的两位小数四舍五入）
    out.push(Math.max(0.0, Math.round(y * 100) / 100));
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
  return nums.map((y, i) => ({ x: i / (nums.length - 1), y: Math.round(y * 100) / 100 }));
}

/*—— Main Widget Setup ——*/
function setup(node) {
  if (node._sigmaSetupDone) return;
  node._sigmaSetupDone = true;

  const gw = node.widgets.find((w) => w.name === GRAPH_DATA_NAME);
  if (!gw || !gw.element) return;
  const ta = gw.element;

  ta.style.minHeight = "10px";
  ta.style.boxSizing = "border-box";
  ta.style.resize = "vertical";

  const storageKey = `Element_SigmaGraph_last_${node.id}`;
  let initialPts = null;
  const cached = localStorage.getItem(storageKey);
  
  if (cached) {
    try {
      initialPts = strToPts(cached);
      ta.value = JSON.stringify(initialPts);  // 【关键修复】防止初始化时丢失 x 坐标
      gw.value = JSON.stringify(initialPts);
    } catch {
      initialPts = null;
    }
  }

  if (!initialPts) {
    const defaultPts =[{x: 0, y: 1}, {x: 0.33, y: 0.67}, {x: 0.67, y: 0.33}, {x: 1, y: 0}];
    initialPts = defaultPts;
    const defaultJson = JSON.stringify(initialPts);
    ta.value = defaultJson;  // 【关键修复】
    gw.value = defaultJson;
  }

  const wrap = $el("div", {
    style: {
      width: "100%", position: "relative", display: "flex",
      flexDirection: "column", flexGrow: "1", minHeight: "180px",
      paddingBottom: "20px", minWidth: `${MIN_NODE_WIDTH}px`
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
    style: { position: "absolute", top: "4px", right: "40px", width: "24px", height: "24px", borderRadius: "3px", border: "1px solid #555", background: "#64B5F6", color: "#fff", cursor: "pointer" }
  });
  const delBtn = $el("button", {
    textContent: "−", title: "Halve density",
    style: { position: "absolute", top: "4px", right: "10px", width: "24px", height: "24px", borderRadius: "3px", border: "1px solid #555", background: "#EF9A9A", color: "#fff", cursor: "pointer" }
  });
  wrap.appendChild(addBtn);
  wrap.appendChild(delBtn);

  const slotBar = $el("div", {
    style: { display: "flex", gap: "4px", marginTop: "4px", alignItems: "center" }
  });
  wrap.appendChild(slotBar);

  const slotsData = JSON.parse(localStorage.getItem(LS_KEY) || "[]");
  let recordMode = false;
  const recBtn = $el("button", { textContent: "💾", title: "Toggle save mode", style: { minWidth: "28px", cursor: "pointer" } });
  slotBar.appendChild(recBtn);

  const slotBtns =[];
  for (let i = 0; i < NUM_SLOTS; i++) {
    const b = $el("button", {
      textContent: `${i + 1}`,
      disabled: !slotsData[i] && !recordMode,
      style: { flex: "1", minWidth: "20px", opacity: slotsData[i]||recordMode ? "1" : "0.3", cursor: slotsData[i]||recordMode ? "pointer" : "not-allowed" }
    });
    slotBar.appendChild(b);
    slotBtns.push(b);

    b.onclick = () => {
      if (recordMode) {
        slotsData[i] = gw.value;
        localStorage.setItem(LS_KEY, JSON.stringify(slotsData));
        recBtn.click();
      } else if (slotsData[i]) {
        let pts;
        try { pts = JSON.parse(slotsData[i]); }
        catch { pts = strToPts(slotsData[i]); }
        applyPoints(pts);
      }
    };
  }

  recBtn.onclick = () => {
    recordMode = !recordMode;
    recBtn.style.background = recordMode ? "#4caf50" : "";
    slotBtns.forEach((b, i) => {
      const ok = slotsData[i] || recordMode;
      b.disabled = !ok;
      b.style.opacity = ok ? "1" : "0.3";
      b.style.cursor  = ok ? "pointer" : "not-allowed";
    });
  };

  const infoBtn = $el("button", { textContent: "ℹ️", title: "Instructions", style: { flex: "0 0 auto", minWidth: "10px", opacity: "0.6", cursor: "pointer", background: "transparent", border: "none", color: "#ccc" } });
  const advBtn = $el("button", { textContent: "§", title: "Advanced (WIP)", disabled: true, style: { flex: "0 0 auto", minWidth: "10px", opacity: "0.4", cursor: "not-allowed", background: "transparent", border: "none", color: "#666" } });
  slotBar.appendChild(infoBtn);
  slotBar.appendChild(advBtn);

  const overlay = $el("div", {
    style: { position: "absolute", top: "15%", left: "50%", transform: "translate(-50%, -50%)", width: "240px", background: "#222", color: "#ccc", border: "1px solid #555", borderRadius: "6px", padding: "8px 12px", fontSize: "11px", lineHeight: "1.4", textAlign: "center", display: "none", zIndex: "9999", pointerEvents: "auto" }
  });
  overlay.innerHTML = `<strong>Sigma Schedule Editor</strong><br>Bidirectional editor for sigma schedules.<br>Use <strong>+ / –</strong> to adjust density.<br>Expand node to preview sigmas.`;
  wrap.appendChild(overlay);

  infoBtn.addEventListener("click", (e) => {
    e.stopPropagation();
    overlay.style.display = overlay.style.display === "none" ? "block" : "none";
  });
  wrap.addEventListener("click", () => {
    if (overlay.style.display === "block") overlay.style.display = "none";
  });

  let undoStack =[];
  function pushUndo(state) {
    undoStack.unshift(state);
    if (undoStack.length > UNDO_LIMIT) undoStack.pop();
  }

  function applyPoints(pts) {
    pushUndo(gw.value);
    const clean = pts.map((p) => ({
      x: Math.round(p.x * 1000) / 1000,
      y: Math.round(p.y * 100) / 100
    }));
    const jsonStr = JSON.stringify(clean);
    gw.value = jsonStr;
    ta.value = jsonStr; // 【关键修复】确保 widget 的 text 区域也保存完整的坐标

    localStorage.setItem(storageKey, gw.value);
    draw(clean);
  }

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
      ctx.lineWidth = 1.5;
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
      .map((v) => v.toFixed(2))
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
      ta.value = prev; // 【关键修复】撤销时也要恢复完整的 JSON 状态
      draw(pts);
    }
  });
  
  // 替换原有增减点逻辑
  
  addBtn.onclick = () => {
    const pts = strToPts(gw.value);
    const new_len = pts.length + 1; // 新点数
    const steps = new_len - 1;      // 对应的区间步数
    // 传入步数，得到 new_len 个 y 值，然后均匀分布 x 坐标
    applyPoints(calcSigmas(pts, steps).map((y, i) => ({ x: i / steps, y })));
  };
  delBtn.onclick = () => {
    const pts = strToPts(gw.value);
    if (pts.length > MIN_POINTS) {
      const new_len = pts.length - 1; // 新点数
      const steps = new_len - 1;      // 对应的区间步数
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
      const orig = nt.prototype.onConfigure;
      nt.prototype.onConfigure = function(info) {
        orig?.apply(this, arguments);
        setup(this);
      };
    }
  },
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
