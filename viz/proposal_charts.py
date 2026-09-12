# -*- coding: utf-8 -*-
"""제안서에 들어갈 그림만 만든다. **인라인 SVG 문자열**을 돌려준다.

────────────────────────────────────────────────────────────────────
★ **그림 하나에는 그것이 증명하는 문장 하나**가 본문에 있어야 한다.
  없으면 장식이다. 장식용 그래프는 결재 문서에서 읽는 사람의 시간을 쓴다.

★ **색은 셋까지** — 강조 1 · 기본 1 · 회색 1.
  `config.COLORS` 는 넷(ok·warn·block·none)이라 그중 셋만 골라 쓴다.
  왜 이 셋인가 — `block` 은 "여기가 문제다"를 가리키는 색이라 강조로,
  `ok` 는 판정색이 아닌 자리에서 기본 막대로, `none` 은 회색으로 쓴다.
  ⚠️ 판정 색을 판정이 아닌 곳에 쓰지 않는다는 규칙(CLAUDE.md 5)과 부딪히지
     않게, **여기서는 값의 좋고 나쁨을 색으로 말하지 않는다.**
     강조는 *"이 칸을 보라"* 이지 *"이 칸이 나쁘다"* 가 아니다.

★ **외부 CDN·이미지 파일·폰트 링크 금지.** 문자열 하나로 끝나야 한다.

⚠️ **눈금을 0부터 그리지 않는 경우가 있다.** 우리 축 분해는 87~92% 구간에
   몰려 있어 0부터 그리면 막대 길이비가 95%를 넘어 차이가 안 보인다.
   자를 때는 **잘랐다는 것을 축에 적는다** — 안 적으면 격차를 과장한 그림이 된다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import html

import pandas as pd

from core import config as C

# 색 셋. 위 docstring 의 근거 참조.
_HI = C.COLORS["block"]      # 강조 — "이 칸을 보라"
_BASE = C.COLORS["ok"]       # 기본
_GREY = C.COLORS["none"]     # 회색
_INK = C.BRAND["ink"]
_MUTED = C.BRAND["muted"]
_LINE = C.BRAND["line"]

_FONT = ("font-family:'Malgun Gothic','Apple SD Gothic Neo',sans-serif")


def _esc(s) -> str:
    return html.escape(str(s), quote=True)


def _svg(w: int, h: int, body: str, title: str) -> str:
    """공통 껍데기. `role="img"` 와 `<title>` 을 넣어 읽어 주는 도구도 읽게 한다."""
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" '
            f'role="img" aria-label="{_esc(title)}" '
            f'xmlns="http://www.w3.org/2000/svg" style="{_FONT}">'
            f'<title>{_esc(title)}</title>{body}</svg>')


def _cap(text: str) -> str:
    """그림 아래 한 줄 — **그레인**을 적는다. 무엇을 하나로 셌는지."""
    return (f'<div style="{_FONT};font-size:9pt;color:{_MUTED};margin-top:4px">'
            f'{_esc(text)}</div>')


# ── 1) 현황 — 단계별 도달 막대 ────────────────────────────────────
def funnel_svg(f: pd.DataFrame) -> str:
    """단계별 **이탈** 막대. **병목 구간 하나만** 강조색.

    증명하는 문장 — *"여기서 가장 많이 빠진다."*

    ⚠️ **도달 건수로 그리지 않는다.** 우리 11단계는 도달이 76,441~79,992 라
       0부터 그리면 막대 길이비가 95.6% 여서 **전부 같아 보인다.** 실제로
       한 번 그려 보고 고쳤다(2026-09-10).
       이 그림이 증명해야 하는 문장은 *"여기서 가장 많이 빠진다"* 이므로
       **빠진 건수**를 그린다 — 주장과 그림이 같은 것을 가리켜야 한다.
       도달 수는 막대 옆에 숫자로 함께 적는다.
    """
    d = f.dropna(subset=["n"]).copy()
    d = d[d["drop"].fillna(0) > 0]      # 아무도 안 빠진 단계는 그리지 않는다
    if d.empty:
        return ""                       # 값이 없으면 아예 그리지 않는다
    top = float(d["drop"].max())
    row_h, gap, left, right = 22, 7, 96, 118
    w = 720
    bar_w = w - left - right
    h = len(d) * (row_h + gap) + 34

    parts = []
    for i, (_, r) in enumerate(d.iterrows()):
        y = i * (row_h + gap) + 8
        drop = float(r["drop"])
        bw = max(1.0, bar_w * drop / top) if top else 1.0
        hit = bool(r.get("is_bottleneck", False))
        col = _HI if hit else _GREY
        parts.append(
            f'<text x="{left - 8}" y="{y + 15}" text-anchor="end" '
            f'font-size="11" fill="{_INK}">{_esc(r["label"])}</text>'
            f'<rect x="{left}" y="{y}" width="{bw:.1f}" height="{row_h}" '
            f'rx="2" fill="{col}" opacity="{1 if hit else .55}"/>'
            f'<text x="{left + bw + 7:.1f}" y="{y + 15}" font-size="11" '
            f'fill="{_INK}" font-weight="{700 if hit else 400}">'
            f'{int(drop):,}</text>'
            f'<text x="{w - 6}" y="{y + 15}" text-anchor="end" '
            f'font-size="9.5" fill="{_MUTED}">도달 {int(r["n"]):,}</text>')
        if hit:
            parts.append(
                f'<text x="{left + bw + 62:.1f}" y="{y + 15}" font-size="10" '
                f'fill="{_HI}">가장 많이 빠짐</text>')

    parts.append(
        f'<line x1="{left}" y1="{h - 20}" x2="{left + bar_w}" y2="{h - 20}" '
        f'stroke="{_LINE}"/>'
        f'<text x="{left}" y="{h - 7}" font-size="9.5" fill="{_MUTED}">'
        f'0건 빠짐</text>'
        f'<text x="{left + bar_w}" y="{h - 7}" text-anchor="end" '
        f'font-size="9.5" fill="{_MUTED}">{int(top):,}건</text>')

    return (_svg(w, h, "".join(parts), "단계별 빠진 건수")
            # ⚠️ caption 은 그대로 찍히는 자리라 마크다운이 해석되지 않는다.
            #   `**강조**` 를 쓰면 별표가 그대로 보인다 — 말로 강조한다.
            + _cap("막대는 그 단계에서 빠진 건수입니다. 도달 수가 아닙니다 · "
                   "발주 한 건을 하나로 셌습니다. 같은 단계를 두 번 밟아도 한 번만 셉니다"))


# ── 2) 원인 — 축별 가로 막대 ──────────────────────────────────────
def gap_svg(g: pd.DataFrame, dim: str, value: str = "준수율") -> str:
    """축별 가로 막대. **최고·최저만** 색, 나머지는 회색.

    증명하는 문장 — *"이 집단과 저 집단이 다르다."*

    ⚠️ 값이 좁은 구간에 몰려 있으면 **눈금을 잘라** 그린다.
       자른 사실을 축에 적는다 — 안 적으면 격차를 과장한 그림이 된다.
    """
    d = g.dropna(subset=[value]).copy()
    if d.empty or len(d) < 2:
        return ""
    d = d.sort_values(value)
    vals = d[value] * 100
    lo, hi = float(vals.min()), float(vals.max())

    # 눈금 시작점 — 0부터 그려서 길이비가 90%를 넘으면 차이가 안 보인다.
    cut = lo / hi > 0.90 if hi else False
    base = (lo - (hi - lo) * 0.35) if cut else 0.0
    span = (hi - base) or 1.0

    row_h, gap, left, right = 20, 8, 84, 96
    w = 720
    bar_w = w - left - right
    h = len(d) * (row_h + gap) + (46 if cut else 34)

    parts = []
    for i, (_, r) in enumerate(d.iterrows()):
        y = i * (row_h + gap) + 8
        v = float(r[value]) * 100
        bw = max(1.0, bar_w * (v - base) / span)
        edge = v in (lo, hi)
        col = _HI if v == lo else (_BASE if v == hi else _GREY)
        parts.append(
            f'<text x="{left - 8}" y="{y + 14}" text-anchor="end" '
            f'font-size="11" fill="{_INK}">{_esc(r[dim])}</text>'
            f'<rect x="{left}" y="{y}" width="{bw:.1f}" height="{row_h}" '
            f'rx="2" fill="{col}" opacity="{1 if edge else .55}"/>'
            f'<text x="{left + bw + 7:.1f}" y="{y + 14}" font-size="11" '
            f'fill="{_INK}" font-weight="{700 if edge else 400}">'
            f'{v:.2f}%</text>')

    axis_y = h - (32 if cut else 20)
    parts.append(
        f'<line x1="{left}" y1="{axis_y}" x2="{left + bar_w}" y2="{axis_y}" '
        f'stroke="{_LINE}"/>'
        f'<text x="{left}" y="{axis_y + 13}" font-size="9.5" fill="{_MUTED}">'
        f'{base:.1f}%</text>'
        f'<text x="{left + bar_w}" y="{axis_y + 13}" text-anchor="end" '
        f'font-size="9.5" fill="{_MUTED}">{hi:.1f}%</text>')
    if cut:
        # ★ 자른 사실을 반드시 적는다.
        parts.append(
            f'<text x="{left}" y="{axis_y + 27}" font-size="9.5" fill="{_HI}">'
            f'가로축은 0 이 아니라 {base:.1f}% 에서 시작합니다 '
            f'(값이 좁은 구간에 몰려 있어 잘랐습니다)</text>')

    return (_svg(w, h, "".join(parts), f"{dim}별 값 비교")
            + _cap(f"{dim} 별 · 기한이 이미 지난 {int(g['분모'].sum()):,}건 기준"))


# ── 3) 추세 — 꺾은선 ──────────────────────────────────────────────
def trend_svg(s: pd.Series, name: str, threshold: float | None = None) -> str:
    """최근 12개월 꺾은선. 임계선이 있으면 **점선**으로.

    증명하는 문장 — *"줄고 있다 / 늘고 있다."*

    ⚠️ **값이 없는 달은 잇지 않는다.** 확정 대기와 얇은 달 때문에 비는 자리를
       0 으로 이으면 *관찰 기간이 모자란 것*이 급락으로 보인다.
    """
    d = s.dropna()
    if len(d) < 3:
        return ""
    w, h, left, right, top, bot = 720, 200, 56, 24, 18, 40
    pw, ph = w - left - right, h - top - bot
    lo, hi = float(d.min()), float(d.max())
    if threshold is not None:
        lo, hi = min(lo, threshold), max(hi, threshold)
    pad = (hi - lo) * 0.2 or 1.0
    lo, hi = lo - pad, hi + pad
    span = hi - lo

    xs = [left + pw * i / max(1, len(d) - 1) for i in range(len(d))]
    ys = [top + ph * (1 - (float(v) - lo) / span) for v in d]

    parts = [f'<rect x="{left}" y="{top}" width="{pw}" height="{ph}" '
             f'fill="none" stroke="{_LINE}"/>']
    if threshold is not None:
        ty = top + ph * (1 - (threshold - lo) / span)
        parts.append(
            f'<line x1="{left}" y1="{ty:.1f}" x2="{left + pw}" y2="{ty:.1f}" '
            f'stroke="{_HI}" stroke-width="1.2" stroke-dasharray="5 4"/>'
            f'<text x="{left + pw - 3}" y="{ty - 5:.1f}" text-anchor="end" '
            f'font-size="9.5" fill="{_HI}">기준 {threshold:g}</text>')

    pts = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    parts.append(f'<polyline points="{pts}" fill="none" stroke="{_BASE}" '
                 f'stroke-width="2"/>')
    for i, (x, y) in enumerate(zip(xs, ys)):
        last = i == len(xs) - 1
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{3.5 if last else 2.5}" '
                     f'fill="{_HI if last else _BASE}"/>')
    parts.append(
        f'<text x="{xs[-1]:.1f}" y="{ys[-1] - 9:.1f}" text-anchor="end" '
        f'font-size="11" font-weight="700" fill="{_INK}">'
        f'{float(d.iloc[-1]):.2f}</text>')

    for x, lab in ((xs[0], str(d.index[0])), (xs[-1], str(d.index[-1]))):
        parts.append(f'<text x="{x:.1f}" y="{h - 22}" text-anchor="middle" '
                     f'font-size="9.5" fill="{_MUTED}">{_esc(lab)}</text>')
    for v, y in ((hi, top), (lo, top + ph)):
        parts.append(f'<text x="{left - 6}" y="{y + 4:.1f}" text-anchor="end" '
                     f'font-size="9.5" fill="{_MUTED}">{v:.1f}</text>')

    miss = int(s.isna().sum())
    cap = f"{name} 월별 · 값이 없는 달 {miss}개는 잇지 않았습니다" if miss else \
          f"{name} 월별"
    return _svg(w, h, "".join(parts), f"{name} 추세") + _cap(cap)
