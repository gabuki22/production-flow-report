# -*- coding: utf-8 -*-
"""공정 시간 · 라인 캐파 데이터 — worklog_공정시간 · line_capacity

⚠️ **합성이다.** 기쁨 지시(2026-09-12) *"필요한 합성데이터 제작"* — 벤치마크 리더 조건
   *"비용 추정치 누락 · 실행 자원 불확실"* 에 데이터로 답하려는 것이다.

두 표를 낸다.
  1) worklog_공정시간 — **지어내지 않는다.** 이미 있는 작업일보 6종(사출·지그삽입·도장·
     레이저·인쇄·검사)을 수주ID×공정으로 합친 것이다. 한 발주가 공정마다 몇 분 걸리는가.
     ⚠️ 앱은 지금까지 `worklog_검사` 하나만 읽었다 — 나머지 다섯을 **안 읽어서 없다고
     했지 없던 것이 아니다**(규칙 20).
  2) line_capacity — **추정 합성.** 공정×호기라인×일자별 인원·정규 가동시간·잔업 상한.
     기쁨 표준(근로시간·인건비 가중): 1일 정상 8h + 잔업 최대 2h.
     인원은 관측 사용시간 중앙값이 정규 캐파의 85%가 되게 잡았다(추정 — 실 배치표가 오면 교체).

그레인   worklog_공정시간 = 발주 1건 × 공정 1개  /  line_capacity = 라인 1개 × 1일

★ 일부러 섞는 것 — line_capacity 에 빠진 날 2% · 잔업상한 결측 5행

실행:  py -X utf8 _generator/gen_capacity.py
시드 고정.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
SRC = ROOT.parent / "mydomain" / "data"          # 작업일보 원본(합성)이 있는 곳
sys.path.insert(0, str(ROOT))
from core import config as C   # noqa: E402

SEED = 20260912_3
PROCESSES = ["사출", "지그삽입", "도장", "레이저", "인쇄", "검사"]   # 공정 순서
TARGET_UTIL = 0.85            # 인원 산정 기준 가동률 — 추정
MISSING_DAY_RATE = 0.02
MISSING_CAP_ROWS = 5


def main() -> int:
    rng = np.random.default_rng(SEED)
    parts, caps = [], []
    for p in PROCESSES:
        w = pd.read_csv(SRC / f"worklog_{p}.csv", encoding="utf-8-sig")
        w["생산일자"] = pd.to_datetime(w["생산일자"])
        g = (w.groupby(["수주ID"], as_index=False)
               .agg(호기라인=("호기라인", "first"), 생산일자=("생산일자", "min"),
                    작업시간분=("작업시간분", "sum"), 셋업시간분=("셋업시간분", "sum"),
                    생산수량=("생산수량", "sum")))
        g.insert(1, "공정", p)
        parts.append(g)

        # 라인·일자별 사용시간 → 인원 → 정규 캐파
        used = w.groupby(["호기라인", "생산일자"])["작업시간분"].sum() / 60
        for line, s in used.groupby(level=0):
            n = int(np.ceil(s.median() / C.WORKDAY_H / TARGET_UTIL))
            days = pd.date_range(w["생산일자"].min(), w["생산일자"].max(), freq="D")
            cap = pd.DataFrame({"공정": p, "호기라인": line, "일자": days,
                                "인원": n + rng.integers(-1, 2, len(days)).clip(-1, 1) * (rng.random(len(days)) < 0.1)})
            cap["인원"] = cap["인원"].clip(lower=max(1, n - 1)).astype(int)
            cap["정규시간h"] = (cap["인원"] * C.WORKDAY_H).astype(float)
            cap["잔업상한h"] = (cap["인원"] * C.OVERTIME_CAP_H).astype(float)
            caps.append(cap)

    wl = pd.concat(parts, ignore_index=True)
    wl["생산일자"] = wl["생산일자"].dt.strftime("%Y-%m-%d")
    lc = pd.concat(caps, ignore_index=True)
    lc = lc[rng.random(len(lc)) >= MISSING_DAY_RATE].reset_index(drop=True)      # 빠진 날
    lc.loc[rng.choice(len(lc), MISSING_CAP_ROWS, replace=False), "잔업상한h"] = np.nan
    lc["일자"] = lc["일자"].dt.strftime("%Y-%m-%d")

    wl.to_parquet(DATA / "worklog_공정시간.parquet", index=False)
    lc.to_parquet(DATA / "line_capacity.parquet", index=False)

    # ── 프로파일 ──
    print(f"worklog_공정시간 {len(wl):,}행 · 발주 {wl['수주ID'].nunique():,} · 공정 {wl['공정'].nunique()}")
    per = wl.groupby("수주ID")["작업시간분"].sum() / 60
    print(f"  발주 1건 전공정 합 중앙 {per.median():.2f}h (10~90% {per.quantile(.1):.2f}~{per.quantile(.9):.2f}h)")
    print(f"line_capacity {len(lc):,}행 · 잔업상한 결측 {lc['잔업상한h'].isna().sum()}")
    u = (wl.assign(h=wl["작업시간분"] / 60).groupby(["공정", "호기라인", "생산일자"])["h"].sum()
           .groupby(level=[0, 1]).median().rename("사용h"))
    c = lc.groupby(["공정", "호기라인"])[["정규시간h", "잔업상한h"]].median()
    prof = c.join(u); prof["가동률"] = (prof["사용h"] / prof["정규시간h"]).round(2)
    print(prof.groupby(level=0).agg(정규h=("정규시간h", "sum"), 잔업상한h=("잔업상한h", "sum"),
                                   사용h=("사용h", "sum"), 가동률=("가동률", "mean")).round(2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
