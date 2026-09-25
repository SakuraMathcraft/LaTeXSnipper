import {entryTemplate, templateParts} from './template-catalog.mjs';

export class TemplateInsertion {
  constructor({source, sync, mathfield, sourceHost, onInsert, isComposing}) {
    Object.assign(this, {source, sync, mathfield, onInsert, isComposing});
    this.target = 'source';
    this.visualSelection = null;
    this.focusOwner = null;
    this.keyboardEntry = false;
    this.allowVisualFocus = false;
    document.addEventListener('keydown', event => { this.keyboardEntry = event.key === 'Tab' && !event.isComposing; }, true);
    document.addEventListener('pointerdown', () => { this.keyboardEntry = false; this.allowVisualFocus = false; }, true);
    document.addEventListener('focusin', event => {
      if (event.target !== mathfield) {
        this.focusOwner = event.target;
        this.allowVisualFocus = false;
        this.keyboardEntry = false;
      } else if (this.keyboardEntry) {
        this.target = 'visual';
        this.allowVisualFocus = true;
        this.keyboardEntry = false;
        this.rememberVisual();
      } else if (!this.allowVisualFocus && this.focusOwner?.isConnected) {
        // MathLive may deliver a delayed focus after the user has moved to source or a toolbar.
        this.focusOwner.focus();
      }
    });
    sourceHost.addEventListener('focusin', () => { this.target = 'source'; });
    // An already-focused MathLive field need not emit focusin after session reset.
    for (const event of ['pointerdown', 'keydown']) mathfield.addEventListener(event, () => {
      this.allowVisualFocus = true; this.target = 'visual'; this.rememberVisual();
    }, true);
    mathfield.addEventListener('focusin', () => { if (this.target === 'visual') this.rememberVisual(); });
    mathfield.addEventListener('selection-change', () => {
      if (mathfield.hasFocus()) this.rememberVisual();
    });
    mathfield.addEventListener('focusout', () => this.rememberVisual());
  }
  reset() { this.target = 'source'; this.visualSelection = null; this.previewOrigin = null; }
  setPreview(active) {
    if (active) {
      this.previewOrigin = {target: this.target, selection: this.visualSelection, revision: this.source.revision};
      this.target = 'source';
      this.source.focus();
    } else {
      const origin = this.previewOrigin;
      this.previewOrigin = null;
      if (origin?.revision === this.source.revision) {
        this.target = origin.target;
        this.visualSelection = origin.selection;
      }
      this.restoreFocus();
    }
  }
  rememberVisual() {
    this.visualSelection = {revision: this.source.revision, selection: structuredClone(this.mathfield.selection)};
  }
  get blocked() { return this.sync.locked || this.source.composing || this.sync.visualComposing || this.isComposing(); }
  restoreFocus() {
    if (this.blocked) return;
    if (this.target === 'visual' && this.sync.visualEnabled) {
      const saved = this.visualSelection;
      this.allowVisualFocus = true;
      HTMLElement.prototype.focus.call(this.mathfield);
      this.visualSelection = saved;
      this.restoreVisualSelection();
    } else this.source.focus();
  }
  restoreVisualSelection() {
    if (this.visualSelection?.revision === this.source.revision) this.mathfield.selection = this.visualSelection.selection;
  }
  insert(entry, {rows = 2, columns = 2, range} = {}) {
    if (this.blocked) return false;
    const template = entryTemplate(entry, rows, columns);
    if (!range && this.target === 'visual' && this.sync.performVisual(() => {
      const saved = this.visualSelection;
      this.allowVisualFocus = true;
      HTMLElement.prototype.focus.call(this.mathfield);
      this.visualSelection = saved;
      this.restoreVisualSelection();
      const selected = this.mathfield.getValue(this.mathfield.selection, 'latex');
      const latex = templateParts(template, selected).map(part => part.hole ? '#?' : part.text).join('');
      this.mathfield.insert(latex, {format: 'latex', insertionMode: 'replaceSelection', selectionMode: 'placeholder'});
    })) {
      this.rememberVisual();
    } else {
      this.source.insertTemplate(templateParts(template, range ? '' : this.source.selectedText), range);
    }
    this.onInsert();
    return true;
  }
}
