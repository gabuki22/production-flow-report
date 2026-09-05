"""
작업일보 생성 — 6공정 · 우리 12개월

⚠️ 합성이다. 성우산업 실제 작업일보가 아니다.

**왜 만드는가**
  인건비를 개당으로 내리려면 **총 인건비 ÷ 총 생산 개수**가 필요하다.
  개당 CT × 시급으로는 매출 대비 30%가 나오지 않는다(개당 8원 = 매출의 0.6%).
  현장의 "인건비 30%"는 **총액 배부**이므로 생산 개수가 있어야 한다.

**기존 자산**
  EDATA7기 worklog_{6공정}.csv 가 이미 있다 — 2,322행 · 2026-04~06 3개월.
  컬럼 구조(작업일보ID·생산일자·제품도번·호기라인·시작·종료·셋업시간분·
  작업시간분·계획수량·생산수량)를 **그대로 따르고 우리 12개월로 확장**한다.

**현장 실측 반영 (2026-08-29)**
  - 사출 40초/사이클 ÷ 캐비티 · 도장 20초/판 ÷ 지그당적재
  - "가동 중 CT는 실효와 거의 같다" → 가동 중에는 설비 CT 그대로
  - 손실은 **교체시간**에 집중: 레이저 판당 5~7초 · 도장 15분/건
  - 원본 작업일보는 케비티 미반영이라 사출 27.4초·도장 24.6초로 과다했다

작성: 2026-08-29 · 보완프롬프트-3 B 후속
"""
from pathlib import Path
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
SEED = 20260829_4

# 설비 CT — 현장 실측. 사출·도장은 사이클/판 단위라 케비티로 나눈다.
CYCLE_CT = {"사출": 40.0, "도장": 20.0}
PER_PIECE_CT = {"지그삽입": 2.0, "레이저": 17.0 / 8.5, "인쇄": 3.0, "검사": 4.0}

# 교체(셋업) — 현장 실측. **건당 고정 시간**이라 로트가 작을수록 개당 부담이 커진다.
SETUP_MIN = {"사출": 30.0,      # "제품 교체시간이 오래 걸리는 편" — 구체값 미확인, 30분 가정
             "지그삽입": 5.0,
             "도장": 15.0,      # ★ 현장 실측 "교체시간 15분"
             "레이저": 6.0 / 60 * (3600 / 17),   # 판당 5~7초 → 건당 환산은 아래에서
             "인쇄": 8.0,
             "검사": 5.0}
LASER_CHANGE_SEC_PER_PLATE = 6.0    # ★ 현장 실측 5~7초/판
LASER_PCS_PER_PLATE = 8.5

# 계획 대비 달성 — 원본 작업일보 실측(중앙 95%·미달 83~86%)을 따른다
ACHIEVE_MEAN, ACHIEVE_SD = 0.95, 0.06

# 1건당 로트 크기 — ★ 한 수주는 여러 일자에 나눠 작업된다.
#   1차에서 수주 전량을 1건에 넣었더니 작업일보가 수주와 1:1이 됐다.
#   실제 작업일보는 "그날 그 설비에서 만든 만큼"이라 한 수주가 여러 건으로 쪼개진다.
LOT_PER_DAY = (400, 1200)           # 일자당 작업 수량

WORK_START = ["08:00", "09:00", "10:00"]   # 원본과 동일하게 3종

HERE = Path(__file__).resolve().parent
from _src import SRC                             # 값 풀 출처 → _src.py
OUT = HERE / "data"

PROCESSES = ["사출", "지그삽입", "도장", "레이저", "인쇄", "검사"]
LINE_PREFIX = {"사출": "IM", "지그삽입": "JG", "도장": "PT",
               "레이저": "LS", "인쇄": "PR", "검사": "QC"}


def part_ct(ms, im, jm):
    """도번별 공정 CT(초/개) — 케비티 반영"""
    d = (ms[["제품도번", "사출도번"]]
         .merge(im[["사출도번", "캐비티수"]], on="사출도번", how="left")
         .merge(jm[["제품도번", "지그당적재"]], on="제품도번", how="left"))
    ct = pd.DataFrame({"제품도번": d["제품도번"]})
    ct["사출"] = CYCLE_CT["사출"] / d["캐비티수"].fillna(1).clip(lower=1)
    ct["도장"] = CYCLE_CT["도장"] / d["지그당적재"].fillna(1).clip(lower=1)
    for k, v in PER_PIECE_CT.items():
        ct[k] = v
    return ct.set_index("제품도번")


def main():
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)

    o = pd.read_csv(OUT / "orders.csv", parse_dates=["수주일"])
    e = pd.read_csv(OUT / "order_events.csv", parse_dates=["이벤트일"])
    ms = pd.read_csv(SRC / "master.csv")
    im = pd.read_csv(SRC / "injection_master.csv")
    jm = pd.read_csv(SRC / "jig_master.csv")

    # 도번 확장분은 원본 35개에서 CT 를 물려받는다
    base_ct = part_ct(ms, im, jm)
    parts = sorted(o["제품도번"].unique())
    idx = rng.integers(0, len(base_ct), len(parts))
    ct = base_ct.iloc[idx].copy()
    ct.index = parts
    for p in parts:
        if p in base_ct.index:
            ct.loc[p] = base_ct.loc[p]

    # 공정작업에 도달한 수주만 작업일보가 생긴다
    proc = (e[e["이벤트구분"] == "공정작업"][["수주ID", "이벤트일"]]
            .drop_duplicates("수주ID"))
    base = o.merge(proc, on="수주ID", how="inner")
    print("=" * 68)
    print("  작업일보 생성  (⚠️ 합성 — 실측 아님)")
    print("=" * 68)
    print(f"\n대상 수주 {len(base):,}건 (공정작업 도달분)")

    frames = {}
    for pi, p in enumerate(PROCESSES):
        # 수주를 일자별 로트로 쪼갠다 — 한 수주가 여러 작업일보 건이 된다
        rows = []
        for r in base.itertuples(index=False):
            remain, day = int(r.수량), pd.Timestamp(r.이벤트일)
            while remain > 0:
                q = min(remain, int(rng.integers(*LOT_PER_DAY)))
                rows.append((r.수주ID, r.제품도번, day, q))
                remain -= q
                day += pd.Timedelta(days=1)
        lots = pd.DataFrame(rows, columns=["수주ID", "제품도번", "생산일자", "로트수량"])
        n = len(lots)
        lot = lots["로트수량"].to_numpy()
        ct_p = ct.loc[lots["제품도번"], p].to_numpy()

        # 셋업 — 레이저는 판당 교체시간을 로트에 맞춰 환산
        if p == "레이저":
            plates = np.ceil(lot / LASER_PCS_PER_PLATE)
            setup = plates * LASER_CHANGE_SEC_PER_PLATE / 60
        else:
            setup = np.full(n, SETUP_MIN[p]) * rng.uniform(0.7, 1.3, n)

        # 계획 대비 달성 — 실측 중앙 95%
        ach = np.clip(rng.normal(ACHIEVE_MEAN, ACHIEVE_SD, n), 0.5, 1.0)
        made = (lot * ach).round().astype(int)

        work_min = made * ct_p / 60 * rng.uniform(0.95, 1.08, n)   # 가동 중 변동 ±
        start = rng.choice(WORK_START, n)
        end_h = np.clip(8 + np.ceil((work_min + setup) / 60), 9, 22).astype(int)

        df = pd.DataFrame({
            "작업일보ID": [f"{p}{i:06d}" for i in range(1, n + 1)],
            "생산일자": lots["생산일자"].dt.date.to_numpy(),
            "제품도번": lots["제품도번"].to_numpy(),
            "호기라인": [f"{LINE_PREFIX[p]}{k}" for k in rng.integers(1, 5, n)],
            "시작": start,
            "종료": [f"{h:02d}:00" for h in end_h],
            "셋업시간분": setup.round(1),
            "작업시간분": work_min.round(1),
            "계획수량": lot,
            "생산수량": made,
            "수주ID": lots["수주ID"].to_numpy(),
        })
        frames[p] = df
        df.to_csv(OUT / f"worklog_{p}.csv", index=False, encoding="utf-8-sig")

        run = (df["작업시간분"] * 60 / df["생산수량"]).median()
        full = ((df["작업시간분"] + df["셋업시간분"]) * 60 / df["생산수량"]).median()
        print(f"  {p:<6}{len(df):>7,}행  생산 {df['생산수량'].sum():>10,}개  "
              f"가동 {run:>5.2f}초/개  셋업포함 {full:>5.2f}초/개  (+{(full/run-1)*100:>4.1f}%)")

    # ★ 공정별 생산량은 같은 물건이 6번 지나간 것이라 합치면 안 된다
    tot_pcs = frames["검사"]["생산수량"].sum()      # 최종 공정 = 실제 완성 개수
    tot_min = sum((f["작업시간분"] + f["셋업시간분"]).sum() for f in frames.values())
    print(f"\n  ★ 최종 생산량(검사 통과) {tot_pcs:,}개 — 공정별 합계로 세면 6배가 된다")
    print(f"    총 작업 {tot_min/60:,.0f}시간 (6공정 합)")

    # ── 인건비 총액 배부 ──
    o2 = pd.read_csv(OUT / "orders.csv")
    sales = (o2["수량"] * pd.read_csv(OUT / "product_cost_bom.csv")
             .set_index("제품도번")["판매단가"].reindex(o2["제품도번"]).to_numpy()).sum()
    print(f"\n[인건비 총액 배부] — 개당 CT 로는 안 되던 것")
    print(f"  총 매출 {sales/1e8:,.1f}억")
    for label, ratio in [("인건비", 0.30), ("가공비", 0.225)]:
        total = sales * ratio
        print(f"  {label} 매출의 {ratio*100:.1f}% = {total/1e8:>6.1f}억 "
              f"→ 개당 {total/tot_pcs:>6.1f}원  (생산 {tot_pcs:,}개로 나눔)")
    hourly = sales * 0.30 / (tot_min / 60)
    print(f"\n  검산: 인건비 총액 ÷ 총 작업시간 = 시간당 {hourly:,.0f}원")
    print(f"        {'✅ 현실권 (시급+간접 포함)' if 8000 <= hourly <= 60000 else '⚠️ 확인 필요'}")
    print(f"\n출력: {OUT}")


if __name__ == "__main__":
    main()
