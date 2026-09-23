// Both Office hosts mount this one layout; their HTML only loads shared assets.
export function mountEditor() {
  document.body.insertAdjacentHTML('afterbegin', `
    <header class="toolbar" aria-label="Editor tools">
      <strong>LaTeX</strong>
      <button id="undoButton" type="button"></button>
      <button id="redoButton" type="button"></button>
      <button id="typographyToggle" type="button" aria-expanded="false" aria-controls="typographyPanel">字体设置</button>
      <label><span data-label="fontSizePoints">字号</span> <input id="fontSizePoints" list="fontSizes" autocomplete="off" size="5"></label>
      <datalist id="fontSizes"></datalist>
      <label><span data-label="color">颜色</span> <input id="color" type="color"></label>
      <button id="previewToggle" type="button" aria-pressed="false">最终预览</button>
      <div id="typographyPanel" class="typography-panel" hidden>
        <label><span data-label="symbolFontId"></span><select id="symbolFontId"></select></label>
        <label><span data-label="numberFontFamily"></span><select id="numberFontFamily"></select></label>
        <label><span data-label="cjkFontFamily"></span><select id="cjkFontFamily"></select></label>
        <label><span data-label="defaultMathStyle"></span><select id="defaultMathStyle"></select></label>
      </div>
      <button id="libraryToggle" class="library-toggle" type="button" aria-expanded="true" aria-controls="symbolLibrary"></button>
    </header>
    <main class="shell">
      <section class="workspace" aria-label="Formula and source">
        <div class="formula-stage"><div id="mathfieldHost" class="mathfield-host"><div id="sourceModeNote" class="source-mode-note" role="status"></div></div>
        <div id="finalPreview" hidden><div id="previewNote"></div><div id="previewStatus" role="status"></div><img id="previewImage" alt="Formula preview" hidden></div></div>
        <div id="sourceResizeHandle" class="source-resize-handle" role="separator" aria-orientation="horizontal" aria-controls="latexSource" aria-label="Resize LaTeX source pane" aria-valuemin="96" aria-valuenow="150" tabindex="0"></div>
        <div id="latexSource"></div>
      </section>
      <aside id="symbolLibrary" class="library" aria-label="Symbols and templates">
        <div class="library-heading">
          <div class="library-tabs" id="libraryTabs" role="tablist" aria-label="Categories"></div>
          <input type="search" id="symbolSearch" autocomplete="off">
        </div>
        <div class="library-controls">
          <span id="libraryTitleText" role="status"></span>
          <div id="matrixSize" hidden>
            <label><span id="matrixRowsLabel"></span><select id="matrixRows"></select></label>
            <label><span id="matrixColumnsLabel"></span><select id="matrixColumns"></select></label>
          </div>
          <button type="button" id="libraryPrevious">‹</button>
          <button type="button" id="libraryNext">›</button>
        </div>
        <div class="symbol-grid" id="symbolGrid" role="tabpanel" tabindex="0"></div>
      </aside>
    </main>
    <footer class="footer">
      <span class="status" id="statusText" role="status"></span>
      <button type="button" id="cancelButton"></button>
      <button type="button" id="acceptButton"></button>
    </footer>`);
}
