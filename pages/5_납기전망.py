# -*- coding: utf-8 -*-
"""납기 전망 — 밀린 수주가 언제 풀리는가.

★ **골격에 없는 우리 화면이다.** 강사 앱의 `5_예산전망` 과 같은 자리다 —
  교안: *"골격은 출발점이지 종착점이 아니다."*

왜 이 화면인가
  우리 퍼널은 단계별 탈락이 최대 1.6%로 평평해서 **통과율로는 문제가 안 보인다.**
  같은 데이터를 납기 축에서 보면 지연 4.0% · 이탈 4.3%가 드러난다.
  대시보드가 "얼마나 새는가"를 본다면, 이 화면은 **"지금 무엇이 남아 있고
  언제 풀리는가"**를 본다.

누가 언제 보는가
  생산·영업 담당이 **주 1회**. 이번 주에 무엇을 먼저 밀지 정하는 자리다.

⚠️ **예측이 아니라 산술 전망이다.**
  지금 밀린 것과 앞으로 올 납기를 최근 실측 처리 속도로 나눈 것뿐이다.
  계절성·설비 정지·긴급 삽입을 모른다. 화면에도 이 문장을 띄운다 —
  안 띄우면 전망이 예측으로 읽히고, 회의에서는 계획으로 읽힌다.
"""
import streamlit as st

from core import config as C, load, metrics as M
from viz import charts, ui

st.set_page_config(page_title="납기 전망", page_icon="📈", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("outlook")

if "run" not in st.session_state:
    st.session_state.run = None
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

# ★ 화면은 **계산하지 않는다.** 여기 쓰는 값은 전부 metrics 에서 온다.
#   DESIGN.md 1절 — 계산이 화면 코드 안에 숨으면 같은 수치를 리포트에서 다시 셀 때
#   값이 갈린다. (2026-09-01 감사에서 이 파일에 계산 4곳이 잡혀 옮겼다)
b = M.backlog(t)
ol = M.outlook(t)
tp = M.throughput(t)
v = M.outlook_verdict(t)

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:4px">'
            '납기 전망</div>'
            f'<div style="font-size:13px;color:{C.BRAND["muted"]};margin-bottom:16px">'
            '밀린 수주가 언제 풀리는가 · <b>예측이 아니라 산술 전망</b></div>',
            unsafe_allow_html=True)

# ── 지표 ──────────────────────────────────────────────────────────
k = st.columns(4)
with k[0]:
    st.markdown(ui.kpi_card("미출하", f"{v['미출하']:,}{C.UNIT}",
                            f"전체 수주의 {v['미출하비중']:.1f}%", "none"),
                unsafe_allow_html=True)
with k[1]:
    # ★ 전에는 "block" 을 박아 값과 무관하게 늘 빨강이었다. 판정 색을 장식에 쓰면
    #   색이 아무 뜻도 없게 된다(교안 3절). 긴급품 비율의 임계값으로 판정한다.
    st.markdown(ui.kpi_card(f"긴급 {C.LONG_URGENT_DAYS}일 초과",
                            f"{v['초과']:,}{C.UNIT}",
                            f"미출하의 {v['초과비중']:.1f}%",
                            M.status_of("긴급품 비율",
                                        v["초과"] / len(t["orders"]) * 100)),
                unsafe_allow_html=True)
with k[2]:
    # 처리 속도는 좋고 나쁨을 가를 기준이 없다 — 판정하지 않는다("none").
    # 기준이 없는데 초록을 칠하면 "정상"이라고 말한 것이 된다.
    st.markdown(ui.kpi_card("주당 처리", f"{tp['주당']:,.0f}{C.UNIT}",
                            f"최근 {tp['기간일']}일 실측", "none"),
                unsafe_allow_html=True)
with k[3]:
    if v["해소주차"]:
        st.markdown(ui.kpi_card("밀림 해소", v["해소주차"],
                                "이 속도가 유지되면", "ok"), unsafe_allow_html=True)
    else:
        st.markdown(ui.kpi_card("밀림 해소", f"{v['주차수']}주 내 없음",
                                f"{v['끝밀림']:,}{C.UNIT} 남음", "block"),
                    unsafe_allow_html=True)

# ── 지금 무엇이 남아 있나 ─────────────────────────────────────────
ui.section("지금 남아 있는 것", "미출하 수주를 납기까지 남은 일수로 나눴다")
left, right = st.columns([1.3, 1])
with left:
    st.plotly_chart(charts.backlog_bars(b), width="stretch",
                    config={"displayModeBar": False})
with right:
    # ★ 2026-09-03 — 여기 색이 C.COLORS["block"] 로 **박혀 있었다.**
    #   0건이어도 빨강으로 떴다 = 판정이 아니라 장식이다.
    #   교안 부록 C: *"강조 색은 '이걸 봐야 한다'는 뜻일 때만 쓴다.
    #   그냥 예쁘게 하려고 쓰면 진짜 봐야 할 때 아무도 안 본다."*
    #   → 긴급품 비율 임계값으로 실제 판정한다. 0건이면 색이 안 붙는다.
    late_lv = M.status_of("긴급품 비율",
                          v["시작밀림"] / len(t["orders"]) * 100)
    late_color = C.COLORS[late_lv] if late_lv != "ok" else C.BRAND["ink"]
    st.markdown(
        f'<div class="card tight">'
        f'<div style="font-size:12px;color:{C.BRAND["muted"]}">이미 늦은 것</div>'
        f'<div style="font-size:22px;font-weight:700;color:{late_color}">'
        f'{v["시작밀림"]:,}{C.UNIT}</div>'
        f'<div style="font-size:12px;color:{C.BRAND["muted"]};margin-top:4px">'
        f'납기가 지난 미출하 — 이번 주 처리분을 여기서 먼저 가져간다</div></div>',
        unsafe_allow_html=True)
    miss = v["납기미정"]
    if miss:
        ui.callout(
            f"<b>납기 미정 {miss:,}{C.UNIT}</b>은 구간에서 뺐습니다. "
            f"남은 일수를 셀 수 없어서입니다 — 빼고 세면 분모가 조용히 줄어드니 "
            f"따로 한 줄로 세워 두었습니다.", "info")

# ── 앞으로 ────────────────────────────────────────────────────────
ui.section(f"앞으로 {C.OUTLOOK_WEEKS}주",
           "막대는 그 주에 해야 할 양, 선은 처리하고 남는 것")
st.plotly_chart(charts.outlook_chart(ol), width="stretch",
                config={"displayModeBar": False})

c1, c2 = st.columns([1.4, 1])
with c1:
    if v["해소주차"]:
        ui.callout(
            f"지금 늦은 <b>{v['시작밀림']:,}{C.UNIT}</b>은 주당 "
            f"<b>{tp['주당']:,.0f}{C.UNIT}</b> 속도가 유지되면 "
            f"<b>{v['해소주차']}</b>에 풀립니다. "
            f"그 전까지는 새로 들어오는 납기와 밀린 것을 같이 처리해야 합니다.",
            "info")
    else:
        ui.callout(
            f"이 속도로는 <b>{v['주차수']}주 뒤에도 {v['끝밀림']:,}{C.UNIT}이 남습니다.</b> "
            f"처리 속도를 올리거나 납기를 다시 잡아야 합니다.")
with c2:
    st.dataframe(ol, hide_index=True, width="stretch")

# ── 이 화면이 말하지 않는 것 ──────────────────────────────────────
# 교안 고정 조항 — 관측 데이터로 인과를 주장하지 않는다.
# 전망을 예측으로 읽지 않게 하는 것이 이 절의 일이다.
ui.section("이 화면이 말하지 않는 것")
st.markdown(f"""
- **예측이 아닙니다.** 지금 밀린 것과 앞으로 올 납기를 **최근 {tp['기간일']}일 실측
  속도**로 나눈 산술입니다. 계절성·설비 정지·긴급 삽입을 모릅니다.
- **처리 속도는 목표가 아니라 실측입니다.** 목표치를 쓰면 전망이 희망이 되고,
  희망은 회의에서 계획으로 읽힙니다.
- **어느 수주를 먼저 할지는 정하지 않습니다.** 고객사·금액·공정 사정은 이 화면에
  없습니다. 순서는 사람이 정합니다.
- **왜 밀렸는지는 답하지 않습니다.** 공정별 체류일은 6공정 작업일보의 처리시간
  비중으로 **배분한 값**이지 실측이 아닙니다 — 줄 서서 기다린 시간은 작업일보에
  안 남습니다. 어느 공정 앞에 얼마나 쌓였는지는 이 데이터로 알 수 없습니다.
""")
st.caption("데이터는 전부 합성입니다. 방법은 확인할 수 있으나 판정은 실데이터로만 할 수 있습니다.")
