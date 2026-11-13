const VISIBLE_MATH_SPACE = "\\,";
const MULTILINE_TEMPLATE = "\\begin{aligned}#@\\\\#?\\end{aligned}";
const menuDefaults = new WeakMap();
const suggestionPopoverRemovers = new WeakMap();

function keepSuggestionPopoverDuringNavigation(popover) {
  let originalRemove = suggestionPopoverRemovers.get(popover);
  if (originalRemove) {
    return originalRemove;
  }

  originalRemove = popover.remove.bind(popover);
  suggestionPopoverRemovers.set(popover, originalRemove);
  Object.defineProperty(popover, 'remove', {
    configurable: true,
    value() {
      if (popover.dataset.keepDuringNavigation === 'true') {
        return;
      }
      return originalRemove();
    }
  });
  return originalRemove;
}

function navigateSuggestion(field, command) {
  const popover = document.getElementById('mathlive-suggestion-popover');
  if (!popover) {
    field.executeCommand(command);
    return;
  }

  const originalRemove = keepSuggestionPopoverDuringNavigation(popover);
  popover.dataset.keepDuringNavigation = 'true';
  try {
    field.executeCommand(command);
  } finally {
    popover.dataset.keepDuringNavigation = 'false';
    if (popover.isConnected) {
      // MathLive increments its private reference count while rebuilding the
      // menu. Restore the steady-state count so a later dismiss can remove it.
      if (popover.querySelector('li')) {
        popover.dataset.refcount = '1';
      } else {
        originalRemove();
      }
    }
  }
}

export function configureMathfieldMenu(mathfield, locale, performEdit) {
  const defaults = menuDefaults.get(mathfield) || mathfield.menuItems;
  menuDefaults.set(mathfield, defaults);
  const item = id => defaults.find(entry => entry.id === id);
  const color = item('color');
  const paste = item('paste');
  const labels = String(locale).startsWith('zh')
    ? {color: '局部上色', cut: '剪切', paste: '粘贴', 'select-all': '全选'}
    : {color: 'Color', cut: 'Cut', paste: 'Paste', 'select-all': 'Select All'};
  mathfield.menuItems = [
    {...color, label: labels.color, submenu: color.submenu.map(swatch => ({
      ...swatch,
      onMenuSelect: props => performEdit(() => swatch.onMenuSelect(props))
    }))},
    {...item('cut'), label: labels.cut},
    {...paste, label: labels.paste, onMenuSelect: async () => {
      try {
        const text = await navigator.clipboard.readText();
        // MathLive puts display delimiters on the plain-text clipboard when cutting a selection.
        const copiedFormula = /^\$\$\s*([\s\S]*?)\s*\$\$$/.exec(text.trim());
        performEdit(() => mathfield.insert(copiedFormula ? copiedFormula[1] : text,
          {format: 'latex', insertionMode: 'replaceSelection'}));
      } catch {
        paste.onMenuSelect();
      }
    }},
    {...item('select-all'), label: labels['select-all']}
  ];
}
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
  const bind = field => {
    let releaseTab = false;
    field.mathModeSpace = VISIBLE_MATH_SPACE;
    field.addEventListener('focusout', () => { releaseTab = false; });
    field.addEventListener("keydown", (event) => {
      if (event.isComposing || event.keyCode === 229) return;
      if (field.mode === 'latex' && !event.altKey && !event.ctrlKey && !event.metaKey
          && (event.key === 'ArrowDown' || event.key === 'ArrowUp')
          && document.getElementById('mathlive-suggestion-popover')?.classList.contains('is-visible')) {
        event.preventDefault();
        event.stopImmediatePropagation();
        navigateSuggestion(field, event.key === 'ArrowDown' ? 'nextSuggestion' : 'previousSuggestion');
        return;
      }
      const leaveEditor = releaseTab && event.key === 'Tab';
      releaseTab = event.key === 'Escape';
      if (leaveEditor) {
        // Like CodeMirror: Escape then Tab leaves the editor without inserting content.
        event.stopImmediatePropagation();
        return;
      }
      if (event.key === 'Tab' && !event.altKey && !event.ctrlKey && !event.metaKey
          && !event.isComposing && !field.readOnly && field.mode !== 'latex') {
        event.preventDefault();
        event.stopImmediatePropagation();
        field.executeCommand(event.shiftKey ? 'moveToPreviousPlaceholder' : 'moveToNextPlaceholder');
        return;
      }
      const shortcut = event.ctrlKey && !event.altKey && !event.metaKey && !event.shiftKey
        ? shortcuts.get(event.key.toLowerCase())
        : null;
      if (shortcut && !event.isComposing && field.mode !== "latex") {
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

      if (!event.shiftKey && field.mode === "latex") {
        return;
      }

      event.preventDefault();
      event.stopImmediatePropagation();
      if (event.shiftKey) {
        onAccept();
        return;
      }

      performEdit(() => addRow(field));
    }, true);
  };
  bind(mathfield);
  return bind;
}

