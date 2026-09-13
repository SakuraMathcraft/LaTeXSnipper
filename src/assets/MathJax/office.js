// Office input normalization. Desktop exports intentionally do not use this adapter.
globalThis.LaTeXSnipperOfficeMath = {
  convert(input) {
    const source = String(input.latex || '');
    const isMathMl = /^(<\?xml[\s\S]*?\?>\s*)?<([a-z_][\w.-]*:)?math(\s|>)/i.test(source.trim());
    return LaTeXSnipperMathJax.convert({...input,
      latex: isMathMl ? source : this.preprocessTexSource(source)});
  },
  readGroup: function(source, start) {
    if (source[start] !== '{') {
      return null;
    }
    let depth = 0;
    for (let index = start; index < source.length; index += 1) {
      if (source[index] === '\\') {
        index += 1;
        continue;
      }
      if (source[index] === '{') {
        depth += 1;
      } else if (source[index] === '}') {
        depth -= 1;
        if (depth === 0) {
          return {
            content: source.slice(start + 1, index),
            end: index + 1
          };
        }
      }
    }
    return null;
  },
  preprocessTexSource: function(source) {
    const normalized = source.replace(/(^|[^\\])\$/g, '$1');
    const command = '\\colorbox';
    let result = '';
    let cursor = 0;
    while (cursor < normalized.length) {
      const commandIndex = normalized.indexOf(command, cursor);
      if (commandIndex < 0) {
        result += normalized.slice(cursor);
        break;
      }
      result += normalized.slice(cursor, commandIndex);
      let groupStart = commandIndex + command.length;
      while (/\s/.test(normalized[groupStart] || '')) {
        groupStart += 1;
      }
      const color = this.readGroup(normalized, groupStart);
      if (!color) {
        result += command;
        cursor = commandIndex + command.length;
        continue;
      }
      groupStart = color.end;
      while (/\s/.test(normalized[groupStart] || '')) {
        groupStart += 1;
      }
      const body = this.readGroup(normalized, groupStart);
      if (!body) {
        result += normalized.slice(commandIndex, color.end);
        cursor = color.end;
        continue;
      }
      let bodyContent = body.content.trim();
      if (bodyContent.length >= 2 && bodyContent[0] === '$' && bodyContent[bodyContent.length - 1] === '$') {
        bodyContent = bodyContent.slice(1, -1);
      }
      const bodyLatex = this.preprocessTexSource(bodyContent);
      result += '\\bbox[' + color.content.trim() + ']{' + bodyLatex + '}';
      cursor = body.end;
    }
    return result;
  }
};
