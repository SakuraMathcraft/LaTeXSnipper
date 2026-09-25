import {renderMathInElement, validateLatex} from './vendor/mathlive.min.mjs';
import {CATEGORIES, findEntries, entryTemplate, templateParts} from './template-catalog.mjs';

const text = {
  zh: {search: '搜索中文、英文或 LaTeX 命令', empty: '没有匹配的符号', results: '搜索结果',
    show: '展开符号库', hide: '收起符号库', previous: '向左翻页', next: '向右翻页', rows: '行', columns: '列'},
  en: {search: 'Search names or LaTeX commands', empty: 'No matching symbols', results: 'Search results',
    show: 'Show symbols', hide: 'Hide symbols', previous: 'Previous page', next: 'Next page', rows: 'Rows', columns: 'Columns'}
};

export class SymbolPanel {
  constructor(insertion) {
    this.insertion = insertion;
    this.locale = 'zh';
    this.category = 'common';
    this.collapsed = false;
    this.scrollPositions = new Map();
    this.cache = new Map();
    this.elements = Object.fromEntries(['symbolLibrary', 'symbolGrid', 'libraryTabs', 'symbolSearch', 'libraryToggle',
      'libraryTitleText', 'matrixSize', 'matrixRows', 'matrixColumns', 'matrixRowsLabel', 'matrixColumnsLabel',
      'libraryPrevious', 'libraryNext'].map(id => [id, document.getElementById(id)]));
    const el = this.elements;
    try {
      const saved = JSON.parse(localStorage.getItem('latexSnipperSymbolPanel') || '{}');
      if (CATEGORIES.some(category => category.id === saved.category)) this.category = saved.category;
      this.collapsed = saved.collapsed === true;
    } catch { /* WebView profiles may disable storage. */ }
    this.observer = new IntersectionObserver(records => {
      for (const record of records) if (record.isIntersecting) {
        this.renderPreview(record.target);
        this.observer.unobserve(record.target);
      }
    }, {root: el.symbolGrid});
    for (const select of [el.matrixRows, el.matrixColumns]) {
      for (let size = 1; size <= 10; size++) select.add(new Option(String(size), String(size), size === 2, size === 2));
    }
    el.symbolLibrary.addEventListener('pointerdown', event => {
      if (this.insertion.blocked) event.preventDefault();
    });
    el.libraryToggle.addEventListener('click', () => {
      if (this.insertion.blocked) return;
      this.collapsed = !this.collapsed;
      this.updateVisibility();
      if (this.collapsed) this.insertion.restoreFocus();
      else el.symbolSearch.focus();
    });
    el.symbolSearch.addEventListener('input', () => this.render());
    el.symbolSearch.addEventListener('keydown', event => {
      if (event.isComposing) return;
      if (event.key === 'ArrowDown') {
        event.preventDefault(); el.symbolGrid.querySelector('button')?.focus();
      }
    });
    el.symbolLibrary.addEventListener('keydown', event => {
      if (event.key !== 'Escape' || event.isComposing || this.insertion.blocked) return;
      event.preventDefault(); event.stopPropagation();
      if (el.symbolSearch.value) { el.symbolSearch.value = ''; this.render(); }
      else { this.collapsed = true; this.updateVisibility(); }
      this.insertion.restoreFocus();
    });
    el.symbolGrid.addEventListener('keydown', event => this.navigateTiles(event));
    el.symbolGrid.addEventListener('focusin', event => {
      const tile = event.target.closest('.symbol-tile');
      if (!tile) return;
      for (const button of el.symbolGrid.querySelectorAll('button')) button.tabIndex = button === tile ? 0 : -1;
    });
    el.libraryTabs.addEventListener('keydown', event => {
      const buttons = [...el.libraryTabs.children];
      const index = buttons.indexOf(event.target);
      const next = event.key === 'ArrowRight' ? (index + 1) % buttons.length
        : event.key === 'ArrowLeft' ? (index + buttons.length - 1) % buttons.length
        : event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : null;
      if (next === null) return;
      event.preventDefault(); buttons[next].click(); buttons[next].focus();
    });
    // Only the tile viewport translates vertical wheels. Horizontal trackpad input stays native.
    el.symbolGrid.addEventListener('wheel', event => {
      if (event.ctrlKey || Math.abs(event.deltaX) >= Math.abs(event.deltaY)) return;
      if (el.symbolGrid.scrollWidth <= el.symbolGrid.clientWidth) return;
      event.preventDefault();
      const unit = event.deltaMode === 1 ? 24 : event.deltaMode === 2 ? el.symbolGrid.clientWidth : 1;
      el.symbolGrid.scrollLeft += event.deltaY * unit;
    }, {passive: false});
    el.symbolGrid.addEventListener('scroll', () => this.updatePaging());
    el.libraryPrevious.addEventListener('click', () => this.page(-1));
    el.libraryNext.addEventListener('click', () => this.page(1));
    new ResizeObserver(() => this.updatePaging()).observe(el.symbolGrid);
  }
  get labels() { return text[this.locale]; }
  configure(locale) {
    this.locale = locale.startsWith('zh') ? 'zh' : 'en';
    const el = this.elements;
    el.symbolSearch.placeholder = this.labels.search;
    el.symbolSearch.setAttribute('aria-label', this.labels.search);
    el.matrixRowsLabel.textContent = this.labels.rows;
    el.matrixColumnsLabel.textContent = this.labels.columns;
    el.libraryPrevious.setAttribute('aria-label', this.labels.previous);
    el.libraryNext.setAttribute('aria-label', this.labels.next);
    el.libraryTabs.replaceChildren(...CATEGORIES.map(category => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'tab'; button.dataset.group = category.id;
      button.id = `category-${category.id}`; button.setAttribute('role', 'tab');
      button.setAttribute('aria-controls', 'symbolGrid'); button.textContent = category[this.locale];
      button.addEventListener('click', () => {
        this.scrollPositions.set(this.category, el.symbolGrid.scrollLeft);
        this.category = category.id; el.symbolSearch.value = ''; this.render();
        el.symbolGrid.scrollLeft = this.scrollPositions.get(this.category) || 0;
        this.save();
      });
      return button;
    }));
    this.render(); this.updateVisibility();
  }
  save() {
    try { localStorage.setItem('latexSnipperSymbolPanel', JSON.stringify({category: this.category, collapsed: this.collapsed})); }
    catch { /* Storage is optional. */ }
  }
  updateVisibility() {
    const el = this.elements;
    el.symbolLibrary.hidden = this.collapsed;
    el.libraryToggle.textContent = this.collapsed ? this.labels.show : this.labels.hide;
    el.libraryToggle.setAttribute('aria-expanded', String(!this.collapsed));
    this.save();
  }
  render() {
    const el = this.elements;
    this.observer.disconnect();
    const entries = findEntries(this.category, el.symbolSearch.value);
    const searching = Boolean(el.symbolSearch.value.trim());
    for (const button of el.libraryTabs.children) {
      const selected = button.dataset.group === this.category && !searching;
      button.classList.toggle('active', selected); button.setAttribute('aria-selected', String(selected));
      button.tabIndex = button.dataset.group === this.category ? 0 : -1;
    }
    const title = searching ? this.labels.results : CATEGORIES.find(category => category.id === this.category)[this.locale];
    el.libraryTitleText.textContent = `${title} · ${entries.length}`;
    el.symbolGrid.setAttribute('aria-label', title);
    el.matrixSize.hidden = !entries.some(entry => entry.matrix);
    el.symbolGrid.replaceChildren(...entries.map((entry, index) => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = `symbol-tile${entry.wide ? ' wide' : ''}`;
      button.dataset.entry = entry.id; button.tabIndex = index === 0 ? 0 : -1;
      button.setAttribute('aria-label', entry[this.locale]);
      button.title = `${entry.nameZh} / ${entry.en}\n${entryTemplate(entry)}${entry.shortcut ? `\nMathLive: Ctrl+${entry.shortcut.toUpperCase()}` : ''}`;
      const label = document.createElement('span'); label.className = 'tile-label'; label.textContent = entry.wide ? entry[this.locale] : entry.zh;
      button.append(label); button.entry = entry;
      button.addEventListener('pointerdown', event => event.preventDefault());
      button.addEventListener('click', () => this.insertion.insert(entry, {rows: Number(el.matrixRows.value), columns: Number(el.matrixColumns.value)}));
      if (entry.wide) this.observer.observe(button);
      else label.style.fontSize = '22px';
      return button;
    }));
    if (!entries.length) {
      const empty = document.createElement('div'); empty.className = 'empty-library'; empty.textContent = this.labels.empty;
      el.symbolGrid.append(empty);
    }
    el.symbolGrid.scrollLeft = 0;
    this.updatePaging();
  }
  renderPreview(button) {
    const entry = button.entry;
    let preview = this.cache.get(entry.id);
    if (!preview) {
      preview = document.createElement('span'); preview.className = 'tile-preview';
      preview.setAttribute('aria-hidden', 'true'); preview.inert = true;
      const latex = templateParts(entryTemplate(entry)).map(part => part.hole ? '\\square' : part.text).join('');
      if (validateLatex(latex).length) {
        preview.textContent = entry[this.locale]; preview.classList.add('tile-label');
      } else {
        preview.textContent = `\\(${latex}\\)`;
        renderMathInElement(preview);
      }
      this.cache.set(entry.id, preview);
      if (this.cache.size > 128) this.cache.delete(this.cache.keys().next().value);
    }
    if (preview.classList.contains('tile-label')) preview.textContent = entry[this.locale];
    button.replaceChildren(preview);
  }
  page(direction) {
    this.elements.symbolGrid.scrollBy({left: direction * this.elements.symbolGrid.clientWidth * .85, behavior: 'smooth'});
  }
  updatePaging() {
    const el = this.elements;
    el.libraryPrevious.disabled = el.symbolGrid.scrollLeft <= 1;
    el.libraryNext.disabled = el.symbolGrid.scrollLeft + el.symbolGrid.clientWidth >= el.symbolGrid.scrollWidth - 1;
  }
  navigateTiles(event) {
    if (event.isComposing) return;
    const buttons = [...this.elements.symbolGrid.querySelectorAll('button')];
    const index = buttons.indexOf(event.target);
    const next = event.key === 'ArrowRight' ? index + 2 : event.key === 'ArrowLeft' ? index - 2
      : event.key === 'ArrowDown' ? index + 1 : event.key === 'ArrowUp' ? index - 1
      : event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : null;
    if (next === null || !buttons.length) return;
    event.preventDefault();
    const button = buttons[Math.max(0, Math.min(buttons.length - 1, next))];
    button.focus(); button.scrollIntoView({block: 'nearest', inline: 'nearest'});
  }
}
