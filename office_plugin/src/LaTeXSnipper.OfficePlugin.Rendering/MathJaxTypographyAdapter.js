(function () {
  'use strict';
  if (globalThis.LaTeXSnipperOfficeTypography) return {ready: true};
  if (MathJax.version !== '4.1.3') throw new Error('Typography adapter requires MathJax 4.1.3');
  const doc = MathJax.startup.document, jax = doc.outputJax;
  const originalTexFont = jax.font;
  const fonts = new Map();
  const supplementalGlyphs = new Set();
  const variants = {
    Automatic: null, Upright: 'normal', Bold: 'bold', Italic: 'italic', BoldItalic: 'bold-italic',
    SansSerif: 'sans-serif', SansSerifBold: 'bold-sans-serif', SansSerifItalic: 'sans-serif-italic',
    SansSerifBoldItalic: 'sans-serif-bold-italic', Monospace: 'monospace',
    Calligraphic: '-tex-calligraphic', Script: 'script', Fraktur: 'fraktur',
    BoldFraktur: 'bold-fraktur', Blackboard: 'double-struck'
  };
  let active = null;
  const texInput = doc.inputJax.find(input => input.name === 'TeX');
  const tokenFactory = texInput.parseOptions.nodeFactory;
  const createToken = tokenFactory.get('token');
  tokenFactory.set('token', (factory, kind, attributes, text) => {
    const node = createToken(factory, kind, attributes, text);
    if (active && node.isToken) {
      const variant = factory.configuration.parser.stack.env.font;
      const explicit = node.attributes.getExplicit('mathvariant');
      if (variant && !(typeof explicit === 'string' && explicit.startsWith('-'))) {
        node.attributes.set('mathvariant', variant);
        node.setProperty('officeLocalVariant', variant);
      }
    }
    return node;
  });

  const isCjk = character => /[\p{Script=Han}\u3000-\u303f\uff01-\uff60\uffe0-\uffe6]/u.test(character);
  const physicalStyle = variant => (variant.includes('bold') ? 1 : 0) | (/italic|mathit/.test(variant) ? 2 : 0);
  function hasMathGlyphs(text, variant) {
    return Array.from(text).every(character => {
      const code = character.codePointAt(0);
      const data = jax.font.getChar(variant, code);
      const key = variant + ':' + code;
      if (data && jax.font.getChar(variant, data[3]?.smp || code)) {
        if (active.typography.SymbolFontId === 'mathjax-tex' && supplementalGlyphs.has(key))
          active.warnings.add('TeX 未覆盖的 ' + variant + ' 字形使用 STIX2 数学字体补充。');
        return true;
      }
      if (active.typography.SymbolFontId !== 'mathjax-tex') return false;
      const supplement = fonts.get('mathjax-stix2');
      if (!supplement.getVariant(variant)) return false;
      const replacement = supplement.getChar(variant, code);
      const target = replacement?.[3]?.smp || code;
      const outline = replacement && supplement.getChar(variant, target);
      if (!outline) return false;
      jax.font.defineChars(variant, {[code]: replacement, [target]: outline});
      supplementalGlyphs.add(key);
      active.warnings.add('TeX 未覆盖的 ' + variant + ' 字形使用 STIX2 数学字体补充。');
      return true;
    });
  }
  function runsFor(node, variant) {
    const text = node.getText(), style = physicalStyle(variant), typography = active.typography;
    if (!text) return [];
    let segments = [];
    if (node.kind === 'mtext' || Array.from(text).some(isCjk)) {
      for (const character of text) {
        const family = isCjk(character) ? typography.CjkFontFamily : 'Times New Roman';
        const last = segments[segments.length - 1];
        if (last && last.family === family) last.text += character;
        else segments.push({text: character, family, style});
      }
    } else if (node.kind === 'mn' && typography.NumberFontFamily) {
      if (['normal', 'bold', 'italic', 'bold-italic', '-tex-mathit'].includes(variant))
        segments = [{text, family: typography.NumberFontFamily, style}];
      else active.warnings.add('数字的局部数学样式 ' + variant + ' 使用数学字体字形。');
    }
    if (!segments.length && ['mi', 'mn'].includes(node.kind) && !hasMathGlyphs(text, variant)) {
      const family = variant.includes('sans-serif') ? 'Arial' : variant === 'monospace' ? 'Consolas'
        : ['normal', 'bold', 'italic', 'bold-italic', '-tex-mathit'].includes(variant) ? 'Times New Roman' : null;
      if (family) {
        segments = [{text, family, style}];
        active.warnings.add(typography.SymbolFontId + ' 缺少 ' + variant + ' 字形，使用 ' + family + ' 轮廓。');
      }
    }
    return segments.map(run => {
      const key = JSON.stringify([run.text, run.family, run.style]);
      active.runs.set(key, {...run, key});
      return key;
    });
  }
  function apply(math) {
    if (!active) return;
    if (!math.root.attributes.hasExplicit('mathcolor')) math.root.attributes.set('mathcolor', active.typography.Color);
    math.root.walkTree(node => {
      if (!node.isToken) return;
      const attrs = node.attributes;
      const local = node.getProperty('officeLocalVariant');
      if (local) attrs.set('mathvariant', local);
      else if (node.kind !== 'mtext' && !attrs.hasExplicit('mathvariant')) {
        // Explicit style inherited from a MathML ancestor also outranks formula defaults.
        let ancestor = node.parent, inherited = false;
        while (ancestor) {
          if (ancestor.attributes?.hasExplicit('mathvariant')) { inherited = true; break; }
          ancestor = ancestor.parent;
        }
        const variant = variants[active.typography.DefaultMathStyle];
        if (variant && !inherited) attrs.set('mathvariant', variant);
      }
      const keys = runsFor(node, attrs.get('mathvariant') || 'normal');
      if (keys.length) node.setProperty('officeFontRuns', keys);
    });
  }
  const action = doc.renderActions.constructor.action('office-typography', [21, () => {}, apply, true]);
  doc.renderActions.add(...action);

  // All metrics and SVG paths come from the same precomputed runs. No post-layout font replacement.
  for (const kind of ['mi', 'mn', 'mtext']) {
    const Base = jax.factory.getNodeClass(kind);
    jax.factory.setNodeClass(kind, class extends Base {
      get officeRuns() {
        const keys = this.node.getProperty('officeFontRuns');
        if (!keys || !active?.outlines) return null;
        return keys.map(key => {
          const run = active.outlines[key];
          if (!run) throw new Error('Missing measured font run: ' + key);
          return run;
        });
      }
      computeBBox(box, recompute) {
        const runs = this.officeRuns;
        if (!runs) return super.computeBBox(box, recompute);
        box.empty();
        box.w = 0; box.h = 0; box.d = 0;
        for (const run of runs) {
          box.h = Math.max(box.h, run.Height); box.d = Math.max(box.d, run.Depth);
          box.w += run.Advance;
        }
        box.clean();
      }
      toSVG(parents) {
        const runs = this.officeRuns;
        if (!runs) return super.toSVG(parents);
        const nodes = this.standardSvgNodes(parents);
        let x = 0;
        for (const run of runs) {
          for (const parent of nodes) {
            const path = this.svg('path', {d: run.Path, 'data-font-family': run.ActualFamily});
            this.adaptor.append(parent, path);
            this.place(x, 0, path);
          }
          x += run.Advance;
        }
      }
    });
  }

  async function selectFont(id) {
    if (!LaTeXSnipperMathJaxConfig.fonts.includes(id)) throw new Error('Unsupported math font: ' + id);
    if (!fonts.size) {
      await MathJax.loader.load('[mathjax-mhchem-extension]/svg');
      const tex = new originalTexFont.constructor({...originalTexFont.options});
      await MathJax.loader.load('[fonts]/mathjax-stix2-font/svg');
      const Font = MathJax._.output.fonts['mathjax-stix2'].svg_ts.MathJaxStix2Font;
      const stix = new Font({dynamicPrefix: '[fonts]/mathjax-stix2-font/svg/dynamic'});
      const configured = MathJax.config.svg.font;
      jax.font = stix;
      try { MathJax.config.svg.font = 'mathjax-stix2'; MathJax._.output.fonts['mathjax-mhchem'].svg.install(); }
      finally { MathJax.config.svg.font = configured; }
      fonts.set('mathjax-tex', tex);
      fonts.set('mathjax-stix2', stix);
    }
    jax.font = fonts.get(id);
  }

  function execute(input, outlines) {
    return LaTeXSnipperMathJax.enqueue(async () => {
      const savedFont = jax.font;
      const overflow = jax.options.displayOverflow;
      active = {typography: input.typography, outlines, runs: new Map(), warnings: new Set()};
      try {
        if (!(input.typography.DefaultMathStyle in variants)) throw new Error('Unsupported math style');
        await selectFont(input.typography.SymbolFontId);
        jax.options.displayOverflow = 'overflow';
        const isMathml = LaTeXSnipperMathJax.isMathMl(input.latex);
        const source = isMathml ? LaTeXSnipperMathJax.mathMlElement(input.latex) : LaTeXSnipperOfficeMath.preprocessTexSource(input.latex);
        const options = {format: isMathml ? 'MathML' : 'TeX', display: input.displayMode !== 'Inline'};
        // Each Office formula is independent, including the two conversion passes below.
        texInput.reset();
        const root = await doc.convertPromise(source, {...options, end: 100});
        const Visitor = MathJax._.core.MmlTree.SerializedMmlVisitor.SerializedMmlVisitor;
        const semantic = new DOMParser().parseFromString(new Visitor().visitTree(root), 'application/xml');
        const publicVariants = {'-tex-mathit': 'italic', '-tex-calligraphic': 'script',
          '-tex-bold-calligraphic': 'bold-script', '-tex-oldstyle': 'normal', '-tex-bold-oldstyle': 'bold', '-tex-variant': 'normal'};
        for (const node of semantic.querySelectorAll('[mathvariant]')) {
          const variant = publicVariants[node.getAttribute('mathvariant')];
          if (variant) node.setAttribute('mathvariant', variant);
        }
        const mathml = new XMLSerializer().serializeToString(semantic.documentElement);
        if (mathml.includes('<merror')) throw new Error('Formula parse error: ' + mathml);
        if (!outlines) return {runs: Array.from(active.runs.values()), mathml, warnings: Array.from(active.warnings)};
        texInput.reset();
        const container = await doc.convertPromise(source, options);
        const adaptor = MathJax.startup.adaptor, svg = adaptor.firstChild(container);
        const unresolved = adaptor.tags(svg, 'text');
        if (unresolved.length) throw new Error('Unsupported font glyph (' + input.typography.SymbolFontId + ', '
          + input.typography.DefaultMathStyle + '): ' + unresolved.map(node => adaptor.outerHTML(node)).join(' '));
        const box = adaptor.getAttribute(svg, 'viewBox').trim().split(/\s+/).map(Number);
        // Include real ink overhang (also present in built-in large operators) in the natural viewport.
        // This adjusts bounds only; glyph selection, metrics and placement have already finished.
        container.style.position = 'absolute'; container.style.visibility = 'hidden';
        document.body.appendChild(container);
        try {
          const ink = svg.getBBox();
          const right = Math.max(box[0] + box[2], ink.x + ink.width);
          const bottom = Math.max(box[1] + box[3], ink.y + ink.height);
          box[0] = Math.min(box[0], ink.x); box[1] = Math.min(box[1], ink.y);
          box[2] = right - box[0]; box[3] = bottom - box[1];
        } finally { container.remove(); }
        const points = input.typography.FontSizePoints / 1000;
        const widthPoints = box[2] * points, heightPoints = box[3] * points;
        const baselinePoints = (box[1] + box[3]) * points;
        adaptor.setAttribute(svg, 'viewBox', box.join(' '));
        adaptor.setAttribute(svg, 'width', widthPoints + 'pt');
        adaptor.setAttribute(svg, 'height', heightPoints + 'pt');
        adaptor.setAttribute(svg, 'style', 'vertical-align: ' + (-baselinePoints) + 'pt;');
        return {svg: adaptor.outerHTML(svg), mathml, widthPoints, heightPoints, baselinePoints,
          version: MathJax.version, warnings: Array.from(active.warnings)};
      } finally { texInput.reset(); active = null; jax.font = savedFont; jax.options.displayOverflow = overflow; }
    });
  }
  globalThis.LaTeXSnipperOfficeTypography = {prepare: input => execute(input, null), render: execute};
  return {ready: true};
})()
