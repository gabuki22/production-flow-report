# -*- coding: utf-8 -*-
"""지표 계산.

**지표의 정의는 위키가 원본이다.** 이 파일은 위키에 적힌 정의를 코드로 옮긴 것일 뿐,
여기서 정의를 새로 만들지 않는다. 정의가 바뀌면 위키를 먼저 고친다.

────────────────────────────────────────────────────────────────────
★ 골격 원본에는 통신사 컬럼명이 박혀 있었다 (2026-09-01 이식 완료).

  visitor_id → 수주ID · funnel_step → 이벤트구분 · billing_amount → 판매단가
  sessions → orders · funnel_events → order_events · is_churned → (계산으로 대체)

이식하며 배운 것 하나 — **이름만 바꾸면 되는 것과 개념이 없는 것은 다르다.**
sessions·customers 는 이름을 바꿔 붙일 데가 있었지만, 획득 채널(channel)은
우리 도메인에 개념 자체가 없어서 다른 것으로 갈아끼워야 했다.
→ channel_efficiency() 주석

시그니처도 하나 바뀌었다. 골격의 funnel(fe) 는 이벤트 테이블 하나만 받았는데,
우리 퍼널은 **완주 코호트로 분모를 자르므로 orders 가 함께 필요하다.**
그래서 funnel(t) 로 바꿨다 — retention_funnel(t)·kpis(t) 와 같은 모양이 됐다.
────────────────────────────────────────────────────────────────────

계산은 전부 pandas로 한다. 어디서 읽어왔든 입력은 동일한 DataFrame이다.

★ 우리 도메인의 두 축이 거의 모든 계산에 걸린다. 함수마다 다시 쓰지 않고 여기 한 번 적는다.

  **최초 도달만 센다**  미납이 다음 주기 생산계획으로 되돌아온다. 재투입을 다시
                       세면 분모가 부풀어 통과율이 좋아 보인다.
  **완주 코호트 61일**  납기가 수주 + 25~60일이라 그 전에는 완주 여부를 판정할 수
                       없다. 자르지 않으면 진행 중인 것을 실패로 센다.
"""
from __future__ import annotations

from datetime import date as _date      # 연간 환산에만 쓴다 — now() 는 쓰지 않는다

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

from core import config as C
from core.load import to_dt

TODAY = pd.Timestamp(C.TODAY)


# ── 공통 ──────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def first_reach(fe: pd.DataFrame) -> pd.DataFrame:
    """단계별 **최초 도달**만 남긴다. 재투입은 다시 세지 않는다.

    그레인 질문의 답이 여기 있다 — 한 수주가 같은 단계를 두 번 밟을 수 있는가?
    **있다.** 미납이 생산계획으로 되돌아오기 때문이다. 그래서 행을 그냥 세면 안 되고
    (수주ID, 이벤트구분) 조합에서 가장 이른 것만 남긴다.

    ★ **'가장 이른 것'은 내가 고른 것이다** (2026-09-02 실습 B-1 에서 드러냄).
      우리 데이터에서는 최초/최종이 **같은 값을 준다** — 중복이 날짜까지 같은
      완전 중복이라 그렇다(납기 준수율 91.05%로 동일).
      **실 ERP 로 바꾸면 갈린다.** 재출하·재작업의 날짜가 다르기 때문이다.
      그때는 *"약속을 언제 지켰나"* 를 묻는 것이므로 **최초**가 맞다.
    """
    f = fe[fe["이벤트구분"].isin(C.FUNNEL_STEPS)].copy()
    f["이벤트일"] = to_dt(f["이벤트일"])
    return (f.sort_values("이벤트일")
             .drop_duplicates(["수주ID", "이벤트구분"])
             [["수주ID", "이벤트구분", "이벤트일"]])


@st.cache_data(show_spinner=False)
def mature_ids(o: pd.DataFrame) -> set:
    """완주 코호트 — 접수 후 COHORT_DAYS 일이 지나 판정이 가능한 수주."""
    d = to_dt(o["수주일"])
    return set(o.loc[d <= TODAY - pd.Timedelta(days=C.COHORT_DAYS), "수주ID"])


@st.cache_data(show_spinner=False)
def order_facts(o: pd.DataFrame, fe: pd.DataFrame) -> pd.DataFrame:
    """수주 1건 = 1행. 납기·출하·판정을 한자리에 모은다.

    **이 표가 납기 준수율·지연·이탈의 공통 분모다.** 화면마다 따로 세면 어긋난다.
    실제로 7주차에 분모를 셋으로 나눠 세다가 같은 지표가 81.9% · 91.1% · 95.7%
    세 값으로 갈렸다. 분모를 한곳에 두는 것이 그 대응이다.
    """
    fr = first_reach(fe)
    ship = fr[fr["이벤트구분"] == C.FUNNEL_STEPS[-1]].set_index("수주ID")["이벤트일"]
    d = o.copy()
    d["수주일"] = to_dt(d["수주일"])
    d["납기일"] = to_dt(d["납기일"])
    d["출하일"] = d["수주ID"].map(ship)
    d["완주"] = d["수주ID"].isin(mature_ids(o))
    d["납기도래"] = d["납기일"].notna() & (d["납기일"] <= TODAY)
    d["출하완료"] = d["출하일"].notna()
    # ★ 납기 미정(납기일 결측 7.0%)을 **눈에 보이게** 둔다.
    #   납기내출하는 NaN 비교라 자동으로 False 가 되는데, 그러면 납기가 아직
    #   안 정해진 발주가 조용히 "약속을 못 지킨 것"으로 깔린다.
    #   우리 주지표는 분모가 '납기 도래'라 영향이 없지만, 출하분만 놓고 세면
    #   95.7% 가 89.0% 로 보인다 — **분모를 바꾼 것보다 결측 처리가 더 크게 움직였다.**
    d["납기미정"] = d["납기일"].isna()
    d["납기내출하"] = d["출하완료"] & (d["출하일"] <= d["납기일"])
    d["지연출하"] = d["출하완료"] & (d["출하일"] > d["납기일"])
    # 긴급품 — 명세 5행(2026-09-02 개정). 납기가 지났는데 아직 안 나갔다.
    #   ★ "이탈"이 아니다. 우리 수주는 사라지지 않고 **더 급해진다.**
    #     유예는 0이다 — 현장은 납기 다음 날부터 급하다.
    d["긴급"] = (d["납기도래"] & ~d["출하완료"]
                 & ((TODAY - d["납기일"]).dt.days > C.URGENT_GRACE_DAYS))
    return d


# ── 퍼널 ──────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def funnel(t: dict) -> pd.DataFrame:
    """단계별 도달 인원과 전환율.

    먼저 정할 것은 **그레인**이다.

        한 대상이 같은 단계를 두 번 밟을 수 있는가?
          있다 → 그냥 세면 안 된다. 고유값으로 센다 (nunique)
          없다 → 행을 그대로 세도 된다 (len)

    ── 우리 답 ──────────────────────────────────────────────────
    그레인은 **제품도번 1개**(2026-09-12 개정 · 전에는 발주 1건). 이 함수는 그 안의
    **발주 건**을 세는 재료다 — 한 수주가 같은 단계를 두 번 밟을 수 있으므로
    (미납 → 생산계획 재투입) 행을 세지 않고 **수주ID 고유값**을 센다.

    ★ 2026-09-02 정정 — 전에 여기 *"행으로 세면 전환율이 100%를 넘는다"* 고 적었는데
      부정확했다. 실측하면 이렇다.

          행 / 행분모      발주접수 100.0% → 출하 85.5%   (안 넘는다)
          행 / 고유분모    발주접수 103.0% → 출하  88.1%   (**앞 3단계가 넘는다**)

      100%를 넘기는 것은 '행으로 세는 것' 자체가 아니라 **분자와 분모의 단위를
      섞는 것**이다. 행/행으로 일관되게 세면 안 넘고, 대신 재투입이 분모에 섞여
      *다른 질문*에 답하게 된다. 교안 표현으로 "둘 다 맞는 숫자"이되,
      **섞으면 어느 쪽도 아닌 숫자**가 된다.

    분모는 **완주 코호트**다. 61일을 안 자르면 최종 통과율이 9%p 넘게 나쁘게 나오는데,
    그 차이는 실패가 아니라 **아직 진행 중인 것**이다.

    반환: DataFrame[step, label, n, n_all, step_rate, cum_rate, drop, is_bottleneck]

        step           config.FUNNEL_STEPS 의 값
        label          config.FUNNEL_LABELS 의 값 (화면 표시용)
        n              그 단계에 도달한 수 — **완주 코호트 기준**
        n_all          코호트를 안 자른 전체 (대조용. 착시가 얼마나인지 보려고 둔다)
        step_rate      전 단계 대비 비율 (첫 단계는 NaN)
        cum_rate       첫 단계 대비 비율
        drop           전 단계에서 빠진 수
        is_bottleneck  step_rate 가 가장 낮은 구간이면 True

    만들고 나서 **반드시 손계산과 대조한다.** → tests/test_metrics.py 에 대조표가 있다.
    """
    fr = first_reach(t["order_events"])
    mature = mature_ids(t["orders"])
    reach = {s: set(fr.loc[fr["이벤트구분"] == s, "수주ID"]) for s in C.FUNNEL_STEPS}

    rows, prev = [], None
    for s in C.FUNNEL_STEPS:
        n = len(reach[s] & mature)
        rows.append({
            "step": s,
            "label": C.FUNNEL_LABELS.get(s, s),
            "n": n,
            "n_all": len(reach[s]),
            "step_rate": np.nan if prev is None else (n / prev if prev else np.nan),
            "drop": 0 if prev is None else prev - n,
        })
        prev = n

    f = pd.DataFrame(rows)
    f["cum_rate"] = f["n"] / f["n"].iloc[0] if f["n"].iloc[0] else np.nan
    # 병목 = 전 단계 대비 비율이 가장 낮은 구간. 첫 단계는 비교 대상이 없어 제외한다.
    f["is_bottleneck"] = False
    if f["step_rate"].notna().any():
        f.loc[f["step_rate"].idxmin(), "is_bottleneck"] = True
    return f


@st.cache_data(show_spinner=False)
def funnel_skips(t: dict) -> int:
    """앞 단계를 건너뛰고 뒤 단계에 온 수주. **퍼널인지 아닌지를 가르는 값이다.**

    많으면 퍼널이 아니라 분류다 — 단계를 다시 짜야 한다.
    """
    fr = first_reach(t["order_events"])
    reach = {s: set(fr.loc[fr["이벤트구분"] == s, "수주ID"]) for s in C.FUNNEL_STEPS}
    return sum(len(reach[C.FUNNEL_STEPS[i]] - reach[C.FUNNEL_STEPS[i - 1]])
               for i in range(1, len(C.FUNNEL_STEPS)))


@st.cache_data(show_spinner=False)
def funnel_by(t: dict, dim: str, step_from: str, step_to: str) -> pd.DataFrame:
    """차원별 특정 구간 전환율. 평균 하나로는 어디를 고칠지 모른다.

    dim 은 분해 축이다. **무엇으로 쪼갤지는 내가 정한다.** → config.DIMS

    쪼개는 기준은 이것이다: 그 축으로 나눴을 때 **손을 쓸 수 있는가.**
    나눠서 격차가 보여도 우리가 못 바꾸는 것이면 분해할 이유가 적다.

    ⚠️ **쪼개면 표본이 준다.** 7주차에 차종 격차가 1차 조회에서 13.2%p(p=0.046)로
    "유의"하게 나왔다가, 표본을 48배로 늘리니 0.8%p(p=0.494)로 사라졌다.
    그래서 칸마다 도달 수를 함께 돌려주고 MIN_SAMPLE 미만은 화면에서 표시한다.

    반환: DataFrame[<dim>, 도달, 전환, 전환율, 비중, 표본부족]
    """
    fr = first_reach(t["order_events"])
    mature = mature_ids(t["orders"])
    a = set(fr.loc[fr["이벤트구분"] == step_from, "수주ID"]) & mature
    b = set(fr.loc[fr["이벤트구분"] == step_to, "수주ID"]) & mature

    # 분해 축은 orders 에 있다 — 골격의 sessions 자리다.
    o = t["orders"][["수주ID", dim]]
    o = o[o["수주ID"].isin(a)].copy()
    o["전환"] = o["수주ID"].isin(b)

    g = (o.groupby(dim, observed=True)
          .agg(도달=("수주ID", "nunique"), 전환=("전환", "sum"))
          .reset_index())
    g["전환율"] = g["전환"] / g["도달"]
    g["비중"] = g["도달"] / g["도달"].sum()
    g["표본부족"] = g["도달"] < C.MIN_SAMPLE
    return g.sort_values("도달", ascending=False).reset_index(drop=True)


@st.cache_data(show_spinner=False)
def metric_by(t: dict, dim: str) -> pd.DataFrame:
    """축별 **주지표(납기 준수율)**. 퍼널 전환율 대신 이걸로 쪼갠다.

    ★ 2026-09-03 신설 — 지적: *"축 간 %차이가 거의 없어 그래프 의미가 없다."*
      퍼널 전환율로 쪼개면 격차가 **0.6%p** 뿐이다. 우리 병목은 *새는 것*이 아니라
      *밀리는 것*이라, **탈락률에는 안 나타나고 납기 축에서 드러나기 때문**이다.
      같은 축을 납기 준수율로 쪼개면 격차가 **4.24%p** 로 벌어진다.

      즉 축이 나빴던 게 아니라 **보는 지표가 안 맞았다.**
      우리 도메인 결론(*"탈락률로는 안 보이고 납기 축에서만 보인다"*)이
      분해 화면에서도 그대로 성립한다.

    반환: DataFrame[<dim>, 분모, 준수, 준수율, 비중, 표본부족]
    """
    d = order_facts(t["orders"], t["order_events"])
    mat = d[d["완주"] & d["납기도래"]]
    g = (mat.groupby(dim, observed=True)
            .agg(분모=("납기내출하", "size"), 준수=("납기내출하", "sum"))
            .reset_index())
    g["준수율"] = g["준수"] / g["분모"]
    g["비중"] = g["분모"] / g["분모"].sum()
    g["표본부족"] = g["분모"] < C.MIN_SAMPLE
    return g.sort_values("분모", ascending=False).reset_index(drop=True)




def part_facts(t: dict) -> pd.DataFrame:
    """**제품도번 1개 = 한 줄.** 오늘의 그레인이다 (2026-09-12).

    반환: DataFrame[제품도번, 발주, 준수, 준수율, 금액, 건당금액,
                    차종, 고객사, 색상, 표본부족]

    ★ **발주 단위 계산(`order_facts`)을 재료로 쓴다.** 두 곳에서 따로 세면
      언젠가 갈린다 — 도번 집계는 그 위에 한 겹 올리는 것이지 다시 세는 것이
      아니다.

    ★ 모집단은 `metric_by` 와 같다 — **완주 코호트 중 납기 도래.** 분모가
      다르면 같은 화면에서 도번 준수율과 축 준수율이 안 맞는다.

    ⚠️ 차종·고객사·색상은 `first` 로 붙인다. 한 도번은 한 차종·한 색상에
      속하므로 대표값이 곧 유일값이다. **고객사만 도번에 따라 여럿일 수 있어**
      대표값으로 읽으면 안 된다 — 그 축은 `metric_by` 로 따로 본다.

    ⚠️ 수량·단가가 `int16` 이라 그대로 곱하면 조용히 감긴다 → `amount_by` 주석.
    """
    d = order_facts(t["orders"], t["order_events"])
    mat = d[d["완주"] & d["납기도래"]].copy()
    mat["_금액"] = mat["수량"].astype("int64") * mat["단가"].astype("int64")

    g = (mat.groupby("제품도번", observed=True)
            .agg(발주=("수주ID", "size"), 준수=("납기내출하", "sum"),
                 금액=("_금액", "sum"),
                 차종=("차종", "first"), 고객사=("고객사", "first"),
                 색상=("색상", "first"))
            .reset_index())
    g["준수율"] = g["준수"] / g["발주"]
    g["건당금액"] = g["금액"] / g["발주"]
    # 도번당 발주가 53~119건이라 MIN_SAMPLE(100) 로 재면 대부분 걸린다.
    # **도번 그레인에서는 표본 기준이 다르다** — 한 도번의 발주 수로 본다.
    g["표본부족"] = g["발주"] < C.MIN_SAMPLE_PART
    return g.sort_values("준수율").reset_index(drop=True)


def _bh_q(pvals: "np.ndarray") -> "np.ndarray":
    """Benjamini-Hochberg 보정 q값.

    ⚠️ **도번 1,200개를 한꺼번에 본다.** 보정 없이 p<0.05 를 세면 우연만으로도
      60개가 걸린다 — 2026-09-12 에 실제로 56개가 나왔고, 그것을 *"상습 지연
      도번을 찾았다"* 고 읽을 뻔했다.
    """
    n = len(pvals)
    order = np.argsort(pvals)
    ranked = pvals[order] * n / np.arange(1, n + 1)
    # 뒤에서부터 누적 최소 — q값은 단조여야 한다
    ranked = np.minimum.accumulate(ranked[::-1])[::-1]
    out = np.empty(n)
    out[order] = np.clip(ranked, 0, 1)
    return out


def _detectable_gap(n: "np.ndarray", p0: float,
                    alpha: float = 0.05, power: float = 0.80) -> "np.ndarray":
    """그 표본 크기로 **검출할 수 있는 최소 차이**(%p).

    표본이 작으면 진짜 차이가 있어도 못 잡는다. 값을 함께 돌려주면 쓰는 쪽이
    *"이 도번은 표본이 작아 판정을 미룬다"* 를 스스로 정할 수 있다.
    """
    z = stats.norm.isf(alpha) + stats.norm.isf(1 - power)
    return z * np.sqrt(p0 * (1 - p0) / np.maximum(n, 1)) * 100


def late_parts(t: dict, threshold: float | None = None,
               alpha: float = 0.05) -> pd.DataFrame:
    """**상습 지연 도번 — 우연과 구분되는 것만.**

    반환: `part_facts` 의 칸 + `p값` · `q값` · `유의` · `검출가능차이` · `판정`

    ★ **준수율이 낮다는 것만으로는 표적이 안 된다.** 한 도번의 발주가 38~88건
      뿐이라, 전체 준수율보다 낮게 나오는 일이 우연히도 자주 생긴다.
      그래서 이항검정(단측) + BH 보정을 걸어 **우연으로 설명되는 것을 뺀다.**

    ★ **실데이터에서 그대로 쓴다.** 진짜 도번 효과가 있으면 `유의` 가 서고,
      없으면 빈 표가 나온다. 데이터가 바뀌어도 코드를 고칠 일이 없다.

    ⚠️ 2026-09-12 이 합성 데이터에서는 **유의한 도번이 없다.** 생성기가 지연율을
      고객사·차종·색상에만 심었고 도번에는 안 심었기 때문이다 —
      빈 표가 나오는 것이 **맞는 동작**이지 고장이 아니다.
    """
    thr = C.LATE_PART_THRESHOLD if threshold is None else threshold
    p = part_facts(t).copy()
    base = float(p["준수"].sum() / p["발주"].sum())      # 전체 준수율

    # 각 도번이 전체보다 **낮은가** — 단측. 높은 쪽은 여기서 볼 것이 아니다.
    p["p값"] = [stats.binomtest(int(a), int(b), base, alternative="less").pvalue
                for a, b in zip(p["준수"], p["발주"])]
    p["q값"] = _bh_q(p["p값"].to_numpy())
    p["유의"] = p["q값"] < alpha
    p["검출가능차이"] = _detectable_gap(p["발주"].to_numpy(), base)
    벌어짐 = (base - p["준수율"]) * 100
    p["판정"] = np.where(
        p["유의"], "우연으로 보기 어려움",
        np.where(벌어짐 < p["검출가능차이"],
                 "표본이 작아 판정 못 함", "우연과 구분 안 됨"))

    out = p[p["준수율"] < thr].reset_index(drop=True)
    # ★ **요약을 값으로 싣는다.** 쓰는 쪽이 통계를 몰라도 되게.
    out.attrs["기준"] = thr
    out.attrs["전체준수율"] = base
    out.attrs["유의개수"] = int(out["유의"].sum())
    out.attrs["우연기대"] = round(len(p) * alpha, 1)
    out.attrs["요약"] = (
        f'기준 {thr * 100:.0f}% 미만 도번 {len(out)}개 중 '
        f'**우연으로 보기 어려운 것 {int(out["유의"].sum())}개** '
        f'(도번 {len(p):,}개를 함께 봐 BH 보정, q<{alpha})')
    return out

def amount_by(t: dict, dim: str) -> pd.DataFrame:
    """축별 **납품 금액** — `metric_by` 와 **같은 기준**으로 센다.

    반환: DataFrame[<dim>, 건수, 금액, 미준수건수, 미준수금액, 미준수건당]

    ★ `metric_by` 와 같은 모집단(완주 코호트 중 납기 도래)을 쓴다. 다른 기준으로
      세면 같은 화면에서 건수와 금액의 분모가 갈린다.

    ⚠️ **수량·단가가 `int16` 이라 그대로 곱하면 조용히 감긴다.**
      `300 × 772 = 231,600` 이 int16 범위(32,767)를 넘어 음수로 뒤집히는데
      **오류가 나지 않는다 — 값만 틀린다.** 2026-09-11 에 건당 383원이 나왔고
      (실제 674,917원) 숫자가 작다는 것 말고는 아무 신호도 없었다.
      **곱하기 전에 int64 로 올린다.**

    ⚠️ 단가는 **재료비에서 역산한 합성값**이다(CLAUDE.md 「미정」). 자릿수와
      상대 크기는 쓸 수 있으나 **계약 단가가 아니다.** 문서에 낼 때 그 한계를
      함께 적는다.
    """
    d = order_facts(t["orders"], t["order_events"])
    mat = d[d["완주"] & d["납기도래"]].copy()
    # ★ 여기가 그 자리다. astype 를 빼면 값이 조용히 틀린다.
    mat["금액"] = mat["수량"].astype("int64") * mat["단가"].astype("int64")
    mat["_미"] = ~mat["납기내출하"]

    g = (mat.groupby(dim, observed=True)
            .agg(건수=("수주ID", "size"), 금액=("금액", "sum"),
                 미준수건수=("_미", "sum"),
                 미준수금액=("금액", lambda s: s[mat.loc[s.index, "_미"]].sum()))
            .reset_index())
    g["미준수건당"] = (g["미준수금액"] / g["미준수건수"]).where(g["미준수건수"] > 0)
    return g.sort_values("금액", ascending=False).reset_index(drop=True)


def urgent_ship_facts(t: dict) -> dict:
    """긴급 운송 — **지연 출하 한 건이 운송비로 얼마인가.**

    반환: {지연건수, 긴급건수, 긴급비율, 회당비용, 지연건당비용, 합계}
      · 모집단은 `amount_by` 와 같다 — 완주 코호트 중 납기 도래, 그중 **지연 출하**.
      · 지연건당비용 = 합계 ÷ 지연 건수. **긴급으로 안 나간 건도 분모에 든다** —
        격차로 환산한 N건 중 어느 건이 긴급이 될지는 데이터가 지목하지 못하므로
        지연 한 건의 기대 운송비로 쓴다.

    ★ 표에 일부러 섞인 것을 여기서 거른다 — 같은 운송ID 두 번(중복 입력)은 한 번만,
      orders 에 없는 수주ID(오타)는 뺀다, 운송비 결측은 건수에는 들고 금액에는 안 든다.
    ⚠️ 이 표는 **추정 합성**이다(`_generator/gen_urgent_shipping.py`). 비율·회당 비용이
      기쁨 구술 자릿수이지 전표가 아니다. 문서에 낼 때 "추정"을 함께 적는다.
    """
    us = t.get("urgent_shipping")
    d = order_facts(t["orders"], t["order_events"])
    late = d[d["완주"] & d["납기도래"] & d["지연출하"]]
    out = {"지연건수": int(len(late)), "긴급건수": 0, "긴급비율": 0.0,
           "회당비용": 0.0, "지연건당비용": 0.0, "합계": 0.0}
    if us is None or not len(us) or not len(late):
        return out
    u = us.drop_duplicates("운송ID")
    u = u[u["수주ID"].isin(late["수주ID"])]
    v = u["운송비"].dropna().astype("float64")
    out.update({"긴급건수": int(len(u)),
                "긴급비율": float(len(u) / len(late)),
                "회당비용": float(v.mean()) if len(v) else 0.0,
                "합계": float(v.sum())})
    # 결측 전표는 회당 평균으로 채워 지연 건당 기대값을 낸다 (건수는 세고 금액만 없는 것)
    out["지연건당비용"] = out["회당비용"] * out["긴급비율"]
    return out


def defect_rate_by(t: dict, dim: str | None = None, months: int | None = None) -> pd.DataFrame:
    """축별 **불량률(수량 가중)** — 가드레일 *"각 공정별"* 의 자리.

    반환: DataFrame[<dim>, 검사건수, 검사수량, 불량수량, 불량률(%), 표본부족] · 불량률 높은 순
      · `dim` 기본은 `config.DEFECT_AXIS`(공정). 원인구분·설비호기·차종 등 defect_events 의
        어느 열이든 된다.
      · `months` 를 주면 검사일 기준 **마지막 N개월**만 센다 — *"최근 6개월 중 두 달"* 을
        공정으로 갈라 볼 때.
      · 건수로 세지 않는다 — 작은 로트가 과대 대표된다(`channel_efficiency` 와 같은 이유).

    ⚠️ `공정` 열은 **추정 배정**이다(`_generator/gen_defect_process.py`). 원인→공정 규칙만
      기쁨 구술이고 설비·자재의 배분은 균등 가정이다. 문서에 낼 때 "추정"을 함께 적는다.
    """
    dim = dim or C.DEFECT_AXIS
    de = t["defect_events"]
    if dim not in de.columns:
        raise KeyError(f"defect_events 에 {dim!r} 열이 없다")
    if months:
        d = to_dt(de["검사일"])
        cut = (d.max().to_period("M") - (months - 1)).to_timestamp()
        de = de[d >= cut]
    g = (de.groupby(dim, observed=True)
           .agg(검사건수=("불량수량", "size"), 검사수량=("검사수량", "sum"),
                불량수량=("불량수량", "sum"))
           .reset_index())
    g["불량률"] = g["불량수량"] / g["검사수량"] * 100
    g["표본부족"] = g["검사건수"] < C.MIN_SAMPLE
    return g.sort_values("불량률", ascending=False).reset_index(drop=True)


def capacity_facts(t: dict) -> pd.DataFrame:
    """공정별 **하루 캐파** — 정규h · 사용h · 가동률 · 잔업 여유h (라인 합 · 일자 중앙값).

    반환: DataFrame[공정, 정규h, 사용h, 잔업여유h, 가동률]
      · 잔업 여유 = 잔업 상한 − (사용 − 정규)⁺ — 이미 정규를 넘긴 만큼은 여유가 아니다.
      · 일자별 값의 **중앙값**이다. 바쁜 날은 이보다 적다.

    ⚠️ `line_capacity` 는 **추정 합성**이다(`_generator/gen_capacity.py`). 인원은 관측
      사용시간이 정규의 85%가 되게 잡은 값이지 배치표가 아니다.
    """
    lc, wl = t.get("line_capacity"), t.get("worklog_공정시간")
    if lc is None or wl is None or not len(lc) or not len(wl):
        return pd.DataFrame()
    cap = lc.groupby(["공정", "호기라인"], observed=True)[["정규시간h", "잔업상한h"]].median()
    use = (wl.assign(h=wl["작업시간분"].astype("float64") / 60)      # int16 합 방지
             .groupby(["공정", "호기라인", "생산일자"], observed=True)["h"].sum()
             .groupby(level=[0, 1]).median().rename("사용h"))
    d = cap.join(use).fillna({"사용h": 0.0})
    d["잔업여유h"] = (d["잔업상한h"] - (d["사용h"] - d["정규시간h"]).clip(lower=0)).clip(lower=0)
    g = (d.groupby(level=0).agg(정규h=("정규시간h", "sum"), 사용h=("사용h", "sum"),
                                잔업여유h=("잔업여유h", "sum")).reset_index())
    g["가동률"] = g["사용h"] / g["정규h"]
    return g


def pull_cost(t: dict, dim: str = "차종", val: str = "V6") -> dict:
    """지연분을 **잔업 시간 안에서 당길 때** — 한 건이 얼마고, 하루 여유가 얼마인가.

    반환: {건당시간h, 잔업시급, 건당비용, 잔업여유h일, 가동일, 조치}
      · 건당시간 = 그 칸(예: 차종 V6) 발주 1건의 **전 공정 작업시간 합**(작업일보 실측 평균)
      · 잔업시급 = config.HOURLY_WAGE × OVERTIME_MULT (기쁨 인건비 표준)
      · 잔업여유h일 = capacity_facts 의 전 공정 합

    ⚠️ **조치가 가정이다** — config.PULL_ACTION. 기쁨이 다른 조치를 정하면 이 함수를 바꾼다.
      비용의 자릿수(편익의 10%대)는 조치가 바뀌어도 크게 안 움직인다는 것이 이 값의 쓸모다.
    """
    wl = t.get("worklog_공정시간")
    if wl is None or not len(wl) or dim not in t["orders"].columns:
        return {}
    m = wl.merge(t["orders"][["수주ID", dim]], on="수주ID", how="inner")
    m = m[m[dim] == val] if val else m
    if not len(m):
        return {}
    per_h = float(m["작업시간분"].astype("float64").sum() / m["수주ID"].nunique() / 60)
    wage = float(C.HOURLY_WAGE * C.OVERTIME_MULT)
    cf = capacity_facts(t)
    return {"건당시간h": per_h, "잔업시급": wage, "건당비용": per_h * wage,
            "잔업여유h일": float(cf["잔업여유h"].sum()) if len(cf) else 0.0,
            "가동일": int(wl["생산일자"].nunique()), "조치": C.PULL_ACTION}


def claim_facts(t: dict) -> dict:
    """고객사 클레임 — **지연 한 건이 클레임 비용으로 얼마인가** (+ 불량 클레임은 따로).

    반환: {지연건수, 지연클레임건수, 지연클레임비율, 건당비용, 지연건당비용, 불량클레임건수, 합계}
      · 모집단은 `urgent_ship_facts` 와 같다 — 완주 코호트 중 납기 도래, 그중 지연 출하.
      · 지연건당비용 = 건당비용 × 지연클레임비율. 클레임이 안 붙은 지연 건도 분모에 든다.
      · 불량 클레임은 **이 제안의 효과가 아니다** — 가드레일 쪽이라 건수만 돌려준다.
    ★ 중복 클레임ID 는 한 번만, orders 에 없는 수주ID 는 뺀다, 비용 결측은 건수엔 들고 금액엔 안 든다.
    ⚠️ **추정 합성**이다(`_generator/gen_claims.py`) — 계기·자릿수·빈도만 기쁨 구술.
    """
    cl = t.get("customer_claims")
    d = order_facts(t["orders"], t["order_events"])
    late = d[d["완주"] & d["납기도래"] & d["지연출하"]]
    out = {"지연건수": int(len(late)), "지연클레임건수": 0, "지연클레임비율": 0.0,
           "건당비용": 0.0, "지연건당비용": 0.0, "불량클레임건수": 0, "합계": 0.0}
    if cl is None or not len(cl) or not len(late):
        return out
    c = cl.drop_duplicates("클레임ID")
    c = c[c["수주ID"].isin(t["orders"]["수주ID"])]
    v = c["클레임비용"].dropna().astype("float64")
    lat = c[(c["구분"] == "지연") & c["수주ID"].isin(late["수주ID"])]
    out.update({"지연클레임건수": int(len(lat)),
                "지연클레임비율": float(len(lat) / len(late)),
                "건당비용": float(v.mean()) if len(v) else 0.0,
                "불량클레임건수": int((c["구분"] == "불량").sum()),
                "합계": float(v.sum())})
    out["지연건당비용"] = out["건당비용"] * out["지연클레임비율"]
    return out


def spillover_facts(t: dict, dim: str = "차종", val: str = "V6", eff: int = 149) -> dict:
    """한 칸(예: 차종 V6)을 당길 때 **다른 칸에 번지는가** — 일정과 품질, 넷으로 답한다.

    (2026-09-12 · 4차 벤치마크 리더 우려 *"잔업·자원이 다른 핵심 차종의 일정·품질에
     부정적 연쇄 반응"*. 근거 문서 `_작업보조/근거-연쇄반응.py` 가 이 값을 그대로 싣는다.)

    반환 dict
      공정별   DataFrame[공정, 건당h, 하루필요h, 잔업여유h, 정규h, 가동률, 여유대비%]
               — eff 건을 가동일로 나눠 하루 몫으로. 공정마다 여유의 몇 %인가
      월별     DataFrame[월, 대상, 기타] 납기 준수율(%) + attrs 상관·좋은달/나쁜달 기타 평균
               — 맞바꿈이면 음(−)의 상관이 나와야 한다
      부하별   DataFrame[구간, 일수, 부하h, 불량률] — 일 부하 사분위별 불량률 + attrs 상관
      초과일수 정규 캐파 합을 넘긴 날 수 — 0이면 "잔업→불량"은 관측 밖이다(그것도 적는다)
      불량률   {대상: %, 기타: %}

    ⚠️ 부하·캐파는 `line_capacity`(추정 배치) 기준. 월별 상관은 관측이라 인과가 아니다.
    """
    o, wl, de = t["orders"], t.get("worklog_공정시간"), t["defect_events"]
    if wl is None or not len(wl):
        return {}
    m = wl.merge(o[["수주ID", dim]], on="수주ID")
    m["h"] = m["작업시간분"].astype("float64") / 60
    days = int(wl["생산일자"].nunique())
    tgt = m[m[dim] == val]
    per = tgt.groupby("공정", observed=True)["h"].sum() / max(tgt["수주ID"].nunique(), 1)
    cf = capacity_facts(t).set_index("공정")
    proc = pd.DataFrame({"건당h": per, "하루필요h": per * eff / days,
                         "잔업여유h": cf["잔업여유h"], "정규h": cf["정규h"], "가동률": cf["가동률"]})
    proc["여유대비%"] = proc["하루필요h"] / proc["잔업여유h"] * 100
    proc = proc.reset_index()

    d = order_facts(o, t["order_events"])
    d = d[d["완주"] & d["납기도래"]].copy()
    d["월"] = to_dt(d["납기일"]).dt.to_period("M")
    d["_g"] = d[dim].eq(val).map({True: val, False: "기타"})
    mon = (d.groupby(["월", "_g"], observed=True)["납기내출하"].mean().unstack() * 100)
    mon = mon[mon.index >= (mon.index.max() - 9)]           # 마지막 10개월
    mon = mon.dropna().reset_index()
    if len(mon) >= 4:
        mon.attrs["상관"] = float(np.corrcoef(mon[val], mon["기타"])[0, 1])
        s = mon.sort_values(val); h = len(s) // 2
        mon.attrs["좋은달_기타"] = float(s.tail(h)["기타"].mean())
        mon.attrs["나쁜달_기타"] = float(s.head(h)["기타"].mean())

    load = m.groupby("생산일자")["h"].sum().rename("부하h")
    dd = de.assign(일=to_dt(de["검사일"]).dt.strftime("%Y-%m-%d")).groupby("일")[["검사수량", "불량수량"]].sum()
    j = dd.join(load, how="inner")
    j["구간"] = pd.qcut(j["부하h"], 4, labels=["하위 25%", "25~50%", "50~75%", "상위 25%"])
    q = (j.groupby("구간", observed=True)
           .agg(일수=("부하h", "size"), 부하h=("부하h", "median"),
                검사수량=("검사수량", "sum"), 불량수량=("불량수량", "sum")).reset_index())
    q["불량률"] = q["불량수량"] / q["검사수량"] * 100
    q.attrs["상관"] = float(np.corrcoef(j["부하h"], j["불량수량"] / j["검사수량"])[0, 1])
    초과 = int((j["부하h"] > float(cf["정규h"].sum())).sum()) if len(cf) else 0

    de2 = de.merge(o[["수주ID", dim]], on="수주ID")
    k = de2.groupby(de2[dim].eq(val))[["검사수량", "불량수량"]].sum()
    rate = (k["불량수량"] / k["검사수량"] * 100)
    return {"공정별": proc, "월별": mon, "부하별": q, "초과일수": 초과, "가동일": days,
            "불량률": {val: float(rate.get(True, float("nan"))), "기타": float(rate.get(False, float("nan")))},
            "대상": val, "효과건수": eff}

def shake(g: pd.DataFrame, denom: str, rate: str) -> pd.DataFrame:
    """표본을 흔들어 본다 — **한 건이 바뀌면 값이 얼마나 움직이는가.**

    ★ 2026-09-08 Day1 프롬프트 4 신설. `표본부족`(분모 < MIN_SAMPLE) 불리언은
      있었는데 *얼마나 흔들리는지*가 없었다. 둘은 다른 것을 말한다 —
      전자는 "이 칸을 믿을 수 있나", 후자는 **"이 축으로 결론을 낼 수 있나"** 다.

    한 건이 뒤집히면 비율은 `1/분모` 만큼 움직인다. 그 폭을 **칸 사이 격차**와
    견준다. 흔들림이 격차보다 크면 순위가 한 건으로 뒤집힌다는 뜻이라
    **그 축으로는 결론을 낼 수 없다.** 값이 틀린 것이 아니라 *격차가 없는* 것이다.

    축 이름·컬럼 이름을 여기에 적지 않는다 — 분모 컬럼과 비율 컬럼만 받는다.
    funnel_by(도달·전환율)에도 metric_by(분모·준수율)에도 그대로 걸린다.

    반환: 원본 + [흔들림, 격차, 결론가능, 건수로쓸것]
      흔들림   한 건이 바뀔 때 움직이는 %p (칸마다)
      격차     칸 사이 최고−최저 %p (축 전체에 같은 값)
      결론가능 격차 > 최대 흔들림
      건수로쓸것 분모가 MIN_COUNT_BASIS 미만 — 비율로 쓰면 큰 표본처럼 읽힌다
    """
    if not len(g):
        return g.assign(흔들림=[], 격차=[], 결론가능=[], 건수로쓸것=[])

    g = g.copy()
    pct = g[rate] * 100 if g[rate].max() <= 1.0 else g[rate]

    g["흔들림"] = 1.0 / g[denom] * 100
    g["격차"] = float(pct.max() - pct.min())
    g["결론가능"] = g["격차"] > g["흔들림"].max()
    g["건수로쓸것"] = g[denom] < C.MIN_COUNT_BASIS
    return g


def shake_verdict(g: pd.DataFrame, dim: str) -> dict:
    """shake() 결과를 한 문장으로. 발견 문장에 그대로 들어갈 재료다.

    교안이 요구한 판정 셋을 그대로 옮긴다 —
      흔들림 < 격차          격차가 진짜다. 근거로 쓸 수 있다
      흔들림 > 격차          못 쓴다. 표본이 더 필요하다
      분모가 작은 칸이 있다  비율로 쓰지 말고 건수로 쓴다
    """
    if not len(g) or "흔들림" not in g:
        return {"축": dim, "판정": "계산 없음", "문장": ""}

    gap = float(g["격차"].iloc[0])
    mx = float(g["흔들림"].max())
    small = g.loc[g["건수로쓸것"], dim].tolist() if "건수로쓸것" in g else []

    if gap > mx:
        판정 = "근거로 쓸 수 있다"
        문장 = (f"격차 {gap:.2f}%p 가 한 건 흔들림 {mx:.3f}%p 보다 크다"
                f" (최소 분모 {int(g[denom_of(g)].min()):,}건).")
    else:
        판정 = "결론을 낼 수 없다"
        문장 = (f"한 건 흔들림 {mx:.3f}%p 가 격차 {gap:.2f}%p 보다 크다 —"
                f" 한 건으로 순위가 뒤집힌다. 표본이 더 필요하다.")
    if small:
        문장 += f" ★ {', '.join(map(str, small))} 은 분모가 작아 비율 말고 건수로 쓴다."
    return {"축": dim, "판정": 판정, "격차": gap, "최대흔들림": mx, "문장": 문장}


def denom_of(g: pd.DataFrame) -> str:
    """분해 표에서 분모 컬럼 이름을 찾는다. funnel_by 는 `도달`, metric_by 는 `분모`."""
    for c in ("분모", "도달"):
        if c in g.columns:
            return c
    raise KeyError("분모 컬럼(분모·도달)을 찾을 수 없다")


# ── 유지 퍼널 ─────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def retention_funnel(t: dict) -> pd.DataFrame:
    """유지 퍼널. config.RETENTION_STEPS 의 단계대로 센다.

    획득 퍼널과 다른 점 셋:

        단계    주어지지 않는다. **내가 정의한다**
        방향    한 방향이 아니다. 오갈 수 있다
        시간    며칠이 아니라 몇 달~몇 년

    **퍼널이 아니면 퍼널이라고 부르지 않는다.** 세 가지를 물어라.

        이 단계는 앞 단계를 반드시 거치는가?  → 그렇다. 셋이 중첩이다
        그레인이 무엇인가?                    → 제품도번 1개. 그 안의 발주 건을 센다
        기간을 어떻게 자르는가?                → 완주 코호트 61일 + 납기 도래

    ⚠️ **우리 유지는 고객 유지가 아니라 수주 생존이다.**
       통신사의 유지는 사람이 남는가지만, 우리 수주는 출하되면 거기서 끝난다.
       이름만 같고 뜻이 다른 것을 같은 말로 부르면 읽는 사람이 잘못 읽는다 —
       그래서 화면에도 이 문장을 띄운다.

    그리고 **관측 기간이 다른 대상을 누적값으로 비교하지 않는다.**
    7주차에 겪은 생존 편향이 여기서 다시 나온다. 코호트를 안 자르면
    "아직 납기가 안 온 수주"가 전부 미출하로 잡혀 이탈률이 부풀어 오른다.

    반환: DataFrame[step, label, n, step_rate, cum_rate, is_bottleneck]
    """
    if not C.RETENTION_STEPS:
        return pd.DataFrame()

    d = order_facts(t["orders"], t["order_events"])
    d = d[d["완주"]]                      # ← 생존 편향 차단. 여기가 핵심이다.

    # 단계 이름 → 그 단계에 남아 있는 수주의 마스크. 중첩이 되도록 누적으로 건다.
    #   ★ 미납없음 — 미납확인을 한 번도 안 거친 수주. 획득 퍼널에서는 순환의 입구라
    #     뺐지만, 유지 축에서는 "한 번에 통과했나"를 묻는 우리 신호다.
    unpaid = set(t["order_events"].loc[
        t["order_events"]["이벤트구분"] == C.STAGE_UNPAID, "수주ID"])
    no_unpaid = ~d["수주ID"].isin(unpaid)
    masks = {
        "납기도래": d["납기도래"],
        "미납없음": d["납기도래"] & no_unpaid,
        "출하완료": d["납기도래"] & no_unpaid & d["출하완료"],
        "납기내출하": d["납기도래"] & no_unpaid & d["납기내출하"],
    }

    rows, prev = [], None
    for name, desc in C.RETENTION_STEPS:
        m = masks.get(name)
        if m is None:                     # 정의에 없는 단계는 조용히 빠지지 않게 막는다
            raise KeyError(
                f"RETENTION_STEPS 의 '{name}' 을 계산할 방법이 metrics.retention_funnel "
                f"에 없습니다. 단계를 추가했으면 masks 에도 함께 넣으십시오.")
        n = int(m.sum())
        rows.append({"step": name, "label": name, "desc": desc, "n": n,
                     "step_rate": np.nan if prev is None else (n / prev if prev else np.nan)})
        prev = n

    r = pd.DataFrame(rows)
    r["cum_rate"] = r["n"] / r["n"].iloc[0] if r["n"].iloc[0] else np.nan
    r["is_bottleneck"] = False
    if r["step_rate"].notna().any():
        r.loc[r["step_rate"].idxmin(), "is_bottleneck"] = True
    return r


@st.cache_data(show_spinner=False)
def urgent_stats(t: dict) -> dict:
    """긴급품 — 납기가 지났는데 아직 안 나간 수주. **빠져나간 게 아니라 남아 있다.**

    코호트를 자른 것과 안 자른 것을 함께 돌려준다. 착시가 얼마나인지 보이려고.
    """
    d = order_facts(t["orders"], t["order_events"])
    due = d[d["납기도래"]]
    mat = due[due["완주"]]
    return {
        "긴급건": int(mat["긴급"].sum()),
        "긴급률": float(mat["긴급"].mean() * 100) if len(mat) else 0.0,
        "분모": int(len(mat)),
        "긴급률_코호트미적용": float(due["긴급"].mean() * 100) if len(due) else 0.0,
    }


# ── KPI ───────────────────────────────────────────────────────────
@st.cache_data(show_spinner=False)
def unit_cost(t: dict) -> dict:
    """개당 원가 — 재료비는 BOM 에서 도번별로, 인건·가공은 매출 대비 총액 배부.

    ⚠️ **product_cost_bom 의 인건비·가공비·영업이익·이익률 컬럼은 쓰지 않는다.**
       그 컬럼들은 배부 전 값이라 도번당 몇 원 수준이고, 그대로 합치면
       이익률이 60%대로 나온다. 제조업에서 나올 수 없는 값이다.
       (8/29에 한 번 이 값을 그대로 썼다가 걸렀다 — 비율이 이상하면
        **절대금액 하나를 외부 시세와 맞춰 본다**가 그때의 교훈이다.)

    인건·가공 배부 비율은 **가정값**이다 → config.COST_RATIO.
    리포트에 들어가면 "가정값 기반"을 문장에 남긴다.
    """
    o, pc, wl = t["orders"], t["product_cost_bom"], t["worklog_검사"]

    price_by = pc.set_index("제품도번")["판매단가"]
    mat_by = pc.set_index("제품도번")["재료비"]
    qty = o["수량"].to_numpy()

    sales = float((qty * price_by.reindex(o["제품도번"]).to_numpy()).sum())
    produced = int(wl["생산수량"].sum())
    W = int(qty.sum())

    price = float((price_by.reindex(o["제품도번"]).to_numpy() * qty).sum() / W)
    cost = {
        "재료비": float((mat_by.reindex(o["제품도번"]).to_numpy() * qty).sum() / W),
        "인건비": sales * C.COST_RATIO["인건비"] / produced,
        "가공비": sales * C.COST_RATIO["가공비"] / produced,
    }
    cost["영업이익"] = price - sum(cost.values())
    return {"cost": cost, "price": price, "sales": sales, "produced": produced}


@st.cache_data(show_spinner=False)
def kpis(t: dict) -> dict:
    """지표 카드.

    ★ 골격의 예시 컬럼(billing_amount · is_churned)은 우리 데이터에 없다.
      금액은 product_cost_bom.판매단가, 이탈은 order_facts 에서 계산한다.

    **없는 지표는 뺀다. 4개일 이유가 없다.**
    골격 예시의 ARPU 는 우리에게 뜻이 없어 넣지 않았다.

    ★ 개당 영업이익도 **일부러 뺐다.** 5원쯤으로 나오는데, 그 값은 인건·가공
      배부 비율(가정값)과 판매단가(역산값)가 거의 다 결정한다. 카드에 올리면
      실측처럼 읽히고, 회의실에서는 카드에 있던 숫자가 인용된다.
      원가는 **가정값이라는 라벨을 붙일 수 있는 자리**(리포트 5장·유효 원가 화면)에만 둔다.
      대신 네 번째 자리에 **지연 출하율**을 넣었다 — 우리 병목의 진짜 얼굴이다.
      탈락률(4.6%)로는 안 보이던 것이 납기 축에서 드러난 값이다.

    반환: {"지표이름": {"value": float, "unit": str, "fmt": str, "note": str}}
    """
    d = order_facts(t["orders"], t["order_events"])
    de = t["defect_events"]
    due = d[d["납기도래"]]
    ch = urgent_stats(t)

    shipped = int(d["출하완료"].sum())
    late = int(d["지연출하"].sum())

    return {
        # 주지표 — 분모는 **납기 도래 전체**다. 출하한 건만 세면 미납이 분모에서
        # 빠져 어려운 건을 미룰수록 지표가 올라간다(굿하트).
        "납기 준수율": {"value": float(due["납기내출하"].mean() * 100),
                        "unit": "%", "fmt": "{:.1f}%",
                        "note": f"분모 = 납기 도래 {len(due):,}건"},
        # 가드레일 — 건수가 아니라 **수량 가중**이다. 큰 로트 한 건이 지배한다.
        "불량률": {"value": float(de["불량수량"].sum() / de["검사수량"].sum() * 100),
                   "unit": "%", "fmt": "{:.2f}%",
                   "note": f"수량 가중 · 검사 {de['검사수량'].sum():,}개"},
        # ★ 이름을 "이탈"이 아니라 **긴급품**으로 쓴다. 사라진 게 아니라 남아 있는 것이라
        #   대응이 정반대다 — 이탈은 되찾는 일이고, 긴급품은 먼저 내보내는 일이다.
        "긴급품 비율": {"value": ch["긴급률"], "unit": "%", "fmt": "{:.1f}%",
                        "note": f"{C.URGENT_DEF} · {ch['긴급건']:,}건"},
        # 분모가 위 둘과 다르다 — **출하된 건** 중 늦은 비율이다.
        # 미출하를 분모에 넣으면 지연과 이탈이 섞여 둘 다 안 보인다.
        "지연 출하율": {"value": late / shipped * 100 if shipped else 0.0,
                        "unit": "%", "fmt": "{:.1f}%",
                        "note": f"출하 {shipped:,}건 중 {late:,}건이 납기 이후"},
    }


@st.cache_data(show_spinner=False)
def monthly(t: dict) -> pd.DataFrame:
    """기간별 추이. 지표 카드의 스파크라인과 아카이브 비교에 쓴다.

    kpis() 가 돌려주는 지표 이름과 **열 이름이 대응**되어야 스파크라인이 그려진다.

    ★ 지표마다 **기준 날짜가 다르다.** 납기 준수율은 납기일, 불량률은 검사일이다.
      한 날짜로 묶으면 편하지만 그러면 둘 중 하나가 틀린다.

    ★ MIN_SAMPLE 미만인 달은 **뺀다.** 분모가 작은 달이 추이를 요동치게 만든다.
    """
    d = order_facts(t["orders"], t["order_events"])
    due = d[d["납기도래"]].copy()
    due["월"] = due["납기일"].dt.to_period("M").astype(str)
    g = due.groupby("월").agg(분모=("납기내출하", "size"), 준수=("납기내출하", "sum"))
    g = g[g["분모"] >= C.MIN_SAMPLE]
    g["납기 준수율"] = (g["준수"] / g["분모"] * 100).round(1)

    # ★ 2026-09-04 — 긴급품·지연 출하도 월별로 낸다.
    #   전에는 이 둘이 추이에 없어서 **카드는 4개인데 전후 비교는 2개**였다.
    #   화면에 안 보이는 지표는 "괜찮은 것"으로 읽힌다 — 카드에 세워 놓고
    #   변화를 안 보여주면 나빠지는 중이어도 아무도 모른다.
    #
    #   둘 다 **납기일** 기준이다. 카드의 전사 값과 같은 정의를 쓴다:
    #     긴급품    납기가 지났는데 아직 미출하        (유예 0일)
    #     지연 출하  출하는 됐으나 납기일을 넘김
    #   분모도 카드와 같게 둔다 — 긴급품은 납기도래분, 지연은 그중 출하분이다.
    g["긴급품 비율"] = (due.groupby("월")
                       .apply(lambda x: (~x["출하완료"]).sum() / len(x) * 100,
                              include_groups=False).round(2))
    shipped = due[due["출하완료"]]
    g["지연 출하율"] = (shipped.groupby("월")
                       .apply(lambda x: (~x["납기내출하"]).sum() / len(x) * 100,
                              include_groups=False).round(2))

    #   아직 확정 안 된 달은 **계산 결과를 지운다** (config.DUE_SETTLE_DAYS).
    #   감추는 것이 아니라 값 자체를 안 남긴다 — 변수에 들어 있으면 리포트로 샌다.
    asof = to_dt(t["orders"]["수주일"]).max()
    settled = (pd.PeriodIndex(g.index, freq="M").to_timestamp(how="end").normalize()
               + pd.Timedelta(days=C.DUE_SETTLE_DAYS)) <= asof
    g.loc[~settled, ["긴급품 비율", "지연 출하율"]] = pd.NA

    de = t["defect_events"].copy()
    de["월"] = to_dt(de["검사일"]).dt.to_period("M").astype(str)
    gd = (de.groupby("월")
            .apply(lambda x: x["불량수량"].sum() / x["검사수량"].sum() * 100,
                   include_groups=False)
            .round(2).rename("불량률"))

    m = g[["납기 준수율", "분모", "긴급품 비율", "지연 출하율"]].join(gd, how="inner")

    # ★ 유효 구간 — 분모가 얇은 달을 뺀다 (Day3 프롬프트 10).
    #   MIN_SAMPLE 은 절대 건수라 데이터 시작 경계를 못 잡는다(첫 달 115 > 100).
    #   중앙값 대비 비율로 잘라야 데이터가 늘어도 규칙이 그대로 산다.
    if len(m) >= 3:
        thin = m["분모"] < m["분모"].median() * C.THIN_MONTH_RATIO
        m = m[~thin]

    m.index.name = "월"
    return m


@st.cache_data(show_spinner=False)
def valid_period(t: dict) -> dict:
    """유효 구간 — 월별 추이에서 **실제로 쓰는 범위**와 뺀 달.

    금요일 리포트의 한계 절에 그대로 들어간다.
    *"언제부터 언제까지를 믿을 수 있는가"* 에 답할 재료다.
    """
    d = order_facts(t["orders"], t["order_events"])
    due = d[d["납기도래"]].copy()
    due["월"] = due["납기일"].dt.to_period("M").astype(str)
    g = due.groupby("월").agg(분모=("납기내출하", "size"))
    g = g[g["분모"] >= C.MIN_SAMPLE]
    med = g["분모"].median()
    thin = g[g["분모"] < med * C.THIN_MONTH_RATIO]
    kept = g[g["분모"] >= med * C.THIN_MONTH_RATIO]
    return {
        "시작": kept.index.min() if len(kept) else None,
        "끝": kept.index.max() if len(kept) else None,
        "쓴달": int(len(kept)), "뺀달": int(len(thin)),
        "뺀목록": [(i, int(v)) for i, v in thin["분모"].items()],
        "중앙분모": int(med) if len(g) else 0,
    }


def status_of(name: str, value: float) -> str:
    """지표 값을 상태 색으로 판정한다. 임계값은 config.THRESHOLDS 에 있다.

    이 함수는 **그대로 쓴다.** 판정 규칙이지 도메인이 아니다.
    THRESHOLDS 가 비어 있으면 전부 "ok"로 나온다 — 채우면 색이 갈린다.
    """
    th = C.THRESHOLDS.get(name)
    if not th:
        return "ok"
    # ★ 높을수록 나쁜 지표. 내 지표 이름을 넣는다.
    higher_is_worse = {"긴급품 비율", "지연 출하율", "이탈률", "이탈율",
                       "해지율", "불량률", "반품률"}
    if name in higher_is_worse:
        return ("block" if value > th["위험"]
                else "warn" if value > th["경고"] else "ok")
    return ("block" if value < th["위험"]
            else "warn" if value < th["경고"] else "ok")


# ── 실험 ──────────────────────────────────────────────────────────
# ★ 실험별로 **무엇을 성과로 볼지**. 도메인이 바뀌면 이 표를 갈아끼운다.
#
#   골격 원본은 EXP_STEPS = {"EXP-001": ("랜딩방문", "요금제조회")} 처럼
#   **퍼널 두 단계 사이의 전환**만 성과로 볼 수 있었다. 우리 실험 셋 중 둘은
#   퍼널 단계가 아니라 **사건의 발생 여부**(불량 스파이크가 났는가)가 성과라
#   구간 대신 **결과 이름**을 적는 형태로 바꿨다.
#
#   전부 "좋은 일이 일어났는가"(1이면 좋음)로 방향을 맞춰 뒀다.
#   방향이 섞이면 lift 부호를 읽을 때마다 헷갈리고, 언젠가 반대로 읽는다.
EXP_SPEC = {
    "EXP-001": {"outcome": "스파이크미발생", "guardrail": "납기내출하"},
    "EXP-002": {"outcome": "납기내출하", "guardrail": "납기내출하"},
    "EXP-003": {"outcome": "공정착수", "guardrail": "납기내출하"},
}


@st.cache_data(show_spinner=False)
def outcome_flags(t: dict, name: str) -> pd.Series:
    """수주ID → 0/1. **1이 좋은 일**이다.

    실험 성과를 여기 한곳에서만 만든다. 화면과 리포트가 따로 세면 어긋난다.
    """
    if name == "스파이크미발생":
        de = t["defect_events"]
        spike = de.groupby("수주ID", observed=True)["스파이크"].any()
        return (~spike).astype(int)
    if name == "납기내출하":
        d = order_facts(t["orders"], t["order_events"])
        return d.set_index("수주ID")["납기내출하"].astype(int)
    if name == "공정착수":
        fr = first_reach(t["order_events"])
        hit = set(fr.loc[fr["이벤트구분"] == C.FIRST_PROCESS, "수주ID"])
        ids = t["orders"]["수주ID"]
        return pd.Series(ids.isin(hit).astype(int).to_numpy(), index=ids)
    raise KeyError(f"성과 '{name}' 을 계산할 방법이 outcome_flags 에 없습니다.")


def _two_prop(sc, nc, stt, nt):
    """두 비율 비교. 차이·신뢰구간·p값을 함께 돌려준다.

    **그대로 쓴다.** 통계 계산은 도메인이 바뀌어도 같다.

    p값만 보면 '유의하지만 실질 효과가 없는' 경우를 놓친다.
    그래서 신뢰구간을 항상 함께 계산해 화면에 그린다.
    """
    rc, rt = sc / nc, stt / nt
    se = np.sqrt(rc * (1 - rc) / nc + rt * (1 - rt) / nt)
    if se == 0:
        return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=0, lo=0, hi=0, p=1.0, lift=0)
    z = (rt - rc) / se
    return dict(rc=rc, rt=rt, nc=nc, nt=nt, diff=rt - rc,
                lo=(rt - rc) - 1.96 * se, hi=(rt - rc) + 1.96 * se,
                p=2 * (1 - stats.norm.cdf(abs(z))),
                lift=(rt / rc - 1) if rc else 0)


def srm_check(asg: pd.DataFrame, exp_id: str) -> dict:
    """SRM(Sample Ratio Mismatch). 배정이 50:50인지 검정한다.

    **그대로 쓴다.** 7주차에 손으로 해본 그 계산이다.

    배정이 50:50이 아니면 배정 로직에 버그가 있다는 뜻이고,
    그 경우 어떤 효과가 나오든 해석할 수 없다.
    """
    a = asg[asg.experiment_id == exp_id]
    c = int((a.variant == "control").sum())
    t = int((a.variant == "treatment").sum())
    if c + t == 0:
        return {"ok": False, "c": 0, "t": 0, "p": 1.0, "ratio": (0.0, 0.0)}
    p = stats.chisquare([c, t]).pvalue
    return {"ok": p >= 0.001, "c": c, "t": t, "p": float(p),
            "ratio": (c / (c + t), t / (c + t))}


def trust_check(srm: dict, n_total: int, days: int | None = None) -> str | None:
    """이 실험을 믿을 수 있는가. **계산하기 전에** 묻는다.

    ────────────────────────────────────────────────────────────
    어려운 일은 계산이 아니다.
    **계산은 이미 할 수 있는데, 화면에 안 그리는 코드를 쓰는 것**이다.
    ────────────────────────────────────────────────────────────

    못 믿을 조건은 셋인데 **분기는 하나**다.

        배정이 깨졌다      srm["ok"] 가 False
        표본이 모자란다    n_total 이 config.MIN_SAMPLE 미만
        기간이 안 찼다     days 가 config.MIN_EXP_DAYS 미만

    하나라도 걸리면 **사유 문자열**을 돌려준다. 돌려주면
    experiment_results() 가 거기서 멈추고 **지표를 계산하지 않는다.**
    다 통과하면 None 을 돌려준다.

    "그래도 회색으로라도 보여주면 안 되나요?"

        안 됩니다. **사람은 본 숫자를 기억합니다.**
        옆에 아무리 경고를 붙여도 회의실에서 인용되는 것은 숫자입니다.

    ★ 걸린 사유를 **전부** 돌려준다. 첫 하나만 돌려주면 그것만 고치고
      다시 돌렸을 때 또 막힌다 — 두 번 헛걸음하게 된다.

    반환: 못 믿을 이유(str) 또는 None
    """
    why = []
    if not srm["ok"]:
        why.append(
            f"배정이 {srm['ratio'][0]*100:.1f}:{srm['ratio'][1]*100:.1f} 로 "
            f"깨졌습니다 (p={srm['p']:.1e}). 어떤 효과가 나와도 해석할 수 없습니다.")
    if n_total < C.MIN_SAMPLE:
        why.append(f"표본이 {n_total:,}건으로 최소 {C.MIN_SAMPLE:,}건에 못 미칩니다.")
    if days is not None and days < C.MIN_EXP_DAYS:
        why.append(f"기간이 {days}일로 최소 {C.MIN_EXP_DAYS}일에 못 미칩니다. "
                   f"새 절차에 긴장한 기간만 잰 것이라 평상시 모습이 아닙니다.")
    return " ".join(why) if why else None


@st.cache_data(show_spinner=False)
def experiment_results(t: dict) -> list[dict]:
    """실험 결과와 판정.

    **판정 순서가 이 함수의 전부다.** 믿을 수 있는지 먼저 묻고,
    믿을 수 있을 때만 계산한다.

    좋은 결과를 먼저 보면 경고를 무시하고 싶어진다. 그래서 사람의 규율에
    맡기지 않고 **코드로 순서를 박는다.**

    ⚠️ **우리 실험 데이터는 설계이지 실행 기록이 아니다.**
       7주차에 설계만 해 둔 것을 데이터로 옮겨 판정 로직을 돌려본 것이다.
       리포트 5장·7장이 이 사실을 문장으로 남긴다.

    ⚠️ **EXP-001 의 "효과 없음"은 발견이 아니다.**
       배정(experiment_assignments)은 나중에 만들었고 불량 데이터는 그 전에
       만들어져서, **배정이 결과에 영향을 줄 수 있는 경로가 애초에 없다.**
       효과가 안 나오는 것이 당연하고, 여기서 "검사 강화는 소용없다"를 읽으면 안 된다.
       효과를 심어 넣지 않은 이유 — 심으면 우리가 하지도 않은 실험이
       "성공"으로 리포트에 실린다. **없는 성과를 만드는 것보다 빈 채로 두는 편이 낫다.**
       계산기가 제대로 도는지는 대신 tests/test_metrics.py 에서
       **답을 아는 표본**으로 확인한다.
    """
    if "experiments" not in t or "experiment_assignments" not in t:
        return []
    ex, asg = t["experiments"], t["experiment_assignments"]
    facts = order_facts(t["orders"], t["order_events"])
    guard_base = facts.set_index("수주ID")["납기내출하"].astype(int)

    out = []
    for _, e in ex.iterrows():
        eid = e.experiment_id
        srm = srm_check(asg, eid)
        a_all = asg[asg.experiment_id == eid]
        n_total = int(len(a_all))
        days = (pd.Timestamp(e.end_date) - pd.Timestamp(e.start_date)).days
        row = {
            "id": eid, "name": e.experiment_name, "hypothesis": e.hypothesis,
            "primary": e.primary_metric, "guardrail": e.guardrail_metric,
            "start": e.start_date, "end": e.end_date, "srm": srm,
            "unit": e.get("unit", ""), "days": days, "n_total": n_total,
        }

        # ★ 판정 과정을 **기록으로 남긴다** (2026-09-04, Day3 프롬프트 12).
        #   결과만 보이면 "왜 효과 없음이지"에 사람이 답을 못 한다. 어느 물음에서
        #   갈렸는지가 안 보이면, 읽는 사람은 마지막 배지 하나로 전부를 판단한다.
        #   ★ 계산은 여기서 한다 — 화면은 이 목록을 펼치기만 한다.
        steps = []

        def _step(q, passed, detail):
            # ⚠️ bool() 로 눌러 담는다. moved·sig 는 numpy 비교라 `numpy.bool_`
            #    인데, `numpy.bool_(False) is False` 는 **False** 다.
            #    그대로 두면 화면의 `passed is False` 분기가 조용히 안 걸린다 —
            #    2026-09-04 에 실제로 EXP-001 만 "어디서 갈렸는가"가 비어 나왔다.
            #    값은 맞고 판정도 맞는데 라벨만 틀리는, 눈으로는 못 찾는 종류다.
            steps.append({"q": q,
                          "passed": None if passed is None else bool(passed),
                          "detail": detail})

        # ★ 판정이 계산보다 먼저다. 못 믿으면 여기서 끝난다.
        reason = trust_check(srm, n_total, days)
        _step("믿을 수 있는가", not reason,
              reason or f"배정 {n_total:,}건 · {days}일 — 세 조건을 다 넘었습니다")
        if reason:
            row["verdict"] = "무효"
            row["color"] = "block"
            row["reason"] = reason
            row["steps"] = steps
            # 뒤 물음들은 **묻지도 않았다.** 안 적으면 '통과'로 읽힌다.
            for q in ("차이가 큰가", "우연이 아닌가", "가드레일은 괜찮은가"):
                steps.append({"q": q, "passed": None,
                              "detail": "묻지 않았습니다 — 앞에서 끝났습니다"})
            out.append(row)
            continue        # 지표를 계산하지 않는다. 숨기는 것이 아니다.

        # ── 여기부터 계산 ─────────────────────────────────────────
        spec = EXP_SPEC.get(eid)
        if spec is None:
            row.update(verdict="데이터 없음", color="none",
                       reason="EXP_SPEC 에 이 실험의 성과 정의가 없습니다.")
            out.append(row)
            continue

        flags = outcome_flags(t, spec["outcome"])
        a = a_all[["수주ID", "variant", "assigned_at"]].copy()
        a["conv"] = a["수주ID"].map(flags)
        a = a.dropna(subset=["conv"])
        a["conv"] = a["conv"].astype(int)

        g = a.groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(g) < 2 or g["count"].min() == 0:
            row.update(verdict="데이터 없음", color="none",
                       reason="대조군·처치군 중 한쪽에 성과를 붙일 수 있는 수주가 없습니다.")
            out.append(row)
            continue
        r = _two_prop(g.loc["control", "sum"], g.loc["control", "count"],
                      g.loc["treatment", "sum"], g.loc["treatment", "count"])
        row.update(r, outcome=spec["outcome"], assignments=a)

        # 가드레일 — 주지표를 올리려 할 때 희생될 수 있는 것.
        # 우리 가드레일은 전부 **납기 준수율**이다. 불량을 잡으려다 납기를 놓치면
        # 성공이 아니다 — 7주차 가설 노트에서 정한 그대로다.
        row["guard"] = None
        gv = a.assign(g=a["수주ID"].map(guard_base)).dropna(subset=["g"])
        if gv["variant"].nunique() == 2:
            gm = gv.groupby("variant", observed=True)["g"].mean()
            row["guard"] = {
                "name": e.guardrail_metric,
                "control": float(gm["control"]),
                "treatment": float(gm["treatment"]),
                "delta": float(gm["treatment"] - gm["control"]),
            }

        # ── 판정 (Day3 실습 C · 프롬프트 4) ─────────────────────────
        # ★ **순서가 이 블록의 전부다.** 교안:
        #     1. 주지표가 [얼마] 이상 움직였는가 — 아니면 "효과 없음"
        #     2. 가드레일이 [얼마] 이상 나빠졌는가 — 그러면 "주의 필요"
        #     3. 둘 다 통과하면 "성공"
        #   *"2번을 1번 뒤에 두고, 1번을 통과했다고 바로 성공으로 가지 마."*
        #   주지표가 좋으면 거기서 멈추고 싶어지는데 코드는 멈추지 않는다.
        #
        # ★ 2026-09-03 정정 — 전에는 `p < 0.05` 하나로만 갈렸다. **크기 기준이 없었다.**
        #   표본이 크면 0.1%p 차이도 유의해진다. 유의성은 *"우연이 아니다"* 이지
        #   *"의미 있게 크다"* 가 아니다. 둘을 **함께** 본다.
        moved = abs(r["diff"]) * 100 >= C.EFFECT_MIN_PP     # 크기
        sig = r["p"] < 0.05                                  # 우연이 아님
        guard_bad = (row["guard"] is not None
                     and row["guard"]["delta"] < -C.GUARDRAIL_TOLERANCE)

        _step("차이가 큰가", moved,
              f"차이 {r['diff']*100:+.2f}%p · 기준 {C.EFFECT_MIN_PP}%p "
              f"(평소 월 변동 폭)")
        _step("우연이 아닌가", sig, f"p={r['p']:.4f} · 기준 0.05")

        if not (moved and sig):
            # 1번에서 걸림 — 가드레일을 보러 가지 않는다
            steps.append({"q": "가드레일은 괜찮은가", "passed": None,
                          "detail": "묻지 않았습니다 — 주지표가 안 움직였습니다"})
            why = []
            if not moved:
                why.append(f"차이 {r['diff']*100:+.2f}%p 는 "
                           f"평소 변동 폭({C.EFFECT_MIN_PP}%p)보다 작습니다")
            if not sig:
                why.append(f"우연과 구분되지 않습니다 (p={r['p']:.3f})")
            row.update(verdict="효과 없음", color="none", reason=". ".join(why) + ".")
        elif guard_bad:
            _step("가드레일은 괜찮은가", False,
                  f"{e.guardrail_metric} {row['guard']['delta']*100:+.1f}%p · "
                  f"허용 -{C.GUARDRAIL_TOLERANCE*100:.0f}%p")
            row.update(verdict="주의 필요", color="warn",
                       reason=f"주지표는 {r['diff']*100:+.2f}%p 움직였으나 "
                              f"가드레일({e.guardrail_metric})이 "
                              f"{row['guard']['delta']*100:.1f}%p 악화됐습니다 "
                              f"(허용 -{C.GUARDRAIL_TOLERANCE*100:.0f}%p).")
        elif r["lift"] > 0:
            _step("가드레일은 괜찮은가", True,
                  f"{e.guardrail_metric} "
                  f"{(row['guard']['delta']*100 if row['guard'] else 0):+.1f}%p "
                  f"· 허용 -{C.GUARDRAIL_TOLERANCE*100:.0f}%p")
            row.update(verdict="성공", color="ok", reason="")
        else:
            _step("가드레일은 괜찮은가", True, "가드레일은 이상 없습니다")
            row.update(verdict="악화", color="block",
                       reason=f"주지표가 {r['diff']*100:+.2f}%p 나빠졌습니다.")
        row["steps"] = steps
        out.append(row)
    return out


def peeking_curve(res: dict, start: str, cuts=(7, 14, 30, 60, 92)) -> pd.DataFrame:
    """관측 시점별 누적 결과. '그때 멈췄다면 무엇을 봤을까'를 재현한다.

    **그대로 쓴다.** 7주차에 겪은 조기 중단이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["d"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days
    rows = []
    for c in cuts:
        s = a[a.d <= c].groupby("variant", observed=True).conv.agg(["sum", "count"])
        if len(s) < 2 or s["count"].min() < 30:
            continue
        r = _two_prop(s.loc["control", "sum"], s.loc["control", "count"],
                      s.loc["treatment", "sum"], s.loc["treatment", "count"])
        rows.append({"cut": c, "lift": r["lift"], "p": r["p"], "sig": r["p"] < 0.05})
    return pd.DataFrame(rows)


def weekly_effect(res: dict, start: str, bucket_days: int = 14) -> pd.DataFrame:
    """기간을 쪼개 효과 추이를 본다. 신규성 효과는 전체 평균에 가려진다.

    **그대로 쓴다.** 7주차에 겪은 그것이다.
    """
    a = res.get("assignments")
    if a is None:
        return pd.DataFrame()
    a = a.copy()
    a["b"] = (to_dt(a.assigned_at) - pd.Timestamp(start)).dt.days // bucket_days
    g = (a[a.b >= 0].groupby(["b", "variant"], observed=True).conv
         .mean().unstack().dropna())
    if g.empty:
        return pd.DataFrame()
    g["lift"] = g.treatment / g.control - 1
    g = g.reset_index()
    g["label"] = g.b.apply(lambda i: f"{int(i)*2+1}~{int(i)*2+2}주")
    return g


# ── 유효 원가 (골격의 "채널 효율" 자리) ───────────────────────────
@st.cache_data(show_spinner=False)
def channel_efficiency(t: dict) -> pd.DataFrame:
    """싸게 만든 것이 실제로 싼 것이 아니다. 불량을 반영한 유효 원가를 함께 낸다.

    ★ 골격 원본은 **획득 채널별 CAC**였다. 우리는 채널 개념이 없어 갈아끼웠다.
      구조는 그대로다 — 한 번 더 해야 하는 몫을 원가에 얹으면 순위가 뒤집힌다.

          통신사   유효 CAC  = 획득비용 ÷ 유지율    안 남으면 다시 데려와야 한다
          우리     유효 원가 = 총원가  ÷ 양품률     불량 나면 다시 만들어야 한다

      함수 이름은 골격 그대로 두었다. 페이지·차트가 이 이름으로 부르고 있어서,
      이름까지 바꾸면 이식 범위가 넓어진다. **무엇을 계산하는지는 반환 컬럼이 말한다.**

    ⚠️ 원가의 인건·가공 부분은 **가정값 배부**다 → config.COST_RATIO.
       리포트에 이 값이 들어가면 "가정값 기반"을 문장에 남긴다.

    반환: DataFrame[구분, 생산수량, 불량률, 원가, 유효원가, 역전]
    """
    dim = C.EFFICIENCY_DIM
    de, o = t["defect_events"], t["orders"]
    u = unit_cost(t)

    # 축별 불량률 — 수량 가중. 건수로 세면 작은 로트가 과대 대표된다.
    d = (de.groupby(dim, observed=True)
           .agg(검사=("검사수량", "sum"), 불량=("불량수량", "sum"))
           .assign(불량률=lambda x: x["불량"] / x["검사"]))

    # 축별 개당 원가 — 재료비는 도번별 실측, 인건·가공은 전체 배부값을 그대로 쓴다
    # (공정별로 다르게 잡을 근거가 없다. 없는 정밀도를 지어내지 않는다).
    pc = t["product_cost_bom"].set_index("제품도번")
    om = o.assign(재료비=pc["재료비"].reindex(o["제품도번"]).to_numpy())
    m = (om.groupby(dim, observed=True)
           .apply(lambda x: (x["재료비"] * x["수량"]).sum() / x["수량"].sum(),
                  include_groups=False)
           .rename("재료비"))

    g = pd.concat([d["불량률"], m], axis=1).dropna().reset_index()
    g = g.rename(columns={dim: "구분"})
    g["원가"] = g["재료비"] + u["cost"]["인건비"] + u["cost"]["가공비"]
    g["유효원가"] = g["원가"] / (1 - g["불량률"])
    g["생산수량"] = (o.groupby(dim, observed=True)["수량"].sum()
                     .reindex(g["구분"]).to_numpy())

    # 역전 — 단순 원가 순위와 유효 원가 순위가 다른 칸
    g["역전"] = (g["원가"].rank().astype(int)
                 != g["유효원가"].rank().astype(int))
    return g[["구분", "생산수량", "불량률", "원가", "유효원가", "역전"]]


# ── 납기 전망 (5번째 화면 · 우리 도메인 고유) ─────────────────────
@st.cache_data(show_spinner=False)
def backlog(t: dict) -> pd.DataFrame:
    """아직 출하되지 않은 수주를 **납기까지 남은 일수**로 나눈다.

    퍼널은 "몇 건이 통과했나"를 보고, 이 표는 **"지금 무엇이 남아 있나"**를 본다.
    같은 데이터인데 축이 달라서 다른 것이 보인다 — 단계별 탈락은 평평한데
    납기 축에서는 밀린 것이 드러난다.

    반환: DataFrame[구간, 건수, 상태, 비중]
    """
    d = order_facts(t["orders"], t["order_events"])
    o = d[~d["출하완료"]].copy()
    o["남은일"] = (o["납기일"] - TODAY).dt.days

    rows = []
    for lo, hi, name, level in C.BACKLOG_BINS:
        m = o["남은일"].notna()
        if lo is not None:
            m &= o["남은일"] >= lo
        if hi is not None:
            m &= o["남은일"] <= hi
        rows.append({"구간": name, "건수": int(m.sum()), "상태": level})
    # 납기 미정은 구간에 넣지 않는다 — 남은 일수를 셀 수 없다.
    # 빼고 세면 분모가 조용히 줄어드니 **따로 한 줄로 세운다.**
    rows.append({"구간": "납기 미정", "건수": int(o["납기일"].isna().sum()),
                 "상태": "none"})
    b = pd.DataFrame(rows)
    b["비중"] = b["건수"] / len(o) if len(o) else 0.0
    return b


@st.cache_data(show_spinner=False)
def throughput(t: dict) -> dict:
    """최근 실측 처리 속도 — 주당 몇 건을 출하했나.

    **목표가 아니라 실측이다.** 캐파 계산이 아니라 "최근에 실제로 이만큼 했다"다.
    목표치를 쓰면 전망이 희망이 되고, 희망은 회의에서 계획으로 읽힌다.
    """
    d = order_facts(t["orders"], t["order_events"])
    ship = d[d["출하완료"]]
    win = TODAY - pd.Timedelta(days=C.THROUGHPUT_WINDOW_DAYS)
    recent = int((ship["출하일"] > win).sum())
    weeks = C.THROUGHPUT_WINDOW_DAYS / 7
    return {"기간일": C.THROUGHPUT_WINDOW_DAYS, "건수": recent,
            "주당": recent / weeks if weeks else 0.0}


@st.cache_data(show_spinner=False)
def outlook(t: dict) -> pd.DataFrame:
    """주차별 전망 — 밀린 것 + 이번 주 납기 vs 처리 속도.

    ⚠️ **예측이 아니라 산술이다.** 지금 밀린 것과 앞으로 올 납기를 최근 실측
       속도로 나눈 것뿐이다. 계절성·설비 정지·긴급 삽입을 모른다.
       화면에도 이 문장을 띄운다 — 안 띄우면 전망이 예측으로 읽힌다.

    반환: DataFrame[주차, 시작일, 납기도래, 처리, 누적밀림]
    """
    d = order_facts(t["orders"], t["order_events"])
    o = d[~d["출하완료"] & d["납기일"].notna()].copy()
    o["남은일"] = (o["납기일"] - TODAY).dt.days

    cap = throughput(t)["주당"]
    carry = float((o["남은일"] < 0).sum())      # 이미 납기를 넘긴 것부터 지고 간다

    rows = []
    for w in range(C.OUTLOOK_WEEKS):
        due = float(((o["남은일"] >= w * 7) & (o["남은일"] < (w + 1) * 7)).sum())
        need = carry + due
        done = min(need, cap)                    # 밀린 것과 새 납기를 같이 처리한다
        carry = need - done
        rows.append({
            "주차": f"{w + 1}주", "시작일": (TODAY + pd.Timedelta(days=w * 7)).date(),
            "납기도래": int(due), "처리": int(done), "누적밀림": int(carry),
        })
    return pd.DataFrame(rows)


def outlook_verdict(t: dict) -> dict:
    """전망을 한 문장으로. **판정은 사람이 하고, 여기서는 재료만 만든다.**

    ★ 화면이 쓸 값을 **전부 여기서** 만든다. 2026-09-01 감사에서
      `pages/5_납기전망.py` 안에 합계·비율 계산이 4곳 있는 것이 잡혔다.
      DESIGN.md 1절 — *"계산 로직을 두 벌 만들지 마십시오"* ·
      *"계산이 화면 코드 안에 숨어 있지 않은가"*.
      화면에 계산이 남으면 같은 수치를 리포트에서 다시 셀 때 값이 갈린다.
    """
    ol = outlook(t)
    b = backlog(t)
    cap = throughput(t)["주당"]
    start = int(ol["누적밀림"].iloc[0] + ol["처리"].iloc[0] - ol["납기도래"].iloc[0])
    end = int(ol["누적밀림"].iloc[-1])
    # 밀림이 0이 되는 주 — 없으면 None
    zero = next((r["주차"] for _, r in ol.iterrows() if r["누적밀림"] == 0), None)

    open_total = int(b["건수"].sum())
    over = int(b.loc[b["상태"] == "block", "건수"].sum())
    undated = int(b.loc[b["구간"] == "납기 미정", "건수"].sum())
    n_orders = len(t["orders"])
    return {
        "주당처리": cap, "시작밀림": max(start, 0), "끝밀림": end,
        "해소주차": zero, "주차수": C.OUTLOOK_WEEKS,
        "악화": end > max(start, 0),
        "미출하": open_total,
        "미출하비중": open_total / n_orders * 100 if n_orders else 0.0,
        "초과": over,
        "초과비중": over / open_total * 100 if open_total else 0.0,
        "납기미정": undated,
    }


def efficiency_verdict(g: pd.DataFrame) -> dict:
    """순위가 뒤집혔는가. **안 뒤집혔으면 그것도 결과다.**

    골격 원본은 "비용만 보면 순위가 뒤집힌다"를 보여주는 화면이었다.
    우리 데이터에서는 **뒤집히지 않는다.** 그냥 "차이 없음"이라고 쓰면 읽는 사람이
    확인할 수 없으니, **뒤집히려면 무엇이 얼마나 커야 하는지**를 함께 낸다.

        뒤집히려면  불량 보정폭 > 원가 격차
        우리 값     보정폭 0.6원  vs  원가 격차 3.2원  →  구조적으로 불가능

    축을 바꿔도 같다 — 고객사·차종·불량유형·원인구분·설비호기를 전부 확인했고
    불량률 격차가 가장 큰 축도 0.15%p 였다 (2026-09-01).
    **합성 데이터가 축별 구조를 안 갖고 있기 때문이지, 현장에 격차가 없다는 뜻이 아니다.**
    """
    if g.empty:
        return {"역전": 0, "원가격차": 0.0, "보정폭": 0.0, "가능": False}
    cost_gap = float(g["원가"].max() - g["원가"].min())
    adj = float((g["유효원가"] - g["원가"]).max() - (g["유효원가"] - g["원가"]).min())
    return {
        "역전": int(g["역전"].sum()),
        "원가격차": cost_gap,
        "보정폭": adj,
        "가능": adj > cost_gap,       # 보정폭이 격차를 못 넘으면 애초에 못 뒤집는다
        "불량률폭": float(g["불량률"].max() - g["불량률"].min()) * 100,
    }


@st.cache_data(show_spinner=False)
def stage_dwell(t: dict) -> pd.DataFrame:
    """단계 사이에 **며칠 머무는가.** 통과율로는 안 보이는 병목을 시간 축에서 본다.

    ★ 2026-09-05 신설. 우리 퍼널은 전 구간 탈락이 최대 1.6%라 **거의 평평하다** —
      통과율만 보면 "어디가 문제인지 모르겠다"로 끝난다. 같은 퍼널을 날짜로 재면
      공정작업 → 출하 한 구간이 **전체 38일 중 25일(67.6%)** 이다.

      분해에서 겪은 것과 같은 구조다(퍼널 전환율 0.63%p vs 납기 준수율 4.24%p).
      **우리 도메인은 새는 것이 아니라 밀린다.** 퍼널도 그 축으로 봐야 한다.

    ⚠️ **완주 코호트 + 최초 도달**만 센다. 재투입(미납 → 생산계획)으로 되돌아온
       것을 다시 세면 같은 수주가 한 구간에 두 번 들어가 중앙값이 부풀어 오른다.

    ⚠️ 음수는 버린다. 이벤트일이 역행한 행이 데이터에 있을 수 있는데(중복 3%),
       그대로 두면 중앙값이 아니라 **분포 전체**가 왼쪽으로 끌린다.

    ⚠️ **마지막 구간(→ 출하)은 성격이 다르다.** 출하일은 공정이 끝나는 날이
       아니라 **납기에 맞춰 잡히는 날**이다. 그래서 공정이 일찍 끝나면 그만큼
       거기서 기다린다 — 19일이 나와도 그건 *공정 병목이 아니라 납기 대기*다.
       같은 막대에 나란히 놓되 **이름을 다르게 불러야** 오해가 안 생긴다.
       → `dwell_verdict()` 의 `대기구간`

    반환: DataFrame[구간, 앞, 뒤, n, 중앙, 평균, p90, 최대, 비중]
    """
    fr = first_reach(t["order_events"])
    mature = mature_ids(t["orders"])
    w = (fr[fr["수주ID"].isin(mature)]
         .pivot_table(index="수주ID", columns="이벤트구분",
                      values="이벤트일", aggfunc="min"))
    rows = []
    for a, b in zip(C.FUNNEL_STEPS[:-1], C.FUNNEL_STEPS[1:]):
        if a not in w.columns or b not in w.columns:
            continue
        d = (to_dt(w[b]) - to_dt(w[a])).dt.days
        d = d[d >= 0].dropna()
        if d.empty:
            continue
        rows.append({
            "구간": f"{C.FUNNEL_LABELS.get(a, a)} → {C.FUNNEL_LABELS.get(b, b)}",
            "앞": a, "뒤": b, "n": int(len(d)),
            "중앙": float(d.median()), "평균": float(d.mean()),
            "p90": float(d.quantile(0.9)), "최대": float(d.max()),
        })
    g = pd.DataFrame(rows)
    if g.empty:
        return g
    # 비중은 **중앙값 기준**이다. 평균으로 나누면 꼬리가 긴 구간이 과대해진다.
    g["비중"] = g["중앙"] / g["중앙"].sum()
    return g


def dwell_verdict(g: pd.DataFrame) -> dict:
    """체류 분포를 한 줄로. **어디가 얼마나 차지하는가**만 말한다(왜는 말하지 않는다)."""
    if g is None or g.empty:
        return {}
    # ★ 구간을 **셋으로 가른다.** 성격이 다른 것을 한 덩어리로 세면
    #   "가장 긴 구간"이 엉뚱한 데를 가리킨다 — 2026-09-05 에 실제로
    #   "공정에 쓰는 시간 17일, 최장은 영업계획 → 생산계획"이 나왔다.
    #   영업계획은 공정이 아니다.
    #
    #     계획   발주접수 → 지시서작성   서류가 도는 시간
    #     공정   지시서작성 → 검사       실제로 만드는 시간
    #     대기   검사 → 출하             납기를 기다리는 시간 (병목이 아니다)
    last = C.FUNNEL_STEPS[-1]
    proc_set = set(getattr(C, "PROCESS_STEPS", []))
    계획 = g[~g["뒤"].isin(proc_set) & (g["뒤"] != last)]
    공정 = g[g["뒤"].isin(proc_set)]
    대기 = g[g["뒤"] == last]

    top = 공정.loc[공정["중앙"].idxmax()] if len(공정) else g.loc[g["중앙"].idxmax()]
    return {
        "총일수": float(g["중앙"].sum()),
        "계획일수": float(계획["중앙"].sum()),
        "공정일수": float(공정["중앙"].sum()),
        "대기일수": float(대기["중앙"].sum()),
        "대기구간": (대기["구간"].iloc[0] if len(대기) else None),
        "대기비중": float(대기["중앙"].sum() / g["중앙"].sum()) if len(대기) else 0.0,
        "최장구간": top["구간"],
        "최장일수": float(top["중앙"]),
        "구간수": int(len(공정)),
        # 공정 구간끼리만 본다. 평균의 몇 배인가 — 고르면 1.0 에 가깝다.
        "쏠림": float(top["중앙"] / 공정["중앙"].mean()) if len(공정) else 1.0,
    }

# ── 제안서 주제 후보 (2026-09-10 Day3) ────────────────────────────
# ★ **하나만 뽑지 않는다.** 발견 하나로 제안서를 만들면 그날 눈에 띈 것이
#   그대로 이번 분기 우선순위가 된다. 만들 수 있는 만큼 만들어 놓고 고른다.
#
# ★ **기각된 후보를 지우지 않는다.** 지우면 *"안 봤다"* 와 *"보고 아니었다"* 가
#   구분되지 않는다. 기각사유만 채워 맨 뒤로 보낸다.
#
# ⚠️ **기각과 "후보로 안 만듦"은 다르다.**
#     기각 = 비교했는데 차이가 작다 · 안 만듦 = 비교 자체가 안 된다(표본 부족).
#
# ⚠️ 새 임계값을 만들지 않는다. 아래 셋은 **이미 있는 값을 빌려 쓴 것**이다.
#     · EFFECT_MIN_PP(1.5%p) — 원래는 실험 효과의 최소 크기. 여기서는
#       *"이 격차가 평소 흔들림보다 큰가"* 를 가르는 데 빌려 쓴다. 같은 질문이다.
#     · MIN_SAMPLE(100건)  — 칸 분모가 이보다 작으면 후보로 만들지 않는다.
#     · THRESHOLDS         — 갈래 ③ 이 그대로 쓴다.
_TOPIC_MIN_PP = C.EFFECT_MIN_PP        # 빌려 쓴 값. 위 주석 참조


def _annual(n: float) -> float:
    """누적 건수를 연간으로. **기간은 config.PERIOD 에서 온다.**

    ⚠️ `datetime.now()` 를 쓰지 않는다 — 오늘이 언제냐에 따라 값이 달라지면
    같은 데이터로 두 번 돌렸을 때 다른 제안서가 나온다.
    지금 우리 기간은 363일이라 계수가 1.006 이지만, **나누는 코드는 남긴다.**
    """
    a, b = (_date.fromisoformat(x) for x in C.PERIOD)
    days = (b - a).days + 1
    return n * 365.25 / days if days else n


def proposal_topics(t: dict) -> list[dict]:
    """제안서로 쓸 만한 주제 후보를 **가능한 만큼** 뽑는다.

    후보 하나의 모양::

        {"키", "제목", "한줄", "규모_연간건수", "근거축", "구간", "기각사유"}

    규모가 큰 순서로 정렬하고 **기각된 것은 맨 뒤**로 보낸다.
    """
    out: list[dict] = []

    # ── ① 퍼널 구간 — 가장 낮은 전환율 구간과 그다음의 격차 ──────
    f = funnel(t)
    ranked = f.dropna(subset=["step_rate"]).sort_values("step_rate")
    if len(ranked) >= 2:
        lo, nx = ranked.iloc[0], ranked.iloc[1]
        gap = (nx["step_rate"] - lo["step_rate"]) * 100
        drop = float(lo["drop"])
        out.append({
            "키": "구간·" + str(lo["label"]),
            "제목": f'{lo["label"]} 구간에서 가장 많이 빠진다',
            "한줄": (f'{lo["label"]} 구간 통과율이 '
                    f'{lo["step_rate"]*100:.2f}% 로 '
                    f'가장 낮다. 다음으로 낮은 {nx["label"]} '
                    f'({nx["step_rate"]*100:.2f}%) 와 {gap:.2f}%p 차이다.'),
            "규모_연간건수": _annual(drop),
            "근거축": "퍼널 구간",
            "구간": str(lo["label"]),
            "기각사유": None if gap >= 0.5 else
                       f"다음 구간과 {gap:.2f}%p 차이라 한 구간의 문제로 보기 어렵습니다",
        })

    # ── ②·②′ 분해 축 ────────────────────────────────────────────
    # ★ **두 지표로 각각 본다.** 우리 데이터는 통과율로 보면 세 축 전부
    #   0.3%p 미만이라 아무것도 안 갈리고, 같은 축을 납기 준수율로 보면
    #   2~4%p 로 벌어진다. **축이 나쁜 게 아니라 보는 지표가 안 맞았다.**
    #   통과율 쪽도 지우지 않고 기각으로 남긴다 — 안 봤다와 구분되어야 한다.
    bottleneck = str(ranked.iloc[0]["label"]) if len(ranked) else None
    b_from = None
    if bottleneck:
        idx = list(f["label"]).index(bottleneck)
        b_from = str(f.iloc[idx - 1]["step"]) if idx > 0 else None
        bottleneck = str(f.iloc[idx]["step"])

    for dim in C.DIMS:
        # ②′ 주지표(납기 준수율) — 우리가 실제로 쓰는 쪽
        g = metric_by(t, dim)
        g = g[g["분모"] >= C.MIN_SAMPLE]          # 비교 자체가 안 되는 칸은 뺀다
        if len(g) >= 2:
            hi = g["준수율"].max()
            g = g.assign(_격차=(hi - g["준수율"]) * 100)
            g = g.assign(_건수=g["_격차"] / 100 * g["분모"])
            # ★ **가장 낮은 칸이 아니라 크기(격차 × 비중)가 가장 큰 칸**을 뽑는다.
            #   교안은 "최고 칸과 최저 칸의 격차" 라고 했는데, 그러면 비중이 작은
            #   칸이 1위로 올라온다 — 2026-09-09 카드 2번이 정확히 *"격차가 가장
            #   큰 칸부터 손대는 것을 그만둔다"* 였다. 세 축 중 둘에서 최저 칸과
            #   크기 1위 칸이 **다르다**(고객사 D사 105건 ↔ E사 250건).
            big = g.loc[g["_건수"].idxmax()]
            worst = g.loc[g["준수율"].idxmin()]
            gap = float(big["_격차"])
            같은칸 = str(big[dim]) == str(worst[dim])
            out.append({
                "키": f"축·{dim}·납기",
                "제목": f"{dim} {big[dim]} 의 납기 준수율이 가장 많이 벌어져 있다",
                "한줄": (f'{dim} {C.josa(big[dim], "이")} '
                        f'{big["준수율"]*100:.2f}% '
                        f'({int(big["준수"]):,} / {int(big["분모"]):,}) 로 '
                        f'가장 높은 {C.josa(dim, "과")} '
                        f'{gap:.2f}%p 벌어져 있습니다. '
                        f'이 {C.josa(dim, "이")} '
                        f'전체의 {big["비중"]*100:.2f}% 라 '
                        f'가장 많은 건수가 걸려 있습니다.'
                        + ("" if 같은칸 else
                           f' 더 많이 벌어진 {C.josa(dim, "은")} '
                           f'{worst[dim]}({worst["_격차"]:.2f}%p) 지만 '
                           f'비중이 {worst["비중"]*100:.2f}% 라 '
                           f'{int(worst["_건수"]):,}건에 그칩니다.')),
                "규모_연간건수": _annual(float(big["_건수"])),
                "근거축": dim,
                "구간": "납기 준수율",
                "기각사유": None if gap >= _TOPIC_MIN_PP else
                           f"차이 {gap:.2f}%p가 {C.say(chr(0xD754) + chr(0xB4E4) + chr(0xB9BC))}"
                           f"({_TOPIC_MIN_PP}%p)보다 작습니다",
            })

        # ② 통과율 — 교안이 지정한 갈래. 우리는 안 갈리지만 **봤다는 것을 남긴다**
        if bottleneck and b_from:
            fb = funnel_by(t, dim, b_from, bottleneck)
            fb = fb[fb["도달"] >= C.MIN_SAMPLE]
            if len(fb) >= 2:
                fgap = (fb["전환율"].max() - fb["전환율"].min()) * 100
                out.append({
                    "키": f"축·{dim}·통과",
                    "제목": f"{dim} 별 {bottleneck} 통과율 차이",
                    "한줄": (f'{bottleneck} 구간 통과율을 '
                            f'{C.josa(dim, "으로")} 나누면 '
                            f'{fb["전환율"].min()*100:.2f}~{fb["전환율"].max()*100:.2f}% 로 '
                            f'{fgap:.2f}%p 차이다.'),
                    "규모_연간건수": _annual(fgap / 100 * float(fb["도달"].sum())),
                    "근거축": dim,
                    "구간": f"{b_from}→{bottleneck} 통과율",
                    "기각사유": None if fgap >= _TOPIC_MIN_PP else
                               (f"차이 {fgap:.2f}%p — 이 지표로는 갈리지 않습니다. "
                                f"같은 축을 납기 준수율로 보면 벌어집니다"),
                })

    # ── ③ 임계값 — config.THRESHOLDS 를 벗어난 지표 ──────────────
    # ★ 지금은 넷 다 안전 구간이라 후보가 안 나온다. 그래도 **"이탈 없음"을
    #   한 줄로 남긴다** — 조용히 빠지면 안 본 것과 구분되지 않는다.
    k = kpis(t)
    off = []
    for name, spec in C.THRESHOLDS.items():
        if name not in k:
            continue
        v = float(k[name]["value"])
        lvl = status_of(name, v)
        if lvl in ("warn", "block"):
            off.append({
                "키": "임계·" + name,
                "제목": f'{C.josa(name, "이")} 기준을 벗어났다',
                "한줄": (f'{C.josa(name, "이")} {v:.2f}% 로 '
                        f'{"위험" if lvl == "block" else "경고"} 구간이다 '
                        f'(경고 {spec["경고"]} · 위험 {spec["위험"]}).'),
                "규모_연간건수": 0.0,      # 건수 환산은 지표마다 분모가 달라 안 한다
                "근거축": "임계값",
                "구간": name,
                "기각사유": None,
            })
    if off:
        out += off
    else:
        out.append({
            "키": "임계·이탈없음",
            "제목": "기준을 벗어난 지표가 없다",
            "한줄": ("정해 둔 경고·위험선을 벗어난 지표가 "
                    f"{len(C.THRESHOLDS)}개 중 0개다."),
            "규모_연간건수": 0.0,
            "근거축": "임계값",
            "구간": "전체",
            "기각사유": "기준을 벗어난 지표가 없습니다 — 이것도 확인한 결과입니다",
        })

    # ── ④ 추세 — 최근 N개월 평균이 직전 N개월보다 낮은 지표 ──────
    # ⚠️ 안 찬 달은 monthly() 가 값을 안 남긴다(DUE_SETTLE_DAYS).
    #    NaN 을 0 으로 읽으면 **관찰 기간이 모자란 것을 하락으로** 읽는다.
    # ⚠️ **12개월을 요구하지 않는다.** 유효 구간이 분모가 얇은 달을 잘라내 10개월이고,
    #    긴급품·지연은 확정 대기까지 빠져 9개월이다. 12를 고정으로 두면 이 갈래가
    #    **영영 후보를 못 낸다** — 안 나오는 것과 못 나오는 것은 다르다.
    #    있는 만큼을 반으로 가르되, 한쪽이 3개월 미만이면 추세로 안 본다.
    mo = monthly(t)
    for name in mo.columns:
        if name == "분모":
            continue
        s = mo[name].dropna()
        half = len(s) // 2
        if half < 3:
            continue
        recent, prev = s.iloc[-half:].mean(), s.iloc[-half * 2:-half].mean()
        worse = (recent < prev) if name == "납기 준수율" else (recent > prev)
        diff = abs(recent - prev)
        out.append({
            "키": "추세·" + name,
            "제목": f'{C.josa(name, "이")} 최근 {half}개월 나빠졌다',
            "한줄": (f'{C.josa(name, "이")} 직전 {half}개월 {prev:.2f}% 에서 '
                    f'최근 {half}개월 {recent:.2f}% 로 {diff:.2f}%p 움직였다.'),
            "규모_연간건수": 0.0,
            "근거축": "추세",
            "구간": name,
            "기각사유": None if (worse and diff >= _TOPIC_MIN_PP) else
                       (f"{diff:.2f}%p 움직였습니다 — "
                       f"{C.say(chr(0xD754) + chr(0xB4E4) + chr(0xB9BC))}({_TOPIC_MIN_PP}%p) 안입니다"
                        if worse else f"나빠지지 않았습니다 ({diff:.2f}%p 좋아짐)"),
        })

    # ── 정렬: 살아남은 것 먼저, 그 안에서 규모 큰 순 ──────────────
    out.sort(key=lambda c: (c["기각사유"] is not None, -c["규모_연간건수"]))
    return out


def topic_evidence(t: dict, topic: dict) -> dict:
    """주제 하나가 쓸 근거를 **한 번에 모아** 돌려준다.

    돌려주는 모양 — 네 항목. 없으면 값 대신 사유를 남긴다::

        {"현황": {...} | None, "현황_없는사유": str | None,
         "원인": ..., "규모": ..., "추세": ...}

    ★ **이 함수는 조회만 한다. 문장을 만들지 않는다.**
      문장은 `report/proposal.py` 가 만든다 — 조회와 서술이 한 곳에 섞이면
      숫자를 고칠 때마다 문장을 다시 읽어야 한다.

    ★ **실측과 환산값을 같은 항목에 섞지 않는다.** 키를 나눈다 —
      `규모.누적건수`(실측) 와 `규모.연간건수`(환산) 는 다른 키다.
      섞으면 환산이 실측처럼 읽힌다.

    ★ 없는 것은 지어내지 않고 `None` 으로 두되 **왜 없는지 사유를 같이** 넣는다.
    """
    ev: dict = {}
    dim = topic.get("근거축")
    구간 = topic.get("구간")

    # ── 현황 — 퍼널 전체 ────────────────────────────────────────
    f = funnel(t)
    ev["현황"] = f
    ev["현황_없는사유"] = None
    ev["현황_병목"] = (str(f.loc[f["is_bottleneck"], "label"].iloc[0])
                     if f["is_bottleneck"].any() else None)

    # ── 원인 — 그 주제의 분해 축 표 ─────────────────────────────
    # ⚠️ **전환율이 아니라 납기 준수율**이다. 전환율로는 세 축 전부 0.3%p 미만이라
    #    표를 그려도 칸 사이에 차이가 안 보인다 (2026-09-09 실측).
    if dim in C.DIMS:
        g = metric_by(t, dim)
        hi = g["준수율"].max()
        g = g.assign(격차=(hi - g["준수율"]) * 100)
        g = g.assign(건수=g["격차"] / 100 * g["분모"])
        g = g.assign(표본부족=g["분모"] < C.MIN_SAMPLE)
        ev["원인"] = g.sort_values("건수", ascending=False)
        ev["원인_없는사유"] = None
        ev["원인_최고칸"] = str(g.loc[g["준수율"].idxmax()][dim])
        ev["원인_최대칸"] = str(g.loc[g["건수"].idxmax()][dim])
        # ⚠️ 같은 "납기 준수율"인데 **분모가 둘**이다. 나란히 인용하면 다른 두 수를
        #    같은 것처럼 쓰게 되므로 **어느 분모인지 키에 적어 둔다.**
        ev["원인_분모"] = f"완주 코호트 중 납기 도래 {int(g['분모'].sum()):,}건"
        ev["지표_분모"] = kpis(t).get("납기 준수율", {}).get("note")
    else:
        ev["원인"] = None
        ev["원인_없는사유"] = (
            f"이 주제는 분해 축이 아니라 '{dim}' 에서 나왔다. "
            f"축 표로 보여줄 것이 없다")

    # ── 규모 — 실측과 환산을 키로 가른다 ────────────────────────
    a, b = (_date.fromisoformat(x) for x in C.PERIOD)
    days = (b - a).days + 1
    연간 = float(topic.get("규모_연간건수") or 0)
    ev["규모"] = {
        "연간건수": 연간,                                   # 환산값
        "누적건수": 연간 * days / 365.25,                   # 실측 기간 안의 값
        "관측기간_일": days,
    }
    ev["규모_가정"] = [
        f"관측 기간 {C.PERIOD[0]} ~ {C.PERIOD[1]} ({days}일) 의 값을 "
        f"365.25일로 환산했습니다",
        "지금 벌어진 차이가 그대로 유지된다고 보았습니다",
        "가장 나은 쪽까지 따라간다고 보지 않았습니다 — 그 가정에는 근거가 없습니다",
    ]

    # ── 금액 (2026-09-11 Day4) ────────────────────────────────────
    #   판정 지적 — *"297건이 매출로 얼마인가"*. **조회하면 나온다.**
    #   ⚠️ 건당 평균을 쓴다. 어느 건이 그 297건인지는 데이터가 지목하지 못한다
    #     (격차에서 환산한 몫이라 특정 수주가 아니다) — 가정으로 적는다.
    dim = topic.get("근거축", "")
    # ⚠️ 대상 값은 topic["키"](축·차종·납기) 에 없다 — 거기엔 **축 이름**만
    #    있다. 값은 위에서 만든 ev["원인_최대칸"] 이다.
    val = ev.get("원인_최대칸", "")
    if dim and dim in C.DIMS and 연간 > 0:
        try:
            amt = amount_by(t, dim)
            row = amt[amt[dim] == val]
            per = float(row["미준수건당"].iloc[0]) if len(row) else 0.0
        except Exception:
            per = 0.0
        if per > 0:
            ev["규모"]["건당금액"] = per
            ev["규모"]["연간금액"] = 연간 * per
            ev["규모"]["누적금액"] = ev["규모"]["누적건수"] * per

    # ── 긴급 운송비 (2026-09-12 · 기쁨 "데이터가 없으면 만들어줘") ──────
    #   페널티 조항은 계약에 없다(기쁨). 늘어나는 비용은 긴급 운송비뿐이라 그것만 센다.
    #   격차로 환산한 연 N건 × 지연 한 건의 기대 운송비. **매출과 자릿수가 다르다** —
    #   그 사실이 결재에 필요하다(운송비로는 이 제안이 정당화되지 않는다).
    if 연간 > 0:
        uf = urgent_ship_facts(t)
        if uf["긴급건수"] > 0:
            ev["규모"]["긴급운송"] = uf
            ev["규모"]["연간운송비"] = 연간 * uf["지연건당비용"]
            if C.SHOW_ESTIMATE_NOTE:
                ev["규모_가정"].append(
                    "긴급 운송 비율과 1회 비용은 추정값입니다 — 실제 운송 전표로 바꿔야 합니다")

    # ── 조치 비용 · 실행 자원 (2026-09-12 · 리더 조건 "비용 추정치 · 실행 자원") ──
    #   건당 비용과 하루 잔업 여유만 싣는다. 몇 건을 당길지는 카드(효과)가 정하므로
    #   곱은 제안서가 한다 — 여기서 곱하면 카드와 다른 건수로 두 값이 생긴다.
    if 연간 > 0 and val and dim in C.DIMS:
        pc = pull_cost(t, dim, val)
        if pc:
            ev["규모"]["당김"] = pc
            ev["규모_가정"].append(
                f"드는 비용은 {C.PULL_ACTION} 기준으로 {'추정' if C.SHOW_ESTIMATE_NOTE else '계산'}했습니다 — "
                f"조치가 달라지면 바뀝니다 (잔업 단가 시급 {C.HOURLY_WAGE:,.0f}원 × {C.OVERTIME_MULT}"
                + (", 잔업 여유는 추정 배치)" if C.SHOW_ESTIMATE_NOTE else ")"))

    # ── 고객사 클레임 (2026-09-12 · 기쁨 "데이터 항목 합성데이터로 생성") ──
    if 연간 > 0:
        cf_ = claim_facts(t)
        if cf_["지연클레임건수"] > 0:
            ev["규모"]["클레임"] = cf_
            ev["규모"]["연간클레임비"] = 연간 * cf_["지연건당비용"]
            if C.SHOW_ESTIMATE_NOTE:
                ev["규모_가정"].append("클레임 빈도(주 1~2건)와 1건 비용(10~50만원)은 추정값입니다 — 클레임 대장으로 바꿔야 합니다")
            ev["규모_가정"].append(
                "금액은 기한을 못 지킨 건의 건당 평균으로 환산했고, "
                "단가는 재료비에서 역산한 값이라 계약 단가가 아닙니다")

    # ── 색상 내역 (2026-09-12 정정 · 처음엔 고객사였다) ──────────────
    #   판정 지적 — *"어느 고객사 물량인지"* 에 고객사별 건수를 넣었다가 7주차
    #   함정 ④에 걸렸다. 대상 차종 안에서 **고객사와 색상이 완전히 겹쳐**(교차 0건)
    #   고객사 차이 0.60%p 가 색상 차이 1.51%p 로 전부 설명됐다.
    #   기쁨 정정: *"칼라는 차종별이지 고객사별이 아님"* — 차종→색상이 실제 구조.
    #   고객사로 쪼개면 **색을 가리고 "그 고객사가 문제"로 읽힌다.** 색상으로 낸다.
    try:
        f = order_facts(t["orders"], t["order_events"])
        m2 = f[f["완주"] & f["납기도래"]]
        if dim and val and dim in m2.columns:
            m2 = m2[m2[dim] == val]
        g2 = (m2.groupby("색상", observed=True)["납기내출하"]
                .agg(발주="size", 준수="sum"))
        g2 = g2[g2["발주"] > 0]
        g2["미준수"] = g2["발주"] - g2["준수"]
        g2["준수율"] = g2["준수"] / g2["발주"]
        g2 = g2.sort_values("준수율")
        ev["색상내역"] = [(str(k), int(r.미준수), float(r.준수율))
                       for k, r in g2.iterrows()]
    except Exception:
        ev["색상내역"] = []
    if 연간 <= 0:
        ev["규모_없는사유"] = (
            "이 주제는 건수로 환산할 수 있는 격차가 아니다 "
            "(지표 이탈·추세는 분모가 달라 한 수로 합칠 수 없다)")
    else:
        ev["규모_없는사유"] = None

    # ── 추세 — 최근 12개월 ──────────────────────────────────────
    # ⚠️ 확정 대기(DUE_SETTLE_DAYS)와 얇은 달 때문에 **안 찬 달은 값이 없다.**
    #    비어 있는 자리를 0 으로 읽으면 관찰 기간이 모자란 것을 하락으로 읽는다.
    mo = monthly(t)
    col = 구간 if 구간 in mo.columns else "납기 준수율"
    s = mo[col].dropna() if col in mo.columns else None
    if s is not None and len(s) >= 3:
        ev["추세"] = mo[[col]].copy()
        ev["추세_지표"] = col
        ev["추세_없는사유"] = None
        ev["추세_빠진달"] = int(mo[col].isna().sum())
    else:
        ev["추세"] = None
        ev["추세_지표"] = col
        ev["추세_없는사유"] = (
            f"'{col}' 의 월별 값이 3개월 미만이다. "
            f"확정 대기와 분모가 얇은 달을 빼면 남는 달이 모자란다")

    # ── 이 근거 전체에 붙는 한계 ────────────────────────────────
    # ★ 축별 격차는 **생성기에 심은 값**이다. 문서에 반드시 따라가야 하는 사실이라
    #   문장을 만드는 쪽이 빠뜨리지 않게 **키 하나로** 담아 둔다.
    ev["한계"] = [
        "데이터가 전부 합성이다 — 방법은 확인할 수 있으나 판정은 실데이터로만 할 수 있다",
        "축별 격차는 데이터를 만들 때 넣은 값이다. 실제로 같은 격차가 나올지는 확인되지 않았다",
    ]
    return ev
