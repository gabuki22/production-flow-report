# -*- coding: utf-8 -*-
"""defect_events 에 `공정` 열을 붙인다 — 추정 합성

⚠️ **합성이다.** 기쁨 지시(2026-09-12) *"데이터가 없으면 만들어줘"*.
   가드레일 구술 *"각 공정별"* 이 데이터에 없어 `원인구분` 으로 대신해 왔다.
   열 **하나만** 붙인다 — 행 수·불량수량·검사수량은 한 건도 안 바뀐다(아래에서 증명).

★ 분포는 기쁨이 정했다(2026-09-12) — *"원인에 따른다"*.
    금형   → 사출 100%               (금형은 사출 공정의 것이다)
    페인트 → 도장 100%
    설비·자재 → 사출·도장·레이저·인쇄 **골고루** (추정 — 실 데이터가 오면 바뀐다)

실행:  py -X utf8 _generator/gen_defect_process.py            (dry-run · 쓰지 않는다)
       py -X utf8 _generator/gen_defect_process.py --apply    (백업 뒤 덮어쓴다)
시드 고정 — 다시 돌리면 같은 배정이 나온다.
"""
from __future__ import annotations

import shutil
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
BAK = ROOT / "_작업보조"

SEED = 20260912_2
PROCESSES = ["사출", "도장", "레이저", "인쇄"]
# ── 원인 → 공정 배정 확률 (기쁨 "원인에 따른다") ──
MAP = {
    "금형":   {"사출": 1.0},
    "페인트": {"도장": 1.0},
    "설비":   {p: 0.25 for p in PROCESSES},     # 추정
    "자재":   {p: 0.25 for p in PROCESSES},     # 추정
}


def main() -> int:
    apply = "--apply" in sys.argv
    src = DATA / "defect_events.parquet"
    d = pd.read_parquet(src)
    if "공정" in d.columns:
        print("이미 공정 열이 있다 — 아무것도 하지 않는다"); return 0
    before = (len(d), int(d["불량수량"].sum()), int(d["검사수량"].sum()))

    rng = np.random.default_rng(SEED)
    known = set(MAP)
    unknown = sorted(set(d["원인구분"].dropna().unique()) - known)
    if unknown:
        print(f"⚠️ MAP 에 없는 원인구분 {unknown} — 배정표를 채운 뒤 다시"); return 1
    proc = np.empty(len(d), dtype=object)
    for cause, w in MAP.items():
        idx = np.flatnonzero((d["원인구분"] == cause).to_numpy())
        ks, ps = list(w), np.array(list(w.values()), dtype=float)
        proc[idx] = rng.choice(ks, size=len(idx), p=ps / ps.sum())
    d["공정"] = pd.array(proc, dtype="string")

    after = (len(d), int(d["불량수량"].sum()), int(d["검사수량"].sum()))
    assert before == after, "행·수량이 바뀌었다 — 열만 붙여야 한다"
    g = d.groupby("공정", observed=True)[["검사수량", "불량수량"]].sum()
    g["불량률%"] = (g["불량수량"] / g["검사수량"] * 100).round(2)
    print(g.assign(행=d["공정"].value_counts()))
    print(pd.crosstab(d["원인구분"], d["공정"]))
    print(f"행 {before[0]:,} · 불량수량 {before[1]:,} · 검사수량 {before[2]:,} — 전후 동일")
    if not apply:
        print("(dry-run — --apply 로 쓴다)"); return 0
    BAK.mkdir(exist_ok=True)
    bak = BAK / f"defect_events.parquet.{datetime.now():%Y%m%d-%H%M%S}.bak"
    shutil.copy2(src, bak)
    d.to_parquet(src, index=False)
    print(f"[적용] {src.name} · 백업 {bak.name} (롤백: 백업을 제자리로 복사)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
