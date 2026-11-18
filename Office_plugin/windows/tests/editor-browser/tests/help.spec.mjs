import {test, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {extname} from 'node:path';
import {fileURLToPath} from 'node:url';

for (const host of ['Word', 'PowerPoint']) {
  const platform = host.toLowerCase();
  test(host + ' help follows the current task and settings flow in both languages', async ({page}) => {
    await page.setViewportSize({width: 744, height: 632});
    const html = await readFile(fileURLToPath(new URL(
      '../../../hosts/' + host + 'AddIn/EditorAssets/help.html', import.meta.url)));
    await page.route('https://*.officeplugin.local/help.html*', route =>
      route.fulfill({body: html, contentType: 'text/html'}));
    await page.route('https://*.officeplugin.local/support/**', async route => {
      const name = decodeURIComponent(new URL(route.request().url()).pathname.slice(1));
      const file = fileURLToPath(new URL(
        '../../../hosts/' + host + 'AddIn/EditorAssets/' + name, import.meta.url));
      const contentType = extname(file) === '.png' ? 'image/png' : 'image/jpeg';
      await route.fulfill({body: await readFile(file), contentType});
    });
    await page.goto('https://latexsnipper-' + platform + '.officeplugin.local/help.html?platform=' + platform + '&locale=zh-CN');
    await expect(page.locator('.lang-zh #zh-start')).toBeVisible();
    await expect(page.locator('.lang-zh #zh-settings')).toContainText('默认字形');
    const chinese = page.locator('.lang-zh section.platform-' + platform);
    await expect(chinese).toBeVisible();
    await expect(chinese).toContainText('生成可编辑的 LaTeX');
    if (host === 'Word') {
      await expect(chinese).toContainText('双击任意原生 MathType 公式');
      await expect(chinese).toContainText('手动或自动编号、编号位置和已有交叉引用');
    } else {
      await expect(chinese).toContainText('选中原生 MathType 公式并点击“加载所选”');
      await expect(chinese).toContainText('编辑更新保留公式原有的 OLE、PNG 或 MathType 格式');
    }
    await expect(page.locator('.lang-zh #zh-support .support-card')).toHaveCount(3);
    await expect(page.locator('.lang-zh #zh-support img')).toHaveCount(3);
    await page.locator('.lang-zh nav a[href="#zh-settings"]').click();
    await expect(page).toHaveURL(/#zh-settings$/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    await page.goto('https://latexsnipper-' + platform + '.officeplugin.local/help.html?platform=' + platform + '&locale=en-US');
    await expect(page.locator('.lang-en #en-start')).toBeVisible();
    await expect(page.locator('.lang-en #en-settings')).toContainText('Default math style');
    const english = page.locator('.lang-en section.platform-' + platform);
    await expect(english).toBeVisible();
    await expect(english).toContainText('creates editable LaTeX');
    if (host === 'Word') {
      await expect(english).toContainText('double-click any native MathType equation');
      await expect(english).toContainText('manual or automatic numbering, number placement, and existing cross-references');
    } else {
      await expect(english).toContainText('select a native MathType equation and use Load Selected');
      await expect(english).toContainText('Editing preserves the original OLE, PNG, or MathType format');
    }
    await expect(page.locator('.lang-en #en-support .support-card')).toHaveCount(3);
  });
}
