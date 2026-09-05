# -*- coding: utf-8 -*-
"""아카이브 — 지난 실행을 찾고 비교한다.

재현이 핵심이다. 같은 입력이면 같은 결과가 나와야 하고,
그것을 확인할 수 없으면 자동화를 신뢰할 수 없다.
"""
import pandas as pd
import streamlit as st

from core import config as C, gates, load, metrics as M
from viz import charts, ui

st.set_page_config(page_title="아카이브", page_icon="🗂️", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("archive")

if "run" not in st.session_state:
    st.session_state.run = None
ui.context_bar(st.session_state.run)

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '아카이브</div>', unsafe_allow_html=True)

runs = gates.load_all()

ui.section("실행 이력")
if not runs:
    st.info("아직 저장된 실행이 없습니다. 실행 화면에서 게이트 2까지 통과하면 "
            "여기에 기록됩니다.")
else:
    for r in runs[:20]:
        lv = {"완료": "ok", "진행중": "warn", "차단": "block"}.get(
            r.get("status", ""), "none")
        gl = r.get("gates", {})
        passed = "".join(
            f'<span style="margin-right:8px">게이트{n} '
            f'{"✓" if str(n) in gl else "—"}</span>' for n in (1, 2, 3))
        # ★ 2026-09-04 (Day3 프롬프트 11) — 게이트별로 **나란히** 보여준다.
        #   전에는 " / " 로 이어 붙여서 어느 근거가 어느 게이트 것인지 알 수 없었다.
        #   게이트 1은 "이 데이터로 시작해도 되는가", 게이트 2는 "계산이 말이 되는가"
        #   로 묻는 것이 다르므로, 합쳐 놓으면 두 판단을 한 판단으로 읽는다.
        rows = []
        for n in ("1", "2", "3"):
            g = gl.get(n)
            if not g:
                continue
            nm = gates.GATES[int(n)]["name"]
            txt = (g.get("note") or "").strip()
            at = (g.get("passed_at", "") or "")[11:16]
            rows.append(
                f'<div style="margin-top:4px">'
                f'<b>게이트 {n} · {nm}</b> {at} — '
                + (txt if txt else
                   '<span style="color:#b45309">근거가 비어 있습니다 '
                   '(2026-09-04 이전 기록)</span>')
                + '</div>')
        notes = "".join(rows)
        st.markdown(
            f'<div class="card tight" style="margin-bottom:8px">'
            f'<div style="display:flex;align-items:center;gap:14px">'
            f'<div style="font-weight:700" class="num">{r["run_id"]}</div>'
            f'<div style="font-size:12px;color:#64748b">{r.get("dataset","")}</div>'
            f'<div style="margin-left:auto">{ui.badge(lv, r.get("status",""))}</div>'
            f'</div>'
            f'<div style="font-size:12px;color:#64748b;margin-top:8px">{passed}</div>'
            + (f'<div style="font-size:12px;color:#94a3b8;margin-top:6px">'
               f'{notes}</div>' if notes else "")
            + '</div>', unsafe_allow_html=True)

# ── 기간 비교 ─────────────────────────────────────────────────────
ui.section("기간 비교", "수준이 아니라 변화를 본다")
t = ui.guard(load.load_all)
if t is None:
    st.stop()
m = ui.guard(M.monthly, t)

if m is not None and len(m) >= 2:
    months = list(m.index)
    metric_cols = [c for c in m.columns]

    c1, c2 = st.columns(2)
    with c1:
        a = st.selectbox("기준 기간", months, index=len(months) - 2)
    with c2:
        b = st.selectbox("비교 기간", months, index=len(months) - 1)

    # ★ 높을수록 나쁜 지표. metrics.status_of() 와 같은 목록을 쓴다.
    HIGHER_IS_WORSE = {"이탈", "이탈률", "이탈율", "해지율", "불량률", "반품률"}

    rows = []
    for col in metric_cols:
        va, vb = m.loc[a, col], m.loc[b, col]
        pct = (vb / va - 1) * 100 if va else 0
        good = (vb <= va) if col in HIGHER_IS_WORSE else (vb >= va)
        rows.append({"지표": col, str(a): f"{va:,.2f}", str(b): f"{vb:,.2f}",
                     "변화": f"{pct:+.1f}%", "판정": "정상" if good else "주의"})

    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True,
                 column_config={"판정": st.column_config.TextColumn(width="small")})

    ui.section("추이")
    col = st.selectbox("지표", metric_cols)
    st.plotly_chart(charts.trend(m, col), width="stretch",
                    config={"displayModeBar": False})

# ── 재현 ──────────────────────────────────────────────────────────
ui.section("재현", "같은 입력이면 같은 결과가 나와야 한다")
if st.button("지금 데이터로 재계산해 비교"):
    f = ui.guard(M.funnel, t)
    k = ui.guard(M.kpis, t)
    if f is not None and k is not None:
        rows = [{"항목": f"{r.label} 도달", "값": f"{r.n:,}"}
                for r in f.itertuples()]
        rows += [{"항목": name, "값": v["fmt"].format(v["value"])}
                 for name, v in k.items()]
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        st.success("계산에 현재 시각을 쓰지 않으므로 "
                   "몇 번을 돌려도 같은 값이 나옵니다.")
