# -*- coding: utf-8 -*-
"""실험 데이터 생성 — experiments · experiment_assignments

⚠️ **우리는 이 실험을 실제로 돌린 적이 없다.**
   7주차에 *설계만* 해 둔 것(그룹당 5,298건 · 41일 · 스위치백)을 데이터로 옮긴 것이다.
   앱의 실험 화면·판정 로직이 실제로 도는지 확인하려고 만들었다.
   **리포트 7장 한계에 "실험은 설계뿐이고 실행 기록이 아니다"를 반드시 남긴다.**

왜 세 건인가 — 한 건만 만들면 **판정 분기가 한 갈래만 돌아 본다.**
못 믿을 조건(배정·표본)에 실제로 걸리는 건을 일부러 섞어야
trust_check() 가 작동하는지 눈으로 볼 수 있다.

    EXP-001  자재 입고 로트 검사 강화   정상 배정 · 충분한 표본   → 계산까지 간다
    EXP-002  색상 묶음 순서 조정       **배정이 깨짐(SRM)**      → 무효로 멈춘다
    EXP-003  지시서 조기 발행          **표본 부족**             → 무효로 멈춘다

배정 단위는 **수주 1건(수주ID)** 이다. 퍼널 그레인과 같아야 조인이 성립한다.

실행:  py -X utf8 _generator/gen_experiments.py
시드 고정 — 다시 돌리면 같은 데이터가 나온다.
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEED = 20260901
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# ── 설계 (출처: 7주차 08_실험설계) ────────────────────────────────
# 스위치백이라 배정 단위가 주차다. 같은 주에 들어온 수주는 같은 처치를 받는다.
# 개별 무작위가 아니라는 사실 자체가 한계이고, 그것을 데이터에도 남긴다.
EXPERIMENTS = [
    {
        "experiment_id": "EXP-001",
        "experiment_name": "자재 입고 로트 검사 강화",
        "hypothesis": "자재 입고 로트 검사를 강화하면 불량 스파이크 발생률이 "
                      "4.0% → 3.0% 로 내려간다 (상대 25%). "
                      "단, 납기 준수율은 2%p 이상 나빠지지 않는다.",
        "primary_metric": "스파이크 미발생률",
        "guardrail_metric": "납기 준수율",
        "start_date": "2026-01-05",
        "end_date": "2026-03-01",      # 8주 (스위치백 각 4주)
        "unit": "주차 블록 (스위치백)",
        "note": "처치가 '검사 절차'라 로트별로 나눌 수 없다 — 검사원이 같은 날 "
                "두 기준을 오갈 수 없어 주 단위로 교차 배정했다.",
    },
    {
        "experiment_id": "EXP-002",
        "experiment_name": "색상 묶음 순서 조정",
        "hypothesis": "밝은 색부터 진한 색 순으로 묶으면 교체 손실이 줄어 "
                      "납기 내 출하율이 오른다.",
        "primary_metric": "납기 내 출하율",
        "guardrail_metric": "납기 준수율",
        "start_date": "2026-04-06",
        "end_date": "2026-05-31",
        "unit": "일 단위 (현장 재량)",
        "note": "현장이 물량이 몰리는 날 처치군을 임의로 뺐다. 무작위가 깨졌다.",
    },
    {
        "experiment_id": "EXP-003",
        "experiment_name": "지시서 조기 발행",
        "hypothesis": "생산계획 확정 즉시 지시서를 내면 공정 착수가 빨라진다.",
        "primary_metric": "공정 착수율",
        "guardrail_metric": "납기 준수율",
        "start_date": "2026-07-06",
        "end_date": "2026-07-17",      # 2주 만에 중단
        "unit": "수주 단위",
        "note": "2주 만에 중단됐다. 표본이 최소 기준에 못 미친다.",
    },
]

# 배정 규모 — (실험, 대상 수주 수, control 비율)
#   EXP-002 의 0.62 가 SRM 을 깨뜨리는 값이다. 50:50 이 아니면 배정 로직에
#   손이 탄 것이고, 그 경우 어떤 효과가 나와도 해석할 수 없다.
PLAN = {
    "EXP-001": {"n": 10_600, "control_ratio": 0.50},
    "EXP-002": {"n": 8_400, "control_ratio": 0.62},   # ← 깨진 배정
    "EXP-003": {"n": 64, "control_ratio": 0.50},      # ← 표본 부족
}


def main() -> None:
    rng = np.random.default_rng(SEED)

    orders = pd.read_parquet(DATA / "orders.parquet")
    orders["수주일"] = pd.to_datetime(orders["수주일"].astype(str))

    ex = pd.DataFrame(EXPERIMENTS)
    rows = []

    for e in EXPERIMENTS:
        eid = e["experiment_id"]
        plan = PLAN[eid]
        lo = pd.Timestamp(e["start_date"])
        hi = pd.Timestamp(e["end_date"])

        pool = orders[(orders["수주일"] >= lo) & (orders["수주일"] <= hi)]
        if len(pool) == 0:
            raise SystemExit(f"{eid}: 기간 {lo.date()}~{hi.date()} 에 수주가 없다.")

        take = min(plan["n"], len(pool))
        pick = pool.sample(n=take, random_state=int(rng.integers(1e6)))

        if e["unit"].startswith("주차"):
            # 스위치백 — 같은 주에 들어온 수주는 같은 처치를 받는다.
            # 이것이 개별 무작위보다 약한 설계라는 사실을 데이터가 그대로 담는다.
            wk = pick["수주일"].dt.isocalendar().week.astype(int)
            variant = np.where(wk % 2 == 0, "treatment", "control")
        else:
            variant = rng.choice(
                ["control", "treatment"], size=take,
                p=[plan["control_ratio"], 1 - plan["control_ratio"]])

        rows.append(pd.DataFrame({
            "experiment_id": eid,
            "수주ID": pick["수주ID"].to_numpy(),
            "variant": variant,
            "assigned_at": pick["수주일"].dt.strftime("%Y-%m-%d").to_numpy(),
        }))

    asg = pd.concat(rows, ignore_index=True)

    # 한 수주가 두 실험에 겹쳐 배정되면 효과가 섞인다. 기간이 안 겹치게 잡았지만
    # 만드는 쪽에서도 확인한다 — 검사기와 생성기가 같은 가정을 공유하면
    # 둘 다 틀렸을 때 함께 통과한다.
    dup = asg.duplicated(["experiment_id", "수주ID"]).sum()
    cross = asg["수주ID"].duplicated().sum()
    assert dup == 0, f"같은 실험에 중복 배정 {dup}건"
    assert cross == 0, f"실험 간 겹친 수주 {cross}건 — 효과가 섞인다"

    DATA.mkdir(parents=True, exist_ok=True)
    ex.to_parquet(DATA / "experiments.parquet", index=False)
    asg.to_parquet(DATA / "experiment_assignments.parquet", index=False)

    print("=" * 64)
    print("  실험 데이터 생성 — 설계만 있고 실행 기록이 아니다")
    print("=" * 64)
    print(f"  experiments              {len(ex):>7,}행")
    print(f"  experiment_assignments   {len(asg):>7,}행")
    print()
    for eid, g in asg.groupby("experiment_id", observed=True):
        c = int((g.variant == "control").sum())
        t = int((g.variant == "treatment").sum())
        print(f"  {eid}  control {c:>6,} : treatment {t:>6,}  "
              f"({c/(c+t)*100:.1f}:{(t)/(c+t)*100:.1f})")
    print()
    print(f"  → {DATA}")


if __name__ == "__main__":
    main()
