# -*- coding: utf-8 -*-
"""긴급 운송 데이터 생성 — urgent_shipping

⚠️ **합성이다.** 실제 운송 전표가 아니다. 기쁨 지시(2026-09-12) *"데이터가 없으면 만들어줘"*.
   제안서가 *"미납 페널티·긴급 운송비·클레임 비용은 데이터에 항목 자체가 없다"* 고
   적어 왔는데, 그중 **긴급 운송비**를 값으로 채워 보려는 것이다.

★ 구조는 기쁨이 정했다(2026-09-12). 지어낸 것이 아니다.
    · **미납 페널티 조항은 계약에 없다.** 늘어나는 비용은 긴급 운송비뿐이다.
      → 페널티 표는 만들지 않는다. 없는 것을 만들면 없는 비용이 문서에 생긴다.
    · 납기를 넘겨 나간 발주 중 긴급 운송(별도 차량)으로 나가는 것은 **일부** — 25% 안팎.
    · 긴급 운송 1회 비용은 **5~10만원** 자릿수.
   위 두 값은 **추정**이다. 실 전표가 오면 CONFIG 두 줄만 바꾼다.

그레인 = **긴급 운송 1건**(운송ID). 한 발주가 두 번 나갈 수 있어 수주ID 가 키가 아니다.

★ 일부러 섞는 것 (교안: *"결측·중복을 일부러 섞을 것"* — 깨끗한 데이터로는 검증할 것이 없다)
    · 운송비 결측 3%     — 전표에 금액이 안 적힌 건
    · 같은 운송 두 번 입력 8건 — 중복 적재
    · 수주ID 오타 3건    — orders 에 없는 키 (참조 무결성 검사가 **경고**로 잡아야 한다)

실행:  py -X utf8 _generator/gen_urgent_shipping.py
시드 고정 — 다시 돌리면 같은 데이터가 나온다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
sys.path.insert(0, str(ROOT))
from core import config as C   # noqa: E402  — 출하 단계 이름·기준일은 config 가 정본

SEED = 20260912

# ── CONFIG — 값을 코드 본문에 박지 않는다 ─────────────────────────
URGENT_RATE = 0.25            # 지연 출하 중 긴급 운송 비율 — 기쁨 "일부" (추정)
COST_MEDIAN = 70_000          # 긴급 운송 1회 중앙값(원) — 기쁨 "5~10만원" (추정)
COST_SIGMA = 0.35             # 로그정규 퍼짐 — 10~90% 가 약 4.5~11만원에 들게
MISSING_RATE = 0.03           # 운송비 결측
DUP_ROWS = 8                  # 중복 입력
BAD_KEY_ROWS = 3              # orders 에 없는 수주ID


def main() -> int:
    rng = np.random.default_rng(SEED)
    o = pd.read_parquet(DATA / "orders.parquet")
    e = pd.read_parquet(DATA / "order_events.parquet")

    # 출하일 = 출하 단계 최초 도달일 (metrics.order_facts 와 같은 정의)
    ship = (e[e["이벤트구분"] == C.FUNNEL_STEPS[-1]]
            .assign(이벤트일=lambda x: pd.to_datetime(x["이벤트일"]))
            .groupby("수주ID")["이벤트일"].min())
    d = o[["수주ID", "납기일", "수량"]].copy()
    d["납기일"] = pd.to_datetime(d["납기일"])
    d["출하일"] = d["수주ID"].map(ship)
    late = d[d["출하일"].notna() & d["납기일"].notna() & (d["출하일"] > d["납기일"])]
    late = late.assign(지연일=(late["출하일"] - late["납기일"]).dt.days)

    pick = late[rng.random(len(late)) < URGENT_RATE].reset_index(drop=True)
    cost = np.exp(rng.normal(np.log(COST_MEDIAN), COST_SIGMA, len(pick)))
    us = pd.DataFrame({
        "운송ID": [f"US-{i:06d}" for i in range(1, len(pick) + 1)],
        "수주ID": pick["수주ID"].astype(str),
        "출하일": pick["출하일"].dt.strftime("%Y-%m-%d"),
        "지연일": pick["지연일"].astype(int),
        "운송구분": "긴급",
        "운송비": (np.round(cost, -3)).astype(float),    # 천원 단위 전표
    })

    # ── 일부러 섞는 것 ──
    miss = rng.random(len(us)) < MISSING_RATE
    us.loc[miss, "운송비"] = np.nan
    dup = us.sample(DUP_ROWS, random_state=int(rng.integers(1 << 31)))
    bad = us.sample(BAD_KEY_ROWS, random_state=int(rng.integers(1 << 31))).copy()
    bad["수주ID"] = bad["수주ID"].str.replace(r"\d$", "X", regex=True)   # 끝자리 오타
    bad["운송ID"] = [f"US-{len(us) + i:06d}" for i in range(1, BAD_KEY_ROWS + 1)]
    us = pd.concat([us, dup, bad], ignore_index=True)
    us = us.sample(frac=1, random_state=int(rng.integers(1 << 31))).reset_index(drop=True)

    us.to_parquet(DATA / "urgent_shipping.parquet", index=False)

    # ── 프로파일 — 만든 뒤 반드시 보여준다 ──
    v = us["운송비"].dropna()
    print(f"지연 출하 {len(late):,}건 → 긴급 운송 {len(pick):,}건 ({len(pick)/len(late)*100:.1f}%)")
    print(f"행 {len(us):,} (중복 {DUP_ROWS} · 오타키 {BAD_KEY_ROWS}) · 운송비 결측 {us['운송비'].isna().sum()}건")
    print(f"운송비 중앙 {v.median():,.0f}원 · 10~90% {v.quantile(.1):,.0f}~{v.quantile(.9):,.0f}원 · 합계 {v.sum()/1e4:,.0f}만원")
    print(f"기간 {us['출하일'].min()} ~ {us['출하일'].max()} · 지연일 중앙 {us['지연일'].median():.0f}일")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
