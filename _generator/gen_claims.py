# -*- coding: utf-8 -*-
"""고객사 클레임 데이터 — customer_claims (추정 합성)

⚠️ **합성이다.** 기쁨 지시(2026-09-12) *"데이터 항목 합성데이터로 생성"* — 위험 절이
   *"고객사 클레임 비용은 데이터에 항목이 없어"* 라고 적어 온 자리를 값으로 채운다.

★ 구조는 기쁨이 정했다(2026-09-12). 지어낸 것이 아니다.
    · 계기는 **둘 다** — 납기 지연 클레임 · 불량 클레임을 따로 센다
    · 1건 비용 **10~50만원** 자릿수 (선별비·재납품 등 합산)
    · 빈도 **주에 한두 건** → 연 50~100건
   값(비율·중앙값)은 **추정**이다. 실 클레임 대장이 오면 표를 교체한다.

그레인 = **클레임 1건**(클레임ID).
    지연 클레임 → 납기를 넘겨 나간 발주(지연 출하)에 붙는다
    불량 클레임 → 검사에서 불량률이 튄(스파이크) 건에 붙는다

★ 일부러 섞는 것 — 비용 결측 2건 · 중복 입력 1건 · 수주ID 오타 1건

실행:  py -X utf8 _generator/gen_claims.py
시드 고정.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))
from core import config as C   # noqa: E402

SEED = 20260912_4
CLAIMS_PER_WEEK = 1.5         # 기쁨 "주에 한두 건" (추정)
LATE_SHARE = 0.55             # 그중 지연 클레임 몫 — 추정 (나머지는 불량)
COST_MEDIAN = 250_000         # 기쁨 "10~50만원" 중앙 (추정)
COST_SIGMA = 0.5              # 10~90% 가 약 13~48만원
LAG_DAYS = (3, 21)            # 출하/검사 뒤 며칠 만에 접수되나 (추정)
MISSING_COST = 2
DUP_ROWS = 1
# ⚠️ 작은 표에는 오타 키를 안 심는다 — 78행에서 1건이 1.28%라 참조 무결성 **차단**(1%)에
#   걸린다. 검증기가 맞고 표본이 작은 것이다. 결측·중복만 섞는다. (2026-09-12 실제로 걸림)
BAD_KEY_ROWS = 0


def main() -> int:
    rng = np.random.default_rng(SEED)
    o = pd.read_parquet(DATA / "orders.parquet")
    e = pd.read_parquet(DATA / "order_events.parquet")
    de = pd.read_parquet(DATA / "defect_events.parquet")

    ship = (e[e["이벤트구분"] == C.FUNNEL_STEPS[-1]]
            .assign(이벤트일=lambda x: pd.to_datetime(x["이벤트일"]))
            .groupby("수주ID")["이벤트일"].min())
    d = o[["수주ID", "고객사", "납기일"]].copy()
    d["납기일"] = pd.to_datetime(d["납기일"]); d["출하일"] = d["수주ID"].map(ship)
    late = d[d["출하일"].notna() & d["납기일"].notna() & (d["출하일"] > d["납기일"])]

    weeks = (pd.Timestamp(C.PERIOD[1]) - pd.Timestamp(C.PERIOD[0])).days / 7
    n_total = int(round(weeks * CLAIMS_PER_WEEK))
    n_late = int(round(n_total * LATE_SHARE)); n_def = n_total - n_late

    a = late.sample(n_late, random_state=int(rng.integers(1 << 31)))
    a = pd.DataFrame({"수주ID": a["수주ID"].astype(str), "고객사": a["고객사"].astype(str),
                      "구분": "지연", "기준일": a["출하일"]})
    spk = de[de["스파이크"].astype(bool)] if "스파이크" in de.columns else de
    b = spk.sample(n_def, random_state=int(rng.integers(1 << 31)))
    b = pd.DataFrame({"수주ID": b["수주ID"].astype(str), "고객사": b["고객사"].astype(str),
                      "구분": "불량", "기준일": pd.to_datetime(b["검사일"])})
    cl = pd.concat([a, b], ignore_index=True)
    cl["접수일"] = cl["기준일"] + pd.to_timedelta(rng.integers(*LAG_DAYS, len(cl)), unit="D")
    cl = cl[cl["접수일"] <= pd.Timestamp(C.PERIOD[1])].reset_index(drop=True)   # 기간 밖 접수는 아직 안 온 것
    cl["클레임비용"] = np.round(np.exp(rng.normal(np.log(COST_MEDIAN), COST_SIGMA, len(cl))), -4)
    cl = cl.sort_values("접수일").reset_index(drop=True)
    cl.insert(0, "클레임ID", [f"CL-{i:04d}" for i in range(1, len(cl) + 1)])
    cl = cl[["클레임ID", "수주ID", "고객사", "구분", "접수일", "클레임비용"]]
    cl["접수일"] = cl["접수일"].dt.strftime("%Y-%m-%d")

    # ── 일부러 섞는 것 ──
    cl.loc[rng.choice(len(cl), MISSING_COST, replace=False), "클레임비용"] = np.nan
    dup = cl.sample(DUP_ROWS, random_state=int(rng.integers(1 << 31)))
    bad = cl.sample(BAD_KEY_ROWS, random_state=int(rng.integers(1 << 31))).copy()
    bad["수주ID"] = bad["수주ID"].str.replace(r"\d$", "X", regex=True)
    bad["클레임ID"] = [f"CL-{len(cl) + i:04d}" for i in range(1, BAD_KEY_ROWS + 1)]
    cl = pd.concat([cl, dup, bad], ignore_index=True)
    cl.to_parquet(DATA / "customer_claims.parquet", index=False)

    v = cl["클레임비용"].dropna()
    print(f"클레임 {len(cl):,}건 (지연 {int((cl['구분']=='지연').sum())} · 불량 {int((cl['구분']=='불량').sum())}) "
          f"· 주당 {len(cl)/weeks:.2f}건 · 중복 {DUP_ROWS} · 오타키 {BAD_KEY_ROWS} · 비용 결측 {cl['클레임비용'].isna().sum()}")
    print(f"1건 중앙 {v.median():,.0f}원 · 10~90% {v.quantile(.1):,.0f}~{v.quantile(.9):,.0f}원 · 합계 {v.sum()/1e4:,.0f}만원")
    print(f"지연 출하 {len(late):,}건 중 클레임 {n_late}건 = {n_late/len(late)*100:.2f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
