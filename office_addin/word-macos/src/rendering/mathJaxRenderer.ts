import { normalizeLatexInput, validateLatex } from "../domain/formula";

interface MathJaxRuntime {
  readonly startup: {
    readonly promise: Promise<unknown>;
  };
  tex2mml(source: string, options: { display: boolean; end: number }): string;
  tex2svg(source: string, options: { display: boolean }): Element;
}

interface MathJaxWindow extends Window {
  MathJax?: MathJaxRuntime | Record<string, unknown>;
}

export interface RenderedFormula {
  readonly svg: SVGElement;
  readonly mathml: string;
}

export class FormulaRenderError extends Error {
  constructor(message: string, options?: ErrorOptions) {
    super(message, options);
    this.name = "FormulaRenderError";
  }
}

let runtimePromise: Promise<MathJaxRuntime> | undefined;

function readGroup(source: string, start: number): { content: string; end: number } | null {
  if (source[start] !== "{") {
    return null;
  }
  let depth = 0;
  for (let index = start; index < source.length; index += 1) {
    if (source[index] === "\\") {
      index += 1;
      continue;
    }
    if (source[index] === "{") {
      depth += 1;
    } else if (source[index] === "}") {
      depth -= 1;
      if (depth === 0) {
        return { content: source.slice(start + 1, index), end: index + 1 };
      }
    }
  }
  return null;
}

export function preprocessTexSource(value: unknown): string {
  const normalized = normalizeLatexInput(value).replace(/(^|[^\\])\$/g, "$1");
  const command = "\\colorbox";
  let result = "";
  let cursor = 0;

  while (cursor < normalized.length) {
    const commandIndex = normalized.indexOf(command, cursor);
    if (commandIndex < 0) {
      result += normalized.slice(cursor);
      break;
    }

    result += normalized.slice(cursor, commandIndex);
    let groupStart = commandIndex + command.length;
    while (/\s/.test(normalized[groupStart] ?? "")) {
      groupStart += 1;
    }
    const color = readGroup(normalized, groupStart);
    if (!color) {
      result += command;
      cursor = commandIndex + command.length;
      continue;
    }

    groupStart = color.end;
    while (/\s/.test(normalized[groupStart] ?? "")) {
      groupStart += 1;
    }
    const body = readGroup(normalized, groupStart);
    if (!body) {
      result += normalized.slice(commandIndex, color.end);
      cursor = color.end;
      continue;
    }

    let bodyContent = body.content.trim();
    if (bodyContent.startsWith("$") && bodyContent.endsWith("$") && bodyContent.length >= 2) {
      bodyContent = bodyContent.slice(1, -1);
    }
    result += `\\bbox[${color.content.trim()}]{${preprocessTexSource(bodyContent)}}`;
    cursor = body.end;
  }

  return result;
}

function configureMathJax(targetWindow: MathJaxWindow): void {
  targetWindow.MathJax = {
    loader: { load: ["[tex]/bbox"] },
    tex: {
      packages: ["base", "ams", "newcommand", "bbox"],
      maxBuffer: 16_384,
      maxMacros: 1_000,
    },
    svg: { fontCache: "none" },
    options: { enableMenu: false },
    startup: { typeset: false },
  };
}

function loadBundledMathJax(): Promise<MathJaxRuntime> {
  if (runtimePromise) {
    return runtimePromise;
  }

  runtimePromise = new Promise<MathJaxRuntime>((resolve, reject) => {
    const targetWindow = window as MathJaxWindow;
    configureMathJax(targetWindow);

    const script = document.createElement("script");
    script.id = "latexsnipper-mathjax-runtime";
    script.src = new URL(
      "assets/mathjax/es5/tex-mml-svg.js",
      document.baseURI,
    ).href;
    script.async = true;
    script.referrerPolicy = "no-referrer";

    let settled = false;
    let timeout = 0;
    const fail = (error: FormulaRenderError) => {
      if (settled) {
        return;
      }
      settled = true;
      window.clearTimeout(timeout);
      script.remove();
      delete targetWindow.MathJax;
      reject(error);
    };
    const succeed = (runtime: MathJaxRuntime) => {
      if (settled) {
        return;
      }
      settled = true;
      window.clearTimeout(timeout);
      resolve(runtime);
    };
    timeout = window.setTimeout(() => {
      fail(new FormulaRenderError("本地 MathJax 加载或初始化超时。"));
    }, 15_000);

    script.addEventListener("error", () => {
      fail(new FormulaRenderError("本地 MathJax 资源加载失败。"));
    });
    script.addEventListener("load", () => {
      const runtime = targetWindow.MathJax as MathJaxRuntime | undefined;
      if (!runtime?.startup?.promise) {
        fail(new FormulaRenderError("本地 MathJax 初始化结构无效。"));
        return;
      }
      void runtime.startup.promise.then(() => {
        if (
          typeof runtime.tex2svg !== "function" ||
          typeof runtime.tex2mml !== "function"
        ) {
          fail(new FormulaRenderError("本地 MathJax 初始化结构无效。"));
          return;
        }
        succeed(runtime);
      }, (error: unknown) => {
        fail(new FormulaRenderError("本地 MathJax 初始化失败。", { cause: error }));
      });
    });
    document.head.append(script);
  }).catch((error: unknown) => {
    runtimePromise = undefined;
    throw error;
  });

  return runtimePromise;
}

function sanitizeSvg(source: Element): SVGElement {
  const candidate =
    source.localName === "svg" ? source : source.querySelector("svg");
  if (!candidate || candidate.namespaceURI !== "http://www.w3.org/2000/svg") {
    throw new FormulaRenderError("MathJax 没有返回有效 SVG。" );
  }

  const svg = candidate.cloneNode(true) as SVGElement;
  svg.querySelectorAll("script, foreignObject, iframe, object, embed, audio, video").forEach(
    (element) => element.remove(),
  );
  for (const element of [svg, ...svg.querySelectorAll("*")]) {
    for (const attribute of [...element.attributes]) {
      const name = attribute.name.toLowerCase();
      const value = attribute.value.trim();
      if (name.startsWith("on")) {
        element.removeAttribute(attribute.name);
        continue;
      }
      if ((name === "href" || name === "xlink:href") && !value.startsWith("#")) {
        element.removeAttribute(attribute.name);
        continue;
      }
      const urls = [...value.matchAll(/url\(\s*(["']?)([^"')\s]+)\1\s*\)/giu)];
      if (urls.some((match) => !match[2]?.startsWith("#"))) {
        element.removeAttribute(attribute.name);
      }
    }
  }
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "公式预览");
  svg.setAttribute("focusable", "false");
  return svg;
}

export function validateMathMl(value: string): string {
  const parsed = new DOMParser().parseFromString(value, "application/xml");
  if (
    parsed.querySelector("parsererror") ||
    parsed.documentElement.localName !== "math" ||
    parsed.documentElement.namespaceURI !== "http://www.w3.org/1998/Math/MathML"
  ) {
    throw new FormulaRenderError("MathJax 没有返回有效 MathML。" );
  }
  return new XMLSerializer().serializeToString(parsed.documentElement);
}

export class MathJaxRenderer {
  readonly #loadRuntime: () => Promise<MathJaxRuntime>;

  constructor(loadRuntime: () => Promise<MathJaxRuntime> = loadBundledMathJax) {
    this.#loadRuntime = loadRuntime;
  }

  async render(latexValue: unknown, display: boolean): Promise<RenderedFormula> {
    const latex = validateLatex(latexValue);
    const source = preprocessTexSource(latex);
    try {
      const runtime = await this.#loadRuntime();
      const container = runtime.tex2svg(source, { display });
      const mathml = runtime.tex2mml(source, { display, end: 20 });
      return {
        svg: sanitizeSvg(container),
        mathml: validateMathMl(mathml),
      };
    } catch (error) {
      if (error instanceof FormulaRenderError) {
        throw error;
      }
      throw new FormulaRenderError("公式预览渲染失败。", { cause: error });
    }
  }
}
