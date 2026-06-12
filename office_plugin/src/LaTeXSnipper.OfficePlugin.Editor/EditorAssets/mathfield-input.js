(function () {
  "use strict";

  const VISIBLE_MATH_SPACE = "\\,";
  const MULTILINE_TEMPLATE = "\\begin{aligned}#@\\\\#?\\end{aligned}";
  const TEMPLATE_SHORTCUTS = Object.freeze({
    f: "\\frac{#0}{#?}",
    r: "\\sqrt{#0}",
    h: "#0^{#?}",
    l: "#0_{#?}",
    j: "#0_{#?}^{#?}",
  });
  const MATRIX_MENU_COMMANDS = Object.freeze({
    "add-row-before": "addRowBefore",
    "add-row-after": "addRowAfter",
    "add-column-before": "addColumnBefore",
    "add-column-after": "addColumnAfter",
    "delete-row": "removeRow",
    "delete-column": "removeColumn",
  });

  function latex(mathfield) {
    return mathfield.getValue("latex-expanded");
  }

  function addRow(mathfield) {
    const before = latex(mathfield);
    mathfield.executeCommand("addRowAfter");
    if (latex(mathfield) !== before) {
      return;
    }

    mathfield.executeCommand("selectAll");
    mathfield.insert(MULTILINE_TEMPLATE, {
      format: "latex",
      insertionMode: "replaceSelection",
      selectionMode: "placeholder",
    });
  }

  function configure(mathfield, onAccept) {
    mathfield.mathModeSpace = VISIBLE_MATH_SPACE;
    document.addEventListener("menu-select", (event) => {
      const command = MATRIX_MENU_COMMANDS[event.detail?.id];
      if (!command) {
        return;
      }

      event.preventDefault();
      mathfield.executeCommand(command);
      mathfield.focus();
    });
    mathfield.addEventListener("keydown", (event) => {
      const shortcut = event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey
        ? TEMPLATE_SHORTCUTS[event.key.toLowerCase()]
        : null;
      if (shortcut && !event.isComposing && mathfield.mode !== "latex") {
        event.preventDefault();
        event.stopImmediatePropagation();
        insertTemplate(mathfield, shortcut);
        return;
      }

      if (
        event.key !== "Enter"
        || event.isComposing
        || event.altKey
        || event.ctrlKey
        || event.metaKey
      ) {
        return;
      }

      if (!event.shiftKey && mathfield.mode === "latex") {
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();
      if (event.shiftKey) {
        onAccept();
        return;
      }

      addRow(mathfield);
    }, true);
  }

  function insertTemplate(mathfield, template) {
    mathfield.insert(template, {
      format: "latex",
      insertionMode: "replaceSelection",
      selectionMode: "placeholder",
    });
    mathfield.focus();
  }

  function setDefaultFontStyle(mathfield, fontStyle) {
    if (fontStyle === "TeX") {
      mathfield.onInsertStyle = undefined;
      return;
    }

    const style = {
      RomanUpright: { variant: "normal", variantStyle: "up" },
      Bold: { variant: "normal", variantStyle: "bold" },
      Italic: { variant: "main", variantStyle: "italic" },
    }[fontStyle];
    if (!style) {
      mathfield.onInsertStyle = undefined;
      return;
    }

    mathfield.onInsertStyle = () => ({ ...style });
    mathfield.applyStyle(style);
  }

  function setDefaultColor(mathfield, fontColor) {
    const color = /^#[0-9a-f]{6}$/i.test(String(fontColor || ""))
      ? String(fontColor).toUpperCase()
      : "#000000";
    mathfield.style.color = color;
    const red = Number.parseInt(color.slice(1, 3), 16);
    const green = Number.parseInt(color.slice(3, 5), 16);
    const blue = Number.parseInt(color.slice(5, 7), 16);
    const luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255;
    mathfield.style.backgroundColor = luminance > 0.72 ? "#202124" : "#FFFFFF";
  }

  window.LaTeXSnipperMathfieldInput = Object.freeze({
    configure,
    insertTemplate,
    setDefaultColor,
    setDefaultFontStyle,
  });
})();
