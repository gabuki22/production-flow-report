# -*- coding: utf-8 -*-
"""제안서 — 주제를 골라 결재 문서를 만드는 화면.

리포트와 **다른 문서**다. 리포트는 *"숫자가 맞는가"* 를 보여주고,
제안서는 *"무엇을 결정해 달라"* 고 말한다. 읽는 사람도 목적도 다르므로
2026-09-10 에 리포트의 임시 탭에서 떼어 독립 메뉴로 옮겼다.

★ **거르는 자리는 조립기 한 곳뿐이다**(`report/proposal.build`).
  화면에서 또 거르면 두 곳이 갈리고, 갈린 뒤에는 어느 쪽이 맞는지 알 수 없다.
"""
from datetime import datetime          # 파일 이름에 붙일 시각 — 표시 전용

import streamlit as st

from core import config as C, gates, load, metrics as M
from report import proposal
from viz import ui

st.set_page_config(page_title="제안서", page_icon="📝", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("proposal")

if "run" not in st.session_state:
    st.session_state.run = None

# 사람이 쓰는 절은 **디스크에서 되살린다.** 세션에만 두면 새로고침에 사라진다.
# ⚠️ `load_human` 은 데이터셋이 다르면 안 불러온다 — 숫자가 달라진 문서에
#    옛 글이 붙으면 사실과 다른 문서가 된다.
if "proposal_human" not in st.session_state:
    st.session_state.proposal_human, _at = gates.load_human("proposal")

ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()

cards = proposal.parse_cards()

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:4px">'
            '제안서</div>'
            '<div style="font-size:13px;color:#64748b;margin-bottom:18px">'
            '주제를 고르면 그 주제의 결재 문서가 만들어집니다. '
            '읽은 사람이 승인·조건부 승인·보류 중 하나를 정할 수 있어야 합니다.'
            '</div>', unsafe_allow_html=True)

if cards.get("없음"):
    ui.callout(f"제안 카드가 아직 없습니다. <code>{cards['path']}</code> 를 "
               f"먼저 만드십시오 — <code>/제안</code> 으로 뽑습니다.")
    st.stop()

# ── ① 주제 고르기 ────────────────────────────────────────────────
topics = M.proposal_topics(t)
살아있는 = [c for c in topics if not c["기각사유"]]
기각된 = [c for c in topics if c["기각사유"]]


def _label(c: dict) -> str:
    """라벨에 **규모(연 N건)** 를 같이 쓴다. 기각된 것은 그렇다고 적는다."""
    n = c["규모_연간건수"]
    size = f"연 {n:,.0f}건" if n >= 1 else "규모 미산정"
    return (f'{c["제목"]}  —  {size}'
            if not c["기각사유"] else f'{c["제목"]}  —  (차이 없음)')


ALL = "전체"
# ★ 추진으로 정한 카드의 주제를 **맨 위에** 둔다 (2026-09-12 기쁨 지시).
#   값을 박지 않는다 — 카드 「분류」가 "할 것"인 제목에 주제의 축·값("차종 V6")이
#   들어 있으면 그 주제가 앞이다. 추진 카드가 바뀌면 순서도 따라 바뀐다.
_할것 = [c["title"] for c in proposal.parse_cards()["cards"] if c.get("분류") == "할 것"]
def _pinned(c: dict) -> bool:
    head = c["제목"].split(" 의 ")[0]          # "차종 V6 의 …" → "차종 V6"
    return " 의 " in c["제목"] and any(head in t for t in _할것)
살아있는 = sorted(살아있는, key=lambda c: not _pinned(c))   # 안정 정렬 — 나머지 순서는 그대로
topics = 살아있는 + 기각된
options = [ALL] + [_label(c) for c in 살아있는 + 기각된]
picked = st.selectbox("주제", options, index=0)

st.caption(f"후보 {len(topics)}개 — 쓸 만한 것 {len(살아있는)} · "
           f"본 뒤 뺀 것 {len(기각된)}. "
           f"**뺀 것도 목록에 남깁니다** — 지우면 *안 봤다* 와 "
           f"*보고 아니었다* 가 구분되지 않습니다.")

if picked == ALL:
    st.divider()
    ui.section("주제 후보")
    st.dataframe(
        [{"주제": c["제목"], "연간 건수": round(c["규모_연간건수"]),
          "근거": c["근거축"], "뺀 이유": c["기각사유"] or ""}
         for c in topics],
        width="stretch", hide_index=True)
    st.caption("　하나를 골라야 문서가 만들어집니다.")
    st.stop()

topic = next(c for c in 살아있는 + 기각된 if _label(c) == picked)

# ── ② 근거 요약 한 줄 ────────────────────────────────────────────
ev = M.topic_evidence(t, topic)
st.divider()
st.markdown(f'<div class="card tight"><b>{topic["한줄"]}</b></div>',
            unsafe_allow_html=True)

secs = proposal.build(topic, ev, cards, st.session_state.proposal_human)

if not secs:
    # 빈 화면 대신 **왜 없는지** 적는다.
    ui.callout("이 주제로는 문서를 만들 수 없습니다 — "
               f"근거가 되는 값이 없습니다. {topic.get('기각사유') or ''}")
    st.stop()

# ── ③ 절별 미리보기 ─────────────────────────────────────────────
st.divider()
ui.section("절")

만든절 = {s["key"] for s in secs}
안만든 = [s for s in C.PROPOSAL_SECTIONS if s["key"] not in 만든절]

nav, body = st.columns([1, 3])
with nav:
    titles = [s["제목"] for s in secs]
    pick = st.radio("절 목차", titles, label_visibility="collapsed")
    st.divider()
    # ⚠️ 진척은 **사람이 쓴 원문**으로 센다. 요청 절은 자동 문장이 붙어 있어
    #    `문장` 으로 세면 안 썼는데도 다 쓴 것으로 보인다.
    done = sum(1 for s in secs if s["kind"] == "human" and s["사람"])
    need = sum(1 for s in secs if s["kind"] == "human")
    st.caption(f"사람 작성 {done}/{need}절")
    st.progress(done / need if need else 0)
    if 안만든:
        # ★ **왜 없는지**를 보여준다. 조용히 빠지면 안 만든 것과 못 만든 것이
        #   구분되지 않는다.
        st.caption("이 주제에 없는 절 — " +
                   " · ".join(s["제목"] for s in 안만든))

sec = next(s for s in secs if s["제목"] == pick)

with body:
    kind = "자동 생성" if sec["kind"] == "auto" else "사람 작성"
    lvl = "ok" if (sec["kind"] == "auto" or sec["사람"]) else "warn"
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:2px">'
        f'<div style="font-size:19px;font-weight:700">{sec["제목"]}</div>'
        f'{ui.badge(lvl, kind)}</div>'
        f'<div style="font-size:12.5px;color:#64748b;margin-bottom:12px">'
        f'{sec["질문"]}</div>', unsafe_allow_html=True)

    if sec["kind"] == "auto":
        st.markdown('<div class="card">'
                    + "".join(f'<p style="margin:0 0 8px">{x}</p>'
                              for x in sec["문장"])
                    + '</div>', unsafe_allow_html=True)
        if sec["차트"]:
            st.markdown(sec["차트"], unsafe_allow_html=True)
        bad = proposal.check_phrasing(" ".join(sec["문장"]))
        if bad:
            ui.callout(f"자동 생성 문장에 인과를 단정하는 표현이 있습니다: "
                       f"<b>{', '.join(bad)}</b>.")
        else:
            st.caption("✓ 인과 단정 표현 검사 통과")
    else:
        # ★ 요청 절에는 **자동으로 붙는 재료**가 있다 — 규모 · 선택지 셋 ·
        #   미뤘을 때 쌓이는 양. 사람이 쓸 칸과 한 상자에 넣으면 어디까지가
        #   자기 말인지 모른다. 위에 따로 보여주고, 아래에서 쓰게 한다.
        자동 = [x for x in sec["문장"] if x != sec["사람"]]
        if 자동:
            st.markdown('<div class="card">'
                        + "".join(f'<p style="margin:0 0 8px">{x}</p>'
                                  for x in 자동)
                        + '</div>', unsafe_allow_html=True)
            st.caption("　위 문장은 데이터에서 자동으로 붙습니다. "
                       "**아래에 쓴 문장이 문서의 마지막 줄**이 됩니다.")

        typed = st.text_area(
            sec["제목"], value=sec["사람"],
            height=200, key=f"h_{sec['key']}", label_visibility="collapsed",
            placeholder=("무엇 때문에 틀릴 수 있는지, 언제 접을지 적으십시오."
                         if sec["key"] == "위험" else
                         "무엇을 결정해 달라고 할지 적으십시오. "
                         "승인·결정·판단 중 한 낱말이 들어가야 합니다."))

        # ★ 결정 동사가 없으면 **경고만** 한다. 저장 버튼을 잠그지 않는다 —
        #   사람이 쓴 문장 때문에 저장이 막히면 사람이 문장을 안 쓰게 된다.
        if sec["key"] == "요청":
            d = proposal.decision_ask(secs)
            if not d["있음"]:
                ui.callout(f'{d["사유"]}. 읽은 사람이 무엇을 해야 하는지 '
                           f'모른 채 문서를 닫게 됩니다. '
                           f'<b>저장은 그대로 됩니다.</b>')
            else:
                st.caption("✓ 결정을 요구하는 문장으로 끝납니다")
        c1, c2 = st.columns([1, 4])
        with c1:
            if st.button("저장", type="primary", key=f"save_{sec['key']}"):
                st.session_state.proposal_human[sec["key"]] = typed
                gates.save_human(st.session_state.proposal_human, "proposal")
                st.toast("저장했습니다 · 파일로 남겼습니다", icon="💾")
                st.rerun()
        with c2:
            st.caption("　다른 절로 넘어가기 전에 저장하십시오 — "
                       "안 누르면 쓰던 글이 사라집니다")
        _, at = gates.load_human("proposal")
        if at:
            st.caption(f"　마지막 저장 {at.replace('T', ' ')} · "
                       f"서버를 다시 켜도 남습니다")

# ── ④ 내려받기 ──────────────────────────────────────────────────
st.divider()
ui.section("내보내기 전 확인")

# ★ **고치지 않는다. 세어서 보여준다.** 내보내기 **앞**에 둔다 — 뒤에 두면
#   내려받고 나서 보게 되고, 그때는 이미 나간 뒤다.
checks = proposal.self_check(secs, topic)
걸린 = [c for c in checks if not c["통과"]]
for col, c in zip(st.columns(len(checks)), checks):
    with col:
        st.markdown(
            f'<div class="card tight" style="text-align:center">'
            f'<div style="font-size:11px;color:#64748b">{c["항목"]}</div>'
            f'<div style="font-size:20px;font-weight:800;color:'
            f'{C.COLORS["ok"] if c["통과"] else C.COLORS["block"]}">'
            f'{c["값"]}</div>'
            f'<div style="font-size:10.5px;color:#94a3b8">기준 {c["기준"]}</div>'
            f'</div>', unsafe_allow_html=True)

if 걸린:
    ui.callout("아래는 <b>고치지 않고 알리기만</b> 합니다 — "
               "무엇을 고칠지는 사람이 정합니다.<br>"
               + "<br>".join(f'· <b>{c["항목"]}</b> — {c["자리"]}'
                             for c in 걸린))
else:
    st.caption("　여섯 항목 모두 기준 안입니다")

st.divider()
ui.section("내보내기")
st.caption("HTML — 단일 파일 · 외부 CSS·이미지·CDN 없음 · A4 인쇄 기준")
st.download_button(
    "제안서.html 내려받기",
    data=proposal.to_html(secs, topic).encode("utf-8"),
    file_name=f"제안서_{datetime.now():%Y%m%d_%H%M}.html",
    mime="text/html", type="primary")
