import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { eeMarkForward } from "./ee_canvas_utils.js";

const NODE_KEY = "Element_prompt_presets";
const API_ROOT = "/element_prompt_presets";
const FALLBACK_PRESET = "default";
const FALLBACK_PROMPT = "new prompt";
const STYLE_ID = "eepp-style";

const CSS = `
.eepp-bar{display:flex;flex-wrap:nowrap;align-items:flex-start;gap:6px;box-sizing:border-box;height:24px !important;padding:0;transform:translateY(-10px)}
.eepp-bar button{height:24px;min-width:26px;padding:0 5px;border:1px solid #3b4558;border-radius:5px;background:#252d3a;color:#dce5f5;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;flex:0 0 auto}
.eepp-bar button:hover{background:#303a4b}
.eepp-bar button:active{background:#1f2632}
.eepp-bar button svg{width:14px;height:14px;display:block;pointer-events:none}
.eepp-bar button.eepp-danger:hover{background:#5a2a2a;border-color:#a3423f;color:#ffd9d9}
.eepp-bar button.eepp-right{margin-left:auto}
.eepp-overlay{position:fixed;inset:0;z-index:10000;background:rgba(0,0,0,.55);display:flex;align-items:center;justify-content:center}
.eepp-dialog{min-width:320px;max-width:min(560px,90vw);background:#1e1e1e;border:1px solid #555;border-radius:8px;box-shadow:0 12px 40px rgba(0,0,0,.6);color:#ddd;font:13px system-ui,sans-serif;padding:14px 16px}
.eepp-dialog h3{margin:0 0 10px;font-size:14px;font-weight:600}
.eepp-dialog label{display:block;margin:8px 0 3px;color:#aaa;font-size:11px}
.eepp-dialog input{width:100%;box-sizing:border-box;background:#111;border:1px solid #555;border-radius:4px;color:#eee;padding:6px 8px;font:12px system-ui,sans-serif}
.eepp-dialog input:focus{outline:none;border-color:#3a7fb5}
.eepp-dialog .eepp-msg{white-space:pre-wrap;line-height:1.5;margin:4px 0}
.eepp-dialog .eepp-list{max-height:45vh;overflow:auto;border:1px solid #444;border-radius:4px;margin-top:6px}
.eepp-dialog .eepp-list button{display:block;width:100%;text-align:left;background:transparent;border:0;border-bottom:1px solid #333;color:#ddd;padding:7px 9px;font:12px system-ui;cursor:pointer}
.eepp-dialog .eepp-list button:last-child{border-bottom:0}
.eepp-dialog .eepp-list button:hover{background:#2d3b4a}
.eepp-dialog .eepp-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
.eepp-dialog .eepp-actions button{font-size:12px;padding:6px 14px;border-radius:4px;border:1px solid #555;background:#2a2a2a;color:#ddd;cursor:pointer}
.eepp-dialog .eepp-actions button.eepp-primary{background:#2b5d8a;border-color:#3a7fb5;color:#fff}
.eepp-dialog .eepp-actions button.eepp-danger{background:#6a2a2a;border-color:#944;color:#fff}
.eepp-toast{position:fixed;right:16px;bottom:16px;z-index:10001;background:rgba(30,30,30,.96);border:1px solid #555;border-left:3px solid #3a7fb5;border-radius:5px;color:#eee;padding:9px 13px;font:12px system-ui;max-width:380px;box-shadow:0 6px 24px rgba(0,0,0,.5);white-space:pre-wrap}
.eepp-toast.err{border-left-color:#b55}
`;

const svgIcon = (p, s = 14) =>
    `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;

const ICONS = {
    save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2z"/><polyline points="17 21 17 13 7 13 7 21"/><polyline points="7 3 7 8 15 8"/>',
    plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
    trash: '<polyline points="3 6 5 6 21 6"/><path d="M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/><path d="M9 6V4a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2"/>',
    folder_x: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><line x1="10" y1="11" x2="15" y2="16"/><line x1="15" y1="11" x2="10" y2="16"/>',
    folder_open: '<path d="M6 14l1.5-4.5A2 2 0 0 1 9.4 8H21a1 1 0 0 1 .96 1.27L20 15a2 2 0 0 1-1.9 1.5H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.9a2 2 0 0 1 1.7.9l1 1.6H18"/>',
    package: '<line x1="16.5" y1="9.4" x2="7.5" y2="4.21"/><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/>',
    clear: '<circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/>',
};

function ensureStyle() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement("style");
    style.id = STYLE_ID;
    style.textContent = CSS;
    document.head.appendChild(style);
}

let toastTimer = null;
function toast(text, isError = false) {
    ensureStyle();
    let el = document.querySelector(".eepp-toast");
    if (!el) {
        el = document.createElement("div");
        el.className = "eepp-toast";
        document.body.appendChild(el);
    }
    el.textContent = String(text ?? "");
    el.classList.toggle("err", !!isError);
    el.style.display = "block";
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.style.display = "none"; }, 3200);
}

function eeDialog(opts) {
    return new Promise((resolve) => {
        ensureStyle();
        const overlay = document.createElement("div");
        overlay.className = "eepp-overlay";
        const card = document.createElement("div");
        card.className = "eepp-dialog";

        const title = document.createElement("h3");
        title.textContent = opts.title || "";
        card.appendChild(title);

        if (opts.message) {
            const msg = document.createElement("div");
            msg.className = "eepp-msg";
            msg.textContent = opts.message;
            card.appendChild(msg);
        }

        const inputs = {};
        for (const f of opts.fields || []) {
            const label = document.createElement("label");
            label.textContent = f.label;
            const input = document.createElement("input");
            input.type = "text";
            input.value = f.value ?? "";
            input.placeholder = f.placeholder ?? "";
            input.spellcheck = false;
            card.appendChild(label);
            card.appendChild(input);
            inputs[f.key] = input;
        }

        if (opts.list) {
            const list = document.createElement("div");
            list.className = "eepp-list";
            if (!opts.list.length) {
                const empty = document.createElement("div");
                empty.className = "eepp-msg";
                empty.textContent = opts.emptyText || "(空)";
                empty.style.padding = "10px";
                list.appendChild(empty);
            }
            for (const item of opts.list) {
                const btn = document.createElement("button");
                btn.type = "button";
                btn.textContent = item.label;
                btn.title = item.title || "";
                btn.onclick = () => finish(item.value);
                list.appendChild(btn);
            }
            card.appendChild(list);
        }

        const error = document.createElement("div");
        error.className = "eepp-msg";
        error.style.color = "#e88";
        error.style.minHeight = "1em";
        card.appendChild(error);

        const actions = document.createElement("div");
        actions.className = "eepp-actions";
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.textContent = opts.cancelLabel || "取消";
        cancel.onclick = () => finish(null);
        actions.appendChild(cancel);

        let submit = null;
        if (opts.submitLabel) {
            submit = document.createElement("button");
            submit.type = "button";
            submit.className = opts.danger ? "eepp-danger" : "eepp-primary";
            submit.textContent = opts.submitLabel;
            submit.onclick = () => {
                const values = {};
                const labels = {};
                for (const f of opts.fields || []) labels[f.key] = f.label;
                for (const [key, input] of Object.entries(inputs)) {
                    values[key] = input.value.trim();
                    if ((opts.required || []).includes(key) && !values[key]) {
                        error.textContent = `请填写：${labels[key] || key}`;
                        input.focus();
                        return;
                    }
                }
                finish({ values, picked: null });
            };
            actions.appendChild(submit);
        }
        card.appendChild(actions);

        let done = false;
        function finish(value) {
            if (done) return;
            done = true;
            overlay.remove();
            document.removeEventListener("keydown", onKey);
            resolve(value);
        }
        function onKey(e) {
            if (e.key === "Escape") {
                e.stopPropagation();
                finish(null);
            } else if (e.key === "Enter" && submit && !e.shiftKey) {
                e.preventDefault();
                submit.click();
            }
        }
        document.addEventListener("keydown", onKey);
        overlay.addEventListener("mousedown", (e) => {
            if (e.target === overlay) finish(null);
        });

        overlay.appendChild(card);
        document.body.appendChild(overlay);
        const focusKey = opts.focusKey || (opts.fields && opts.fields[0] && opts.fields[0].key);
        if (focusKey && inputs[focusKey]) setTimeout(() => inputs[focusKey].focus(), 0);
    });
}

async function ppGet(path, params) {
    const query = new URLSearchParams(params || {}).toString();
    const response = await api.fetchApi(`${API_ROOT}${path}${query ? "?" + query : ""}`, { cache: "no-store" });
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
        throw new Error(data.message || `HTTP ${response.status}`);
    }
    return data;
}

async function ppPost(path, body) {
    const response = await api.fetchApi(`${API_ROOT}${path}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
        const error = new Error(data.message || `HTTP ${response.status}`);
        error.data = data;
        throw error;
    }
    if (data.success === false) throw new Error(data.message || "操作失败");
    return data;
}

function valueOf(item) {
    return item && typeof item === "object" ? (item.value ?? item.text) : item;
}

function comboValues(widget) {
    return (widget?.options?.values || []).map(valueOf);
}

function setCombo(widget, values, preferred) {
    if (!widget) return "";
    const items = values && values.length ? values : [""];
    widget.options = widget.options || {};
    widget.options.values = items;
    let value = preferred;
    if (value === undefined || value === null || !items.includes(value)) value = items[0];
    widget.value = value;
    const el = widget.inputEl || widget.element;
    const select = el?.tagName === "SELECT" ? el : el?.querySelector?.("select");
    if (select) {
        select.innerHTML = "";
        for (const item of items) {
            const option = document.createElement("option");
            option.value = item;
            option.textContent = item;
            select.appendChild(option);
        }
        select.value = value;
    } else if (el && "value" in el) {
        el.value = value;
    }
    return value;
}

function setPromptText(node, widget, text) {
    const value = text ?? "";
    widget.value = value;
    const el = widget.inputEl || widget.element;
    if (el && "value" in el) el.value = value;
    if (typeof widget.callback === "function") widget.callback(value);
    node.setDirtyCanvas?.(true, true);
}

function addToolbarButton(bar, icon, title, onClick, className) {
    const button = document.createElement("button");
    button.type = "button";
    button.innerHTML = svgIcon(icon);
    button.title = title || "";
    if (className) button.className = className;
    button.onclick = (event) => {
        event.preventDefault();
        event.stopPropagation();
        Promise.resolve(onClick()).catch((error) => toast(error.message || String(error), true));
    };
    bar.appendChild(button);
    return button;
}

function pickFile(accept) {
    return new Promise((resolve) => {
        const input = document.createElement("input");
        input.type = "file";
        input.accept = accept;
        input.style.display = "none";
        document.body.appendChild(input);
        let done = false;
        const finish = (file) => {
            if (done) return;
            done = true;
            input.remove();
            resolve(file);
        };
        input.addEventListener("change", () => finish(input.files?.[0] || null));
        input.addEventListener("cancel", () => finish(null));
        input.click();
    });
}

async function fileToBase64(file) {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let binary = "";
    const chunk = 0x8000;
    for (let i = 0; i < bytes.length; i += chunk) {
        binary += String.fromCharCode.apply(null, bytes.subarray(i, i + chunk));
    }
    return btoa(binary);
}

function setup(node) {
    const presetWidget = node.widgets?.find((w) => w.name === "presets");
    const promptWidget = node.widgets?.find((w) => w.name === "entry");
    const textWidget = node.widgets?.find((w) => w.name === "prompt_text");
    if (!presetWidget || !promptWidget || !textWidget) return null;

    ensureStyle();
    let sequence = 0;

    const originalPresetCallback = presetWidget.callback;
    const originalPromptCallback = promptWidget.callback;

    async function loadPrompts(preset, preferredPrompt, loadText) {
        const token = ++sequence;
        const data = await ppGet("/prompts", { presets: preset });
        if (token !== sequence) return;
        const prompts = data.prompts && data.prompts.length ? data.prompts : [FALLBACK_PROMPT];
        const prompt = setCombo(promptWidget, prompts, preferredPrompt);
        if (loadText) {
            const textData = await ppGet("/text", { presets: preset, prompt });
            if (token !== sequence) return;
            setPromptText(node, textWidget, textData.prompt_text || "");
        }
    }

    async function loadPromptText(preset, prompt) {
        const token = ++sequence;
        const data = await ppGet("/text", { presets: preset, prompt });
        if (token !== sequence) return;
        setPromptText(node, textWidget, data.prompt_text || "");
    }

    async function refreshState(preferredPreset, preferredPrompt, loadTextIfEmpty) {
        const token = ++sequence;
        const data = await ppGet("/state");
        if (token !== sequence) return;

        const presets = data.presets && data.presets.length ? data.presets : [FALLBACK_PRESET];
        const targetPreset = presets.includes(preferredPreset) ? preferredPreset : presets[0];
        const changedPreset = targetPreset !== preferredPreset;
        setCombo(presetWidget, presets, targetPreset);

        const allPrompts = data.prompts || {};
        const prompts = allPrompts[targetPreset] && allPrompts[targetPreset].length
            ? allPrompts[targetPreset]
            : [FALLBACK_PROMPT];
        const targetPrompt = prompts.includes(preferredPrompt) ? preferredPrompt : prompts[0];
        const changedPrompt = targetPrompt !== preferredPrompt;
        setCombo(promptWidget, prompts, targetPrompt);

        if (changedPreset || changedPrompt || (loadTextIfEmpty && !textWidget.value)) {
            const textData = await ppGet("/text", { presets: targetPreset, prompt: targetPrompt });
            if (token !== sequence) return;
            setPromptText(node, textWidget, textData.prompt_text || "");
        }
        node.setDirtyCanvas?.(true, true);
    }

    async function saveCurrent() {
        const preset = presetWidget.value;
        const prompt = promptWidget.value;
        if (!preset || !prompt) {
            toast("请先选择 presets 和 prompt", true);
            return;
        }
        const data = await ppPost("/save", {
            presets: preset,
            prompt,
            prompt_text: textWidget.value ?? "",
        });
        toast(data.message || "已保存");
    }

    async function createEntry() {
        const result = await eeDialog({
            title: "新建词条",
            message: "presets 不存在时会自动创建；新词条会保存当前文本框内容。",
            fields: [
                { key: "presets", label: "presets（分类）", value: presetWidget.value || "", placeholder: "例如：HUMAN" },
                { key: "prompt", label: "entry（词条名）", value: "", placeholder: "例如：麦田女草帽" },
            ],
            required: ["presets", "prompt"],
            submitLabel: "创建",
            focusKey: "presets",
        });
        if (!result) return;
        const data = await ppPost("/create", {
            presets: result.values.presets,
            prompt: result.values.prompt,
            prompt_text: textWidget.value ?? "",
        });
        await refreshState(result.values.presets, result.values.prompt, false);
        (textWidget.inputEl || textWidget.element)?.focus?.();
        toast(data.message || "已新建");
    }

    async function deletePreset() {
        const preset = presetWidget.value;
        if (!preset) return;
        const ok = await eeDialog({
            title: "删除预设",
            message: `确定删除整个分类「${preset}」及其所有词条？此操作不可撤销。`,
            submitLabel: "删除",
            danger: true,
        });
        if (!ok) return;
        const data = await ppPost("/delete_preset", { presets: preset });
        await refreshState(undefined, undefined, true);
        toast(data.message || "已删除");
    }

    async function deletePrompt() {
        const preset = presetWidget.value;
        const prompt = promptWidget.value;
        if (!preset || !prompt) return;
        const last = comboValues(promptWidget).length <= 1;
        const ok = await eeDialog({
            title: "删除词条",
            message: last
                ? `确定删除词条「${prompt}」？这是「${preset}」的最后一个词条，分类也会一并删除。`
                : `确定删除词条「${prompt}」？此操作不可撤销。`,
            submitLabel: "删除",
            danger: true,
        });
        if (!ok) return;
        const data = await ppPost("/delete_prompt", { presets: preset, prompt });
        await refreshState(preset, undefined, true);
        toast(data.message || "已删除");
    }

    async function loadPresetFile() {
        const file = await pickFile(".json,.xlsx,.csv");
        if (!file) return;
        const body = { name: file.name };
        if (file.name.toLowerCase().endsWith(".json")) {
            try {
                body.data = JSON.parse(await file.text());
            } catch {
                throw new Error(`不是有效的 JSON 文件：${file.name}`);
            }
        } else {
            body.file = await fileToBase64(file);
        }
        const data = await ppPost("/load_preset", body);
        const renamed = Object.entries(data.renamed || {})
            .map(([from, to]) => `${from} → ${to}`)
            .join("\n");
        const first = data.loaded && data.loaded.length ? data.loaded[0] : undefined;
        await refreshState(first, undefined, true);
        toast(`${data.message || "已加载"}${renamed ? `\n重命名：\n${renamed}` : ""}`);
    }

    async function exportPresets() {
        const data = await ppGet("/export");
        const text = JSON.stringify(data.presets || {}, null, 2);
        const filename = "prompts.json";
        if (window.showSaveFilePicker) {
            try {
                const handle = await window.showSaveFilePicker({
                    suggestedName: filename,
                    types: [{ description: "JSON", accept: { "application/json": [".json"] } }],
                });
                const writable = await handle.createWritable();
                await writable.write(text);
                await writable.close();
                toast(`已导出：${handle.name}`);
                return;
            } catch (error) {
                if (error?.name === "AbortError") return;
            }
        }
        const url = URL.createObjectURL(new Blob([text], { type: "application/json" }));
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        toast("已导出到浏览器下载目录");
    }

    async function clearAll() {
        const state = await ppGet("/state");
        const count = (state.presets || []).length;
        if (!count) {
            toast("当前没有预设");
            return;
        }
        const ok = await eeDialog({
            title: "清空所有预设",
            message: `确定删除全部 ${count} 个分类及其所有词条？此操作不可撤销。\n（promptPresets 文件夹里导出的 .json 文件不受影响）`,
            submitLabel: "清空",
            danger: true,
        });
        if (!ok) return;
        const data = await ppPost("/clear_all", {});
        await refreshState(undefined, undefined, true);
        toast(data.message || "已清空");
    }

    presetWidget.callback = async (value) => {
        if (typeof originalPresetCallback === "function") originalPresetCallback.call(presetWidget, value);
        try {
            await loadPrompts(value, undefined, true);
        } catch (error) {
            toast(error.message || String(error), true);
        }
    };

    promptWidget.callback = async (value) => {
        if (typeof originalPromptCallback === "function") originalPromptCallback.call(promptWidget, value);
        if (!presetWidget.value || !value) return;
        try {
            await loadPromptText(presetWidget.value, value);
        } catch (error) {
            toast(error.message || String(error), true);
        }
    };

    const bar = document.createElement("div");
    bar.className = "eepp-bar";
    addToolbarButton(bar, ICONS.folder_open, "Load preset file", loadPresetFile);
    addToolbarButton(bar, ICONS.plus, "New entry", createEntry);
    addToolbarButton(bar, ICONS.save, "Save entry", saveCurrent);
    addToolbarButton(bar, ICONS.trash, "Delete current prompt", deletePrompt, "eepp-danger");
    addToolbarButton(bar, ICONS.folder_x, "Delete current preset", deletePreset, "eepp-danger");
    addToolbarButton(bar, ICONS.package, "Export all presets to a JSON file", exportPresets);
    addToolbarButton(bar, ICONS.clear, "Clear all presets", clearAll, "eepp-danger eepp-right");
    node.addDOMWidget("eepp_toolbar", "div", bar, {
        serialize: false,
        hideOnZoom: false,
        margin: 10,
        getMinHeight: () => 34,
        getMaxHeight: () => 34,
    });
    eeMarkForward(bar);

    // 画布拖拽缩放以 computeSize() 的宽度为下限
    const MIN_WIDTH = 240;
    const origComputeSize = node.computeSize;
    node.computeSize = function (out) {
        const size = origComputeSize ? origComputeSize.call(this, out) : [this.size[0], this.size[1]];
        if (size && size[0] < MIN_WIDTH) size[0] = MIN_WIDTH;
        return size;
    };

    if (node.size) {
        const width = Math.max(node.size[0] || 0, 380);
        const height = Math.max(node.size[1] || 0, 240);
        node.setSize?.([width, height]);
    }

    const controller = {
        initialized: false,
        refreshAfterConfigure() {
            return refreshState(presetWidget.value, promptWidget.value, true);
        },
    };
    node.__eepp = controller;

    setTimeout(() => {
        if (controller.initialized) return;
        controller.initialized = true;
        refreshState(presetWidget.value, promptWidget.value, true)
            .catch((error) => toast(error.message || String(error), true));
    }, 150);

    return controller;
}

app.registerExtension({
    name: "Element_easy.PromptPresets",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== NODE_KEY) return;

        const originalOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = originalOnNodeCreated ? originalOnNodeCreated.apply(this, arguments) : undefined;
            try {
                setup(this);
            } catch (error) {
                console.error("[Element_prompt_presets] 初始化失败", error);
            }
            return result;
        };

        const originalOnConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function (info) {
            const result = originalOnConfigure ? originalOnConfigure.apply(this, arguments) : undefined;
            const controller = this.__eepp;
            if (controller) {
                controller.initialized = true;
                setTimeout(() => {
                    controller.refreshAfterConfigure()
                        .catch((error) => toast(error.message || String(error), true));
                }, 120);
            }
            return result;
        };
    },
});
