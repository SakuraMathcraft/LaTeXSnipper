# LaTeXSnipper 2.1 Handwriting Plan

## Goal

LaTeXSnipper 2.1 adds a dedicated handwriting formula window built on top of the existing `pix2text` recognition pipeline.

This version does not aim to build a true stroke-native math recognizer. It aims to deliver a practical workflow:

1. user writes on a canvas
2. the canvas is exported to an image
3. `pix2text` recognizes the image as LaTeX
4. the result is rendered immediately
5. the user can correct and insert it back into the main window


## Product Positioning

2.1 should treat handwriting as a new input source into the existing LaTeX preview and editing flow.

The handwriting window is not a replacement for screenshot recognition. It is an additional recognition entry focused on:

- mouse writing
- stylus writing
- fast formula drafting
- quick correction before insertion


## Scope

### In Scope

- independent handwriting window
- drawing canvas
- tools: `Write`, `Erase`, `Select and Correct`, `Clear`, `Undo`, `Redo`
- debounce-based auto recognition after idle
- LaTeX text preview
- rendered math preview
- insert recognized result back into main window
- fallback manual editing when recognition is wrong

### Out of Scope for 2.1

- true Windows Ink stroke recognizer integration
- pressure-sensitive brush behavior
- pixel-perfect lasso transform
- multi-page or notebook canvas
- advanced handwriting model fine-tuning
- confidence heatmap or symbol-level segmentation UI


## Why Reuse pix2text

The current codebase already has a stable `pix2text` integration:

- subprocess isolation
- resident worker
- timeout protection
- warmup path
- preview rendering path

Relevant existing integration points:

- [`src/backend/model.py`](e:/LaTexSnipper/src/backend/model.py)
- [`src/main.py`](e:/LaTexSnipper/src/main.py)

This makes 2.1 primarily a UI and interaction feature rather than a model integration project.


## User Flow

### Primary Flow

1. user opens the handwriting window from the main window
2. user writes a formula on the canvas
3. when no input occurs for `700ms`, recognition is triggered
4. recognized LaTeX is shown in an editable text area
5. rendered preview updates automatically
6. user optionally edits the result
7. user clicks `Insert`
8. the main window receives the final LaTeX and refreshes its preview/history logic

### Correction Flow

1. user writes formula
2. result is incorrect
3. user uses `Erase` or `Select and Correct`
4. user rewrites the affected area
5. recognition reruns after idle
6. user edits text manually if needed


## UX Decisions

### 1. Window Model

Use a separate `HandwritingWindow`.

Reason:

- keeps `main.py` complexity contained
- allows tool-specific layout
- avoids contaminating the main recognition screen
- matches user expectation from TeXstudio-style assistants

### 2. Auto Recognition Trigger

Use debounce on input idle, not immediate recognition on every stroke.

Recommended default:

- recognition delay: `700ms`
- if currently recognizing, coalesce new requests and run once more after current inference finishes

Reason:

- current preview editor uses `300ms` debounce, but handwriting is noisier
- a longer delay avoids excessive worker churn

### 3. Canvas Growth

Do not continuously resize the whole window on every stroke.

Use:

- logical canvas growth when content nears the edge
- optional window size growth in larger steps only when necessary

Reason:

- constant window resizing feels unstable
- canvas growth is enough for the first release

### 4. Erase Strategy

For 2.1, erase should operate on strokes, not pixels.

Reason:

- stroke-level undo/redo stays simple
- implementation is stable
- good enough for first release

### 5. Select and Correct Strategy

For 2.1, `Select and Correct` should mean:

- draw a rectangular selection
- delete intersecting strokes
- keep non-selected strokes
- allow user to rewrite the removed portion

It should not mean:

- moving selected strokes
- scaling strokes
- symbol-aware correction


## Proposed Architecture

2.1 should introduce a dedicated handwriting domain.

Recommended structure:

```text
src/
  main.py

  handwriting/
    __init__.py
    handwriting_window.py
    ink_canvas.py
    recognizer.py
    stroke_store.py
    tools.py
    types.py
```

### Module Responsibilities

#### `handwriting_window.py`

Responsible for:

- window layout
- toolbar and tool switching
- recognition debounce timer
- recognition state
- LaTeX result editor
- rendered preview
- insert/cancel actions
- communication with main window

#### `ink_canvas.py`

Responsible for:

- collecting pointer input
- rendering strokes
- current tool behavior
- selection rectangle
- exporting a cropped `QImage`
- edge detection for canvas growth

#### `stroke_store.py`

Responsible for:

- stroke list
- deleted stroke handling
- undo stack
- redo stack
- hit-testing for erase and selection

#### `recognizer.py`

Responsible for:

- converting `QImage` to PIL image
- optional preprocessing
- calling existing `ModelWrapper.predict(..., "pix2text")`
- reporting result or failure

#### `tools.py`

Defines:

- `WRITE`
- `ERASE`
- `SELECT_CORRECT`

#### `types.py`

Defines simple data containers:

- `Point`
- `Stroke`
- `CanvasExportResult`


## Main Window Integration

`src/main.py` should remain the application shell and launch point.

Required additions:

### 1. New Entry Action

Add a button or menu action in `MainWindow`:

- label: `手写识别`
- behavior: open `HandwritingWindow`

### 2. Insert Callback

`HandwritingWindow` should return final LaTeX to `MainWindow`.

Recommended behavior after insert:

- call `_set_editor_text_silent(latex)`
- set `self._formula_types[latex] = "pix2text"`
- call `_refresh_preview()` or reuse existing render path
- optionally add to history only after explicit insert

### 3. Shared Model Reuse

Do not create another separate model stack if possible.

Prefer:

- reuse `MainWindow.model`
- call into the same `ModelWrapper`

Reason:

- avoids duplicate worker processes
- avoids duplicate warmup cost
- matches current application architecture


## Recognition Pipeline

### Input

Source:

- `QImage` exported from canvas

### Preprocessing

2.1 should include only lightweight preprocessing:

- crop to stroke bounding box plus padding
- white background
- black pen rendering
- optional image upscale by `2x`
- optional grayscale conversion

Do not add heavy denoise or morphology in v1 of this feature.

Reason:

- keep latency low
- avoid introducing many error-prone knobs before baseline behavior is known

### Inference

Recognizer should call the existing formula mode:

```python
result = model.predict(pil_img, model_name="pix2text")
```

This should remain the default path for 2.1.

### Output

Return:

- raw LaTeX string
- optional normalized LaTeX string
- optional error message


## UI Layout

Recommended window layout:

```text
+-----------------------------------------------------------+
| Toolbar: Write | Erase | Select and Correct | Clear ...   |
+-----------------------------------+-----------------------+
|                                   | LaTeX Result          |
| Ink Canvas                        | editable text area    |
|                                   +-----------------------+
|                                   | Render Preview        |
|                                   | QWebEngine / preview  |
+-----------------------------------+-----------------------+
| Status | Recognizing... | Cancel | Insert                 |
+-----------------------------------------------------------+
```

### Toolbar Buttons

- `Write`
- `Erase`
- `Select and Correct`
- `Clear`
- `Undo`
- `Redo`

### Bottom Buttons

- `Cancel`
- `Insert`

### Status Area

Show:

- `Ready`
- `Writing`
- `Recognizing`
- `Recognition failed`
- `Updated`


## Functional Detail by Tool

### Write

Behavior:

- left mouse or stylus draws a stroke
- stroke is appended on release
- recognition debounce restarts

### Erase

Behavior:

- pointer movement tests intersection with existing strokes
- intersecting strokes are removed as whole units
- each erase action is undoable

### Select and Correct

Behavior:

- user drags a rectangular selection
- selected strokes are highlighted
- releasing the drag marks them as current selection
- pressing inside a correction action removes selected strokes
- new strokes can then be written in that area

For 2.1, selection can be simplified further:

- selecting immediately removes intersecting strokes
- canvas enters write mode again

This is acceptable if implementation time is tight.

### Clear

Behavior:

- clear all strokes
- clear current recognition result
- clear preview

### Undo

Behavior:

- undo last stroke add, stroke erase, selection delete, or clear

### Redo

Behavior:

- redo last undone action


## Class Design

### `HandwritingWindow`

Suggested fields:

```python
self.model
self.canvas
self.result_editor
self.preview_view
self.recognize_timer
self._recognizing
self._recognize_pending
self._last_export_fingerprint
```

Suggested methods:

- `set_tool(tool)`
- `_on_canvas_changed()`
- `_schedule_recognition()`
- `_run_recognition()`
- `_on_recognition_finished(latex, error=None)`
- `_refresh_preview_from_editor()`
- `_insert_result()`

### `InkCanvas`

Suggested fields:

```python
self.strokes
self.undo_stack
self.redo_stack
self.current_stroke
self.current_tool
self.selection_rect
self.pen_width
self.canvas_margin
self.logical_scene_rect
```

Suggested methods:

- `set_tool(tool)`
- `clear_canvas()`
- `undo()`
- `redo()`
- `export_image()`
- `content_bounding_rect()`
- `_grow_scene_if_needed(point)`
- `_erase_at(point)`
- `_select_rect(rect)`


## Signals and Communication

Recommended PyQt signals:

### `InkCanvas`

- `contentChanged`
- `strokeFinished`
- `selectionChanged`

### `HandwritingWindow`

- `latexInserted(str)`

Communication pattern:

1. canvas emits `contentChanged`
2. window restarts debounce timer
3. timer fires
4. recognizer runs
5. result editor updates
6. preview updates
7. insert emits final text back to main window


## State Management

### Recognition State

The window should track:

- idle
- scheduled
- recognizing
- dirty-while-recognizing

Recommended rule:

- if content changes during recognition, set `dirty` flag
- when current recognition finishes, rerun once if `dirty` is set

This prevents overlapping inference calls.

### Undo/Redo State

Represent each action as a command:

- `AddStroke`
- `DeleteStrokes`
- `ClearAll`

This is enough for 2.1.


## Error Handling

Recognition failures must not block the canvas.

Required behavior:

- keep strokes intact
- preserve previous LaTeX unless configured otherwise
- show status text
- allow user to retry by waiting or editing manually

Typical failure cases:

- worker not ready
- worker timeout
- empty crop
- invalid image conversion


## Performance Targets

2.1 targets should stay pragmatic.

Suggested baseline:

- canvas input remains visually smooth during writing
- idle-to-result under `1.5s` on a warmed-up environment for short formulas
- no UI freeze during recognition

Do not optimize prematurely beyond this.


## Implementation Plan

### Phase 1: Base Window and Canvas

Deliver:

- new `handwriting` package
- `HandwritingWindow`
- `InkCanvas`
- write tool
- clear
- undo/redo

Acceptance:

- user can write
- user can clear
- user can undo/redo strokes

### Phase 2: pix2text Recognition

Deliver:

- canvas export
- debounce timer
- recognizer wrapper
- LaTeX result text area
- rendered preview

Acceptance:

- handwriting window can recognize a simple handwritten formula
- result updates after idle
- preview renders correctly

### Phase 3: Erase and Select-and-Correct

Deliver:

- stroke erase
- rectangular selection delete
- correction rewrite flow

Acceptance:

- user can remove wrong strokes without resetting whole canvas

### Phase 4: Main Window Integration

Deliver:

- open handwriting window from main UI
- insert recognized LaTeX back into main editor
- preserve preview consistency

Acceptance:

- inserted result behaves like existing recognized formulas

### Phase 5: Polish

Deliver:

- status messaging
- edge growth behavior
- keyboard shortcuts
- optional remembered window geometry


## File-Level Change Plan

### New Files

- `src/handwriting/__init__.py`
- `src/handwriting/handwriting_window.py`
- `src/handwriting/ink_canvas.py`
- `src/handwriting/recognizer.py`
- `src/handwriting/stroke_store.py`
- `src/handwriting/tools.py`
- `src/handwriting/types.py`

### Modified Files

- [`src/main.py`](e:/LaTexSnipper/src/main.py)

Expected changes in `main.py`:

- import handwriting window
- add launch action/button
- add callback for inserted LaTeX
- reuse existing preview/editor helper methods


## Technical Risks

### Risk 1: pix2text Accuracy on Handwriting

This is the main product risk.

Mitigation:

- keep the LaTeX text area editable
- keep recognition trigger lightweight and repeatable
- tune preprocessing only after baseline testing

### Risk 2: Repeated Recognition Churn

If recognition fires too often, UX will feel noisy.

Mitigation:

- `700ms` debounce
- no parallel recognitions
- dirty rerun flag only once

### Risk 3: Canvas Export Quality

If the crop is too loose or too tight, results degrade.

Mitigation:

- crop to stroke bounds plus padding
- fixed white background
- stable pen width rendering

### Risk 4: main.py Growth

`main.py` is already large.

Mitigation:

- keep all handwriting logic outside `main.py`
- only add launch and insert integration points there


## Testing Plan

### Manual Test Set

Use a small formula set first:

- `x^2`
- `\frac{1}{2}`
- `\int_0^1 x dx`
- `\sqrt{a+b}`
- `\sum_{i=1}^{n} i`
- `\begin{bmatrix} a & b \\ c & d \end{bmatrix}`

Verify:

- write flow
- erase flow
- selection correction flow
- undo/redo
- idle recognition
- insert into main window

### Regression Checks

Ensure no breakage in:

- screenshot recognition
- main preview rendering
- history/favorites behavior
- existing `pix2text` worker lifecycle


## 2.1 Minimum Deliverable

If schedule is tight, 2.1 must still ship with:

- independent handwriting window
- write
- clear
- undo
- redo
- idle-triggered `pix2text` recognition
- editable LaTeX output
- rendered preview
- insert back to main window

This is the true minimum useful version.

`Erase` and `Select and Correct` can be simplified, but the above should not be cut.


## Recommendation

Build 2.1 as a new handwriting input window that reuses the current `pix2text` worker and the current LaTeX preview flow.

Keep the first release narrow:

- stroke-based canvas
- debounce recognition
- manual correction
- insert back to main editor

Do not overbuild around perfect correction semantics before baseline recognition quality is measured.
