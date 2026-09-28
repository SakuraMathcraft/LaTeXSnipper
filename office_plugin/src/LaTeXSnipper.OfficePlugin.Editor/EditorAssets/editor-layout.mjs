// Both Office hosts mount this one layout; their HTML only loads shared assets.
const icon = paths => `<svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">${paths}</svg>`;
const icons = {
  undo: icon('<path d="m9 4-5 5 5 5M4 9h9a6 6 0 0 1 0 12h-2"/>'),
  redo: icon('<path d="m15 4 5 5-5 5m5-5h-9a6 6 0 0 0 0 12h2"/>'),
  preview: icon('<path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>'),
  edit: icon('<path d="m15 5 4 4M4 20l4.5-1 10-10a2.8 2.8 0 0 0-4-4l-10 10L4 20Z"/>'),
  favorite: icon('<path d="m12 2 3.1 6.3 7 1-5.1 5 .9 7-5.9-3.3-5.9 3.3.9-7-5.1-5 7-1L12 2Z"/>'),
  library: icon('<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16m3-12h6m-6 4h6m-6 4h4"/>')
};

export function mountEditor() {
  document.body.setAttribute('theme', 'light');
  document.body.insertAdjacentHTML('afterbegin', `
    <header class="toolbar" aria-label="Editor tools">
      <strong>LaTeX</strong>
      <div class="toolbar-group">
        <button id="undoButton" class="tool-icon" type="button" aria-keyshortcuts="Control+Z">${icons.undo}</button>
        <button id="redoButton" class="tool-icon" type="button" aria-keyshortcuts="Control+Y">${icons.redo}</button>
      </div>
      <div class="toolbar-group">
        <div class="toolbar-popover-anchor">
          <button id="typographyToggle" type="button" aria-expanded="false" aria-controls="typographyPanel">字体设置</button>
          <div id="typographyPanel" class="typography-panel" hidden>
            <label><span data-label="symbolFontId"></span><select id="symbolFontId"></select></label>
            <label><span data-label="numberFontFamily"></span><select id="numberFontFamily"></select></label>
            <label><span data-label="cjkFontFamily"></span><select id="cjkFontFamily"></select></label>
            <label><span data-label="defaultMathStyle"></span><select id="defaultMathStyle"></select></label>
          </div>
        </div>
      </div>
      <div class="toolbar-group">
        <div class="size-picker" id="sizePicker">
          <label for="fontSizePoints" data-label="fontSizePoints">字号</label>
          <div class="size-picker-control">
            <input id="fontSizePoints" role="combobox" autocomplete="off" inputmode="decimal" aria-autocomplete="none" aria-haspopup="listbox" aria-controls="fontSizeMenu" aria-expanded="false">
            <button id="fontSizeToggle" type="button" aria-label="选择字号" aria-expanded="false" aria-controls="fontSizeMenu"><svg viewBox="0 0 16 16" aria-hidden="true"><path d="m4 6 4 4 4-4"/></svg></button>
          </div>
          <div id="fontSizeMenu" class="font-size-menu" role="listbox" hidden></div>
        </div>
        <label class="color-field"><span data-label="color">颜色</span> <input id="color" type="color"></label>
      </div>
      <button id="previewToggle" type="button" aria-pressed="false"><span class="preview-icon">${icons.preview}</span><span class="edit-icon">${icons.edit}</span><span class="button-label">最终预览</span></button>
      <button id="currentFavoriteButton" class="tool-icon favorite-toggle" type="button" aria-pressed="false">${icons.favorite}</button>
      <button id="libraryToggle" class="library-toggle tool-icon" type="button" aria-expanded="true" aria-controls="symbolLibrary">${icons.library}</button>
    </header>
    <main class="shell">
      <aside id="symbolLibrary" class="library" aria-label="Symbols and templates">
        <div class="library-search"><input type="search" id="symbolSearch" autocomplete="off"></div>
        <div class="library-tabs" id="libraryTabs" role="tablist" aria-orientation="vertical" aria-label="Categories"></div>
        <div class="library-content">
          <div class="library-controls">
            <span id="libraryTitleText" role="status"></span>
            <div id="matrixSize" hidden>
              <label><span id="matrixRowsLabel"></span><select id="matrixRows"></select></label>
              <label><span id="matrixColumnsLabel"></span><select id="matrixColumns"></select></label>
            </div>
          </div>
          <div class="symbol-grid" id="symbolGrid" role="tabpanel" tabindex="0"></div>
        </div>
      </aside>
      <section class="workspace" aria-label="Formula and source">
        <div class="formula-stage"><div id="mathfieldHost" class="mathfield-host"><div id="sourceModeNote" class="source-mode-note" role="status" hidden><span id="sourceModeMessage"></span><button id="adoptVisualButton" type="button" hidden></button></div></div>
        <div id="finalPreview" hidden><div id="previewNote"></div><div id="previewStatus" role="status"></div><img id="previewImage" alt="Formula preview" hidden></div></div>
        <div id="sourceResizeHandle" class="source-resize-handle" role="separator" aria-orientation="horizontal" aria-controls="latexSource" aria-label="Resize LaTeX source pane" aria-valuemin="96" aria-valuenow="150" tabindex="0"></div>
        <div id="latexSource"></div>
      </section>
    </main>
    <footer class="footer">
      <span class="status" id="statusText" role="status"></span>
      <button type="button" id="cancelButton"></button>
      <button type="button" id="acceptButton"></button>
    </footer>`);
}
