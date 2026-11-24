// Crypto Lab Terminal — GitHub Pages. Reads ./data.json (written hourly by GitHub Actions) + live prices via Binance WebSocket.
(function () {
  const fmt = {
    usd: (v, d) => v == null || isNaN(v) ? '—' : Number(v).toLocaleString('en-US', {minimumFractionDigits: d ?? 2, maximumFractionDigits: d ?? 2}),
    px: (v) => { if (v == null || isNaN(v)) return '—'; const a = Math.abs(v); if (a >= 1000) return fmt.usd(v, 2); if (a >= 1) return fmt.usd(v, 4); if (a === 0) return '0';
      const d = Math.max(4, -Math.floor(Math.log10(a)) + 3); return Number(v).toFixed(d); },
    pct: (v, d = 2) => v == null || isNaN(v) ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(d) + '%',
    big: (v) => v == null ? '—' : d3.format('.3~s')(v).replace('G', 'B'),
    time: (s) => { if (!s) return '—'; const d = new Date(s); return isNaN(d) ? s : d.toLocaleString('th-TH', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}); },
  };
  const cls = (v) => v > 0 ? 'pos' : v < 0 ? 'neg' : 'flat';
  const SERIES = {keltner_trend: '#33c3b4', golden_cross_50_200: '#8f7cf2', breakout_funding_filter: '#f2a93b', 'BTC buy & hold': '#6b7a8a'};
  const ROLE = {champion: 'Champion', challenger_1: 'Challenger 1', challenger_2: 'Challenger 2'};
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const DRAWERS = {};
  const draw = (name, fn) => { DRAWERS[name] = fn; document.querySelectorAll(`[data-draw="${name}"]`).forEach((el) => {
    if (el.closest('[hidden]')) return;   // hidden tabs are drawn when opened (charts need a real width)
    try { fn(el); } catch (e) { el.textContent = 'แสดงผลไม่ได้'; console.error(name, e); } }); };
  const redraw = (name) => { if (DRAWERS[name]) draw(name, DRAWERS[name]); };
  let D = null;
  const chart = {sym: 'BTC', tf: '4h', rows: null, ws: null, live: false, loading: false};
  const TF_LABEL = {'1m': '1 นาที', '5m': '5 นาที', '15m': '15 นาที', '1h': '1 ชั่วโมง', '4h': '4 ชั่วโมง'};
  const isDefault = () => chart.sym === 'BTC' && chart.tf === '4h';
  const chartRows = () => (isDefault() || !chart.rows) ? D.candles : chart.rows;
  function withIndicators(rows) {
    let e20 = null, e200 = null, ag = null, al = null, prev = null; const out = [];
    rows.forEach((r, i) => {
      e20 = e20 == null ? r.close : e20 + (2 / 21) * (r.close - e20);
      e200 = e200 == null ? r.close : e200 + (2 / 201) * (r.close - e200);
      let rsi = 50;
      if (prev != null) { const d = r.close - prev, g = Math.max(d, 0), l = Math.max(-d, 0);
        ag = ag == null ? g : (ag * 13 + g) / 14; al = al == null ? l : (al * 13 + l) / 14; rsi = al === 0 ? 100 : 100 - 100 / (1 + ag / al); }
      prev = r.close; out.push(Object.assign({}, r, {ema20: e20, ema200: e200, rsi14: rsi}));
    });
    return out;
  }
  const kl = (k) => ({time: new Date(k[0]).toISOString().slice(0, 16) + 'Z', open: +k[1], high: +k[2], low: +k[3], close: +k[4], quote_volume: +k[7], closed: k[6] < Date.now()});
  async function loadChart() {
    if (chart.ws) { chart.ws.onclose = null; chart.ws.close(); chart.ws = null; }
    chart.live = false;
    if (isDefault()) { chart.rows = null; redrawChart(); return; }
    chart.loading = true; redrawChart();
    const pair = chart.sym + 'USDT';
    const hosts = ['https://data-api.binance.vision', 'https://api.binance.com'];
    let raw = null;
    for (const h of hosts) { try { const r = await fetch(`${h}/api/v3/klines?symbol=${pair}&interval=${chart.tf}&limit=500`); if (r.ok) { raw = await r.json(); break; } } catch (e) { /* try next host */ } }
    chart.loading = false;
    if (!raw) { chart.rows = []; redrawChart(); return; }
    chart.rows = withIndicators(raw.map(kl)); redrawChart();
    const want = `${chart.sym}|${chart.tf}`;
    const open = (attempt) => {
      if (`${chart.sym}|${chart.tf}` !== want) return;
      const ws = new WebSocket(['wss://data-stream.binance.vision/ws/', 'wss://stream.binance.com:9443/ws/'][attempt % 2] + pair.toLowerCase() + '@kline_' + chart.tf);
      chart.ws = ws;
      ws.onopen = () => { chart.live = true; redraw('chartLive'); };
      ws.onmessage = (ev) => {
        const k = JSON.parse(ev.data).k; if (!k || !chart.rows) return;
        const bar = kl([k.t, k.o, k.h, k.l, k.c, k.v, k.T, k.q]); bar.closed = k.x;
        const rows = chart.rows, last = rows[rows.length - 1];
        if (last && last.time === bar.time) rows[rows.length - 1] = bar; else if (!last || bar.time > last.time) { rows.push(bar); if (rows.length > 500) rows.shift(); }
        const prev = rows.length > 1 ? rows[rows.length - 2] : null, cur = rows[rows.length - 1];
        if (prev) { cur.ema20 = prev.ema20 + (2 / 21) * (cur.close - prev.ema20); cur.ema200 = prev.ema200 + (2 / 201) * (cur.close - prev.ema200); cur.rsi14 = prev.rsi14; }
        chartDirty = true;
      };
      ws.onclose = () => { chart.live = false; redraw('chartLive'); setTimeout(() => open(attempt + 1), 3000); };
      ws.onerror = () => ws.close();
    };
    open(0);
  }
  let chartDirty = false;
  function redrawChart() { ['chartTitle', 'chartLive', 'candleTime', 'candles', 'o_close', 'o_high', 'o_low', 'o_vol', 'o_rsi', 'o_chg'].forEach(redraw); }
  document.addEventListener('click', (e) => {
    const b = e.target.closest && e.target.closest('.seg button'); if (!b) return;
    document.querySelectorAll('.seg button').forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
    chart.tf = b.dataset.tf; loadChart();
  });
  document.addEventListener('change', (e) => { if (e.target && e.target.id === 'chart-sym') { chart.sym = e.target.value; loadChart(); } });

  // ---------------- tabs (hash routing) ----------------
  const TABS = ['overview', 'plans', 'scan', 'portfolio', 'strategy'];
  function showTab(name) {
    if (!TABS.includes(name)) name = 'overview';
    document.querySelectorAll('[data-view]').forEach((s) => { s.hidden = s.dataset.view !== name; });
    document.querySelectorAll('.tab').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === name)));
    if (D) render();
  }
  document.querySelectorAll('.tab').forEach((b) => b.addEventListener('click', () => {
    history.replaceState(null, '', '#' + b.dataset.tab); showTab(b.dataset.tab);
    window.scrollTo({top: document.querySelector('.tabs').offsetTop - 50, behavior: 'smooth'});
  }));
  window.addEventListener('hashchange', () => showTab(location.hash.slice(1)));

  // ---------------- render ----------------
  function render() {
    const s = D.status[0], acc = D.accounts, S = D.scanner || {}, A = S.analysis || null, P = S.plans || [];
    const CR = chartRows();
    const lastBar = CR[CR.length - 1] || {};
    const prevBar = CR.length > 1 ? CR[CR.length - 2] : null;
    const chg = prevBar ? (lastBar.close / prevBar.close - 1) * 100 : null;
    const total = acc.reduce((a, x) => a + +x.equity, 0), cap = acc.reduce((a, x) => a + +x.start_capital, 0);
    const btcNow = s.btc_close, e200 = (A && A.btc_ema200) || s.btc_ema200;
    const up = btcNow > e200, enterNow = P.filter((p) => p.state === 'enter_now'), near = P.filter((p) => p.state !== 'enter_now');
    const open = acc.reduce((n, x) => n + +x.open_positions, 0);

    draw('mode', (el) => el.textContent = s.mode === 'paper' ? 'PAPER · เงินจำลอง' : String(s.mode).toUpperCase());
    draw('btc', (el) => el.textContent = fmt.usd(btcNow));
    draw('tick', (el) => el.textContent = fmt.time(D.generated_at));

    // ---- hero ----
    draw('decisionBox', (el) => { el.classList.toggle('go', enterNow.length > 0); el.classList.toggle('stop', !up && !enterNow.length); });
    draw('heroTitle', (el) => {
      el.replaceChildren(mk('span', 'dot'));
      if (enterNow.length) el.append(`มีสัญญาณซื้อ ${enterNow.length} เหรียญ: ${enterNow.slice(0, 4).map((p) => p.symbol).join(', ')}`);
      else if (open) el.append(`ถือสถานะ ${open} ตัว — ปล่อยให้บอทจัดการตามกฎ`);
      else if (!up) el.append('ถือเงินสด — ตลาดเป็นขาลง ยังไม่ใช่จังหวะซื้อ');
      else el.append('ตลาดเปิดให้เข้าได้ — รอสัญญาณจากแผนเทรด');
    });
    draw('heroSub', (el) => {
      if (enterNow.length) el.textContent = 'ดูจุดเข้า, stop และขนาดไม้ได้ที่แท็บ "แผนเทรด" — ตั้ง stop ทุกครั้งหลังซื้อ';
      else if (!up) el.textContent = `กลยุทธ์หลักจะเริ่มซื้อเมื่อ BTC กลับขึ้นเหนือเส้น EMA200 (4h) ซึ่งตอนนี้อยู่ที่ ${fmt.usd(e200, 0)} · ระหว่างนี้มี ${near.length} เหรียญที่อยู่ในรายการเฝ้าดู`;
      else el.textContent = `BTC อยู่เหนือ EMA200 แล้ว · มี ${near.length} เหรียญใกล้จุดเข้า ระบบจะแจ้ง Telegram เมื่อเกิดสัญญาณ`;
    });
    draw('gate', (el) => {
      el.replaceChildren(); el.classList.toggle('open', up);
      const gap = (btcNow / e200 - 1) * 100;
      const frac = up ? 1 : Math.max(0.03, Math.min(1, 1 + gap / 25));   // -25% → empty, 0% → full
      const tr = mk('div', 'track'), f = mk('div', 'fill'); f.style.width = (frac * 100).toFixed(1) + '%'; tr.append(f);
      const l = mk('div', 'lbl');
      l.append(mk('span', null, `BTC ${fmt.usd(btcNow, 0)}`),
        mk('span', null, up ? `อยู่เหนือ EMA200 ${fmt.pct(gap, 1)} → บอทเปิดเทรดได้` : `ต้องขึ้นอีก ${fmt.pct(-gap / (1 + gap / 100), 1)} ถึง ${fmt.usd(e200, 0)} บอทจึงเริ่มซื้อ`));
      el.append(tr, l);
    });
    draw('tiles', (el) => {
      el.replaceChildren();
      const tile = (t, v, sub, c) => { const d = mk('div', 'tile'); d.append(mk('div', 't', t)); const vv = mk('div', 'v ' + (c || ''), v); d.append(vv, mk('div', 's', sub)); el.append(d); };
      tile('สภาพตลาด', A ? A.regime_th : (up ? 'ขาขึ้น' : 'ขาลง'), A ? `${A.liquid_up}/${A.liquid_coins} เหรียญเป็นขาขึ้น (${A.breadth_pct.toFixed(0)}%)` : '', A ? (A.regime === 'bull' ? 'pos' : A.regime === 'bear' ? 'neg' : '') : '');
      tile('BTC 30 วัน', A && A.btc_mom_30d_pct != null ? fmt.pct(A.btc_mom_30d_pct, 1) : '—', A ? `RSI 4h ${A.btc_rsi14.toFixed(0)}` : '', A ? cls(A.btc_mom_30d_pct) : '');
      tile('ความผันผวน BTC', A ? A.btc_vol_annual_pct.toFixed(0) + '%' : '—', A ? `ต่อปี · ปกติ ~${A.btc_vol_base_pct.toFixed(0)}%` : '', A && A.btc_vol_annual_pct > A.btc_vol_base_pct * 1.3 ? 'neg' : '');
      const pnl = cap ? (total / cap - 1) * 100 : 0;
      tile('พอร์ตจำลอง', fmt.usd(total, 0) + ' USDT', `${fmt.pct(pnl)} · ถือ ${open} สถานะ`, cls(pnl));
    });
    draw('nPlans', (el) => { el.textContent = P.length; el.classList.toggle('hot', enterNow.length > 0); });
    draw('nScan', (el) => el.textContent = S.total || 0);

    // ---- overview ----
    draw('regimeChip', (el) => { if (!A) { el.textContent = '—'; return; } el.className = 'chip ' + (A.regime === 'bull' ? 'up' : A.regime === 'bear' ? 'down' : 'paper'); el.textContent = A.regime_th; });
    draw('anMeta', (el) => el.textContent = S.generated_at ? fmt.time(S.generated_at) : '');
    draw('anLines', (el) => { el.replaceChildren(); if (!A) { el.append(mk('li', null, 'ยังไม่มีผลวิเคราะห์ (รอบอทรันรอบถัดไป)')); return; } for (const t of A.lines) el.append(mk('li', null, t)); });
    draw('chartTitle', (el) => el.textContent = `${chart.sym}/USDT · ${TF_LABEL[chart.tf]} · Binance`);
    draw('chartLive', (el) => { const on = isDefault() ? (document.getElementById('live')?.classList.contains('up')) : chart.live;
      el.className = 'chip ' + (on ? 'up' : ''); el.textContent = chart.loading ? 'กำลังโหลด…' : on ? '● เรียลไทม์' : '○ ไม่สด'; });
    draw('candleTime', (el) => el.textContent = lastBar.time ? 'แท่งล่าสุด ' + fmt.time(lastBar.time) : '');
    draw('chartSym', (el) => { if (el.options.length) return; const syms = Array.from(new Set(['BTC', ...D.market.map((m) => m.symbol)]));
      for (const x of syms) el.append(new Option(x + '/USDT', x)); el.value = chart.sym; });
    draw('o_close', (el) => el.textContent = fmt.px(lastBar.close));
    draw('o_high', (el) => el.textContent = fmt.px(lastBar.high));
    draw('o_low', (el) => el.textContent = fmt.px(lastBar.low));
    draw('o_vol', (el) => el.textContent = fmt.big(lastBar.quote_volume));
    draw('o_rsi', (el) => el.textContent = lastBar.rsi14 == null ? '—' : Number(lastBar.rsi14).toFixed(1));
    draw('o_chg', (el) => { el.className = cls(chg); el.textContent = fmt.pct(chg); });
    draw('candles', candles);
    draw('marketRows', (tb) => {
      tb.replaceChildren();
      for (const r of D.market) { const tr = tb.insertRow(); tr.insertCell().textContent = r.symbol;
        const a = tr.insertCell(); a.className = 'num'; a.textContent = fmt.px(r.last);
        const b = tr.insertCell(); b.className = 'num ' + cls(r.change_24h_pct); b.textContent = fmt.pct(r.change_24h_pct);
        const c = tr.insertCell(); c.className = 'num'; c.textContent = fmt.big(r.quote_volume_24h); }
    });
    draw('events', (el) => {
      el.replaceChildren();
      if (!D.events.length) { el.append(mk('div', 'empty', 'ยังไม่มีการซื้อขาย — บอทตรวจทุกชั่วโมง และจะแสดงที่นี่เมื่อมีสัญญาณซื้อ/ขาย หรือ Sentinel ปฏิเสธ/หยุดการเทรด')); return; }
      const kind = {BUY: 'buy', SELL: 'sell', SENTINEL_HALT: 'warn', SENTINEL_REJECT: 'warn', ERROR: 'warn', GROK_VETO: 'warn'};
      const name = {BUY: 'ซื้อ', SELL: 'ขาย', SENTINEL_HALT: 'Sentinel หยุด', SENTINEL_REJECT: 'Sentinel ปฏิเสธ', SENTINEL_RESUME: 'กลับมาเทรด', ERROR: 'ข้อผิดพลาด', SIGNALS: 'สัญญาณ', GROK_REVIEW: 'Grok ตรวจ', GROK_VETO: 'Grok คัดค้าน'};
      for (const e of D.events) { const card = mk('div', 'ev ' + (kind[e.event] || 'info')); const h = mk('div', 'h');
        h.append(mk('span', null, (name[e.event] || e.event) + (e.symbol ? ' · ' + e.symbol : '')), mk('span', 't', fmt.time(e.time)));
        const bits = [ROLE[e.role] || e.strategy]; if (e.price != null) bits.push('@ ' + fmt.px(e.price));
        if (e.pnl != null) bits.push('กำไร/ขาดทุน ' + (e.pnl > 0 ? '+' : '') + fmt.usd(e.pnl)); if (e.detail) bits.push(e.detail);
        card.append(h, mk('div', 'd', bits.join(' · '))); el.append(card); }
    });

    // ---- plans ----
    draw('plans', (el) => {
      el.replaceChildren();
      if (!P.length) { el.append(mk('div', 'empty', 'ตอนนี้ยังไม่มีเหรียญที่เข้าเงื่อนไขหรือใกล้จุดเข้า (ต้องอยู่เหนือ EMA200 และใกล้ทะลุกรอบ Keltner) ระบบจะแจ้งใน Telegram ทันทีเมื่อมี')); return; }
      const ST = {enter_now: ['เข้าได้ตอนนี้', 'buy_signal'], near: ['ใกล้จุดเข้า', 'uptrend'], wait_btc: ['รอ BTC ขาขึ้น', 'new']};
      for (const p of P.slice(0, 24)) {
        const card = mk('div', 'plan ' + p.state);
        const top = mk('div', 'top', p.symbol); top.append(mk('span', 'pill ' + ST[p.state][1], ST[p.state][0]));
        if (!p.in_universe) top.append(mk('span', 'pill illiquid', 'นอก Top 20'));
        const kv = mk('div', 'kv'); const add = (k, v) => kv.append(mk('span', null, k), mk('span', null, v));
        add('ราคาตอนนี้', fmt.px(p.price));
        add('จุดเข้า', fmt.px(p.entry) + (p.state === 'enter_now' ? '' : `  (+${p.distance_pct.toFixed(1)}%)`));
        add('Stop', fmt.px(p.stop) + `  (−${p.stop_pct.toFixed(1)}%)`);
        add('ขนาดไม้', `~${fmt.usd(p.size_usdt, 0)} USDT`);
        add('เสียได้สูงสุด', `${fmt.usd(p.risk_usdt, 1)} USDT`);
        const t1 = mk('div', 'txt'); t1.append(mk('b', null, 'เข้า: '), p.how_to_enter);
        const t2 = mk('div', 'txt'); t2.append(mk('b', null, 'ออก: '), p.how_to_exit);
        card.append(top, kv, t1, t2); if (p.note) card.append(mk('div', 'txt', '⚠️ ' + p.note)); el.append(card);
      }
    });

    // ---- scan ----
    renderScanner();

    // ---- portfolio ----
    draw('total', (el) => el.textContent = fmt.usd(total) + ' USDT');
    draw('totalsub', (el) => { const p = cap ? (total / cap - 1) * 100 : 0; el.className = 'subv ' + cls(p); el.textContent = fmt.pct(p) + ' ตั้งแต่เริ่ม · 3 บัญชี × 500 USDT'; });
    draw('accounts', (el) => {
      el.replaceChildren();
      for (const x of acc) {
        const row = mk('div', 'acct'); const n = mk('div', 'n', x.strategy); n.append(mk('span', 'role', ROLE[x.role] || x.role));
        const r = mk('div', 'r'); r.append(mk('span', cls(x.pnl_pct), fmt.pct(x.pnl_pct)), ` จำลอง · backtest ${fmt.pct(x.bt_return_pct, 1)} · Sharpe ${Number(x.bt_sharpe).toFixed(2)}`);
        const r2 = mk('div', 'r', `ถือ ${x.open_positions} · ปิดแล้ว ${x.closed_trades}`); r2.style.textAlign = 'right';
        row.append(n, mk('div', 'v', fmt.usd(x.equity)), r, r2); el.append(row);
      }
    });
    draw('risk', (el) => {
      el.replaceChildren();
      const bar = (f, c) => { const b = mk('div', 'rbar'); const i = mk('i'); i.style.width = Math.max(2, Math.min(100, f * 100)) + '%'; i.style.background = c; b.append(i); return b; };
      const col = (f) => f >= 0.8 ? 'var(--down)' : f >= 0.5 ? 'var(--amber)' : 'var(--up)';
      for (const r of D.risk) { const g = mk('div', 'gauge'); const l = mk('div', 'lbl', ROLE[r.role] || r.role);
        const sm = mk('small', null, r.halted ? '⛔ หยุด' + (r.resume_on ? ' ถึง ' + r.resume_on : '') : '● ทำงานปกติ'); sm.style.color = r.halted ? 'var(--down)' : 'var(--up)'; l.append(sm);
        const body = mk('div'); const lu = r.day_pnl_pct < 0 ? r.day_pnl_pct / r.daily_limit_pct : 0, su = r.loss_streak / r.loss_streak_limit;
        const l1 = mk('div', 'gline'); l1.append(mk('span', null, 'ขาดทุนวันนี้'), mk('span', null, fmt.pct(r.day_pnl_pct) + ' / เพดาน ' + r.daily_limit_pct + '%'));
        const l2 = mk('div', 'gline'); l2.append(mk('span', null, 'แพ้ติดกัน'), mk('span', null, r.loss_streak + ' / ' + r.loss_streak_limit + ' ครั้ง'));
        body.append(l1, bar(lu, col(lu)), l2, bar(su, col(su))); if (r.halted && r.halt_reason) { const h = mk('div', 'gline', r.halt_reason); h.style.color = 'var(--down)'; body.append(h); }
        g.append(l, body); el.append(g); }
    });
    draw('paperEquity', (el) => {
      const n = d3.groups(D.equity, (r) => r.strategy)[0]?.[1].length || 0;
      if (n < 2) { el.replaceChildren(mk('div', 'empty', 'เพิ่งเริ่มเทรดจำลอง (' + n + ' รอบ) กราฟจะขึ้นเมื่อบอทรันครบหลายชั่วโมง')); return; }
      lines(el, D.equity, {xKey: 'time', yKey: 'equity', sKey: 'strategy', parse: (q) => new Date(q), height: 200, yFmt: d3.format(',.1f'), xFmt: d3.utcFormat('%d %b'), empty: ''});
    });
    draw('posRows', (tb) => {
      tb.replaceChildren(); document.querySelectorAll('.posempty').forEach((e) => e.hidden = D.positions.length > 0);
      for (const r of D.positions) { const tr = tb.insertRow(); tr.insertCell().textContent = r.symbol; tr.insertCell().textContent = r.strategy;
        for (const k of ['entry', 'last', 'stop']) { const c = tr.insertCell(); c.className = 'num'; c.textContent = fmt.px(r[k]); }
        const p = tr.insertCell(); p.className = 'num ' + cls(r.pnl); p.textContent = (r.pnl > 0 ? '+' : '') + fmt.usd(r.pnl); }
    });

    // ---- strategy ----
    draw('btCurves', (el) => lines(el, D.bt_curves, {xKey: 'date', yKey: 'equity', sKey: 'series', parse: (q) => new Date(q + 'T00:00:00Z'), height: 260, yFmt: d3.format(',.0f'), xFmt: d3.utcFormat('%b %y'), empty: 'ยังไม่มีผล backtest'}));
    draw('btLegend', (el) => { el.replaceChildren(); for (const [n, rs] of d3.groups(D.bt_curves, (r) => r.series)) { const sp = mk('span'); const i = mk('i'); i.style.background = SERIES[n] || '#9aa'; sp.append(i, n + ' → ' + d3.format(',.0f')(rs[rs.length - 1].equity)); el.append(sp); } });
    draw('leaderRows', (tb) => {
      tb.replaceChildren();
      const label = {champion: '👑 Champion', challenger_1: 'Challenger 1', challenger_2: 'Challenger 2', passed: 'ผ่าน (สำรอง)', cut: 'ตัดทิ้ง', benchmark: 'ตัวเทียบ'};
      for (const r of D.leaderboard) { const tr = tb.insertRow();
        if (/^(champion|challenger)/.test(r.status)) tr.className = 'hl'; if (r.status === 'benchmark') tr.className = 'bench';
        tr.insertCell().textContent = r.name; const st = tr.insertCell(); st.textContent = label[r.status] || r.status;
        st.style.color = r.status === 'cut' ? 'var(--down)' : /^(champion|challenger)/.test(r.status) ? 'var(--accent)' : 'var(--muted)';
        const a = tr.insertCell(); a.className = 'num ' + cls(r.return_pct); a.textContent = fmt.pct(r.return_pct, 1);
        const b = tr.insertCell(); b.className = 'num'; b.textContent = Number(r.max_dd_pct).toFixed(1) + '%';
        const c = tr.insertCell(); c.className = 'num'; c.textContent = Number(r.sharpe).toFixed(2);
        const d = tr.insertCell(); d.className = 'num'; d.textContent = r.trades == null ? '–' : r.trades; }
    });
  }

  // ---------------- scanner ----------------
  const SCAN_LABEL = {buy_signal: 'สัญญาณซื้อ', uptrend: 'ขาขึ้น', downtrend: 'ขาลง', illiquid: 'สภาพคล่องต่ำ', new: 'ข้อมูลไม่พอ'};
  let scanFilter = 'buy_signal,uptrend';
  function renderScanner() {
    const S = D.scanner;
    draw('scanMeta', (el) => el.textContent = S ? `${S.total} เหรียญ · แท่ง ${fmt.time(S.bar)}` : 'ยังไม่มีผลสแกน');
    draw('scanTabs', (el) => {
      el.replaceChildren(); if (!S) return;
      const c = S.counts || {};
      const tabs = [['buy_signal,uptrend', `น่าสนใจ ${(c.buy_signal || 0) + (c.uptrend || 0)}`], ['buy_signal', `สัญญาณซื้อ ${c.buy_signal || 0}`],
        ['downtrend', `ขาลง ${c.downtrend || 0}`], ['illiquid', `สภาพคล่องต่ำ ${c.illiquid || 0}`], ['all', `ทั้งหมด ${S.total}`]];
      for (const [k, label] of tabs) { const b = mk('button', 'ftab', label); b.type = 'button'; b.setAttribute('aria-pressed', String(k === scanFilter));
        b.onclick = () => { scanFilter = k; renderScanner(); }; el.append(b); }
    });
    draw('scanRows', (tb) => {
      tb.replaceChildren(); if (!S) return;
      const q = (document.getElementById('scan-search')?.value || '').trim().toUpperCase();
      const allow = scanFilter === 'all' ? null : scanFilter.split(',');
      let rows = S.rows.filter((r) => (q ? r.symbol.includes(q) : (!allow || allow.includes(r.status))));
      const total = rows.length; rows = rows.slice(0, 200);
      if (!rows.length) { const tr = tb.insertRow(); const td = tr.insertCell(); td.colSpan = 9; td.style.fontFamily = 'inherit'; td.style.color = 'var(--muted)'; td.style.fontWeight = '400';
        td.textContent = scanFilter === 'buy_signal' ? 'ตอนนี้ไม่มีเหรียญไหนเข้าเงื่อนไขซื้อของกลยุทธ์' : 'ไม่พบเหรียญ'; return; }
      for (const r of rows) {
        const tr = tb.insertRow(); tr.insertCell().textContent = r.symbol;
        tr.insertCell().append(mk('span', 'pill ' + r.status, SCAN_LABEL[r.status] || r.status));
        const n = (v, f, colored) => { const td = tr.insertCell(); td.className = 'num' + (colored && v != null ? ' ' + cls(v) : ''); td.textContent = v == null ? '–' : f(v); };
        n(r.price, fmt.px); n(r.change_24h_pct, fmt.pct, true); n(r.vs_ema200_pct, (v) => fmt.pct(v, 1), true);
        n(r.rsi14, (v) => v.toFixed(0)); n(r.mom_30d_pct, (v) => fmt.pct(v, 1), true); n(r.quote_volume_24h, fmt.big);
        const sg = tr.insertCell(); sg.style.fontFamily = 'inherit'; sg.style.fontWeight = '400';
        sg.textContent = [r.buy_signals && ('ซื้อ: ' + r.buy_signals), r.sell_signals && ('ถ้าถืออยู่ควรขาย: ' + r.sell_signals)].filter(Boolean).join(' · ') || '–';
      }
      if (total > rows.length) { const tr = tb.insertRow(); const td = tr.insertCell(); td.colSpan = 9; td.style.color = 'var(--muted)'; td.textContent = `แสดง ${rows.length} จาก ${total} — พิมพ์ค้นหาเพื่อดูเหรียญอื่น`; }
    });
  }
  document.addEventListener('input', (e) => { if (e.target && e.target.id === 'scan-search' && D) redraw('scanRows'); });

  // ---------------- charts ----------------
  function tipBox(el) { const t = mk('div', 'tip'); t.hidden = true; el.append(t); return t; }
  function placeTip(el, tip, x, y) { tip.hidden = false; tip.style.left = Math.max(0, Math.min(el.clientWidth - tip.offsetWidth, x + 12)) + 'px'; tip.style.top = Math.max(0, y - tip.offsetHeight - 8) + 'px'; }

  function candles(el) {
    el.replaceChildren();
    if (chart.loading) { el.append(mk('div', 'empty', 'กำลังโหลดกราฟจาก Binance…')); return; }
    const src = chartRows();
    if (!src.length) { el.append(mk('div', 'empty', 'โหลดกราฟไม่สำเร็จ — เบราว์เซอร์เชื่อมต่อ Binance ไม่ได้ ลองเลือกใหม่อีกครั้ง')); return; }
    const W = Math.max(280, el.clientWidth);
    const rows = src.slice(-Math.max(40, Math.min(src.length, Math.floor(W / 6))));
    const short = ['1m', '5m', '15m'].includes(chart.tf);
    const H = W < 500 ? 340 : 400, mR = 64, mL = 4, top = 6, gap = 8, hVol = 50, hRsi = 62, hMain = H - hVol - hRsi - gap * 2 - 26;
    const yVol0 = top + hMain + gap, yRsi0 = yVol0 + hVol + gap + 4;
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H).attr('role', 'img').attr('aria-label', 'กราฟแท่งเทียน BTC/USDT 4 ชั่วโมง พร้อม EMA20, EMA200, volume และ RSI');
    const x = d3.scaleBand().domain(rows.map((r) => r.time)).range([mL, W - mR]).padding(0.25);
    const y = d3.scaleLinear().domain([d3.min(rows, (r) => Math.min(r.low, r.ema200)), d3.max(rows, (r) => Math.max(r.high, r.ema200))]).nice().range([top + hMain, top]);
    const yv = d3.scaleLinear().domain([0, d3.max(rows, (r) => r.quote_volume)]).range([yVol0 + hVol, yVol0]);
    const yr = d3.scaleLinear().domain([0, 100]).range([yRsi0 + hRsi, yRsi0]);
    const g0 = svg.append('g');
    const yf = (v) => Math.abs(v) >= 1000 ? d3.format(',.0f')(v) : fmt.px(v);
    y.ticks(5).forEach((t) => { g0.append('line').attr('x1', mL).attr('x2', W - mR).attr('y1', y(t)).attr('y2', y(t)).style('stroke', '#151e27'); g0.append('text').attr('x', W - mR + 6).attr('y', y(t) + 3).text(yf(t)); });
    [30, 70].forEach((t) => { g0.append('line').attr('x1', mL).attr('x2', W - mR).attr('y1', yr(t)).attr('y2', yr(t)).style('stroke', '#26323f').style('stroke-dasharray', '3 3'); g0.append('text').attr('x', W - mR + 6).attr('y', yr(t) + 3).text(t); });
    g0.append('text').attr('x', W - mR + 6).attr('y', yVol0 + 10).text('Vol');
    const step = Math.ceil(rows.length / Math.max(2, Math.floor((W - mR) / 90)));
    rows.forEach((r, i) => { if (i % step === 0) svg.append('text').attr('x', x(r.time) + x.bandwidth() / 2).attr('y', H - 4).attr('text-anchor', 'middle').text((short ? d3.timeFormat('%H:%M') : chart.tf === '1h' ? d3.timeFormat('%d %b %H:%M') : d3.utcFormat('%d %b'))(new Date(r.time))); });
    const up = '#22c983', down = '#f0525b', g = svg.append('g');
    rows.forEach((r) => { const cx = x(r.time) + x.bandwidth() / 2, c = r.close >= r.open ? up : down;
      g.append('line').attr('x1', cx).attr('x2', cx).attr('y1', y(r.high)).attr('y2', y(r.low)).style('stroke', c);
      g.append('rect').attr('x', x(r.time)).attr('width', x.bandwidth()).attr('y', y(Math.max(r.open, r.close))).attr('height', Math.max(1, Math.abs(y(r.open) - y(r.close)))).style('fill', c).style('opacity', r.closed ? 1 : .55);
      g.append('rect').attr('x', x(r.time)).attr('width', x.bandwidth()).attr('y', yv(r.quote_volume)).attr('height', yVol0 + hVol - yv(r.quote_volume)).style('fill', c).style('opacity', .3); });
    const line = (f, sc) => d3.line().x((r) => x(r.time) + x.bandwidth() / 2).y((r) => sc(f(r)));
    [['ema20', '#33c3b4', y, 1.4], ['ema200', '#f2a93b', y, 1.8], ['rsi14', '#8f7cf2', yr, 1.3]].forEach(([k, c, sc, w]) => svg.append('path').datum(rows).attr('d', line((r) => r[k], sc)).style('fill', 'none').style('stroke', c).style('stroke-width', w));
    const last = rows[rows.length - 1], tc = last.close >= last.open ? up : down;
    svg.append('line').attr('x1', mL).attr('x2', W - mR).attr('y1', y(last.close)).attr('y2', y(last.close)).style('stroke', tc).style('stroke-dasharray', '2 3').style('opacity', .6);
    svg.append('rect').attr('x', W - mR + 2).attr('y', y(last.close) - 8).attr('width', mR - 4).attr('height', 16).attr('rx', 3).style('fill', tc);
    svg.append('text').attr('x', W - mR + 6).attr('y', y(last.close) + 4).style('fill', '#06120c').style('font-weight', 600).text(yf(last.close));
    const tip = tipBox(el), cross = svg.append('line').style('stroke', '#3a4757').attr('y1', top).attr('y2', H - 16).style('display', 'none');
    svg.append('rect').attr('x', mL).attr('width', W - mR - mL).attr('height', H).style('fill', 'transparent')
      .on('pointermove', (ev) => { const [px] = d3.pointer(ev); const i = Math.max(0, Math.min(rows.length - 1, Math.floor((px - mL) / x.step()))); const r = rows[i], cx = x(r.time) + x.bandwidth() / 2;
        cross.attr('x1', cx).attr('x2', cx).style('display', null); tip.textContent = '';
        [fmt.time(r.time) + (r.closed ? '' : ' (ยังไม่ปิด)'), 'เปิด ' + fmt.px(r.open) + '  สูง ' + fmt.px(r.high), 'ต่ำ ' + fmt.px(r.low) + '  ปิด ' + fmt.px(r.close),
          'EMA20 ' + fmt.px(r.ema20) + '  EMA200 ' + fmt.px(r.ema200), 'RSI ' + Number(r.rsi14).toFixed(1) + '  Vol ' + fmt.big(r.quote_volume)].forEach((t) => tip.append(mk('div', null, t)));
        const [, py] = d3.pointer(ev, el); placeTip(el, tip, cx * el.clientWidth / W, py); })
      .on('pointerleave', () => { tip.hidden = true; cross.style('display', 'none'); });
  }

  function lines(el, rows, o) {
    el.replaceChildren(); if (!rows.length) { el.append(mk('div', 'empty', o.empty)); return; }
    const series = d3.groups(rows, (r) => r[o.sKey]); const W = Math.max(260, el.clientWidth), H = o.height, mL = 4, mR = 58, mT = 8, mB = 20;
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H).attr('role', 'img').attr('aria-label', 'กราฟ equity');
    const xs = d3.scaleUtc().domain(d3.extent(rows, (r) => o.parse(r[o.xKey]))).range([mL, W - mR]);
    const ys = d3.scaleLinear().domain(d3.extent(rows, (r) => +r[o.yKey])).nice().range([H - mB, mT]);
    if (ys.domain()[0] === ys.domain()[1]) ys.domain([ys.domain()[0] * .98, ys.domain()[1] * 1.02]);
    ys.ticks(4).forEach((t) => { svg.append('line').attr('x1', mL).attr('x2', W - mR).attr('y1', ys(t)).attr('y2', ys(t)).style('stroke', '#151e27'); svg.append('text').attr('x', W - mR + 6).attr('y', ys(t) + 3).text(o.yFmt(t)); });
    xs.ticks(Math.max(2, Math.floor(W / 120))).forEach((t) => svg.append('text').attr('x', xs(t)).attr('y', H - 4).attr('text-anchor', 'middle').text(o.xFmt(t)));
    for (const [n, rs] of series) { const c = SERIES[n] || '#9aa';
      svg.append('path').datum(rs).attr('d', d3.line().x((r) => xs(o.parse(r[o.xKey]))).y((r) => ys(+r[o.yKey]))).style('fill', 'none').style('stroke', c).style('stroke-width', n === 'BTC buy & hold' ? 1.2 : 1.8);
      const l = rs[rs.length - 1]; svg.append('circle').attr('cx', xs(o.parse(l[o.xKey]))).attr('cy', ys(+l[o.yKey])).attr('r', 3).style('fill', c); }
    const tip = tipBox(el), keys = Array.from(new Set(rows.map((r) => r[o.xKey]))).sort();
    svg.append('rect').attr('x', mL).attr('width', W - mR - mL).attr('height', H).style('fill', 'transparent')
      .on('pointermove', (ev) => { const [px] = d3.pointer(ev); const key = keys[d3.bisector((d) => o.parse(d)).center(keys, xs.invert(px))]; tip.textContent = ''; tip.append(mk('div', null, fmt.time(o.parse(key))));
        for (const [n, rs] of series) { const r = rs.find((q) => q[o.xKey] === key); if (r) { const d = mk('div', null, n + '  ' + o.yFmt(+r[o.yKey])); d.style.color = SERIES[n] || '#ccc'; tip.append(d); } }
        const [, py] = d3.pointer(ev, el); placeTip(el, tip, xs(o.parse(key)) * el.clientWidth / W, py); })
      .on('pointerleave', () => { tip.hidden = true; });
  }

  // ---------------- data + live ----------------
  async function load() {
    try { const r = await fetch('data.json?t=' + Date.now(), {cache: 'no-store'}); D = await r.json(); render(); }
    catch (e) { document.querySelector('main').prepend(mk('div', 'err', 'โหลดข้อมูลไม่สำเร็จ: ' + e.message)); }
  }
  let dirty = false, hovering = false, lastMsg = 0, wsStarted = false;
  document.addEventListener('pointerover', (e) => { hovering = !!(e.target.closest && e.target.closest('[data-draw="candles"]')); });
  function liveChip(on) {
    let c = document.getElementById('live');
    if (!c) { c = mk('span', 'chip', ''); c.id = 'live'; document.querySelector('.bar .spacer').before(c); }
    c.className = 'chip ' + (on ? 'up' : ''); c.textContent = on ? '● LIVE' : '○ ออฟไลน์'; syncBar(); redraw('chartLive');
    c.title = on ? 'ราคาอัปเดตทุกวินาทีจาก Binance' : 'เชื่อมต่อราคาสดไม่ได้ กำลังลองใหม่ (ข้อมูลรายชั่วโมงยังแสดงอยู่)';
  }
  function connect() {
    if (!D || wsStarted) return; wsStarted = true;
    const syms = Array.from(new Set(['BTC', ...D.market.map((m) => m.symbol)])).map((x) => x.toLowerCase() + 'usdt');
    const streams = ['btcusdt@kline_4h', ...syms.map((x) => x + '@miniTicker')].join('/');
    const hosts = ['wss://data-stream.binance.vision/stream?streams=', 'wss://stream.binance.com:9443/stream?streams='];
    let attempt = 0;
    const open = () => {
      const ws = new WebSocket(hosts[attempt % hosts.length] + streams);
      ws.onmessage = (ev) => {
        lastMsg = Date.now(); const d = JSON.parse(ev.data).data; if (!d) return;
        if (d.e === '24hrMiniTicker') {
          const sym = d.s.replace('USDT', ''), row = D.market.find((r) => r.symbol === sym);
          if (row) { row.last = +d.c; row.change_24h_pct = (+d.c / +d.o - 1) * 100; row.quote_volume_24h = +d.q; }
          if (sym === 'BTC') D.status[0].btc_close = +d.c;
          dirty = true;
        } else if (d.e === 'kline') {
          const k = d.k, t = new Date(k.t).toISOString().slice(0, 16) + 'Z', last = D.candles[D.candles.length - 1];
          const bar = {time: t, open: +k.o, high: +k.h, low: +k.l, close: +k.c, quote_volume: +k.q, closed: k.x};
          if (last && last.time === t) Object.assign(last, bar);
          else if (last && t > last.time) { const a20 = 2 / 21, a200 = 2 / 201;
            D.candles.push(Object.assign({}, bar, {ema20: last.ema20 + a20 * (bar.close - last.ema20), ema200: last.ema200 + a200 * (bar.close - last.ema200), rsi14: last.rsi14})); D.candles.shift(); }
          dirty = true;
        }
      };
      ws.onopen = () => { attempt = 0; liveChip(true); };
      ws.onclose = () => { liveChip(false); attempt++; setTimeout(open, Math.min(30000, 2000 * attempt)); };
      ws.onerror = () => ws.close();
    };
    open();
  }
  setInterval(() => {
    if (!D) return;
    if (dirty) { dirty = false; ['btc', 'gate', 'marketRows'].forEach(redraw); if (isDefault() && !hovering) redrawChart(); }
    if (chartDirty && !isDefault() && !hovering) { chartDirty = false; redrawChart(); }
  }, 1000);
  function syncBar() { const b = document.querySelector('.bar'); if (b) document.documentElement.style.setProperty('--barh', b.offsetHeight + 'px'); }
  window.addEventListener('resize', syncBar); syncBar();
  setInterval(() => { if (lastMsg && Date.now() - lastMsg > 60000) liveChip(false); }, 10000);
  let rw; window.addEventListener('resize', () => { clearTimeout(rw); rw = setTimeout(() => D && render(), 200); });

  showTab(location.hash.slice(1));
  load().then(connect); setInterval(load, 5 * 60 * 1000);
})();
