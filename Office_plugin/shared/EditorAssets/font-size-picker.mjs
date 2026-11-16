export class FontSizePicker {
  constructor({onOpen, blocked}) {
    this.onOpen = onOpen;
    this.blocked = blocked;
    this.root = document.getElementById('sizePicker');
    this.input = document.getElementById('fontSizePoints');
    this.toggle = document.getElementById('fontSizeToggle');
    this.menu = document.getElementById('fontSizeMenu');
    this.options = [];
    this.activeIndex = -1;
    this.toggle.addEventListener('click', () => this.menu.hidden ? this.open() : this.close());
    this.input.addEventListener('keydown', event => this.onKeyDown(event));
    this.menu.addEventListener('click', event => {
      const option = event.target.closest('.size-option');
      if (option) this.choose(option);
    });
    document.addEventListener('pointerdown', event => {
      if (!this.root.contains(event.target)) this.close();
    });
  }

  configure(catalog, zh) {
    this.close();
    this.namedSizes = catalog.namedSizes;
    this.menu.replaceChildren();
    const group = label => {
      const heading = document.createElement('div');
      heading.className = 'size-group-label';
      heading.textContent = label;
      this.menu.append(heading);
    };
    const add = (label, points, value) => {
      const button = document.createElement('button');
      button.type = 'button'; button.className = 'size-option'; button.role = 'option'; button.tabIndex = -1;
      button.id = `font-size-option-${this.options.length}`;
      button.dataset.value = String(value); button.dataset.points = String(points);
      const name = document.createElement('span'); name.textContent = label;
      const detail = document.createElement('small'); detail.textContent = `${points} pt`;
      button.append(name, detail); this.menu.append(button); this.options.push(button);
    };
    this.options = [];
    group(zh ? '中文字号' : 'Named sizes');
    for (const [name, points] of Object.entries(catalog.namedSizes)) add(name, points, name);
    group(zh ? '常用磅值' : 'Point sizes');
    for (const points of catalog.commonPointSizes) add(String(points), points, points);
    this.toggle.setAttribute('aria-label', zh ? '选择字号' : 'Choose font size');
  }

  selectedIndex() {
    const text = this.input.value.trim();
    const points = Object.hasOwn(this.namedSizes, text) ? this.namedSizes[text] : Number(text);
    const named = this.options.findIndex(option => Object.hasOwn(this.namedSizes, option.dataset.value)
      && Number(option.dataset.points) === points);
    if (named >= 0) return named;
    return this.options.findIndex(option => option.dataset.value === text);
  }

  highlight(index) {
    this.activeIndex = index;
    this.options.forEach((option, i) => option.setAttribute('aria-selected', String(i === index)));
    if (index >= 0) {
      this.input.setAttribute('aria-activedescendant', this.options[index].id);
      this.options[index].scrollIntoView({block: 'nearest'});
    } else this.input.removeAttribute('aria-activedescendant');
  }

  open() {
    if (this.blocked() || this.input.disabled) return;
    this.onOpen();
    this.menu.hidden = false;
    this.input.setAttribute('aria-expanded', 'true');
    this.toggle.setAttribute('aria-expanded', 'true');
    this.highlight(this.selectedIndex());
  }

  close() {
    this.menu.hidden = true;
    this.input.setAttribute('aria-expanded', 'false');
    this.toggle.setAttribute('aria-expanded', 'false');
    this.input.removeAttribute('aria-activedescendant');
  }

  choose(option) {
    this.input.value = option.dataset.value;
    this.input.dispatchEvent(new Event('input', {bubbles: true}));
    this.close();
    this.input.focus();
  }

  onKeyDown(event) {
    if (event.isComposing || this.blocked()) return;
    if (event.key === 'Tab') { this.close(); return; }
    if (event.key === 'Escape' && !this.menu.hidden) {
      event.preventDefault(); event.stopPropagation(); this.close(); return;
    }
    if (event.key === 'Enter' && !this.menu.hidden) {
      event.preventDefault(); event.stopPropagation();
      if (this.activeIndex >= 0) this.choose(this.options[this.activeIndex]);
      return;
    }
    if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
    event.preventDefault();
    if (this.menu.hidden) this.open();
    else this.highlight(Math.max(0, Math.min(this.options.length - 1,
      this.activeIndex + (event.key === 'ArrowDown' ? 1 : -1))));
  }

  setLocked(locked) {
    this.toggle.disabled = locked;
    if (locked) this.close();
  }
}
