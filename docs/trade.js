// Crypto Lab — เทรดจากหน้า dashboard
// - คีย์ Binance ถูกเข้ารหัส (AES-GCM, PBKDF2 310,000 รอบ) และเก็บเฉพาะในเบราว์เซอร์นี้ ไม่ถูกส่งไปที่ไหนนอกจาก Binance
// - ส่งคำสั่งผ่าน Binance WebSocket API (REST ใช้จากเบราว์เซอร์ไม่ได้เพราะ CORS)
// - เริ่มที่ Testnet (เงินปลอม) เสมอ; เงินจริงต้องพิมพ์ยืนยันทุกออเดอร์
(function () {
  const NETS = {
    testnet: {label: 'TESTNET (เงินทดลอง)', ws: 'wss://ws-api.testnet.binance.vision/ws-api/v3', keysUrl: 'https://testnet.binance.vision/'},
    live: {label: 'BINANCE (เงินจริง)', ws: 'wss://ws-api.binance.com:443/ws-api/v3', keysUrl: 'https://www.binance.com/en/my/settings/api-management'},
  };
  const STORE = 'cl.keys.v1', SETTINGS = 'cl.trade.settings.v1';
  const enc = new TextEncoder(), dec = new TextDecoder();
  const b64 = (u8) => btoa(String.fromCharCode(...new Uint8Array(u8)));
  const unb64 = (s) => Uint8Array.from(atob(s), (c) => c.charCodeAt(0));
  const hex = (buf) => Array.from(new Uint8Array(buf)).map((b) => b.toString(16).padStart(2, '0')).join('');
  const ls = {get: (k) => { try { return localStorage.getItem(k); } catch (e) { return null; } },
              set: (k, v) => { try { localStorage.setItem(k, v); return true; } catch (e) { return false; } },
              del: (k) => { try { localStorage.removeItem(k); } catch (e) { /* ignore */ } }};

  // ---------- crypto ----------
  async function deriveKey(pass, salt) {
    const base = await crypto.subtle.importKey('raw', enc.encode(pass), 'PBKDF2', false, ['deriveKey']);
    return crypto.subtle.deriveKey({name: 'PBKDF2', salt, iterations: 310000, hash: 'SHA-256'}, base, {name: 'AES-GCM', length: 256}, false, ['encrypt', 'decrypt']);
  }
  async function sealKeys(obj, pass) {
    const salt = crypto.getRandomValues(new Uint8Array(16)), iv = crypto.getRandomValues(new Uint8Array(12));
    const ct = await crypto.subtle.encrypt({name: 'AES-GCM', iv}, await deriveKey(pass, salt), enc.encode(JSON.stringify(obj)));
    return JSON.stringify({v: 1, net: obj.net, salt: b64(salt), iv: b64(iv), ct: b64(ct)});
  }
  async function openKeys(blob, pass) {
    const j = JSON.parse(blob);
    const pt = await crypto.subtle.decrypt({name: 'AES-GCM', iv: unb64(j.iv)}, await deriveKey(pass, unb64(j.salt)), unb64(j.ct));
    return JSON.parse(dec.decode(pt));
  }
  async function hmacHex(secret, payload) {
    const k = await crypto.subtle.importKey('raw', enc.encode(secret), {name: 'HMAC', hash: 'SHA-256'}, false, ['sign']);
    return hex(await crypto.subtle.sign('HMAC', k, enc.encode(payload)));
  }
  // WebSocket API: signature payload = all params except signature, sorted by name, joined as k=v&k=v
  const signPayload = (params) => Object.keys(params).filter((k) => k !== 'signature').sort().map((k) => `${k}=${params[k]}`).join('&');

  // ---------- session ----------
  let session = null;   // {net, apiKey, secret} — memory only
  let ws = null, wsReady = null, reqId = 0;
  const pending = new Map();
  let idleTimer = null;
  const IDLE_MS = 30 * 60 * 1000;
  function touch() { clearTimeout(idleTimer); if (session) idleTimer = setTimeout(() => { logout('ล็อกอัตโนมัติหลังไม่ได้ใช้งาน 30 นาที'); }, IDLE_MS); }
  ['click', 'keydown'].forEach((ev) => document.addEventListener(ev, touch, {passive: true}));

  function connectWs() {
    if (wsReady) return wsReady;
    wsReady = new Promise((resolve, reject) => {
      const s = new WebSocket(NETS[session.net].ws);
      const t = setTimeout(() => { reject(new Error('เชื่อมต่อ Binance ไม่ได้ (หมดเวลา) — เครือข่ายอาจบล็อก WebSocket')); s.close(); }, 10000);
      s.onopen = () => { clearTimeout(t); ws = s; resolve(s); };
      s.onmessage = (ev) => {
        const m = JSON.parse(ev.data), p = pending.get(m.id); if (!p) return; pending.delete(m.id);
        if (m.status === 200) p.resolve(m.result); else p.reject(new Error(binanceError(m.error)));
      };
      s.onclose = () => { ws = null; wsReady = null; for (const [, p] of pending) p.reject(new Error('การเชื่อมต่อหลุด')); pending.clear(); };
      s.onerror = () => { clearTimeout(t); reject(new Error('เชื่อมต่อ Binance ไม่ได้ — เครือข่ายอาจบล็อก WebSocket')); };
    });
    return wsReady;
  }
  function binanceError(e) {
    if (!e) return 'ไม่ทราบสาเหตุ';
    const th = {'-2015': 'API key ไม่ถูกต้อง, IP ไม่ได้รับอนุญาต หรือคีย์ไม่มีสิทธิ์เทรด', '-1022': 'ลายเซ็นไม่ถูกต้อง (Secret key ผิด)', '-2010': 'Binance ปฏิเสธออเดอร์ (ยอดเงินไม่พอหรือผิดเงื่อนไข)',
      '-1013': 'ขนาดหรือราคาไม่ตรงเงื่อนไขของเหรียญ (เล็กเกินไป/ทศนิยมไม่ถูก)', '-1021': 'เวลาเครื่องไม่ตรงกับ Binance — ตั้งเวลาอัตโนมัติในเครื่อง', '-2011': 'ยกเลิกไม่ได้ (ออเดอร์ไม่มีอยู่แล้ว)'};
    return (th[String(e.code)] ? th[String(e.code)] + ' — ' : '') + `${e.msg} (code ${e.code})`;
  }
  async function call(method, params = {}, signed = false) {
    if (!session) throw new Error('ยังไม่ได้เข้าสู่ระบบ');
    await connectWs();
    const p = Object.assign({}, params);
    if (signed) { p.apiKey = session.apiKey; p.timestamp = Date.now(); p.recvWindow = 10000; p.signature = await hmacHex(session.secret, signPayload(p)); }
    const id = 'cl' + (++reqId);
    return new Promise((resolve, reject) => {
      pending.set(id, {resolve, reject});
      ws.send(JSON.stringify({id, method, params: p}));
      setTimeout(() => { if (pending.has(id)) { pending.delete(id); reject(new Error('Binance ไม่ตอบกลับ (หมดเวลา)')); } }, 15000);
    });
  }

  // ---------- symbol rules (lot size, tick size, min notional) ----------
  const rules = {};
  async function symbolRules(symbol) {
    if (rules[symbol]) return rules[symbol];
    const r = await call('exchangeInfo', {symbol});
    const s = r.symbols[0], f = Object.fromEntries(s.filters.map((x) => [x.filterType, x]));
    const step = +(f.LOT_SIZE || {}).stepSize || 1e-8, tick = +(f.PRICE_FILTER || {}).tickSize || 1e-8;
    const minNotional = +((f.NOTIONAL || f.MIN_NOTIONAL || {}).minNotional || 5);
    rules[symbol] = {step, tick, minNotional, minQty: +(f.LOT_SIZE || {}).minQty || 0, base: s.baseAsset};
    return rules[symbol];
  }
  const decimals = (x) => { const s = String(x); if (s.includes('e-')) return +s.split('e-')[1]; const i = s.indexOf('.'); return i < 0 ? 0 : s.slice(i + 1).replace(/0+$/, '').length; };
  const floorTo = (v, step) => (Math.floor(v / step + 1e-9) * step).toFixed(decimals(step));
  const roundTo = (v, step) => (Math.round(v / step) * step).toFixed(decimals(step));

  // ---------- settings ----------
  const defaults = {maxOrderUsdt: 125, stopDefaultPct: 5};
  const settings = () => { try { return Object.assign({}, defaults, JSON.parse(ls.get(SETTINGS) || '{}')); } catch (e) { return defaults; } };

  // ---------- UI helpers ----------
  const $ = (sel) => document.querySelector(sel);
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const fmtN = (v, d = 2) => v == null || isNaN(v) ? '—' : Number(v).toLocaleString('en-US', {minimumFractionDigits: d, maximumFractionDigits: d});
  const fmtP = (v) => v == null || isNaN(v) ? '—' : (window.CL ? window.CL.fmt.px(v) : String(v));
  function log(msg, kind = 'info') {
    const box = $('#tr-log'); if (!box) return;
    const row = mk('div', 'ev ' + kind); const h = mk('div', 'h');
    h.append(mk('span', null, msg), mk('span', 't', new Date().toLocaleTimeString('th-TH'))); row.append(h); box.prepend(row);
    while (box.children.length > 30) box.lastChild.remove();
  }
  function openDialog(id) { const d = document.getElementById(id); if (d && !d.open) d.showModal(); }
  function closeDialog(id) { const d = document.getElementById(id); if (d && d.open) d.close(); }

  function renderAuth() {
    const btn = $('#auth-btn'), has = !!ls.get(STORE);
    if (session) { btn.textContent = '🔓 ' + (session.net === 'live' ? 'เงินจริง' : 'Testnet'); btn.className = 'authbtn ' + (session.net === 'live' ? 'live' : 'test'); }
    else { btn.textContent = has ? '🔒 ปลดล็อก' : 'เข้าสู่ระบบ'; btn.className = 'authbtn'; }
    document.querySelectorAll('[data-auth="in"]').forEach((e) => e.hidden = !session);
    document.querySelectorAll('[data-auth="out"]').forEach((e) => e.hidden = !!session);
    const st = $('#tr-status');
    if (st) st.textContent = session ? `เชื่อมต่อแล้ว: ${NETS[session.net].label}` : has ? 'มีคีย์ที่บันทึกไว้ในเบราว์เซอร์นี้ — ใส่รหัสผ่านเพื่อปลดล็อก' : 'ยังไม่ได้เชื่อมบัญชี Binance';
    $('#tr-netbadge') && ($('#tr-netbadge').textContent = session ? NETS[session.net].label : '');
    $('#tr-netbadge') && ($('#tr-netbadge').className = 'chip ' + (session && session.net === 'live' ? 'down' : 'paper'));
    const lf = $('#login-first'), lu = $('#login-unlock');
    if (lf && lu) { lf.hidden = has; lu.hidden = !has; }
  }

  async function login(ev) {
    ev.preventDefault();
    const f = ev.target, err = f.querySelector('.formerr'); err.textContent = '';
    try {
      if (ls.get(STORE)) {
        session = await openKeys(ls.get(STORE), f.pass_unlock.value).catch(() => { throw new Error('รหัสผ่านไม่ถูกต้อง'); });
      } else {
        const apiKey = f.api_key.value.trim(), secret = f.api_secret.value.trim(), pass = f.pass_new.value, net = f.net.value;
        if (apiKey.length < 20 || secret.length < 20) throw new Error('API key / Secret สั้นเกินไป — คัดลอกมาให้ครบ');
        if (pass.length < 8) throw new Error('รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร');
        if (pass !== f.pass_new2.value) throw new Error('รหัสผ่านสองช่องไม่ตรงกัน');
        if (net === 'live' && f.live_ack.value.trim() !== 'เงินจริง') throw new Error('พิมพ์คำว่า "เงินจริง" เพื่อยืนยันการใช้บัญชีจริง');
        session = {net, apiKey, secret};
        if (!ls.set(STORE, await sealKeys(session, pass))) log('เบราว์เซอร์ไม่อนุญาตให้บันทึก — ต้องใส่คีย์ใหม่ทุกครั้ง', 'warn');
      }
      f.reset(); closeDialog('dlg-login'); touch(); renderAuth();
      log('เข้าสู่ระบบแล้ว: ' + NETS[session.net].label, 'buy');
      if (window.CL) window.CL.showTab('trade');
      refreshAccount();
    } catch (e) { session = null; err.textContent = e.message; }
  }
  function logout(reason) {
    session = null; clearTimeout(idleTimer); if (ws) ws.close(); ws = null; wsReady = null;
    renderAuth(); renderBalances(null); renderOrders(null); if (reason) log(reason, 'warn');
  }
  function forget() {
    if (!confirmInline('ลบคีย์ที่บันทึกในเบราว์เซอร์นี้? (ต้องใส่ API key ใหม่ภายหลัง)')) return;
    ls.del(STORE); logout('ลบคีย์ออกจากเบราว์เซอร์แล้ว');
  }
  let confirmArm = 0;
  function confirmInline(msg) {   // window.confirm is unreliable in some views: press twice within 4 s
    if (Date.now() - confirmArm < 4000) { confirmArm = 0; return true; }
    confirmArm = Date.now(); log(msg + ' — กดปุ่มเดิมอีกครั้งภายใน 4 วินาทีเพื่อยืนยัน', 'warn'); return false;
  }

  // ---------- account ----------
  let balances = {};
  async function refreshAccount() {
    if (!session) return;
    try {
      const acct = await call('account.status', {omitZeroBalances: true}, true);
      balances = Object.fromEntries(acct.balances.map((b) => [b.asset, {free: +b.free, locked: +b.locked}]));
      if (!acct.canTrade) log('คีย์นี้ไม่มีสิทธิ์เทรด — เปิด "Enable Spot & Margin Trading" ที่ Binance', 'warn');
      renderBalances(acct);
      const oo = await call('openOrders.status', {}, true); renderOrders(oo);
    } catch (e) { log('โหลดบัญชีไม่สำเร็จ: ' + e.message, 'warn'); renderBalances(null); }
  }
  function priceOf(asset) {
    if (asset === 'USDT') return 1;
    const D = window.CL && window.CL.data(); const row = D && D.market.find((m) => m.symbol === asset);
    return row ? row.last : null;
  }
  function renderBalances(acct) {
    const tb = $('#tr-bal'); if (!tb) return; tb.replaceChildren();
    const tot = $('#tr-total');
    if (!acct) { if (tot) tot.textContent = '—'; return; }
    let total = 0;
    const rows = Object.entries(balances).map(([a, b]) => { const p = priceOf(a); const v = p != null ? (b.free + b.locked) * p : null; if (v) total += v; return {a, b, v}; })
      .sort((x, y) => (y.v || 0) - (x.v || 0));
    for (const r of rows) { const tr = tb.insertRow(); tr.insertCell().textContent = r.a;
      const c1 = tr.insertCell(); c1.className = 'num'; c1.textContent = fmtN(r.b.free, r.b.free < 1 ? 6 : 4);
      const c2 = tr.insertCell(); c2.className = 'num'; c2.textContent = r.b.locked ? fmtN(r.b.locked, 6) : '–';
      const c3 = tr.insertCell(); c3.className = 'num'; c3.textContent = r.v == null ? '–' : fmtN(r.v, 2); }
    if (!rows.length) { const tr = tb.insertRow(); const td = tr.insertCell(); td.colSpan = 4; td.textContent = 'บัญชีว่าง'; }
    if (tot) tot.textContent = fmtN(total, 2) + ' USDT (ประมาณ, เฉพาะเหรียญที่มีราคาในหน้านี้)';
  }
  function renderOrders(list) {
    const tb = $('#tr-orders'); if (!tb) return; tb.replaceChildren();
    if (!list || !list.length) { const tr = tb.insertRow(); const td = tr.insertCell(); td.colSpan = 6; td.style.color = 'var(--muted)'; td.textContent = list ? 'ไม่มีออเดอร์ค้าง' : '—'; return; }
    for (const o of list) { const tr = tb.insertRow();
      tr.insertCell().textContent = o.symbol.replace('USDT', '');
      tr.insertCell().textContent = (o.side === 'BUY' ? 'ซื้อ' : 'ขาย') + ' · ' + o.type.replace('_', ' ');
      const a = tr.insertCell(); a.className = 'num'; a.textContent = o.origQty;
      const b = tr.insertCell(); b.className = 'num'; b.textContent = +o.price ? o.price : '–';
      const c = tr.insertCell(); c.className = 'num'; c.textContent = +o.stopPrice ? o.stopPrice : '–';
      const btn = mk('button', 'btn sm', 'ยกเลิก'); btn.type = 'button';
      btn.onclick = async () => { try { await call('order.cancel', {symbol: o.symbol, orderId: o.orderId}, true); log(`ยกเลิกออเดอร์ ${o.symbol} แล้ว`, 'info'); refreshAccount(); } catch (e) { log('ยกเลิกไม่สำเร็จ: ' + e.message, 'warn'); } };
      tr.insertCell().append(btn); }
  }

  // ---------- order ticket ----------
  function fillSymbols() {
    const sel = $('#tk-sym'); if (!sel || sel.options.length) return;
    const D = window.CL && window.CL.data(); if (!D) return;
    const syms = Array.from(new Set(['BTC', ...D.market.map((m) => m.symbol), ...((D.scanner || {}).plans || []).map((p) => p.symbol)]));
    for (const s of syms) sel.append(new Option(s + '/USDT', s));
  }
  function ticketPreview() {
    const f = $('#ticket'); if (!f) return;
    fillSymbols();
    const side = f.side.value, type = f.otype.value, sym = f.sym.value, px = priceOf(sym);
    f.querySelectorAll('[data-for="limit"]').forEach((e) => e.hidden = type !== 'LIMIT');
    f.querySelectorAll('[data-for="buy"]').forEach((e) => e.hidden = side !== 'BUY');
    f.querySelectorAll('[data-for="sell"]').forEach((e) => e.hidden = side !== 'SELL');
    const amt = +f.amount.value || 0, lim = +f.limit_price.value || px;
    const stopOn = f.use_stop.checked && side === 'BUY';
    f.stop_price.disabled = !stopOn;
    const ref = type === 'LIMIT' ? lim : px;
    if (stopOn && !f.stop_price.value && ref) f.stop_price.value = +(ref * (1 - settings().stopDefaultPct / 100)).toPrecision(6);
    const st = +f.stop_price.value;
    const risk = stopOn && ref && st && st < ref ? amt * (1 - st / ref) : null;
    const out = $('#tk-preview');
    if (out) out.textContent = side === 'BUY'
      ? `ซื้อ ${sym} ประมาณ ${fmtN(amt, 2)} USDT @ ${type === 'LIMIT' ? fmtP(lim) : 'ราคาตลาด ~' + fmtP(px)}` + (risk != null ? ` · ถ้าโดน stop เสียประมาณ ${fmtN(risk, 2)} USDT` : ' · ไม่มี stop-loss ⚠️')
      : `ขาย ${f.qty.value || '—'} ${sym} @ ${type === 'LIMIT' ? fmtP(lim) : 'ราคาตลาด ~' + fmtP(px)}`;
    const free = $('#tk-free');
    if (free) free.textContent = session ? (side === 'BUY' ? `มี USDT ใช้ได้ ${fmtN((balances.USDT || {}).free, 2)}` : `มี ${sym} ใช้ได้ ${fmtN((balances[sym] || {}).free, 6)}`) : '';
  }
  let pendingOrder = null;
  async function reviewOrder(ev) {
    ev.preventDefault();
    const f = ev.target, err = f.querySelector('.formerr'); err.textContent = '';
    try {
      if (!session) { openDialog('dlg-login'); return; }
      const sym = f.sym.value, symbol = sym + 'USDT', side = f.side.value, type = f.otype.value, s = settings();
      if (side === 'BUY' && +f.amount.value > s.maxOrderUsdt) throw new Error(`เกินเพดานต่อออเดอร์ ${s.maxOrderUsdt} USDT (ปรับได้ที่ "การตั้งค่าความปลอดภัย")`);
      const r = await symbolRules(symbol), px = priceOf(sym) || 0;
      const o = {symbol, side, type};
      if (type === 'LIMIT') { const lp = +f.limit_price.value; if (!(lp > 0)) throw new Error('ใส่ราคา Limit'); o.price = roundTo(lp, r.tick); o.timeInForce = 'GTC'; }
      let notional;
      if (side === 'BUY') {
        const amt = +f.amount.value; if (!(amt > 0)) throw new Error('ใส่จำนวนเงิน USDT');
        if (amt > s.maxOrderUsdt) throw new Error(`เกินเพดานต่อออเดอร์ ${s.maxOrderUsdt} USDT (ตั้งค่าใน "การตั้งค่าความปลอดภัย")`);
        if (type === 'MARKET') o.quoteOrderQty = amt.toFixed(2);
        else o.quantity = floorTo(amt / +o.price, r.step);
        notional = amt;
      } else {
        const q = +f.qty.value; if (!(q > 0)) throw new Error('ใส่จำนวนเหรียญที่จะขาย');
        o.quantity = floorTo(q, r.step); notional = q * (type === 'LIMIT' ? +o.price : px);
      }
      if (notional < r.minNotional) throw new Error(`มูลค่าต่ำกว่าขั้นต่ำของ Binance (${r.minNotional} USDT)`);
      const stop = side === 'BUY' && f.use_stop.checked ? +f.stop_price.value : null;
      if (side === 'BUY' && f.use_stop.checked && !(stop > 0 && stop < (type === 'LIMIT' ? +o.price : px))) throw new Error('Stop ต้องต่ำกว่าราคาซื้อ');
      pendingOrder = {o, stop, rules: r, sym, notional};
      const box = $('#cf-summary'); box.replaceChildren();
      const add = (k, v) => box.append(mk('span', null, k), mk('span', null, v));
      add('บัญชี', NETS[session.net].label); add('คำสั่ง', `${side === 'BUY' ? 'ซื้อ' : 'ขาย'} ${sym} · ${type === 'MARKET' ? 'ราคาตลาด' : 'Limit ' + o.price}`);
      add('มูลค่า', `~${fmtN(notional, 2)} USDT`); if (o.quantity) add('จำนวน', `${o.quantity} ${sym}`);
      add('Stop-loss', stop ? `${roundTo(stop, r.tick)} (−${((1 - stop / (type === 'LIMIT' ? +o.price : px)) * 100).toFixed(1)}%)` : 'ไม่มี ⚠️');
      $('#cf-live').hidden = session.net !== 'live'; $('#cf-type').value = ''; $('#cf-err').textContent = '';
      openDialog('dlg-confirm');
    } catch (e) { err.textContent = e.message; }
  }
  async function placeOrder(ev) {
    ev.preventDefault();
    if (!pendingOrder || !session) return;
    if (session.net === 'live' && $('#cf-type').value.trim() !== 'ยืนยัน') { $('#cf-err').textContent = 'พิมพ์คำว่า "ยืนยัน" เพื่อส่งออเดอร์เงินจริง'; return; }
    const {o, stop, rules: r, sym} = pendingOrder; pendingOrder = null; closeDialog('dlg-confirm');
    try {
      const res = await call('order.place', o, true);
      const filled = +res.executedQty, avg = filled ? +res.cummulativeQuoteQty / filled : null;
      log(`${o.side === 'BUY' ? 'ซื้อ' : 'ขาย'} ${sym}: ${res.status} · ${filled ? `ได้ ${res.executedQty} @ ~${fmtP(avg)}` : 'ออเดอร์รอจับคู่'}`, o.side === 'BUY' ? 'buy' : 'sell');
      if (stop && o.side === 'BUY') {
        await refreshAccount();
        const qty = floorTo(Math.min(filled || +o.quantity || 0, (balances[sym] || {}).free || 0), r.step);
        if (+qty > 0 && res.status === 'FILLED') {
          const sp = roundTo(stop, r.tick), lp = roundTo(stop * 0.995, r.tick);
          const s2 = await call('order.place', {symbol: o.symbol, side: 'SELL', type: 'STOP_LOSS_LIMIT', quantity: qty, stopPrice: sp, price: lp, timeInForce: 'GTC'}, true);
          log(`ตั้ง stop-loss ${sym} ที่ ${sp} แล้ว (order ${s2.orderId})`, 'info');
        } else if (res.status !== 'FILLED') log('ออเดอร์ Limit ยังไม่จับคู่ — ตั้ง stop-loss เองหลังจับคู่แล้ว', 'warn');
      }
    } catch (e) { log('ส่งออเดอร์ไม่สำเร็จ: ' + e.message, 'warn'); }
    refreshAccount();
  }

  // ---------- wire up ----------
  function init() {
    renderAuth();
    $('#auth-btn').addEventListener('click', () => { if (session) { window.CL && window.CL.showTab('trade'); } else openDialog('dlg-login'); });
    $('#login-form').addEventListener('submit', login);
    $('#login-form').addEventListener('change', (e) => { if (e.target.name === 'net') { const live = e.target.value === 'live';
      $('#login-live').hidden = !live; $('#keys-link').href = NETS[e.target.value].keysUrl; } });
    $('#btn-logout').addEventListener('click', () => logout('ออกจากระบบแล้ว (คีย์ยังเก็บเข้ารหัสไว้ในเบราว์เซอร์นี้)'));
    $('#btn-forget').addEventListener('click', forget);
    $('#btn-refresh').addEventListener('click', refreshAccount);
    document.querySelectorAll('[data-close]').forEach((b) => b.addEventListener('click', () => closeDialog(b.dataset.close)));
    const tk = $('#ticket');
    tk.addEventListener('input', () => { tk.querySelector('.formerr').textContent = ''; ticketPreview(); }); tk.addEventListener('change', ticketPreview); tk.addEventListener('submit', reviewOrder);
    $('#cf-form').addEventListener('submit', placeOrder);
    $('#btn-sellall').addEventListener('click', () => { const s = $('#ticket').sym.value; const b = balances[s]; if (b) { $('#ticket').qty.value = b.free; ticketPreview(); } });
    const sf = $('#settings-form'); const cur = settings();
    sf.max_order.value = cur.maxOrderUsdt; sf.stop_pct.value = cur.stopDefaultPct;
    sf.addEventListener('submit', (e) => { e.preventDefault(); ls.set(SETTINGS, JSON.stringify({maxOrderUsdt: Math.max(5, +sf.max_order.value || defaults.maxOrderUsdt), stopDefaultPct: Math.min(50, Math.max(0.5, +sf.stop_pct.value || 5))})); log('บันทึกการตั้งค่าแล้ว', 'info'); });
    // "trade this plan" from plan cards
    document.addEventListener('cl:plan', (e) => {
      const p = e.detail, f = $('#ticket'); fillSymbols();
      if (![...f.sym.options].some((o) => o.value === p.symbol)) f.sym.append(new Option(p.symbol + '/USDT', p.symbol));
      f.sym.value = p.symbol; f.side.value = 'BUY'; f.otype.value = 'MARKET';
      f.amount.value = Math.round(p.size_usdt); f.use_stop.checked = true; f.stop_price.value = p.stop;
      window.CL && window.CL.showTab('trade'); ticketPreview();
      if (!session) openDialog('dlg-login');
      log(`เตรียมออเดอร์ตามแผน ${p.symbol}: ~${Math.round(p.size_usdt)} USDT, stop ${p.stop}` + (p.state !== 'enter_now' ? ' ⚠️ ยังไม่ถึงจุดเข้า' : ''), 'info');
    });
    setInterval(() => { if (session) ticketPreview(); }, 2000);
    setTimeout(ticketPreview, 1500);
  }
  window.CLTrade = {signPayload, hmacHex, sealKeys, openKeys, floorTo, roundTo};   // exposed for tests
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
