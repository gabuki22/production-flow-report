# -*- coding: utf-8 -*-
"""공용 UI — 디자인 시스템과 재사용 컴포넌트.

색·간격·타이포를 여기서만 정의한다. 페이지마다 스타일을 흩뿌리면
나중에 한 곳을 고쳐도 다른 곳이 안 따라온다.
"""
from __future__ import annotations

import streamlit as st

from core import config as C

STATUS_MARK = {"ok": "●", "warn": "▲", "block": "✕", "none": "○"}
STATUS_TEXT = {"ok": "정상", "warn": "주의", "block": "차단", "none": "없음"}


def css() -> None:
    st.markdown(f"""<style>
:root {{
  --ok:{C.COLORS['ok']}; --warn:{C.COLORS['warn']};
  --block:{C.COLORS['block']}; --none:{C.COLORS['none']};
  --primary:{C.BRAND['primary']}; --ink:{C.BRAND['ink']};
  --muted:{C.BRAND['muted']}; --line:{C.BRAND['line']};
  --bg:{C.BRAND['bg']}; --surface:{C.BRAND['surface']};
}}
html, body, [class*="css"] {{
  font-family: Pretendard, -apple-system, 'Malgun Gothic', sans-serif;
}}
.stApp {{ background: var(--bg); }}
.block-container {{ padding: 1.2rem 2.2rem 3rem; max-width: 1320px; }}
/* 툴바의 메뉴·배포 버튼만 숨긴다.
   header 나 stToolbar 를 통째로 숨기면 안 된다 — 사이드바를 다시 여는
   stExpandSidebarButton 이 그 안에 들어 있어서, 한 번 접으면
   되돌릴 방법이 사라진다. */
[data-testid="stMainMenu"],
[data-testid="stAppDeployButton"],
[data-testid="stStatusWidget"] {{ display: none; }}
footer {{ visibility: hidden; }}
[data-testid="stHeader"] {{ background: transparent; }}
[data-testid="stExpandSidebarButton"] {{ visibility: visible !important; }}

/* pages/ 에서 자동 생성되는 목차는 감춘다. sidebar_nav() 가 대신 그린다 */
[data-testid="stSidebarNav"] {{ display: none; }}

/* 숫자는 고정폭이라야 자릿수가 흔들리지 않는다 */
.num {{ font-variant-numeric: tabular-nums; font-feature-settings: "tnum"; }}

/* 상단 컨텍스트 바 — 지금 보는 숫자가 어느 데이터의 것인지 잃지 않게 한다 */
.ctx {{
  display:flex; align-items:center; gap:18px; flex-wrap:wrap;
  background:var(--surface); border:1px solid var(--line);
  border-radius:12px; padding:12px 18px; margin-bottom:20px;
}}
.ctx .k {{ font-size:11px; color:var(--muted); letter-spacing:.04em; }}
.ctx .v {{ font-size:14px; font-weight:600; color:var(--ink); }}
.ctx .sep {{ width:1px; height:26px; background:var(--line); }}

.card {{
  background:var(--surface); border:1px solid var(--line);
  border-radius:14px; padding:22px 24px; height:100%;
}}
.card.tight {{ padding:16px 18px; }}

/* 지표 카드 */
.kpi .label {{ font-size:12px; color:var(--muted); font-weight:600;
  letter-spacing:.03em; }}
.kpi .value {{ font-size:32px; font-weight:700; color:var(--ink);
  line-height:1.15; margin:4px 0 2px;
  font-variant-numeric:tabular-nums; }}
.kpi .sub {{ font-size:12px; color:var(--muted); }}

/* 상태 배지 */
.badge {{
  display:inline-flex; align-items:center; gap:5px;
  font-size:11px; font-weight:700; padding:3px 10px; border-radius:999px;
  letter-spacing:.02em;
}}
.b-ok    {{ background:rgba(16,185,129,.12);  color:var(--ok); }}
.b-warn  {{ background:rgba(245,158,11,.14);  color:#b45309; }}
.b-block {{ background:rgba(244,63,94,.12);   color:var(--block); }}
.b-none  {{ background:rgba(100,116,139,.12); color:var(--none); }}

/* 실험 카드 — 왼쪽 굵은 선이 곧 판정이다 */
.exp {{
  background:var(--surface); border:1px solid var(--line);
  border-left:5px solid var(--line); border-radius:12px;
  padding:18px 22px; margin-bottom:14px;
}}
.exp.ok    {{ border-left-color:var(--ok); }}
.exp.warn  {{ border-left-color:var(--warn); background:#fffdf7; }}
.exp.block {{ border-left-color:var(--block); background:#fff8f9; }}
.exp.none  {{ border-left-color:var(--none); }}
.exp .id {{ font-size:11px; font-weight:700; color:var(--muted);
  letter-spacing:.06em; }}
.exp .nm {{ font-size:16px; font-weight:700; color:var(--ink); margin-top:2px; }}
.exp .hy {{ font-size:12px; color:var(--muted); margin-top:4px; }}
.exp .mv {{ font-size:22px; font-weight:700; color:var(--ink);
  font-variant-numeric:tabular-nums; }}
.exp .guard {{
  margin-top:12px; padding-top:12px; border-top:1px dashed var(--line);
  font-size:13px;
}}
.exp .note {{ font-size:12.5px; color:#92400e; margin-top:6px; }}
.exp .blocked {{
  font-size:13px; color:var(--block); background:rgba(244,63,94,.06);
  border-radius:8px; padding:12px 14px; margin-top:10px;
}}

/* 게이트 */
.gate {{
  border:1.5px solid var(--line); border-radius:14px;
  padding:20px 24px; background:var(--surface);
}}
.gate.final {{ border-color:var(--block); background:#fff8f9; }}
.gate .q {{ font-size:16px; font-weight:700; color:var(--ink); }}
.gate .warnbox {{
  background:rgba(245,158,11,.08); border-radius:8px;
  padding:12px 14px; margin:12px 0; font-size:13px; color:#92400e;
}}

/* 스테퍼 */
.stepper {{ display:flex; align-items:flex-start; gap:0; margin:6px 0 22px; }}
.stepper .s {{ flex:1; text-align:center; position:relative; }}
.stepper .dot {{
  width:26px; height:26px; border-radius:50%; margin:0 auto 7px;
  display:flex; align-items:center; justify-content:center;
  font-size:11px; font-weight:700;
  background:var(--surface); border:2px solid var(--line); color:var(--muted);
}}
.stepper .s.done .dot {{ background:var(--ok); border-color:var(--ok); color:#fff; }}
.stepper .s.now .dot  {{ background:var(--primary); border-color:var(--primary);
  color:#fff; box-shadow:0 0 0 4px rgba(79,70,229,.16); }}
.stepper .s .t {{ font-size:11px; color:var(--muted); }}
.stepper .s.now .t {{ color:var(--primary); font-weight:700; }}
.stepper .s:not(:last-child):after {{
  content:""; position:absolute; top:13px; left:50%; width:100%;
  height:2px; background:var(--line); z-index:-1;
}}
.stepper .s.done:not(:last-child):after {{ background:var(--ok); }}

/* 로그 */
.log {{ font-family:ui-monospace,Menlo,Consolas,monospace; font-size:12px;
  background:#0f172a; color:#cbd5e1; border-radius:10px; padding:14px 16px;
  max-height:220px; overflow-y:auto; }}
.log .t {{ color:#64748b; margin-right:10px; }}
.log .warn {{ color:#fbbf24; }}
.log .block {{ color:#fb7185; }}

.sec {{ font-size:18px; font-weight:700; color:var(--ink); margin:26px 0 12px; }}
.sec .hint {{ font-size:12px; font-weight:400; color:var(--muted);
  margin-left:10px; }}
.callout {{
  border-left:3px solid var(--warn); background:rgba(245,158,11,.07);
  padding:12px 16px; border-radius:0 8px 8px 0; font-size:13.5px;
  color:#78350f; margin-top:12px;
}}
.callout.info {{ border-left-color:var(--primary);
  background:rgba(79,70,229,.05); color:#3730a3; }}
div[data-testid="stMetricValue"] {{ font-variant-numeric:tabular-nums; }}

/* ── 탭 (2026-09-05) ──────────────────────────────────────────
   화면을 셋으로 묶으면서 탭이 **길잡이**가 됐다. 기본 탭은 텍스트만
   있어 지금 어디인지 훑어서는 안 보인다 — 고른 것만 진하게 띄운다.
   ⚠️ 안쪽 탭(획득/유지)은 한 단 작게 둔다. 크기가 같으면 어느 것이
      바깥이고 어느 것이 안쪽인지 알 수 없다. */
div[data-testid="stTabs"] button[role="tab"] {{
  font-size:14.5px; font-weight:600; padding:9px 20px;
  color:var(--muted); border-radius:9px 9px 0 0;
}}
div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
  color:var(--primary); background:rgba(79,70,229,.06);
}}
div[data-testid="stTabs"] div[data-testid="stTabs"] button[role="tab"] {{
  font-size:13px; font-weight:500; padding:6px 14px;
}}

/* ── 섹션 제목 — 앞에 색 막대를 세운다 ─────────────────────────
   탭 안에 섹션이 여럿이라 어디서 새 덩어리가 시작하는지 안 보였다. */
.sec {{ padding-left:11px; border-left:3px solid var(--primary); }}

/* ── 카드에 숨결 ─────────────────────────────────────────────
   그림자를 아주 옅게. 진하게 주면 화면이 무거워지고 숫자보다
   테두리가 먼저 보인다. */
.card {{ box-shadow:0 1px 2px rgba(15,23,42,.04); }}
.card.kpi {{ transition:box-shadow .15s ease; }}
.card.kpi:hover {{ box-shadow:0 3px 10px rgba(79,70,229,.10); }}

/* 숫자는 전부 자릿수 고정폭 — 표에서 자리가 흔들리면 읽기 어렵다 */
.card .value, .num {{ font-variant-numeric:tabular-nums; }}
</style>""", unsafe_allow_html=True)


def badge(level: str, text: str | None = None) -> str:
    return (f'<span class="badge b-{level}">{STATUS_MARK[level]} '
            f'{text or STATUS_TEXT[level]}</span>')


def context_bar(run: dict | None, extra: dict | None = None) -> None:
    items = [("데이터셋", C.DATASET),
             ("기간", f"{C.PERIOD[0]} ~ {C.PERIOD[1]}")]
    if run:
        items.append(("마지막 실행", run.get("started_at", "-").replace("T", " ")))
    for k, v in (extra or {}).items():
        items.append((k, v))
    html = '<div class="ctx">'
    for i, (k, v) in enumerate(items):
        if i:
            html += '<div class="sep"></div>'
        html += f'<div><div class="k">{k}</div><div class="v num">{v}</div></div>'
    if run:
        lv = {"진행중": "warn", "완료": "ok", "차단": "block"}.get(
            run.get("status", ""), "none")
        html += ('<div style="margin-left:auto">'
                 + badge(lv, run.get("status", "")) + "</div>")
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def section(title: str, hint: str = "") -> None:
    h = f'<span class="hint">{hint}</span>' if hint else ""
    st.markdown(f'<div class="sec">{title}{h}</div>', unsafe_allow_html=True)


def kpi_card(label: str, value: str, sub: str = "", level: str = "ok") -> str:
    return (f'<div class="card kpi tight"><div class="label">{label}</div>'
            f'<div class="value">{value}</div>'
            f'<div class="sub">{badge(level, sub or None)}</div></div>')


def callout(text: str, kind: str = "warn") -> None:
    cls = "callout info" if kind == "info" else "callout"
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)


def stepper(steps: list[str], current: int) -> None:
    html = '<div class="stepper">'
    for i, s in enumerate(steps):
        cls = "done" if i < current else ("now" if i == current else "")
        mark = "✓" if i < current else str(i + 1)
        html += f'<div class="s {cls}"><div class="dot">{mark}</div><div class="t">{s}</div></div>'
    html += "</div>"
    st.markdown(html, unsafe_allow_html=True)


def logbox(entries: list[dict]) -> None:
    if not entries:
        st.caption("아직 기록이 없습니다.")
        return
    rows = "".join(
        f'<div><span class="t">{e["at"]}</span>'
        f'<span class="{e["level"] if e["level"] != "ok" else ""}">{e["msg"]}</span></div>'
        for e in entries[-40:])
    st.markdown(f'<div class="log">{rows}</div>', unsafe_allow_html=True)


def sidebar_nav(active: str) -> None:
    with st.sidebar:
        st.markdown(
            f'<div style="padding:6px 0 14px">'
            f'<div style="font-size:17px;font-weight:800;color:{C.BRAND["ink"]}">'
            f'{C.APP_NAME}</div>'
            f'<div style="font-size:11px;color:{C.BRAND["muted"]}">'
            f'{C.DATASET}</div></div>', unsafe_allow_html=True)
        st.page_link("app.py", label="홈", icon="🏠")
        st.page_link("pages/1_실행.py", label="실행", icon="▶️")
        st.page_link("pages/2_대시보드.py", label="대시보드", icon="📊")
        st.page_link("pages/3_리포트.py", label="리포트", icon="📄")
        st.page_link("pages/4_아카이브.py", label="아카이브", icon="🗂️")
        # ★ 골격에 없는 우리 화면. 아카이브 뒤에 둔 이유 — 1~4는 "앱을 돌리는 순서"고
        #   이건 도메인 질문이라 성격이 다르다. 순서에 끼워 넣으면 절차처럼 읽힌다.
        st.page_link("pages/5_납기전망.py", label="납기 전망", icon="📈")
        # ★ 2026-09-10 — 제안서를 독립 메뉴로 올렸다(전에는 리포트 안 임시 탭).
        #   5 뒤에 두는 이유는 위와 같다 — 1~4 가 "앱을 돌리는 순서"고
        #   5·6 은 그 순서 밖에서 묻는 것이라 성격이 다르다.
        #   ⚠️ 리포트와 제안서는 **다른 문서**다. 한 화면에 얹혀 있으면
        #      읽는 사람도 목적도 다른 둘을 같은 것으로 읽게 된다.
        st.page_link("pages/6_제안서.py", label="제안서", icon="📝")
        st.divider()
        st.caption("발송은 초안까지만 만듭니다.\n실제 메일은 나가지 않습니다.")


def todo_card(e) -> None:
    """아직 채우지 않은 자리에 안내를 그린다.

    **골격 전용이다.** 전부 채우고 나면 이 함수와 core/todo.py를 지워도 된다.
    """
    st.markdown(
        f'<div style="border:1.5px dashed #94a3b8;border-radius:14px;'
        f'padding:20px 24px;background:{C.BRAND["surface"]};margin:8px 0 18px">'
        f'<div style="font-size:11px;font-weight:700;color:{C.BRAND["primary"]};'
        f'letter-spacing:.06em">★ {e.day}</div>'
        f'<div style="font-size:16px;font-weight:700;color:{C.BRAND["ink"]};'
        f'margin:6px 0 4px">{e.task}</div>'
        + (f'<div style="font-size:13px;color:#475569;line-height:1.6">'
           f'{e.hint}</div>' if e.hint else "")
        + (f'<div style="font-size:12px;color:{C.BRAND["muted"]};margin-top:10px;'
           f'font-family:ui-monospace,Consolas,monospace">{e.where}</div>'
           if e.where else "")
        + '</div>', unsafe_allow_html=True)


def guard(fn, *args, **kwargs):
    """아직 안 채운 함수를 호출하면 안내 카드를 그리고 None을 돌려준다.

    **골격 전용이다.** 덕분에 빈 골격도 화면이 뜨고, 채운 자리부터 살아난다.

        f = ui.guard(M.funnel, t)
        if f is None:
            st.stop()
    """
    from core.todo import NotYet
    try:
        return fn(*args, **kwargs)
    except NotYet as e:
        todo_card(e)
        return None


def verdict_steps(r: dict) -> None:
    """판정이 **어느 물음에서 갈렸는지** 펼쳐 보인다 (Day3 프롬프트 12).

    배지 하나만 보이면 "왜 효과 없음이지"에 사람이 답을 못 한다.
    특히 **묻지 않은 물음**을 안 적으면 통과한 것으로 읽힌다 —
    EXP-002 는 가드레일이 괜찮아서 넘어간 것이 아니라 배정이 깨져서
    아예 계산하지 않은 것이다. 둘은 화면에서 구분되지 않는다.

    ★ 계산하지 않는다. metrics.experiment_results() 가 남긴 목록을 그릴 뿐이다.
    """
    steps = r.get("steps")
    if not steps:
        return
    stopped = next((s for s in steps if s["passed"] is False), None)
    state = "error" if r["color"] in ("block", "warn") else "complete"
    label = (f"판정 과정 — {r['verdict']}"
             + (f" · **{stopped['q']}**에서 갈렸습니다" if stopped else ""))
    with st.status(label, state=state, expanded=False):
        for i, s in enumerate(steps, 1):
            mark = {True: "✓", False: "✕", None: "—"}[s["passed"]]
            tone = {True: C.COLORS["ok"], False: C.COLORS["block"],
                    None: C.BRAND["muted"]}[s["passed"]]
            st.markdown(
                f'<div style="margin:2px 0;font-size:13px">'
                f'<span style="color:{tone};font-weight:700">{mark}</span> '
                f'<b>{i}. {s["q"]}</b> — '
                f'<span style="color:{C.BRAND["muted"]}">{s["detail"]}</span>'
                f'</div>', unsafe_allow_html=True)
        st.caption("　순서는 코드에 박혀 있습니다 — 앞에서 걸리면 뒤는 묻지 "
                   "않습니다. 규율에 맡기면 좋은 결과부터 보게 됩니다.")


def metric_def(name: str) -> None:
    """지표 정의를 **접힌 채로** 옆에 둔다 (Day3 프롬프트 13).

    화면에는 숫자만 있고 그 숫자가 무엇인지는 없었다. 회의에서 "납기 준수율
    91%"가 인용될 때, 분모가 무엇인지 아는 사람과 모르는 사람이 같은 문장을
    다르게 읽는다. 그렇다고 카드에 정의를 붙여 두면 매일 보는 사람에게는
    소음이다 — **묻는 사람만 펼치게** 한다.

    ⚠️ 정본은 notes/03_지표정의.md 다. 여기 뜨는 것은 요약이다.
    """
    d = C.METRIC_DEFS.get(name)
    if not d:
        return
    with st.popover("정의", width="stretch"):
        st.markdown(f"**{name}**")
        st.markdown(
            f'<div style="font-size:13px;line-height:1.7">'
            f'<div style="font-family:monospace;background:#f1f5f9;padding:8px 10px;'
            f'border-radius:6px;margin:6px 0">{d["식"]}</div>'
            f'<b>그레인</b> {d["그레인"]}<br>'
            f'<b>기준일</b> {d["기준일"]}'
            f'</div>', unsafe_allow_html=True)
        callout(f'<b>주의</b> {d["주의"]}', "info")
        th = C.THRESHOLDS.get(name)
        if th:
            st.caption(f"　경고 {th['경고']} · 위험 {th['위험']} "
                       f"— 현장 기준으로 정한 값입니다")


@st.dialog("감춘 근거", width="large")
def _blocked_dialog(r: dict) -> None:
    """못 믿을 실험의 **근거 전부**를 모달로 편다 (Day3 프롬프트 13 ★).

    카드에는 한 문장만 남긴다. 사유를 카드에 다 적으면 카드가 사유로 덮이고,
    그러면 사람들은 사유를 안 읽는다. 그렇다고 요약만 두면 **"왜 못 믿는지"를
    확인할 길이 없어서 우회하려 든다** — 교안: *"이유를 모르면 우회하려 한다."*
    """
    st.markdown(f"**{r['id']} · {r['name']}**")
    st.caption(f"　{r['hypothesis']}")
    st.markdown(f'<div class="blocked"><b>✕ 지표를 표시하지 않습니다</b><br>'
                f'{r["reason"]}</div>', unsafe_allow_html=True)

    srm = r.get("srm") or {}
    st.markdown("**배정이 설계대로 갈렸는가**")
    a, b, c = st.columns(3)
    a.metric("대조군", f"{srm.get('c', 0):,}")
    b.metric("처치군", f"{srm.get('t', 0):,}")
    ratio = srm.get("ratio") or (0.0, 0.0)
    c.metric("비율", f"{ratio[0]*100:.1f} : {ratio[1]*100:.1f}",
             help="50:50 에서 멀수록 배정이 깨진 것입니다")
    if srm.get("p") is not None:
        st.caption(f"　SRM 검정 p = {srm['p']:.3g} "
                   f"(0.001 미만이면 우연으로 보기 어렵습니다)")

    st.markdown("**양과 시간은 충분한가**")
    d, e = st.columns(2)
    d.metric("배정 건수", f"{r.get('n_total', 0):,}",
             f"최소 {C.MIN_SAMPLE:,}", delta_color="off")
    e.metric("기간", f"{r.get('days', 0)}일",
             f"최소 {C.MIN_EXP_DAYS}일", delta_color="off")

    callout("이 실험의 <b>지표는 계산하지 않았습니다.</b> 감춘 것이 아니라 "
            "계산 자체를 하지 않았습니다 — 값이 변수에 들어 있으면 "
            "리포트나 로그로 샙니다.", "info")


def blocked_evidence(r: dict) -> None:
    """카드 밑에 근거 열기 버튼 하나만 둔다."""
    if st.button("감춘 근거 보기 →", key=f"why_{r['id']}"):
        _blocked_dialog(r)


# ── URL 에 상태를 싣는다 (Day3 프롬프트 14) ───────────────────────
# 화면을 골라 놓고 링크를 보내면 상대는 **기본 화면**을 본다. 그래서 회의에서
# "고객사로 놓고 보세요, 아니 기준을 납기로 바꾸시고…" 를 말로 다시 한다.
# 무엇을 보고 있었는지가 주소에 실리면 그 왕복이 사라진다.
#
# ⚠️ URL 은 **사람이 고칠 수 있는 입력**이다. 남이 보낸 링크의 값을 그대로
#    믿고 쓰면 없는 축으로 groupby 해서 죽는다. 반드시 허용 목록으로 거른다.
def url_state(key: str, default, options=None):
    """URL 에서 초기값을 읽는다. 목록 밖 값이면 기본값으로 되돌린다."""
    v = st.query_params.get(key)
    if v is None:
        return default
    if options is not None and v not in options:
        return default          # 조용히 되돌린다 — 링크가 낡았을 뿐이다
    return v


def push_url(**kv) -> None:
    """지금 보고 있는 상태를 주소에 적는다.

    **값이 바뀔 때만 쓴다.** 매번 쓰면 rerun 이 돌아 화면이 깜빡인다.
    """
    for k, v in kv.items():
        cur = st.query_params.get(k)
        if v is None:
            if cur is not None:
                del st.query_params[k]
        elif str(v) != cur:
            st.query_params[k] = str(v)
