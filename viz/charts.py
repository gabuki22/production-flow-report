# -*- coding: utf-8 -*-
"""화면용 차트 (Plotly).

PDF용 차트는 viz/pdf_charts.py 에 matplotlib으로 따로 있다.
Plotly를 이미지로 내보내려면 kaleido가 필요한데 환경을 심하게 탄다.
**화면은 Plotly, 인쇄는 matplotlib** — 이 분리를 지킨다.
"""
from __future__ import annotations

import plotly.graph_objects as go

from core import config as C

FONT = "Pretendard, -apple-system, 'Malgun Gothic', sans-serif"


def _base(fig, height=360, margin=None):
    fig.update_layout(
        height=height,
        margin=margin or dict(l=8, r=8, t=8, b=8),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family=FONT, size=13, color=C.BRAND["ink"]),
        hoverlabel=dict(font_family=FONT, font_size=13),
        showlegend=False,
    )
    return fig


def funnel_bars(f):
    """퍼널. 단계별 폭이 도달 수에 비례하고 병목 구간을 색으로 표시한다.

    단위는 config.UNIT 을 따른다 — 골격은 "명"이 박혀 있었는데 우리는 수주를 센다.
    """
    top = f.n.iloc[0]
    colors = [C.COLORS["block"] if b else C.BRAND["primary"]
              for b in f.is_bottleneck]
    # ★ 2026-09-05 — 라벨을 줄였다. "79,589건 · 전 단계의 99.5%" 는
    #   막대 밖으로 나가 오른쪽 끝에서 **잘렸다**(화면에서 "99.5" 까지만 보였다).
    #   단계가 6 → 11 로 늘고 컬럼이 반으로 좁아지면서 드러난 것이다.
    #   "전 단계의" 는 퍼널 그림에서 자명하므로 괄호 하나로 충분하다.
    text = []
    for _, r in f.iterrows():
        if r.step_rate == r.step_rate:
            text.append(f"{r.n:,}{C.UNIT} ({r.step_rate*100:.1f}%)")
        else:
            text.append(f"{r.n:,}{C.UNIT}")
    fig = go.Figure(go.Bar(
        x=f.n, y=f.label, orientation="h",
        marker=dict(color=colors, line=dict(width=0)),
        text=text, textposition="outside",
        textfont=dict(size=12, color=C.BRAND["muted"]),
        hovertemplate="%{y}<br>%{x:,}" + C.UNIT + "<extra></extra>",
    ))
    fig.update_yaxes(autorange="reversed", showgrid=False,
                     tickfont=dict(size=13))
    fig.update_xaxes(visible=False, range=[0, top * 1.30])
    # ★ 2026-09-05 — 높이를 **단계 수에 비례**하게 바꿨다.
    #   300 으로 박혀 있었는데 퍼널이 6단계 → 11단계가 되면서 막대당 높이가
    #   절반(27px)이 됐다. 옆의 체류 차트는 막대당 46px 이라 **같은 단계인데
    #   두 그림의 줄 간격이 달라** 눈으로 짝을 못 맞춘다.
    #   46 은 dwell_bars 와 같은 값이다 — 나란히 놓고 읽으라고 만든 짝이므로
    #   **한쪽을 고치면 다른 쪽도 같이 봐야 한다.**
    return _base(fig, height=46 * len(f) + 40, margin=dict(l=8, r=8, t=4, b=4))


def device_compare(g, rate="전환율", denom="도달", hit="전환"):
    """축별 비율 비교. 격차가 보이는 것이 목적이다.

    함수 이름은 골격 그대로다(원본은 기기별이었다). 축은 첫 열을 그대로 쓰므로
    config.DIMS 를 바꿔도 이 함수는 안 고쳐도 된다.

    ★ 2026-09-04 — 열 이름을 인자로 받게 했다. 전에는 `전환율/도달/전환` 이 박혀
      있어서 **퍼널 전환율로만** 쪼갤 수 있었다. 우리 격차는 전환율에 0.6%p 밖에
      안 나타나고 납기 준수율에 4.24%p 로 나타나므로, 같은 그림을 주지표로도
      그릴 수 있어야 한다. 기본값은 퍼널이라 기존 호출부는 그대로 돈다.
    """
    # ★ 2026-09-05 — **막대에서 점으로 바꿨다.**
    #   값이 87.4~91.6% 라 0 부터 막대를 그리면 길이 비가 95.4% —
    #   우리가 찾아낸 **4.2%p 격차가 눈으로 구분되지 않는다.** 그 차이를 보라고
    #   만든 그림인데 그림이 그 일을 안 하고 있었다.
    #
    #   ⚠️ 막대의 축을 잘라서 차이를 키우는 것은 정직하지 않다 —
    #      막대는 **길이**로 값을 말하므로 0 에서 시작해야 한다.
    #      점은 **위치**로 말하므로 축을 좁혀도 왜곡이 아니다.
    #      대신 축 눈금을 **보이게** 둔다. 안 보이면 얼마나 좁힌 건지 알 수 없다.
    g = g.sort_values(rate)
    lowest = g[rate].min()
    colors = [C.COLORS["block"] if v == lowest else C.BRAND["primary"]
              for v in g[rate]]
    lo, hi = g[rate].min() * 100, g[rate].max() * 100
    pad = max((hi - lo) * 0.45, 0.4)

    fig = go.Figure()
    # 가장 낮은 값에서 각 점까지 선을 그어 **격차 자체**를 보이게 한다
    for y, v in zip(g[g.columns[0]], g[rate]):
        fig.add_shape(type="line", x0=lo, x1=v * 100, y0=y, y1=y,
                      line=dict(color=C.BRAND["line"], width=2))
    fig.add_trace(go.Scatter(
        x=g[rate] * 100, y=g[g.columns[0]], mode="markers+text",
        marker=dict(color=colors, size=13,
                    line=dict(color="#ffffff", width=2)),
        text=[f"  {v*100:.1f}%  ({n:,}{C.UNIT} 중 {c:,}{C.UNIT})"
              for v, n, c in zip(g[rate], g[denom], g[hit])],
        textposition="middle right",
        textfont=dict(size=12, color=C.BRAND["muted"]),
        hovertemplate="%{y}<br>%{x:.2f}%<extra></extra>",
    ))
    fig.update_yaxes(showgrid=False, tickfont=dict(size=13))
    # ★ 축을 보인다 — 좁힌 구간을 숨기면 4.2%p 가 40%p 처럼 읽힌다
    fig.update_xaxes(visible=True, showgrid=True, gridcolor=C.BRAND["line"],
                     tickfont=dict(size=11, color=C.BRAND["muted"]),
                     ticksuffix="%", range=[lo - pad, hi + pad * 3.6])
    return _base(fig, height=52 * len(g) + 56,
                 margin=dict(l=8, r=8, t=4, b=26))


def forest(res):
    """실험 효과의 신뢰구간. 0을 지나면 유의하지 않다는 뜻이다.

    p값 하나만 보면 '얼마나' 좋아졌는지 모른다. 구간을 그려야 크기가 보인다.
    """
    lo, hi, d = res["lo"] * 100, res["hi"] * 100, res["diff"] * 100
    color = C.COLORS[res["color"]] if res["color"] in C.COLORS else C.BRAND["primary"]
    span = max(abs(lo), abs(hi)) * 1.5 or 1
    fig = go.Figure()
    fig.add_vline(x=0, line=dict(color=C.BRAND["line"], width=1.5))
    fig.add_trace(go.Scatter(
        x=[lo, hi], y=[0, 0], mode="lines",
        line=dict(color=color, width=4), hoverinfo="skip"))
    fig.add_trace(go.Scatter(
        x=[d], y=[0], mode="markers",
        marker=dict(color=color, size=13,
                    line=dict(color="white", width=2)),
        hovertemplate=f"차이 {d:+.2f}%p<br>95%% CI [{lo:+.2f}, {hi:+.2f}]<extra></extra>"))
    fig.update_xaxes(range=[-span, span], zeroline=False,
                     showgrid=False, ticksuffix="%p",
                     tickfont=dict(size=11, color=C.BRAND["muted"]))
    fig.update_yaxes(visible=False, range=[-1, 1])
    return _base(fig, height=86, margin=dict(l=8, r=8, t=6, b=22))


def spark(series, color=None):
    """지표 카드의 소형 추이선. 축도 눈금도 없다 — 모양만 본다."""
    fig = go.Figure(go.Scatter(
        y=list(series), mode="lines",
        line=dict(color=color or C.BRAND["primary"], width=2, shape="spline"),
        fill="tozeroy", fillcolor="rgba(79,70,229,0.08)",
        hoverinfo="skip"))
    fig.update_xaxes(visible=False)
    fig.update_yaxes(visible=False,
                     range=[min(series) * 0.97, max(series) * 1.03])
    return _base(fig, height=44, margin=dict(l=0, r=0, t=0, b=0))


def peeking(df, final_lift):
    """관측 시점별 효과. 초반에 멈췄으면 무엇을 봤을지 보여준다."""
    colors = [C.COLORS["warn"] if s else C.COLORS["none"] for s in df.sig]
    fig = go.Figure()
    fig.add_hline(y=final_lift * 100, line=dict(
        color=C.BRAND["muted"], width=1, dash="dot"))
    fig.add_trace(go.Bar(
        x=[f"{int(c)}일" for c in df.cut], y=df.lift * 100,
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{v*100:+.1f}%" for v in df.lift],
        textposition="outside", textfont=dict(size=12),
        hovertemplate="%{x}<br>상대효과 %{y:.1f}%<extra></extra>"))
    fig.update_xaxes(showgrid=False, tickfont=dict(size=12))
    fig.update_yaxes(showgrid=True, gridcolor=C.BRAND["line"],
                     ticksuffix="%", tickfont=dict(size=11,
                                                   color=C.BRAND["muted"]))
    return _base(fig, height=240, margin=dict(l=8, r=8, t=20, b=8))


def effect_decay(w):
    """기간별 효과 추이. 신규성 효과는 여기서만 드러난다."""
    fig = go.Figure()
    fig.add_hline(y=0, line=dict(color=C.BRAND["line"], width=1))
    fig.add_trace(go.Scatter(
        x=w.label, y=w.lift * 100, mode="lines+markers",
        line=dict(color=C.COLORS["warn"], width=3, shape="spline"),
        marker=dict(size=9, color=C.COLORS["warn"],
                    line=dict(color="white", width=2)),
        hovertemplate="%{x}<br>상대효과 %{y:.1f}%<extra></extra>"))
    fig.update_xaxes(showgrid=False, tickfont=dict(size=12))
    fig.update_yaxes(showgrid=True, gridcolor=C.BRAND["line"],
                     ticksuffix="%", tickfont=dict(size=11,
                                                   color=C.BRAND["muted"]))
    return _base(fig, height=240, margin=dict(l=8, r=8, t=12, b=8))


def cac_compare(g):
    """원가와 유효 원가를 나란히. 순위가 뒤집히는지 보이는 것이 목적이다.

    ★ 골격 원본은 채널별 CAC 였다(컬럼 channel·CAC·유효CAC). 우리는 채널 개념이
      없어 축과 컬럼을 바꿨다 — 축 이름을 코드에 박지 않으려고 device_compare 처럼
      **첫 열을 그대로 쓴다.** 그래야 config.EFFICIENCY_DIM 을 바꿔도 안 깨진다.

    ⚠️ **뒤집히지 않아도 이 차트는 그린다.** 안 뒤집힌 것을 보이는 것이
      "차이 없음"이라고 글로 쓰는 것보다 낫다.
    """
    g = g.sort_values("원가")
    label = g[g.columns[0]]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="원가", y=label, x=g.원가, orientation="h",
        marker=dict(color=C.BRAND["line"], line=dict(width=0)),
        text=[f"{v:,.0f}" for v in g.원가], textposition="inside",
        textfont=dict(size=11, color=C.BRAND["ink"]),
        hovertemplate="%{y} 원가 %{x:,.0f}원<extra></extra>"))
    fig.add_trace(go.Bar(
        name="유효 원가", y=label, x=g.유효원가, orientation="h",
        marker=dict(color=[C.COLORS["block"] if r else C.BRAND["primary"]
                           for r in g.역전], line=dict(width=0)),
        text=[f"{v:,.0f}" for v in g.유효원가], textposition="outside",
        textfont=dict(size=11, color=C.BRAND["muted"]),
        hovertemplate="%{y} 유효 원가 %{x:,.0f}원<extra></extra>"))
    fig.update_layout(barmode="group", bargap=0.35, bargroupgap=0.05)
    fig.update_yaxes(showgrid=False, tickfont=dict(size=13))
    fig.update_xaxes(visible=False, range=[0, g.유효원가.max() * 1.28])
    fig = _base(fig, height=64 * len(g) + 46, margin=dict(l=8, r=8, t=28, b=4))
    # ★ _base() 가 showlegend=False 를 건다. 막대가 둘이라 범례가 없으면
    #   어느 쪽이 유효 원가인지 알 수 없으므로 **_base 뒤에** 되켠다.
    fig.update_layout(showlegend=True,
                      legend=dict(orientation="h", y=1.12, x=0,
                                  font=dict(size=11)))
    return fig


def trend(m, col, suffix=""):
    fig = go.Figure(go.Scatter(
        x=list(m.index), y=m[col], mode="lines+markers",
        line=dict(color=C.BRAND["primary"], width=2.5, shape="spline"),
        marker=dict(size=6),
        hovertemplate="%{x}<br>%{y:,.2f}" + suffix + "<extra></extra>"))
    fig.update_xaxes(showgrid=False, tickfont=dict(size=11))
    fig.update_yaxes(showgrid=True, gridcolor=C.BRAND["line"],
                     tickfont=dict(size=11, color=C.BRAND["muted"]))
    return _base(fig, height=260, margin=dict(l=8, r=8, t=8, b=8))


# ── 납기 전망 (5번째 화면 · 우리 도메인 고유) ─────────────────────
def backlog_bars(b):
    """미출하 수주를 납기까지 남은 일수 구간으로. 색은 **판정에만** 쓴다.

    구간 이름·순서·상태색은 config.BACKLOG_BINS 가 정한다 — 여기서 정하지 않는다.
    """
    fig = go.Figure(go.Bar(
        x=b.건수, y=b.구간, orientation="h",
        marker=dict(color=[C.COLORS[s] for s in b.상태], line=dict(width=0)),
        text=[f"{n:,}{C.UNIT} · {r*100:.1f}%" for n, r in zip(b.건수, b.비중)],
        textposition="outside", textfont=dict(size=12, color=C.BRAND["muted"]),
        hovertemplate="%{y}<br>%{x:,}" + C.UNIT + "<extra></extra>"))
    fig.update_yaxes(autorange="reversed", showgrid=False, tickfont=dict(size=13))
    fig.update_xaxes(visible=False, range=[0, b.건수.max() * 1.42])
    return _base(fig, height=46 * len(b) + 40, margin=dict(l=8, r=8, t=4, b=4))


def outlook_chart(ol):
    """주차별 — 막대는 그 주에 해야 할 양, 선은 **남는 것**.

    남는 것(누적 밀림)을 선으로 따로 그리는 이유: 막대만 보면 매주 비슷해 보이는데,
    실제로 물어야 할 것은 *"쌓이는가 줄어드는가"* 다.
    """
    fig = go.Figure()
    fig.add_bar(name="그 주 납기 도래", x=ol.주차, y=ol.납기도래,
                marker=dict(color=C.BRAND["line"], line=dict(width=0)),
                hovertemplate="%{x}<br>납기 %{y:,}" + C.UNIT + "<extra></extra>")
    fig.add_bar(name="처리(최근 실측 속도)", x=ol.주차, y=ol.처리,
                marker=dict(color=C.BRAND["primary"], line=dict(width=0)),
                hovertemplate="%{x}<br>처리 %{y:,}" + C.UNIT + "<extra></extra>")
    fig.add_scatter(name="남는 것(누적)", x=ol.주차, y=ol.누적밀림,
                    mode="lines+markers", yaxis="y2",
                    line=dict(color=C.COLORS["block"], width=3, shape="spline"),
                    marker=dict(size=8, line=dict(color="white", width=2)),
                    hovertemplate="%{x}<br>남는 것 %{y:,}" + C.UNIT + "<extra></extra>")
    fig.update_layout(
        barmode="group", bargap=0.3,
        yaxis=dict(title=None, showgrid=True, gridcolor=C.BRAND["line"],
                   tickfont=dict(size=11, color=C.BRAND["muted"])),
        yaxis2=dict(overlaying="y", side="right", showgrid=False,
                    tickfont=dict(size=11, color=C.COLORS["block"])))
    fig.update_xaxes(showgrid=False, tickfont=dict(size=12))
    fig = _base(fig, height=320, margin=dict(l=8, r=8, t=34, b=8))
    fig.update_layout(showlegend=True,
                      legend=dict(orientation="h", y=1.14, x=0,
                                  font=dict(size=11)))
    return fig


def dwell_bars(g, height=None):
    """단계별 체류일수. **통과율 퍼널 바로 아래**에 같은 순서로 놓는다.

    같은 단계 순서를 두 번 보여주는 것이 목적이다 —
    위(통과율)는 평평한데 아래(체류일)는 한쪽으로 쏠린 것이 한눈에 보여야 한다.

    막대 길이는 **중앙값**, 옅은 막대는 p90 이다. 평균을 쓰지 않는 이유는
    꼬리가 긴 구간(최대 74일)이 평균을 끌어 실제 감각과 어긋나기 때문이다.
    """
    g = g.iloc[::-1]                      # 퍼널과 같은 위→아래 순서로 뒤집는다
    worst = g["중앙"].max()
    colors = [C.COLORS["block"] if v == worst else C.BRAND["primary"]
              for v in g["중앙"]]
    fig = go.Figure()
    # p90 을 뒤에 옅게 깔아 **꼬리가 얼마나 긴지**를 같이 보여준다
    fig.add_trace(go.Bar(
        x=g["p90"], y=g["구간"], orientation="h", name="p90",
        marker=dict(color="rgba(148,163,184,.28)", line=dict(width=0)),
        hovertemplate="%{y}<br>p90 %{x:.0f}일<extra></extra>"))
    fig.add_trace(go.Bar(
        x=g["중앙"], y=g["구간"], orientation="h", name="중앙",
        marker=dict(color=colors, line=dict(width=0)),
        text=[f"{v:.0f}일  ({s*100:.0f}%)" for v, s in zip(g["중앙"], g["비중"])],
        textposition="outside", textfont=dict(size=12, color=C.BRAND["muted"]),
        hovertemplate="%{y}<br>중앙 %{x:.0f}일<extra></extra>"))
    fig.update_layout(barmode="overlay", showlegend=False)
    fig.update_yaxes(showgrid=False, tickfont=dict(size=12))
    fig.update_xaxes(visible=False, range=[0, g["p90"].max() * 1.35])
    # ★ 2026-09-05 — 높이를 밖에서 받을 수 있게 했다.
    #   퍼널(11단계)과 나란히 놓는데 이쪽은 10구간이라 46px 씩 곱하면
    #   **두 그림의 아래끝이 46px 어긋난다.** 짝으로 읽으라고 만든 그림이
    #   서로 안 맞으면 눈이 먼저 그 어긋남을 본다.
    return _base(fig, height=height or (46 * len(g) + 40),
                 margin=dict(l=8, r=8, t=4, b=4))
