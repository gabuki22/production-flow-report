# -*- coding: utf-8 -*-
"""숫자 검산.

  py -X utf8 tests/test_metrics.py

test_app.py 는 **화면이 뜨는지**를 보고, 이 파일은 **값이 맞는지**를 본다.
둘은 다르다 — 틀린 값도 화면에는 잘 뜬다.

교안이 시킨 것: *"만들고 나서 반드시 손계산과 대조한다."*
대조표는 7주차 실측(2026-08-29)이다. 그때 손으로 세고 눈으로 확인한 값이라
여기 박아 두고, 코드를 고쳤을 때 이 값에서 벗어나면 잡히게 한다.

★ **검사기와 대상이 같은 식을 공유하면 함께 틀린다.**
  그래서 여기서는 metrics 의 함수를 다시 부르지 않고, 되도록
  **원본 데이터에서 직접** 세어 비교한다.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import config as C, load, metrics as M    # noqa: E402

ok = True


def check(cond, label, got=""):
    global ok
    print(f"  [{'PASS' if cond else 'FAIL'}] {label}" + (f"   {got}" if got else ""))
    ok = ok and bool(cond)


def near(a, b, tol):
    return abs(a - b) <= tol


t = load.load_all()
o, fe = t["orders"], t["order_events"]

# ── 1. 그레인 ─────────────────────────────────────────────────────
# 이 검사가 이 파일에서 가장 중요하다. 그레인이 틀리면 나머지가 전부 틀린다.
print("1. 그레인 — 발주 1건(수주ID)")

rows_by_event = (fe["이벤트구분"] == "출하").sum()
uniq_by_order = fe.loc[fe["이벤트구분"] == "출하", "수주ID"].nunique()
check(rows_by_event > uniq_by_order,
      "출하 이벤트 행 수 > 수주ID 고유 수 (재투입이 실재한다)",
      f"{rows_by_event:,}행 / {uniq_by_order:,}건")

# 행으로 세면 100%를 넘는다 — **넘는 순간 그레인이 틀린 것이다.**
n_first = (fe["이벤트구분"] == "발주접수").sum()
check(rows_by_event / n_first > 0 and uniq_by_order <= o["수주ID"].nunique(),
      "수주ID 고유값으로 세면 분모를 넘지 않는다",
      f"{uniq_by_order:,} ≤ {o['수주ID'].nunique():,}")

f = M.funnel(t)
check(f["n"].is_monotonic_decreasing, "퍼널이 단조 감소한다 (뒤 단계가 더 많을 수 없다)")
check((f["cum_rate"] <= 1.0).all(), "누적 전환율이 100%를 넘지 않는다",
      f"최대 {f['cum_rate'].max()*100:.1f}%")
check(M.funnel_skips(t) == 0, "앞 단계를 건너뛴 수주 0건 (진짜 퍼널이다)",
      f"{M.funnel_skips(t)}건")

# ── 2. 7주차 실측과 대조 ──────────────────────────────────────────
print("\n2. 2026-08-29 손계산 대조표")

EXPECT = {                       # (기대값, 허용오차)
    "발주접수 도달": (79_992, 0),
    "출하 도달":     (76_441, 0),
    "최종 누적":     (95.6, 0.1),      # %
    # ★ 2026-09-05 갱신 — **공정작업 한 덩어리를 6공정으로 쪼개고 재생성했다.**
    #   퍼널이 6단계 → 11단계가 되면서 값이 조금씩 움직였다:
    #     출하 도달   76,334 → 76,441   (공정별 통과율의 곱이 정확히 같지는 않다)
    #     납기 준수율 91.25 → 90.55     (단계가 늘어 소요일 분산이 누적된다)
    #     불량률      3.56 → 3.54       (불량을 붙이는 기준이 사출 도달분으로 바뀌었다)
    #     긴급품      4.55 → 4.45
    #
    #   ⚠️ **총 리드타임과 총 통과율은 예전과 같게 맞췄는데도 움직였다.**
    #      로그정규를 11번 뽑으면 6번 뽑을 때보다 꼬리가 길어지기 때문이다 —
    #      "합계를 맞췄으니 결과도 같겠지"가 틀린 자리다.
    "납기 준수율":   (90.55, 0.1),
    "불량률":        (3.54, 0.01),
    "긴급품 비율":   (4.45, 0.05),
}
check(int(f["n"].iloc[0]) == EXPECT["발주접수 도달"][0], "발주접수 도달",
      f"{int(f['n'].iloc[0]):,}")
check(int(f["n"].iloc[-1]) == EXPECT["출하 도달"][0], "출하 도달",
      f"{int(f['n'].iloc[-1]):,}")
check(near(f["cum_rate"].iloc[-1] * 100, *EXPECT["최종 누적"]), "최종 누적 전환율",
      f"{f['cum_rate'].iloc[-1]*100:.1f}%")

k = M.kpis(t)
for name, (want, tol) in [("납기 준수율", EXPECT["납기 준수율"]),
                          ("불량률", EXPECT["불량률"]),
                          ("긴급품 비율", EXPECT["긴급품 비율"])]:
    check(near(k[name]["value"], want, tol), name,
          f"{k[name]['value']:.2f} (기대 {want})")

# ── 3. 분모를 바꾸면 값이 갈린다 ──────────────────────────────────
# 7주차에 같은 지표가 여러 값으로 갈렸던 것. 코드가 **어느 분모를 쓰는지** 못박는다.
print("\n3. 납기 준수율 — 분모 4종")

d = M.order_facts(o, fe)
sh = d[d["출하완료"]]
by_ship_ok = sh.loc[~sh["납기미정"], "납기내출하"].mean() * 100   # 출하 · 납기 있음
by_due = d.loc[d["납기도래"], "납기내출하"].mean() * 100          # 납기 도래 전체 ← 우리 것
by_ship_all = sh["납기내출하"].mean() * 100                       # 출하 전체(결측 포함)
by_all = d["납기내출하"].mean() * 100                             # 전체 수주
print(f"      출하·납기있음 {by_ship_ok:.1f}%  >  납기 도래 {by_due:.1f}%  >  "
      f"출하 전체 {by_ship_all:.1f}%  >  전체 수주 {by_all:.1f}%")
check(by_ship_ok > by_due > by_ship_all > by_all,
      "네 값이 이 순서로 갈린다 (같은 지표 이름, 다른 숫자)")
check(near(k["납기 준수율"]["value"], by_due, 0.05),
      "우리가 쓰는 분모는 **납기 도래 전체** (굿하트 회피)")

# ★ 이 검사가 이 파일에서 두 번째로 중요하다.
#   순서가 단조롭지 않은 이유는 분모 크기가 아니라 **결측 처리**다.
#   '출하 전체'에는 납기 미정 7.0%가 전부 미준수로 깔려 있어서, 분모가 더 좁은데도
#   값이 더 낮게 나온다. 처음 이 파일을 썼을 때 "분모가 넓어질수록 낮아진다"고
#   단정했다가 여기서 걸렸다 — **분모를 바꾼 것보다 결측이 더 크게 움직였다.**
miss = int(sh["납기미정"].sum())
print(f"      납기 미정 {miss:,}건({miss/len(sh)*100:.1f}%)을 빼면 "
      f"{by_ship_all:.1f}% → {by_ship_ok:.1f}%  ({by_ship_ok-by_ship_all:+.1f}%p)")
check(by_ship_ok - by_ship_all > abs(by_ship_ok - by_due),
      "결측 처리의 영향(%p)이 분모 선택의 영향보다 크다",
      f"{by_ship_ok-by_ship_all:.1f}%p vs {abs(by_ship_ok-by_due):.1f}%p")

# ── 4. 코호트 — 안 자르면 진행 중인 것을 실패로 센다 ──────────────
print("\n4. 완주 코호트 61일")

mature = M.mature_ids(o)
check(0 < len(mature) < len(o), "코호트가 전체의 일부다",
      f"{len(mature):,} / {len(o):,}")
reach_last = set(M.first_reach(fe).pipe(
    lambda x: x.loc[x["이벤트구분"] == C.FUNNEL_STEPS[-1], "수주ID"]))
cut = len(reach_last & mature) / len(mature) * 100
nocut = len(reach_last) / len(o) * 100
print(f"      코호트 {cut:.1f}%  vs  안 자름 {nocut:.1f}%   차이 {cut-nocut:+.1f}%p")
check(cut > nocut, "코호트를 자르면 통과율이 올라간다 (착시가 제거된다)")

# ── 5. 유지 퍼널은 중첩이어야 한다 ────────────────────────────────
print("\n5. 유지 퍼널 — 단계가 중첩인가")

r = M.retention_funnel(t)
check(len(r) == len(C.RETENTION_STEPS), "RETENTION_STEPS 만큼 나온다")
check(r["n"].is_monotonic_decreasing, "각 단계가 앞 단계의 부분집합이다",
      " ≥ ".join(f"{v:,}" for v in r["n"]))

# ★ 교안 프롬프트 6 이 반드시 확인하라 한 것 —
#   "앞 단계를 거치지 않고 다음 단계에 나타난 대상이 몇 건인가.
#    많으면 이건 퍼널이 아니라고 말해줘."
d_ = M.order_facts(o, fe); d_ = d_[d_["완주"]]
# 단계 이름을 여기 박지 않고 config 에서 가져온다 — 단계를 바꿨을 때
# 검사만 옛 이름을 들고 있으면 KeyError 로 죽는다 (2026-09-02 실제로 겪음).
_unpaid = set(fe.loc[fe["이벤트구분"] == C.STAGE_UNPAID, "수주ID"])
_no = ~d_["수주ID"].isin(_unpaid)
masks = {"납기도래": d_["납기도래"],
         "미납없음": d_["납기도래"] & _no,
         "출하완료": d_["납기도래"] & _no & d_["출하완료"],
         "납기내출하": d_["납기도래"] & _no & d_["납기내출하"]}
names = [n for n, _ in C.RETENTION_STEPS]
skips = sum(int((masks[b] & ~masks[a]).sum()) for a, b in zip(names, names[1:]))
check(skips == 0, "앞 단계를 안 거치고 나타난 대상 0건 (퍼널로 성립한다)",
      f"{skips}건")

# ★ 이 퍼널의 값어치는 끝값이 아니라 **손실 분해**다. 두 손실의 합이
#   전체 손실과 맞는지 본다 — 어긋나면 단계가 중첩이 아니라는 뜻이다.
#   (2026-09-02: 전에는 "첫 구간 탈락 = 긴급품"을 검사했는데, 미납 단계를
#    끼우면서 성립하지 않는다 — 미납을 겪고도 납기 내 출하한 건이 있다)
a_, b_, c_ = (int(x) for x in r["n"])
check((a_ - b_) + (b_ - c_) == a_ - c_, "두 손실의 합 = 전체 손실",
      f"{a_-b_:,} + {b_-c_:,} = {a_-c_:,}")
# ★ 끝값과 납기 준수율은 **거의 같지만 같지 않다.** 분모가 다르다 —
#   KPI 는 납기 도래 전체(78,987), 유지 퍼널은 그중 완주 코호트만(74,424).
#   2026-09-02: "같다"고 단언했다가 이 검사가 잡았다. 0.06%p 차이다.
#   작다고 뭉개지 않고 **왜 다른지 아는 상태**로 둔다 — 교안: 분모가 다르면 값이 다르다.
gap = abs(c_ / a_ * 100 - k["납기 준수율"]["value"])
check(gap < 0.5, "끝값과 납기 준수율의 차이가 0.5%p 미만 (분모만 다르다)",
      f"{c_/a_*100:.2f}% vs {k['납기 준수율']['value']:.2f}%  차이 {gap:.2f}%p")
check(gap > 0, "그래도 **같지는 않다** — 코호트를 자른 쪽이 유지 퍼널이다")

# ── 6. 통계 계산기 자가검증 — **답을 아는 표본** ──────────────────
# 합성 실험 데이터에는 효과를 심지 않았다(하지도 않은 실험을 "성공"으로 만들지
# 않으려고). 그래서 계산기가 도는지는 여기서 확인한다.
print("\n6. _two_prop — 답을 아는 표본으로 되찾는가")

res = M._two_prop(sc=100, nc=1000, stt=150, nt=1000)      # 10% → 15%
check(near(res["rc"], 0.10, 1e-9) and near(res["rt"], 0.15, 1e-9), "비율 복원")
check(near(res["lift"], 0.5, 1e-9), "상대 효과 +50%", f"{res['lift']*100:+.1f}%")
check(res["p"] < 0.01, "5%p 차이는 유의하다", f"p={res['p']:.5f}")
check(res["lo"] < res["diff"] < res["hi"], "신뢰구간이 추정치를 감싼다")

same = M._two_prop(sc=100, nc=1000, stt=100, nt=1000)      # 차이 없음
check(same["p"] > 0.9 and same["lo"] < 0 < same["hi"],
      "차이가 없으면 구간이 0을 지난다", f"p={same['p']:.3f}")

tiny = M._two_prop(sc=5, nc=50, stt=8, nt=50)              # 표본이 작으면
check(tiny["p"] > 0.05, "표본이 작으면 같은 크기 차이도 유의하지 않다",
      f"p={tiny['p']:.3f}")

# ── 7. 못 믿을 조건 분기 ──────────────────────────────────────────
print("\n7. trust_check — 셋 다 걸리는가")

good = {"ok": True, "ratio": (0.5, 0.5), "p": 0.5}
bad = {"ok": False, "ratio": (0.62, 0.38), "p": 1e-100}
check(M.trust_check(good, C.MIN_SAMPLE + 1, C.MIN_EXP_DAYS + 1) is None,
      "다 통과하면 None")
check("배정" in (M.trust_check(bad, 9999, 99) or ""), "배정이 깨지면 잡는다")
check("표본" in (M.trust_check(good, 10, 99) or ""), "표본이 모자라면 잡는다")
check("기간" in (M.trust_check(good, 9999, 3) or ""), "기간이 안 차면 잡는다")
# ★ 교안 프롬프트 2 — "사유에는 실제 숫자를 넣어줘. '표본 부족'이 아니라
#   '표본 62건 (최소 200)' 처럼." 두루뭉술하면 사람이 판단할 수 없다.
r_ = M.trust_check(good, 10, 3) or ""
check("10" in r_ and str(C.MIN_SAMPLE) in r_, "사유에 실제 표본 수와 기준값이 둘 다 있다", r_[:46])
check("3일" in r_ and f"{C.MIN_EXP_DAYS}일" in r_, "사유에 실제 기간과 기준값이 둘 다 있다")
b_ = M.trust_check(bad, 9999, 99) or ""
check("%" in b_ or ":" in b_, "배정 사유에 실제 비율이 있다", b_[:46])
both = M.trust_check(good, 10, 3) or ""
check("표본" in both and "기간" in both, "걸린 사유를 **전부** 돌려준다")

# ── 8. 무효 실험은 지표를 계산하지 않는다 ─────────────────────────
print("\n8. 판정이 계산보다 먼저다")

for e in M.experiment_results(t):
    if e["verdict"] == "무효":
        check("rc" not in e and "lift" not in e,
              f"{e['id']} 무효 — 지표를 계산조차 하지 않았다")
check(any(e["verdict"] == "무효" for e in M.experiment_results(t)),
      "무효 분기가 실제로 돈다 (안 돌면 이 검사는 아무것도 안 본 것이다)")

# ── 8-1. 판정 순서 (Day3 실습 C) ──────────────────────────────────
# ★ 교안: "2번을 1번 뒤에 두고, 1번을 통과했다고 바로 성공으로 가지 마."
#   순서가 바뀌면 **가드레일이 무너진 실험이 성공으로 보고된다.**
#   화면으로는 안 보이므로 여기서 못박는다.
print("\n8-1. 판정 순서 — 주지표 → 가드레일 → 성공")


def verdict_of(diff_pp, p, guard_delta_pp):
    """판정 로직만 떼어내 시험한다. 실제 데이터에 없는 조합도 넣어 보려고."""
    moved = abs(diff_pp) >= C.EFFECT_MIN_PP
    sig = p < 0.05
    guard_bad = guard_delta_pp is not None and guard_delta_pp / 100 < -C.GUARDRAIL_TOLERANCE
    if not (moved and sig):
        return "효과 없음"
    if guard_bad:
        return "주의 필요"
    return "성공" if diff_pp > 0 else "악화"


check(verdict_of(0.5, 0.001, 0) == "효과 없음",
      "크기가 작으면 유의해도 효과 없음", "0.5%p · p=0.001")
check(verdict_of(5.0, 0.30, 0) == "효과 없음",
      "크면 우연과 구분 안 되면 효과 없음", "5.0%p · p=0.30")
check(verdict_of(5.0, 0.001, -5.0) == "주의 필요",
      "★ 주지표가 크게 좋아도 가드레일이 무너지면 주의 필요", "주지표 +5%p · 가드레일 -5%p")
check(verdict_of(5.0, 0.001, -1.0) == "성공",
      "가드레일이 허용 안이면 성공", "가드레일 -1%p (허용 -3%p)")
check(verdict_of(-5.0, 0.001, 0) == "악화", "주지표가 나빠지면 악화")

# 순서가 바뀌었다면 세 번째가 "성공"으로 나온다 — 그게 교안이 막으려는 사고다
check(verdict_of(5.0, 0.001, -5.0) != "성공",
      "  · 순서가 뒤집혔으면 이 검사가 실패한다")

# ── 8-2. (가)/(나) — 계산조차 안 하는가 (Day3 프롬프트 7) ────────
# 교안: "계산해 놓고 숨기는 것이 아니라, 못 믿으면 계산조차 하지 않는다.
#        손에 없으면 못 쓴다. 그게 설계다."
#   ⚠️ **화면으로는 (가)와 (나)가 구분되지 않는다** — 어느 쪽이든 숫자가 안 보인다.
#      그래서 결과 객체를 직접 뜯어 지표 키가 실제로 없는지 본다.
#      값이 변수에 들어 있으면 리포트·로그로 샌다(금요일에 실제로 그 일이 생긴다).
print("\n8-2. 무효 실험에 지표가 '없는가' — 감춘 게 아니라")

METRIC_KEYS = {"rc", "rt", "diff", "lo", "hi", "p", "lift",
               "nc", "nt", "assignments", "outcome", "guard"}
void = [r for r in M.experiment_results(t) if r["verdict"] == "무효"]
check(len(void) > 0, "무효 실험이 실제로 있다 (없으면 이 절은 아무것도 안 본다)",
      f"{len(void)}건")
for r in void:
    leaked = sorted(METRIC_KEYS & set(r))
    check(not leaked, f"{r['id']} — 지표 키가 객체에 없다", str(leaked) if leaked else "0개")

# 조건 값은 **있어야 한다.** 교안: 표본 수·기간·배정 비율은 보여주는 쪽이다.
for r in void:
    check("srm" in r and "days" in r, f"{r['id']} — 조건 값(배정·기간)은 남아 있다")

# 통과한 실험에는 지표가 있어야 한다 — 없으면 반대로 다 감춘 것이다
okr = [r for r in M.experiment_results(t) if r["verdict"] != "무효"]
check(all("rc" in r for r in okr), "통과한 실험에는 지표가 있다",
      f"{len(okr)}건")

# ── 8-3. 유효 구간 (Day3 프롬프트 10) ────────────────────────────
# 교안 부록 C — 관측 기간이 다른 것을 나란히 두지 않는다.
#   MIN_SAMPLE 은 절대 건수라 **데이터 시작 경계를 못 잡는다**(첫 달 115 > 100).
#   중앙값 대비 비율로 자른다.
print(chr(10) + "8-3. 유효 구간 — 분모가 얇은 달을 뺐는가")

vp = M.valid_period(t)
mm = M.monthly(t)
check(vp["뺀달"] > 0, "얇은 달이 실제로 잘렸다 (0이면 이 규칙은 아무것도 안 한다)",
      f"{vp['뺀달']}개월: {vp['뺀목록']}")
check(int(mm["분모"].min()) >= vp["중앙분모"] * C.THIN_MONTH_RATIO,
      "남은 달은 전부 중앙값의 70% 이상",
      f"최소 {int(mm['분모'].min()):,} ≥ {vp['중앙분모']*C.THIN_MONTH_RATIO:,.0f}")
_chg = mm["분모"].pct_change().dropna().abs()
check(_chg.max() < 0.5, "전월 대비 분모 급변(50%+)이 없다",
      f"최대 {_chg.max()*100:.0f}%")
check(len(mm) >= 3, "자르고도 추이를 볼 달이 남는다", f"{len(mm)}개월")

# ── 9. 임계값 방향 ────────────────────────────────────────────────
# 불량률은 **높을수록 나쁘다.** 부등호가 뒤집히는 유일한 자리라 실수하기 쉽다.
print("\n9. status_of — 방향이 반대인 지표")

check(M.status_of("납기 준수율", 95) == "ok", "납기 95% → 정상")
check(M.status_of("납기 준수율", 85) == "warn", "납기 85% → 경고")
check(M.status_of("납기 준수율", 70) == "block", "납기 70% → 위험")
check(M.status_of("불량률", 3.0) == "ok", "불량 3.0% → 정상")
# ★ 긴급품 비율·지연 출하율도 **높을수록 나쁘다.** 방향 목록에 없으면 색이 반대로 뜬다
#   (교안 실습 D: "방향을 적는 것을 잊지 마십시오").
#   2026-09-02: 전에는 "임계값 미설정 → ok" 를 검사했는데, 임계값을 넣자 이 검사가
#   FAIL 로 잡혔다. **검사가 옛 전제를 들고 있으면 사실이 바뀐 것을 알려준다.**
for nm in ("긴급품 비율", "지연 출하율"):
    check(nm in C.THRESHOLDS, f"{nm} 임계값이 설정돼 있다",
          str(C.THRESHOLDS.get(nm, "없음")))
    check(M.status_of(nm, 9.9) == "ok", f"{nm} 9.9% → 정상")
    check(M.status_of(nm, 10.1) == "block", f"{nm} 10.1% → 위험 (선을 넘으면 갈린다)")

# ★ 지표 카드 전부에 임계값이 있는가 — 하나라도 비면 그 카드는 **무조건 초록**이다.
_k = M.kpis(t)
_no = [n for n in _k if n not in C.THRESHOLDS]
check(not _no, "지표 카드 전부에 임계값이 있다", f"없는 것: {_no}" if _no else f"{len(_k)}/{len(_k)}")
check(M.status_of("불량률", 4.5) == "warn", "불량 4.5% → 경고")
check(M.status_of("불량률", 6.0) == "block", "불량 6.0% → 위험")

# ── 10. 재현 — 같은 입력이면 같은 결과 ────────────────────────────
print("\n10. 재현")

f2 = M.funnel(t)
check(f["n"].tolist() == f2["n"].tolist(), "두 번 돌려도 같은 값이다")
check(not any("now" in str(v).lower() for v in [C.TODAY]),
      "기준일이 고정값이다 (현재 시각을 쓰지 않는다)", f"TODAY={C.TODAY}")

# ★ 교안 고정 조항 — "계산 경로에 현재 시각을 넣지 않는다."
#   같은 입력에 같은 결과가 나와야 보고에 쓸 수 있다.
#   손으로 확인하면 다음 사람이 또 확인해야 하므로 검사로 박는다.
import re as _re                                          # noqa: E402
import tokenize as _tk, io as _io                         # noqa: E402
# ⚠️ 토큰을 걷어 이으면 `datetime . now` 처럼 점 둘레에 공백이 생긴다.
#    공백을 허용하지 않으면 **검사가 아무것도 못 잡는다**
#    (2026-09-10 자가검증에서 드러났다).
NOW = (r"datetime\s*\.\s*now|Timestamp\s*\.\s*now|"
       r"date\s*\.\s*today|time\s*\.\s*time")
ROOT = Path(__file__).resolve().parent.parent


def _code_only(src: str) -> str:
    """주석과 문자열을 걷어낸 **실행되는 코드만** 돌려준다.

    ⚠️ 소스를 통째로 훑으면 *"`datetime.now()` 를 쓰지 않는다"* 라고 적은
      **주석이 검사에 걸린다** — 규칙을 설명하는 글이 규칙을 어긴 꼴이다.
      2026-09-10 에 실제로 걸렸고, 그때 고를 수 있는 길은 둘이었다:
      주석에서 그 말을 지우거나, 검사가 코드만 보게 하거나.
      **주석을 지우면 왜 안 되는지가 사라지므로** 검사를 고쳤다.
    """
    out = []
    for tok in _tk.generate_tokens(_io.StringIO(src).readline):
        if tok.type in (_tk.COMMENT, _tk.STRING):
            continue
        out.append(tok.string)
    return " ".join(out)


for mod in ["core/metrics.py", "core/validate.py", "core/load.py"]:
    hits = _re.findall(NOW, _code_only((ROOT / mod).read_text(encoding="utf-8")))
    check(not hits, f"{mod} — 현재 시각을 쓰지 않는다", f"{len(hits)}곳")

# ★ **검사기를 꺼 본다** (규칙 12) — 진짜 호출을 심으면 잡히는가.
#   주석만 거르고 코드도 함께 걸러 버리면 이 검사는 영원히 통과한다.
check(bool(_re.findall(NOW, _code_only("x = datetime.now()  # 주석"))),
      "  · 코드에 심으면 잡힌다 (자가검증)")
check(not _re.findall(NOW, _code_only("# datetime.now() 를 쓰지 않는다")),
      "  · 주석에 있으면 안 잡힌다 (자가검증)")

# sections.py 는 **한 곳만** 허용한다 — 이메일 초안 footer 의 "생성 시각"이다.
# 표시용이라 숫자에 영향을 주지 않는다. 늘어나면 여기서 걸린다.
sec_src = (ROOT / "report/sections.py").read_text(encoding="utf-8")
sec_hits = _re.findall(NOW, sec_src)
check(len(sec_hits) == 1, "report/sections.py — 현재 시각은 1곳(초안 생성 시각)뿐",
      f"{len(sec_hits)}곳")
check("email_draft" in sec_src.split("datetime.now")[0].rsplit("def ", 1)[-1],
      "  · 그 1곳이 email_draft() 안에 있다 (계산 경로가 아니다)")


# ── 8-4. 판정 과정 기록 (Day3 프롬프트 12) ───────────────────────
# 화면이 "어디서 갈렸는가"를 `passed is False` 로 찾는다. 그런데 판정 플래그는
# numpy 비교에서 나와 `numpy.bool_` 이고, **`numpy.bool_(False) is False` 는
# False** 다. 값도 맞고 판정도 맞는데 라벨만 조용히 비는, 눈으로는 못 찾는 종류다.
# 2026-09-04 에 EXP-001 에서 실제로 났다.
print(chr(10) + "8-4. 판정 과정이 기록되고, 화면이 그것을 찾을 수 있는가")

_res = M.experiment_results(t)
check(all("steps" in r for r in _res),
      "실험마다 판정 단계가 남는다", f"{len(_res)}건")

_types = {type(s["passed"]).__name__ for r in _res for s in r["steps"]}
check(_types <= {"bool", "NoneType"},
      "passed 가 파이썬 bool/None 이다 (numpy.bool_ 이면 `is False` 가 안 걸린다)",
      " ".join(sorted(_types)))

# 실패한 실험은 **어디서 갈렸는지**를 찾을 수 있어야 한다
for r in _res:
    if r["verdict"] in ("성공",):
        continue
    stopped = next((s for s in r["steps"] if s["passed"] is False), None)
    check(stopped is not None,
          f"  · {r['id']} ({r['verdict']}) 는 갈린 물음을 찾을 수 있다",
          stopped["q"] if stopped else "못 찾음")

# 앞에서 걸리면 뒤는 **묻지 않은 것**으로 남아야 한다 — 통과로 읽히면 안 된다
_invalid = [r for r in _res if r["verdict"] == "무효"]
check(all(any(s["passed"] is None for s in r["steps"]) for r in _invalid),
      "무효 실험은 뒤 물음이 '묻지 않았다'로 남는다 (통과로 안 읽힌다)",
      f"{len(_invalid)}건")


# ── 8-5. 한계 절이 경고를 흘리지 않는가 (Day4 프롬프트 5·6) ───────
# 교안: "검증에서 경고가 났는데 한계에 없으면 그 경고는 사라진 것과 같다."
# 그래서 한계는 사람이 매번 쓰는 것이 아니라 **조립한다.** 조립이 실제로
# 전부를 담고 있는지는 눈으로 세면 놓친다 — 함수가 돌려주는 개수와 대조한다.
print("\n8-5. 한계 절이 재료를 흘리지 않는가")

from report import sections as _S           # noqa: E402
from core import validate as _V             # noqa: E402

_limits = _S._s7_limits(t)["body"]

_warns = [c for c in _V.run_checks(t) if c["level"] == "warn"]
check(all(w["name"] in _limits for w in _warns),
      "검증 경고가 전부 한계에 있다", f"{len(_warns)}건")

_void = [r for r in M.experiment_results(t) if r["verdict"] == "무효"]
check(all(r["id"] in _limits for r in _void),
      "판정 못 한 실험이 전부 한계에 있다", f"{len(_void)}건")

_vp = M.valid_period(t)
check(all(m in _limits for m, _ in _vp["뺀목록"]),
      "추이에서 뺀 달이 한계에 이름으로 있다", f"{len(_vp['뺀목록'])}달")

# ★ 조건이 붙은 항목은 데이터가 좋아지면 사라지지만, 이 셋은 분석의 성격이라
#   어떤 데이터에서도 사라지면 안 된다. 2026-09-04 에 앞 둘이 빠져 있었다.
for _phrase in ("관측 데이터이므로 인과를 주장할 수 없",
                "그보다 긴 주기의 변화는",
                "전부 합성입니다"):
    check(_phrase in _limits, f"  · 항상 넣는 문장: {_phrase[:20]}…")

# 감춘 실험의 **수치**는 한계에도 없어야 한다 (사유만 적는다)
check("p=0.1464" not in _limits and "95.98" not in _limits,
      "무효 실험의 효과 수치가 한계로 새지 않는다")


# ── 8-6. 문서에 박힌 수치가 코드와 갈리지 않는가 (2026-09-05) ────
# **문서는 조용히 낡는다.** 9/4 에 생성기를 고쳐 데이터를 다시 만들었는데
# CLAUDE.md·README 의 수치 4건이 옛 값 그대로 남아 있었다 —
# 납기 91.1(→91.3) · 긴급품 4.57%(→4.55) · 3,403건(→3,388) · 끝값 91.11(→91.28).
#
# 눈으로는 안 잡힌다. 숫자가 그럴듯해서 읽고도 넘어간다.
# 그래서 **코드가 내는 값을 문서에서 찾아** 없으면 FAIL 시킨다.
#
# ⚠️ 문서를 파싱하지 않는다. "이 값이 문서에 글자로 있는가"만 본다 —
#    파싱하면 문장을 바꿀 때마다 검사가 깨져서 결국 검사를 지우게 된다.
print("\n8-6. 문서 수치가 코드와 같은가")

_DOCS = {n: (ROOT / n).read_text(encoding="utf-8")
         for n in ("CLAUDE.md", "README.md")}

_r = M.retention_funnel(t)
_ch = M.urgent_stats(t)
_f = M.funnel(t)

# (값, 이름, **그 값을 싣는 문서**) — 어느 문서가 무엇을 싣는지 여기 적는다.
#
# ⚠️ 처음엔 "어느 문서엔가 있으면 통과"로 짰다가 약했다 — CLAUDE.md 를
#    망가뜨려도 README 에 값이 남아 통과했다. 둘이 같이 낡을 때만 잡히는데
#    **한쪽만 낡는 쪽이 더 흔하다.**
# ⚠️ 그다음 "그 지표 이름이 나오는 문서면 값도 있어야 한다"로 바꿨더니 오탐이 났다 —
#    README 는 납기 준수율을 *개념으로만* 언급하고 값은 안 싣는다.
#    **언급과 인용은 다르다.** 그래서 문서를 명시한다.
# ⚠️ 한계 — 여기 안 적은 문서에 값을 새로 쓰면 이 검사는 모른다.
_CLAIMS = [
    (f"{M.kpis(t)['납기 준수율']['value']:.1f}%", "납기 준수율", ["CLAUDE.md"]),
    (f"{M.kpis(t)['불량률']['value']:.2f}%", "불량률", ["CLAUDE.md"]),
    (f"{_ch['긴급률']:.2f}%", "긴급품 비율", ["CLAUDE.md", "README.md"]),
    (f"{_ch['긴급건']:,}건", "긴급품 건수", ["CLAUDE.md", "README.md"]),
    (f"{_r['cum_rate'].iloc[-1]*100:.2f}%", "유지 퍼널 끝값", ["CLAUDE.md"]),
    (f"{_f.cum_rate.iloc[-1]*100:.1f}%", "최종 출하율", ["CLAUDE.md"]),
]
for _val, _what, _where in _CLAIMS:
    _stale = [n for n in _where if _val not in _DOCS[n]]
    check(not _stale, f"  · {_what} {_val} — {' · '.join(_where)}",
          "낡음: " + " · ".join(_stale) if _stale else "")

# ★ 자가검증 — 한 문서만 낡아도 정말 잡는가
_probe = _DOCS["CLAUDE.md"].replace(f"{_ch['긴급률']:.2f}%", "99.99%")
check(f"{_ch['긴급률']:.2f}%" not in _probe,
      "  · 한 문서만 낡아도 잡는다 (자가검증)")


# ── 8-7. 유지 퍼널 두 손실의 **정체** (2026-09-05) ────────────────
# 화면이 두 손실에 이름을 붙인다. 그 이름이 사실인지 여기서 본다.
#
# ⚠️ 2026-09-05 에 ②를 "한 번에 갔는데도 늦은 것"이라 적었다가 **거짓이었다.**
#    실측하니 전부 검사 미도달 + 전부 미출하 — 늦게 나간 게 아니라 **안 나간** 것이다.
#    화면 문구는 코드로 확인되지 않으면 언제든 이렇게 어긋난다.
print("\n8-7. 유지 퍼널 두 손실의 정체")

_ev = t["order_events"]
_fr = M.first_reach(_ev)
_unpaid = set(_ev.loc[_ev["이벤트구분"] == C.STAGE_UNPAID, "수주ID"])
_검사 = set(_fr.loc[_fr["이벤트구분"] == C.PROCESS_STEPS[-1], "수주ID"])
_mat = M.order_facts(t["orders"], t["order_events"])
_mat = _mat[_mat["수주ID"].isin(M.mature_ids(t["orders"]))]
_due = _mat[_mat["납기도래"]]
_miss = _due[~_due["납기내출하"]]
_A = _miss[_miss["수주ID"].isin(_unpaid)]        # ① 미납확인 찍힘
_B = _miss[~_miss["수주ID"].isin(_unpaid)]       # ② 안 찍힘

check(len(_A) + len(_B) == len(_miss), "두 손실을 합치면 미준수 전체다",
      f"{len(_A):,} + {len(_B):,} = {len(_miss):,}")

# ① 은 "만들어졌는데 늦음" — 검사까지 간 것이 대부분이어야 이름이 맞다
_a_reached = _A["수주ID"].isin(_검사).mean()
check(_a_reached > 0.9, "  · ① 은 검사까지 간 것이다 (만들어졌는데 늦음)",
      f"{_a_reached*100:.1f}%")

# ② 는 "아직 안 만들어짐" — 검사 미도달 + 미출하여야 이름이 맞다
_b_notreached = (~_B["수주ID"].isin(_검사)).mean()
_b_unshipped = (~_B["출하완료"]).mean()
check(_b_notreached > 0.9, "  · ② 는 검사에 못 갔다 (아직 안 만들어짐)",
      f"{_b_notreached*100:.1f}%")
check(_b_unshipped > 0.9, "  · ② 는 출하도 안 됐다",
      f"{_b_unshipped*100:.1f}%")

# ★ 화면 문구가 이 사실과 맞는지 — 옛 문구가 남아 있으면 잡는다
_dash = (ROOT / "pages" / "2_대시보드.py").read_text(encoding="utf-8")
check("한 번에 갔는데도 늦었다" not in _dash,
      "  · 화면에 옛 설명('한 번에 갔는데도 늦었다')이 남아 있지 않다")


# ── 8-8. 표본 흔들림 shake() (2026-09-08 Day1 프롬프트 4) ──────────
# **한 건이 바뀌면 값이 얼마나 움직이는가.** 그 폭이 칸 사이 격차보다 크면
# 순위가 한 건으로 뒤집히므로 그 축으로는 결론을 낼 수 없다.
#
# ⚠️ 우리 실데이터에서는 이 규칙이 **한 번도 걸리지 않는다**(최소 칸 분모 2,502).
#    그래서 실데이터만으로 검사하면 **규칙이 죽어 있어도 전부 PASS 한다.**
#    일부러 깨진 표본을 넣고, 규칙을 꺼서 미검출까지 확인한다.
print("\n8-8. 표본 흔들림")

_g = pd.DataFrame({"축": ["a", "b"], "분모": [1000, 250],
                   "준수": [900, 200], "준수율": [0.90, 0.80]})
_s = M.shake(_g, "분모", "준수율")
check(near(_s["흔들림"].iloc[0], 0.1, 1e-9), "  · 손계산 1/1000 = 0.100%p",
      f"{_s['흔들림'].iloc[0]:.4f}")
check(near(_s["격차"].iloc[0], 10.0, 1e-9), "  · 격차 90−80 = 10.00%p")
check(bool(_s["결론가능"].iloc[0]), "  · 격차 > 흔들림 → 결론 가능")

# ★ 일부러 걸어 본다 — 안 잡히면 이 규칙은 장식이다
_bad = pd.DataFrame({"축": ["a", "b"], "분모": [40, 35],
                     "준수": [20, 17], "준수율": [0.500, 0.4857]})
_sb = M.shake(_bad, "분모", "준수율")
check(not bool(_sb["결론가능"].iloc[0]),
      "  · ★ 흔들림 > 격차를 잡는다 (일부러 걸어 봄)",
      f"격차 {_sb['격차'].iloc[0]:.2f} < 흔들림 {_sb['흔들림'].max():.2f}")
check("결론을 낼 수 없다" in M.shake_verdict(_sb, "축")["판정"],
      "  · 판정 문장이 사람에게 그렇게 말한다")

# ★ 규칙을 꺼 본다 — 끄면 미검출이어야 실제로 작동 중이었던 것이다
_tiny = pd.DataFrame({"축": ["a", "b"], "분모": [3, 500],
                      "준수": [1, 450], "준수율": [0.3333, 0.90]})
check(bool(M.shake(_tiny, "분모", "준수율")["건수로쓸것"].iloc[0]),
      f"  · 분모 3 → 건수로 쓴다 (기준 {C.MIN_COUNT_BASIS})")
_saved = C.MIN_COUNT_BASIS
C.MIN_COUNT_BASIS = 0
check(not M.shake(_tiny, "분모", "준수율")["건수로쓸것"].any(),
      "  · ★ 기준을 0으로 끄면 미검출 (자가검증)")
C.MIN_COUNT_BASIS = _saved

# 두 분해 함수 양쪽에 걸리는가 — 분모 컬럼 이름이 다르다(도달 / 분모)
_fb = M.shake(M.funnel_by(t, C.DIMS[0], "검사", "출하"), "도달", "전환율")
_mb = M.shake(M.metric_by(t, C.DIMS[0]), "분모", "준수율")
check(M.denom_of(_fb) == "도달" and M.denom_of(_mb) == "분모",
      "  · funnel_by·metric_by 양쪽에 걸린다")
check(bool(_mb["결론가능"].iloc[0]),
      "  · 실데이터 주지표 분해는 결론 가능",
      f"격차 {_mb['격차'].iloc[0]:.2f}%p > 흔들림 {_mb['흔들림'].max():.3f}%p")


# ── 8-9. 발견.md 가 앱과 같은 값을 말하는가 (2026-09-08 Day1) ──────
# 발견.md 는 제안서의 근거가 된다. **거기 적힌 값이 앱과 갈리면 제안 전체가 흔들린다** —
# 교안: *"제안서에서 숫자 하나가 틀리면 '다른 것도 확인해 봐야겠네요' 가 나오고 거기서 끝난다."*
#
# 8-6 과 같은 방법으로 문서에서 **글자로 찾는다.** 파싱하지 않는다.
#
# ⚠️ 검사 범위를 「발견」 절로 **자른다.** 내일 원인이 붙고 모레 제안이 붙는데,
#    문서 전체에 인과 표현 검사를 걸면 그때 제안 절이 통째로 걸린다.
#    (9/4 에 유출 검사를 문서 전체에 걸었다가 헛짚은 것과 같은 실수)
print("\n8-9. 발견.md ↔ 앱")

_F = ROOT / "발견.md"
if not _F.exists():
    check(False, "  · 발견.md 가 있다")
else:
    _doc = _F.read_text(encoding="utf-8")
    _head = _doc.split("## 못 쓰는 숫자")[0]      # 발견 절만

    def _has(val, what, where=None):
        check(str(val) in (where if where is not None else _doc),
              f"  · {what}", str(val))

    _k = M.kpis(t)
    for _n in ("납기 준수율", "불량률", "긴급품 비율", "지연 출하율"):
        _fmt = ".2f"
        _has(f"{_k[_n]['value']:{_fmt}}%", f"지표 {_n}")

    # 두 분모가 둘 다 적혀 있는가 — 하나만 적으면 어느 쪽인지 모른다
    _g = M.metric_by(t, C.DIMS[0])
    _has(f"{int(_g['분모'].sum()):,}", "분해 분모(완주&납기도래)")
    _has(f"{int(M.order_facts(t['orders'], t['order_events'])['납기도래'].sum()):,}",
         "카드 분모(납기도래)")

    # 발견 절의 칸 값 — 격차·비중·흔들림·크기가 전부 실측과 같은가
    for _dim, _cell in (("차종", "V6"), ("색상", "블루"), ("고객사", "D사")):
        _gg = M.shake(M.metric_by(t, _dim), "분모", "준수율")
        _r = _gg[_gg[_dim] == _cell].iloc[0]
        _gap = (_gg["준수율"].max() - _r["준수율"]) * 100
        _has(f"{int(_r['준수']):,} / {int(_r['분모']):,}", f"{_cell} 분자/분모", _head)
        _has(f"{_gap:.2f}%p", f"{_cell} 격차", _head)
        _has(f"{_r['비중']*100:.2f}%", f"{_cell} 비중", _head)
        _has(f"{_gap * _r['비중']:.3f}", f"{_cell} 격차x비중", _head)

    # ★ 발견 절에 원인·제안이 섞이지 않았는가 (오늘 것이 아니다)
    _BAN = ["때문에", "덕분에", "효과로", "입증되었", "증명되었", "확실히",
            "원인이다", "유발했다"]
    _hit = [w for w in _BAN if w in _head]
    check(not _hit, "  · ★ 발견 절에 인과 표현이 없다",
          "걸림: " + " · ".join(_hit) if _hit else "")

    # ★ 자가검증 — 인과 표현을 심으면 정말 걸리는가
    check(any(w in (_head + " 이것 때문에 늦었다") for w in _BAN),
          "  · ★ 심어 보면 걸린다 (자가검증)")

    # 「못 쓰는 숫자」 절이 비어 있지 않은가 — 교안: 비었으면 실습 D를 안 한 것
    _unusable = _doc.split("## 못 쓰는 숫자")[-1].split("## 확인한 정의")[0]
    check(_unusable.count("|") > 8, "  · 「못 쓰는 숫자」 절이 비어 있지 않다",
          f"표 칸 {_unusable.count('|')}")

    # 감춘 실험의 효과 수치가 발견으로 새지 않았는가
    _hidden = [r for r in M.experiment_results(t) if r.get("lift") is None]
    check(len(_hidden) >= 1 and all(str(r["id"]) in _doc for r in _hidden),
          "  · 감춘 실험이 「못 쓰는 숫자」에 이름으로 있다",
          " · ".join(r["id"] for r in _hidden))


# ── 도번 단위 대조 (2026-09-12 · 기쁨 "모든 기준은 도번으로") ────────────
print("\n도번 단위 — 발주 단위와 어긋나지 않는가")
_fp, _fo = M.funnel_parts(t), M.funnel(t)
check((_fp["멈춘발주"].iloc[1:].to_numpy() == _fo["drop"].iloc[1:].to_numpy()).all(),
      "  · funnel_parts 의 구간별 멈춘 발주 수 == funnel 의 빠짐 수 (11구간)",
      f"{int(_fp['멈춘발주'].sum()):,} vs {int(_fo['drop'].iloc[1:].sum()):,}")
check(int(_fp.iloc[0]["n"]) == _fp.attrs.get("도번전체") and (_fp["n"] + _fp["drop"] == _fp.attrs.get("도번전체")).all(),
      "  · 구간마다 멈춘 도번 + 안 멈춘 도번 = 도번 전체", f"{_fp.attrs.get('도번전체')}")
_mp, _mo = M.metric_by_parts(t, C.DIMS[1]), M.metric_by(t, C.DIMS[1])
_j2 = _mp.merge(_mo[[C.DIMS[1], "준수율"]].rename(columns={"준수율": "_발주"}), on=C.DIMS[1])
check(((_j2["발주가중준수율"] - _j2["_발주"]).abs() < 1e-9).all(),
      "  · metric_by_parts.발주가중준수율 == metric_by.준수율 (같은 재료)",
      f"최대 차이 {(_j2['발주가중준수율'] - _j2['_발주']).abs().max():.2e}")
check(((_j2["준수율"] - _j2["_발주"]).abs() * 100 < 0.5).all(),
      "  · 도번 평균과 발주 가중의 차이가 0.5%p 미만 (단위가 바뀌어도 결론이 안 바뀐다)",
      f"최대 {((_j2['준수율'] - _j2['_발주']).abs() * 100).max():.3f}%p")
check(int(_mp["도번"].sum()) == t["orders"]["제품도번"].nunique() or int(_mp["도번"].sum()) <= t["orders"]["제품도번"].nunique(),
      "  · 축별 도번 수 합이 전체 도번 수를 넘지 않는다", f"{int(_mp['도번'].sum())}")
_sk = M.surrogate_key_check(t)
check(_sk["정확도"] >= 0.99, "  · 대리 키(고객사+도번+수량+접수일) 정확도 ≥ 99% (notes/11)",
      f"{_sk['정확도'] * 100:.2f}% · 묶인 {_sk['묶인건수']}건")

print(f"\n{'모두 통과' if ok else '실패 있음'}")
sys.exit(0 if ok else 1)
