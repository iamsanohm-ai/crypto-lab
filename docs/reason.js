// แท็บ "เหตุผล": ระบบคิดทีละขั้นว่าทำไมซื้อ/ไม่ซื้อตอนนี้ และจะออกเมื่อไหร่ — ตัวเลขจริงจากแท่ง 4h + ผลทดสอบย้อนหลัง + ราคาสดทุกวินาที
(function () {
  const $ = (s) => document.querySelector(s);
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const pf = (p) => p == null || isNaN(p) ? '—' : p >= 1000 ? p.toLocaleString('en-US', {maximumFractionDigits: 2}) : p >= 1 ? p.toFixed(4) : p.toPrecision(4);
  const pct = (v, d = 1) => v == null || isNaN(v) ? '—' : (v > 0 ? '+' : '') + v.toFixed(d) + '%';
  const cls = (v) => v > 0 ? 'pos' : v < 0 ? 'neg' : 'flat';
  const VERD = {enter: ['เข้าได้', 'ok'], wait: ['รอ', 'wait'], no: ['ไม่ซื้อ', 'no'], hold: ['ถืออยู่', 'ok']};
  let sel = null, key = '';
  const T = () => { const d = window.CL && window.CL.data(); return d && d.scanner && d.scanner.thinking; };
  const live = (sym) => window.CLOrb && window.CLOrb.price ? window.CLOrb.price(sym) : null;

  function list(items) {
    const el = $('#rs-list'); el.replaceChildren();
    for (const it of items) {
      const [vt, vc] = VERD[it.verdict] || ['?', 'no'];
      const b = mk('button', 'rs-item' + (sel === it.symbol ? ' on' : '')); b.type = 'button';
      const pass = it.steps.filter((s) => s.ok === true).length, hard = it.steps.filter((s) => s.ok !== null).length;
      b.append(mk('b', null, it.symbol), mk('span', 'rs-v ' + vc, vt), mk('small', null, `ผ่าน ${pass}/${hard} ข้อ${it.in_universe ? '' : ' · นอก Top 20'}`));
      b.onclick = () => { sel = it.symbol; key = ''; render(); };
      el.append(b);
    }
  }

  function ladder(it, p) {
    // แถบราคาแนวนอน: stop → entry → +1R → +2R พร้อมจุดราคาสด
    const P = it.plan, lo = Math.min(P.stop, p || P.stop) * 0.995, hi = Math.max(P.two_r_price, p || 0, it.live.chase_max) * 1.005;
    const X = (v) => ((v - lo) / (hi - lo) * 100).toFixed(2) + '%';
    const w = mk('div', 'rs-lad'); const bar = mk('div', 'rs-bar');
    const zone = (a, b, c) => { const z = mk('i', 'z ' + c); z.style.left = X(a); z.style.width = ((b - a) / (hi - lo) * 100).toFixed(2) + '%'; bar.append(z); };
    zone(P.stop, P.entry, 'loss'); zone(P.entry, P.two_r_price, 'gain');
    const mark = (v, label, c) => { const m = mk('span', 'mk ' + c); m.style.left = X(v); m.append(mk('em', null, label), mk('small', null, pf(v))); bar.append(m); };
    mark(P.stop, 'Stop', 'st'); mark(P.entry, it.verdict === 'hold' ? 'ซื้อที่' : 'จุดเข้า', 'en'); mark(P.one_r_price, '+1R ทุนคืน', 'be'); mark(P.two_r_price, '+2R', 'tg');
    if (p) { const d = mk('span', 'now'); d.style.left = X(p); d.title = 'ราคาสด'; bar.append(d); }
    w.append(bar); return w;
  }

  function detail(it) {
    const el = $('#rs-detail'); el.replaceChildren();
    const p = live(it.symbol), L = it.live, P = it.plan;
    const [vt, vc] = VERD[it.verdict] || ['?', 'no'];
    // live chase check (ข้อ "ไม่ไล่ราคา") คำนวณใหม่ทุกวินาที
    let chase = null, chaseTxt = 'รอราคาสด…';
    if (p) { chase = p <= L.chase_max; chaseTxt = `ราคาสด ${pf(p)} ${chase ? '≤' : '>'} เพดาน ${pf(L.chase_max)} → ${chase ? 'ยังไม่ไกลเกินไป' : 'วิ่งไปไกลแล้ว ไม่ไล่ซื้อ'}`; }
    const head = mk('div', 'rs-head ' + vc);
    head.append(mk('span', 'rs-big', it.symbol), mk('span', 'rs-v ' + vc, vt), mk('p', null, it.verdict === 'enter' && chase === false ? 'สัญญาณเกิดแล้ว แต่ราคาวิ่งไปไกล — ไม่ไล่ซื้อ รอย่อ/รอรอบใหม่' : it.headline));
    if (p) head.append(mk('div', 'rs-px', `ราคาสด ${pf(p)} · ${pct((p / L.close - 1) * 100, 2)} จากราคาปิดแท่ง 4h ล่าสุด`));
    el.append(head);
    // ความคิดทีละขั้น
    const ol = mk('ol', 'rs-steps');
    it.steps.forEach((s) => {
      const ok = s.id === 'chase' ? (it.verdict === 'hold' ? null : chase) : s.ok;
      const li = mk('li', ok === true ? 'ok' : ok === false ? 'bad' : 'info');
      li.append(mk('span', 'ic', ok === true ? '✓' : ok === false ? '✕' : 'i'), mk('b', null, s.q), mk('code', null, s.id === 'chase' ? chaseTxt : s.data), mk('p', null, s.why));
      ol.append(li);
    });
    el.append(mk('div', 'op-t', 'ระบบคิดทีละขั้น (ตัวเลขจริงจากแท่ง 4h ที่ปิดแล้ว)'), ol);
    // สภากลยุทธ์ + ความน่าจะเป็น (คิดหลายทาง)
    const PB = (window.CL.data().scanner || {}).prob, X = PB && PB.coins[it.symbol];
    if (X) {
      const cw = mk('div', 'rs-council');
      for (const v of X.council.votes) { const r = mk('div', 'rs-vote ' + (v.vote > 0 ? 'up' : v.vote < 0 ? 'dn' : 'nt'));
        r.append(mk('b', null, v.vote > 0 ? '▲ ซื้อ' : v.vote < 0 ? '▼ ไม่ซื้อ/short' : '• รอ'), mk('span', null, v.who), mk('small', null, v.why)); cw.append(r); }
      el.append(mk('div', 'op-t', `สภากลยุทธ์ ${X.council.votes.length} เสียง → มติ "${X.council.verdict}" (คะแนนรวม ${X.council.score >= 0 ? '+' : ''}${X.council.score}; ซื้อเมื่อ ≥ +2 และ BTC ขาขึ้น, short เมื่อ ≤ −3)`), cw);
      const P = X.prob;
      if (P) {
        const g = mk('div', 'rs-money');
        const m2 = (k, v, s2, c) => { const d = mk('div'); d.append(mk('span', null, k), mk('b', c || '', v), mk('small', null, s2 || '')); g.append(d); };
        m2('โอกาสขึ้นใน 7 วัน', `${(P.p_up7 * 100).toFixed(0)}% / ${(P.flat.p_up7 * 100).toFixed(0)}%`, 'เทรนด์ 50 วันดำเนินต่อ / ไม่มีเทรนด์');
        m2('ช่วงที่เป็นไปได้ 90%', `${P.p5.toFixed(1)}% → +${P.p95.toFixed(1)}%`, 'ผลตอบแทน 7 วัน (เทรนด์ต่อ)');
        m2('ถ้าซื้อตามแผน', `ถึงเป้า ${(P.long.p_target * 100).toFixed(0)}% · โดน stop ${(P.long.p_stop * 100).toFixed(0)}%`, `คาดหวัง ${P.long.ev_pct >= 0 ? '+' : ''}${P.long.ev_pct.toFixed(2)}% (ไม่มีเทรนด์ ${P.flat.long_ev >= 0 ? '+' : ''}${P.flat.long_ev.toFixed(2)}%)`, P.long.ev_pct > 0 && P.flat.long_ev > 0 ? 'pos' : 'neg');
        m2('ถ้า short ตามแผน', `ถึงเป้า ${(P.short.p_target * 100).toFixed(0)}% · โดน stop ${(P.short.p_stop * 100).toFixed(0)}%`, `คาดหวัง ${P.short.ev_pct >= 0 ? '+' : ''}${P.short.ev_pct.toFixed(2)}% (ไม่มีเทรนด์ ${P.flat.short_ev >= 0 ? '+' : ''}${P.flat.short_ev.toFixed(2)}%)`, P.short.ev_pct > 0 && P.flat.short_ev > 0 ? 'pos' : 'neg');
        el.append(mk('div', 'op-t', `ความน่าจะเป็น — จำลอง ${PB.paths.toLocaleString()} อนาคต × 2 สถานการณ์ จากการเคลื่อนไหวจริง 50 วันล่าสุด (stop 3×ATR, เป้า 2R, หักค่าธรรมเนียม)`), g);
      }
    }
    // เงิน
    const money = mk('div', 'rs-money');
    const m = (k, v, s, c) => { const d = mk('div'); d.append(mk('span', null, k), mk('b', c || '', v), mk('small', null, s || '')); money.append(d); };
    m('ซื้อ', `${P.size_usdt.toFixed(2)} USDT`, `≈ ${pf(P.qty)} ${it.symbol}`);
    m('ถ้าผิดทาง เสียสูงสุด', `−${P.worst_usdt.toFixed(2)} USDT`, `stop ${pf(P.stop)} (−${P.stop_pct}%) รวมค่าธรรมเนียม ${P.fee_usdt} USDT`, 'neg');
    m('ถ้าถูกทาง (เฉลี่ยในอดีต)', `+${P.avg_win_usdt.toFixed(2)} USDT`, 'ชนะประมาณ 1 ใน 3 ครั้ง', 'pos');
    m('ตอนแพ้ (เฉลี่ยในอดีต)', `${P.avg_loss_usdt.toFixed(2)} USDT`, 'ส่วนใหญ่ออกก่อนถึง stop', 'neg');
    m('คาดหวังต่อเทรด', P.expected_usdt == null ? '—' : `${P.expected_usdt > 0 ? '+' : ''}${P.expected_usdt.toFixed(2)} USDT`, 'เฉลี่ยระยะยาวหลังค่าธรรมเนียม · ไม่ใช่การรับประกัน', cls(P.expected_usdt));
    m('ระยะเวลาถือ', P.typical_hold.split(' · ')[0].replace('ถ้าชนะ มักถือ ', ''), P.typical_hold);
    el.append(mk('div', 'op-t', 'เป็นเงิน (ทุน 500 USDT · เสี่ยง 0.5% ต่อครั้ง)'), money);
    // แผนออก
    el.append(mk('div', 'op-t', 'จะออกเมื่อไหร่ — ตัดขาดทุนเร็ว ปล่อยกำไรวิ่ง'), ladder(it, p));
    const ex = mk('div', 'rs-exits');
    it.exits.forEach((x, i) => { const r = mk('div', 'rs-ex ' + x.kind); r.append(mk('span', 'n', String(i + 1)), mk('b', null, x.when), mk('p', null, x.what));
      if (x.status) r.append(mk('small', null, x.status)); ex.append(r); });
    el.append(ex);
    if (p && it.verdict === 'hold') { const pnl = (p / P.entry - 1) * 100; el.append(mk('p', 'rs-note ' + cls(pnl), `ตอนนี้ ${pct(pnl, 2)} จากราคาซื้อ · stop ปัจจุบัน ${pf(P.stop)}`)); }
    // ปุ่มส่งไปหน้าซื้อขาย
    const act = mk('div', 'rs-act');
    const btn = mk('button', 'btn', it.verdict === 'enter' && chase !== false ? 'ใช้แผนนี้ในหน้า "ซื้อขาย" →' : 'เตรียมแผนนี้ไว้ในหน้า "ซื้อขาย" (ยังไม่ถึงจุดเข้า)'); btn.type = 'button';
    btn.onclick = () => document.dispatchEvent(new CustomEvent('cl:plan', {detail: {symbol: it.symbol, size_usdt: P.size_usdt, stop: +pf(P.stop).replace(/,/g, ''), state: it.verdict === 'enter' ? 'enter_now' : 'wait'}}));
    act.append(btn, mk('small', null, 'ทุกออเดอร์เงินจริงต้องเข้าสู่ระบบด้วยคีย์ของคุณ และกดยืนยันก่อนส่งเสมอ · ตั้ง stop-loss ให้อัตโนมัติ'));
    el.append(act);
  }

  function logic(ev) {
    const el = $('#rs-logic'); if (!el || el.dataset.k === (ev.period || [])[1]) return; el.dataset.k = (ev.period || [])[1]; el.replaceChildren();
    const A = (window.CL.data().scanner || {}).analysis || {}, R = ev.regime;
    const PB = (window.CL.data().scanner || {}).prob;
    if (PB) {
      const C = PB.calibration || {}, lw = mk('div', 'rs-qa');
      lw.append(mk('b', null, 'ระบบเรียนรู้จากคำทำนายของตัวเองอย่างไร'));
      lw.append(mk('p', null, `ทุกวันระบบบันทึกคำทำนาย "โอกาสขึ้นใน 7 วัน" ของทุกเหรียญที่ซื้อขายคล่อง → ครบ 7 วันเทียบกับราคาจริง → ถ้าทายมั่นใจเกินจริง ครั้งต่อไปจะลดความมั่นใจลงเอง (ยิ่งมีหลักฐานมาก ยิ่งปรับมาก)`));
      lw.append(mk('p', null, C.n ? `ตรวจแล้ว ${C.n} คำทำนาย · ทายทิศถูก ${(C.hit_rate * 100).toFixed(0)}% · Brier ${C.brier} (เดาแบบไม่รู้อะไรได้ ${C.brier_naive} — ต่ำกว่า = ดีกว่า) · รอตรวจ ${C.pending}`
        : `กำลังเก็บคำทำนาย ${C.pending || 0} รายการ — ผลตรวจชุดแรกจะเริ่มแสดงหลังครบ 7 วัน`));
      if (C.table) { const tb = mk('div', 'rs-cal'); for (const b2 of C.table) tb.append(mk('span', null, `ทาย ${b2.bin}: จริง ${(b2.real * 100).toFixed(0)}% (${b2.n})`)); lw.append(tb); }
      el.append(lw);
    }
    const q = mk('div', 'rs-qa');
    q.append(mk('b', null, 'ถาม: ถ้าต้องรอ BTC ขึ้นอีกเกือบ 20% เท่ากับขาดทุน 20% ไปแล้วไหม?'));
    q.append(mk('p', null, `ไม่ใช่ครับ — ตอนนี้บอทถือเงินสด 100% เงินไม่ได้ลดลงเลย ที่เสียไปคือ "โอกาส" ช่วงต้นของขาขึ้น ไม่ใช่เงิน`));
    if (R) q.append(mk('p', null, `ในอดีต ตอนที่ BTC ตัดขึ้นเหนือ EMA200 มันขึ้นจากจุดต่ำสุดมาแล้วเฉลี่ย ~${R.cross_stats.median_from_low_pct}% — นั่นคือส่วนที่เราพลาด แลกกับการไม่โดนลากลงไปตอนตลาดยังลง (${R.cross_stats.whipsaw_pct}% ของการตัดขึ้นเป็น "หลอก" ไม่ถึง 3 วันก็หลุดลงมาอีก)`));
    if (A.btc_ema200_7d_pct != null) q.append(mk('p', null, `และระยะ ~20% ไม่ได้คงที่: เส้น EMA200 เองกำลังลดลงมาหาราคา (${pct(A.btc_ema200_7d_pct, 1)} ใน 7 วัน) ถ้า BTC แค่ทรงตัว 2 สัปดาห์ ระยะห่างจะเหลือประมาณ ${A.btc_gap_flat_2w_pct}%`));
    el.append(q);
    if (R) {
      el.append(mk('p', 'rs-sub', `ทดสอบจริงช่วง ${R.period[0].slice(0, 10)} → ${R.period[1].slice(0, 10)}: กฎเดียวกัน เปลี่ยนแค่ "รอตลาดแบบไหนก่อนซื้อ"`));
      const tb = mk('table'), hd = mk('tr'); ['รอแบบไหน', 'ผลตอบแทน', 'Sharpe', 'ลดลงหนักสุด', 'เทรด', 'คาดหวัง/เทรด'].forEach((h, i) => hd.append(mk('th', i ? 'num' : null, h)));
      const th = mk('thead'); th.append(hd); const tbd = mk('tbody');
      for (const f of R.filters) { const tr = mk('tr', f.filter === 'ema200' ? 'cur' : null);
        tr.append(mk('td', null, f.label), mk('td', 'num ' + cls(f.return_pct), pct(f.return_pct)), mk('td', 'num', f.sharpe.toFixed(2)), mk('td', 'num neg', pct(f.max_dd_pct)), mk('td', 'num', String(f.trades)), mk('td', 'num', (f.expectancy_r > 0 ? '+' : '') + f.expectancy_r.toFixed(3) + 'R'));
        tbd.append(tr); }
      tb.append(th, tbd); const w = mk('div', 'tablewrap'); w.append(tb); el.append(w);
      const best = R.filters.reduce((a, b) => (b.sharpe > a.sharpe ? b : a));
      el.append(mk('p', 'rs-sub', `สรุป: ซื้อโดยไม่รอ (${pct(R.filters[0].return_pct)}) แย่กว่ารอ BTC เหนือ EMA200 (${pct(R.filters.find((f) => f.filter === 'ema200').return_pct)}) และลดลงหนักกว่า · ${best.filter === 'ema200' ? 'กฎปัจจุบันดีที่สุด' : `"${best.label}" ได้ Sharpe ${best.sharpe.toFixed(2)} ใกล้เคียงกฎปัจจุบันมาก (ต่างกันน้อยเกินกว่าจะสรุปได้) จึงยังใช้กฎเดิม`} · ตัวกรองที่เร็วกว่า (EMA50) เข้าเร็วกว่าแต่โดนหลอกบ่อยจนผลแย่ลง`));
    }
    if (ev.exit_variants) {
      el.append(mk('div', 'op-t', 'ทดสอบวิธี "ออก" เพื่อให้ขาดทุนน้อยที่สุดแต่ยังได้กำไร'));
      const tb = mk('table'), hd = mk('tr'); ['วิธีออก', 'ผลตอบแทน', 'Sharpe', 'ลดลงหนักสุด', 'ชนะเฉลี่ย', 'แพ้เฉลี่ย', 'คาดหวัง'].forEach((h, i) => hd.append(mk('th', i ? 'num' : null, h)));
      const th = mk('thead'); th.append(hd); const tbd = mk('tbody');
      for (const v of ev.exit_variants) { const tr = mk('tr', v.variant === 'be_1r' ? 'cur' : null);
        tr.append(mk('td', null, v.label), mk('td', 'num ' + cls(v.return_pct), pct(v.return_pct)), mk('td', 'num', v.sharpe.toFixed(2)), mk('td', 'num neg', pct(v.max_dd_pct)),
          mk('td', 'num pos', '+' + v.avg_win_r + 'R'), mk('td', 'num neg', v.avg_loss_r + 'R'), mk('td', 'num', (v.expectancy_r > 0 ? '+' : '') + v.expectancy_r + 'R'));
        tbd.append(tr); }
      tb.append(th, tbd); const w = mk('div', 'tablewrap'); w.append(tb); el.append(w);
      el.append(mk('p', 'rs-sub', 'R = จำนวนเงินที่ยอมเสียต่อเทรด (2.5 USDT) · กฎปัจจุบันตัดขาดทุนเร็วอยู่แล้ว (แพ้เฉลี่ยแค่ครึ่งหนึ่งของ R เพราะขายเมื่อปิดต่ำกว่า EMA20 ก่อนถึง stop) · แถวที่ไฮไลต์ = กฎที่ระบบใช้อยู่ (เจ้าของอนุมัติ 25 พ.ย. 2026) · stop แคบลงได้เงินมากขึ้นแต่ขาดทุนต่อครั้งและช่วงติดลบหนักกว่า'));
    }
  }

  function render() {
    const v = $('#view-reason'); if (!v || v.hidden) return;
    const t = T(); if (!t || !t.items) { $('#rs-detail').replaceChildren(mk('div', 'empty', 'รอข้อมูลจากบอท (สแกนรอบถัดไป)')); return; }
    if (!sel || !t.items.some((i) => i.symbol === sel)) sel = t.items[0] && t.items[0].symbol;
    const k = t.items.map((i) => i.symbol + i.verdict).join() + sel;
    if (k !== key) { key = k; list(t.items); }
    const it = t.items.find((i) => i.symbol === sel); if (it) detail(it);
    logic(t.evidence || {});
  }
  function init() { setInterval(() => { if (!document.hidden) render(); }, 1000); document.addEventListener('click', (e) => { if (e.target.closest('[data-tab="reason"]')) setTimeout(render, 50); }); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
