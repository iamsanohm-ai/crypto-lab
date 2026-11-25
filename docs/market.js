// ตาราง Top 20 แบบละเอียด: ราคาสด + การเปลี่ยนแปลง 1 ชม./4 ชม./24 ชม./7 วัน/30 วัน + ช่วงราคา 24 ชม. + EMA200/RSI/แนวโน้ม/คะแนน
// สร้างตารางครั้งเดียว แล้วแก้เฉพาะช่องที่ค่าเปลี่ยน (ไม่สร้างใหม่ทุกวินาที — เบาเครื่อง)
(function () {
  const $ = (s) => document.querySelector(s);
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const pct = (v, d = 2) => v == null || isNaN(v) ? '—' : (v > 0 ? '+' : '') + v.toFixed(d) + '%';
  const cls = (v) => v == null || isNaN(v) ? 'flat' : v > 0 ? 'pos' : v < 0 ? 'neg' : 'flat';
  const WIN = {};   // symbol -> {'1h': open, '4h': open, '7d': open}
  let winAt = 0, rowsEl = null, built = '';
  const CELLS = {}; // symbol -> {td..}
  const LAST = {};  // symbol -> last price shown (for flash)

  async function fetchWindows(syms) {
    const q = encodeURIComponent(JSON.stringify(syms.map((s) => s + 'USDT')));
    for (const w of ['1h', '4h', '1d', '7d']) {
      try { const r = await fetch(`https://data-api.binance.vision/api/v3/ticker?type=MINI&windowSize=${w}&symbols=${q}`, {cache: 'no-store'});
        if (!r.ok) continue; for (const x of await r.json()) { const s = x.symbol.slice(0, -4), o = WIN[s] || (WIN[s] = {}); o[w] = +x.openPrice; if (w === '1d') { o.hi = +x.highPrice; o.lo = +x.lowPrice; } } } catch (e) { /* retry next minute */ }
    }
    winAt = Date.now();
  }
  function set(td, text, c) { if (td.textContent !== text) td.textContent = text; const k = td.dataset.base + ' ' + (c || ''); if (td.className !== k.trim()) td.className = k.trim(); }

  function build(D) {
    rowsEl.replaceChildren();
    for (const r of D.market) {
      const tr = mk('tr'); const c = {};
      const name = mk('td', 'stick'); const b = mk('b', null, r.symbol); b.title = 'เปิดกราฟ ' + r.symbol; b.onclick = () => openChart(r.symbol); name.append(b); tr.append(name);
      const sp = mk('td'); c.spark = sp; tr.append(sp);
      for (const k of ['px', 'h1', 'h4', 'h24', 'd7', 'd30']) { const td = mk('td', 'num'); td.dataset.base = 'num'; c[k] = td; tr.append(td); }
      const rg = mk('td'); const rw = mk('div', 'rngw'); const bar = mk('div', 'rng'); const dot = mk('i'); bar.append(dot); const lbl = mk('small'); rw.append(bar, lbl); rg.append(rw); c.dot = dot; c.rlbl = lbl; tr.append(rg);
      for (const k of ['vol', 'ema', 'rsi']) { const td = mk('td', 'num'); td.dataset.base = 'num'; c[k] = td; tr.append(td); }
      const trd = mk('td'); c.trend = trd; tr.append(trd);
      const sc = mk('td', 'num'); sc.dataset.base = 'num'; c.score = sc; tr.append(sc);
      CELLS[r.symbol] = c; rowsEl.append(tr);
    }
  }
  function spark(td, arr, live) {
    if (!arr || arr.length < 2) { if (td.textContent !== '—') td.textContent = '—'; return; }
    const a = arr.slice(); if (live) a[a.length - 1] = live;
    const lo = Math.min(...a), hi = Math.max(...a), k = hi - lo || 1, W = 90, H = 24;
    const pts = a.map((v, i) => `${(i / (a.length - 1) * W).toFixed(1)},${(H - 2 - (v - lo) / k * (H - 4)).toFixed(1)}`).join(' ');
    let svg = td.firstChild;
    if (!svg || svg.nodeName !== 'svg') { td.textContent = ''; svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg'); svg.setAttribute('width', W); svg.setAttribute('height', H);
      const pl = document.createElementNS('http://www.w3.org/2000/svg', 'polyline'); pl.setAttribute('fill', 'none'); pl.setAttribute('stroke-width', '1.3'); svg.append(pl); td.append(svg); }
    const pl = svg.firstChild; if (pl.getAttribute('points') !== pts) { pl.setAttribute('points', pts); pl.setAttribute('stroke', a[a.length - 1] >= a[0] ? '#22c983' : '#f0525b'); }
  }
  function openChart(sym) {
    const s = document.getElementById('chart-sym'); if (!s) return;
    if (![...s.options].some((o) => o.value === sym)) s.append(new Option(sym + '/USDT', sym));
    s.value = sym; s.dispatchEvent(new Event('change', {bubbles: true}));
    const box = document.querySelector('[data-draw="candles"]'); if (box) box.scrollIntoView({behavior: 'smooth', block: 'center'});
  }

  function tick() {
    if (document.hidden) return;
    const v = $('#view-overview'); if (!v || v.hidden) return;
    const D = window.CL && window.CL.data(); if (!D || !D.market) return;
    rowsEl = rowsEl || $('#mkt-rows'); if (!rowsEl) return;
    const key = D.market.map((r) => r.symbol).join(); if (key !== built) { built = key; build(D); }
    if (Date.now() - winAt > 60000) { winAt = Date.now(); fetchWindows(D.market.map((r) => r.symbol)); }
    const SR = new Map((((D.scanner || {}).rows) || []).map((r) => [r.symbol, r]));
    const fmt = window.CL.fmt, now = Date.now();
    for (const r of D.market) {
      const c = CELLS[r.symbol]; if (!c) continue;
      const p = r.last, s = SR.get(r.symbol) || {}, w = WIN[r.symbol] || {}, k = s.price ? p / s.price : 1;
      const fl = LAST[r.symbol] != null && p !== LAST[r.symbol] ? (p > LAST[r.symbol] ? 'fu' : 'fd') : (c.px.dataset.until > now ? c.px.dataset.fl : '');
      if (LAST[r.symbol] != null && p !== LAST[r.symbol]) { c.px.dataset.until = now + 700; c.px.dataset.fl = fl; }
      LAST[r.symbol] = p;
      set(c.px, fmt.px(p), fl);
      const ch = (o) => o ? (p / o - 1) * 100 : null;
      set(c.h1, pct(ch(w['1h'])), cls(ch(w['1h']))); set(c.h4, pct(ch(w['4h'])), cls(ch(w['4h'])));
      set(c.h24, pct(r.change_24h_pct), cls(r.change_24h_pct)); set(c.d7, pct(ch(w['7d']), 1), cls(ch(w['7d'])));
      const m30 = s.mom_30d_pct == null ? null : ((1 + s.mom_30d_pct / 100) * k - 1) * 100; set(c.d30, pct(m30, 1), cls(m30));
      const hi = Math.max(r.high24 || w.hi || 0, p), lo = Math.min(r.low24 || w.lo || Infinity, p);
      if (hi && lo < Infinity) { const f = Math.max(0, Math.min(1, (p - lo) / ((hi - lo) || 1)));
        c.dot.style.left = (f * 100).toFixed(1) + '%'; const t = `${fmt.px(lo)} → ${fmt.px(hi)} · อยู่ที่ ${Math.round(f * 100)}%`; if (c.rlbl.textContent !== t) c.rlbl.textContent = t; }
      else if (c.rlbl.textContent !== 'รอข้อมูลสด…') c.rlbl.textContent = 'รอข้อมูลสด…';
      set(c.vol, fmt.big(r.quote_volume_24h));
      const ema = s.vs_ema200_pct == null ? null : ((1 + s.vs_ema200_pct / 100) * k - 1) * 100; set(c.ema, pct(ema, 1), cls(ema));
      set(c.rsi, s.rsi14 == null ? '—' : Number(s.rsi14).toFixed(0), s.rsi14 > 70 || s.rsi14 < 30 ? 'hot' : '');
      const st = {buy_signal: ['มีสัญญาณซื้อ', 'up'], uptrend: ['ขาขึ้น', 'up'], downtrend: ['ขาลง', 'down'], illiquid: ['สภาพคล่องต่ำ', ''], new: ['ข้อมูลน้อย', '']}[s.status] || ['—', ''];
      if (c.trend.textContent !== st[0]) { c.trend.replaceChildren(mk('span', 'tr ' + st[1], st[0])); }
      set(c.score, s.score == null ? '—' : String(s.score), s.score >= 70 ? 'pos' : s.score >= 50 ? 'hot' : 'flat');
      spark(c.spark, s.spark, p);
    }
    const n = $('#mkt-note'); if (n) { const t = winAt ? `ราคาสดทุกวินาที · ช่วงเวลา 1ชม./4ชม./7วัน อัปเดต ${Math.round((now - winAt) / 1000)} วิที่แล้ว` : 'ราคาสดทุกวินาที'; if (n.textContent !== t) n.textContent = t; }
  }
  setInterval(tick, 1000);
})();
