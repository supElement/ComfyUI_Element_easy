/*
# 原始代码来自 TWanSigmaGraph (https://github.com/Temult/TWanSigmaGraph)
# 原作者: Temult
# 许可证: MIT License
# 
# 修改说明:
# - 【重大更新】实现三次样条插值，曲线真正平滑且经过所有控制点
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
const NODE_CLASS      = "Element_SigmaGraph_Curve";
const GRAPH_DATA_NAME = "graph_data";
const STEPS_NAME      = "steps";
const CANVAS_TYPE     = "SIGMA_GRAPH_CURVE_CANVAS";
const MIN_POINTS      = 2;
const NUM_SLOTS       = 8;
const LS_KEY          = "sigma_graph_saveSlots";
const UNDO_LIMIT      = 1;
const MIN_NODE_WIDTH  = 200;
const GRAB_THRESHOLD  = 0.08;
const POINT_RADIUS    = 4;
const POINT_COLOR     = "#1E88E5";
const CURVE_COLOR     = "#fff";
const CONTROL_COLOR   = "#ff6b6b";  // 控制点颜色
const GUIDE_COLOR     = "#444";     // 辅助线颜色

/*—— Cubic Spline Interpolation ——*/

/**
 * 计算三次样条插值系数（Thomas算法）
 */
function computeSplineCoefficients(points) {
    const n = points.length - 1;
    if (n < 1) return [];
    
    const x = points.map(p => p.x);
    const y = points.map(p => p.y);
    const h = [];
    
    for (let i = 0; i < n; i++) {
        h.push(x[i+1] - x[i]);
    }
    
    // 构建三对角矩阵
    const A = Array(n+1).fill().map(() => Array(n+1).fill(0));
    const b = Array(n+1).fill(0);
    
    A[0][0] = 1;
    A[n][n] = 1;
    
    for (let i = 1; i < n; i++) {
        A[i][i-1] = h[i-1];
        A[i][i] = 2 * (h[i-1] + h[i]);
        A[i][i+1] = h[i];
        b[i] = 3 * ((y[i+1] - y[i]) / h[i] - (y[i] - y[i-1]) / h[i-1]);
    }
    
    // Thomas算法求解
    const cPrime = Array(n+1).fill(0);
    const dPrime = Array(n+1).fill(0);
    const M = Array(n+1).fill(0);
    
    cPrime[0] = A[0][1] / A[0][0];
    dPrime[0] = b[0] / A[0][0];
    
    for (let i = 1; i <= n; i++) {
        const denom = A[i][i] - A[i][i-1] * cPrime[i-1];
        if (i < n) cPrime[i] = A[i][i+1] / denom;
        dPrime[i] = (b[i] - A[i][i-1] * dPrime[i-1]) / denom;
    }
    
    M[n] = dPrime[n];
    for (let i = n-1; i >= 0; i--) {
        M[i] = dPrime[i] - cPrime[i] * M[i+1];
    }
    
    // 计算系数
    const coeffs = [];
    for (let i = 0; i < n; i++) {
        const a = y[i];
        const b_coef = (y[i+1] - y[i]) / h[i] - h[i] * (2*M[i] + M[i+1]) / 3;
        const c = M[i];
        const d = (M[i+1] - M[i]) / (3 * h[i]);
        
        coeffs.push({
            a, b: b_coef, c, d,
            x0: x[i], x1: x[i+1]
        });
    }
    
    return coeffs;
}

/**
 * 评估样条函数在x处的值
 */
function evaluateSpline(x, coeffs) {
    for (let coeff of coeffs) {
        if (x >= coeff.x0 && x <= coeff.x1) {
            const dx = x - coeff.x0;
            const val = coeff.a + coeff.b*dx + coeff.c*dx*dx + coeff.d*dx*dx*dx;
            // 限制在 [0, 1]
            return Math.max(0.0, Math.min(1.0, val));
        }
    }
    // 边界处理
    if (coeffs.length === 0) return 0;
    if (x < coeffs[0].x0) {
        // 返回限制后的端点值
        return Math.max(0.0, Math.min(1.0, coeffs[0].a));
    }
    const last = coeffs[coeffs.length-1];
    const lastVal = last.a + last.b*(last.x1-last.x0) + last.c*(last.x1-last.x0)**2 + last.d*(last.x1-last.x0)**3;
    return Math.max(0.0, Math.min(1.0, lastVal));
}

/**
 * 将样条转换为贝塞尔曲线控制点，用于Canvas绘制
 * 每个区间转换为一条三次贝塞尔曲线，并限制控制点在合理范围内
 */
function splineToBezier(points) {
    if (points.length < 2) return [];
    
    const coeffs = computeSplineCoefficients(points);
    const bezierCurves = [];
    
    for (let i = 0; i < points.length - 1; i++) {
        const p0 = points[i];
        const p3 = points[i+1];
        const coeff = coeffs[i];
        
        // 计算一阶导数在端点的值
        const dx = p3.x - p0.x;
        const dy_dx_0 = coeff.b;
        const dy_dx_1 = coeff.b + 2*coeff.c*dx + 3*coeff.d*dx*dx;
        
        // 转换为贝塞尔控制点
        const cp1x = p0.x + dx / 3;
        // 限制控制点y值在[0,1]范围内，避免曲线绘制越界
        let cp1y = p0.y + dy_dx_0 * (dx / 3);
        cp1y = Math.max(-0.5, Math.min(1.5, cp1y)); // 允许稍微超出以便曲线平滑，但不要太离谱
        
        const cp2x = p3.x - dx / 3;
        let cp2y = p3.y - dy_dx_1 * (dx / 3);
        cp2y = Math.max(-0.5, Math.min(1.5, cp2y));
        
        bezierCurves.push({
            p0: { x: p0.x, y: Math.max(0.0, Math.min(1.0, p0.y)) },
            cp1: { x: cp1x, y: cp1y },
            cp2: { x: cp2x, y: cp2y },
            p3: { x: p3.x, y: Math.max(0.0, Math.min(1.0, p3.y)) }
        });
    }
    
    return bezierCurves;
}

/**
 * 格式化数值，避免科学计数法，处理浮点精度
 */
function formatValue(val) {
    // 处理极小的浮点误差
    if (Math.abs(val) < 1e-10) val = 0.0;
    if (Math.abs(val - 1.0) < 1e-10) val = 1.0;
    // 限制范围
    val = Math.max(0.0, Math.min(1.0, val));
    // 四舍五入到10位小数，避免科学计数法
    return Math.round(val * 10000000000) / 10000000000;
}

/**
 * 计算平滑曲线上的采样点（用于预览）
 */
function calcSmoothSigmas(points, steps) {
    steps = Math.max(1, steps | 0);
    const p = (points || []).slice().sort((a, b) => a.x - b.x);
    
    if (p.length < 2) return Array(steps + 1).fill(1.0);
    
    // 确保边界
    if (!p.some((pt) => Math.abs(pt.x) < 1e-6))
        p.unshift({ x: 0, y: Math.max(0.0, Math.min(1.0, p[0].y)) });
    if (!p.some((pt) => Math.abs(pt.x - 1) < 1e-6))
        p.push({ x: 1, y: Math.max(0.0, Math.min(1.0, p[p.length - 1].y)) });
    
    const coeffs = computeSplineCoefficients(p);
    const out = [];
    
    for (let i = 0; i < steps + 1; i++) {
        const t = i / steps;
        let y = evaluateSpline(t, coeffs);
        // 格式化避免科学计数法
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
            // 解析时限制y值
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
        textContent: "R", title: "Reset curve",
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
                    await fetch('/element_easy/sigma_Curve_presets', {
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
            const response = await fetch('/element_easy/sigma_Curve_presets');
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
     * 绘制平滑样条曲线和控制点
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
            // 计算贝塞尔曲线控制点并绘制
            const bezierCurves = splineToBezier(pts);
            
            // 绘制平滑曲线 - 使用clip限制绘制区域在[0,1]范围内
            ctx.save();
            ctx.beginPath();
            ctx.rect(0, 0, w, h);
            ctx.clip();
            
            ctx.strokeStyle = CURVE_COLOR;
            ctx.lineWidth = 1.0;
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            ctx.beginPath();
            
            if (bezierCurves.length > 0) {
                const first = bezierCurves[0];
                ctx.moveTo(first.p0.x * w, (1 - Math.max(0.0, Math.min(1.0, first.p0.y))) * h);
                
                for (let curve of bezierCurves) {
                    // 限制绘制点的y值在[0,1]可视化范围内
                    const cp1y_clamped = Math.max(0.0, Math.min(1.0, curve.cp1.y));
                    const cp2y_clamped = Math.max(0.0, Math.min(1.0, curve.cp2.y));
                    const p3y_clamped = Math.max(0.0, Math.min(1.0, curve.p3.y));
                    
                    ctx.bezierCurveTo(
                        curve.cp1.x * w, (1 - cp1y_clamped) * h,
                        curve.cp2.x * w, (1 - cp2y_clamped) * h,
                        curve.p3.x * w, (1 - p3y_clamped) * h
                    );
                }
            }
            ctx.stroke();
            ctx.restore();
            
            // 可选：绘制控制点和辅助线（用于调试，默认关闭）
            const showControlPoints = false;
            if (showControlPoints) {
                ctx.strokeStyle = GUIDE_COLOR;
                ctx.lineWidth = 0.5;
                ctx.setLineDash([2, 2]);
                
                for (let curve of bezierCurves) {
                    ctx.beginPath();
                    ctx.moveTo(curve.p0.x * w, (1 - curve.p0.y) * h);
                    ctx.lineTo(curve.cp1.x * w, (1 - curve.cp1.y) * h);
                    ctx.moveTo(curve.p3.x * w, (1 - curve.p3.y) * h);
                    ctx.lineTo(curve.cp2.x * w, (1 - curve.cp2.y) * h);
                    ctx.stroke();
                    
                    // 控制点
                    ctx.fillStyle = CONTROL_COLOR;
                    ctx.beginPath();
                    ctx.arc(curve.cp1.x * w, (1 - curve.cp1.y) * h, 2, 0, 2 * Math.PI);
                    ctx.arc(curve.cp2.x * w, (1 - curve.cp2.y) * h, 2, 0, 2 * Math.PI);
                    ctx.fill();
                }
                ctx.setLineDash([]);
            }

            // 绘制锚点（数据点）
            pts.forEach((p) => {
                const px = p.x * w;
                const py = (1 - Math.max(0.0, Math.min(1.0, p.y))) * h;
                ctx.fillStyle = POINT_COLOR;
                ctx.beginPath();
                ctx.arc(px, py, POINT_RADIUS, 0, 2 * Math.PI);
                ctx.fill();
                
                // 点的外圈
                //ctx.strokeStyle = "#fff";
                //ctx.lineWidth = 1;
                //ctx.stroke();
            });
        }

        // 更新预览
        const stepsW = node.widgets.find((w) => w.name === STEPS_NAME).value | 0;
        const sigmaValues = calcSmoothSigmas(pts, stepsW);
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
    
    // 【关键】这些变量必须在 onpointerdown 外部声明，否则无法记录状态
    let dragIdx = -1;
    let lastClickTime = 0;
    let lastClickX = 0;
    let lastClickY = 0;
    const DOUBLE_CLICK_DELAY = 300; // 毫秒

   canvas.onpointerdown = (e) => {
       const rect = canvas.getBoundingClientRect();
       const x = (e.clientX - rect.left) / rect.width;
       const y = 1 - (e.clientY - rect.top) / rect.height;
       let pts = strToPts(gw.value);  // 【修改】用 let 而不是 const，方便后续复制
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
           
           // 【关键】创建副本用于修改
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
           
           // 使用当前样条计算曲线 y 值
           const coeffs = computeSplineCoefficients(pts);
           const curveY = evaluateSpline(x, coeffs);
           
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
            // 限制 y 在 [0,1] 范围内
            const ny = Math.min(1, Math.max(0, y));
            // 边界点只能上下移动，内部点可以左右移动但保持排序
            if (dragIdx === 0) {
                pts[dragIdx] = { x: 0, y: ny };
            } else if (dragIdx === pts.length - 1) {
                pts[dragIdx] = { x: 1, y: ny };
            } else {
                // 限制 x 在相邻点之间
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
    name: "Element_SigmaGraph_Curve.widget",
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