let bridge = null;
let mathfield = null;
let resultView = null;
let ce = null;
let mathJsonFormatted = '';
let computeHelpers = {};

const latexOutput = document.getElementById('latex-output');
const mathjsonOutput = document.getElementById('mathjson-output');
const resultOutput = document.getElementById('result-output');
const host = document.getElementById('mathfield-host');
const resultRenderHost = document.getElementById('result-render-host');
const VISIBLE_MATH_SPACE = '\\,';
const MULTILINE_TEMPLATE = '\\begin{aligned}#@\\\\#?\\end{aligned}';

const RESERVED_SOLVE_TOKENS = new Set([
  'sin', 'cos', 'tan', 'log', 'ln', 'exp', 'sqrt', 'frac', 'left', 'right',
  'sum', 'prod', 'int', 'lim', 'pi', 'theta', 'alpha', 'beta', 'gamma', 'delta',
  'epsilon', 'phi', 'psi', 'omega', 'sigma', 'lambda', 'mu', 'nu', 'rho', 'tau',
]);

function setThemeMode(mode) {
  document.body.dataset.theme = mode === 'light' ? 'light' : 'dark';
}

function clearRenderedResult() {
  if (resultView) resultView.setValue('', { silenceNotifications: true });
  document.body.classList.add('result-empty');
}

function setRenderedResult(latex, detail = '') {
  const rendered = String(latex ?? '').trim();
  if (resultView) {
    resultView.setValue(rendered, { silenceNotifications: true });
  }
  document.body.classList.toggle('result-empty', !rendered);
  resultOutput.textContent = detail || '';
}

function normalizeComputeError(err, fallback = '计算失败') {
  const message = String(err ?? '').trim();
  if (!message) return fallback;
  if (message.includes('Timeout exceeded')) return '前端计算引擎无法完成当前表达式';
  if (message.includes('Nothing')) return '表达式当前无法得到可用结果';
  if (message.includes('unexpected') || message.includes('parse')) return `公式解析失败：${message}`;
  if (message.includes('undefined')) return `表达式未定义：${message}`;
  return `${fallback}：${message}`;
}

function inferSolveVariable(latex) {
  const tokens = (String(latex || '').match(/[a-zA-Z]+/g) || [])
    .filter((token) => !RESERVED_SOLVE_TOKENS.has(token.toLowerCase()));
  const singleLetter = tokens.find((token) => token.length === 1);
  return singleLetter || tokens[0] || 'x';
}

function currentLatex() {
  return mathfield?.getValue('latex-expanded')?.trim() || '';
}

function unwrapMultilineLatex(latex) {
  const text = String(latex || '').trim();
  if (!text) return '';
  const displaylines = text.match(/^\\displaylines\{([\s\S]*)\}$/);
  if (displaylines) return displaylines[1].trim();
  const env = text.match(/^\\begin\{(multline|align)\}([\s\S]*)\\end\{\1\}$/);
  if (env) return String(env[2] || '').trim();
  return text;
}

function splitIntoMultilineSegments(latex) {
  const text = String(latex || '').trim();
  if (!text) return [];
  const explicit = text
    .split(/\\\\|\r?\n/)
    .map((part) => part.trim())
    .filter(Boolean);
  if (explicit.length > 1) return explicit;

  let segments = text
    .replace(/\s+/g, ' ')
    .split(/(?<==)|(?<=\+)|(?<=-)|(?<=,)|(?<=;)/)
    .map((part) => part.trim())
    .filter(Boolean);

  if (segments.length <= 1) segments = [text];
  return segments;
}

function decorateAlignSegment(segment) {
  const line = String(segment || '').trim();
  if (!line) return '';
  if (line.includes('&')) return line;
  const equalIndex = line.indexOf('=');
  if (equalIndex >= 0) {
    return `${line.slice(0, equalIndex)}&=${line.slice(equalIndex + 1)}`;
  }
  return line;
}

function applyMultilineLayout(kind = 'displaylines') {
  const latex = currentLatex();
  if (!latex) {
    setStatus('请先输入公式，再应用多行排版');
    return;
  }
  const normalizedLatex = unwrapMultilineLatex(latex);
  const lines = splitIntoMultilineSegments(normalizedLatex);
  let wrapped = latex;
  if (kind === 'multline') {
    wrapped = `\\begin{multline}\n${lines.join(' \\\\\n')}\n\\end{multline}`;
  } else if (kind === 'align') {
    wrapped = `\\begin{align}\n${lines.map(decorateAlignSegment).join(' \\\\\n')}\n\\end{align}`;
  } else {
    wrapped = `\\displaylines{${lines.join(' \\\\ ')}}`;
  }
  setLatex(wrapped);
  setStatus(`已应用 ${kind} 多行排版`);
}

  function insertSnippet(kind = '') {
  if (!mathfield) return;
  const map = {
    fraction: '\\frac{#?}{#?}',
    superscript: 'x^{#?}',
    subscript: 'x_{#?}',
    subsuperscript: 'x_{#?}^{#?}',
    sqrt: '\\sqrt{#?}',
    sum: '\\sum_{n=1}^{\\infty} #?',
    product: '\\prod_{n=1}^{\\infty} #?',
    integral: '\\int_{a}^{b} #?\\,dx',
    matrix2: '\\begin{bmatrix}#? & #? \\\\ #? & #?\\end{bmatrix}',
    newline: ' \\\\ ',
  };
  const template = map[String(kind || '').trim()];
  if (!template) {
    setStatus('当前快捷插入模板不可用');
    return;
  }
    try {
      if (kind === 'newline') {
        const latex = currentLatex();
        const inMultiline = /\\begin\{(multline|align)\}|^\\displaylines\{/.test(latex);
        if (!inMultiline) {
          applyMultilineLayout('displaylines');
          mathfield.focus();
          syncOutputs();
          setStatus('已启用 displaylines 多行环境');
          return;
        }
      }
      mathfield.insert(template, { format: 'latex' });
      mathfield.focus();
      syncOutputs();
    setStatus(`已插入${kind === 'newline' ? '换行' : '快捷模板'}`);
  } catch (err) {
    setStatus(`快捷插入失败：${String(err)}`);
  }
}

function currentExpression(actionLabel = '计算') {
  if (!ce || !mathfield) {
    throw new Error('计算引擎尚未就绪');
  }
  const latex = currentLatex();
  if (!latex) {
    throw new Error(`请先输入公式，再执行${actionLabel}`);
  }
  return { latex, expr: ce.parse(latex) };
}

function extractResultLatex(result) {
  if (Array.isArray(result)) {
    return result
      .map((item) => item?.latex ?? String(item))
      .filter(Boolean)
      .join(',\\;');
  }
  return result?.latex ?? String(result ?? '');
}

function isEmptyResult(result) {
  const latex = extractResultLatex(result);
  return !latex || latex === '\\mathrm{Nothing}' || latex === 'Nothing';
}

function syncKeyboardState() {
  const vk = window.mathVirtualKeyboard;
  const visible = !!vk?.visible;
  document.body.classList.toggle('vk-visible', visible);

  const rawHeight =
    vk?.boundingRect?.height ||
    vk?.element?.getBoundingClientRect?.().height ||
    0;
  const height = visible ? Math.max(220, Math.min(rawHeight || 300, 380)) : 0;
  document.documentElement.style.setProperty('--vk-height', `${height}px`);
}

function installClipboardBridge() {
  if (!bridge) return;
  const clipboardApi = {
    async readText() {
      return new Promise((resolve, reject) => {
        try {
          if (typeof bridge.readClipboardText === 'function') {
            bridge.readClipboardText((text) => resolve(String(text ?? '')));
            return;
          }
          reject(new Error('剪贴板读取接口不可用'));
        } catch (err) {
          reject(err);
        }
      });
    },
    async writeText(text) {
      return new Promise((resolve, reject) => {
        try {
          if (typeof bridge.writeClipboardText === 'function') {
            bridge.writeClipboardText(String(text ?? ''), (ok) => {
              if (ok === false) {
                reject(new Error('剪贴板写入失败'));
              } else {
                resolve();
              }
            });
            return;
          }
          reject(new Error('剪贴板写入接口不可用'));
        } catch (err) {
          reject(err);
        }
      });
    },
  };
  try {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: clipboardApi,
    });
  } catch (_) {
    try {
      navigator.clipboard = clipboardApi;
    } catch (_) {
      // Ignore if the current engine does not allow overriding clipboard.
    }
  }
}

function isMathfieldActive() {
  return !!mathfield && (
    document.activeElement === mathfield ||
    mathfield.matches?.(':focus') ||
    mathfield.matches?.(':focus-within')
  );
}

function addMathRow() {
  const before = currentLatex();
  mathfield.executeCommand('addRowAfter');
  if (currentLatex() !== before) return;

  mathfield.executeCommand('selectAll');
  mathfield.insert(MULTILINE_TEMPLATE, {
    format: 'latex',
    insertionMode: 'replaceSelection',
    selectionMode: 'placeholder',
  });
}

function hideVirtualKeyboard() {
  try {
    mathfield?.executeCommand?.('hideVirtualKeyboard');
  } finally {
    syncKeyboardState();
  }
}

function handleMathfieldKeydown(event) {
  if (!isMathfieldActive()) return;

  if (event.key === 'Escape') {
    event.preventDefault();
    hideVirtualKeyboard();
    return;
  }

  if (
    event.key === 'Enter' &&
    event.shiftKey &&
    !event.isComposing &&
    !event.altKey &&
    !event.ctrlKey &&
    !event.metaKey
  ) {
    event.preventDefault();
    event.stopImmediatePropagation();
    insertToMain();
    return;
  }

  if (mathfield.mode === 'latex') return;

  if (
    event.key === 'Enter' &&
    !event.isComposing &&
    !event.altKey &&
    !event.ctrlKey &&
    !event.metaKey
  ) {
    event.preventDefault();
    event.stopImmediatePropagation();
    addMathRow();
  }
}

function compactText(value, maxChars = 320, maxLines = 10) {
  const text = String(value ?? '');
  const normalized = text.replace(/\r\n/g, '\n');
  const lines = normalized.split('\n');
  const clippedLines = lines.slice(0, maxLines);
  let clipped = clippedLines.join('\n');
  if (clipped.length > maxChars) clipped = `${clipped.slice(0, maxChars - 1)}…`;
  if (lines.length > maxLines || normalized.length > maxChars) {
    if (!clipped.endsWith('…')) clipped += '\n…';
  }
  return clipped;
}

function isPrimitiveMathJson(node) {
  return (
    node === null ||
    typeof node === 'string' ||
    typeof node === 'number' ||
    typeof node === 'boolean'
  );
}

function isInlineMathJsonArray(node) {
  return (
    Array.isArray(node) &&
    node.length <= 4 &&
    node.every((item) => isPrimitiveMathJson(item))
  );
}

function formatMathJsonNode(node, level = 0) {
  const indent = '  '.repeat(level);
  const childIndent = '  '.repeat(level + 1);

  if (isPrimitiveMathJson(node)) {
    return JSON.stringify(node);
  }

  if (Array.isArray(node)) {
    if (node.length === 0) return '[]';
    if (isInlineMathJsonArray(node)) {
      return `[${node.map((item) => formatMathJsonNode(item, level + 1)).join(', ')}]`;
    }

    const lines = node.map((item, index) => {
      const rendered = formatMathJsonNode(item, level + 1);
      const suffix = index < node.length - 1 ? ',' : '';
      return `${childIndent}${rendered}${suffix}`;
    });
    return `[\n${lines.join('\n')}\n${indent}]`;
  }

  if (typeof node === 'object') {
    const entries = Object.entries(node);
    if (!entries.length) return '{}';
    const lines = entries.map(([key, value], index) => {
      const rendered = formatMathJsonNode(value, level + 1);
      const suffix = index < entries.length - 1 ? ',' : '';
      return `${childIndent}${JSON.stringify(key)}: ${rendered}${suffix}`;
    });
    return `{\n${lines.join('\n')}\n${indent}}`;
  }

  return JSON.stringify(String(node));
}

function setStatus(text) {
  bridge?.onComputeError?.(text || '');
}

function syncOutputs() {
  if (!mathfield) return;
  const latex = mathfield.getValue('latex-expanded') || '';
  document.body.classList.toggle('editor-empty', !latex.trim());
  document.body.classList.toggle('workspace-empty', !latex.trim());
  latexOutput.textContent = latex;
  bridge?.onLatexChanged?.(latex);

  try {
    if (ce) {
      const expr = ce.parse(latex || '');
      mathJsonFormatted = formatMathJsonNode(expr?.json ?? null);
      mathjsonOutput.textContent = compactText(mathJsonFormatted, 260, 8);
      mathjsonOutput.title = mathJsonFormatted;
      bridge?.onMathJsonChanged?.(mathJsonFormatted);
    } else {
      mathJsonFormatted = '计算引擎尚未就绪';
      mathjsonOutput.textContent = '计算引擎尚未就绪';
      mathjsonOutput.title = '';
    }
  } catch (err) {
    const message = String(err);
    mathJsonFormatted = message;
    mathjsonOutput.textContent = compactText(message, 260, 8);
    mathjsonOutput.title = message;
  }
}

async function evaluateExpression() {
  try {
    const { expr } = currentExpression('计算');
    const result = await expr.evaluateAsync();
    if (isEmptyResult(result)) {
      throw new Error('表达式当前没有可显示的计算结果');
    }
    const rendered = extractResultLatex(result);
    setRenderedResult(rendered, '已完成符号计算。');
    bridge?.onEvaluationResult?.(rendered);
    setStatus('计算完成');
  } catch (err) {
    clearRenderedResult();
    resultOutput.textContent = normalizeComputeError(err, '计算失败');
    setStatus(resultOutput.textContent);
  }
}

async function simplifyExpression() {
  try {
    const { expr } = currentExpression('化简');
    const result = expr.simplify();
    const rendered = extractResultLatex(result);
    if (isEmptyResult(result)) {
      throw new Error('当前公式无法进一步化简');
    }
    setRenderedResult(rendered, '已完成公式化简。');
    bridge?.onEvaluationResult?.(rendered);
    setStatus('化简完成');
  } catch (err) {
    clearRenderedResult();
    resultOutput.textContent = normalizeComputeError(err, '化简失败');
    setStatus(resultOutput.textContent);
  }
}

async function numericEvaluate() {
  try {
    const { expr } = currentExpression('数值化');
    const result = expr.N();
    if (isEmptyResult(result)) {
      throw new Error('当前公式无法数值化');
    }
    const rendered = extractResultLatex(result);
    setRenderedResult(rendered, '已完成数值化计算。');
    bridge?.onEvaluationResult?.(rendered);
    setStatus('数值化完成');
  } catch (err) {
    clearRenderedResult();
    resultOutput.textContent = normalizeComputeError(err, '数值化失败');
    setStatus(resultOutput.textContent);
  }
}

async function expandExpression() {
  try {
    const { expr } = currentExpression('展开');
    const result = typeof expr.expand === 'function'
      ? expr.expand()
      : computeHelpers.expand?.(expr) ?? null;
    if (!result || isEmptyResult(result)) {
      throw new Error('当前公式无法展开');
    }
    const rendered = extractResultLatex(result);
    setRenderedResult(rendered, '已完成公式展开。');
    bridge?.onEvaluationResult?.(rendered);
    setStatus('展开完成');
  } catch (err) {
    clearRenderedResult();
    resultOutput.textContent = normalizeComputeError(err, '展开失败');
    setStatus(resultOutput.textContent);
  }
}

async function factorExpression() {
  try {
    const { expr } = currentExpression('因式分解');
    const result = typeof expr.factor === 'function'
      ? expr.factor()
      : computeHelpers.factor?.(expr) ?? null;
    if (!result || isEmptyResult(result)) {
      throw new Error('当前公式无法做因式分解');
    }
    const rendered = extractResultLatex(result);
    setRenderedResult(rendered, '已完成因式分解。');
    bridge?.onEvaluationResult?.(rendered);
    setStatus('因式分解完成');
  } catch (err) {
    clearRenderedResult();
    resultOutput.textContent = normalizeComputeError(err, '因式分解失败');
    setStatus(resultOutput.textContent);
  }
}

async function solveExpression() {
  try {
    const { latex, expr } = currentExpression('求解');
    const variable = inferSolveVariable(latex);
    let result = null;
    if (typeof expr.solve === 'function') {
      result = expr.solve(variable);
    } else if (computeHelpers.solve) {
      result = computeHelpers.solve(expr, variable);
    }
    if (!result || isEmptyResult(result)) {
      throw new Error(`未找到关于 ${variable} 的可用解`);
    }
    const rendered = Array.isArray(result)
      ? result
          .map((item) => `${variable} = ${item?.latex ?? String(item)}`)
          .join(',\\;')
      : extractResultLatex(result);
    setRenderedResult(rendered, `已尝试对 ${variable} 求解。`);
    bridge?.onEvaluationResult?.(rendered);
    setStatus('求解完成');
  } catch (err) {
    clearRenderedResult();
    resultOutput.textContent = normalizeComputeError(err, '求解失败');
    setStatus(resultOutput.textContent);
  }
}

function setLatex(value) {
  if (!mathfield) return;
  mathfield.setValue(value || '', { silenceNotifications: true });
  syncOutputs();
}

function copyLatex() {
  const text = latexOutput.textContent || '';
  if (bridge?.copyLatexToClipboard) {
    bridge.copyLatexToClipboard(text);
    return;
  }
  navigator.clipboard?.writeText(text);
  setStatus('已复制 LaTeX');
}

function copyMathJson() {
  const text = mathJsonFormatted || mathjsonOutput.textContent || '';
  if (bridge?.copyMathJsonToClipboard) {
    bridge.copyMathJsonToClipboard(text);
    return;
  }
  navigator.clipboard?.writeText(text);
  setStatus('已复制 MathJSON');
}

function insertToMain() {
  const latex = (mathfield?.getValue('latex-expanded') || '').trim();
  bridge?.requestInsertToMain?.(latex);
}

window.workbenchApi = {
  setLatex,
  setThemeMode,
  evaluateExpression,
  simplifyExpression,
  numericEvaluate,
  expandExpression,
  factorExpression,
  solveExpression,
  copyLatex,
  copyMathJson,
  insertToMain,
  applyMultilineLayout,
  insertSnippet,
};

function setupBridge() {
  return new Promise((resolve) => {
    if (!window.qt || !window.QWebChannel) {
      resolve();
      return;
    }
    new QWebChannel(qt.webChannelTransport, (channel) => {
      bridge = channel.objects.pyBridge || null;
      resolve();
    });
  });
}

async function bootstrap() {
  await setupBridge();
  try {
    const [{ MathfieldElement }, computeModule] = await Promise.all([
      import('./vendor/mathlive.min.mjs'),
      import('./vendor/compute-engine.min.esm.js'),
    ]);

    const { ComputeEngine, expand, factor, solve } = computeModule;
    computeHelpers = { expand, factor, solve };
    ce = new ComputeEngine();
    ce.timeLimit = 0;
    MathfieldElement.computeEngine = ce;
    installClipboardBridge();
    MathfieldElement.fontsDirectory = new URL('./vendor/fonts', window.location.href).href;
    if (window.mathVirtualKeyboard) {
      window.mathVirtualKeyboard.container = document.body;
      window.mathVirtualKeyboard.addEventListener?.('geometrychange', syncKeyboardState);
      window.mathVirtualKeyboard.addEventListener?.('visibilitychange', syncKeyboardState);
    }

    mathfield = new MathfieldElement();
    mathfield.tabIndex = 0;
    mathfield.mathVirtualKeyboardPolicy = 'onfocus';
    mathfield.mathModeSpace = VISIBLE_MATH_SPACE;
    mathfield.smartFence = true;
    mathfield.smartMode = false;
    mathfield.style.overflowX = 'auto';
    mathfield.style.overflowY = 'auto';
    host.appendChild(mathfield);

    resultView = new MathfieldElement();
    resultView.readOnly = true;
    resultView.mathVirtualKeyboardPolicy = 'manual';
    resultView.smartFence = false;
    resultView.smartMode = false;
    resultRenderHost.appendChild(resultView);

    mathfield.addEventListener('input', () => {
      syncOutputs();
      clearRenderedResult();
      resultOutput.textContent = '等待执行计算、化简、数值化或求解。';
      setStatus('正在编辑');
      syncKeyboardState();
    });
    mathfield.addEventListener('keydown', handleMathfieldKeydown, true);
    mathfield.addEventListener('focusin', () => queueMicrotask(syncKeyboardState));
    mathfield.addEventListener('focusout', () => setTimeout(syncKeyboardState, 0));

    syncOutputs();
    syncKeyboardState();
    setThemeMode(document.body.dataset.theme || 'dark');
    document.body.classList.add('editor-empty');
    document.body.classList.add('workspace-empty');
    document.body.classList.add('result-empty');
    resultOutput.textContent = '等待执行计算、化简、数值化或求解。';
    bridge?.onEditorReady?.();
  } catch (err) {
    setStatus(`数学工作台加载失败：${String(err)}`);
    resultOutput.textContent = String(err);
  }
}

bootstrap();
