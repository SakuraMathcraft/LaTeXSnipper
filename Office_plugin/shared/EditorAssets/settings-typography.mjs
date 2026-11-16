import {populateCjkFonts} from './cjk-font-picker.mjs';

export function populateTypographyOptions(payload, current, locale) {
  const zh = locale.startsWith('zh');
  const options = (id, values, selected) => {
    const select = document.getElementById(id);
    select.replaceChildren();
    for (const value of new Set([...values, selected])) {
      select.add(new Option(value || (zh ? '跟随符号字体' : 'Follow symbol font'), value));
    }
    select.value = selected;
  };
  options('symbolFontId', payload.symbolFonts, current.symbolFontId);
  options('numberFontFamily', ['', ...payload.systemFonts], current.numberFontFamily);
  populateCjkFonts(document.getElementById('cjkFontFamily'), payload.cjkFonts, current.cjkFontFamily, zh);

  const styles = document.getElementById('formulaMathStyle');
  styles.replaceChildren();
  for (const style of payload.mathStyles) styles.add(new Option(zh ? style.zh : style.en, style.id));

  const sizes = document.getElementById('formulaFontSizePoints');
  sizes.replaceChildren();
  for (const size of payload.namedSizes) sizes.add(new Option(size.name, String(size.points)));
  for (const points of payload.commonPointSizes) sizes.add(new Option(String(points), String(points)));
  if (![...sizes.options].some(option => Number(option.value) === current.formulaFontSizePoints)) {
    sizes.add(new Option(String(current.formulaFontSizePoints), String(current.formulaFontSizePoints)));
  }
}
