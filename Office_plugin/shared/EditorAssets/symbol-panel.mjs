import {renderMathInElement, validateLatex} from './vendor/mathlive.min.mjs';
import {CATALOG, CATEGORIES, findEntries, entryTemplate, templateParts} from './template-catalog.mjs';
import {outerColor} from './formula-color.mjs';

const FAVORITES_KEY = 'latexSnipperSymbolFavorites';
const CUSTOM_FAVORITES_KEY = 'latexSnipperCustomFormulaFavorites';

const text = {
  zh: {search: '搜索中文、英文或 LaTeX 命令', empty: '没有匹配的符号', commonEmpty: '右键点击公式磁贴，或点击工具栏星标，将公式加入常用',
    results: '搜索结果', show: '显示符号库', hide: '隐藏符号库', rows: '行', columns: '列',
    addFavorite: '加入常用', removeFavorite: '从常用移除', addCurrent: '将当前公式加入常用', removeCurrent: '从常用移除当前公式', custom: '我的公式'},
  en: {search: 'Search names or LaTeX commands', empty: 'No matching symbols',
    commonEmpty: 'Right-click a tile or use the toolbar star to add a formula', results: 'Search results',
    show: 'Show symbols', hide: 'Hide symbols', rows: 'Rows', columns: 'Columns',
    addFavorite: 'Add to Common', removeFavorite: 'Remove from Common', addCurrent: 'Add current formula to Common',
    removeCurrent: 'Remove current formula from Common', custom: 'My formula'}
};

export class SymbolPanel {
  constructor(insertion, currentLatex) {
    this.insertion = insertion;
    this.currentLatex = currentLatex;
    this.currentButton = document.getElementById('currentFavoriteButton');
    this.locale = 'zh';
    this.category = 'common';
    this.collapsed = false;
    this.scrollPositions = new Map();
    this.cache = new Map();
    this.favorites = new Set();
    this.customFavorites = [];
    this.currentButtons = [];
    this.visibleButtons = new Set();
    this.renderFrame = 0;
    this.renderGeneration = 0;
    this.elements = Object.fromEntries(['symbolLibrary', 'symbolGrid', 'libraryTabs', 'symbolSearch', 'libraryToggle',
      'libraryTitleText', 'matrixSize', 'matrixRows', 'matrixColumns', 'matrixRowsLabel', 'matrixColumnsLabel']
      .map(id => [id, document.getElementById(id)]));
    const el = this.elements;
    this.previewObserver = new IntersectionObserver(records => {
      let visible = false;
      for (const record of records) {
        if (record.isIntersecting) { this.visibleButtons.add(record.target); visible = true; }
        else this.visibleButtons.delete(record.target);
      }
      if (visible) this.scheduleRender(true);
    }, {root: el.symbolGrid, rootMargin: '180px'});
    try {
      const saved = JSON.parse(localStorage.getItem('latexSnipperSymbolPanel') || '{}');
      if (CATEGORIES.some(category => category.id === saved.category)) this.category = saved.category;
      this.collapsed = saved.collapsed === true;
    } catch { /* WebView profiles may disable storage. */ }
    try {
      const saved = JSON.parse(localStorage.getItem(FAVORITES_KEY) || '[]');
      if (Array.isArray(saved)) {
        const templates = new Set(CATALOG.map(entry => entry.template));
        this.favorites = new Set(saved.filter(value => typeof value === 'string' && templates.has(value)));
      }
    } catch { this.favorites.clear(); }
    try {
      const saved = JSON.parse(localStorage.getItem(CUSTOM_FAVORITES_KEY) || '[]');
      if (!Array.isArray(saved)) throw new TypeError('Invalid custom favorites');
      this.customFavorites = [...new Set(saved.filter(value => typeof value === 'string' && value.trim()))];
    } catch { this.customFavorites = []; }
    this.currentButton.addEventListener('click', () => this.toggleCurrentFavorite());
    this.menu = document.createElement('div');
    this.menu.className = 'symbol-context-menu';
    this.menu.setAttribute('role', 'menu');
    this.menu.hidden = true;
    this.menuButton = document.createElement('button');
    this.menuButton.type = 'button';
    this.menuButton.setAttribute('role', 'menuitem');
    this.menu.append(this.menuButton);
    document.body.append(this.menu);
    this.menuButton.addEventListener('pointerdown', event => event.preventDefault());
    this.menuButton.addEventListener('click', () => {
      this.toggleFavorite(this.menuEntry);
      this.closeMenu();
    });
    document.addEventListener('pointerdown', event => {
      if (!this.menu.hidden && !this.menu.contains(event.target)) this.closeMenu();
    }, true);
    document.addEventListener('keydown', event => {
      if (event.key !== 'Escape' || this.menu.hidden) return;
      event.preventDefault();
      event.stopPropagation();
      this.closeMenu();
    }, true);
    this.previewWidth = 0;
    new ResizeObserver(() => {
      const width = el.symbolGrid.clientWidth;
      if (!width || width === this.previewWidth) return;
      this.previewWidth = width;
      this.remeasureRendered();
    }).observe(el.symbolGrid);
    document.fonts?.addEventListener('loadingdone', () => this.remeasureRendered());
    document.fonts?.ready.then(() => this.remeasureRendered());
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
    el.symbolGrid.addEventListener('focusout', () => queueMicrotask(() => this.packTiles()));
    el.libraryTabs.addEventListener('keydown', event => {
      const buttons = [...el.libraryTabs.children];
      const index = buttons.indexOf(event.target);
      const next = event.key === 'ArrowDown' ? (index + 1) % buttons.length
        : event.key === 'ArrowUp' ? (index + buttons.length - 1) % buttons.length
        : event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : null;
      if (next === null) return;
      event.preventDefault(); buttons[next].click(); buttons[next].focus();
    });
  }
  get labels() { return text[this.locale]; }
  configure(locale) {
    this.locale = locale.startsWith('zh') ? 'zh' : 'en';
    const el = this.elements;
    el.symbolSearch.placeholder = this.labels.search;
    el.symbolSearch.setAttribute('aria-label', this.labels.search);
    el.matrixRowsLabel.textContent = this.labels.rows;
    el.matrixColumnsLabel.textContent = this.labels.columns;
    el.libraryTabs.replaceChildren(...CATEGORIES.map(category => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'tab'; button.dataset.group = category.id;
      button.id = `category-${category.id}`; button.setAttribute('role', 'tab');
      button.setAttribute('aria-controls', 'symbolGrid'); button.textContent = category[this.locale];
      button.addEventListener('click', () => {
        this.scrollPositions.set(this.category, el.symbolGrid.scrollTop);
        this.category = category.id; el.symbolSearch.value = ''; this.render();
        el.symbolGrid.scrollTop = this.scrollPositions.get(this.category) || 0;
        this.save();
      });
      return button;
    }));
    this.render(); this.updateVisibility(); this.updateCurrentFavorite();
  }
  save() {
    try { localStorage.setItem('latexSnipperSymbolPanel', JSON.stringify({category: this.category, collapsed: this.collapsed})); }
    catch { /* Storage is optional. */ }
  }
  toggleFavorite(entry) {
    if (!entry) return;
    if (entry.literal) {
      this.customFavorites = this.customFavorites.filter(value => value !== entry.template);
      localStorage.setItem(CUSTOM_FAVORITES_KEY, JSON.stringify(this.customFavorites));
      this.dropCustomPreviewCache();
    } else {
      if (this.favorites.has(entry.template)) this.favorites.delete(entry.template);
      else this.favorites.add(entry.template);
      localStorage.setItem(FAVORITES_KEY, JSON.stringify([...this.favorites]));
    }
    this.render(); this.updateCurrentFavorite();
  }
  toggleCurrentFavorite() {
    if (this.insertion.blocked) return;
    const latex = this.currentLatex();
    if (!latex.trim()) return;
    const catalogEntry = CATALOG.find(entry => entry.template === latex);
    if (catalogEntry) {
      if (this.favorites.has(latex)) this.favorites.delete(latex);
      else this.favorites.add(latex);
      localStorage.setItem(FAVORITES_KEY, JSON.stringify([...this.favorites]));
    } else {
      if (this.customFavorites.includes(latex)) this.customFavorites = this.customFavorites.filter(value => value !== latex);
      else this.customFavorites.push(latex);
      localStorage.setItem(CUSTOM_FAVORITES_KEY, JSON.stringify(this.customFavorites));
      this.dropCustomPreviewCache();
    }
    this.category = 'common'; this.elements.symbolSearch.value = ''; this.render(); this.updateCurrentFavorite(); this.save();
  }
  dropCustomPreviewCache() {
    for (const id of this.cache.keys()) if (id.startsWith('custom-')) this.cache.delete(id);
  }
  updateCurrentFavorite() {
    const latex = this.currentLatex() || '';
    const active = this.favorites.has(latex) || this.customFavorites.includes(latex);
    const label = active ? this.labels.removeCurrent : this.labels.addCurrent;
    this.currentButton.disabled = this.insertion.blocked || !latex.trim();
    this.currentButton.setAttribute('aria-pressed', String(active));
    this.currentButton.setAttribute('aria-label', label);
    this.currentButton.title = label;
  }
  customEntries() {
    return this.customFavorites.map((latex, index) => ({id: `custom-${index}`, template: latex, literal: true,
      zh: `${this.labels.custom} ${index + 1}`, en: `My formula ${index + 1}`,
      nameZh: `我的公式 ${index + 1}`, matrix: null}));
  }
  openMenu(entry, x, y) {
    this.menuEntry = entry;
    this.menuButton.textContent = entry.literal || this.favorites.has(entry.template) ? this.labels.removeFavorite : this.labels.addFavorite;
    this.menu.hidden = false;
    this.menu.style.left = `${Math.max(8, Math.min(x, innerWidth - this.menu.offsetWidth - 8))}px`;
    this.menu.style.top = `${Math.max(8, Math.min(y, innerHeight - this.menu.offsetHeight - 8))}px`;
  }
  closeMenu() {
    this.menu.hidden = true;
    this.menuEntry = null;
  }
  updateVisibility() {
    const el = this.elements;
    el.symbolLibrary.hidden = this.collapsed;
    document.querySelector('.shell').classList.toggle('library-collapsed', this.collapsed);
    el.libraryToggle.setAttribute('aria-label', this.collapsed ? this.labels.show : this.labels.hide);
    el.libraryToggle.title = this.collapsed ? this.labels.show : this.labels.hide;
    el.libraryToggle.setAttribute('aria-expanded', String(!this.collapsed));
    this.save();
    if (!this.collapsed) this.scheduleRender(true);
  }
  render() {
    const el = this.elements;
    this.closeMenu();
    this.renderGeneration++;
    if (this.renderFrame) cancelAnimationFrame(this.renderFrame);
    this.renderFrame = 0;
    this.previewObserver.disconnect();
    this.visibleButtons.clear();
    const searching = Boolean(el.symbolSearch.value.trim());
    const custom = this.customEntries();
    const entries = searching ? [...findEntries(this.category, el.symbolSearch.value),
      ...custom.filter(entry => entry.template.toLowerCase().includes(el.symbolSearch.value.trim().toLowerCase()))]
      : this.category === 'common' ? [...CATALOG.filter(entry => this.favorites.has(entry.template)), ...custom]
        : findEntries(this.category);
    for (const button of el.libraryTabs.children) {
      const selected = button.dataset.group === this.category && !searching;
      button.classList.toggle('active', selected); button.setAttribute('aria-selected', String(selected));
      button.tabIndex = button.dataset.group === this.category ? 0 : -1;
    }
    const title = searching ? this.labels.results : CATEGORIES.find(category => category.id === this.category)[this.locale];
    el.libraryTitleText.textContent = `${title} · ${entries.length}`;
    el.symbolGrid.setAttribute('aria-label', title);
    el.matrixSize.hidden = (!searching && this.category === 'common') || !entries.some(entry => entry.matrix);
    this.currentButtons = entries.map((entry, index) => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'symbol-tile';
      button.dataset.entry = entry.id; button.dataset.order = String(index); button.tabIndex = index === 0 ? 0 : -1;
      button.classList.toggle('favorite', entry.literal || this.favorites.has(entry.template));
      button.setAttribute('aria-label', entry[this.locale]);
      button.title = `${entry.nameZh} / ${entry.en}\n${entryTemplate(entry)}${entry.shortcut ? `\nMathLive: Ctrl+${entry.shortcut.toUpperCase()}` : ''}`;
      const symbol = document.createElement('span'); symbol.className = 'tile-preview';
      const caption = document.createElement('span'); caption.className = 'tile-caption';
      caption.textContent = this.locale === 'zh' ? entry.nameZh : entry.en;
      button.append(symbol, caption); button.entry = entry;
      button.addEventListener('pointerdown', event => event.preventDefault());
      button.addEventListener('click', () => this.insertion.insert(entry, {rows: Number(el.matrixRows.value), columns: Number(el.matrixColumns.value)}));
      button.addEventListener('contextmenu', event => {
        event.preventDefault();
        this.openMenu(entry, event.clientX, event.clientY);
      });
      button.addEventListener('keydown', event => {
        if (event.key !== 'ContextMenu' && !(event.shiftKey && event.key === 'F10')) return;
        event.preventDefault();
        const rect = button.getBoundingClientRect();
        this.openMenu(entry, rect.left + 12, rect.bottom - 8);
      });
      return button;
    });
    el.symbolGrid.replaceChildren(...this.currentButtons);
    const relabelled = [];
    for (const button of this.currentButtons) {
      const cached = this.cache.get(button.entry.id);
      if (cached) {
        if (cached.dataset.fallback) {
          cached.textContent = button.entry[this.locale];
          relabelled.push(button);
        }
        button.querySelector('.tile-preview').append(cached);
        button.style.width = cached.dataset.tileWidth || '56px';
      } else {
        this.previewObserver.observe(button);
      }
    }
    this.measureBatch(relabelled);
    this.packTiles();
    if (!entries.length) {
      const empty = document.createElement('div'); empty.className = 'empty-library';
      empty.textContent = this.category === 'common' && !searching ? this.labels.commonEmpty : this.labels.empty;
      el.symbolGrid.append(empty);
    }
    el.symbolGrid.scrollTop = 0;
    this.scheduleRender();
  }
  scheduleRender() {
    if (this.collapsed || this.renderFrame || !this.visibleButtons.size) return;
    const generation = this.renderGeneration;
    this.renderFrame = requestAnimationFrame(() => {
      this.renderFrame = 0;
      if (generation !== this.renderGeneration) return;
      const batch = [];
      for (const button of this.visibleButtons) {
        this.visibleButtons.delete(button);
        if (!button.querySelector('.tile-preview-content')) batch.push(button);
        if (batch.length === 4) break;
      }
      for (const button of batch) {
        this.previewObserver.unobserve(button);
        this.renderPreview(button);
      }
      this.measureBatch(batch);
      if (batch.length) this.packTiles();
      this.scheduleRender();
    });
  }
  remeasureRendered() {
    this.measureBatch(this.currentButtons.filter(button => button.querySelector('.tile-preview-content')));
    this.packTiles();
  }
  renderPreview(button) {
    const entry = button.entry;
    let preview = this.cache.get(entry.id);
    if (!preview) {
      preview = document.createElement('span'); preview.className = 'tile-preview-content';
      preview.setAttribute('aria-hidden', 'true'); preview.inert = true;
      const source = templateParts(entryTemplate(entry)).map(part => part.hole ? '\\square' : part.text).join('');
      const color = outerColor(source);
      const latex = color?.body ?? source;
      if (color) preview.style.color = color.color;
      if (validateLatex(latex).length) {
        preview.textContent = entry[this.locale];
        preview.dataset.fallback = 'true';
      } else {
        preview.textContent = `\\(${latex}\\)`;
        renderMathInElement(preview);
      }
      this.cache.set(entry.id, preview);
      if (this.cache.size > 256) this.cache.delete(this.cache.keys().next().value);
    }
    if (preview.dataset.fallback) preview.textContent = entry[this.locale];
    const frame = button.querySelector('.tile-preview');
    frame.replaceChildren(preview);
  }
  measureBatch(buttons) {
    if (!buttons.length) return;
    const available = this.elements.symbolGrid.clientWidth - 16;
    const range = document.createRange();
    for (const button of buttons) button.querySelector('.tile-preview-content').style.zoom = '1';
    const sizes = buttons.map(button => {
      const preview = button.querySelector('.tile-preview-content');
      range.selectNodeContents(button.querySelector('.tile-caption').firstChild);
      const formulaWidth = preview.getBoundingClientRect().width;
      const labelWidth = range.getBoundingClientRect().width;
      return {button, preview, formulaWidth,
        width: Math.max(56, Math.min(available, Math.ceil(Math.max(formulaWidth, labelWidth) + 16)))};
    });
    for (const {button, preview, formulaWidth, width} of sizes) {
      button.style.width = `${width}px`;
      preview.dataset.tileWidth = button.style.width;
      preview.style.zoom = formulaWidth > width - 16 ? String((width - 16) / formulaWidth) : '1';
    }
  }
  packTiles() {
    const grid = this.elements.symbolGrid;
    if (grid.contains(document.activeElement) && document.activeElement.classList.contains('symbol-tile')) return;
    const buttons = [...this.currentButtons];
    if (!buttons.length) return;
    const available = grid.clientWidth - 16;
    const widths = new Map(buttons.map(button => [button, Math.min(available, parseFloat(button.style.width) || 56)]));
    const ordered = [];
    while (buttons.length) {
      let remaining = available;
      const first = buttons.shift();
      ordered.push(first);
      remaining -= widths.get(first);
      while (buttons.length && remaining > 62) {
        let best = -1;
        for (let index = 0; index < Math.min(12, buttons.length); index++) {
          const width = widths.get(buttons[index]) + 6;
          if (width <= remaining && (best < 0 || width < widths.get(buttons[best]) + 6)) best = index;
        }
        if (best < 0) break;
        const next = buttons.splice(best, 1)[0];
        ordered.push(next);
        remaining -= widths.get(next) + 6;
      }
    }
    const scrollTop = grid.scrollTop;
    if (ordered.some((button, index) => grid.children[index] !== button)) grid.append(...ordered);
    grid.scrollTop = scrollTop;
  }
  navigateTiles(event) {
    if (event.isComposing) return;
    const buttons = [...this.elements.symbolGrid.querySelectorAll('button')];
    if (!buttons.includes(event.target)) return;
    if (!['ArrowRight', 'ArrowLeft', 'ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return;
    event.preventDefault();
    let button = event.key === 'Home' ? buttons[0] : event.key === 'End' ? buttons.at(-1) : null;
    if (!button) {
      const current = event.target.getBoundingClientRect();
      const cx = current.left + current.width / 2, cy = current.top + current.height / 2;
      const vertical = event.key === 'ArrowDown' || event.key === 'ArrowUp';
      const sign = event.key === 'ArrowDown' || event.key === 'ArrowRight' ? 1 : -1;
      const choices = buttons.filter(candidate => candidate !== event.target).map(candidate => {
        const rect = candidate.getBoundingClientRect();
        const dx = rect.left + rect.width / 2 - cx, dy = rect.top + rect.height / 2 - cy;
        const primary = vertical ? dy : dx, secondary = vertical ? dx : dy;
        return {candidate, primary, score: Math.abs(primary) + Math.abs(secondary) * 2};
      }).filter(choice => choice.primary * sign > 1).sort((a, b) => a.score - b.score);
      button = choices[0]?.candidate;
    }
    if (!button) return;
    button.focus(); button.scrollIntoView({block: 'nearest', inline: 'nearest'});
  }
}
