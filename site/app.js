// Trading Research Bot dashboard — vanilla JS, no build step, no dependencies.
// Reads data/latest.json (written by src/report.py each time the pipeline runs).

const COLOR_OTHER = getComputedStyle(document.documentElement).getPropertyValue('--series-1').trim() || '#2a78d6';
const COLOR_DIAMOND = getComputedStyle(document.documentElement).getPropertyValue('--series-3').trim() || '#1baf7a';
const COLOR_SMART_RING = getComputedStyle(document.documentElement).getPropertyValue('--status-good').trim() || '#0ca30c';

let allStocks = [];
let sortState = { col: 'conviction_score', dir: 'desc' };

async function init() {
  let data;
  try {
    const resp = await fetch('data/latest.json', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    data = await resp.json();
  } catch (err) {
    document.getElementById('subtitle').textContent =
      'Could not load data/latest.json — run the pipeline at least once (python3 -m src.main), ' +
      'or if you are previewing locally, serve this folder with `python3 -m http.server` rather than opening index.html directly (browsers block fetch() on file:// paths).';
    console.error(err);
    return;
  }

  allStocks = data.stocks || [];
  document.getElementById('subtitle').textContent =
    `${allStocks.length} stocks scanned · generated ${formatTimestamp(data.generated_at)}`;

  renderStatTiles(data);
  populateSectorFilter(allStocks);
  renderScatter(allStocks);
  renderTable();
  wireControls();
  renderFooter(data);
}

function formatTimestamp(ts) {
  // ts format: YYYY-MM-DD_HHMM
  if (!ts) return 'unknown time';
  const [datePart, timePart] = ts.split('_');
  if (!timePart) return datePart;
  return `${datePart} ${timePart.slice(0, 2)}:${timePart.slice(2, 4)}`;
}

function renderStatTiles(data) {
  const diamonds = allStocks.filter(s => s.diamond_in_rough).length;
  const smart = allStocks.filter(s => s.smart_money_aligned).length;
  const avgConviction = allStocks.length
    ? (allStocks.reduce((sum, s) => sum + (s.conviction_score || 0), 0) / allStocks.length).toFixed(1)
    : '—';

  const tiles = [
    { value: allStocks.length, label: 'Stocks scanned' },
    { value: diamonds, label: 'Diamond-in-the-rough' },
    { value: smart, label: 'Smart-money aligned' },
    { value: avgConviction, label: 'Avg. conviction score' },
  ];

  const row = document.getElementById('statRow');
  row.innerHTML = tiles.map(t => `
    <div class="stat-tile">
      <div class="value">${t.value}</div>
      <div class="label">${t.label}</div>
    </div>
  `).join('');
}

function populateSectorFilter(stocks) {
  const sectors = [...new Set(stocks.map(s => s.sector).filter(Boolean))].sort();
  const select = document.getElementById('sectorFilter');
  for (const sector of sectors) {
    const opt = document.createElement('option');
    opt.value = sector;
    opt.textContent = sector;
    select.appendChild(opt);
  }
}

function pointColor(s) {
  return s.diamond_in_rough ? COLOR_DIAMOND : COLOR_OTHER;
}

function renderScatter(stocks) {
  const svg = document.getElementById('scatter');
  const W = 760, H = 420, M = { top: 16, right: 16, bottom: 40, left: 44 };
  const plotW = W - M.left - M.right;
  const plotH = H - M.top - M.bottom;

  const withCoords = stocks.filter(s =>
    typeof s.drawdown === 'number' && typeof s.conviction_score === 'number');
  if (!withCoords.length) {
    svg.innerHTML = '';
    return;
  }

  const xMax = Math.max(0.05, ...withCoords.map(s => s.drawdown));
  const xScale = v => M.left + (v / xMax) * plotW;
  const yScale = v => M.top + plotH - (v / 100) * plotH;

  let svgParts = [];

  // gridlines (recessive)
  for (let gy = 0; gy <= 100; gy += 25) {
    const y = yScale(gy);
    svgParts.push(`<line x1="${M.left}" y1="${y}" x2="${W - M.right}" y2="${y}" stroke="var(--gridline)" stroke-width="1"/>`);
    svgParts.push(`<text x="${M.left - 8}" y="${y + 4}" text-anchor="end" font-size="11" fill="var(--text-muted)">${gy}</text>`);
  }
  const xTickStep = xMax > 0.5 ? 0.2 : 0.1;
  for (let gx = 0; gx <= xMax + 0.001; gx += xTickStep) {
    const x = xScale(gx);
    svgParts.push(`<line x1="${x}" y1="${M.top}" x2="${x}" y2="${H - M.bottom}" stroke="var(--gridline)" stroke-width="1"/>`);
    svgParts.push(`<text x="${x}" y="${H - M.bottom + 18}" text-anchor="middle" font-size="11" fill="var(--text-muted)">${Math.round(gx * 100)}%</text>`);
  }
  // axis labels
  svgParts.push(`<text x="${M.left + plotW / 2}" y="${H - 6}" text-anchor="middle" font-size="12" fill="var(--text-secondary)">Off 52-week high</text>`);
  svgParts.push(`<text x="14" y="${M.top + plotH / 2}" text-anchor="middle" font-size="12" fill="var(--text-secondary)" transform="rotate(-90 14 ${M.top + plotH / 2})">Conviction score</text>`);
  // baseline axes
  svgParts.push(`<line x1="${M.left}" y1="${H - M.bottom}" x2="${W - M.right}" y2="${H - M.bottom}" stroke="var(--baseline)" stroke-width="1.5"/>`);
  svgParts.push(`<line x1="${M.left}" y1="${M.top}" x2="${M.left}" y2="${H - M.bottom}" stroke="var(--baseline)" stroke-width="1.5"/>`);

  for (const s of withCoords) {
    const cx = xScale(s.drawdown);
    const cy = yScale(s.conviction_score);
    const color = pointColor(s);
    const ring = s.smart_money_aligned
      ? `stroke="${COLOR_SMART_RING}" stroke-width="2"` : `stroke="var(--surface-1)" stroke-width="1"`;
    svgParts.push(
      `<circle class="pt" data-ticker="${s.ticker}" cx="${cx}" cy="${cy}" r="6" fill="${color}" fill-opacity="0.85" ${ring} style="cursor:pointer"/>`
    );
  }

  svg.innerHTML = svgParts.join('');

  const tooltip = document.getElementById('tooltip');
  svg.querySelectorAll('.pt').forEach(circle => {
    const ticker = circle.getAttribute('data-ticker');
    const s = withCoords.find(x => x.ticker === ticker);
    circle.addEventListener('mouseenter', (e) => {
      tooltip.style.display = 'block';
      tooltip.innerHTML = `
        <strong>${s.ticker}</strong> — ${s.shortName || ''}<br>
        <span style="color:var(--text-secondary)">${s.sector || ''}</span><br>
        Conviction: ${s.conviction_score}/100 &nbsp; Price: $${(s.price ?? 0).toFixed(2)}<br>
        Off high: ${(s.drawdown * 100).toFixed(1)}% &nbsp; Analyst upside: ${((s.analyst_upside ?? 0) * 100).toFixed(1)}%
        ${s.smart_money_aligned ? '<br><span style="color:var(--status-good-text)">🔥 smart money aligned</span>' : ''}
      `;
    });
    circle.addEventListener('mousemove', (e) => {
      tooltip.style.left = (e.clientX + 14) + 'px';
      tooltip.style.top = (e.clientY + 14) + 'px';
    });
    circle.addEventListener('mouseleave', () => { tooltip.style.display = 'none'; });
  });
}

const COLUMNS = [
  { key: 'ticker', label: 'Ticker' },
  { key: 'shortName', label: 'Name' },
  { key: 'sector', label: 'Sector' },
  { key: 'price', label: 'Price', num: true, fmt: v => `$${v?.toFixed(2) ?? '—'}` },
  { key: 'conviction_score', label: 'Conviction', num: true, fmt: v => v?.toFixed(1) ?? '—' },
  { key: 'valuation_discount', label: 'Val. discount', num: true, fmt: pctFmt },
  { key: 'analyst_upside', label: 'Analyst upside', num: true, fmt: pctFmt },
  { key: 'drawdown', label: 'Off high', num: true, fmt: pctFmt },
  { key: 'flags', label: 'Flags' },
];

function pctFmt(v) {
  return typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '—';
}

function getFiltered() {
  const q = document.getElementById('searchBox').value.trim().toLowerCase();
  const sector = document.getElementById('sectorFilter').value;
  const diamondOnly = document.getElementById('diamondOnly').checked;
  const smartOnly = document.getElementById('smartOnly').checked;

  return allStocks.filter(s => {
    if (q && !(`${s.ticker} ${s.shortName || ''}`.toLowerCase().includes(q))) return false;
    if (sector && s.sector !== sector) return false;
    if (diamondOnly && !s.diamond_in_rough) return false;
    if (smartOnly && !s.smart_money_aligned) return false;
    return true;
  });
}

function renderTable() {
  const rows = getFiltered();
  rows.sort((a, b) => {
    const av = a[sortState.col], bv = b[sortState.col];
    if (av == null) return 1;
    if (bv == null) return -1;
    const cmp = typeof av === 'number' ? av - bv : String(av).localeCompare(String(bv));
    return sortState.dir === 'asc' ? cmp : -cmp;
  });

  const wrap = document.getElementById('tableWrap');
  if (!rows.length) {
    wrap.innerHTML = '<div class="empty-state">No stocks match the current filters.</div>';
    return;
  }

  const thead = `<thead><tr>${COLUMNS.map(c => `
    <th class="${c.num ? 'num' : ''} ${sortState.col === c.key ? 'sorted' : ''}" data-key="${c.key}">${c.label}</th>
  `).join('')}</tr></thead>`;

  const tbody = `<tbody>${rows.map(s => `
    <tr>
      <td><strong>${s.ticker}</strong></td>
      <td>${s.shortName || ''}</td>
      <td>${s.sector || ''}</td>
      <td class="num">${COLUMNS.find(c => c.key === 'price').fmt(s.price)}</td>
      <td class="num">${COLUMNS.find(c => c.key === 'conviction_score').fmt(s.conviction_score)}</td>
      <td class="num">${pctFmt(s.valuation_discount)}</td>
      <td class="num">${pctFmt(s.analyst_upside)}</td>
      <td class="num">${pctFmt(s.drawdown)}</td>
      <td>
        ${s.diamond_in_rough ? '<span class="badge diamond">diamond</span>' : ''}
        ${s.smart_money_aligned ? '<span class="badge smart">smart money</span>' : ''}
      </td>
    </tr>
  `).join('')}</tbody>`;

  wrap.innerHTML = `<table>${thead}${tbody}</table>`;

  wrap.querySelectorAll('th').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.getAttribute('data-key');
      if (key === 'flags') return;
      if (sortState.col === key) {
        sortState.dir = sortState.dir === 'asc' ? 'desc' : 'asc';
      } else {
        sortState = { col: key, dir: 'desc' };
      }
      renderTable();
    });
  });
}

function wireControls() {
  ['searchBox', 'sectorFilter', 'diamondOnly', 'smartOnly'].forEach(id => {
    document.getElementById(id).addEventListener('input', renderTable);
  });
}

function renderFooter(data) {
  document.getElementById('footer').innerHTML = `
    Data: SEC EDGAR (insider trading, institutional 13F), Senate eFD (congressional trades, experimental),
    Yahoo Finance (price/fundamentals via yfinance). Generated ${formatTimestamp(data.generated_at)}.
    This page reads a static JSON file and has no backend — it only shows what the last automated run produced.
  `;
}

init();
