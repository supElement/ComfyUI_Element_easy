# Element_prompt_presets.py
# 自包含的提示词库节点：presets = 分类，prompt = 词条。
# 数据文件：ComfyUI/user/element_easy/promptPresets/prompts.json
import base64
import csv
import hashlib
import io
import json
import locale
import os
import re
import sys
import threading
import time
import warnings
import xml.etree.ElementTree as ET
import zipfile

from aiohttp import web
import folder_paths
from server import PromptServer

DB_FILENAME = "prompts.json"
LEGACY_TAGS_FILENAME = "prompt_tags.json"
FALLBACK_PRESET = "default"
FALLBACK_PROMPT = "new prompt"

_STORE_LOCK = threading.RLock()


def _store_dir():
    d = os.path.join(folder_paths.get_user_directory(), "element_easy", "promptPresets")
    os.makedirs(d, exist_ok=True)
    return d


def _store_path():
    return os.path.join(_store_dir(), DB_FILENAME)


def _unwrap_payload(data):
    """兼容 {"presets": {...}} / {"categories": {...}} 包装，但不误伤同名分类。"""
    if not isinstance(data, dict):
        return data
    for key in ("presets", "categories"):
        inner = data.get(key)
        if isinstance(inner, dict) and inner and all(
            isinstance(v, dict) and not _is_entry(v) for v in inner.values()
        ):
            return inner
    return data


def _clean_db(data):
    """兼容 {分类: {词条: 文本}} 与 {分类: {词条: {"text": ..., "tags": true}}}。"""
    data = _unwrap_payload(data)
    if not isinstance(data, dict):
        return {}
    out = {}
    for preset, prompts in data.items():
        preset = str(preset).strip()
        if not preset or not isinstance(prompts, dict):
            continue
        clean_prompts = {}
        for name, value in prompts.items():
            name = str(name).strip()
            if not name:
                continue
            clean_prompts[name] = _entry_value(_entry_text(value), _entry_tags(value))
        out[preset] = clean_prompts
    return out


def _entry_text(value):
    if isinstance(value, dict):
        value = value.get("text", "")
    return value if isinstance(value, str) else str(value)


def _entry_tags(value):
    return isinstance(value, dict) and bool(value.get("tags"))


def _entry_value(text, tags):
    return {"text": text, "tags": True} if tags else text


def _is_entry(value):
    return isinstance(value, str) or (
        isinstance(value, dict) and isinstance(value.get("text"), str)
    )


def _read_db():
    path = _store_path()
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            db = _clean_db(json.load(f))
    except Exception as e:
        print(f"[Element_prompt_presets] 读取 {path} 失败: {e}")
        return {}
    return _migrate_legacy_tags(db)


def _write_db(db):
    path = _store_path()
    text = json.dumps(db, ensure_ascii=False, indent=2)
    tmp = path + f".tmp.{os.getpid()}.{time.time_ns()}"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.replace(tmp, path)


def _migrate_legacy_tags(db):
    """旧版把 tags 存在独立文件里，这里并入 prompts.json 后删除旧文件。"""
    path = os.path.join(_store_dir(), LEGACY_TAGS_FILENAME)
    if not os.path.isfile(path):
        return db
    try:
        with open(path, "r", encoding="utf-8") as f:
            legacy = json.load(f)
    except Exception:
        legacy = {}
    changed = False
    if isinstance(legacy, dict):
        for preset, entries in legacy.items():
            if not isinstance(entries, dict):
                continue
            for name, flag in entries.items():
                if flag and name in db.get(preset, {}):
                    db[preset][name] = _entry_value(_entry_text(db[preset][name]), True)
                    changed = True
    if changed:
        _write_db(db)
    try:
        os.remove(path)
    except OSError:
        pass
    return db


def _state(db):
    return {
        "success": True,
        "presets": _sorted_names(db.keys()),
        "prompts": {preset: _sorted_names(prompts.keys()) for preset, prompts in db.items()},
        "tags": {
            preset: {name: True for name, value in prompts.items() if _entry_tags(value)}
            for preset, prompts in db.items()
        },
        "dir": _store_dir(),
    }


def _ordered_prompt_names(db, first_prompts):
    ordered = list(first_prompts)
    seen = set(ordered)
    for prompts in db.values():
        for name in prompts:
            if name not in seen:
                seen.add(name)
                ordered.append(name)
    return ordered


def _safe_filename(name, fallback="preset"):
    stem = os.path.basename(str(name or "").strip())
    stem = os.path.splitext(stem)[0]
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f\r\n\t]', "_", stem).strip().strip(".")
    if not stem:
        stem = f"{fallback}_{time.strftime('%Y%m%d_%H%M%S')}"
    if stem.lower() == os.path.splitext(DB_FILENAME)[0].lower():
        stem += "_preset"
    return stem[:120]


def _parse_preset(data, fallback_name):
    data = _unwrap_payload(data)
    if not isinstance(data, dict) or not data:
        raise ValueError("预设内容为空")

    values = list(data.values())
    if all(_is_entry(v) for v in values):
        prompts = {}
        for name, value in data.items():
            name = str(name).strip()
            if name:
                prompts[name] = _entry_value(_entry_text(value), _entry_tags(value))
        if prompts:
            return {fallback_name: prompts}
        raise ValueError("预设中没有有效词条")

    if all(isinstance(v, dict) for v in values):
        out = {}
        for preset, prompts in data.items():
            preset = str(preset).strip()
            if not preset:
                continue
            clean = {}
            for name, value in prompts.items():
                name = str(name).strip()
                if name:
                    clean[name] = _entry_value(_entry_text(value), _entry_tags(value))
            out[preset] = clean
        if out:
            return out
        raise ValueError("预设中没有有效词条")

    raise ValueError("预设结构无法识别（不能混合分类和文本）")


def _local_tag(tag):
    return tag.rsplit("}", 1)[-1]


def _xml_text(node):
    return "".join(t.text or "" for t in node.iter() if _local_tag(t.tag) == "t")


def _col_index(ref):
    match = re.match(r"([A-Z]+)", str(ref or "").upper())
    if not match:
        return None
    index = 0
    for ch in match.group(1):
        index = index * 26 + (ord(ch) - 64)
    return index - 1


def _xlsx_shared_strings(zf):
    try:
        root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [_xml_text(si) for si in root if _local_tag(si.tag) == "si"]


def _xlsx_sheet_paths(zf):
    paths = [n for n in zf.namelist() if re.match(r"xl/worksheets/sheet\d+\.xml$", n)]
    paths.sort(key=lambda n: int(re.search(r"sheet(\d+)\.xml$", n).group(1)))
    return paths


def _xlsx_sheet_rows(zf, path, shared):
    rows = []
    for row in ET.fromstring(zf.read(path)).iter():
        if _local_tag(row.tag) != "row":
            continue
        cells = {}
        for cell in row:
            if _local_tag(cell.tag) != "c":
                continue
            index = _col_index(cell.get("r"))
            if index is None:
                index = len(cells)
            kind = cell.get("t")
            if kind == "inlineStr":
                value = _xml_text(cell)
            else:
                node = next((c for c in cell if _local_tag(c.tag) == "v"), None)
                value = "" if node is None or node.text is None else node.text
                if kind == "s":
                    try:
                        value = shared[int(value)]
                    except (ValueError, IndexError):
                        value = ""
            cells[index] = value
        if cells:
            rows.append([cells.get(i, "") for i in range(max(cells) + 1)])
    return rows


def _read_xlsx(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        shared = _xlsx_shared_strings(zf)
        return [_xlsx_sheet_rows(zf, path, shared) for path in _xlsx_sheet_paths(zf)]


def _read_csv(raw):
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = raw.decode("utf-16", errors="replace")
    else:
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                text = raw.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        else:
            text = raw.decode("utf-8", errors="replace")
    try:
        dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
        return [row for row in csv.reader(io.StringIO(text), dialect)]
    except csv.Error:
        return [row for row in csv.reader(io.StringIO(text))]


def _first_filled(cells):
    return next((i for i, c in enumerate(cells) if c), -1)


def _table_rows_to_db(rows, fallback, db):
    table = []
    for row in rows:
        cells = [str(c if c is not None else "").strip() for c in row]
        while cells and not cells[-1]:
            cells.pop()
        if sum(1 for c in cells if c) < 2:
            continue
        table.append(cells)
    if not table:
        return

    # 以内容最多的一行定位表格起始列，整列空白的列在此去掉
    anchor = max(table, key=lambda cells: (sum(1 for c in cells if c), _first_filled(cells)))
    start = _first_filled(anchor)
    aligned = [cells for cells in table if _first_filled(cells) >= start] or table
    width = max(len(cells) for cells in aligned)
    used = [i for i in range(start, width) if any(i < len(cells) and cells[i] for cells in aligned)]
    if not used:
        return

    two_col = len(used) <= 2
    preset = ""
    for cells in table:
        if _first_filled(cells) < start:
            cells = cells[_first_filled(cells):]
        else:
            cells = [cells[i] if i < len(cells) else "" for i in used]
        cells = cells + ["", "", ""]
        if two_col:
            name, text, category = cells[0], "\n".join(c for c in cells[1:] if c), fallback
        else:
            name = cells[1]
            text = "\n".join(c for c in cells[2:] if c)
            if not name:
                continue
            if cells[0]:
                preset = cells[0]
            category = preset or fallback
        if not name:
            continue
        prompts = db.setdefault(category, {})
        final = name
        index = 2
        while final in prompts:
            final = f"{name} ({index})"
            index += 1
        prompts[final] = text


def _parse_table(raw, filename, fallback):
    ext = os.path.splitext(filename)[1].lower()
    if ext in (".xlsx", ".xlsm"):
        try:
            sheets = _read_xlsx(raw)
        except (zipfile.BadZipFile, ET.ParseError):
            raise ValueError("无法读取该表格：旧版 .xls 请先另存为 .xlsx，或文件已损坏")
    elif ext == ".csv":
        sheets = [_read_csv(raw)]
    else:
        raise ValueError("表格文件只支持 .xlsx / .csv")
    db = {}
    for rows in sheets:
        _table_rows_to_db(rows, fallback, db)
    db = {preset: prompts for preset, prompts in db.items() if prompts}
    if not db:
        raise ValueError("表格中没有有效词条（需要「分类 / 词条 / 文本」三列）")
    return db


def _single_line(text, seed):
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[int(seed) % len(lines)]


def _selected_pairs(selection):
    try:
        data = json.loads(selection) if selection else []
    except Exception:
        return []
    pairs = []
    for item in data if isinstance(data, list) else []:
        if isinstance(item, (list, tuple)) and len(item) == 2:
            preset, prompt = str(item[0]), str(item[1])
            if preset and prompt:
                pairs.append((preset, prompt))
    return pairs


def _entry_seed(seed, preset, prompt):
    # 哈希派生而非 seed+i：仿射偏移仍受 lcm 周期限制
    key = f"{seed}|{preset}|{prompt}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(key, digest_size=8).digest(), "big")


_COLLATOR = None

# Windows 系统语言 LCID → 排序 locale
_WIN_LCID = {
    0x0404: "zh_TW", 0x0C04: "zh_HK", 0x0804: "zh_CN", 0x1004: "zh_SG",
    0x0411: "ja_JP", 0x0412: "ko_KR", 0x0419: "ru_RU", 0x0422: "uk_UA",
    0x0409: "en_US", 0x0407: "de_DE", 0x040C: "fr_FR", 0x0C0A: "es_ES",
    0x0410: "it_IT", 0x0416: "pt_BR", 0x0816: "pt_PT", 0x0415: "pl_PL",
    0x041F: "tr_TR", 0x0405: "cs_CZ", 0x0408: "el_GR", 0x042A: "vi_VN",
    0x041E: "th_TH", 0x0413: "nl_NL", 0x041D: "sv_SE", 0x040B: "fi_FI",
    0x0406: "da_DK", 0x0414: "nb_NO", 0x040E: "hu_HU", 0x0418: "ro_RO",
    0x0401: "ar_SA", 0x040D: "he_IL", 0x0421: "id_ID", 0x0439: "hi_IN",
}


def _collator_locales():
    """按系统语言给出候选排序 locale，依次尝试。"""
    for var in ("LC_ALL", "LC_COLLATE", "LANG"):
        value = os.environ.get(var, "").strip()
        if value and value.upper() not in ("C", "POSIX", "C.UTF-8", "C.UTF8"):
            yield value
            yield re.split(r"[.@]", value)[0].replace("-", "_")
    if sys.platform == "win32":
        try:
            import ctypes
            name = _WIN_LCID.get(ctypes.windll.kernel32.GetUserDefaultUILanguage())
            if name:
                yield name
        except Exception:
            pass
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            default = locale.getdefaultlocale()[0]
        if default:
            yield default
    except Exception:
        pass


def _collator_ready():
    global _COLLATOR
    if _COLLATOR is None:
        _COLLATOR = False
        for name in _collator_locales():
            try:
                locale.setlocale(locale.LC_COLLATE, name)
                _COLLATOR = True
                break
            except locale.Error:
                continue
    return _COLLATOR


def _sorted_names(names):
    """按系统语言排序（中文拼音、日文假名、韩文、俄文等本地规则）；无可用 locale 时退回 Unicode 码位。"""
    if _collator_ready():
        return sorted(names, key=locale.strxfrm)
    return sorted(names, key=str.casefold)


def _error(message, status=400):
    return web.json_response({"success": False, "message": message}, status=status)


class ElementPromptPresets:
    @classmethod
    def INPUT_TYPES(cls):
        db = _read_db()
        presets = list(db.keys())
        first_prompts = list(db.get(presets[0], {}).keys()) if presets else []
        if not presets:
            presets = [FALLBACK_PRESET]
        prompt_names = _ordered_prompt_names(db, first_prompts)
        if not prompt_names:
            prompt_names = [FALLBACK_PROMPT]
        presets = _sorted_names(presets)
        prompt_names = _sorted_names(set(prompt_names))
        default_prompt = first_prompts[0] if first_prompts else prompt_names[0]
        return {
            "required": {
                "presets": (presets, {"default": presets[0]}),
                "entry": (prompt_names, {"default": default_prompt}),
                "single_line": ("BOOLEAN", {"default": False}),
                "seed": ("INT", {
                    "default": 0,
                    "min": 0,
                    "max": 0xFFFFFFFFFFFFFFFF,
                    "control_after_generate": True,
                }),
                "prompt_text": ("STRING", {"multiline": True, "default": ""}),
            },
            "optional": {
                "link": ("STRING", {"default": ", "}),
                "selection": ("STRING", {"default": "[]"}),
            },
        }

    RETURN_TYPES = ("STRING", "STRING")
    RETURN_NAMES = ("prompt_text", "prompt_list")
    OUTPUT_IS_LIST = (False, True)
    FUNCTION = "get_prompt"
    CATEGORY = "Element_easy/Text"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        try:
            stamp = os.path.getmtime(_store_path())
        except OSError:
            stamp = 0
        return f"{stamp}|{kwargs.get('selection', '')}"

    def get_prompt(self, presets="", entry="", single_line=False, seed=0,
                   prompt_text="", link=", ", selection="[]"):
        texts = []
        pairs = _selected_pairs(selection)
        if pairs:
            db = _read_db()
            for preset, prompt in pairs:
                if (preset, prompt) == (presets, entry):
                    value = prompt_text
                elif prompt in db.get(preset, {}):
                    value = _entry_text(db[preset][prompt])
                else:
                    continue
                texts.append(_single_line(value, _entry_seed(seed, preset, prompt)) if single_line else value)

        if texts:
            return ((link or "").join(texts), texts,)

        current = _single_line(prompt_text, seed) if single_line else prompt_text
        return (current, [current],)


NODE_CLASS_MAPPINGS = {"Element_prompt_presets": ElementPromptPresets}
NODE_DISPLAY_NAME_MAPPINGS = {"Element_prompt_presets": "Element Prompt Presets"}


# ================= API =================

@PromptServer.instance.routes.get("/element_prompt_presets/state")
async def eepp_state(request):
    return web.json_response(_state(_read_db()))


@PromptServer.instance.routes.get("/element_prompt_presets/prompts")
async def eepp_prompts(request):
    preset = request.rel_url.query.get("presets", "")
    db = _read_db()
    prompts = db.get(preset, {})
    names = _sorted_names(prompts.keys())
    return web.json_response({
        "success": True,
        "prompts": names,
        "tags": {name: True for name, value in prompts.items() if _entry_tags(value)},
    })


@PromptServer.instance.routes.get("/element_prompt_presets/text")
async def eepp_text(request):
    preset = request.rel_url.query.get("presets", "")
    prompt = request.rel_url.query.get("prompt", "")
    db = _read_db()
    return web.json_response({
        "success": True,
        "prompt_text": _entry_text(db.get(preset, {}).get(prompt, "")),
    })


@PromptServer.instance.routes.post("/element_prompt_presets/save")
async def eepp_save(request):
    data = await request.json()
    preset = str(data.get("presets") or "").strip()
    prompt = str(data.get("prompt") or "").strip()
    if not preset or not prompt:
        return _error("presets 和 prompt 不能为空")
    text = data.get("prompt_text")
    text = "" if text is None else str(text)
    with _STORE_LOCK:
        db = _read_db()
        prompts = db.setdefault(preset, {})
        prompts[prompt] = _entry_value(text, _entry_tags(prompts.get(prompt)))
        _write_db(db)
    out = _state(db)
    out["message"] = f"已保存：{preset} / {prompt}"
    return web.json_response(out)


@PromptServer.instance.routes.post("/element_prompt_presets/create")
async def eepp_create(request):
    data = await request.json()
    preset = str(data.get("presets") or "").strip()
    prompt = str(data.get("prompt") or "").strip()
    if not preset or not prompt:
        return _error("presets 和 prompt 不能为空")
    text = data.get("prompt_text")
    text = "" if text is None else str(text)
    with _STORE_LOCK:
        db = _read_db()
        if prompt in db.get(preset, {}):
            return _error(f"词条已存在：{preset} / {prompt}", status=409)
        db.setdefault(preset, {})[prompt] = _entry_value(text, bool(data.get("tags")))
        _write_db(db)
    out = _state(db)
    out["message"] = f"已新建：{preset} / {prompt}"
    return web.json_response(out)


@PromptServer.instance.routes.post("/element_prompt_presets/toggle_tags")
async def eepp_toggle_tags(request):
    data = await request.json()
    preset = str(data.get("presets") or "").strip()
    prompt = str(data.get("prompt") or "").strip()
    if not preset or not prompt:
        return _error("presets 和 prompt 不能为空")
    with _STORE_LOCK:
        db = _read_db()
        prompts = db.get(preset)
        if prompts is None or prompt not in prompts:
            return _error(f"词条不存在：{preset} / {prompt}", status=404)
        value = prompts[prompt]
        enabled = not _entry_tags(value)
        prompts[prompt] = _entry_value(_entry_text(value), enabled)
        _write_db(db)
    out = _state(db)
    out["tags_on"] = enabled
    out["message"] = f"{prompt}: {'tags' if enabled else 'natural language'} | {prompt}：{'标签' if enabled else '自然语言'}"
    return web.json_response(out)


@PromptServer.instance.routes.post("/element_prompt_presets/delete_preset")
async def eepp_delete_preset(request):
    data = await request.json()
    preset = str(data.get("presets") or "").strip()
    if not preset:
        return _error("presets 不能为空")
    with _STORE_LOCK:
        db = _read_db()
        if preset not in db:
            return _error(f"预设不存在：{preset}", status=404)
        del db[preset]
        _write_db(db)
    out = _state(db)
    out["message"] = f"已删除预设：{preset}"
    return web.json_response(out)


@PromptServer.instance.routes.post("/element_prompt_presets/delete_prompt")
async def eepp_delete_prompt(request):
    data = await request.json()
    preset = str(data.get("presets") or "").strip()
    prompt = str(data.get("prompt") or "").strip()
    if not preset or not prompt:
        return _error("presets 和 prompt 不能为空")
    with _STORE_LOCK:
        db = _read_db()
        prompts = db.get(preset)
        if prompts is None or prompt not in prompts:
            return _error(f"词条不存在：{preset} / {prompt}", status=404)
        del prompts[prompt]
        removed_preset = not prompts
        if removed_preset:
            del db[preset]
        _write_db(db)
    out = _state(db)
    out["removed_preset"] = removed_preset
    out["message"] = f"已删除词条：{prompt}"
    if removed_preset:
        out["message"] += f"（预设 {preset} 已无词条，一并删除）"
    return web.json_response(out)


@PromptServer.instance.routes.post("/element_prompt_presets/load_preset")
async def eepp_load_preset(request):
    req = await request.json()
    try:
        filename = os.path.basename(str(req.get("name") or ""))
        fallback = _safe_filename(os.path.splitext(filename)[0], fallback="preset")
        if "data" in req:
            incoming = _parse_preset(req["data"], fallback)
        elif req.get("file"):
            try:
                raw = base64.b64decode(str(req["file"]))
            except Exception:
                raise ValueError("文件内容无法解码")
            incoming = _parse_table(raw, filename, fallback)
        else:
            raise ValueError("预设内容为空")
    except Exception as e:
        return _error(str(e))

    with _STORE_LOCK:
        db = _read_db()
        used = set(db.keys())
        loaded, renamed = [], {}
        for preset, prompts in incoming.items():
            final = preset
            if final in used:
                index = 2
                while f"{preset} ({index})" in used:
                    index += 1
                final = f"{preset} ({index})"
                renamed[preset] = final
            db[final] = prompts
            used.add(final)
            loaded.append(final)
        _write_db(db)

    out = _state(db)
    out["loaded"] = loaded
    out["renamed"] = renamed
    out["message"] = f"已加载 {len(loaded)} 个预设"
    return web.json_response(out)


@PromptServer.instance.routes.get("/element_prompt_presets/export")
async def eepp_export(request):
    db = _read_db()
    return web.json_response({"success": True, "presets": db})


@PromptServer.instance.routes.post("/element_prompt_presets/clear_all")
async def eepp_clear_all(request):
    with _STORE_LOCK:
        count = len(_read_db())
        _write_db({})
    out = _state({})
    out["message"] = f"已清空 {count} 个预设"
    return web.json_response(out)
