import {test, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {resolve, extname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';

const root = fileURLToPath(new URL('../../../', import.meta.url));
const shared = resolve(root, 'office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets');
const source = page => page.locator('#latexSource .cm-content');
async function open(page, latex = 'x+1', host = 'word') {
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
  await page.addInitScript(latex => {
    window.__latexSnipperPendingInit = {latex, locale: 'zh', mode: 'update'};
    window.posted = [];
    window.chrome = {webview: {postMessage: message => window.posted.push(message)}};
  }, latex);
  await page.goto(`https://latexsnipper-${host}.officeplugin.local/editor.html`);
  await expect(page).toHaveTitle('LaTeXSnipper');
  await expect(source(page)).toBeVisible();
  await expect(page.locator('#acceptButton')).toHaveText('更新');
  return errors;
}
async function submitted(page) {
  await page.locator('#acceptButton').click();
  return page.evaluate(() => window.posted.at(-1)?.latex);
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

test('source history includes visual edits; unfocused notifications cannot replace newer source', async ({page}) => {
  const errors = await open(page);
  await page.locator('#mathfieldHost math-field').click();
  await page.locator('#mathfieldHost math-field').press('End');
  await page.keyboard.type('2');
  await expect.poll(() => source(page).innerText()).toContain('2');
  await page.locator('#mathfieldHost math-field').press('Control+z');
  expect(await submitted(page)).toBe('x+1');
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
  expect(await page.evaluate(() => window.posted.length)).toBe(0);
  await source(page).dispatchEvent('compositionend');
  await expect.poll(() => page.locator('#mathfieldHost math-field').evaluate(el => el.getValue('latex'))).toContain('中文');
  expect(await submitted(page)).toBe('\\text{中文}');
});

test('PPT uses the same editor with diagnostics, search and dark theme', async ({page}) => {
  await page.emulateMedia({colorScheme: 'dark'});
  await page.setViewportSize({width: 980, height: 680});
  const errors = await open(page, '\\frac{a}{b', 'powerpoint');
  await expect(page.locator('.cm-lintRange-error')).not.toHaveCount(0);
  await source(page).press('Control+f');
  await expect(page.locator('.cm-search')).toBeVisible();
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-dark.png')});
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

test('find/replace, source symbol insertion, session reset and submission locking', async ({page}) => {
  const errors = await open(page, 'x+x');
  await source(page).press('Control+f');
  await page.locator('.cm-search input[name="search"]').fill('x');
  await page.locator('.cm-search input[name="replace"]').fill('y');
  await page.locator('.cm-search button[name="replaceAll"]').click();
  expect(await submitted(page)).toBe('y+y');
  await source(page).press('Escape');
  await source(page).press('End');
  await page.locator('#symbolGrid button').filter({hasText: /^α$/}).click();
  expect(await submitted(page)).toBe('y+y\\alpha');
  await page.evaluate(() => window.LaTeXSnipperEditor.init({latex: 'new', locale: 'zh'}));
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
    await page.evaluate(() => window.LaTeXSnipperEditor.init({latex: '', locale: 'zh'}));
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
    await page.evaluate(() => window.LaTeXSnipperEditor.init({latex: 'z', locale: 'zh'}));
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

test('keyboard search, independent horizontal scrolling, lazy previews and compact layout', async ({page}) => {
  const errors = await open(page, 'x');
  await source(page).press('End');
  await page.locator('[data-group="structures"]').click();
  const grid = page.locator('#symbolGrid');
  await expect.poll(() => grid.locator('.tile-preview').count()).toBeGreaterThan(0);
  expect(await grid.locator('.tile-preview').count()).toBeLessThan(await grid.locator('button').count());
  const gridBox = await grid.boundingBox();
  await page.mouse.move(gridBox.x + 50, gridBox.y + 20);
  await page.mouse.wheel(0, 350);
  await expect.poll(() => grid.evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
  const scrolled = await grid.evaluate(el => el.scrollLeft);
  const sourceBox = await source(page).boundingBox();
  await page.mouse.move(sourceBox.x + 30, sourceBox.y + 10);
  await page.mouse.wheel(0, 200);
  expect(await grid.evaluate(el => el.scrollLeft)).toBe(scrolled);
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
  await expect.poll(() => tile(page, '分数').locator('.tile-preview').count()).toBe(1);
  const cached = await tile(page, '分数').locator('.tile-preview').elementHandle();
  await page.locator('[data-group="greek"]').click();
  await page.locator('[data-group="structures"]').click();
  await expect.poll(() => tile(page, '分数').locator('.tile-preview').count()).toBe(1);
  expect(await tile(page, '分数').locator('.tile-preview').evaluate((element, previous) => element === previous, cached)).toBe(true);
  await tile(page, '分数').focus();
  await page.keyboard.press('ArrowRight');
  await expect(tile(page, '下标')).toBeFocused();
  await page.keyboard.press('ArrowLeft');
  await expect(tile(page, '分数')).toBeFocused();
  const resize = page.locator('#sourceResizeHandle');
  const before = Number(await resize.getAttribute('aria-valuenow'));
  await resize.press('ArrowUp');
  expect(Number(await resize.getAttribute('aria-valuenow'))).toBeGreaterThan(before);
  await page.locator('#libraryNext').click();
  await expect.poll(() => page.locator('#symbolGrid').evaluate(el => el.scrollLeft)).toBeGreaterThan(0);
  await page.locator('#libraryPrevious').click();
  await expect.poll(() => page.locator('#symbolGrid').evaluate(el => el.scrollLeft)).toBe(0);
  await page.screenshot({path: join(tmpdir(), 'latexsnipper-editor-6a-structures.png')});
  await page.evaluate(() => window.LaTeXSnipperEditor.init({latex: 'x', locale: 'en'}));
  await searchTile(page, '分数');
  await expect(tile(page, 'Fraction')).toBeVisible();
  await page.locator('#symbolSearch').press('Escape');
  await expect(source(page)).toBeFocused();
  expect(errors).toEqual([]);
});
