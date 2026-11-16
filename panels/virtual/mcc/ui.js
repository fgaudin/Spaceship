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

/* A titled box inside a console. */
export function box(container, title, className = '') {
  const section = create('section', `mcc-box ${className}`);
  section.append(create('h3', '', title));
  container.append(section);
  return section;
}
