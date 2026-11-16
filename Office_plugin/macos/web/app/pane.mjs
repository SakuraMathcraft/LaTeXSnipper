// Hosts the shared task pane (taskpane-app.mjs) without WebView2: the page's
// window.chrome.webview.postMessage calls arrive here and replies go through
// window.LaTeXSnipperTaskPane.apply, exactly as on Windows.
const DRAFT_FIELDS = ['latex', 'display', 'autoNumber', 'manualNumber'];

export class Pane {
  constructor() {
    this.current = {latex: '', display: false, autoNumber: false, manualNumber: ''};
    this.lastStatus = {kind: 'info', message: '', busy: false, ocrActive: false};
    this.handlers = {};
    globalThis.chrome = {...(globalThis.chrome || {}), webview: {postMessage: message => this.receive(message)}};
  }

  async mount() {
    const {startTaskPane} = await import('/shared/taskpane-app.mjs');
    startTaskPane();
  }

  configure({strings, locale, ...handlers}) {
    this.handlers = handlers;
    this.apply({type: 'state', strings, locale, ...this.current});
  }

  receive(message) {
    if (!message || typeof message !== 'object') return;
    for (const field of DRAFT_FIELDS) if (message[field] !== undefined) this.current[field] = message[field];
    if (message.type === 'insert') this.handlers.onInsert?.(this.state());
    else if (message.type === 'connect') this.handlers.onConnect?.();
    else if (message.type === 'ocr') this.handlers.onOcr?.();
  }

  apply(payload) {
    if (globalThis.LaTeXSnipperTaskPane) globalThis.LaTeXSnipperTaskPane.apply(payload);
    else (globalThis.__latexSnipperTaskPanePending ||= []).push(payload);
  }

  state() {
    return {...this.current};
  }

  /** Shows a draft (latex and, in Word, display/numbering options); `updateMode` marks a loaded formula. */
  load({updateMode = false, ...draft}) {
    for (const field of DRAFT_FIELDS) if (draft[field] !== undefined) this.current[field] = draft[field];
    this.apply({type: 'state', updateMode, ...this.current});
  }

  /** Partial updates keep the previous message, so clearing busy does not erase it. */
  status(update) {
    this.lastStatus = {...this.lastStatus, ...update};
    this.apply({type: 'status', ...this.lastStatus});
  }
}
