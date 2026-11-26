// กลยุทธ์ที่ผ่านการทดสอบ: เก็บ funding (ซื้อ spot + short perpetual เท่ากัน — ราคาขึ้นลงไม่กระทบ ได้ค่า funding ทุก 8 ชม.)
// ข้อมูล funding สดดึงจาก Binance Futures โดยเบราว์เซอร์ของคุณเอง (เซิร์ฟเวอร์ GitHub ถูกบล็อก) · กฎ = ตามที่ทดสอบย้อนหลัง
(function () {
  const $ = (s) => document.querySelector(s);
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const pct = (v, d = 2) => v == null || isNaN(v) ? '—' : (v > 0 ? '+' : '') + v.toFixed(d) + '%';
  const cls = (v) => v == null || isNaN(v) ? 'flat' : v > 0 ? 'pos' : v < 0 ? 'neg' : 'flat';
  const ENTER = 0.0001, EXIT = 0.0, FEE_RT = 2 * (0.00075 + 0.0002);   // ตรงกับ research/edge_search.json (limit order + ส่วนลด BNB)
  let R = null, rows = [], at = 0, err = null, busy = false;

  async function load() {
    if (busy) return; busy = true;
    try {
      if (!R) { const r = await fetch('edge_search.json?t=' + Date.now(), {cache: 'no-store'}); if (r.ok) R = await r.json(); }
      const D = window.CL && window.CL.data(); const syms = ((D && D.market) || []).map((m) => m.symbol);
      if (!syms.length) return;
      const prem = await (await fetch('https://fapi.binance.com/fapi/v1/premiumIndex', {cache: 'no-store'})).json();
      const P = new Map(prem.map((x) => [x.symbol, x]));
      const out = [];
      for (const s of syms) {
        const fs = P.has(s + 'USDT') ? s + 'USDT' : '1000' + s + 'USDT', p = P.get(fs); if (!p) { out.push({sym: s, nofut: true}); continue; }   // เช่น PEPE → 1000PEPEUSDT
        let hist = [];
        try { hist = await (await fetch(`https://fapi.binance.com/fapi/v1/fundingRate?symbol=${fs}&limit=9`, {cache: 'no-store'})).json(); } catch (e) { /* skip */ }
        const rates = hist.map((h) => +h.fundingRate), avg3 = rates.length ? rates.reduce((a, b) => a + b, 0) / rates.length : null;
        out.push({sym: s, last: +p.lastFundingRate, next: +p.nextFundingTime, mark: +p.markPrice, index: +p.indexPrice, avg3, n: rates.length});
      }
      // เลือกตามกฎ: 5 อันดับที่ funding เฉลี่ย 3 วัน > 0.01%/รอบ
      const ranked = out.filter((r) => r.avg3 != null).sort((a, b) => b.avg3 - a.avg3);
      const pick = new Set(ranked.filter((r) => r.avg3 > ENTER).slice(0, 5).map((r) => r.sym));
      for (const r of out) r.action = r.nofut ? 'ไม่มี futures' : pick.has(r.sym) ? 'เข้า/ถือ' : r.avg3 != null && r.avg3 > EXIT ? 'ถือต่อได้ (ไม่เปิดใหม่)' : 'ไม่ทำ/ปิด';
      rows = out.sort((a, b) => (b.avg3 ?? -9) - (a.avg3 ?? -9)); at = Date.now(); err = null;
    } catch (e) { err = 'ดึง funding จาก Binance Futures ไม่ได้ในเบราว์เซอร์นี้ (' + e.message + ')'; }
    finally { busy = false; render(); }
  }

  function render() {
    const el = $('#carry'); if (!el) return; el.replaceChildren();
    const fc = R && R.funding_carry && R.funding_carry.maker_bnb, mk2 = R && R.funding_carry && R.funding_carry.market;
    const head = mk('div', 'cy-head');
    if (fc) {
      const yrs = Object.entries(fc.by_year).map(([y, v]) => `${y}: ${pct(v, 1)}`).join(' · ');
      head.append(mk('p', 'sc-why', `ทดสอบจริง ${R.period[0].slice(0, 10)} → ${R.period[1].slice(0, 10)} (funding จริงของ Top 20 รายเดือน): ผลตอบแทน ${pct(fc.return_pct, 1)} · ขาดทุนสะสมสูงสุด ${pct(fc.max_dd_pct, 1)} · รายปี ${yrs}`
        + ` — ถ้าส่งออเดอร์แบบ market (ค่าธรรมเนียมสูงกว่า) เหลือ ${pct(mk2.return_pct, 1)} และปี 2026 ${pct(mk2.by_year['2026'], 1)} · ต้องใช้ limit order + จ่ายค่าธรรมเนียมด้วย BNB`));
    }
    head.append(mk('p', 'sc-why', 'วิธีทำ (ต่อ 1 เหรียญ): ซื้อ spot X USDT + เปิด short perpetual X USDT (leverage 1x) พร้อมกัน → ราคาขึ้น/ลงหักล้างกันเอง ได้ค่า funding ทุก 8 ชม. เมื่อ funding เป็นบวก · ปิดทั้งสองขาเมื่อ funding เฉลี่ยกลายเป็นลบ'));
    el.append(head);
    if (err) { el.append(mk('div', 'empty', err)); return; }
    if (!rows.length) { el.append(mk('div', 'empty', 'กำลังดึง funding สด…')); return; }
    const tb = mk('table', 'mkt'); const hr = mk('tr');
    ['เหรียญ', 'funding ล่าสุด', 'เฉลี่ย 3 วัน', 'ต่อปี (ประมาณ)', 'รายได้/วัน ต่อ 100 USDT', 'mark vs index', 'ระบบแนะนำ'].forEach((h, i) => hr.append(mk('th', i && i < 6 ? 'num' : null, h)));
    const th = mk('thead'); th.append(hr); const bd = mk('tbody');
    for (const r of rows) {
      const tr = mk('tr'); tr.append(mk('td', null, r.sym));
      if (r.nofut) { const td = mk('td', 'flat', 'ไม่มีสัญญา perpetual'); td.colSpan = 6; tr.append(td); bd.append(tr); continue; }
      const yr = r.avg3 * 3 * 365 * 100, perday = 100 * r.avg3 * 3;
      tr.append(mk('td', 'num ' + cls(r.last), pct(r.last * 100, 4)), mk('td', 'num ' + cls(r.avg3), pct(r.avg3 * 100, 4)), mk('td', 'num ' + cls(yr), pct(yr, 1)),
        mk('td', 'num ' + cls(perday), (perday >= 0 ? '+' : '') + perday.toFixed(3) + ' USDT'), mk('td', 'num', pct((r.mark / r.index - 1) * 100, 3)));
      const a = mk('td'); a.append(mk('span', 'tr ' + (r.action === 'เข้า/ถือ' ? 'up' : r.action.startsWith('ถือ') ? '' : 'down'), r.action)); tr.append(a); bd.append(tr);
    }
    tb.append(th, bd); const w = mk('div', 'tablewrap'); w.append(tb); el.append(w);
    const picked = rows.filter((r) => r.action === 'เข้า/ถือ');
    const est = picked.reduce((s, r) => s + 100 * r.avg3 * 3, 0);
    el.append(mk('p', 'help', `ถ้าทำตามกฎด้วย 100 USDT ต่อเหรียญ (${picked.length} เหรียญ): รายได้ประมาณ ${est.toFixed(3)} USDT/วัน จาก funding ปัจจุบัน (ประมาณการ — funding เปลี่ยนทุก 8 ชม.) · ค่าเปิด+ปิดทั้งสองขาประมาณ ${(FEE_RT * 100).toFixed(2)}% ต่อรอบ จึงคุ้มเมื่อถือหลายวัน`
      + ` · ความเสี่ยงที่ผลทดสอบยังไม่รวม: ราคา spot กับ futures ห่างกันชั่วคราว, ขา short ถูกบังคับปิดถ้าราคาพุ่งแรงและ margin ไม่พอ (ใช้ 1x และเผื่อ margin) · อัปเดตล่าสุด ${at ? new Date(at).toLocaleTimeString('th-TH') : '—'}`));
  }
  function init() { setTimeout(load, 3000); setInterval(() => { const v = $('#view-scalp'); if (v && !v.hidden && !document.hidden) load(); }, 300000);
    document.addEventListener('click', (e) => { if (e.target.closest('[data-tab="scalp"]') && Date.now() - at > 120000) setTimeout(load, 200); }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
