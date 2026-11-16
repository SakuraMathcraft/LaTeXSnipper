// Ribbon commands, task pane, dialogs and OCR for Word and PowerPoint on Mac,
// following WordPluginController / PowerPointPluginController and the
// *RibbonCallbacks command wrapper. Runs in the shared runtime that
// taskpane.html hosts for the whole session.
/* global Office */
import {api, ApiError, catalog, loadSettings} from './api.mjs';
import {startRenderer} from './renderer.mjs';
import {describeError, text} from './strings.mjs';
import {PowerPointCommands} from './powerpoint/commands.mjs';
import {WordCommands} from './word/commands.mjs';

const OCR_TIMEOUT_SECONDS = 120;
const OCR_POLL_MS = 250;
const DIALOG_CLOSE_SETTLE_MS = 1000;
const DIALOG_ALREADY_OPEN = 12007;
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));

export class Controller {
  constructor(hostName, pane) {
    this.host = hostName === Office.HostType.Word ? 'word' : 'powerpoint';
    this.locale = String(Office.context.displayLanguage || 'zh-CN');
    this.t = (key, values) => text(this.locale, this.host, key, values);
    this.commands = this.host === 'word' ? new WordCommands(this.t) : new PowerPointCommands(this.t);
    this.pane = pane;
    this.busy = false;
    this.ocr = null;
    this.dialog = null;
    this.session = 0;
    this.editor = null;
    this.savedDraft = null;
  }

  start() {
    const word = this.host === 'word';
    const commands = word ? {
      insertInline: () => this.openEditor({display: false, numberingMode: 'None', numberText: ''}),
      insertDisplay: () => this.openEditor({display: true, numberingMode: 'None', numberText: ''}),
      insertNumbered: () => this.openEditor(this.numberedOptions()),
      loadSelected: () => this.loadSelected(),
      deleteSelected: () => this.serial(() => this.deleteSelected()),
      parseSelected: () => this.serial(() => this.parse(false)),
      parseAll: () => this.serial(() => this.parse(true)),
      insertReference: () => this.serial(async () => this.report('info', await this.commands.insertReferencePlaceholder())),
      addNumber: () => this.serial(async () => this.report('info', await this.commands.addNumber(await this.options()))),
      renumberAll: () => this.serial(() => this.renumber()),
      insertChapterBoundary: () => this.serial(() => this.insertBoundary('chapter')),
      insertSectionBoundary: () => this.serial(() => this.insertBoundary('section')),
    } : {
      insertFormula: () => this.openEditor({}),
      loadSelected: () => this.loadSelected(),
      deleteSelected: () => this.serial(() => this.deleteSelected()),
      convertToPng: () => this.serial(() => this.convert('Png')),
      convertToSvg: () => this.serial(() => this.convert('Svg')),
    };
    Object.assign(commands, {
      screenshotOcr: () => this.toggleOcr(),
      formatSelected: () => this.serial(() => this.format(false)),
      formatAll: () => this.serial(() => this.format(true)),
      showTaskPane: () => this.showPane().then(() => this.status('info', this.t('TaskPaneShownStatus'))),
      openSettings: () => this.openDialog('settings.html', 60, 80).then(() => this.status('info', this.t('SettingsStatus'))),
      openHelp: () => this.openDialog('help.html', 80, 80).then(() => this.status('info', this.t('HelpStatus'))),
    });
    for (const [name, command] of Object.entries(commands)) {
      Office.actions.associate(name, event => {
        // Commands only start work; results are reported in the pane.
        Promise.resolve().then(command).catch(error => this.fail(error));
        event.completed();
      });
    }
    this.pane.configure({
      strings: this.paneStrings(),
      locale: this.locale,
      onInsert: state => this.serial(() => this.insertFromPane(state)),
      onConnect: () => this.serial(() => this.testConnection()),
      onOcr: () => this.toggleOcr(),
    });
    if (word) {
      Office.context.document.addHandlerAsync(Office.EventType.DocumentSelectionChanged, () => this.completeReference());
    }
    this.pane.status({kind: 'info', message: this.t('ReadyStatus'), busy: false, ocrActive: false});
    startRenderer().catch(error => this.fail(error));
  }

  paneStrings() {
    const keys = {officePlugin: 'OfficePluginLabel', connect: 'ConnectButton', equation: 'EquationLabel',
      screenshotOcr: 'ScreenshotOcrButton', cancelOcr: 'CancelOcrButton', insert: 'EditorInsert'};
    if (this.host === 'word') Object.assign(keys, {display: 'DisplayOption', autoNumber: 'AutoNumberOption',
      manualNumber: 'ManualNumberPlaceholder'});
    return Object.fromEntries(Object.entries(keys).map(([key, id]) => [key, this.t(id)]));
  }

  // Status ----------------------------------------------------------------------------

  showPane() {
    return Office.addin.showAsTaskpane().catch(() => {});
  }

  /** Every status makes the pane visible, like the Windows Visible*StatusSink. */
  status(kind, message) {
    this.pane.status({kind, message, busy: this.busy, ocrActive: Boolean(this.ocr)});
    this.showPane();
  }

  report(kind, key, values) {
    this.status(kind, this.t(key, values));
  }

  fail(error) {
    this.status('error', describeError(error));
  }

  /**
   * RunSerialAsync: one document command at a time. A command that arrives
   * while another runs is dropped and "Working..." is shown.
   */
  async serial(command) {
    if (this.busy) {
      this.report('info', 'WorkingStatus');
      return;
    }
    this.busy = true;
    this.report('info', 'WorkingStatus');
    try {
      await command();
    } catch (error) {
      this.fail(error);
    } finally {
      this.busy = false;
      this.pane.status({busy: false, ocrActive: Boolean(this.ocr)});
    }
  }

  postBatch(result, keys) {
    // Windows OLE formulas that were left alone are reported with the result.
    const ole = result.ole ? ' ' + this.t('OleFormulasSkipped', {count: result.ole}) : '';
    const post = (kind, key, values) => this.status(kind, this.t(key, values) + ole);
    if (result.failed > 0) {
      post(result.succeeded ? 'info' : 'error', keys.failed, {total: result.total, succeeded: result.succeeded,
        failed: result.failed, skipped: result.skipped ?? 0, reason: result.reason});
    } else if (!result.succeeded) {
      post('info', keys.unchanged);
    } else {
      post('success', result.skipped ? keys.skipped : keys.changed, {count: result.succeeded, skipped: result.skipped});
    }
  }

  // Settings and formula defaults -------------------------------------------------------

  options() {
    return loadSettings(this.host);
  }

  /** ResolveForNewFormula: the preset, at the selection's text size when configured. */
  async newTypography() {
    const settings = await this.options();
    if (!settings.followHostFontSize) return settings.typography;
    const size = await this.commands.selectionFontSize().catch(() => 0);
    return size ? {...settings.typography, fontSizePoints: size} : settings.typography;
  }

  /** GetFormulaOptions: the pane's numbering, with Automatic for the Numbered Formula command. */
  paneOptions(state = this.pane.state()) {
    const manual = String(state.manualNumber || '').trim();
    const numberingMode = state.autoNumber ? 'Automatic' : manual ? 'Manual' : 'None';
    return {display: Boolean(state.display) || numberingMode !== 'None', numberingMode, numberText: manual};
  }

  numberedOptions() {
    const options = this.paneOptions();
    return options.numberingMode === 'None' ? {display: true, numberingMode: 'Automatic', numberText: ''} : options;
  }

  // Commands ----------------------------------------------------------------------------

  async insert(latex, typography, options) {
    if (this.host === 'word') {
      this.report('info', 'OmmlInsertingStatus');
      await this.commands.insert({latex, typography, ...options}, await this.options());
      return 'OmmlInsertedStatus';
    }
    const settings = await this.options();
    this.report('info', 'ConvertingStatus');
    return this.commands.insert({latex, typography, format: settings.insertionBackend});
  }

  async insertFromPane(state) {
    const options = this.host === 'word' ? this.paneOptions(state) : {};
    this.report('success', await this.insert(state.latex, await this.newTypography(), options));
  }

  async loadSelected() {
    if (this.busy) {
      this.report('info', 'WorkingStatus');
      return;
    }
    const target = await this.commands.loadSelected();
    this.savedDraft = this.pane.state();
    this.pane.load({latex: target.formula.latex, updateMode: true,
      display: target.formula.displayMode === 'Display', autoNumber: target.formula.numberingMode === 'Automatic',
      manualNumber: target.formula.numberText || ''});
    await this.openEditor(null, target);
    this.report('success', 'LoadedStatus');
  }

  restoreDraft() {
    if (!this.savedDraft) return;
    this.pane.load(this.savedDraft);
    this.savedDraft = null;
  }

  async deleteSelected() {
    const {count, ole} = await this.commands.deleteSelected();
    const message = this.t(count > 1 && this.host === 'powerpoint' ? 'DeletedManyStatus' : 'DeletedStatus', {count});
    this.status('success', ole ? `${message} ${this.t('OleFormulasSkipped', {count: ole})}` : message);
  }

  async format(all) {
    const settings = await this.options();
    const result = await this.commands.format(all, settings.typography, message => this.status('info', message));
    if (result.key) return this.report('info', result.key);
    this.postBatch(result, {failed: 'FormattedWithFailuresStatus', unchanged: 'NoFormattingNeededStatus',
      skipped: 'FormattedWithSkippedStatus', changed: 'FormattedStatus'});
  }

  async convert(format) {
    const result = await this.commands.convert(format, message => this.status('info', message));
    this.postBatch(result, {failed: 'ConvertedWithFailuresStatus', unchanged: 'NoConversionNeededStatus',
      skipped: 'ConvertedWithSkippedStatus', changed: 'ConvertedStatus'});
  }

  async parse(all) {
    const settings = await this.options();
    const result = await this.commands.parse(all, {pane: this.paneOptions(), settings, typography: settings.typography,
      followHostFontSize: settings.followHostFontSize}, message => this.status('info', message));
    if (result.key) return this.report('info', result.key);
    // Windows leaves parsed automatic numbers until "Renumber all"; Mac numbers them right away.
    if (result.automatic) await this.commands.renumber(settings);
    if (result.failed) {
      this.report(result.succeeded ? 'info' : 'error', 'ParsedWithFailuresStatus', {total: result.total,
        succeeded: result.succeeded, failed: result.failed, reason: describeError(result.reason)});
    } else {
      this.report('success', 'ParsedStatus', {count: result.succeeded});
    }
  }

  async renumber() {
    const {key, values} = await this.commands.renumber(await this.options());
    this.report(key === 'RenumberedStatus' ? 'success' : 'info', key, values);
  }

  async insertBoundary(kind) {
    this.report('success', await this.commands.insertBoundary(kind, await this.options()));
  }

  async completeReference() {
    if (this.busy || !this.commands.pendingReference) return;
    try {
      if (await this.commands.completeReference()) this.report('success', 'ReferenceInsertedStatus');
    } catch {
      // Like Windows, the request stays pending until a numbered formula is selected.
    }
  }

  async testConnection() {
    await api('/api/recognition/config');
    this.report('success', 'ConnectedAutomationStatus');
  }

  // OCR -----------------------------------------------------------------------------------

  async toggleOcr() {
    if (this.ocr) {
      const {jobId, controller} = this.ocr;
      this.ocr = null;
      controller.abort();
      if (jobId) await api(`/api/recognition/jobs/${encodeURIComponent(jobId)}`, {method: 'DELETE'}).catch(() => {});
      this.report('info', 'OcrCanceledStatus');
      return;
    }
    const state = {jobId: null, controller: new AbortController()};
    this.ocr = state;
    this.report('info', 'OcrWaitingStatus');
    try {
      const latex = await this.waitForOcr(state);
      if (this.ocr !== state) return;
      this.ocr = null;
      // OCR only fills the pane, like Windows; it never inserts.
      this.pane.load({...this.pane.state(), latex});
      this.report('success', 'OcrLoadedStatus');
    } catch (error) {
      if (this.ocr !== state || error?.name === 'AbortError') return;
      this.ocr = null;
      this.fail(error);
    }
  }

  async waitForOcr(state) {
    const created = await this.requestOcr(state);
    state.jobId = created?.job?.id;
    if (!state.jobId) throw new ApiError(502, 'invalid_response', this.t('InvalidResponse'));
    const deadline = Date.now() + (OCR_TIMEOUT_SECONDS + 10) * 1000;
    let announced = false;
    while (Date.now() < deadline) {
      await sleep(OCR_POLL_MS);
      if (this.ocr !== state) throw new DOMException('canceled', 'AbortError');
      const {job} = await api(`/api/recognition/jobs/${encodeURIComponent(state.jobId)}`, {signal: state.controller.signal});
      if (job.state === 'completed') {
        const item = (job.items || []).find(entry => String(entry.text || '').trim());
        if (!item) throw new ApiError(422, 'empty_formula', this.t('OcrEmpty'));
        return item.text;
      }
      if (job.state === 'failed' || job.state === 'canceled')
        throw new ApiError(422, job.error?.code || job.state, job.error?.message || this.t('OcrFailed'));
      if (!announced && (job.state === 'queued' || job.state === 'running')) {
        announced = true;
        this.report('info', 'OcrRecognizingStatus');
      }
    }
    throw new ApiError(504, 'timeout', this.t('OcrTimeout'));
  }

  async requestOcr(state) {
    try {
      return await api('/api/recognition/next', {method: 'POST', body: {timeout: OCR_TIMEOUT_SECONDS},
        signal: state.controller.signal});
    } catch (error) {
      if (error?.code === 'next_result_busy') throw new ApiError(409, error.code, this.t('AutomationOcrAlreadyWaiting'));
      throw error;
    }
  }

  // Editor --------------------------------------------------------------------------------

  /** Opens the editor for a new formula (`options`) or the loaded `target`. */
  async openEditor(options, target = null) {
    if (this.busy) {
      this.report('info', 'WorkingStatus');
      return;
    }
    const word = this.host === 'word';
    const typography = target ? target.formula.typography : await this.newTypography();
    const draft = this.pane.state();
    this.session += 1;
    this.editor = {session: this.session, options, target};
    const init = {
      type: 'init',
      session: this.session,
      typography,
      catalog: await catalog(),
      referencePreview: word,
      latex: target ? target.formula.latex : draft.latex,
      display: target ? target.formula.displayMode === 'Display' : word ? Boolean(options.display) : true,
      forceDisplay: !word,
      mode: target ? 'update' : 'insert',
      locale: this.locale,
    };
    await this.openDialog('editor.html', 62, 78, init);
    this.report('info', 'EditorReadyStatus');
  }

  async onEditorAccept(dialog, message) {
    const editor = this.editor;
    if (!editor || message.session !== editor.session) return;
    let key;
    try {
      if (this.busy) throw new Error(this.t('WorkingStatus'));
      this.busy = true;
      if (editor.target) {
        const {changed} = await this.commands.update(editor.target, {latex: message.latex, typography: message.typography});
        key = changed ? 'UpdatedStatus' : 'UnchangedStatus';
      } else {
        key = await this.insert(message.latex, message.typography, editor.options);
      }
    } catch (error) {
      this.fail(error);
      dialog.messageChild(JSON.stringify({type: 'submitFailed', session: message.session, message: describeError(error)}));
      return;
    } finally {
      this.busy = false;
      this.pane.status({busy: false});
    }
    this.editor = null;
    // Close the dialog that sent the message: Office for Mac can report a
    // dialog event for it first, which clears this.dialog.
    this.closeDialog(dialog);
    if (editor.target) this.restoreDraft();
    this.report(key === 'UnchangedStatus' ? 'info' : 'success', key);
  }

  onEditorCancel(dialog) {
    if (this.editor?.target) this.restoreDraft();
    this.editor = null;
    this.closeDialog(dialog);
  }

  // Dialogs -------------------------------------------------------------------------------

  async openDialog(page, width, height, init = null) {
    const replacing = Boolean(this.dialog);
    if (replacing) {
      // Office for Mac reports no close event and may accept a new dialog
      // before the old one is gone, orphaning it; give it time to close.
      this.closeDialog();
      await sleep(DIALOG_CLOSE_SETTLE_MS);
    }
    // A runtime that a ribbon command started without the pane cannot close
    // its first dialog on Word for Mac; showing the pane first avoids that
    // (Windows shows the pane for every command too).
    await this.showPane();
    const url = new URL(`./${page}`, location.href);
    url.search = new URLSearchParams({host: this.host, platform: this.host, locale: this.locale}).toString();
    let result;
    for (let attempt = 0; ; attempt++) {
      result = await new Promise(resolve =>
        Office.context.ui.displayDialogAsync(url.href, {width, height, displayInIframe: false}, resolve));
      if (result.status === Office.AsyncResultStatus.Succeeded) break;
      // Office needs a moment to tear down a dialog before it accepts another (12007).
      if (result.error?.code !== DIALOG_ALREADY_OPEN || attempt >= (replacing ? 20 : 3)) throw new Error(this.t('DialogFailed'));
      await sleep(150);
    }
    const dialog = result.value;
    this.dialog = dialog;
    dialog.addEventHandler(Office.EventType.DialogMessageReceived, event => {
      let message;
      try { message = JSON.parse(event.message); } catch { return; }
      if (message.type === 'ready' && init) dialog.messageChild(JSON.stringify(init));
      else if (message.type === 'accept') this.onEditorAccept(dialog, message);
      else if (message.type === 'cancel') this.onEditorCancel(dialog);
      else if (message.type === 'close') this.closeDialog(dialog);
      else if (message.type === 'settingsSaved') this.onSettingsSaved();
    });
    dialog.addEventHandler(Office.EventType.DialogEventReceived, () => {
      if (this.dialog !== dialog) return;
      this.dialog = null;
      if (this.editor?.target) this.restoreDraft();
      this.editor = null;
    });
  }

  /** Word re-applies numbering boundary visibility after a settings change. */
  async onSettingsSaved() {
    if (this.host !== 'word') return;
    try {
      await this.commands.applyBoundaryVisibility(await this.options());
    } catch (error) {
      this.fail(error);
    }
  }

  closeDialog(dialog = this.dialog) {
    if (this.dialog === dialog) this.dialog = null;
    try { dialog?.close(); } catch { /* already closed */ }
  }
}
