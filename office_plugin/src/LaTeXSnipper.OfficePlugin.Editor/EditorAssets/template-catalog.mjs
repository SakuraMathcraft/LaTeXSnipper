import {GROUPS, STRINGS} from './symbol-library.mjs';
import {matrixTemplate} from './matrix-templates.mjs';

export {STRINGS};

// These are references into the catalog, never another copy of a template.
const shortcuts = new Map([
  ['Fraction', 'f'], ['Square root', 'r'], ['Superscript', 'h'],
  ['Subscript', 'l'], ['Subscript and superscript', 'j']
]);
const byTemplate = new Map();
for (const group of GROUPS) {
  let section = '';
  for (const item of group.items) {
    if (item.section) { section = `${item.section} ${item.sectionEn || ''}`; continue; }
    const [zh, rawTemplate, en = zh, nameZh = zh] = item;
    const template = /#[@0]/.test(rawTemplate) ? rawTemplate.replace(/#@/g, '#0') : rawTemplate.replace('#?', '#0');
    let entry = byTemplate.get(template);
    if (!entry) {
      entry = {id: `symbol-${byTemplate.size}`, zh, en, nameZh, template, groups: [], aliases: [],
        matrix: template.startsWith('matrix:') ? template.slice(7) : null,
        shortcut: shortcuts.get(en) || null};
      byTemplate.set(template, entry);
    }
    entry.groups.push(group.id);
    entry.aliases.push(zh, en, nameZh, section);
  }
}
export const CATALOG = [...byTemplate.values()];
for (const entry of CATALOG) {
  if (entry.matrix) entry.groups.push('matrices');
  if (entry.shortcut || entry.template === '\\alpha' || entry.template === '\\pi'
      || entry.template === '\\leq' || entry.template === '\\infty' || entry.matrix === 'bmatrix') entry.groups.push('common');
  entry.search = [...entry.aliases, entry.template, entry.matrix ? matrixTemplate(entry.matrix) : ''].join(' ').toLowerCase();
  entry.wide = Boolean(entry.matrix || /#[0-9?@]/.test(entry.template) || entry.zh.length > 3);
}

export const CATEGORIES = [
  {id: 'common', zh: '常用', en: 'Common'},
  ...GROUPS.map(group => ({id: group.id, zh: STRINGS.zh.tabs[group.id], en: STRINGS.en.tabs[group.id]})),
  {id: 'matrices', zh: '矩阵', en: 'Matrices'}
];
export function findEntries(category, query = '') {
  const terms = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return CATALOG.filter(entry => terms.length ? terms.every(term => entry.search.includes(term)) : entry.groups.includes(category));
}
export function entryTemplate(entry, rows = 2, columns = 2) {
  return entry.matrix ? matrixTemplate(entry.matrix, rows, columns) : entry.template;
}

// #0 / #@ explicitly take the selection. Otherwise the first hole takes it.
// Return literal and hole tokens so adapters never reinterpret user source as a template.
export function templateParts(template, selected = '') {
  const tokens = template.split(/(#[0-9?@])/g);
  const explicit = tokens.findIndex(token => token === '#0' || token === '#@');
  const selectionIndex = explicit < 0 ? tokens.findIndex(token => /^#[0-9?@]$/.test(token)) : explicit;
  return tokens.map((text, index) => /^#[0-9?@]$/.test(text)
    ? (selected && index === selectionIndex ? {text: selected} : {hole: true}) : {text});
}

export const COMMANDS = [...new Set(CATALOG.flatMap(entry =>
  entryTemplate(entry).match(/\\[a-zA-Z]+/g) || []))].map(label => ({
    label,
    // Prefer a structural template beginning with the exact command.
    entry: CATALOG.find(entry => !entry.matrix && entry.template.startsWith(label)
      && !/[a-zA-Z]/.test(entry.template[label.length] || '') && /#[0-9?@]/.test(entry.template))
  }));
