/* A row of 7-segment digits drawn in SVG. Segments are named as usual (a top, b and c right, d bottom, e and f left,
   g middle); h is an extra vertical bar through the middle, used only to draw a plus sign. */

const SVG_NAMESPACE = 'http://www.w3.org/2000/svg';

// character → the segments it lights
const GLYPHS = {
  '0': 'abcdef', '1': 'bc', '2': 'abdeg', '3': 'abcdg', '4': 'bcfg', '5': 'acdfg', '6': 'acdefg', '7': 'abc',
  '8': 'abcdefg', '9': 'abcdfg', '-': 'g', '+': 'gh', '_': 'd', ' ': '',
  A: 'abcefg', C: 'adef', E: 'adefg', F: 'aefg', H: 'bcefg', L: 'def', P: 'abefg', S: 'acdfg',
  b: 'cdefg', d: 'bcdeg', n: 'ceg', o: 'cdeg', r: 'eg', t: 'defg', u: 'cde', y: 'bcdfg',
};
const UNKNOWN_GLYPH = 'g';

// segment → SVG path, in a 21 × 34 box. h comes first so that it is drawn under the others: when it is off it must
// not hide the middle of g.
const SEGMENT_PATHS = {
  h: 'M10,9.5 L11.6,11 L11.6,23 L10,24.5 L8.4,23 L8.4,11 Z',
  a: 'M4,1 L16,1 L14,4 L6,4 Z',
  b: 'M17,2 L17,15 L14.5,16.5 L14.5,5 Z',
  c: 'M17,19 L17,32 L14.5,29 L14.5,17.5 Z',
  d: 'M4,33 L16,33 L14,30 L6,30 Z',
  e: 'M3,19 L3,32 L5.5,29 L5.5,17.5 Z',
  f: 'M3,2 L3,15 L5.5,16.5 L5.5,5 Z',
  g: 'M4.5,17 L6.5,15.3 L13.5,15.3 L15.5,17 L13.5,18.7 L6.5,18.7 Z',
};

function createDigit() {
  const svg = document.createElementNS(SVG_NAMESPACE, 'svg');
  svg.setAttribute('viewBox', '0 0 21 34');
  const segments = {};
  for (const [name, path] of Object.entries(SEGMENT_PATHS)) {
    const segment = document.createElementNS(SVG_NAMESPACE, 'path');
    segment.setAttribute('d', path);
    segment.setAttribute('class', 's');
    svg.appendChild(segment);
    segments[name] = segment;
  }
  const decimalPoint = document.createElementNS(SVG_NAMESPACE, 'circle');
  decimalPoint.setAttribute('cx', '19.3');
  decimalPoint.setAttribute('cy', '32');
  decimalPoint.setAttribute('r', '1.4');
  decimalPoint.setAttribute('class', 's');
  svg.appendChild(decimalPoint);
  return { svg, segments, decimalPoint };
}

/* "12.5" → [{character: '1'}, {character: '2', point: true}, {character: '5'}]: a decimal point shares the digit
   before it, unless there is none or that digit already has one. */
function splitIntoDigits(text) {
  const digits = [];
  for (const character of text) {
    const previous = digits[digits.length - 1];
    if (character === '.' && previous && !previous.point) previous.point = true;
    else if (character === '.') digits.push({ character: ' ', point: true });
    else digits.push({ character, point: false });
  }
  return digits;
}

/* Returns { node, render }. render({text, blank, blink}) shows the text right-aligned; too long a text loses its
   left end. */
export function createSevenSegmentDisplay(digitCount, colorClass) {
  const node = document.createElement('div');
  node.className = `seg7 ${colorClass || ''}`;
  const digits = Array.from({ length: digitCount }, createDigit);
  digits.forEach((digit) => node.appendChild(digit.svg));

  function render(payload) {
    const shown = splitIntoDigits(payload.blank ? '' : String(payload.text ?? ''));
    while (shown.length < digitCount) shown.unshift({ character: ' ', point: false });
    node.classList.toggle('flash', Boolean(payload.blink) && !payload.blank);
    shown.slice(-digitCount).forEach(({ character, point }, index) => {
      const lit = GLYPHS[character] ?? UNKNOWN_GLYPH;
      for (const [name, segment] of Object.entries(digits[index].segments)) {
        segment.classList.toggle('on', lit.includes(name));
      }
      digits[index].decimalPoint.classList.toggle('on', point);
    });
  }

  render({ text: '', blank: true });
  return { node, render };
}
