# -*- coding: utf-8 -*-
"""검증.

검증은 **자동으로 통과시키지 않는다.** 결과를 사람 앞에 놓고 게이트에서 판단하게 한다.
경고를 앱이 마음대로 무시하면, 사람은 무엇을 승인했는지 모른 채 승인하게 된다.

판정 3종:

  ok    통과
  warn  경고 — **정상일 수도 있다. 사람이 판단한다.**
  block 차단 — 이 상태로는 분석할 수 없다.

────────────────────────────────────────────────────────────────────
차단과 경고를 가르는 것은 한 질문이다.

    이 규칙이 깨진 채로 계산하면 값이 틀리는가?
        틀린다              → block
        해석만 조심하면 된다 → warn

차단을 늘리면 안전해 보이지만, 실무 데이터는 늘 어딘가 깨져 있어서
앱이 아무것도 못 돌리게 된다. **차단은 "이대로 계산하면 확실히 틀리는 것"에만 건다.**
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import pandas as pd

from core import config as C
from core.load import to_dt
from core.todo import todo


def _r(name, level, msg, detail=""):
    """검증 결과 한 줄. 그대로 쓴다."""
    return {"name": name, "level": level, "msg": msg, "detail": detail}


def profile(t: dict) -> pd.DataFrame:
    """적재 직후 개요. 게이트 1에서 사람이 보는 화면.

    **그대로 쓴다.** 어느 도메인이든 행수·컬럼·기간·결측은 먼저 본다.
    """
    rows = []
    for name, df in t.items():
        # 2026-09-01 — 골격 원본은 `_date` 접미사와 `year_month` 만 찾았다.
        # 우리 컬럼은 수주일·이벤트일·검사일·생산일자라 하나도 안 걸려
        # 프로파일의 '기간' 칸이 전부 비었고, 프롬프트 5의 확인할 것
        # ("모든 테이블이 기간 안에 있는가")을 화면에서 답할 수 없었다.
        # ① config.VALIDATION 의 관측 컬럼을 먼저 보고 ② datetime 형 ③ 원래 규칙 순.
        date_col = (C.VALIDATION["날짜범위"]["관측컬럼"].get(name)
                    or next((c for c in df.columns if df[c].dtype.kind == "M"), None)
                    or next((c for c in df.columns
                             if c.endswith("_date") or c == "year_month"), None))
        span = ""
        if date_col is not None and date_col in df.columns:
            s = to_dt(df[date_col])
            span = f"{s.min():%Y-%m-%d} ~ {s.max():%Y-%m-%d}" if s.notna().any() else ""
        rows.append({
            "테이블": name, "행수": len(df), "컬럼": df.shape[1],
            "기간": span,
            "결측 컬럼": int(df.isna().any().sum()),
            "메모리(MB)": round(df.memory_usage(deep=True).sum() / 1e6, 1),
        })
    return pd.DataFrame(rows)


def run_checks(t: dict) -> list[dict]:
    """정합성 검증. 결과는 게이트 1에서 사람에게 보여준다.

    ★ Day1 실습 D에서 채웁니다. **규칙 3건**을 직접 씁니다.

        1. 행 수      — 비어 있거나 예상보다 크게 다르면?
        2. 필수 컬럼  — 계산에 꼭 필요한 컬럼이 있는가?
        3. 날짜 범위  — config.PERIOD 를 벗어난 데이터가 있는가?

    각 규칙마다 물어라: **이게 깨지면 계산이 틀리는가, 해석만 조심하면 되는가.**
    그 답이 block 과 warn 을 가른다.

    아래 reference_checks_telecom() 에 통신사에서 쓴 12건이 그대로 있다.
    읽어보고 **내 데이터에 맞는 것만** 가져다 고쳐 쓴다. 대부분은 안 맞는다.

    다 쓰고 나면 **정상 파일을 일부러 망가뜨려 넣어 본다.**
    컬럼 하나를 지우거나 날짜를 한 해 옮긴다. 차단이 뜨고 게이트 버튼이
    비활성되는 것까지 눈으로 봐야 한다.
    **경고만 띄우고 진행되면 그 검증은 없는 것과 같다.**

    반환: [_r(이름, 레벨, 메시지, 상세), ...]
    """
    V = C.VALIDATION
    out = []

    # ── 규칙 1. 행 수 — 기준 적재량 대비 ──────────────────────────
    #    0행은 확실히 차단이다. 문제는 그 위인데, "직전 적재의 절반"을 선으로 잡았다.
    r = V["행수"]
    worst, rows = [], []
    for name, df in t.items():
        base = r["기준행"].get(name)
        if not base:
            continue
        ratio = len(df) / base
        # ★ 양쪽을 본다 (2026-09-05). 줄어드는 것만 보다가 order_events 가
        #   +81% 늘어난 것을 놓쳤다 — 중복 적재면 분모가 부풀어 모든 비율이
        #   틀리는데, 줄어들 때와 정확히 같은 크기의 사고다.
        lv = ("block" if ratio < r["차단비율"]
              else "warn" if ratio < r["경고비율"] else
              "warn" if (base >= r.get("상한적용최소", 0)
                         and ratio > r.get("경고상한", float("inf"))) else "ok")
        rows.append(f"{name} {len(df):,}행 (기준 {base:,} 대비 {ratio*100:.0f}%)")
        if lv != "ok":
            방향 = "늘었다" if ratio > 1 else "줄었다"
            worst.append((lv, f"{name} {len(df):,}행 / 기준 {base:,} = "
                              f"{ratio*100:.0f}% ({방향})"))
    level = ("block" if any(l == "block" for l, _ in worst)
             else "warn" if worst else "ok")
    out.append(_r(
        "행 수",
        level,
        "; ".join(m for _, m in worst) if worst
        else f"{len(rows)}개 테이블 {sum(len(d) for d in t.values()):,}행 — 기준 대비 정상",
        r["근거"] + ("  |  " + "; ".join(rows) if worst else "")))

    # ── 규칙 2. 필수 컬럼 — 없으면 그 계산이 아예 안 된다 ─────────
    r = V["필수컬럼"]
    missing = []
    for name, cols in r["컬럼"].items():
        df = t.get(name)
        if df is None:
            missing.append(f"{name}(테이블 자체 없음)")
            continue
        gone = [c for c in cols if c not in df.columns]
        if gone:
            missing.append(f"{name}: {', '.join(gone)}")
    out.append(_r(
        "필수 컬럼",
        r["판정"] if missing else "ok",
        "없는 컬럼 — " + " / ".join(missing) if missing
        else f"{len(r['컬럼'])}개 테이블의 필수 컬럼 "
             f"{sum(len(c) for c in r['컬럼'].values())}개 전부 있음",
        r["근거"]))

    # ── 규칙 3. 날짜 범위 — 관측 컬럼만 본다 ──────────────────────
    #    납기일은 미래여야 정상이라 이 규칙에서 뺐다. 예정을 관측처럼 검사하면
    #    "아직 안 온 납기" 10,293건이 전부 오류로 잡힌다.
    r = V["날짜범위"]
    lo, hi = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
    # ★ 비율을 **테이블마다 따로** 낸다. 2026-09-01 이전에는 전체 행 수로 나눴는데,
    #   그러면 작은 테이블이 **통째로 틀려도 경고에 그친다.**
    #   실측: experiment_assignments(19,064행)는 날짜가 100% 어긋나도
    #   전체 915,263행 대비 2.08% 라 차단선 5%를 못 넘었다.
    #   이 규칙의 근거는 "월 분모가 실제로 틀어진다"이고, 분모는 테이블마다 따로 선다.
    #   → tests/test_guards.py 2절이 이걸 잡았다.
    bad, worst = [], 0.0
    for name, col in r["관측컬럼"].items():
        df = t.get(name)
        if df is None or col not in df.columns or len(df) == 0:
            continue
        d = to_dt(df[col])
        n = int(((d < lo) | (d > hi)).sum())
        if n:
            ratio = n / len(d)
            worst = max(worst, ratio)
            bad.append((ratio, f"{name}.{col} {n:,}건 ({ratio*100:.2f}%) "
                               f"— 실제 {d.min().date()} ~ {d.max().date()}"))
    out.append(_r(
        "날짜 범위",
        "block" if worst > r["차단비율"] else "warn" if bad else "ok",
        "; ".join(m for _, m in sorted(bad, reverse=True)) if bad
        else f"관측 컬럼 {len(r['관측컬럼'])}개 전부 "
             f"{C.PERIOD[0]} ~ {C.PERIOD[1]} 안에 있음",
        r["근거"]))

    # ── 규칙 4. 참조 무결성 — 조인이 실제로 이어지는가 ────────────
    #    ★ 강사 레퍼런스 검증 7번을 우리 키로 옮긴 것. 교안이 "읽고 내 데이터에
    #      맞는 것만 가져다 쓰라"던 목록에서 실제로 가져왔다.
    #
    #    규칙 1~3은 **파일의 모양**만 본다. 그래서 "이름은 맞고 내용이 다른 파일"이
    #    통과한다 — 강사 배포본의 통신사 experiments.parquet 이 실제로 통과했다.
    #    키를 맞춰 봐야 걸린다.
    r = V.get("참조무결성")
    if r:
        broken_fk, worst_fk = [], 0.0
        for child, ckey, parent, pkey in r["관계"]:
            cdf, pdf_ = t.get(child), t.get(parent)
            if cdf is None or pdf_ is None:
                continue
            if ckey not in cdf.columns or pkey not in pdf_.columns:
                continue          # 컬럼 자체가 없으면 규칙 2가 이미 잡는다
            keys = pd.Series(cdf[ckey]).astype(str)
            parent_keys = set(pd.Series(pdf_[pkey]).astype(str))
            n = int((~keys.isin(parent_keys)).sum())
            if n:
                ratio = n / len(keys)
                worst_fk = max(worst_fk, ratio)
                broken_fk.append(
                    (ratio, f"{child}.{ckey} → {parent} 에 없는 키 "
                            f"{n:,}건 ({ratio*100:.2f}%)"))

        # 부모에만 있고 자식이 하나도 안 붙은 것 — 끊어진 게 아니라 '안 쓰임'이라 경고
        idle = []
        for parent, pkey, child, ckey in r.get("고아부모", []):
            pdf_, cdf = t.get(parent), t.get(child)
            if pdf_ is None or cdf is None:
                continue
            if pkey not in pdf_.columns or ckey not in cdf.columns:
                continue
            used = set(pd.Series(cdf[ckey]).astype(str))
            unused = sorted(set(pd.Series(pdf_[pkey]).astype(str)) - used)
            if unused:
                idle.append(f"{parent} 에 정의됐지만 {child} 에 한 건도 없는 "
                            f"{pkey} {len(unused)}개 ({', '.join(unused[:4])})")

        lv = ("block" if worst_fk > r["차단비율"]
              else "warn" if (broken_fk or idle) else "ok")
        msg = "; ".join(m for _, m in sorted(broken_fk, reverse=True)) or ""
        if idle:
            msg = (msg + "; " if msg else "") + "; ".join(idle)
        out.append(_r(
            "참조 무결성", lv,
            msg or f"조인 관계 {len(r['관계'])}건 전부 이어짐",
            r["근거"]))

    return out


def summarize(checks: list[dict]) -> dict:
    """통과·경고·차단을 센다. 차단이 하나라도 있으면 게이트를 못 넘는다.

    **그대로 쓴다.**
    """
    n = {"ok": 0, "warn": 0, "block": 0}
    for c in checks:
        n[c["level"]] += 1
    return {**n, "total": len(checks), "can_pass": n["block"] == 0}


# ══════════════════════════════════════════════════════════════════
# 참고 — 통신사 데이터에서 쓴 검증 12건
#
# **이 함수는 호출되지 않는다.** 읽고 필요한 것만 위 run_checks() 로 옮긴다.
# 대부분은 통신사 테이블·컬럼에 묶여 있어서 그대로는 안 돌아간다.
#
# 눈여겨볼 것은 규칙 자체가 아니라 **무엇을 block 으로 두고 무엇을 warn 으로
# 뒀는가**이다.
#
#   block  기간 정합성 · 퍼널 순서 · 신규 고객 일치 · 배정 중복 ·
#          중도절단 · 참조 무결성        ← 깨지면 계산이 틀린다
#   warn   월 커버리지 · 결측률 2건 · 응답률 · 표본 수 · 배정 균형
#                                        ← 정상일 수도 있다. 사람이 판단한다
# ══════════════════════════════════════════════════════════════════
def reference_checks_telecom(t: dict) -> list[dict]:
    out = []
    lo, hi = pd.Timestamp(C.PERIOD[0]), pd.Timestamp(C.PERIOD[1])
    cu, se, fe = t["customers"], t["sessions"], t["funnel_events"]
    um, asg, ad = t["usage_monthly"], t["experiment_assignments"], t["ad_spend"]

    # 1. 기간 — 기간이 어긋나면 조인에 구멍이 생긴다
    bad = []
    for label, s in [("sessions", se.session_date), ("funnel_events", fe.event_date),
                     ("ad_spend", ad.spend_date)]:
        d = to_dt(s)
        if d.min() < lo or d.max() > hi:
            bad.append(f"{label} {d.min().date()}~{d.max().date()}")
    out.append(_r("기간 정합성", "block" if bad else "ok",
                  "기간을 벗어난 테이블이 있습니다" if bad else
                  f"모든 테이블이 {C.PERIOD[0]} ~ {C.PERIOD[1]} 안에 있습니다",
                  "; ".join(bad)))

    # 2. 월 커버리지 — 빠진 달이 있어도 정상일 수 있다
    m = sorted(um.year_month.astype(str).unique())
    out.append(_r("월 커버리지", "ok" if len(m) == 12 else "warn",
                  f"{m[0]} ~ {m[-1]} ({len(m)}개월)"))

    # 3. 퍼널 역행 — 앞 단계를 안 거치고 뒤 단계에 온 대상
    piv = (fe.pivot_table(index="visitor_id", columns="step_order",
                          values="event_id", aggfunc="count").fillna(0) > 0)
    cols = sorted(piv.columns)
    viol = sum(int(((~piv[a]) & piv[b]).sum()) for a, b in zip(cols, cols[1:]))
    out.append(_r("퍼널 순서", "block" if viol else "ok",
                  f"단계 역행 {viol}건" if viol else "단계 역행 없음"))

    # 4. 신규 고객 = 최종 통과자
    paid = set(fe.loc[fe.funnel_step == C.FUNNEL_STEPS[-1], "visitor_id"])
    newc = set(cu.loc[cu.visitor_id.notna(), "visitor_id"])
    out.append(_r("신규 고객 일치", "ok" if newc == paid else "block",
                  f"신규 {len(newc):,}명 / 최종 통과 {len(paid):,}명"))

    # 5. 실험 배정 중복 — 한 대상이 두 번 배정되면 결과를 못 믿는다
    dup = int(asg.duplicated(["experiment_id", "visitor_id"]).sum())
    out.append(_r("배정 중복", "block" if dup else "ok",
                  f"중복 {dup}건" if dup else "중복 없음"))

    # 6. 중도절단 — 떠난 뒤의 기록이 있으면 데이터가 잘못됐다
    ch = cu[cu.is_churned][["customer_id", "churn_date"]].copy()
    ch["cm"] = to_dt(ch.churn_date).dt.strftime("%Y-%m")
    mg = um.merge(ch, on="customer_id", how="inner")
    after = int((mg.year_month.astype(str) > mg.cm).sum())
    out.append(_r("중도절단", "block" if after else "ok",
                  f"이탈 이후 사용 기록 {after}건" if after else
                  "이탈 이후 사용 기록 없음"))

    # 7. 참조 무결성 — 끊어진 참조가 있으면 조인에서 조용히 사라진다
    fk_bad = []
    if not set(um.customer_id) <= set(cu.customer_id):
        fk_bad.append("usage_monthly")
    if not set(fe.session_id) <= set(se.session_id):
        fk_bad.append("funnel_events")
    out.append(_r("참조 무결성", "block" if fk_bad else "ok",
                  f"끊어진 참조: {', '.join(fk_bad)}" if fk_bad else "모든 참조 정상"))

    # 8. 결측 — 경고로만 낸다. **구조적 결측은 오류가 아니다.**
    nn = int(cu.visitor_id.isna().sum())
    if nn:
        out.append(_r("visitor_id 결측", "warn",
                      f"고객 {len(cu):,}명 중 {nn:,}명({nn/len(cu)*100:.0f}%)이 "
                      f"퍼널 이력이 없습니다",
                      "기존 고객은 이번 기간 퍼널을 거치지 않았으므로 정상일 수 있습니다. "
                      "다만 퍼널 테이블과 INNER JOIN하면 이 인원이 전부 사라집니다."))

    # 9. 캠페인 결측 — 자연 유입은 캠페인이 없다
    cn = int(se.campaign_id.isna().sum())
    if cn:
        out.append(_r("campaign_id 결측", "warn",
                      f"세션 {len(se):,}건 중 {cn:,}건({cn/len(se)*100:.0f}%)에 "
                      f"캠페인이 없습니다",
                      "자연 유입(검색·직접 방문)은 캠페인이 없으므로 정상일 수 있습니다."))

    # 10. 응답률 — 응답자 평균은 전체 평균이 아니다
    st_ = t["support_tickets"]
    resp = st_.satisfaction_score.notna().mean()
    if resp < 0.5:
        out.append(_r("만족도 응답률", "warn",
                      f"응답률 {resp*100:.1f}% — 응답자 평균은 전체 만족도가 아닙니다",
                      "극단적 경험을 한 쪽이 더 많이 응답하는 경향이 있습니다. "
                      "이 경고는 리포트 7장 한계로 옮깁니다."))

    # 11. 표본 크기
    small = []
    for _, e in t["experiments"].iterrows():
        n = int((asg.experiment_id == e.experiment_id).sum())
        if n < C.MIN_SAMPLE:
            small.append(f"{e.experiment_id}({n:,})")
    out.append(_r("실험 표본", "warn" if small else "ok",
                  f"표본 부족: {', '.join(small)}" if small else
                  "모든 실험이 최소 표본을 넘습니다"))

    # 12. SRM — 실험 결과를 보기 전에 반드시 확인
    from core.metrics import srm_check
    broken = []
    for _, e in t["experiments"].iterrows():
        s = srm_check(asg, e.experiment_id)
        if not s["ok"]:
            broken.append(f"{e.experiment_id} ({s['ratio'][0]*100:.1f}:"
                          f"{s['ratio'][1]*100:.1f}, p={s['p']:.1e})")
    out.append(_r("실험 배정 균형(SRM)", "warn" if broken else "ok",
                  f"배정이 깨진 실험: {', '.join(broken)}" if broken else
                  "모든 실험의 배정이 균형입니다",
                  "배정이 깨진 실험은 어떤 효과가 나와도 해석할 수 없습니다. "
                  "결과를 쓰지 말고 재실험해야 합니다." if broken else ""))

    return out
