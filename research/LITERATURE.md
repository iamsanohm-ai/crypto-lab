# ฐานความรู้จากงานวิจัย (ใช้โดย Scout/Judge ทุกคืน)

รวบรวมเมื่อ 2026-11-22 · เน้นงานที่ผ่าน peer review (Journal of Finance, JFQA, Finance Research Letters ฯลฯ) · งานที่เป็น working paper/preprint ระบุไว้
**กติกา:** ข้อค้นพบจากงานวิจัยเป็น "สมมติฐานที่มีเหตุผล" ไม่ใช่ข้อพิสูจน์ — ทุกข้อต้องผ่าน walk-forward + final check ของเราบนข้อมูล Binance ก่อนใช้

## 1. Momentum / trend following — หลักฐานแข็งแรงที่สุด
- **Liu, Tsyvinski & Wu (2022), Journal of Finance** — "Common Risk Factors in Cryptocurrency": ตลาด, ขนาด และ **momentum** อธิบายผลตอบแทนข้ามเหรียญได้; momentum 1–4 สัปดาห์มีนัยสำคัญ · [Yale PDF](https://economics.yale.edu/sites/default/files/2022-10/LiuTsyvinskiWu2019%20COMMON%20RISK%20FACTORS.pdf) · [NBER](https://www.nber.org/system/files/working_papers/w25882/w25882.pdf)
- **Fieberg, Liedtke, Poddig, Walker & Zaremba (2025), JFQA** — "A Trend Factor for the Cross Section of Cryptocurrency Returns" (CTREND): รวมสัญญาณราคา+volume หลายช่วงเวลา, อยู่รอดหลังต้นทุน และยังได้ผลในเหรียญใหญ่ที่สภาพคล่องสูง · [Cambridge](https://www.cambridge.org/core/journals/journal-of-financial-and-quantitative-analysis/article/trend-factor-for-the-cross-section-of-cryptocurrency-returns/4C1509ACBA33D5DCAF0AC24379148178) · [PDF](https://jfqa.org/wp-content/uploads/2024/09/24955-trend-factor-cross-section-crypto-returns.pdf)
- **Fieberg, Liedtke, Metko & Zaremba (2023), Quantitative Finance** — factor momentum ใน crypto มาจาก price momentum · [RePEc](https://ideas.repec.org/a/taf/quantf/v23y2023i12p1853-1869.html)
- Time-series momentum: มีอยู่จริง แต่**ต้นทุนกินกำไรมากเมื่อถือสั้น/rebalance บ่อย** — ได้ผลดีกว่าที่ความถี่ต่ำ · [AUT](https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf) · [Springer](https://www.springerprofessional.de/en/time-series-momentum-trading-strategy-for-cryptocurrencies/26140838) · [Reading: BTC intraday TSMOM](https://centaur.reading.ac.uk/100181/3/21Sep2021Bitcoin%20Intraday%20Time-Series%20Momentum.R2.pdf)
- **สอดคล้องกับผลของเรา:** ทั้ง 3 ตัวที่ผ่าน (keltner, golden cross, breakout) เป็น trend-following

## 2. Reversal — ใช้ได้กับเหรียญเล็ก/สภาพคล่องต่ำเท่านั้น
- เหรียญใหญ่ที่สุดมี **daily momentum** ไม่ใช่ reversal; reversal มาจากความไม่มีสภาพคล่อง · [Finance Research Letters/IRFA 2021](https://www.sciencedirect.com/science/article/pii/S1057521921002349)
- Reversal กระจุกในคู่ที่ volume ต่ำ = ค่าตอบแทนของผู้ให้สภาพคล่อง · [Bianchi, Babiak & Dickerson, J. Banking & Finance](https://www.sciencedirect.com/science/article/abs/pii/S0378426622001418)
- **สอดคล้องกับผลของเรา:** mean-reversion ทุกแบบใน top-20 ล้มเหลว (rsi2 −18%, bb −2%) → **อย่าเสียเวลากับ reversal ใน universe นี้**

## 3. Funding rate
- funding ติดลบสุดขั้ว → ผลตอบแทน BTC 24 ชม. ถัดไปเป็นบวกอย่างมีนัยสำคัญ แต่ความสัมพันธ์ไม่เป็นเส้นตรงและขึ้นกับช่วงเวลา · [ResearchGate: Perpetual Futures Pricing](https://www.researchgate.net/publication/397830745_Perpetual_Futures_Pricing) · [SSRN: Predictability of Funding Rates](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5576424)
- กำไรจาก carry (short perp + long spot) ลดลงตามเวลา · [arXiv 2510.14435](https://arxiv.org/pdf/2510.14435) · [ScienceDirect: funding arbitrage CEX/DEX](https://www.sciencedirect.com/science/article/pii/S2096720925000818)
- **ผลของเรา:** funding_negative_extreme บน altcoin −33% → งานวิจัยพูดถึง **BTC** ไม่ใช่ alt; ควรทดสอบเฉพาะ BTC/ETH ถือ 24 ชม.

## 4. Volatility targeting (ขนาดไม้ตามความผันผวน)
- หลักฐานส่วนใหญ่จาก practitioner/working paper: ลด drawdown และเพิ่ม Sharpe ใน backtest · [SSRN Karassavidis (WP)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5821842) · [Grayscale](https://research.grayscale.com/reports/beyond-volatility-rethinking-crypto-risk-for-portfolio-managers)
- ระบบเรามีแล้วบางส่วน (ขนาดไม้ = 0.5% / ระยะ ATR stop) — ทดสอบเพิ่ม: ลดขนาดรวมเมื่อ volatility ของ BTC สูง

## 5. Technical analysis & data snooping — เหตุผลที่ต้องหวาดระแวง
- งานหนึ่งพบกฎ TA ~15,000 กฎทำกำไรใน crypto แต่อีกงานที่ใช้ White's Reality Check พบว่า **"ผลตอบแทนส่วนเกินที่มีนัยสำคัญเกิดขึ้นน้อยมาก"** · [Finance Research Letters 2020](https://www.sciencedirect.com/science/article/abs/pii/S1544612320304414)
- พลังของ Reality Check ลดลงเมื่อใส่กฎที่ไม่เกี่ยวข้องเข้าไปมาก → ใช้ Hansen SPA หรือ Deflated Sharpe · [Hansen SPA](https://www.researchgate.net/publication/256066609_Re-Examining_the_Profitability_of_Technical_Analysis_with_White's_Reality_Check_and_Hansen's_SPA_Test)
- **ผลต่อระบบ:** Judge ต้องรายงาน **Deflated Sharpe Ratio** (ปรับตามจำนวนไอเดียที่ทดสอบ) ทุกคืน

## 6. Machine learning / AI
- มีงานที่รายงาน Sharpe สูงหลังต้นทุน (LSTM/GRU) · [ScienceDirect 2022](https://www.sciencedirect.com/science/article/pii/S2405918822000174) · [Filippou, Rapach & Thimsen (WP)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3914414)
- แต่ภาพรวม: ML **ไม่ค่อยชนะโมเดลง่ายๆ นอกตัวอย่าง** และ edge ทางสถิติมักหายไปเมื่อหักต้นทุน; R² สูงมาจาก daily reversal ในเหรียญเล็ก · [arXiv 2606.00071 review](https://arxiv.org/pdf/2606.00071) · [arXiv 2606.00060: ML BTC walk-forward with costs](https://arxiv.org/html/2606.00060v1)
- **ผลต่อระบบ:** ยังไม่ใช้ ML จนกว่าโมเดลง่ายจะถึงขีดจำกัด; ระวัง "AI trading bot" ที่โฆษณาบน YouTube (มักเป็น scam)

## 7. Seasonality (เวลาของวัน/วันในสัปดาห์)
- มีรูปแบบเวลาของวัน (UTC เช้าต่ำ, บ่าย-ค่ำสูง) · [Springer 2024](https://link.springer.com/article/10.1007/s11156-024-01304-1) · [Reading](https://centaur.reading.ac.uk/81745/3/2.R%26R.Manuscript.pdf)
- Monday/weekend effect **หายไปหลังปี 2015** · [FRL 2024](https://www.sciencedirect.com/science/article/pii/S1544612324004598) · [Baur et al. 2019](https://www.sciencedirect.com/science/article/abs/pii/S1544612319301710)
- **ผลต่อระบบ:** แท่ง 4h ใช้ประโยชน์ได้น้อย; อาจใช้เลือกเวลา execution เท่านั้น

## คิวไอเดียสำหรับ Scout (เรียงตามความน่าเชื่อถือของหลักฐาน)
1. `ctrend_xs` — CTREND แบบง่าย: คะแนนรวมของราคาเทียบ MA หลายช่วง (5/10/20/50/100/200 วัน) + volume, ถือ top 3–5, rebalance รายสัปดาห์, กรองด้วย BTC regime
2. `tsmom_weekly` — time-series momentum 4 สัปดาห์ rebalance รายสัปดาห์ (ความถี่ต่ำ ลดต้นทุน)
3. `xs_momentum_4w` — cross-sectional momentum 4 สัปดาห์ตาม Liu-Tsyvinski-Wu
4. `btc_funding_extreme` — BTC/ETH เท่านั้น, funding ติดลบสุดขั้ว → ถือ 24 ชม.
5. `vol_target_overlay` — ลดขนาดไม้ทั้งพอร์ตเมื่อ realized vol ของ BTC สูงกว่าค่ากลาง (ทดสอบกับ champion)
6. Judge: เพิ่ม Deflated Sharpe Ratio ใน final check
