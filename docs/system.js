// สถานะระบบแบบสด: แต่ละส่วนทำงานล่าสุดเมื่อไหร่, รอบถัดไปอีกนานแค่ไหน, งานบน GitHub Actions ที่กำลังรัน และกิจกรรมล่าสุด
(function () {
  const $ = (s) => document.querySelector(s);
  const mk = (tag, c, text) => { const e = document.createElement(tag); if (c) e.className = c; if (text != null) e.textContent = text; return e; };
  const D = () => window.CL && window.CL.data();
  let runs = null, runsErr = null, runsAt = 0, hb = null;

  const ago = (ms) => { if (ms == null || isNaN(ms)) return '—'; const s = Math.max(0, Math.round(ms / 1000));
    if (s < 60) return `${s} วินาทีที่แล้ว`; if (s < 3600) return `${Math.floor(s / 60)} นาทีที่แล้ว`;
    if (s < 86400) return `${Math.floor(s / 3600)} ชม. ${Math.floor((s % 3600) / 60)} นาทีที่แล้ว`; return `${Math.floor(s / 86400)} วันที่แล้ว`; };
  const cd = (ms) => { const s = Math.max(0, Math.round(ms / 1000)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(x).padStart(2, '0'); };
  const since = (iso) => iso ? Date.now() - new Date(iso).getTime() : null;
  const nextUtc = (hhmm) => { const [h, m] = hhmm.split(':').map(Number); const n = new Date(); const t = new Date(Date.UTC(n.getUTCFullYear(), n.getUTCMonth(), n.getUTCDate(), h, m));
    if (t <= n) t.setUTCDate(t.getUTCDate() + 1); return t - n; };
  const nextTick = (every, off) => { const now = Date.now(), p = every * 60000, o = off * 60000; return (Math.floor((now - o) / p) + 1) * p + o - now; };
  const next4h = () => { const p = 4 * 3600000, now = Date.now(); return (Math.floor(now / p) + 1) * p - now; };
  const thTime = (iso) => window.CL ? window.CL.fmt.time(iso) : iso;

  async function fetchRuns() {
    const sys = (D() || {}).system; if (!sys) return;
    try {
      const r = await fetch(`https://api.github.com/repos/${sys.repo}/actions/runs?per_page=40`, {cache: 'no-store'});
      if (!r.ok) throw new Error(r.status === 403 ? 'GitHub จำกัดจำนวนการเรียก ลองใหม่อีกสักครู่' : 'HTTP ' + r.status);
      runs = (await r.json()).workflow_runs.filter((w) => w.name !== 'pages build and deployment'); runsErr = null; runsAt = Date.now();
    } catch (e) { runsErr = e.message; }
    render();
  }
  async function heartbeat() {
    try { const r = await fetch('heartbeat.json?t=' + Date.now(), {cache: 'no-store'}); const j = await r.json();
      if (hb && j.generated_at !== hb && window.CL && window.CL.reload) window.CL.reload();
      hb = j.generated_at; } catch (e) { /* ignore */ }
  }

  function tile(el, state, title, value, sub) {
    const t = mk('div', 'sys-t ' + state); const h = mk('div', 'sys-h'); h.append(mk('span', 'sys-dot'), mk('span', null, title));
    t.append(h, mk('div', 'sys-v', value), mk('div', 'sys-s', sub)); el.append(t);
  }

  function render() {
    const d = D(); if (!d || !d.system) return;
    const sys = d.system, S = d.scanner || {};
    const el = $('#sys-tiles');
    if (el) {
      el.replaceChildren();
      const live = window.CL.liveAge ? window.CL.liveAge() : null;
      tile(el, live != null && live < 6000 ? 'ok' : live != null && live < 30000 ? 'warn' : 'bad', 'ราคาสด Binance',
        live == null ? 'เชื่อมต่อ…' : live < 2000 ? 'สด' : ago(live), 'อัปเดตทุกวินาที');
      const lt = since(sys.last_bot_tick), lim = sys.tick_every_min * 60000;
      tile(el, lt != null && lt < lim + 10 * 60000 ? 'ok' : lt != null && lt < 3 * lim ? 'warn' : 'bad', 'บอทเทรด · รอบถัดไป',
        cd(nextTick(sys.tick_every_min, sys.tick_offset_min)), 'รันล่าสุด ' + ago(lt));
      const st = since(S.generated_at);
      tile(el, st != null && st < lim + 15 * 60000 ? 'ok' : 'warn', 'สแกนทั้งกระดาน', `${S.total || 0} เหรียญ`, ago(st));
      tile(el, 'ok', 'แท่ง 4 ชม. ปิดใน', cd(next4h()), 'บอทตัดสินใจตอนแท่งปิด');
      const jt = since(sys.judge_at);
      tile(el, jt != null && jt < 30 * 3600000 ? 'ok' : 'warn', 'ทดสอบกลยุทธ์', cd(nextUtc(sys.judge_utc)), 'ทุกคืน 22:43');
      const bt = since(sys.brief_at);
      tile(el, bt == null || bt < 30 * 3600000 ? 'ok' : 'warn', 'สรุปเช้า Telegram', cd(nextUtc(sys.brief_utc)), 'ทุกเช้า 07:05');
    }
    // GitHub Actions live
    const ga = $('#sys-runs');
    if (ga) {
      ga.replaceChildren();
      if (!runs) { ga.append(mk('span', 'gh-sum', runsErr ? 'ดึงสถานะจาก GitHub ไม่ได้' : 'กำลังดึงสถานะ…')); }
      else {
        const NAME = {'bot-loop': 'บอทวนรอบ', nightly: 'งานกลางคืน', 'paper-bot': 'บอทสำรอง'};
        const shown = runs.filter((w) => w.conclusion !== 'cancelled').slice(0, 4);   // ยกเลิก = รีสตาร์ทตามปกติ ไม่ต้องแสดง
        const fails = runs.filter((w) => w.conclusion === 'failure' && since(w.updated_at) < 86400000).length;
        for (const w of shown) {
          const running = w.status !== 'completed', okc = w.conclusion === 'success';
          const row = mk('a', 'gh-run ' + (running ? 'run' : okc ? 'ok' : 'bad'));
          row.href = w.html_url; row.target = '_blank'; row.rel = 'noopener';
          row.title = running ? 'กำลังทำงาน' : okc ? 'สำเร็จ' : 'ล้มเหลว';
          row.append(mk('span', 'gh-ic', running ? '' : okc ? '✓' : '✕'), mk('span', 'gh-n', NAME[w.name] || w.name),
            mk('span', 'gh-s', running ? 'ทำงาน ' + ago(since(w.run_started_at || w.created_at)).replace('ที่แล้ว', '') : ago(since(w.updated_at))));
          ga.append(row);
        }
        ga.append(mk('span', 'gh-sum ' + (fails ? 'bad' : 'ok'), fails ? `ล้มเหลว ${fails} ครั้งใน 24 ชม.` : 'ไม่มีงานล้มเหลวใน 24 ชม.'));
      }
    }
    // activity feed
    const af = $('#sys-activity');
    if (af && d.activity) {
      const key = d.activity.length + (d.activity[0] || {}).time;
      if (af.dataset.key !== key) {
        af.dataset.key = key; af.replaceChildren();
        const KIND = {tick: 'info', buy: 'buy', sell: 'sell', sentinel_halt: 'warn', sentinel_reject: 'warn', error: 'warn', signals: 'info', universe: 'info', sentinel_resume: 'info'};
        for (const a of d.activity.slice(0, 25)) {
          const row = mk('div', 'ev ' + (KIND[a.kind] || 'info')); const h = mk('div', 'h');
          h.append(mk('span', null, a.text), mk('span', 't', thTime(a.time))); row.append(h); af.append(row);
        }
      }
    }
    // top-bar heartbeat
    const chip = $('#sys-chip');
    if (chip) { const lt2 = since(sys.last_bot_tick), healthy = lt2 != null && lt2 < (sys.tick_every_min + 10) * 60000;
      chip.className = 'chip ' + (healthy ? 'up' : 'paper'); chip.textContent = `⚙ บอทรอบถัดไป ${cd(nextTick(sys.tick_every_min, sys.tick_offset_min))}`;
      chip.title = `บอทรันล่าสุด ${ago(lt2)}`; }
  }

  function init() {
    setInterval(render, 1000);
    setInterval(fetchRuns, 90000); setTimeout(fetchRuns, 2500);
    setInterval(heartbeat, 30000); setTimeout(heartbeat, 5000);
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
