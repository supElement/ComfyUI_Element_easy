import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { eeMarkForward } from "./ee_canvas_utils.js";
import { hideWidgetAndSlot } from "./ee_node_utils.js";

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
.eepp-dialog label.eepp-check{display:flex;align-items:center;gap:6px;color:#ddd;font-size:12px;cursor:pointer}
.eepp-dialog label.eepp-check input{width:auto;margin:0}
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
.eepp-sel-overlay{position:fixed;inset:0;z-index:9990;background:rgba(0,0,0,.6);display:flex;align-items:center;justify-content:center}
.eepp-sel-card{display:flex;flex-direction:column;width:min(760px,92vw);height:min(780px,88vh);min-width:360px;min-height:300px;max-width:98vw;max-height:96vh;overflow:hidden;resize:both;box-sizing:border-box;background:#1e1e1e;border:1px solid #555;border-radius:8px;box-shadow:0 12px 40px rgba(0,0,0,.6);color:#ddd;font:13px system-ui,sans-serif;padding:10px 12px}
.eepp-sel-head{display:flex;flex-wrap:wrap;align-items:center;gap:6px;flex:0 0 auto;margin-bottom:10px;min-width:0}
.eepp-sel-head button{height:26px;padding:0 10px;border:1px solid #3b4558;border-radius:5px;background:#252d3a;color:#dce5f5;cursor:pointer;font:12px system-ui,sans-serif;white-space:nowrap}
.eepp-sel-head button:hover{background:#303a4b}
.eepp-sel-head button.eepp-on{background:#7a2626;border-color:#b34545;color:#ffe3e3}
.eepp-sel-head button.eepp-filter-on{background:#24507a;border-color:#3a7fb5;color:#fff}
.eepp-sel-spacer{flex:1 1 auto}
.eepp-sel-head label{display:flex;align-items:center;gap:5px;color:#aaa;font-size:12px;white-space:nowrap}
.eepp-sel-head input{width:80px;height:26px;box-sizing:border-box;background:#111;border:1px solid #555;border-radius:4px;color:#eee;padding:0 8px;font:12px system-ui,sans-serif}
.eepp-sel-head .eepp-sel-close{width:26px;padding:0}
.eepp-sel-body{flex:1 1 auto;min-height:0;overflow:auto;padding:0 4px 8px 0}
.eepp-sel-body::-webkit-scrollbar{width:10px}
.eepp-sel-body::-webkit-scrollbar-thumb{background:#3a465c;border-radius:5px}
.eepp-sel-group{margin-bottom:16px}
.eepp-sel-grouphead{display:flex;align-items:center;gap:6px;margin-bottom:9px;min-width:0}
.eepp-sel-catwrap{position:relative;display:flex;max-width:70%;min-width:0}
.eepp-sel-cat{flex:1 1 auto;height:34px;padding:0 16px;border:1px solid #3b4a5e;border-radius:5px;background:#2f3b4a;color:#ddd;font:14px system-ui,sans-serif;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.eepp-sel-cat:hover{background:#3a4757}
.eepp-sel-cat.eepp-active{background:#1b5fae;border-color:#2f7fd1;color:#fff}
.eepp-sel-chev{width:26px;height:26px;padding:0;border:0;background:transparent;color:#aaa;cursor:pointer;font:14px system-ui,sans-serif;transition:transform .15s}
.eepp-sel-chev.eepp-open{transform:rotate(90deg)}
.eepp-sel-items{display:flex;flex-wrap:wrap;align-items:flex-start;gap:8px 10px}
.eepp-sel-items.eepp-collapsed{display:none}
.eepp-sel-itemwrap{position:relative;display:flex;flex:0 0 auto;max-width:100%;min-width:0}
.eepp-sel-item{width:auto;max-width:100%;height:30px;padding:0 12px;border:1px solid #3b4558;border-radius:5px;background:#3a3a3a;color:#ddd;font:13px system-ui,sans-serif;cursor:pointer;text-align:center;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.eepp-sel-item:hover{background:#474747}
.eepp-sel-item.eepp-active{background:#1b5fae;border-color:#2f7fd1;color:#fff}
.eepp-sel-x{position:absolute;top:-7px;right:-7px;display:none;width:17px;height:17px;padding:0;border:0;border-radius:50%;background:#c0392b;color:#fff;font:12px/17px system-ui,sans-serif;text-align:center;cursor:pointer;z-index:1}
.eepp-sel-x:hover{background:#e04b3a}
.eepp-sel-card.eepp-del .eepp-sel-x{display:block}
.eepp-sel-empty{color:#888;padding:24px 8px;text-align:center}
.eepp-sel-foot{display:flex;justify-content:flex-end;flex:0 0 auto;margin-top:8px;padding-top:10px;border-top:1px solid #3a3a3a}
.eepp-sel-foot button{height:28px;padding:0 20px;border:1px solid #3a7fb5;border-radius:5px;background:#2b5d8a;color:#fff;font:12px system-ui,sans-serif;cursor:pointer}
.eepp-sel-foot button:hover{background:#3470a5}
.eepp-sel-foot button:active{background:#24507a}
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
    select: '<path d="M9 11l3 3L22 4"/><path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"/>',
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
            if (f.type === "checkbox") {
                const label = document.createElement("label");
                label.className = "eepp-check";
                const input = document.createElement("input");
                input.type = "checkbox";
                input.checked = !!f.value;
                label.append(input, document.createTextNode(f.label));
                card.appendChild(label);
                inputs[f.key] = input;
                continue;
            }
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
        if (opts.leftAction) {
            const left = document.createElement("button");
            left.type = "button";
            left.textContent = opts.leftAction.label;
            left.style.marginRight = "auto";
            left.onclick = async () => {
                left.disabled = true;
                try {
                    await opts.leftAction.onClick?.();
                    finish(null);
                } catch (e) {
                    error.textContent = e.message || String(e);
                } finally {
                    left.disabled = false;
                }
            };
            actions.appendChild(left);
        }
        const cancel = document.createElement("button");
        cancel.type = "button";
        cancel.textContent = opts.cancelLabel || "Cancel | 取消";
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
                    values[key] = input.type === "checkbox" ? input.checked : input.value.trim();
                    if (input.type !== "checkbox" && (opts.required || []).includes(key) && !values[key]) {
                        error.textContent = `Please fill in | 请填写：${labels[key] || key}`;
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
    const linkWidget = node.widgets?.find((w) => w.name === "link");
    const selectionWidget = node.widgets?.find((w) => w.name === "selection");
    if (!presetWidget || !promptWidget || !textWidget) return null;
    if (selectionWidget) hideWidgetAndSlot(node, "selection");

    ensureStyle();
    let sequence = 0;

    const pairKey = (preset, prompt) => `${preset}\u0000${prompt}`;

    let tagIndex = new Map();

    function isTagged(preset, entry) {
        return tagIndex.has(pairKey(preset, entry));
    }

    function setTagIndex(tags) {
        tagIndex = new Map();
        for (const [preset, entries] of Object.entries(tags || {})) {
            if (!entries || typeof entries !== "object") continue;
            for (const [entry, on] of Object.entries(entries)) {
                if (on) tagIndex.set(pairKey(preset, entry), true);
            }
        }
    }

    function mergePresetTags(preset, tags) {
        const prefix = `${preset}\u0000`;
        for (const key of [...tagIndex.keys()]) {
            if (key.startsWith(prefix)) tagIndex.delete(key);
        }
        for (const [entry, on] of Object.entries(tags || {})) {
            if (on) tagIndex.set(pairKey(preset, entry), true);
        }
    }

    function applyEntryLabels() {
        promptWidget.options = promptWidget.options || {};
        promptWidget.options.getOptionLabel = (value) => {
            const name = String(value ?? "");
            return isTagged(presetWidget.value, name) ? `${name} ⬤` : name;
        };
        const el = promptWidget.inputEl || promptWidget.element;
        const select = el?.tagName === "SELECT" ? el : el?.querySelector?.("select");
        select?.querySelectorAll?.("option").forEach((option) => {
            option.textContent = promptWidget.options.getOptionLabel(option.value);
        });
        node.setDirtyCanvas?.(true, true);
    }

    function readSelection() {
        try {
            const data = JSON.parse(selectionWidget?.value || "[]");
            if (!Array.isArray(data)) return [];
            return data
                .filter((item) => Array.isArray(item) && item.length === 2)
                .map(([preset, prompt]) => [String(preset), String(prompt)]);
        } catch {
            return [];
        }
    }

    function writeSelection(pairs) {
        if (!selectionWidget) return;
        selectionWidget.value = JSON.stringify(pairs);
        node.setDirtyCanvas?.(true, true);
    }

    function dropSelection(preset, prompt) {
        const pairs = readSelection();
        const next = pairs.filter(([p, e]) => p !== preset || (prompt !== undefined && e !== prompt));
        if (next.length !== pairs.length) writeSelection(next);
    }

    const originalPresetCallback = presetWidget.callback;
    const originalPromptCallback = promptWidget.callback;

    async function loadPrompts(preset, preferredPrompt, loadText) {
        const token = ++sequence;
        const data = await ppGet("/prompts", { presets: preset });
        if (token !== sequence) return;
        mergePresetTags(preset, data.tags || {});
        const prompts = data.prompts && data.prompts.length ? data.prompts : [FALLBACK_PROMPT];
        const prompt = setCombo(promptWidget, prompts, preferredPrompt);
        applyEntryLabels();
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

        setTagIndex(data.tags || {});
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
        applyEntryLabels();

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
            title: "New Entry | 新建词条",
            message: "Presets are created automatically if missing; the new entry stores the current text box content. | presets 不存在时会自动创建；新词条会保存当前文本框内容。",
            fields: [
                { key: "presets", label: "presets | 分类", value: presetWidget.value || "", placeholder: "e.g. HUMAN" },
                { key: "prompt", label: "entry | 词条名", value: "", placeholder: "e.g. 麦田女草帽" },
                { key: "tags", label: "tags | 标签", type: "checkbox", value: false },
            ],
            required: ["presets", "prompt"],
            submitLabel: "Create | 创建",
            focusKey: "presets",
            leftAction: {
                label: "Modify Tags | 修改标签",
                onClick: async () => {
                    const preset = presetWidget.value;
                    const prompt = promptWidget.value;
                    if (!preset || !prompt) throw new Error("No current entry | 当前没有选中的词条");
                    const data = await ppPost("/toggle_tags", { presets: preset, prompt });
                    await refreshState(preset, prompt, false);
                    toast(data.message || "Tags updated | 标签已切换");
                },
            },
        });
        if (!result) return;
        const data = await ppPost("/create", {
            presets: result.values.presets,
            prompt: result.values.prompt,
            prompt_text: textWidget.value ?? "",
            tags: result.values.tags,
        });
        await refreshState(result.values.presets, result.values.prompt, false);
        (textWidget.inputEl || textWidget.element)?.focus?.();
        toast(data.message || "已新建");
    }

    async function deletePreset() {
        const preset = presetWidget.value;
        if (!preset) return;
        const ok = await eeDialog({
            title: "Delete Preset | 删除预设",
            message: `Delete the category "${preset}" and all of its entries? This cannot be undone. | 确定删除整个分类「${preset}」及其所有词条？此操作不可撤销。`,
            submitLabel: "Delete | 删除",
            danger: true,
        });
        if (!ok) return;
        const data = await ppPost("/delete_preset", { presets: preset });
        dropSelection(preset);
        await refreshState(undefined, undefined, true);
        toast(data.message || "已删除");
    }

    async function deletePrompt() {
        const preset = presetWidget.value;
        const prompt = promptWidget.value;
        if (!preset || !prompt) return;
        const last = comboValues(promptWidget).length <= 1;
        const ok = await eeDialog({
            title: "Delete Entry | 删除词条",
            message: last
                ? `Delete the entry "${prompt}"? It is the last entry of "${preset}", so the category is removed too. | 确定删除词条「${prompt}」？这是「${preset}」的最后一个词条，分类也会一并删除。`
                : `Delete the entry "${prompt}"? This cannot be undone. | 确定删除词条「${prompt}」？此操作不可撤销。`,
            submitLabel: "Delete | 删除",
            danger: true,
        });
        if (!ok) return;
        const data = await ppPost("/delete_prompt", { presets: preset, prompt });
        dropSelection(preset, prompt);
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
            title: "Clear All Presets | 清空所有预设",
            message: `Delete all ${count} categories and their entries? This cannot be undone. (Exported .json files in the promptPresets folder are not affected.) | 确定删除全部 ${count} 个分类及其所有词条？此操作不可撤销。（promptPresets 文件夹里导出的 .json 文件不受影响）`,
            submitLabel: "Clear | 清空",
            danger: true,
        });
        if (!ok) return;
        const data = await ppPost("/clear_all", {});
        writeSelection([]);
        await refreshState(undefined, undefined, true);
        toast(data.message || "已清空");
    }

    async function openSelectionDialog() {
        const [state, exported] = await Promise.all([ppGet("/state"), ppGet("/export")]);
        const db = exported.presets || {};
        const presets = (state.presets || []).filter((preset) => db[preset]);
        for (const preset of Object.keys(db)) {
            if (!presets.includes(preset)) presets.push(preset);
        }
        const groups = presets
            .map((preset) => {
                const names = state.prompts?.[preset] || Object.keys(db[preset] || {});
                return { preset, entries: names.filter((entry) => entry in (db[preset] || {})) };
            })
            .filter((group) => group.entries.length);

        const tagMap = new Set();
        for (const [preset, entries] of Object.entries(state.tags || {})) {
            if (!entries || typeof entries !== "object") continue;
            for (const [entry, on] of Object.entries(entries)) {
                if (on) tagMap.add(pairKey(preset, entry));
            }
        }
        const isTag = (preset, entry) => tagMap.has(pairKey(preset, entry));
        const FILTER_KEY = `eepp_select_filters:${node.id}`;
        let showTags = true;
        let showNl = true;
        try {
            const saved = JSON.parse(localStorage.getItem(FILTER_KEY) || "null");
            if (saved && typeof saved === "object") {
                showTags = saved.tags !== false;
                showNl = saved.nl !== false;
            }
        } catch {}
        if (!showTags && !showNl) {
            showTags = true;
            showNl = true;
        }
        const isVisible = (preset, entry) => (isTag(preset, entry) ? showTags : showNl);

        const selected = new Set(readSelection().map(([preset, prompt]) => pairKey(preset, prompt)));
        const valid = new Set();
        for (const group of groups) {
            for (const entry of group.entries) valid.add(pairKey(group.preset, entry));
        }
        for (const key of [...selected]) {
            if (!valid.has(key)) selected.delete(key);
        }

        function persist() {
            const pairs = [];
            for (const group of groups) {
                for (const entry of group.entries) {
                    if (selected.has(pairKey(group.preset, entry))) pairs.push([group.preset, entry]);
                }
            }
            writeSelection(pairs);
        }
        persist();

        ensureStyle();
        const overlay = document.createElement("div");
        overlay.className = "eepp-sel-overlay";
        const card = document.createElement("div");
        card.className = "eepp-sel-card";

        const head = document.createElement("div");
        head.className = "eepp-sel-head";

        const delBtn = document.createElement("button");
        delBtn.type = "button";
        delBtn.textContent = "delete | 删除";
        delBtn.title = "Show/hide delete marks | 显示/隐藏删除标志";

        const spacer = document.createElement("div");
        spacer.className = "eepp-sel-spacer";

        const tagsBtn = document.createElement("button");
        tagsBtn.type = "button";
        tagsBtn.className = showTags ? "eepp-filter-on" : "";
        tagsBtn.textContent = "tags | 标签";
        tagsBtn.title = "Show/hide tags entries | 显示/隐藏 tags 词条";

        const nlBtn = document.createElement("button");
        nlBtn.type = "button";
        nlBtn.className = showNl ? "eepp-filter-on" : "";
        nlBtn.textContent = "Natural language | 自然语言";
        nlBtn.title = "Show/hide natural language entries | 显示/隐藏自然语言词条";

        const allBtn = document.createElement("button");
        allBtn.type = "button";
        allBtn.textContent = "select All | 全选";

        const noneBtn = document.createElement("button");
        noneBtn.type = "button";
        noneBtn.textContent = "clear select | 清空选择";

        const linkLabel = document.createElement("label");
        linkLabel.textContent = "link | 分隔符";
        const linkInput = document.createElement("input");
        linkInput.type = "text";
        linkInput.value = linkWidget?.value ?? ", ";
        linkInput.spellcheck = false;
        linkInput.title = "Separator for merging selected entries | 选中条目合并成单段文本时的分隔符";
        linkInput.oninput = () => {
            if (!linkWidget) return;
            linkWidget.value = linkInput.value;
            node.setDirtyCanvas?.(true, true);
        };
        linkLabel.appendChild(linkInput);

        const closeBtn = document.createElement("button");
        closeBtn.type = "button";
        closeBtn.className = "eepp-sel-close";
        closeBtn.textContent = "✕";
        closeBtn.title = "Close | 关闭";

        head.append(delBtn, spacer, tagsBtn, nlBtn, allBtn, noneBtn, linkLabel, closeBtn);
        card.appendChild(head);

        const body = document.createElement("div");
        body.className = "eepp-sel-body";
        card.appendChild(body);

        const foot = document.createElement("div");
        foot.className = "eepp-sel-foot";
        const applyBtn = document.createElement("button");
        applyBtn.type = "button";
        applyBtn.textContent = "Apply";
        applyBtn.title = "Apply selection and close | 应用当前选择并关闭";
        applyBtn.onclick = () => {
            persist();
            close();
        };
        foot.appendChild(applyBtn);
        card.appendChild(foot);

        if (!groups.length) {
            const empty = document.createElement("div");
            empty.className = "eepp-sel-empty";
            empty.textContent = "No presets | 当前没有预设";
            body.appendChild(empty);
        }

        const ui = [];
        for (const group of groups) {
            const wrap = document.createElement("div");
            wrap.className = "eepp-sel-group";

            const headRow = document.createElement("div");
            headRow.className = "eepp-sel-grouphead";

            const catWrap = document.createElement("div");
            catWrap.className = "eepp-sel-catwrap";
            const catBtn = document.createElement("button");
            catBtn.type = "button";
            catBtn.className = "eepp-sel-cat";
            catBtn.textContent = group.preset;
            catBtn.title = "Select/deselect all entries in this category | 选择/取消该分类下全部条目";
            const catDel = document.createElement("button");
            catDel.type = "button";
            catDel.className = "eepp-sel-x";
            catDel.textContent = "×";
            catDel.title = `Delete category "${group.preset}" and all its entries | 删除分类「${group.preset}」及其全部条目`;
            catWrap.append(catBtn, catDel);

            const chev = document.createElement("button");
            chev.type = "button";
            chev.className = "eepp-sel-chev eepp-open";
            chev.textContent = "›";
            chev.title = "Collapse/expand | 折叠/展开";

            headRow.append(catWrap, chev);

            const itemsEl = document.createElement("div");
            itemsEl.className = "eepp-sel-items";

            const itemEls = new Map();
            for (const entry of group.entries) {
                const itemWrap = document.createElement("div");
                itemWrap.className = "eepp-sel-itemwrap";
                const item = document.createElement("button");
                item.type = "button";
                item.className = "eepp-sel-item";
                item.textContent = entry;
                item.title = entry;
                const itemDel = document.createElement("button");
                itemDel.type = "button";
                itemDel.className = "eepp-sel-x";
                itemDel.textContent = "×";
                itemDel.title = `Delete entry "${entry}" | 删除词条「${entry}」`;
                itemWrap.append(item, itemDel);
                itemsEl.appendChild(itemWrap);
                itemEls.set(entry, item);

                item.onclick = () => {
                    const key = pairKey(group.preset, entry);
                    if (selected.has(key)) selected.delete(key);
                    else selected.add(key);
                    updateGroup(group.preset);
                    persist();
                };
                itemDel.onclick = (event) => {
                    event.preventDefault();
                    event.stopPropagation();
                    deleteEntry(group.preset, entry)
                        .catch((error) => toast(error.message || String(error), true));
                };
            }

            wrap.append(headRow, itemsEl);
            body.appendChild(wrap);

            catBtn.onclick = () => {
                const keys = group.entries
                    .filter((entry) => isVisible(group.preset, entry))
                    .map((entry) => pairKey(group.preset, entry));
                if (!keys.length) return;
                const allOn = keys.every((key) => selected.has(key));
                for (const key of keys) {
                    if (allOn) selected.delete(key);
                    else selected.add(key);
                }
                updateGroup(group.preset);
                persist();
            };
            catDel.onclick = (event) => {
                event.preventDefault();
                event.stopPropagation();
                deletePreset(group.preset)
                    .catch((error) => toast(error.message || String(error), true));
            };
            chev.onclick = () => {
                const collapsed = itemsEl.classList.toggle("eepp-collapsed");
                chev.classList.toggle("eepp-open", !collapsed);
            };

            ui.push(Object.assign(group, { wrap, catBtn, itemsEl, itemEls }));
            updateGroup(group.preset);
        }
        updateVisibility();

        function updateGroup(preset) {
            const group = ui.find((item) => item.preset === preset);
            if (!group) return;
            let any = false;
            for (const entry of group.entries) {
                const on = selected.has(pairKey(preset, entry));
                group.itemEls.get(entry)?.classList.toggle("eepp-active", on);
                if (on && isVisible(preset, entry)) any = true;
            }
            group.catBtn.classList.toggle("eepp-active", any);
        }

        function updateVisibility() {
            for (const group of ui) {
                let visibleCount = 0;
                for (const entry of group.entries) {
                    const show = isVisible(group.preset, entry);
                    const el = group.itemEls.get(entry);
                    if (el?.parentElement) el.parentElement.style.display = show ? "" : "none";
                    if (show) visibleCount++;
                }
                group.wrap.style.display = visibleCount ? "" : "none";
                updateGroup(group.preset);
            }
        }

        function selectAll(on) {
            for (const group of ui) {
                const entries = on
                    ? group.entries.filter((entry) => isVisible(group.preset, entry))
                    : group.entries;
                for (const entry of entries) {
                    const key = pairKey(group.preset, entry);
                    if (on) selected.add(key);
                    else selected.delete(key);
                }
                updateGroup(group.preset);
            }
            persist();
        }

        allBtn.onclick = () => selectAll(true);
        noneBtn.onclick = () => selectAll(false);

        function toggleFilter(which) {
            if (which === "tags") {
                if (showTags && !showNl) return;
                showTags = !showTags;
                tagsBtn.classList.toggle("eepp-filter-on", showTags);
            } else {
                if (showNl && !showTags) return;
                showNl = !showNl;
                nlBtn.classList.toggle("eepp-filter-on", showNl);
            }
            try {
                localStorage.setItem(FILTER_KEY, JSON.stringify({ tags: showTags, nl: showNl }));
            } catch {}
            updateVisibility();
        }
        tagsBtn.onclick = () => toggleFilter("tags");
        nlBtn.onclick = () => toggleFilter("nl");

        async function deleteEntry(preset, entry) {
            const data = await ppPost("/delete_prompt", { presets: preset, prompt: entry });
            const group = ui.find((item) => item.preset === preset);
            if (group) {
                group.entries = group.entries.filter((name) => name !== entry);
                const el = group.itemEls.get(entry);
                group.itemEls.delete(entry);
                el?.parentElement?.remove();
                selected.delete(pairKey(preset, entry));
                if (group.entries.length) {
                    updateVisibility();
                } else {
                    const index = ui.indexOf(group);
                    if (index >= 0) ui.splice(index, 1);
                    const groupIndex = groups.indexOf(group);
                    if (groupIndex >= 0) groups.splice(groupIndex, 1);
                    group.wrap.remove();
                    updateVisibility();
                }
            }
            persist();
            await refreshState(presetWidget.value, promptWidget.value, true).catch(() => {});
            toast(data.message || "已删除");
        }

        async function deletePreset(preset) {
            const group = ui.find((item) => item.preset === preset);
            const count = group ? group.entries.length : 0;
            const ok = await eeDialog({
                title: "Delete Category | 删除分类",
                message: `Delete category "${preset}" and its ${count} entries? This cannot be undone. | 确定删除分类「${preset}」及其 ${count} 个条目？此操作不可撤销。`,
                submitLabel: "Delete | 删除",
                danger: true,
            });
            if (!ok) return;
            const data = await ppPost("/delete_preset", { presets: preset });
            if (group) {
                for (const entry of group.entries) selected.delete(pairKey(preset, entry));
                const index = ui.indexOf(group);
                if (index >= 0) ui.splice(index, 1);
                const groupIndex = groups.indexOf(group);
                if (groupIndex >= 0) groups.splice(groupIndex, 1);
                group.wrap.remove();
            }
            persist();
            await refreshState(presetWidget.value, promptWidget.value, true).catch(() => {});
            toast(data.message || "已删除");
        }

        let deleteMode = false;
        delBtn.onclick = () => {
            deleteMode = !deleteMode;
            delBtn.classList.toggle("eepp-on", deleteMode);
            card.classList.toggle("eepp-del", deleteMode);
        };

        const BOX_KEY = "eepp_select_box";
        try {
            const saved = JSON.parse(localStorage.getItem(BOX_KEY) || "null");
            if (saved?.w >= 360 && saved?.h >= 300) {
                card.style.width = Math.min(saved.w, innerWidth * 0.98) + "px";
                card.style.height = Math.min(saved.h, innerHeight * 0.96) + "px";
            }
        } catch {}

        let sizeTimer = 0;
        const observer = new ResizeObserver(() => {
            clearTimeout(sizeTimer);
            sizeTimer = setTimeout(() => {
                try {
                    localStorage.setItem(BOX_KEY, JSON.stringify({
                        w: card.offsetWidth,
                        h: card.offsetHeight,
                    }));
                } catch {}
            }, 300);
        });
        observer.observe(card);

        function close() {
            observer.disconnect();
            clearTimeout(sizeTimer);
            overlay.remove();
            document.removeEventListener("keydown", onKey);
        }
        function onKey(event) {
            if (event.key !== "Escape") return;
            if (document.querySelector(".eepp-overlay")) return;
            event.stopPropagation();
            close();
        }
        closeBtn.onclick = close;
        document.addEventListener("keydown", onKey);
        overlay.addEventListener("mousedown", (event) => {
            if (event.target === overlay) close();
        });

        overlay.appendChild(card);
        document.body.appendChild(overlay);
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
    addToolbarButton(bar, ICONS.folder_open, "Load preset file | 加载文件", loadPresetFile);
    addToolbarButton(bar, ICONS.plus, "New entry | 新建词条", createEntry);
    addToolbarButton(bar, ICONS.select, "Select entries | 选择条目", openSelectionDialog);
    addToolbarButton(bar, ICONS.save, "Save entry | 保存词条", saveCurrent);
    addToolbarButton(bar, ICONS.trash, "Delete current prompt | 删除当前词条", deletePrompt, "eepp-danger");
    addToolbarButton(bar, ICONS.folder_x, "Delete current preset | 删除当前分类", deletePreset, "eepp-danger");
    addToolbarButton(bar, ICONS.package, "Export all presets to a JSON file | 导出全部预设", exportPresets);
    addToolbarButton(bar, ICONS.clear, "Clear all presets | 清空全部预设", clearAll, "eepp-danger eepp-right");
    node.addDOMWidget("eepp_toolbar", "div", bar, {
        serialize: false,
        hideOnZoom: false,
        margin: 10,
        getMinHeight: () => 34,
        getMaxHeight: () => 34,
    });
    eeMarkForward(bar);

    // 画布拖拽缩放以 computeSize() 的宽度为下限
    const MIN_WIDTH = 268;
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
