"""
mydomain 합성 데이터 생성기 — 성우산업 생산 퍼널

⚠️ 이 스크립트가 만드는 것은 전부 **합성 데이터**다. 실측이 아니다.
   실 ERP 데이터는 반출 금지라(경로 b) 스키마·값 체계만 복제하고 값은 생성한다.

값 체계 출처: 같은 도메인 합성 위키의 raw/ (실 ERP 아님)
  - master.csv               제품도번·차종·고객사·색상·단가·공정별 CT
  - order_lifecycle_events   수주ID 형식(SO{YYMM}-{4자리})·9열 구조·수량 분포·고객사 비율

난수 시드 고정 → 다시 돌리면 같은 데이터가 나온다.

작성: 2026-08-29 · 7주차 Day5 자기도메인 (프롬프트 2-1)
"""
from pathlib import Path
import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────
# CONFIG — 값을 코드 본문에 박지 않는다. 바꿀 값은 전부 여기에.
#          각 값 옆에 "왜 그 값인지"를 남긴다.
# ─────────────────────────────────────────────────────────────
SEED = 20260829                    # 고정 시드 — 재현성
# ★ 2차 보정(2026-08-29 현장): "하루 작업량은 200~300 제품도번"
#   1차는 하루 5.2 도번뿐이라 현실과 48배 어긋났다.
#   목표 250 도번/일 × 361일 ÷ 공정작업 도달률(약 94%) ≈ 96,000 수주
N_ORDERS = 96000                   # 하루 약 250 도번이 공정에 들어가게 역산
# 도번 pool — 35개(EDATA7기 master)로는 하루 250 도번을 돌릴 수 없다.
#   실제 성우산업은 9,614 도번. 합성은 1,200으로 둔다(도번당 월 약 6.7건).
#   ★ 도번 코드만 확장하고 속성(차종·색상·단가·CT)은 master.csv 35개에서 샘플링한다.
N_PARTS = 1200
PERIOD_START = "2025-09-01"        # 최근 12개월
PERIOD_END = "2026-08-29"          # 접수 마지막 날
# ★ 관측 종료일 — 이 날짜 이후의 이벤트는 "아직 안 일어난 일"이라 기록되지 않는다.
#   이걸 안 자르면 모든 수주가 결말까지 기록돼, 최근 접수분도 완주한 것처럼 보인다.
#   실제 데이터는 최근 건일수록 중간 단계에 멈춰 있다 — 그래야 코호트 절단을 연습할 수 있다.
OBSERVED_UNTIL = "2026-08-29"

# 퍼널 단계 — 명세 2행 그대로. 순서가 곧 퍼널이다.
STAGES = ["발주접수", "영업계획", "생산계획", "지시서작성", "공정작업", "출하"]
STAGE_UNPAID = "미납확인"          # 퍼널 밖 — 출하 못한 건의 분기(순환)

# 단계별 통과율 (앞 단계 도달자 중 다음으로 가는 비율)
#   ★ 2026-08-29 정정 — 초판은 출하 통과율을 0.62 로 두었으나 **비현실적이었다.**
#     현장 기준: 납기 준수율은 90% 이상이어야 정상, 80% 미만이면 위험.
#     0.62 로는 납기 준수율이 45.8% 밖에 안 나와 전 구간이 위험으로 찍혔다.
#     제조업에서 수주의 38%가 영원히 출하 안 되면 회사가 유지되지 않는다.
#
#   → **미납의 정의를 바꿨다.** 미납 = "영원히 미출하"가 아니라 **"납기를 못 맞춤(지연 출하)"**.
#     대부분은 결국 출하되고, 문제는 *언제* 나가느냐다. 병목은 여전히 하단이지만
#     "새는" 것이 아니라 "밀리는" 것으로 나타난다(2회차 판단은 유지).
#   ★ 2차 정정 — 통과율을 더 올렸다. 0.96~0.98 로도 4단계 누적되니 12.8% 가 탈락해
#     납기 준수율이 77.8% 에 머물렀다. **제조업에서 발주는 취소되지 않는 한 결국 만들어진다.**
#     탈락(영영 안 만들어짐)은 취소·반품 수준의 소수여야 한다.
#
#   ★★ 그래서 병목의 성격을 다시 잡았다:
#      우리 도메인의 병목은 **"새는 것"이 아니라 "밀리는 것"**이다.
#      퍼널(탈락 기준)은 거의 평평하고, 문제는 **납기 축**에서 드러난다.
#      → 탈락률로는 안 보이고 납기 준수율로만 보이는 병목이다.
PASS_RATE = {
    "영업계획":   0.995,  # 접수됐는데 영업계획에 안 올라가는 일은 거의 없다
    "생산계획":   0.99,   # 자재·캐파로 일부 보류
    "지시서작성": 0.995,  # 계획 후 지시서는 거의 나간다
    "공정작업":   0.99,   # 착수 못 한 채 사라지는 건 드물다
    "출하":       0.985,  # 최종 미출하 = 취소·반품 수준
}

# 지연 출하 비율 — 출하는 되지만 납기를 넘긴 건. ★ 이것이 우리 도메인의 진짜 문제다.
#   납기 준수율 ≈ 누적통과율(0.955) × 정시율(0.955) ≈ 91% 를 겨냥한다.
#   현장 기준(경고 90% · 위험 80%)에서 평균은 정상, 변동으로 일부 월이 경고에 걸리는 상태.
LATE_RATE = 0.045                  # 출하분 중 납기 초과 비율
LATE_EXTRA_DAYS = (3, 25)          # 지연 시 납기 초과 일수 범위

# 미납(지연) → 생산계획 재투입 비율 (우리 도메인 고유 순환)
REWORK_RATE = 0.45                 # 밀린 건의 절반 가까이가 다음 주기 계획에 다시 잡힌다

# 단계 간 소요일 (영업일 기준 대략값, 로그정규 분포의 중앙값)
LEADTIME_DAYS = {
    "영업계획":   2,
    "생산계획":   3,
    "지시서작성": 2,
    "공정작업":   5,
    "출하":       7,
}

MISSING_COL = "납기일"             # 결측을 심을 컬럼
MISSING_RATE = 0.07                # 가이드 5~10% — 납기 미확정 발주가 실제로 있다
DUP_RATE = 0.03                    # 이벤트 중복 3% — 이중 기록

# 경로 — 하드코딩 금지. 이 파일 위치 기준으로 잡는다.
HERE = Path(__file__).resolve().parent          # 이 파일이 있는 폴더
from _src import SRC                             # 값 풀 출처 → _src.py     # 값 풀 출처
OUT = HERE / "data"


def expand_parts(rng, m):
    """도번 pool 을 N_PARTS 로 확장한다.

    코드만 새로 만들고 **속성은 원본 35개에서 통째로 샘플링**한다.
    (차종·색상·단가·CT 조합을 쪼개지 않아야 도번 하나의 성격이 일관된다)
    """
    if N_PARTS <= len(m):
        return m
    idx = rng.integers(0, len(m), N_PARTS - len(m))
    extra = m.iloc[idx].copy().reset_index(drop=True)
    extra["제품도번"] = [f"P-{3100 + i}" for i in range(len(extra))]
    extra["단가"] = (extra["단가"] * rng.uniform(0.85, 1.15, len(extra))).round(0).astype(int)
    return pd.concat([m, extra], ignore_index=True)


def load_value_pools():
    """master.csv 에서 실제 값 풀을 읽는다. 값을 새로 발명하지 않는다."""
    m = pd.read_csv(SRC / "master.csv")
    # 고객사 분포는 lifecycle 실측 비율을 따른다
    ev = pd.read_csv(SRC / "order_lifecycle_events.csv")
    cust_w = ev.loc[ev["이벤트구분"] == "접수", "고객사"].value_counts(normalize=True)
    return m, cust_w


def build_orders(rng, master, cust_w):
    """대상 테이블 — 한 행 = 수주 1건"""
    # 고객사를 먼저 뽑고, 그 고객사가 실제로 쓰는 도번 중에서 제품을 고른다
    customers = rng.choice(cust_w.index.to_numpy(), size=N_ORDERS, p=cust_w.to_numpy())
    by_cust = {c: g["제품도번"].to_numpy() for c, g in master.groupby("고객사")}
    all_parts = master["제품도번"].to_numpy()
    parts = np.array([
        rng.choice(by_cust.get(c, all_parts)) for c in customers
    ])

    start = pd.Timestamp(PERIOD_START)
    end = pd.Timestamp(PERIOD_END)
    span = (end - start).days
    # 접수일은 기간에 고르게. 단, 마지막 45일은 아직 진행 중일 수 있게 남겨 둔다
    offsets = rng.integers(0, span, size=N_ORDERS)
    받은날 = pd.to_datetime([start + pd.Timedelta(days=int(d)) for d in offsets])

    # 수량 — ★ 현장 실측(2026-08-29): "개수는 하루에 20만개 정도"
    #   1차는 EDATA7기 lifecycle 분포(중앙 2,500)를 그대로 써 하루 64만 개가 나왔다.
    #   간지(월 8,000장)·발포지(월 25,000장) 사용량과 볼트 캐파 기록(도장 월 20만)이
    #   전부 "우리가 과다하다"를 가리켰다.
    #   목표: 하루 20만 개 ÷ 하루 266 수주 ≈ 수주당 750개
    qty = np.clip(rng.normal(750, 380, N_ORDERS), 100, 1800).round(-1).astype(int)

    # 납기일 = 접수 + 25~60일
    due = 받은날 + pd.to_timedelta(rng.integers(25, 61, N_ORDERS), unit="D")

    seq = rng.permutation(N_ORDERS) + 1
    order_id = [f"SO{d.strftime('%y%m')}-{s:04d}" for d, s in zip(받은날, seq)]

    df = pd.DataFrame({
        "수주ID": order_id,
        "제품도번": parts,
        "고객사": customers,
        "수주일": 받은날,
        "수량": qty,
        "납기일": due,
    })
    # master 속성 붙이기 (차종·색상은 도번에 종속 — 새로 만들지 않는다)
    df = df.merge(master[["제품도번", "차종", "색상", "단가"]], on="제품도번", how="left")
    return df.sort_values("수주일").reset_index(drop=True)


def build_events(rng, orders):
    """이벤트 테이블 — 한 행 = 수주 × 단계 도달 1회"""
    rows = []
    reached = {}          # 단계별 도달한 수주ID 집합
    cur = orders.copy()
    cur["이벤트일"] = cur["수주일"]

    # 1단계: 전원 발주접수
    for r in cur.itertuples(index=False):
        rows.append((r.수주ID, r.제품도번, r.고객사, r.이벤트일, STAGES[0], r.수량, r.납기일, None))
    reached[STAGES[0]] = set(cur["수주ID"])

    # 2~5단계: 통과율만큼 살아남아 다음 단계로 (출하는 아래에서 따로 — 납기에 묶이므로)
    for stage in STAGES[1:-1]:
        keep = rng.random(len(cur)) < PASS_RATE[stage]
        cur = cur[keep].copy()
        # 소요일 — 로그정규로 흩어지게(음수 방지)
        days = np.maximum(1, rng.lognormal(np.log(LEADTIME_DAYS[stage]), 0.5, len(cur))).round()
        cur["이벤트일"] = cur["이벤트일"] + pd.to_timedelta(days, unit="D")
        for r in cur.itertuples(index=False):
            rows.append((r.수주ID, r.제품도번, r.고객사, r.이벤트일, stage, r.수량, r.납기일, None))
        reached[stage] = set(cur["수주ID"])

    # 6단계 출하 — ★ 날짜를 납기일에 묶는다.
    #   정시분은 납기 전에, 지연분(LATE_RATE)은 납기를 넘겨 나간다.
    #   이렇게 해야 "납기 준수율"이 설계값대로 나온다. 리드타임만 쓰면 납기와 무관해진다.
    ship = cur[rng.random(len(cur)) < PASS_RATE[STAGES[-1]]].copy()
    is_late = rng.random(len(ship)) < LATE_RATE
    early = -rng.integers(0, 11, len(ship))                       # 납기 0~10일 전
    late = rng.integers(*LATE_EXTRA_DAYS, size=len(ship))          # 납기 +3~25일
    delta = np.where(is_late, late, early)
    ship_date = ship["납기일"] + pd.to_timedelta(delta, unit="D")
    # 공정작업보다 빠를 수는 없다 — 최소 하루 뒤로 밀어 순서를 지킨다
    ship["이벤트일"] = np.maximum(ship_date.to_numpy(),
                                (ship["이벤트일"] + pd.Timedelta(days=1)).to_numpy())
    for r in ship.itertuples(index=False):
        rows.append((r.수주ID, r.제품도번, r.고객사, r.이벤트일, STAGES[-1], r.수량, r.납기일, None))
    reached[STAGES[-1]] = set(ship["수주ID"])

    ev = pd.DataFrame(rows, columns=[
        "수주ID", "제품도번", "고객사", "이벤트일", "이벤트구분", "수량", "납기일", "변경사유"])

    # 미납확인 — ★ 납기를 넘긴 건. 지연 출하분 + 끝내 미출하분 둘 다.
    #   납기 다음날 시점에 "아직 안 나갔다"가 확인되는 이벤트다.
    shipped_on = ev[ev["이벤트구분"] == STAGES[-1]].set_index("수주ID")["이벤트일"]
    proc = orders[orders["수주ID"].isin(reached["공정작업"])].copy()
    proc["출하일"] = proc["수주ID"].map(shipped_on)
    overdue = proc[proc["출하일"].isna() | (proc["출하일"] > proc["납기일"])].copy()
    overdue["이벤트일"] = overdue["납기일"] + pd.Timedelta(days=1)
    사유 = ["자재 결품", "설비 비가동", "계획외 삽입", "색상 교체 대기", "외주 지연"]
    overdue["변경사유"] = rng.choice(사유, size=len(overdue))
    unpaid = overdue[["수주ID", "제품도번", "고객사", "이벤트일", "수량", "납기일", "변경사유"]].copy()
    unpaid["이벤트구분"] = STAGE_UNPAID

    # 순환 — 미납분 일부가 생산계획으로 재투입 (같은 수주ID가 다시 등장)
    rework = unpaid.sample(frac=REWORK_RATE, random_state=SEED).copy()
    rework["이벤트구분"] = "생산계획"
    rework["이벤트일"] = rework["이벤트일"] + pd.to_timedelta(
        rng.integers(5, 20, len(rework)), unit="D")
    rework["변경사유"] = "미납 재투입"

    ev = pd.concat([ev, unpaid[ev.columns], rework[ev.columns]], ignore_index=True)
    return ev.sort_values(["이벤트일", "수주ID"]).reset_index(drop=True), reached


def inject_dirt(rng, orders, events):
    """결측·중복을 일부러 섞는다. 깨끗한 데이터면 검증할 것이 없다."""
    # 결측 — 납기일 (실무에서도 납기 미확정 발주가 있다)
    n_miss = int(len(orders) * MISSING_RATE)
    idx = rng.choice(orders.index, size=n_miss, replace=False)
    orders.loc[idx, MISSING_COL] = pd.NaT
    events.loc[events["수주ID"].isin(orders.loc[idx, "수주ID"]), MISSING_COL] = pd.NaT

    # 중복 — 같은 이벤트가 두 번 기록된 것
    n_dup = int(len(events) * DUP_RATE)
    dup = events.sample(n=n_dup, random_state=SEED)
    events = pd.concat([events, dup], ignore_index=True)
    events = events.sort_values(["이벤트일", "수주ID"]).reset_index(drop=True)
    events.insert(0, "event_id", [f"EV{i:06d}" for i in range(1, len(events) + 1)])
    return orders, events


def main():
    rng = np.random.default_rng(SEED)
    OUT.mkdir(parents=True, exist_ok=True)

    master, cust_w = load_value_pools()
    master = expand_parts(rng, master)
    orders = build_orders(rng, master, cust_w)
    events, reached = build_events(rng, orders)

    # ★ 관측 창 절단 — 아직 안 일어난 이벤트는 기록에 없다.
    #   최근 접수분은 자연히 중간 단계에서 멈춘다(진행 중). 이게 실제 데이터의 모습이다.
    cutoff = pd.Timestamp(OBSERVED_UNTIL)
    before = len(events)
    events = events[events["이벤트일"] <= cutoff].reset_index(drop=True)
    print(f"[관측 창] {OBSERVED_UNTIL} 이후 이벤트 {before - len(events):,}건 절단 "
          f"(아직 진행 중이라 기록이 없는 것)")

    orders, events = inject_dirt(rng, orders, events)

    orders.to_csv(OUT / "orders.csv", index=False, encoding="utf-8-sig")
    events.to_csv(OUT / "order_events.csv", index=False, encoding="utf-8-sig")

    # ── 생성 직후 프로파일 (가이드: 만든 뒤 반드시 보여준다) ──
    print("=" * 62)
    print("  합성 데이터 생성 완료  (⚠️ 전부 합성 — 실측 아님)")
    print("=" * 62)
    for name, df, datecol in [("orders", orders, "수주일"), ("order_events", events, "이벤트일")]:
        print(f"\n[{name}.csv]  {len(df):,}행 × {len(df.columns)}열")
        print(f"  기간: {df[datecol].min():%Y-%m-%d} ~ {df[datecol].max():%Y-%m-%d}")

    print("\n── 컬럼별 결측률 (orders) ──")
    ms = (orders.isna().mean() * 100).round(1)
    print("  " + " · ".join(f"{k} {v}%" for k, v in ms[ms > 0].items()) or "  없음")

    print("\n── 퍼널 (수주ID 고유 · 최초 도달만) ──")
    first = events[events["이벤트구분"].isin(STAGES)].sort_values("이벤트일")
    first = first.drop_duplicates(["수주ID", "이벤트구분"])
    prev = None
    print(f"  {'단계':<12}{'도달':>7}{'전단계대비':>12}{'누적':>10}")
    base = first.loc[first["이벤트구분"] == STAGES[0], "수주ID"].nunique()
    for s in STAGES:
        n = first.loc[first["이벤트구분"] == s, "수주ID"].nunique()
        step = f"{n/prev*100:.1f}%" if prev else "—"
        print(f"  {s:<12}{n:>7,}{step:>12}{n/base*100:>9.1f}%")
        prev = n

    proc = first[first["이벤트구분"] == "공정작업"].copy()
    proc["일"] = proc["이벤트일"].dt.date
    daily = proc.groupby("일")["제품도번"].nunique()
    print(f"\n  ★ 하루 공정작업 도번 수: 평균 {daily.mean():.0f}개 "
          f"(중앙 {daily.median():.0f} · 범위 {daily.min()}~{daily.max()})  [목표 200~300]")
    print(f"  도번 pool {orders['제품도번'].nunique():,}개")

    n_unpaid = events.loc[events["이벤트구분"] == STAGE_UNPAID, "수주ID"].nunique()
    n_rework = events.loc[events["변경사유"] == "미납 재투입", "수주ID"].nunique()
    print(f"\n  미납확인 {n_unpaid:,}건  ·  그중 생산계획 재투입 {n_rework:,}건 (순환)")
    print(f"  이벤트 중복 {int(len(events)*DUP_RATE/(1+DUP_RATE)):,}건 심음")
    print(f"\n출력: {OUT}")


if __name__ == "__main__":
    main()
