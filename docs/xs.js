// กลยุทธ์ที่ผ่านเกณฑ์: Long เหรียญแข็ง / Short เหรียญอ่อน (ไม่เสี่ยงทิศทางตลาด) — ผลวิจัย + บัญชีจำลอง + พอร์ตเป้าหมายวันนี้
(function () {
  const $ = (s) => document.querySelector(s);
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const pct = (v, d = 1) => v == null || isNaN(v) ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(d) + '%';
  const cls = (v) => v > 0 ? 'pos' : v < 0 ? 'neg' : 'flat';
  let R = null, P = null, key = '';
  async function load() {
    try { const r = await fetch('xs_research.json?t=' + Date.now(), {cache: 'no-store'}); if (r.ok) R = await r.json(); } catch (e) { /* none */ }
    try { const r = await fetch('xs_paper.json?t=' + Date.now(), {cache: 'no-store'}); if (r.ok) P = await r.json(); } catch (e) { /* none */ }
    render();
  }
  function spark(curve, W = 520, H = 90) {
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg'); svg.setAttribute('viewBox', `0 0 ${W} ${H}`); svg.setAttribute('class', 'xs-curve'); svg.setAttribute('preserveAspectRatio', 'none');
    const v = curve.map((x) => x[1]), lo = Math.min(...v), hi = Math.max(...v);
    const pts = v.map((y, i) => `${(i / (v.length - 1) * W).toFixed(1)},${(H - 4 - (y - lo) / (hi - lo || 1) * (H - 8)).toFixed(1)}`).join(' ');
    const pl = document.createElementNS(ns, 'polyline'); pl.setAttribute('points', pts); pl.setAttribute('fill', 'none'); pl.setAttribute('stroke', '#22c983'); pl.setAttribute('stroke-width', '1.6');
    const base = document.createElementNS(ns, 'line'); const y1 = H - 4 - (1 - lo) / (hi - lo || 1) * (H - 8);
    base.setAttribute('x1', 0); base.setAttribute('x2', W); base.setAttribute('y1', y1); base.setAttribute('y2', y1); base.setAttribute('stroke', '#2a3542'); base.setAttribute('stroke-dasharray', '3 4');
    svg.append(base, pl); return svg;
  }
  function render() {
    const el = $('#xs'); if (!el) return;
    const k = (R && R.generated_at) + (P && P.updated_at); if (k === key) return; key = k; el.replaceChildren();
    if (R && R.ensemble_oos) {
      const E = R.ensemble_oos, B = R.btc_buy_hold_oos;
      const g = mk('div', 'xs-kpi');
      const kv = (a, b, c, s) => { const d = mk('div'); d.append(mk('span', null, a), mk('b', c, b), mk('small', null, s || '')); g.append(d); };
      kv('ผลตอบแทน (ช่วงที่ไม่เคยเห็น)', pct(E.total_pct), 'pos', `${R.oos[0].slice(0, 10)} → ${R.oos[1].slice(0, 10)}`);
      kv('Sharpe', E.sharpe.toFixed(2), 'pos', 'ถือ BTC เฉยๆ ได้ ' + pct(B.total_pct) + ' แต่ลดลงหนักสุด ' + pct(B.max_dd_pct));
      kv('ช่วงตลาดขาลง', pct(E.btc_down_pct), cls(E.btc_down_pct), 'วันที่ BTC อยู่ใต้ EMA200');
      kv('ขาดทุนสะสมสูงสุด', pct(E.max_dd_pct), 'neg', 'ใช้เงินครึ่งเดียว ≈ ครึ่งของตัวเลขนี้');
      kv('รายปี', Object.entries(E.by_year).map(([y, v]) => `${y.slice(2)}: ${pct(v, 0)}`).join(' '), 'xs-yr', 'หักค่าธรรมเนียม + slippage + funding จริงแล้ว');
      el.append(g);
      const cw = mk('div', 'xs-cw'); cw.append(mk('div', 'op-t', 'เงินจำลองของกลยุทธ์ (ทดสอบย้อนหลัง ช่วงที่ไม่เคยเห็น · เส้นประ = ทุนเริ่มต้น)'), spark(E.curve)); el.append(cw);
    }
    const how = mk('p', 'sc-why'); how.append(mk('b', null, 'คิดอย่างไร: '), 'ทุก 7–14 วัน จัดอันดับ Top 20 ตามผลตอบแทน 7/14/30 วันที่ผ่านมา → long ตัวที่แข็งที่สุด + short ตัวที่อ่อนที่สุดด้วยเงินเท่ากัน (ใช้ 12 ชุดพารามิเตอร์พร้อมกัน ไม่เลือกเฉพาะตัวที่ผลดีที่สุด) → ตลาดขึ้นหรือลงทั้งกระดานไม่กระทบมาก กำไรมาจาก "ตัวแข็งยังแข็ง ตัวอ่อนยังอ่อน" ซึ่งงานวิจัยคริปโตพบว่าเกิดขึ้นจริง');
    el.append(how);
    if (P && P.targets) {
      const box = mk('div', 'xs-now');
      box.append(mk('div', 'op-t', `พอร์ตเป้าหมายวันนี้ (${P.last_day}) · บัญชีจำลอง ${P.equity.toFixed(2)} USDT (${pct((P.equity / P.capital - 1) * 100, 2)})`));
      const L = P.targets.filter((t) => t.weight > 0), S = P.targets.filter((t) => t.weight < 0).reverse();
      const col = (title, arr, c) => { const d = mk('div', 'xs-col'); d.append(mk('b', c, title));
        for (const t of arr) { const r = mk('div', 'xs-row'); const bar = mk('i'); bar.style.width = Math.min(100, Math.abs(t.weight) / 0.15 * 100) + '%'; bar.className = c;
          r.append(mk('span', null, t.symbol.replace('USDT', '')), bar, mk('em', null, `${(Math.abs(t.weight) * 100).toFixed(1)}% · 30 วัน ${pct(t.mom30_pct)}`)); d.append(r); }
        return d; };
      const cols = mk('div', 'xs-cols'); cols.append(col('LONG (ซื้อ) — ลงน้อยที่สุด/แข็งที่สุด', L, 'pos'), col('SHORT (ขาย) — อ่อนที่สุด', S, 'neg')); box.append(cols);
      box.append(mk('p', 'help', 'บัญชีจำลองอัปเดตวันละครั้งบนเซิร์ฟเวอร์ (ใช้ราคา spot แทน perpetual, ยังไม่รวม funding) · ส่งออเดอร์จริงจากคอมของคุณด้วย tools/xs_executor.py (ถามยืนยันทุกออเดอร์) · ต้องใช้บัญชี Binance Futures'));
      el.append(box);
    } else el.append(mk('div', 'empty', 'บัญชีจำลองจะเริ่มในรอบบอทถัดไป'));
  }
  function init() { load(); setInterval(() => { const v = $('#view-scalp'); if (v && !v.hidden && !document.hidden) load(); }, 300000); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
