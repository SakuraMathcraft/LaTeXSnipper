// Structural checks only: rendering remains responsible for TeX command semantics.
export function inspectLatex(source) {
  const stack = [], diagnostics = [];
  const tokens = /%[^\n]*|\\verb\*?([^\w\s]).*?\1|\\(?:begin|end)\s*\{([^{}]+)\}|\\[a-zA-Z]+\*?|\\[^\r\n]|[{}]/g;
  for (const match of source.matchAll(tokens)) {
    const token = match[0], from = match.index, to = from + token.length;
    if (token.startsWith('%') || token.startsWith('\\verb')) continue;
    if (token === '{' || token.startsWith('\\begin')) {
      stack.push({from, to, name: token === '{' ? '}' : match[2]});
    } else if (token === '}' || token.startsWith('\\end')) {
      const expected = token === '}' ? '}' : match[2];
      if (stack.at(-1)?.name === expected) stack.pop();
      else diagnostics.push({from, to, severity: 'error', message: `不匹配的结束标记 / Unmatched closing: ${token}`});
    }
  }
  for (const open of stack) diagnostics.push({...open, severity: 'error', message: `缺少结束标记 / Missing closing: ${open.name}`});
  return diagnostics;
}

// Ignore layout whitespace, but never whitespace inside text commands or comments.
export function comparableLatex(source) {
  const result = [];
  let depth = 0, textDepth = -1, awaitingText = false;
  for (const token of source.match(/\\[a-zA-Z]+\*?|\\[^\r\n]|\s+|./gs) || []) {
    if (token === '%') return null;
    if (/^\\(?:text\w*|operatorname\*?)$/.test(token)) awaitingText = true;
    if (token === '{') { depth++; if (awaitingText) { if (textDepth < 0) textDepth = depth; awaitingText = false; } }
    if (!/^\s+$/.test(token) || textDepth >= 0) result.push(token);
    if (token === '}') { if (depth === textDepth) textDepth = -1; depth--; }
  }
  return JSON.stringify(result);
}

export function isMathMl(source) { return /^\s*(?:<\?xml[^>]*>\s*)?<math(?:\s|>|:)/i.test(source); }
