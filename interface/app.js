/** On retrouve un élément du formulaire à partir de son sélecteur */
const $ = (selector) => document.querySelector(selector);
const labels = {
  delta: 'Delta',
  gamma: 'Gamma',
  vega: 'Véga',
  theta: 'Thêta',
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
  digital_call: 'Digitale call',
  digital_put: 'Digitale put',
  one_touch_up: 'One-touch haut',
  custom: 'Payoff libre',
};
const pages = {
  price: ['Valorisation', 'Prix de la position et couverture en actions', 'Calculer'],
  greeks: ['Grecs', 'Cliquez sur un grec pour afficher sa courbe', 'Calculer les grecs'],
  convergence: [
    'Convergence',
    'Évolution du résultat lorsque le nombre de pas augmente',
    'Calculer la convergence',
  ],
  benchmark: [
    'Temps de calcul',
    'Comparaison du temps nécessaire aux deux moteurs',
    'Mesurer les temps',
  ],
  tree: ['Arbre', 'Taille et couleur des nœuds selon leur probabilité', 'Construire l’arbre'],
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

/** On construit les choix HTML d’une liste en conservant la valeur sélectionnée */
function options(map, selected) {
  return Object.entries(map)
    .map(
      /** On transforme un choix en option HTML sélectionnable */
      ([value, label]) =>
        `<option value="${value}" ${String(value) === String(selected) ? 'selected' : ''}>${escapeHtml(label)}</option>`,
    )
    .join('');
}
/** On affiche les lignes de la position et les champs propres à chaque produit */
function renderLegs() {
  $('#legs').innerHTML = legs
    .map(
      /** On construit les cellules et les champs d’une ligne de position */
      (leg, i) =>
        `<tr data-leg="${i}"><td><select data-field="kind" aria-label="Produit ligne ${i + 1}">${options(kinds, leg.kind)}</select></td><td><select data-field="american" aria-label="Exercice ligne ${i + 1}" ${['digital_call', 'digital_put', 'one_touch_up'].includes(leg.kind) ? 'disabled' : ''}>${options({ false: 'Européen', true: 'Américain' }, leg.american)}</select></td><td><input data-field="strike" aria-label="Strike ligne ${i + 1}" type="number" step="any" min="0" value="${leg.strike}"></td><td><input data-field="expiry" aria-label="Échéance ligne ${i + 1}" type="date" value="${escapeHtml(leg.expiry)}"></td><td><input data-field="quantity" aria-label="Quantité ligne ${i + 1}" type="number" step="any" value="${leg.quantity}"></td><td><input data-field="multiplier" aria-label="Multiplicateur ligne ${i + 1}" type="number" min="0.001" step="any" value="${leg.multiplier}"></td><td><button class="delete-leg" data-delete="${i}" aria-label="Supprimer la ligne ${i + 1}" ${legs.length === 1 ? 'disabled' : ''}>×</button></td></tr>${extraLeg(leg, i)}`,
    )
    .join('');
}
/** On ajoute les champs de versement, de barrière ou de payoff nécessaires au produit */
function extraLeg(leg, i) {
  let fields = '';
  if (['digital_call', 'digital_put', 'one_touch_up'].includes(leg.kind))
    fields += `<label>Versement (EUR)<input data-field="payout" type="number" min="0" step="any" value="${leg.payout}"></label>`;
  if (leg.kind === 'one_touch_up')
    fields += `<label>Observation<select data-field="monitoring">${options({ continuous: 'Continue', grid: 'Dates de l’arbre' }, leg.monitoring)}</select></label>`;
  if (leg.kind === 'custom')
    fields += `<label>Payoff f(S, K)<input class="expression" data-field="expression" value="${escapeHtml(leg.expression)}"></label>`;
  return fields
    ? `<tr class="extra-leg" data-leg="${i}"><td colspan="7"><div class="extra-fields">${fields}</div></td></tr>`
    : '';
}
/** On lit et on vérifie les champs des instruments pour actualiser la position */
function syncLegs() {
  document.querySelectorAll('#legs [data-field]').forEach(
    /** On reporte le champ modifié dans les paramètres de son instrument */ (field) => {
      const leg = legs[Number(field.closest('[data-leg]').dataset.leg)],
        key = field.dataset.field;
      if (key === 'american') leg[key] = field.value === 'true';
      else if (['kind', 'expiry', 'expression', 'monitoring'].includes(key)) leg[key] = field.value;
      else {
        if (!field.value.trim() || !Number.isFinite(Number(field.value)))
          throw Error('Renseignez les paramètres numériques des instruments');
        leg[key] = Number(field.value);
      }
    },
  );
}
/** On lit une valeur numérique du formulaire et on refuse une saisie manquante */
function readNumber(id) {
  const field = $(id);
  if (!field.value.trim() || !Number.isFinite(Number(field.value)))
    throw Error('Un paramètre numérique est manquant');
  return Number(field.value);
}
/** On rassemble le marché, les contrats et les conventions dans la demande de calcul */
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
/** On lit les réglages propres à l’analyse affichée */
function getSettings() {
  return page === 'convergence'
    ? { metric: $('#metric').value, tolerance: readNumber('#tolerance') }
    : {};
}
/** On crée les champs supplémentaires nécessaires à l’onglet choisi */
function pageOptions() {
  if (page === 'convergence')
    return `<div class="options-panel"><div class="options-grid"><label>Résultat à étudier<select id="metric">${options({ price: 'Prix de la position', ...labels }, 'price')}</select></label><label>Tolérance absolue<input id="tolerance" type="number" step="any" min="0.00000001" value="0.001"></label></div></div>`;
  return '';
}
/** On change d’onglet et on prépare son affichage sans lancer de calcul */
function setPage(next) {
  if (busy || next === page) return;
  page = next;
  result = requestSnapshot = settingsSnapshot = null;
  document.querySelectorAll('.nav-item').forEach(
    /** On indique dans la navigation quel onglet est actif */ (button) => {
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
      ? 'Vue illustrative sur 6 pas, avec les paramètres de la position'
      : page === 'convergence' || page === 'benchmark'
        ? 'Les nombres de pas seront choisis au lancement du calcul'
        : '';
  $('#results').innerHTML =
    `<p class="empty-state">Cliquez sur « ${pages[page][2]} » pour lancer le calcul.</p>`;
  $('#stale').hidden = $('#error').hidden = true;
  $('#export-results').disabled = true;
}
/** On signale que les résultats doivent être recalculés après une modification */
function markStale() {
  if (result) $('#stale').hidden = false;
}
/** On adapte le contrôle de pruning au type d’arbre sélectionné */
function updatePruning() {
  const binomial = $('#tree-mode').value === 'binomial';
  $('#use-pruning').disabled = binomial;
  $('#pruning-note').textContent = binomial
    ? 'Le pruning est disponible avec l’arbre trinomial'
    : 'Écarter les branches très peu probables';
}
/** On affiche le message d’erreur à côté du formulaire */
function showError(message) {
  $('#error').textContent = message;
  $('#error').hidden = false;
}
/** On suit la demande sur le serveur jusqu’au résultat ou à l’erreur */
async function poll(id) {
  while (true) {
    const response = await fetch('/api/jobs/' + id),
      job = await response.json();
    if (!response.ok) throw Error(job.error || 'Serveur indisponible');
    $('#progress-message').textContent = job.progress || 'Calcul en cours';
    if (job.state === 'done') return job.result;
    if (job.state === 'error') throw Error(job.error);
    await new Promise(
      /** On attend brièvement avant de redemander l’état du calcul */ (resolve) =>
        setTimeout(resolve, 300),
    );
  }
}
/** On lance l’analyse demandée, on suit son avancement et on affiche son résultat */
async function run(action = page, metric = null) {
  if (busy) return;
  let payload;
  try {
    if (action === 'curve') {
      if (!requestSnapshot || !$('#stale').hidden)
        throw Error('Recalculez les grecs après avoir modifié les paramètres');
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
          /** On affiche l’erreur dans le bloc de la courbe demandée */ (el) =>
            (el.textContent = error.message),
        );
    return;
  }
  const controls = [...document.querySelectorAll('input,select,button')].map(
    /** On mémorise l’état des contrôles avant le calcul */ (el) => [el, el.disabled],
  );
  controls.forEach(
    /** On désactive les contrôles pendant le calcul */ ([el]) => (el.disabled = true),
  );
  busy = true;
  document.body.classList.add('busy');
  $('#progress').hidden = false;
  $('#error').hidden = true;
  $('#progress-message').textContent =
    action === 'curve' ? 'Calcul de la courbe de ' + labels[metric] : 'Calcul en cours';
  const start = performance.now(),
    timer = setInterval(
      /** On actualise le temps écoulé affiché pendant le calcul */
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
        /** On signale l’erreur dans les blocs de la courbe concernée */ (el) =>
          (el.textContent = error.message),
      );
  } finally {
    busy = false;
    clearInterval(timer);
    document.body.classList.remove('busy');
    $('#progress').hidden = true;
    controls.forEach(
      /** On rétablit l’état des contrôles après le calcul */ ([el, disabled]) => {
        if (el.isConnected) el.disabled = disabled;
      },
    );
    $('#export-results').disabled = !result;
    updatePruning();
  }
}
/** On construit un panneau de résultats avec son titre et son contenu */
function panel(title, subtitle, body) {
  return `<section class="result-panel"><div class="section-heading"><div><h3>${escapeHtml(title)}</h3>${subtitle ? `<p>${escapeHtml(subtitle)}</p>` : ''}</div></div>${body}</section>`;
}
/** On transforme les en-têtes et les lignes en tableau HTML */
function dataTable(headers, rows) {
  return `<div class="table-scroll"><table><thead><tr>${headers.map(/** On construit la cellule d’en-tête du tableau */ (h) => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead><tbody>${rows.map(/** On construit une ligne du tableau de résultats */ (row) => `<tr>${row.map(/** On transforme la valeur en cellule de tableau */ (c) => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
/** On place un tableau dans un bloc que l’utilisateur peut déplier */
function tableDetails(title, headers, rows) {
  return `<details class="values-details"><summary>${escapeHtml(title)}</summary>${dataTable(headers, rows)}</details>`;
}
/** On affiche le nom du moteur au-dessus de ses résultats */
function engineHeading(name) {
  return `<div class="engine-title">${name === 'python' ? 'Python' : 'VBA / Excel'}</div>`;
}
/** On choisit la présentation correspondant au type de résultat reçu */
function renderResult(data) {
  if (data.action === 'price') renderPrices(data);
  else if (data.action === 'greeks') renderGreeks(data);
  else if (data.action === 'convergence') renderConvergence(data);
  else if (data.action === 'benchmark') renderBenchmark(data);
  else if (data.action === 'tree') renderTrees(data);
}
/** On prépare les messages qui expliquent les limites du calcul */
function warningText(report) {
  return (report.warnings || [])
    .map(
      /** On transforme un avertissement en paragraphe lisible */ (text) =>
        `<p class="small-note">${escapeHtml(text)}</p>`,
    )
    .join('');
}
/** On distingue les temps de construction, de valorisation et de couverture */
function pricingTimings(times) {
  const rows = [
    ['Arbre + valorisation', times.build + times.price, 'timing-price'],
    ['Construction de l’arbre', times.build, 'timing-detail'],
    ['Valorisation', times.price, 'timing-detail'],
    ['Couverture en delta', times.greeks, 'timing-hedge'],
  ];
  const other = Math.max(0, times.total - times.build - times.price - times.greeks);
  if (other >= 0.00005) rows.push(['Autres traitements', other, 'timing-other']);
  return (
    '<div class="timing-breakdown">' +
    rows
      .map(
        /** On affiche le libellé et la durée de cette étape du calcul */
        ([label, seconds, style]) =>
          `<div class="${style}"><span>${label}</span><span>${numberText(seconds * 1000, 1)} ms</span></div>`,
      )
      .join('') +
    '</div>'
  );
}
/** On présente les prix, la valeur de position, la couverture et les temps */
function renderPrices(data) {
  let html = '';
  for (const [engine, report] of Object.entries(data.results)) {
    if (Object.keys(data.results).length > 1) html += engineHeading(engine);
    const shares = report.hedge_shares,
      note =
        shares === null
          ? 'Delta indisponible'
          : shares === 0
            ? 'Aucune action nécessaire'
            : shares > 0
              ? 'Actions à acheter'
              : 'Actions à vendre';
    const unit =
      requestSnapshot.legs.length === 1
        ? 'Prix unitaire : ' + numberText(report.unit_prices[0], 6) + ' EUR'
        : requestSnapshot.legs.length + ' instruments';
    html +=
      `<div class="metrics"><div class="metric"><div class="metric-label">Valeur de la position</div><div class="metric-value">${numberText(report.price)} <small>EUR</small></div><div class="metric-note">${unit}</div></div><div class="metric"><div class="metric-label">Couverture en delta</div><div class="metric-value">${numberText(shares, 2)} <small>actions</small></div><div class="metric-note">${note}</div></div><div class="metric"><div class="metric-label">Temps total du moteur</div><div class="metric-value">${numberText(report.timings.total * 1000, 1)} <small>ms</small></div><div class="metric-note">${pricingTimings(report.timings)}${engine === 'vba' ? '<div class="timing-other">Hors ouverture d’Excel et échanges</div>' : ''}</div></div></div>` +
      warningText(report);
  }
  if (data.results.python && data.results.vba)
    html += `<p class="compare-gap">Écart Python − VBA : ${numberText(data.results.python.price - data.results.vba.price, 10)} EUR</p>`;
  html +=
    '<p class="small-note">Le temps du delta inclut les valorisations supplémentaires nécessaires à la couverture et les opérations associées.</p>';
  $('#results').innerHTML = html;
}
/** On affiche les sensibilités et on prépare l’ouverture de leurs courbes */
function renderGreeks(data) {
  let html = '';
  for (const [engine, report] of Object.entries(data.results)) {
    if (Object.keys(data.results).length > 1) html += engineHeading(engine);
    html +=
      '<div class="greek-list">' +
      Object.entries(report.greeks)
        .map(
          /** On crée le bloc dépliable d’un grec avec sa valeur et sa courbe */
          ([name, row]) =>
            `<details class="greek-item" data-greek="${name}"><summary><span class="greek-name">${labels[name]}<small>${definitions[name]}</small>${row.warning ? '<small class="greek-caution">À contrôler</small>' : ''}</span><span class="greek-value">${numberText(row.value, 6)}<small>${escapeHtml(row.unit)}</small></span></summary><div class="greek-content">${row.warning ? `<p class="notice">${escapeHtml(row.warning)}</p>` : ''}<p class="greek-note">${labels[name]} de la position en fonction du prix de l’action</p><div data-curve="${name}" class="graph-empty">Calcul de la courbe…</div></div></details>`,
        )
        .join('') +
      '</div>';
    html += warningText(report);
  }
  html +=
    '<p class="small-note">Véga et rho par point de pourcentage · Thêta et charm par jour · Volga par point de volatilité au carré</p>';
  $('#results').innerHTML = html;
  document.querySelectorAll('[data-greek]').forEach(
    /** On associe l’ouverture d’un bloc à la demande de sa courbe */ (item) =>
      item.addEventListener(
        'toggle',
        /** On calcule la courbe à l’ouverture du grec si elle n’a pas encore été obtenue */ () => {
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
/** On affiche la courbe et le tableau du grec demandé */
function renderCurve(name, data) {
  document.querySelectorAll(`[data-curve="${name}"]`).forEach(
    /** On remplit le bloc de courbe avec le graphique et les valeurs reçues */ (el) => {
      el.className = '';
      el.innerHTML =
        lineChart(
          data.rows,
          'spot',
          'value',
          'Prix de l’action (EUR)',
          labels[name] + ' (' + data.unit + ')',
        ) +
        tableDetails(
          'Voir les valeurs',
          ['Moteur', 'Prix de l’action', 'Valeur'],
          data.rows.map(
            /** On prépare la ligne de valeurs correspondant à ce spot */ (r) => [
              r.engine.toUpperCase(),
              numberText(r.spot, 2),
              numberText(r.value, 6),
            ],
          ),
        );
    },
  );
}
/** On présente la convergence et les erreurs par rapport à la référence */
function renderConvergence(data) {
  const metric = settingsSnapshot.metric || 'price',
    title = labels[metric] || 'Prix de la position';
  let html = `<p class="small-note">Référence : ${escapeHtml(data.reference.label)} = ${numberText(data.reference.value, 8)}${data.reference.empirical ? ' · Comparaison numérique, sans garantie d’erreur exacte' : ''}</p>`;
  html += panel(
    'Convergence',
    title,
    `<div class="result-body">${lineChart(data.rows, 'steps', 'value', 'Nombre de pas', title, 'engine', data.reference.value)}</div>`,
  );
  html += panel(
    'Erreur absolue',
    'Écart avec la référence',
    `<div class="result-body">${lineChart(data.rows, 'steps', 'error', 'Nombre de pas', 'Erreur absolue', 'engine', data.tolerance)}</div>`,
  );
  html += `<p class="small-note">${data.thresholds.map(/** On résume les nombres de pas qui respectent la tolérance */ (row) => `${row.engine.toUpperCase()} : ${row.remaining_tested ?? 'aucun nombre de'} pas ${row.remaining_tested ? 'et les valeurs suivantes testées sont sous' : 'testé sous'} la tolérance`).join(' · ')}. La convergence peut osciller.</p>`;
  html += tableDetails(
    'Voir les résultats',
    ['Moteur', 'Pas', 'Valeur', 'Erreur absolue', 'Erreur relative'],
    data.rows.map(
      /** On prépare une ligne avec le nombre de pas et les erreurs mesurées */ (r) => [
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
/** On compare les prix et les temps mesurés dans les moteurs */
function renderBenchmark(data) {
  const rows = data.rows.map(
    /** On convertit le temps du moteur en millisecondes pour le graphique */ (r) => ({
      ...r,
      core_ms: r.core * 1000,
    }),
  );
  $('#results').innerHTML =
    panel(
      'Temps de calcul',
      'Construction et valorisation de l’arbre',
      `<div class="result-body">${lineChart(rows, 'steps', 'core_ms', 'Nombre de pas', 'Temps du moteur (ms)')}</div>`,
    ) +
    dataTable(
      [
        'Moteur',
        'Pas',
        'Prix (EUR)',
        'Construction (ms)',
        'Valorisation (ms)',
        'Moteur (ms)',
        'Ouverture Excel (ms)',
        'Échanges (ms)',
        'Total (ms)',
      ],
      rows.map(
        /** On présente les temps détaillés du moteur et de ses échanges */ (r) => [
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
    '<p class="small-note">Les calculs sont répétés automatiquement. Le temps du moteur est distingué du démarrage et des échanges avec Excel.</p>';
}
/** On affiche les arbres, leurs probabilités et le détail des nœuds */
function renderTrees(data) {
  let html = '';
  for (const [engine, report] of Object.entries(data.results)) {
    if (Object.keys(data.results).length > 1) html += engineHeading(engine);
    html += panel(
      'Arbre des probabilités',
      'Plus le nœud est probable, plus il est grand et rouge',
      treeChart(report) +
        '<div class="probability-legend"><span>Peu probable</span><span class="probability-scale"></span><span>Très probable</span></div>',
    );
    if (report.note) html += `<p class="small-note">${escapeHtml(report.note)}</p>`;
    html += tableDetails(
      'Voir les nœuds',
      ['Pas', 'Prix de l’action', 'Valeur de l’option', 'Probabilité', 'Exercice anticipé'],
      report.nodes.map(
        /** On prépare une ligne décrivant le prix et la probabilité du nœud */ (n) => [
          n.step,
          numberText(n.spot, 4),
          numberText(n.value, 6),
          numberText(n.probability * 100, 3) + ' %',
          n.early_exercise ? 'Oui' : '—',
        ],
      ),
    );
  }
  $('#results').innerHTML = html;
}
/** On vérifie les moteurs disponibles et on actualise leur indication à l’écran */
async function refreshStatus() {
  try {
    const data = await (await fetch('/api/status')).json();
    $('#vba-status').textContent = data.vba.available ? 'Excel disponible' : 'Excel indisponible';
    $('#vba-status').title = data.vba.reason || '';
  } catch (error) {
    $('#vba-status').textContent = 'Serveur indisponible';
  }
}
/** On déclenche le téléchargement local du texte JSON fourni */
function download(value, name) {
  const url = URL.createObjectURL(new Blob([value], { type: 'application/json' })),
    a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(
    /** On libère l’adresse temporaire créée pour le téléchargement */ () =>
      URL.revokeObjectURL(url),
    1000,
  );
}
/** On vérifie qu’une date importée existe et respecte le format attendu */
function validateDate(value) {
  if (
    !/^\d{4}-\d{2}-\d{2}$/.test(value) ||
    !Number.isFinite(Date.parse(value)) ||
    new Date(value).toISOString().slice(0, 10) !== value
  )
    throw Error('Date invalide dans le fichier');
}
/** On vérifie la configuration importée puis on remplit les champs du formulaire */
function restore(data) {
  const r = data.request || data;
  if (!r.market || !r.grid || !Array.isArray(r.legs) || !r.legs.length || r.legs.length > 30)
    throw Error('Fichier de paramètres invalide');
  const restored = r.legs.map(
    /** On complète les champs optionnels d’un instrument importé */ (leg) => ({
      ...leg,
      payout: leg.payout ?? 1,
      expression: leg.expression ?? 'max(S-K,0)',
      monitoring: leg.monitoring ?? 'continuous',
    }),
  );
  for (const leg of restored) {
    if (!Object.hasOwn(kinds, leg.kind))
      throw Error('Ce produit ne fait pas partie du calculateur');
    if (
      typeof leg.american !== 'boolean' ||
      (leg.american && ['digital_call', 'digital_put', 'one_touch_up'].includes(leg.kind))
    )
      throw Error('Exercice incompatible avec ce produit');
    for (const key of ['strike', 'quantity', 'multiplier', 'payout'])
      if (typeof leg[key] !== 'number' || !Number.isFinite(leg[key]))
        throw Error('Paramètre numérique invalide');
    if (leg.strike < 0 || leg.multiplier <= 0 || leg.payout < 0)
      throw Error('Paramètre de contrat invalide');
    if (!['grid', 'continuous'].includes(leg.monitoring))
      throw Error('Observation de barrière invalide');
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
      throw Error('Valeur numérique invalide');
    if (
      $(id).tagName === 'SELECT' &&
      ![...$(id).options].some(
        /** On vérifie que la valeur importée existe dans la liste de choix */ (o) =>
          o.value === String(value),
      )
    )
      throw Error('Convention inconnue');
  }
  validateDate(r.valuation_date);
  if (r.market.dividend_date) validateDate(r.market.dividend_date);
  if (
    Number(values['#spot']) <= 0 ||
    Number(values['#volatility']) <= 0 ||
    Number(values['#dividend']) < 0
  )
    throw Error('Marché invalide');
  Object.entries(values).forEach(
    /** On reporte une valeur importée dans son champ du formulaire */ ([id, value]) =>
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
    /** On relie chaque bouton de navigation à son onglet */ (button) =>
      button.addEventListener(
        'click',
        /** On ouvre l’onglet correspondant au bouton cliqué */ () => setPage(button.dataset.page),
      ),
  );
$('#add-leg').addEventListener(
  'click',
  /** On ajoute un instrument en reprenant les paramètres de la dernière ligne */ () => {
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
  /** On retire l’instrument dont le bouton de suppression est cliqué */ (event) => {
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
  /** On adapte les champs de l’instrument après un changement de produit */ (event) => {
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
  /** On mémorise la saisie et on signale que les résultats sont à recalculer */ () => {
    try {
      syncLegs();
    } catch (error) {}
    markStale();
  },
);
document.addEventListener(
  'input',
  /** On marque les résultats comme anciens lorsqu’un champ est saisi */ (event) => {
    if (event.target.matches('input:not([type="file"]),select')) markStale();
  },
);
document.addEventListener(
  'change',
  /** On actualise le pruning et l’état des résultats après un changement de choix */ (event) => {
    if (event.target.matches('input:not([type="file"]),select')) markStale();
    updatePruning();
  },
);
$('#run').addEventListener(
  'click',
  /** On lance le calcul lorsque le bouton principal est cliqué */ () => run(),
);
$('#refresh-status').addEventListener('click', refreshStatus);
$('#export-config').addEventListener(
  'click',
  /** On exporte les paramètres courants dans un fichier JSON */ () => {
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
  /** On ouvre le sélecteur du fichier de paramètres à importer */ () => $('#config-file').click(),
);
$('#config-file').addEventListener(
  'change',
  /** On lit le fichier choisi et on restaure sa configuration */ async (event) => {
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
  /** On exporte les résultats avec les paramètres utilisés pour leur calcul */ () => {
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
