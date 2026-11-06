# Element Prompt Presets — Usage Guide

A local prompt-library node: pick a **category → entry**, review or edit the text, then output it downstream. It can also output a single line chosen by seed.

Presets are stored in `ComfyUI/user/element_easy/promptPresets/prompts.json`.

## 1. Inputs

| Input | Description |
|---|---|
| presets | Category (e.g. fantasy / portrait / narrative) |
| entry | Entry under the selected category |
| single_line | When on, output **one line** from the text box; when off, output the whole text |
| seed | Seed used to pick the line |
| prompt_text | The prompt text box, showing the selected entry; editable |

> After editing the text box, click **Save entry** (floppy icon) to write it back to the library. Otherwise the change only applies to the current run.

## 2. Toolbar (left to right)

| Icon | Name | Action |
|---|---|---|
| Open folder | Load file | Import `.json` / `.xlsx` / `.csv`; duplicate category names become `name (2)` |
| + | New entry | Create an entry under the given category and store the current text |
| Floppy | Save entry | Save the current text into the selected category / entry |
| Trash | Delete entry | Delete the current entry (if it is the last one, the category is removed too) |
| Folder with X | Delete category | Delete the whole category and all its entries |
| Package | Export | Export **all presets** as one JSON file to any disk / folder |
| Circle with X (far right) | Clear all | Delete every preset after a confirmation; exported `.json` files are not touched |

## 3. single_line and seed

With `single_line` on, one line is picked from the text box:

1. Lines are split by newline and **blank lines are skipped** (empty paragraphs never produce empty output);
2. Line index = `seed % line count`, so even a huge seed maps to a valid line instead of always hitting the last one.

| Control mode | Behaviour |
|---|---|
| fixed | Same seed, same line every time |
| increment | Seed +1 after each run, walking down the lines and wrapping at the end |
| decrement | Seed −1 after each run, walking up the lines |
| random | A new random seed before each run, uniformly random line |

## 4. Importing files

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
- Wrapped form: `{"presets": { ... }}` or `{"categories": { ... }}`.

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
