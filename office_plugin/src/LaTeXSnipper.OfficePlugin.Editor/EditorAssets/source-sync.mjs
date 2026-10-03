import {comparableLatex, inspectLatex, isMathMl} from './latex-structure.mjs';
import {inheritFormulaColor, outerColor} from './formula-color.mjs';

// MathLive serializes visual rows on one line. Line breaks here are TeX layout
// whitespace, so the source pane can show the same rows without changing math.
export function formatVisualLatex(value) {
  let depth = 0, textDepth = -1, awaitingText = false, result = '';
  for (const token of value.match(/\\[a-zA-Z]+\*?|\\[^\r\n]|\s+|./gs) || []) {
    if (/^\\(?:text|textbf|textit|textrm|textsf|texttt|operatorname)\*?$/.test(token)) awaitingText = true;
    if (token === '{') { depth++; if (awaitingText) { if (textDepth < 0) textDepth = depth; awaitingText = false; } }
    result += token === '\\\\' && textDepth < 0 ? '\\\\\n' : token;
    if (token === '}') { if (depth === textDepth) textDepth = -1; depth--; }
  }
  return result;
}

export class SourceSync {
  constructor({source, mathfield, readVisual, recreateMathfield, onMode, schedule = callback => setTimeout(callback, 120), cancel = handle => clearTimeout(handle)}) {
    Object.assign(this, {source, mathfield, readVisual, recreateMathfield, onMode, schedule, cancel});
    this.pending = null;
    this.ticket = null;
    this.composing = false;
    this.visualComposing = false;
    this.visualEnabled = false;
    this.locked = false;
  }
  stopPending() { if (this.pending !== null) this.cancel(this.pending); this.pending = null; }
  setMode(enabled, reason = '') { this.visualEnabled = enabled; this.mathfield.readOnly = this.locked || !enabled; this.onMode(reason); }
  setLocked(locked) {
    this.locked = locked;
    this.ticket = null;
    this.source.setEnabled(!locked);
    this.mathfield.readOnly = locked || !this.visualEnabled;
  }
  load(value) {
    this.stopPending(); this.ticket = null; this.composing = false; this.visualComposing = false;
    this.source.reset(value);
    this.refresh();
  }
  sourceChanged({origin, composing}) {
    this.stopPending(); this.ticket = null;
    if (origin === 'visual') return;
    this.setMode(false, 'updating');
    if (this.composing || composing) return;
    const revision = this.source.revision;
    this.pending = this.schedule(() => {
      this.pending = null;
      if (revision === this.source.revision && !this.composing) this.refresh();
    });
  }
  composition(active) {
    this.composing = active;
    this.stopPending(); this.ticket = null;
    this.setMode(false, 'composing');
    if (!active) this.sourceChanged({origin: 'source', composing: false});
  }
  refresh() {
    this.stopPending(); this.ticket = null;
    const value = this.source.value;
    if (isMathMl(value)) {
      this.mathfield.setValue('', {silenceNotifications: true});
      if (this.readVisual() && this.recreateMathfield) this.mathfield = this.recreateMathfield();
      this.setMode(false, 'mathml'); return;
    }
    try {
      // MathLive only renders a displaylines array at the field root, not inside
      // textcolor. Project the outer global color into CSS; the source keeps its
      // wrapper and visual commits below restore it from that same source.
      const color = outerColor(value);
      const visualSource = color?.body ?? value;
      if (this.mathfield.style) this.mathfield.style.color = color?.color || '#000000';
      this.mathfield.setValue(visualSource, {silenceNotifications: true});
      const comparable = comparableLatex(visualSource);
      const structuralError = Boolean(inspectLatex(value).length);
      let visual = this.readVisual();
      // A previous unsupported formula can leave MathLive's serializer state in
      // the reused field. Confirm a mismatch with a fresh parser before locking
      // visual editing; only that second result describes the source itself.
      if (!structuralError && comparable !== null && this.recreateMathfield
          && (this.mathfield.errors?.length || comparable !== comparableLatex(visual))) {
        this.mathfield = this.recreateMathfield();
        this.mathfield.setValue(visualSource, {silenceNotifications: true});
        visual = this.readVisual();
      }
      const invalid = structuralError || Boolean(this.mathfield.errors?.length);
      const safe = comparable !== null && comparable === comparableLatex(visual) && !invalid;
      this.setMode(safe, safe ? '' : invalid ? 'invalid' : 'sourceOnly');
    } catch { this.setMode(false, 'invalid'); }
  }
  beforeVisualInput(event) {
    if (this.locked) { event.preventDefault(); return; }
    if (event.inputType === 'historyUndo' || event.inputType === 'historyRedo') {
      event.preventDefault(); this.history(event.inputType === 'historyRedo'); return;
    }
    if (!this.visualEnabled || this.composing || this.pending !== null) { event.preventDefault(); return; }
    this.ticket = this.source.revision;
  }
  visualInput() {
    if (this.locked || this.visualComposing) return;
    if (this.ticket === this.source.revision && this.visualEnabled && !this.composing) {
      const color = outerColor(this.source.value)?.color;
      const visual = formatVisualLatex(this.readVisual());
      const value = color ? inheritFormulaColor(visual, color) : visual;
      this.ticket = null;
      this.source.replace(value, 'visual');
    }
  }
  visualComposition(active) {
    this.visualComposing = active;
    if (!active) this.visualInput();
  }
  performVisual(action) {
    if (this.locked || this.composing || this.visualComposing) return false;
    if (this.pending !== null) this.refresh();
    if (!this.visualEnabled) return false;
    this.ticket = this.source.revision;
    action(); this.visualInput();
    return true;
  }
  adoptVisual() {
    if (this.locked || this.composing || this.visualComposing) return false;
    const color = outerColor(this.source.value)?.color;
    const visual = formatVisualLatex(this.readVisual());
    this.source.replace(color ? inheritFormulaColor(visual, color) : visual, 'visual');
    this.refresh();
    return this.visualEnabled;
  }
  history(redo) {
    if (this.locked || this.composing || this.visualComposing) return;
    this.stopPending(); this.ticket = null;
    if (redo) this.source.redo(); else this.source.undo();
    this.refresh();
  }
}
