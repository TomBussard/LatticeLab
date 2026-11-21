const $ = (selector) => document.querySelector(selector);
const labels = {
  delta: 'Delta',
  gamma: 'Gamma',
  vega: 'Vega',
  theta: 'Theta',
  rho: 'Rho',
  vanna: 'Vanna',
  volga: 'Volga',
  charm: 'Charm',
  speed: 'Speed',
};
const definitions = {
  delta: '∂V / ∂S',
  gamma: '∂²V / ∂S²',
  vega: '∂V / ∂σ',
  theta: '∂V / ∂t',
  rho: '∂V / ∂r',
  vanna: '∂²V / ∂S∂σ',
  volga: '∂²V / ∂σ²',
  charm: '∂²V / ∂S∂t',
  speed: '∂³V / ∂S³',
};
const kinds = {
  call: 'Call',
  put: 'Put',
  digital_call: 'Digital call',
  digital_put: 'Digital put',
  one_touch_up: 'Up one-touch',
  custom: 'Custom payoff',
};
const pages = {
  price: ['Pricing', 'Position value and equity hedge', 'Calculate'],
  greeks: ['Greeks', 'Select a Greek to see its curve', 'Calculate Greeks'],
  convergence: [
    'Convergence',
    'Price and error as the grid is refined',
    'Run convergence study',
  ],
  benchmark: [
    'Runtime',
    'Runtime for the two engines',
    'Measure runtime',
  ],
  tree: ['Tree', 'Node size and colour reflect probability', 'Build tree'],
};
let page = 'price',
  busy = false,
  result = null,
  requestSnapshot = null,
  settingsSnapshot = null;
let legs = [
  {
    kind: 'call',
    strike: 100,
    expiry: '2027-10-29',
    american: false,
    quantity: 1,
    multiplier: 1,
    payout: 1,
    expression: 'max(S-K,0)',
    monitoring: 'continuous',
  },
];

function options(map, selected) {
  return Object.entries(map)
    .map(
      ([value, label]) =>
        `<option value="${value}" ${String(value) === String(selected) ? 'selected' : ''}>${escapeHtml(label)}</option>`,
    )
    .join('');
}
function renderLegs() {
  $('#legs').innerHTML = legs
    .map(
      (leg, i) =>
        `<tr data-leg="${i}"><td><select data-field="kind" aria-label="Product in leg ${i + 1}">${options(kinds, leg.kind)}</select></td><td><select data-field="american" aria-label="Exercise in leg ${i + 1}" ${['digital_call', 'digital_put', 'one_touch_up'].includes(leg.kind) ? 'disabled' : ''}>${options({ false: 'European', true: 'American' }, leg.american)}</select></td><td><input data-field="strike" aria-label="Strike in leg ${i + 1}" type="number" step="any" min="0" value="${leg.strike}"></td><td><input data-field="expiry" aria-label="Expiry in leg ${i + 1}" type="date" value="${escapeHtml(leg.expiry)}"></td><td><input data-field="quantity" aria-label="Quantity in leg ${i + 1}" type="number" step="any" value="${leg.quantity}"></td><td><input data-field="multiplier" aria-label="Multiplier in leg ${i + 1}" type="number" min="0.001" step="any" value="${leg.multiplier}"></td><td><button class="delete-leg" data-delete="${i}" aria-label="Remove leg ${i + 1}" ${legs.length === 1 ? 'disabled' : ''}>×</button></td></tr>${extraLeg(leg, i)}`,
    )
    .join('');
}
function extraLeg(leg, i) {
  let fields = '';
  if (['digital_call', 'digital_put', 'one_touch_up'].includes(leg.kind))
    fields += `<label>Payout (EUR)<input data-field="payout" type="number" min="0" step="any" value="${leg.payout}"></label>`;
  if (leg.kind === 'one_touch_up')
    fields += `<label>Observation<select data-field="monitoring">${options({ continuous: 'Continuous', grid: 'Tree dates' }, leg.monitoring)}</select></label>`;
  if (leg.kind === 'custom')
    fields += `<label>Payoff f(S, K)<input class="expression" data-field="expression" value="${escapeHtml(leg.expression)}"></label>`;
  return fields
    ? `<tr class="extra-leg" data-leg="${i}"><td colspan="7"><div class="extra-fields">${fields}</div></td></tr>`
    : '';
}
function syncLegs() {
  document.querySelectorAll('#legs [data-field]').forEach(
    (field) => {
      const leg = legs[Number(field.closest('[data-leg]').dataset.leg)],
        key = field.dataset.field;
      if (key === 'american') leg[key] = field.value === 'true';
      else if (['kind', 'expiry', 'expression', 'monitoring'].includes(key)) leg[key] = field.value;
      else {
        if (!field.value.trim() || !Number.isFinite(Number(field.value)))
          throw Error('Enter a number for each position field');
        leg[key] = Number(field.value);
      }
    },
  );
}
function readNumber(id) {
  const field = $(id);
  if (!field.value.trim() || !Number.isFinite(Number(field.value)))
    throw Error('Enter a number in each market field');
  return Number(field.value);
}
function getRequest() {
  syncLegs();
  return {
    engine: $('#engine').value,
    valuation_date: $('#valuation-date').value,
    day_basis: readNumber('#day-basis'),
    market: {
      spot: readNumber('#spot'),
      volatility: readNumber('#volatility') / 100,
      rate: readNumber('#rate') / 100,
      yield_rate: readNumber('#yield-rate') / 100,
      dividend: readNumber('#dividend'),
      dividend_date: $('#dividend-date').value || null,
    },
    grid: {
      steps: readNumber('#steps'),
      mode: $('#tree-mode').value,
      pruning: $('#use-pruning').checked && $('#tree-mode').value === 'trinomial' ? 1e-10 : 0,
    },
    legs: structuredClone(legs),
    greeks: page === 'greeks' ? Object.keys(labels) : page === 'price' ? ['delta'] : [],
  };
}
function getSettings() {
  return page === 'convergence'
    ? { metric: $('#metric').value, tolerance: readNumber('#tolerance') }
    : {};
}
function pageOptions() {
  if (page === 'convergence')
    return `<div class="options-panel"><div class="options-grid"><label>Metric<select id="metric">${options({ price: 'Position value', ...labels }, 'price')}</select></label><label>Absolute tolerance<input id="tolerance" type="number" step="any" min="0.00000001" value="0.001"></label></div></div>`;
  return '';
}
function setPage(next) {
  if (busy || next === page) return;
  page = next;
  result = requestSnapshot = settingsSnapshot = null;
  document.querySelectorAll('.nav-item').forEach(
    (button) => {
      button.classList.toggle('active', button.dataset.page === page);
      if (button.dataset.page === page) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    },
  );
  $('#page-title').textContent = pages[page][0];
  $('#page-description').textContent = pages[page][1];
  $('#run').textContent = pages[page][2];
  $('#page-options').innerHTML = pageOptions();
  $('#run-hint').textContent =
    page === 'tree'
      ? 'The tree shows up to six steps for the first leg.'
      : page === 'convergence' || page === 'benchmark'
        ? 'Grid sizes are chosen when the calculation starts'
        : '';
  $('#results').innerHTML =
    `<p class="empty-state">Select ${pages[page][2]} to see the results.</p>`;
  $('#stale').hidden = $('#error').hidden = true;
  $('#export-results').disabled = true;
}
function markStale() {
  if (result) $('#stale').hidden = false;
}
function updatePruning() {
  const binomial = $('#tree-mode').value === 'binomial';
  $('#use-pruning').disabled = binomial;
  $('#pruning-note').textContent = binomial
    ? 'Pruning applies to the trinomial tree'
    : 'Skip branches below the probability threshold';
}
function showError(message) {
  $('#error').textContent = message;
  $('#error').hidden = false;
}
async function poll(id) {
  while (true) {
    const response = await fetch('/api/jobs/' + id),
      job = await response.json();
    if (!response.ok) throw Error(job.error || 'Server unavailable');
    $('#progress-message').textContent = job.progress || 'Calculating';
    if (job.state === 'done') return job.result;
    if (job.state === 'error') throw Error(job.error);
    await new Promise(
      (resolve) =>
        setTimeout(resolve, 300),
    );
  }
}
async function run(action = page, metric = null) {
  if (busy) return;
  let payload;
  try {
    if (action === 'curve') {
      if (!requestSnapshot || !$('#stale').hidden)
        throw Error('Recalculate the Greeks after changing the inputs');
      payload = {
        action: 'curve',
        request: structuredClone(requestSnapshot),
        settings: { metric },
      };
    } else {
      payload = { action, request: getRequest(), settings: getSettings() };
      if (action === 'tree') payload.request.grid.steps = Math.min(6, payload.request.grid.steps);
    }
  } catch (error) {
    showError(error.message);
    if (action === 'curve')
      document
        .querySelectorAll(`[data-curve="${metric}"]`)
        .forEach(
          (el) =>
            (el.textContent = error.message),
        );
    return;
  }
  const controls = [...document.querySelectorAll('input,select,button')].map(
    (el) => [el, el.disabled],
  );
  controls.forEach(
    ([el]) => (el.disabled = true),
  );
  busy = true;
  document.body.classList.add('busy');
  $('#progress').hidden = false;
  $('#error').hidden = true;
  $('#progress-message').textContent =
    action === 'curve' ? 'Calculating the curve for ' + labels[metric] : 'Calculating';
  const start = performance.now(),
    timer = setInterval(
      () => ($('#elapsed').textContent = ((performance.now() - start) / 1000).toFixed(1) + ' s'),
      200,
    );
  try {
    const response = await fetch('/api/jobs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      }),
      job = await response.json();
    if (!response.ok) throw Error(job.error);
    const data = await poll(job.id);
    if (action === 'curve') {
      result.curves ??= {};
      result.curves[metric] = data;
      renderCurve(metric, data);
    } else {
      requestSnapshot = structuredClone(payload.request);
      settingsSnapshot = structuredClone(payload.settings);
      result = data;
      $('#stale').hidden = true;
      renderResult(data);
    }
  } catch (error) {
    showError(error.message);
    if (action !== 'curve') markStale();
    document
      .querySelectorAll(`[data-curve="${metric}"]`)
      .forEach(
        (el) =>
          (el.textContent = error.message),
      );
  } finally {
    busy = false;
    clearInterval(timer);
    document.body.classList.remove('busy');
    $('#progress').hidden = true;
    controls.forEach(
      ([el, disabled]) => {
        if (el.isConnected) el.disabled = disabled;
      },
    );
    $('#export-results').disabled = !result;
    updatePruning();
  }
}
function panel(title, subtitle, body) {
  return `<section class="result-panel"><div class="section-heading"><div><h3>${escapeHtml(title)}</h3>${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ''}</div></div>${body}</section>`;
}
function dataTable(headers, rows) {
  return `<div class="table-scroll"><table><thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((row) => `<tr>${row.map((c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function tableDetails(title, headers, rows) {
  return `<details class="values-details"><summary>${escapeHtml(title)}</summary>${dataTable(headers, rows)}</details>`;
}
function engineHeading(name) {
  return `<div class="engine-title">${name === 'python' ? 'Python' : 'VBA / Excel'}</div>`;
}
function renderResult(data) {
  if (data.action === 'price') renderPrices(data);
  else if (data.action === 'greeks') renderGreeks(data);
  else if (data.action === 'convergence') renderConvergence(data);
  else if (data.action === 'benchmark') renderBenchmark(data);
  else if (data.action === 'tree') renderTrees(data);
}
function warningText(report) {
  return (report.warnings || [])
    .map(
      (text) =>
        `<p class="small-note">${escapeHtml(text)}</p>`,
    )
    .join('');
}
function pricingTimings(times) {
  const rows = [
    ['Tree construction and pricing', times.build + times.price, 'timing-price'],
    ['Tree construction', times.build, 'timing-detail'],
    ['Pricing', times.price, 'timing-detail'],
    ['Delta hedge', times.greeks, 'timing-hedge'],
  ];
  const other = Math.max(0, times.total - times.build - times.price - times.greeks);
  if (other >= 0.00005) rows.push(['Other calculations', other, 'timing-other']);
  return (
    '<div class="timing-breakdown">' +
    rows
      .map(
        ([label, seconds, style]) =>
          `<div class="${style}"><span>${label}</span><span>${numberText(seconds * 1000, 1)} ms</span></div>`,
      )
      .join('') +
    '</div>'
  );
}
function renderPrices(data) {
  let html = '';
  for (const [engine, report] of Object.entries(data.results)) {
    if (Object.keys(data.results).length > 1) html += engineHeading(engine);
    const shares = report.hedge_shares,
      note =
        shares === null
          ? 'Delta unavailable'
          : shares === 0
            ? 'No hedge trade needed'
            : shares > 0
              ? 'Shares to buy'
              : 'Shares to sell';
    const unit =
      requestSnapshot.legs.length === 1
        ? 'Unit price ' + numberText(report.unit_prices[0], 6) + ' EUR'
        : requestSnapshot.legs.length + ' instruments';
    html +=
      `<div class="metrics"><div class="metric"><div class="metric-label">Position value</div><div class="metric-value">${numberText(report.price)} <small>EUR</small></div><div class="metric-note">${unit}</div></div><div class="metric"><div class="metric-label">Delta hedge</div><div class="metric-value">${numberText(shares, 2)} <small>shares</small></div><div class="metric-note">${note}</div></div><div class="metric"><div class="metric-label">Total engine time</div><div class="metric-value">${numberText(report.timings.total * 1000, 1)} <small>ms</small></div><div class="metric-note">${pricingTimings(report.timings)}${engine === 'vba' ? '<div class="timing-other">Excludes Excel startup and data transfer</div>' : ''}</div></div></div>` +
      warningText(report);
  }
  if (data.results.python && data.results.vba)
    html += `<p class="compare-gap">Python less VBA: ${numberText(data.results.python.price - data.results.vba.price, 10)} EUR</p>`;
  html +=
    '<p class="small-note">Delta timing includes the extra valuations used to size the hedge.</p>';
  $('#results').innerHTML = html;
}
function renderGreeks(data) {
  let html = '';
  for (const [engine, report] of Object.entries(data.results)) {
    if (Object.keys(data.results).length > 1) html += engineHeading(engine);
    html +=
      '<div class="greek-list">' +
      Object.entries(report.greeks)
        .map(
          ([name, row]) =>
            `<details class="greek-item" data-greek="${name}"><summary><span class="greek-name">${labels[name]}<small>${definitions[name]}</small>${row.warning ? '<small class="greek-caution">Check against reference</small>' : ''}</span><span class="greek-value">${numberText(row.value, 6)}<small>${escapeHtml(row.unit)}</small></span></summary><div class="greek-content">${row.warning ? `<p class="notice">${escapeHtml(row.warning)}</p>` : ''}<p class="greek-note">${labels[name]} of the position across share prices</p><div data-curve="${name}" class="graph-empty">Calculating the curve…</div></div></details>`,
        )
        .join('') +
      '</div>';
    html += warningText(report);
  }
  html +=
    '<p class="small-note">Vega and rho per percentage point · Theta and charm per day · Volga per squared volatility point</p>';
  $('#results').innerHTML = html;
  document.querySelectorAll('[data-greek]').forEach(
    (item) =>
      item.addEventListener(
        'toggle',
        () => {
          if (!item.open) return;
          if (busy) {
            item.open = false;
            return;
          }
          const name = item.dataset.greek;
          if (result.curves?.[name]) renderCurve(name, result.curves[name]);
          else run('curve', name);
        },
      ),
  );
}
function renderCurve(name, data) {
  document.querySelectorAll(`[data-curve="${name}"]`).forEach(
    (el) => {
      el.className = '';
      el.innerHTML =
        lineChart(
          data.rows,
          'spot',
          'value',
          'Share price (EUR)',
          labels[name] + ' (' + data.unit + ')',
        ) +
        tableDetails(
          'Show values',
          ['Engine', 'Share price', 'Value'],
          data.rows.map(
            (r) => [
              r.engine.toUpperCase(),
              numberText(r.spot, 2),
              numberText(r.value, 6),
            ],
          ),
        );
    },
  );
}
function renderConvergence(data) {
  const metric = settingsSnapshot.metric || 'price',
    title = labels[metric] || 'Position value';
  let html = `<p class="small-note">Reference: ${escapeHtml(data.reference.label)} = ${numberText(data.reference.value, 8)}${data.reference.empirical ? ' · Numerical reference from a finer grid' : ''}</p>`;
  html += panel(
    'Convergence',
    title,
    `<div class="result-body">${lineChart(data.rows, 'steps', 'value', 'Time steps', title, 'engine', data.reference.value)}</div>`,
  );
  html += panel(
    'Absolute error',
    'Difference from reference',
    `<div class="result-body">${lineChart(data.rows, 'steps', 'error', 'Time steps', 'Absolute error', 'engine', data.tolerance, 'Tolerance')}</div>`,
  );
  html += `<p class="small-note">${data.thresholds.map((row) => `${row.engine.toUpperCase()}: ${row.remaining_tested == null ? 'no tested grid met and maintained the tolerance' : 'all tested grids from ' + row.remaining_tested + ' steps met the tolerance'}`).join(' · ')}. Convergence can oscillate.</p>`;
  html += tableDetails(
    'Show results',
    ['Engine', 'Step', 'Value', 'Absolute error', 'Relative error'],
    data.rows.map(
      (r) => [
        r.engine.toUpperCase(),
        r.steps,
        numberText(r.value, 8),
        numberText(r.error, 8),
        numberText(r.relative_error, 8),
      ],
    ),
  );
  $('#results').innerHTML = html;
}
function renderBenchmark(data) {
  const rows = data.rows.map(
    (r) => ({
      ...r,
      core_ms: r.core * 1000,
    }),
  );
  $('#results').innerHTML =
    panel(
      'Runtime',
      'Tree construction and backward induction',
      `<div class="result-body">${lineChart(rows, 'steps', 'core_ms', 'Time steps', 'Engine time (ms)')}</div>`,
    ) +
    dataTable(
      [
        'Engine',
        'Step',
        'Price (EUR)',
        'Construction (ms)',
        'Pricing (ms)',
        'Engine (ms)',
        'Excel startup (ms)',
        'Transfer (ms)',
        'Total (ms)',
      ],
      rows.map(
        (r) => [
          r.engine.toUpperCase(),
          r.steps,
          numberText(r.value, 6),
          numberText(r.build * 1000, 2),
          numberText(r.price * 1000, 2),
          numberText(r.core_ms, 2),
          numberText(r.startup === undefined ? null : r.startup * 1000, 2),
          numberText(r.bridge === undefined ? null : r.bridge * 1000, 2),
          numberText(r.roundtrip * 1000, 2),
        ],
      ),
    ) +
    '<p class="small-note">Times are the median of two runs. Excel startup and data transfer are measured separately.</p>';
}
function renderTrees(data) {
  let html = '';
  for (const [engine, report] of Object.entries(data.results)) {
    if (Object.keys(data.results).length > 1) html += engineHeading(engine);
    html += panel(
      'Share price and option value',
      'S is the share price and V is the option value, both in euros. Node size and colour show the risk-neutral probability of reaching that point.',
      treeChart(report) +
        '<div class="probability-legend"><span>Lower probability</span><span class="probability-scale"></span><span>Higher probability</span>' +
        (report.nodes.some((node) => node.early_exercise) ? '<span class="exercise-key">Early exercise</span>' : '') + '</div>',
    );
    if (report.note) html += `<p class="small-note">${escapeHtml(report.note)}</p>`;
    html += tableDetails(
      'Show nodes',
      ['Step', 'Share price', 'Option value', 'Probability', 'Early exercise'],
      report.nodes.map(
        (n) => [
          n.step,
          numberText(n.spot, 4),
          numberText(n.value, 6),
          numberText(n.probability * 100, 3) + ' %',
          n.early_exercise ? 'Yes' : 'No',
        ],
      ),
    );
  }
  $('#results').innerHTML = html;
}
async function refreshStatus() {
  try {
    const data = await (await fetch('/api/status')).json();
    $('#vba-status').textContent = data.vba.available ? 'Excel available' : 'Excel unavailable';
    $('#vba-status').title = data.vba.reason || '';
  } catch (error) {
    $('#vba-status').textContent = 'Server unavailable';
  }
}
function download(value, name) {
  const url = URL.createObjectURL(new Blob([value], { type: 'application/json' })),
    a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(
    () =>
      URL.revokeObjectURL(url),
    1000,
  );
}
function validateDate(value) {
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
    !Number.isFinite(Date.parse(value)) ||
    new Date(value).toISOString().slice(0, 10) !== value
  )
    throw Error('The file contains an invalid date');
}
function restore(data) {
  const r = data.request || data;
  if (!r.market || !r.grid || !Array.isArray(r.legs) || !r.legs.length || r.legs.length > 30)
    throw Error('Invalid settings file');
  const restored = r.legs.map(
    (leg) => ({
      ...leg,
      payout: leg.payout ?? 1,
      expression: leg.expression ?? 'max(S-K,0)',
      monitoring: leg.monitoring ?? 'continuous',
    }),
  );
  for (const leg of restored) {
    if (!Object.hasOwn(kinds, leg.kind))
      throw Error('This product is unavailable');
    if (
      typeof leg.american !== 'boolean' ||
      (leg.american && ['digital_call', 'digital_put', 'one_touch_up'].includes(leg.kind))
    )
      throw Error('This exercise style is unavailable for the product');
    for (const key of ['strike', 'quantity', 'multiplier', 'payout'])
      if (typeof leg[key] !== 'number' || !Number.isFinite(leg[key]))
        throw Error('Invalid numeric input');
    if (leg.strike < 0 || leg.multiplier <= 0 || leg.payout < 0)
      throw Error('Invalid contract terms');
    if (!['grid', 'continuous'].includes(leg.monitoring))
      throw Error('Invalid barrier monitoring mode');
    validateDate(leg.expiry);
    delete leg._touch_settled;
  }
  const values = {
    '#spot': r.market.spot,
    '#volatility': r.market.volatility * 100,
    '#rate': r.market.rate * 100,
    '#yield-rate': r.market.yield_rate ?? 0,
    '#dividend': r.market.dividend ?? 0,
    '#valuation-date': r.valuation_date,
    '#dividend-date': r.market.dividend_date || '',
    '#day-basis': r.day_basis ?? 365,
    '#steps': r.grid.steps,
    '#tree-mode': r.grid.mode,
    '#engine': r.engine || 'python',
  };
  values['#yield-rate'] *= 100;
  for (const [id, value] of Object.entries(values)) {
    if ($(id).type === 'number' && !Number.isFinite(Number(value)))
      throw Error('Invalid numeric value');
    if (
      $(id).tagName === 'SELECT' &&
      ![...$(id).options].some(
        (o) =>
          o.value === String(value),
      )
    )
      throw Error('Unknown convention');
  }
  validateDate(r.valuation_date);
  if (r.market.dividend_date) validateDate(r.market.dividend_date);
  if (
    Number(values['#spot']) <= 0 ||
    Number(values['#volatility']) <= 0 ||
    Number(values['#dividend']) < 0
  )
    throw Error('Invalid market inputs');
  Object.entries(values).forEach(
    ([id, value]) =>
      ($(id).value = value),
  );
  $('#use-pruning').checked = Number(r.grid.pruning) > 0;
  legs = restored;
  renderLegs();
  updatePruning();
  markStale();
}
document
  .querySelectorAll('[data-page]')
  .forEach(
    (button) =>
      button.addEventListener(
        'click',
        () => setPage(button.dataset.page),
      ),
  );
$('#add-leg').addEventListener(
  'click',
  () => {
    try {
      syncLegs();
      if (legs.length < 30) {
        legs.push({ ...legs.at(-1) });
        renderLegs();
        markStale();
      }
    } catch (error) {
      showError(error.message);
    }
  },
);
$('#legs').addEventListener(
  'click',
  (event) => {
    const button = event.target.closest('[data-delete]');
    if (button && legs.length > 1) {
      syncLegs();
      legs.splice(Number(button.dataset.delete), 1);
      renderLegs();
      markStale();
    }
  },
);
$('#legs').addEventListener(
  'change',
  (event) => {
    if (!event.target.dataset.field) return;
    try {
      syncLegs();
      if (event.target.dataset.field === 'kind') {
        const leg = legs[Number(event.target.closest('[data-leg]').dataset.leg)];
        if (['digital_call', 'digital_put', 'one_touch_up'].includes(leg.kind))
          leg.american = false;
        renderLegs();
      }
      markStale();
    } catch (error) {
      showError(error.message);
    }
  },
);
$('#legs').addEventListener(
  'input',
  () => {
    try {
      syncLegs();
    } catch (error) {}
    markStale();
  },
);
document.addEventListener(
  'input',
  (event) => {
    if (event.target.matches('input:not([type="file"]),select')) markStale();
  },
);
document.addEventListener(
  'change',
  (event) => {
    if (event.target.matches('input:not([type="file"]),select')) markStale();
    updatePruning();
  },
);
$('#run').addEventListener(
  'click',
  () => run(),
);
$('#refresh-status').addEventListener('click', refreshStatus);
$('#export-config').addEventListener(
  'click',
  () => {
    try {
      download(
        JSON.stringify({ version: 2, request: getRequest() }, null, 2),
        'parametres-pricer.json',
      );
    } catch (error) {
      showError(error.message);
    }
  },
);
$('#import-config').addEventListener(
  'click',
  () => $('#config-file').click(),
);
$('#config-file').addEventListener(
  'change',
  async (event) => {
    const file = event.target.files[0];
    if (!file) return;
    try {
      restore(JSON.parse(await file.text()));
      $('#error').hidden = true;
    } catch (error) {
      showError(error.message);
    } finally {
      event.target.value = '';
    }
  },
);
$('#export-results').addEventListener(
  'click',
  () => {
    if (result)
      download(
        JSON.stringify({ request: requestSnapshot, settings: settingsSnapshot, result }, null, 2),
        'resultats-pricer.json',
      );
  },
);
renderLegs();
updatePruning();
refreshStatus();
