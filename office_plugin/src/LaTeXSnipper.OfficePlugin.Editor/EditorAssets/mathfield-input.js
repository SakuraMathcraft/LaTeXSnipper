(function () {
  "use strict";

  const VISIBLE_MATH_SPACE = "\\,";
  const MULTILINE_TEMPLATE = "\\begin{aligned}#@\\\\#?\\end{aligned}";

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
    mathfield.addEventListener("keydown", (event) => {
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

  window.LaTeXSnipperMathfieldInput = Object.freeze({ configure, insertTemplate });
})();
