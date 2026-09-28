import {test, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {resolve, extname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';

const root = fileURLToPath(new URL('../../../', import.meta.url));

async function routeHostAssets(page, host) {
  await page.route('https://*.officeplugin.local/**', async route => {
    const url = new URL(route.request().url());
    const relative = decodeURIComponent(url.pathname.slice(1));
    const directory = url.hostname.includes('editor-shared')
      ? resolve(root, 'office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets')
      : resolve(root, `office_plugin/hosts/${host === 'word' ? 'Word' : 'PowerPoint'}AddIn/EditorAssets`);
    const path = relative.startsWith('vendor/') ? resolve(root, 'src/assets/mathlive', relative)
      : resolve(directory, relative);
    const types = {'.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css',
      '.html': 'text/html', '.woff2': 'font/woff2'};
    await route.fulfill({body: await readFile(path), contentType: types[extname(path)] || 'application/octet-stream'});
  });
}

for (const host of ['word', 'powerpoint']) {
  test(`${host} task pane keeps a colored cases formula visually editable`, async ({page}) => {
    const latex = String.raw`\textcolor{#ff0000}{\mu(n)=\begin{cases}1,&n=1\\
(-1)^k,&n=p_1\cdots p_k\\
0,&p^2\mid n\end{cases}}`;
    await routeHostAssets(page, host);
    await page.goto(`https://latexsnipper-${host}.officeplugin.local/taskpane.html`);
    const field = page.locator('#previewHost math-field');
    await expect(page.locator('#latexSource .cm-content')).toHaveText('e^{i\\pi}+1=0');
    await page.evaluate(() => window.LaTeXSnipperTaskPane.apply({type: 'state', latex: '\\begin{cases}'}));
    await page.evaluate(latex => window.LaTeXSnipperTaskPane.apply({type: 'state', latex, locale: 'zh'}), latex);
    await expect(page.locator('#latexSource .cm-line')).toHaveCount(3);
    await expect.poll(() => field.evaluate(element => element.readOnly)).toBe(false);
    await expect(page.locator('#sourceModeNote')).toBeHidden();
    await expect.poll(() => field.evaluate(element => getComputedStyle(element).color)).toBe('rgb(255, 0, 0)');
  });

  test(`${host} task pane can explicitly adopt a normalized visual formula`, async ({page}) => {
    await routeHostAssets(page, host);
    await page.goto(`https://latexsnipper-${host}.officeplugin.local/taskpane.html`);
    await page.evaluate(() => window.LaTeXSnipperTaskPane.apply({type: 'state',
      latex: 'x\\displaylines{y=z}', locale: 'zh'}));
    await expect(page.locator('#sourceModeNote')).toContainText('改写');
    await page.locator('#sourceModeNote button').click();
    await expect(page.locator('#sourceModeNote')).toBeHidden();
    await expect.poll(() => page.locator('#previewHost math-field').evaluate(field => field.readOnly)).toBe(false);
  });

  test(`${host} task pane shows the default formula without a host draft`, async ({page}) => {
    await routeHostAssets(page, host);
    await page.goto(`https://latexsnipper-${host}.officeplugin.local/taskpane.html`);
    await expect(page.locator('#latexSource .cm-content')).toHaveText('e^{i\\pi}+1=0');
    await expect.poll(() => page.locator('#previewHost math-field').evaluate(field => field.getValue('latex')))
      .toBe('e^{i\\pi}+1=0');
  });

  test(`${host} task pane shares source and visual editing`, async ({page}) => {
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await routeHostAssets(page, host);
    await page.addInitScript(() => {
      window.posted = [];
      window.chrome = {webview: {postMessage: message => window.posted.push(message)}};
      window.__latexSnipperTaskPanePending = [{type: 'state', latex: 'x+1', locale: 'zh',
        display: false, autoNumber: false, manualNumber: '', strings: {insert: '插入'}}];
    });
    await page.goto(`https://latexsnipper-${host}.officeplugin.local/taskpane.html`);
    const source = page.locator('#latexSource .cm-content');
    const visual = page.locator('#previewHost math-field');
    await expect(source).toHaveText('x+1');
    await page.setViewportSize({width: 380, height: 700});
    await page.screenshot({path: join(tmpdir(), `latexsnipper-${host}-taskpane.png`), fullPage: true});
    await source.fill('x+2');
    await expect.poll(() => visual.evaluate(field => field.getValue('latex'))).toBe('x+2');
    await visual.click();
    await page.keyboard.type('3');
    await expect.poll(() => source.innerText()).toContain('3');
    await source.fill('\\begin{align}x&=1\\end{align}');
    await expect.poll(() => visual.evaluate(field => field.readOnly)).toBe(false);
    await page.locator('#insertButton').click();
    expect(await page.evaluate(() => window.posted.findLast(message => message.type === 'insert')?.latex))
      .toBe('\\begin{align}x&=1\\end{align}');
    if (host === 'word') {
      await page.locator('#autoNumber').check();
      expect(await page.evaluate(() => window.posted.findLast(message => message.type === 'state')))
        .toMatchObject({autoNumber: true, display: true});
    }
    expect(errors).toEqual([]);
  });
}
