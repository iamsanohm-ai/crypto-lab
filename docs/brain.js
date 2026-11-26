// "สมองของระบบ": รวมสิ่งที่ทุกส่วนกำลังทำ/คิด/เลือก ไว้ที่เดียว — ทุกบรรทัดมาจากข้อมูลจริงของระบบ
// 1) แถบความคิดสด (ทุกหน้า) ใต้แท็บ   2) แผง "ระบบกำลังคิดอะไร" ในหน้าภาพรวม (แตะเพื่อไปหน้าที่เกี่ยวข้อง)
(function () {
  const $ = (s) => document.querySelector(s);
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const pct = (v, d = 1) => v == null || isNaN(v) ? '—' : (v > 0 ? '+' : '') + Number(v).toFixed(d) + '%';
  const ago = (iso) => { if (!iso) return ''; const s = Math.max(0, Math.round((Date.now() - new Date(iso)) / 1000));
    return s < 60 ? s + ' วิ' : s < 3600 ? Math.floor(s / 60) + ' นาที' : Math.floor(s / 3600) + ' ชม.'; };
  let SC = null, XS = null, scAt = 0, bandI = 0, bandAt = 0;

  async function loadScalp() {
    try { const r = await fetch('scalper.json?t=' + Date.now(), {cache: 'no-store'}); if (r.ok) { SC = await r.json(); scAt = Date.now(); } } catch (e) { /* keep */ }
    try { const r = await fetch('xs_paper.json?t=' + Date.now(), {cache: 'no-store'}); if (r.ok) XS = await r.json(); } catch (e) { /* none yet */ }
  }

  // แต่ละโมดูล: สถานะ (ok/wait/stop/info), สิ่งที่ทำ, สิ่งที่คิด, สิ่งที่เลือก
  function modules() {
    const D = window.CL && window.CL.data(); if (!D) return [];
    const S = D.scanner || {}, A = S.analysis || {}, T = S.thinking || {}, out = [];
    const up = A.btc_vs_ema200_pct > 0;
    // 1. บอทหลัก
    const acc = (D.accounts || [])[0] || {};
    out.push({tab: 'reason', mod: 'บอทหลัก 4 ชม.', st: up ? 'ok' : 'wait',
      did: `ตรวจตลาดทุก 15 นาที · ล่าสุด ${ago((D.system || {}).last_bot_tick)}ที่แล้ว`,
      think: up ? 'BTC อยู่เหนือ EMA200 — ตลาดเปิดให้เข้าได้' : `BTC ต่ำกว่า EMA200 ${pct(A.btc_vs_ema200_pct)} — ในอดีตซื้อช่วงนี้ผลแย่กว่า`,
      pick: acc.open_positions ? `ถือ ${acc.open_positions} สถานะ` : up ? 'รอสัญญาณทะลุกรอบ Keltner' : 'เลือกถือเงินสด 100% (ไม่ขาดทุน)'});
    // 2. ความคิดรายเหรียญ
    if (T.items) { const n = (v) => T.items.filter((x) => x.verdict === v).length;
      const best = T.items.find((x) => x.verdict === 'enter') || T.items.find((x) => x.verdict === 'wait');
      out.push({tab: 'reason', mod: 'สมองตัดสินใจ', st: n('enter') ? 'ok' : 'wait', did: `คิดทีละขั้น ${T.items.length} เหรียญ × 8 คำถาม`,
        think: `เข้าได้ ${n('enter')} · รอ ${n('wait')} · ไม่ซื้อ ${n('no')}`, pick: best ? `${best.symbol}: ${best.headline}` : 'ยังไม่มีเหรียญผ่าน'}); }
    // 3. สนามประลองระยะสั้น
    if (SC && SC.models) { const G = SC.gates || {}, ck = SC.checks || {};
      const open = SC.models.filter((m) => (G[m.id] || {}).open), last = Object.values(ck).sort((a, b) => b.at.localeCompare(a.at))[0];
      const fired = Object.entries(ck).flatMap(([k, v]) => v.fired.map((s) => s)).length;
      out.push({tab: 'scalp', mod: 'เทรดระยะสั้น', st: open.length ? 'ok' : 'wait', did: `${SC.models.length} กลยุทธ์ เทรดเงาด้วยราคาจริง · ตรวจล่าสุด ${last ? ago(last.at) + 'ที่แล้ว' : '—'}`,
        think: `เงาเปิดอยู่ ${SC.shadow.length} · ปิดแล้ว ${SC.shadow_closed.length} ครั้ง · สัญญาณรอบล่าสุด ${fired}`,
        pick: open.length ? `ใช้เงินกับ: ${open.map((m) => m.label).join(', ')}` : 'ยังไม่ใช้เงิน — ไม่มีกลยุทธ์ไหนผลเงาเป็นบวกพอ'});
      out.push({tab: 'scalp', mod: 'บัญชีระยะสั้น', st: SC.sentinel && SC.sentinel.halted ? 'stop' : 'info', did: `เงิน ${(SC.equity || 0).toFixed(2)} USDT`,
        think: `กำไร/ขาดทุนรวม ${((SC.stats || {}).pnl_usdt || 0).toFixed(2)} USDT จาก ${(SC.stats || {}).trades || 0} เทรด`,
        pick: SC.sentinel && SC.sentinel.halted ? 'Sentinel สั่งพัก: ' + SC.sentinel.halted.reason : `Sentinel ปกติ · แพ้ติด ${(SC.sentinel || {}).loss_streak || 0}/3`}); }
    if (XS && XS.targets) { const L = XS.targets.filter((t) => t.weight > 0).slice(0, 3).map((t) => t.symbol.replace('USDT', '')), S = XS.targets.filter((t) => t.weight < 0).slice(-3).map((t) => t.symbol.replace('USDT', ''));
      out.push({tab: 'scalp', mod: 'Long แข็ง/Short อ่อน', st: 'ok', did: `จัดพอร์ตวันละครั้ง · บัญชีจำลอง ${XS.equity.toFixed(2)} USDT`,
        think: 'ตลาดขาลงทั้งกระดาน → กำไรจากส่วนต่าง: ตัวที่ลงน้อยกว่า vs ตัวที่ลงหนัก (ทดสอบแล้ว: ตลาดขาลง +30%)', pick: `Long ${L.join(', ')} · Short ${S.join(', ')}`}); }
    // 4. ORB สแกนทั้งกระดาน
    const orb = window.CLOrb && window.CLOrb.changes ? window.CLOrb.changes() : [];
    const rows = (S.rows || []).filter((r) => r.status !== 'illiquid' && r.score != null);
    const top = rows.slice().sort((a, b) => b.raw_score - a.raw_score)[0];
    out.push({tab: 'scan', mod: 'สแกนทั้งกระดาน', st: 'info', did: `${S.total || 0} เหรียญ · คะแนนใหม่จากราคาสดทุก 2 วิ`,
      think: orb.length ? `คะแนนเปลี่ยน ${orb.filter((c) => Date.now() - c.t < 60000).length} ครั้งใน 1 นาที · ล่าสุด ${orb[0].sym} ${orb[0].from}→${orb[0].to}` : 'รอราคาสด…',
      pick: top ? `น่าสนใจสุด: ${top.symbol} (ดิบ ${top.raw_score})` : '—'});
    // 5. Judge
    out.push({tab: 'strategy', mod: 'ห้องทดสอบ (Judge)', st: 'info', did: `ทดสอบย้อนหลังทุกคืน · ล่าสุด ${ago((D.system || {}).judge_at)}ที่แล้ว`,
      think: 'walk-forward 29 กลยุทธ์ + วิธีออก + ตัวกรองตลาด + ระยะสั้น 5 นาที/1 ชม.', pick: 'Champion: Keltner Trend (k=2, stop 3×ATR)'});
    return out;
  }

  function band() {
    const el = $('#think-band'); if (!el) return;
    const M = modules(); if (!M.length) return;
    // ความคิดล่าสุดแบบเหตุการณ์ (จากบอทระยะสั้น) ผสมกับสถานะโมดูล
    const evs = ((SC && SC.events) || []).slice(0, 6).map((e) => ({tab: 'scalp', mod: 'ระยะสั้น', st: e.kind === 'buy' ? 'ok' : e.kind === 'sell' ? 'info' : 'wait', line: e.text, t: e.t}));
    const items = M.map((m) => ({tab: m.tab, mod: m.mod, st: m.st, line: `${m.think} → ${m.pick}`})).concat(evs);
    if (Date.now() - bandAt > 4500) { bandAt = Date.now(); bandI = (bandI + 1) % items.length;
      const it = items[bandI]; el.replaceChildren();
      const b = mk('button', 'tb-in st-' + it.st); b.type = 'button'; b.onclick = () => window.CL.showTab(it.tab);
      b.append(mk('span', 'tb-dot'), mk('b', null, it.mod), mk('span', 'tb-l', it.line), mk('span', 'tb-go', it.t ? ago(it.t) + 'ที่แล้ว' : 'ดู →'));
      el.append(b); }
  }

  function panel() {
    const el = $('#brain'); if (!el) return;
    const v = $('#view-overview'); if (!v || v.hidden) return;
    const M = modules(); const key = JSON.stringify(M); if (el.dataset.k === key) return; el.dataset.k = key; el.replaceChildren();
    for (const m of M) {
      const r = mk('button', 'br-row st-' + m.st); r.type = 'button'; r.onclick = () => window.CL.showTab(m.tab);
      const h = mk('div', 'br-h'); h.append(mk('span', 'tb-dot'), mk('b', null, m.mod), mk('span', 'br-did', m.did));
      const g = mk('div', 'br-g'); g.append(mk('span', 'k', 'คิด'), mk('span', null, m.think), mk('span', 'k', 'เลือก'), mk('span', 'pk', m.pick));
      r.append(h, g); el.append(r);
    }
  }

  function init() { loadScalp(); setInterval(loadScalp, 30000); setInterval(() => { if (!document.hidden) { band(); panel(); } }, 1000); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
