import { enqueueRibbonCommand, RibbonCommandName } from "../services/ribbonCommands";

function complete(event: Office.AddinCommands.Event): void {
  event.completed();
}

function publish(name: RibbonCommandName, event: Office.AddinCommands.Event): void {
  void enqueueRibbonCommand(name).finally(() => complete(event));
  showTaskpane();
}

function showTaskpane(): void {
  const officeWithAddin = Office as typeof Office & {
    addin: { showAsTaskpane: () => Promise<void> };
  };
  void officeWithAddin.addin.showAsTaskpane();
}

const openEditorCommand = (event: Office.AddinCommands.Event): void => publish("editor", event);
const insertFormulaCommand = (event: Office.AddinCommands.Event): void => publish("insert", event);
const screenshotOcrCommand = (event: Office.AddinCommands.Event): void => publish("ocr", event);
const numberedFormulaCommand = (event: Office.AddinCommands.Event): void => publish("numbered", event);
const loadSelectedCommand = (event: Office.AddinCommands.Event): void => publish("loadSelected", event);
const deleteSelectedCommand = (event: Office.AddinCommands.Event): void => publish("deleteSelected", event);
const renumberCommand = (event: Office.AddinCommands.Event): void => publish("renumber", event);
const helpCommand = (event: Office.AddinCommands.Event): void => publish("help", event);

Office.onReady(() => {
  Office.actions.associate("openEditorCommand", openEditorCommand);
  Office.actions.associate("insertFormulaCommand", insertFormulaCommand);
  Office.actions.associate("screenshotOcrCommand", screenshotOcrCommand);
  Office.actions.associate("numberedFormulaCommand", numberedFormulaCommand);
  Office.actions.associate("loadSelectedCommand", loadSelectedCommand);
  Office.actions.associate("deleteSelectedCommand", deleteSelectedCommand);
  Office.actions.associate("renumberCommand", renumberCommand);
  Office.actions.associate("helpCommand", helpCommand);
});
