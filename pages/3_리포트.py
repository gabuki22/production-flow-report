# -*- coding: utf-8 -*-
"""리포트 — 남에게 보내는 문서.

8장 중 5장은 자동으로 쓰고, **3장(배경·해석·제안)은 사람이 쓴다.**
자동 생성 문장은 인과를 단정하지 않는지 스스로 검사한다.
"""
from datetime import datetime          # 파일 이름에 붙일 시각 — 표시 전용

import streamlit as st

from core import config as C, gates, load, metrics as M
from report import sections as S, to_pdf
from viz import pdf_charts, ui

st.set_page_config(page_title="리포트", page_icon="📄", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("report")

if "run" not in st.session_state:
    st.session_state.run = None
if "human" not in st.session_state:
    # ★ 2026-09-05 — **디스크에서 되살린다.**
    #   전에는 빈 dict 로 시작해서, 서버를 다시 켜면 사람이 쓴 글이
    #   통째로 사라졌다(그날 쓴 글이 실제로 날아갔다).
    #   이 앱에서 가장 값진 것이 사람이 쓴 장인데 가장 약하게 담겨 있었다.
    st.session_state.human, st.session_state.human_saved_at = gates.load_human()
ui.context_bar(st.session_state.run)

t = ui.guard(load.load_all)
if t is None:
    st.stop()
secs = S.build(t, st.session_state.human)

# ★ 한계를 표에서 고쳤으면 그것을 쓴다 (Day4 프롬프트 11).
#   화면과 PDF 가 갈리면 안 되므로 **여기 한 곳에서** 갈아끼운다.
#   PDF·이메일 초안·발송 전 점검이 전부 이 secs 를 본다.
if st.session_state.get("limit_rows"):
    secs = [S.limits_from_rows(st.session_state.limit_rows)
            if s["title"].startswith("7.") else s for s in secs]

# ★ 리포트 차트에 쓸 분해 축. 화면에서 고른 축이 아니라 **문서에 실릴 축**이라
#   config.DIMS 의 첫 번째로 고정한다. 매번 다른 축이 실리면 지난 문서와 비교가 안 된다.
DIM = C.DIMS[0]

st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:16px">'
            '리포트</div>', unsafe_allow_html=True)

nav, body = st.columns([1, 3.4])

with nav:
    titles = [s["title"] for s in secs]
    pick = st.radio("목차", titles, label_visibility="collapsed")
    st.divider()
    done = sum(1 for s in secs if s["kind"] == "human" and s["body"].strip())
    need = sum(1 for s in secs if s["kind"] == "human")
    left = sum(1 for s in secs if s["kind"] == "todo")
    st.caption(f"사람 작성 {done}/{need}장")
    st.progress(done / need if need else 0)
    if left:
        st.caption(f"아직 안 만든 장 {left}개")

sec = next(s for s in secs if s["title"] == pick)

with body:
    kind = {"auto": "자동 생성", "human": "사람 작성",
            "todo": "아직 안 만듦"}[sec["kind"]]
    lvl = {"auto": "ok", "todo": "none"}.get(
        sec["kind"], "ok" if sec["body"].strip() else "warn")
    st.markdown(
        f'<div style="display:flex;align-items:center;gap:12px;margin-bottom:10px">'
        f'<div style="font-size:19px;font-weight:700">{sec["title"]}</div>'
        f'{ui.badge(lvl, kind)}</div>', unsafe_allow_html=True)

    if sec["kind"] == "todo":
        ui.todo_card(sec["todo"])
    elif sec["kind"] == "auto":
        # ★ 카드는 원시 HTML 이라 마크다운이 해석되지 않는다. 본문은 **강조**를
        #   쓰는 마크다운이므로 여기서 굵게 바꿔 준다 (PDF 쪽은 fpdf2 의
        #   markdown=True 가 같은 표기를 처리한다).
        st.markdown(
            f'<div class="card"><div style="white-space:pre-line;'
            f'font-size:14px;line-height:1.75">'
            f'{S.to_html(sec["body"])}</div></div>',
            unsafe_allow_html=True)
        bad = S.check_phrasing(sec["body"])
        if bad:
            ui.callout(f"자동 생성 문장에 인과를 단정하는 표현이 있습니다: "
                       f"<b>{', '.join(bad)}</b>. 관측 데이터로는 인과를 "
                       f"주장할 수 없습니다.")
        else:
            st.caption("✓ 인과 단정 표현 검사 통과")

        if "funnel" in sec.get("charts", []):
            f = M.funnel(t)
            st.image(pdf_charts.funnel_png(f), width="stretch")
        if "device" in sec.get("charts", []):
            f = M.funnel(t)
            bi = max(int(f.index[f.is_bottleneck][0]), 1)
            g = M.funnel_by(t, DIM,
                            f.step.iloc[bi - 1], f.step.iloc[bi])
            st.image(pdf_charts.device_png(g), width="stretch")
        if "experiments" in sec.get("charts", []):
            st.image(pdf_charts.experiments_png(M.experiment_results(t)),
                     width="stretch")

        # ★ 2026-09-04 (Day4 프롬프트 11) — 한계는 표에서 고친다.
        #   조립된 것이 전부는 아니다. "찾았는데 없었다" 같은 것은 사람이 더해야
        #   하고, 조립이 잘못 집은 것은 빼야 한다. 다만 **빼면 흔적을 남긴다** —
        #   검증 경고가 조용히 사라지면 그 경고는 없던 일이 된다.
        if sec["title"].startswith("7."):
            with st.expander("한계 항목 편집 — 행을 더하거나 뺄 수 있습니다"):
                import pandas as _pd
                base = st.session_state.get("limit_rows") or S.limit_rows(t)
                ed = st.data_editor(
                    _pd.DataFrame(base), num_rows="dynamic", width="stretch",
                    key="limit_editor",
                    column_config={
                        "출처": st.column_config.SelectboxColumn(
                            options=S._LIMIT_SOURCES, required=True, width="small"),
                        "내용": st.column_config.TextColumn(required=True,
                                                           width="large"),
                        "포함": st.column_config.CheckboxColumn(
                            default=True, width="small",
                            help="끄면 리포트와 PDF 에 안 들어갑니다"),
                        "고정": st.column_config.CheckboxColumn(
                            disabled=True, width="small",
                            help="분석의 성격이라 뺄 수 없는 항목입니다"),
                    })
                rows = ed.to_dict("records")

                # ★ 고정 행은 되살린다. 화면에서 체크를 꺼도 리포트에서는 안 빠진다 —
                #   "합성 데이터" 문장이 빠진 문서는 실측 보고서로 읽힌다.
                forced = [r["내용"] for r in rows
                          if r.get("고정") and not r.get("포함", True)]
                for r in rows:
                    if r.get("고정"):
                        r["포함"] = True

                dropped = [r for r in rows
                           if r.get("출처") == "검증 경고" and not r.get("포함", True)]
                base_texts = {r["내용"] for r in base}
                gone = [r["내용"] for r in base
                        if r["출처"] == "검증 경고"
                        and r["내용"] not in {x.get("내용") for x in rows}]

                a, b = st.columns([1, 1])
                with a:
                    if st.button("적용", type="primary"):
                        st.session_state.limit_rows = rows
                        st.rerun()
                with b:
                    if st.button("되돌리기"):
                        st.session_state.pop("limit_rows", None)
                        st.rerun()

                if forced:
                    ui.callout(
                        f"<b>{len(forced)}건은 뺄 수 없습니다.</b> 관측·기간·합성 "
                        f"데이터 문장은 이 분석의 성격이라, 빠지면 리포트가 "
                        f"사실과 다른 문서가 됩니다.", "info")
                if dropped or gone:
                    ui.callout(
                        f"<b>검증 경고를 뺐습니다</b> — "
                        f"{' · '.join((r['내용'][:40] for r in dropped))}"
                        f"{' · '.join(x[:40] for x in gone)}. "
                        f"검증이 잡은 것을 문서에서 빼면 <b>그 경고는 없던 일이 "
                        f"됩니다.</b> 뺀 이유를 게이트 3 근거에 적으십시오.")
    else:
        # ★ 2026-09-05 — **번호를 눌러 한 칸씩 쓴다.**
        #   전에는 2·6·8 을 한 폼에 쌓아 뒀는데, 어느 칸을 쓰는 중인지 눈이
        #   흩어지고 스크롤이 길어져 **아래 두 칸이 자주 빈 채로 남았다.**
        #   한 칸만 보이면 그 칸을 쓴다.
        #
        #   폼은 그대로 둔다(Day4 프롬프트 10) — 한 글자 칠 때마다 화면이 다시
        #   돌면 긴 해석을 쓰다 만다. st.form 은 제출 전까지 재실행하지 않는다.
        #
        #   ⚠️ 고르는 것은 **폼 밖**에 둔다. 폼 안에 넣으면 제출을 누르기 전까지
        #      재실행이 없어서 번호를 눌러도 칸이 안 바뀐다.
        #   ⚠️ 칸을 바꾸면 저장 안 한 글은 사라진다. 자동 저장을 안 하기로 한
        #      결정 그대로라 없애지 않고 **경고를 붙인다.**
        humans = [s for s in secs if s["kind"] == "human"]

        def _tab(h):
            no, name = h["title"].split(".", 1)
            return f"{no.strip()} {name.strip()}" + ("  ✓" if h["body"].strip() else "")

        tabs = {_tab(h): h for h in humans}
        # 목차에서 고른 장이 기본으로 열린다 — 고른 것과 열린 것이 다르면
        # 왜 다른 칸이 떴는지 설명할 길이 없다.
        cur = next((_tab(h) for h in humans if h["title"] == sec["title"]),
                   _tab(humans[0]))
        picked = st.segmented_control("사람이 쓰는 장", list(tabs), default=cur,
                                      key="hpick", label_visibility="collapsed")
        hsec = tabs.get(picked) or tabs[cur]

        with st.form("사람이 쓰는 장"):
            st.markdown(f"**{hsec['title']}**")
            typed = st.text_area(
                hsec["title"], value=hsec["body"], height=240,
                key=f"h_{hsec['title']}", label_visibility="collapsed",
                placeholder=hsec["placeholder"])
            c1, c2 = st.columns([1, 4])
            with c1:
                saved = st.form_submit_button("저장", type="primary")
            with c2:
                st.caption("　다른 번호로 넘어가기 전에 저장하십시오 — "
                           "안 누르면 쓰던 글이 사라집니다")

        if saved:
            st.session_state.human[hsec["title"]] = typed
            # 누른 것만 남긴다 — 자동 저장은 안 한다(교안 프롬프트 10)
            gates.save_human(st.session_state.human)
            st.session_state.human_saved_at = None    # 아래에서 다시 읽는다
            # 걸려도 저장은 한다. 사람의 문장이라 고칠지는 사람이 정한다.
            hits = ({hsec["title"]: S.check_phrasing(typed)}
                    if typed and S.check_phrasing(typed) else {})
            # rerun 하면 이 자리의 안내가 지워진다 — 세션에 담아 넘긴다.
            st.session_state.save_msg = hits or True
            st.rerun()

        if st.session_state.pop("save_msg", None):
            st.toast("저장했습니다 · 파일로 남겼습니다", icon="💾")

        # 언제 저장된 것인지 보인다 — 안 보이면 저장됐는지 매번 의심한다
        _, at = gates.load_human()
        if at:
            st.caption(f"　마지막 저장 {at.replace('T', ' ')} · "
                       f"서버를 다시 켜도 남습니다")

        # ★ 2026-09-04 (Day4 프롬프트 3) — **사람이 쓴 장에도 검사를 건다.**
        #   전에는 kind=="auto" 갈래에서만 돌아서 2·6·8장은 아예 검사되지
        #   않았다. 그런데 교안이 지목한 대로 **사람이 쓴 해석에 "때문에"가
        #   훨씬 자주 들어간다** — 자동 문장은 조심해서 만들지만 사람은 안 그렇다.
        #   검사를 안 거는 것이 아니라 *가장 필요한 곳에 안 걸려 있던* 것이다.
        #
        #   ★ 폼이 셋을 한꺼번에 받으므로 **셋 다** 검사한다. 고른 장만 보면
        #     해석은 고쳤는데 제안에 남은 표현을 못 본 채 게이트로 간다.
        #   저장을 막지는 않는다. 사람의 문장이라 고칠지는 사람이 정한다.
        hits = {h["title"]: S.check_phrasing(h["body"])
                for h in humans if h["body"] and S.check_phrasing(h["body"])}
        if hits:
            ui.callout(
                "인과를 단정하는 표현이 있습니다 — "
                + " · ".join(f"<b>{k}</b>: {', '.join(v)}" for k, v in hits.items())
                + '. 관측 데이터로는 인과를 주장할 수 없습니다 — '
                  '<b>"A 때문에 B"</b> 대신 '
                  '<b>"A가 낮은 구간에서 B도 낮다"</b>로 적으십시오.')
        elif any(h["body"] for h in humans):
            st.caption("✓ 인과 단정 표현 검사 통과")

# ── 내보내기 ──────────────────────────────────────────────────────
st.divider()
ui.section("내보내기")

c1, c2 = st.columns(2)
with c1:
    st.markdown("**PDF** — 표지 · 목차 · 차트 포함")
    # ★ 2026-09-04 (Day4 프롬프트 12) — 만드는 동안 무슨 일이 일어나는지 보여준다.
    #   PDF 생성은 몇 초 걸린다. 그동안 화면이 멈춘 것처럼 보이면
    #   **사람은 버튼을 또 누른다.** 단계를 찍어 주면 기다린다.
    #
    #   실패를 조용히 삼키지 않는다 — 만들어졌다고 표시됐는데 안 만들어진 것이
    #   가장 나쁘다. state="error" 로 두고 무엇이 실패했는지 남긴다.
    if st.button("PDF 만들기", type="primary"):
        with st.status("리포트를 만드는 중", expanded=True) as box:
            try:
                n_auto = sum(1 for s in secs if s["kind"] == "auto")
                n_human = sum(1 for s in secs if s["kind"] == "human")
                st.write(f"1) 장별 내용 모으는 중 — {len(secs)}장 "
                         f"(자동 {n_auto} · 사람 {n_human})")
                f = M.funnel(t)
                bi = max(int(f.index[f.is_bottleneck][0]), 1)
                g = M.funnel_by(t, DIM, f.step.iloc[bi - 1], f.step.iloc[bi])

                st.write("2) 차트 이미지 만드는 중 — 퍼널 · 분해 · 실험")
                charts = {
                    "funnel": pdf_charts.funnel_png(f),
                    "device": pdf_charts.device_png(g),
                    "experiments": pdf_charts.experiments_png(
                        M.experiment_results(t)),
                }

                st.write("3) PDF 조립하는 중")
                # 표지 지표는 **화면과 같은 함수**에서 온다 — PDF 가 따로
                # 계산하면 같은 이름의 값이 두 곳에서 갈린다
                k = M.kpis(t)
                pdf = to_pdf.build_pdf(
                    secs, charts,
                    kpis=[(n, v["fmt"].format(v["value"]),
                           M.status_of(n, v["value"])) for n, v in k.items()])
                st.session_state.pdf = pdf
                # 파일 이름의 시각은 **화면 표시용**이다. 계산 경로에는 현재
                # 시각을 넣지 않는다 — 재현이 안 된다 (CLAUDE.md 코드 규칙 2).
                st.session_state.pdf_name = (
                    f"{C.APP_NAME.replace(chr(32), chr(95))}_{C.PERIOD[0][:7]}_"
                    f"{datetime.now():%Y%m%d-%H%M}.pdf")
                box.update(label=f"완성 · {len(pdf)/1024:.0f}KB",
                           state="complete", expanded=False)
            except Exception as e:                     # noqa: BLE001
                box.update(label="PDF 만들기 실패", state="error", expanded=True)
                st.error(f"{type(e).__name__}: {e}")
                st.session_state.pop("pdf", None)
        if st.session_state.get("pdf"):
            st.toast("리포트가 만들어졌습니다", icon="📄")

    if st.session_state.get("pdf"):
        # download_button 은 재실행을 일으킨다 — 파일을 세션에 담아 두었다.
        st.download_button("PDF 내려받기", st.session_state.pdf,
                           file_name=st.session_state.get(
                               "pdf_name",
                               f"{C.APP_NAME.replace(chr(32), chr(95))}_"
                               f"{C.PERIOD[0][:7]}.pdf"),
                           mime="application/pdf")

with c2:
    st.markdown("**이메일 초안** — 실제로 보내지 않습니다")
    draft = S.email_draft(t, secs)
    st.text_input("받는 사람", draft["to"], disabled=True)
    st.text_input("제목", draft["subject"], disabled=True)
    with st.expander("본문 미리보기"):
        st.markdown(draft["html"], unsafe_allow_html=True)

    run = st.session_state.run
    if run and gates.is_passed(run, 2):
        st.markdown('<div class="gate final" style="margin-top:12px">'
                    '<div class="q">게이트 3 · 발송</div>'
                    '<div style="font-size:12.5px;color:#9f1239;margin-top:6px">'
                    '<b>되돌릴 수 없습니다.</b> 통과시키면 발송 기록이 남습니다.</div>'
                    '</div>', unsafe_allow_html=True)

        # ★ 2026-09-04 (Day4 프롬프트 8) — 발송 전 최종 점검.
        #   게이트 3은 되돌릴 수 없으므로 **여기서 걸러야 한다.**
        #   사람이 매번 기억해서 하는 점검은 언젠가 건너뛴다 — 그래서 코드로 박고
        #   하나라도 걸리면 확인 문구 칸조차 열지 않는다.
        #   ★ 계산은 sections.preflight() 가 한다. 화면은 목록을 그릴 뿐이다.
        pf = S.preflight(t, secs)
        with st.status(
                f"발송 전 점검 — {sum(c['ok'] for c in pf)}/{len(pf)} 통과",
                state="complete" if all(c["ok"] for c in pf) else "error",
                expanded=not all(c["ok"] for c in pf)):
            for c in pf:
                st.markdown(
                    f'<div style="margin:3px 0;font-size:13px">'
                    f'<span style="color:{C.COLORS["ok"] if c["ok"] else C.COLORS["block"]};'
                    f'font-weight:700">{"✓" if c["ok"] else "✕"}</span> '
                    f'<b>{c["name"]}</b> — '
                    f'<span style="color:{C.BRAND["muted"]}">{c["detail"]}</span></div>',
                    unsafe_allow_html=True)

        blocked = [c["name"] for c in pf if not c["ok"]]
        if gates.is_passed(run, 3):
            st.success("게이트 3 통과 기록됨 · 실제 발송은 하지 않았습니다.")
        elif blocked:
            ui.callout(f"<b>{len(blocked)}건이 걸려 통과할 수 없습니다.</b> "
                       f"{' · '.join(blocked)}")
        else:
            ok = st.text_input('확인 문구로 "발송"을 입력하십시오', key="g3")
            # ★ 2026-09-05 — 여기도 한 번 눌러 넘어갈 수 있게. 다만 확인 문구
            #   "발송"은 그대로 둔다. **되돌릴 수 없는 유일한 게이트**라 두 손이
            #   필요하다 — 고르는 손과, 발송이라고 치는 손.
            pick3 = st.pills("빠른 근거", C.GATE_PRESETS[3], key="g3pick")
            note = st.text_input(
                "직접 적기 (기록에 남습니다)", key="g3note",
                placeholder="예: 초안 확정. 실제 발송 없음. 게이트 통과 기록만 남김. "
                            "합성 데이터라 실제 보고에 쓸 수 없음 — 한계 N건 명시함")
            reason3 = note.strip() or (pick3 or "")
            enough3 = len(reason3) >= C.GATE_NOTE_MIN
            if st.button("확정", disabled=(ok != "발송" or not enough3)):
                gates.pass_gate(run, 3, reason3)
                gates.save(run)
                st.rerun()
            if not enough3:
                st.caption(f"　위에서 하나 고르거나 {C.GATE_NOTE_MIN}자 이상 "
                           f"직접 적으십시오. 게이트 1·2의 근거와 나란히 남습니다.")
    else:
        st.caption("게이트 2를 통과해야 발송 확정 단계가 열립니다.")
