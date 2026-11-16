export function populateCjkFonts(select, fonts, current, zh) {
  select.replaceChildren();
  for (const font of fonts) select.add(new Option(font.label, font.id));
  if (!fonts.some(font => font.id === current)) {
    const prompt = new Option(zh ? '请选择汉字字体' : 'Choose a Chinese font', current);
    prompt.disabled = true;
    prompt.hidden = true;
    select.add(prompt);
  }
  select.value = current;
}
