import {MathfieldElement} from './vendor/mathlive.min.mjs';
import {SourceEditor} from './source-editor.bundle.js';
import {SourceSync} from './source-sync.mjs';
import {COMMANDS, CATALOG} from './template-catalog.mjs';
import {TemplateInsertion} from './template-insertion.mjs';
import {configureMathfield, configureMathfieldMenu} from './mathfield-input.mjs';

export const DEFAULT_LATEX = 'e^{i\\pi}+1=0';

const MODE_MESSAGES = {
  zh: {sourceOnly: '可视化编辑会改写这段源码，请在下方修改。', invalid: '源码结构有误，请在下方修正。',
    mathml: 'MathML 请在源码区编辑。', updating: '正在更新可视化编辑区…'},
  en: {sourceOnly: 'Visual editing would rewrite this source. Edit it below.', invalid: 'Fix the source below.',
    mathml: 'Edit MathML in the source pane.', updating: 'Updating visual editor…'}
};

export class TaskPaneFormula {
  constructor({previewHost, sourceHost, modeNote, onChange, onAccept}) {
    Object.assign(this, {previewHost, sourceHost, modeNote, onChange, onAccept});
    this.locale = 'zh';
    MathfieldElement.fontsDirectory = new URL('./vendor/fonts', import.meta.url).href;
    MathfieldElement.soundsDirectory = null;
    this.mathfield = this.createField();
    this.source = new SourceEditor(sourceHost, {
      commands: COMMANDS,
      completeTemplate: (entry, range) => this.insertion.insert(entry, {range}),
      onChange: (_value, change) => { this.sync?.sourceChanged(change); this.onChange(this.source.value); },
      onComposition: active => this.sync?.composition(active)
    });
    this.sync = new SourceSync({source: this.source, mathfield: this.mathfield,
      readVisual: () => this.mathfield.getValue('latex'), recreateMathfield: () => this.recreateField(),
      onMode: reason => this.showMode(reason)});
    this.insertion = new TemplateInsertion({source: this.source, sync: this.sync, mathfield: this.mathfield,
      sourceHost, onInsert: () => this.resize(), isComposing: () => false});
    this.bindMathfieldInput = configureMathfield(this.mathfield, {onAccept, insert: entry => this.insertion.insert(entry),
      shortcuts: new Map(CATALOG.filter(entry => entry.shortcut).map(entry => [entry.shortcut, entry])),
      performEdit: action => this.sync.performVisual(action)});
    this.sync.load(DEFAULT_LATEX);
  }

  createField() {
    const field = new MathfieldElement();
    field.smartFence = true;
    field.mathVirtualKeyboardPolicy = 'manual';
    field.setAttribute('aria-label', this.locale.startsWith('zh') ? '可视化公式编辑器' : 'Visual formula editor');
    field.addEventListener('beforeinput', event => this.sync?.beforeVisualInput(event));
    field.addEventListener('input', () => { this.sync?.visualInput(); this.resize(); });
    field.addEventListener('compositionstart', () => this.sync?.visualComposition(true));
    field.addEventListener('compositionend', () => this.sync?.visualComposition(false));
    field.addEventListener('keydown', event => {
      if ((event.ctrlKey || event.metaKey) && !event.altKey && !event.isComposing
          && ['z', 'y'].includes(event.key.toLowerCase())) {
        event.preventDefault();
        event.stopImmediatePropagation();
        this.sync?.history(event.shiftKey || event.key.toLowerCase() === 'y');
      }
    }, true);
    this.previewHost.replaceChildren(field);
    configureMathfieldMenu(field, this.locale, action => this.sync?.performVisual(action));
    return field;
  }

  recreateField() {
    this.mathfield = this.createField();
    this.insertion.bindMathfield(this.mathfield);
    this.bindMathfieldInput(this.mathfield);
    return this.mathfield;
  }

  showMode(reason) {
    this.modeNote.hidden = !reason;
    this.modeNote.textContent = MODE_MESSAGES[this.locale.startsWith('zh') ? 'zh' : 'en'][reason] || '';
  }

  load(latex, locale = 'zh') {
    this.locale = String(locale).toLowerCase();
    this.mathfield.setAttribute('aria-label', this.locale.startsWith('zh') ? '可视化公式编辑器' : 'Visual formula editor');
    configureMathfieldMenu(this.mathfield, this.locale, action => this.sync.performVisual(action));
    if (latex !== this.source.value) this.sync.load(latex);
    this.resize();
  }

  resize() {
    requestAnimationFrame(() => {
      const height = Math.ceil(this.mathfield.scrollHeight || this.mathfield.getBoundingClientRect().height || 44);
      this.previewHost.style.height = `${Math.max(100, Math.min(260, height + 24))}px`;
    });
  }

  get latex() { return this.source.value; }
}
