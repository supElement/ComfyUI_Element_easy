import { app } from "../../scripts/app.js";
import { $el } from "../../scripts/ui.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "LoadImageWithPreview"; 

app.registerExtension({
    name: "element_easy.ImageLoader",
  
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;

        try {
            const inputDef = nodeData?.input;
            if (inputDef) {
                for (const section of ["required", "optional"]) {
                    const sec = inputDef[section];
                    if (!sec) continue;
                    delete sec.crop_data;
                    delete sec.mask_data;
                    delete sec.shape_data;
                }
            }
        } catch (e) {}


        $el("style", {
            textContent: `
                .ee-container { display: flex; flex-direction: column; width: 100%; height: 100%; min-height: 100px; overflow: hidden; background: #1e1e1e; font-family: sans-serif; user-select: none; -webkit-user-select: none;}
                .ee-header { display: flex; padding: 4px; background: #282828; gap: 4px; align-items: center; }
                .ee-btn { background: #444; color: white; border: none; padding: 4px 8px; cursor: pointer; border-radius: 3px; font-size: 12px; }
                .ee-btn:hover { background: #555; }
                .ee-btn.active { background: #007acc; }
                .ee-btn-lmask:active { background: #007acc !important; }  
				
                .ee-grid { 
                    display: grid; 
                    grid-template-columns: repeat(auto-fit, minmax(110px, 1fr)); 
                    gap: 6px; 
                    overflow-y: auto; 
                    flex: 1; 
                    padding: 6px; 
                }
                .ee-grid-item { aspect-ratio: 1; background: #222; cursor: pointer; border: 2px solid transparent; }
                .ee-grid-item:hover { border-color: #555; }
                .ee-grid-item.selected { border-color: #007acc; }
                .ee-grid-item img { width: 100%; height: 100%; object-fit: contain; }
                
                .ee-editor-wrap { display: none; flex-direction: column; flex: 1; position: relative; }
                
                .ee-toolbar { 
                    display: flex; 
                    padding: 4px; 
                    gap: 4px; 
                    background: #2a2a2a; 
                    align-items: flex-start;
                    flex-wrap: wrap;
                }
                
                .ee-toolbar-row {
                    display: flex;
                    align-items: center;
                    gap: 4px;
                    flex-wrap: nowrap;
                }
                
                .ee-toolbar-group { 
                    display: flex; 
                    align-items: center; 
                    gap: 4px; 
                    border-right: 1px solid #444; 
                    padding-right: 4px; 
                    flex-shrink: 0;
                }
                
                .ee-toolbar-group:last-child {
                    border-right: none;
                }
                
                .ee-canvas-container { position: relative; flex: 1; overflow: hidden; display: flex; align-items: center; justify-content: center; background: #000; }
                .ee-canvas-container img { 
                    position: absolute; 
                    pointer-events: none;
                }
                
                .ee-canvas-container canvas.shape-canvas { position: absolute; pointer-events: none; z-index: 1; left: 0; top: 0; }
                .ee-canvas-container canvas.mask-canvas { position: absolute; cursor: none; z-index: 2; left: 0; top: 0; }
                .ee-brush-cursor { 
                    position: fixed; 
                    border: 2px solid rgba(255, 255, 255, 0.8); 
                    border-radius: 50%; 
                    pointer-events: none; 
                    z-index: 9999; 
                    display: none;
                    box-shadow: 0 0 4px rgba(0,0,0,0.5);
                    transform: translate(-50%, -50%); 
                }
                
                .ee-switch-btn {
                    background: #666;
                    color: white;
                    border: none;
                    padding: 6px 16px;
                    cursor: pointer;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: bold;
                    min-width: 40px;
                    transition: background-color 0.2s;
                }
                .ee-switch-btn.active {
                    background: #007acc;
                }
                .ee-switch-btn:hover {
                    opacity: 0.9;
                }
                
                .ee-color-wrapper { position: relative; display: inline-block; width: 28px; height: 28px; }
                .ee-color-wrapper input[type="color"] { width: 100%; height: 100%; padding: 0; border: none; border-radius: 3px; cursor: pointer; }
                .ee-color-overlay { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); color: white; font-size: 12px; font-weight: bold; text-shadow: 0 0 2px rgba(0,0,0,0.8), 0 0 4px rgba(0,0,0,0.8); pointer-events: none; z-index: 10; line-height: 1; }
                .ee-color-label { color: #aaa; font-size: 12px; font-weight: bold; margin-right: 2px; }
                .ee-slider-container { display: flex; align-items: center; gap: 4px; }
                .ee-slider-container span { color: #aaa; font-size: 11px; white-space: nowrap; }
                .ee-slider-container input[type="range"] { width: 80px; height: 4px; cursor: pointer; -webkit-appearance: none; appearance: none; background: transparent; }
                .ee-slider-container input[type="range"]::-webkit-slider-runnable-track { height: 4px; background: #555; border-radius: 2px; }
                .ee-slider-container input[type="range"]::-webkit-slider-thumb { -webkit-appearance: none; appearance: none; width: 14px; height: 14px; background: #007acc; border-radius: 50%; margin-top: -5px; cursor: pointer; }
                .ee-slider-container input[type="range"]::-moz-range-track { height: 4px; background: #555; border-radius: 2px; }
                .ee-slider-container input[type="range"]::-moz-range-thumb { width: 14px; height: 14px; background: #007acc; border-radius: 50%; border: none; cursor: pointer; }
				.ee-src-btn { background:#444; color:#fff; border:none; height:28px; line-height:28px; padding:0 8px; cursor:pointer; border-radius:3px; font-size:12px; font-weight:bold; flex-shrink:0; }
                .ee-src-btn:hover { background:#555; }
                .ee-src-btn.active { background:#007acc; color:#fff; }
                .ee-drop-overlay { position:absolute; left:0; top:0; right:0; bottom:0; display:none; align-items:center; justify-content:center; background:rgba(0,122,204,0.25); border:2px dashed #007acc; box-sizing:border-box; color:#fff; font-size:14px; font-weight:bold; z-index:5; pointer-events:none; }

            `,
            parent: document.head,
        });

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        
        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);

            const isNodes2_0 = !!document.querySelector("comfy-app") || 
                               !!document.querySelector(".comfy-vue") || 
                               (window.comfyAPI && window.comfyAPI.vue);

            const hideWidgetAndSlot = (widgetName) => {
                const w = this.widgets?.find(w => w.name === widgetName);
                if (w) {
                    w.type = "hidden_custom"; 
                    w.hidden = true;
                    w.computeSize = () => [0, 0];
                    w.draw = () => {};

                    if (isNodes2_0) {
                        if (w.inputEl) {
                            w.inputEl.style.display = "none";
                            if (w.inputEl.parentElement) w.inputEl.parentElement.style.display = "none";
                        }
                    } else {
                        const el = w.inputEl || w.element;
                        if (el) {
                            el.style.visibility = "hidden";
                            el.style.position = "absolute";
                            el.style.width = "0";
                            el.style.height = "0";
                            el.style.padding = "0";
                            el.style.margin = "0";
                            el.style.border = "none";
                            if (el.parentElement) {
                                el.parentElement.style.visibility = "hidden";
                                el.parentElement.style.position = "absolute";
                                el.parentElement.style.width = "0";
                                el.parentElement.style.height = "0";
                            }
                        }
                    }
                }
                
                if (this.inputs) {
                    const idx = this.inputs.findIndex(i => i.name === widgetName);
                    if (idx !== -1) {
                        this.removeInput(idx);
                    }
                }
            };
            hideWidgetAndSlot("mask_data");
            hideWidgetAndSlot("shape_data"); 
			hideWidgetAndSlot("crop_data");
        };
    },

    async nodeCreated(node) {
        if (node.comfyClass !== NODE_NAME) return;
		
		//const storageKey = (type) => `${type}_${node.id}_${currentPath}`;
		
        const isNewNode = typeof node.id !== 'number' || node.id < 0;
		let lastScrollTop = 0;
        let editorCtx = null;
        if (isNewNode) {
            node.size = [580, 600];
        }

        const pathWidget = node.widgets.find(w => w.name === "folder_path");
        const sortWidget = node.widgets.find(w => w.name === "sort_method");
        let imageWidget = node.widgets.find(w => w.name === "selected_image");

        let maskWidget = {
            name: "mask_data",
            type: "hidden",
            value: node.widgets?.find(w => w.name === "mask_data")?.value || node.widgets?.find(w => w.name === "mask_data")?.options?.default || "",
            hidden: true,
            computeSize: () => [0, 0],
            draw: () => {}  
        };
        
        let maskColorWidget = {
            name: "mask_color_data",
            type: "hidden", 
            value: node.widgets?.find(w => w.name === "mask_color_data")?.value || "",
            hidden: true,
            computeSize: () => [0, 0],
            draw: () => {}  
        };
        
        let shapeWidget = {
            name: "shape_data",
            type: "hidden", 
            value: node.widgets?.find(w => w.name === "shape_data")?.value || node.widgets?.find(w => w.name === "shape_data")?.options?.default || "",
            hidden: true,
            computeSize: () => [0, 0],
            draw: () => {}  
        };
        
		let cropWidget = { name: "crop_data", type: "hidden", value: node.widgets?.find(w => w.name === "crop_data")?.value || node.widgets?.find(w => w.name === "crop_data")?.options?.default || "", hidden: true, computeSize: () => [0, 0], draw: () => {} };
        if (node.widgets) {
            const isNodes2_0 = !!document.querySelector("comfy-app") || 
                               !!document.querySelector(".comfy-vue") || 
                               (window.comfyAPI && window.comfyAPI.vue);

            if (!isNodes2_0) {
                const hideDom = (name) => {
                    const oldW = node.widgets.find(w => w.name === name);
                    if (oldW) {
                        const el = oldW.inputEl || oldW.element;
                        if (el) {
                            el.style.visibility = "hidden";
                            el.style.position = "absolute";
                            el.style.width = "0";
                            el.style.height = "0";
                            el.style.padding = "0";
                            el.style.margin = "0";
                            el.style.overflow = "hidden";
                            if (el.parentElement) {
                                el.parentElement.style.visibility = "hidden";
                                el.parentElement.style.position = "absolute";
                                el.parentElement.style.width = "0";
                                el.parentElement.style.height = "0";
                            }
                        }
                    }
                };
                hideDom("mask_data");
                hideDom("shape_data");
            }

            node.widgets = node.widgets.filter(w => w.name !== "mask_data" && w.name !== "shape_data" && w.name !== "mask_color_data" && w.name !== "crop_data" );
            node.widgets.push(maskWidget, shapeWidget, maskColorWidget, cropWidget);
        }
        
        requestAnimationFrame(() => {
            if (node.setDirtyCanvas) node.setDirtyCanvas(true, true);
        });

        const isImageConnected = () => {
            if (!node.inputs) return false;
            const imgInput = node.inputs.find(i => i.name === "image");
            return imgInput && imgInput.link !== null;
        };

        const container = $el("div.ee-container");

        // ====== ▶ 按钮：只运行到本节点（仅编辑界面显示）======
        const runToNode = async () => {
            if (!isImageConnected()) return;  
            try {
                const p = await app.graphToPrompt();
                const prompt = p.output;
                const selectedNodeId = String(node.id);
                const isolatedPrompt = {};
                const traceDependencies = (nodeId) => {
                    if (!prompt[nodeId] || isolatedPrompt[nodeId]) return;
                    isolatedPrompt[nodeId] = prompt[nodeId];
                    const inputs = prompt[nodeId].inputs;
                    for (let key in inputs) {
                        const val = inputs[key];
                        if (Array.isArray(val) && val.length === 2) {
                            traceDependencies(String(val[0]));
                        }
                    }
                };
                traceDependencies(selectedNodeId);
                if (Object.keys(isolatedPrompt).length === 0) {
                    console.warn("No dependencies found for node", selectedNodeId);
                    return;
                }
                const originalGraphToPrompt = app.graphToPrompt;
                app.graphToPrompt = async function (...args) {
                    const originalModes = new Map();
                    for (const n of app.graph._nodes) {
                        originalModes.set(n.id, n.mode);
                        if (!isolatedPrompt[String(n.id)]) {
                            n.mode = 2;
                        } else {
                            n.mode = 0;
                        }
                    }
                    try {
                        return await originalGraphToPrompt.apply(this, args);
                    } finally {
                        for (const n of app.graph._nodes) {
                            if (originalModes.has(n.id)) {
                                n.mode = originalModes.get(n.id);
                            }
                        }
                    }
                };
                try {
                    await app.queuePrompt(0, 1);
                } finally {
                    if (app.graphToPrompt !== originalGraphToPrompt) {
                        app.graphToPrompt = originalGraphToPrompt;
                    }
                }
            } catch (err) {
                console.error("Failed to execute isolated node:", err);
            }
        };
        const runBtn = $el("button.ee-btn", {
            textContent: "▶",
            title: " 只运行到本节点，加载连入的图像\n Run only to this node (load the connected input image)",
            style: {
                fontSize: "13px",
                width: "28px",
                height: "28px",
                padding: "0",
                display: "none",   
                alignItems: "center",
                justifyContent: "center",
                lineHeight: "1px",
                verticalAlign: "middle",
                color: "#ffffff",
                backgroundColor: "#007acc",
                border: "none",
                borderRadius: "3px",
                flexShrink: 0
            },
            onclick: () => runToNode()
        });

		
		// ====== 浏览来源切换（input / folder_path）======
        let browseSource = "fpath";          
        let inputDir = "";                   
        const isAbsPath = (p) => /^[a-zA-Z]:[\\/]/.test(p) || p.startsWith("\\\\") || p.startsWith("/");
        const splitPath = (p) => { const i = Math.max(p.lastIndexOf("/"), p.lastIndexOf("\\")); return i === -1 ? ["", p] : [p.slice(0, i), p.slice(i + 1)]; };
        const joinPath = (dir, name) => { const sep = dir.includes("\\") ? "\\" : "/"; return dir.endsWith("/") || dir.endsWith("\\") ? dir + name : dir + sep + name; };
        const ensureInputDir = async () => {
            if (inputDir) return inputDir;
            try { const res = await api.fetchApi("/element_easy/paths"); const d = await res.json(); if (d && d.input) inputDir = d.input; } catch (e) {}
            return inputDir;
        };
        const inputDirBtn = $el("button.ee-src-btn", {
            textContent: "Input",
            title: " 显示 ComfyUI\\input 目录中的图像\n Show images from the ComfyUI input directory",
            onclick: () => setBrowseSource("input")
        });
        const fpathBtn = $el("button.ee-src-btn.active", {
            textContent: "Fpath",
            title: " 显示 folder_path 参数指定目录中的图像\n Show images from the folder_path directory",
            onclick: () => setBrowseSource("fpath")
        });
        const setBrowseSource = async (src) => {
            browseSource = src;
            inputDirBtn.classList.toggle("active", src === "input");
            fpathBtn.classList.toggle("active", src === "fpath");
            if (src === "input") {
                inputDir = await ensureInputDir();
                if (!inputDir) { browseSource = "fpath"; inputDirBtn.classList.remove("active"); fpathBtn.classList.add("active"); return; }
                currentPath = inputDir;
            } else {
                currentPath = pathWidget ? pathWidget.value : "";
            }
            showGrid();
        };
        ensureInputDir();  


        // ====== Crop 控件 ======
        const cropBtn = $el("button.ee-btn.tool-btn", {
            textContent: "⛶ Crop",
            title: " 裁切模式：拖拽画出裁切框；框内拖动=移动；边缘拖动=调整大小\n Crop mode: drag to draw; drag inside = move; drag edges = resize",
            style: { width: "70px", height: "28px", padding: "0", lineHeight: "1px", verticalAlign: "middle" },
            onclick: () => setCropMode(!cropMode)
        });

        const cropDivInput = $el("input", {
            type: "number", min: 1, step: 1, value: 32,
            title: " 裁切框宽高的步进\n Step (px) for crop width/height",
            style: { width: "46px", height: "24px", background: "#222", color: "#fff", border: "1px solid #555", borderRadius: "3px", padding: "0 2px", fontSize: "12px" }
        });
        const cropRemoveBtn = $el("button.ee-btn", {
            textContent: "✕",
            title: " 移除裁切框\n Remove crop box",
            style: { width: "28px", height: "28px", padding: "0", fontSize: "14px" },
            onclick: () => { cropRect = null; cropDrag = null; exportCrop(); redrawCrop(); }
        });
        const cropGroup = $el("div.ee-toolbar-group", {
            style: {
                display: "none", alignItems: "center", gap: "4px", flexShrink: "0",
                position: "absolute", left: "50%", top: "50%", transform: "translate(-50%, -50%)",
                zIndex: "2",
                borderRight: "none", paddingRight: "0"   
            }
        }, [
            cropBtn,
            $el("span", { textContent: "div:", style: { color: "#aaa", fontSize: "11px" } }),
            cropDivInput,
            cropRemoveBtn
        ]);


        const header = $el("div.ee-header", { style: { display: "flex", gap: "4px", alignItems: "center", padding: "4px", backgroundColor: "transparent", position: "relative" } }, [
            runBtn,
            cropGroup,
            inputDirBtn,
            fpathBtn,
            $el("button.ee-btn", {
                textContent: "Return",
                id: "ee-btn-back",
                title: " 切换 浏览/编辑 界面\n Toggle between browse and editor view",
                style: {
                    background: "#007acc",
                    color: "#fff",
                    fontSize: "12px",
                    fontWeight: "bold",
                    padding: "0px 4px 0px 0px",
                    width: "70px",
                    height: "28px",
                    lineHeight: "28px",
                    verticalAlign: "middle",
                    marginLeft: "auto"
                },
                onclick: () => {
                    if (editorView.style.display !== "none") {
                        showGrid();
                    } else {
                        returnToEditor();
                    }
                }
            })
        ]);

        // ====== crop 组布局自适应 ======
        const returnBtn = header.querySelector("#ee-btn-back");
        const updateCropGroupLayout = () => {
            if (!cropGroup || cropGroup.style.display === "none") return;
            const headerW = header.clientWidth;
            const runW = runBtn.offsetWidth;
            const retW = returnBtn ? returnBtn.offsetWidth : 0;
            const cropW = cropGroup.offsetWidth;   
            const avail = headerW - runW - retW - 16;   // 16px 余量（gap+padding）
            if (cropW > 0 && cropW <= avail) {
                cropGroup.style.position = "absolute";
                cropGroup.style.left = "50%";
                cropGroup.style.top = "50%";
                cropGroup.style.transform = "translate(-50%, -50%)";
            } else {
                cropGroup.style.position = "static";
                cropGroup.style.left = "auto";
                cropGroup.style.top = "auto";
                cropGroup.style.transform = "none";
            }
        };

        const gridView = $el("div.ee-grid");

        const handleWheel = (e) => {
            if (gridView.contains(e.target)) {
                e.stopPropagation();          
                e.stopImmediatePropagation(); 
                e.preventDefault();           
                requestAnimationFrame(() => {
                    gridView.scrollTop += (e.deltaY || e.detail || e.wheelDelta);
                });
            }
        };

        window.addEventListener("wheel", handleWheel, { capture: true, passive: false });

        const oldOnRemoved = node.onRemoved;
        node.onRemoved = function() {
            window.removeEventListener("wheel", handleWheel, { capture: true, passive: false });
            if (oldOnRemoved) oldOnRemoved.apply(this, arguments);
        };
        
        const editorView = $el("div.ee-editor-wrap", { style: { display: "none" } });
        
        let drawTargetIsImage = false;
        let currentTool = "brush"; 
        let brushSize = 20;
        let maskColor = "#808080"; 
        let maskOpacity = 0.8;   
        let shapeColor = "#ff0000";
        let shapeOpacity = 1.0; 
        let shapeThickness = 5;
        let shapeFill = false;
        let isShiftPressed = false;
        let lastBrushPos = null;
        
        const brushCursor = $el("div.ee-brush-cursor");
        document.body.appendChild(brushCursor);
        
        const updateBrushCursor = () => {
            brushCursor.style.width = brushSize + "px";
            brushCursor.style.height = brushSize + "px";
        };
        updateBrushCursor();

        const setTool = (tool, btn) => {
            currentTool = tool;
            cropMode = false;
            cropBtn.classList.remove("active");   
            editorView.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            if (tool === 'brush' || tool === 'eraser') {
                maskCanvas.style.cursor = "none";
                brushCursor.style.display = "block";
                updateBrushCursor();
            } else {
                maskCanvas.style.cursor = "crosshair";
                brushCursor.style.display = "none";
            }
        };


        const toggleDrawTarget = (btn) => {
            drawTargetIsImage = !drawTargetIsImage;
            if (drawTargetIsImage) {
                btn.classList.add('active');
                btn.textContent = "Image";
            } else {
                btn.classList.remove('active');
                btn.textContent = "Mask";
            }
        };

        const BTN_WIDTH = "70px";        
        const BTN_HEIGHT = "28px";      
        const SLIDER_WIDTH = "60px";   
        
        const brushBtn = $el("button.ee-btn.tool-btn.active", { textContent: "🖌️ Brush", title: " 画笔(shift键画直线) \n Paintbrush (Shift key to draw straight lines)", style: { width: BTN_WIDTH, height: BTN_HEIGHT, padding: "4", lineHeight: "1px", verticalAlign: "middle" }, onclick: (e) => setTool('brush', e.target) });
        const eraserBtn = $el("button.ee-btn.tool-btn", { textContent: "🧹 Eraser", title: " 橡皮擦(shift键画直线) \n Eraser (use the shift key to draw a straight line)", style: { width: BTN_WIDTH, height: BTN_HEIGHT, padding: "0", lineHeight: "1px", verticalAlign: "middle" }, onclick: (e) => setTool('eraser', e.target) });
        const boxBtn = $el("button.ee-btn.tool-btn", { textContent: "🔳 Box", title: " 盒子/方框 (shift键画正方形) \n Box/Rectangle (use Shift key to draw a square)", style: { width: BTN_WIDTH, height: BTN_HEIGHT, padding: "0", lineHeight: "1px", verticalAlign: "middle" }, onclick: (e) => setTool('rect', e.target) });
        const circleBtn = $el("button.ee-btn.tool-btn", { textContent: "⭕ Circle", title: " 圆/椭圆 (shift键画正圆) \n Circle/Ellipse (use Shift key to draw a perfect circle)", style: { width: BTN_WIDTH, height: BTN_HEIGHT, padding: "0", lineHeight: "1px", verticalAlign: "middle" }, onclick: (e) => setTool('circle', e.target) });
        const toolBtnMap = { brush: brushBtn, eraser: eraserBtn, rect: boxBtn, circle: circleBtn };
		
		// ====== Mask/La/Undo/Clear ======
        const targetToggleBtn = $el("button.ee-btn", {
            textContent: "Mask",
            title: " 切换绘制目标 Mask(遮罩)/Image(图像)\n Toggle draw target between Mask and Image",
            style: { width: "56px", height: BTN_HEIGHT, padding: "0", lineHeight: "1px", verticalAlign: "middle" },
            onclick: (e) => toggleDrawTarget(e.currentTarget)
        });
        const lmaskBtn = $el("button.ee-btn", {
            id: "ee-btn-lmask",
            textContent: "La",
            title: " 将图像Alpha通道作为遮罩载入\n Load image alpha channel as mask",
            style: { width: "28px", height: BTN_HEIGHT, padding: "0", lineHeight: "1px", verticalAlign: "middle", fontSize: "11px" },
            onclick: () => {
                if (!imgEl || !imgEl.src || imgEl.src === transparentPixel) return;
                loadAlphaAsMask(imgEl.src, (alphaCanvas) => {
                    maskCtx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
                    maskCtx.drawImage(alphaCanvas, 0, 0);
                    exportMask();
                });
            }
        });
        const undoBtn = $el("button.ee-btn", {
            textContent: "↩️",
            title: " 撤销上一步绘制\n Undo last stroke",
            style: { width: "28px", height: BTN_HEIGHT, padding: "0", lineHeight: "1px", verticalAlign: "middle" },
            onclick: () => undo()
        });
        const clearBtn = $el("button.ee-btn", {
            textContent: "🗑️",
            title: " 清除全部遮罩与图形\n Clear all mask & shapes",
            style: { width: "28px", height: BTN_HEIGHT, padding: "0", lineHeight: "1px", verticalAlign: "middle" },
            onclick: () => clearAll()
        });


        const toolsGroup = $el("div.ee-toolbar-group", { style: { display: "flex", alignItems: "center", gap: "6px", borderRight: "1px solid #444", paddingRight: "4px" } }, [
            targetToggleBtn,
            lmaskBtn,
            brushBtn,
            eraserBtn,
            boxBtn,
            circleBtn,
            $el("label", { style: { color: "white", fontSize: "12px", cursor: "pointer", display: "flex", alignItems: "center", gap: "4px", height: BTN_HEIGHT, marginLeft: "6px" } }, [
                $el("input", { type: "checkbox", title: " 填充(方形或圆) \n Fill (box or circle)", style: { margin: "0" }, onchange: (e) => shapeFill = e.target.checked }),
                " S-fill"
            ]),
            undoBtn,
            clearBtn
        ]);

        
        const maskControlGroup = $el("div.ee-toolbar-group", {
            style: { display: "flex", alignItems: "center", gap: "4px", borderRight: "1px solid #444", paddingRight: "0px" }
        }, [
            $el("div.ee-color-wrapper", {}, [ $el("input", { type: "color", value: "#808080", title: " 遮罩颜色(不影响输出) \n Mask color(preview only)", oninput: (e) => maskColor = e.target.value }), $el("span.ee-color-overlay", { textContent: "M" }) ]),
            $el("div.ee-slider-container", {}, [ $el("span", { textContent: "B-size:" }), $el("input", { type: "range", min: 1, max: 100, value: 20, title: " 画笔半径 \n Brush size", style: { width: SLIDER_WIDTH }, oninput: (e) => { brushSize = parseInt(e.target.value); updateBrushCursor(); } }) ]),
            $el("div.ee-slider-container", {}, [ $el("span", { textContent: "M-op:" }), $el("input", { type: "range", min: 0.1, max: 1, step: 0.1, value: 0.8, title: " 遮罩透明度(不影响输出) \n Mask opacity (preview only)", style: { width: SLIDER_WIDTH }, oninput: (e) => { maskOpacity = parseFloat(e.target.value); maskCanvas.style.opacity = maskOpacity; } }) ])
        ]);
        
        const imageControlGroup = $el("div.ee-toolbar-group", {
            style: { display: "flex", alignItems: "center", gap: "4px", paddingRight: "0px" }
        }, [
            $el("div.ee-color-wrapper", {}, [ $el("input", { type: "color", value: "#ff0000", title: " 画在图像上的颜色 \n Image shape color", oninput: (e) => shapeColor = e.target.value }), $el("span.ee-color-overlay", { textContent: "I" }) ]),
            $el("div.ee-slider-container", {}, [ $el("span", { textContent: "I-op:" }), $el("input", { type: "range", min: 0.1, max: 1, step: 0.1, value: 1.0, title: " 画在图像上的透明度 \n Image opacity (affects output)", style: { width: SLIDER_WIDTH }, oninput: (e) => { shapeOpacity = parseFloat(e.target.value); } }) ]),
            $el("div.ee-slider-container", {}, [ $el("span", { textContent: "S-edge:" }), $el("input", { type: "range", min: 1, max: 50, value: 5, title: " 盒子/圆的外框宽度 \n Edge width", style: { width: SLIDER_WIDTH }, oninput: (e) => shapeThickness = parseInt(e.target.value) }) ])
        ]);
        
        const toolbar = $el("div.ee-toolbar");
        const toolbarRow1 = $el("div.ee-toolbar-row");
        toolbarRow1.appendChild(toolsGroup);
        toolbar.appendChild(toolbarRow1);
        
        const toolbarRow2 = $el("div.ee-toolbar-row");
        toolbarRow2.appendChild(maskControlGroup);
        toolbarRow2.appendChild(imageControlGroup);
        toolbar.appendChild(toolbarRow2);

        const imgEl = $el("img");
        const shapeCanvas = document.createElement("canvas");
        shapeCanvas.className = "shape-canvas";
        const shapeCtx = shapeCanvas.getContext("2d");

        const maskCanvas = document.createElement("canvas");
        maskCanvas.className = "mask-canvas";
        const maskCtx = maskCanvas.getContext("2d");
        maskCanvas.style.opacity = maskOpacity;

        const canvasContainer = $el("div.ee-canvas-container", {
            style: { userSelect: "none", webkitUserSelect: "none" }
        }, [imgEl, shapeCanvas, maskCanvas]);
        
        imgEl.draggable = false;
        imgEl.style.webkitUserDrag = "none";
        imgEl.style.userDrag = "none";
        canvasContainer.onselectstart = () => false;
        canvasContainer.ondragstart = () => false;
        
        editorView.appendChild(toolbar);
        editorView.appendChild(canvasContainer);
        
        container.appendChild(header);
        container.appendChild(gridView);
        container.appendChild(editorView);

        container.style.width = "100%";
        container.style.height = "100%";
        container.style.position = "absolute"; 
        container.style.inset = "0";

        const wrapper = document.createElement("div");
        wrapper.style.position = "relative";
        wrapper.style.width = "100%";
        wrapper.style.height = "100%";
        wrapper.appendChild(container);

        const widget = node.addDOMWidget("ee_ui", "div", wrapper);

        if (widget?.element) {
            widget.element.style.height = "100%";
            widget.element.style.width = "100%";
            widget.element.style.display = "flex";
            
            setTimeout(() => {
                const parent = widget.element.parentElement;
                if (parent) {
                    parent.style.flex = "1";
                    parent.style.display = "flex";
                    parent.style.flexDirection = "column";
                    parent.style.overflow = "hidden"; 
                }
            }, 50);
        }

        const MIN_NODE_WIDTH = 280;
        const MIN_NODE_HEIGHT = 350; 
        const NON_WIDGET_HEIGHT = 150;
        const MIN_WIDGET_HEIGHT = 200;
        let lastWidgetHeight = MIN_WIDGET_HEIGHT;
        
        const origComputeSize = node.computeSize;
        node.computeSize = function(out) {
            let size = origComputeSize ? origComputeSize.apply(this, arguments) : [MIN_NODE_WIDTH, MIN_NODE_HEIGHT];
            if (size[0] < MIN_NODE_WIDTH) size[0] = MIN_NODE_WIDTH;
            if (size[1] < MIN_NODE_HEIGHT) size[1] = MIN_NODE_HEIGHT;
            return size;
        };
        
        const onResize = node.onResize;
        node.onResize = function(size) {
            if (onResize) onResize.apply(this, arguments);
            const availableHeight = Math.max(0, size[1] - NON_WIDGET_HEIGHT);
            lastWidgetHeight = availableHeight || MIN_WIDGET_HEIGHT;
            
            if (editorView.style.display !== "none") requestAnimationFrame(resizeCanvas);
            updateToolbarLayout(size[0]);
        };
        
        const updateToolbarLayout = (containerWidth) => {
            const neededWidth = 866; 
            if (containerWidth >= neededWidth) {
                toolbar.style.flexDirection = "row";
                toolbar.style.flexWrap = "nowrap";
                toolbarRow2.style.marginLeft = "auto";
            } else {
                toolbar.style.flexDirection = "column";
                toolbar.style.flexWrap = "wrap";
                toolbarRow2.style.marginLeft = "0";
            }
			updateCropGroupLayout();
        };

        let currentPath = "";
        let originalImageSize = { w: 1024, h: 1024 };
        let history = []; 
		
		// ====== Crop 状态与逻辑 ======
        let cropMode = false;
        let cropRect = null;        
        let cropDrag = null;
        
        const cropCanvas = document.createElement("canvas");
        cropCanvas.className = "crop-canvas";
        cropCanvas.style.cssText = "position:absolute;left:0;top:0;pointer-events:none;z-index:3;";
        const cropCtx = cropCanvas.getContext("2d");
        canvasContainer.appendChild(cropCanvas);
        
        const getScaleX = () => maskCanvas.width / (maskCanvas.getBoundingClientRect().width || maskCanvas.width);
        const cropDivNow = () => Math.max(1, parseInt(cropDivInput?.value) || 1);
        const snapV = (v, d) => Math.max(0, Math.round(v / d) * d);
        const snapQ = (v, d) => Math.round(v / d) * d;
        
        const exportCrop = () => {
            cropWidget.value = cropRect ? JSON.stringify([Math.round(cropRect.x), Math.round(cropRect.y), Math.round(cropRect.w), Math.round(cropRect.h)]) : "";
            try { if (node.graph && node.graph.change) node.graph.change(); } catch (e) {}
        };

        
        const redrawCrop = () => {
            if (!cropCtx) return;
            cropCtx.setTransform(1, 0, 0, 1, 0, 0);
            cropCtx.clearRect(0, 0, cropCanvas.width, cropCanvas.height);
            if (!cropRect) return;
            const W = cropCanvas.width, H = cropCanvas.height, r = cropRect;
            cropCtx.fillStyle = "rgba(0,0,0,0.45)";
            cropCtx.fillRect(0, 0, W, Math.max(0, r.y));
            cropCtx.fillRect(0, r.y + r.h, W, Math.max(0, H - r.y - r.h));
            cropCtx.fillRect(0, r.y, Math.max(0, r.x), r.h);
            cropCtx.fillRect(r.x + r.w, r.y, Math.max(0, W - r.x - r.w), r.h);
            cropCtx.strokeStyle = "#57a8ff";
            cropCtx.lineWidth = Math.max(2, 2 * getScaleX());
            cropCtx.strokeRect(r.x, r.y, r.w, r.h);
        };
		
		// ====== 从 crop_data 恢复裁切框======
        const restoreCrop = () => {
            try {
                const raw = cropWidget ? (cropWidget.value || "") : "";
                if (!raw || !raw.startsWith("[")) return;
                const arr = JSON.parse(raw);
                if (!Array.isArray(arr) || arr.length !== 4) return;
                const [x, y, w, h] = arr.map(v => Math.max(0, Math.round(Number(v) || 0)));
                if (w <= 0 || h <= 0) return;
                const W = cropCanvas.width || 1, H = cropCanvas.height || 1;
                const cx = Math.min(Math.max(0, x), W - 1);
                const cy = Math.min(Math.max(0, y), H - 1);
                cropRect = { x: cx, y: cy, w: Math.max(1, Math.min(w, W - cx)), h: Math.max(1, Math.min(h, H - cy)) };
                exportCrop();
                redrawCrop();
            } catch (e) {}
        };

		
        const setCropMode = (on) => {
            cropMode = on;
            cropBtn.classList.toggle("active", on);
            if (on) {
                editorView.querySelectorAll('.tool-btn').forEach(b => b.classList.remove('active'));
                brushCursor.style.display = "none";
                maskCanvas.style.cursor = "crosshair";
            } else {
                const tb = toolBtnMap[currentTool];
                if (tb) tb.classList.add("active");
                if (currentTool === 'brush' || currentTool === 'eraser') {
                    maskCanvas.style.cursor = "none";
                    brushCursor.style.display = "block";
                } else {
                    maskCanvas.style.cursor = "crosshair";
                }
            }
            redrawCrop();
        };
        
        const cropInRect = (p) => cropRect && p.x >= cropRect.x && p.x <= cropRect.x + cropRect.w && p.y >= cropRect.y && p.y <= cropRect.y + cropRect.h;
        
        const cropEdgeAt = (p) => {
            if (!cropRect) return null;
            const tol = Math.max(3, 8 * getScaleX());
            const r = cropRect;
            if (p.x < r.x - tol || p.x > r.x + r.w + tol || p.y < r.y - tol || p.y > r.y + r.h + tol) return null;
            const nearL = Math.abs(p.x - r.x) <= tol;
            const nearR = Math.abs(p.x - (r.x + r.w)) <= tol;
            const nearT = Math.abs(p.y - r.y) <= tol;
            const nearB = Math.abs(p.y - (r.y + r.h)) <= tol;
            const h = nearL ? "l" : nearR ? "r" : "";
            const v = nearT ? "t" : nearB ? "b" : "";
            return (h || v) ? { h, v } : null;
        };
        
        const cropCursorFor = (ed) => {
            if ((ed.h === "l" && ed.v === "t") || (ed.h === "r" && ed.v === "b")) return "nwse-resize";
            if ((ed.h === "r" && ed.v === "t") || (ed.h === "l" && ed.v === "b")) return "nesw-resize";
            if (ed.h) return "ew-resize";
            return "ns-resize";
        };
        
        const cropApplyResize = (p, dg) => {
            const d = cropDivNow(), o = dg.orig;
            let x0 = o.x, y0 = o.y, x1 = o.x + o.w, y1 = o.y + o.h;
            if (dg.ed.h === "l") x0 = Math.min(Math.max(0, snapQ(p.x, d)), x1 - d);
            else if (dg.ed.h === "r") x1 = Math.max(Math.min(maskCanvas.width, snapQ(p.x, d)), x0 + d);
            if (dg.ed.v === "t") y0 = Math.min(Math.max(0, snapQ(p.y, d)), y1 - d);
            else if (dg.ed.v === "b") y1 = Math.max(Math.min(maskCanvas.height, snapQ(p.y, d)), y0 + d);
            cropRect = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
        };
        
        const updateCropDrag = (pos) => {
            if (!cropDrag) return;
            const W = maskCanvas.width, H = maskCanvas.height;
            if (cropDrag.kind === "move") {
                cropRect.x = Math.round(Math.max(0, Math.min(W - cropRect.w, pos.rawX - cropDrag.dx)));
                cropRect.y = Math.round(Math.max(0, Math.min(H - cropRect.h, pos.rawY - cropDrag.dy)));
            } else if (cropDrag.kind === "resize") {
                cropApplyResize(pos, cropDrag);
            } else {
                const d = cropDrag.d;
                const x = snapV(Math.min(cropDrag.sx, pos.rawX), d), y = snapV(Math.min(cropDrag.sy, pos.rawY), d);
                const w = Math.max(d, Math.round(Math.abs(pos.rawX - cropDrag.sx) / d) * d);
                const h = Math.max(d, Math.round(Math.abs(pos.rawY - cropDrag.sy) / d) * d);
                cropRect = { x, y, w: Math.min(w, W - x), h: Math.min(h, H - y) };
            }
            redrawCrop();
        };

        const resizeObserver = new ResizeObserver((entries) => {
            for (let entry of entries) {
                const { width, height } = entry.contentRect;
                if (width > 0 && height > 0 && editorView.style.display !== "none") {
                    resizeCanvas();
                }
            }
        });
        resizeObserver.observe(canvasContainer);

        const resizeCanvas = () => {
            if (editorView.style.display === "none") return;
            const containerWidth = canvasContainer.clientWidth;
            const containerHeight = canvasContainer.clientHeight;
            if (containerWidth === 0 || containerHeight === 0) return;
            const imgRatio = originalImageSize.w / originalImageSize.h;
            const containerRatio = containerWidth / containerHeight;
            let displayWidth, displayHeight, offsetX, offsetY;
            if (imgRatio > containerRatio) {
                displayWidth = containerWidth;
                displayHeight = containerWidth / imgRatio;
                offsetX = 0;
                offsetY = (containerHeight - displayHeight) / 2;
            } else {
                displayHeight = containerHeight;
                displayWidth = containerHeight * imgRatio;
                offsetX = (containerWidth - displayWidth) / 2;
                offsetY = 0;
            }
            const imgStyles = { position: "absolute", left: "0", top: "0", width: displayWidth + "px", height: displayHeight + "px", transform: `translate(${offsetX}px, ${offsetY}px)`, objectFit: "fill", maxWidth: "none", maxHeight: "none" };
            const canvasStyles = { position: "absolute", left: "0", top: "0", width: displayWidth + "px", height: displayHeight + "px", transform: `translate(${offsetX}px, ${offsetY}px)` };
            Object.assign(imgEl.style, imgStyles);
            Object.assign(shapeCanvas.style, canvasStyles);
            Object.assign(maskCanvas.style, canvasStyles);
            Object.assign(cropCanvas.style, canvasStyles);
            if (shapeCanvas.width !== originalImageSize.w || shapeCanvas.height !== originalImageSize.h) {
                shapeCanvas.width = originalImageSize.w;
                shapeCanvas.height = originalImageSize.h;
                maskCanvas.width = originalImageSize.w;
                maskCanvas.height = originalImageSize.h;
                cropCanvas.width = originalImageSize.w;
                cropCanvas.height = originalImageSize.h;
                if (cropRect) {
                    cropRect.w = Math.min(cropRect.w, cropCanvas.width);
                    cropRect.h = Math.min(cropRect.h, cropCanvas.height);
                    cropRect.x = Math.max(0, Math.min(cropRect.x, cropCanvas.width - cropRect.w));
                    cropRect.y = Math.max(0, Math.min(cropRect.y, cropCanvas.height - cropRect.h));
                    exportCrop();
                }
                redrawCrop();
                restoreData();
            }
        };

		// UI连线状态自适应更新
        const updateMode = () => {
            const connected = isImageConnected();
            if (connected) {
                gridView.style.display = "none";
                editorView.style.display = "flex";
                runBtn.style.display = "flex";
                cropGroup.style.display = "flex";
				requestAnimationFrame(updateCropGroupLayout);
                inputDirBtn.style.display = "none";
                fpathBtn.style.display = "none";
                lmaskBtn.style.display = "block";
                targetToggleBtn.style.display = "inline-block";
                undoBtn.style.display = "inline-block";
                clearBtn.style.display = "inline-block";
            } else {
                showGrid();
            }
        };

		
		let lastImageLink = null;
        const transparentPixel = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
        
        const origOnConnectionsChange = node.onConnectionsChange;
        node.onConnectionsChange = function(type, index, connected, link_info) {
            if (origOnConnectionsChange) origOnConnectionsChange.apply(this, arguments);
            const isInputChange = (type === LiteGraph.INPUT || type === "input");
            if (!isInputChange) { return; }
            updateMode();
            if (this.inputs && index >= 0 && index < this.inputs.length) {
                const input = this.inputs[index];
                if (input.name === "image") {
                    if (connected && link_info) {
                        if (lastImageLink !== link_info.id) {
                            clearAll();
                            if (imgEl && imgEl.src && imgEl.src.includes("type=temp")) {
                                imgEl.src = transparentPixel;
                            }
                            lastImageLink = link_info.id;
                            editorCtx = null;
                        }
                    } else {
                        clearAll();
                        if (imgEl && imgEl.src && imgEl.src.includes("type=temp")) {
                            imgEl.src = transparentPixel;
                        }
                        lastImageLink = null;
                        editorCtx = null;
                    }
                }
            }
        };


        const origOnExecuted = node.onExecuted;
        node.onExecuted = function(message) {
            if (origOnExecuted) origOnExecuted.apply(this, arguments);
            if (message && message.ee_preview && message.ee_preview.length > 0) {
                const imgInfo = message.ee_preview[0];
                const imgSrc = `/view?filename=${encodeURIComponent(imgInfo.filename)}&type=${imgInfo.type}&t=${Date.now()}`;
                const tempImg = new Image();
                tempImg.onload = () => {
                    originalImageSize.w = tempImg.width;
                    originalImageSize.h = tempImg.height;
                    imgEl.src = imgSrc;
                    setTimeout(() => { resizeCanvas(); }, 50);
                };
                tempImg.src = imgSrc;
                gridView.style.display = "none";
                editorView.style.display = "flex";
                runBtn.style.display = "flex";
                cropGroup.style.display = "flex";
				requestAnimationFrame(updateCropGroupLayout);
                inputDirBtn.style.display = "none";
                fpathBtn.style.display = "none";
                lmaskBtn.style.display = "block";
                targetToggleBtn.style.display = "inline-block";
                undoBtn.style.display = "inline-block";
                clearBtn.style.display = "inline-block";
                editorCtx = { type: "preview" };
            }
        };



        const loadImages = async (restoreScroll = 0) => {
            currentPath = (browseSource === "input" && inputDir) ? inputDir : pathWidget.value;
            gridView.innerHTML = "<div style='color:white; padding:10px;'>loading...</div>";
            try {
                const res = await api.fetchApi("/element_easy/images", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ folder_path: currentPath, sort_method: sortWidget?.value || "newest_first" }) });
                const images = await res.json();
                renderGrid(Object.keys(images));
                if (restoreScroll > 0) requestAnimationFrame(() => { gridView.scrollTop = restoreScroll; });
            } catch (err) {
                gridView.innerHTML = "<div style='color:red;'>Loading failed, please check the directory</div>";
            }
        };

        const renderGrid = (filenames) => {
            gridView.innerHTML = "";
            filenames.forEach(filename => {
                const item = $el("div.ee-grid-item", {
                    onclick: () => {
                        lastScrollTop = gridView.scrollTop;
                        localStorage.setItem('ee_scroll_' + node.id + '_' + currentPath, lastScrollTop.toString());
                        openEditor(filename);   
                    }
                }, [
                    $el("img", { src: `/element_easy/view?folder_path=${encodeURIComponent(currentPath)}&filename=${encodeURIComponent(filename)}` })
                ]);
                const selVal = imageWidget ? (imageWidget.value || "") : "";
                let matched = false;
                if (selVal) {
                    if (browseSource === "input" && inputDir) {
                        matched = selVal === joinPath(inputDir, filename);
                    } else {
                        matched = selVal === filename || (pathWidget && selVal === joinPath(pathWidget.value, filename));
                    }
                }
                if (matched) item.classList.add("selected");
                gridView.appendChild(item);
            });
        };


        const showGrid = () => {
            currentPath = (browseSource === "input" && inputDir) ? inputDir : (pathWidget ? pathWidget.value : currentPath);
            gridView.style.display = "grid";
            editorView.style.display = "none";
            runBtn.style.display = "none";
            cropGroup.style.display = "none";
            inputDirBtn.style.display = "inline-block";
            fpathBtn.style.display = "inline-block";
            lmaskBtn.style.display = "none";
            targetToggleBtn.style.display = "none";
            undoBtn.style.display = "none";
            clearBtn.style.display = "none";
            const savedScroll = localStorage.getItem('ee_scroll_' + node.id + '_' + currentPath);
            loadImages(savedScroll ? parseInt(savedScroll, 10) : 0);
        };
        


        const loadAlphaAsMask = (imgSrc, callback) => {
            const tempImg = new Image();
            tempImg.crossOrigin = "anonymous";
            tempImg.onload = () => {
                const tempCanvas = document.createElement('canvas');
                tempCanvas.width = tempImg.width;
                tempCanvas.height = tempImg.height;
                const tempCtx = tempCanvas.getContext('2d');
                tempCtx.drawImage(tempImg, 0, 0);
                const imageData = tempCtx.getImageData(0, 0, tempCanvas.width, tempCanvas.height);
                const data = imageData.data;
                const alphaCanvas = document.createElement('canvas');
                alphaCanvas.width = tempImg.width;
                alphaCanvas.height = tempImg.height;
                const alphaCtx = alphaCanvas.getContext('2d');
                const alphaImageData = alphaCtx.createImageData(tempImg.width, tempImg.height);
                const alphaData = alphaImageData.data;
                for (let i = 0; i < data.length; i += 4) {
                    alphaData[i] = 128;       
                    alphaData[i + 1] = 128;   
                    alphaData[i + 2] = 128;   
                    alphaData[i + 3] = data[i + 3]; 
                }
                alphaCtx.putImageData(alphaImageData, 0, 0);
                callback(alphaCanvas);
            };
            tempImg.src = imgSrc;
        };

        const openEditor = (filename) => {
            const savedScroll = localStorage.getItem('ee_scroll_' + node.id + '_' + currentPath);
            lastScrollTop = savedScroll ? parseInt(savedScroll, 10) : 0;
        
            let viewFolder = currentPath;
            let viewName = filename;
            let storageValue = filename;
            if (isAbsPath(filename)) {
                const parts = splitPath(filename);
                viewFolder = parts[0];
                viewName = parts[1];
                storageValue = filename;
            } else if (browseSource === "input" && inputDir) {
                storageValue = joinPath(inputDir, filename);
            }
        
            const isSwitchingImage = imageWidget && imageWidget.value !== storageValue;
            if (imageWidget) imageWidget.value = storageValue;
            localStorage.setItem('ee_image_' + node.id + '_' + currentPath, storageValue);
            editorCtx = { type: "file", value: storageValue, folder: viewFolder };
        
            if (isSwitchingImage) {
                maskCtx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
                shapeCtx.clearRect(0, 0, shapeCanvas.width, shapeCanvas.height);
                maskWidget.value = "";
                shapeWidget.value = "";
                if (maskColorWidget) maskColorWidget.value = "";
                history = [];
                cropRect = null; cropDrag = null; exportCrop(); redrawCrop();
            }
        
            gridView.style.display = "none";
            editorView.style.display = "flex";
            runBtn.style.display = "flex";
            cropGroup.style.display = "flex";
			requestAnimationFrame(updateCropGroupLayout);
            inputDirBtn.style.display = "none";
            fpathBtn.style.display = "none";
            lmaskBtn.style.display = "block";
            targetToggleBtn.style.display = "inline-block";
            undoBtn.style.display = "inline-block";
            clearBtn.style.display = "inline-block";
        
            const imgSrc = `/element_easy/view?folder_path=${encodeURIComponent(viewFolder)}&filename=${encodeURIComponent(viewName)}`;
            const tempImg = new Image();
            tempImg.onload = () => {
                originalImageSize.w = tempImg.width;
                originalImageSize.h = tempImg.height;
                imgEl.src = imgSrc;
                setTimeout(() => resizeCanvas(), 50);
            };
            tempImg.src = imgSrc;
        };


        const showEditorChrome = () => {
            gridView.style.display = "none";
            editorView.style.display = "flex";
            runBtn.style.display = "flex";
            cropGroup.style.display = "flex";
			requestAnimationFrame(updateCropGroupLayout);
            inputDirBtn.style.display = "none";
            fpathBtn.style.display = "none";
            lmaskBtn.style.display = "block";
            targetToggleBtn.style.display = "inline-block";
            undoBtn.style.display = "inline-block";
            clearBtn.style.display = "inline-block";
        };

        
        const returnToEditor = () => {
            const connected = isImageConnected();
            if (!editorCtx) {
                if (connected) showEditorChrome();  
                return;                             
            }
            if (editorCtx.type === "preview") {
                showEditorChrome();                 
                setTimeout(() => resizeCanvas(), 50);
                return;
            }
            const val = editorCtx.value;           
            if (isAbsPath(val)) {
                openEditor(val);                    
            } else {
                currentPath = pathWidget ? pathWidget.value : currentPath;
                openEditor(val);                    
            }
        };


        // ====== 拖拽导入（资源管理器 / 浏览器）到编辑器界面 ======
        const dropOverlay = $el("div.ee-drop-overlay", { textContent: "⬇ 释放导入图像 → 保存到 ComfyUI/input" });
        editorView.appendChild(dropOverlay);
        
        const uploadAndSelect = async (blob, name) => {
            try {
                const fd = new FormData();
                fd.append("image", blob, name || "dropped.png");
                const res = await api.fetchApi("/element_easy/upload", { method: "POST", body: fd });
                if (!res.ok) throw new Error("HTTP " + res.status);
                const data = await res.json();
                if (!data || !data.full) throw new Error(data && data.error ? data.error : "invalid response");
                await ensureInputDir();
                openEditor(data.full);   
            } catch (err) {
                console.error("Drag-drop import failed:", err);
                alert("导入拖拽图像失败 / Failed to import dropped image: " + err.message);
            }
        };
        
        const isImageFile = (f) => (f.type && f.type.startsWith("image/")) || /\.(png|jpe?g|gif|bmp|webp|tiff?)$/i.test(f.name || "");
        
        editorView.addEventListener("dragenter", (e) => {
            e.preventDefault(); e.stopPropagation();
            if (editorView.style.display !== "none") dropOverlay.style.display = "flex";
        });
        editorView.addEventListener("dragover", (e) => {
            e.preventDefault(); e.stopPropagation();
            if (editorView.style.display !== "none") dropOverlay.style.display = "flex";
        });
        editorView.addEventListener("dragleave", (e) => {
            e.preventDefault();
            const rt = e.relatedTarget;
            if (!rt || !editorView.contains(rt)) dropOverlay.style.display = "none";
        });
        editorView.addEventListener("drop", async (e) => {
            e.preventDefault(); e.stopPropagation();
            dropOverlay.style.display = "none";
            if (editorView.style.display === "none") return;   
            const dt = e.dataTransfer;
            if (!dt) return;
            if (dt.files && dt.files.length > 0) {
                const file = Array.from(dt.files).find(isImageFile);
                if (!file) { alert("请拖入图像文件 / Please drop an image file"); return; }
                await uploadAndSelect(file, file.name);
                return;
            }
            const url = (dt.getData("text/uri-list") || dt.getData("text/plain") || "").trim();
            if (url && /^(https?|data):/i.test(url)) {
                try {
                    const resp = await fetch(url, { mode: "cors" });
                    const blob = await resp.blob();
                    let name = "dropped.png";
                    try {
                        const last = decodeURIComponent(url.split("/").pop().split("?")[0]);
                        if (last) name = /\.[a-z0-9]+$/i.test(last) ? last : last + ".png";
                    } catch (_) {}
                    await uploadAndSelect(blob, name);
                } catch (err) {
                    alert("无法直接获取网页图片（受 CORS 限制），请先保存到本地后拖入 / Cannot fetch web image (CORS). Save it locally and drag the file instead.");
                }
            }
        });

        // ====== Ctrl+V 粘贴剪贴板图像（window 捕获阶段，优先于 ComfyUI 默认行为）======
        const handlePaste = async (e) => {
            if (editorView.style.display === "none") return;   
            const sel = app.canvas && app.canvas.selected_nodes;
            const isSelected = !!(sel && (sel[node.id] || Object.values(sel).includes(node)));
            if (!isSelected) return;                           
            const ae = document.activeElement;
            if (ae && (ae.tagName === "INPUT" || ae.tagName === "TEXTAREA" || ae.isContentEditable)) return;
            const items = e.clipboardData && e.clipboardData.items;
            if (!items) return;
            let file = null;
            for (const it of items) {
                if (it.type && it.type.startsWith("image/")) { file = it.getAsFile(); break; }
            }
            if (!file) return;                                 
            e.preventDefault();
            e.stopImmediatePropagation();
            e.stopPropagation();
            const ext = (file.type.split("/")[1] || "png").toLowerCase().replace("jpeg", "jpg");
            const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
            const name = `pasted_${stamp}_${node.id}.${ext}`;
            await uploadAndSelect(file, name);
        };
        window.addEventListener("paste", handlePaste, true);   

        let isDrawing = false, isWindowTracking = false, startX = 0, startY = 0, snapshot = null, currentPos = { x: 0, y: 0 };

        const getPos = (e) => {
            const canvasRect = maskCanvas.getBoundingClientRect();
            const relativeX = e.clientX - canvasRect.left;
            const relativeY = e.clientY - canvasRect.top;
            const scaleX = maskCanvas.width / canvasRect.width;
            const scaleY = maskCanvas.height / canvasRect.height;
            const rawX = relativeX * scaleX;
            const rawY = relativeY * scaleY;
            const isInside = rawX >= 0 && rawX <= maskCanvas.width && rawY >= 0 && rawY <= maskCanvas.height;
            return { x: Math.max(0, Math.min(maskCanvas.width, rawX)), y: Math.max(0, Math.min(maskCanvas.height, rawY)), rawX: rawX, rawY: rawY, isInside: isInside };
        };

        const saveHistory = () => {
            history.push({ mask: maskCanvas.toDataURL(), shape: shapeCanvas.toDataURL() });
            if (history.length > 20) history.shift();
        };

        const exportMask = () => {
            maskColorWidget.value = maskCanvas.toDataURL('image/png');
            const outCanvas = document.createElement('canvas');
            outCanvas.width = maskCanvas.width;
            outCanvas.height = maskCanvas.height;
            const outCtx = outCanvas.getContext('2d');
            outCtx.drawImage(maskCanvas, 0, 0);
            outCtx.globalCompositeOperation = "source-in";
            outCtx.fillStyle = 'white';
            outCtx.fillRect(0, 0, outCanvas.width, outCanvas.height);
            outCtx.globalCompositeOperation = "destination-over";
            outCtx.fillStyle = 'black';
            outCtx.fillRect(0, 0, outCanvas.width, outCanvas.height);
            maskWidget.value = outCanvas.toDataURL('image/png');
        };

        const exportShapes = () => { shapeWidget.value = shapeCanvas.toDataURL('image/png'); };

        window.addEventListener('keydown', (e) => { if (e.key === 'Shift') isShiftPressed = true; });
        window.addEventListener('keyup', (e) => { if (e.key === 'Shift') isShiftPressed = false; });

        maskCanvas.addEventListener("mousedown", (e) => {
            const pos = getPos(e);
            if (!pos.isInside) return;
			    if (cropMode) {
                    isDrawing = true;
                    const d = cropDivNow();
                    const ed = cropEdgeAt(pos);
                    if (ed && cropRect) cropDrag = { kind: "resize", ed, orig: { ...cropRect } };
                    else if (cropRect && cropInRect(pos)) cropDrag = { kind: "move", dx: pos.rawX - cropRect.x, dy: pos.rawY - cropRect.y };
                    else {
                        cropRect = { x: snapV(pos.rawX, d), y: snapV(pos.rawY, d), w: d, h: d };
                        cropDrag = { kind: "new", sx: Math.round(pos.rawX), sy: Math.round(pos.rawY), d };
                    }
                    redrawCrop();
                    window.addEventListener("mousemove", handleWindowMouseMove);
                    window.addEventListener("mouseup", handleWindowMouseUp);
                    isWindowTracking = true;
                    return;
                }

            isDrawing = true;
            saveHistory();
            startX = pos.rawX; startY = pos.rawY;
            lastBrushPos = { x: pos.rawX, y: pos.rawY };
            currentPos = { x: pos.rawX, y: pos.rawY, isInside: true };
            const targetCtx = drawTargetIsImage ? shapeCtx : maskCtx;
            const targetCanvas = drawTargetIsImage ? shapeCanvas : maskCanvas;
            snapshot = targetCtx.getImageData(0, 0, targetCanvas.width, targetCanvas.height);
            if (currentTool === 'brush' || currentTool === 'eraser') {
                targetCtx.lineCap = "round"; targetCtx.lineJoin = "round"; targetCtx.beginPath(); targetCtx.moveTo(pos.rawX, pos.rawY);
            }
            window.addEventListener("mousemove", handleWindowMouseMove);
            window.addEventListener("mouseup", handleWindowMouseUp);
            isWindowTracking = true;
        });

        maskCanvas.addEventListener("mouseenter", (e) => {
            if (!cropMode && (currentTool === 'brush' || currentTool === 'eraser')) brushCursor.style.display = "block";
        });

        maskCanvas.addEventListener("mouseleave", () => { brushCursor.style.display = "none"; });

        let cursorRafId = null;
        
        const updateCursorPosition = (e) => {
            const containerRect = canvasContainer.getBoundingClientRect();
            const containerWidth = containerRect.width; const containerHeight = containerRect.height;
            const imgRatio = originalImageSize.w / originalImageSize.h; const containerRatio = containerWidth / containerHeight;
            let displayWidth, displayHeight, offsetX, offsetY;
            if (imgRatio > containerRatio) { displayWidth = containerWidth; displayHeight = containerWidth / imgRatio; offsetX = 0; offsetY = (containerHeight - displayHeight) / 2; } 
            else { displayHeight = containerHeight; displayWidth = containerHeight * imgRatio; offsetX = (containerWidth - displayWidth) / 2; offsetY = 0; }
            const cursorX = Math.max(containerRect.left + offsetX, Math.min(containerRect.left + offsetX + displayWidth, e.clientX));
            const cursorY = Math.max(containerRect.top + offsetY, Math.min(containerRect.top + offsetY + displayHeight, e.clientY));
            brushCursor.style.left = cursorX + "px"; brushCursor.style.top = cursorY + "px";
        };

        const updateDrawing = (pos) => {
            const scaleX = maskCanvas.width / maskCanvas.getBoundingClientRect().width;
            const targetCtx = drawTargetIsImage ? shapeCtx : maskCtx;
            const drawColor = drawTargetIsImage ? shapeColor : maskColor;
            const drawOpacity = drawTargetIsImage ? shapeOpacity : 1.0;
            
            if (currentTool === 'brush') {
                targetCtx.lineWidth = brushSize * scaleX; targetCtx.lineCap = "round"; targetCtx.lineJoin = "round";
                targetCtx.globalCompositeOperation = "source-over"; targetCtx.strokeStyle = drawColor; targetCtx.globalAlpha = drawOpacity;
                if (isShiftPressed && lastBrushPos) { targetCtx.putImageData(snapshot, 0, 0); targetCtx.beginPath(); targetCtx.moveTo(startX, startY); targetCtx.lineTo(pos.rawX, pos.rawY); targetCtx.stroke(); } 
                else { targetCtx.lineTo(pos.rawX, pos.rawY); targetCtx.stroke(); targetCtx.beginPath(); targetCtx.moveTo(pos.rawX, pos.rawY); lastBrushPos = { x: pos.rawX, y: pos.rawY }; }
                targetCtx.globalAlpha = 1.0;
            } else if (currentTool === 'eraser') {
                targetCtx.lineWidth = brushSize * scaleX; targetCtx.lineCap = "round"; targetCtx.lineJoin = "round";
                targetCtx.globalCompositeOperation = "destination-out"; targetCtx.globalAlpha = 1.0;
                if (isShiftPressed && lastBrushPos) { targetCtx.putImageData(snapshot, 0, 0); targetCtx.beginPath(); targetCtx.moveTo(startX, startY); targetCtx.lineTo(pos.rawX, pos.rawY); targetCtx.stroke(); } 
                else { targetCtx.lineTo(pos.rawX, pos.rawY); targetCtx.stroke(); targetCtx.beginPath(); targetCtx.moveTo(pos.rawX, pos.rawY); lastBrushPos = { x: pos.rawX, y: pos.rawY }; }
            } else {
                if (snapshot) {  
                    targetCtx.putImageData(snapshot, 0, 0); 
					targetCtx.globalCompositeOperation = "source-over"; 
					targetCtx.lineWidth = shapeThickness * scaleX; 
					targetCtx.strokeStyle = drawColor; 
					targetCtx.fillStyle = drawColor; 
					targetCtx.globalAlpha = drawOpacity;
					const savedLineCap = targetCtx.lineCap;
                    const savedLineJoin = targetCtx.lineJoin;
                    let endX = pos.rawX, endY = pos.rawY;
                    if (currentTool === 'rect') {
                        targetCtx.lineCap = "butt";
                        targetCtx.lineJoin = "miter";
                        let width = endX - startX, height = endY - startY;
                        if (isShiftPressed) { const size = Math.max(Math.abs(width), Math.abs(height)); width = width > 0 ? size : -size; height = height > 0 ? size : -size; }
                        if (shapeFill) { targetCtx.fillRect(startX, startY, width, height); }
                        targetCtx.strokeRect(startX, startY, width, height);
                    } else if (currentTool === 'circle') {
                        let radiusX = Math.abs(endX - startX), radiusY = Math.abs(endY - startY);
                        if (isShiftPressed) { const radius = Math.max(radiusX, radiusY); radiusX = radius; radiusY = radius; }
                        targetCtx.beginPath(); targetCtx.ellipse(startX, startY, radiusX, radiusY, 0, 0, Math.PI * 2);
                        if (shapeFill) targetCtx.fill(); targetCtx.stroke();
                    }
					targetCtx.lineCap = savedLineCap;
                    targetCtx.lineJoin = savedLineJoin;
                    targetCtx.globalAlpha = 1.0;
                }
            }
        };

        const handleWindowMouseMove = (e) => {
            if (!isDrawing) return;
            const pos = getPos(e);
            if (cropMode) { updateCropDrag(pos); return; }
            currentPos = { x: pos.rawX, y: pos.rawY, isInside: pos.isInside };
            updateDrawing(pos);
        };

        
        const handleWindowMouseUp = (e) => {
            if (!isDrawing) { cleanupWindowTracking(); return; }
            const pos = getPos(e);
			if (cropMode) { isDrawing = false; cropDrag = null; exportCrop(); cleanupWindowTracking(); return; }
            if ((currentTool === 'rect' || currentTool === 'circle') && snapshot) {
                const scaleX = maskCanvas.width / maskCanvas.getBoundingClientRect().width;
                const targetCtx = drawTargetIsImage ? shapeCtx : maskCtx;
                const drawColor = drawTargetIsImage ? shapeColor : maskColor;
                const drawOpacity = drawTargetIsImage ? shapeOpacity : 1.0;
                let endX = pos.rawX, endY = pos.rawY;
                targetCtx.putImageData(snapshot, 0, 0); 
				targetCtx.globalCompositeOperation = "source-over"; 
				targetCtx.lineWidth = shapeThickness * scaleX; 
				targetCtx.strokeStyle = drawColor; 
				targetCtx.fillStyle = drawColor; 
				targetCtx.globalAlpha = drawOpacity;
				const savedLineCap = targetCtx.lineCap;
                const savedLineJoin = targetCtx.lineJoin;
                
                if (currentTool === 'rect') {
                    targetCtx.lineCap = "butt";
                    targetCtx.lineJoin = "miter";
                    let width = endX - startX, height = endY - startY;
                    if (isShiftPressed) { const size = Math.max(Math.abs(width), Math.abs(height)); width = width > 0 ? size : -size; height = height > 0 ? size : -size; }
                    if (shapeFill) targetCtx.fillRect(startX, startY, width, height); 
                    targetCtx.strokeRect(startX, startY, width, height);
                } else if (currentTool === 'circle') {
                    let radiusX = Math.abs(endX - startX), radiusY = Math.abs(endY - startY);
                    if (isShiftPressed) { const radius = Math.max(radiusX, radiusY); radiusX = radius; radiusY = radius; }
                    targetCtx.beginPath(); targetCtx.ellipse(startX, startY, radiusX, radiusY, 0, 0, Math.PI * 2);
                    if (shapeFill) targetCtx.fill(); targetCtx.stroke();
                }
				targetCtx.lineCap = savedLineCap;
                targetCtx.lineJoin = savedLineJoin;
                targetCtx.globalAlpha = 1.0;
            }
            finishDrawing();
            cleanupWindowTracking();
        };
        
        const cleanupWindowTracking = () => { window.removeEventListener("mousemove", handleWindowMouseMove); window.removeEventListener("mouseup", handleWindowMouseUp); isWindowTracking = false; };

        maskCanvas.addEventListener("mousemove", (e) => {
            if (!cursorRafId) {
                cursorRafId = requestAnimationFrame(() => {
                    cursorRafId = null;
                    updateCursorPosition(e);
                });
            }
            if (cropMode) {
                const p = getPos(e);
                const ed = cropEdgeAt(p);
                maskCanvas.style.cursor = ed ? cropCursorFor(ed) : (cropInRect(p) ? "move" : "crosshair");
                if (isDrawing) updateCropDrag(p);
                return;
            }
            if (!isDrawing) return;
            const pos = getPos(e);
            updateDrawing(pos);
        });


        const finishDrawing = () => {
            if (isDrawing) {
                isDrawing = false;
                if (cropMode) { cropDrag = null; exportCrop(); return; }
                lastBrushPos = null;
                snapshot = null;
                if (drawTargetIsImage) exportShapes();
                else exportMask();
            }
        };

        
        maskCanvas.addEventListener("mouseup", finishDrawing);
        
        const clearAll = () => {
            saveHistory();
            maskCtx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
            shapeCtx.clearRect(0, 0, shapeCanvas.width, shapeCanvas.height);
            exportMask(); exportShapes();
        };

        const undo = () => {
            if (history.length > 0) {
                const state = history.pop();
                const mImg = new Image();
                mImg.onload = () => { maskCtx.clearRect(0, 0, maskCanvas.width, maskCanvas.height); maskCtx.drawImage(mImg, 0, 0); exportMask(); }; mImg.src = state.mask;
                const sImg = new Image();
                sImg.onload = () => { shapeCtx.clearRect(0, 0, shapeCanvas.width, shapeCanvas.height); shapeCtx.drawImage(sImg, 0, 0); exportShapes(); }; sImg.src = state.shape;
            }
        };

        const restoreData = () => {
            if (shapeWidget.value && shapeWidget.value.startsWith("data:image")) {
                const sImg = new Image(); sImg.onload = () => { shapeCtx.clearRect(0, 0, shapeCanvas.width, shapeCanvas.height); shapeCtx.drawImage(sImg, 0, 0); }; sImg.src = shapeWidget.value;
            }
            const colorData = maskColorWidget.value || maskWidget.value;
            if (colorData && colorData.startsWith("data:image")) {
                const mImg = new Image(); mImg.onload = () => { maskCtx.clearRect(0, 0, maskCanvas.width, maskCanvas.height); maskCtx.drawImage(mImg, 0, 0); }; mImg.src = colorData;
            }
			restoreCrop();
        };

        if (pathWidget) {
            const orig = pathWidget.callback;
            pathWidget.callback = function(val) {
                if (orig) orig.call(this, val);
                if (browseSource !== "input" && currentPath !== val) {  
                    currentPath = val;
                    showGrid();
                }
            };
        }
        
        if (sortWidget) {
            const orig = sortWidget.callback;
            sortWidget.callback = function(val) {
                if (orig) orig.call(this, val);
                loadImages();
            };
        }       

        setTimeout(() => {
			
            updateMode();
            
            if (!isImageConnected()) {
                currentPath = pathWidget.value;
                const lastSelectedImage = localStorage.getItem('ee_image_' + node.id + '_' + currentPath);
                const targetImage = lastSelectedImage || (imageWidget ? imageWidget.value : null);
                
                if (targetImage) {
                    const savedScroll = localStorage.getItem('ee_scroll_' + node.id + '_' + currentPath);
                    lastScrollTop = savedScroll ? parseInt(savedScroll, 10) : 0;
                    openEditor(targetImage);
                } else {
					showGrid();
                    //loadImages();
                }
            }
            
            if(node.onResize) node.onResize(node.size);
        }, 300);

        const originalOnRemoved = node.onRemoved;
        node.onRemoved = function() {
            try {
                const keysToRemove = [];
                const prefix1 = 'ee_scroll_' + node.id + '_';
                const prefix2 = 'ee_image_' + node.id + '_';
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    if (key && (key.startsWith(prefix1) || key.startsWith(prefix2))) keysToRemove.push(key);
                }
                keysToRemove.forEach(key => localStorage.removeItem(key));
            } catch (e) {}
            cleanupWindowTracking();
            window.removeEventListener("paste", handlePaste, true);
            if (brushCursor && brushCursor.parentNode) brushCursor.parentNode.removeChild(brushCursor);
            if (cursorRafId) cancelAnimationFrame(cursorRafId);
            resizeObserver.disconnect();
            if (originalOnRemoved) originalOnRemoved.apply(this, arguments);
        };

    }
});
