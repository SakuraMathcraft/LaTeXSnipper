import {test, expect} from '@playwright/test';
import {readFile} from 'node:fs/promises';
import {extname} from 'node:path';
import {fileURLToPath} from 'node:url';

for (const host of ['Word', 'PowerPoint']) {
  const platform = host.toLowerCase();
  test(host + ' help follows the current task and settings flow in both languages', async ({page}) => {
    await page.setViewportSize({width: 744, height: 632});
    const html = await readFile(fileURLToPath(new URL(
      '../../../office_plugin/hosts/' + host + 'AddIn/EditorAssets/help.html', import.meta.url)));
    await page.route('https://*.officeplugin.local/help.html*', route =>
      route.fulfill({body: html, contentType: 'text/html'}));
    await page.route('https://*.officeplugin.local/support/**', async route => {
      const name = decodeURIComponent(new URL(route.request().url()).pathname.slice(1));
      const file = fileURLToPath(new URL(
        '../../../office_plugin/hosts/' + host + 'AddIn/EditorAssets/' + name, import.meta.url));
      const contentType = extname(file) === '.png' ? 'image/png' : 'image/jpeg';
      await route.fulfill({body: await readFile(file), contentType});
    });
    await page.goto('https://latexsnipper-' + platform + '.officeplugin.local/help.html?platform=' + platform + '&locale=zh-CN');
    await expect(page.locator('.lang-zh #zh-start')).toBeVisible();
    await expect(page.locator('.lang-zh #zh-settings')).toContainText('默认字形');
    await expect(page.locator('.lang-zh section.platform-' + platform)).toBeVisible();
    await expect(page.locator('.lang-zh #zh-support .support-card')).toHaveCount(3);
    await expect(page.locator('.lang-zh #zh-support img')).toHaveCount(3);
    await page.locator('.lang-zh nav a[href="#zh-settings"]').click();
    await expect(page).toHaveURL(/#zh-settings$/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);

    await page.goto('https://latexsnipper-' + platform + '.officeplugin.local/help.html?platform=' + platform + '&locale=en-US');
    await expect(page.locator('.lang-en #en-start')).toBeVisible();
    await expect(page.locator('.lang-en #en-settings')).toContainText('Default math style');
    await expect(page.locator('.lang-en section.platform-' + platform)).toBeVisible();
    await expect(page.locator('.lang-en #en-support .support-card')).toHaveCount(3);
  });
}
