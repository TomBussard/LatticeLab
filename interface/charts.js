const chartColors = ['#176453', '#a86c3d', '#657c9e', '#ad8e4d', '#8b6c8f'];

function escapeHtml(value) {
  return String(value ?? '').replace(
    /[&<>"']/g,
    (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c],
  );
}

function numberText(value, digits = 4) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'n/a';
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

function lineChart(rows, xKey, yKey, xLabel, yLabel, groupKey = 'engine', target = null, targetLabel = 'Reference') {
  const points = rows.filter(
    (r) =>
      Number.isFinite(r[xKey]) && Number.isFinite(r[yKey]),
  );
  if (!points.length)
    return '<div class="graph-empty">No data for this chart</div>';
  const groups = [
    ...new Set(
      points.map(
        (r) => r[groupKey] ?? 'Value',
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
      ...points.map((r) => r[xKey]),
    ),
    xmax = Math.max(
      ...points.map((r) => r[xKey]),
    );
  let ymin = Math.min(
      ...points.map((r) => r[yKey]),
    ),
    ymax = Math.max(
      ...points.map((r) => r[yKey]),
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
  let svg = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(yLabel)} by ${escapeHtml(xLabel)}">`;
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
    svg += `<line x1="${left}" x2="${width - right}" y1="${py(target)}" y2="${py(target)}" stroke="#9faaa0" stroke-dasharray="3 4"><title>${escapeHtml(targetLabel)}: ${target}</title></line>`;
  }
  groups.forEach(
    (group, i) => {
      const data = points
        .filter(
          (r) =>
            (r[groupKey] ?? 'Value') === group,
        )
        .sort((a, b) => a[xKey] - b[xKey]);
      const color = chartColors[i % chartColors.length];
      const dash = String(group).toLowerCase().includes('vba') ? 'stroke-dasharray="6 4"' : '';
      svg += `<polyline points="${data.map((r) => `${px(r[xKey])},${py(r[yKey])}`).join(' ')}" fill="none" stroke="${color}" stroke-width="2" ${dash}/>`;
      data.forEach(
        (r) => {
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
  return `<div class="chart">${svg}</svg></div><div class="chart-legend">${legend}${target !== null ? '<span>··· ' + escapeHtml(targetLabel) + '</span>' : ''}</div>`;
}

function probabilityColor(probability) {
  const t = Math.sqrt(Math.max(0, Math.min(1, probability)));
  return `rgb(${Math.round(36 + 171 * t)},${Math.round(100 - 40 * t)},${Math.round(175 - 108 * t)})`;
}

function treeChart(report) {
  const nodes = report.nodes || [],
    edges = report.edges || [];
  if (!nodes.length) return '<p class="graph-empty">No nodes to display</p>';
  const steps = Math.max(...nodes.map((node) => node.step));
  const columns = Array.from({ length: steps + 1 }, () => []);
  for (const node of nodes) columns[node.step].push(node);
  const rowSpacing = 58;
  const width = Math.max(760, (steps + 1) * 145);
  const height = 76 + rowSpacing * (Math.max(...columns.map((col) => col.length)) - 1);
  const xForStep = (step) => 35 + (step * (width - 150)) / Math.max(steps, 1);
  const locations = new Map();
  columns.forEach((column, step) => {
    column.sort((a, b) => b.spot - a.spot);
    column.forEach((node, i) => {
      locations.set(String(node.id), {
        x: xForStep(step),
        y: height / 2 + (i - (column.length - 1) / 2) * rowSpacing,
      });
    });
  });
  let svg = `<svg viewBox="0 0 ${width} ${height + 36}" width="${width}" role="img" aria-label="Share prices, option values and risk-neutral probabilities by time step">`;
  edges.forEach(
    (edge) => {
      const a = locations.get(String(edge.source)),
        b = locations.get(String(edge.target));
      if (a && b)
        svg += `<line class="tree-line" x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}"><title>Branch probability: ${numberText(edge.probability * 100, 3)} %</title></line>`;
    },
  );
  nodes.forEach(
    (node) => {
      const p = locations.get(String(node.id)),
        probability = Math.max(0, Math.min(1, node.probability)),
        radius = Math.sqrt(9 + 391 * probability);
      svg += `<circle class="tree-node ${node.early_exercise ? 'exercise' : ''}" data-probability="${probability}" cx="${p.x}" cy="${p.y}" r="${radius}" fill="${probabilityColor(probability)}"><title>Step ${node.step} · Share price ${numberText(node.spot, 4)} EUR · Option ${numberText(node.value, 6)} EUR · Probability ${numberText(probability * 100, 4)} %${node.early_exercise ? ' · Early exercise' : ''}</title></circle>`;
      const labelX = p.x + radius + 4;
      svg += `<text class="tree-text" x="${labelX}" y="${p.y - 2}">S ${numberText(node.spot, 2)}</text>`;
      svg += `<text class="tree-text tree-value" x="${labelX}" y="${p.y + 12}">V ${numberText(node.value, 2)}</text>`;
    },
  );
  for (let step = 0; step <= steps; step++)
    svg += `<text class="chart-tick" x="${xForStep(step)}" y="${height + 16}" text-anchor="middle">Step ${step}</text>`;
  return `<div class="tree-scroll">${svg}</svg></div>`;
}
