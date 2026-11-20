/* A strip chart in a console's box, over the last minutes of the flight (charts.js, history.js). */
import { box, create } from './ui.js';
import { stripChart } from './charts.js';
import { history, onHistory } from './history.js';

export const CONSOLE_CHART_WINDOW_S = 15 * 60;

export function chartBox(root, title, place, options) {
  const section = box(root, title, place);
  section.classList.add('mcc-chart-box');
  const area = create('div', 'mcc-chart');
  section.append(area);
  const chart = stripChart(area, { window: CONSOLE_CHART_WINDOW_S, ...options });
  onHistory(() => chart.update(history().columns));
  chart.update(history().columns);
  return chart;
}
