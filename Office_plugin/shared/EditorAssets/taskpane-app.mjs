import {TaskPaneFormula, DEFAULT_LATEX} from './taskpane-formula.mjs';

export function startTaskPane() {
  const element = id => document.getElementById(id);
  const els = Object.fromEntries(['hostLabel', 'connectButton', 'statusBanner', 'statusText', 'equationLabel',
    'previewHost', 'latexSource', 'sourceModeNote', 'displayMode', 'displayLabel', 'autoNumber',
    'autoNumberLabel', 'manualNumber', 'ocrButton', 'insertButton'].map(id => [id, element(id)]));
  const state = {busy: false, ocrActive: false, strings: {}};
  let applying = false;
  const post = message => window.chrome?.webview?.postMessage(message);
  const formula = new TaskPaneFormula({previewHost: els.previewHost, sourceHost: els.latexSource,
    modeNote: els.sourceModeNote, onChange: () => emitState(), onAccept: () => post({type: 'insert', ...readState()})});

  function readState() {
    const values = {latex: formula.latex};
    if (els.displayMode) Object.assign(values, {display: els.displayMode.checked,
      autoNumber: els.autoNumber.checked, manualNumber: els.manualNumber.value});
    return values;
  }

  function emitState() {
    if (!applying) post({type: 'state', ...readState()});
  }

  function applyLabels(strings) {
    if (!strings) return;
    state.strings = {...state.strings, ...strings};
    for (const [id, key] of [['hostLabel', 'officePlugin'], ['connectButton', 'connect'],
      ['equationLabel', 'equation'], ['displayLabel', 'display'], ['autoNumberLabel', 'autoNumber'],
      ['ocrButton', 'screenshotOcr'], ['insertButton', 'insert']]) {
      if (els[id] && strings[key]) els[id].textContent = strings[key];
    }
    if (els.manualNumber && strings.manualNumber) els.manualNumber.placeholder = strings.manualNumber;
  }

  function applyState(payload) {
    applying = true;
    try {
      applyLabels(payload.strings);
      const locale = String(payload.locale || 'zh').toLowerCase();
      document.documentElement.lang = locale.startsWith('zh') ? 'zh-CN' : 'en';
      const latex = typeof payload.latex === 'string' && payload.latex.trim()
        ? payload.latex
        : DEFAULT_LATEX;
      formula.load(latex, locale);
      if (els.displayMode) {
        els.displayMode.checked = Boolean(payload.display);
        els.autoNumber.checked = Boolean(payload.autoNumber);
        els.manualNumber.value = payload.manualNumber || '';
      }
    } finally { applying = false; }
  }

  function applyStatus(payload) {
    state.busy = Boolean(payload.busy);
    state.ocrActive = Boolean(payload.ocrActive);
    const kind = payload.kind || 'info';
    els.statusBanner.className = `status-banner ${state.ocrActive ? 'pending' : kind === 'success' ? 'success' : kind === 'error' ? 'error' : ''}`.trim();
    els.statusText.textContent = payload.message || '';
    els.ocrButton.textContent = state.ocrActive ? state.strings.cancelOcr || 'Cancel OCR'
      : state.strings.screenshotOcr || els.ocrButton.textContent;
    for (const button of [els.connectButton, els.insertButton]) button.disabled = state.busy;
    els.ocrButton.disabled = false;
    els.ocrButton.classList.toggle('active', state.ocrActive);
  }

  function apply(payload) {
    if (payload?.type === 'state') applyState(payload);
    if (payload?.type === 'status') applyStatus(payload);
  }

  for (const input of [els.displayMode, els.autoNumber, els.manualNumber].filter(Boolean)) {
    input.addEventListener(input === els.manualNumber ? 'input' : 'change', () => {
      if (input === els.autoNumber && input.checked) {
        els.manualNumber.value = '';
        els.displayMode.checked = true;
      }
      if (input === els.manualNumber && input.value.trim()) {
        els.autoNumber.checked = false;
        els.displayMode.checked = true;
      }
      emitState();
    });
  }
  els.connectButton.addEventListener('click', () => post({type: 'connect', ...readState()}));
  els.ocrButton.addEventListener('click', () => post({type: 'ocr', ...readState()}));
  els.insertButton.addEventListener('click', () => post({type: 'insert', ...readState()}));
  window.LaTeXSnipperTaskPane = {apply};
  for (const payload of window.__latexSnipperTaskPanePending || []) apply(payload);
  window.__latexSnipperTaskPanePending = [];
  post({type: 'state', ...readState()});
}
