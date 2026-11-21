const chartColors = ['#176453', '#a86c3d', '#657c9e', '#ad8e4d', '#8b6c8f'];

function escapeHtml(value) {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
}

function numberText(value, digits = 4) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return '—';
  const numeric = Number(value);
  return (numeric === 0 ? 0 : numeric).toLocaleString('en-GB', {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function axisNumber(value) {
  if (Math.abs(value) > 0 && (Math.abs(value) < 0.001 || Math.abs(value) > 100000))
    return value.toExponential(1);
  return Number(value.toPrecision(4)).toLocaleString('en-GB');
}

function lineChart(rows, xKey, yKey, xLabel, yLabel, groupKey = 'engine', target = null) {
  const points = rows.filter(
    /** On conserve seulement les points dont les coordonnées sont finies */ (r) =>
      Number.isFinite(r[xKey]) && Number.isFinite(r[yKey]),
  );
  if (!points.length)
    return '<div class="graph-empty">Aucune donnée disponible pour ce graphique</div>';
  const groups = [
    ...new Set(
      points.map(
        /** On retrouve le groupe auquel appartient ce point */ (r) => r[groupKey] ?? 'Valeur',
      ),
    ),
  ];
  const width = 860,
    height = 300,
    left = 75,
    right = 22,
    top = 24,
    bottom = 50;
  let xmin = Math.min(
      ...points.map(/** On lit l’abscisse pour déterminer la borne minimale */ (r) => r[xKey]),
    ),
    xmax = Math.max(
      ...points.map(/** On lit l’abscisse pour déterminer la borne maximale */ (r) => r[xKey]),
    );
  let ymin = Math.min(
      ...points.map(/** On lit l’ordonnée pour déterminer la borne minimale */ (r) => r[yKey]),
    ),
    ymax = Math.max(
      ...points.map(/** On lit l’ordonnée pour déterminer la borne maximale */ (r) => r[yKey]),
    );
  if (target !== null && Number.isFinite(target)) {
    ymin = Math.min(ymin, target);
    ymax = Math.max(ymax, target);
  }
  if (xmin === xmax) {
    xmin -= 1;
    xmax += 1;
  }
  const pad = (ymax - ymin) * 0.12 || Math.max(Math.abs(ymax) * 0.05, 0.001);
  ymin -= pad;
  ymax += pad;
  if (['error', 'total_ms', 'roundtrip_ms', 'core_ms'].includes(yKey)) ymin = 0;
  const px = (x) => left + ((x - xmin) / (xmax - xmin)) * (width - left - right);
  const py = (y) => height - bottom - ((y - ymin) / (ymax - ymin)) * (height - top - bottom);
  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(yLabel)} en fonction de ${escapeHtml(xLabel)}">`;
  for (let i = 0; i <= 4; i++) {
    const y = ymin + (i / 4) * (ymax - ymin),
      x = xmin + (i / 4) * (xmax - xmin);
    svg += `<line class="chart-grid" x1="${left}" x2="${width - right}" y1="${py(y)}" y2="${py(y)}"/>`;
    svg += `<text class="chart-tick" x="${left - 12}" y="${py(y) + 4}" text-anchor="end">${axisNumber(y)}</text>`;
    svg += `<text class="chart-tick" x="${px(x)}" y="${height - bottom + 21}" text-anchor="middle">${axisNumber(x)}</text>`;
  }
  svg += `<text class="chart-label" x="${left}" y="12">${escapeHtml(yLabel)}</text>`;
  svg += `<text class="chart-label" x="${width - right}" y="${height - 8}" text-anchor="end">${escapeHtml(xLabel)}</text>`;
  if (target !== null && Number.isFinite(target)) {
    svg += `<line x1="${left}" x2="${width - right}" y1="${py(target)}" y2="${py(target)}" stroke="#9faaa0" stroke-dasharray="3 4"><title>Référence : ${target}</title></line>`;
  }
  groups.forEach(
    /** On dessine la courbe et les points de ce groupe */ (group, i) => {
      const data = points
        .filter(
          /** On conserve les points du groupe en cours de dessin */ (r) =>
            (r[groupKey] ?? 'Valeur') === group,
        )
        .sort(/** On classe les points par abscisse croissante */ (a, b) => a[xKey] - b[xKey]);
      const color = chartColors[i % chartColors.length];
      const dash = String(group).toLowerCase().includes('vba') ? 'stroke-dasharray="6 4"' : '';
      svg += `<polyline points="${data.map(/** On convertit le point en coordonnées utilisables par la ligne SVG */ (r) => `${px(r[xKey])},${py(r[yKey])}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2" ${dash}/>`;
      data.forEach(
        /** On ajoute le point et son information au survol */ (r) => {
          svg += `<circle cx="${px(r[xKey])}" cy="${py(r[yKey])}" r="3" fill="${color}"><title>${escapeHtml(group)} · ${escapeHtml(xLabel)} ${r[xKey]} · ${escapeHtml(yLabel)} ${r[yKey]}</title></circle>`;
        },
      );
    },
  );
  const legend = groups
    .map(
      (group, i) =>
        `<span><svg width="20" height="10" aria-hidden="true"><line x1="0" x2="17" y1="5" y2="5" stroke="${chartColors[i % chartColors.length]}" stroke-width="2" ${String(group).includes('vba') ? 'stroke-dasharray="4 3"' : ''}/></svg> ${escapeHtml(String(group).toUpperCase())}</span>`,
    )
    .join('');
  return `<div class="chart">${svg}</svg></div><div class="chart-legend">${legend}${target !== null ? '<span>··· Référence</span>' : ''}</div>`;
}

function probabilityColor(probability) {
  const t = Math.sqrt(Math.max(0, Math.min(1, probability)));
  return `rgb(${Math.round(36 + 171 * t)},${Math.round(100 - 40 * t)},${Math.round(175 - 108 * t)})`;
}

function treeChart(report) {
  const nodes = report.nodes || [],
    edges = report.edges || [];
  if (!nodes.length) return '<p class="graph-empty">Tree vide</p>';
  const steps = Math.max(
    ...nodes.map(
      /** On lit le numéro de pas pour déterminer la profondeur de l’arbre */ (n) => n.step,
    ),
  );
  const width = Math.max(820, (steps + 1) * 145),
    height = Math.max(330, (2 * steps + 1) * 44);
  const locations = new Map();
  for (let step = 0; step <= steps; step++) {
    const column = nodes
      .filter(/** On conserve les nœuds de la colonne en cours */ (n) => n.step === step)
      .sort(
        /** On classe les nœuds de la colonne par prix décroissant */ (a, b) => b.spot - a.spot,
      );
    column.forEach(
      /** On attribue au nœud sa position dans la colonne du dessin */ (node, i) =>
        locations.set(String(node.id), {
          x: 45 + (step * (width - 145)) / Math.max(steps, 1),
          y: height / 2 + (i - (column.length - 1) / 2) * 44,
        }),
    );
  }
  let svg = `<svg viewBox="0 0 ${width} ${height + 36}" width="${width}" role="img" aria-label="Transition probabilities">`;
  edges.forEach(
    /** On dessine le lien entre les deux nœuds de la branche */ (edge) => {
      const a = locations.get(String(edge.source)),
        b = locations.get(String(edge.target));
      if (a && b)
        svg += `<line class="tree-line" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"><title>Probability de transition : ${numberText(edge.probability * 100, 3)} %</title></line>`;
    },
  );
  nodes.forEach(
    /** On dessine le nœud avec une taille et une couleur liées à sa probabilité */ (node) => {
      const p = locations.get(String(node.id)),
        probability = Math.max(0, Math.min(1, node.probability)),
        radius = Math.sqrt(9 + 391 * probability);
      svg += `<circle class="tree-node ${node.early_exercise ? 'exercise' : ''}" data-probability="${probability}" cx="${p.x}" cy="${p.y}" r="${radius}" fill="${probabilityColor(probability)}"><title>Pas ${node.step} · Action ${numberText(node.spot, 4)} EUR · Option ${numberText(node.value, 6)} EUR · Probability ${numberText(probability * 100, 4)} %${node.early_exercise ? ' · Early exercise' : ''}</title></circle>`;
      svg += `<text class="tree-text" x="${p.x + radius + 5}" y="${p.y + 4}">${numberText(node.spot, 2)}</text>`;
    },
  );
  for (let step = 0; step <= steps; step++)
    svg += `<text class="chart-tick" x="${45 + (step * (width - 145)) / Math.max(steps, 1)}" y="${height + 22}" text-anchor="middle">${step}</text>`;
  return `<div class="tree-scroll">${svg}</svg></div>`;
}
