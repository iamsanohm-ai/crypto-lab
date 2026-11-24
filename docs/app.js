// Crypto Lab Terminal — static version for GitHub Pages. Reads ./data.json written hourly by GitHub Actions.
(function () {
  const fmt = {
    usd: (v, d) => v == null || isNaN(v) ? '—' : Number(v).toLocaleString('en-US', {minimumFractionDigits: d ?? 2, maximumFractionDigits: d ?? 2}),
    px: (v) => v == null ? '—' : (Math.abs(v) >= 1000 ? fmt.usd(v, 2) : Math.abs(v) >= 1 ? fmt.usd(v, 4) : Number(v).toPrecision(4)),
    pct: (v) => v == null || isNaN(v) ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(2) + '%',
    big: (v) => v == null ? '—' : d3.format('.3~s')(v).replace('G', 'B'),
    time: (s) => { if (!s) return '—'; const d = new Date(s); return isNaN(d) ? s : d.toLocaleString('th-TH', {day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit'}); },
  };
  const cls = (v) => v > 0 ? 'ct-pos' : v < 0 ? 'ct-neg' : 'ct-flat';
  const SERIES = {keltner_trend: '#2bc4b6', golden_cross_50_200: '#8f7cf2', breakout_funding_filter: '#f2a93b', 'BTC buy & hold': '#6b7a8a'};
  const ROLE = {champion: 'Champion', challenger_1: 'Challenger 1', challenger_2: 'Challenger 2'};
  const $$ = (name) => document.querySelectorAll(`[data-draw="${name}"]`);
  const draw = (name, fn) => $$(name).forEach((el) => { try { fn(el); } catch (e) { el.textContent = 'แสดงผลไม่ได้'; console.error(name, e); } });
  const mk = (tag, cl, text) => { const e = document.createElement(tag); if (cl) e.className = cl; if (text != null) e.textContent = text; return e; };
  let D = null;

  function render() {
    const s = D.status[0], acc = D.accounts;
    const lastClosed = (() => { for (let i = D.candles.length - 1; i >= 0; i--) if (D.candles[i].closed) return D.candles[i]; return D.candles[D.candles.length - 1]; })();
    const closed = D.candles.filter((c) => c.closed);
    const chg = closed.length > 1 ? (closed[closed.length - 1].close / closed[closed.length - 2].close - 1) * 100 : null;
    const total = acc.reduce((a, x) => a + +x.equity, 0), cap = acc.reduce((a, x) => a + +x.start_capital, 0);

    draw('mode', (el) => el.textContent = s.mode === 'paper' ? 'PAPER' : String(s.mode).toUpperCase());
    draw('regime', (el) => { el.className = 'ct-chip ' + (s.regime === 'up' ? 'up' : 'down'); el.textContent = s.regime === 'up' ? 'BTC > EMA200 · ขาขึ้น' : 'BTC < EMA200 · ขาลง'; });
    draw('btc', (el) => el.textContent = fmt.usd(s.btc_close));
    draw('tick', (el) => el.textContent = fmt.time(s.last_bot_tick) + ' · ข้อมูล ' + fmt.time(D.generated_at));
    draw('candleTime', (el) => el.textContent = 'แท่งปิดล่าสุด ' + fmt.time(s.candle_time));
    draw('takeaway', (el) => {
      const champ = acc.find((x) => x.role === 'champion'); const open = acc.reduce((n, x) => n + +x.open_positions, 0);
      const gap = (s.btc_close / s.btc_ema200 - 1) * 100; el.textContent = '';
      const b = (t) => mk('b', null, t);
      if (s.regime === 'up') el.append('BTC อยู่เหนือ EMA200 ', b(fmt.pct(gap)), ' กลยุทธ์ขาขึ้นเปิดสถานะได้ ตอนนี้ถืออยู่ ', b(String(open)), ' สถานะ');
      else el.append('BTC อยู่ต่ำกว่า EMA200 ', b(fmt.pct(gap)), ' จึงเป็นตลาดขาลง champion (', b(champ ? champ.strategy : '—'), ') และ challenger 2 จะไม่เปิดสถานะใหม่จนกว่า BTC จะกลับขึ้นเหนือเส้นนี้ ตอนนี้ถืออยู่ ', b(String(open)), ' สถานะ');
    });
    draw('total', (el) => el.textContent = fmt.usd(total) + ' USDT');
    draw('totalsub', (el) => { const p = cap ? (total / cap - 1) * 100 : 0; el.className = 'ct-sub ' + cls(p); el.textContent = fmt.pct(p) + ' ตั้งแต่เริ่ม (3 บัญชี × 500 USDT)'; });
    draw('accounts', (el) => {
      el.replaceChildren();
      for (const x of acc) {
        const row = mk('div', 'ct-acct'); const n = mk('div', 'n', x.strategy); n.append(mk('span', 'ct-role', ROLE[x.role] || x.role));
        const r = mk('div', 'r'); r.append(mk('span', cls(x.pnl_pct), fmt.pct(x.pnl_pct)), ` paper · BT ${fmt.pct(x.bt_return_pct)} · Sharpe ${Number(x.bt_sharpe).toFixed(2)}`);
        const r2 = mk('div', 'r', `${x.open_positions} ถือ · ${x.closed_trades} ปิด`); r2.style.textAlign = 'right';
        row.append(n, mk('div', 'v', fmt.usd(x.equity)), r, r2); el.append(row);
      }
    });
    draw('o_close', (el) => el.textContent = fmt.usd(lastClosed.close));
    draw('o_high', (el) => el.textContent = fmt.usd(lastClosed.high));
    draw('o_low', (el) => el.textContent = fmt.usd(lastClosed.low));
    draw('o_vol', (el) => el.textContent = fmt.big(lastClosed.quote_volume));
    draw('o_rsi', (el) => el.textContent = Number(lastClosed.rsi14).toFixed(1));
    draw('o_chg', (el) => { el.className = cls(chg); el.textContent = fmt.pct(chg); });
    draw('marketRows', (tb) => {
      tb.replaceChildren();
      for (const r of D.market) { const tr = tb.insertRow(); tr.insertCell().textContent = r.symbol;
        const a = tr.insertCell(); a.className = 'num'; a.textContent = fmt.px(r.last);
        const b = tr.insertCell(); b.className = 'num ' + cls(r.change_24h_pct); b.textContent = fmt.pct(r.change_24h_pct);
        const c = tr.insertCell(); c.className = 'num'; c.textContent = fmt.big(r.quote_volume_24h); }
    });
    draw('leaderRows', (tb) => {
      tb.replaceChildren();
      const label = {champion: '👑 Champion', challenger_1: 'Challenger 1', challenger_2: 'Challenger 2', passed: 'ผ่าน (สำรอง)', cut: 'ตัดทิ้ง', benchmark: 'เกณฑ์เทียบ'};
      for (const r of D.leaderboard) { const tr = tb.insertRow();
        if (/^(champion|challenger)/.test(r.status)) tr.className = 'hl'; if (r.status === 'benchmark') tr.className = 'bench';
        tr.insertCell().textContent = r.name; const st = tr.insertCell(); st.textContent = label[r.status] || r.status;
        st.style.color = r.status === 'cut' ? 'var(--down)' : /^(champion|challenger)/.test(r.status) ? 'var(--accent)' : 'var(--muted)';
        const a = tr.insertCell(); a.className = 'num ' + cls(r.return_pct); a.textContent = fmt.pct(r.return_pct);
        const b = tr.insertCell(); b.className = 'num'; b.textContent = Number(r.max_dd_pct).toFixed(1) + '%';
        const c = tr.insertCell(); c.className = 'num'; c.textContent = Number(r.sharpe).toFixed(2);
        const d = tr.insertCell(); d.className = 'num'; d.textContent = r.trades == null ? '–' : r.trades; }
    });
    draw('posRows', (tb) => {
      tb.replaceChildren(); document.querySelectorAll('.ct-posempty').forEach((e) => e.hidden = D.positions.length > 0);
      for (const r of D.positions) { const tr = tb.insertRow(); tr.insertCell().textContent = r.symbol; tr.insertCell().textContent = r.strategy;
        for (const k of ['entry', 'last', 'stop']) { const c = tr.insertCell(); c.className = 'num'; c.textContent = fmt.px(r[k]); }
        const p = tr.insertCell(); p.className = 'num ' + cls(r.pnl); p.textContent = (r.pnl > 0 ? '+' : '') + fmt.usd(r.pnl); }
    });
    draw('events', (el) => {
      el.replaceChildren();
      if (!D.events.length) { el.append(mk('div', 'ct-empty', 'ยังไม่มีสัญญาณหรือเทรด บอทตรวจทุกชั่วโมง และจะแสดงที่นี่เมื่อกลยุทธ์ส่งสัญญาณซื้อ/ขาย หรือ Sentinel ปฏิเสธ/หยุดการเทรด')); return; }
      const kind = {BUY: 'buy', SELL: 'sell', SENTINEL_HALT: 'warn', SENTINEL_REJECT: 'warn', ERROR: 'warn', GROK_VETO: 'warn'};
      const name = {BUY: 'ซื้อ', SELL: 'ขาย', SENTINEL_HALT: 'Sentinel หยุด', SENTINEL_REJECT: 'Sentinel ปฏิเสธ', SENTINEL_RESUME: 'กลับมาเทรด', ERROR: 'ข้อผิดพลาด', SIGNALS: 'สัญญาณ', GROK_REVIEW: 'Grok ตรวจ', GROK_VETO: 'Grok คัดค้าน'};
      for (const e of D.events) { const card = mk('div', 'ct-ev ' + (kind[e.event] || 'info')); const h = mk('div', 'h');
        h.append(mk('span', null, (name[e.event] || e.event) + (e.symbol ? ' · ' + e.symbol : '')), mk('span', 't', fmt.time(e.time)));
        const bits = [ROLE[e.role] || e.strategy]; if (e.price != null) bits.push('@ ' + fmt.px(e.price));
        if (e.pnl != null) bits.push('P&L ' + (e.pnl > 0 ? '+' : '') + fmt.usd(e.pnl)); if (e.detail) bits.push(e.detail);
        card.append(h, mk('div', 'd', bits.join(' · '))); el.append(card); }
    });
    draw('risk', (el) => {
      el.replaceChildren();
      const bar = (f, c) => { const b = mk('div', 'ct-bar'); const i = mk('i'); i.style.width = Math.max(2, Math.min(100, f * 100)) + '%'; i.style.background = c; b.append(i); return b; };
      const col = (f) => f >= 0.8 ? 'var(--down)' : f >= 0.5 ? 'var(--amber)' : 'var(--up)';
      for (const r of D.risk) { const g = mk('div', 'ct-gauge'); const l = mk('div', 'lbl', ROLE[r.role] || r.role);
        const sm = mk('small', null, r.halted ? '⛔ หยุด' + (r.resume_on ? ' ถึง ' + r.resume_on : '') : '● ทำงาน'); sm.style.color = r.halted ? 'var(--down)' : 'var(--up)'; l.append(sm);
        const body = mk('div'); const lu = r.day_pnl_pct < 0 ? r.day_pnl_pct / r.daily_limit_pct : 0, su = r.loss_streak / r.loss_streak_limit;
        const l1 = mk('div', 'ct-gline'); l1.append(mk('span', null, 'ขาดทุนวันนี้'), mk('span', null, fmt.pct(r.day_pnl_pct) + ' / ' + r.daily_limit_pct + '%'));
        const l2 = mk('div', 'ct-gline'); l2.append(mk('span', null, 'แพ้ติดกัน'), mk('span', null, r.loss_streak + ' / ' + r.loss_streak_limit));
        body.append(l1, bar(lu, col(lu)), l2, bar(su, col(su))); if (r.halted && r.halt_reason) { const h = mk('div', 'ct-gline', r.halt_reason); h.style.color = 'var(--down)'; body.append(h); }
        g.append(l, body); el.append(g); }
    });
    draw('candles', candles);
    draw('btCurves', (el) => lines(el, D.bt_curves, {xKey: 'date', yKey: 'equity', sKey: 'series', parse: (s) => new Date(s + 'T00:00:00Z'), height: 240, yFmt: d3.format(',.0f'), empty: 'ยังไม่มีผล backtest'}));
    draw('btLegend', (el) => { el.replaceChildren(); for (const [n, rs] of d3.groups(D.bt_curves, (r) => r.series)) { const sp = mk('span'); const i = mk('i'); i.style.background = SERIES[n] || '#9aa'; sp.append(i, n + ' ' + d3.format(',.0f')(rs[rs.length - 1].equity)); el.append(sp); } });
    draw('paperEquity', (el) => {
      const n = d3.groups(D.equity, (r) => r.strategy)[0]?.[1].length || 0;
      if (n < 2) { el.replaceChildren(mk('div', 'ct-empty', 'เพิ่งเริ่ม paper trading (' + n + ' รอบ) กราฟจะขึ้นเมื่อบอทรันครบหลายชั่วโมง')); return; }
      lines(el, D.equity, {xKey: 'time', yKey: 'equity', sKey: 'strategy', parse: (s) => new Date(s), height: 150, yFmt: d3.format(',.1f'), empty: ''});
    });
  }

  function tipBox(el) { const t = mk('div', 'ct-tip'); t.hidden = true; el.append(t); return t; }
  function placeTip(el, tip, x, y) { tip.hidden = false; tip.style.left = Math.max(0, Math.min(el.clientWidth - tip.offsetWidth, x + 12)) + 'px'; tip.style.top = Math.max(0, y - tip.offsetHeight - 8) + 'px'; }

  function candles(el) {
    el.replaceChildren();
    const rows = D.candles.slice(-Math.max(40, Math.min(D.candles.length, Math.floor(el.clientWidth / 5))));
    const W = Math.max(280, el.clientWidth), H = 420, mR = 64, mL = 4, hMain = 260, gap = 8, hVol = 54, hRsi = 70, top = 6;
    const yVol0 = top + hMain + gap, yRsi0 = yVol0 + hVol + gap + 6;
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H).attr('role', 'img').attr('aria-label', 'กราฟแท่งเทียน BTC/USDT 4 ชั่วโมง');
    const x = d3.scaleBand().domain(rows.map((r) => r.time)).range([mL, W - mR]).padding(0.25);
    const y = d3.scaleLinear().domain([d3.min(rows, (r) => Math.min(r.low, r.ema200)), d3.max(rows, (r) => Math.max(r.high, r.ema200))]).nice().range([top + hMain, top]);
    const yv = d3.scaleLinear().domain([0, d3.max(rows, (r) => r.quote_volume)]).range([yVol0 + hVol, yVol0]);
    const yr = d3.scaleLinear().domain([0, 100]).range([yRsi0 + hRsi, yRsi0]);
    const g0 = svg.append('g');
    y.ticks(6).forEach((t) => { g0.append('line').attr('x1', mL).attr('x2', W - mR).attr('y1', y(t)).attr('y2', y(t)).style('stroke', '#18222c'); g0.append('text').attr('x', W - mR + 6).attr('y', y(t) + 3).text(d3.format(',.0f')(t)); });
    [30, 70].forEach((t) => { g0.append('line').attr('x1', mL).attr('x2', W - mR).attr('y1', yr(t)).attr('y2', yr(t)).style('stroke', '#2a3644').style('stroke-dasharray', '3 3'); g0.append('text').attr('x', W - mR + 6).attr('y', yr(t) + 3).text(t); });
    g0.append('text').attr('x', W - mR + 6).attr('y', yVol0 + 10).text('Vol');
    const step = Math.ceil(rows.length / Math.max(2, Math.floor((W - mR) / 90)));
    rows.forEach((r, i) => { if (i % step === 0) svg.append('text').attr('x', x(r.time) + x.bandwidth() / 2).attr('y', H - 2).attr('text-anchor', 'middle').text(d3.utcFormat('%d %b')(new Date(r.time))); });
    const up = '#26d07c', down = '#f0525b', g = svg.append('g');
    rows.forEach((r) => { const cx = x(r.time) + x.bandwidth() / 2, c = r.close >= r.open ? up : down;
      g.append('line').attr('x1', cx).attr('x2', cx).attr('y1', y(r.high)).attr('y2', y(r.low)).style('stroke', c);
      g.append('rect').attr('x', x(r.time)).attr('width', x.bandwidth()).attr('y', y(Math.max(r.open, r.close))).attr('height', Math.max(1, Math.abs(y(r.open) - y(r.close)))).style('fill', c).style('opacity', r.closed ? 1 : .55);
      g.append('rect').attr('x', x(r.time)).attr('width', x.bandwidth()).attr('y', yv(r.quote_volume)).attr('height', yVol0 + hVol - yv(r.quote_volume)).style('fill', c).style('opacity', .35); });
    const line = (f, sc) => d3.line().x((r) => x(r.time) + x.bandwidth() / 2).y((r) => sc(f(r)));
    [['ema20', '#2bc4b6', y], ['ema200', '#f2a93b', y], ['rsi14', '#8f7cf2', yr]].forEach(([k, c, sc]) => svg.append('path').datum(rows).attr('d', line((r) => r[k], sc)).style('fill', 'none').style('stroke', c).style('stroke-width', 1.5));
    const last = rows[rows.length - 1], tc = last.close >= last.open ? up : down;
    svg.append('rect').attr('x', W - mR + 2).attr('y', y(last.close) - 8).attr('width', mR - 4).attr('height', 16).attr('rx', 3).style('fill', tc);
    svg.append('text').attr('x', W - mR + 6).attr('y', y(last.close) + 4).style('fill', '#071018').style('font-weight', 600).text(d3.format(',.0f')(last.close));
    const tip = tipBox(el), cross = svg.append('line').style('stroke', '#3a4757').attr('y1', top).attr('y2', H - 14).style('display', 'none');
    svg.append('rect').attr('x', mL).attr('width', W - mR - mL).attr('height', H).style('fill', 'transparent')
      .on('pointermove', (ev) => { const [px] = d3.pointer(ev); const i = Math.max(0, Math.min(rows.length - 1, Math.floor((px - mL) / x.step()))); const r = rows[i], cx = x(r.time) + x.bandwidth() / 2;
        cross.attr('x1', cx).attr('x2', cx).style('display', null); tip.textContent = '';
        [d3.utcFormat('%d %b %H:%M UTC')(new Date(r.time)) + (r.closed ? '' : ' (ยังไม่ปิด)'), 'O ' + fmt.usd(r.open) + '  H ' + fmt.usd(r.high), 'L ' + fmt.usd(r.low) + '  C ' + fmt.usd(r.close),
          'EMA20 ' + fmt.usd(r.ema20) + '  EMA200 ' + fmt.usd(r.ema200), 'RSI ' + Number(r.rsi14).toFixed(1) + '  Vol ' + fmt.big(r.quote_volume)].forEach((t) => tip.append(mk('div', null, t)));
        const [, py] = d3.pointer(ev, el); placeTip(el, tip, cx * el.clientWidth / W, py); })
      .on('pointerleave', () => { tip.hidden = true; cross.style('display', 'none'); });
  }

  function lines(el, rows, o) {
    el.replaceChildren(); if (!rows.length) { el.append(mk('div', 'ct-empty', o.empty)); return; }
    const series = d3.groups(rows, (r) => r[o.sKey]); const W = Math.max(260, el.clientWidth), H = o.height, mL = 4, mR = 58, mT = 8, mB = 18;
    const svg = d3.select(el).append('svg').attr('viewBox', `0 0 ${W} ${H}`).attr('height', H).attr('role', 'img').attr('aria-label', 'กราฟ equity');
    const xs = d3.scaleUtc().domain(d3.extent(rows, (r) => o.parse(r[o.xKey]))).range([mL, W - mR]);
    const ys = d3.scaleLinear().domain(d3.extent(rows, (r) => +r[o.yKey])).nice().range([H - mB, mT]);
    if (ys.domain()[0] === ys.domain()[1]) ys.domain([ys.domain()[0] * .98, ys.domain()[1] * 1.02]);
    ys.ticks(4).forEach((t) => { svg.append('line').attr('x1', mL).attr('x2', W - mR).attr('y1', ys(t)).attr('y2', ys(t)).style('stroke', '#18222c'); svg.append('text').attr('x', W - mR + 6).attr('y', ys(t) + 3).text(o.yFmt(t)); });
    xs.ticks(Math.max(2, Math.floor(W / 120))).forEach((t) => svg.append('text').attr('x', xs(t)).attr('y', H - 3).attr('text-anchor', 'middle').text(d3.utcFormat('%b %y')(t)));
    for (const [n, rs] of series) { const c = SERIES[n] || '#9aa';
      svg.append('path').datum(rs).attr('d', d3.line().x((r) => xs(o.parse(r[o.xKey]))).y((r) => ys(+r[o.yKey]))).style('fill', 'none').style('stroke', c).style('stroke-width', 1.7);
      const l = rs[rs.length - 1]; svg.append('circle').attr('cx', xs(o.parse(l[o.xKey]))).attr('cy', ys(+l[o.yKey])).attr('r', 3).style('fill', c); }
    const tip = tipBox(el), dates = Array.from(new Set(rows.map((r) => r[o.xKey]))).sort();
    svg.append('rect').attr('x', mL).attr('width', W - mR - mL).attr('height', H).style('fill', 'transparent')
      .on('pointermove', (ev) => { const [px] = d3.pointer(ev); const key = dates[d3.bisector((d) => o.parse(d)).center(dates, xs.invert(px))]; tip.textContent = ''; tip.append(mk('div', null, key));
        for (const [n, rs] of series) { const r = rs.find((q) => q[o.xKey] === key); if (r) { const d = mk('div', null, n + '  ' + o.yFmt(+r[o.yKey])); d.style.color = SERIES[n] || '#ccc'; tip.append(d); } }
        const [, py] = d3.pointer(ev, el); placeTip(el, tip, xs(o.parse(key)) * el.clientWidth / W, py); })
      .on('pointerleave', () => { tip.hidden = true; });
  }

  async function load() {
    try { const r = await fetch('data.json?t=' + Date.now(), {cache: 'no-store'}); D = await r.json(); render(); }
    catch (e) { document.querySelector('.ct').prepend(mk('div', 'ct-err', 'โหลดข้อมูลไม่สำเร็จ: ' + e.message)); }
  }
  let rw; window.addEventListener('resize', () => { clearTimeout(rw); rw = setTimeout(() => D && render(), 200); });
  load(); setInterval(load, 5 * 60 * 1000);
})();
