// Catalogs and size limits come from the native typography contract.
export class TypographyPanel {
  constructor({onChange, onMode, onComposition, blocked}) {
    Object.assign(this, {onChange, onMode, onComposition, blocked});
    this.composing = false;
    this.panel = document.getElementById('typographyPanel');
    this.toggle = document.getElementById('typographyToggle');
    this.preview = document.getElementById('previewToggle');
    this.fields = Object.fromEntries(['symbolFontId', 'numberFontFamily', 'cjkFontFamily', 'defaultMathStyle', 'fontSizePoints', 'color']
      .map(key => [key, document.getElementById(key)]));
    this.toggle.addEventListener('click', () => {
      if (this.blocked()) return;
      this.panel.hidden = !this.panel.hidden;
      this.toggle.setAttribute('aria-expanded', String(!this.panel.hidden));
      if (!this.panel.hidden) this.fields.symbolFontId.focus();
    });
    this.panel.addEventListener('keydown', event => {
      if (event.key === 'Escape' && !event.isComposing) {
        event.preventDefault(); event.stopPropagation(); this.close(); this.toggle.focus();
      }
    });
    this.panel.addEventListener('focusout', () => queueMicrotask(() => {
      if (!this.panel.contains(document.activeElement) && document.activeElement !== this.toggle) this.close();
    }));
    document.addEventListener('pointerdown', event => {
      if (!this.panel.contains(event.target) && !this.toggle.contains(event.target)) this.close();
    });
    this.preview.addEventListener('click', () => {
      if (this.blocked()) return;
      this.close(); this.active = !this.active; this.renderMode(); this.onMode(this.active);
    });
    for (const input of Object.values(this.fields)) {
      input.addEventListener('input', () => this.onChange());
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
      if (follow) input.add(new Option(this.zh ? '跟随符号字体' : 'Follow symbols', ''));
      for (const value of new Set([...values, ...(current ? [current] : [])])) input.add(new Option(value, value));
      input.value = current || '';
    };
    options(this.fields.symbolFontId, this.catalog.symbolFonts, this.initial.symbolFontId);
    options(this.fields.numberFontFamily, this.catalog.systemFonts, this.initial.numberFontFamily, true);
    options(this.fields.cjkFontFamily, this.catalog.systemFonts, this.initial.cjkFontFamily);
    options(this.fields.defaultMathStyle, this.catalog.mathStyles, this.initial.defaultMathStyle);
    const styleNames = {Automatic: '自动', Upright: '正体', Bold: '粗体', Italic: '斜体', BoldItalic: '粗斜体',
      SansSerif: '无衬线', SansSerifBold: '无衬线粗体', SansSerifItalic: '无衬线斜体', SansSerifBoldItalic: '无衬线粗斜体',
      Monospace: '等宽', Calligraphic: '花体', Script: '手写体', Fraktur: '哥特体', BoldFraktur: '哥特粗体', Blackboard: '双线体'};
    if (this.zh) for (const option of this.fields.defaultMathStyle.options) option.text = styleNames[option.value] || option.value;
    this.fields.fontSizePoints.value = String(this.initial.fontSizePoints);
    this.fields.color.value = this.initial.color;
    const sizes = document.getElementById('fontSizes'); sizes.replaceChildren();
    for (const [name, points] of Object.entries(this.catalog.namedSizes)) sizes.append(new Option(`${name} · ${points} pt`, name));
    this.toggle.textContent = this.zh ? '字体设置' : 'Typography';
    this.snapshot();
    this.renderMode();
  }
  renderMode() {
    this.preview.textContent = this.active ? (this.zh ? '返回编辑' : 'Edit') : (this.zh ? '最终预览' : 'Preview');
    this.preview.setAttribute('aria-pressed', String(this.active));
    document.getElementById('mathfieldHost').hidden = this.active;
    document.getElementById('finalPreview').hidden = !this.active;
    document.getElementById('previewNote').textContent = this.reference
      ? (this.zh ? '参考预览：以 Word 原生公式的实际排版为准。' : 'Reference preview: Word controls native equation layout.')
      : (this.zh ? '最终预览 · 实际字号' : 'Final preview · actual point size');
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
  setLocked(locked) {
    for (const input of [this.toggle, this.preview, ...Object.values(this.fields)]) input.disabled = locked;
  }
}
