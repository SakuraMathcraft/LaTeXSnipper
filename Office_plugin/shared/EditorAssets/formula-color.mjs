import {isMathMl} from './latex-structure.mjs';

const DEFAULT_COLOR = '#000000';

function groupAt(text, opening) {
  if (text[opening] !== '{') return null;
  let depth = 1;
  for (let index = opening + 1; index < text.length; index++) {
    if (text[index] === '%') {
      while (index + 1 < text.length && !/[\r\n]/.test(text[index + 1])) index++;
      continue;
    }
    if (text[index] === '\\') {
      let delimiter = index + 5;
      if (text.startsWith('\\verb', index) && !/[A-Za-z]/.test(text[delimiter] || '')) {
        if (text[delimiter] === '*') delimiter++;
        const end = text.indexOf(text[delimiter], delimiter + 1);
        if (end >= 0) { index = end; continue; }
      }
      index++;
      continue;
    }
    if (text[index] === '{') depth++;
    else if (text[index] === '}' && --depth === 0)
      return {body: text.slice(opening + 1, index), end: index + 1};
  }
  return null;
}

function colorAt(text, start) {
  if (!text.startsWith('\\textcolor{', start)) return null;
  const color = groupAt(text, start + 10);
  const body = color && groupAt(text, color.end);
  return body ? {color: color.body.toLowerCase(), body: body.body, end: body.end} : null;
}

function removeInheritedColor(latex, inherited) {
  let result = '';
  for (let index = 0; index < latex.length;) {
    const command = colorAt(latex, index);
    if (command) {
      const body = removeInheritedColor(command.body, command.color);
      result += command.color === inherited ? body : `\\textcolor{${command.color}}{${body}}`;
      index = command.end;
    } else if (latex[index] === '\\' && index + 1 < latex.length) {
      result += latex.slice(index, index + 2);
      index += 2;
    } else result += latex[index++];
  }
  return result;
}

export function outerColor(latex) {
  const text = latex.trim();
  const command = colorAt(text, 0);
  return command?.end === text.length && /^#[0-9a-f]{6}$/.test(command.color)
    ? {color: command.color, body: command.body} : null;
}

export function formulaColor(latex) {
  if (isMathMl(latex)) {
    const {root, style} = mathMlElements(latex);
    const color = (mathMlColor(style) || mathMlColor(root))?.toLowerCase();
    return /^#[0-9a-f]{6}$/.test(color || '') ? color : DEFAULT_COLOR;
  }
  return outerColor(latex)?.color || DEFAULT_COLOR;
}

function mathMlElements(source) {
  const root = new DOMParser().parseFromString(source.trim(), 'application/xml').documentElement;
  if (root.localName !== 'math') return {};
  const nodes = Array.from(root.children).filter(node => !['annotation', 'annotation-xml'].includes(node.localName));
  return {root, style: nodes.length === 1 && ['mstyle', 'mrow'].includes(nodes[0].localName) ? nodes[0] : null};
}

function mathMlColor(element) {
  return element?.getAttribute('mathcolor') ?? element?.getAttribute('color');
}

export function hasFormulaContent(latex) {
  return Boolean((outerColor(latex)?.body ?? latex).trim());
}

export function withFormulaColor(latex, color) {
  if (isMathMl(latex)) {
    const {root, style} = mathMlElements(latex);
    if (!root || (!mathMlColor(root) && !mathMlColor(style) && color.toLowerCase() === DEFAULT_COLOR)) return latex;
    for (const element of [root, style].filter(Boolean)) {
      element.removeAttribute('mathcolor');
      element.removeAttribute('color');
    }
    if (color.toLowerCase() !== DEFAULT_COLOR) root.setAttribute('mathcolor', color);
    return new XMLSerializer().serializeToString(root);
  }
  const current = outerColor(latex);
  const body = current ? removeInheritedColor(current.body, current.color) : latex;
  const normalized = color.toLowerCase();
  return normalized === DEFAULT_COLOR ? body : `\\textcolor{${normalized}}{${body}}`;
}

export function initialFormulaColor(latex, color) {
  if (isMathMl(latex)) {
    const {root, style} = mathMlElements(latex);
    return mathMlColor(root) || mathMlColor(style) ? latex : withFormulaColor(latex, color || DEFAULT_COLOR);
  }
  return outerColor(latex) ? latex : withFormulaColor(latex, color || DEFAULT_COLOR);
}

export function inheritFormulaColor(latex, color) {
  const current = outerColor(latex);
  const body = current?.color === color ? current.body : latex;
  return `\\textcolor{${color}}{${removeInheritedColor(body, color)}}`;
}
