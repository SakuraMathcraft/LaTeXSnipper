// PowerPoint commands, following PowerPointPluginController. Formulas are PNG
// (default) or SVG pictures tagged with the Windows schema (tags.mjs). Unlike
// Windows, every replacement inserts the new picture first, puts it on the
// original's layer, and deletes the original only then.
/* global Office, PowerPoint */
import {newId, normalizeLatex, sameTypography} from '../metadata.mjs';
import {paddedSvg, pictureSize, rasterizePicture, renderSvg} from '../renderer.mjs';
import {
  ALT_TEXT_PREFIX, DOCUMENT_ID_PROPERTY, createFormula, formulaFromTags, formulaTags, isFormulaTagSet, isOleFormulaTagSet,
} from './tags.mjs';

const BATCH_SIZE = 5;
const MIN_LEFT_POINTS = 72;
const MIN_TOP_POINTS = 96;

export class PowerPointCommandError extends Error {}

async function render(latex, typography, format) {
  const rendered = await renderSvg(latex, true, typography);
  const size = pictureSize(rendered);
  const data = format === 'Svg' ? paddedSvg(rendered) : await rasterizePicture(rendered);
  return {...size, data, format};
}

function insertPicture(picture, placement) {
  const options = {
    coercionType: picture.format === 'Svg' ? Office.CoercionType.XmlSvg : Office.CoercionType.Image,
    imageWidth: placement.width,
    imageHeight: placement.height,
  };
  if (placement.left !== undefined) Object.assign(options, {imageLeft: placement.left, imageTop: placement.top});
  return new Promise((resolve, reject) => Office.context.document.setSelectedDataAsync(picture.data, options, result =>
    result.status === Office.AsyncResultStatus.Succeeded
      ? resolve() : reject(new PowerPointCommandError(result.error?.message || 'PowerPoint 未能插入公式图片。'))));
}

async function tagsOf(context, shapes) {
  for (const shape of shapes) shape.tags.load('items/key,items/value');
  await context.sync();
  return shapes.map(shape => shape.tags.items.map(tag => [tag.key, tag.value]));
}

export class PowerPointCommands {
  constructor(text) {
    this.t = text;
  }

  error(key, values) {
    return new PowerPointCommandError(this.t(key, values));
  }

  async selectionFontSize() {
    return PowerPoint.run(async context => {
      const range = context.presentation.getSelectedTextRangeOrNullObject();
      range.load('font/size');
      await context.sync();
      const size = range.isNullObject ? 0 : range.font.size;
      return size >= 1 && size <= 1638 ? size : 0;
    });
  }

  /** PowerPointDocumentIdentityStore: the custom document property LaTeXSnipper.DocumentId. */
  async documentId(context) {
    const properties = context.presentation.properties.customProperties;
    const property = properties.getItemOrNullObject(DOCUMENT_ID_PROPERTY);
    property.load('value');
    await context.sync();
    if (!property.isNullObject && String(property.value || '').trim()) return String(property.value);
    const id = newId();
    properties.add(DOCUMENT_ID_PROPERTY, id);
    await context.sync();
    return id;
  }

  async currentSlide(context) {
    const slides = context.presentation.getSelectedSlides();
    slides.load('items/id');
    await context.sync();
    if (!slides.items.length) throw this.error('NoActiveSlide');
    return slides.items[0];
  }

  /**
   * Every top-level formula shape, like the Windows "all" walk (group members
   * are not visited); Windows OLE formulas are counted, never touched.
   */
  async allEntries(context) {
    const slides = context.presentation.slides;
    slides.load('items/id');
    await context.sync();
    for (const slide of slides.items) slide.shapes.load('items/id');
    await context.sync();
    const entries = [];
    let ole = 0;
    for (const slide of slides.items) {
      const tags = await tagsOf(context, slide.shapes.items);
      slide.shapes.items.forEach((shape, index) => {
        if (isOleFormulaTagSet(tags[index])) ole++;
        else if (isFormulaTagSet(tags[index])) entries.push({slideId: slide.id, shapeId: shape.id, tags: tags[index]});
      });
    }
    return {entries, ole};
  }

  /** Selected formula shapes; Windows OLE formulas are counted, never touched. */
  async selectedEntries(context) {
    const slide = await this.currentSlide(context);
    const shapes = context.presentation.getSelectedShapes();
    shapes.load('items/id');
    await context.sync();
    if (!shapes.items.length) throw this.error('SelectedFormulaRequired');
    const tags = await tagsOf(context, shapes.items);
    const entries = [];
    let ole = 0;
    shapes.items.forEach((shape, index) => {
      if (isOleFormulaTagSet(tags[index])) ole++;
      else if (isFormulaTagSet(tags[index])) entries.push({slideId: slide.id, shapeId: shape.id, tags: tags[index]});
    });
    return {entries, ole};
  }

  /** EnsureUniqueShapeIdentity: foreign or duplicated ids are re-tagged in place. */
  async uniqueIdentity(context, entry, all) {
    const formula = formulaFromTags(entry.tags);
    const documentId = await this.documentId(context);
    const duplicates = all.filter(other => formulaFromTagsSafe(other.tags)?.equationId === formula.equationId);
    if (formula.documentId === documentId && duplicates.length <= 1) return formula;
    const rebound = {...formula, documentId, equationId: newId()};
    const shape = context.presentation.slides.getItem(entry.slideId).shapes.getItem(entry.shapeId);
    for (const [key, value] of formulaTags(rebound)) shape.tags.add(key, value);
    await context.sync();
    return rebound;
  }

  /**
   * Inserts `picture` on the entry's slide (or the current one), then tags
   * it. With `replace`, the new picture takes the original's position, user
   * scale (width based, like Windows) and layer before the original goes.
   */
  async place(context, formula, picture, replace = null, scale = 1) {
    let slideId;
    let placement = {width: picture.widthPoints * scale, height: picture.heightPoints * scale};
    let original = null;
    if (replace) {
      slideId = replace.slideId;
      original = context.presentation.slides.getItem(slideId).shapes.getItem(replace.shapeId);
      original.load('left,top,zOrderPosition');
      await context.sync();
      placement = {...placement, left: original.left, top: original.top};
    } else {
      slideId = (await this.currentSlide(context)).id;
      // GetInsertionPoint: centred, but at least 72 pt from the left and 96 pt from the top.
      const page = context.presentation.pageSetup;
      page.load('slideWidth,slideHeight');
      await context.sync();
      placement = {...placement, left: Math.max(MIN_LEFT_POINTS, (page.slideWidth - placement.width) / 2),
        top: Math.max(MIN_TOP_POINTS, (page.slideHeight - placement.height) / 2)};
    }
    // setSelectedDataAsync acts on the selection: with a shape or text
    // selected, PowerPoint for Mac can put the picture into that shape or
    // replace a selected picture. Selecting only the slide makes it a new,
    // independent shape and leaves the selected one untouched.
    context.presentation.slides.getItem(slideId).setSelectedShapes([]);
    context.presentation.setSelectedSlides([slideId]);
    await context.sync();
    const shapes = context.presentation.slides.getItem(slideId).shapes;
    shapes.load('items/id');
    await context.sync();
    const before = new Set(shapes.items.map(shape => shape.id));
    await insertPicture(picture, placement);
    shapes.load('items/id,items/left,items/top,items/zOrderPosition');
    await context.sync();
    const inserted = shapes.items.filter(shape => !before.has(shape.id));
    if (inserted.length !== 1) throw new PowerPointCommandError('PowerPoint 未能定位新插入的公式图片。');
    const [shape] = inserted;
    // SVG pictures keep their aspect ratio, so each side is set explicitly.
    shape.width = placement.width;
    shape.height = placement.height;
    shape.left = placement.left;
    shape.top = placement.top;
    for (const [key, value] of formulaTags(formula)) shape.tags.add(key, value);
    shape.altTextDescription = ALT_TEXT_PREFIX + formula.equationId;
    if (original) {
      for (let step = shape.zOrderPosition; step > original.zOrderPosition + 1; step--)
        shape.setZOrder(PowerPoint.ShapeZOrder.sendBackward);
      original.delete();
    }
    await context.sync();
    return {slideId, shapeId: shape.id};
  }

  // Commands ---------------------------------------------------------------------------

  async insert({latex, typography, format}) {
    return PowerPoint.run(async context => {
      const source = normalizeLatex(latex);
      const picture = await render(source, typography, format);
      const formula = createFormula({documentId: await this.documentId(context), latex: source, typography, format,
        naturalWidthPoints: picture.widthPoints, naturalHeightPoints: picture.heightPoints});
      await this.place(context, formula, picture);
      return format === 'Svg' ? 'InsertedSvgStatus' : 'InsertedImageStatus';
    });
  }

  async loadSelected() {
    return PowerPoint.run(async context => {
      const {entries, ole} = await this.selectedEntries(context);
      if (!entries.length) throw this.error(ole ? 'OleFormulaWindowsOnly' : 'SelectedFormulaRequired');
      const formula = await this.uniqueIdentity(context, entries[0], (await this.allEntries(context)).entries);
      return {slideId: entries[0].slideId, shapeId: entries[0].shapeId, formula};
    });
  }

  /** Edit: same picture format, position, user scale and layer, new source and style. */
  async update(target, {latex, typography}) {
    return PowerPoint.run(async context => {
      const shape = context.presentation.slides.getItem(target.slideId).shapes.getItemOrNullObject(target.shapeId);
      shape.load('width');
      await context.sync();
      if (shape.isNullObject) throw this.error('SelectedFormulaRequired');
      const [tags] = await tagsOf(context, [shape]);
      const current = formulaFromTagsSafe(tags);
      if (current?.equationId !== target.formula.equationId) throw this.error('SelectedFormulaRequired');
      const source = normalizeLatex(latex);
      if (source === current.latex.trim() && sameTypography(typography, current.typography)) return {changed: false};
      const picture = await render(source, typography, current.format);
      const formula = {...current, latex: source, typography, naturalWidthPoints: picture.widthPoints,
        naturalHeightPoints: picture.heightPoints};
      await this.place(context, formula, picture, target, shape.width / current.naturalWidthPoints);
      return {changed: true};
    });
  }

  async deleteSelected() {
    return PowerPoint.run(async context => {
      const {entries, ole} = await this.selectedEntries(context);
      if (!entries.length) throw this.error(ole ? 'OleFormulaWindowsOnly' : 'SelectedFormulaRequired');
      for (const entry of entries) context.presentation.slides.getItem(entry.slideId).shapes.getItem(entry.shapeId).delete();
      await context.sync();
      return {count: entries.length, ole};
    });
  }

  /**
   * Format (reset style and natural size) and conversion (PNG ↔ SVG, keeping
   * the user scale) share the Windows batch loop: `change` returns the new
   * typography/format and scale, or null when the formula needs nothing.
   */
  async batch(all, change, progress, progressKey) {
    const {entries, ole} = await PowerPoint.run(async context => {
      const every = await this.allEntries(context);
      const selected = all ? every : await this.selectedEntries(context);
      for (const entry of selected.entries) {
        try {
          entry.formula = await this.uniqueIdentity(context, entry, every.entries);
        } catch (error) {
          entry.error = error;
          continue;
        }
        entry.shape = context.presentation.slides.getItem(entry.slideId).shapes.getItem(entry.shapeId);
        entry.shape.load('width,height');
      }
      await context.sync();
      for (const entry of selected.entries) {
        if (!entry.formula) continue;
        entry.scale = entry.shape.width / entry.formula.naturalWidthPoints;
        entry.heightScale = entry.shape.height / entry.formula.naturalHeightPoints;
      }
      return selected;
    });
    const result = {succeeded: 0, failed: 0, skipped: 0, reason: '', total: entries.length, ole};
    for (let start = 0; start < entries.length; start += BATCH_SIZE) {
      for (const entry of entries.slice(start, start + BATCH_SIZE)) {
        if (entry.error) {
          result.failed++;
          result.reason ||= entry.error.message;
          continue;
        }
        const plan = change(entry);
        if (!plan) continue;
        try {
          await PowerPoint.run(async context => {
            const shape = context.presentation.slides.getItem(entry.slideId).shapes.getItemOrNullObject(entry.shapeId);
            await context.sync();
            if (shape.isNullObject) { result.skipped++; return; }
            const picture = await render(entry.formula.latex, plan.typography, plan.format);
            const formula = {...entry.formula, typography: plan.typography, format: plan.format,
              naturalWidthPoints: picture.widthPoints, naturalHeightPoints: picture.heightPoints};
            await this.place(context, formula, picture, entry, plan.scale);
            result.succeeded++;
          });
        } catch (error) {
          result.failed++;
          result.reason ||= error?.message || String(error);
        }
      }
      progress(this.t(progressKey, {processed: Math.min(start + BATCH_SIZE, entries.length), total: entries.length}));
    }
    return result;
  }

  async format(all, typography, progress) {
    // Unlike Windows, which compares only the width, a picture stretched in
    // one direction also counts as resized and gets its natural size back.
    const natural = entry => Math.abs(entry.scale - 1) <= 0.01 && Math.abs(entry.heightScale - 1) <= 0.01;
    return this.batch(all, entry => sameTypography(entry.formula.typography, typography) && natural(entry)
      ? null : {typography, format: entry.formula.format, scale: 1}, progress, 'BatchFormattingStatus');
  }

  async convert(format, progress) {
    return this.batch(false, entry => entry.formula.format === format
      ? null : {typography: entry.formula.typography, format, scale: entry.scale}, progress, 'BatchConvertingStatus');
  }
}

function formulaFromTagsSafe(tags) {
  try { return formulaFromTags(tags); } catch { return null; }
}
