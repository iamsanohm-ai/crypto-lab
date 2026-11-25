"""ORB score: คะแนน 0–100 ต่อเหรียญ — สูตรแบบ "weighted clamp + cap" (ไม่ใช่การทำนาย แค่จัดลำดับความน่าสนใจตามกฎของระบบ)

ส่วนประกอบ k:  s_k = round(10 · w_k · clamp((b_k − x_k) / (b_k − g_k), 0, 1)) / 10
    w_k = น้ำหนักสูงสุด, x_k = ค่าที่วัดได้, g_k = เกณฑ์ได้คะแนนเต็ม, b_k = เกณฑ์ได้ศูนย์
RawScore = round(Σ s_k)
CapFlag = 1 ถ้าเข้าเงื่อนไขเสี่ยงข้อใดข้อหนึ่ง → FinalScore = min(RawScore, 100 − 41 · CapFlag)  (คือไม่เกิน 59)
"""
from __future__ import annotations

import math

# name: (weight, full-score threshold g, zero-score threshold b, label)
COMPONENTS = {
    "trend":     (25, 15.0, -10.0, "แนวโน้ม: ราคาเทียบ EMA200 (%)"),
    "momentum":  (20, 40.0, -20.0, "Momentum 30 วัน (%)"),
    "liquidity": (20, math.log10(50e6), math.log10(2e6), "สภาพคล่อง: volume 24 ชม. (log10 USDT)"),
    "volatility": (15, 1.5, 6.0, "ความผันผวน: ATR 4h (% ของราคา) — ต่ำดีกว่า"),
    "entry":     (20, 0.0, 10.0, "ระยะห่างถึงจุดเข้า Keltner (%) — ใกล้ดีกว่า"),
}
CAP_REASONS = {
    "illiquid": "สภาพคล่องต่ำกว่า 2 ล้าน USDT/วัน",
    "btc_down": "BTC อยู่ใต้ EMA200 (ตลาดขาลง — บอทไม่เปิดสถานะ)",
    "below_ema200": "เหรียญอยู่ใต้ EMA200 ของตัวเอง",
    "no_data": "ข้อมูลไม่พอ (เหรียญใหม่ < 200 แท่ง)",
}


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def component(name: str, x: float | None) -> float:
    w, g, b, _ = COMPONENTS[name]
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return 0.0
    return round(10 * w * clamp((b - x) / (b - g))) / 10


def score(metrics: dict, caps: list[str]) -> dict:
    comps = {k: component(k, metrics.get(k)) for k in COMPONENTS}
    raw = round(sum(comps.values()))
    cap_flag = 1 if caps else 0
    return {"score": min(raw, 100 - 41 * cap_flag), "raw": raw, "components": comps, "caps": caps}
