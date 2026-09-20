import {entryTemplate, templateParts} from './template-catalog.mjs';

export class TemplateInsertion {
  constructor({source, sync, mathfield, sourceHost, onInsert}) {
    Object.assign(this, {source, sync, mathfield, onInsert});
    this.target = 'source';
    this.visualSelection = null;
    sourceHost.addEventListener('focusin', () => { this.target = 'source'; });
    // An already-focused MathLive field need not emit focusin after session reset.
    for (const event of ['pointerdown', 'keydown']) mathfield.addEventListener(event, () => {
      this.target = 'visual'; this.rememberVisual();
    }, true);
    mathfield.addEventListener('focusin', () => { this.target = 'visual'; this.rememberVisual(); });
    mathfield.addEventListener('selection-change', () => {
      if (mathfield.hasFocus()) this.rememberVisual();
    });
    mathfield.addEventListener('focusout', () => this.rememberVisual());
  }
  reset() { this.target = 'source'; this.visualSelection = null; }
  rememberVisual() {
    this.visualSelection = {revision: this.source.revision, selection: structuredClone(this.mathfield.selection)};
  }
  get blocked() { return this.sync.locked || this.source.composing || this.sync.visualComposing; }
  restoreFocus() {
    if (this.blocked) return;
    if (this.target === 'visual' && this.sync.visualEnabled) {
      const saved = this.visualSelection;
      this.mathfield.focus();
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
      this.mathfield.focus();
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
