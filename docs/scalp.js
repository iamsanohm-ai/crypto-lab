// เทรดเร็ว (paper): เงินจำลองจากราคาจริง — ผลจากบอทบนเซิร์ฟเวอร์ (sync ทุก 5 นาที) + ตีราคาสดทุกวินาทีในเบราว์เซอร์
(function () {
  const $ = (s) => document.querySelector(s);
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const COINS = ['BTC', 'ETH', 'SOL', 'BNB', 'XRP', 'DOGE', 'ADA', 'LINK', 'AVAX', 'SUI', 'LTC', 'TRX'];
  const FEE = 0.001, SLIP = 0.0005;
  let S = null, R = null, sAt = 0, liveAt = 0, mode = 'off';
  const PX = {}, PREV = {}, FL = {}, SPARK = {};
  const usd = (v, sign) => (v == null || isNaN(v)) ? '—' : (sign && v > 0 ? '+' : '') + v.toFixed(2) + ' USDT';
  const pct = (v, d = 2) => (v == null || isNaN(v)) ? '—' : (v > 0 ? '+' : '') + v.toFixed(d) + '%';
  const pf = (p) => p == null ? '—' : p >= 100 ? p.toFixed(2) : p >= 1 ? p.toFixed(4) : p.toPrecision(4);
  const cls = (v) => v > 0 ? 'pos' : v < 0 ? 'neg' : 'flat';
  const ago = (iso) => { if (!iso) return '—'; const s = Math.max(0, Math.round((Date.now() - new Date(iso)) / 1000));
    return s < 60 ? s + ' วิที่แล้ว' : s < 3600 ? Math.floor(s / 60) + ' นาทีที่แล้ว' : Math.floor(s / 3600) + ' ชม.ที่แล้ว'; };
  const hhmm = (iso) => new Date(iso).toLocaleTimeString('th-TH', {hour: '2-digit', minute: '2-digit', second: '2-digit'});

  async function load() {
    try { const r = await fetch('scalper.json?t=' + Date.now(), {cache: 'no-store'}); if (r.ok) { S = await r.json(); sAt = Date.now(); } } catch (e) { /* keep */ }
    if (!R) try { const r = await fetch('scalp_research.json?t=' + Date.now(), {cache: 'no-store'}); if (r.ok) R = await r.json(); } catch (e) { /* none */ }
    if (S && S.prices) for (const [k, v] of Object.entries(S.prices)) if (PX[k] == null) PX[k] = v;
  }
  function onTick(sym, p) {
    if (PX[sym] != null && p !== PX[sym]) { PREV[sym] = PX[sym]; FL[sym] = Date.now(); }
    PX[sym] = p; liveAt = Date.now();
    const a = SPARK[sym] || (SPARK[sym] = []); a.push(p); if (a.length > 120) a.shift();
  }
  function connect() {
    const url = 'wss://data-stream.binance.vision/stream?streams=' + COINS.map((c) => c.toLowerCase() + 'usdt@miniTicker').join('/');
    let tries = 0;
    const open = () => { let ws; try { ws = new WebSocket(url); } catch (e) { tries++; setTimeout(open, 4000); return; }
      ws.onmessage = (ev) => { const d = JSON.parse(ev.data).data; if (d && d.s) { mode = 'ws'; onTick(d.s.replace('USDT', ''), +d.c); } };
      ws.onclose = () => { tries++; setTimeout(open, Math.min(20000, 2000 * tries)); }; ws.onerror = () => ws.close(); };
    open();
    setInterval(async () => {
      if (document.hidden || (mode === 'ws' && Date.now() - liveAt < 5000)) return;
      try { const q = encodeURIComponent(JSON.stringify(COINS.map((c) => c + 'USDT')));
        const r = await fetch('https://data-api.binance.vision/api/v3/ticker/price?symbols=' + q, {cache: 'no-store'});
        if (r.ok) { (await r.json()).forEach((x) => onTick(x.symbol.replace('USDT', ''), +x.price)); mode = 'poll'; } } catch (e) { /* retry */ }
    }, 3000);
  }

  // ตีราคาสถานะด้วยราคาสด (ประมาณการ: ถ้าขายตอนนี้ หลังค่าธรรมเนียม + slippage)
  const mtm = (p) => { const px = PX[p.sym] ?? p.entry, exit = px * (1 - SLIP);
    const net = (exit * (1 - FEE)) / (p.entry * (1 + FEE)) - 1; return {px, net, usd: p.qty ? p.qty * exit * (1 - FEE) - p.cost : null}; };
  const equityLive = () => !S ? null : S.cash + S.positions.reduce((a, p) => a + p.qty * (PX[p.sym] ?? p.entry), 0);

  function hero() {
    const el = $('#sc-hero'); if (!el || !S) return; el.replaceChildren();
    const eq = equityLive(), tot = eq - S.capital, day0 = S.sentinel && S.sentinel.day_start_equity, g = S.gate || {}, sen = S.sentinel || {};
    const a = mk('div', 'sc-big'); a.append(mk('div', 'k', 'เงินในบัญชีเทรดเร็ว (จำลอง · ตีราคาสดทุกวินาที)'), mk('div', 'v', eq.toFixed(2) + ' USDT'),
      mk('div', 's ' + cls(tot), `${usd(tot, true)} (${pct(tot / S.capital * 100)}) ตั้งแต่เริ่ม · วันนี้ ${day0 ? usd(eq - day0, true) : '—'}`));
    const tiles = mk('div', 'sc-tiles'), st = S.stats || {};
    const t = (k, v, s, c) => { const d = mk('div', 'sc-t'); d.append(mk('span', null, k), mk('b', c || '', v), mk('small', null, s)); tiles.append(d); };
    t('ใช้เงินจริงในบัญชีจำลอง?', g.open ? 'ใช้เงิน' : 'เทรดเงา', g.open ? 'ผลเงาล่าสุดเป็นบวก' : `รอผลเงาเป็นบวก (${g.n || 0}/${g.need || 30})`, g.open ? 'pos' : 'amber');
    t('ผลเฉลี่ยเงา 30 ครั้งล่าสุด', g.avg_pct == null ? '—' : pct(g.avg_pct, 3), g.win_pct == null ? 'ยังไม่มีข้อมูล' : `ชนะ ${g.win_pct}% · หลังค่าธรรมเนียม`, cls(g.avg_pct));
    t('เทรดที่ใช้เงิน', String(st.trades || 0), `ชนะ ${st.wins || 0} · รวม ${usd(st.pnl_usdt || 0, true)}`, cls(st.pnl_usdt));
    t('Sentinel', sen.halted ? 'หยุดพัก' : 'ปกติ', sen.halted ? sen.halted.reason : `แพ้ติดกัน ${sen.loss_streak || 0}/3`, sen.halted ? 'neg' : 'pos');
    t('ราคาสด', Date.now() - liveAt < 5000 ? 'สด' : 'กำลังเชื่อม', mode === 'ws' ? 'WebSocket ทุกวินาที' : 'สำรอง ทุก 3 วิ', Date.now() - liveAt < 5000 ? 'pos' : 'amber');
    t('บอทบนเซิร์ฟเวอร์', ago(S.updated_at), 'เช็คราคาทุก 15 วิ · ส่งขึ้นเว็บทุก 5 นาที', Date.now() - new Date(S.updated_at) < 20 * 60000 ? 'pos' : 'amber');
    const m = S.model || {}, ex = m.exit || {};
    const why = mk('p', 'sc-why');
    why.append(mk('b', null, 'กติกา: '), `${m.strategy === 'momo_burst' ? 'ซื้อเมื่อราคาทะลุจุดสูงสุด ' + (m.params || {}).n + ' แท่ง (5 นาที) พร้อม volume พุ่ง ' + (m.params || {}).k + ' เท่า ในขาขึ้น' : m.strategy}`
      + ` → ขายทันทีเมื่อกำไร +${(ex.tp * 100).toFixed(1)}% หรือขาดทุน -${(ex.sl * 100).toFixed(1)}% หรือถือครบ ${ex.hold * 5} นาที · เสี่ยงไม่เกิน 0.5% ต่อครั้ง · ไม่เกิน 125 USDT/ครั้ง · ถือพร้อมกันไม่เกิน 3`);
    el.append(a, tiles, why);
  }

  function tape() {
    const el = $('#sc-tape'); if (!el) return;
    if (el.children.length !== COINS.length) { el.replaceChildren(); COINS.forEach((c) => { const d = mk('div', 'sc-c'); d.dataset.s = c; d.append(mk('b'), mk('span', 'p'), mk('canvas'), mk('small')); el.append(d); }); }
    const W = (S && S.watch) || {}, now = Date.now();
    for (const d of el.children) {
      const s = d.dataset.s, w = W[s] || {}, p = PX[s], up = PREV[s] != null && p > PREV[s];
      d.className = 'sc-c' + (now - (FL[s] || 0) < 700 ? (up ? ' fu' : ' fd') : '') + (w.signal ? ' sig' : '');
      d.children[0].textContent = s; d.children[1].textContent = pf(p);
      d.children[3].textContent = w.trend_up == null ? 'รอข้อมูลบอท' : `${w.trend_up ? 'ขาขึ้น' : 'ขาลง'} ${pct(w.vs_ema200_pct, 1)}` + (w.to_break_pct != null ? ` · ห่างจุดทะลุ ${w.to_break_pct}% · vol ${w.vol_x}x` : '');
      const cv = d.children[2], a = SPARK[s] || [];
      const r = devicePixelRatio || 1, cw = cv.clientWidth || 100, ch = 22; if (cv.width !== cw * r) { cv.width = cw * r; cv.height = ch * r; }
      const c = cv.getContext('2d'); c.setTransform(r, 0, 0, r, 0, 0); c.clearRect(0, 0, cw, ch);
      if (a.length > 1) { const lo = Math.min(...a), hi = Math.max(...a), k = hi - lo || 1; c.beginPath();
        a.forEach((v, i) => { const x = i / (a.length - 1) * cw, y = ch - 2 - (v - lo) / k * (ch - 4); i ? c.lineTo(x, y) : c.moveTo(x, y); });
        c.strokeStyle = a[a.length - 1] >= a[0] ? '#22c983' : '#f0525b'; c.lineWidth = 1.2; c.stroke(); }
    }
  }

  function posList(sel, list, money) {
    const el = $(sel); if (!el) return; el.replaceChildren();
    if (!list.length) { el.append(mk('div', 'empty', money ? 'ยังไม่ถือเหรียญ — ' + (S.gate && S.gate.open ? 'รอสัญญาณ' : 'รอผลเงาเป็นบวกก่อนจึงจะใช้เงิน') : 'ไม่มีเทรดเงาที่เปิดอยู่ — รอสัญญาณจากแท่ง 5 นาทีถัดไป')); return; }
    for (const p of list) {
      const m = mtm(p), row = mk('div', 'sc-pos ' + cls(m.net));
      const lo = p.sl, hi = p.tp, f = Math.max(0, Math.min(1, (m.px - lo) / (hi - lo)));
      const bar = mk('div', 'sc-rng'); const dot = mk('i'); dot.style.left = (f * 100) + '%'; const en = mk('em'); en.style.left = ((p.entry - lo) / (hi - lo) * 100) + '%'; bar.append(en, dot);
      const left = Math.max(0, Math.round(p.deadline - Date.now() / 1000));
      row.append(mk('b', null, p.sym), mk('span', 'n', money ? usd(m.usd, true) : pct(m.net * 100)), mk('span', 'd', `เข้า ${pf(p.entry)} → ตอนนี้ ${pf(m.px)} (${pct(m.net * 100)})`), bar,
        mk('small', null, `stop ${pf(lo)} · เป้า ${pf(hi)} · เหลือเวลา ${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}${money ? ` · ${p.cost.toFixed(2)} USDT` : ''}`));
      el.append(row);
    }
  }

  function trades() {
    const el = $('#sc-trades'); if (!el || !S) return;
    const key = (S.trades[0] || {}).closed_at + '|' + (S.shadow_closed[0] || {}).closed_at; if (el.dataset.k === key) return; el.dataset.k = key; el.replaceChildren();
    const all = [...S.trades.map((t) => ({...t, money: true})), ...S.shadow_closed.slice(0, 40)].sort((a, b) => b.closed_at.localeCompare(a.closed_at)).slice(0, 40);
    if (!all.length) { el.append(mk('div', 'empty', 'ยังไม่มีเทรดที่ปิดแล้ว')); return; }
    const TH = {tp: 'ถึงเป้า', sl: 'โดน stop', time: 'ครบเวลา'};
    for (const t of all) { const r = mk('div', 'sc-tr ' + cls(t.net_pct));
      r.append(mk('span', 't', hhmm(t.closed_at)), mk('b', null, t.sym), mk('span', 'k', t.money ? 'เงิน' : 'เงา'), mk('span', null, TH[t.reason] || t.reason),
        mk('span', 'n', t.money ? usd(t.pnl_usdt, true) : pct(t.net_pct, 2))); el.append(r); }
  }

  function events() {
    const el = $('#sc-events'); if (!el || !S) return;
    const key = (S.events[0] || {}).t; if (el.dataset.k === key) return; el.dataset.k = key; el.replaceChildren();
    for (const e of S.events.slice(0, 30)) { const r = mk('div', 'ev ' + ({buy: 'buy', sell: 'sell', halt: 'warn', warn: 'warn'}[e.kind] || 'info'));
      const h = mk('div', 'h'); h.append(mk('span', null, e.text), mk('span', 't', hhmm(e.t))); r.append(h); el.append(r); }
  }

  function curve() {
    const cv = $('#sc-curve'); if (!cv || !S) return;
    const pts = S.curve.map(([t, v]) => [t * 1000, v]); const eq = equityLive(); if (eq != null) pts.push([Date.now(), eq]);
    const r = devicePixelRatio || 1, W = cv.clientWidth || 600, H = 160; if (cv.width !== W * r) { cv.width = W * r; cv.height = H * r; }
    const c = cv.getContext('2d'); c.setTransform(r, 0, 0, r, 0, 0); c.clearRect(0, 0, W, H);
    if (pts.length < 2) { c.fillStyle = '#5d6c7b'; c.font = '12px sans-serif'; c.fillText('กำลังเก็บข้อมูล equity ทุก 5 นาที…', 10, 20); return; }
    const vs = pts.map((p) => p[1]).concat([S.capital]), lo = Math.min(...vs), hi = Math.max(...vs), pad = Math.max(0.5, (hi - lo) * 0.15);
    const t0 = pts[0][0], t1 = pts[pts.length - 1][0], X = (t) => 44 + (t - t0) / (t1 - t0 || 1) * (W - 54), Y = (v) => 8 + (1 - (v - lo + pad) / (hi - lo + 2 * pad)) * (H - 26);
    c.strokeStyle = '#1b2530'; c.fillStyle = '#5d6c7b'; c.font = '10px ui-monospace,monospace'; c.lineWidth = 1;
    for (const v of [lo, S.capital, hi]) { c.beginPath(); c.moveTo(44, Y(v)); c.lineTo(W - 10, Y(v)); c.stroke(); c.fillText(v.toFixed(1), 2, Y(v) + 3); }
    c.beginPath(); pts.forEach(([t, v], i) => i ? c.lineTo(X(t), Y(v)) : c.moveTo(X(t), Y(v)));
    c.strokeStyle = pts[pts.length - 1][1] >= S.capital ? '#22c983' : '#f0525b'; c.lineWidth = 1.6; c.stroke();
    const [lx, ly] = [X(pts[pts.length - 1][0]), Y(pts[pts.length - 1][1])]; c.fillStyle = '#fff'; c.beginPath(); c.arc(lx, ly, 2.5 + (Date.now() % 1000) / 500, 0, 6.283); c.fill();
  }

  function learn() {
    const el = $('#sc-learn'); if (!el || !R || el.dataset.k === R.generated_at) return; el.dataset.k = R.generated_at; el.replaceChildren();
    const NAME = {momo_burst: 'ทะลุจุดสูง + volume พุ่ง', rsi2_dip: 'ซื้อตอนย่อแรง (RSI2)', ema_cross: 'EMA9 ตัด EMA21', bb_bounce: 'เด้งจากขอบล่าง Bollinger'};
    el.append(mk('p', 'sc-why', `ทดสอบบนแท่ง 5 นาทีจริงของ ${R.coins.length} เหรียญ ย้อนหลัง ${R.days} วัน · เลือกค่าจาก ${R.days - R.oos_days} วันแรก แล้ววัดผลจริงใน ${R.oos_days} วันล่าสุดที่ไม่เคยเห็น · ค่าธรรมเนียม+slippage ไปกลับ ${R.costs.round_trip_pct}% · ช่วงเดียวกัน BTC ถือเฉยๆ ${pct(R.btc_buy_hold_oos_pct)}`));
    const tb = mk('table'); const th = mk('tr'); ['กลยุทธ์', 'เทรด', 'ชนะ', 'เฉลี่ย/ครั้ง ก่อนค่าธรรมเนียม', 'เฉลี่ย/ครั้ง หลังค่าธรรมเนียม'].forEach((h, i) => th.append(mk('th', i ? 'num' : null, h)));
    const thead = mk('thead'); thead.append(th); const tbody = mk('tbody');
    for (const b of R.best_per_strategy) { const tr = mk('tr');
      tr.append(mk('td', null, NAME[b.strategy] || b.strategy), mk('td', 'num', String(b.oos.trades)), mk('td', 'num', b.oos.win_pct + '%'),
        mk('td', 'num ' + cls(b.oos_gross.avg_pct), pct(b.oos_gross.avg_pct, 3)), mk('td', 'num ' + cls(b.oos.avg_pct), pct(b.oos.avg_pct, 3))); tbody.append(tr); }
    tb.append(thead, tbody); const w = mk('div', 'tablewrap'); w.append(tb); el.append(w);
    el.append(mk('p', R.passed ? 'sc-ok' : 'sc-warn', R.passed ? 'มีกลยุทธ์ที่ผ่าน: เฉลี่ยเป็นบวกหลังค่าธรรมเนียมในช่วงที่ไม่เคยเห็น'
      : 'บทเรียน: ช่วงนี้ไม่มีกลยุทธ์เข้าเร็ว-ออกเร็วตัวไหนทำกำไรหลังค่าธรรมเนียม (ตลาดขาลง ซื้อแล้วโดน stop บ่อย) — ระบบจึง "เทรดเงา" ไปก่อน ไม่ใช้เงิน และจะเริ่มใช้เงินเองเมื่อผลเงาล่าสุดเป็นบวก'));
  }

  function tick() {
    if (document.hidden) return;
    const v = $('#view-scalp'); if (!v || v.hidden || !S) return;
    hero(); tape(); posList('#sc-pos', S.positions, true); posList('#sc-shadow', S.shadow, false); trades(); events(); curve(); learn();
  }
  function init() { load().then(tick); setInterval(load, 30000); setInterval(tick, 1000); setTimeout(connect, 800); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
