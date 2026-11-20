/* Strip charts over the mission clock, drawn with uPlot (vendor/uPlot.iife.min.js, MIT, loaded by the page as the
   global `uPlot`). A chart fills its container and follows its size.

     const chart = stripChart(container, {
       series: [{ label: 'ALT', color: AMBER, unit: 'km', value: (columns, i) => columns.alt[i] / 1000 }, ...],
       scales: { right: { range: [0, 100] } },          // optional: a series with scale: 'right' gets an axis there
     });
     chart.update(columns);                             // the history's columns (history.js)
*/

export const AMBER = '#ffb000', CYAN = '#4fc3f7', GREEN = '#7bd88f', MAGENTA = '#ff6ad5', RED = '#ff5f56', WHITE = '#e8e6df';
const AXIS = '#8b929a', GRID = 'rgba(255,255,255,0.07)';
const FONT = '11px ui-monospace, "DejaVu Sans Mono", Menlo, monospace';

/* "12:34" or "1:02:03" from seconds of MET. */
export function shortMet(seconds) {
  if (seconds == null || !Number.isFinite(seconds)) return '';
  const whole = Math.max(0, Math.round(seconds));
  const h = Math.floor(whole / 3600), m = Math.floor(whole / 60) % 60, s = whole % 60;
  return h ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}` : `${m}:${String(s).padStart(2, '0')}`;
}

function axis(scale, side) {
  return {
    scale, side, stroke: AXIS, font: FONT, size: 52, gap: 4,
    grid: { show: side === 3, stroke: GRID, width: 1 }, ticks: { show: false },
    values: (u, splits) => splits.map((value) => (value == null ? '' : `${+value.toFixed(Math.abs(value) < 10 ? 1 : 0)}`)),
  };
}

export function stripChart(container, { series, scales = {}, window: seconds = null }) {
  const usedScales = [...new Set(series.map((line) => line.scale || 'y'))];
  const options = {
    width: Math.max(100, container.clientWidth), height: Math.max(80, container.clientHeight),
    padding: [8, 6, 0, 0],
    legend: { show: true, live: false },
    cursor: { show: true, points: { show: false }, drag: { x: false, y: false } },
    scales: { x: { time: false }, ...Object.fromEntries(usedScales.map((name) => [name, { auto: true, ...(scales[name] || {}) }])) },
    axes: [
      { stroke: AXIS, font: FONT, grid: { stroke: GRID, width: 1 }, ticks: { show: false }, size: 26,
        values: (u, splits) => splits.map(shortMet) },
      ...usedScales.filter((name) => !(scales[name] && scales[name].hidden)).map((name, index) => axis(name, index === 0 ? 3 : 1)),
    ],
    series: [
      { label: 'MET', value: (u, value) => shortMet(value) },
      ...series.map((line) => ({
        label: line.label, scale: line.scale || 'y', stroke: line.color, width: line.width || 1.6,
        dash: line.dash, spanGaps: false, points: { show: false },
        value: (u, value) => (value == null ? '—' : `${value.toFixed(line.decimals ?? 1)}${line.unit ? ` ${line.unit}` : ''}`),
      })),
    ],
  };
  const plot = new uPlot(options, [[], ...series.map(() => [])], container);
  new ResizeObserver(() => {
    if (container.clientWidth && container.clientHeight) plot.setSize({ width: container.clientWidth, height: container.clientHeight - legendHeight(plot) });
  }).observe(container);

  return {
    plot,
    update(columns) {
      let first = 0;
      const times = columns.t;
      if (seconds && times.length) {
        const from = times[times.length - 1] - seconds;
        first = times.findIndex((t) => t >= from);
      }
      const data = [times.slice(first)];
      for (const line of series) {
        const values = [];
        for (let index = first; index < times.length; index++) {
          const value = line.value(columns, index);
          values.push(value == null || !Number.isFinite(value) ? null : value);
        }
        data.push(values);
      }
      plot.setData(data);
    },
  };
}

function legendHeight(plot) {
  const legend = plot.root.querySelector('.u-legend');
  return legend ? legend.offsetHeight : 0;
}
