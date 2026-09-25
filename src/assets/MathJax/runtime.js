// Shared configuration, conversion, and asynchronous host bridge. No host font preferences.
(function (global) {
  'use strict';
  const config = global.LaTeXSnipperMathJaxConfig;
  const tasks = new Map();
  let queue = Promise.resolve();
  const api = global.LaTeXSnipperMathJax = {
    version: config.version,
    ready: false,
    error: '',
    configure(settings = {}) {
      const root = settings.root.replace(/\/$/, '');
      const remote = /^https?:/.test(root) && !settings.localFonts;
      const output = settings.output || 'chtml';
      const font = settings.font || config.defaultFont;
      const fontRoot = remote
        ? (root.includes('/npm/') ? root.split('/npm/')[0] + '/npm/@mathjax' : new URL(root).origin + '/@mathjax')
        : root + '/fonts';
      const fontVersion = remote ? '@' + config.version : '';
      api.ready = false;
      api.error = '';
      global.MathJax = {
        loader: {
          paths: {mathjax: root, fonts: fontRoot,
            [font]: fontRoot + '/' + font + '-font' + fontVersion,
            'mathjax-mhchem-extension': fontRoot + '/mathjax-mhchem-font-extension' + fontVersion},
          dependencies: {
            ['[mathjax-mhchem-extension]/' + output]: ['[' + font + ']/' + output]
          },
          load: ['core', 'input/tex', 'input/mml', 'output/' + output,
            ...config.extensions.filter(name => !['configmacros', 'textmacros'].includes(name))
              .map(name => '[tex]/' + name)],
          failed(error) { api.error = String(error.message || error); }
        },
        output: {
          font,
          fontPath: '[fonts]/%%FONT%%-font' + fontVersion,
          scale: settings.scale || 1
        },
        tex: {
          packages: {'[+]': config.extensions},
          inlineMath: [['$', '$'], ['\\(', '\\)']],
          displayMath: [['$$', '$$'], ['\\[', '\\]']],
          processEscapes: true
        },
        svg: {fontCache: 'none'},
        options: {...(settings.options || {})},
        startup: {
          output,
          typeset: settings.typeset !== false,
          pageReady() {
            return MathJax.startup.defaultPageReady().then(() => { api.ready = true; });
          }
        }
      };
      return global.MathJax;
    },
    load(settings) {
      // Retry a missing entry point before any MathJax modules have executed.
      const roots = [settings.root, ...(settings.fallbackRoots || [])];
      function attempt() {
        const root = roots.shift();
        api.configure({...settings, root});
        const script = document.createElement('script');
        script.src = root.replace(/\/$/, '') + '/startup.js';
        script.onerror = () => {
          script.remove();
          if (roots.length) attempt();
          else api.error = 'MathJax startup.js could not be loaded';
        };
        document.head.appendChild(script);
      }
      attempt();
    },
    convert(input) {
      const run = async () => {
        await MathJax.startup.promise;
        let source = String(input.latex || '');
        const isMathMl = api.isMathMl(source);
        if (isMathMl) source = api.mathMlElement(source);
        const display = input.displayMode !== 'Inline';
        const outputs = input.outputs || ['svg', 'mathml'];
        const result = {version: MathJax.version};
        if (outputs.includes('mathml')) {
          result.mathml = isMathMl ? source.trim() : await MathJax.tex2mmlPromise(source, {display});
        }
        if (outputs.includes('svg')) {
          const container = await (isMathMl ? MathJax.mathml2svgPromise : MathJax.tex2svgPromise)(source, {display});
          const adaptor = MathJax.startup.adaptor;
          const node = adaptor.firstChild(container);
          Object.assign(result, {
            svg: adaptor.outerHTML(node),
            widthEx: adaptor.getAttribute(node, 'width') || '0ex',
            heightEx: adaptor.getAttribute(node, 'height') || '0ex',
            style: adaptor.getAttribute(node, 'style') || '',
            scale: Number(input.fontScale) > 0 ? Number(input.fontScale) : 1,
            warnings: []
          });
        }
        return result;
      };
      return api.enqueue(run);
    },
    isMathMl(source) {
      return /^(<\?xml[\s\S]*?\?>\s*)?<([a-z_][\w.-]*:)?math(\s|>)/i.test(String(source).trim());
    },
    mathMlElement(source) {
      // MathJax's HTML adaptor expects one element, not an XML processing instruction.
      return String(source).trim().replace(/^<\?xml[\s\S]*?\?>\s*/i, '');
    },
    enqueue(operation) {
      const pending = queue.then(operation);
      queue = pending.catch(() => {});
      return pending;
    },
    start(id, operation) {
      if (tasks.has(id)) throw new Error('Duplicate MathJax request: ' + id);
      const task = {state: 'pending'};
      tasks.set(id, task);
      Promise.resolve().then(operation).then(value => {
        task.state = 'done';
        task.value = value;
      }, error => {
        task.state = 'done';
        task.value = {error: String(error.stack || error.message || error)};
      });
    },
    take(id) {
      const task = tasks.get(id);
      if (!task || task.state !== 'done') return null;
      tasks.delete(id);
      return JSON.stringify(task.value);
    },
    cancel(id) { tasks.delete(id); }
  };
})(globalThis);
