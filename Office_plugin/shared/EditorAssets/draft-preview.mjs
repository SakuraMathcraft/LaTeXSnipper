// A single revision covers source and typography. Render results never mutate the draft.
export class DraftPreview {
  constructor({send, snapshot, changed, result, schedule = fn => setTimeout(fn, 180), cancel = handle => clearTimeout(handle)}) {
    Object.assign(this, {send, snapshot, changed, result, schedule, cancel});
    this.session = null; this.revision = 0; this.pending = null;
    this.active = false; this.locked = false; this.composing = false;
  }
  invalidate() {
    if (this.pending !== null) this.cancel(this.pending);
    this.pending = null;
    this.revision++;
    if (this.session !== null) this.send({type: 'cancelPreview', session: this.session});
    this.changed();
  }
  configure(session) {
    this.invalidate(); this.session = session; this.active = false;
    this.locked = false; this.composing = false;
  }
  update() {
    this.invalidate();
    if (!this.active || this.locked || this.composing) return;
    const revision = this.revision;
    this.pending = this.schedule(() => {
      this.pending = null;
      const draft = this.snapshot();
      if (draft && revision === this.revision) this.send({type: 'preview', session: this.session, revision, ...draft});
    });
  }
  setActive(active) { this.active = active; this.update(); }
  setLocked(locked) { this.locked = locked; this.update(); }
  setComposing(composing) { this.composing = composing; this.update(); }
  receive(response) {
    if (!this.active || this.locked || this.composing || response.session !== this.session || response.revision !== this.revision) return false;
    this.result(response); return true;
  }
  stop() { this.active = false; this.invalidate(); }
}
