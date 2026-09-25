import {comparableLatex, inspectLatex, isMathMl} from './latex-structure.mjs';

export class SourceSync {
  constructor({source, mathfield, readVisual, onMode, schedule = callback => setTimeout(callback, 120), cancel = handle => clearTimeout(handle)}) {
    Object.assign(this, {source, mathfield, readVisual, onMode, schedule, cancel});
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
      this.setMode(false, 'mathml'); return;
    }
    try {
      this.mathfield.setValue(value, {silenceNotifications: true});
      const comparable = comparableLatex(value);
      const safe = comparable !== null && comparable === comparableLatex(this.readVisual())
        && !inspectLatex(value).length && !this.mathfield.errors?.length;
      this.setMode(safe, safe ? '' : 'sourceOnly');
    } catch { this.setMode(false, 'sourceOnly'); }
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
      const value = this.readVisual();
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
  history(redo) {
    if (this.locked || this.composing || this.visualComposing) return;
    this.stopPending(); this.ticket = null;
    if (redo) this.source.redo(); else this.source.undo();
    this.refresh();
  }
}
