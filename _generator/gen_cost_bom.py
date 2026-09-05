"""
BOM 기반 원가 전개 (roll-up) — mydomain

⚠️ 합성이다. 성우산업 실제 원가가 아니다.

**gen_cost_defect.py 와의 차이**
  기존: 판매단가 × "평균 이익률 8%" 라는 **가정**에서 원가를 역산
  여기: BOM 원단위 × 자재단가 를 **아래에서 위로 쌓아** 원가를 만든다

  09_판정에서 확인했듯 이익률 8%는 🔴 결정적 가정이었다 —
  8%→12% 로 바꾸면 적자 도번이 17.6% → 2.2% 로 사라진다.
  BOM 전개는 그 가정을 없앤다(대신 다른 가정이 그 자리에 온다 — §5 민감도).

**재료 (EDATA7기 위키 · 전부 기존 자산)**
  product_bom      제품도번별 수지g·페인트g·트레이구수·박스입수
  process_bom      공정별 자재 개당원단위 (신나·잉크 포함)
  resource_master  자재 단가 + ★연결코드(PT↔RES 매핑)
  material_master  부자재 단가
  cost_master      공정별 시간당 가공비·인건비·간접비배부율
  loss_factor      도번별 로스보정계수
  master           공정별 CT(초/개)

작성: 2026-08-29 · 보완프롬프트-3 B
"""
from pathlib import Path
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────
SEED = 20260829_3

# 로스보정계수를 어디에 곱하는가 — 판단이 필요한 지점이다.
#   불량이 나면 **자재는 버려지지만 이미 쓴 공수도 회수되지 않는다.**
#   즉 재료·가공·인건 모두 로스만큼 더 든다. 경비는 배부라 자동 반영된다.
#   ⚠️ 기존 gen_cost_defect 는 이 문제를 다루지 않았다(이익률에서 역산했으므로).
LOSS_ON = {"재료비": True, "가공비": True, "인건비": True}

# 공정명 정규화 — process_bom '출하검사' ↔ cost_master '검사'
PROCESS_ALIAS = {"출하검사": "검사"}

# 도번 pool 확장 시 (mydomain 은 1,200 도번, BOM 은 35)
N_PARTS_TARGET = 1200

# ★ 현장 실측 단가 (2026-08-29) — 합성 단가를 덮어쓴다.
#   합성 resource_master 단가가 실제와 크게 달랐다:
#     도료   합성 8,648~19,539원/kg  vs  실제 4L에 15만원 = 약 28,846원/kg (1.8배)
#     트레이  합성 417~1,891원/장     vs  실제 200원/장 (합성의 16%)
PAINT_PRICE_PER_L = 150000 / 4          # 4리터 15만원
PAINT_DENSITY = 1.3                     # g/mL — 도료 통상
# ★ 도료 개당 사용량 — 현장 실측 "4리터로 2,000개 정도"
#   합성 product_bom 의 원단위_페인트g(평균 12.4g)는 과다했다.
#   150,000원 ÷ 2,000개 = 개당 75원 → 원단위 환산 2.6g/개 (합성의 21%)
#   ★ 도번별 편차는 원단위 비율을 그대로 살려 반영한다(큰 부품은 더 쓴다).
PAINT_PCS_PER_CAN = 2000
PAINT_CAN_L = 4
TRAY_PRICE = 200                        # 원/장 (200~500, 보통 200)
TRAY_REUSE = 0.10                       # 재사용률 10% → 90%만 원가에 반영

# ★ 포장 보조자재 — 현장 실측 월 사용량 (2026-08-29)
#   월 총액을 월 생산량으로 나눠 개당으로 내린다. 개당 원단위를 모르기 때문이다.
INTERLEAF_MONTHLY = (8000, 90)          # 간지  월 8,000장 × 90원
FOAM_MONTHLY = (25000, 22)              # 발포지 월 25,000장 × 22원

# ★ 비닐 — 2026-09-02 현장 확인으로 신설. 8/29에는 "잘 모르겠다" 하셔서 빠져 있었다.
#   단가만으로는 개당 원가가 안 나온다. **무엇 하나당 1장인지**가 300배를 가른다.
#       제품 1개당 1장   50.00원  (재료비의 24.4% — 페인트 다음으로 큰 자재가 된다)
#       트레이 1판당      1.04원
#       박스 1개당        0.17원  ← 현장에서 고른 것
#   그래서 박스 입수(트레이구수 × 박스입수_트레이, 중앙값 288개)로 나눈다.
#   트레이·박스와 같은 방식이다 — 판값을 담기는 개수로 나눈다.
VINYL_PRICE = 50                        # 원/장 (현장 확인 2026-09-02)
VINYL_PER = "박스"                      # 비닐 1장이 담는 단위 — 박스 1개당 1장

# ★ 수지 소요량 — 사내 실측 (2026-08 원재료 인상 대응 · 전수 2,561건 · 원문 비공개)
#   "예) 개당중량 14.81 · 런너 13.85 · CAV 2 → ERP 43.47 / 고객사 21.7"
#   ERP 소요량 = 개당중량 × Cavity + 런너중량   (2,561건 전수 확인 · 불일치 0)
#
#   ★★ 두 가지를 바로잡는다:
#     1) 개당 제품중량 14.81g — 합성 원단위(평균 67.3g)는 4.5배 과다했다
#     2) **런너를 아예 안 넣었다.** 사출은 제품 외에 런너가 같이 나오고
#        그것도 수지를 쓴다. 런너/제품 비율이 14.81 : 13.85 ≈ 0.94 로 거의 1:1이다.
#
#   소요량(개당) = 제품중량 + 런너중량 / Cavity
#   ⚠️ ERP 식은 "샷당"이라 Cavity 를 곱하지만, 개당으로 내리려면 런너만 나눈다.
PART_WEIGHT_G = 14.81                   # 개당 제품중량 (볼트 실측 예시)
RUNNER_WEIGHT_G = 13.85                 # 샷당 런너중량 (〃)

HERE = Path(__file__).resolve().parent
from _src import SRC                             # 값 풀 출처 → _src.py
OUT = HERE / "data"

# ★ 공정 CT — 현장 기준(2026-08-29). 합성 master.csv 의 CT 는 쓰지 않는다.
#   "사출 1사이클 40초(케비티마다 다름) · 지그삽입 개당 2초 ·
#    도장 1분에 3판=20초/판(케비티마다 다름) · 레이저 개당 1~2초 ·
#    인쇄 개당 3초 · 검사 개당 4초"
#
#   ★★ 사출·도장은 **사이클/판 단위**다. 케비티로 나눠야 개당이 된다.
#      합성 master.csv 는 이걸 반영 안 해 CT 합이 58.4초/개였다 —
#      케비티를 반영하면 23.7초로 41% 수준이다.
CYCLE_CT = {"사출": 40.0, "도장": 20.0}          # 케비티(캐비티수·지그당적재)로 나눈다
PER_PIECE_CT = {"지그삽입": 2.0, "레이저": 1.5, "인쇄": 3.0, "검사": 4.0}


def load():
    f = lambda n: pd.read_csv(SRC / n)
    return (f("product_bom.csv"), f("process_bom.csv"), f("resource_master.csv"),
            f("material_master.csv"), f("cost_master.csv"), f("loss_factor.csv"),
            f("master.csv"), f("injection_master.csv"), f("jig_master.csv"))


# 단위 환산 — ★ 여기서 두 번 틀렸다. 기록해 둔다.
#   1차: 포장단위로만 나눔 → 원/kg 을 g 원단위에 곱해 **1,000배**.
#        총원가 19,581원 vs 판매단가 1,361원 → 이익률 −3,123% 로 터졌다.
#   2차: kg→g 는 고쳤으나 **포장단위로 나눈 것을 그대로 뒀다** → 이번엔 1/20~1/100.
#        재료비가 20.5원(구성비 16.6%)까지 떨어져 현장 기준 40%와 크게 어긋났다.
#
#   ★ 실제 시세로 검산해 밝혔다:
#     PP/PC 수지 kg당 2,000~4,000원 · 자동차 도료 kg당 1~2만원 · 트레이 개당 수백~수천원
#     → resource_master.단가는 **단위(kg·개)당**이고, 포장단위는 **발주 로트**일 뿐이다.
#       나누면 안 된다. kg→g 환산만 한다.
#
#   ★ 교훈: BOM 전개는 단위가 전부다. 그리고 **단위는 실제 시세로 검산해야** 안다.
#     데이터 안에서는 어느 해석이 맞는지 알 수 없었다.
UNIT_TO_BOM = {"kg": 1000.0, "g": 1.0, "개": 1.0, "ea": 1.0}


def unit_price(rm, mm):
    """자재코드 → **BOM 원단위 1 단위당** 가격.

    포장단위로 나눠 낱개 단가를 만들고, 다시 단위 배수로 나눈다.
      3,277원 / 25kg = 131.1원/kg → ÷1000 = 0.1311원/g

    ★ resource_master.연결코드 가 PT-xxx ↔ RES-xxx 매핑표다.
      product_bom·process_bom 은 PT 코드를 쓰고 단가는 RES 쪽에 있다.
      추측으로 잇지 않고 이 컬럼을 쓴다.
    """
    p = {}
    for _, r in rm.iterrows():
        # ★ 포장단위로 나누지 않는다. 단가는 이미 **단위(kg·개)당**이다.
        per = r["단가"] / UNIT_TO_BOM.get(str(r["단위"]).strip(), 1.0)
        p[r["자재코드"]] = per
        if isinstance(r.get("연결코드"), str) and r["연결코드"]:
            p[r["연결코드"]] = per            # PT-104 로도 찾을 수 있게
    for _, r in mm.iterrows():
        p.setdefault(r["자재코드"], r["단가"])
    return p


def material_cost(pb, pcb, price, cavity):
    """재료비 — product_bom(수지·페인트·트레이·박스) + process_bom(신나·잉크 등)"""
    rows = []
    # 현장 실측 단가로 환산 — 도료는 원/g, 트레이는 재사용분을 뺀다
    # 개당 도료비를 현장 실측(4L=2,000개)에서 정하고, 도번별 편차는 원단위 비율로
    paint_cost_avg = PAINT_PRICE_PER_L * PAINT_CAN_L / PAINT_PCS_PER_CAN   # 개당 75원
    unit_avg = pb["원단위_페인트g"].mean()
    tray_per_sheet = TRAY_PRICE * (1 - TRAY_REUSE)
    # 수지 소요량 — 볼트 실측 기준으로 재계산. 도번별 편차는 원단위 비율로 살린다.
    unit_avg_resin = pb["원단위_수지g"].mean()
    for _, r in pb.iterrows():
        cav = max(cavity.get(r["사출도번"], 4), 1)
        소요량 = (PART_WEIGHT_G + RUNNER_WEIGHT_G / cav) * (r["원단위_수지g"] / unit_avg_resin)
        수지 = price.get(r["원재료코드"], np.nan) * 소요량
        페인트 = paint_cost_avg * (r["원단위_페인트g"] / unit_avg)
        트레이 = tray_per_sheet / max(r["트레이구수"], 1)
        박스입수 = max(r["트레이구수"] * r["박스입수_트레이"], 1)
        박스 = price.get(r["박스코드"], np.nan) / 박스입수
        비닐 = VINYL_PRICE / 박스입수          # 박스 1개당 1장
        rows.append({"제품도번": r["제품도번"], "수지": 수지, "페인트": 페인트,
                     "트레이": 트레이, "박스": 박스, "비닐": 비닐})
    m = pd.DataFrame(rows)

    # process_bom 은 g/ml 단위 개당원단위 — 낱개 단가에 곱한다
    pcb = pcb.copy()
    pcb["단가"] = pcb["자재코드"].map(price)
    pcb["금액"] = pcb["단가"] * pcb["개당원단위"]
    extra = (pcb[pcb["자재구분"].isin(["신나", "잉크"])]
             .groupby("제품도번")["금액"].sum().rename("신나잉크"))
    m = m.merge(extra, on="제품도번", how="left")
    m["신나잉크"] = m["신나잉크"].fillna(0)
    # 포장 보조자재 — 월 총액 ÷ 월 생산량
    o = pd.read_csv(OUT / "orders.csv", parse_dates=["수주일"])
    days = (o["수주일"].max() - o["수주일"].min()).days
    monthly_pcs = o["수량"].sum() / days * 20          # 20영업일
    간지 = INTERLEAF_MONTHLY[0] * INTERLEAF_MONTHLY[1] / monthly_pcs
    발포지 = FOAM_MONTHLY[0] * FOAM_MONTHLY[1] / monthly_pcs
    m["간지"] = 간지
    m["발포지"] = 발포지
    m["재료비"] = m[["수지", "페인트", "트레이", "박스", "비닐",
                    "신나잉크", "간지", "발포지"]].sum(axis=1)
    return m


# ★ 인건비·가공비 배부 (2026-08-29 확정)
#   개당 CT × 시급으로는 매출 대비 30% 가 안 나온다 — 개당 8원 = 매출의 0.6% 였다.
#   현장의 "인건비 30% · 가공비 22.5%"는 **매출 대비 총액 배부**다(현장 확인).
#   → 작업일보(gen_worklog.py)의 총 생산량으로 나눠 개당으로 내린다.
#     검산: 인건비 총액 ÷ 총 작업시간 = 시간당 52,069원 (간접 인원 포함 총액 기준)
LABOR_RATIO = 0.300        # 매출 대비 인건비
MFG_RATIO = 0.225          # 매출 대비 가공비 (설비비·전기료·인건·소모품·유지비)
MATERIAL_RATIO = 0.400     # 매출 대비 재료비 — 판매단가를 여기서 역산한다

# ★ 판매단가 재구성 (2026-08-29)
#   합성 master.csv 단가(243~4,909원 · 평균 1,361원)는 우리 BOM 재료비와 안 맞았다.
#   제품중량 14.81g · 수지 3,277원/kg 이면 재료비가 155원인데, 단가 1,330원이면
#   재료비 비중이 11.7% 다 — 현장 기준 40% 와 크게 어긋난다.
#
#   사내 근거 (같은 2026-08 실측):
#     "4.1%는 사출 단품(단가 100원대) 평균이고, 누락분에는 도장·조립이 얹힌
#      상위레벨(단가 900원대)이 섞여 있어 단가 대비 원재료 비중이 작다"
#   → 실제 단가는 사출 단품 100원대 / 도장·조립 완제품 900원대다.
#     합성은 상위레벨 쪽에 치우쳐 있었다.
#
#   ★ 판매단가 = 재료비 ÷ 0.40 으로 역산한다.
#     그러면 재료비·인건비·가공비·이익이 현장 구조(40:30:22.5:7.5)로 자동으로 닫힌다.
#     도번별 편차는 재료비 편차가 그대로 반영된다(자재 많이 쓰는 부품이 비싸다).
PRICE_JITTER = (0.85, 1.20)   # 같은 재료비라도 협상력·차종에 따라 단가가 다르다


def allocate_conversion(ms):
    """작업일보 총 생산량으로 인건비·가공비를 개당 배부한다.

    ★ 배부 기준을 **작업시간**으로 한다 — 수량으로 나누면 손 많이 가는 도번이
      싸게 잡힌다. 공정 CT 가 긴 도번일수록 인건비를 더 짊어져야 한다.
    """
    import glob
    logs = {}
    for f in glob.glob(str(OUT / "worklog_*.csv")):
        p = Path(f).stem.replace("worklog_", "")
        logs[p] = pd.read_csv(f)
    if not logs:
        return None
    all_log = pd.concat(logs.values(), ignore_index=True)
    all_log["총시간분"] = all_log["작업시간분"] + all_log["셋업시간분"]

    o = pd.read_csv(OUT / "orders.csv")
    pc = pd.read_csv(OUT / "product_cost_bom.csv").set_index("제품도번")["판매단가"]         if (OUT / "product_cost_bom.csv").exists() else None
    sales = (o["수량"] * ms.set_index("제품도번")["단가"]
             .reindex(o["제품도번"]).fillna(0).to_numpy()).sum()

    # 도번별 총 작업시간 → 시간 비중으로 배부
    by_part = all_log.groupby("제품도번").agg(시간=("총시간분", "sum"),
                                            수량=("생산수량", "sum"))
    total_h = by_part["시간"].sum()
    by_part["인건비_총"] = sales * LABOR_RATIO * by_part["시간"] / total_h
    by_part["가공비_총"] = sales * MFG_RATIO * by_part["시간"] / total_h
    by_part["인건비"] = by_part["인건비_총"] / by_part["수량"]
    by_part["가공비"] = by_part["가공비_총"] / by_part["수량"]
    return by_part[["인건비", "가공비"]].reset_index()


def conversion_cost(ms, cm, im, jm):
    """(구) 가공비·인건비 — 현장 CT × 시간당 요율. 배부 방식으로 대체됐다."""
    cm = cm.copy()
    cm["공정"] = cm["공정"].replace(PROCESS_ALIAS)
    rate = cm.set_index("공정")

    d = (ms[["제품도번", "사출도번"]]
         .merge(im[["사출도번", "캐비티수"]], on="사출도번", how="left")
         .merge(jm[["제품도번", "지그당적재"]], on="제품도번", how="left"))
    ct = pd.DataFrame({"제품도번": d["제품도번"]})
    ct["사출"] = CYCLE_CT["사출"] / d["캐비티수"].fillna(1).clip(lower=1)
    ct["도장"] = CYCLE_CT["도장"] / d["지그당적재"].fillna(1).clip(lower=1)
    for k, v in PER_PIECE_CT.items():
        ct[k] = v

    g = l = oh = 0.0
    for proc in list(CYCLE_CT) + list(PER_PIECE_CT):
        if proc not in rate.index:
            continue
        h = ct[proc] / 3600
        gg = h * rate.loc[proc, "시간당가공비"]
        ll = h * rate.loc[proc, "시간당인건비"]
        g = g + gg; l = l + ll
        oh = oh + (gg + ll) * rate.loc[proc, "간접비배부율"]
    return pd.DataFrame({"제품도번": ct["제품도번"], "가공비": g,
                         "인건비": l, "경비": oh})


def build(rng):
    pb, pcb, rm, mm, cm, lf, ms, im, jm = load()
    price = unit_price(rm, mm)
    cavity = im.set_index("사출도번")["캐비티수"].to_dict()
    mat = material_cost(pb, pcb, price, cavity)
    conv = allocate_conversion(ms)
    if conv is None:                       # 작업일보가 없으면 구 방식으로
        conv = conversion_cost(ms, cm, im, jm)
    if "경비" not in conv.columns:
        conv["경비"] = 0.0                 # 경비는 가공비에 통합됐다

    d = (ms[["제품도번", "고객사", "색상", "단가"]].rename(columns={"단가": "판매단가"})
         .merge(mat, on="제품도번", how="left")
         .merge(conv, on="제품도번", how="left")
         .merge(lf[["제품도번", "로스보정계수"]], on="제품도번", how="left"))

    k = d["로스보정계수"].fillna(1.0)
    for col in ("재료비", "가공비", "인건비"):
        if LOSS_ON[col]:
            d[col] = d[col] * k
    d["경비"] = d["경비"] * k                      # 경비는 가공+인건에 비례하므로 함께

    # ★ 판매단가를 재료비에서 역산 — 현장 구조(재료비 40%)를 만족시킨다
    d["판매단가"] = (d["재료비"] / MATERIAL_RATIO
                    * rng.uniform(*PRICE_JITTER, len(d))).round(0)
    d["총원가"] = d[["재료비", "가공비", "인건비", "경비"]].sum(axis=1)
    d["영업이익"] = d["판매단가"] - d["총원가"]
    d["이익률"] = d["영업이익"] / d["판매단가"] * 100
    return d.round(2)


def expand(rng, base):
    """35 → 1,200 도번. 속성이 같은 원본 행에서 통째로 물려받는다.

    ★ 원단위는 흔들지 않는다 — 같은 사출도번이면 같은 수지 원단위여야 한다.
      흔드는 것은 판매단가뿐이고, 그것도 generate_mydata 와 같은 ±15% 범위다.
    """
    o = pd.read_csv(OUT / "orders.csv")
    parts = sorted(o["제품도번"].unique())
    have = set(base["제품도번"])
    new = [p for p in parts if p not in have]
    if not new:
        return base
    idx = rng.integers(0, len(base), len(new))
    ex = base.iloc[idx].copy().reset_index(drop=True)
    ex["제품도번"] = new
    # 판매단가만 흔들고 원가는 그대로 → 이익률이 도번마다 달라진다
    ex["판매단가"] = (ex["재료비"] / MATERIAL_RATIO
                      * rng.uniform(*PRICE_JITTER, len(ex))).round(0)
    ex["영업이익"] = ex["판매단가"] - ex["총원가"]
    ex["이익률"] = (ex["영업이익"] / ex["판매단가"] * 100).round(2)
    return pd.concat([base, ex], ignore_index=True)


def main():
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    base = build(rng)

    print("=" * 68)
    print("  BOM 원가 전개  (⚠️ 합성 — 실측 아님)")
    print("=" * 68)
    print(f"\n[1] 원본 35 도번 전개")
    items = ["재료비", "가공비", "인건비", "경비"]
    share = (base[items].sum() / base["총원가"].sum() * 100).round(1)
    print("    구성비:", " · ".join(f"{k} {v}%" for k, v in share.items()))
    print(f"    총원가 평균 {base['총원가'].mean():,.1f}원 · 판매단가 평균 {base['판매단가'].mean():,.1f}원")
    print(f"    이익률 평균 {base['이익률'].mean():.1f}% "
          f"({base['이익률'].min():.1f} ~ {base['이익률'].max():.1f}%)")
    print(f"    적자 도번 {int((base['이익률'] < 0).sum())} / {len(base)}")
    print("\n    재료비 내역 평균:")
    for c in ["수지", "페인트", "트레이", "박스", "비닐", "신나잉크", "간지", "발포지"]:
        print(f"      {c:<8}{base[c].mean():>10,.2f}원  ({base[c].mean()/base['재료비'].mean()*100:>4.1f}%)")

    full = expand(rng, base)
    full.to_csv(OUT / "product_cost_bom.csv", index=False, encoding="utf-8-sig")
    print(f"\n[2] {len(full):,} 도번으로 확장 → product_cost_bom.csv")
    print(f"    이익률 평균 {full['이익률'].mean():.1f}% "
          f"({full['이익률'].min():.1f} ~ {full['이익률'].max():.1f}%)")
    print(f"    적자 도번 {int((full['이익률'] < 0).sum()):,} ({(full['이익률'] < 0).mean()*100:.1f}%)")

    o = pd.read_csv(OUT / "orders.csv", parse_dates=["수주일", "납기일"])
    oc = o.merge(full[["제품도번", "판매단가", "총원가", "영업이익", "이익률"]],
                 on="제품도번", how="left")
    oc["수주_이익"] = (oc["수량"] * oc["영업이익"]).round(0)
    oc.to_csv(OUT / "orders_costed_bom.csv", index=False, encoding="utf-8-sig")
    print(f"\n[3] orders_costed_bom.csv  {len(oc):,}행 · 커버리지 "
          f"{oc['총원가'].notna().mean()*100:.0f}%")
    print(f"    총 이익 {oc['수주_이익'].sum()/1e8:.1f}억 · 적자 수주 "
          f"{(oc['수주_이익'] < 0).mean()*100:.1f}%")
    print(f"\n출력: {OUT}")


if __name__ == "__main__":
    main()
