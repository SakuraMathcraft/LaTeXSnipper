// Catalogs and size limits come from the native typography contract.
import {FontSizePicker} from './font-size-picker.mjs';

export class TypographyPanel {
  constructor({onChange, onMode, onComposition, blocked}) {
    Object.assign(this, {onChange, onMode, onComposition, blocked});
    this.composing = false;
    this.panel = document.getElementById('typographyPanel');
    this.toggle = document.getElementById('typographyToggle');
    this.preview = document.getElementById('previewToggle');
    this.fields = Object.fromEntries(['symbolFontId', 'numberFontFamily', 'cjkFontFamily', 'defaultMathStyle', 'fontSizePoints', 'color']
      .map(key => [key, document.getElementById(key)]));
    this.sizePicker = new FontSizePicker({onOpen: () => this.close(), blocked: this.blocked});
    this.toggle.addEventListener('click', () => {
      if (this.blocked()) return;
      this.panel.hidden = !this.panel.hidden;
      this.toggle.setAttribute('aria-expanded', String(!this.panel.hidden));
    });
    this.panel.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !event.isComposing) {
        event.preventDefault(); event.stopPropagation(); this.close(); this.toggle.focus();
      }
    });
    document.addEventListener('pointerdown', event => {
      if (!this.panel.contains(event.target) && !this.toggle.contains(event.target)) this.close();
    });
    this.preview.addEventListener('click', () => {
      if (this.blocked()) return;
      this.close(); this.active = !this.active; this.renderMode(); this.onMode(this.active);
    });
    for (const input of Object.values(this.fields)) {
      input.addEventListener(input.tagName === 'SELECT' ? 'change' : 'input', () => {
        this.onChange(input);
      });
      input.addEventListener('compositionstart', () => { this.composing = true; this.onComposition(); });
      input.addEventListener('compositionend', () => { this.composing = false; this.onComposition(); });
    }
  }
  close() { this.panel.hidden = true; this.toggle.setAttribute('aria-expanded', 'false'); }
  configure(payload) {
    this.catalog = payload.catalog; this.initial = payload.typography;
    this.zh = String(payload.locale).startsWith('zh'); this.reference = payload.referencePreview;
    this.active = false; this.composing = false; this.close();
    const labels = this.zh ? ['符号字体', '数字字体', '汉字字体', '默认字形', '字号', '颜色']
      : ['Symbols', 'Numbers', 'CJK', 'Math style', 'Size', 'Color'];
    Object.entries(this.fields).forEach(([key, input], index) => {
      document.querySelector(`[data-label="${key}"]`).textContent = labels[index];
      input.setAttribute('aria-label', labels[index]);
    });
    const options = (input, values, current, follow = false) => {
      input.replaceChildren();
      for (const value of new Set([...(follow ? [''] : []), ...values, current || ''])) {
        if (value || follow) input.add(new Option(value || (this.zh ? '跟随符号字体' : 'Follow symbols'), value));
      }
      input.value = current || '';
    };
    options(this.fields.symbolFontId, this.catalog.symbolFonts, this.initial.symbolFontId);
    options(this.fields.numberFontFamily, this.catalog.systemFonts, this.initial.numberFontFamily, true);
    options(this.fields.cjkFontFamily, this.catalog.cjkFonts, this.initial.cjkFontFamily);
    this.fields.defaultMathStyle.replaceChildren();
    for (const style of this.catalog.mathStyles)
      this.fields.defaultMathStyle.add(new Option(this.zh ? style.zh : style.en, style.id));
    this.fields.defaultMathStyle.value = this.initial.defaultMathStyle;
    this.fields.fontSizePoints.value = String(this.initial.fontSizePoints);
    this.fields.color.value = this.initial.color;
    this.sizePicker.configure(this.catalog, this.zh);
    this.toggle.textContent = this.zh ? '字体设置' : 'Typography';
    this.snapshot();
    this.renderMode();
  }
  renderMode() {
    this.preview.querySelector('.button-label').textContent = this.active ? (this.zh ? '返回编辑' : 'Edit') : (this.zh ? '最终预览' : 'Preview');
    this.preview.setAttribute('aria-pressed', String(this.active));
    document.getElementById('mathfieldHost').hidden = this.active;
    document.getElementById('finalPreview').hidden = !this.active;
    document.getElementById('previewNote').textContent = this.reference
      ? (this.zh ? '参考预览：以 Word 原生公式的实际排版为准。' : 'Reference preview: Word controls native equation layout.')
      : '';
  }
  snapshot() {
    if (!this.catalog) return null;
    const values = Object.fromEntries(Object.entries(this.fields).map(([key, input]) => [key, input.value]));
    const size = values.fontSizePoints.trim();
    const points = Object.hasOwn(this.catalog.namedSizes, size) ? this.catalog.namedSizes[size]
      : /^(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)$/.test(size) ? Number(size) : NaN;
    const valid = Number.isFinite(points) && points >= this.catalog.minimumPoints && points <= this.catalog.maximumPoints;
    this.fields.fontSizePoints.setCustomValidity(valid ? '' : (this.zh ? '请输入有效的数字或中文字号。' : 'Enter a valid point size or size name.'));
    this.fields.fontSizePoints.setAttribute('aria-invalid', String(!valid));
    if (!valid || !this.catalog.symbolFonts.includes(values.symbolFontId)) return null;
    return {...values, typographyVersion: this.initial.typographyVersion, fontSizePoints: points};
  }
  apply(typography) {
    if (!this.catalog || !typography) return;
    for (const [key, input] of Object.entries(this.fields)) {
      const value = typography[key] ?? '';
      if (input.tagName === 'SELECT' && value && !Array.from(input.options).some(option => option.value === value))
        input.add(new Option(value, value));
      input.value = String(value);
    }
    this.snapshot();
  }
  setLocked(locked) {
    for (const input of [this.toggle, this.preview, ...Object.values(this.fields)]) input.disabled = locked;
    this.sizePicker.setLocked(locked);
  }
}
