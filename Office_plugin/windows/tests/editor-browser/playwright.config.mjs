import {defineConfig} from '@playwright/test';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
export default defineConfig({testDir: './tests', testMatch: '**/*.spec.mjs', workers: 1, timeout: 30000,
  outputDir: join(tmpdir(), 'latexsnipper-editor-playwright'), reporter: 'list',
  use: {channel: 'msedge', headless: true, viewport: {width: 1180, height: 780}}});
