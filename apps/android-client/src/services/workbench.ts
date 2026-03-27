import type {
  ComputeAction,
  LayoutKind,
  WorkbenchResult,
  WorkbenchSample,
  WorkbenchSnippet,
} from '../types/workbench';

type ComputeEngineModule = typeof import('@cortex-js/compute-engine');
type ComputeEngineInstance = InstanceType<ComputeEngineModule['ComputeEngine']>;

let computeEnginePromise: Promise<ComputeEngineInstance> | null = null;

async function getComputeEngine(): Promise<ComputeEngineInstance> {
  if (!computeEnginePromise) {
    computeEnginePromise = import('@cortex-js/compute-engine').then(({ ComputeEngine }) => new ComputeEngine());
  }
  return computeEnginePromise;
}

export async function warmupWorkbenchEngine(): Promise<void> {
  await getComputeEngine();
}

export const snippets: WorkbenchSnippet[] = [
  { id: 'fraction', label: '分式', latex: '\\frac{#?}{#?}', description: '插入分子/分母模板' },
  { id: 'sqrt', label: '根式', latex: '\\sqrt{#?}', description: '插入平方根' },
  { id: 'superscript', label: '上标', latex: 'x^{#?}', description: '插入指数' },
  { id: 'subscript', label: '下标', latex: 'x_{#?}', description: '插入下标' },
  { id: 'sum', label: '求和', latex: '\\sum_{n=1}^{\\infty} #?', description: '插入求和号' },
  { id: 'integral', label: '积分', latex: '\\int_{a}^{b} #?\\,dx', description: '插入定积分' },
  {
    id: 'matrix2',
    label: '矩阵',
    latex: '\\begin{bmatrix}#? & #? \\\\ #? & #?\\end{bmatrix}',
    description: '插入 2x2 矩阵',
  },
  { id: 'newline', label: '换行', latex: ' \\\\ ', description: '在多行环境中新增一行' },
];

export const samples: WorkbenchSample[] = [
  {
    id: 'quadratic',
    label: '二次方程',
    latex: 'x^2 + 5x + 6 = 0',
    note: '适合测试求解与因式分解',
  },
  {
    id: 'series',
    label: '级数',
    latex: '\\sum_{n=1}^{10} n^2',
    note: '适合测试化简与求值',
  },
  {
    id: 'integral',
    label: '积分',
    latex: '\\int_0^{\\pi} \\sin(x)\\,dx',
    note: '适合测试符号计算',
  },
  {
    id: 'matrix',
    label: '矩阵',
    latex: '\\begin{bmatrix}1 & 2 \\\\ 3 & 4\\end{bmatrix}^2',
    note: '适合测试前端 MathJSON 输出',
  },
];

export const computeActions: Array<{ id: ComputeAction; label: string; note: string }> = [
  { id: 'evaluate', label: '计算', note: '执行符号计算' },
  { id: 'simplify', label: '化简', note: '合并和整理表达式' },
  { id: 'numeric', label: '数值化', note: '输出近似数值' },
  { id: 'expand', label: '展开', note: '展开乘积与幂' },
  { id: 'factor', label: '因式分解', note: '尝试分解多项式' },
  { id: 'solve', label: '求解', note: '自动推断变量' },
];

export async function getMathJsonPreview(latex: string): Promise<string> {
  const value = latex.trim();
  if (!value) return '等待输入公式...';

  try {
    const computeEngine = await getComputeEngine();
    const expr = computeEngine.parse(value);
    return JSON.stringify(expr?.json ?? null, null, 2);
  } catch (error) {
    return normalizeError(error, 'MathJSON 解析失败');
  }
}

export async function runComputeAction(action: ComputeAction, latex: string): Promise<WorkbenchResult> {
  const input = latex.trim();
  if (!input) {
    return {
      action,
      ok: false,
      summary: '请先输入公式',
      latex: '',
      text: '请先输入公式，再执行计算。',
      mathJson: 'null',
    };
  }

  try {
    const computeEngine = await getComputeEngine();
    const expr = computeEngine.parse(input) as any;
    const mathJson = JSON.stringify(expr?.json ?? null, null, 2);
    const result = applyAction(action, expr, input);
    const resolved = result instanceof Promise ? await result : result;
    const resultLatex = latexOf(resolved);

    if (!resultLatex) {
      throw new Error('当前表达式没有返回可展示的结果');
    }

    return {
      action,
      ok: true,
      summary: summaryForAction(action),
      latex: resultLatex,
      text: resultLatex,
      mathJson,
    };
  } catch (error) {
    return {
      action,
      ok: false,
      summary: `${labelForAction(action)}失败`,
      latex: '',
      text: normalizeError(error, `${labelForAction(action)}失败`),
      mathJson: 'null',
    };
  }
}

export function applyMultilineLayout(latex: string, kind: LayoutKind): string {
  const value = latex.trim();
  if (!value) return latex;

  const normalizedLatex = unwrapMultilineLatex(value);
  const lines = splitIntoMultilineSegments(normalizedLatex);

  if (kind === 'multline') {
    return `\\begin{multline}\n${lines.join(' \\\\\n')}\n\\end{multline}`;
  }

  if (kind === 'align') {
    return `\\begin{align}\n${lines.map(decorateAlignSegment).join(' \\\\\n')}\n\\end{align}`;
  }

  return `\\displaylines{${lines.join(' \\\\ ')}}`;
}

function applyAction(action: ComputeAction, expr: any, latex: string): unknown {
  switch (action) {
    case 'evaluate':
      return expr.evaluateAsync?.() ?? expr.evaluate?.() ?? expr;
    case 'simplify':
      return expr.simplify?.() ?? expr;
    case 'numeric':
      return expr.N?.() ?? expr.evaluate?.() ?? expr;
    case 'expand':
      if (typeof expr.expand === 'function') return expr.expand();
      throw new Error('当前表达式无法展开');
    case 'factor':
      if (typeof expr.factor === 'function') return expr.factor();
      throw new Error('当前表达式无法做因式分解');
    case 'solve': {
      const variable = inferSolveVariable(latex);
      if (typeof expr.solve === 'function') {
        const solved = expr.solve(variable);
        if (Array.isArray(solved)) {
          return solved.map((item: any) => `${variable} = ${latexOf(item)}`);
        }
        return solved;
      }
      throw new Error(`当前环境暂未提供关于 ${variable} 的求解器`);
    }
    default:
      return expr;
  }
}

function latexOf(value: unknown): string {
  if (Array.isArray(value)) {
    return value
      .map((item) => latexOf(item))
      .filter(Boolean)
      .join(',\\;');
  }

  if (typeof value === 'string') return value;

  if (value && typeof value === 'object') {
    const candidate = value as {
      latex?: string;
      toString?: () => string;
      toLatex?: () => string;
    };
    if (typeof candidate.latex === 'string' && candidate.latex.trim()) {
      return candidate.latex;
    }
    if (typeof candidate.toLatex === 'function') {
      const rendered = candidate.toLatex();
      if (rendered) return rendered;
    }
    if (typeof candidate.toString === 'function') {
      const rendered = candidate.toString();
      if (rendered && rendered !== '[object Object]') return rendered;
    }
  }

  return '';
}

function inferSolveVariable(latex: string): string {
  const matches = latex.match(/[a-zA-Z]/g);
  return matches?.[0] ?? 'x';
}

function summaryForAction(action: ComputeAction): string {
  switch (action) {
    case 'evaluate':
      return '已完成符号计算';
    case 'simplify':
      return '已完成公式化简';
    case 'numeric':
      return '已输出数值结果';
    case 'expand':
      return '已完成公式展开';
    case 'factor':
      return '已完成因式分解';
    case 'solve':
      return '已尝试对表达式求解';
    default:
      return '计算完成';
  }
}

function labelForAction(action: ComputeAction): string {
  return computeActions.find((item) => item.id === action)?.label ?? '计算';
}

function normalizeError(error: unknown, fallback: string): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  if (typeof error === 'string' && error.trim()) return error;
  return fallback;
}

function unwrapMultilineLatex(latex: string): string {
  const displaylines = latex.match(/^\\displaylines\{([\s\S]*)\}$/);
  if (displaylines) return displaylines[1];

  const env = latex.match(/^\\begin\{(align|multline)\}([\s\S]*)\\end\{\1\}$/);
  if (env) return env[2];

  return latex;
}

function splitIntoMultilineSegments(latex: string): string[] {
  return latex
    .split(/\\\\/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function decorateAlignSegment(line: string): string {
  if (line.includes('&')) return line;
  const equalIndex = line.indexOf('=');
  if (equalIndex >= 0) {
    return `${line.slice(0, equalIndex)}&=${line.slice(equalIndex + 1)}`;
  }
  return line;
}