/* Small DOM and formatting helpers shared by the consoles. */

export function create(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function formatMet(seconds) {
  if (seconds == null || !Number.isFinite(seconds)) return '---:--:--';
  const sign = seconds < 0 ? '-' : '';
  const whole = Math.floor(Math.abs(seconds));
  return `${sign}${String(Math.floor(whole / 3600)).padStart(3, '0')}:${String(Math.floor(whole / 60) % 60).padStart(2, '0')}:${String(whole % 60).padStart(2, '0')}`;
}

export function fixed(value, decimals = 0, unit = '') {
  if (value == null || !Number.isFinite(value)) return '—';
  return `${value.toFixed(decimals)}${unit ? ` ${unit}` : ''}`;
}

export const km = (metres, decimals = 1) => fixed(metres == null ? null : metres / 1000, decimals, 'km');

/* A two-column list of figures. figures([{name, id}]) builds it; set(id, text, tone) updates one value. */
export function figures(container, rows) {
  const list = create('dl', 'mcc-figures');
  const cells = {};
  for (const [id, name] of rows) {
    const value = create('dd', '', '—');
    list.append(create('dt', '', name), value);
    cells[id] = value;
  }
  container.append(list);
  return (id, text, tone = '') => {
    cells[id].textContent = text;
    cells[id].className = tone;
  };
}

/* A titled box inside a console, on the console's fixed grid of tiles (CONSOLE_TILES columns × rows): `at` is its
   top-left tile [column, row], `size` how many tiles it takes [width, height]. Nothing reflows; a box whose content
   is longer scrolls inside it. */
export const CONSOLE_TILES = [3, 2];
export function box(container, title, { at, size = [1, 1] }) {
  const section = create('section', 'mcc-box');
  section.style.gridColumn = `${at[0] + 1} / span ${size[0]}`;
  section.style.gridRow = `${at[1] + 1} / span ${size[1]}`;
  if (at[0] + size[0] > CONSOLE_TILES[0] || at[1] + size[1] > CONSOLE_TILES[1]) console.warn(`MCC box ${title} is off the console's grid`);
  section.append(create('h3', '', title));
  container.append(section);
  return section;
}
