import { app } from "../../scripts/app.js";
import { $el } from "../../scripts/ui.js";
import { api } from "../../scripts/api.js";

const NODE_NAME = "LoadImageWithPreview"; 

app.registerExtension({
    name: "element_easy.ImageLoader",
  
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_NAME) return;

        try {
            if (nodeData?.input?.required) {
                if (nodeData.input.required.mask_data) {
                    nodeData.input.required.mask_data[1] = {
                        ...(nodeData.input.required.mask_data[1] || {}),
                        hidden: true,
                        forceInput: false, 
                    };
                }
                if (nodeData.input.required.shape_data) {
                    nodeData.input.required.shape_data[1] = {
                        ...(nodeData.input.required.shape_data[1] || {}),
                        hidden: true,
                        forceInput: false, 
                    };
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
				
                .ee-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 2px; overflow-y: auto; flex: 1; padding: 2px; }
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
        };
    },

    async nodeCreated(node) {
        if (node.comfyClass !== NODE_NAME) return;
		
        const isNewNode = typeof node.id !== 'number' || node.id < 0;
		let lastScrollTop = 0;
        
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

            node.widgets = node.widgets.filter(w => 
                w.name !== "mask_data" && w.name !== "shape_data" && w.name !== "mask_color_data"
            );
            node.widgets.push(maskWidget, shapeWidget, maskColorWidget);
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

        const refreshPlayBtn = $el("button.ee-btn", { 
            id: "ee-btn-refresh-play",
            textContent: "⟳",
            title: "Refresh",
            style: { 
                fontSize: "20px",        
                width: "28px",           
                height: "28px",          
                padding: "0",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
				lineHeight: "1px",
				verticalAlign: "middle",
				marginLeft: "0",       
                //marginRight: "8px",   
                color: "#ffffff",       
                backgroundColor: "#007acc", 
                border: "none",
                borderRadius: "3px",
				flexShrink: 0
  
            },
            onclick: async () => {
                if (isImageConnected()) {
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
                            console.log("Successfully queued isolated node execution (Flawless Method)");
                        } finally {
                            if (app.graphToPrompt !== originalGraphToPrompt) {
                                app.graphToPrompt = originalGraphToPrompt;
                            }
                        }
                        
                    } catch (err) {
                        console.error("Failed to execute isolated node:", err);
                    }
                } else {
                    loadImages();
                }
            }
        });
		
		const targetToggleBtn = $el("button.ee-switch-btn", { 
            textContent: "Mask", 
            title: "Click to switch draw target (Mask/Image)", 
            style: { 
                marginLeft: "4px", 
                marginRight: "4px",
                width: "60px",        
                height: "28px",     
                padding: "0",
                fontSize: "13px",
                fontWeight: "bold"
            }, 
            onclick: function(e) { toggleDrawTarget(e.target); } 
        });
        
        const undoBtn = $el("button.ee-btn", { 
            textContent: "↩️", 
            title: "Undo", 
            style: { width: "28px", height: "28px", padding: "0", fontSize: "16px", marginLeft: "2px", lineHeight: "1px", verticalAlign: "middle" }, 
            onclick: () => undo() 
        });
        
        const clearBtn = $el("button.ee-btn", { 
            textContent: "🗑️", 
            title: "Clear All", 
            style: { width: "28px", height: "28px", padding: "0", fontSize: "16px", marginLeft: "2px", lineHeight: "1px", verticalAlign: "middle" }, 
            onclick: () => clearAll() 
        });
		
        const lmaskBtn = $el("button.ee-btn", { 
            textContent: "La",
            id: "ee-btn-lmask",
            title: "Load image alpha channel as mask",
            style: { 
                display: "none",         
                //marginLeft: "4px",     
                fontSize: "13px", 
                fontWeight: "bold", 
                padding: "0px", 
				width: "28px", 
                height: "28px",          
                lineHeight: "28px",
                backgroundColor: "#444",
                color: "white",
                border: "none",
                borderRadius: "3px"
            }, 
            onclick: function(e) {
                if (imgEl && imgEl.src && editorView.style.display !== "none") {
                    saveHistory(); 
                    loadAlphaAsMask(imgEl.src, (alphaCanvas) => {
                        maskCtx.drawImage(alphaCanvas, 0, 0);
                        exportMask(); 
                    });
                }
            }
        });



        const header = $el("div.ee-header", {
            style: { 
                display: "flex", 
                gap: "4px", 
                alignItems: "center", 
                padding: "4px",
                backgroundColor: "transparent"
            }
        }, [
            refreshPlayBtn,
            targetToggleBtn,
            lmaskBtn,    
            undoBtn,
            clearBtn,

            $el("button.ee-btn", { 
                textContent: "◂Return",
                id: "ee-btn-back", 
                style: { 
                    display: "none", background: "#007acc", color: "#fff",
                    fontSize: "12px", fontWeight: "bold", padding: "0px 4px 0px 0px", width: "70px", height: "28px", lineHeight: "28px", verticalAlign: "middle", marginLeft: "auto"
                }, 
                onclick: () => showGrid() 
            })
        ]);
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
        
        const toolsGroup = $el("div.ee-toolbar-group", {
            style: { display: "flex", alignItems: "center", gap: "6px", borderRight: "1px solid #444", paddingRight: "4px" }
        }, [
            $el("button.ee-btn.tool-btn.active", { textContent: "🖌️ Brush", style: { width: BTN_WIDTH, height: BTN_HEIGHT, padding: "4", lineHeight: "1px", verticalAlign: "middle" }, onclick: (e) => setTool('brush', e.target) }),
            $el("button.ee-btn.tool-btn", { textContent: "🧹 Eraser", style: { width: BTN_WIDTH, height: BTN_HEIGHT, padding: "0", lineHeight: "1px", verticalAlign: "middle" }, onclick: (e) => setTool('eraser', e.target) }),
            $el("button.ee-btn.tool-btn", { textContent: "🔳 Box", style: { width: BTN_WIDTH, height: BTN_HEIGHT, padding: "0", lineHeight: "1px", verticalAlign: "middle" }, onclick: (e) => setTool('rect', e.target) }),
            $el("button.ee-btn.tool-btn", { textContent: "⭕ Circle", style: { width: BTN_WIDTH, height: BTN_HEIGHT, padding: "0", lineHeight: "1px", verticalAlign: "middle" }, onclick: (e) => setTool('circle', e.target) }),
            $el("label", { style: { color: "white", fontSize: "12px", cursor: "pointer", display: "flex", alignItems: "center", gap: "4px", height: BTN_HEIGHT, marginLeft: "6px" } }, [
                $el("input", { type: "checkbox", style: { margin: "0" }, onchange: (e) => shapeFill = e.target.checked }), " S-fill"
            ])
        ]);
        
        const maskControlGroup = $el("div.ee-toolbar-group", {
            style: { display: "flex", alignItems: "center", gap: "4px", borderRight: "1px solid #444", paddingRight: "0px" }
        }, [
            $el("div.ee-color-wrapper", {}, [ $el("input", { type: "color", value: "#808080", title: "Mask color", oninput: (e) => maskColor = e.target.value }), $el("span.ee-color-overlay", { textContent: "M" }) ]),
            $el("div.ee-slider-container", {}, [ $el("span", { textContent: "B-size:" }), $el("input", { type: "range", min: 1, max: 100, value: 20, title: "Brush size", style: { width: SLIDER_WIDTH }, oninput: (e) => { brushSize = parseInt(e.target.value); updateBrushCursor(); } }) ]),
            $el("div.ee-slider-container", {}, [ $el("span", { textContent: "M-op:" }), $el("input", { type: "range", min: 0.1, max: 1, step: 0.1, value: 0.8, title: "Mask opacity (preview only)", style: { width: SLIDER_WIDTH }, oninput: (e) => { maskOpacity = parseFloat(e.target.value); maskCanvas.style.opacity = maskOpacity; } }) ])
        ]);
        
        const imageControlGroup = $el("div.ee-toolbar-group", {
            style: { display: "flex", alignItems: "center", gap: "4px", paddingRight: "0px" }
        }, [
            $el("div.ee-color-wrapper", {}, [ $el("input", { type: "color", value: "#ff0000", title: "Image shape color", oninput: (e) => shapeColor = e.target.value }), $el("span.ee-color-overlay", { textContent: "I" }) ]),
            $el("div.ee-slider-container", {}, [ $el("span", { textContent: "I-op:" }), $el("input", { type: "range", min: 0.1, max: 1, step: 0.1, value: 1.0, title: "Image opacity (affects output)", style: { width: SLIDER_WIDTH }, oninput: (e) => { shapeOpacity = parseFloat(e.target.value); } }) ]),
            $el("div.ee-slider-container", {}, [ $el("span", { textContent: "S-edge:" }), $el("input", { type: "range", min: 1, max: 50, value: 5, title: "Edge width", style: { width: SLIDER_WIDTH }, oninput: (e) => shapeThickness = parseInt(e.target.value) }) ])
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
        };

        let currentPath = "";
        let originalImageSize = { w: 1024, h: 1024 };
        let history = []; 

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
            
            if (shapeCanvas.width !== originalImageSize.w || shapeCanvas.height !== originalImageSize.h) {
                shapeCanvas.width = originalImageSize.w;
                shapeCanvas.height = originalImageSize.h;
                maskCanvas.width = originalImageSize.w;
                maskCanvas.height = originalImageSize.h;
                restoreData();
            }
        };
		
		// UI连线状态自适应更新
        const updateMode = () => {
            const connected = isImageConnected();
            const backBtn = header.querySelector("#ee-btn-back");
            //const lmaskBtn = header.querySelector("#ee-btn-lmask");

            if (connected) {
                refreshPlayBtn.textContent = "▶";
                refreshPlayBtn.title = "Queue Selected Node (Apply Input Image)";
                refreshPlayBtn.style.fontSize = "13px";
                
                gridView.style.display = "none";
                editorView.style.display = "flex";
                if (backBtn) backBtn.style.display = "none";
                lmaskBtn.style.display = "block";
				targetToggleBtn.style.display = "inline-block";
                undoBtn.style.display = "inline-block";
                clearBtn.style.display = "inline-block";
            } else {
                refreshPlayBtn.textContent = "⟳";
                refreshPlayBtn.title = "Refresh";
                refreshPlayBtn.style.fontSize = "16px";
				
				showGrid();
            
            }
        };
        
		
		let lastImageLink = null;
        const transparentPixel = "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";
        
        const origOnConnectionsChange = node.onConnectionsChange;
        node.onConnectionsChange = function(type, index, connected, link_info) {
            if (origOnConnectionsChange) origOnConnectionsChange.apply(this, arguments);
            
            const isInputChange = (type === LiteGraph.INPUT || type === "input");
            if (!isInputChange) {
                return; 
            }
            
            updateMode();
            
            // 监听节点输入端口的变化
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
                        }
                    } else {
                        clearAll();
                        if (imgEl && imgEl.src && imgEl.src.includes("type=temp")) {
                            imgEl.src = transparentPixel;
                        }
                        lastImageLink = null;
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
                    
                    setTimeout(() => {
                        resizeCanvas();
                    }, 50);
                };
                tempImg.src = imgSrc;
                
                gridView.style.display = "none";
                editorView.style.display = "flex";
                const lmaskBtn = header.querySelector("#ee-btn-lmask");
                if (lmaskBtn) lmaskBtn.style.display = "block";
            }
        };

        const loadImages = async (restoreScroll = 0) => {
            currentPath = pathWidget.value;
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
						localStorage.setItem('ee_scroll_' + currentPath, lastScrollTop.toString()); 
						localStorage.setItem('ee_image_' + currentPath, filename);
                        openEditor(filename);
                    }
                }, [ $el("img", { src: `/element_easy/view?folder_path=${encodeURIComponent(currentPath)}&filename=${encodeURIComponent(filename)}` }) ]);
                if (imageWidget && imageWidget.value === filename) item.classList.add("selected");
                gridView.appendChild(item);
            });
        };

        const showGrid = () => {
            gridView.style.display = "grid";
            editorView.style.display = "none";
            header.querySelector("#ee-btn-back").style.display = "none";
            lmaskBtn.style.display = "none"; 
			targetToggleBtn.style.display = "none";
            undoBtn.style.display = "none";
            clearBtn.style.display = "none";
			const savedScroll = localStorage.getItem('ee_scroll_' + currentPath);
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
			const savedScroll = localStorage.getItem('ee_scroll_' + currentPath);
			lastScrollTop = savedScroll ? parseInt(savedScroll, 10) : 0;
			const isSwitchingImage = imageWidget && imageWidget.value !== filename;
            if (imageWidget) imageWidget.value = filename;
            localStorage.setItem('ee_image_' + currentPath, filename);
            
            if (isSwitchingImage) {
                maskCtx.clearRect(0, 0, maskCanvas.width, maskCanvas.height);
                shapeCtx.clearRect(0, 0, shapeCanvas.width, shapeCanvas.height);
                maskWidget.value = "";
                shapeWidget.value = "";
                if (maskColorWidget) maskColorWidget.value = ""; 
                history = [];
            }
            
            gridView.style.display = "none";
            editorView.style.display = "flex";
            header.querySelector("#ee-btn-back").style.display = "block";
            lmaskBtn.style.display = "block";
			targetToggleBtn.style.display = "inline-block";
            undoBtn.style.display = "inline-block";
            clearBtn.style.display = "inline-block";
        
            const imgSrc = `/element_easy/view?folder_path=${encodeURIComponent(currentPath)}&filename=${encodeURIComponent(filename)}`;
            const tempImg = new Image();
            tempImg.onload = () => {
                originalImageSize.w = tempImg.width;
                originalImageSize.h = tempImg.height;
                imgEl.src = imgSrc;
                setTimeout(() => resizeCanvas(), 50);
            };
            tempImg.src = imgSrc;
        };

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

        maskCanvas.addEventListener("mouseenter", (e) => { if (currentTool === 'brush' || currentTool === 'eraser') brushCursor.style.display = "block"; });
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
            currentPos = { x: pos.rawX, y: pos.rawY, isInside: pos.isInside };
            updateDrawing(pos);
        };
        
        const handleWindowMouseUp = (e) => {
            if (!isDrawing) { cleanupWindowTracking(); return; }
            const pos = getPos(e);
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
            if (!cursorRafId) { cursorRafId = requestAnimationFrame(() => { cursorRafId = null; updateCursorPosition(e); }); }
            if (!isDrawing) return;
            const pos = getPos(e);
            updateDrawing(pos);
        });

        const finishDrawing = () => {
            if(isDrawing) { isDrawing = false; lastBrushPos = null; snapshot = null;  
                if (drawTargetIsImage) exportShapes(); else exportMask();
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
        };

        if (pathWidget) {
            const orig = pathWidget.callback;
            pathWidget.callback = function(val) {
                if (orig) orig.call(this, val);
                if (currentPath !== val) { currentPath = val; showGrid(); }
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
                const lastSelectedImage = localStorage.getItem('ee_image_' + currentPath);
                const targetImage = lastSelectedImage || (imageWidget ? imageWidget.value : null);
                
                if (targetImage) {
                    const savedScroll = localStorage.getItem('ee_scroll_' + currentPath);
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
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    if (key && (key.startsWith('ee_scroll_') || key.startsWith('ee_image_'))) keysToRemove.push(key);
                }
                keysToRemove.forEach(key => localStorage.removeItem(key));
            } catch (e) {}
            cleanupWindowTracking();
            if (brushCursor && brushCursor.parentNode) brushCursor.parentNode.removeChild(brushCursor);
            if (cursorRafId) cancelAnimationFrame(cursorRafId);
            resizeObserver.disconnect();
            if (originalOnRemoved) originalOnRemoved.apply(this, arguments);
        };
    }
});
