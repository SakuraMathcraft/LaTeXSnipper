const VISIBLE_MATH_SPACE = "\\,";
const MULTILINE_TEMPLATE = "\\begin{aligned}#@\\\\#?\\end{aligned}";
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

export function configureMathfield(mathfield, {onAccept, insert, shortcuts, performEdit}) {
  let releaseTab = false;
  mathfield.addEventListener('focusout', () => { releaseTab = false; });
  mathfield.mathModeSpace = VISIBLE_MATH_SPACE;
  document.addEventListener("menu-select", (event) => {
    const command = MATRIX_MENU_COMMANDS[event.detail?.id];
    if (!command) {
      return;
    }

    event.preventDefault();
    performEdit(() => mathfield.executeCommand(command));
    mathfield.focus();
  });
  mathfield.addEventListener("keydown", (event) => {
    if (event.isComposing || event.keyCode === 229) return;
    const leaveEditor = releaseTab && event.key === 'Tab';
    releaseTab = event.key === 'Escape';
    if (leaveEditor) {
      // Like CodeMirror: Escape then Tab leaves the editor without inserting content.
      event.stopImmediatePropagation();
      return;
    }
    if (event.key === 'Tab' && !event.altKey && !event.ctrlKey && !event.metaKey
        && !event.isComposing && !mathfield.readOnly && mathfield.mode !== 'latex') {
      event.preventDefault();
      event.stopImmediatePropagation();
      mathfield.executeCommand(event.shiftKey ? 'moveToPreviousPlaceholder' : 'moveToNextPlaceholder');
      return;
    }
    const shortcut = event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey
      ? shortcuts.get(event.key.toLowerCase())
      : null;
    if (shortcut && !event.isComposing && mathfield.mode !== "latex") {
      event.preventDefault();
      event.stopImmediatePropagation();
      insert(shortcut);
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

    performEdit(() => addRow(mathfield));
  }, true);
}

