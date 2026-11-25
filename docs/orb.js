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


  // ---------- LIVE SCORING: ราคาทุกเหรียญจาก Binance (ทุกวินาที) → คำนวณคะแนนใหม่ทุก 2 วินาที ----------
  const LIVE = {};            // SYMBOLUSDT -> {c, o, q, t}
  let liveMode = 'off', liveMsgAt = 0, liveDirty = false, changes = 0;
  const prevScore = {}, flashUntil = {}, CHANGES = [];
  function onTickers(arr) {
    const now = Date.now();
    for (const t of arr) { if (!t.s || !t.s.endsWith('USDT')) continue; LIVE[t.s] = {c: +t.c, o: +t.o, q: +t.q, t: now}; }
    liveMsgAt = now; liveDirty = true;
  }
  function connectLive() {
    const hosts = ['wss://data-stream.binance.vision/ws/!miniTicker@arr', 'wss://stream.binance.com:443/ws/!miniTicker@arr', 'wss://stream.binance.com:9443/ws/!miniTicker@arr'];
    let attempt = 0;
    const open = () => {
      let ws; try { ws = new WebSocket(hosts[attempt % hosts.length]); } catch (e) { attempt++; setTimeout(open, 3000); return; }
      ws.onmessage = (ev) => { const d = JSON.parse(ev.data); if (Array.isArray(d)) { liveMode = 'ws'; onTickers(d); } };
      ws.onclose = () => { attempt++; setTimeout(open, Math.min(20000, 2000 * attempt)); };
      ws.onerror = () => ws.close();
    };
    open();
    setInterval(async () => {   // REST fallback when the WebSocket is blocked
      if (document.hidden || (liveMode === 'ws' && Date.now() - liveMsgAt < 6000)) return;
      for (const h of ['https://data-api.binance.vision', 'https://api.binance.com']) {
        try { const r = await fetch(h + '/api/v3/ticker/24hr?type=MINI', {cache: 'no-store'}); if (!r.ok) continue;
          const j = await r.json(); onTickers(j.map((x) => ({s: x.symbol, c: x.lastPrice, o: x.openPrice, q: x.quoteVolume}))); liveMode = 'poll'; return; } catch (e) { /* next */ }
      }
    }, 5000);
  }
  const clamp01 = (v) => Math.max(0, Math.min(1, v));
  function comp(C, k, x) { const c = C[k]; if (x == null || isNaN(x)) return 0; return Math.round(10 * c.weight * clamp01((c.zero - x) / (c.zero - c.full))) / 10; }
  function liveRows(S) {
    const C = S.orb.components, btc = LIVE.BTCUSDT, btcRow = S.rows.find((r) => r.symbol === 'BTC');
    let btcUp = S.analysis ? S.analysis.regime !== 'bear' && (S.analysis.btc_vs_ema200_pct || 0) > 0 : false;
    if (btc && S.analysis && S.analysis.btc_ema200) btcUp = btc.c > S.analysis.btc_ema200;
    return S.rows.filter((r) => r.score != null).map((r) => {
      const L = LIVE[r.symbol + 'USDT']; if (!L || !r.price) return r;
      const p = L.c, k = p / r.price;
      const vs = r.vs_ema200_pct == null ? null : ((1 + r.vs_ema200_pct / 100) * k - 1) * 100;
      const mom = r.mom_30d_pct == null ? null : ((1 + r.mom_30d_pct / 100) * k - 1) * 100;
      const entry = r.entry_dist_pct == null ? null : ((1 + r.entry_dist_pct / 100) / k - 1) * 100;
      const atrp = r.atr_pct == null ? null : r.atr_pct / k;
      const qv = L.q || r.quote_volume_24h;
      const comps = {trend: comp(C, 'trend', vs), momentum: comp(C, 'momentum', mom), liquidity: comp(C, 'liquidity', qv > 0 ? Math.log10(qv) : null),
                     volatility: comp(C, 'volatility', atrp), entry: comp(C, 'entry', entry)};
      const raw = Math.round(Object.values(comps).reduce((a, b) => a + b, 0));
      const caps = [];
      if (qv < (S.min_liquid_usdt || 2e6)) caps.push('illiquid');
      if (vs == null) caps.push('no_data'); else if (vs < 0) caps.push('below_ema200');
      if (!btcUp) caps.push('btc_down');
      const score = caps.length ? Math.min(raw, 59) : raw;
      return Object.assign({}, r, {price: p, change_24h_pct: L.o ? (p / L.o - 1) * 100 : r.change_24h_pct, quote_volume_24h: qv,
        vs_ema200_pct: vs == null ? null : +vs.toFixed(1), mom_30d_pct: mom == null ? null : +mom.toFixed(1),
        entry_dist_pct: entry == null ? null : +entry.toFixed(2), components: comps, raw_score: raw, score, caps, live: true});
    });
  }
  function liveStatus() {
    const el = document.getElementById('orb-live'); if (!el) return;
    const age = liveMsgAt ? Math.round((Date.now() - liveMsgAt) / 1000) : null;
    const on = age != null && age <= 8;
    el.className = 'orb-live ' + (on ? 'on' : '');
    el.textContent = on ? `● LIVE SCORING ${liveMode === 'ws' ? '' : '(สำรอง) '}· ${Object.keys(LIVE).length} เหรียญ · คะแนนเปลี่ยน ${changes} ครั้ง` : '○ กำลังเชื่อมต่อราคาทุกเหรียญ…';
  }

  function rowsOf(S) { return liveRows(S); }
  function ranked(S) { return rowsOf(S).slice().sort((a, b) => b.score - a.score || b.raw_score - a.raw_score); }

  function header(S, rows) {
    const el = $('#orb-head'); el.replaceChildren();
    const liquid = rows.filter((r) => r.status !== 'illiquid');
    const hi = rows.filter((r) => r.score >= 70).length, capped = rows.filter((r) => r.caps.length).length;
    const A = S.analysis || {};
    const items = [['สแกน', rows.length], ['มีสภาพคล่อง', liquid.length], ['คะแนน ≥ 70', hi], ['ถูก cap', capped],
      ['ตลาด', A.regime_th || '—'], ['แท่ง', window.CL ? window.CL.fmt.time(S.bar) : S.bar]];
    const sc = liquid.map((r) => r.score).sort((a, b) => a - b), n = sc.length;
    const med = n ? (n % 2 ? sc[(n - 1) / 2] : (sc[n / 2 - 1] + sc[n / 2]) / 2) : 0, avg = n ? sc.reduce((a, b) => a + b, 0) / n : 0;
    const upN = liquid.filter((r) => (r.vs_ema200_pct ?? -1) > 0).length, now = Date.now();
    const cpm = CHANGES.filter((c) => now - c.t < 60000).length;
    items.splice(4, 0, ['คะแนนเฉลี่ย', avg.toFixed(1)], ['มัธยฐาน', med], ['% ขาขึ้น', (n ? Math.round(upN / n * 100) : 0) + '%'],
      ['คะแนนเปลี่ยน/นาที', cpm], ['กระแสประสาท/วิ', NET.ips || 0]);
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

  // ================= NEURAL MAP (canvas) =================
  // neuron = เหรียญ (ใกล้แกนกลาง/สว่าง = คะแนนสูง, มุม = ความสัมพันธ์กับ BTC) · synapse = เพื่อนบ้านใกล้กัน
  // impulse = กระแสประสาท: ยิงเมื่อคะแนนของเหรียญเปลี่ยนจากราคาสด แล้วแผ่ไปยังเพื่อนบ้าน (+ สัญญาณพื้นหลังเบาๆ)
  const NET = {nodes: new Map(), edges: [], nbr: new Map(), pulses: [], key: '', canvas: null, ctx: null, W: 0, H: 0, dpr: 1, hover: null, running: false};
  const reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const hash = (s, k) => { let h = 2166136261 ^ k; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return ((h >>> 0) % 10000) / 10000; };
  const DK = ['trend', 'momentum', 'liquidity', 'volatility', 'entry'], DCOL = ['51,195,180', '242,169,59', '120,170,255', '200,130,255', '255,120,160'];
  const NCOL = {buy_signal: [34, 201, 131], uptrend: [51, 195, 180], downtrend: [240, 82, 91], illiquid: [70, 84, 100], new: [242, 169, 59]};

  function ensureCanvas() {
    const host = $('#orb-graph'); if (!host) return false;
    if (!NET.canvas || !host.contains(NET.canvas)) {
      host.replaceChildren();
      NET.canvas = document.createElement('canvas'); NET.canvas.className = 'orb-canvas';
      NET.canvas.setAttribute('role', 'img'); NET.canvas.setAttribute('aria-label', 'แผนที่ประสาท: เหรียญเป็นเซลล์ประสาท ใกล้แกนกลาง = คะแนนสูง จุดวิ่ง = คะแนนเปลี่ยนจากราคาสด');
      host.append(NET.canvas); NET.ctx = NET.canvas.getContext('2d');
      if ('IntersectionObserver' in window) new IntersectionObserver((es) => { NET.offscreen = !es[0].isIntersecting; }).observe(NET.canvas);
      NET.canvas.addEventListener('mousemove', (e) => { const n = hit(e); NET.hover = n; NET.canvas.style.cursor = n ? 'pointer' : 'default'; });
      NET.canvas.addEventListener('mouseleave', () => { NET.hover = null; });
      NET.canvas.addEventListener('click', (e) => { const n = hit(e); if (n) { fire(n, 3); select(n.row); } });
    }
    const w = Math.min(760, host.clientWidth || 600), h = Math.round(w * 0.78);
    if (w !== NET.W) { NET.W = w; NET.H = h; NET.dpr = Math.min(1.5, window.devicePixelRatio || 1);
      NET.canvas.width = w * NET.dpr; NET.canvas.height = h * NET.dpr; NET.canvas.style.width = w + 'px'; NET.canvas.style.height = h + 'px'; NET.key = ''; }
    return true;
  }
  function hit(e) {
    const rc = NET.canvas.getBoundingClientRect(), x = e.clientX - rc.left, y = e.clientY - rc.top; let best = null, bd = 196;
    for (const n of NET.nodes.values()) { const d = (n.x - x) ** 2 + (n.y - y) ** 2; if (d < bd) { bd = d; best = n; } }
    return best;
  }
  function target(r, i, n, rankPct) {
    const W = NET.W, C = W / 2, CY = NET.H / 2;
    if (r.symbol === 'BTC') return [C, CY];
    const ang = (i / n) * Math.PI * 2 - Math.PI / 2 + (hash(r.symbol, 1) - 0.5) * 0.35;
    let rad = W * (0.05 + 0.29 * Math.sqrt(rankPct));          // rank → even, dense fill (closer = higher rank)
    rad *= 1 + (hash(r.symbol, 2) - 0.5) * 0.18;
    const lobe = 1 + 0.08 * Math.cos(2 * ang) + 0.05 * Math.sin(3 * ang + 0.6) + 0.03 * Math.cos(5 * ang);
    const cx = Math.cos(ang), side = cx >= 0 ? 1 : -1;            // two hemispheres with a central fissure
    const x = C + cx * rad * lobe * 1.22 + side * W * 0.016, y = CY + Math.sin(ang) * rad * lobe * 0.98;
    return [Math.max(10, Math.min(W - 10, x)), Math.max(10, Math.min(NET.H - 10, y))];
  }
  function graph(S, rows) {
    if (!ensureCanvas()) return;
    const pts = rows.slice().sort((a, b) => (b.corr_btc ?? -1) - (a.corr_btc ?? -1)), n = pts.length || 1;
    const rank = new Map(rows.slice().sort((a, b) => b.raw_score - a.raw_score || b.score - a.score).map((r, i) => [r.symbol, i / Math.max(1, rows.length - 1)]));
    const seen = new Set();
    pts.forEach((r, i) => {
      const [tx, ty] = target(r, i, n, rank.get(r.symbol)); seen.add(r.symbol);
      let node = NET.nodes.get(r.symbol);
      if (!node) { node = {sym: r.symbol, x: tx, y: ty, flash: 0}; NET.nodes.set(r.symbol, node); }
      if (node.raw != null && node.raw !== r.raw_score) fire(node, 2);
      Object.assign(node, {tx, ty, row: r, raw: r.raw_score, score: r.score, status: r.status, corr: r.corr_btc});
    });
    for (const k of [...NET.nodes.keys()]) if (!seen.has(k)) NET.nodes.delete(k);
    const key = [...seen].sort().join(',') + '|' + NET.W;
    if (key !== NET.key) { NET.key = key; buildEdges(); }
    if (!NET.running) { NET.running = true; requestAnimationFrame(frame); }
  }
  function buildEdges() {
    const ns = [...NET.nodes.values()], edges = [], nbr = new Map(), seenE = new Set();
    ns.forEach((a) => nbr.set(a.sym, []));
    const add = (a, b, hub) => { const k = a.sym < b.sym ? a.sym + '|' + b.sym : b.sym + '|' + a.sym; if (seenE.has(k)) return; seenE.add(k);
      const e = {a, b, hub, bend: (hash(k, 3) - 0.5) * 0.5}; edges.push(e); nbr.get(a.sym).push(e); nbr.get(b.sym).push(e); };
    for (const a of ns) {
      const k = a.status === 'illiquid' ? 3 : 5;
      const near = ns.filter((b) => b !== a).map((b) => [b, (b.tx - a.tx) ** 2 + (b.ty - a.ty) ** 2]).sort((x, y) => x[1] - y[1]).slice(0, k);
      near.forEach(([b]) => add(a, b, false));
    }
    // long-range association fibres (brain-like cross connections)
    for (let i = 0; i < ns.length; i += 3) { const a = ns[i], b = ns[Math.floor(hash(a.sym, 7) * ns.length)]; if (b && b !== a) add(a, b, false); }
    const btc = NET.nodes.get('BTC');
    if (btc) ns.filter((b) => b !== btc && b.status !== 'illiquid').sort((x, y) => (y.corr ?? 0) - (x.corr ?? 0)).slice(0, 26).forEach((b) => add(btc, b, true));
    NET.edges = edges; NET.nbr = nbr;
  }
  function fire(node, hops) {
    node.flash = 1;
    if (reduceMotion) return;
    for (const e of (NET.nbr.get(node.sym) || [])) if (Math.random() < 0.6 && NET.pulses.length < 260) NET.pulses.push({e, from: node, t: 0, sp: 0.012 + Math.random() * 0.02, hops: hops - 1, hot: true});
  }
  function bez(e, from, t) {
    const a = from === e.a ? e.a : e.b, b = from === e.a ? e.b : e.a;
    const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, dx = b.x - a.x, dy = b.y - a.y;
    const cx = mx - dy * e.bend, cy = my + dx * e.bend, u = 1 - t;
    return [u * u * a.x + 2 * u * t * cx + t * t * b.x, u * u * a.y + 2 * u * t * cy + t * t * b.y, b];
  }
  const SPR = {};
  function sprite(col) {
    const k = String(col); if (SPR[k]) return SPR[k];
    const cv = document.createElement('canvas'); cv.width = cv.height = 64; const g = cv.getContext('2d');
    const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32); gr.addColorStop(0, `rgba(${col},0.8)`); gr.addColorStop(1, `rgba(${col},0)`);
    g.fillStyle = gr; g.fillRect(0, 0, 64, 64); return (SPR[k] = cv);
  }
  function frame(ts) {
    const c = NET.ctx, W = NET.W, H = NET.H, dpr = NET.dpr;
    if (!c || !NET.canvas.isConnected) { NET.running = false; return; }
    requestAnimationFrame(frame);
    if (document.hidden || NET.offscreen || (NET.view || (NET.view = document.getElementById('view-scan'))).hidden) return;
    const minGap = W < 600 ? 48 : 32; if (ts - (NET.lastTs || 0) < minGap) return; NET.lastTs = ts;
    c.setTransform(dpr, 0, 0, dpr, 0, 0);
    c.clearRect(0, 0, W, H);
    const C = W / 2, CY = H / 2;
    const bg = c.createRadialGradient(C, CY, 0, C, CY, W * 0.55); bg.addColorStop(0, 'rgba(242,169,59,0.07)'); bg.addColorStop(0.5, 'rgba(51,195,180,0.025)'); bg.addColorStop(1, 'rgba(0,0,0,0)');
    c.fillStyle = bg; c.fillRect(0, 0, W, H);
    // rank guide rings (closer to BTC = higher rank)
    const nAll = Math.max(1, NET.nodes.size - 1);
    c.setLineDash([3, 5]); c.lineWidth = 1; c.font = '600 10px ui-monospace,monospace'; c.textAlign = 'left';
    for (const [k, label] of [[10, 'Top 10'], [50, 'Top 50'], [150, 'Top 150']]) {
      if (k >= nAll) continue;
      const rr = W * (0.05 + 0.29 * Math.sqrt(k / nAll));
      c.strokeStyle = 'rgba(150,170,190,0.22)'; c.beginPath(); c.ellipse(C, CY, rr * 1.22, rr * 0.98, 0, 0, 6.283); c.stroke();
      c.fillStyle = 'rgba(160,180,200,0.65)'; c.fillText(label, C + rr * 1.22 + 4, CY - 3);
    }
    c.setLineDash([]);
    // ease neurons toward their score position
    for (const n of NET.nodes.values()) { const k = reduceMotion ? 1 : 0.06; n.x += (n.tx - n.x) * k; n.y += (n.ty - n.y) * k; n.flash *= 0.94; }
    // synapses
    c.lineWidth = 0.6;
    const seg = (e) => { const a = e.a, b = e.b, mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2, dx = b.x - a.x, dy = b.y - a.y;
      c.moveTo(a.x, a.y); c.quadraticCurveTo(mx - dy * e.bend, my + dx * e.bend, b.x, b.y); };
    const hot = [];
    for (const [cls, col] of [[0, 'rgba(175,200,220,0.13)'], [1, 'rgba(130,150,170,0.08)'], [2, 'rgba(242,169,59,0.14)']]) {
      c.beginPath();
      for (const e of NET.edges) { const k = e.hub ? 2 : (e.a.status === 'illiquid' && e.b.status === 'illiquid') ? 1 : 0; if (k !== cls) continue;
        if (cls === 0 && Math.max(e.a.flash, e.b.flash) > 0.15) { hot.push(e); continue; } seg(e); }
      c.strokeStyle = col; c.stroke();
    }
    for (const e of hot) { c.strokeStyle = `rgba(200,225,245,${0.13 + Math.max(e.a.flash, e.b.flash) * 0.55})`; c.beginPath(); seg(e); c.stroke(); }
    // ambient firing (weighted toward high scores)
    if (!reduceMotion) for (let q = 0; q < 2; q++) if (Math.random() < 0.6) {
      if (!NET.pool || NET.poolAt !== NET.key + NET.nodes.size) { NET.pool = [...NET.nodes.values()].filter((x) => x.status !== 'illiquid'); NET.poolAt = NET.key + NET.nodes.size; }
      const pool = NET.pool, n = pool[Math.floor(Math.random() * pool.length)];
      if (n && Math.random() < 0.3 + (n.raw || 0) / 140) for (const e of (NET.nbr.get(n.sym) || []).slice(0, 2)) NET.pulses.push({e, from: n, t: 0, sp: 0.01 + Math.random() * 0.015, hops: 1, hot: false});
    }
    // impulses
    const next = [];
    c.globalCompositeOperation = 'lighter';
    for (const p of NET.pulses) {
      p.t += p.sp;
      if (p.t <= p.sp + 1e-9) NET.spawn = (NET.spawn || 0) + 1;
      for (let k = 0; k < 3; k++) {
        const tt = Math.max(0, p.t - k * 0.05), [x, y] = bez(p.e, p.from, Math.min(1, tt));
        const al = (p.hot ? 0.9 : 0.55) * (1 - k / 3);
        c.fillStyle = p.e.hub ? `rgba(255,196,90,${al})` : p.hot ? `rgba(255,220,140,${al})` : `rgba(140,230,255,${al})`;
        c.beginPath(); c.arc(x, y, k ? 1.4 : 2.4, 0, 6.283); c.fill();
      }
      if (p.t < 1) next.push(p);
      else { const [, , dest] = bez(p.e, p.from, 1); dest.flash = Math.max(dest.flash, p.hot ? 0.8 : 0.35);
        if (p.hops > 0) for (const e of (NET.nbr.get(dest.sym) || [])) if (e !== p.e && Math.random() < 0.3 && next.length < 260) next.push({e, from: dest, t: 0, sp: p.sp, hops: p.hops - 1, hot: p.hot}); }
    }
    if (!NET.ipsAt || ts - NET.ipsAt > 1000) { NET.ips = NET.spawn; NET.spawn = 0; NET.ipsAt = ts; }
    NET.pulses = next.slice(-260);
    // dendrites: 5 rays = 5 score components (length = component / weight)
    const CW = window.CL && window.CL.data().scanner && window.CL.data().scanner.orb ? window.CL.data().scanner.orb.components : null;
    if (CW) { c.lineWidth = 1.1; c.lineCap = 'round';
      DK.forEach((k, i) => { const w = CW[k] ? CW[k].weight : 20, ang = -Math.PI / 2 + i * 1.2566, ca = Math.cos(ang), sa = Math.sin(ang);
        c.beginPath();
        for (const n of NET.nodes.values()) { if (n.status === 'illiquid' || n.sym === 'BTC' || !n.row || !n.row.components) continue;
          const L = 3 + ((n.row.components[k] || 0) / w) * 11; c.moveTo(n.x + ca * 2.5, n.y + sa * 2.5); c.lineTo(n.x + ca * L, n.y + sa * L); }
        c.strokeStyle = `rgba(${DCOL[i]},0.7)`; c.stroke(); });
      c.lineCap = 'butt'; }
    // neurons
    const top = rowsTop();
    for (const n of NET.nodes.values()) {
      const col = NCOL[n.status] || [140, 150, 160], s = (n.raw || 0) / 100, ill = n.status === 'illiquid';
      const rad = ill ? 1.4 : 2.2 + s * 4.5, glow = ill ? 0 : 6 + s * 16 + n.flash * 18;
      if (glow) { c.globalAlpha = Math.min(1, 0.45 + n.flash * 0.6); c.drawImage(sprite(col), n.x - glow, n.y - glow, glow * 2, glow * 2); c.globalAlpha = 1; }
      c.fillStyle = n.flash > 0.3 ? `rgba(255,255,255,${0.6 + n.flash * 0.4})` : `rgba(${col},${ill ? 0.45 : 0.95})`;
      c.beginPath(); c.arc(n.x, n.y, rad, 0, 6.283); c.fill();
    }
    c.globalCompositeOperation = 'source-over';
    // BTC core
    const btc = NET.nodes.get('BTC');
    if (btc) { const pulse = reduceMotion ? 0 : (Math.sin(ts / 600) + 1) / 2;
      const g = c.createRadialGradient(btc.x, btc.y, 0, btc.x, btc.y, 30 + pulse * 8); g.addColorStop(0, 'rgba(242,169,59,0.55)'); g.addColorStop(1, 'rgba(242,169,59,0)');
      c.fillStyle = g; c.beginPath(); c.arc(btc.x, btc.y, 30 + pulse * 8, 0, 6.283); c.fill();
      c.fillStyle = '#0b1016'; c.strokeStyle = '#f2a93b'; c.lineWidth = 1.5; c.beginPath(); c.arc(btc.x, btc.y, 15, 0, 6.283); c.fill(); c.stroke();
      c.fillStyle = '#f2a93b'; c.font = '700 10px ui-monospace,monospace'; c.textAlign = 'center'; c.fillText('BTC', btc.x, btc.y + 3.5); }
    // labels: top coins, selection, hover
    c.font = '600 10px ui-monospace,monospace'; c.textAlign = 'left';
    const placed = [[C - 22, CY - 22, 44], [C - 22, CY - 7, 44], [C - 22, CY + 8, 44]];   // keep the BTC core clear
    const lab = (n, color) => {
      const txt = n.sym + ' ' + n.score, w = c.measureText(txt).width + 8; let lx = n.x + 8, ly = n.y - 8;
      if (lx + w > W - 2) lx = n.x - 8 - w;
      for (let tries = 0; tries < 8 && placed.some((b) => lx < b[0] + b[2] && lx + w > b[0] && ly < b[1] + 15 && ly + 15 > b[1]); tries++) ly += 15;
      placed.push([lx, ly, w]);
      c.strokeStyle = 'rgba(200,215,230,0.25)'; c.lineWidth = 0.6; c.beginPath(); c.moveTo(n.x, n.y); c.lineTo(lx, ly + 7); c.stroke();
      c.fillStyle = 'rgba(6,9,13,0.82)'; c.fillRect(lx, ly, w, 14); c.fillStyle = color; c.fillText(txt, lx + 4, ly + 10.5); };
    const sn = sel && NET.nodes.get(sel.symbol);
    c.font = '500 8.5px ui-monospace,monospace'; c.textAlign = 'center';
    for (const n of NET.nodes.values()) { if (n.status === 'illiquid' || n.sym === 'BTC' || top.includes(n.sym) || n === sn) continue;
      c.fillStyle = n.flash > 0.3 ? '#ffe2a0' : 'rgba(190,205,220,0.6)'; c.fillText(String(n.score), n.x, n.y + 15); }
    c.font = '600 10px ui-monospace,monospace'; c.textAlign = 'left';
    if (sn) lab(sn, '#f2a93b');
    for (const sym of top) { const n = NET.nodes.get(sym); if (n && n.sym !== 'BTC' && n !== sn) lab(n, '#cfd8e3'); }
    if (sn) { c.strokeStyle = '#f2a93b'; c.lineWidth = 1.5; c.beginPath(); c.arc(sn.x, sn.y, 9 + (reduceMotion ? 0 : Math.sin(ts / 250) * 2), 0, 6.283); c.stroke(); }
    if (NET.hover) {
      const r = NET.hover.row || {}, ST = {buy_signal: 'มีสัญญาณซื้อ', uptrend: 'ขาขึ้น', downtrend: 'ขาลง', illiquid: 'สภาพคล่องต่ำ', new: 'ข้อมูลไม่พอ'};
      const CAP = {btc_down: 'BTC ขาลง', below_ema200: 'อยู่ใต้ EMA200', illiquid: 'สภาพคล่องต่ำ', no_data: 'ข้อมูลไม่พอ'};
      const lines = [`${r.symbol}  คะแนน ${r.score}${r.caps && r.caps.length ? ` (ดิบ ${r.raw_score})` : ''}`, `สถานะ: ${ST[r.status] || r.status}`,
        `24 ชม. ${r.change_24h_pct == null ? '—' : (r.change_24h_pct > 0 ? '+' : '') + r.change_24h_pct.toFixed(2) + '%'} · เทียบ EMA200 ${r.vs_ema200_pct == null ? '—' : (r.vs_ema200_pct > 0 ? '+' : '') + r.vs_ema200_pct + '%'}`,
        r.caps && r.caps.length ? 'ถูกจำกัดคะแนนเพราะ: ' + r.caps.map((x) => CAP[x] || x).join(', ') : 'ไม่ถูกจำกัดคะแนน', 'แตะเพื่อดูรายละเอียด'];
      c.font = '12px ui-monospace,monospace'; const bw = Math.max(...lines.map((t) => c.measureText(t).width)) + 18, bh = lines.length * 17 + 12;
      let bx = NET.hover.x + 14, by = NET.hover.y + 14; if (bx + bw > W - 4) bx = NET.hover.x - 14 - bw; if (by + bh > H - 4) by = NET.hover.y - 14 - bh;
      c.fillStyle = 'rgba(8,12,17,0.94)'; c.strokeStyle = 'rgba(242,169,59,0.6)'; c.lineWidth = 1; c.fillRect(bx, by, bw, bh); c.strokeRect(bx, by, bw, bh);
      lines.forEach((t, i) => { c.fillStyle = i === 0 ? '#f2a93b' : i === lines.length - 1 ? '#6b7a8a' : '#cfd8e3'; c.fillText(t, bx + 9, by + 20 + i * 17); });
    }
  }
  let topCache = [], topAt = 0;
  function rowsTop() { if (Date.now() - topAt > 2000) { topAt = Date.now(); topCache = [...NET.nodes.values()].filter((n) => n.status !== 'illiquid').sort((a, b) => b.score - a.score || b.raw - a.raw).slice(0, 12).map((n) => n.sym); } return topCache; }
  window.addEventListener('resize', () => { if (NET.canvas) { ensureCanvas(); } });

  function registry(S, rows) {
    const el = $('#orb-reg'); const oldList = el.querySelector('.or-list'); const keepScroll = oldList ? oldList.scrollTop : 0; el.replaceChildren();
    const r0 = sel || rows[0];
    if (r0) {
      const card = mk('div', 'or-card ' + scoreCls(r0.score));
      const top = mk('div', 'or-top'); top.append(mk('b', null, r0.symbol), mk('span', 'or-score', String(r0.score)));
      const bar = mk('div', 'or-bar'); const fill = mk('i'); fill.style.width = r0.score + '%'; bar.append(fill);
      card.append(top, bar);
      if (r0.caps.length) card.append(mk('div', 'or-cap', `CAP ≤59 · raw ${r0.raw_score}`));
      card.append(Object.assign(mk('div', 'or-auto'), {id: 'orb-auto'}));
      const V = window.CL && window.CL.data().orb_validation;
      const hb = V && V.horizons['30d'] && V.horizons['30d'].buckets.find((b) => b.bucket === bucketOf(r0.score));
      if (hb && hb.mean_pct != null) card.append(mk('div', 'or-hist', `ในอดีต เหรียญคะแนน ${hb.bucket} ให้ผลตอบแทน 30 วันถัดไปเฉลี่ย ${hb.mean_pct > 0 ? '+' : ''}${hb.mean_pct}% (ชนะ ${hb.win_rate_pct}%)`));
      el.append(card);
    }
    const list = mk('div', 'or-list');
    rows.filter((r) => showIlliquid || r.status !== 'illiquid').slice(0, 60).forEach((r) => {
      const it = mk('button', 'or-row' + (sel && sel.symbol === r.symbol ? ' on' : '') + ((flashUntil[r.symbol] || 0) > Date.now() ? ' flash' : '')); it.type = 'button';
      const b = mk('span', 'or-mini'); const f = mk('i', scoreCls(r.score)); f.style.width = r.score + '%'; b.append(f);
      it.append(mk('span', 'or-sym', r.symbol), b, mk('span', 'or-n ' + scoreCls(r.score), String(r.score)));
      it.onclick = () => select(r); list.append(it);
    });
    el.append(list); list.scrollTop = keepScroll;
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

  const bucketOf = (v) => v >= 80 ? '80–100' : v >= 60 ? '60–79' : v >= 40 ? '40–59' : '0–39';
  function validation(V) {
    const el = $('#orb-valid'); el.replaceChildren();
    if (!V) { el.append(mk('div', 'empty', 'ยังไม่มีผลทดสอบย้อนหลังของคะแนน (Judge จะสร้างคืนนี้)')); return; }
    const h = mk('div', 'ov-head');
    h.append(mk('b', null, 'คะแนนนี้ได้ผลจริงไหม? ทดสอบย้อนหลัง'), mk('span', 'oh-i', `${V.weeks} สัปดาห์ · ${V.samples.toLocaleString()} ตัวอย่าง · ${V.period[0]} → ${V.period[1]} · หักต้นทุน ${(V.cost_roundtrip * 100).toFixed(1)}%`));
    el.append(h, mk('div', 'ov-verdict ' + V.verdict, V.verdict_th));
    const grid = mk('div', 'ov-grid');
    for (const [hk, label] of [['7d', 'ผลตอบแทน 7 วันถัดไป (เฉลี่ย)'], ['30d', 'ผลตอบแทน 30 วันถัดไป (เฉลี่ย)']]) {
      const hv = V.horizons[hk]; if (!hv) continue;
      const box = mk('div'); box.append(mk('div', 'ov-h', `${label} · IC ${hv.ic_mean} (บวก ${hv.ic_positive_weeks_pct}% ของสัปดาห์)`));
      const mx = Math.max(1, ...hv.buckets.map((b) => Math.abs(b.mean_pct || 0)));
      for (const b of hv.buckets) {
        const row = mk('div', 'ov-row'), tr = mk('div', 'ov-track'), bar = mk('i');
        const v = b.mean_pct || 0, w = Math.abs(v) / mx * 50;
        bar.style.left = (v >= 0 ? 50 : 50 - w) + '%'; bar.style.width = w + '%'; bar.style.background = v >= 0 ? 'var(--up)' : 'var(--down)';
        tr.append(bar);
        row.append(mk('span', null, b.bucket), tr, mk('b', v >= 0 ? 'pos' : 'neg', (v > 0 ? '+' : '') + v.toFixed(2) + '%'), mk('span', 'n', `ชนะ ${b.win_rate_pct}%`));
        box.append(row);
      }
      box.append(mk('div', 'ov-h', `ค่าเฉลี่ยทั้งตลาด ${hv.all_mean_pct > 0 ? '+' : ''}${hv.all_mean_pct}% · ช่วงทดสอบเป็นตลาดผสม/ขาลงสำหรับ altcoin ส่วนใหญ่`));
      grid.append(box);
    }
    el.append(grid);
  }

  let lastPick = 0, cycleI = 0;
  function select(r, auto) { sel = r; if (!auto) lastPick = Date.now(); draw(true); }
  setInterval(() => {
    const D = window.CL && window.CL.data(); const S = D && D.scanner; if (!S || !S.orb || document.hidden) return;
    if (Date.now() - lastPick < 20000) return;
    const top = ranked(S).filter((r) => r.status !== 'illiquid').slice(0, 8); if (!top.length) return;
    cycleI = (cycleI + 1) % top.length; select(top[cycleI], true);
    const a = document.getElementById('orb-auto'); if (a) a.textContent = `วนแสดงอัตโนมัติ ${cycleI + 1}/${top.length} · แตะเหรียญเพื่อหยุด 20 วินาที`;
  }, 5000);
  setInterval(() => { const c = document.getElementById('orb-clock'); if (c) c.textContent = new Date().toISOString().slice(11, 19) + ' UTC'; }, 1000);
  function tape(S, rows) {
    const el = document.getElementById('orb-tape'); if (!el) return; el.replaceChildren();
    const items = rows.filter((r) => r.status !== 'illiquid').slice(0, 30);
    for (let k = 0; k < 2; k++) for (const r of items) {
      const sp = mk('span'); sp.append(r.symbol, mk('b', (r.change_24h_pct || 0) >= 0 ? 'pos' : 'neg', fmtPct(r.change_24h_pct, 2)), mk('b', scoreCls(r.score), String(r.score)));
      el.append(sp); }
  }
  function draw(force) {
    const D = window.CL && window.CL.data(); const S = D && D.scanner;
    const root = $('#orb'); if (!root) return;
    if (!S || !S.orb) { root.hidden = true; return; }
    root.hidden = false;
    const key = S.generated_at + '|' + (sel && sel.symbol) + '|' + showIlliquid + '|' + (D.orb_validation ? D.orb_validation.generated_at : '');
    if (!force && key === lastKey) return; lastKey = key;
    const rows = ranked(S);
    const now = Date.now();
    for (const r of rows) { const pv = prevScore[r.symbol];
      if (pv != null && pv !== r.raw_score) { flashUntil[r.symbol] = now + 1800; changes++;
        if (r.status !== 'illiquid') { CHANGES.unshift({sym: r.symbol, from: pv, to: r.raw_score, final: r.score, t: now, chg: r.change_24h_pct}); CHANGES.length = Math.min(CHANGES.length, 400); } }
      prevScore[r.symbol] = r.raw_score; }
    if (sel) sel = rows.find((r) => r.symbol === sel.symbol) || null;
    if (!sel) sel = rows.find((r) => r.status !== 'illiquid') || rows[0];
    header(S, rows); checks(S, rows); graph(S, rows); registry(S, rows); detail(S); validation(D.orb_validation); insight(S, rows); heat(rows);
    if (!document.getElementById('orb-tape').childElementCount || force === 'tape') tape(S, rows);
  }
  document.addEventListener('change', (e) => { if (e.target && e.target.id === 'orb-illiquid') { showIlliquid = e.target.checked; draw(true); } });
  function insight(S, rows) {
    const el = document.getElementById('nm-insight'); if (!el) return;
    const liq = rows.filter((r) => r.status !== 'illiquid'), up = liq.filter((r) => (r.vs_ema200_pct ?? -1) > 0).length;
    const top = liq.slice(0, 5), capped = top.length && top.every((r) => r.caps.includes('btc_down'));
    el.replaceChildren();
    const sum = mk('div', 'nm-sum');
    const p1 = mk('p'); p1.append(mk('b', null, 'อ่านภาพนี้: '), 'จุดแต่ละจุดคือเหรียญ 1 ตัว ยิ่งอยู่ใกล้ BTC ตรงกลางและสว่าง = คะแนนยิ่งสูง (น่าสนใจกว่า) · สีเขียว = ขาขึ้น, สีแดง = ขาลง · จุดเรืองแสงที่วิ่งไปตามเส้น = คะแนนของเหรียญนั้นเพิ่งเปลี่ยนจากราคาสด');
    const p2 = mk('p'); p2.append(mk('b', null, 'ตอนนี้: '), `ใน ${liq.length} เหรียญที่ซื้อขายคล่อง มี ${up} ตัว (${liq.length ? Math.round(up / liq.length * 100) : 0}%) เป็นขาขึ้น · 5 อันดับแรก: ${top.map((r) => `${r.symbol} ${r.score}`).join(', ') || '—'}`);
    const p3 = mk('p', capped ? 'nm-warn' : 'nm-ok');
    p3.append(mk('b', null, 'แปลว่า: '), capped ? 'ทุกเหรียญถูกจำกัดคะแนนไว้ไม่เกิน 59 เพราะ BTC ยังเป็นขาลง — ระบบแนะนำให้ "เฝ้าดู" ยังไม่ใช่จังหวะซื้อ' : top.some((r) => r.score >= 70) ? 'มีเหรียญคะแนน 70+ — ดูแผนเทรดก่อนตัดสินใจ (ในอดีตคะแนนสูงมากอาจหมายถึงวิ่งไปไกลแล้ว)' : 'ยังไม่มีเหรียญคะแนนสูงพอ — เฝ้าดูต่อ');
    sum.append(p1, p2, p3);
    const feed = mk('div', 'nm-feed'); feed.append(mk('div', 'op-t', 'คะแนนดิบเปลี่ยนล่าสุด (ก่อนจำกัด 59 · จากราคาสด) · แตะเพื่อดูเหรียญ'));
    const list = mk('div', 'nm-chips');
    if (!CHANGES.length) list.append(mk('span', 'nm-chip', 'รอราคาสด…'));
    for (const ch of CHANGES.slice(0, 12)) {
      const upc = ch.to > ch.from, chip = mk('button', 'nm-chip ' + (upc ? 'up' : 'down')); chip.type = 'button';
      chip.textContent = `${ch.sym} ${ch.from}→${ch.to} ${upc ? '▲' : '▼'} · ${Math.max(0, Math.round((Date.now() - ch.t) / 1000))} วิ`;
      chip.onclick = () => { const r = rows.find((x) => x.symbol === ch.sym); if (r) select(r); }; list.append(chip);
    }
    feed.append(list); el.append(sum, feed);
  }

  function heat(rows) {
    const el = document.getElementById('nm-heat'); if (!el) return;
    const liq = (r) => r.status === 'illiquid' ? 1 : 0, all = [...rows].sort((a, b) => liq(a) - liq(b) || b.score - a.score || b.raw_score - a.raw_score);
    const cells = el.querySelectorAll('.hm-c');
    if (cells.length !== all.length) { el.replaceChildren(); all.forEach(() => { const b = mk('button', 'hm-c'); b.type = 'button'; el.append(b); }); }
    const now = Date.now(), list = el.querySelectorAll('.hm-c');
    all.forEach((r, i) => { const b = list[i], ill = r.status === 'illiquid', s = r.score;
      const hue = s >= 70 ? 150 : s >= 50 ? 170 - (70 - s) * 2 : s >= 30 ? 40 : 355;
      b.style.background = ill ? '#1a222b' : `hsl(${hue} ${45 + s / 3}% ${14 + s * 0.38}%)`;
      b.className = 'hm-c' + ((flashUntil[r.symbol] || 0) > now ? ' fl' : '') + (sel && sel.symbol === r.symbol ? ' on' : '');
      b.textContent = r.symbol.slice(0, 4); if (ill) b.style.color = '#4a5866';
      b.title = `${r.symbol} · คะแนน ${s}${r.caps.length ? ' (ดิบ ' + r.raw_score + ')' : ''} · 24ชม. ${r.change_24h_pct == null ? '—' : r.change_24h_pct.toFixed(2) + '%'}`;
      b.onclick = () => select(r); });
    const cap = document.getElementById('nm-heat-cap');
    if (cap) cap.textContent = `ทั้งกระดาน ${all.length} เหรียญ · เหรียญซื้อขายคล่องก่อน เรียงคะแนนสูง→ต่ำ (ซ้ายบน→ขวาล่าง) แล้วตามด้วยสภาพคล่องต่ำ · ยิ่งเขียวสว่าง = คะแนนสูง · กะพริบ = คะแนนเพิ่งเปลี่ยน · ช่องเทาเข้ม = สภาพคล่องต่ำ`;
  }

  window.CLOrb = {render: () => draw(false)};
  setInterval(() => { liveStatus(); if (liveDirty && !document.hidden && !document.getElementById('view-scan').hidden) { liveDirty = false; draw(true); } }, 2000);
  setTimeout(connectLive, 1500);
  setInterval(() => draw(false), 3000);
})();
