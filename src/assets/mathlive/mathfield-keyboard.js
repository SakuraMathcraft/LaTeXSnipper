const NAVIGATION_COMMANDS = Object.freeze({
  ArrowLeft: 'moveToPreviousChar',
  ArrowRight: 'moveToNextChar',
  ArrowUp: 'moveUp',
  ArrowDown: 'moveDown',
});

const LATEX_NAVIGATION_COMMANDS = Object.freeze({
  ArrowUp: 'previousSuggestion',
  ArrowDown: 'nextSuggestion',
});

export function routeMathfieldNavigationKey(mathfield, event) {
  if (!mathfield || event.isComposing) return false;

  const command = mathfield.mode === 'latex'
    ? LATEX_NAVIGATION_COMMANDS[event.key] ?? NAVIGATION_COMMANDS[event.key]
    : NAVIGATION_COMMANDS[event.key];
  if (!command) return false;

  event.preventDefault();
  event.stopImmediatePropagation();
  mathfield.executeCommand(command);
  return true;
}
