import test from 'node:test';
import assert from 'node:assert/strict';
import {DraftPreview} from '../../../office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets/draft-preview.mjs';
function fixture() {
  const messages = [], results = [], jobs = new Map(); let id = 0;
  let draft = {latex: 'x', typography: {fontSizePoints: 12}};
  const preview = new DraftPreview({send: m => messages.push(m), snapshot: () => draft,
    changed() {}, result: r => results.push(r), schedule: fn => { jobs.set(++id, fn); return id; }, cancel: id => jobs.delete(id)});
  const flush = () => { const pending = [...jobs.values()]; jobs.clear(); pending.forEach(fn => fn()); };
  preview.configure(1);
  return {preview, messages, results, jobs, flush, setDraft: value => { draft = value; }};
}
test('source and style edits coalesce; late results are discarded even before the next render starts', () => {
  const f = fixture(); f.preview.setActive(true); f.flush();
  const old = f.messages.at(-1);
  f.setDraft({latex: 'y', typography: {fontSizePoints: 14}}); f.preview.update();
  assert.equal(f.preview.receive(old), false);
  f.setDraft({latex: 'z', typography: {fontSizePoints: 16}}); f.preview.update(); f.flush();
  const current = f.messages.at(-1);
  assert.equal(current.latex, 'z'); assert.equal(current.typography.fontSizePoints, 16);
  assert.equal(f.preview.receive(current), true); assert.equal(f.results.length, 1);
});
test('locking cancels timers and renders, then resumes the current draft after submission failure', () => {
  const f = fixture(); f.preview.setActive(true); f.preview.setLocked(true); f.flush();
  assert.equal(f.messages.some(m => m.type === 'preview'), false);
  f.preview.setLocked(false); f.flush(); const request = f.messages.at(-1);
  f.preview.setLocked(true); assert.equal(f.preview.receive(request), false);
  f.preview.setLocked(false); f.flush(); assert.equal(f.preview.receive(f.messages.at(-1)), true);
});
test('composition, cancellation and a new session invalidate outstanding work', () => {
  const f = fixture(); f.preview.setActive(true); f.flush(); const first = f.messages.at(-1);
  f.preview.setComposing(true); f.flush(); assert.equal(f.preview.receive(first), false);
  f.preview.setComposing(false); f.flush(); const second = f.messages.at(-1);
  f.preview.stop(); assert.equal(f.preview.receive(second), false);
  f.preview.configure(2); f.preview.setActive(true); f.flush();
  assert.equal(f.preview.receive(second), false); assert.equal(f.preview.receive(f.messages.at(-1)), true);
});
test('invalid draft sends no render request', () => {
  const f = fixture(); f.setDraft(null); f.preview.setActive(true); f.flush();
  assert.equal(f.messages.some(m => m.type === 'preview'), false);
});
