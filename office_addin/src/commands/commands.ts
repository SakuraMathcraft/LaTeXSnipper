import { enqueueRibbonCommand, RibbonCommandName } from "../services/ribbonCommands";

function complete(event: Office.AddinCommands.Event): void {
  try {
    event.completed();
  } catch {
    // Older command runtimes may not expose completed during manual testing.
  }
}

function publish(name: RibbonCommandName, event: Office.AddinCommands.Event): void {
  enqueueRibbonCommand(name)
    .catch(() => undefined)
    .finally(() => complete(event));
  tryShowTaskpane();
}

function tryShowTaskpane(): void {
  const officeWithAddin = Office as typeof Office & {
    addin?: { showAsTaskpane?: () => Promise<void> };
  };
  officeWithAddin.addin?.showAsTaskpane?.().catch(() => undefined);
}

const openEditorCommand = (event: Office.AddinCommands.Event): void => {
  tryShowTaskpane();
  complete(event);
};
const insertFormulaCommand = (event: Office.AddinCommands.Event): void => publish("insert", event);
const screenshotOcrCommand = (event: Office.AddinCommands.Event): void => publish("ocr", event);
const numberedFormulaCommand = (event: Office.AddinCommands.Event): void => publish("numbered", event);
const loadSelectedCommand = (event: Office.AddinCommands.Event): void => publish("loadSelected", event);
const deleteSelectedCommand = (event: Office.AddinCommands.Event): void => publish("deleteSelected", event);
const renumberCommand = (event: Office.AddinCommands.Event): void => publish("renumber", event);

Office.onReady(() => {
  Office.actions.associate("openEditorCommand", openEditorCommand);
  Office.actions.associate("insertFormulaCommand", insertFormulaCommand);
  Office.actions.associate("screenshotOcrCommand", screenshotOcrCommand);
  Office.actions.associate("numberedFormulaCommand", numberedFormulaCommand);
  Office.actions.associate("loadSelectedCommand", loadSelectedCommand);
  Office.actions.associate("deleteSelectedCommand", deleteSelectedCommand);
  // Route cached manifests that still expose the former command to deletion.
  Office.actions.associate("updateSelectedCommand", deleteSelectedCommand);
  Office.actions.associate("renumberCommand", renumberCommand);
});
