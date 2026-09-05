# -*- coding: utf-8 -*-
"""대시보드 — 여기서 발견이 일어난다.

반복해서 보는 화면이므로 실행 절차를 지나치지 않고 바로 지표에 닿게 한다.

이 화면은 Day2~3에 걸쳐 살아난다.
  Day2  지표 카드 · 획득 퍼널 · 유지 퍼널
  Day3  분해 · 실험 카드
"""
import streamlit as st

from core import config as C, load, metrics as M
from viz import charts, ui

st.set_page_config(page_title="대시보드", page_icon="📊", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("dash")

if "run" not in st.session_state:
    st.session_state.run = None
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '대시보드</div>', unsafe_allow_html=True)

# ── 지표 카드 ─────────────────────────────────────────────────────
k = ui.guard(M.kpis, t)
if k:
    m = ui.guard(M.monthly, t)
    cols = st.columns(len(k))
    for col, (name, v) in zip(cols, k.items()):
        with col:
            lv = M.status_of(name, v["value"])
            st.markdown(ui.kpi_card(name, v["fmt"].format(v["value"]), "", lv),
                        unsafe_allow_html=True)
            # 정의는 **접힌 채로** 옆에 둔다 (Day3 프롬프트 13).
            # 카드에 펼쳐 두면 매일 보는 사람에게는 소음이고, 아예 없으면
            # 분모를 모르는 사람이 같은 숫자를 다르게 읽는다.
            ui.metric_def(name)
            # 추이가 있으면 스파크라인. 지표 이름과 열 이름이 같아야 그려진다.
            if m is not None and name in getattr(m, "columns", []):
                st.plotly_chart(
                    charts.spark(m[name], C.COLORS[lv] if lv != "ok" else None),
                    width="stretch", config={"displayModeBar": False},
                    key=f"sp_{name}")
    if not C.THRESHOLDS:
        st.caption("config.THRESHOLDS 가 비어 있어 전부 정상으로 표시됩니다. "
                   "임계값을 채우면 색이 갈립니다.")

# ── 퍼널 둘 — 탭으로 나눈다 (Day2 프롬프트 13 · Day3 실습 H) ──────
# ★ 지적(2026-09-03): "획득퍼널 유지퍼널 구분이 없음, 기간별 전후 비교 없음."
#   세로로 쌓여 있어 아래를 보려면 스크롤해야 했고, 둘이 붙어 있어 **무엇을 보고
#   있는지** 구분이 안 됐다.
#
# @st.fragment — 기간을 바꿔도 **이 함수 안만** 다시 그린다. 안 붙이면 기간 하나
#   바꿀 때마다 데이터를 다시 읽고 위쪽 지표 카드까지 전부 다시 그린다.


def _period_filter(key: str):
    """기간 필터 — **유효 구간 안에서만** 고른다.

    범위를 화면에 박지 않고 monthly() 에서 가져온다. 분모가 얇아 잘라낸 달을
    여기서 다시 보여주면 잘라낸 의미가 없다.
    """
    months = list(M.monthly(t).index)
    if len(months) < 2:
        return (months[0], months[-1]) if months else (None, None)
    # 남이 보낸 링크의 달이 우리 유효 구간에 없을 수 있다 — 그러면 전체로 되돌린다
    a = ui.url_state("from", months[0], months)
    b = ui.url_state("to", months[-1], months)
    if months.index(a) > months.index(b):
        a, b = months[0], months[-1]
    return st.select_slider("기간", options=months, value=(a, b),
                            key=f"period_{key}", label_visibility="collapsed")


@st.fragment
def _acq_tab():
    lo, hi = _period_filter("acq")
    st.caption(f"　기간 **{lo} ~ {hi}** · 퍼널은 완주 코호트 전체를 셉니다 — "
               f"기간은 아래 전후 비교에 걸립니다")
    # 지금 보고 있는 것을 주소에 적는다. 링크를 그대로 보내면 같은 화면이 열린다.
    ui.push_url(**{"from": lo, "to": hi})

    ui.section("획득 퍼널", "그레인을 먼저 확인한다")
    f = ui.guard(M.funnel, t)
    if f is not None:
        # ── 배치 (2026-09-05) ─────────────────────────────────
        # ★ 전에는 왼쪽에 퍼널+체류를 세로로 쌓고 오른쪽에 분해를 뒀다.
        #   재 보니 **오른쪽 아래가 644px 비어 있었고**, 두 차트의 윗줄이
        #   157px 어긋나 있었다(오른쪽 컬럼 위에 위젯이 있어서).
        #
        #   퍼널과 체류는 **같은 단계를 두 축으로 본 짝**이다. 나란히 놓으면
        #   왼쪽은 평평한데 오른쪽은 쏠린 것이 한눈에 들어온다 —
        #   세로로 쌓으면 스크롤하는 사이에 앞 그림을 잊는다.
        #   분해는 그 다음 물음(누가 낮은가)이라 아래 전폭으로 내린다.
        c_pass, c_time = st.columns(2)
        with c_pass:
            st.plotly_chart(charts.funnel_bars(f), width="stretch",
                            config={"displayModeBar": False})
            bn = f[f.is_bottleneck].iloc[0]
            bi = max(int(f.index[f.label == bn.label][0]), 1)
            prev = f.iloc[bi - 1]
            ui.callout(
                f"<b>통과율로 본 병목은 {prev.label} → {bn.label}</b> 구간입니다. "
                f"{prev.n:,}{C.UNIT} 중 {bn.n:,}{C.UNIT}만 넘어가 "
                f"<b>{(1-bn.step_rate)*100:.1f}%가 다음 단계로 못 갑니다.</b>")
            # ★ 여기를 '이탈'이라 쓰지 않는다. 명세 5행의 긴급품(납기 지난 미출하)과
            #   다른 것인데 같은 말을 쓰면 두 숫자가 한 이름으로 회의에 올라간다.

        with c_time:
            # ── 같은 퍼널을 시간 축으로 (2026-09-05) ──────────────
            # ★ 통과율 퍼널 **바로 아래**에 같은 순서로 놓는다. 위는 평평한데
            #   아래는 한쪽으로 쏠린 것이 한눈에 보여야 한다 — 두 그림을 떨어뜨려
            #   두면 "둘 다 봤다"가 되고 **둘을 겹쳐 읽는 일**은 안 일어난다.
            dw = ui.guard(M.stage_dwell, t)
            if dw is not None and len(dw):
                v = M.dwell_verdict(dw)
                st.markdown(
                    f'<div style="font-size:13px;font-weight:700;margin:14px 0 2px">'
                    f'같은 퍼널을 <span style="color:{C.BRAND["primary"]}">'
                    f'머문 날짜</span>로 보면</div>'
                    f'<div style="font-size:12px;color:{C.BRAND["muted"]};'
                    f'margin-bottom:6px">진한 막대 = 중앙값 · 옅은 막대 = 상위 10%'
                    f'</div>', unsafe_allow_html=True)
                # 퍼널과 **같은 높이**로 넘긴다 (11단계 vs 10구간이라
                # 각자 계산하면 아래끝이 어긋난다)
                st.plotly_chart(charts.dwell_bars(dw, height=46 * len(f) + 40),
                                width="stretch",
                                config={"displayModeBar": False})
                ui.callout(
                    f"발주에서 출하까지 중앙 <b>{v['총일수']:.0f}일</b>이고, "
                    f"성격이 셋으로 갈립니다 — "
                    f"계획 <b>{v['계획일수']:.0f}일</b>(서류가 도는 시간) · "
                    f"공정 <b>{v['공정일수']:.0f}일</b>(실제로 만드는 시간) · "
                    f"<b>{v['대기구간']} {v['대기일수']:.0f}일"
                    f"({v['대기비중']*100:.0f}%)</b>. "
                    f"<b>마지막은 병목이 아니라 납기 대기입니다</b> — "
                    f"출하일이 납기에 맞춰 잡히므로 일찍 끝나면 그만큼 기다립니다.",
                    "info")
                ui.callout(
                    f"공정 {v['구간수']}개 중 가장 긴 곳은 <b>{v['최장구간']} "
                    f"{v['최장일수']:.0f}일</b>로 평균의 "
                    f"<b>{v['쏠림']:.1f}배</b>입니다. "
                    f"통과율로는 전 구간 탈락이 최대 "
                    f"<b>{(1-f.step_rate.min())*100:.1f}%</b>라 "
                    f"<b>이 차이가 안 보입니다</b> — "
                    f"<b>새는 것이 아니라 밀리는 것</b>이기 때문입니다.")


        st.divider()
        # ★ 2026-09-05 — 분해에 **제목을 세웠다.** 전에는 제목 없이 축·기준
        #   버튼만 떠 있어서 그 버튼이 무엇을 고르는 것인지 알 수 없었다
        #   (지적: "탭버튼도 뜬금없는 위치에 있는거같아").
        #   위젯은 자기가 무엇을 바꾸는지 **위에 적혀 있어야** 자리를 얻는다.
        ui.section("분해 — 누가 낮은가", "축과 기준을 골라서 본다")
        # ★ 분해 축은 config.DIMS 가 정본이다. 화면에 목록을 박아 두면
        #   축을 늘릴 때 고칠 곳이 둘이 되고, 반드시 한쪽만 고치는 날이 온다.
        # ★ 무엇으로 쪼갤지 못지않게 **무엇을 쪼갤지**가 중요하다 (2026-09-04).
        #   같은 축, 같은 데이터인데 보는 값에 따라 격차가 이만큼 갈린다:
        #       퍼널 전환율   0.6%p   →  "이 축으로는 안 갈린다"
        #       납기 준수율   4.24%p  →  "D사를 봐야 한다"
        #
        # ★ 2026-09-05 — 두 버튼 줄을 **가로로 나란히** 뒀다. 세로로 쌓여
        #   있으니 어느 것이 축이고 어느 것이 기준인지 라벨 없이는 몰랐다.
        #   라벨을 살리고(collapsed 를 풀고) 한 줄에 둔다.
        BASES = ["납기 준수율", "퍼널 전환율"]
        c_dim, c_basis = st.columns([1, 1])
        with c_dim:
            # 축 목록은 config.DIMS 가 정본이다. 화면에 박아 두면 축을 늘릴 때
            # 고칠 곳이 둘이 되고, 반드시 한쪽만 고치는 날이 온다.
            dim = st.segmented_control(
                "쪼갤 축", C.DIMS,
                default=ui.url_state("dim", C.DIMS[0], C.DIMS), key="dim")
            if dim is None:
                dim = C.DIMS[0]
        with c_basis:
            basis = st.segmented_control(
                "볼 값", BASES,
                default=ui.url_state("basis", BASES[0], BASES), key="basis")
            if basis is None:      # 선택 해제 시 None 이 온다
                basis = "납기 준수율"

        # ★ 2026-09-05 — **고르라고 해놓고 설명이 없었다.**
        #   물음: *"납기 준수율과 퍼널 전환율은 뭘 뜻하는건지 모르겠어"*
        #   고르는 사람이 두 선택지의 뜻을 모르면 그 토글은 없는 것과 같다.
        #   버튼 바로 밑에 **한 줄로** 둔다 — 눌러야 나오는 곳에 두면 안 본다.
        st.caption(
            "　**납기 준수율** = 약속한 날짜까지 나갔는가 (결과)　·　"
            "**퍼널 전환율** = 다음 단계로 넘어갔는가 (과정)")

        if basis == "납기 준수율":
            g = ui.guard(M.metric_by, t, dim)
            rate, denom, hit = "준수율", "분모", "준수"
            what = "납기 준수율"
        else:
            i = st.selectbox(
                "구간", range(len(f) - 1),
                format_func=lambda i: f"{f.label.iloc[i]} → {f.label.iloc[i+1]}",
                index=min(bi - 1, len(f) - 2))
            g = ui.guard(M.funnel_by, t, dim,
                         f.step.iloc[i], f.step.iloc[i + 1])
            rate, denom, hit = "전환율", "도달", "전환"
            what = "전환율"

        ui.push_url(dim=dim, basis=basis)

        if g is not None and len(g):
            st.plotly_chart(charts.device_compare(g, rate, denom, hit),
                            width="stretch",
                            config={"displayModeBar": False})
            # ★ 이름을 best/worst 로 둔다. 전에는 hi/lo 였는데 위쪽 기간 필터의
            #   lo, hi 를 덮어써서 기간 슬라이스가 DataFrame 행을 받아 터졌다
            #   (2026-09-03). 같은 함수 안에서 짧은 이름을 재사용하지 않는다.
            best = g.loc[g[rate].idxmax()]
            worst = g.loc[g[rate].idxmin()]
            if best[g.columns[0]] != worst[g.columns[0]]:
                gap = (best[rate] - worst[rate]) * 100
                ui.callout(
                    f"<b>{worst[g.columns[0]]}</b>이(가) 전체의 "
                    f"<b>{worst.비중*100:.1f}%</b>인데 {what}은 "
                    f"<b>{worst[rate]*100:.1f}%</b>로 "
                    f"{best[g.columns[0]]}({best[rate]*100:.1f}%)보다 "
                    f"<b>{gap:.1f}%p 낮습니다.</b>")
                # ★ 쪼개면 표본이 준다. 격차를 보여준 바로 옆에 이 말을 붙인다 —
                #   7주차에 13.2%p(p=0.046) 였던 차종 격차가 표본을 48배로 늘리니
                #   0.8%p(p=0.494)로 사라졌다. 격차만 보이고 표본이 안 보이면
                #   회의실에서 인용되는 것은 격차뿐이다.
                if g.표본부족.any():
                    ui.callout(
                        f"칸 {int(g.표본부족.sum())}개가 최소 표본"
                        f"({C.MIN_SAMPLE}건) 미만입니다. 그 칸의 {what}은 "
                        f"참고용으로만 보십시오.", "warn")
                elif gap < 1.0:
                    # ★ 퍼널로 골랐을 때는 **왜 안 갈리는지**까지 말한다.
                    #   "격차가 작다"만 보면 데이터가 부실한 줄 안다.
                    #   실제로는 우리 도메인의 성질이다 — 발주는 취소되지
                    #   않으니 결국 다 만들어지고, 갈리는 것은 *언제* 나가느냐다.
                    더 = ("<br>같은 축을 <b>납기 준수율</b>로 보면 갈립니다 — "
                          "발주는 취소되지 않아 결국 다 만들어지므로 "
                          "<b>통과율은 어느 축으로 쪼개도 비슷</b>하고, "
                          "갈리는 것은 <b>언제 나가느냐</b>입니다."
                          if basis == "퍼널 전환율" else "")
                    ui.callout(
                        f"격차가 <b>{gap:.1f}%p</b>입니다. 이 정도 차이는 "
                        f"표본을 늘리면 사라질 수 있습니다 — 손을 쓰기 전에 "
                        f"같은 축으로 한 기간 더 보십시오.{더}", "info")


    # ── 기간별 전후 비교 ──────────────────────────────────────────
    seg = M.monthly(t).loc[lo:hi]
    if len(seg) >= 2:
        ui.section("기간별 전후 비교", "수준이 아니라 변화를 본다")
        names = [c for c in seg.columns if c != "분모"]

        # ★ 2026-09-04 — 끝값이 비어 있으면 **그 지표는 카드를 안 만든다.**
        #   긴급품·지연 출하는 납기 뒤 최대 24일에 걸쳐 확정되므로, 데이터 끝
        #   가까운 달은 monthly() 가 값을 아예 안 남긴다(DUE_SETTLE_DAYS).
        #   여기서 NaN 을 0으로 채우거나 앞 값으로 끌어오면, **관찰이 덜 된 것이
        #   개선으로 보인다.** 실제로 8월 지연 출하율이 4.2 → 2.51 로 보였다.
        shown, hidden, short = [], [], []
        for name in names:
            v = seg[name].dropna()
            if len(v) < 2:
                hidden.append(name)
                continue
            shown.append(name)
            # 끝 달이 남들보다 이르면 **구간이 짧은 것**이다. 캡션에 월이 찍히긴
            # 하지만 왜 다른지는 안 보인다 — 안 적으면 "7월에 멈춘 지표"로 읽는다.
            if v.index[-1] != seg.index[-1]:
                short.append(f"{name}({v.index[-1]}까지)")

        for col, name in zip(st.columns(max(len(shown), 1)), shown):
            v = seg[name].dropna()
            first, last = v.iloc[0], v.iloc[-1]
            # ★ 낮을수록 좋은 지표는 색이 반대다. 안 뒤집으면 불량률이 올라간 것을
            #   초록으로 칠한다 — 판정을 거꾸로 전달하게 된다.
            inverse = name in {"불량률", "긴급품 비율", "지연 출하율"}
            col.metric(name, f"{last:.2f}", f"{last - first:+.2f}",
                       delta_color="inverse" if inverse else "normal",
                       border=True)
            # 지표마다 **비교 구간이 다를 수 있다.** 확정 안 된 달을 뺐기 때문이다.
            # 한 줄로 뭉뚱그리면 다른 구간끼리 비교한 것을 같은 구간으로 읽는다.
            col.caption(f"　{v.index[0]} {first:.2f} → {v.index[-1]} {last:.2f}")

        # ★ 2026-09-05 — 전에는 안내가 둘이었다(짧은 구간 / 아예 뺌).
        #   사유가 같은데 문장을 두 번 읽히고 있었다 — 조건만 다르다.
        #   **같은 이유를 두 번 말하지 않는다.** 무엇이 어떻게 됐는지만 갈라 쓴다.
        if short or hidden:
            무엇 = " · ".join(
                [f"<b>{x}</b>(구간이 짧음)" for x in short]
                + [f"<b>{x}</b>(비교 못 함)" for x in hidden])
            ui.callout(
                f"{무엇} — 납기를 넘긴 수주가 <b>납기 뒤 최대 24일</b>에 걸쳐 "
                f"나가므로 끝 달은 아직 확정되지 않았습니다"
                f"(관찰 {C.DUE_SETTLE_DAYS}일 필요). 그대로 채우면 "
                f"<b>관찰이 덜 된 것이 개선으로 보입니다.</b>",
                "warn" if hidden else "info")
        st.caption("　△ 는 각 지표의 **첫 달 → 마지막 달 차이**입니다. "
                   "낮을수록 좋은 지표는 색이 반대로 붙습니다.")


@st.fragment
def _ret_tab():

    ui.section("유지 퍼널 — 납기를 못 지킨 것을 둘로 가른다",
               "같은 '못 지킴'이라도 종류가 다르고, 대응도 다르다")

    # ★ 2026-09-05 — 물음: *"유지퍼널은 뭐야?"*
    #   설명은 아래에 잔뜩 있었는데 **"이 화면을 왜 보는가"가 없었다.**
    #   단계 이름과 주의사항부터 읽으면 무엇을 얻는 화면인지 끝까지 안 나온다.
    #   답을 맨 앞에 놓는다.
    ui.callout(
        "지표 카드의 <b>납기 준수율</b>은 결과 하나만 줍니다 — 못 지킨 것이 "
        "몇 %인지는 알려주지만 <b>왜 그랬는지</b>는 말하지 않습니다. "
        "이 화면은 그 '못 지킴'을 <b>두 종류로 가릅니다</b>:<br>"
        "① <b>만들어졌는데 늦은 것</b> — 검사까지 갔고 미납확인이 찍혔습니다 · "
        "② <b>아직 만들어지지도 않은 것</b> — 공정 중에 멈춰 검사까지 못 갔습니다.<br>"
        "①은 <i>왜 밀렸는가</i>를, ②는 <i>어디서 멈췄는가</i>를 봐야 합니다. "
        "<b>같은 '납기 미준수'인데 물어볼 것이 다릅니다.</b>", "info")
    if not C.RETENTION_STEPS:
        st.caption("config.RETENTION_STEPS 가 비어 있습니다. "
                   "7주차에 정한 유지의 정의를 옮기면 여기에 그려집니다.")
    rf = ui.guard(M.retention_funnel, t)
    if rf is not None and len(rf):
        if "is_bottleneck" not in rf.columns:
            rf = rf.assign(is_bottleneck=False)
        ch = M.urgent_stats(t)
        c1, c2 = st.columns([1.15, 1])
        with c1:
            st.plotly_chart(charts.funnel_bars(rf), width="stretch",
                            config={"displayModeBar": False})
            for _, r in rf.iterrows():
                st.caption(f"　**{r.label}** — {r.desc}")
            # ★ 이 퍼널이 주는 것은 끝값이 아니라 **손실이 어디서 나는가**다.
            #   끝값(91.1%)은 납기 준수율과 같다 — 정의상 그렇게 될 수밖에 없다.
            #   값어치는 그 91.1%를 두 손실로 쪼갠다는 데 있다.
            a, b, c = (int(x) for x in rf.n)
            # ★ 이 화면의 **본론**이라 캡션(작은 회색)에 묻어 두지 않는다.
            #   2026-09-05 이전에는 주의사항과 같은 크기로 있어서, 읽는 사람이
            #   무엇이 결론이고 무엇이 단서인지 구분할 수 없었다.
            # ⚠️ 색을 **값으로 정한다.** 처음엔 ①에 빨강 ②에 주황을 박았는데
            #    test_guards 8절이 잡았다 — 둘 중 어느 쪽도 임계값을 넘은 것이
            #    아니라 그냥 두 종류다. **판정이 아닌 곳에 판정 색을 쓰면
            #    안 넘었는데 넘은 것처럼 읽힌다.**
            #    대신 **큰 쪽을 진하게** 한다. 그건 값으로 정해지는 것이고
            #    "어디부터 볼 것인가"라는 뜻이 있다.
            # ⚠️ 2026-09-05 정정 — ②를 *늦게 나간 것*이라고 적었다가 **거짓이었다.**
            #    실측하니 2,214건 전부가 검사 미도달 + 전부 미출하다.
            #    늦게 나간 것이 아니라 **아직 안 나간** 것이다.
            #    자동 문장이 거짓말한다는 그 자리를 내가 손으로 만든 셈이다.
            #    → test_metrics 8-7 절이 두 손실의 정체를 붙들고 있다.
            손실 = [("① 만들어졌는데 늦음", a - b, "검사까지 감 · 미납확인 찍힘"),
                    ("② 아직 안 만들어짐", b - c, "공정 중 멈춤 · 검사 못 감")]
            큰쪽 = max(x[1] for x in 손실)
            칸 = "".join(
                f'<div><div style="font-size:22px;font-weight:800;'
                f'color:{C.BRAND["primary"] if n == 큰쪽 else C.BRAND["muted"]}">'
                f'{n:,}{C.UNIT}</div>'
                f'<div style="font-size:12px;color:{C.BRAND["muted"]}">'
                f'{label} ({n/a*100:.1f}%)<br>{why}</div></div>'
                for label, n, why in 손실)
            st.markdown(
                f'<div class="card tight" style="margin-top:10px">'
                f'<div style="font-size:12px;color:{C.BRAND["muted"]};'
                f'margin-bottom:6px">못 지킨 {a-c:,}{C.UNIT}의 정체 — '
                f'진한 쪽이 큽니다</div>'
                f'<div style="display:flex;gap:22px;flex-wrap:wrap">{칸}</div>'
                f'</div>', unsafe_allow_html=True)
            st.caption(f"　끝값 {c/a*100:.2f}% 는 지표 카드의 납기 준수율과 **거의 같지만 "
                       f"같지 않습니다** — 여기는 완주 코호트만 세고 카드는 납기 도래 "
                       f"전체를 셉니다. **끝값을 보러 오는 화면이 아닙니다.**")
        with c2:
            st.markdown(ui.kpi_card(
                "긴급품", f"{ch['긴급률']:.1f}%",
                f"{ch['긴급건']:,}건", M.status_of("긴급품 비율", ch["긴급률"])),
                unsafe_allow_html=True)
            # ★ 이름이 같고 뜻이 다른 것을 그냥 두면 읽는 사람이 잘못 읽는다.
            ui.callout(
                "여기서 <b>유지</b>는 사람이 남는 것이 아니라 "
                "<b>수주가 출하까지 살아남는 것</b>입니다. 우리 수주는 출하되면 "
                "거기서 끝나므로, 통신사의 유지율과 같은 말로 읽으면 안 됩니다.", "info")
            ui.callout(
                f"유지는 <b>관측 기간이 대상마다 다릅니다.</b> 먼저 들어온 수주는 오래 "
                f"관측됐고 나중에 들어온 수주는 짧게 관측됐습니다. 그래서 완주 코호트"
                f"({C.COHORT_DAYS}일)만 셌습니다 — 안 자르면 긴급품 비율이 "
                f"{ch['긴급률_코호트미적용']:.1f}%로 나오는데 그 차이는 "
                f"<b>아직 납기가 오지 않은 수주</b>가 섞인 결과입니다. "
                f"<b>누적값으로 비교하면 기간의 그림자를 효과로 착각합니다.</b>")



@st.fragment
def _exp_tab():
    """실험 — 믿을 수 있는지 먼저, 그 다음 지표."""
    ui.section("실험 결과", "믿을 수 있는지 먼저 보고, 그 다음에 지표를 본다")
    res = ui.guard(M.experiment_results, t)
    if res is not None and not res:
        st.caption("실험이 없습니다. 전후 비교로 대신하되 "
                   "**인과를 주장할 수 없다**를 카드에 남기십시오.")
    for r in (res or []):
        cls = r["color"]
        head = (f'<div class="exp {cls}">'
                f'<div style="display:flex;align-items:flex-start;gap:12px">'
                f'<div style="flex:1"><div class="id">{r["id"]}</div>'
                f'<div class="nm">{r["name"]}</div>'
                f'<div class="hy">{r["hypothesis"]}</div></div>'
                f'<div>{ui.badge(cls, r["verdict"])}</div></div>')

        if r["verdict"] == "무효":
            # 못 믿을 실험의 숫자는 보여주지 않는다.
            # 계산해 놓고 숨기는 것이 아니라 계산 자체를 하지 않았다.
            head += (f'<div class="blocked"><b>✕ 지표를 표시하지 않습니다</b><br>'
                     f'{r["reason"]}</div>')
            st.markdown(head + "</div>", unsafe_allow_html=True)
            ui.verdict_steps(r)
            # ★ 근거 전부는 모달로 (Day3 프롬프트 13). 카드에 다 적으면 카드가
            #   사유로 덮여서 아무도 안 읽고, 요약만 두면 확인할 길이 없어
            #   "왜 못 믿는지"를 못 본 사람이 규칙을 우회하려 든다.
            ui.blocked_evidence(r)
            continue

        if "rc" not in r:
            head += (f'<div style="margin-top:12px;font-size:13px;color:#64748b">'
                     f'{r.get("reason", "")}</div>')
            st.markdown(head + "</div>", unsafe_allow_html=True)
            ui.verdict_steps(r)
            continue

        head += (f'<div style="margin-top:14px;display:flex;gap:28px;'
                 f'align-items:baseline;flex-wrap:wrap">'
                 f'<div><div style="font-size:11px;color:#64748b">{r["primary"]}</div>'
                 f'<div class="mv">{r["rc"]*100:.2f}% → {r["rt"]*100:.2f}%</div></div>'
                 f'<div><div style="font-size:11px;color:#64748b">상대 효과</div>'
                 f'<div class="mv">{r["lift"]*100:+.1f}%</div></div>'
                 f'<div><div style="font-size:11px;color:#64748b">p값</div>'
                 f'<div class="mv">{r["p"]:.4f}</div></div>'
                 f'<div><div style="font-size:11px;color:#64748b">표본</div>'
                 f'<div style="font-size:13px;color:#475569" class="num">'
                 f'{r["nc"]:,} / {r["nt"]:,}</div></div></div>')
        st.markdown(head + "</div>", unsafe_allow_html=True)

        c1, c2 = st.columns([1, 1.1])
        with c1:
            st.caption("효과 크기와 95% 신뢰구간 (0을 지나면 유의하지 않음)")
            st.plotly_chart(charts.forest(r), width="stretch",
                            config={"displayModeBar": False}, key=f"fr_{r['id']}")
        with c2:
            if r.get("guard"):
                gd = r["guard"]
                bad = gd["delta"] < -0.03
                st.markdown(
                    f'<div class="card tight" style="border-color:'
                    f'{C.COLORS["warn"] if bad else C.BRAND["line"]}">'
                    f'<div style="font-size:11px;color:#64748b">가드레일 · {gd["name"]}</div>'
                    f'<div style="font-size:20px;font-weight:700;margin-top:4px" class="num">'
                    f'{gd["control"]*100:.1f}% → {gd["treatment"]*100:.1f}% '
                    f'<span style="color:{C.COLORS["warn"] if bad else C.COLORS["ok"]}">'
                    f'({gd["delta"]*100:+.1f}%p)</span></div>'
                    + ('<div class="note">주지표는 개선됐지만 가드레일이 무너졌습니다.</div>'
                       if bad else
                       '<div style="font-size:12px;color:#64748b;margin-top:6px">'
                       '이상 없음</div>')
                    + '</div>', unsafe_allow_html=True)
            elif r.get("reason"):
                st.markdown(f'<div class="card tight">'
                            f'<div style="font-size:13px;color:#64748b">{r["reason"]}</div>'
                            f'</div>', unsafe_allow_html=True)

        ui.verdict_steps(r)

        # 기간을 쪼개야 드러나는 것 — 초기 효과가 남아 있는가
        w = M.weekly_effect(r, r["start"])
        if not w.empty and len(w) >= 3:
            with st.expander("기간을 쪼개서 보기 — 효과가 유지되는가"):
                st.plotly_chart(charts.effect_decay(w), width="stretch",
                                config={"displayModeBar": False})
                ui.callout(
                    f"전체 평균은 <b>{r['lift']*100:+.1f}%</b>인데 "
                    f"초반 <b>{w.lift.iloc[0]*100:+.0f}%</b>에서 "
                    f"후반 <b>{w.lift.iloc[-1]*100:+.0f}%</b>로 갑니다. "
                    f"기간 평균만 보면 안 보이는 것입니다.")

        # 그때 멈췄다면 무엇을 봤을까
        pc = M.peeking_curve(r, r["start"])
        if not pc.empty and len(pc) >= 3:
            with st.expander("만약 여기서 멈췄다면? — 조기 중단 시뮬레이터"):
                cuts = list(pc.cut.astype(int))
                sel = st.select_slider("실험 종료일", options=cuts, value=cuts[0],
                                       key=f"peek_{r['id']}")
                row = pc[pc.cut == sel].iloc[0]
                a, b = st.columns([1, 1.4])
                with a:
                    lv = "warn" if row.sig else "none"
                    st.markdown(
                        ui.kpi_card(f"{sel}일차에 종료했다면", f"{row.lift*100:+.1f}%",
                                    "유의 — 성공으로 보고" if row.sig
                                    else "유의하지 않음", lv),
                        unsafe_allow_html=True)
                    st.caption(f"p = {row.p:.3f}")
                with b:
                    st.plotly_chart(charts.peeking(pc, r["lift"]), width="stretch",
                                    config={"displayModeBar": False})
                ui.callout("종료 시점은 실험을 **시작하기 전에** 정해야 합니다.")



@st.fragment
def _cost_tab():
    """유효 원가 — 싸게 만든 것이 실제로 싼 것이 아니다."""
    ui.section(f"{C.EFFICIENCY_DIM}별 유효 원가", "싸게 만든 것이 실제로 싼 것이 아니다")
    ce = ui.guard(M.channel_efficiency, t)
    if ce is not None and len(ce):
        ev = M.efficiency_verdict(ce)
        c1, c2 = st.columns([1.3, 1])
        with c1:
            st.plotly_chart(charts.cac_compare(ce), width="stretch",
                            config={"displayModeBar": False})
        with c2:
            naive = list(ce.sort_values("원가")["구분"].astype(str))
            real = list(ce.sort_values("유효원가")["구분"].astype(str))
            flipped = ev["역전"] > 0
            st.markdown(
                f'<div class="card tight">'
                f'<div style="font-size:12px;color:#64748b">단순 원가 순위</div>'
                f'<div style="font-size:14px;margin:4px 0 12px">{" < ".join(naive)}</div>'
                f'<div style="font-size:12px;color:#64748b">불량률 반영 순위</div>'
                f'<div style="font-size:14px;font-weight:700;color:'
                f'{C.COLORS["block"] if flipped else C.COLORS["ok"]}">'
                f'{" < ".join(real)}</div></div>', unsafe_allow_html=True)
            # ★ 안 뒤집혔으면 **그것도 결과다.** 다만 "차이 없음"으로 끝내지 않고
            #   뒤집히려면 무엇이 얼마나 커야 하는지를 같이 낸다 — 그래야 읽는 사람이
            #   다음에 실데이터를 넣었을 때 스스로 판정할 수 있다.
            if flipped:
                ui.callout(f"순위가 <b>{ev['역전']}칸</b>에서 뒤집힙니다. "
                           f"단순 원가로 고르면 실제로는 더 비싼 쪽을 고르게 됩니다.")
            else:
                ui.callout(
                    f"이 데이터에서는 <b>순위가 뒤집히지 않습니다.</b> "
                    f"뒤집히려면 불량 보정폭이 원가 격차보다 커야 하는데, "
                    f"보정폭 <b>{ev['보정폭']:.1f}원</b> vs 원가 격차 "
                    f"<b>{ev['원가격차']:.1f}원</b>입니다 "
                    f"({C.EFFICIENCY_DIM}별 불량률 폭 {ev['불량률폭']:.2f}%p). "
                    f"<b>없음도 결과입니다</b> — 리포트 7장에 그대로 실립니다.", "info")
            st.caption("인건·가공은 매출 대비 총액 배부한 **가정값**입니다. "
                       "리포트에 쓸 때 '가정값 기반'을 남기십시오.")



# ── 화면을 셋으로 묶는다 (2026-09-05) ─────────────────────────────
# ★ 전에는 전부 세로로 쌓여 **한 페이지가 30,000px**(화면 30개 분량)이었다.
#   실험 3건이 15,700px 부터 시작했고 유효 원가는 25,800px 아래라
#   **끝까지 내려가는 사람이 없었다.** 안 보이는 것은 없는 것과 같다.
#
#   퍼널 둘은 안쪽 탭으로 그대로 두고, 바깥에 큰 탭 셋을 둔다 —
#   퍼널(어디서 막히나) · 실험(무엇을 바꿔봤나) · 원가(얼마가 드나).
#   물음이 다르면 화면도 나눈다.
MAIN = st.tabs(["📉  퍼널",  "🧪  실험",  "💰  유효 원가"])

with MAIN[0]:
    tab_acq, tab_ret = st.tabs(["획득 퍼널", "유지 퍼널"])
    with tab_acq:
        _acq_tab()
    with tab_ret:
        _ret_tab()

with MAIN[1]:
    _exp_tab()

with MAIN[2]:
    _cost_tab()