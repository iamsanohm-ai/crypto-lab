// คลังกลยุทธ์ — อ่าน library.json (Judge สร้างทุกคืน) แสดงเป็นตาราง/การ์ด กรอง ค้นหา เรียงลำดับ ดูรายละเอียด และลิงก์ไปโค้ด
(function () {
  const $ = (s) => document.querySelector(s);
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const NS = 'http://www.w3.org/2000/svg';
  const svgEl = (tag, attrs) => { const e = document.createElementNS(NS, tag); for (const k in attrs) e.setAttribute(k, attrs[k]); return e; };
  const pct = (v, d = 2) => v == null || isNaN(v) ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(d) + '%';
  const cls = (v) => v > 0 ? 'pos' : v < 0 ? 'neg' : 'flat';
  const KIND = {trend: 'Trend', reversion: 'Reversion', breakout: 'Breakout', other: 'อื่นๆ'};
  const STATUS = {champion: '👑 Champion', challenger_1: 'Challenger 1', challenger_2: 'Challenger 2', passed: 'ผ่านเกณฑ์', cut: 'ไม่ผ่าน'};
  let L = null;
  const st = {q: '', kind: 'all', only: 'all', sort: 'return_pct', view: 'table'};
  try { Object.assign(st, JSON.parse(localStorage.getItem('cl.lib.v1') || '{}')); } catch (e) { /* ignore */ }
  const save = () => { try { localStorage.setItem('cl.lib.v1', JSON.stringify({kind: st.kind, only: st.only, sort: st.sort, view: st.view})); } catch (e) { /* ignore */ } };

  function spark(values, w, h, area) {
    const s = svgEl('svg', {viewBox: `0 0 ${w} ${h}`, preserveAspectRatio: 'none', class: 'spark', role: 'img'});
    if (!values || values.length < 2) return s;
    const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
    const pts = values.map((v, i) => [(i / (values.length - 1)) * w, h - 3 - ((v - lo) / span) * (h - 6)]);
    const up = values[values.length - 1] >= values[0];
    const col = up ? 'var(--up)' : 'var(--down)';
    const d = pts.map((p, i) => (i ? 'L' : 'M') + p[0].toFixed(1) + ' ' + p[1].toFixed(1)).join(' ');
    if (area) {
      const gid = 'g' + Math.random().toString(36).slice(2, 8);
      const defs = svgEl('defs', {}), lg = svgEl('linearGradient', {id: gid, x1: 0, x2: 0, y1: 0, y2: 1});
      lg.append(svgEl('stop', {offset: '0%', 'stop-color': up ? '#22c983' : '#f0525b', 'stop-opacity': '.28'}), svgEl('stop', {offset: '100%', 'stop-color': up ? '#22c983' : '#f0525b', 'stop-opacity': '0'}));
      defs.append(lg); s.append(defs);
      s.append(svgEl('path', {d: d + ` L${w} ${h} L0 ${h} Z`, fill: `url(#${gid})`}));
      // starting-capital reference line
      const y0 = h - 3 - ((values[0] - lo) / span) * (h - 6);
      s.append(svgEl('line', {x1: 0, x2: w, y1: y0, y2: y0, stroke: 'var(--line)', 'stroke-dasharray': '3 3'}));
    }
    s.append(svgEl('path', {d, fill: 'none', stroke: col, 'stroke-width': area ? 1.8 : 1.5, 'vector-effect': 'non-scaling-stroke'}));
    const last = pts[pts.length - 1];
    if (area) s.append(svgEl('circle', {cx: last[0], cy: last[1], r: 3, fill: col}));
    return s;
  }

  function filtered() {
    const q = st.q.trim().toLowerCase();
    let b = L.bots.filter((x) => (st.kind === 'all' || x.kind === st.kind)
      && (st.only === 'all' || (st.only === 'passed' ? x.status !== 'cut' : x.classic))
      && (!q || (x.title + ' ' + x.name + ' ' + x.reason + ' ' + x.id).toLowerCase().includes(q)));
    const k = st.sort, desc = k !== 'max_dd_pct_abs';
    b = b.slice().sort((a, c) => k === 'max_dd_pct_abs' ? Math.abs(a.max_dd_pct) - Math.abs(c.max_dd_pct) : (c[k] ?? -1e9) - (a[k] ?? -1e9));
    return b;
  }

  function render() {
    if (!L) return;
    const counts = {all: L.bots.length}; L.bots.forEach((b) => { counts[b.kind] = (counts[b.kind] || 0) + 1; });
    const chips = $('#lib-kinds'); chips.replaceChildren();
    for (const k of ['all', 'trend', 'reversion', 'breakout', 'other']) {
      if (k !== 'all' && !counts[k]) continue;
      const b = mk('button', 'ftab', `${k === 'all' ? 'ทั้งหมด' : KIND[k]} ${counts[k]}`); b.type = 'button'; b.setAttribute('aria-pressed', String(st.kind === k));
      b.onclick = () => { st.kind = k; save(); render(); }; chips.append(b);
    }
    document.querySelectorAll('#lib-only button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.only === st.only)));
    document.querySelectorAll('#lib-view button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.mode === st.view)));
    $('#lib-sort').value = st.sort;
    const list = filtered();
    $('#lib-count').textContent = `แสดง ${list.length} จาก ${L.bots.length} บอท · ${L.data} · ${L.period[0]} → ${L.period[1]} (${L.years} ปี) · ${L.costs}`;
    $('#lib-table-wrap').hidden = st.view !== 'table';
    $('#lib-cards').hidden = st.view !== 'cards';
    const top = L.bots.reduce((a, b) => (b.return_pct > a.return_pct ? b : a), L.bots[0]);

    // table
    const tb = $('#lib-rows'); tb.replaceChildren();
    for (const x of list) {
      const tr = tb.insertRow(); if (x.status !== 'cut') tr.className = 'hl';
      const n = tr.insertCell(); n.className = 'libname';
      const nt = mk('div', 't'); nt.append(mk('span', 'bid', x.id), x.title); n.append(nt, mk('div', 'd', x.reason));
      tr.insertCell().append(mk('span', 'pill kind-' + x.kind, KIND[x.kind]));
      const sc = tr.insertCell(); sc.className = 'sparkcell'; sc.append(spark(x.spark, 110, 30, false));
      const num = (v, f, c) => { const td = tr.insertCell(); td.className = 'num ' + (c ? cls(v) : ''); td.textContent = f(v); };
      num(x.return_pct, (v) => pct(v), true); num(x.annual_pct, (v) => pct(v), true); num(x.sharpe, (v) => v.toFixed(2));
      num(x.max_dd_pct, (v) => v.toFixed(1) + '%'); num(x.win_rate_pct, (v) => v.toFixed(0) + '%'); num(x.pl_ratio, (v) => v == null ? '–' : v.toFixed(2));
      const s = tr.insertCell(); s.append(mk('span', 'pill st-' + (x.status.startsWith('challenger') ? 'chal' : x.status), STATUS[x.status] || x.status));
      const a = mk('div', 'acts'); tr.insertCell().append(a);
      const d = mk('button', 'btn sm', 'รายละเอียด'); d.type = 'button'; d.onclick = () => detail(x);
      const c = mk('a', 'btn sm ghost', 'โค้ด ↗'); c.href = x.code_url; c.target = '_blank'; c.rel = 'noopener';
      a.append(d, c);
    }
    if (!list.length) { const tr = tb.insertRow(); const td = tr.insertCell(); td.colSpan = 11; td.className = 'emptycell'; td.textContent = 'ไม่พบบอทที่ตรงกับตัวกรอง'; }

    // cards
    const cg = $('#lib-cards'); cg.replaceChildren();
    for (const x of list) {
      const card = mk('article', 'libcard' + (x.status !== 'cut' ? ' good' : '') + (x === top ? ' top' : ''));
      const head = mk('div', 'lc-head'); head.append(mk('span', 'bid', x.id), mk('span', 'pill kind-' + x.kind, KIND[x.kind]));
      if (x === top) head.append(mk('span', 'pill topbadge', '★ ผลตอบแทนสูงสุด'));
      head.append(mk('span', 'lc-ret ' + cls(x.return_pct), pct(x.return_pct, 1)));
      const ch = mk('div', 'lc-chart'); ch.append(spark(x.curve, 300, 96, true));
      const h = mk('h3', null, x.title);
      const tags = mk('div', 'lc-tags'); tags.append(mk('span', null, STATUS[x.status] || x.status), mk('span', null, `${x.trades} เทรด`));
      const g = mk('div', 'lc-stats');
      const add = (k, v, c) => { const d = mk('div'); d.append(mk('span', null, k), mk('b', c || '', v)); g.append(d); };
      add('ผลตอบแทน', pct(x.return_pct, 1), cls(x.return_pct)); add('ต่อปี', pct(x.annual_pct), cls(x.annual_pct)); add('Sharpe', x.sharpe.toFixed(2));
      add('Max DD', x.max_dd_pct.toFixed(1) + '%'); add('อัตราชนะ', x.win_rate_pct.toFixed(0) + '%'); add('P/L', x.pl_ratio == null ? '–' : x.pl_ratio.toFixed(2));
      const act = mk('div', 'lc-act');
      const d = mk('button', 'btn sm', 'รายละเอียด'); d.type = 'button'; d.onclick = () => detail(x);
      const c = mk('a', 'btn sm ghost', 'โค้ด ↗'); c.href = x.code_url; c.target = '_blank'; c.rel = 'noopener';
      act.append(d, c);
      card.append(head, ch, h, tags, g, act); cg.append(card);
    }
  }

  function bigChart(x) {
    const w = 640, h = 220, pad = 6, a = x.curve, b = L.benchmark.curve;
    const all = a.concat(b), lo = Math.min(...all), hi = Math.max(...all), span = hi - lo || 1;
    const s = svgEl('svg', {viewBox: `0 0 ${w} ${h}`, class: 'bigspark', role: 'img', 'aria-label': `equity ของ ${x.title} เทียบ BTC ถือยาว`});
    const path = (vals, col, dash) => { const d = vals.map((v, i) => (i ? 'L' : 'M') + ((i / (vals.length - 1)) * w).toFixed(1) + ' ' + (h - pad - ((v - lo) / span) * (h - 2 * pad)).toFixed(1)).join(' ');
      s.append(svgEl('path', Object.assign({d, fill: 'none', stroke: col, 'stroke-width': 2, 'vector-effect': 'non-scaling-stroke'}, dash ? {'stroke-dasharray': '4 4'} : {}))); };
    [lo, (lo + hi) / 2, hi].forEach((v) => { const y = h - pad - ((v - lo) / span) * (h - 2 * pad); s.append(svgEl('line', {x1: 0, x2: w, y1: y, y2: y, stroke: '#151e27'}));
      const t = svgEl('text', {x: 4, y: y - 3, fill: 'var(--muted)', 'font-size': 10, 'font-family': 'var(--mono)'}); t.textContent = Math.round(v).toLocaleString('en-US'); s.append(t); });
    path(b, '#6b7a8a', true); path(a, a[a.length - 1] >= a[0] ? '#22c983' : '#f0525b', false);
    return s;
  }

  function detail(x) {
    const box = $('#lib-detail'); box.replaceChildren();
    const h = mk('h3'); h.append(mk('span', 'bid', x.id), ' ' + x.title); box.append(h);
    box.append(mk('p', 'help', x.reason));
    const legend = mk('div', 'legend'); legend.innerHTML = '';
    const l1 = mk('span'); const i1 = mk('i'); i1.style.background = x.return_pct >= 0 ? 'var(--up)' : 'var(--down)'; l1.append(i1, `${x.title} ${pct(x.return_pct, 1)}`);
    const l2 = mk('span'); const i2 = mk('i'); i2.style.background = '#6b7a8a'; l2.append(i2, `BTC ถือยาว ${pct(L.benchmark.return_pct, 1)} (ร่วงสูงสุด ${L.benchmark.max_dd_pct.toFixed(0)}%)`);
    legend.append(l1, l2); box.append(legend, bigChart(x));
    const kv = mk('div', 'kvs');
    const add = (k, v) => kv.append(mk('span', null, k), mk('span', null, v));
    add('ประเภท', KIND[x.kind]); add('สถานะ', STATUS[x.status] || x.status);
    add('ผลตอบแทน / ต่อปี', `${pct(x.return_pct)} / ${pct(x.annual_pct)}`); add('Sharpe', x.sharpe.toFixed(2));
    add('ร่วงสูงสุด (Max DD)', x.max_dd_pct.toFixed(1) + '%'); add('เดือนที่แย่ที่สุด', pct(x.worst_month_pct, 1));
    add('อัตราชนะ / P/L', `${x.win_rate_pct.toFixed(0)}% / ${x.pl_ratio == null ? '–' : x.pl_ratio.toFixed(2)}`);
    add('จำนวนเทรด / แพ้ติดกันนานสุด', `${x.trades} / ${x.losing_streak}`);
    add('พารามิเตอร์ (ช่วงล่าสุด)', JSON.stringify(x.params));
    add('ตลาดที่ทำให้แพ้', x.kills);
    box.append(kv);
    const note = mk('p', 'help', x.status === 'cut'
      ? 'ไม่ผ่านเกณฑ์ (ต้องกำไรหลังต้นทุน และ Sharpe สูงกว่า BTC ถือยาว) — บอทจะไม่ใช้กลยุทธ์นี้'
      : 'ผ่านเกณฑ์ — ใช้อยู่ในบอทเทรดจำลอง ถ้าอยากเปลี่ยน champion บอก Claude ให้แก้ config/strategy.yaml');
    box.append(note);
    const act = mk('div', 'dlgbtns');
    const c = mk('a', 'btn ghost', 'ดูโค้ด Python ↗'); c.href = x.code_url; c.target = '_blank'; c.rel = 'noopener';
    const close = mk('button', 'btn primary', 'ปิด'); close.type = 'button'; close.onclick = () => $('#dlg-lib').close();
    act.append(c, close); box.append(act);
    $('#dlg-lib').showModal();
  }

  async function load() {
    try { const r = await fetch('library.json?t=' + Date.now(), {cache: 'no-store'}); L = await r.json(); render(); }
    catch (e) { const t = $('#lib-count'); if (t) t.textContent = 'โหลดคลังกลยุทธ์ไม่สำเร็จ: ' + e.message; }
  }
  function init() {
    $('#lib-search').addEventListener('input', (e) => { st.q = e.target.value; render(); });
    $('#lib-sort').addEventListener('change', (e) => { st.sort = e.target.value; save(); render(); });
    document.querySelectorAll('#lib-only button').forEach((b) => b.addEventListener('click', () => { st.only = b.dataset.only; save(); render(); }));
    document.querySelectorAll('#lib-view button').forEach((b) => b.addEventListener('click', () => { st.view = b.dataset.mode; save(); render(); }));
    load();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
