# -*- coding: utf-8 -*-
"""앱 전체 점검.

  python tests/test_app.py

렌더만 보는 것이 아니라 **조작까지** 돌린다.
게이트를 통과시키고 PDF를 만들어 봐야 실제로 동작하는지 알 수 있다.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from streamlit.testing.v1 import AppTest   # noqa: E402

# ★ 테스트가 **진짜 아카이브에 쓰지 않게** 임시 폴더로 돌린다.
#   2026-09-01: 이걸 안 걸고 돌렸더니 게이트 통과 기록 5건이 runs/ 에 쌓였다.
#   아카이브는 "누가 언제 무엇을 보고 통과시켰는가"가 남는 자리인데,
#   테스트가 만든 기록이 섞이면 **판단 증거와 잡음을 구분할 수 없다.**
#   (runs/ 는 일부러 git 추적 중이라 그대로 두면 커밋까지 따라간다)
import tempfile                            # noqa: E402
from core import config as _C              # noqa: E402
_C.RUNS_DIR = Path(tempfile.mkdtemp(prefix="myreport_test_runs_"))
# ★ 2026-09-05 — **초안도 같이 격리한다.** 사람이 쓴 장을 파일로 남기게 만든
#   그날, 검사가 진짜 drafts/human.json 을 덮어썼다 —
#   4-2 절이 앱을 조작해 "저장"을 누르기 때문이다.
#   사람이 써 둔 글이 있었다면 **검사 한 번에 지워졌을 것**이다.
#   runs/ 에서 이미 겪은 사고인데(2026-09-01) 새 저장소를 만들 때 또 놓쳤다.
#   → 파일로 뭔가를 남기는 기능을 만들면 **검사도 같이 격리**한다.
_C.DRAFTS_DIR = Path(tempfile.mkdtemp(prefix="myreport_test_drafts_"))

# ★ 목록을 손으로 적지 않는다. 화면을 늘렸을 때 여기만 안 고치면
#   **새 화면이 한 번도 안 켜진 채로 "모두 통과"가 뜬다.**
PAGES = sorted(f"pages/{p.name}"
               for p in (Path(__file__).resolve().parent.parent / "pages").glob("*.py"))
ok = True


def check(cond, label, got=""):
    """got 은 **실패했을 때 무엇을 봤는지**를 남기려고 받는다.

    PASS/FAIL 만 찍으면 실패했을 때 다시 돌려 봐야 원인을 안다.
    (tests/test_metrics.py 와 같은 모양으로 맞췄다)
    """
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"   {got}" if got else ""))
    ok = ok and bool(cond)


def click(at, label):
    for b in at.button:
        if b.label == label:
            b.click().run()
            return True
    return False


print("1. 페이지 렌더")
at = AppTest.from_file("app.py", default_timeout=300).run()
check(not at.exception, "app.py")
for p in PAGES:
    at.switch_page(p).run()
    check(not at.exception, p)
    if at.exception:
        for e in at.exception:
            print(f"         {type(e.value).__name__}: {e.value}")

print("\n2. 실행 흐름과 게이트")
at.switch_page("pages/1_실행.py").run()
at.button[0].click().run()
check(not at.exception and at.session_state.run["step"] >= 1, "적재")
if at.text_input:
    at.text_input[0].set_value("날짜 범위 경고는 추출 시점 차이 — 그 행만 빼고 진행").run()
check(click(at, "통과시키기") and "1" in at.session_state.run["gates"],
      "게이트1 통과 · 판단 근거 기록")
if at.text_input:
    at.text_input[-1].set_value("납기 준수율 91.1% — 직전 기간과 유사").run()
check(click(at, "통과시키기") and "2" in at.session_state.run["gates"],
      "게이트2 통과")

print("\n3. 대시보드 조작")
at.switch_page("pages/2_대시보드.py").run()
from core import config as C2   # noqa: E402
# ★ 축 목록을 테스트에 박지 않는다. config.DIMS 를 늘렸을 때 테스트가
#   조용히 옛 축만 보고 통과하면, 새 축이 깨진 것을 아무도 모른다.
# 2026-09-04: st.radio -> st.segmented_control 로 바꾸면서 여기가 깨졌다.
#   AppTest 에서는 button_group 으로 잡힌다. 위젯을 바꾸면 검사도 같이 바꾼다.
for d in C2.DIMS[1:]:
    at.button_group(key="dim").set_value([d]).run()
    check(not at.exception, f"분해 축 전환 — {d}")
check(not at.exception, f"분해 축 {len(C2.DIMS)}종 전부 렌더")

# 기준 전환 — 퍼널 전환율로 바꿔도 죽지 않는가 (열 이름이 다르다)
at.button_group(key="basis").set_value(["퍼널 전환율"]).run()
check(not at.exception, "기준 전환 — 퍼널 전환율")
at.button_group(key="basis").set_value(["납기 준수율"]).run()
check(not at.exception, "기준 전환 — 납기 준수율")

print("\n4. 리포트와 PDF")
at.switch_page("pages/3_리포트.py").run()
at.radio[0].set_value("6. 해석").run()
# 2026-09-04: 사람 장 셋이 st.form 하나로 묶여서 text_area[0] 은 "2. 배경"이다.
#   위치로 집으면 엉뚱한 장에 쓴다 — **키로 집는다.**
at.text_area(key="h_6. 해석").set_value("탈락률이 아니라 납기 축에서 문제가 드러난다.").run()
check(click(at, "저장") and at.session_state.human, "사람 작성 저장")
check(click(at, "PDF 만들기") and "pdf" in at.session_state, "PDF 생성")
if "pdf" in at.session_state:
    print(f"         {len(at.session_state.pdf)/1024:.0f}KB")

print("\n4-1. 리포트 8장 — 안 채운 장이 남았는가")
from report import sections as S2   # noqa: E402
from core import load as L2         # noqa: E402

_secs = S2.build(L2.load_all())
_left = [x["title"] for x in _secs if x["kind"] == "todo"]
check(not _left, "골격 todo 로 남은 장 없음",
      f"남은 장: {_left}" if _left else "8/8 채움")
for x in _secs:
    if x["kind"] != "auto":
        continue
    bad = S2.check_phrasing(x["body"])
    # ★ 자동 생성 문장이 인과를 단정하면 사람이 눈으로 못 잡는다.
    #   화면에서도 검사하지만, 화면은 그 장을 열어야 돌아간다 —
    #   여기서 8장 전부를 한 번에 돌린다.
    check(not bad, f"{x['title']} 인과 단정 없음", str(bad) if bad else "")

print("\n4-2. 인과 검사가 실제로 잡는가 — 일부러 걸어 본다 (Day4 프롬프트 4)")
# ★ 만든 것과 동작하는 것은 다르다.
#   2026-09-04: check_phrasing 은 kind=="auto" 갈래에서만 돌고 있었다.
#   즉 **사람이 쓴 2·6·8장은 아예 검사되지 않았다** — 교안이 지목한 대로
#   자동 문장보다 사람이 쓴 해석에 "때문에"가 훨씬 자주 들어가는데,
#   가장 필요한 곳에 안 걸려 있었다.
at.switch_page("pages/3_리포트.py").run()


def _scan():
    import re as _re
    w = [_re.sub(r"<[^>]+>", "", str(m.value)) for m in at.markdown
         if "인과를 단정" in str(m.value)]
    o = [str(c.value) for c in at.caption if "검사 통과" in str(c.value)]
    return w, o


at.radio[0].set_value("6. 해석").run()
at.text_area(key="h_6. 해석").set_value("D사 물량이 몰리기 때문에 납기 준수율이 낮다.").run()
click(at, "저장")
_w, _o = _scan()
check(len(_w) == 1, "사람이 쓴 장에서 경고가 뜬다", f"{len(_w)}건")
check(_w and "때문에" in _w[0], "  · 어떤 단어가 걸렸는지 보인다",
      "때문에" if _w and "때문에" in _w[0] else "안 보임")

at.text_area(key="h_6. 해석").set_value(
    "D사 납기 준수율이 88.3%로 가장 낮다. 원인은 이 데이터로 가릴 수 없다.").run()
click(at, "저장")
_w, _o = _scan()
check(not _w and _o, "  · 되돌리면 경고가 사라진다",
      f"경고 {len(_w)} · 통과 {len(_o)}")

# ★ 자가검증 — 금지어를 비우면 이 검사가 실제로 FAIL 하는가.
#   검사기와 대상이 같은 전제를 공유하면 둘이 같이 망가지고 둘 다 통과한다.
_saved = S2.BANNED[:]
try:
    S2.BANNED.clear()
    check(not S2.check_phrasing("D사 물량이 몰리기 때문에 낮다."),
          "  · 금지어를 비우면 못 잡는다 (자가검증)")
finally:
    S2.BANNED[:] = _saved
check(S2.check_phrasing("D사 물량이 몰리기 때문에 낮다.") == ["때문에"],
      "  · 되돌린 뒤 다시 잡는다")

print("\n4-3. 감춘 수치가 PDF·메일로 새지 않는가 (Day4 프롬프트 7)")
# 교안: "화면에서 감췄는데 문서에 들어가면 감춘 의미가 없다."
# 우리는 trust_check() 를 계산 앞에 둬서 구조상 샐 곳이 없지만,
# **만든 것과 동작하는 것은 다르다.** 실제 PDF 를 뽑아서 본다.
import re as _re3, tempfile as _tf            # noqa: E402
from pathlib import Path as _P                # noqa: E402
import pypdf as _pypdf                        # noqa: E402
from report import to_pdf as TP2              # noqa: E402
from core import config as C2, metrics as M2  # noqa: E402
from viz import pdf_charts as PC2             # noqa: E402

_t = L2.load_all()
_secs2 = S2.build(_t, {})
_f2 = M2.funnel(_t)
_bi2 = max(int(_f2.index[_f2.is_bottleneck][0]), 1)
_g2 = M2.funnel_by(_t, C2.DIMS[0], _f2.step.iloc[_bi2 - 1], _f2.step.iloc[_bi2])
_ch2 = {"funnel": PC2.funnel_png(_f2), "device": PC2.device_png(_g2),
        "experiments": PC2.experiments_png(M2.experiment_results(_t))}
_p2 = _P(_tf.gettempdir()) / "test_leak_check.pdf"
_p2.write_bytes(TP2.build_pdf(_secs2, _ch2))
_txt = "".join(pg.extract_text() or "" for pg in _pypdf.PdfReader(str(_p2)).pages)

check(len(_txt) > 1000, "PDF 에서 텍스트를 뽑을 수 있다", f"{len(_txt):,}자")
check(_txt.count(chr(0xFFFD)) == 0, "한글이 깨지지 않는다 (대체문자 0개)")
# 2026-09-05: PDF 를 다시 짜면서 **목차에도** 빈 장을 표시하게 했다.
#   ("작성되지 않음" 이 목차 3 + 본문 3 = 6회)
#   숫자를 3 으로 박아 뒀더니 검사가 먼저 걸렸다 — 고정 숫자는 화면이 바뀌면
#   같이 낡는다. **빈 장 수에서 세는** 쪽으로 바꾼다.
_empty = sum(1 for x in _secs2 if x["kind"] == "human"
             and not (x.get("body") or "").strip())
check(_txt.count("작성되지 않음") == _empty * 2,
      "빈 장이 목차와 본문에 각각 찍힌다",
      f"{_txt.count('작성되지 않음')}회 (빈 장 {_empty}개 × 2)")

# ★ 감춘 실험 **주변만** 잘라서 본다. 문서 전체에서 숫자를 찾으면
#   EXP-001(감추지 않은 실험)의 값이 걸려 오탐이 난다 —
#   2026-09-04 에 실제로 그렇게 헛짚었다.
_D = chr(92) + "d"
_S_ = chr(92) + "s"
_DOT = chr(92) + "."
_EFFECT = [
    ("p" + _S_ + "*=" + _S_ + "*0" + _DOT + _D + "+", "p값"),
    (_D + "+" + _DOT + _D + "+%" + _S_ + "*→", "전후 비율"),
    (chr(92) + "[-?" + _D + "+" + _DOT + _D + "+,", "신뢰구간"),
    ("상대" + _S_ + "*[-+]?" + _D, "상대 효과"),
]
for _r in M2.experiment_results(_t):
    if _r["verdict"] != "무효":
        continue
    _i = _txt.find(_r["id"])
    _seg = _txt[_i:_i + 420] if _i >= 0 else ""
    _hits = [n for pat, n in _EFFECT if _re3.search(pat, _seg)]
    check(not _hits, f"  · {_r['id']} 효과 수치가 PDF 로 새지 않는다",
          str(_hits) if _hits else "")
    check(_r["id"] in _txt, f"  · {_r['id']} 은 사유와 함께 문서에 남는다")

# 이메일 초안도 같이 본다
_blob = _re3.sub("<[^>]+>", " ", S2.email_draft(_t, _secs2).get("html", ""))
for _r in M2.experiment_results(_t):
    if _r["verdict"] != "무효":
        continue
    _i = _blob.find(_r["id"])
    _seg = _blob[_i:_i + 300] if _i >= 0 else ""
    _hits = [n for pat, n in _EFFECT if _re3.search(pat, _seg)]
    check(not _hits, f"  · {_r['id']} 효과 수치가 메일 초안으로 새지 않는다",
          str(_hits) if _hits else "")


print("\n4-4. 발송 전 점검이 게이트 3을 잠그는가 (Day4 프롬프트 8·9)")
# 게이트 3은 되돌릴 수 없다. 그래서 **여기서 걸러야 한다.**
# 사람이 매번 기억해서 하는 점검은 언젠가 건너뛴다 — 코드로 박는다.
at.switch_page("pages/3_리포트.py").run()

_pf_empty = S2.preflight(L2.load_all(), S2.build(L2.load_all(), {}))
check(not all(c["ok"] for c in _pf_empty),
      "사람 장이 비면 점검이 걸린다",
      " · ".join(c["name"] for c in _pf_empty if not c["ok"]))
check(not any("확인 문구" in str(x.label) for x in at.text_input),
      "  · 걸린 동안 확인 문구 칸이 열리지 않는다")

_human = {
    "2. 배경": "납기 준수율이 경고선에 붙어 있어 어디에서 밀리는지 확인하려 했다.",
    "6. 해석": "고객사별 납기 준수율이 갈린다. 원인은 이 데이터로 가릴 수 없다.",
    "8. 제안": "D사 착수 시점을 먼저 본다. 색상 묶음 순서 변경은 하지 않는다.",
}
_pf_full = S2.preflight(L2.load_all(), S2.build(L2.load_all(), _human))
check(all(c["ok"] for c in _pf_full), "세 장을 채우면 점검이 통과한다",
      f"{sum(c['ok'] for c in _pf_full)}/{len(_pf_full)}")

# ★ 자가검증 — 인과 표현을 심으면 점검이 실제로 막는가
_bad_human = dict(_human)
_bad_human["6. 해석"] = "D사 물량이 몰리기 때문에 납기 준수율이 낮다."
_pf_bad = S2.preflight(L2.load_all(), S2.build(L2.load_all(), _bad_human))
check(not all(c["ok"] for c in _pf_bad),
      "  · 인과 표현을 심으면 점검이 막는다 (자가검증)",
      " · ".join(c["name"] for c in _pf_bad if not c["ok"]))

# 점검 항목이 통째로 사라지지 않았는지 — 개수를 고정한다
check(len(_pf_full) == 5, "점검 항목이 5개다", f"{len(_pf_full)}개")


print("\n4-5. 사람이 쓴 장이 새로고침을 넘어 남는가 (2026-09-05)")
# ⚠️ 2026-09-05: st.session_state 는 메모리뿐이라 서버를 다시 켜면
#    사람이 쓴 배경·해석·제안이 **통째로 사라졌다.** 실제로 날아갔다.
#    이 앱에서 가장 값진 것이 사람이 쓴 장인데 가장 약하게 담겨 있었다 —
#    자동화하지 않는 이유가 "틀렸을 때 누가 책임지는가"이고, 그래서
#    사람이 시간을 들여 쓴다. 그 글이 새로고침 한 번에 사라지면
#    **다음부터 아무도 안 쓴다.**
from core import gates as _G                     # noqa: E402

_draft = _G.C.DRAFTS_DIR / "human.json"
_backup = _draft.read_text(encoding="utf-8") if _draft.exists() else None
try:
    if _draft.exists():
        _draft.unlink()
    _at3 = AppTest.from_file("app.py", default_timeout=300).run()
    _at3.switch_page("pages/3_리포트.py").run()
    _at3.radio[0].set_value("6. 해석").run()
    _글 = "검사용 해석 문장. 원인은 이 데이터로 가릴 수 없다."
    _at3.text_area(key="h_6. 해석").set_value(_글).run()
    click(_at3, "저장")
    check(_draft.exists(), "저장을 누르면 파일로 남는다")

    # 새 세션 = 서버 재시작
    _at4 = AppTest.from_file("app.py", default_timeout=300).run()
    _at4.switch_page("pages/3_리포트.py").run()
    check(_at4.session_state.human.get("6. 해석") == _글,
          "  · 새 세션에서 그대로 되살아난다")

    # ★ 데이터셋이 바뀌면 남의 글이다 — 숫자가 달라진 리포트에 옛 해석이
    #   붙으면 사실과 다른 문서가 된다
    import json as _json
    _d = _json.loads(_draft.read_text(encoding="utf-8"))
    _d["dataset"] = "다른 데이터셋"
    _draft.write_text(_json.dumps(_d, ensure_ascii=False), encoding="utf-8")
    check(_G.load_human()[0] == {},
          "  · 데이터셋이 다르면 안 불러온다 (자가검증)")
finally:
    if _backup is not None:
        _draft.write_text(_backup, encoding="utf-8")
    elif _draft.exists():
        _draft.unlink()


print("\n5. 아카이브")
at.switch_page("pages/4_아카이브.py").run()
check(click(at, "지금 데이터로 재계산해 비교") and not at.exception, "재현")

print("\n6. 게이트 3은 되돌릴 수 없다")
from core import gates    # noqa: E402
r = gates.new_run()
gates.pass_gate(r, 2, "")
gates.pass_gate(r, 3, "")
check(gates.revert_gate(r, 2) is True, "게이트2는 되돌릴 수 있다")
check(gates.revert_gate(r, 3) is False, "게이트3은 되돌릴 수 없다")

print(f"\n{'모두 통과' if ok else '실패 있음'}")
sys.exit(0 if ok else 1)
