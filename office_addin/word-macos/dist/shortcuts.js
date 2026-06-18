export function shouldInsertFormulaShortcut(event) {
  return Boolean(event?.metaKey) && !event?.ctrlKey && event?.key === "Enter";
}

export function shouldClearInputShortcut(event) {
  return Boolean(event?.metaKey) && !event?.ctrlKey && String(event?.key ?? "").toLowerCase() === "k";
}
