// Word commands, following WordPluginController and the Windows formula
// lifecycle. Formulas are OMML content controls with metadata in document
// variables (contract.mjs); paragraph-level changes rewrite the paragraph's
// own OOXML (ooxml.mjs) so user content around a formula stays as it was.
/* global Word */
import {api} from '../api.mjs';
import {newId, normalizeLatex, sameTypography} from '../metadata.mjs';
import {renderMathMl} from '../renderer.mjs';
import {
  BOUNDARY_TAGS, BOUNDARY_TITLE, BOOKMARK_PREFIX, REFERENCE_MARKER, bookmarkName, createFormula,
  equationIdFromTag, manualNumberText, numberStateAfter, numberStates, referenceCode,
  sequenceCode, sequenceResult,
} from './contract.mjs';
import {
  Variables, WordCommandError, boundaryKind, bodyControls, containsEmbeddedObject, controlByTag, countFormulasWithId,
  isBoundaryControl, isFormulaControl, oleFormulaCount, paragraphOoxml, replaceParagraphs, selectedFormulaControls,
  sequenceFields, styleControl, textWidthPoints,
} from './document.mjs';
import {
  automaticNumberXml, deleteFormulaXml, equationControl, extractOMath, flatPackage, formulaParagraph, manualNumberXml,
  paragraphHasContent, replaceFormulaXml,
} from './ooxml.mjs';
import {applyCandidates, findCandidates, paragraphGroups, processTag} from './parsing.mjs';

const BATCH_SIZE = 5;
const RELATIONS_BEFORE = new Set(['Before', 'AdjacentBefore']);
const RELATIONS_APART = new Set(['Before', 'After', 'Unrelated']);

const bookmarkId = () => 100000 + Math.floor(Math.random() * 2000000000);

/** LaTeX → semantic MathML (shared renderer) → OMML (Word's stylesheet, in the host) → one m:oMath. */
export async function renderEquation(formula) {
  const mathml = await renderMathMl(formula.latex, formula.displayMode === 'Display', formula.typography);
  const {omml} = await api('/api/omml', {method: 'POST', body: {mathml, typography: formula.typography}});
  return extractOMath(omml);
}

function numberXml(formula, state, settings) {
  if (formula.numberingMode === 'Manual')
    return manualNumberXml(formula.equationId, manualNumberText(formula.numberText, settings.numberEnclosure), bookmarkId());
  if (formula.numberingMode === 'Automatic')
    return automaticNumberXml(formula.equationId, sequenceCode(state), sequenceResult(state, state.value), bookmarkId());
  return null;
}

function displayParagraph(formula, sdt, state, settings, widthPoints) {
  return formulaParagraph({sdt, display: true, number: numberXml(formula, state, settings),
    placement: settings.numberPlacement, widthPoints});
}

export class WordCommands {
  constructor(text) {
    this.t = text;
    this.pendingReference = null;
  }

  error(key, values) {
    return new WordCommandError(this.t(key, values));
  }

  async selectionFontSize() {
    return Word.run(async context => {
      const font = context.document.getSelection().font;
      font.load('size');
      await context.sync();
      return font.size >= 1 && font.size <= 1638 ? font.size : 0;
    });
  }

  // Shared steps ---------------------------------------------------------------------

  /** The state a new automatic number gets at `range`: boundaries and automatic formulas before it. */
  async numberStateAt(context, variables, range, settings) {
    const controls = (await bodyControls(context)).filter(control => isBoundaryControl(control) || isFormulaControl(control));
    const relations = controls.map(control => control.getRange('Whole').compareLocationWith(range));
    await context.sync();
    const before = [];
    for (const [index, control] of controls.entries()) {
      if (!RELATIONS_BEFORE.has(relations[index].value)) continue;
      if (isBoundaryControl(control)) before.push({kind: boundaryKind(control)});
      else if (this.tryLoad(variables, control)?.numberingMode === 'Automatic') before.push({kind: 'formula'});
    }
    return numberStateAfter(before, settings);
  }

  tryLoad(variables, control) {
    try { return variables.load(control.tag); } catch { return null; }
  }

  /** EnsureUniqueFormulaIdentity: copies get a new equation id the first time they are used. */
  async uniqueIdentity(context, variables, control, formula) {
    const documentId = variables.documentId();
    if (formula.documentId === documentId && await countFormulasWithId(context, formula.equationId) <= 1) {
      await variables.flush(context);
      return formula;
    }
    const rebound = {...formula, documentId, equationId: newId()};
    const tag = variables.save(rebound);
    await variables.flush(context);
    control.tag = tag;
    await context.sync();
    return rebound;
  }

  async updateNumberField(context, control) {
    for (const field of await sequenceFields(context, control.paragraphs.getFirst().getRange('Whole'))) field.updateResult();
    await context.sync();
  }

  async insertionGuard(context, selection) {
    const parent = selection.parentContentControlOrNullObject;
    parent.load('tag');
    const inside = selection.contentControls;
    inside.load('items/tag');
    await context.sync();
    if ((!parent.isNullObject && isFormulaControl(parent)) || inside.items.some(isFormulaControl))
      throw this.error('InsertInsideFormulaError');
  }

  /** Selected managed formulas; Windows OLE formulas are reported, never touched. */
  async selectedFormulas(context) {
    const controls = await selectedFormulaControls(context);
    const ole = await oleFormulaCount(context, context.document.getSelection());
    if (!controls.length) throw this.error(ole ? 'OleFormulaWindowsOnly' : 'SelectedFormulaRequired');
    return {controls, ole};
  }

  // Insert, load, update -------------------------------------------------------------

  /** Inserts a new formula at the selection (InsertManagedEquationAsync). */
  async insert({latex, typography, display, numberingMode, numberText}, settings) {
    return Word.run(async context => {
      const selection = context.document.getSelection();
      await this.insertionGuard(context, selection);
      const variables = await Variables.load(context);
      const formula = createFormula({documentId: variables.documentId(), latex, display, numberingMode, numberText, typography});
      const sdt = equationControl(await renderEquation(formula), variables.save(formula));
      const tag = sdtTag(sdt);
      if (formula.displayMode === 'Inline') {
        await variables.flush(context);
        selection.insertOoxml(flatPackage(`<w:p>${sdt}</w:p>`), Word.InsertLocation.replace);
      } else {
        // A display formula always gets a paragraph of its own: the current
        // one when it is empty, otherwise a new one after it.
        let paragraph = selection.paragraphs.getLast();
        if (paragraphHasContent(await paragraphOoxml(context, paragraph)))
          paragraph = paragraph.insertParagraph('', Word.InsertLocation.after);
        const state = formula.numberingMode === 'Automatic'
          ? await this.numberStateAt(context, variables, paragraph.getRange('Start'), settings) : null;
        const width = formula.numberingMode === 'None' ? 0 : await textWidthPoints(context, paragraph);
        await variables.flush(context);
        // Word merges a package's last paragraph into the target and drops its
        // properties; its own packages end with an empty paragraph for that.
        paragraph.insertOoxml(flatPackage(displayParagraph(formula, sdt, state, settings, width) + '<w:p/>'),
          Word.InsertLocation.replace);
      }
      await context.sync();
      const control = await controlByTag(context, tag);
      if (!control) throw new WordCommandError('Word 未能保留刚插入的公式控件，请重试。');
      styleControl(control, tag, formula.typography.fontSizePoints);
      if (formula.numberingMode === 'Automatic') await this.updateNumberField(context, control);
      control.getRange('After').select(Word.SelectionMode.start);
      await context.sync();
      return formula;
    });
  }

  /** LoadSelectedFormulaTargetAsync: the first selected formula, with its identity made unique. */
  async loadSelected() {
    return Word.run(async context => {
      const {controls} = await this.selectedFormulas(context);
      const variables = await Variables.load(context);
      const control = controls[0];
      const formula = await this.uniqueIdentity(context, variables, control, variables.load(control.tag));
      return {controlId: control.id, formula};
    });
  }

  /**
   * UpdateFormulaAsync, content-only path: the formula's own m:oMath is
   * replaced; its control, paragraph layout, number, bookmark and every
   * reference to it stay. `preserveScale` keeps a user's resize as a ratio.
   */
  async update(target, {latex, typography}, {preserveScale = true} = {}) {
    return Word.run(async context => {
      const control = context.document.contentControls.getByIdOrNullObject(target.controlId);
      control.load('tag');
      control.font.load('size');
      await context.sync();
      const variables = await Variables.load(context);
      const valid = !control.isNullObject && equationIdFromTag(control.tag) === target.formula.equationId
        && variables.documentId() === target.formula.documentId
        && await countFormulasWithId(context, target.formula.equationId) === 1;
      if (!valid) throw this.error('SelectedFormulaRequired');
      const previous = target.formula;
      const next = {...previous, latex: normalizeLatex(latex), typography};
      if (next.latex === previous.latex.trim() && sameTypography(next.typography, previous.typography)
        && (preserveScale || !customScale(control, previous))) return {formula: previous, changed: false};
      const scale = preserveScale && control.font.size > 0 ? control.font.size / previous.typography.fontSizePoints : 1;
      const omath = await renderEquation(next);
      const tag = variables.save(next);
      await variables.flush(context);
      control.insertOoxml(flatPackage(`<w:p>${omath}</w:p>`), Word.InsertLocation.replace);
      styleControl(control, tag, next.typography.fontSizePoints * scale);
      await context.sync();
      return {formula: next, changed: true};
    });
  }

  // Delete ------------------------------------------------------------------------------

  /** DeleteSelectedFormulaAsync: numbered formulas lose their number and layout tabs too. */
  async deleteSelected() {
    return Word.run(async context => {
      const {controls, ole} = await this.selectedFormulas(context);
      const variables = await Variables.load(context);
      const formulas = controls.map(control => ({control, formula: variables.load(control.tag)}));
      for (const {control, formula} of formulas.reverse()) {
        if (formula.numberingMode === 'None') {
          control.delete(false);
          await context.sync();
          continue;
        }
        const paragraph = control.paragraphs.getFirst();
        const xml = await paragraphOoxml(context, paragraph);
        if (containsEmbeddedObject(xml)) throw this.error('ParseObjectParagraphSkipped');
        await replaceParagraphs(context, paragraph, paragraph, deleteFormulaXml(xml, formula.equationId));
      }
      return {count: controls.length, ole};
    });
  }

  // Format ------------------------------------------------------------------------------

  /** FormatAsync: resets formulas to the default style and their natural size. */
  async format(all, typography, progress) {
    const entries = await Word.run(async context => {
      const controls = all ? (await bodyControls(context)).filter(isFormulaControl)
        : (await this.selectedFormulas(context)).controls;
      controls.forEach(control => control.font.load('size'));
      await context.sync();
      return controls.map(control => ({controlId: control.id, tag: control.tag, size: control.font.size}));
    });
    if (!entries.length) return {key: 'NoFormattingTargetsStatus'};
    const result = {succeeded: 0, failed: 0, skipped: 0, reason: ''};
    for (let start = 0; start < entries.length; start += BATCH_SIZE) {
      for (const entry of entries.slice(start, start + BATCH_SIZE)) {
        try {
          const target = await this.formatTarget(entry);
          if (!target) { result.skipped++; continue; }
          // NeedsFormatting: another style, or a size the user changed by hand.
          if (sameTypography(target.formula.typography, typography)
            && Math.abs(entry.size - target.formula.typography.fontSizePoints) <= 0.1) continue;
          const {changed} = await this.update(target, {latex: target.formula.latex, typography}, {preserveScale: false});
          if (changed) result.succeeded++;
        } catch (error) {
          result.failed++;
          result.reason ||= error?.message || String(error);
        }
      }
      progress(this.t('BatchFormattingStatus', {processed: Math.min(start + BATCH_SIZE, entries.length), total: entries.length}));
    }
    return {...result, total: entries.length};
  }

  async formatTarget(entry) {
    return Word.run(async context => {
      const control = context.document.contentControls.getByIdOrNullObject(entry.controlId);
      control.load('tag');
      await context.sync();
      if (control.isNullObject || control.tag !== entry.tag) return null;
      const variables = await Variables.load(context);
      const formula = await this.uniqueIdentity(context, variables, control, variables.load(control.tag));
      return {controlId: control.id, formula};
    });
  }

  // Numbering ---------------------------------------------------------------------------

  /** AutoNumberSelectedAsync: a display formula becomes automatically numbered. */
  async addNumber(settings) {
    return Word.run(async context => {
      const {controls} = await this.selectedFormulas(context);
      const variables = await Variables.load(context);
      const control = controls[0];
      const formula = await this.uniqueIdentity(context, variables, control, variables.load(control.tag));
      if (formula.numberingMode !== 'None') return 'AlreadyNumberedStatus';
      if (formula.displayMode !== 'Display') return 'AutoNumberDisplayOnlyStatus';
      const next = {...formula, numberingMode: 'Automatic', numberText: ''};
      const paragraph = control.paragraphs.getFirst();
      const xml = await paragraphOoxml(context, paragraph);
      if (containsEmbeddedObject(xml)) throw this.error('ParseObjectParagraphSkipped');
      const state = await this.numberStateAt(context, variables, control.getRange('Whole'), settings);
      const width = await textWidthPoints(context, paragraph);
      const omath = await renderEquation(next);
      const tag = variables.save(next);
      const replacement = displayParagraph(next, equationControl(omath, tag), state, settings, width);
      await variables.flush(context);
      await replaceParagraphs(context, paragraph, paragraph, replaceFormulaXml(xml, formula.equationId, replacement));
      const updated = await controlByTag(context, tag);
      if (!updated) throw new WordCommandError('Word 未能保留刚插入的公式控件，请重试。');
      styleControl(updated, tag, next.typography.fontSizePoints);
      await this.updateNumberField(context, updated);
      return 'AutoNumberedStatus';
    });
  }

  /** RenumberAutomaticFormulasAsync. */
  async renumber(settings) {
    return Word.run(async context => {
      const controls = await bodyControls(context);
      const variables = await Variables.load(context);
      const timeline = [];
      let skippedMetadata = 0;
      let skippedNumbering = 0;
      for (const control of controls) {
        if (isBoundaryControl(control)) timeline.push({kind: boundaryKind(control), range: control.getRange('Whole')});
        if (!isFormulaControl(control)) continue;
        const formula = this.tryLoad(variables, control);
        if (!formula) { skippedMetadata++; continue; }
        if (formula.numberingMode === 'Automatic')
          timeline.push({kind: 'formula', name: bookmarkName(formula.equationId), range: control.getRange('Whole')});
      }
      await this.addOleSlots(context, controls, timeline);
      const states = numberStates(timeline, settings);
      const prepared = [];
      for (const [index, state] of states) {
        const field = await this.numberField(context, timeline[index].name);
        if (!field) { skippedNumbering++; continue; }
        field.code = sequenceCode(state);
        prepared.push({name: timeline[index].name});
      }
      await context.sync();
      const body = context.document.body.getRange('Whole');
      for (const field of await sequenceFields(context, body)) field.updateResult();
      await context.sync();
      // Re-bookmark exactly the new result (step 7). Updated fields need fresh
      // proxies: an old field's result range is stale after updateResult.
      for (const {name} of prepared) {
        const field = await this.numberField(context, name);
        if (field) field.result.insertBookmark(name);
      }
      const fields = body.fields;
      fields.load('items/code');
      await context.sync();
      for (const field of fields.items) if (field.code.includes(REFERENCE_MARKER)) field.updateResult();
      await context.sync();
      if (!prepared.length && !skippedMetadata && !skippedNumbering) return {key: 'NoNumberedStatus'};
      return skippedMetadata || skippedNumbering
        ? {key: 'RenumberedWithSkippedStatus', values: {count: prepared.length, metadataSkipped: skippedMetadata, numberingSkipped: skippedNumbering}}
        : {key: 'RenumberedStatus', values: {count: prepared.length}};
    });
  }

  /** The SEQ field a formula's number bookmark lies on (BuildEquationSequenceFieldMap). */
  async numberField(context, name) {
    const range = context.document.getBookmarkRangeOrNullObject(name);
    await context.sync();
    if (range.isNullObject) return null;
    const fields = await sequenceFields(context, range.paragraphs.getFirst().getRange('Whole'));
    const relations = fields.map(field => field.result.compareLocationWith(range));
    await context.sync();
    return fields.find((field, index) => !RELATIONS_APART.has(relations[index].value)) || null;
  }

  /**
   * Windows OLE formulas with automatic numbers take part in the count. Mac
   * cannot read their payload, so a LaTeXSnipperEq_ bookmark on a SEQ field
   * that no OMML formula owns counts as one (they are never edited).
   */
  async addOleSlots(context, controls, timeline) {
    const owned = new Set(controls.filter(isFormulaControl).map(control => bookmarkName(equationIdFromTag(control.tag))));
    const names = context.document.body.getRange('Whole').getBookmarks(false, false);
    await context.sync();
    for (const name of names.value.filter(item => item.startsWith(BOOKMARK_PREFIX) && !owned.has(item))) {
      if (!await this.numberField(context, name)) continue;
      const range = context.document.getBookmarkRangeOrNullObject(name);
      const relations = timeline.map(item => item.range.compareLocationWith(range));
      await context.sync();
      const position = relations.filter(relation => RELATIONS_BEFORE.has(relation.value)).length;
      timeline.splice(position, 0, {kind: 'formula', name, range});
    }
  }

  /** InsertNumberingBoundaryAsync, then an immediate renumber like Windows. */
  async insertBoundary(kind, settings) {
    await Word.run(async context => {
      const control = context.document.getSelection().getRange('End').insertContentControl();
      control.tag = BOUNDARY_TAGS[kind];
      control.title = BOUNDARY_TITLE;
      control.insertText(this.t(kind === 'chapter' ? 'ChapterBoundaryText' : 'SectionBoundaryText'), Word.InsertLocation.replace);
      control.appearance = Word.ContentControlAppearance.hidden;
      control.font.hidden = kind === 'chapter' ? settings.hideChapterBoundary : settings.hideSectionBoundary;
      await context.sync();
    });
    await this.renumber(settings);
    return 'BoundaryInsertedStatus';
  }

  /** ApplyNumberingBoundaryVisibilityAsync, after the settings change. */
  async applyBoundaryVisibility(settings) {
    await Word.run(async context => {
      for (const control of (await bodyControls(context)).filter(isBoundaryControl))
        control.font.hidden = boundaryKind(control) === 'chapter' ? settings.hideChapterBoundary : settings.hideSectionBoundary;
      await context.sync();
    });
  }

  // References --------------------------------------------------------------------------

  /** InsertReferencePlaceholderAsync: the placeholder replaces the selection and waits for a formula. */
  async insertReferencePlaceholder() {
    await Word.run(async context => {
      const range = context.document.getSelection().insertText(this.t('ReferencePlaceholderText'), Word.InsertLocation.replace);
      range.track();
      await context.sync();
      this.pendingReference = range;
    });
    return 'ReferencePlaceholderStatus';
  }

  /**
   * CompletePendingReferenceAsync, on every selection change: once a numbered
   * formula is selected, or the caret is in its paragraph, the placeholder
   * becomes REF LaTeXSnipperEq_<id> \h.
   */
  async completeReference() {
    const placeholder = this.pendingReference;
    if (!placeholder) return false;
    return Word.run(placeholder, async context => {
      let control = (await selectedFormulaControls(context))[0];
      if (!control) {
        const controls = context.document.getSelection().paragraphs.getFirst().contentControls;
        controls.load('items/id,items/tag');
        await context.sync();
        control = controls.items.find(isFormulaControl);
      }
      if (!control) return false;
      const formula = this.tryLoad(await Variables.load(context), control);
      if (!formula || formula.numberingMode === 'None') return false;
      const field = placeholder.insertField(Word.InsertLocation.replace, Word.FieldType.empty, referenceCode(formula.equationId).trim(), true);
      field.updateResult();
      placeholder.untrack();
      await context.sync();
      this.pendingReference = null;
      return true;
    });
  }

  // Parse --------------------------------------------------------------------------------

  /**
   * ParseLatexAsync: delimited LaTeX in the selection or the whole body
   * (tables cell by cell) becomes formulas; failures stay as text.
   */
  async parse(all, {pane, settings, typography, followHostFontSize}, progress) {
    return Word.run(async context => {
      const selection = context.document.getSelection();
      selection.load('isEmpty');
      await context.sync();
      if (!all && selection.isEmpty) return {key: 'NoParsingTargetsStatus'};
      const markers = all ? {} : {start: '_LSParseStart' + newId().slice(0, 12), end: '_LSParseEnd' + newId().slice(0, 12)};
      if (!all) {
        selection.getRange('Start').insertBookmark(markers.start);
        selection.getRange('End').insertBookmark(markers.end);
      }
      try {
        return await this.parseScope(context, all ? context.document.body : selection, markers,
          {pane, settings, typography, followHostFontSize}, progress);
      } finally {
        if (!all) {
          context.document.deleteBookmark(markers.start);
          context.document.deleteBookmark(markers.end);
          await context.sync();
        }
      }
    });
  }

  async parseScope(context, scope, markers, options, progress) {
    const paragraphs = scope.paragraphs;
    paragraphs.load('items/text,items/tableNestingLevel');
    await context.sync();
    const cells = paragraphs.items.map(paragraph => {
      const cell = paragraph.parentTableCellOrNullObject;
      cell.load('rowIndex,cellIndex');
      return cell;
    });
    await context.sync();
    const regions = [];
    let key = null;
    for (const [index, paragraph] of paragraphs.items.entries()) {
      const cell = cells[index];
      const current = cell.isNullObject ? 'body' : `${paragraph.tableNestingLevel}:${cell.rowIndex}:${cell.cellIndex}`;
      if (current !== key) regions.push([]);
      key = current;
      regions[regions.length - 1].push(index);
    }
    const groups = paragraphGroups(regions.map(indexes => indexes.map(index => paragraphs.items[index].text)))
      .map(([region, first, last]) => ({first: paragraphs.items[regions[region][first]], last: paragraphs.items[regions[region][last]]}));
    for (const group of groups) {
      group.xml = await paragraphOoxml(context, group.first, group.last);
      group.candidates = findCandidates(group.xml, markers);
    }
    const total = groups.reduce((count, group) => count + group.candidates.length, 0);
    if (!total) return {key: 'NoParsingTargetsStatus'};
    const variables = await Variables.load(context);
    const result = {succeeded: 0, failed: 0, reason: '', automatic: false};
    let processed = 0;
    for (const group of groups.reverse()) {
      if (!group.candidates.length) continue;
      if (containsEmbeddedObject(group.xml)) {
        result.failed += group.candidates.length;
        result.reason ||= this.t('ParseObjectParagraphSkipped');
        continue;
      }
      const width = group.candidates.some(candidate => candidate.display)
        ? await textWidthPoints(context, group.first) : 0;
      for (const candidate of group.candidates) {
        try {
          candidate.xml = await this.prepareCandidate(candidate, variables, options, width);
          if (candidate.xml.automatic) result.automatic = true;
        } catch (error) {
          result.failed++;
          result.reason ||= error?.message || String(error);
        }
      }
      const prepared = group.candidates.filter(candidate => candidate.xml);
      if (prepared.length) {
        await variables.flush(context);
        await replaceParagraphs(context, group.first, group.last, applyCandidates(group.xml, prepared, markers));
        result.succeeded += prepared.length;
      }
      processed += group.candidates.length;
      progress(this.t('BatchParsingStatus', {processed, total}));
    }
    return {...result, total};
  }

  async prepareCandidate(candidate, variables, {pane, settings, typography, followHostFontSize}, width) {
    const tagged = processTag(candidate.latex, candidate.display);
    if (!tagged) throw this.error('InvalidParsingSourceStatus');
    let numberingMode = 'None';
    let numberText = '';
    if (candidate.display && tagged.numberText !== null) {
      numberingMode = 'Manual';
      numberText = tagged.numberText;
    } else if (candidate.display) {
      numberingMode = pane.numberingMode;
      numberText = pane.manualNumber;
    }
    const size = followHostFontSize && candidate.fontSizePoints ? candidate.fontSizePoints : typography.fontSizePoints;
    const formula = createFormula({documentId: variables.documentId(), latex: tagged.latex, display: candidate.display,
      numberingMode, numberText, typography: {...typography, fontSizePoints: size}});
    const sdt = equationControl(await renderEquation(formula), variables.save(formula));
    if (!candidate.display) return {sdt};
    // Automatic numbers are renumbered once the parse is done.
    const state = {prefix: '', reset: false, enclosure: settings.numberEnclosure, value: 1};
    return {paragraph: displayParagraph(formula, sdt, state, settings, width), automatic: formula.numberingMode === 'Automatic'};
  }
}

const sdtTag = sdt => /<w:tag w:val="([^"]+)"/.exec(sdt)[1];

function customScale(control, formula) {
  return !(Math.abs(control.font.size - formula.typography.fontSizePoints) <= 0.1);
}

