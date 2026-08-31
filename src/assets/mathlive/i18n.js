(function () {
  const requested = new URLSearchParams(window.location.search).get('lang') || 'zh_CN';
  const language = requested === 'en_US' ? 'en_US' : 'zh_CN';
  const english = {
    'LaTeXSnipper 数学工作台': 'LaTeXSnipper Math Workspace',
    '公式编辑区': 'Formula Editor',
    '输入公式，或使用上方示例与下方快捷插入开始编辑': 'Enter a formula, load an example above, or use a quick insert below.',
    'LaTeX 源码': 'LaTeX Source',
    'MathJSON 结构': 'MathJSON Structure',
    '计算结果': 'Result',
    '从这里开始': 'Start here',
    '输入公式后，可执行计算、化简、数值化或求解。': 'Enter a formula, then evaluate, simplify, approximate, or solve it.',
    '上方可直接载入示例，下方可快捷插入分式、上下标、求和与矩阵。': 'Load an example above or quickly insert fractions, scripts, sums, and matrices below.',
    '适合最简单的多行排版，只负责逐行换开显示。': 'is the simplest multiline layout and displays each line separately.',
    '适合一条很长的公式拆成多行，不强调等号或符号对齐。': 'breaks one long formula across lines without aligning operators.',
    '适合推导、方程组和多步变形，可围绕 = 等符号做对齐。': 'is suited to derivations and equation systems, with alignment around operators such as =.',
    '计算失败': 'Evaluation failed',
    '前端计算引擎无法完成当前表达式': 'The embedded compute engine could not finish this expression',
    '表达式当前无法得到可用结果': 'The expression did not produce a usable result',
    '公式解析失败：{message}': 'Formula parsing failed: {message}',
    '表达式未定义：{message}': 'The expression is undefined: {message}',
    '{fallback}：{message}': '{fallback}: {message}',
    '请先输入公式，再应用多行排版': 'Enter a formula before applying a multiline layout',
    '已应用 {kind} 多行排版': 'Applied the {kind} multiline layout',
    '当前快捷插入模板不可用': 'This quick-insert template is unavailable',
    '已插入快捷模板': 'Quick template inserted',
    '快捷插入失败：{message}': 'Quick insert failed: {message}',
    '计算': 'evaluate',
    '计算引擎尚未就绪': 'The compute engine is not ready',
    '请先输入公式，再执行{action}': 'Enter a formula before you {action}',
    '剪贴板读取接口不可用': 'Clipboard reading is unavailable',
    '剪贴板写入失败': 'Could not write to the clipboard',
    '剪贴板写入接口不可用': 'Clipboard writing is unavailable',
    '表达式当前没有可显示的计算结果': 'The expression has no displayable result',
    '已完成符号计算。': 'Symbolic evaluation completed.',
    '计算完成': 'Evaluation completed',
    '化简': 'simplify',
    '当前公式无法进一步化简': 'The formula cannot be simplified further',
    '已完成公式化简。': 'Simplification completed.',
    '化简完成': 'Simplification completed',
    '化简失败': 'Simplification failed',
    '数值化': 'approximate',
    '当前公式无法数值化': 'The formula cannot be approximated numerically',
    '已完成数值化计算。': 'Numerical evaluation completed.',
    '数值化完成': 'Numerical evaluation completed',
    '数值化失败': 'Numerical evaluation failed',
    '展开': 'expand',
    '当前公式无法展开': 'The formula cannot be expanded',
    '已完成公式展开。': 'Expansion completed.',
    '展开完成': 'Expansion completed',
    '展开失败': 'Expansion failed',
    '因式分解': 'factor',
    '当前公式无法做因式分解': 'The formula cannot be factored',
    '已完成因式分解。': 'Factorization completed.',
    '因式分解完成': 'Factorization completed',
    '因式分解失败': 'Factorization failed',
    '求解': 'solve',
    '未找到关于 {variable} 的可用解': 'No solution for {variable} was found',
    '已尝试对 {variable} 求解。': 'Attempted to solve for {variable}.',
    '求解完成': 'Solving completed',
    '求解失败': 'Solving failed',
    '已复制 LaTeX': 'LaTeX copied',
    '已复制 MathJSON': 'MathJSON copied',
    '等待执行计算、化简、数值化或求解。': 'Waiting to evaluate, simplify, approximate, or solve.',
    '正在编辑': 'Editing',
    '数学工作台加载失败：{message}': 'Math workspace failed to load: {message}',
    'MathLive 初始化失败：{message}': 'MathLive failed to initialize: {message}',
  };

  function format(template, values) {
    return String(template).replace(/\{([^{}]+)\}/g, (match, key) => (
      Object.prototype.hasOwnProperty.call(values || {}, key) ? String(values[key]) : match
    ));
  }

  function t(source, values = {}) {
    const template = language === 'en_US' ? (english[source] || source) : source;
    return format(template, values);
  }

  function localizeDocument() {
    document.documentElement.lang = language === 'en_US' ? 'en-US' : 'zh-CN';
    for (const element of document.querySelectorAll('[data-i18n]')) {
      element.textContent = t(element.dataset.i18n || '');
    }
    if (document.title) document.title = t(document.title);
  }

  window.lsnI18n = { language, t, localizeDocument };
  document.addEventListener('DOMContentLoaded', localizeDocument, { once: true });
})();
