# -*- coding: utf-8 -*-
"""실행 — 데이터를 넣고 8단계를 돌린다.

사람이 개입하는 곳은 게이트 세 곳뿐이다.
게이트는 앱이 판단하지 않는다. 판단할 재료를 놓고 사람이 누른다.
누가 언제 무엇을 보고 통과시켰는지 run 기록에 남는다.
"""
import streamlit as st

from core import config as C, gates, load, metrics as M, validate as V
from viz import ui

st.set_page_config(page_title="실행", page_icon="▶️", layout="wide",
                   initial_sidebar_state="expanded")
ui.css()
ui.sidebar_nav("run")

if "run" not in st.session_state:
    st.session_state.run = None
run = st.session_state.run

ui.context_bar(run)
st.markdown('<div style="font-size:24px;font-weight:800;margin-bottom:18px">'
            '실행</div>', unsafe_allow_html=True)

# ── 1. 데이터 선택 ────────────────────────────────────────────────
ui.section("1. 데이터 선택")
src = st.radio("원본", ["등록된 데이터셋", "파일 업로드"],
               horizontal=True, label_visibility="collapsed")

tables = None
if src == "등록된 데이터셋":
    st.selectbox("데이터셋", [C.DATASET], label_visibility="collapsed")
    if st.button("적재 시작", type="primary"):
        st.session_state.run = gates.new_run()
        run = st.session_state.run
        with st.spinner("적재 중..."):
            tables = ui.guard(load.load_all)
        if tables is None:
            st.session_state.run = None
            st.stop()
        gates.log(run, f"적재 완료 · {len(tables)}개 테이블 "
                       f"{sum(len(d) for d in tables.values()):,}행")
        gates.advance(run, "적재")
        st.session_state.loaded = True
        st.rerun()
else:
    up = st.file_uploader("데이터 파일 (**파일명이 테이블명**이어야 합니다)",
                          type=["csv", "parquet", "xlsx", "xls"],
                          accept_multiple_files=True)
    st.caption("배포본에서는 파일당 20MB로 제한됩니다. "
               "큰 데이터는 parquet 으로 바꿔 넣으십시오.")
    if up and st.button("적재 시작", type="primary"):
        st.session_state.run = gates.new_run("업로드")
        run = st.session_state.run
        tables = load.load_uploaded(up)
        gates.log(run, f"업로드 {len(tables)}개 테이블 적재")
        gates.advance(run, "적재")
        st.session_state.loaded = True
        st.rerun()

if not run:
    st.info("데이터를 적재하면 진행 상태가 표시됩니다.")
    st.stop()

if tables is None:
    tables = ui.guard(load.load_all)
    if tables is None:
        st.stop()

# ── 진행 스테퍼 ───────────────────────────────────────────────────
ui.section("진행")
ui.stepper(gates.STEPS, run["step"])

# ── 2. 프로파일 ───────────────────────────────────────────────────
if run["step"] >= 1:
    ui.section("2. 프로파일", "적재된 데이터가 무엇인지 먼저 본다")
    prof = V.profile(tables)
    st.dataframe(prof, width="stretch", hide_index=True)
    gates.advance(run, "프로파일")

# ── 3. 검증 ───────────────────────────────────────────────────────
if run["step"] >= 2:
    ui.section("3. 검증", "통과·경고·차단을 나눠 사람 앞에 놓는다")
    checks = ui.guard(V.run_checks, tables)
    if checks is None:
        st.stop()
    s = V.summarize(checks)
    gates.advance(run, "검증")

    c1, c2, c3 = st.columns(3)
    for col, k, label in [(c1, "ok", "통과"), (c2, "warn", "경고"),
                          (c3, "block", "차단")]:
        with col:
            st.markdown(ui.kpi_card(label, f"{s[k]}건", "", k),
                        unsafe_allow_html=True)

    st.write("")
    for c in checks:
        with st.container():
            st.markdown(
                f'<div class="card tight" style="margin-bottom:8px">'
                f'{ui.badge(c["level"])} <b>{c["name"]}</b><br>'
                f'<span style="font-size:13px;color:#475569">{c["msg"]}</span>'
                + (f'<div style="font-size:12px;color:#94a3b8;margin-top:6px">'
                   f'{c["detail"]}</div>' if c["detail"] else "")
                + '</div>', unsafe_allow_html=True)

# ── 게이트 1 ──────────────────────────────────────────────────────
if run["step"] >= 3 and not gates.is_passed(run, 1):
    ui.section("게이트 1 · 입구")
    warns = [c for c in checks if c["level"] == "warn"]
    body = (f'<div class="gate"><div class="q">{gates.GATES[1]["question"]}</div>')
    if warns:
        body += ('<div class="warnbox"><b>경고 '
                 f'{len(warns)}건을 확인하십시오.</b><br>'
                 + "<br>".join(f"· {w['name']} — {w['msg']}" for w in warns)
                 + "</div>")
    body += ('<div style="font-size:12.5px;color:#64748b">'
             '되돌릴 수 있는 게이트입니다.</div></div>')
    st.markdown(body, unsafe_allow_html=True)

    note = st.text_input("판단 근거 (기록에 남습니다)",
                         placeholder="예: 날짜 범위 경고는 추출 시점 차이라 그 행만 빼고 진행")
    # ★ 2026-09-04 (Day3 프롬프트 11) — **근거 없이는 통과시키지 않는다.**
    #   기존 기록을 열어 보니 게이트 1·2 가 둘 다 note="" 로 남아 있었다.
    #   "게이트1 ✓ 게이트2 ✓" 만 있고 무엇을 보고 통과시켰는지가 없으면
    #   거버넌스 기록이 아니라 통과 도장일 뿐이다. 나중에 이 실행을 다시 꺼낼
    #   사람은 "왜 통과였지"에 답할 수 없다.
    enough = len(note.strip()) >= C.GATE_NOTE_MIN
    a, b = st.columns([1, 1])
    with a:
        if st.button("되돌리기"):
            st.session_state.run = None
            st.rerun()
    with b:
        if st.button("통과시키기", type="primary",
                     disabled=not (s["can_pass"] and enough)):
            gates.pass_gate(run, 1, note)
            gates.advance(run, "게이트1")
            # 2026-09-01 추가 — 골격은 게이트 2에서만 저장한다. Day1에는 계산을
            # 아직 안 만들어 게이트 2에 못 가므로 통과 근거가 어디에도 안 남는다.
            # 산출물 5(게이트 1 통과 기록)를 위해 여기서 한 번 저장한다.
            gates.save(run)
            st.rerun()
    if not s["can_pass"]:
        st.error("차단 항목이 있어 통과할 수 없습니다.")
    elif not enough:
        st.caption(f"　판단 근거를 {C.GATE_NOTE_MIN}자 이상 적어야 통과시킬 수 "
                   f"있습니다. 이 문장이 아카이브에 그대로 남습니다.")

# ── 4. 계산 ───────────────────────────────────────────────────────
if gates.is_passed(run, 1):
    ui.section("4. 계산")
    f = ui.guard(M.funnel, tables)
    k = ui.guard(M.kpis, tables)
    if f is None or k is None:
        st.stop()
    res = ui.guard(M.experiment_results, tables) or []
    gates.advance(run, "계산")
    if "계산 완료" not in [l["msg"][:5] for l in run["log"]]:
        gates.log(run, f"계산 완료 · 퍼널 {len(f)}단계 · 실험 {len(res)}건")

    cols = st.columns(4)
    for col, (name, v) in zip(cols, k.items()):
        with col:
            st.markdown(ui.kpi_card(name, v["fmt"].format(v["value"]), "",
                                    M.status_of(name, v["value"])),
                        unsafe_allow_html=True)

    st.write("")
    # column_config 로 막대를 붙인다 (Day2 프롬프트 12).
    # 숫자만 있는 표에서는 **어느 단계가 얕은지**를 사람이 뺄셈해서 찾아야 한다.
    # 게이트 2 앞이라 "계산이 말이 되는가"를 훑는 자리 — 여기서 눈에 안 띄면
    # 이상한 값이 그대로 통과한다.
    #
    # ⚠️ style.format 과 column_config 는 같이 못 쓴다(서식이 무시된다).
    #    포맷을 column_config 쪽으로 옮긴다.
    st.dataframe(
        f[["label", "n", "step_rate", "cum_rate"]].rename(columns={
            "label": "단계", "n": "도달", "step_rate": "단계 전환율",
            "cum_rate": "누적 전환율"}),
        width="stretch", hide_index=True,
        column_config={
            "단계": st.column_config.TextColumn(width="medium"),
            "도달": st.column_config.NumberColumn(format="%,d"),
            # 단계 전환율은 **1.0 근처에 몰려** 있어 0~1 막대로는 다 차 보인다.
            # 최소값 부근으로 눈금을 좁혀야 차이가 보인다.
            # format="percent" — 값이 0~1 이라 "%.2f%%" 를 주면 0.99% 로 찍힌다
            "단계 전환율": st.column_config.ProgressColumn(
                format="percent", min_value=float(f.step_rate.min()) * 0.995,
                max_value=1.0),
            "누적 전환율": st.column_config.ProgressColumn(
                format="percent", min_value=0.0, max_value=1.0),
        })

# ── 게이트 2 ──────────────────────────────────────────────────────
if gates.is_passed(run, 1) and not gates.is_passed(run, 2):
    ui.section("게이트 2 · 출구")
    st.markdown(f'<div class="gate"><div class="q">'
                f'{gates.GATES[2]["question"]}</div>'
                f'<div style="font-size:12.5px;color:#64748b;margin-top:8px">'
                f'계산 결과가 상식에 맞는지, 이전 기간과 크게 다르지 않은지 '
                f'확인하십시오. 되돌릴 수 있습니다.</div></div>',
                unsafe_allow_html=True)
    note2 = st.text_input("판단 근거", key="g2",
                          placeholder="예: 납기 준수율 91.3%는 직전 기간과 유사, 자릿수 이상 없음")
    enough2 = len(note2.strip()) >= C.GATE_NOTE_MIN
    a, b = st.columns([1, 1])
    with a:
        if st.button("되돌리기", key="r2"):
            gates.revert_gate(run, 2) or gates.revert_gate(run, 1)
            st.rerun()
    with b:
        if st.button("통과시키기", type="primary", key="p2",
                     disabled=not enough2):
            gates.pass_gate(run, 2, note2)
            gates.advance(run, "대시보드")
            gates.save(run)
            st.rerun()
    if not enough2:
        st.caption(f"　판단 근거를 {C.GATE_NOTE_MIN}자 이상 적어야 통과시킬 수 "
                   f"있습니다. 게이트 1의 근거와 **나란히** 아카이브에 남습니다.")

if gates.is_passed(run, 2):
    gates.advance(run, "리포트")
    run["status"] = "완료"
    gates.save(run)
    st.success("계산과 검증이 끝났습니다. 대시보드와 리포트로 넘어가십시오.")
    a, b = st.columns(2)
    with a:
        st.page_link("pages/2_대시보드.py", label="📊 대시보드 열기 →")
    with b:
        st.page_link("pages/3_리포트.py", label="📄 리포트 열기 →")

# ── 로그 ──────────────────────────────────────────────────────────
ui.section("로그")
ui.logbox(run["log"])
