import {EditorState, Annotation, Compartment, Transaction} from '@codemirror/state';
import {EditorView, keymap, lineNumbers, highlightActiveLine, highlightActiveLineGutter, drawSelection} from '@codemirror/view';
import {StreamLanguage, syntaxHighlighting, HighlightStyle, bracketMatching, indentOnInput} from '@codemirror/language';
import {tags} from '@lezer/highlight';
import {defaultKeymap, history, historyKeymap, undo, redo, indentWithTab, isolateHistory} from '@codemirror/commands';
import {search, searchKeymap, highlightSelectionMatches} from '@codemirror/search';
import {autocompletion, closeBrackets, closeBracketsKeymap, completionKeymap, snippetCompletion} from '@codemirror/autocomplete';
import {linter, lintGutter} from '@codemirror/lint';
import {inspectLatex, isMathMl} from '../../office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets/latex-structure.mjs';

import {templateFields, templateTransaction} from './template-fields.js';

const origin = Annotation.define();
const language = StreamLanguage.define({
  startState: () => ({depth: 0, environment: false, envDepth: 0, envChange: 0}),
  token(stream, state) {
    if (stream.eatSpace()) return null;
    if (stream.match(/%.*/)) return 'comment';
    const env = stream.match(/\\(begin|end)(?![a-zA-Z])/);
    if (env) { state.environment = true; state.envChange = env[1] === 'begin' ? 1 : -1; return 'keyword'; }
    if (stream.match(/\\[a-zA-Z]+\*?|\\./)) return 'keyword';
    if (stream.eat('{')) { state.depth++; return 'bracket'; }
    if (stream.eat('}')) {
      state.depth = Math.max(0, state.depth - 1);
      if (state.environment) state.envDepth = Math.max(0, state.envDepth + state.envChange);
      state.environment = false; return 'bracket';
    }
    if (state.environment && stream.match(/[\w*]+/)) return 'typeName';
    if (stream.match(/\d+(?:\.\d+)?/)) return 'number';
    if (stream.match(/[&_^=+\-*/<>|]/)) return 'operator';
    if (stream.match(/[()[\]]/)) return 'bracket';
    if (stream.match(/[\u2e80-\uffef]+/)) return 'string';
    stream.next(); return null;
  },
  indent: (state, text, context) => Math.max(0, state.depth + state.envDepth
    - (text.startsWith('}') || /^\\end\b/.test(text) ? 1 : 0)) * context.unit,
  languageData: {commentTokens: {line: '%'}, closeBrackets: {brackets: ['(', '[', '{']}}
});
const highlight = HighlightStyle.define([
  {tag: tags.keyword, color: 'var(--source-command)'},
  {tag: tags.typeName, color: 'var(--source-environment)'},
  {tag: tags.number, color: 'var(--source-number)'},
  {tag: tags.operator, color: 'var(--source-operator)'},
  {tag: tags.bracket, color: 'var(--source-bracket)'},
  {tag: tags.string, color: 'var(--source-text)'},
  {tag: tags.comment, color: 'var(--source-comment)', fontStyle: 'italic'}
]);
const environments = ['align', 'align*', 'aligned', 'gather', 'gathered', 'split', 'cases', 'matrix', 'pmatrix', 'bmatrix', 'vmatrix', 'Vmatrix', 'array'];

export class SourceEditor {
  constructor(parent, {onChange, onComposition, commands = [], completeTemplate}) {
    this.revision = 0;
    this.composing = false;
    this.editable = new Compartment();
    const commandOptions = commands.map(({label, entry}) => ({label, type: 'function',
      ...(entry ? {detail: entry.en, apply: (_view, _completion, from, to) => completeTemplate(entry, {from, to})} : {})}));
    this.extensions = [templateFields, language, syntaxHighlighting(highlight), lineNumbers(), highlightActiveLine(), highlightActiveLineGutter(),
      drawSelection(), bracketMatching(), indentOnInput(), closeBrackets(), history(), search({top: true}), highlightSelectionMatches(),
      lintGutter(), linter(view => isMathMl(view.state.doc.toString()) ? [] : inspectLatex(view.state.doc.toString()), {delay: 250}),
      autocompletion({override: [context => {
        const env = context.matchBefore(/\\begin\{[\w*]*$/);
        if (env) return {from: env.from + 7, options: environments.map(name => snippetCompletion(
          `${name}}\n\t\${body}\n\\end{${name}}`, {label: name, type: 'type'})), validFor: /^[\w*]*$/};
        const command = context.matchBefore(/\\[a-zA-Z]*$/);
        return command ? {from: command.from, options: commandOptions, validFor: /^\\[a-zA-Z]*$/} : null;
      }]}),
      keymap.of([...closeBracketsKeymap, ...completionKeymap, ...defaultKeymap, ...historyKeymap, ...searchKeymap, indentWithTab]),
      this.editable.of(EditorView.editable.of(true)),
      EditorView.contentAttributes.of({'aria-label': 'LaTeX source', spellcheck: 'false'}),
      EditorView.domEventHandlers({
        compositionstart: () => { this.composing = true; onComposition(true); },
        compositionend: () => { queueMicrotask(() => { this.composing = false; onComposition(false); }); }
      }),
      EditorView.updateListener.of(update => {
        if (update.docChanged) {
          this.revision++;
          onChange(this.value, {revision: this.revision, origin: update.transactions.find(tr => tr.docChanged)?.annotation(origin) || 'source',
            composing: this.composing || update.view.composing});
        }
      }),
      EditorView.theme({'&': {height: '100%', fontSize: '14px'}, '.cm-scroller': {overflow: 'auto', fontFamily: 'Consolas, "Cascadia Mono", monospace'},
        '.cm-content': {padding: '8px 0'}, '.cm-focused': {outline: 'none'}, '.cm-gutters': {backgroundColor: 'var(--source-bg)', color: 'var(--muted)', border: 'none'}})
    ];
    this.view = new EditorView({parent, state: EditorState.create({extensions: this.extensions})});
  }
  get value() { return this.view.state.doc.toString(); }
  reset(value) { this.revision++; this.view.setState(EditorState.create({doc: value, extensions: this.extensions})); }
  replace(value, from = 'visual') {
    if (value === this.value) return;
    this.view.dispatch({changes: {from: 0, to: this.view.state.doc.length, insert: value},
      annotations: [origin.of(from), isolateHistory.of('full'), Transaction.userEvent.of('input.visual')]});
  }
  get selectedText() { const {from, to} = this.view.state.selection.main; return this.view.state.sliceDoc(from, to); }
  insertTemplate(parts, range = this.view.state.selection.main) {
    if (this.composing || this.view.state.readOnly) return;
    this.view.dispatch({...templateTransaction(parts, range.from, range.to, this.view.state.sliceDoc(range.to, range.to + 1)),
      annotations: [isolateHistory.of('full'), Transaction.userEvent.of('input.template')]});
    this.focus();
  }
  undo() { return undo(this.view); }
  redo() { return redo(this.view); }
  focus() { this.view.focus(); }
  setEnabled(value) { this.view.dispatch({effects: this.editable.reconfigure([EditorView.editable.of(value), EditorState.readOnly.of(!value)])}); }
}
