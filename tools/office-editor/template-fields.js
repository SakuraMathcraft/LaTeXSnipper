import {StateEffect, StateField, EditorSelection, Prec} from '@codemirror/state';
import {Decoration, EditorView, keymap, WidgetType} from '@codemirror/view';

const setFields = StateEffect.define();
class EmptyField extends WidgetType {
  toDOM() {
    const marker = document.createElement('span');
    marker.className = 'cm-template-hole';
    marker.setAttribute('aria-hidden', 'true');
    return marker;
  }
}
const emptyField = new EmptyField();
const fields = StateField.define({
  create: () => null,
  update(value, transaction) {
    for (const effect of transaction.effects) if (effect.is(setFields)) return effect.value;
    if (!value || transaction.isUserEvent('undo') || transaction.isUserEvent('redo')) return null;
    const ranges = value.ranges.map(range => ({
      from: transaction.changes.mapPos(range.from, -1), to: transaction.changes.mapPos(range.to, 1)
    }));
    const current = ranges[value.active];
    const selection = transaction.state.selection.main;
    return selection.from < current.from || selection.to > current.to ? null : {...value, ranges};
  },
  provide: field => EditorView.decorations.from(field, value => value ? Decoration.set(
    value.ranges.slice(0, -1).map(range => range.from === range.to
      ? Decoration.widget({widget: emptyField}).range(range.from)
      : Decoration.mark({class: 'cm-template-field'}).range(range.from, range.to)), true) : Decoration.none)
});

function moveField(direction) {
  return view => {
    const value = view.state.field(fields);
    if (!value || view.composing || view.state.readOnly) return false;
    const next = value.active + direction;
    if (next < 0 || next >= value.ranges.length) return false;
    const range = value.ranges[next];
    view.dispatch({selection: EditorSelection.single(range.from, range.to), scrollIntoView: true,
      effects: setFields.of(next === value.ranges.length - 1 ? null : {...value, active: next})});
    return true;
  };
}

export const templateFields = [fields, Prec.highest(keymap.of([
  {key: 'Tab', run: moveField(1), shift: moveField(-1)},
  {key: 'Escape', run: view => {
    if (!view.state.field(fields)) return false;
    view.dispatch({effects: setFields.of(null)}); return true;
  }}
]))];

export function templateTransaction(parts, from, to, following = '') {
  let insert = '';
  const ranges = [];
  for (const part of parts) {
    if (part.hole) ranges.push({from: from + insert.length, to: from + insert.length});
    else insert += part.text;
  }
  if (/\\[a-zA-Z]+$/.test(insert) && /^[a-zA-Z]/.test(following)) insert += ' ';
  ranges.push({from: from + insert.length, to: from + insert.length});
  return {changes: {from, to, insert}, selection: EditorSelection.single(ranges[0].from),
    effects: setFields.of(ranges.length > 1 ? {ranges, active: 0} : null), scrollIntoView: true};
}
