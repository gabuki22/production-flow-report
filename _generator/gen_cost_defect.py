"""
원가 · 불량 데이터 연결 및 보정 — mydomain

⚠️ 산출물은 전부 **합성**이다. 성우산업 실제 원가·불량률이 아니다.

두 가지를 한다.
  1) 원가  — EDATA7기 product_cost.csv 를 조인하되 **이익률을 제조업 현실선으로 재보정**
             (원본 평균 65.8%는 자동차 부품 제조업 상식과 자릿수가 안 맞는다)
  2) 불량  — loss_factor 를 조인하고, 우리 12개월 기간의 불량 사건을 생성
             ★ 현장 기준: **대부분 3%, 튀는 것이 30% 내외** (배치 단위로 튄다)

★ 기존 자산 우선: 값 체계·구성비는 EDATA7기에서 가져온다. 새로 지어내지 않는다.

작성: 2026-08-29 · 7주차 Day5 보완 (프롬프트 C·D)
"""
from pathlib import Path
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────
# CONFIG — 값을 코드 본문에 박지 않는다. 바꿀 값은 전부 여기에.
#          각 값 옆에 "왜 그 값인지"를 남긴다.
# ─────────────────────────────────────────────────────────────
SEED = 20260829_2                  # 기존 생성기(20260829)와 다른 시드 — 독립 재현

# ── 원가 ──
# 원본(EDATA7기) 평균 영업이익률 65.8%는 제조업 상식과 자릿수가 안 맞는다.
# 자동차 부품 2차 벤더의 영업이익률은 통상 한 자릿수다.
# 판매단가는 그대로 두고 **원가를 올려** 이익률을 현실선으로 압축한다.
# ⚠️ 아래 세 값은 현장 확인 대상이다. 바꾸려면 여기만 고친다.
PROFIT_MEAN = 0.08                 # 목표 평균 영업이익률 8%
PROFIT_MIN = -0.05                 # 적자 도번이 존재한다(단가 협상 실패·소량 다품종)
PROFIT_MAX = 0.20                  # 고수익 도번 상한

# 원가 항목 구성비 — ★ 현장 기준(2026-08-29)
#   "인건비 한 30%, 자재비 40%, 기타 관리비 20~25% 정도"
#
#   ★ 정정(2026-08-29 2차·3차): **3항목이고, 셋째 이름은 "가공비"다.**
#     2차에서 컬럼이 넷이라 남은 자리에 "가공비 7.5%"를 임의로 만들어 넣었다 — 오류.
#     3차에서 정의를 받았다:
#       원재료 · 인건비 · **가공비**(설비비 · 전기료 · 인건비 · 소모품 교체비 · 설비 유지비)
#       "공정별로 같음" — 공정마다 같은 구조로 산정된다
#     즉 앞서 "기타 관리비"라 부른 것이 회사에서는 **가공비**다.
#     EDATA7기 4컬럼 → 우리 3항목: 재료비→원재료 · 인건비→인건비 · (가공비+경비)→가공비
#
#   40 : 30 : 22.5 = 92.5 이므로 비율을 유지한 채 100으로 정규화한다.
COST_MIX = {"재료비": 0.432, "인건비": 0.324, "가공비": 0.243}

# ── 불량 ──
# ★ 현장 기준(2026-08-29): "불량률은 3~30%인데 대부분 3%이고 튀는 것이 30% 내외"
#   30% 불량은 그 제품의 상시 특성이 아니라 **자재·설비 이상이 난 배치**에서 나온다.
#   그래서 도번 고유값이 아니라 **배치(수주) 단위로 튀게** 모델링한다.
# ★ 2차 보정(2026-08-29 현장): "보통 2~3% 불량인데, 총 불량률이 3~4% 나올 정도의 빈도"
#   → 평상시 2~3%(중심 2.5%) · 스파이크 기여가 약 1%p 되게 빈도를 역산.
#     기여 = SPIKE_RATE × (스파이크불량률 − 평상시) ≈ 0.04 × (0.285 − 0.025) ≈ 1.0%p
#   1차(평상시 3%·빈도 6%)는 총 4.74%로 현장 감각(3~4%)보다 높았다.
BASE_DEFECT = (0.018, 0.032)       # 평상시 불량률 범위 1.8~3.2%
BASE_DEFECT_MODE = 0.025           # 최빈값 2.5%
SPIKE_RATE = 0.04                  # 총 불량률이 3~4%에 들어오는 빈도 (역산값)
# ★ 스파이크의 월별 군집 강도. 0이면 균등(월별 변동이 사라짐), 클수록 특정 달에 몰린다.
#   자재 로트·설비 이상은 실제로 시기에 몰리므로 균등 가정이 오히려 비현실적이다.
SPIKE_MONTH_SD = 0.45              # 로그정규 σ — 월 스파이크율이 대략 2~3배 폭으로 흔들린다
SPIKE_DEFECT = (0.25, 0.32)        # 스파이크 시 불량률 25~32% (중심 30%)
ENV_MISSING = 0.08                 # 환경 온습도 결측 8% (현실의 기록 누락)

# 경로 — 하드코딩 금지
HERE = Path(__file__).resolve().parent
from _src import SRC                             # 값 풀 출처 → _src.py
OUT = HERE / "data"


def rebuild_cost(rng, parts):
    """원가 재보정 — 판매단가는 유지하고 원가를 올려 이익률을 현실선으로.

    ★ 도번 pool 이 1,200으로 확장됐으므로 원가도 전 도번에 붙여야 한다.
      원본 35개 밖의 도번은 **속성이 같은 원본 행에서 이익률을 물려받고**
      판매단가는 orders 의 단가를 쓴다.
    """
    pc = pd.read_csv(SRC / "product_cost.csv")
    if len(parts) > len(pc):
        idx = rng.integers(0, len(pc), len(parts) - len(pc))
        extra = pc.iloc[idx].copy().reset_index(drop=True)
        extra["제품도번"] = [x for x in parts if x not in set(pc["제품도번"])]
        # 판매단가는 orders 의 단가(도번별 ±15% 흔들린 값)를 그대로 쓴다
        extra["판매단가"] = extra["판매단가"] * rng.uniform(0.85, 1.15, len(extra))
        pc = pd.concat([pc, extra], ignore_index=True)
    before = pc["이익률"].copy()

    # 원본의 수익성 **순위는 보존**하고 범위만 압축한다.
    # (어느 도번이 더 남는지는 설계된 패턴이므로 뒤집지 않는다)
    rank = before.rank(pct=True)                      # 0~1
    target = PROFIT_MIN + rank * (PROFIT_MAX - PROFIT_MIN)
    # 평균을 PROFIT_MEAN 에 맞춘다
    target = target + (PROFIT_MEAN - target.mean())
    target = target.clip(PROFIT_MIN, PROFIT_MAX)

    out = pc.copy()
    out["영업이익"] = (out["판매단가"] * target).round(2)
    out["총원가"] = (out["판매단가"] - out["영업이익"]).round(2)
    for k, w in COST_MIX.items():
        out[k] = (out["총원가"] * w).round(2)
    out["경비"] = 0.0            # 컬럼 유지(하위 호환) — 값은 가공비에 통합됐다
    out["이익률"] = (out["영업이익"] / out["판매단가"] * 100).round(1)

    out.attrs["before"] = before
    return out


def build_defect_events(rng, orders, events):
    """우리 12개월 기간의 불량 사건 생성.

    ★ 공정작업에 도달한 수주에만 붙인다 — 공정을 안 거쳤으면 불량이 없다.
    ★ 구성비(불량유형·원인구분·설비호기)는 EDATA7기 defect_detail 에서 가져온다.
    """
    dd = pd.read_csv(SRC / "defect_detail.csv")
    pools = {c: dd[c].value_counts(normalize=True) for c in ["불량유형", "원인구분", "설비호기"]}

    proc = events[events["이벤트구분"] == "공정작업"][["수주ID", "이벤트일"]]
    base = orders.merge(proc, on="수주ID", how="inner")
    n = len(base)

    # 평상시 불량률 — 삼각분포(최빈 2.5%)
    rate = rng.triangular(BASE_DEFECT[0], BASE_DEFECT_MODE, BASE_DEFECT[1], n)

    # ★ 스파이크는 시간에 균등 분포하지 않는다.
    #   자재 로트 불량·설비 이상은 **특정 시기에 몰린다.** 균등하게 흩뿌리면
    #   표본이 커질수록 월평균이 대수의 법칙으로 수렴해 **월별 변동이 사라진다.**
    #   → 월별 스파이크 확률에 배수를 곱해 군집을 만든다.
    ym = pd.to_datetime(base["이벤트일"]).dt.to_period("M")
    months = ym.unique()
    mult = pd.Series(
        rng.lognormal(0, SPIKE_MONTH_SD, len(months)), index=months)
    mult = mult / mult.mean()                      # 평균 배수 1 — 전체 빈도는 유지
    p_spike = np.clip(ym.map(mult).to_numpy() * SPIKE_RATE, 0, 0.5)
    spike = rng.random(n) < p_spike
    rate = np.where(spike, rng.uniform(*SPIKE_DEFECT, n), rate)

    out = pd.DataFrame({
        "defect_id": [f"DF{i:06d}" for i in range(1, n + 1)],
        "수주ID": base["수주ID"].to_numpy(),
        "제품도번": base["제품도번"].to_numpy(),
        "고객사": base["고객사"].to_numpy(),
        "색상": base["색상"].to_numpy(),
        "검사일": base["이벤트일"].to_numpy(),
        "검사수량": base["수량"].to_numpy(),
        "불량률": rate.round(4),
        "스파이크": spike,
    })
    out["불량수량"] = (out["검사수량"] * out["불량률"]).round().astype(int)
    for c, p in pools.items():
        out[c] = rng.choice(p.index.to_numpy(), size=n, p=p.to_numpy())
    out["환경온도"] = rng.normal(23, 3, n).round(1)
    out["환경습도"] = rng.normal(55, 8, n).round(1)

    # 결측 — 환경 기록 누락
    miss = rng.choice(out.index, size=int(n * ENV_MISSING), replace=False)
    out.loc[miss, ["환경온도", "환경습도"]] = np.nan
    return out


def main():
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)
    orders = pd.read_csv(OUT / "orders.csv", parse_dates=["수주일", "납기일"])
    events = pd.read_csv(OUT / "order_events.csv", parse_dates=["이벤트일"])

    print("=" * 64)
    print("  원가·불량 연결  (⚠️ 전부 합성 — 실측 아님)")
    print("=" * 64)

    # ── 1. 원가 ──
    cost = rebuild_cost(rng, sorted(orders["제품도번"].unique()))
    before = cost.attrs["before"]
    cost.to_csv(OUT / "product_cost_adj.csv", index=False, encoding="utf-8-sig")
    print("\n[1] 원가 재보정 — 판매단가 유지, 원가를 올려 이익률 압축")
    print(f"    이익률  원본 {before.mean():>6.1f}% ({before.min():.1f}~{before.max():.1f}%)")
    print(f"           보정 {cost['이익률'].mean():>6.1f}% ({cost['이익률'].min():.1f}~{cost['이익률'].max():.1f}%)")
    print(f"    적자 도번 {int((cost['이익률'] < 0).sum())}개 / {len(cost)}개")
    print(f"    순위 보존 검증: 상관 {before.corr(cost['이익률'], method='spearman'):.3f} (1.000이어야 함)")

    # 수주에 원가 조인 (원본 orders.csv 는 그대로 둔다)
    oc = orders.merge(
        cost[["제품도번", "판매단가", "총원가", "영업이익", "이익률"]], on="제품도번", how="left")
    oc["수주_매출"] = (oc["수량"] * oc["판매단가"]).round(0)
    oc["수주_이익"] = (oc["수량"] * oc["영업이익"]).round(0)
    oc.to_csv(OUT / "orders_costed.csv", index=False, encoding="utf-8-sig")
    print(f"    → orders_costed.csv  {len(oc):,}행 (원본 orders.csv 무수정)")
    print(f"    수주당 평균 이익 {oc['수주_이익'].mean():,.0f}원 · 총 이익 {oc['수주_이익'].sum()/1e8:.2f}억")

    # ── 2. 불량 ──
    df = build_defect_events(rng, orders, events)
    df.to_csv(OUT / "defect_events.csv", index=False, encoding="utf-8-sig")
    r = df["불량률"] * 100
    print(f"\n[2] 불량 사건 생성 — 공정작업 도달 건에만")
    print(f"    {len(df):,}행 · {df['검사일'].min():%Y-%m-%d} ~ {df['검사일'].max():%Y-%m-%d}")
    print(f"    불량률  평균 {r.mean():.2f}%  중앙값 {r.median():.2f}%  범위 {r.min():.2f}~{r.max():.2f}%")
    print(f"    스파이크 {int(df['스파이크'].sum()):,}건 ({df['스파이크'].mean()*100:.1f}%) "
          f"· 스파이크 평균 {r[df['스파이크']].mean():.1f}%")
    print(f"    평상시 평균 {r[~df['스파이크']].mean():.2f}%  (현장 기준: 대부분 3%)")
    print(f"    환경 결측 {df['환경온도'].isna().mean()*100:.1f}%")
    print(f"\n출력: {OUT}")


if __name__ == "__main__":
    main()
