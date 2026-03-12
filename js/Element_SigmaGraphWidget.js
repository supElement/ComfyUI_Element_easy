/*
# 原始代码来自 TWanSigmaGraph (https://github.com/Temult/TWanSigmaGraph)
# 原作者: Temult
# 许可证: MIT License
# 
# 修改说明:
# - 【更新】实现在鼠标点击曲线的位置增减控制点，其它控制点位置和曲率最大限度保持不变（双击添加，右键删除）
# - 【更新】改为使用单独json文件存取预设
# - 【新增】加入 custom_sigmas, latent 可选输入端, 添加节点可单独执行功能
# - 【修复】y值限制在[0,1]范围内，修复浮点精度问题
#
# 修改者: [supElement]
# 修改日期: 2026-02-28
*/

import { app } from "/../scripts/app.js";
import { $el } from "/../scripts/ui.js";
import { api } from "/../scripts/api.js";

/*—— Constants ——*/
const NODE_CLASS      = "Element_SigmaGraph";
const GRAPH_DATA_NAME = "graph_data";
const STEPS_NAME      = "steps";
const CANVAS_TYPE     = "SIGMA_GRAPH_CANVAS";
const MIN_POINTS      = 2;
const NUM_SLOTS       = 8;
const LS_KEY          = "sigma_graph_saveSlots";
const UNDO_LIMIT      = 1;
const MIN_NODE_WIDTH  = 200;
const GRAB_THRESHOLD  = 0.08;
const POINT_RADIUS    = 4;
const POINT_COLOR     = "#1E88E5";
const LINE_COLOR      = "#fff";
const GUIDE_COLOR     = "#444";

/*—— Linear Interpolation ——*/

/**
 * 线性插值计算
 */
function linearInterpolate(x, points) {
    if (!points || points.length < 2) return 0.0;
    
    for (let i = 0; i < points.length - 1; i++) {
        const p1 = points[i];
        const p2 = points[i + 1];
        
        if (x >= p1.x && x <= p2.x) {
            if (Math.abs(p2.x - p1.x) < 1e-6) return Math.max(0.0, Math.min(1.0, p1.y));
            const t = (x - p1.x) / (p2.x - p1.x);
            const y = p1.y + t * (p2.y - p1.y);
            return Math.max(0.0, Math.min(1.0, y));
        }
    }
    
    if (x < points[0].x) return Math.max(0.0, Math.min(1.0, points[0].y));
    return Math.max(0.0, Math.min(1.0, points[points.length - 1].y));
}

/**
 * 格式化数值，避免科学计数法，处理浮点精度
 */
function formatValue(val) {
    if (Math.abs(val) < 1e-10) val = 0.0;
    if (Math.abs(val - 1.0) < 1e-10) val = 1.0;
    val = Math.max(0.0, Math.min(1.0, val));
    return Math.round(val * 10000000000) / 10000000000;
}

/**
 * 计算线性插值的采样点（用于预览）
 */
function calcLinearSigmas(points, steps) {
    steps = Math.max(1, steps | 0);
    const p = (points || []).slice().sort((a, b) => a.x - b.x);
    
    if (p.length < 2) return Array(steps + 1).fill(1.0);
    
    // 确保边界
    if (!p.some((pt) => Math.abs(pt.x) < 1e-6))
        p.unshift({ x: 0, y: Math.max(0.0, Math.min(1.0, p[0].y)) });
    if (!p.some((pt) => Math.abs(pt.x - 1) < 1e-6))
        p.push({ x: 1, y: Math.max(0.0, Math.min(1.0, p[p.length - 1].y)) });
    
    const out = [];
    
    for (let i = 0; i < steps + 1; i++) {
        const t = i / steps;
        let y = linearInterpolate(t, p);
        y = formatValue(y);
        out.push(y);
    }
    
    return out;
}

function strToPts(str) {
    try {
        const arr = JSON.parse(str);
        if (
            Array.isArray(arr) &&
            arr.every((o) => typeof o.x === "number" && typeof o.y === "number")
        ) {
            return arr.map(p => ({
                x: p.x,
                y: Math.max(0.0, Math.min(1.0, p.y))
            }));
        }
    } catch { /* ignore */ }

    const nums = str
        .split(/[^0-9.+-]+/)
        .map(parseFloat)
        .filter((n) => !isNaN(n));
    if (nums.length < 2) {
        const y = nums[0] || 1;
        return [{ x: 0, y: Math.max(0.0, Math.min(1.0, y)) }, { x: 1, y: Math.max(0.0, Math.min(1.0, nums[0] != null ? y : 0)) }];
    }
    return nums.map((y, i) => ({ 
        x: i / (nums.length - 1), 
        y: formatValue(y)
    }));
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
        initialPts = [{x: 0, y: 1}, {x: 1, y: 0}];
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
            paddingBottom: "20px"
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

    const resetBtn = $el("button", {
        textContent: "R", title: "Reset line",
        style: { position: "absolute", top: "4px", right: "4px", width: "24px", height: "24px", borderRadius: "50%", border: "1px solid #555", background: "#505050", color: "#fff", cursor: "pointer" }
    });
    wrap.appendChild(resetBtn);

    const slotBar = $el("div", {
        style: { display: "flex", gap: "4px", marginTop: "4px", alignItems: "center" }
    });
    wrap.appendChild(slotBar);
 
    let slotsData = []; 
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

    const slotBtns = [];
    
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
                recBtn.click();
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
            recBtn.style.background = "#ff4444";
            recBtn.style.border = "1px solid #ff4444";
        } else {
            recBtn.style.background = "none";
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
                    updateSlotUI();
                }
            }
        } catch (e) {
            console.error("[Element_SigmaGraph] 读取预设文件失败", e);
        }
    }
    
    loadPresetsFromFile();

    let undoStack = [];
    function pushUndo(state) {
        undoStack.unshift(state);
        if (undoStack.length > UNDO_LIMIT) undoStack.pop();
    }

    function applyPoints(pts) {
        pushUndo(gw.value);
        const clean = pts.map((p) => ({
            x: Math.round(p.x * 100000) / 100000,  
            y: formatValue(p.y)
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
    
    /**
     * 绘制直线连接的控制点
     */
    function draw(overridePts) {
        const pts = overridePts || strToPts(gw.value);
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.clientWidth, h = canvas.clientHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);

        // 绘制网格
        ctx.strokeStyle = GUIDE_COLOR;
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        for (let i = 1; i < 10; i++) {
            const x = (i * w) / 10, y = (i * h) / 10;
            ctx.moveTo(x, 0); ctx.lineTo(x, h);
            ctx.moveTo(0, y); ctx.lineTo(w, y);
        }
        ctx.stroke();

        if (pts.length >= 2) {
            // 绘制直线连接
            ctx.strokeStyle = LINE_COLOR;
            ctx.lineWidth = 1.0;
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            ctx.beginPath();
            
            // 按x排序
            const sortedPts = pts.slice().sort((a, b) => a.x - b.x);
            
            ctx.moveTo(sortedPts[0].x * w, (1 - Math.max(0.0, Math.min(1.0, sortedPts[0].y))) * h);
            
            for (let i = 1; i < sortedPts.length; i++) {
                const p = sortedPts[i];
                ctx.lineTo(p.x * w, (1 - Math.max(0.0, Math.min(1.0, p.y))) * h);
            }
            ctx.stroke();

            // 绘制锚点（数据点）
            sortedPts.forEach((p) => {
                const px = p.x * w;
                const py = (1 - Math.max(0.0, Math.min(1.0, p.y))) * h;
                ctx.fillStyle = POINT_COLOR;
                ctx.beginPath();
                ctx.arc(px, py, POINT_RADIUS, 0, 2 * Math.PI);
                ctx.fill();
            });
        }

        // 更新预览
        const stepsW = node.widgets.find((w) => w.name === STEPS_NAME).value | 0;
        const sigmaValues = calcLinearSigmas(pts, stepsW);
        preview.value = sigmaValues
            .map((v) => parseFloat(v.toFixed(5)))
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
    
    resetBtn.onclick = () => {
        pushUndo(gw.value);
        const defaultPoints = [{x: 0, y: 1}, {x: 1, y: 0}];
        applyPoints(defaultPoints);
    };

    /* ============================================
     * 双击加点功能 - 手动检测实现
     * ============================================ */
    
    let dragIdx = -1;
    let lastClickTime = 0;
    let lastClickX = 0;
    let lastClickY = 0;
    const DOUBLE_CLICK_DELAY = 300;

   canvas.onpointerdown = (e) => {
       const rect = canvas.getBoundingClientRect();
       const x = (e.clientX - rect.left) / rect.width;
       const y = 1 - (e.clientY - rect.top) / rect.height;
       let pts = strToPts(gw.value);
       const currentTime = Date.now();
   
       // 右键删除点
       if (e.button === 2) {
           const idx = pts.findIndex(p => Math.hypot(p.x - x, p.y - y) < GRAB_THRESHOLD);
           if (idx > 0 && idx < pts.length - 1 && pts.length > MIN_POINTS) {
               pushUndo(gw.value);
               pts.splice(idx, 1);
               applyPoints(pts);
           }
           e.preventDefault();
           return;
       }
   
       // 检测双击（手动实现）
       const timeDiff = currentTime - lastClickTime;
       const distDiff = Math.hypot(x - lastClickX, y - lastClickY);
   
       if (timeDiff < DOUBLE_CLICK_DELAY && distDiff < 0.05 && e.button === 0) {
           e.preventDefault();
           lastClickTime = 0;
           
           pts = pts.slice();
           
           const existingIdx = pts.findIndex(p => Math.hypot(p.x - x, p.y - y) < GRAB_THRESHOLD);
           if (existingIdx >= 0) return;
           
           pushUndo(gw.value);
           
           // 找到 x 所在的区间
           pts.sort((a, b) => a.x - b.x);
           let insertIdx = pts.findIndex(p => p.x > x);
           if (insertIdx === -1) insertIdx = pts.length;
           
           const leftPt = pts[insertIdx - 1] || pts[0];
           const rightPt = pts[insertIdx] || pts[pts.length - 1];
           
           // 检查间距
           if (Math.abs(rightPt.x - leftPt.x) < 0.05) {
               return;
           }
           
           // 使用线性插值计算新点的 y 值
           const curveY = linearInterpolate(x, pts);
           
           const newX = Math.max(leftPt.x + 0.005, Math.min(rightPt.x - 0.005, x));
           
           const newPoint = { 
               x: newX,
               y: formatValue(curveY)
           };
           
           pts.splice(insertIdx, 0, newPoint);
           
           applyPoints(pts);
           return;
       }
   
       // 记录本次点击
       lastClickTime = currentTime;
       lastClickX = x;
       lastClickY = y;
   
       // 单击 - 开始拖拽
       if (e.button === 0) {
           dragIdx = pts.findIndex(p => Math.hypot(p.x - x, p.y - y) < GRAB_THRESHOLD);
           if (dragIdx >= 0) {
               e.target.setPointerCapture(e.pointerId);
           }
       }
   };

    
    canvas.onpointermove = (e) => {
        const rect = canvas.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = 1 - (e.clientY - rect.top) / rect.height;
        const pts = strToPts(gw.value);

        if (dragIdx >= 0) {
            const ny = Math.min(1, Math.max(0, y));
            if (dragIdx === 0) {
                pts[dragIdx] = { x: 0, y: ny };
            } else if (dragIdx === pts.length - 1) {
                pts[dragIdx] = { x: 1, y: ny };
            } else {
                const minX = pts[dragIdx - 1].x + 0.01;
                const maxX = pts[dragIdx + 1].x - 0.01;
                const nx = Math.min(maxX, Math.max(minX, x));
                pts[dragIdx] = { x: nx, y: ny };
            }
            applyPoints(pts);
        }

        const over = pts.some(p => Math.hypot(p.x - x, p.y - y) < GRAB_THRESHOLD);
        canvas.style.cursor = dragIdx >= 0 || over ? "pointer" : "crosshair";
    };
    
    canvas.onpointerup = (e) => {
        if (dragIdx >= 0) {
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
