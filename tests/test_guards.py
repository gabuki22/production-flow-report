# -*- coding: utf-8 -*-
"""망가뜨린 데이터를 앱이 거르는가.

  py -X utf8 tests/test_guards.py

교안(Day1 실습 E · core/validate.py 주석)이 시킨 것:

> 다 쓰고 나면 **정상 파일을 일부러 망가뜨려 넣어 본다.**
> 컬럼 하나를 지우거나 날짜를 한 해 옮긴다. 차단이 뜨고 게이트 버튼이
> 비활성되는 것까지 눈으로 봐야 한다.
> **경고만 띄우고 진행되면 그 검증은 없는 것과 같다.**

────────────────────────────────────────────────────────────────────
★ 이 파일의 0번 검사가 가장 중요하다 — **정상 데이터가 통과하는지 먼저 본다.**

  전부 차단하는 검증기는 여기 있는 망가뜨리기 검사를 **모두 통과한다.**
  그리고 아무 데이터도 못 쓰게 만든다. 차단을 확인하기 전에
  통과를 먼저 확인하지 않으면, 이 파일은 아무것도 증명하지 않는다.
  (2026-07-31 UNC 정규식 사고 — 검사기와 대상이 같이 깨져 함께 통과했다)
────────────────────────────────────────────────────────────────────

**망가뜨린 파일을 저장소에 두지 않는다.** 정상 데이터에서 그때그때 만든다 —
사본을 두면 정본이 바뀔 때 사본만 옛날 것으로 남고, 어느 날 그 사본으로
"통과했다"고 말하게 된다.

화면으로 눈으로 보려면 → `tests/_망가뜨린데이터/README.md`
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config as C, load, validate as V   # noqa: E402

ok = True


def check(cond, label, got=""):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"   {got}" if got else ""))
    ok = ok and bool(cond)


def level_of(tables: dict, name: str) -> str:
    """검증 결과에서 규칙 하나의 판정을 꺼낸다."""
    for c in V.run_checks(tables):
        if c["name"] == name:
            return c["level"]
    return "(없음)"


def summary(tables: dict) -> dict:
    return V.summarize(V.run_checks(tables))


CLEAN = load.load_all()


def broken(**edits) -> dict:
    """정상 데이터를 얕게 복사한 뒤 지정한 테이블만 갈아끼운다.

    원본 dict 를 건드리지 않는다 — 검사 하나가 다음 검사를 오염시키면
    실패가 어디서 왔는지 알 수 없게 된다.
    """
    t = dict(CLEAN)
    t.update(edits)
    return t


# ── 0. 먼저 — 정상 데이터는 통과하는가 ────────────────────────────
print("0. 정상 데이터 (이게 실패하면 아래는 아무 의미가 없다)")

s = summary(CLEAN)
check(s["block"] == 0, "차단 0건", f"통과 {s['ok']} · 경고 {s['warn']} · 차단 {s['block']}")
check(s["can_pass"] is True, "게이트를 넘을 수 있다")
for rule in ("행 수", "필수 컬럼", "날짜 범위"):
    check(level_of(CLEAN, rule) != "block", f"{rule} — 차단 아님",
          level_of(CLEAN, rule))

# ── 1. 컬럼 하나를 지운다 (교안이 든 예 ①) ────────────────────────
print("\n1. 필수 컬럼을 지운다 — 교안이 든 예")

for table, col in [("orders", "납기일"), ("orders", "수주ID"),
                   ("order_events", "이벤트구분"), ("defect_events", "불량수량")]:
    t = broken(**{table: CLEAN[table].drop(columns=[col])})
    lv = level_of(t, "필수 컬럼")
    check(lv == "block", f"{table}.{col} 삭제 → 차단", lv)
    check(summary(t)["can_pass"] is False, f"{table}.{col} 삭제 → 게이트 잠김")

# 필수가 아닌 컬럼은 지워도 막지 않는다 — **아무거나 막으면 검증이 아니다**
t = broken(orders=CLEAN["orders"].drop(columns=["색상"]))
check(level_of(t, "필수 컬럼") == "ok", "필수가 아닌 컬럼(색상) 삭제 → 통과",
      level_of(t, "필수 컬럼"))

# ── 2. 날짜를 한 해 옮긴다 (교안이 든 예 ②) ───────────────────────
print("\n2. 날짜를 옮긴다 — 교안이 든 예")

e = CLEAN["order_events"].copy()
e["이벤트일"] = (pd.to_datetime(e["이벤트일"].astype(str)) +
                 pd.DateOffset(years=1)).dt.strftime("%Y-%m-%d")
t = broken(order_events=e)
check(level_of(t, "날짜 범위") == "block", "이벤트일 전부 +1년 → 차단",
      level_of(t, "날짜 범위"))
check(summary(t)["can_pass"] is False, "게이트 잠김")

# 일부만 벗어나면 **경고**다 — 추출 시점 차이는 그 행만 빼면 된다
e2 = CLEAN["order_events"].copy()
n_shift = int(len(e2) * 0.02)                       # 2% — 차단선 5% 아래
idx = e2.index[:n_shift]
e2.loc[idx, "이벤트일"] = (
    pd.to_datetime(e2.loc[idx, "이벤트일"].astype(str))
    + pd.DateOffset(years=1)).dt.strftime("%Y-%m-%d")
t = broken(order_events=e2)
lv = level_of(t, "날짜 범위")
check(lv == "warn", "이벤트일 2%만 +1년 → 경고(차단 아님)", lv)
check(summary(t)["can_pass"] is True, "경고는 사람이 판단한다 — 게이트는 열려 있다")

# ★ 차단선 근처에서 판정이 실제로 갈리는지. 임계값이 코드에 살아 있는지 보는 자리다.
for pct, want in [(0.04, "warn"), (0.06, "block")]:
    e3 = CLEAN["order_events"].copy()
    idx = e3.index[:int(len(e3) * pct)]
    e3.loc[idx, "이벤트일"] = (
        pd.to_datetime(e3.loc[idx, "이벤트일"].astype(str))
        + pd.DateOffset(years=1)).dt.strftime("%Y-%m-%d")
    lv = level_of(broken(order_events=e3), "날짜 범위")
    check(lv == want, f"기간 밖 {pct*100:.0f}% → {want}", lv)

# ★★ 작은 테이블이 **통째로** 틀렸을 때. 이 검사가 실제 구멍을 잡았다 —
#    비율을 전체 행 수로 나누던 때는 experiment_assignments(19,064행)가
#    100% 어긋나도 전체 915,263행 대비 2.08% 라 경고에 그쳤다.
#    큰 테이블로만 시험했으면 끝까지 몰랐을 것이다.
a = CLEAN["experiment_assignments"].copy()
a["assigned_at"] = (pd.to_datetime(a["assigned_at"].astype(str))
                    + pd.DateOffset(years=3)).dt.strftime("%Y-%m-%d")
t = broken(experiment_assignments=a)
lv = level_of(t, "날짜 범위")
check(lv == "block",
      "가장 작은 테이블이 100% 어긋남 → 차단 (전체 대비로는 2%뿐)", lv)
check(summary(t)["can_pass"] is False, "게이트 잠김")

# ── 3. 행이 줄어든다 — 추출이 잘려 온 경우 ────────────────────────
print("\n3. 행이 줄어든다 — 파일이 잘려 왔을 때")

for frac, want in [(0.40, "block"), (0.75, "warn"), (0.95, "ok")]:
    t = broken(orders=CLEAN["orders"].head(int(len(CLEAN["orders"]) * frac)))
    lv = level_of(t, "행 수")
    check(lv == want, f"orders 를 {frac*100:.0f}% 로 자름 → {want}", lv)

t = broken(orders=CLEAN["orders"].head(0))
check(level_of(t, "행 수") == "block", "orders 0행 → 차단")

# ── 4. 테이블 자체가 없다 ─────────────────────────────────────────
print("\n4. 테이블이 통째로 빠졌다")

t = {k: v for k, v in CLEAN.items() if k != "defect_events"}
check(level_of(t, "필수 컬럼") == "block", "defect_events 없음 → 차단",
      level_of(t, "필수 컬럼"))

# ── 5. 막지 *않아야* 하는 것 ──────────────────────────────────────
# 차단을 늘리면 안전해 보이지만, 실무 데이터는 늘 어딘가 깨져 있어서
# 앱이 아무것도 못 돌리게 된다. **차단은 "이대로 계산하면 확실히 틀리는 것"에만.**
print("\n5. 막지 않아야 하는 것 — 차단을 남발하면 앱을 못 쓴다")

o = CLEAN["orders"].copy()
o.loc[o.index[:int(len(o) * 0.3)], "납기일"] = None      # 납기 미정 30%
t = broken(orders=o)
check(level_of(t, "날짜 범위") != "block", "납기일 결측 30% → 차단 아님",
      level_of(t, "날짜 범위"))
check(summary(t)["can_pass"] is True,
      "납기 미정은 실재한다 — 앱을 멈추지 않는다")

# 납기일이 **미래**인 것은 정상이다. 예정 컬럼을 관측처럼 검사하면
# 2026-08-29 기준 10,293건(10.7%)이 전부 오류로 잡힌다.
o2 = CLEAN["orders"].copy()
o2["납기일"] = (pd.to_datetime(o2["납기일"].astype(str))
                + pd.DateOffset(years=2)).dt.strftime("%Y-%m-%d")
t = broken(orders=o2)
check(level_of(t, "날짜 범위") != "block", "납기일 전부 +2년(미래) → 차단 아님",
      level_of(t, "날짜 범위"))
# ★ 처음엔 결과 전체를 문자열로 만들어 "납기일"을 찾았다가 오탐했다 —
#   규칙의 **근거 설명문**에 "납기일은 미래여야 정상"이라고 적혀 있어서다.
#   찾을 곳은 **판정 메시지(msg)** 다. 설명문에 있는 것은 정상이다.
msgs = " ".join(c["msg"] for c in V.run_checks(t) if c["name"] == "날짜 범위")
check("납기일" not in msgs, "납기일이 날짜 검사의 **지적 대상**에 없다", msgs[:60])

# ── 6. 검사기가 잠들지 않았는지 ───────────────────────────────────
# 규칙 표를 비우면 검사가 조용히 아무것도 안 본다. 그런 상태로 "통과"가 뜨면
# **아무도 모른다.** 표가 살아 있는지 값으로 확인한다.
print("\n6. 규칙 표가 살아 있는가")

V_ = C.VALIDATION
check(len(V_["필수컬럼"]["컬럼"]) == len(C.TABLES),
      "필수컬럼 규칙이 모든 테이블을 덮는다",
      f"{len(V_['필수컬럼']['컬럼'])} / {len(C.TABLES)}")
check(set(V_["행수"]["기준행"]) == set(C.TABLES),
      "행수 기준이 모든 테이블에 있다")
# 규칙 수를 여기 박지 않는다 — 규칙을 늘렸을 때 이 검사만 따로 고치는 일이 없게,
# 표에 있는 것과 실제로 도는 것이 **같은지**를 본다. (2026-09-01 규칙 4 추가로 3→4)
check(len(V.run_checks(CLEAN)) == len(V_),
      "표에 적힌 규칙이 전부 실제로 돈다",
      f"표 {len(V_)}건 / 실행 {len(V.run_checks(CLEAN))}건")
check("납기일" in V_["날짜범위"]["예정컬럼"],
      "납기일이 예정 컬럼으로 분류돼 있다")
check(len(V_["참조무결성"]["관계"]) >= 5,
      "참조 관계가 비어 있지 않다", f"{len(V_['참조무결성']['관계'])}건")

# ── 7. 강사가 준 진짜 파일로 — **이름은 맞고 내용이 다른 파일** ────
# ★ 여기 쓰는 파일은 **만든 것이 아니라 강사가 준 것**이다.
#   `_강사배포/화면/project3-report/data/` 의 통신사 완성본 9종 중
#   우리와 **파일명이 겹치는 둘**을 그대로 가져다 쓴다.
#
#   실무에서 데이터가 틀리는 방식은 컬럼이 사라지는 것보다
#   **"엉뚱한 파일을 같은 이름으로 받는 것"** 쪽이 훨씬 흔하다.
#   일부러 망가뜨린 것보다 이쪽이 진짜 시험이다.
print("\n7. 강사 통신사 파일을 우리 자리에 넣으면 — 이름은 같고 내용이 다르다")

#   parents[0]=tests · [1]=my-report · [2]=학습  → 형제 폴더인 프로젝트3위키로 간다
TEACHER = (Path(__file__).resolve().parents[2]
           / "프로젝트3위키" / "_강사배포" / "화면" / "project3-report" / "data")

if not TEACHER.exists():
    print(f"  [SKIP] 강사 배포본이 없다 — {TEACHER}")
else:
    # (1) 배정 파일 — 키가 visitor_id 라 우리 수주와 이어질 수 없다
    a = pd.read_parquet(TEACHER / "experiment_assignments.parquet")
    t = broken(experiment_assignments=a)
    s = summary(t)
    check(s["can_pass"] is False, "강사 experiment_assignments → 게이트 잠김",
          f"차단 {s['block']}건")
    check(level_of(t, "필수 컬럼") == "block", "  · 수주ID 가 없다 → 차단")
    check(level_of(t, "참조 무결성") == "block", "  · 실험 키가 안 이어진다 → 차단")

    # (2) 실험 파일 — ★ 이게 이 파일에서 가장 중요한 검사다.
    #     필수 컬럼(experiment_id·experiment_name)이 **둘 다 있고**
    #     행 수도 기준 3행의 167%라 규칙 1~3을 **전부 통과한다.**
    #     실험 ID까지 EXP-001~003 이 겹쳐서, 막지 않으면 통신사 가설로
    #     우리 성과를 계산하게 된다.
    e = pd.read_parquet(TEACHER / "experiments.parquet")
    t = broken(experiments=e)
    check(level_of(t, "필수 컬럼") == "ok",
          "강사 experiments — 필수 컬럼 규칙은 통과한다 (모양이 맞다)")
    check(level_of(t, "행 수") == "ok",
          "  · 행 수 규칙도 통과한다 (5행 / 기준 3행)")
    check(level_of(t, "참조 무결성") in ("warn", "block"),
          "  · **참조 무결성만 잡는다** — 규칙 4를 넣은 이유",
          level_of(t, "참조 무결성"))
    msgs = " ".join(c["msg"] for c in V.run_checks(t) if c["name"] == "참조 무결성")
    check("EXP-004" in msgs, "  · 우리에게 없는 실험이 이름으로 드러난다",
          msgs[:70])

    # ⚠️ 알려진 한계 — 여기서 **차단까지는 가지 않는다.**
    #    실험을 정의만 해 두고 아직 안 돌린 것은 정상이라 warn 이 맞다.
    #    파일이 통째로 바뀐 것을 차단으로 잡으려면 스키마 지문(컬럼 집합 대조) 같은
    #    다른 규칙이 필요하다. **못 잡는다는 사실을 여기 적어 둔다** —
    #    적어 두지 않으면 "검증을 통과했으니 맞는 파일"로 읽힌다.
    check(summary(t)["can_pass"] is True,
          "  · (한계) 게이트는 열려 있다 — 사람이 경고를 보고 판단해야 한다")

# ── 8. 판정 색이 장식으로 쓰이지 않는가 (Day3 부록 C) ────────────
# 교안: "강조 색은 '이걸 봐야 한다'는 뜻일 때만 쓴다.
#        그냥 예쁘게 하려고 쓰면 진짜 봐야 할 때 아무도 안 본다."
#
# 화면 코드에서 C.COLORS[...] 를 **고정 문자열 키**로 쓰면 값과 무관하게
# 늘 같은 색이다 = 장식이다. 판정이라면 색이 조건으로 갈려야 한다.
# 2026-09-03: 이 검사를 만들자 5_납기전망.py 의 박힌 빨강 1곳이 잡혔다.
print("\n8. 판정 색이 장식으로 쓰이지 않는가")

import re as _re2                                    # noqa: E402

ROOT2 = Path(__file__).resolve().parent.parent
LIT = _re2.compile(r"""C\.COLORS\[\s*["'](?:ok|warn|block|none)["']\s*\]""")

for f in sorted((ROOT2 / "pages").glob("*.py")):
    body = "\n".join(l for l in f.read_text(encoding="utf-8").split("\n")
                     if not l.strip().startswith("#"))
    fixed = 0
    for line in body.split("\n"):
        n = len(LIT.findall(line))
        if n and " if " not in line:      # 삼항으로 갈리면 판정이다
            fixed += n
    check(fixed == 0, f"{f.name} — 값과 무관하게 박힌 판정 색 없음", f"{fixed}곳")


# ── 9. 게이트를 근거 없이 통과시킬 수 있는가 (Day3 프롬프트 11) ────
# 게이트는 앱이 판단하지 않는 자리다. 그러니 **사람이 무엇을 봤는지**가
# 그 자리의 유일한 산출물이다. 근거가 비면 기록이 아니라 통과 도장이다.
#
# 2026-09-04: 저장된 실행을 열어 보니 게이트 1·2 가 둘 다 note="" 였다.
#   화면에 입력칸은 있었지만 비워 둬도 눌리는 버튼이었다.
#   규칙이 화면 코드에만 있어 metrics 검산으로는 안 잡힌다. 여기서 본다.
print("\n9. 게이트를 근거 없이 통과시킬 수 없는가")

run_src = (ROOT2 / "pages" / "1_실행.py").read_text(encoding="utf-8")
live = "\n".join(l for l in run_src.split("\n")
                 if not l.strip().startswith("#"))

check("GATE_NOTE_MIN" in live,
      "근거 최소 길이가 config 에서 온다 (화면에 숫자를 박지 않았다)")

guarded = sum(1 for l in live.split("\n") if "enough" in l and "disabled" in l)
check(guarded >= 2, "게이트 1·2 통과 버튼이 둘 다 근거 길이로 잠긴다",
      f"{guarded}곳")

# ★ 자가검증 — 규칙을 껐을 때 이 검사가 정말로 실패하는가.
#   검사기와 대상이 같은 패턴을 공유하면 둘 다 조용히 통과한다.
faked = live.replace("and enough)", ")").replace("disabled=not enough2", "")
would = sum(1 for l in faked.split("\n") if "enough" in l and "disabled" in l)
check(would < 2, "근거 요구를 빼면 이 검사가 실제로 실패한다 (자가검증)",
      f"{would}곳")

# 아카이브가 게이트별로 나란히 보여주는가 — 뭉치면 두 판단이 한 판단이 된다
arc = (ROOT2 / "pages" / "4_아카이브.py").read_text(encoding="utf-8")
check(chr(34) + " / " + chr(34) + ".join" not in arc,
      "아카이브가 게이트 근거를 한 줄로 뭉치지 않는다")
check("근거가 비어 있습니다" in arc,
      "근거가 빈 옛 기록을 조용히 숨기지 않는다")


# ── 10. URL 로 들어온 값을 그대로 믿는가 (Day3 프롬프트 14) ────────
# URL 은 **사람이 고칠 수 있는 입력**이다. 남이 보낸 링크의 축 이름을 그대로
# groupby 에 넘기면 KeyError 로 죽는다. 링크가 낡았을 뿐인데 화면이 터진다.
print("\n10. URL 상태를 허용 목록으로 거르는가")

import importlib                                     # noqa: E402
_ui = importlib.import_module("viz.ui")

check(_ui.url_state("dim", "고객사", ["고객사", "차종"]) == "고객사",
      "값이 없으면 기본값")

# 실제 쿼리 파라미터를 흉내 낸다 — st.query_params 는 dict 처럼 동작한다
class _QP(dict):
    pass

_saved = _ui.st.query_params
try:
    _ui.st.query_params = _QP({"dim": "없는축"})
    check(_ui.url_state("dim", "고객사", ["고객사", "차종"]) == "고객사",
          "목록 밖 값이면 기본값으로 되돌린다 (죽지 않는다)")
    _ui.st.query_params = _QP({"dim": "차종"})
    check(_ui.url_state("dim", "고객사", ["고객사", "차종"]) == "차종",
          "목록 안 값은 그대로 쓴다")
finally:
    _ui.st.query_params = _saved

# 화면이 목록을 넘기지 않고 부르면 방어가 없는 것과 같다
_dash = (ROOT2 / "pages" / "2_대시보드.py").read_text(encoding="utf-8")
_calls = [l for l in _dash.split("\n") if "url_state(" in l]
check(len(_calls) >= 4, "대시보드가 URL 상태를 4개 이상 읽는다", f"{len(_calls)}곳")
check(all("," in c.split("url_state(")[1] for c in _calls),
      "url_state 호출이 전부 기본값을 넘긴다")


# ── 11. 밖으로 나가면 안 되는 것이 섞여 있는가 (2026-09-05) ───────
# 이 폴더는 **언젠가 배포된다.** 과제 제출물이 스트림릿 URL 이고, 그때
# 저장소가 통째로 남의 손에 넘어간다. 그 시점에 훑으면 늦다 —
# 배포는 급할 때 하고, 급하면 안 훑는다.
#
# 2026-09-05 에 실제로 이런 것이 있었다:
#   · 실명 거래처 + 단가 인상 분쟁 인용 4곳 (볼트 노트 경로째로)
#   · 볼트 경로 6곳 — 배포물에 볼트 노트명·경로를 쓰지 않는다는 규칙 위반
#     (받는 사람에게는 **없는 위치**라 찾다가 만다)
#
# ⚠️ 회사명과 현장 발언 인용은 **일부러 남겼다.** 수업 맥락에서는 자연스럽고,
#    임계값의 근거가 "현장 기준 구술"이라는 사실 자체가 지워지면 안 된다.
#    지운 것은 **제3자 이름**·**개인 이름**·**받는 사람이 못 여는 경로**다.
#
# ★ 2026-09-05 배포일에 하나 더 배웠다 — **훑지 않는 폴더가 있었다.**
#   `_참고자료/` 를 검사에서 빼 뒀는데 그 안에 볼트 경로가 남아 있었다.
#   검사가 통과했지만 잡아서가 아니라 **보지 않아서**였다.
#   → 규칙: **안 훑는 것은 안 내보낸다.** 목록은 `배포제외.txt` 한 곳에 두고
#     여기서 그것을 읽어 훑을 범위를 정한다. 두 곳에 두면 반드시 갈라진다.
print("\n11. 밖으로 나가면 안 되는 것이 섞여 있는가")

_LEAK = [
    ("wiki/", "볼트 노트 경로"),
    ("raw/학습", "볼트 폴더 경로"),
    ("L-wiki", "볼트 저장소 이름"),
    ("C:" + chr(92) + chr(92) + "Users", "내 PC 절대경로"),
    ("유비덤", "실명 거래처(ERP)"),
    ("HKMC", "실명 거래처"),
    ("범한", "실명 거래처"),
    ("LS오토", "실명 거래처"),
    ("기쁨", "개인 이름"),
]

# 훑을 범위 = 배포할 범위. 목록은 배포제외.txt 하나뿐이다.
_SKIP = [l.strip() for l in (ROOT2 / "배포제외.txt").read_text(encoding="utf-8").splitlines()
         if l.strip() and not l.lstrip().startswith("#")]

_scan = [f for f in ROOT2.rglob("*")
         if f.suffix in (".py", ".md", ".toml")
         and not any(s in f.relative_to(ROOT2).as_posix() for s in _SKIP)
         and f.name != "test_guards.py"]

for _needle, _why in _LEAK:
    _hits = []
    for _f in _scan:
        try:
            if _needle in _f.read_text(encoding="utf-8"):
                _hits.append(_f.relative_to(ROOT2).as_posix())
        except (OSError, UnicodeDecodeError):
            continue
    check(not _hits, f"  · {_why} 없음 ({_needle})",
          " · ".join(_hits[:3]) if _hits else "")

# ★ 자가검증 — 정말로 잡는가. 있는 문자열을 하나 넣어 본다.
_probe = "wiki/decisions/" + "어떤노트.md " + "기쁨" + "님이 적음"
check(sum(1 for n, _ in _LEAK if n in _probe) >= 2,
      "  · 검사 목록이 볼트 경로와 개인 이름을 둘 다 잡는다 (자가검증)")

# ★ 훑지 않은 폴더가 그대로 배포되면 검사는 통과하되 아무것도 막지 못한다.
#   빼 둔 것이 배포제외에 **전부** 들어 있는지 여기서 본다.
_unscanned = [f.relative_to(ROOT2).as_posix() for f in ROOT2.rglob("*")
              if f.suffix in (".py", ".md", ".toml") and f not in _scan
              and f.name != "test_guards.py"]
_uncovered = [d for d in _unscanned if not any(s in d for s in _SKIP)]
check(not _uncovered, "  · 훑지 않은 파일이 전부 배포제외에 있다",
      " · ".join(sorted(_uncovered)[:3]) if _uncovered else f"{len(_unscanned)}개 제외")


# ── 12. 골격의 이름이 남아 있는가 (2026-09-05) ────────────────────
# 물음: *"제목은 왜 성장퍼널이야?"*
# 골격이 통신사 성장 퍼널이라 앱 이름이 "성장 리포트"였다. 퍼널 단계도 지표도
# 이탈→긴급품도 전부 우리 것으로 갈아엎었으면서 **제목만 강사 것이었다.**
#
# 이름은 config.APP_NAME 한 곳에 둔다. 화면·PDF·메일이 각자 문자열을 들고
# 있으면 반드시 한쪽만 고치는 날이 온다.
print("\n12. 골격에서 온 이름이 남아 있지 않은가")

_SKELETON = ["성장 리포트", "성장리포트", "성장 퍼널 분석", "성장 성과 분석"]
for _n in _SKELETON:
    _hits = [f.relative_to(ROOT2).as_posix() for f in ROOT2.rglob("*")
             if f.suffix in (".py", ".toml") and "_참고자료" not in str(f)
             and "__pycache__" not in str(f) and f.name != "test_guards.py"
             and _n in f.read_text(encoding="utf-8", errors="ignore")]
    check(not _hits, f"  · 골격 이름 '{_n}' 없음",
          " · ".join(_hits) if _hits else "")

# 이름을 한 곳에서만 쓰는가 — 화면·메일·PDF 가 config 를 본다
for _f, _what in [("app.py", "진입 화면"), ("viz/ui.py", "사이드바"),
                  ("report/sections.py", "메일 제목"),
                  ("pages/3_리포트.py", "PDF 파일명")]:
    _src = (ROOT2 / _f).read_text(encoding="utf-8")
    check("C.APP_NAME" in _src, f"  · {_what} 이 config.APP_NAME 을 쓴다")


# ── 13. 검사가 진짜 사용자 파일에 쓰지 않는가 (2026-09-05) ────────
# 두 번 겪었다.
#   2026-09-01  검사가 runs/ 에 게이트 통과 기록 5건을 쌓았다
#   2026-09-05  초안 저장을 만든 날, 검사가 drafts/human.json 을 덮어썼다
#               (4-2 절이 앱을 조작해 "저장"을 누른다)
#               사람이 써 둔 글이 있었다면 **검사 한 번에 지워졌을 것**이다.
#
# ★ 규칙 — **파일로 뭔가를 남기는 기능을 만들면 검사도 같이 격리한다.**
#   config 의 `*_DIR` 이 늘어날 때마다 test_app 이 그것을 임시 폴더로
#   돌려놓고 있는지 여기서 본다. 사람이 기억할 일이 아니다.
print("\n13. 검사가 진짜 사용자 파일에 쓰지 않는가")

_app_src = (ROOT2 / "tests" / "test_app.py").read_text(encoding="utf-8")
_cfg_src = (ROOT2 / "core" / "config.py").read_text(encoding="utf-8")

import re as _re4                                    # noqa: E402
# ★ **쓰는 폴더만** 본다. DATA_DIR·ASSETS_DIR 는 읽기 전용이라
#   임시 폴더로 돌리면 오히려 검사가 데이터를 못 찾는다.
#   "config 에 있는 모든 *_DIR" 로 잡았다가 그 둘이 걸렸다 —
#   규칙을 넓게 잡으면 못 지킬 것을 요구하게 되고, 결국 규칙을 끈다.
_dirs = _re4.findall("^([A-Z_]+_DIR)" + chr(92) + "s*=", _cfg_src, _re4.M)
_code = chr(10).join(
    f.read_text(encoding="utf-8")
    for f in (ROOT2 / "core").glob("*.py"))
_written = [d for d in _dirs
            if f"C.{d}.mkdir" in _code or f"{d}.mkdir" in _code]
check(bool(_written), "쓰는 폴더를 찾았다", " · ".join(_written))
for _d in _written:
    check(f"_C.{_d} = Path(tempfile.mkdtemp" in _app_src,
          f"  · test_app 이 {_d} 를 임시 폴더로 돌린다")

print(f"\n{'모두 통과' if ok else '실패 있음'}")
sys.exit(0 if ok else 1)
