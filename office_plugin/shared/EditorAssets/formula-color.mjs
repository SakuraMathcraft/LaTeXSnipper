const DEFAULT_COLOR = '#000000';

function groupAt(text, opening) {
  if (text[opening] !== '{') return null;
  let depth = 1;
  for (let index = opening + 1; index < text.length; index++) {
    if (text[index] === '\\') { index++; continue; }
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
  return outerColor(latex)?.color || DEFAULT_COLOR;
}

export function hasFormulaContent(latex) {
  return Boolean((outerColor(latex)?.body ?? latex).trim());
}

export function withFormulaColor(latex, color) {
  const current = outerColor(latex);
  const body = current ? removeInheritedColor(current.body, current.color) : latex;
  const normalized = color.toLowerCase();
  return normalized === DEFAULT_COLOR ? body : `\\textcolor{${normalized}}{${body}}`;
}

export function initialFormulaColor(latex, color) {
  return outerColor(latex) ? latex : withFormulaColor(latex, color || DEFAULT_COLOR);
}

export function inheritFormulaColor(latex, color) {
  const current = outerColor(latex);
  const body = current?.color === color ? current.body : latex;
  return `\\textcolor{${color}}{${removeInheritedColor(body, color)}}`;
}
