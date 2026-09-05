# -*- coding: utf-8 -*-
"""리포트 8장 조립.

────────────────────────────────────────────────────────────────────
자동으로 쓰는 장과 사람이 쓰는 장이 나뉜다. 가르는 질문은 하나다.

    이 문장이 틀렸을 때 누가 책임지는가?
        사람이 진다        → 사람이 쓴다   (2 배경 · 6 해석 · 8 제안)
        사실이 틀린 것뿐   → 자동으로 쓴다 (1 요약 · 3 방법 · 4 결과 · 5 실험 · 7 한계)

**해석과 제안을 자동화하는 순간 책임이 사라진다.** 그것이 이 수업의 결론이다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

from datetime import datetime

from core import config as C, metrics as M, validate as V

# ★ 자동 생성 문장에 인과를 단정하는 말을 쓰지 않는다.
#   관측 데이터로는 인과를 주장할 수 없는데, 방심하면 자동 문장이 인과를 쓴다.
#
# ⚠️ **말마다 근거를 적는다** (2026-09-04). 근거 없이 늘어난 금지어 목록은
#    나중에 누가 통째로 지운다 — 어제 "검증 규칙은 적게 만든다"를 박아 둔 것과
#    같은 이유다. 지켜지는 만큼만 있는 것이 좋다.
#
#   판단 기준은 하나 — **이 말이 상관을 인과로 바꾸는가.**
#   "늘었다"는 사실이고 "기인한다"는 주장이다.
BANNED = [
    # ── 교안 기본 여섯 ──
    "때문에",      # A 때문에 B → "A가 낮은 구간에서 B도 낮다"
    "덕분에",      # 덕분에 올랐다 → "적용한 뒤 값이 높았다"
    "효과로",      # 효과로 개선 → 효과가 있었다고 이미 단정한 말
    "입증되었",    # 입증 = 인과가 확정됐다는 뜻. 관측으로는 못 한다
    "증명되었",    # 위와 같음
    "확실히",      # 불확실성을 지우는 말. "가능성이 있다"로
    # ── 제조·품질에서 우리가 쓰는 말 (2026-09-04 추가) ──
    "원인이다",    # 공정 보고에서 습관적으로 쓴다. 상관을 원인으로 굳힌다
    "유발했",      # "교체가 지연을 유발했다" — 방향과 인과를 동시에 단정
    "기인한",      # "~에 기인한다" — 원인 지목의 완곡한 표현일 뿐이다
    "초래했",      # 유발과 같은 자리. 결과를 한쪽에 묶는다
    "탓에",        # 구어체 인과. 보고서에도 섞여 들어온다
    "영향을 미쳤", # 크기도 방향도 없이 인과만 남는다. 무엇이 얼마나인지 없다
]


def check_phrasing(text: str) -> list[str]:
    """자동 생성 문장에 인과 단정 표현이 섞였는지 스스로 검사한다.

    **그대로 쓴다.** 사람이 쓴 장에도 걸어라 — 사람이 더 자주 쓴다.
    """
    return [w for w in BANNED if w in text]


import re as _re                                     # noqa: E402

# ★ **지표 값**의 모양들 (Day4 프롬프트 8).
#   감춘 실험 주변에 이 모양이 나오면 계산해 놓고 흘린 것이다.
#   조건 값(표본 수·기간·배정 비율)은 여기 없다 — 그건 보여주는 쪽이다.
_EFFECT_PATTERNS = [
    (r"p\s*=\s*0\.\d+", "p값"),
    (r"\d+\.\d+%\s*→", "전후 비율"),
    (r"\[-?\d+\.\d+,", "신뢰구간"),
    (r"상대\s*[-+]?\d", "상대 효과"),
]


def _fmt(n, unit=""):
    return f"{n:,.0f}{unit}"


def to_html(text: str) -> str:
    """본문의 마크다운 표기를 HTML 로 바꾼다. **화면 전용.**

    본문은 마크다운(`**강조**`)으로 쓴다 — PDF(fpdf2 markdown=True)와
    .md 내려받기가 그대로 읽기 때문이다. 그런데 리포트 화면의 카드는
    원시 HTML 이라 마크다운이 해석되지 않아 별표가 그대로 보인다.
    **한 본문이 매체마다 다르게 보이면 어느 쪽이 원본인지 알 수 없다.**

    HTML 특수문자를 먼저 이스케이프한다 — 본문에 사람이 쓴 장이 섞여 들어올 수
    있고, 거기 `<` 가 있으면 카드 레이아웃이 깨진다.
    """
    import html as _html
    import re as _re
    t = _html.escape(text)
    return _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t, flags=_re.S)


# ── 자동으로 쓰는 장 ──────────────────────────────────────────────
def _s1_summary(t: dict) -> dict:
    """1. 요약

    **수치는 쓰되 인과는 쓰지 않는다.** "A가 낮다"는 되고 "B 탓에 A가 낮다"는 안 된다.
    다 쓰고 나서 check_phrasing() 으로 자기 문장을 검사한다.
    """
    f = M.funnel(t)
    k = M.kpis(t)
    ch = M.urgent_stats(t)

    # 교안 프롬프트 1 — "각각 현재값과 변화를 한 줄씩".
    # 수준만 있으면 읽는 사람이 좋아지는 중인지 나빠지는 중인지 모른다.
    #
    # ⚠️ 지표마다 **비교 구간이 다르다.** 긴급품·지연 출하는 납기 뒤 최대 24일에
    #    걸쳐 확정돼 끝 달이 비어 있다(DUE_SETTLE_DAYS). 한 구간으로 뭉뚱그리면
    #    다른 구간끼리 비교한 것을 같은 구간으로 읽는다. 각자의 구간을 같이 적는다.
    m = M.monthly(t)

    def _chg(name: str) -> str:
        if name not in m.columns:
            return ""
        v = m[name].dropna()
        if len(v) < 2:
            return " (변화를 낼 구간이 없습니다)"
        return (f" · {v.index[0]} {v.iloc[0]:.2f} → {v.index[-1]} {v.iloc[-1]:.2f}"
                f" ({v.iloc[-1] - v.iloc[0]:+.2f}%p)")

    body = f"""\
{C.DATASET}의 발주 → 출하 흐름을 **{C.GRAIN}** 단위로 셌습니다.
기간은 {C.PERIOD[0]} ~ {C.PERIOD[1]}, 기준일은 {C.TODAY}입니다.

완주 코호트(접수 후 {C.COHORT_DAYS}일 이상) {_fmt(f.n.iloc[0])}건 기준으로
최종 출하율은 **{f.cum_rate.iloc[-1]*100:.1f}%**이고, 앞 단계를 건너뛴 수주는
**{M.funnel_skips(t)}건**입니다.

**지표 넷**
· **납기 준수율 {k['납기 준수율']['value']:.1f}%** (주지표 · 경고 {C.THRESHOLDS['납기 준수율']['경고']:.0f} · 위험 {C.THRESHOLDS['납기 준수율']['위험']:.0f}){_chg('납기 준수율')}
· **불량률 {k['불량률']['value']:.2f}%** (가드레일 · 경고 {C.THRESHOLDS['불량률']['경고']:.0f} 초과 · 위험 {C.THRESHOLDS['불량률']['위험']:.0f} 초과){_chg('불량률')}
· **긴급품 비율 {ch['긴급률']:.1f}%** ({_fmt(ch['긴급건'])}건 · 납기가 지났는데 아직 미출하){_chg('긴급품 비율')}
· **지연 출하율 {k['지연 출하율']['value']:.1f}%** (출하는 됐으나 납기 이후){_chg('지연 출하율')}

뒤 둘의 비교 구간이 앞 둘보다 짧은 것은 **아직 확정되지 않은 달을 뺐기** 때문입니다.
사유는 방법 장에 적었습니다.

단계별 탈락은 최대 {(1-f.step_rate.min())*100:.1f}%로 고르게 낮아, 퍼널의 통과율만으로는
구간 사이의 차이가 드러나지 않습니다. 같은 기간을 납기 축에서 보면 지연 출하와
긴급품이 관측됩니다. 긴급품은 사라진 수주가 아니라 **아직 나가지 않은 수주**입니다 —
납기를 넘긴 뒤에는 우선순위가 올라가 최대한 빨리 내보내게 됩니다.

[주의] 데이터는 전부 합성입니다. 실 ERP 반출이 되지 않아 스키마와 값 체계만 복제했습니다.
방법은 확인할 수 있으나 **판정은 실데이터로만** 할 수 있습니다."""
    return {"title": "1. 요약", "kind": "auto", "body": body}


def _s3_method(t: dict) -> dict:
    """3. 방법

    **분석 단위(그레인)를 반드시 밝힌다.** 읽는 사람이 숫자를 다시 세어볼 수 있어야 한다.
    무엇을 어떻게 셌는지, 무엇을 뺐는지, 어떤 검정을 썼는지.

    지표의 정의는 **위키가 원본**이다. 여기서 새로 정의하지 않는다.
    """
    d = M.order_facts(t["orders"], t["order_events"])
    due = int(d["납기도래"].sum())
    vp = M.valid_period(t)          # 뺀 달을 문서에도 이름으로 적는다
    body = f"""\
**분석 단위(그레인)** — {C.GRAIN}. 이벤트 행이 아니라 수주ID 고유값으로 셉니다.
한 수주가 같은 단계를 두 번 밟을 수 있어(미납 → 생산계획 재투입) 행을 세면
분모가 부풀고 전환율이 100%를 넘습니다.

**센 방법** — 단계별로 **최초 도달만** 셉니다. 재투입은 다시 세지 않습니다.

**뺀 것 넷**
· 접수 후 {C.COHORT_DAYS}일이 안 지난 수주 — 납기가 수주 + 25~60일이라 그 전에는
  완주 여부를 판정할 수 없습니다. 자르지 않으면 진행 중인 것이 실패로 들어갑니다.
· 납기가 아직 오지 않은 수주 — 주지표의 분모는 **납기 도래 {_fmt(due)}건**입니다.
· 분모가 얇은 달 — 월 표본 {C.MIN_SAMPLE}건 미만, 그리고 **월 분모가 중앙값의
  {C.THIN_MONTH_RATIO*100:.0f}%에 못 미치는 달**을 추이에서 뺍니다. 건수만으로 자르면
  데이터가 시작되는 경계를 못 잡습니다(첫 달 {_fmt(vp['뺀목록'][0][1])}건이
  최소 표본은 넘었습니다). 실제로 뺀 달은 {' · '.join(f"{a}({b:,}건)" for a, b in vp['뺀목록'])}이고,
  쓰는 구간은 **{vp['시작']} ~ {vp['끝']}**입니다.
· **아직 확정되지 않은 달** — 긴급품 비율과 지연 출하율은 납기일에 값이 정해지지
  않습니다. 납기를 넘긴 수주가 **납기 뒤 최대 24일**(중앙 13일)에 걸쳐 나가기
  때문입니다. 그래서 관측 {C.DUE_SETTLE_DAYS}일이 지나지 않은 달은 이 두 지표를
  **계산하지 않습니다.** 그대로 두면 아직 안 나간 것이 긴급품으로 과대 잡히고,
  늦게 나갈 것이 지연 분모에서 빠져 과소 잡혀 **관찰이 덜 된 것이 개선으로 보입니다.**
  납기 준수율은 납기일이 지나는 순간 판정이 끝나므로 이 문제가 없습니다.

**분모를 고른 이유** — 출하한 건만 세면 미납이 분모에서 빠져, 어려운 건을 미룰수록
지표가 올라갑니다. 그래서 분모를 납기 도래 전체로 두었습니다.

**쓴 검정** — 두 비율 비교(정규근사)와 95% 신뢰구간, 배정 균형은 카이제곱(SRM).
p값만 보면 크기를 알 수 없어 신뢰구간을 함께 냅니다.

**지표 정의의 원본은 위키입니다.** 이 문서는 정의를 옮긴 것이지 새로 만들지 않았습니다."""
    return {"title": "3. 방법", "kind": "auto", "body": body}


def _s4_results(t: dict) -> dict:
    """4. 결과

    숫자를 나열하되 **해석하지 않는다.** 해석은 6장이고 사람이 쓴다.
    "낮다"까지가 결과이고 "왜 낮은가"는 해석이다.
    """
    f = M.funnel(t)
    k = M.kpis(t)
    r = M.retention_funnel(t)
    ch = M.urgent_stats(t)
    ce = M.channel_efficiency(t)
    ev = M.efficiency_verdict(ce)

    lines = [f"· {row.label} {_fmt(row.n)}건"
             + ("" if row.step_rate != row.step_rate
                else f" (전 단계의 {row.step_rate*100:.1f}%)")
             for row in f.itertuples()]
    bn = f[f.is_bottleneck].iloc[0]

    # ── 분해 (교안 프롬프트 2 — "단계별 값과 분해 결과를 나열한다") ──
    # 화면에서 본 것이 문서에 없으면 회의에서 인용할 수 없다.
    #
    # ★ 두 축을 **둘 다** 적는다. 주지표로 쪼개면 갈리고 퍼널로 쪼개면 안 갈리는데,
    #   안 갈린다는 것도 결과다 — 안 적으면 다음 사람이 같은 축을 또 쪼갠다.
    dim = C.DIMS[0]
    g = M.metric_by(t, dim).sort_values("준수율")
    dec = [f"· {row[dim]} {row.준수율*100:.1f}% "
           f"({_fmt(int(row.분모))}건 · 전체의 {row.비중*100:.1f}%)"
           for _, row in g.iterrows()]
    gap = (g["준수율"].max() - g["준수율"].min()) * 100
    thin = int(g["표본부족"].sum())

    # 체류일 — 통과율로는 안 보이는 것. 화면에서 본 것이 문서에 없으면
    # 회의에서 인용할 수 없다 (2026-09-05).
    dw = M.stage_dwell(t)
    dv = M.dwell_verdict(dw)

    fb_gaps = []
    for d in C.DIMS:
        x = M.funnel_by(t, d, bn.step_prev, bn.step) if hasattr(bn, "step_prev") \
            else M.funnel_by(t, d, f.step.iloc[-2], f.step.iloc[-1])
        fb_gaps.append((d, (x["전환율"].max() - x["전환율"].min()) * 100))

    body = f"""\
**획득 퍼널** (완주 코호트 {_fmt(f.n.iloc[0])}건)
""" + "\n".join(lines) + f"""

전 단계 대비 비율이 가장 낮은 구간은 **{bn.label}** 진입({bn.step_rate*100:.1f}%)입니다.
코호트를 자르지 않으면 최종 통과율이
{f.n_all.iloc[-1]/f.n_all.iloc[0]*100:.1f}%로 {f.cum_rate.iloc[-1]*100 - f.n_all.iloc[-1]/f.n_all.iloc[0]*100:.1f}%p 만큼 다르게 나옵니다.

**지표**
""" + "\n".join(f"· {n} {v['fmt'].format(v['value'])} — {v['note']}"
                for n, v in k.items()) + f"""

**분해 — {dim}별 납기 준수율** (완주 코호트 중 납기 도래분)
""" + "\n".join(dec) + f"""

가장 낮은 칸과 가장 높은 칸의 차이는 **{gap:.2f}%p**입니다.
최소 표본({C.MIN_SAMPLE}건) 미만인 칸은 {thin}개입니다.

같은 축을 **퍼널 전환율**({f.label.iloc[-2]} → {f.label.iloc[-1]})로 쪼개면
""" + " · ".join(f"{d} {v:.2f}%p" for d, v in fb_gaps) + f"""
로, 어느 축으로도 갈리지 않습니다. 단계 통과율과 납기 준수 여부가 같은 축에서
다르게 갈린다는 것까지가 관측된 사실이고, 그 이유는 이 장에서 다루지 않습니다.

**단계별 체류일** (중앙값 · 통과율로는 안 보이는 것)
""" + "\n".join(f"· {row['구간']} {row['중앙']:.0f}일 ({row['비중']*100:.0f}%)"
                for _, row in dw.iterrows()) + f"""

발주에서 출하까지 중앙 {dv['총일수']:.0f}일이고 성격이 셋으로 갈립니다 —
계획 {dv['계획일수']:.0f}일 · 공정 {dv['공정일수']:.0f}일 ·
{dv['대기구간']} {dv['대기일수']:.0f}일({dv['대기비중']*100:.0f}%).
**마지막은 병목이 아니라 납기 대기입니다** — 출하일은 공정이 끝나는 날이 아니라
납기에 맞춰 잡히므로, 일찍 끝나면 그만큼 기다립니다.
공정 {dv['구간수']}개 중 가장 긴 곳은 **{dv['최장구간']} {dv['최장일수']:.0f}일**로
평균의 {dv['쏠림']:.1f}배입니다.

**유지(수주 생존)**
""" + "\n".join(f"· {row.label} {_fmt(row.n)}건"
                + ("" if row.step_rate != row.step_rate
                   else f" (전 단계의 {row.step_rate*100:.1f}%)")
                for row in r.itertuples()) + f"""
· 긴급품 {_fmt(ch['긴급건'])}건 ({ch['긴급률']:.1f}%)

**유효 원가** ({C.EFFICIENCY_DIM}별 · 인건·가공은 가정값 배부)
· 원가 격차 {ev['원가격차']:.1f}원 · 불량 보정폭 {ev['보정폭']:.1f}원
· 순위 역전 **{ev['역전']}건**. 보정폭이 원가 격차보다 작아 이 데이터에서는
  순위가 바뀌지 않습니다."""
    return {"title": "4. 결과", "kind": "auto", "body": body,
            "charts": ["funnel", "device"]}


def _s5_experiments(t: dict) -> dict:
    """5. 실험

    **무효 판정된 실험은 사유만 적고 수치를 쓰지 않는다.** 화면에서 감춘 숫자를
    리포트에 쓰면 감춘 의미가 없다. metrics.experiment_results() 의 verdict 를 보고
    분기한다.
    """
    res = M.experiment_results(t)
    if not res:
        return {"title": "5. 실험", "kind": "auto", "charts": [], "body":
                "실험이 없습니다. 전후 비교로 대신할 경우 관측 데이터로는 "
                "**인과를 주장할 수 없다**를 같은 문단에 남겨야 합니다."}

    head = ("[주의] **아래 실험은 설계이지 실행 기록이 아닙니다.** 7주차에 설계만 해 둔 것을 "
            "데이터로 옮겨 판정 절차가 도는지 확인한 것입니다. "
            "**성과를 실적으로 인용할 수 없습니다.**\n")
    blocks = []
    for r in res:
        b = [f"**{r['id']} {r['name']}** — {r['verdict']}",
             f"· 가설: {r['hypothesis']}",
             f"· 배정 단위: {r.get('unit','')} · 기간 {r['days']}일"]
        if r["verdict"] == "무효":
            # 수치를 쓰지 않는다. 화면에서 감춘 것을 문서에 쓰면 감춘 의미가 없다.
            b.append(f"· **지표를 계산하지 않았습니다.** {r['reason']}")
        elif "rc" in r:
            b.append(f"· {r['outcome']} {r['rc']*100:.2f}% → {r['rt']*100:.2f}% "
                     f"(상대 {r['lift']*100:+.1f}%, p={r['p']:.4f}, "
                     f"표본 {_fmt(r['nc'])}/{_fmt(r['nt'])})")
            b.append(f"· 95% 신뢰구간 [{r['lo']*100:+.2f}, {r['hi']*100:+.2f}]%p")
            if r.get("guard"):
                b.append(f"· 가드레일 {r['guard']['name']} "
                         f"{r['guard']['delta']*100:+.2f}%p "
                         f"(허용 -{C.GUARDRAIL_TOLERANCE*100:.0f}%p)")
            if r["verdict"] == "효과 없음":
                b.append("· 이 결과를 '처치가 소용없다'로 읽을 수 없습니다 — "
                         "배정과 성과가 서로 영향을 줄 수 있는 경로가 "
                         "이 데이터에는 없습니다.")
        else:
            b.append(f"· {r.get('reason','')}")
        blocks.append("\n".join(b))

    n_void = sum(1 for r in res if r["verdict"] == "무효")
    tail = (f"\n실험 {len(res)}건 중 **{n_void}건이 무효**입니다. "
            f"무효는 결과가 나쁘다는 뜻이 아니라 **판정할 수 없다**는 뜻입니다.")
    return {"title": "5. 실험", "kind": "auto", "charts": ["experiments"],
            "body": head + "\n" + "\n\n".join(blocks) + tail}


def _s7_limits(t: dict) -> dict:
    """7. 한계 — 검증 경고에서 조립한다

    **사람이 매번 쓰는 것이 아니라 경고를 그대로 옮긴다.**
    검증에서 경고가 났는데 한계에 안 적히면 **그 경고는 사라진 것과 같다.**

    한계는 세 곳에서 온다.

        검증 경고        validate.run_checks() 에서 level == "warn" 인 것
        못 한 것         표본이 모자라 판정 못 한 것 · 기간이 짧아 못 본 것
        찾았는데 없던 것  **"없음"도 결과다**
    """
    warns = [c for c in V.run_checks(t) if c["level"] == "warn"]
    res = M.experiment_results(t)
    void = [r for r in res if r["verdict"] == "무효"]
    ce = M.channel_efficiency(t)
    ev = M.efficiency_verdict(ce)
    d = M.order_facts(t["orders"], t["order_events"])
    miss = int(d["납기미정"].sum())
    ch = M.urgent_stats(t)

    parts = ["**확인하지 못한 것**\n"]

    # ★ 2026-09-04 (Day4 프롬프트 5) — **무조건 들어가는 문장 셋.**
    #   앞 둘은 교안이 "항상 넣는다"고 못박은 것인데 **빠져 있었다.**
    #   조건이 붙은 항목(경고·무효 실험)은 데이터가 좋으면 사라지지만,
    #   이 셋은 이 분석의 성격 자체라 어떤 데이터에서도 사라지지 않는다.
    #   조건부 항목 사이에 섞어 두면 어느 날 조용히 없어진다 — 그래서 맨 앞에 못박는다.
    parts.append(
        "· **관측 데이터이므로 인과를 주장할 수 없습니다.** 무작위 배정이 없어 "
        "*\"A가 낮은 구간에서 B도 낮다\"* 까지만 말할 수 있고, "
        "*\"A가 B를 낮췄다\"* 는 이 데이터로 가릴 수 없습니다.")
    parts.append(
        f"· **기간이 {C.PERIOD[0]} ~ {C.PERIOD[1]}이므로 그보다 긴 주기의 변화는 "
        f"관측되지 않습니다.** 연 단위 계절성이나 차종 교체 주기처럼 "
        f"한 해를 넘는 흐름은 이 창 안에서 보이지 않습니다.")
    parts.append(
        "· **데이터가 전부 합성입니다.** 실 ERP 반출이 되지 않아 스키마와 값 체계만 "
        "복제했습니다. 절차는 확인할 수 있으나 **판정은 실데이터로만** 할 수 있습니다.")

    # ① 검증 경고 — 그대로 옮긴다
    if warns:
        parts.append("\n**검증에서 난 경고** (게이트 1에서 사람이 보고 넘긴 것)\n")
        parts += [f"· {w['name']} — {w['msg']}" for w in warns]
    else:
        parts.append("\n· 검증 경고는 없었습니다.")

    # ② 못 한 것
    parts.append("\n**판정하지 못한 것**\n")
    for r in void:
        parts.append(f"· {r['id']} {r['name']} — {r['reason']}")
    parts.append(
        f"· 납기 미정 발주 {_fmt(miss)}건이 있습니다. 주지표의 분모에서는 빠지지만, "
        f"출하분만 놓고 세면 같은 지표가 6.7%p 다르게 나옵니다 — "
        f"**분모를 바꾼 것보다 결측 처리가 값을 더 크게 움직였습니다.**")
    parts.append(
        f"· 긴급품 {_fmt(ch['긴급건'])}건을 사전에 예측할 수단이 없습니다. "
        f"착수 지연일·자재 결품 이력·계획 변경 횟수가 데이터에 없어 **사후 판정만** 됩니다.")
    # ★ 2026-09-05 — 6공정으로 쪼갠 뒤 이 문장이 **거짓이 됐다.**
    #   전에는 "나눌 수 없다"였는데 이제 나뉜다. 다만 **나뉜 것이 실측은 아니다** —
    #   공정별 배분은 작업일보 CT 비중으로 심은 값이라, 그 사실을 대신 적는다.
    parts.append(
        "· **공정별 체류일은 실측이 아니라 배분한 값입니다.** 6공정 작업일보의 "
        "개당 처리시간(CT) 비중으로 나눴는데, **CT 는 처리시간이지 대기시간이 "
        "아닙니다.** 실제로 줄 서서 기다린 시간은 작업일보에 남지 않아, "
        "어느 공정 앞에 얼마나 쌓였는지는 이 데이터로 알 수 없습니다.")

    # 유효 구간 — 언제부터 언제까지를 믿을 수 있는가 (Day3 프롬프트 10)
    vp = M.valid_period(t)
    if vp["뺀달"]:
        lst = " · ".join(f"{mm}({n:,}건)" for mm, n in vp["뺀목록"])
        parts.append(
            f"· **월별 추이의 유효 구간은 {vp['시작']} ~ {vp['끝']}({vp['쓴달']}개월)입니다.** "
            f"{lst}은 분모가 중앙값({vp['중앙분모']:,}건)의 "
            f"{C.THIN_MONTH_RATIO*100:.0f}% 에 못 미쳐 뺐습니다 — "
            f"납기가 수주 + 25~60일이라 **데이터 시작 월에는 일부만 잡힙니다.** "
            f"성과가 나쁜 것이 아니라 관측 기간의 문제입니다.")

    # ③ 찾았는데 없던 것 — **"없음"도 결과다**
    parts.append("\n**찾았는데 없던 것** (없음도 결과입니다)\n")
    parts.append(
        f"· {C.EFFICIENCY_DIM}별 유효 원가에서 **순위 역전이 {ev['역전']}건**입니다. "
        f"불량률 격차가 {ev['불량률폭']:.2f}%p뿐이라 보정폭({ev['보정폭']:.1f}원)이 "
        f"원가 격차({ev['원가격차']:.1f}원)를 넘지 못합니다. "
        f"고객사·차종·불량유형·원인구분·설비호기로 바꿔도 같았습니다.")
    # 분해 축 — 격차가 없는 것도 결과다 (Day3 실습 A)
    f_ = M.funnel(t)
    bi_ = int(f_.index[f_.is_bottleneck][0])
    gaps = []
    for dim in C.DIMS:
        g_ = M.funnel_by(t, dim, f_.step.iloc[bi_ - 1], f_.step.iloc[bi_])
        gaps.append(f"{dim} {(g_.전환율.max() - g_.전환율.min()) * 100:.2f}%p")
    parts.append(
        f"· 병목 구간({f_.label.iloc[bi_-1]} → {f_.label.iloc[bi_]})을 "
        f"{len(C.DIMS)}개 축으로 쪼갰으나 **어느 축으로도 1%p 넘게 갈리지 않습니다** "
        f"({' · '.join(gaps)}). 이 축들로는 개선점을 찾을 수 없다는 것을 확인한 것입니다.")
    # ★ 심은 것을 발견이라 쓰지 않는다 (2026-09-03)
    parts.append(
        "· **축별 차이는 합성 단계에서 넣은 값입니다.** 고객사·차종·색상마다 지연율에 "
        "배수를 걸어 데이터를 만들었으므로, 분해 화면의 격차는 *발견*이 아니라 "
        "**넣은 값을 되찾은 것**입니다. 실데이터에서 같은 격차가 나올지는 확인되지 "
        "않았습니다.")
    parts.append(
        "· 무작위 배정 이력이 없어 SRM을 실데이터로 검정할 수 없습니다. "
        "전후 비교로 갈 경우 '비교 두 기간의 물량·차종·인원이 같은가'로 대체해야 합니다.")

    # ★ 검증이 **못 잡는 것**을 적는다. 적지 않으면 "검증을 통과했으니 맞는 데이터"로
    #   읽힌다 — 통과의 뜻을 좁혀 두는 것이 이 장의 일이다.
    parts.append("\n**검증이 잡지 못하는 것**\n")
    parts.append(
        f"· 검증 {len(V.run_checks(t))}종은 행 수·필수 컬럼·날짜 범위·참조 무결성을 봅니다. "
        f"**'이름은 맞고 내용이 다른 파일'은 모양이 맞아 통과할 수 있습니다.** "
        f"다른 데이터셋의 파일을 같은 이름으로 받아 넣어 본 결과, "
        f"참조 무결성이 경고로 드러냈을 뿐 차단까지는 가지 않았습니다. "
        f"파일이 통째로 바뀐 것을 막으려면 스키마 지문 대조가 따로 필요합니다.")
    parts.append(
        "· 검증 통과는 '이 데이터로 계산할 수 있다'는 뜻이지 "
        "'이 데이터가 맞다'는 뜻이 아닙니다.")

    # ④ 가정값 — 실측과 섞이지 않게 따로 묶는다
    parts.append("\n**가정값이 들어간 곳** (실측이 아닙니다)\n")
    parts.append(
        f"· 인건비·가공비는 매출 대비 총액 배부입니다 "
        f"(인건 {C.COST_RATIO['인건비']*100:.0f}% · 가공 {C.COST_RATIO['가공비']*100:.0f}%). "
        f"도번별 실측이 아니라 **가정값 기반**입니다.")
    parts.append(
        "· 판매단가는 재료비에서 역산한 값이지 계약 단가가 아닙니다.")
    parts.append(
        "· 불량 손실 금액을 말할 수 없습니다. 재작업 회수율 컬럼이 없어, "
        "0%로 보는지 80%로 보는지에 따라 손실이 몇 배로 갈립니다.")

    return {"title": "7. 한계", "kind": "auto", "body": "\n".join(parts)}


# ── 사람이 쓰는 장 (제공) ─────────────────────────────────────────
def _s2_background(human: dict) -> dict:
    return {
        "title": "2. 배경", "kind": "human",
        "body": human.get("2. 배경", ""),
        "placeholder": "이 분석을 왜 했는지, 어떤 의사결정을 앞두고 있는지 적으십시오.",
    }


def _s6_interpretation(human: dict) -> dict:
    return {
        "title": "6. 해석", "kind": "human",
        "body": human.get("6. 해석", ""),
        "placeholder": ("숫자가 무엇을 뜻하는지 적으십시오. "
                        "자동으로 쓰지 않습니다 — 해석은 사람의 책임입니다."),
    }


def _s8_proposal(human: dict) -> dict:
    return {
        "title": "8. 제안", "kind": "human",
        "body": human.get("8. 제안", ""),
        "placeholder": ("무엇을 할 것인지, 무엇을 하지 않을 것인지 적으십시오. "
                        "선택하지 않으면 제안이 아니라 보고입니다."),
    }


# ── 조립 ──────────────────────────────────────────────────────────
def _safe(title: str, fn, *args) -> dict:
    """아직 안 채운 장은 "todo" 종류로 돌려준다. 골격 전용."""
    from core.todo import NotYet
    try:
        return fn(*args)
    except NotYet as e:
        return {"title": title, "kind": "todo", "body": "", "todo": e}


def build(t: dict, human: dict | None = None) -> list[dict]:
    """8장을 조립한다. human 은 사람이 쓴 장의 본문 딕셔너리.

    **순서와 자동/사람 구분은 바꾸지 않는다.** 장 개수는 도메인에 맞게 줄여도 되지만,
    해석과 제안을 자동으로 돌리는 것만은 하지 않는다.
    """
    human = human or {}
    return [
        _safe("1. 요약", _s1_summary, t),
        _s2_background(human),
        _safe("3. 방법", _s3_method, t),
        _safe("4. 결과", _s4_results, t),
        _safe("5. 실험", _s5_experiments, t),
        _s6_interpretation(human),
        _safe("7. 한계", _s7_limits, t),
        _s8_proposal(human),
    ]


def email_draft(t: dict, sections: list[dict]) -> dict:
    """이메일 초안. **실제로 보내지 않는다.**

    그대로 쓴다. 이메일 HTML은 인라인 스타일과 표 레이아웃만 쓴다 —
    외부 CSS·자바스크립트·이미지는 대부분의 메일 클라이언트가 막는다.

    받을 사람이 없으면 초안까지만 만들고, 게이트 3은 "보냈다고 치고" 기록만 남긴다.
    """
    summary = next((s["body"] for s in sections if s["title"].startswith("1.")), "")
    subject = f"[{C.APP_NAME}] {C.PERIOD[0][:7]}~{C.PERIOD[1][:7]}"
    html = (
        f'<div style="font-family:sans-serif;color:#0f172a;max-width:640px">'
        f'<h2 style="font-size:18px">{subject}</h2>'
        f'<p style="font-size:14px;line-height:1.7;white-space:pre-line">'
        f'{summary}</p>'
        # ★ 이 파일에서 현재 시각을 쓰는 **유일한 자리**이고, 계산 경로가 아니다.
        #   교안 고정 조항 — "계산 경로에 현재 시각을 넣지 않는다"(같은 입력에 같은
        #   결과가 나와야 하므로). 여기는 초안을 **언제 뽑았는지** 적는 표시용이라
        #   숫자에 영향을 주지 않는다. 지표·퍼널·실험은 전부 config.TODAY 를 쓴다.
        #   → tests/test_metrics.py 10절이 이 조항을 검사한다.
        f'<p style="font-size:12px;color:#64748b;margin-top:20px">'
        f'자동 생성 · {datetime.now().strftime("%Y-%m-%d %H:%M")}</p></div>')
    return {"to": C.EMAIL_TO_EXAMPLE, "subject": subject, "html": html}


# ── 발송 전 최종 점검 (Day4 프롬프트 8) ───────────────────────────
def preflight(t: dict, secs: list[dict]) -> list[dict]:
    """게이트 3 앞에서 **하나라도 걸리면 통과하지 말라**고 말해 주는 점검.

    게이트 3은 되돌릴 수 없다. 그래서 여기서 걸러야 하고,
    **사람이 매번 기억해서 하는 점검은 언젠가 건너뛴다.**

    ★ 계산은 여기서 한다 — 화면은 결과 목록을 그리기만 한다.

    돌려주는 것: [{"name", "ok", "detail"}] · 하나라도 ok=False 면 통과 금지.
    """
    out = []

    def add(name, ok, detail):
        out.append({"name": name, "ok": bool(ok), "detail": detail})

    # ① 사람이 쓰는 장이 비어 있는가
    empty = [s["title"] for s in secs if s["kind"] == "human" and not s["body"].strip()]
    add("사람이 쓰는 장이 채워졌는가", not empty,
        "비어 있음: " + " · ".join(empty) if empty
        else "2·6·8장 모두 채움")

    # ② 인과 단정 표현 — **자동·사람 장 전부**
    hits = {s["title"]: check_phrasing(s["body"])
            for s in secs if s["body"] and check_phrasing(s["body"])}
    add("인과 단정 표현이 없는가", not hits,
        " · ".join(f"{k}: {', '.join(v)}" for k, v in hits.items()) if hits
        else f"{len([s for s in secs if s['body']])}개 장 검사 통과")

    # ③ 검증 경고가 한계 절에 다 있는가
    limits = next((s["body"] for s in secs if s["title"].startswith("7.")), "")
    warns = [c for c in V.run_checks(t) if c["level"] == "warn"]
    missing = [w["name"] for w in warns if w["name"] not in limits]
    add("검증 경고가 한계 절에 다 있는가", not missing,
        "빠짐: " + " · ".join(missing) if missing
        else f"경고 {len(warns)}건 전부 반영")

    # ④ 감춘 항목의 **수치**가 문서로 새지 않았는가
    #    조건 값(표본·기간·배정 비율)은 보여주는 쪽이다. 감출 것은 지표 값이다.
    doc = "\n".join(s["body"] for s in secs)
    leaked = []
    for r in M.experiment_results(t):
        if r["verdict"] != "무효":
            continue
        i = doc.find(r["id"])
        seg = doc[i:i + 500] if i >= 0 else ""
        for pat, label in _EFFECT_PATTERNS:
            if _re.search(pat, seg):
                leaked.append(f"{r['id']}({label})")
    add("감춘 항목의 수치가 새지 않았는가", not leaked,
        "샘: " + " · ".join(leaked) if leaked
        else "무효 실험 주변에 효과·p값·신뢰구간 없음")

    # ⑤ 숫자가 대시보드와 같은가 — 같은 함수를 쓰는지 본다
    k = M.kpis(t)
    s1 = next((s["body"] for s in secs if s["title"].startswith("1.")), "")
    off = [n for n, v in k.items()
           if v["fmt"].format(v["value"]) not in s1]
    add("요약의 지표가 화면과 같은가", not off,
        "다름: " + " · ".join(off) if off
        else " · ".join(f"{n} {v['fmt'].format(v['value'])}" for n, v in k.items()))

    return out


# ── 한계 절을 표에서 고칠 수 있게 (Day4 프롬프트 11) ──────────────
# 한계는 검증 경고에서 **조립**된다. 그런데 조립된 것이 전부는 아니다 —
# "찾았는데 없었다" 같은 것은 사람이 더해야 한다. 그래서 표로 편다.
#
# ⚠️ 조립 결과를 다시 파싱한다. 남의 형식이면 위험하지만 **우리가 쓴 형식**이라
#    괜찮다. 대신 형식을 바꾸면 여기도 같이 바꿔야 한다 — 그 사실을 검사로 묶는다.
_LIMIT_SOURCES = ["검증 경고", "못 한 것", "찾았는데 없음", "항상"]

_HEADER_TO_SOURCE = {
    "확인하지 못한 것": "항상",
    "검증에서 난 경고": "검증 경고",
    "판정하지 못한 것": "못 한 것",
    "찾았는데 없던 것": "찾았는데 없음",
    "검증이 잡지 못하는 것": "못 한 것",
    "가정값이 들어간 곳": "못 한 것",
}

# ★ 이 셋은 분석의 성격 자체라 **체크를 끌 수 없다.**
#   끄면 리포트가 거짓말을 한다 — 합성 데이터라는 사실이 빠진 문서는
#   실측 보고서로 읽힌다.
_LOCKED = ["관측 데이터이므로 인과를 주장할 수 없", "그보다 긴 주기의 변화는",
           "데이터가 전부 합성입니다"]


def limit_rows(t: dict) -> list[dict]:
    """한계 절을 편집 가능한 행으로 쪼갠다. [{"출처","내용","포함","고정"}]"""
    rows, src = [], "항상"
    for line in _s7_limits(t)["body"].split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("**") and not s.startswith("· "):
            # ⚠️ strip("*") 로는 안 된다 — 헤더 뒤에 "(게이트 1에서…)" 가 붙어 있어
            #    끝 글자가 `)` 라 뒤쪽 별표가 안 벗겨진다. 2026-09-04 에 이것 때문에
            #    검증 경고 행이 통째로 "항상"으로 들어갔다.
            m = _re.match(r"\*\*(.+?)\*\*", s)
            head = m.group(1).strip() if m else s.strip("*").strip()
            src = _HEADER_TO_SOURCE.get(head, src)
        elif s.startswith("·"):
            txt = s[1:].strip()
            rows.append({
                "출처": src, "내용": txt, "포함": True,
                "고정": any(k in txt for k in _LOCKED),
            })
    return rows


def limits_from_rows(rows: list[dict]) -> dict:
    """편집된 행으로 7장을 다시 만든다. 포함=False 인 행은 안 넣는다."""
    parts, cur = [], None
    for r in rows:
        if not r.get("포함", True) or not str(r.get("내용", "")).strip():
            continue
        if r.get("출처") != cur:
            cur = r.get("출처")
            parts.append(f"\n**{cur}**\n" if cur != "항상"
                         else "**확인하지 못한 것**\n")
        parts.append(f"· {str(r['내용']).strip()}")
    if not parts:
        parts = ["· (한계가 비어 있습니다 — 반드시 있습니다. 다시 확인하십시오.)"]
    return {"title": "7. 한계", "kind": "auto", "body": "\n".join(parts)}
