// ORB Scanner — terminal view ของผลสแกนทั้งกระดาน: กราฟวงกลม (ใกล้ศูนย์กลาง = คะแนนสูง, มุม = ความสัมพันธ์กับ BTC),
// ทะเบียนคะแนน, ผลตรวจแต่ละด้าน และรายละเอียดเหรียญที่เลือก — ข้อมูลจาก data.json (scanner) ไม่มีการทำนาย
(function () {
  const NS = 'http://www.w3.org/2000/svg';
  const $ = (s) => document.querySelector(s);
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const sv = (tag, a) => { const e = document.createElementNS(NS, tag); for (const k in a) e.setAttribute(k, a[k]); return e; };
  const COMP_TH = {trend: 'แนวโน้ม', momentum: 'Momentum', liquidity: 'สภาพคล่อง', volatility: 'ความผันผวน', entry: 'ใกล้จุดเข้า'};
  const STATUS_COL = {buy_signal: '#22c983', uptrend: '#33c3b4', downtrend: '#f0525b', illiquid: '#3a4654', new: '#f2a93b'};
  let sel = null, showIlliquid = false, lastKey = '';
  const scoreCls = (v) => v >= 70 ? 'sc-hi' : v >= 50 ? 'sc-mid' : 'sc-lo';
  const fmtPct = (v, d = 1) => v == null ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(d) + '%';
  const px = (v) => (window.CL ? window.CL.fmt.px(v) : String(v));

  function rowsOf(S) { return S.rows.filter((r) => r.score != null); }
  function ranked(S) { return rowsOf(S).slice().sort((a, b) => b.score - a.score || b.raw_score - a.raw_score); }

  function header(S, rows) {
    const el = $('#orb-head'); el.replaceChildren();
    const liquid = rows.filter((r) => r.status !== 'illiquid');
    const hi = rows.filter((r) => r.score >= 70).length, capped = rows.filter((r) => r.caps.length).length;
    const A = S.analysis || {};
    const items = [['สแกน', rows.length], ['มีสภาพคล่อง', liquid.length], ['คะแนน ≥ 70', hi], ['ถูก cap', capped],
      ['ตลาด', A.regime_th || '—'], ['แท่ง', window.CL ? window.CL.fmt.time(S.bar) : S.bar]];
    for (const [k, v] of items) { const d = mk('div', 'oh-i'); d.append(mk('span', null, k), mk('b', null, String(v))); el.append(d); }
  }

  function checks(S, rows) {
    const el = $('#orb-checks'); el.replaceChildren();
    const liquid = rows.filter((r) => r.status !== 'illiquid');
    for (const [k, c] of Object.entries(S.orb.components)) {
      const vals = liquid.map((r) => r.components[k] / c.weight);
      const pass = vals.length ? vals.filter((v) => v >= 0.7).length / vals.length * 100 : 0;
      const box = mk('div', 'oc');
      const top = mk('div', 'oc-top'); top.append(mk('span', null, COMP_TH[k] + ` · w${c.weight}`), mk('b', pass >= 50 ? 'pos' : pass >= 25 ? '' : 'neg', pass.toFixed(0) + '%'));
      const svg = sv('svg', {viewBox: '0 0 100 26', preserveAspectRatio: 'none', class: 'oc-hist'});
      const bins = new Array(10).fill(0); vals.forEach((v) => { bins[Math.min(9, Math.floor(v * 10))]++; });
      const mx = Math.max(1, ...bins);
      bins.forEach((n, i) => svg.append(sv('rect', {x: i * 10 + 1, width: 8, y: 26 - (n / mx) * 24, height: (n / mx) * 24, fill: i >= 7 ? '#22c983' : i >= 4 ? '#33c3b4' : '#3a4654'})));
      if (sel) { const v = sel.components[k] / c.weight; svg.append(sv('line', {x1: v * 100, x2: v * 100, y1: 0, y2: 26, stroke: '#f2a93b', 'stroke-width': 1.5})); }
      box.append(top, svg, mk('div', 'oc-lbl', c.label));
      el.append(box);
    }
    const f = mk('div', 'oc-formula');
    f.append(mk('div', null, 'sₖ = round(10·wₖ·clamp((bₖ−xₖ)/(bₖ−gₖ),0,1))/10'), mk('div', null, 'Raw = round(Σ sₖ)'), mk('div', null, 'Final = min(Raw, 100 − 41·Cap)'));
    el.append(f);
  }

  function graph(S, rows) {
    const el = $('#orb-graph'); el.replaceChildren();
    const W = 600, C = 300;
    const svg = sv('svg', {viewBox: `0 0 ${W} ${W}`, class: 'orb-svg', role: 'img', 'aria-label': 'กราฟวงกลม: ใกล้ศูนย์กลาง = คะแนนสูง, มุม = ความสัมพันธ์กับ BTC'});
    [80, 160, 240].forEach((r) => svg.append(sv('circle', {cx: C, cy: C, r, fill: 'none', stroke: '#16202a', 'stroke-dasharray': '2 4'})));
    const pts = rows.slice().sort((a, b) => (b.corr_btc ?? -1) - (a.corr_btc ?? -1));
    const n = pts.length || 1;
    const rays = sv('g', {}), nodes = sv('g', {});
    pts.forEach((r, i) => {
      const ang = (i / n) * Math.PI * 2 - Math.PI / 2;
      const rad = 46 + (1 - Math.min(100, r.raw_score) / 100) * 230;
      const x = C + Math.cos(ang) * rad, y = C + Math.sin(ang) * rad;
      const hiCorr = (r.corr_btc ?? 0) >= 0.5, isSel = sel && sel.symbol === r.symbol;
      rays.append(sv('line', {x1: C, y1: C, x2: x, y2: y, stroke: isSel ? '#f2a93b' : hiCorr ? '#d9b84a' : '#c9d3dd', 'stroke-opacity': isSel ? 1 : r.status === 'illiquid' ? 0.06 : 0.22, 'stroke-width': isSel ? 2 : 0.7}));
      const liq = Math.max(6, Math.log10(Math.max(1, r.quote_volume_24h)));
      const dot = sv('circle', {cx: x, cy: y, r: Math.max(1.6, (liq - 5.5) * 1.6), fill: STATUS_COL[r.status] || '#888', 'fill-opacity': r.status === 'illiquid' ? 0.5 : 0.95, class: 'orb-dot', tabindex: 0});
      if (isSel) dot.setAttribute('stroke', '#fff'), dot.setAttribute('stroke-width', 2);
      const t = sv('title', {}); t.textContent = `${r.symbol} · คะแนน ${r.score} (raw ${r.raw_score}) · corr BTC ${r.corr_btc ?? '—'}`; dot.append(t);
      dot.addEventListener('click', () => select(r));
      dot.addEventListener('keydown', (e) => { if (e.key === 'Enter') select(r); });
      nodes.append(dot);
    });
    svg.append(rays, nodes);
    svg.append(sv('circle', {cx: C, cy: C, r: 22, fill: '#0b1016', stroke: '#f2a93b', 'stroke-width': 1.5}));
    const tt = sv('text', {x: C, y: C + 4, 'text-anchor': 'middle', fill: '#f2a93b', 'font-size': 12, 'font-family': 'var(--mono)', 'font-weight': 700}); tt.textContent = 'BTC'; svg.append(tt);
    const lg = sv('text', {x: 8, y: W - 10, fill: '#5d6c7b', 'font-size': 11, 'font-family': 'var(--mono)'}); lg.textContent = 'ใกล้ศูนย์กลาง = คะแนนสูง · เส้นทอง = วิ่งตาม BTC มาก'; svg.append(lg);
    el.append(svg);
  }

  function registry(S, rows) {
    const el = $('#orb-reg'); el.replaceChildren();
    const r0 = sel || rows[0];
    if (r0) {
      const card = mk('div', 'or-card ' + scoreCls(r0.score));
      const top = mk('div', 'or-top'); top.append(mk('b', null, r0.symbol), mk('span', 'or-score', String(r0.score)));
      const bar = mk('div', 'or-bar'); const fill = mk('i'); fill.style.width = r0.score + '%'; bar.append(fill);
      card.append(top, bar);
      if (r0.caps.length) card.append(mk('div', 'or-cap', `CAP ≤59 · raw ${r0.raw_score}`));
      el.append(card);
    }
    const list = mk('div', 'or-list');
    rows.filter((r) => showIlliquid || r.status !== 'illiquid').slice(0, 60).forEach((r) => {
      const it = mk('button', 'or-row' + (sel && sel.symbol === r.symbol ? ' on' : '')); it.type = 'button';
      const b = mk('span', 'or-mini'); const f = mk('i', scoreCls(r.score)); f.style.width = r.score + '%'; b.append(f);
      it.append(mk('span', 'or-sym', r.symbol), b, mk('span', 'or-n ' + scoreCls(r.score), String(r.score)));
      it.onclick = () => select(r); list.append(it);
    });
    el.append(list);
  }

  function detail(S) {
    const el = $('#orb-detail'); el.replaceChildren();
    const r = sel; if (!r) { el.append(mk('div', 'empty', 'แตะจุดบนกราฟหรือชื่อในรายการเพื่อดูรายละเอียด')); return; }
    const left = mk('div', 'od-col');
    left.append(mk('div', 'od-h', `${r.symbol}/USDT · คะแนน ${r.score}${r.caps.length ? ` (raw ${r.raw_score}, ถูก cap)` : ''}`));
    for (const [k, c] of Object.entries(S.orb.components)) {
      const v = r.components[k], row = mk('div', 'od-comp');
      const bar = mk('div', 'or-bar'); const f = mk('i'); f.style.width = (v / c.weight * 100) + '%'; bar.append(f);
      row.append(mk('span', null, COMP_TH[k]), bar, mk('b', null, `${v}/${c.weight}`)); left.append(row);
    }
    if (r.caps.length) { const cap = mk('div', 'od-caps'); cap.append(mk('b', null, 'เหตุผลที่ถูก cap ไม่เกิน 59:')); r.caps.forEach((c) => cap.append(mk('div', null, '• ' + (S.orb.cap_reasons[c] || c)))); left.append(cap); }
    const mid = mk('div', 'od-col');
    mid.append(mk('div', 'od-h', '10 วันล่าสุด (แท่ง 4h)'));
    if (r.spark && r.spark.length > 1) {
      const v = r.spark, lo = Math.min(...v), hi = Math.max(...v), sp = hi - lo || 1, w = 300, h = 90;
      const svg = sv('svg', {viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: 'none', class: 'od-spark'});
      const d = v.map((p, i) => (i ? 'L' : 'M') + (i / (v.length - 1) * w).toFixed(1) + ' ' + (h - 4 - (p - lo) / sp * (h - 8)).toFixed(1)).join(' ');
      const col = v[v.length - 1] >= v[0] ? '#22c983' : '#f0525b';
      svg.append(sv('path', {d: d + ` L${w} ${h} L0 ${h} Z`, fill: col, 'fill-opacity': 0.12}), sv('path', {d, fill: 'none', stroke: col, 'stroke-width': 1.8, 'vector-effect': 'non-scaling-stroke'}));
      mid.append(svg);
    } else mid.append(mk('div', 'empty', 'ไม่มีกราฟ (สภาพคล่องต่ำ)'));
    const right = mk('div', 'od-col');
    const kv = mk('div', 'kvs');
    const add = (k, v) => kv.append(mk('span', null, k), mk('span', null, v));
    add('ราคา', px(r.price)); add('24 ชม.', fmtPct(r.change_24h_pct, 2)); add('เทียบ EMA200', fmtPct(r.vs_ema200_pct));
    add('30 วัน', fmtPct(r.mom_30d_pct)); add('ATR 4h', r.atr_pct == null ? '—' : r.atr_pct.toFixed(2) + '%');
    add('ห่างจุดเข้า', r.entry_dist_pct == null ? '—' : (r.entry_dist_pct <= 0 ? 'ทะลุแล้ว' : '+' + r.entry_dist_pct.toFixed(1) + '%'));
    add('Corr กับ BTC', r.corr_btc == null ? '—' : r.corr_btc.toFixed(2)); add('Volume 24 ชม.', window.CL ? window.CL.fmt.big(r.quote_volume_24h) : r.quote_volume_24h);
    right.append(kv);
    const plan = ((S.plans) || []).find((p) => p.symbol === r.symbol);
    if (plan) { const b = mk('button', 'btn sm', 'เตรียมออเดอร์ตามแผน →'); b.type = 'button'; b.onclick = () => document.dispatchEvent(new CustomEvent('cl:plan', {detail: plan})); right.append(b); }
    el.append(left, mid, right);
  }

  function select(r) { sel = r; draw(true); }
  function draw(force) {
    const D = window.CL && window.CL.data(); const S = D && D.scanner;
    const root = $('#orb'); if (!root) return;
    if (!S || !S.orb) { root.hidden = true; return; }
    root.hidden = false;
    const key = S.generated_at + '|' + (sel && sel.symbol) + '|' + showIlliquid;
    if (!force && key === lastKey) return; lastKey = key;
    const rows = ranked(S);
    if (sel) sel = rows.find((r) => r.symbol === sel.symbol) || null;
    if (!sel) sel = rows.find((r) => r.status !== 'illiquid') || rows[0];
    header(S, rows); checks(S, rows); graph(S, rows); registry(S, rows); detail(S);
  }
  document.addEventListener('change', (e) => { if (e.target && e.target.id === 'orb-illiquid') { showIlliquid = e.target.checked; draw(true); } });
  window.CLOrb = {render: () => draw(false)};
  setInterval(() => draw(false), 3000);
})();
