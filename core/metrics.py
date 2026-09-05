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
    그레인은 **발주 1건(수주ID)**. 한 수주가 같은 단계를 두 번 밟을 수 있으므로
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
        그레인이 무엇인가?                    → 수주 1건. 획득 퍼널과 같다
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
