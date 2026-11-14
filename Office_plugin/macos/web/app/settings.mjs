// Settings dialog. Field handling and texts follow the Windows settings.js;
// every change is saved at once, like on Windows. Values are stored by the
// add-in host in the cross-platform settings.json schema.
/* global Office */
import {populateTypographyOptions} from '/shared/settings-typography.mjs';
import {api, catalog, loadSettings} from './api.mjs';
import {isChinese} from './strings.mjs';

const params = new URLSearchParams(location.search);
const host = params.get('host') === 'powerpoint' ? 'powerpoint' : 'word';
const locale = String(params.get('locale') || navigator.language || 'zh').toLowerCase();
const zh = isChinese(locale);
const hostName = host === 'word' ? 'Word' : 'PowerPoint';

const TEXT = {
  zh: {
    title: `LaTeXSnipper ${hostName} 插件设置`,
    backendTitle: '公式插入方式',
    backendHint: '默认插入 PNG 图片，也可切换为 SVG 图片。',
    backendPng: 'PNG 图片', backendSvg: 'SVG 图片',
    numberingTitle: '带编号公式默认布局', numberRight: '右编号', numberLeft: '左编号',
    numberingHint: '此设置只影响新插入的编号公式，以及之后被自动编号的普通公式。',
    enclosureLabel: '外框', enclosureNone: '无', includeChapter: '包含章编号', includeSection: '包含节编号',
    hideChapterBoundary: '隐藏章分隔符', hideSectionBoundary: '隐藏节分隔符', separatorLabel: '层级分隔符',
    formulaDefaultsTitle: '公式默认属性',
    formulaDefaultsHint: '这些设置应用于新插入公式和格式化命令。',
    colorLabel: '字体颜色', resetColor: '恢复黑色', fontStyleLabel: '默认字形', fontSizeLabel: '公式字号',
    symbolFontLabel: '符号字体', numberFontLabel: '数字字体', cjkFontLabel: '汉字字体',
    presetTitle: '全局公式预设',
    presetHint: '导入会替换当前宿主的公式默认属性；导出时用 JSON 文件名命名预设。编辑器内调整只作用于当前公式。',
    importPreset: '导入 JSON', exportPreset: '导出 JSON', importedPreset: '已导入：', exportedPreset: '已导出：',
    followHostSize: '新建时跟随文字字号（无有效选区时使用上述字号）',
    editorTitle: '编辑器键盘行为', acceptShortcut: '插入或更新当前公式', fractionShortcut: '插入分式',
    rootShortcut: '插入根号', superscriptShortcut: '插入上标', subscriptShortcut: '插入下标', scriptsShortcut: '插入上下标',
  },
  en: {
    title: `LaTeXSnipper ${hostName} Plugin Settings`,
    backendTitle: 'Formula Insertion',
    backendHint: 'PNG images are the default. SVG image insertion is also available.',
    backendPng: 'PNG Image', backendSvg: 'SVG Image',
    numberingTitle: 'Default Numbered Formula Layout', numberRight: 'Number on the right', numberLeft: 'Number on the left',
    numberingHint: 'This setting applies to newly inserted numbered formulas and ordinary formulas numbered later.',
    enclosureLabel: 'Enclosure', enclosureNone: 'None', includeChapter: 'Include chapter number',
    includeSection: 'Include section number', hideChapterBoundary: 'Hide chapter boundaries',
    hideSectionBoundary: 'Hide section boundaries', separatorLabel: 'Level separator',
    formulaDefaultsTitle: 'Default Formula Properties',
    formulaDefaultsHint: 'These settings apply to new formulas and formatting commands.',
    colorLabel: 'Font color', resetColor: 'Reset to black', fontStyleLabel: 'Default math style', fontSizeLabel: 'Formula size',
    symbolFontLabel: 'Symbol font', numberFontLabel: 'Number font', cjkFontLabel: 'CJK font',
    presetTitle: 'Global formula preset',
    presetHint: "Import replaces this host's formula defaults. The JSON filename names the preset. Editor changes apply to the current formula.",
    importPreset: 'Import JSON', exportPreset: 'Export JSON', importedPreset: 'Imported: ', exportedPreset: 'Exported: ',
    followHostSize: 'Follow text size for new formulas (use the size above when unavailable)',
    editorTitle: 'Editor Keyboard Behavior', acceptShortcut: 'insert or update the current formula',
    fractionShortcut: 'insert a fraction', rootShortcut: 'insert a square root', superscriptShortcut: 'insert a superscript',
    subscriptShortcut: 'insert a subscript', scriptsShortcut: 'insert superscript and subscript',
  },
};
const strings = zh ? TEXT.zh : TEXT.en;

const element = id => document.getElementById(id);
const typographyInputs = ['formulaColor', 'formulaMathStyle', 'formulaFontSizePoints', 'symbolFontId',
  'numberFontFamily', 'cjkFontFamily'];
const numberingSelects = ['numberEnclosure', 'numberSeparator'];
const numberingFlags = ['includeChapter', 'includeSection', 'hideChapterBoundary', 'hideSectionBoundary'];
const backendButtons = [...document.querySelectorAll('[data-backend]')];
const placementButtons = [...document.querySelectorAll('[data-placement]')];
const presetStatus = element('presetStatus');
let state = null;

function applyText() {
  document.title = strings.title;
  document.documentElement.lang = zh ? 'zh-CN' : 'en';
  for (const node of document.querySelectorAll('[data-i18n]')) node.textContent = strings[node.dataset.i18n] ?? node.textContent;
  element('backendPanel').hidden = host !== 'powerpoint';
  element('numberingPanel').hidden = host !== 'word';
}

function render() {
  for (const button of backendButtons) button.classList.toggle('active', button.dataset.backend === state.insertionBackend);
  for (const button of placementButtons) button.classList.toggle('active', button.dataset.placement === state.numberPlacement);
  element('formulaColor').value = state.formulaColor.toLowerCase();
  for (const name of typographyInputs.slice(1)) element(name).value = String(state[name]);
  element('followHostFontSize').checked = state.followHostFontSize;
  if (host !== 'word') return;
  for (const name of numberingSelects) element(name).value = state[name];
  for (const name of numberingFlags) element(name).checked = state[name];
}

function showStatus(message, error = false) {
  presetStatus.textContent = message;
  presetStatus.classList.toggle('error', error);
}

async function populate(settings) {
  const options = await catalog();
  state = settings;
  populateTypographyOptions({...options, namedSizes: Object.entries(options.namedSizes)
    .map(([name, points]) => ({name, points}))}, {
    symbolFontId: settings.symbolFontId,
    numberFontFamily: settings.numberFontFamily,
    cjkFontFamily: settings.cjkFontFamily,
    formulaFontSizePoints: settings.formulaFontSizePoints,
  }, locale);
  render();
}

async function save() {
  try {
    state = await api(`/api/settings/${host}`, {method: 'PUT', body: state});
    render();
    try { Office.context.ui.messageParent(JSON.stringify({type: 'settingsSaved'})); } catch { /* opened outside Office */ }
  } catch (error) {
    showStatus(error.message, true);
    state = await loadSettings(host);
    render();
  }
}

function bind() {
  const change = (name, read) => { state[name] = read(); save(); };
  for (const button of backendButtons)
    button.addEventListener('click', () => { state.insertionBackend = button.dataset.backend; render(); save(); });
  for (const button of placementButtons)
    button.addEventListener('click', () => { state.numberPlacement = button.dataset.placement; render(); save(); });
  for (const name of numberingSelects) element(name).addEventListener('change', () => change(name, () => element(name).value));
  for (const name of numberingFlags) element(name).addEventListener('change', () => change(name, () => element(name).checked));
  element('formulaColor').addEventListener('change', () => change('formulaColor', () => element('formulaColor').value.toUpperCase()));
  element('resetFormulaColor').addEventListener('click', () => { state.formulaColor = '#000000'; render(); save(); });
  element('formulaMathStyle').addEventListener('change', () => change('formulaMathStyle', () => element('formulaMathStyle').value));
  element('formulaFontSizePoints').addEventListener('change', () =>
    change('formulaFontSizePoints', () => Number(element('formulaFontSizePoints').value)));
  for (const name of ['symbolFontId', 'numberFontFamily', 'cjkFontFamily'])
    element(name).addEventListener('change', () => change(name, () => element(name).value));
  element('followHostFontSize').addEventListener('change', () =>
    change('followHostFontSize', () => element('followHostFontSize').checked));
  for (const [id, kind] of [['importTypography', 'import'], ['exportTypography', 'export']]) {
    element(id).addEventListener('click', async () => {
      try {
        const result = await api(`/api/settings/${host}/${kind}`, {method: 'POST', body: {}});
        if (result.canceled) return;
        if (result.settings) await populate(result.settings);
        showStatus(`${strings[kind === 'import' ? 'importedPreset' : 'exportedPreset']}${result.name || ''}`);
      } catch (error) {
        showStatus(error.message, true);
      }
    });
  }
}

applyText();
bind();
Office.onReady().then(() => loadSettings(host)).then(populate).catch(error => showStatus(error.message, true));
