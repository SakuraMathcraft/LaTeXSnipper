import {test, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {resolve, extname, join} from 'node:path';
import {fileURLToPath} from 'node:url';
import {tmpdir} from 'node:os';

const root = fileURLToPath(new URL('../../../', import.meta.url));

for (const host of ['Word', 'PowerPoint']) {
  test(`${host} settings show named point sizes and aligned follow-size checkbox`, async ({page}) => {
    await page.emulateMedia({colorScheme: 'dark'});
    await page.setViewportSize({width: 744, height: 632});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://*.officeplugin.local/**', async route => {
      const url = new URL(route.request().url());
      const directory = url.hostname.includes('editor-shared')
        ? 'office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets'
        : `office_plugin/hosts/${host}AddIn/EditorAssets`;
      const path = resolve(root, directory, decodeURIComponent(url.pathname.slice(1)));
      const types = {'.js': 'text/javascript', '.mjs': 'text/javascript', '.css': 'text/css', '.html': 'text/html'};
      await route.fulfill({body: await readFile(path), contentType: types[extname(path)]});
    });
    await page.addInitScript(() => {
      window.posted = [];
      window.chrome = {webview: {postMessage: message => window.posted.push(message)}};
      window.__latexSnipperSettingsInit = {
        locale: 'zh', formulaFontSizePoints: 12,
        symbolFontId: 'mathjax-tex', numberFontFamily: '', cjkFontFamily: 'Microsoft YaHei',
        symbolFonts: ['mathjax-tex', 'mathjax-stix2'], systemFonts: ['Microsoft YaHei', 'SimSun', 'Arial'],
        cjkFonts: [{id: 'Microsoft YaHei', label: '微软雅黑'}, {id: 'SimSun', label: '宋体'}], mathStyles: [
          {id: 'Automatic', zh: '自动数学样式', en: 'Automatic'},
          {id: 'Upright', zh: '正体', en: 'Upright'},
          {id: 'BoldFraktur', zh: '哥特粗体', en: 'Bold Fraktur'}],
        namedSizes: [{name: '小四', points: 12}, {name: '五号', points: 10.5}],
        commonPointSizes: [10.5, 12, 13]
      };
    });
    await page.goto(`https://latexsnipper-${host.toLowerCase()}.officeplugin.local/settings.html`);
    const backend = page.locator('[data-backend]').first().locator('..');
    const slider = () => backend.evaluate(el => {
      const style = getComputedStyle(el, '::before');
      return {transform: style.transform, duration: style.transitionDuration};
    });
    expect((await slider()).duration).toBe('0.18s');
    await page.locator('[data-backend]').nth(1).click();
    await expect.poll(async () => (await slider()).transform).not.toBe('none');
    expect(await page.evaluate(() => window.posted.at(-1).insertionBackend)).toBe(host === 'Word' ? 'WordOmml' : 'PowerPointPng');
    await page.emulateMedia({reducedMotion: 'reduce'});
    expect((await slider()).duration).toBe('0s');
    expect(await page.locator('html').evaluate(el => getComputedStyle(el).colorScheme)).toBe('light');
    await expect(page.locator('#formulaColor')).toHaveValue('#000000');
    await expect(page.locator('#formulaMathStyle')).toHaveValue('Automatic');
    await expect(page.locator('#formulaMathStyle option:checked')).toHaveText('自动数学样式');
    await expect(page.locator('#formulaMathStyle option[value="BoldFraktur"]')).toHaveText('哥特粗体');
    const size = page.locator('#formulaFontSizePoints');
    await expect(size).toHaveJSProperty('tagName', 'SELECT');
    await expect(size).toHaveValue('12');
    await expect(size.locator('option:checked')).toHaveText('小四');
    await size.selectOption({label: '五号'});
    expect(await page.evaluate(() => window.posted.at(-1).formulaFontSizePoints)).toBe(10.5);
    const checkbox = page.locator('#followHostFontSize');
    const label = page.locator('.follow-host-option [data-i18n="followHostSize"]');
    const inputBox = await checkbox.boundingBox();
    const textBox = await label.boundingBox();
    expect(inputBox.x + inputBox.width).toBeLessThan(textBox.x);
    expect(Math.abs(inputBox.y + inputBox.height / 2 - (textBox.y + textBox.height / 2))).toBeLessThan(5);
    await checkbox.check();
    expect(await page.evaluate(() => window.posted.at(-1).followHostFontSize)).toBe(true);
    await page.locator('#symbolFontId').selectOption('mathjax-stix2');
    await page.locator('#numberFontFamily').selectOption('Arial');
    await page.locator('#cjkFontFamily').selectOption('SimSun');
    expect(await page.locator('#cjkFontFamily option').allTextContents()).not.toContain('Arial');
    await expect(page.locator('#cjkFontFamily option').first()).toHaveAttribute('value', 'Microsoft YaHei');
    await expect(page.locator('#cjkFontFamily')).toHaveValue('SimSun');
    await expect(page.locator('#cjkFontFamily option:checked')).toHaveText('宋体');
    expect(await page.evaluate(() => window.posted.at(-1))).toMatchObject({
      symbolFontId: 'mathjax-stix2', numberFontFamily: 'Arial', cjkFontFamily: 'SimSun'});
    await page.locator('#importTypography').click();
    expect(await page.evaluate(() => window.posted.at(-1).type)).toBe('importTypography');
    await page.locator('#exportTypography').click();
    expect(await page.evaluate(() => window.posted.at(-1).type)).toBe('exportTypography');
    await page.evaluate(() => window.LaTeXSnipperSettings.presetResult({kind: 'import', name: '论文公式'}));
    await expect(page.locator('#presetStatus')).toContainText('论文公式');
    await page.screenshot({path: join(tmpdir(), `latexsnipper-${host.toLowerCase()}-settings.png`), fullPage: true});
    expect(errors).toEqual([]);
  });

  test(`${host} sidebar and status pane stay light under a dark OS theme`, async ({page}) => {
    await page.emulateMedia({colorScheme: 'dark'});
    await page.route('https://*.officeplugin.local/**', async route => {
      const url = new URL(route.request().url());
      const name = decodeURIComponent(url.pathname.slice(1));
      if (name === 'taskpane.js') {
        await route.fulfill({body: '', contentType: 'text/javascript'});
        return;
      }
      const path = url.hostname.includes('editor-shared')
        ? resolve(root, 'office_plugin/src/LaTeXSnipper.OfficePlugin.Editor/EditorAssets', name)
        : resolve(root, `office_plugin/hosts/${host}AddIn/EditorAssets`, name);
      await route.fulfill({body: await readFile(path), contentType: name.endsWith('.css') ? 'text/css' : 'text/html'});
    });
    await page.goto(`https://latexsnipper-${host.toLowerCase()}.officeplugin.local/taskpane.html`);
    expect(await page.locator('html').evaluate(el => getComputedStyle(el).colorScheme)).toBe('light');
    expect(await page.locator('body').evaluate(el => getComputedStyle(el).backgroundColor)).toBe('rgb(247, 248, 251)');
    expect(await page.locator('#statusBanner').evaluate(el => getComputedStyle(el).color)).not.toBe('rgb(243, 247, 251)');
  });
}
