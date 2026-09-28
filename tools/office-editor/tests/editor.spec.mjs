import {test, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {resolve, extname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const shared = resolve(root, 'office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets');
const source = page => page.locator('#latexSource .cm-content');
async function open(page, latex = 'x+1', host = 'word', color = '#000000') {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text()); });
  await page.route('https://*.officeplugin.local/**', async route => {
    const url = new URL(route.request().url());
    const relative = decodeURIComponent(url.pathname.slice(1));
    const directory = url.hostname.includes('editor-shared') ? shared
      : resolve(root, `office_plugin/hosts/${host === 'word' ? 'Word' : 'PowerPoint'}AddIn/EditorAssets`);
    const path = relative.startsWith('vendor/') ? resolve(root, 'src/assets/mathlive', relative) : resolve(directory, relative);
    const types = {'.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.woff2': 'font/woff2'};
    await route.fulfill({body: await readFile(path), contentType: types[extname(path)] || 'application/octet-stream'});
  });
  await page.addInitScript(({latex, color}) => {
    window.editorInit = {latex, locale: 'zh', mode: 'update', session: 1, display: true, referencePreview: false,
      typography: {typographyVersion: 1, symbolFontId: 'mathjax-tex', numberFontFamily: '', cjkFontFamily: 'Microsoft YaHei', defaultMathStyle: 'Automatic', fontSizePoints: 12, color},
      catalog: {symbolFonts: ['mathjax-tex', 'mathjax-stix2'], systemFonts: ['Microsoft YaHei', 'SimSun', 'Arial'],
        cjkFonts: ['Microsoft YaHei', 'SimSun'], mathStyles: [
          {id: 'Automatic', zh: '自动数学样式', en: 'Automatic'},
          {id: 'Upright', zh: '正体', en: 'Upright'}, {id: 'Bold', zh: '粗体', en: 'Bold'},
          {id: 'BoldFraktur', zh: '哥特粗体', en: 'Bold Fraktur'}],
        namedSizes: {'初号': 42, '四号': 14, '小四': 12, '五号': 10.5}, commonPointSizes: [10.5, 12, 14, 18, 24, 36, 42], minimumPoints: 1, maximumPoints: 1638}};
    window.__latexSnipperPendingInit = window.editorInit;
    window.posted = [];
    window.chrome = {webview: {postMessage: message => window.posted.push(message)}};
  }, {latex, color});
  await page.goto(`https://latexsnipper-${host}.officeplugin.local/editor.html`);
  await expect(page).toHaveTitle('LaTeXSnipper');
  await expect(source(page)).toBeVisible();
  await expect(page.locator('#acceptButton')).toHaveText('更新');
  return errors;
}
async function submitted(page) {
  await page.locator('#acceptButton').click();
  return page.evaluate(() => {
    const latex = window.posted.findLast(message => message.type === 'accept')?.latex;
    window.LaTeXSnipperEditor.setSubmitting(false);
    return latex;
  });
}

test('complex source survives load, reference focus, source editing, undo and submission', async ({page}) => {
  const latex = '  \\begin{align}\n&\\text{设 } A,B \\text{ 为事件}\\\\\n&P(A\\mid B)=\\frac{P(A\\cap B)}{P(B)}\n\\end{align} % 注释\n';
  const errors = await open(page, latex);
  await page.locator('#mathfieldHost math-field').click();
  expect(await submitted(page)).toBe(latex);
  await source(page).fill('\\frac{a}{b}+12');
  await expect(page.locator('#latexSource .cm-line span')).not.toHaveCount(0);
  expect(await submitted(page)).toBe('\\frac{a}{b}+12');
  await source(page).press('Control+z');
  expect(await submitted(page)).toBe(latex);
  expect(errors).toEqual([]);
  await expect(page.locator('#sourceModeNote')).toContainText('源码区');
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-light.png')});
});

test('editor starts in the visual field and returns there after host focus', async ({page}) => {
  const errors = await open(page, 'x+1');
  await expect(visual(page)).toBeFocused();
  await expect(page.locator('#undoButton')).not.toBeFocused();
  await page.locator('#undoButton').evaluate(button => button.focus());
  await expect(visual(page)).toBeFocused();
  await page.keyboard.type('2');
  await expect.poll(() => source(page).innerText()).toContain('2');
  expect(errors).toEqual([]);
});

test('removing an align container releases visual editing without retaining its old rows', async ({page}) => {
  const errors = await open(page, '\\begin{align}x&=1\\\\y&=2\\end{align}');
  await expect.poll(() => visual(page).evaluate(field => field.readOnly)).toBe(false);
  await source(page).fill('');
  await expect.poll(() => visual(page).evaluate(field => field.getValue('latex'))).toBe('');
  await expect.poll(() => visual(page).evaluate(field => field.readOnly)).toBe(false);
  await source(page).fill('x+1');
  await expect.poll(() => visual(page).evaluate(field => field.getValue('latex'))).toBe('x+1');
  await expect(page.locator('#sourceModeNote')).toBeHidden();
  await source(page).fill('\\begin{align}a&=b\\\\c&=d\\end{align}');
  await expect.poll(() => visual(page).evaluate(field => field.readOnly)).toBe(false);
  await source(page).fill('');
  await expect(page.locator('#sourceModeNote')).toBeHidden();
  expect(errors).toEqual([]);
});

test('source that MathLive would rewrite can be adopted explicitly and undone', async ({page}) => {
  const latex = 'x\\displaylines{y=z}';
  const errors = await open(page, latex);
  await expect(page.locator('#sourceModeNote')).toContainText('改写');
  await expect.poll(() => visual(page).evaluate(field => field.readOnly)).toBe(true);
  await page.locator('#adoptVisualButton').click();
  await expect.poll(() => visual(page).evaluate(field => field.readOnly)).toBe(false);
  expect(await source(page).innerText()).not.toBe(latex);
  await source(page).press('Control+z');
  await expect(source(page)).toHaveText(latex);
  expect(errors).toEqual([]);
});

test('source history includes visual edits; unfocused notifications cannot replace newer source', async ({page}) => {
  const errors = await open(page);
  await page.locator('#mathfieldHost math-field').click();
  await page.locator('#mathfieldHost math-field').press('End');
  await page.keyboard.type('2');
  await expect.poll(() => source(page).innerText()).toContain('2');
  await page.locator('#mathfieldHost math-field').press('Control+z');
  expect(await submitted(page)).toBe('x+1');
  await page.locator('#mathfieldHost math-field').click();
  await page.locator('#mathfieldHost math-field').press('Control+y');
  expect(await submitted(page)).toBe('x+12');
  await source(page).fill('newest');
  await page.evaluate(() => { const mf = document.querySelector('#mathfieldHost math-field'); mf.setValue('stale', {silenceNotifications: true}); mf.dispatchEvent(new Event('input')); });
  expect(await submitted(page)).toBe('newest');
  expect(errors).toEqual([]);
});

test('IME composition keeps source editable, blocks submission and updates after commit', async ({page}) => {
  await open(page);
  await source(page).dispatchEvent('compositionstart');
  await source(page).fill('\\text{中文}');
  await page.locator('#acceptButton').click();
  expect(await page.evaluate(() => window.posted.filter(message => message.type === 'accept').length)).toBe(0);
  await source(page).dispatchEvent('compositionend');
  await expect.poll(() => page.locator('#mathfieldHost math-field').evaluate(el => el.getValue('latex'))).toContain('中文');
  expect(await submitted(page)).toBe('\\text{中文}');
});

test('PPT uses the same light editor with diagnostics and search under a dark OS theme', async ({page}) => {
  await page.emulateMedia({colorScheme: 'dark'});
  await page.setViewportSize({width: 980, height: 680});
  const errors = await open(page, '\\frac{a}{b', 'powerpoint');
  await expect(page.locator('.cm-lintRange-error')).not.toHaveCount(0);
  await source(page).press('Control+f');
  await expect(page.locator('.cm-search')).toBeVisible();
  expect(await page.locator('html').evaluate(el => getComputedStyle(el).colorScheme)).toBe('light');
  expect(await page.locator('body').evaluate(el => getComputedStyle(el).backgroundColor)).toBe('rgb(238, 242, 247)');
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-forced-light.png')});
  expect(errors).toEqual([]);
});

test('brackets, command and environment completion and indentation work from the source pane', async ({page}) => {
  const errors = await open(page, '');
  await source(page).click();
  await page.keyboard.type('{');
  expect(await submitted(page)).toBe('{}');
  await source(page).fill('\\fra');
  await source(page).press('Control+Space');
  await expect(page.locator('.cm-tooltip-autocomplete')).toBeVisible();
  // CodeMirror deliberately ignores acceptance during the popup's first 75 ms.
  await page.waitForTimeout(100);
  await source(page).press('Enter');
  expect(await submitted(page)).toBe('\\frac{}{}');
  await source(page).fill('\\begin{ali');
  await source(page).press('Control+Space');
  await expect(page.locator('.cm-tooltip-autocomplete')).toContainText('aligned');
  await page.waitForTimeout(100);
  await source(page).press('Enter');
  expect(await submitted(page)).toContain('\\end{align}');
  await source(page).fill('\\begin{aligned}');
  await source(page).press('End');
  await source(page).press('Enter');
  await page.keyboard.type('x');
  expect(await submitted(page)).toBe('\\begin{aligned}\n  x');
  expect(errors).toEqual([]);
});

test('environment completion consumes the existing auto-closed brace', async ({page}) => {
  const errors = await open(page, '');
  for (const [prefix, name] of [['ali', 'align'], ['cas', 'cases'], ['mat', 'matrix']]) {
    await source(page).fill('');
    await source(page).click();
    await page.keyboard.type(`\\begin{${prefix}`);
    expect(await submitted(page)).toBe(`\\begin{${prefix}}`);
    await source(page).press('Control+Space');
    await expect(page.locator('.cm-tooltip-autocomplete')).toBeVisible();
    await page.waitForTimeout(100);
    await source(page).press('Enter');
    const completed = await submitted(page);
    expect(completed).toMatch(new RegExp(`^\\\\begin\\{${name}\\}[\\s\\S]*\\\\end\\{${name}\\}$`));
    expect(completed).not.toContain(`\\end{${name}}}`);
  }
  expect(errors).toEqual([]);
});

test('find/replace, source symbol insertion, session reset and submission locking', async ({page}) => {
  const errors = await open(page, 'x+x');
  await source(page).press('Control+f');
  await page.locator('.cm-search input[name="search"]').fill('x');
  await page.locator('.cm-search input[name="replace"]').fill('y');
  await page.locator('.cm-search button[name="replaceAll"]').click();
  expect(await submitted(page)).toBe('y+y');
  await source(page).press('Escape');
  await source(page).press('End');
  await page.locator('[data-group="greek"]').click();
  await page.locator('#symbolGrid').getByRole('button', {name: 'α', exact: true}).click();
  expect(await submitted(page)).toBe('y+y\\alpha');
  await page.evaluate(() => window.LaTeXSnipperEditor.init({...window.editorInit,latex: 'new', locale: 'zh'}));
  await source(page).press('Control+z');
  expect(await submitted(page)).toBe('new');
  await page.evaluate(() => window.LaTeXSnipperEditor.setSubmitting(true));
  await expect(page.locator('#acceptButton')).toBeDisabled();
  await expect(source(page)).toHaveAttribute('contenteditable', 'false');
  expect(errors).toEqual([]);
});

const visual = page => page.locator('#mathfieldHost math-field');
const tile = (page, name) => page.locator('#symbolGrid').getByRole('button', {name, exact: true});
async function searchTile(page, query) {
  await page.locator('#symbolSearch').fill(query);
}

for (const host of ['word', 'powerpoint']) {
  test(`${host}: source selection survives search, template fields and a single undo/redo`, async ({page}) => {
    const errors = await open(page, 'x+1', host);
    await source(page).press('Control+a');
    await searchTile(page, 'Fraction');
    await tile(page, '分数').click();
    expect(errors).toEqual([]);
    await expect(source(page)).toHaveText('\\frac{x+1}{}');
    await page.keyboard.type('y');
    await expect(source(page)).toHaveText('\\frac{x+1}{y}');
    await source(page).press('Control+z');
    await expect(source(page)).toHaveText('\\frac{x+1}{}');
    await source(page).press('Control+z');
    await expect(source(page)).toHaveText('x+1');
    await source(page).press('Control+y');
    await expect(source(page)).toHaveText('\\frac{x+1}{}');
    await page.evaluate(() => window.LaTeXSnipperEditor.init({...window.editorInit,latex: '', locale: 'zh'}));
    await source(page).click();
    await searchTile(page, 'Fraction');
    await tile(page, '分数').click();
    expect(errors).toEqual([]);
    await page.keyboard.type('a');
    await source(page).press('Tab');
    await page.keyboard.type('b');
    expect(await submitted(page)).toBe('\\frac{a}{b}');
    expect(errors).toEqual([]);
  });

  test(`${host}: visual selection survives search and matrix dimensions use the same insertion path`, async ({page}) => {
    const errors = await open(page, 'x+1', host);
    await visual(page).click();
    await visual(page).press('Control+a');
    await searchTile(page, 'Fraction');
    await tile(page, '分数').click();
    expect(errors).toEqual([]);
    await expect(source(page)).toContainText('\\frac{x+1}');
    await page.keyboard.type('2');
    await expect(source(page)).toHaveText('\\frac{x+1}{2}');
    await page.locator('#undoButton').click();
    await expect(source(page)).toContainText('\\frac{x+1}');
    await page.locator('#undoButton').click();
    await expect(source(page)).toHaveText('x+1');
    await page.locator('#redoButton').click();
    await expect(source(page)).toContainText('\\frac{x+1}');
    await page.evaluate(() => window.LaTeXSnipperEditor.init({...window.editorInit,latex: 'z', locale: 'zh'}));
    await source(page).press('Control+a');
    await searchTile(page, 'Bracketed matrix');
    await page.locator('#matrixRows').selectOption('3');
    await page.locator('#matrixColumns').selectOption('2');
    await tile(page, '方括号矩阵').click();
    await expect(source(page)).toHaveText('\\begin{bmatrix} z &  \\\\  &  \\\\  &  \\end{bmatrix}');
    await page.keyboard.type('b');
    await source(page).press('Tab');
    await page.keyboard.type('c');
    expect(await submitted(page)).toContain('z & b \\\\ c &');
    expect(errors).toEqual([]);
  });
}

test('reference-only formulas route tiles to source; composition and submission guard every entry', async ({page}) => {
  const latex = '\\begin{align}x&=1\\\\y&=2\\end{align} % keep';
  const errors = await open(page, latex);
  await source(page).press('Control+End');
  await visual(page).click();
  await searchTile(page, 'alpha');
  await tile(page, 'α').click();
  await expect(source(page)).toHaveText(latex + '\\alpha');
  await source(page).dispatchEvent('compositionstart');
  await tile(page, 'α').click();
  await page.locator('#undoButton').click();
  await expect(source(page)).toHaveText(latex + '\\alpha');
  await source(page).dispatchEvent('compositionend');
  await source(page).fill('x+1');
  await page.evaluate(() => window.LaTeXSnipperEditor.setSubmitting(true));
  await expect.poll(() => visual(page).evaluate(el => el.readOnly)).toBe(true);
  await page.waitForTimeout(180);
  expect(await visual(page).evaluate(el => el.readOnly)).toBe(true);
  await tile(page, 'α').click();
  await expect(source(page)).toHaveText('x+1');
  await expect(page.locator('#undoButton')).toBeDisabled();
  await page.evaluate(() => window.LaTeXSnipperEditor.setSubmitting(false));
  await visual(page).dispatchEvent('compositionstart');
  await tile(page, 'α').click();
  await expect(source(page)).toHaveText('x+1');
  await visual(page).dispatchEvent('compositionend');
  expect(errors).toEqual([]);
});

test('global search, vertical symbol scrolling, rendered previews and compact layout', async ({page}) => {
  const errors = await open(page, 'x');
  await source(page).press('End');
  await page.locator('[data-group="structures"]').click();
  const grid = page.locator('#symbolGrid');
  await expect.poll(() => grid.locator('.tile-preview-content').count()).toBeGreaterThan(0);
  await expect.poll(() => grid.evaluate(el => {
    const viewport = el.getBoundingClientRect();
    return [...el.querySelectorAll('.symbol-tile')].filter(button => {
      const rect = button.getBoundingClientRect();
      return rect.bottom > viewport.top && rect.top < viewport.bottom;
    }).every(button => Boolean(button.querySelector('.tile-preview-content')));
  })).toBe(true);
  const gridBox = await grid.boundingBox();
  await page.mouse.move(gridBox.x + 50, gridBox.y + 20);
  await page.mouse.wheel(0, 350);
  await expect.poll(() => grid.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
  const scrolled = await grid.evaluate(el => el.scrollTop);
  const sourceBox = await source(page).boundingBox();
  await page.mouse.move(sourceBox.x + 30, sourceBox.y + 10);
  await page.mouse.wheel(0, 200);
  expect(await grid.evaluate(el => el.scrollTop)).toBe(scrolled);
  await searchTile(page, 'alpha');
  await page.locator('#symbolSearch').press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(source(page)).toHaveText('x\\alpha');
  await searchTile(page, 'not-found-123');
  await expect(grid).toContainText('没有匹配');
  await page.locator('#symbolSearch').press('Escape');
  await expect(source(page)).toBeFocused();
  await page.locator('#libraryToggle').click();
  await expect(page.locator('#symbolLibrary')).toBeHidden();
  await expect(source(page)).toBeFocused();
  await page.locator('#libraryToggle').click();
  await page.setViewportSize({width: 640, height: 480});
  await expect(page.locator('#acceptButton')).toBeInViewport();
  await expect(source(page)).toBeInViewport();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-6a-compact.png')});
  expect(errors).toEqual([]);
});

test('visual template Tab navigation and shortcut wrapping share history', async ({page}) => {
  const errors = await open(page, '');
  await visual(page).click();
  await searchTile(page, 'Fraction');
  await tile(page, '分数').click();
  await expect(visual(page)).toBeFocused();

  await page.keyboard.type('a');
  expect(errors).toEqual([]);
  await expect(source(page)).toHaveText('\\frac{a}{\\placeholder{}}');
  await visual(page).press('Tab');
  await page.keyboard.type('b');
  await expect(source(page)).toHaveText('\\frac{a}{b}');
  await visual(page).press('Control+a');
  await visual(page).press('Control+r');
  await expect(source(page)).toHaveText('\\sqrt{\\frac{a}{b}}');
  await visual(page).press('Control+z');
  await expect(source(page)).toHaveText('\\frac{a}{b}');
  expect(errors).toEqual([]);
});

test('escaped source wraps literally; keyboard navigation, cached tiles and resize keep editing usable', async ({page}) => {
  const latex = '\\left\\{x\\right\\}+\\text{${literal} #?}';
  const errors = await open(page, latex);
  await source(page).press('Control+a');
  await searchTile(page, 'Fraction');
  await tile(page, '分数').click();
  await page.keyboard.type('d');
  await expect(source(page)).toHaveText('\\frac{' + latex + '}{d}');
  await page.locator('[data-group="structures"]').click();
  await expect.poll(() => tile(page, '分数').locator('.tile-preview-content').count()).toBe(1);
  const cached = await tile(page, '分数').locator('.tile-preview-content').elementHandle();
  await page.locator('[data-group="greek"]').click();
  await page.locator('[data-group="structures"]').click();
  await expect.poll(() => tile(page, '分数').locator('.tile-preview-content').count()).toBe(1);
  expect(await tile(page, '分数').locator('.tile-preview-content').evaluate((element, previous) => element === previous, cached)).toBe(true);
  await tile(page, '分数').focus();
  await page.keyboard.press('ArrowDown');
  await expect(tile(page, '分数')).not.toBeFocused();
  await page.keyboard.press('Home');
  await expect(tile(page, '分数')).toBeFocused();
  const resize = page.locator('#sourceResizeHandle');
  const before = Number(await resize.getAttribute('aria-valuenow'));
  await resize.press('ArrowUp');
  expect(Number(await resize.getAttribute('aria-valuenow'))).toBeGreaterThan(before);
  await page.locator('[data-group="geometry"]').click();
  const grid = page.locator('#symbolGrid');
  expect(await grid.locator('button').count()).toBeGreaterThan(100);
  await grid.evaluate(el => { el.scrollTop = 400; });
  const scrolled = await grid.evaluate(el => el.scrollTop);
  expect(scrolled).toBeGreaterThan(0);
  await page.locator('[data-group="greek"]').click();
  await page.locator('[data-group="geometry"]').click();
  expect(await grid.evaluate(el => el.scrollTop)).toBeGreaterThanOrEqual(scrolled - 10);
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-6a-structures.png')});
  await page.evaluate(() => window.LaTeXSnipperEditor.init({...window.editorInit,latex: 'x', locale: 'en'}));
  await searchTile(page, '分数');
  await expect(tile(page, 'Fraction')).toBeVisible();
  await page.locator('#symbolSearch').press('Escape');
  await expect(visual(page)).toBeFocused();
  expect(errors).toEqual([]);
});

const latestPreview = page => page.evaluate(() => window.posted.findLast(message => message.type === 'preview'));
async function deliverPreview(page, request, overrides = {}) {
  await page.evaluate(({request, overrides}) => window.LaTeXSnipperEditor.previewResult({session: request.session,
    revision: request.revision, image: 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="80" height="30"><text y="20">x+1</text></svg>'),
    widthPoints: 60, heightPoints: 22.5, warnings: [], ...overrides}), {request, overrides});
}

test('typography and current source share one preview and submission snapshot in both hosts', async ({page}) => {
  for (const host of ['word', 'powerpoint']) {
    await open(page, 'x+1', host);
    await page.locator('#typographyToggle').click();
    await page.locator('#symbolFontId').selectOption('mathjax-stix2');
    await page.locator('#numberFontFamily').selectOption('Arial');
    await page.locator('#cjkFontFamily').selectOption('SimSun');
    await page.locator('#defaultMathStyle').selectOption('Upright');
    await page.locator('#fontSizePoints').fill('五号');
    await page.locator('#color').fill('#cc2200');
    await page.locator('#previewToggle').click();
    await expect.poll(() => latestPreview(page)).toBeTruthy();
    const request = await latestPreview(page);
    expect(request.typography).toEqual({typographyVersion: 1, symbolFontId: 'mathjax-stix2', numberFontFamily: 'Arial',
      cjkFontFamily: 'SimSun', defaultMathStyle: 'Upright', fontSizePoints: 10.5, color: '#cc2200'});
    await deliverPreview(page, request);
    await expect(page.locator('#previewImage')).toBeVisible();
    expect(await page.locator('#previewImage').evaluate(image => image.getBoundingClientRect().width)).toBe(80);
    await page.locator('#acceptButton').click();
    const accepted = await page.evaluate(() => window.posted.findLast(message => message.type === 'accept'));
    expect(accepted.typography).toEqual(request.typography);
    expect(accepted.latex).toBe(request.latex);
    await expect(page.locator('#fontSizePoints')).toBeDisabled();
    await page.evaluate(() => window.LaTeXSnipperEditor.setSubmitting(false));
    await expect.poll(async () => (await latestPreview(page)).revision).toBeGreaterThan(request.revision);
  }
});

test('visual Enter creates a readable source line for each formula row', async ({page}) => {
  const errors = await open(page, 'x=1');
  await visual(page).click();
  await visual(page).press('End');
  await visual(page).press('Enter');
  await page.keyboard.type('y=2');
  await expect.poll(() => page.locator('#latexSource .cm-line').count()).toBeGreaterThan(1);
  const latex = await submitted(page);
  expect(latex).toMatch(/\\\\\s*\n/);
  expect(errors).toEqual([]);
});

test('plain source Tab inserts at the caret while template fields retain Tab navigation', async ({page}) => {
  const errors = await open(page, 'abcd');
  await source(page).press('Home');
  await source(page).press('ArrowRight');
  await source(page).press('ArrowRight');
  await source(page).press('Tab');
  expect(await submitted(page)).toBe('ab\tcd');
  expect(errors).toEqual([]);
});

test('font controls stay open while moving between native selects', async ({page}) => {
  const errors = await open(page, 'x+1');
  await page.locator('#typographyToggle').click();
  const panel = page.locator('#typographyPanel');
  for (const [id, value] of [['symbolFontId', 'mathjax-stix2'], ['numberFontFamily', 'Arial'],
    ['cjkFontFamily', 'SimSun'], ['defaultMathStyle', 'Upright']]) {
    const select = page.locator(`#${id}`);
    await select.focus();
    await expect(panel).toBeVisible();
    await select.selectOption(value);
    await expect(select).toHaveValue(value);
    if (id === 'numberFontFamily') await expect(select.locator('option').first()).toHaveAttribute('value', '');
    if (id === 'cjkFontFamily') await expect(select.locator('option').first()).toHaveAttribute('value', 'Microsoft YaHei');
    if (id === 'symbolFontId') await expect(select.locator('option').first()).toHaveAttribute('value', 'mathjax-tex');
  }
  expect(await page.locator('#cjkFontFamily option').allTextContents()).not.toContain('Arial');
  await expect(page.locator('#defaultMathStyle option:checked')).toHaveText('正体');
  await expect(panel).toBeVisible();
  await submitted(page);
  expect((await page.evaluate(() => window.posted.findLast(message => message.type === 'accept').typography)).numberFontFamily).toBe('Arial');
  expect(errors).toEqual([]);
});

test('browser chrome is suppressed while editor shortcuts keep working', async ({page}) => {
  const errors = await open(page, 'x');
  const contextMenuBlocked = await page.evaluate(() => {
    const event = new MouseEvent('contextmenu', {bubbles: true, cancelable: true, composed: true});
    document.querySelector('#latexSource').dispatchEvent(event);
    return event.defaultPrevented;
  });
  expect(contextMenuBlocked).toBe(true);
  const browserFindBlocked = await page.evaluate(() => {
    const event = new KeyboardEvent('keydown', {key: 'f', ctrlKey: true, bubbles: true, cancelable: true});
    document.querySelector('#undoButton').dispatchEvent(event);
    return event.defaultPrevented;
  });
  expect(browserFindBlocked).toBe(true);
  await source(page).press('Control+f');
  await expect(page.locator('.cm-search')).toBeVisible();
  await source(page).press('Escape');
  await visual(page).click();
  await visual(page).press('Control+a');
  await visual(page).press('Control+r');
  await expect(source(page)).toHaveText('\\sqrt{x}');
  expect(errors).toEqual([]);
});

test('visual right-click offers the compact Chinese menu and keeps editing active', async ({page}) => {
  await page.emulateMedia({colorScheme: 'dark'});
  const errors = await open(page, 'x');
  expect(await visual(page).evaluate(field => field.menuItems.map(item => [item.id, item.label]))).toEqual([
    ['color', '局部上色'], ['cut', '剪切'], ['paste', '粘贴'], ['select-all', '全选']
  ]);
  expect(await visual(page).evaluate(field => ['menu-toggle', 'virtual-keyboard-toggle'].map(part =>
    getComputedStyle(field.shadowRoot.querySelector(`[part~="${part}"]`)).display))).toEqual(['none', 'none']);
  await visual(page).click();
  await expect(visual(page)).toBeFocused();
  await visual(page).click({button: 'right'});
  await expect(page.getByRole('menuitem', {name: '局部上色'})).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(visual(page)).toBeFocused();
  await page.keyboard.type('2');
  await expect(source(page)).toHaveText('x2');
  await page.evaluate(() => window.mathVirtualKeyboard.show());
  await expect.poll(() => page.evaluate(() => window.mathVirtualKeyboard.visible)).toBe(true);
  expect(await page.locator('.ML__keyboard').evaluate(el => getComputedStyle(el).getPropertyValue('--_background').trim())).toBe('#cacfd7');
  await page.keyboard.press('Escape');
  await expect.poll(() => page.evaluate(() => window.mathVirtualKeyboard.visible)).toBe(false);
  await page.keyboard.type('3');
  await expect(source(page)).toHaveText('x23');
  expect(errors).toEqual([]);
});

test('global color matches visual editing and menu color immediately updates source', async ({page}) => {
  const errors = await open(page, 'x+y', 'word', '#cc0000');
  await expect(source(page)).toHaveText('\\textcolor{#cc0000}{x+y}');
  await expect.poll(() => visual(page).evaluate(field => getComputedStyle(field).color)).toBe('rgb(204, 0, 0)');
  await visual(page).click();
  await visual(page).press('Control+a');
  await visual(page).click({button: 'right'});
  await page.getByRole('menuitem', {name: '局部上色'}).click();
  await page.getByRole('menuitemcheckbox', {name: 'teal'}).click();
  await expect(source(page)).toContainText('\\textcolor{teal}');
  await expect(source(page)).toContainText('\\textcolor{#cc0000}');
  await page.locator('#color').fill('#0000cc');
  await expect(source(page)).toContainText('\\textcolor{#0000cc}');
  await expect(source(page)).not.toContainText('\\textcolor{#cc0000}');
  await visual(page).press('ArrowRight');
  await page.locator('#previewToggle').click();
  await expect.poll(() => page.evaluate(() => window.posted.findLast(message => message.type === 'preview')?.typography.color)).toBe('#0000cc');
  await source(page).fill('\\textcolor{#00aa00}{z}');
  await expect(page.locator('#color')).toHaveValue('#00aa00');
  await expect.poll(() => page.evaluate(() => window.posted.findLast(message => message.type === 'preview')?.typography.color)).toBe('#00aa00');
  expect(await submitted(page)).toBe('\\textcolor{#00aa00}{z}');
  expect((await page.evaluate(() => window.posted.findLast(message => message.type === 'accept').typography)).color).toBe('#00aa00');
  await source(page).fill('z');
  await expect(page.locator('#color')).toHaveValue('#000000');
  await expect.poll(() => page.evaluate(() => window.posted.findLast(message => message.type === 'preview')?.typography.color)).toBe('#000000');
  expect(errors).toEqual([]);
});

test('compact visual menu selects, cuts and pastes through the source state', async ({page}) => {
  const errors = await open(page, 'x+y');
  await page.context().grantPermissions(['clipboard-read', 'clipboard-write'],
    {origin: 'https://latexsnipper-word.officeplugin.local'});
  await visual(page).click({button: 'right'});
  await page.getByRole('menuitem', {name: '全选'}).click();
  await visual(page).click({button: 'right'});
  await page.getByRole('menuitem', {name: '剪切'}).click();
  await expect(source(page)).toBeEmpty();
  await visual(page).click({button: 'right'});
  await page.getByRole('menuitem', {name: '粘贴'}).click();
  await expect(source(page)).toHaveText('x+y');
  expect(errors).toEqual([]);
});

test('colored source remains editable in MathLive', async ({page}) => {
  const errors = await open(page, '\\textcolor{#cc0000}{x+\\textcolor{teal}{y}}');
  await expect(visual(page)).toHaveJSProperty('readOnly', false);
  await expect(page.locator('#color')).toHaveValue('#cc0000');
  await page.locator('#previewToggle').click();
  await expect.poll(() => page.evaluate(() => window.posted.findLast(message => message.type === 'preview')?.typography.color)).toBe('#cc0000');
  expect(errors).toEqual([]);
});

test('empty formula inherits its configured color in source and visual editing', async ({page}) => {
  const errors = await open(page, '', 'word', '#363bd3');
  await expect(source(page)).toHaveText('\\textcolor{#363bd3}{}');
  await expect(page.locator('#color')).toHaveValue('#363bd3');
  await expect(visual(page)).toHaveJSProperty('readOnly', false);
  await visual(page).click();
  await page.keyboard.type('x');
  await expect(source(page)).toHaveText('\\textcolor{#363bd3}{x}');
  expect(errors).toEqual([]);
});

test('local color on the final symbol does not pin the old global color', async ({page}) => {
  const errors = await open(page, 'x=L', 'word', '#363bd3');
  await visual(page).evaluate(field => {
    field.focus();
    field.executeCommand('moveToMathfieldEnd');
    field.executeCommand('extendSelectionBackward');
  });
  await visual(page).click({button: 'right'});
  await page.getByRole('menuitem', {name: '局部上色'}).click();
  await page.getByRole('menuitemcheckbox', {name: 'red'}).click();
  await expect(source(page)).toContainText('\\textcolor{red}{L}');
  await page.locator('#color').fill('#145a32');
  await expect(source(page)).toContainText('\\textcolor{#145a32}');
  await expect(source(page)).not.toContainText('#363bd3');
  expect(errors).toEqual([]);
});

test('LaTeX suggestion arrows keep the same visual field and complete the command', async ({page}) => {
  const errors = await open(page, '');
  await visual(page).click();
  const original = await visual(page).evaluate(field => { field.dataset.instance = 'initial'; return field.dataset.instance; });
  await page.keyboard.type('\\alef');
  await expect(page.locator('#mathlive-suggestion-popover')).toHaveClass(/is-visible/);
  await page.locator('#mathlive-suggestion-popover').evaluate(popover => { window.__suggestionPopover = popover; });
  await page.keyboard.press('ArrowDown');
  expect(await page.evaluate(() => document.getElementById('mathlive-suggestion-popover') === window.__suggestionPopover)).toBe(true);
  await page.keyboard.press('ArrowUp');
  expect(await page.evaluate(() => document.getElementById('mathlive-suggestion-popover') === window.__suggestionPopover)).toBe(true);
  expect(await visual(page).evaluate(field => field.dataset.instance)).toBe(original);
  await page.keyboard.press('Enter');
  await expect.poll(() => source(page).innerText()).toContain('\\alef');
  expect(errors).toEqual([]);
});

test('Common starts empty and right-click favorites persist without matrix controls', async ({page}) => {
  const errors = await open(page, 'x');
  await expect(page.locator('#libraryTitleText')).toHaveText('常用 · 0');
  await expect(page.locator('#symbolGrid')).toContainText('右键点击公式磁贴');
  await expect(page.locator('#matrixSize')).toBeHidden();
  const order = await page.locator('#libraryTabs .tab').evaluateAll(tabs => tabs.map(tab => tab.dataset.group));
  expect(order.slice(8, 14)).toEqual(['sets', 'analysis', 'algebra', 'geometry', 'topology', 'numberTheory']);
  await page.locator('[data-group="structures"]').click();
  await tile(page, '矩阵').click({button: 'right'});
  await page.getByRole('menuitem', {name: '加入常用'}).click();
  await page.locator('[data-group="common"]').click();
  await expect(tile(page, '矩阵')).toBeVisible();
  await expect(page.locator('#matrixSize')).toBeHidden();
  await page.reload();
  await expect(tile(page, '矩阵')).toBeVisible();
  await tile(page, '矩阵').click({button: 'right'});
  await page.getByRole('menuitem', {name: '从常用移除'}).click();
  await expect(page.locator('#libraryTitleText')).toHaveText('常用 · 0');
  expect(errors).toEqual([]);
});

test('current formula can be saved to Common and survives editor reload', async ({page}) => {
  const errors = await open(page, 'x+1');
  const favorite = page.locator('#currentFavoriteButton');
  await expect(favorite).toHaveAttribute('aria-pressed', 'false');
  await favorite.click();
  await expect(favorite).toHaveAttribute('aria-pressed', 'true');
  await expect(tile(page, '我的公式 1')).toBeVisible();
  await page.reload();
  await expect(tile(page, '我的公式 1')).toBeVisible();
  await source(page).fill('');
  await tile(page, '我的公式 1').click();
  await expect(source(page)).toHaveText('x+1');
  await tile(page, '我的公式 1').click({button: 'right'});
  await page.getByRole('menuitem', {name: '从常用移除'}).click();
  await expect(page.locator('#libraryTitleText')).toHaveText('常用 · 0');
  expect(errors).toEqual([]);
});

test('opening controls leaves selection to the user and preview has no redundant caption', async ({page}) => {
  const errors = await open(page, 'x+1');
  await expect(source(page)).not.toBeFocused();
  await page.locator('#typographyToggle').click();
  await expect(page.locator('#symbolFontId')).not.toBeFocused();
  await page.locator('#fontSizeToggle').click();
  await expect(page.locator('#fontSizePoints')).not.toBeFocused();
  await page.locator('#previewToggle').click();
  await expect(page.locator('#previewNote')).toBeEmpty();
  expect(errors).toEqual([]);
});

test('large categories paint on demand and keep visible tiles available', async ({page}) => {
  const errors = await open(page, 'x');
  const first = await page.evaluate(() => {
    const start = performance.now();
    document.querySelector('[data-group="analysis"]').click();
    return {elapsed: performance.now() - start,
      total: document.querySelectorAll('#symbolGrid .symbol-tile').length,
      rendered: document.querySelectorAll('#symbolGrid .tile-preview-content').length};
  });
  expect(first.total).toBeGreaterThan(100);
  expect(first.rendered).toBeLessThan(first.total);
  expect(first.elapsed).toBeLessThan(300);
  await expect.poll(() => page.locator('#symbolGrid .tile-preview-content').count()).toBeGreaterThan(0);
  const grid = page.locator('#symbolGrid');
  await grid.evaluate(element => { element.scrollTop = 1200; });
  await expect.poll(() => grid.evaluate(element => [...element.querySelectorAll('.symbol-tile')]
    .filter(tile => tile.getBoundingClientRect().bottom > element.getBoundingClientRect().top
      && tile.getBoundingClientRect().top < element.getBoundingClientRect().bottom)
    .some(tile => tile.querySelector('.tile-preview-content')))).toBe(true);
  expect(errors).toEqual([]);
});

test('symbol tiles render LaTeX and pack to their measured width', async ({page}) => {
  await page.setViewportSize({width: 932, height: 592});
  const errors = await open(page, '');
  await page.locator('[data-group="greek"]').click();
  const alpha = tile(page, 'α').locator('.tile-preview-content');
  await expect(alpha).toHaveCount(1);
  expect(await alpha.evaluate(el => Boolean(el.querySelector('[class*="ML__"]')))).toBe(true);
  const compactGreekCount = await page.locator('#symbolGrid .symbol-tile').evaluateAll(buttons => {
    const top = buttons[0].getBoundingClientRect().top;
    return buttons.filter(button => Math.abs(button.getBoundingClientRect().top - top) < 2).length;
  });
  expect(compactGreekCount).toBeGreaterThanOrEqual(3);
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-compact-greek.png')});
  const invalidGreek = await page.evaluate(async () => {
    const base = 'https://latexsnipper-editor-shared.officeplugin.local/';
    const [{findEntries, entryTemplate, templateParts}, {validateLatex}] = await Promise.all([
      import(`${base}template-catalog.mjs`), import(`${base}vendor/mathlive.min.mjs`)]);
    return findEntries('greek').flatMap(entry => {
      const latex = templateParts(entryTemplate(entry)).map(part => part.hole ? '\\square' : part.text).join('');
      return validateLatex(latex).length ? [entry.zh] : [];
    });
  });
  expect(invalidGreek).toEqual([]);
  await page.locator('[data-group="topology"]').click();
  for (const name of ['开集', '闭包']) {
    const rendered = tile(page, name).locator('.tile-preview-content');
    await rendered.scrollIntoViewIfNeeded();
    await expect(rendered).toHaveCount(1);
    expect(await rendered.evaluate(el => Boolean(el.querySelector('[class*="ML__"]')))).toBe(true);
    await expect(rendered).not.toHaveText(name);
  }
  await page.locator('[data-group="structures"]').click();
  const fraction = tile(page, '分数');
  const superscript = tile(page, '上标');
  await expect(fraction.locator('.tile-preview-content')).toHaveCount(1);
  await expect(superscript.locator('.tile-preview-content')).toHaveCount(1);
  const first = await fraction.boundingBox(), second = await superscript.boundingBox();
  expect(Math.abs(first.y - second.y)).toBeLessThan(2);
  expect(second.x).toBeGreaterThan(first.x);
  await expect(tile(page, '矩阵')).toHaveCount(1);
  await page.locator('[data-group="delimiters"]').click();
  const parentheses = tile(page, '( )'), brackets = tile(page, '[ ]');
  await expect(parentheses.locator('.tile-preview-content')).toHaveCount(1);
  await expect(brackets.locator('.tile-preview-content')).toHaveCount(1);
  expect(Math.abs((await parentheses.boundingBox()).y - (await brackets.boundingBox()).y)).toBeLessThan(2);
  await page.locator('[data-group="geometry"]').click();
  const distance = tile(page, '欧氏距离');
  await distance.scrollIntoViewIfNeeded();
  await expect(distance.locator('.tile-preview-content')).toHaveCount(1);
  await page.setViewportSize({width: 640, height: 592});
  await expect.poll(() => distance.locator('.tile-preview').evaluate(frame =>
    frame.querySelector('.tile-preview-content').getBoundingClientRect().width <= frame.clientWidth + 1)).toBe(true);
  await page.setViewportSize({width: 932, height: 592});
  await page.setViewportSize({width: 1920, height: 900});
  await page.locator('[data-group="analysis"]').click();
  const firstRow = await page.locator('#symbolGrid .symbol-tile').evaluateAll(buttons => {
    const top = buttons[0].getBoundingClientRect().top;
    return buttons.filter(button => Math.abs(button.getBoundingClientRect().top - top) < 2).length;
  });
  expect(firstRow).toBeGreaterThan(1);
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-wide-analysis.png')});
  await page.setViewportSize({width: 932, height: 592});
  await page.locator('[data-group="chemistry"]').click();
  const barium = tile(page, 'Ba²⁺');
  await barium.scrollIntoViewIfNeeded();
  await expect(barium.locator('.tile-preview-content')).toHaveCount(1);
  const chemistryRow = await page.locator('#symbolGrid .symbol-tile').evaluateAll(buttons => {
    const top = buttons[0].getBoundingClientRect().top;
    return buttons.filter(button => Math.abs(button.getBoundingClientRect().top - top) < 2).length;
  });
  expect(chemistryRow).toBeGreaterThan(1);
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-adaptive-tiles.png')});
  await searchTile(page, 'Dirac operator');
  await expect(tile(page, 'Dirac 算子').locator('.tile-preview-content')).toHaveText('Dirac 算子');
  await page.evaluate(() => window.LaTeXSnipperEditor.init({...window.editorInit, locale: 'en'}));
  await expect(tile(page, 'Dirac operator').locator('.tile-preview-content')).toHaveText('Dirac operator');
  expect(errors).toEqual([]);
});

test('the same Greek formulas keep compact measured widths in Greek and Common', async ({page}) => {
  await page.setViewportSize({width: 1164, height: 752});
  const errors = await open(page, '');
  await page.locator('[data-group="greek"]').click();
  for (const name of ['α', 'β', 'π']) {
    await tile(page, name).click({button: 'right'});
    await page.getByRole('menuitem', {name: '加入常用'}).click();
  }
  await page.evaluate(() => document.fonts.ready);
  const greekWidth = await tile(page, 'α').evaluate(el => el.getBoundingClientRect().width);
  await page.locator('[data-group="common"]').click();
  await expect(tile(page, 'π').locator('.tile-preview-content')).toHaveCount(1);
  const commonWidth = await tile(page, 'α').evaluate(el => el.getBoundingClientRect().width);
  expect(Math.abs(greekWidth - commonWidth)).toBeLessThan(1);
  const firstRow = await page.locator('#symbolGrid .symbol-tile').evaluateAll(buttons => {
    const top = buttons[0].getBoundingClientRect().top;
    return buttons.filter(button => Math.abs(button.getBoundingClientRect().top - top) < 2).length;
  });
  expect(firstRow).toBeGreaterThanOrEqual(3);
  expect(errors).toEqual([]);
});

test('styled size picker offers named and numeric sizes while accepting custom points', async ({page}) => {
  const errors = await open(page, 'x+1');
  await page.locator('#fontSizeToggle').click();
  const menu = page.locator('#fontSizeMenu');
  await expect(menu).toBeVisible();
  await expect(menu.locator('.size-option')).toHaveCount(11);
  await menu.getByRole('option', {name: '四号 14 pt'}).click();
  await expect(page.locator('#fontSizePoints')).toHaveValue('四号');
  await submitted(page);
  expect((await page.evaluate(() => window.posted.findLast(message => message.type === 'accept').typography)).fontSizePoints).toBe(14);
  await page.locator('#fontSizePoints').fill('14.5');
  await submitted(page);
  expect((await page.evaluate(() => window.posted.findLast(message => message.type === 'accept').typography)).fontSizePoints).toBe(14.5);
  await page.locator('#fontSizePoints').press('ArrowDown');
  await expect(menu).toBeVisible();
  await page.locator('#fontSizePoints').press('Escape');
  await expect(menu).toBeHidden();
  expect(errors).toEqual([]);
});

test('desktop editor keeps the full symbol catalog in a left sidebar', async ({page}) => {
  await page.emulateMedia({colorScheme: 'dark'});
  await page.setViewportSize({width: 1164, height: 805});
  const errors = await open(page, 'd(p,q)=\\|p-q\\|');
  await page.locator('[data-group="geometry"]').click();
  const library = await page.locator('#symbolLibrary').boundingBox();
  const workspaceBox = await page.locator('.workspace').boundingBox();
  const grid = page.locator('#symbolGrid');
  expect(library.x + library.width).toBeLessThan(workspaceBox.x);
  expect(library.height).toBeGreaterThan(600);
  expect(await grid.locator('button').count()).toBeGreaterThan(100);
  expect(await grid.evaluate(el => el.scrollWidth - el.clientWidth)).toBeLessThanOrEqual(1);
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-redesign-dark.png')});
  await page.locator('#typographyToggle').click();
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-redesign-fonts.png')});
  await page.locator('#fontSizeToggle').click();
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-redesign-sizes.png')});
  expect(errors).toEqual([]);
});

test('invalid sizes, stale results, composition and new sessions cannot show an old preview', async ({page}) => {
  await open(page);
  await page.locator('#previewToggle').click();
  await expect.poll(() => latestPreview(page)).toBeTruthy();
  const old = await latestPreview(page);
  await source(page).fill('y+2');
  await deliverPreview(page, old);
  await expect(page.locator('#previewImage')).toBeHidden();
  await expect.poll(async () => (await latestPreview(page)).latex).toBe('y+2');
  const current = await latestPreview(page);
  await deliverPreview(page, current);
  await expect(page.locator('#previewImage')).toBeVisible();
  await page.locator('#fontSizePoints').fill('1e2');
  await page.locator('#acceptButton').click();
  await expect(page.locator('#fontSizePoints')).toHaveAttribute('aria-invalid', 'true');
  expect(await page.evaluate(() => window.posted.some(message => message.type === 'accept'))).toBe(false);
  await deliverPreview(page, current);
  await expect(page.locator('#previewImage')).toBeHidden();
  await page.locator('#fontSizePoints').fill('14.5');
  await source(page).dispatchEvent('compositionstart');
  await deliverPreview(page, current);
  await expect(page.locator('#previewImage')).toBeHidden();
  await source(page).dispatchEvent('compositionend');
  await page.evaluate(() => window.LaTeXSnipperEditor.init({...window.editorInit, session: 2, display: false, referencePreview: true}));
  await deliverPreview(page, current);
  await expect(page.locator('#finalPreview')).toBeHidden();
  await expect(page.locator('#fontSizePoints')).toHaveValue('12');
  await page.locator('#previewToggle').click();
  await expect(page.locator('#previewNote')).toContainText('Word');
  await expect.poll(async () => (await latestPreview(page)).session).toBe(2);
  const fresh = await latestPreview(page);
  expect(fresh.display).toBe(false);
  await deliverPreview(page, fresh, {error: 'Render failed'});
  await expect(page.locator('#previewStatus')).toHaveText('Render failed');
  await expect(page.locator('#previewImage')).toBeHidden();
  await page.locator('#cancelButton').click();
  expect(await page.evaluate(() => window.posted.at(-1))).toEqual({type: 'cancel', session: 2});
  await deliverPreview(page, fresh);
  await expect(page.locator('#previewImage')).toBeHidden();
});


test('typography panel and preview remain usable in small light and dark windows', async ({page}) => {
  const errors = await open(page);
  for (const colorScheme of ['light', 'dark']) {
    await page.emulateMedia({colorScheme});
    await page.setViewportSize({width: 640, height: 480});
    await page.locator('#typographyToggle').click();
    const panel = await page.locator('#typographyPanel').boundingBox();
    expect(panel.x).toBeGreaterThanOrEqual(0); expect(panel.x + panel.width).toBeLessThanOrEqual(640);
    await page.locator('#cjkFontFamily').selectOption('SimSun');
    await page.screenshot({path: join(tmpdir(), `latexsnipper-6b-${colorScheme}.png`)});
    await page.locator('#cjkFontFamily').press('Escape');
    await expect(page.locator('#typographyToggle')).toBeFocused();
    await expect(page.locator('#typographyPanel')).toBeHidden();
    await expect(page.locator('#acceptButton')).toBeInViewport();
  }
  expect(errors).toEqual([]);
});


for (const host of ['word', 'powerpoint']) {
  test(`${host}: preview roundtrip preserves visual selection unless source changes`, async ({page}) => {
    const errors = await open(page, 'a+b', host);
    await visual(page).click();
    await visual(page).press('Control+a');
    await page.locator('#previewToggle').click();
    await expect(source(page)).toBeFocused();
    await page.locator('#previewToggle').click();
    await expect(visual(page)).toBeFocused();
    await searchTile(page, 'Fraction');
    await tile(page, '分数').click();
    await expect(source(page)).toHaveText('\\frac{a+b}{\\placeholder{}}');
    await page.locator('#previewToggle').click();
    await source(page).fill('newer');
    await page.locator('#previewToggle').click();
    await expect(source(page)).toBeFocused();
    expect(await submitted(page)).toBe('newer');
    expect(errors).toEqual([]);
  });
}

test('toolbar IME blocks submission and mode changes until committed', async ({page}) => {
  const errors = await open(page);
  await page.locator('[data-group="greek"]').click();
  const size = page.locator('#fontSizePoints');
  await size.focus();
  await size.dispatchEvent('compositionstart');
  await size.fill('小四');
  await page.locator('#undoButton').click();
  await tile(page, 'α').click();
  await expect(source(page)).toHaveText('x+1');
  await page.locator('#acceptButton').click();
  expect(await page.evaluate(() => window.posted.some(m => m.type === 'accept'))).toBe(false);
  await page.locator('#previewToggle').click();
  await expect(page.locator('#finalPreview')).toBeHidden();
  await size.dispatchEvent('compositionend');
  expect(await submitted(page)).toBe('x+1');
  expect(await page.evaluate(() => window.posted.findLast(m => m.type === 'accept').typography.fontSizePoints)).toBe(12);
  expect(errors).toEqual([]);
});

test('Escape then Tab leaves either editor; font panel closes explicitly', async ({page}) => {
  const errors = await open(page);
  await visual(page).click();
  await visual(page).press('Escape');
  await page.keyboard.press('Tab');
  await expect(page.locator('#sourceResizeHandle')).toBeFocused();
  await source(page).click();
  await source(page).press('Escape');
  await page.keyboard.press('Tab');
  await expect(source(page)).not.toBeFocused();
  await page.locator('#typographyToggle').click();
  await page.locator('#defaultMathStyle').focus();
  await page.keyboard.press('Tab');
  await expect(page.locator('#typographyPanel')).toBeVisible();
  await page.locator('#defaultMathStyle').press('Escape');
  await expect(page.locator('#typographyPanel')).toBeHidden();
  expect(await submitted(page)).toBe('x+1');
  expect(errors).toEqual([]);
});

test('short windows retain both panes and sidebar scrolls vertically', async ({page}) => {
  const errors = await open(page);
  await page.setViewportSize({width: 640, height: 400});
  const resize = page.locator('#sourceResizeHandle');
  await resize.press('End');
  const formula = await page.locator('.formula-stage').boundingBox();
  const sourceBox = await page.locator('#latexSource').boundingBox();
  expect(formula.height).toBeGreaterThan(20);
  expect(sourceBox.height).toBeGreaterThan(20);
  await expect(page.locator('#acceptButton')).toBeInViewport();
  await page.locator('[data-group="geometry"]').click();
  const grid = page.locator('#symbolGrid');
  const gridBox = await grid.boundingBox();
  await page.mouse.move(gridBox.x + 80, gridBox.y + 30);
  await page.mouse.wheel(0, 320);
  await expect.poll(() => grid.evaluate(el => el.scrollTop)).toBeGreaterThan(0);
  const native = await grid.evaluate(el => ['horizontal', 'zoom'].map(mode => {
    const event = new WheelEvent('wheel', {deltaX: mode === 'horizontal' ? 100 : 0, deltaY: 10,
      ctrlKey: mode === 'zoom', cancelable: true}); el.dispatchEvent(event); return !event.defaultPrevented;
  }));
  expect(native).toEqual([true, true]);
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-6c-compact.png')});
  expect(errors).toEqual([]);
});


test('keyboard entry into MathLive works while a late focus cannot steal a toolbar field', async ({page}) => {
  const errors = await open(page);
  await page.locator('#libraryToggle').focus();
  await page.keyboard.press('Tab');
  await expect(page.locator('#symbolSearch')).toBeFocused();
  await page.locator('#fontSizePoints').click();
  await page.evaluate(() => HTMLElement.prototype.focus.call(document.querySelector('math-field')));
  await expect(page.locator('#fontSizePoints')).toBeFocused();
  await page.locator('#fontSizePoints').fill('18');
  expect(await submitted(page)).toBe('x+1');
  expect(errors).toEqual([]);
});
