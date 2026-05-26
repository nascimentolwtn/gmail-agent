# Plan: Tag Picker Modal Redesign

**Status:** Not started
**File:** `.claude/plans/tag-picker-redesign.md`
**Napkin item:** `[ ] [2026-05-22] Redesign tag picker modal: click-to-add / ✕-to-remove list instead of ctrl+click <select multiple>`

## Goal

Replace the `<select multiple>` tag picker modal with a clickable list UI. No ctrl+click needed — single click to add/remove tags.

## UI Behavior

1. **Chosen section** (top of modal): Shows currently selected tags. Each row has the label name + "✕" button on the right. Click "✕" to remove.
2. **Available list** (below chosen section): Scrollable list of all labels matching the filter. Each row has the label name + "+" button on the right. Click label name or "+" to add.
3. Already-selected labels in the available list show a highlighted/selected style and their "+" button is hidden or dimmed.
4. Filter input filters the available list only (not the chosen section).
5. Frequent labels (top-N) appear first, then A–Z, with a separator — same as current behavior.
6. Pre-selected tags from auto-suggestion (DECISIONS[idx].action) appear as chosen when modal opens.

## Files to Modify

### 1. `templates/dashboard.html` — Modal HTML

**Replace** (lines 72–83):
```html
<select id="tagSelect" multiple onchange="handleSelectChange(this)"></select>
```

**With:**
```html
<div id="tagPickerChosen" class="tag-picker-chosen"></div>
<div id="tagPickerList" class="tag-picker-list"></div>
```

### 2. `templates/dashboard.html` — JavaScript

**Remove these functions entirely:**
- `renderLabelOptions(names)`
- `makeOption(n)`
- `toggleTag(name, checked)`
- `handleSelectChange(sel)`

**Remove these variables:**
- `let modalSelectedTags = new Set()` → replace with `const selectedTags = new Set()`
- `let rebuilding = false` → no longer needed

**Modify `openTagModal(idx)`:**
- Initialize `selectedTags` Set from `DECISIONS[idx].action` (tag names without "tag:" prefix)
- Also track a `preSelectedTags` Set (same initial values) — used to visually distinguish auto-suggested vs user-added
- Call `renderPicker()` instead of `renderLabelOptions(allLabelNames)`

**Add new functions:**

```
renderPicker()
  → calls renderChosen() + renderAvailable()

renderChosen()
  → builds #tagPickerChosen div content
  → for each name in allLabelNames where selectedTags.has(name):
    → create .tag-picker.row with .tag-picker-name (clickable) + .tag-picker-remove ("✕")
    → add CSS class .tag-picker-pre if name is in preSelectedTags
  → if selectedTags is empty, show placeholder text

renderAvailable()
  → reads filter term from #tagFilter
  → builds #tag-picker-list div content
  → same top-N frequent / separator / A-Z logic as current renderLabelOptions
  → skip names already in selectedTags (they appear in chosen section)
  → call appendLabelRow(container, name)

appendLabelRow(container, name)
  → create .tag-picker-row div
  → add .tag-picker-row-selected if selectedTags.has(name)
  → .tag-picker-name (onclick: toggle — add if not selected, remove if selected)
  → .tag-picker-add "+" button (onclick: addTag(name))
  → append to container

addTag(name)
  → selectedTags.add(name)
  → renderPicker()

removeTag(name)
  → selectedTags.delete(name)
  → preSelectedTags.delete(name)
  → renderPicker()

filterLabels(term)
  → just calls renderAvailable() (chosen section doesn't filter)

closeTagModal()
  → also clear selectedTags and preSelectedTags

confirmTagPick()
  → read from selectedTags Set (Array.from(selectedTags))
  → build action array: selectedTags.map(l => 'tag:' + l)
  → rest is same as current (set state[idx], DECISIONS[idx], call updateRowUI)
```

### 3. `static/styles.css` — New styles

**Remove:**
```css
.modal select { ... }
.modal select option { ... }
.modal select option:disabled { ... }
```

**Add:**
```css
/* Tag picker list */
.tag-picker-chosen {
  margin-bottom: 8px;
  min-height: 0;
}
.tag-picker-list {
  max-height: 50vh;
  overflow-y: auto;
  border: 1px solid #ddd;
  border-radius: 6px;
  margin-bottom: 12px;
}
.tag-picker-empty {
  padding: 12px;
  color: #999;
  font-size: 0.82rem;
  text-align: center;
}
.tag-picker-row {
  display: flex;
  align-items: center;
  padding: 5px 10px;
  border-bottom: 1px solid #f0f0f0;
  cursor: default;
}
.tag-picker-row:last-child { border-bottom: none; }
.tag-picker-row:hover { background: #f8f9fa; }
.tag-picker-row-selected { background: #e8f0fe; }
.tag-picker-row-selected:hover { background: #d2e3fc; }
.tag-picker-row-chosen { background: #e8f0fe; }
.tag-picker-row.tag-picker-pre { background: #fff8e1; }
.tag-picker-name {
  flex: 1;
  font-size: 0.85rem;
  cursor: pointer;
  user-select: none;
}
.tag-picker-name:hover { color: #1a73e8; }
.tag-picker-add,
.tag-picker-remove {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 0.85rem;
  font-weight: 700;
  cursor: pointer;
  flex-shrink: 0;
  margin-left: 6px;
}
.tag-picker-add { color: #1a73e8; background: #e8f0fe; }
.tag-picker-add:hover { background: #d2e3fc; }
.tag-picker-remove { color: #ea4335; background: #fce8e6; }
.tag-picker-remove:hover { background: #f8c9c5; }
.tag-picker-sep {
  padding: 4px 10px;
  color: #ccc;
  font-size: 0.75rem;
  letter-spacing: 2px;
  text-align: center;
  border-bottom: 1px solid #f0f0f0;
}
```

## Implementation Order

1. `templates/dashboard.html` — Replace `<select>` with two `<div>`s
2. `templates/dashboard.html` — Rewrite all tag picker JS functions
3. `static/styles.css` — Replace `.modal select` rules with new tag-picker classes

## Notes

- `.tag-picker-pre` (pale yellow `#fff8e1`) distinguishes auto-suggested tags from user-added ones in the chosen section
- The filter only affects the available list, not the chosen section
- No "rebuilding" flag needed — the new approach doesn't fire spurious DOM events
- selectedTags is the single source of truth; confirmTagPick reads from it directly
