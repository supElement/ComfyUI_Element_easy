# Element Prompt Presets — Usage Guide

A local prompt-library node: pick a **category → entry**, review or edit the text, then output it downstream. You can also multi-select a batch of entries to output a merged single text and a text list. A single line or the whole text can be chosen by seed.

Presets, including their tags marks, are stored in `ComfyUI/user/element_easy/promptPresets/prompts.json`; entries without a mark are natural language. A legacy `prompt_tags.json` is merged into it automatically on first read and then deleted.

## 1. Inputs

| Input | Description |
|---|---|
| presets | Category (e.g. fantasy / portrait / narrative) |
| entry | Entry under the selected category; tagged entries show a solid dot `⬤` after the name (display only, never included in the output) |
| single_line | When on, output **one line** per text; when off, output the whole text |
| seed | Seed used to pick the line |
| prompt_text | The prompt text box, showing the selected entry; editable |
| link | Separator used to merge selected entries into one text, default `, ` |

> `selection` holds the multi-select state. It is maintained by the **Select entries** dialog and saved with the workflow; it is hidden on the node.

> After editing the text box, click **Save entry** (floppy icon) to write it back to the library. Otherwise the change only applies to the current run.

> **tags** means keyword-style prompts; **Natural language** means descriptive sentences. Imported presets and all presets created before this feature default to Natural language.

## 2. Toolbar (left to right)

| Icon | Name | Action |
|---|---|---|
| Open folder | Load file | Import `.json` / `.xlsx` / `.csv`; duplicate category names become `name (2)` |
| + | New entry | Create an entry under the given category and store the current text; tick `tags | 标签`, or use `Modify Tags | 修改标签` at the bottom left to toggle the current entry's tags mark |
| Checklist | Select entries | Open the multi-select dialog to output several entries, or delete entries / categories |
| Floppy | Save entry | Save the current text into the selected category / entry |
| Trash | Delete entry | Delete the current entry (if it is the last one, the category is removed too) |
| Folder with X | Delete category | Delete the whole category and all its entries |
| Package | Export | Export **all presets** as one JSON file to any disk / folder |
| Circle with X (far right) | Clear all | Delete every preset after a confirmation; exported `.json` files are not touched |

## 3. Multi-select dialog (Select entries)

Click the checklist button in the toolbar:

- All presets are shown as **category → entry**; the arrow next to a category collapses it;
- Click an entry to toggle it; selected entries are blue. A category turns blue when any of its entries is selected;
- Click a category name to select / deselect all **currently visible** entries in that category;
- `tags | 标签` and `Natural language | 自然语言` filters are both on by default: tags-only hides natural language entries, natural-language-only hides tags entries (at least one filter stays on); the switch state is remembered per node, so it only affects that node's dialog (stored in the browser);
- `select All | 全选` selects all currently visible entries; `clear select | 清空选择` clears every selection;
- `delete | 删除` toggle: when on, a red × appears on entries and categories. Click an entry's × to delete that entry; click a category's × to delete the whole category (asks for confirmation first);
- The `link | 分隔符` input is kept in sync with the node's `link` parameter;
- Drag the bottom-right corner to resize; the size is remembered;
- The **Apply** button at the bottom right confirms the selection and closes. Changes are written to the node as you click, so closing the dialog never loses them;
- The selection is saved with the workflow, so reopening the dialog restores the previous selection. Entries deleted from the library are skipped automatically.

> The node still uses presets / entry to show the **current entry**; multi-select and the current entry do not affect each other.

## 4. Output ports

| Port | Content |
|---|---|
| prompt_text | Single text: with no selection, the current entry (original behaviour); with a selection, every selected entry joined by `link` |
| prompt_list | List: with no selection, `[current entry text]`; with a selection, the text of every selected entry |

- Order follows the category / entry order shown in the dialog;
- With `single_line` on, each selected entry is reduced to one line first; each entry's line is derived from a hash of `seed + category + entry`, so lines are **independent** (see section 5);
- When `prompt_list` is connected to a normal text node, ComfyUI runs it once per item; nodes that accept lists receive the whole list;
- Selected entries that no longer exist are skipped; if none remain, the node falls back to the current entry.

## 5. single_line and seed

With `single_line` on, one line is picked from the current entry (and from each selected entry) separately:

1. Lines are split by newline and **blank lines are skipped** (empty paragraphs never produce empty output);
2. Line index = `seed % line count`, so even a huge seed maps to a valid line instead of always hitting the last one.

With a multi-selection, every entry uses its own derived seed instead of sharing one:

- Derived seed = `hash(seed, category, entry)`, so line choices are unrelated across entries and do not jump in sync when the seed changes;
- With N entries of n₁ … n_N lines each, about `n₁ × n₂ × … × n_N` combinations are possible (sharing one seed allows at most their least common multiple).

| Control mode | Behaviour |
|---|---|
| fixed | Same seed, same set of lines every time |
| increment | Seed +1 after each run; entries change lines independently, walking combinations near-randomly |
| decrement | Seed −1 after each run; entries change lines independently |
| random | A new random seed before each run, uniformly random combination |

## 6. Importing files

### 4.1 JSON

```json
{
  "fantasy": {
    "giant mountain": "First prompt text ...",
    "wheat field": "Another prompt text ..."
  },
  "portrait": {
    "white shirt": "..."
  }
}
```

Also supported:

- Single-category file: `{"entry name": "text", ...}` — imported under the file name;
- Wrapped form: `{"presets": { ... }}` or `{"categories": { ... }}`;
- Exported form with tags: an entry value may be an object `{"text": "text", "tags": true}`. Plain strings and objects can be mixed in one category; entries without the tags mark are treated as natural language.

```json
{
  "fantasy": {
    "giant mountain": {"text": "keyword-style prompt ...", "tags": true},
    "wheat field": "natural language description ..."
  }
}
```

### 4.2 Tables (.xlsx / .csv)

Read as three columns: **category | entry | text**. Example:

| category | entry | text |
|---|---|---|
| human scene | mountain top | First prompt text ... |
|  | plateau | Another prompt text ... |
|  | bedroom | ... |
| Dreamlike Scenes | Fantasy Forests | …… |

- No header detection: a header row is imported like any other row (delete it afterwards if unwanted);
- Empty columns on the left and columns that are blank everywhere are ignored; rows with only one filled cell (e.g. a title) are skipped;
- When the category cell is merged or only filled on the first row, rows below reuse the category above;
- Fully empty rows are skipped; duplicate entry names inside one category become `name (2)`;
- With only two columns (entry | text), everything goes into a category named after the file;
- The text column may contain multiple lines; all worksheets in the workbook are read;
- Save from WPS / Excel as `.xlsx`; for Google Sheets use "File → Download → Microsoft Excel / CSV";
- Old `.xls` files must be saved as `.xlsx` first.
