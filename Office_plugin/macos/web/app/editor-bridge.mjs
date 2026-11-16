// Stands in for MathLiveFormulaEditorForm: the shared editor.js posts the same
// messages it posts to WebView2, previews render locally with the shared
// typography renderer, and accept/cancel go to the task pane runtime, which is
// the only context allowed to change the document.
/* global Office */
import {renderSvg, startRenderer, svgDataUrl} from './renderer.mjs';

let session = null;
let latestPreview = 0;

const editor = () => globalThis.LaTeXSnipperEditor;
const toParent = message => Office.context.ui.messageParent(JSON.stringify(message));

async function preview(message) {
  const ticket = ++latestPreview;
  const response = {session: message.session, revision: message.revision};
  try {
    const rendered = await renderSvg(message.latex, message.display, message.typography);
    Object.assign(response, {image: svgDataUrl(rendered.svg), widthPoints: rendered.widthPoints,
      heightPoints: rendered.heightPoints, warnings: rendered.warnings});
  } catch (error) {
    response.error = error?.message || String(error);
  }
  // Stale previews are dropped here and again by DraftPreview's revision check.
  if (ticket === latestPreview && message.session === session) editor()?.previewResult(response);
}

function fromEditor(message) {
  if (!message || message.session !== session) return;
  if (message.type === 'preview') preview(message);
  else if (message.type === 'cancelPreview') latestPreview++;
  else if (message.type === 'accept' || message.type === 'cancel') toParent(message);
}

function fromParent(arg) {
  let message;
  try { message = JSON.parse(arg.message); } catch { return; }
  if (message.type === 'init') {
    session = message.session;
    const payload = {...message, display: message.forceDisplay ? true : message.display};
    if (editor()) editor().init(payload);
    else globalThis.__latexSnipperPendingInit = payload;
  } else if (message.type === 'submitFailed' && message.session === session) {
    editor()?.setSubmitting(false);
    editor()?.setStatus(message.message);
  }
}

globalThis.chrome = {...(globalThis.chrome || {}), webview: {postMessage: fromEditor}};

Office.onReady(() => {
  Office.context.ui.addHandlerAsync(Office.EventType.DialogParentMessageReceived, fromParent, () =>
    toParent({type: 'ready'}));
  startRenderer().catch(error => editor()?.setStatus(error?.message || String(error)));
});
