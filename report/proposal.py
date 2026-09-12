# -*- coding: utf-8 -*-
"""제안서 조립 — **결재 문서**다. 분석 문서가 아니다.

────────────────────────────────────────────────────────────────────
읽는 사람이 다르다.

    분석 문서   같은 분석을 하는 사람이 읽는다 → "어떻게 계산했나"
    제안서     결정 권한을 가진 사람이 읽는다 → "뭘 해야 하나 · 얼마짜리인가"

그래서 이 문서에는 **계산 과정이 들어가지 않는다.**
함수 이름·컬럼 이름·판정 로직은 부록으로도 넣지 않는다. 궁금하면 앱을 열면 된다.

가르는 질문은 하나 — **이 절을 채울 데이터 함수 이름을 지금 댈 수 있는가?**
    댈 수 있다 → 자동으로 쓴다 (현황 · 원인 · 규모 · 제안)
    판단이 든다 → 사람이 쓴다 (위험·철회 기준 / 요청)

★ **못 채우는 절은 만들지 않는다.** 자리를 비워 두는 것과 자리를 안 만드는 것은
  다르다 — 비워 두면 그 자리가 **그대로 인쇄된다.**
  (2026-09-09 판 에서는 빈 자리를 `todo` 로 남겼다. 오늘 규칙이 바뀌었다)

★ 절 제목·순서는 `config.PROPOSAL_SECTIONS` 에서 읽는다. 여기 박지 않는다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from core import config as C
# ★ 새로 만들지 않는다. 리포트에서 쓰는 그 검사를 그대로 가져온다 —
#   우리 BANNED 는 교안 기본 여섯 + 제조·품질 여섯이라 새로 만들면 뒤가 사라진다.
from report.sections import BANNED, check_phrasing  # noqa: F401  (재수출)
from viz import proposal_charts as PC

CARDS_PATH = C.ROOT / "제안카드.md"
BASIS_PATH = C.ROOT / "판단기준.md"

_FIELD = re.compile(r"^\|\s*\*\*(?P<k>[^*]+)\*\*\s*\|\s*(?P<v>.*?)\s*\|\s*$", re.M)
_CARD = re.compile(r"^##\s+제안\s*(?P<no>\d+)\s*—\s*(?P<title>.+?)\s*$", re.M)
_SIZE_N = re.compile(r"=\s*\*\*([\d,]+)건\*\*")
# 기대 효과 — 카드 「효과」 칸의 "좁히면 **N건**". **문서에 적을 값은 카드에서 읽는다.**
_EFFECT_N = re.compile(r"좁히면\s*\*\*([\d,]+)건\*\*")


def _effect_n(c: dict) -> int | None:
    m = _EFFECT_N.search(c.get("효과", ""))
    return int(m.group(1).replace(",", "")) if m else None


# ── 재료 읽기 — **읽기만 한다** ───────────────────────────────────
def parse_cards(path: Path | str | None = None) -> dict:
    """`제안카드.md` 를 딕셔너리로 읽는다. **고치지 않는다.**

    화면에서 값을 고치기 시작하면 카드와 화면 중 어느 것이 진짜인지 알 수 없게 된다.
    """
    p = Path(path) if path else CARDS_PATH
    if not p.exists():
        return {"path": str(p), "updated": None, "cards": [], "없음": True}

    text = p.read_text(encoding="utf-8")
    m = re.search(r"최종 갱신:\s*(\S+)", text)
    heads = list(_CARD.finditer(text))
    cards = []
    for i, h in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        block = re.split(r"^###\s", text[h.end():end], maxsplit=1, flags=re.M)[0]
        fields = {mm.group("k").strip(): mm.group("v").strip()
                  for mm in _FIELD.finditer(block)}
        cards.append({
            "no": int(h.group("no")), "title": h.group("title").strip(),
            # ⚠️ 칸을 늘리면 **여기도 늘린다.** 카드에만 넣고 이 목록을 안 고치면
            #    파서가 조용히 못 읽고 화면은 "값이 없다"고 말한다 — 카드에는 있는데.
            **{k: fields.get(k, "")
               for k in ("분류", "근거", "비용", "효과", "되돌림", "크기",
                         "확인")},
        })
    return {"path": str(p), "updated": m.group(1) if m else None,
            "cards": cards, "없음": False}


_DATE_H2 = re.compile(r"^##\s+(?P<date>\d{4}-\d{2}-\d{2}[^\n]*)$", re.M)
_H3 = re.compile(r"^###\s+(?P<h>.+?)\s*$", re.M)
_ROW_HEAD = re.compile(r"^\|\s*(?P<c>[^|]+?)\s*\|", re.M)

# ⚠️ **소제목이 한 가지가 아니다.** 날마다 말이 갈렸다 — 하나만 잡으면
#    조용히 최신 항목이 빠진다. 늘어나면 여기에 더한다.
BASIS_HEADS = ("오늘 내가 정한 것", "오늘 내린 결정")


def basis_decisions(path: Path | str | None = None, limit: int = 12) -> list[dict]:
    """`판단기준.md` 에서 결정 문장을 뽑는다. **최근 것이 앞.**"""
    p = Path(path) if path else BASIS_PATH
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8")
    blocks = list(_DATE_H2.finditer(text))
    out: list[dict] = []
    for i, b in enumerate(blocks):
        end = blocks[i + 1].start() if i + 1 < len(blocks) else len(text)
        seg = text[b.end():end]
        date = b.group("date").split("—")[0].strip()
        for h in _H3.finditer(seg):
            if not any(k in h.group("h") for k in BASIS_HEADS):
                continue
            nxt = _H3.search(seg, h.end())
            body = seg[h.end(): nxt.start() if nxt else len(seg)]
            for r in _ROW_HEAD.finditer(body):
                cell = r.group("c").strip()
                if (not cell or set(cell) <= set("-: ")
                        or cell in ("정한 것", "결정", "무엇을 · 왜", "왜")):
                    continue
                out.append({"날짜": date, "문장": cell.strip("*").strip()})
    out.reverse()
    return out[:limit]


def _by_kind(cards: list[dict], kind: str) -> list[dict]:
    return [c for c in cards if c.get("분류") == kind]


def biggest_card(cards: list[dict]) -> dict | None:
    """크기(격차 × 비중)가 가장 큰 카드.

    **근거 문장을 정규식으로 긁지 않는다** — 한 문장에 여러 칸의 숫자가 섞여
    짝이 어긋난다(2026-09-09 실제로 어긋났다). 카드의 `크기` 칸만 읽는다.
    """
    best, best_n = None, -1
    for c in cards:
        m = _SIZE_N.search(c.get("크기", ""))
        if m and (n := int(m.group(1).replace(",", ""))) > best_n:
            best, best_n = c, n
    return best


# ── 절 하나 만들기 ───────────────────────────────────────────────
def _sec(spec: dict, 문장: list[str], 차트: str = "", 표=None,
         사람: str = "") -> dict:
    """절 하나. **문장이 없으면 절을 만들지 않는다** (None 을 돌려준다).

    ★ `사람` 은 **그 절에서 사람이 쓴 원문**이다. 절이 직접 들고 있어야 한다 —
      요청 절은 자동 문장과 사람 문장이 한 목록에 섞여 있어서, 나중에 글자를
      보고 가르면 사람이 *"승인 —"* 으로 시작하는 문장을 쓴 순간 어긋난다.
    """
    문장 = [s for s in 문장 if s and s.strip()]
    if not 문장 and spec["kind"] == "auto":
        return None
    return {"제목": spec["제목"], "질문": spec["질문"], "kind": spec["kind"],
            "key": spec["key"], "문장": 문장, "차트": 차트, "표": 표,
            "사람": (사람 or "").strip()}


def _spec(key: str) -> dict:
    return next(s for s in C.PROPOSAL_SECTIONS if s["key"] == key)


def build(topic: dict, evidence: dict, cards: dict,
          human: dict | None = None) -> list[dict]:
    """제안서 절 목록을 조립한다.

    ★ `evidence` 에 없는 값으로 문장을 만들지 않는다.
      **없으면 그 절을 아예 만들지 않는다.**
    ★ `config.PROPOSAL_SECTIONS` 의 순서 그대로. 바꾸지 않는다.
    """
    human = human or {}
    ev, cs = evidence, cards.get("cards", [])
    out: list[dict] = []

    for spec in C.PROPOSAL_SECTIONS:
        key = spec["key"]

        if key == "현황":
            f = ev.get("현황")
            if f is None or not len(f):
                continue
            svg = (PC.funnel_svg(f, unit="개", side="멈춤 없음",
                                 title=f"구간별 멈춘 {C.GRAIN_SUB}가 있는 {C.GRAIN_UNIT} 수",
                                 cap=f"막대는 그 구간에서 멈춘 {C.GRAIN_SUB}가 하나라도 있는 {C.GRAIN_UNIT} 수입니다 · "
                                     f"{C.GRAIN_UNIT} {f.attrs.get('도번전체', 0):,}개 기준 · 오른쪽은 멈춘 {C.GRAIN_SUB}가 없는 {C.GRAIN_UNIT} 수")
                   if f.attrs.get("그레인") == "도번" else PC.funnel_svg(f))
            out.append(_sec(spec, _s_현황(ev), svg, f))

        elif key == "원인":
            g = ev.get("원인")
            if g is None or not len(g):
                continue                      # 축 주제가 아니면 이 절은 없다
            out.append(_sec(spec, _s_원인(topic, ev),
                            PC.gap_svg(g, topic.get("근거축", "")), g))

        elif key == "규모":
            if ev.get("규모_없는사유"):
                continue                      # 건수로 못 재면 이 절은 없다
            svg = ""
            s = ev.get("추세")
            if s is not None and len(s):
                col = ev.get("추세_지표", "")
                thr = C.THRESHOLDS.get(col, {}).get("경고")
                svg = PC.trend_svg(s[col], col, thr)
            out.append(_sec(spec, _s_규모(ev, cs), svg, s))

        elif key == "제안":
            if not cs:
                continue
            out.append(_sec(spec, _s_제안(cs, ev), "", None))

        elif key == "요청":
            # 문장은 사람이 쓰고, 규모·선택지·미룬 값만 붙는다. **사람 문장이 뒤.**
            out.append(_sec(spec, _s_요청(ev, cs, human.get(key, "")), "", None,
                            사람=human.get(key, "")))

        else:                                  # 사람이 쓰는 절 (위험)
            out.append(_sec(spec, [human.get(key, "")], "", None,
                            사람=human.get(key, "")))

    return [s for s in out if s]

# ── 조사 ─────────────────────────────────────────────────────────
# ★ **여기서 다시 짜지 않는다.** `config.josa()` 한 곳에만 둔다 —
#   두 곳에 같은 규칙을 두면 한쪽만 고쳐지고, 어느 쪽이 맞는지 알 수 없게 된다.
_j = C.josa


# ── 문장 만들기 ──────────────────────────────────────────────────
# ★ **숫자 나열이 아니라 맥락이 있는 문장.** 한 절은 세 문장을 넘지 않는다.
#
#     1문장   무슨 일이 일어나는가 — 숫자와 **분모를 함께**
#     2문장   그게 왜 문제인가 — **비교 대상 대비** 얼마나 벌어졌는지
#     3문장   그래서 얼마인가 — **연간으로 환산한** 규모
#
# ★ **실측 문장과 환산 문장을 한 문장에 합치지 않는다.** 합치면 환산이
#   실측처럼 읽힌다. 환산 문장 뒤에는 **쓴 가정을 괄호로** 한 줄 붙인다.
#
# ★ **함수 이름·컬럼 이름을 문장에 넣지 않는다.** 결재 문서라 읽는 사람이
#   우리 코드를 모른다. 수업 용어(코호트·가드레일·그레인)도 쓰지 않는다.
#
# ★ 카드와 근거에 없는 사실을 넣지 않는다. 없으면 **그 문장을 안 쓴다.**
_MAX_SENT = 3


def _cut(sents: list[str], n: int = _MAX_SENT) -> list[str]:
    """세 문장을 넘지 않게. 넘으면 **뒤를 버린다** — 앞이 더 중요하다.

    규모 절만 넷을 쓴다 — 마지막 하나가 **문장이 아니라 쓴 가정**이라서다.
    """
    return [s for s in sents if s and s.strip()][:n]


def _s_현황(ev: dict) -> list[str]:
    """지금 어디서 빠지고 있습니까."""
    f = ev.get("현황")
    if f is None or not len(f):
        return []
    d = f[f["drop"].fillna(0) > 0]
    if d.empty:
        return []
    r = (f[f["is_bottleneck"]].iloc[0] if f["is_bottleneck"].any()
         else d.nlargest(1, "drop").iloc[0])
    나머지 = d[d["label"] != r["label"]]
    첫 = float(f["n"].iloc[0])

    # ★ 도번 단위 (2026-09-12) — 표가 `funnel_parts` 면 도번으로 말한다.
    #   도달 도번은 11단계 전부 1,200개라 "어디까지 갔다"가 아니라 **"어느 구간에서
    #   멈춘 발주가 있는 도번이 몇 개인가"** 가 도번 단위의 사실이다.
    if f.attrs.get("그레인") == "도번":
        전체 = int(f.attrs.get("도번전체", 첫)); 깨끗 = f.attrs.get("깨끗한도번")
        lab = str(r["label"]).replace(" ", "")
        s1 = (f'{C.GRAIN_UNIT} {전체:,}개 가운데 {int(r["drop"]):,}개({float(r["drop"]) / 전체 * 100:.0f}%)에 '
              f'{lab}에서 멈춘 {_j(C.GRAIN_SUB, "이")} 있습니다'
              + (f' — 어느 구간에서도 멈추지 않은 {_j(C.GRAIN_UNIT, "은")} {int(깨끗):,}개입니다.' if 깨끗 is not None else '.'))
        s2 = ""
        if len(나머지):
            second = 나머지.nlargest(1, "drop").iloc[0]
            s2 = (f'다음으로 많은 구간은 {str(second["label"]).replace(" ", "")} '
                  f'{int(second["drop"]):,}개이고, {_j(lab, "은")} 그 '
                  f'{float(r["drop"]) / float(second["drop"]):.1f}배입니다.')
        s3 = (f'{lab}에서 멈춘 {_j(C.GRAIN_SUB, "은")} {int(r["멈춘발주"]):,}건인데 {C.GRAIN_UNIT}당 '
              f'중앙 {float(r["도번당중앙"]):.0f}건 · 최대 {int(r["도번당최대"])}건이라, '
              f'몇몇 {C.GRAIN_UNIT}의 문제가 아니라 {float(r["drop"]) / 전체 * 100:.0f}%에 '
              f'한 건씩 퍼져 있습니다.')
        return _cut([s1, s2, s3])

    s1 = (f'발주 {int(첫):,}건 가운데 {int(r["n"]):,}건이 '
          f'{str(r["label"]).replace(" ", "")}까지 갔습니다.')
    s2 = ""
    if len(나머지):
        second = 나머지.nlargest(1, "drop").iloc[0]
        s2 = (f'{str(r["label"]).replace(" ", "")}에서 {int(r["drop"]):,}건이 '
              f'빠지는데, 다음으로 많이 빠지는 '
              f'{str(second["label"]).replace(" ", "")}'
              f'({int(second["drop"]):,}건)의 '
              f'{float(r["drop"]) / float(second["drop"]):.1f}배입니다.')
    총이탈 = float(d["drop"].sum())
    s3 = (f'전체에서 빠지는 {int(총이탈):,}건 중 '
          f'{float(r["drop"]) / 총이탈 * 100:.1f}% 가 이 한 구간에 몰려 있습니다.'
          ) if 총이탈 else ""
    return _cut([s1, s2, s3])


def _s_원인(topic: dict, ev: dict) -> list[str]:
    """어느 쪽에서 벌어지고 있습니까.

    ⚠️ **왜 그런지는 쓰지 않는다.** 우리 데이터로는 *어느 칸이 낮은가*까지만
       댈 수 있다. 원인을 대면 없는 것을 있는 것처럼 만든다.
    """
    g, dim = ev.get("원인"), topic.get("근거축", "")
    if g is None or not len(g):
        return []
    big = g.iloc[0]                                # 크기 큰 순으로 정렬돼 있다
    최고 = ev.get("원인_최고칸", "")
    hi = g.loc[g["준수율"].idxmax()]

    # ★ 도번 단위 (2026-09-12) — 준수율은 그 칸 **도번들의 평균**, 발주 수는 옆에 적는다.
    도번 = int(big["도번"]) if "도번" in g.columns else None
    s1 = (f'{_j(dim, "으로")} 나누면 {_j(big[dim], "이")} '
          + (f'{C.GRAIN_UNIT} {도번:,}개 평균 ' if 도번 else '')
          + f'{big["준수율"] * 100:.2f}%로, 기한 안에 나간 {_j(C.GRAIN_SUB, "이")} '
          f'{int(big["분모"]):,}건 중 {int(big["준수"]):,}건입니다.')
    저조 = int(big["저조도번"]) if "저조도번" in g.columns else None
    s2 = (f'가장 높은 {최고}({hi["준수율"] * 100:.2f}%)와 '
          f'{float(big["격차"]):.2f}%p 벌어지고, '
          f'이 {_j(dim, "이")} 전체 {C.GRAIN_UNIT}의 '
          f'{big["비중"] * 100:.1f}%를 차지합니다'
          + (f' — {C.LATE_PART_THRESHOLD * 100:.0f}% 밑인 {_j(C.GRAIN_UNIT, "은")} {저조:,}개입니다.'
             if 저조 is not None else '.'))

    # ★ 격차 최대 칸과 크기 최대 칸이 다르면 **그 사실을 적는다.**
    #   안 적으면 "가장 낮은 칸을 왜 안 골랐나" 라는 질문이 남는다.
    s3 = ""
    worst = g.loc[g["준수율"].idxmin()]
    if str(worst[dim]) != str(big[dim]):
        s3 = (f'{_j(worst[dim], "이")} {float(worst["격차"]):.2f}%p로 더 '
              f'벌어지지만 '
              f'전체의 {worst["비중"] * 100:.1f}% 뿐이라 '
              f'{int(worst["건수"]):,}건에 그칩니다.')
    # ★ 어느 **색상**에서 벌어지는지를 적는다 (2026-09-12 · 처음엔 고객사였다).
    #   판정 지적은 *"어느 고객사 물량인지"* 였으나, 고객사가 색상의 대리변수라
    #   그대로 내면 "그 고객사가 문제"로 읽힌다(7주차 함정 ④). 색상은 도장에서
    #   실제로 시간이 갈리는 축이라 결재자가 손댈 수 있는 자리다.
    내역 = ev.get("색상내역") or []
    s4 = (f'색상으로 나누면 {C.GRAIN_UNIT} 평균이 '
          + " · ".join(f'{k} {r*100:.1f}%({n:,}건 늦음)' for k, n, r in 내역[:4])
          + '으로, ' + f'{_j(내역[0][0], "이")} 가장 낮습니다.') if 내역 else ""
    return _cut([s1, s2, s3, s4], 4)


def _s_규모(ev: dict, cards: list[dict] | None = None) -> list[str]:
    """연간 몇 건짜리 문제입니까.

    ★ **실측과 환산을 다른 문장으로 나눈다.** 합치면 환산이 실측처럼 읽힌다.
    """
    규모 = ev.get("규모") or {}
    연간 = float(규모.get("연간건수") or 0)
    누적 = float(규모.get("누적건수") or 0)
    if 연간 <= 0:
        return []

    # ★ **건수만 세 번 말하면 결재가 안 난다** (2026-09-11 판정).
    #   판정 사유가 *"297건이 매출로 얼마인지 한 줄도 없다"* 였다.
    #   금액은 `metrics.amount_by()` 가 조회한다 — 지어내지 않는다.
    누적금 = float(규모.get("누적금액") or 0)
    연간금 = float(규모.get("연간금액") or 0)

    def _억(v: float) -> str:
        return f"{v / 1e8:,.2f}억원"

    s1 = (f'관측한 기간 동안 이 차이로 기한을 못 지킨 것이 '
          f'{int(round(누적)):,}건'
          + (f', 납품 금액으로 {_억(누적금)}입니다.' if 누적금 else '입니다.'))
    s2 = (f'같은 상태가 이어지면 연 {int(round(연간)):,}건'
          + (f' · {_억(연간금)}입니다.' if 연간금 else '입니다.'))
    # ★ **그림이 증명하는 문장.** 추세 꺾은선을 그려 놓고 본문이 건수만 말하면
    #   그 그림은 장식이다(2026-09-10 자가 검사가 잡았다).
    #   ⚠️ **없는 방향을 지어내지 않는다.** 평평하면 평평하다고 적는다 — 그것도
    #     결재에 필요한 사실이다. *"기다리면 줄어든다"* 는 반론이 여기서 막힌다.
    s3 = _s_추세(ev)
    # ★ **비용이 왜 없는지를 데이터 근거 자리에서 말한다** (강사앱 재제출 02 ·
    #   2026-09-12). 03·06 에 비용 상한을 적자 평가자가 *데이터 근거* 항목에서도
    #   비용을 물었다 — 이유는 카드 「비용」 칸에, 누가 언제 받는지는 요청 절에
    #   **이미 있었는데 이 절에만 없었다**(B). 세 곳이 같은 값을 읽는다.
    s5 = _s_비용없음(cards or [], 규모)
    가정 = ev.get("규모_가정") or []
    s4 = f'({" · ".join(가정)})' if 가정 else ""                # 쓴 가정
    # ★ **운송비는 매출과 자릿수가 다르다는 것을 보인다** (2026-09-12). 페널티 조항은
    #   없고(기쁨) 긴급 운송비만 있는데, 그것으로는 이 제안이 정당화되지 않는다 —
    #   그 사실을 숨기지 않는다. 값은 `urgent_ship_facts` 가 표에서 센다.
    uf, 운송연간 = 규모.get("긴급운송") or {}, float(규모.get("연간운송비") or 0)
    # 클레임 (2026-09-12) — 지연 건에 붙는 것만. 불량 클레임은 이 제안의 효과가 아니다.
    cf, 클레임연간 = 규모.get("클레임") or {}, float(규모.get("연간클레임비") or 0)
    클레임 = (f', 고객사 클레임은 지연 건의 {cf["지연클레임비율"] * 100:.1f}%에 '
             f'1건 {cf["건당비용"] / 1e4:,.0f}만원이라 연 {클레임연간 / 1e4:,.0f}만원'
             if (cf and 클레임연간) else "")
    s6 = (f'늦게 나간 건 가운데 {uf["긴급비율"] * 100:.0f}%가 긴급 운송으로 나가고 '
          f'1회 {uf["회당비용"] / 1e4:,.1f}만원이라, 연 {int(round(연간)):,}건이면 '
          f'운송비는 연 {운송연간 / 1e4:,.0f}만원' + 클레임 + '입니다.') if (uf and 운송연간) else ""
    return _cut([s1, s2, s6, s3, s5, s4], 6)


def _s_비용없음(cards: list[dict], 규모: dict | None = None) -> str:
    """비용을 못 낸 **이유**와 **누가 언제** 받아 오는지 — 한 문장.

    이유는 **추진 카드**의 「비용」 칸 첫 문장(*"미확인 — "* 뒤)에서 읽는다.
    주체·기한은 요청 절과 같은 `_who`·`_when`. **짓지 않는다** — 카드에 없으면
    그 조각은 비운다.
    """
    할것 = [c for c in cards if c.get("분류") == "할 것"]
    if not 할것:
        return ""
    raw = 할것[0].get("비용", "")
    이유 = ""
    if "미확인" in raw:
        이유 = (raw.split("—", 1)[-1].split(".")[0].replace("**", "").strip()
                .removesuffix("이다"))            # 괄호 안에서는 서술어를 뗀다
    who, when = _who(cards), _when(cards)
    받음 = (f' — {" · ".join(who)}에서 {when}에 받아 채웁니다.' if (who and when)
            else ' — 받아 올 곳과 기한은 아직 정하지 않았습니다.')
    # ★ 추정치가 있으면 **없다고 하지 않는다** (2026-09-12 리더 조건). 조치 가정은 가정 줄에.
    당김, eff = (규모 or {}).get("당김") or {}, _effect_n(할것[0])
    if 당김 and eff:
        return (f'드는 비용은 {C.PULL_ACTION} 기준 연 {eff * 당김["건당비용"] / 1e4:,.0f}만원'
                f'(발주 1건 {당김["건당시간h"]:.1f}시간 × 잔업 단가)'
                + ('으로 추정하며, 확정값은' if C.SHOW_ESTIMATE_NOTE else '입니다. 확정값은')
                + 받음.replace(" — ", " ", 1))
    return (f'드는 비용은 데이터에 없어 못 냈습니다'
            + (f'({이유})' if 이유 else '') + 받음)


def _s_추세(ev: dict) -> str:
    """추세 그림이 증명하는 한 문장. 값이 없으면 빈 문자열."""
    s, col = ev.get("추세"), ev.get("추세_지표", "")
    if s is None or not len(s) or col not in s.columns:
        return ""
    v = s[col].dropna()
    if len(v) < 4:                       # 반씩 갈라 볼 수 없으면 방향을 말하지 않는다
        return ""
    half = len(v) // 2
    앞, 뒤 = float(v.iloc[:half].mean()), float(v.iloc[half:].mean())
    diff = 뒤 - 앞
    if abs(diff) < C.EFFECT_MIN_PP:      # 평소 변동폭 안 — 새 기준을 만들지 않는다
        return (f'{_j(col, "은")} 최근 {len(v)}개월 동안 '
                f'{v.min():.1f}~{v.max():.1f}% 사이를 오갔고 방향이 뚜렷하지 '
                f'않습니다. 그대로 두면 줄어든다고 볼 근거가 없습니다.')
    쪽 = "올랐습니다" if diff > 0 else "내려갔습니다"
    return (f'{_j(col, "은")} 직전 {half}개월 {앞:.1f}% 에서 '
            f'최근 {len(v) - half}개월 {뒤:.1f}% 로 {abs(diff):.1f}%p {쪽}.')


_WHEN = re.compile(r"\(\*{0,2}([^)*]*(?:주|일|달|개월)\s*안?)\*{0,2}\)")


def _when(cards: list[dict]) -> str:
    """비용을 언제까지 확인하는가. **카드 「확인」 칸에서 읽는다.**

    ★ 기한은 바뀌는 값이라 코드에 박지 않는다(규칙 15). 카드가 정본이다.
    ⚠️ 카드마다 다르면 **가장 늦은 것 하나만** 쓰지 않고 비워 둔다 —
      한 기한으로 뭉뚱그리면 늦은 쪽이 가려진다.
    """
    seen = {m.group(1).strip() for c in cards
            if "미확인" in c.get("비용", "")
            for m in [_WHEN.search(c.get("확인", ""))] if m}
    return seen.pop() if len(seen) == 1 else ""


_PLAN = re.compile(r"일정:\s*(.+?)\s*\*\*\(")


def _plan(cards: list[dict]) -> str:
    """추진 카드 「확인」 칸의 *일정:* 뒤 — 주차별 누가 무엇을. **카드가 정본**, 짓지 않는다."""
    for c in cards:
        if c.get("분류") == "할 것":
            m = _PLAN.search(c.get("확인", ""))
            if m:
                return m.group(1).strip()
    return ""


def _who(cards: list[dict]) -> list[str]:
    """비용을 아직 모르는 카드들의 **확인 주체**를 카드에서 모은다.

    ★ **짓지 않는다.** 카드의 `확인` 칸에 적힌 것만 읽는다. 안 적혀 있으면
      그 카드는 주체가 없는 것이고, 문서는 *"주체를 아직 안 정했다"* 고 말한다 —
      "현업" 같은 두루뭉술한 말로 메우면 아무도 자기 일인 줄 모른다.
    """
    seen: list[str] = []
    for c in cards:
        if "미확인" not in c.get("비용", ""):
            continue
        raw = c.get("확인", "")
        who = raw.split("—")[0].replace("**", "").strip() if raw else ""
        for one in (x.strip() for x in who.split("·")):
            if one and one not in seen:
                seen.append(one)
    return seen


def _s_요청(ev: dict, cards: list[dict], 사람: str = "") -> list[str]:
    """무엇을 결정해 주셔야 합니까.

    ★ **무엇을 해달라는 말은 짓지 않는다.** 여기서 만드는 것은 결정에 필요한
      **재료**뿐이다 — 규모 · 선택지 셋 · 미뤘을 때 쌓이는 양.
      요청은 사람이 책임지는 말이라 자동으로 만들면 책임의 주체가 사라진다.

    ★ **사람 문장을 맨 뒤에 둔다.** 문서의 마지막 줄이 결정을 요구하는 문장이어야
      읽은 사람이 무엇을 해야 하는지 알고 문서를 닫는다.

    ★ **선택지가 셋이어야 선택지다.** 보류만 있으면 고를 것이 없고, 승인만 있으면
      결재가 아니라 통보다. 셋에 각각 무엇이 따라오는지 한 줄씩 붙인다.
    """
    연간 = float((ev.get("규모") or {}).get("연간건수") or 0)
    할것, 다시, 멈출 = (_by_kind(cards, k)
                     for k in ("할 것", "다시 할 것", "하지 말 것"))
    # 비용을 아직 모르는 카드 — **채우지 않고 센다** (규칙 15)
    미확 = [c for c in cards if "미확인" in c.get("비용", "")]

    out: list[str] = []
    연간금 = float((ev.get("규모") or {}).get("연간금액") or 0)
    if 연간 > 0:
        out.append(f'이 문제는 연 {int(round(연간)):,}건'
                   + (f' · {연간금 / 1e8:,.2f}억원 규모입니다.' if 연간금
                      else ' 규모입니다.'))

    # ── 선택지 셋 ────────────────────────────────────────────────
    #   각 줄의 뒷말은 **카드에서 세어** 만든다. 무엇이 따라오는지가 카드에 있다.
    if 할것:
        # ★ **지켜야 할 선을 승인 줄에 붙인다** (2026-09-12 · 답변지 14 · 7주차 함정 ②).
        #   주지표를 올리자면서 부작용 선이 없으면 "좋아 보이는데 좋지 않은 것"이 승인된다.
        #   값은 config 에서 — 4% 는 THRESHOLDS 와 같은 값이라 한 곳만 바꾸면 갈린다.
        ppm = C.GUARDRAIL_DEFECT_PPM
        선 = (f' 불량률이 {ppm / 10_000:.0f}%({ppm:,}ppm)를 넘으면 조치하고, '
              f'목표치는 매월 낮춥니다.')
        # ★ **예산 범위** (강사앱 03·06 · 2026-09-12). 비용 실액은 확인 필요 그대로고,
        #   **상한을 규칙으로** 적는다 — config.COST_CAP_RULE. 금액은 편익에서 계산.
        eff = next((n for n in (_effect_n(c) for c in 할것) if n), None)
        per = float(((ev or {}).get("규모") or {}).get("건당금액") or 0)
        당김 = ((ev or {}).get("규모") or {}).get("당김") or {}
        추정 = (f' 지금 {"추정은" if C.SHOW_ESTIMATE_NOTE else "계산으로는"} {C.PULL_ACTION} 기준 '
                f'연 {eff * 당김["건당비용"] / 1e4:,.0f}만원입니다.'
                if (eff and 당김) else '')
        상한 = (f' 소요 비용은 {C.COST_CAP_RULE}(연 {eff * per / 1e8:.2f}억원)여야 '
                f'착수합니다.' + 추정) if (eff and per) else ''
        out.append(f'승인 — {C.say("할 것")} {len(할것)}건에 착수합니다.' + 상한 + 선)
    if 미확:
        # ★ **낱말 하나로 두지 않는다.** [무엇을 모르는가] 는 카드에 있고,
        #   여기에 [누가 확인하는가] 를 붙인다. [모르는 채로 할 수 있는 결정] 은
        #   선택지 셋 자체가 답한다 — 조건부 승인이 바로 그 자리다.
        누가 = _who(cards)
        언제 = _when(cards)
        뒤 = (f'{" · ".join(누가)}에서 {언제 + "에 " if 언제 else ""}받아 '
              f'채운 뒤 착수합니다.' if 누가
              else '확인할 곳을 아직 정하지 않았습니다.')
        # 리더 조건(2026-09-12 3차) — "확정 비용 **및 잔업 여유**". 낱말 하나를 받는 목록에 더한다.
        plan = _plan(cards)      # 4차 리더 조건(04) — 주차별 담당·일정. 카드에서 읽는다
        out.append(f'조건부 승인 — 드는 비용이 {C.say("미확인")}인 '
                   f'{len(미확)}건과 잔업 여유를 {뒤}' + (f' 일정은 {plan}입니다.' if plan else ''))
    if 다시 or 멈출:
        뒤 = " · ".join(f'{C.say(k)} {len(v)}건'
                       for k, v in (("하지 말 것", 멈출), ("다시 할 것", 다시)) if v)
        out.append(f'보류 — {뒤}만 그대로 두고 나머지는 다음 분기에 다시 봅니다.')

    # ── 미뤘을 때 ────────────────────────────────────────────────
    #   ★ 우리 기간이 363일이라 연간 ≈ 관측 누적이다. 분기는 **연간 ÷ 4** 로
    #     환산하는데, 그 가정을 괄호로 적는다 — 실측처럼 읽히면 안 된다.
    if 연간 > 0:
        뒤 = (f' · {연간금 / 4 / 1e8:,.2f}억원' if 연간금 else '')
        out.append(f'결정을 미루면 다음 분기까지 {int(round(연간 / 4)):,}건'
                   f'{뒤}이 더 쌓입니다. (연간을 넷으로 나눴고, 지금 상태가 '
                   f'그대로 이어진다고 보았습니다)')

    # ★ 맨 뒤. 비어 있으면 안 붙인다 — 화면이 그때 경고한다.
    if 사람 and 사람.strip():
        out.append(사람.strip())
    return out


# ── 결정 동사 ────────────────────────────────────────────────────
# ★ **결재 문서는 결정을 요구하는 문장으로 끝나야 한다.** 그 문장이 없으면 읽은
#   사람이 무엇을 해야 하는지 모른 채 문서를 닫는다.
#
# ★ ⚠️ **경고만 한다. 조립도 저장도 막지 않는다.** 사람이 쓴 문장 때문에 문서가
#   안 만들어지면 사람이 문장을 안 쓰게 된다. 자동 절에 거는 검사(`_sec` 의
#   빈 문장 차단)는 자동으로 쓴 부분에만 걸린다.
DECIDE_VERBS = ("승인", "결정", "판단")


def decision_ask(secs: list[dict]) -> dict:
    """마지막 절의 **사람 문장**에 결정 동사가 있는가. 판정만 하고 고치지 않는다.

    ⚠️ 자동 문장에는 선택지 셋 때문에 "승인" 이 늘 들어 있다. 전체를 보면 검사가
      **항상 통과해서** 아무것도 안 잡는다 — **사람이 쓴 문장만** 본다.
    """
    요청 = next((s for s in secs if s["key"] == "요청"), None)
    if 요청 is None:
        return {"있음": False, "문장": "", "사유": "요청 절이 없습니다"}
    문장 = 요청.get("사람", "")
    if not 문장:
        return {"있음": False, "문장": "",
                "사유": "요청 문장을 아직 쓰지 않았습니다"}
    if any(v in 문장 for v in DECIDE_VERBS):
        return {"있음": True, "문장": 문장, "사유": ""}
    return {"있음": False, "문장": 문장,
            "사유": f'결정을 요구하는 말({" · ".join(DECIDE_VERBS)})이 '
                    f'문장에 없습니다'}


def _s_제안(cards: list[dict], ev: dict | None = None) -> list[str]:
    """무엇을 하자는 것입니까.

    ★ **순서를 바꾸지 않는다** — 멈출 것 → 다시 잴 것 → 할 것.
      할 것을 앞에 두면 읽는 사람이 거기서 멈추고 멈추자는 말은 안 읽힌다.
    """
    if not cards:
        return []
    묶음 = [(k, _by_kind(cards, k))
           for k in ("하지 말 것", "다시 할 것", "할 것")]
    있는것 = [(k, v) for k, v in 묶음 if v]
    if not 있는것:
        return []

    # ★ 인쇄되는 말은 **config.PROPOSAL_WORDS 한 곳**에서 온다.
    #   키(하지 말 것 / 다시 할 것 / 할 것)는 카드의 내부 분류라 바꾸지 않는다.
    # ★ **개수만 적지 않는다. 제목을 함께 낸다** (2026-09-11 Day4 프롬프트 6).
    #   전에는 개수만 적고 **첫 묶음의 제목만** 실었다. 그래서 결재자가
    #   **승인할 대상("추진 1건")이 무엇인지 문서에서 못 찾았다** —
    #   내용은 카드에 있었는데 문서가 안 내보낸 것이다(B: 있는데 안 내보냈다).
    #
    # ★ **승인 대상은 첫 문장에서 지목한다.** 한 장 요약이 절마다 첫 문장을
    #   가져가므로(`to_html`), 첫 문장에 없으면 요약만 읽는 사람은 또 못 찾는다.
    #   ⚠️ 그렇다고 **순서를 바꾸지는 않는다**(규칙 14) — 제목 나열은 그대로
    #     하지 말 것 → 다시 할 것 → 할 것이다. 지목과 나열은 다른 일이다.
    #
    # ⚠️ **값을 코드에 적지 않는다.** 제목도 효과도 카드에서 읽는다(규칙 15).
    def _titles(v: list[dict]) -> str:
        return " · ".join(str(c["title"]).replace(chr(34), "") for c in v)

    할것 = next((v for k, v in 있는것 if k == "할 것"), [])

    s1 = " · ".join(f'{C.say(k)} {len(v)}건' for k, v in 있는것) + "입니다."
    if 할것:
        s1 += (f' 승인 대상은 {C.say("할 것")} {len(할것)}건 — '
               f'{_titles(할것)} 입니다.')
        # ★ **타 대안 대비 왜 이것부터인가** (강사앱 03 · 2026-09-12). 카드 「크기」 칸에
        #   *전 축 1위* 가 있었는데 문서에 안 실렸다(B). 카드에서 읽는다.
        big = biggest_card(cards)
        m = _SIZE_N.search(big.get("크기", "")) if big else None
        if big and m and big in 할것:
            s1 += (f' 후보 {len(cards)}건 가운데 개선 건수가 가장 큽니다'
                   f'({int(m.group(1).replace(",", "")):,}건).')

    # 나열은 순서대로. **승인 대상은 위에서 이미 적었으므로 여기서 뺀다** —
    # 같은 제목이 한 절에 두 번 나오면 안 된다.
    # ★ 재측정에는 **얼마나** 를 붙인다 (2026-09-12 · 답변지 15). 카드 제목은
    #   *왜* 다시 도는지만 말한다. 표본·기간은 config 에서 읽는다 — 안 적으면
    #   결재자는 "다시 돌린다"가 며칠짜리인지 모른다.
    def _tail(k: str) -> str:
        return (f' (각각 표본 {C.MIN_SAMPLE}건 · {C.MIN_EXP_DAYS}일 이상 채운 뒤 판정)'
                if k == "다시 할 것" else "")

    s2 = " ".join(f'{C.say(k)} — {_titles(v)}{_tail(k)}.'
                  for k, v in 있는것 if k != "할 것")

    미확 = sum(1 for c in cards if "미확인" in c.get("비용", ""))
    누가 = _who(cards)
    # 전부일 때 "6건 가운데 6건" 은 읽히지 않는다. 결재 문서라 말을 가른다.
    몇 = f'{len(cards)}건 모두' if 미확 == len(cards) else f'{len(cards)}건 가운데 {미확}건은'
    # 기대 효과도 **카드에서 읽는다.** 없으면 안 붙인다.
    eff = next((n for n in (_effect_n(c) for c in 할것) if n), None)
    # ★ **편익을 금액으로** (강사앱 03 · 우선순위 2 의 [매출액]). 건당 금액은
    #   규모 절이 쓴 것과 같은 값(`ev["규모"]["건당금액"]`) — 두 절이 갈리면 안 된다.
    per = float(((ev or {}).get("규모") or {}).get("건당금액") or 0)
    효과금 = eff * per if (eff and per) else 0.0
    앞 = (f'{C.say("할 것")} {len(할것)}건은 벌어진 폭의 절반을 좁히면 {eff:,}건'
          + (f', 연간 {효과금 / 1e8:.2f}억원의 매출을 지킵니다. ' if 효과금
             else '입니다. ')) if (할것 and eff) else ''
    # ★ **비용 추정치 + 자원 배분** (2026-09-12 리더 조건 ①③). 값은 ev["규모"]["당김"] —
    #   작업일보 실측 시간 × 기쁨 인건비 표준. 조치(잔업 당김)는 가정이고 가정 줄에 적힌다.
    당김 = ((ev or {}).get("규모") or {}).get("당김") or {}
    비용 = eff * 당김["건당비용"] if (eff and 당김) else 0.0
    언제 = f'{(_when(cards) + "에") if _when(cards) else "기한 미정으로"}'
    if 비용 and 효과금:
        s3 = (앞 + f'드는 비용은 {C.PULL_ACTION} 기준 연 {비용 / 1e4:,.0f}만원'
              f'(편익의 {비용 / 효과금 * 100:.0f}%)'
              + ('으로 추정하며, 확정값은 ' if C.SHOW_ESTIMATE_NOTE else '입니다. 확정값은 ')
              + (f'{" · ".join(누가)}에서 {언제} 받습니다.' if 누가
                 else '확정할 곳을 아직 정하지 않았습니다.'))
    else:
        s3 = (앞 + f'{몇} 드는 비용이 '
              f'{C.say("미확인")} 상태입니다. 데이터 밖이라 '
              + (f'{" · ".join(누가)}에서 {언제} 받아야 합니다.' if 누가
                 else '확인할 곳을 아직 정하지 않았습니다.')) if 미확 else ""
    s4 = ""
    if 비용 and 당김.get("잔업여유h일") and 당김.get("가동일"):
        하루 = eff * 당김["건당시간h"] / 당김["가동일"]
        s4 = (f'당길 몫은 하루 {하루:.1f}시간으로 전 라인 잔업 여유(하루 {당김["잔업여유h일"]:,.0f}시간)의 '
              f'{하루 / 당김["잔업여유h일"] * 100:.1f}%라, 다른 차종의 작업 시간을 쓰지 않습니다.')
    return _cut([s1, s2, s3, s4], 4)


# ── 자가 검사 (2026-09-10 Day3 프롬프트 11) ──────────────────────
# ★ **고치지 않는다. 세어서 알린다.** 문서를 코드가 손대기 시작하면 사람이
#   무엇을 썼는지 알 수 없게 된다 — 리포트 8장에서 이미 정한 원칙이다.
#
# ★ **거르는 자리는 조립기 한 곳뿐**이라, 여기서는 아무것도 안 거른다.

def _sec_of(secs: list[dict], needle: str) -> str:
    """그 말이 어느 절에 있는지. 프롬프트 11이 절 이름까지 요구한다."""
    for s in secs:
        if any(needle in x for x in s["문장"]):
            return s["제목"]
    return "(본문 밖)"


def _chart_subject(sec: dict, topic: dict) -> str:
    """그 절의 그림이 **강조하는 대상 이름**. 못 찾으면 빈 문자열.

    ★ 그림을 그린 표에서 직접 뽑는다. 그림과 검사가 같은 값을 봐야
      *"그림이 가리키는 것을 문장이 말하는가"* 를 실제로 검사하게 된다.
    """
    df = sec.get("표")
    if df is None or not len(df):
        return ""
    key = sec["key"]
    try:
        if key == "현황":                       # 이탈 막대 — 강조한 한 단계
            hit = df[df.get("is_bottleneck") == True]      # noqa: E712
            return str(hit.iloc[0]["label"]) if len(hit) else ""
        if key == "원인":                       # 축별 막대 — 가장 낮은 칸
            dim = topic.get("근거축", "")
            if dim not in df.columns or "준수율" not in df.columns:
                return ""
            return str(df.sort_values("준수율").iloc[0][dim])
        if key == "규모":                       # 추세 꺾은선 — 그린 지표 이름
            for c in df.columns:
                if c in C.THRESHOLDS:
                    return str(c)
    except Exception:
        return ""                               # 검사가 문서 조립을 막지 않는다
    return ""


def self_check(secs: list[dict], topic: dict | None = None) -> list[dict]:
    """제안서 여섯 항목 검사. `{"항목","값","기준","통과","자리"}` 목록.

    ⚠️ **문장을 고치지 않는다.** 어디가 걸렸는지만 돌려준다.
    """
    topic = topic or {}
    out: list[dict] = []

    # ① 빈칸 — 사람이 쓸 자리가 빈 채로 남았는가
    빈 = [s["제목"] for s in secs if s["kind"] == "human" and not s["사람"]]
    out.append({"항목": "빈칸", "값": len(빈), "기준": "0",
                "통과": not 빈, "자리": " · ".join(빈)})

    # ② 정체불명 용어 — 팀 밖 사람이 뜻을 모를 말
    말 = []
    for w in C.PROPOSAL_JARGON:
        자리 = [s["제목"] for s in secs if any(w in x for x in s["문장"])]
        if 자리:
            말.append(f'{w}({자리[0]})')
    out.append({"항목": "정체불명 용어", "값": len(말), "기준": "0",
                "통과": not 말, "자리": " · ".join(말)})

    # ③ 그림마다 대응하는 문장이 있는가
    #    ★ **그림이 그리는 대상이 본문 문장에 나오는가**로 본다. 안 나오면
    #      그 그림은 아무 문장도 증명하지 않는 장식이다.
    무대응 = []
    for s in secs:
        if not s["차트"]:
            continue
        본문 = " ".join(s["문장"])
        # ⚠️ **그림을 그린 그 표에서 뽑는다.** 주제 딕셔너리에서 뽑으면 안 된다 —
        #   축 주제의 `구간` 칸에는 구간이 아니라 **지표 이름**이 들어 있어서,
        #   현황 절 그림에 엉뚱한 이름을 씌워 오탐이 났다(2026-09-10).
        키 = _chart_subject(s, topic)
        if not 키:
            # ⚠️ **못 찾은 것을 통과로 세지 않는다.** 그림은 있는데 대상을
            #   못 뽑으면 검사가 눈이 먼 것이지 문서가 옳은 것이 아니다.
            #   (검사기를 꺼 보다 2026-09-10 에 드러났다 — 규칙 12)
            무대응.append(f'{s["제목"]}(그림이 무엇을 그리는지 확인 못 함)')
        elif 키 not in 본문:
            무대응.append(f'{s["제목"]}(그림은 {_j(키, "을")} 그리는데 '
                          f'문장에 없음)')
    out.append({"항목": "대응 문장 없는 그래프", "값": len(무대응), "기준": "0",
                "통과": not 무대응, "자리": " · ".join(무대응)})

    # ④ 마지막 줄이 결정을 요구하는가
    d = decision_ask(secs)
    out.append({"항목": "마지막 줄 결정 동사", "값": "있음" if d["있음"] else "없음",
                "기준": "있음", "통과": d["있음"],
                "자리": d["사유"] or d["문장"][:40]})

    # ⑤ 절 개수
    out.append({"항목": "절 개수", "값": len(secs), "기준": "7 이하",
                "통과": len(secs) <= 7,
                "자리": " · ".join(s["key"] for s in secs)})

    # ⑥ 밖으로 나가면 안 되는 것 (2026-09-11)
    #    ★ 회사명은 **소스에는 일부러 남기고**(근거의 출처가 지워지면 그 숫자를
    #      못 믿는다) **나가는 문서에서만** 뺀다. 그래서 `test_guards` 가 아니라
    #      여기서 본다 — 검사하는 범위가 다르다.
    본문전체 = " ".join(x for s in secs for x in s["문장"])
    샌것 = [w for w in C.PROPOSAL_OUT_BAN
            if w in 본문전체 or w in str(topic.get("제목", ""))]
    out.append({"항목": "나가면 안 되는 말", "값": len(샌것), "기준": "0",
                "통과": not 샌것,
                "자리": " · ".join(f'{w}({_sec_of(secs, w)})' for w in 샌것)})

    # ⑦ 폰트가 못 그리는 글자 — PDF 에서 조용히 네모로 나가는 자리 (규칙 16)
    #    ⚠️ **import 를 함수 안에 둔다.** 맨 위에 두면 제안서를 만들 때마다
    #      PDF 폰트를 읽는다 — 이 검사를 안 돌릴 때도.
    try:
        from report.to_pdf import missing_glyphs
        본문 = " ".join(x for s in secs for x in s["문장"])
        없는글자 = sorted(set(missing_glyphs(본문)))
    except Exception as e:                       # 폰트 파일이 없을 수도 있다
        out.append({"항목": "폰트에 없는 글자", "값": "확인 못 함", "기준": "0",
                    "통과": False, "자리": str(e)[:60]})
    else:
        out.append({"항목": "폰트에 없는 글자", "값": len(없는글자), "기준": "0",
                    "통과": not 없는글자,
                    "자리": " ".join(f'{c}(U+{ord(c):04X} · '
                                     f'{_sec_of(secs, c)})'
                                     for c in 없는글자)})
    return out


# ── 내보내기 ─────────────────────────────────────────────────────
# ★ **템플릿 파일을 읽지 않는다.** 이 함수가 직접 만든다.
#   (2026-09-09 판 은 강사 템플릿의 <style> 을 읽었다. 오늘은 우리가 짠다 —
#    두 방식을 함께 두면 어느 것이 진짜인지 알 수 없게 되므로 그쪽은 버렸다.)
#
# ★ **웹폰트·CDN·외부 이미지 금지.** 파일 하나로 열려야 한다.
#   폰트는 시스템에 있는 것으로 물러난다 — fonts/*.ttf 를 link 로 걸면
#   파일 하나로 안 열린다.
#
# ★ **계산 과정·함수 이름·컬럼 이름을 문서에 넣지 않는다.**
#   결재 문서라 읽는 사람이 우리 코드를 모른다.
#
# ★ **빈 절은 그리지 않는다.** 조립기가 이미 안 만들지만, 여기서도 한 번 더
#   거르지 않는다 — 거르는 자리는 한 곳뿐이다. 문장이 없으면 절이 없다.
_A4_CSS = """
@page{size:A4;margin:18mm 16mm}
:root{--ink:#111827;--muted:#6b7280;--line:#d1d5db;--hi:#b42318;--soft:#f3f4f6}
*{box-sizing:border-box}
html,body{margin:0;padding:0}
body{font-family:'Malgun Gothic','Apple SD Gothic Neo','Noto Sans KR',sans-serif;
     color:var(--ink);font-size:10.5pt;line-height:1.62;background:#fff}
.page{max-width:186mm;margin:0 auto;padding:16mm 0}
h1{font-size:17pt;font-weight:800;margin:0 0 2mm;line-height:1.32;
   letter-spacing:-.01em}
.sub{color:var(--muted);font-size:9.5pt;margin-bottom:4mm}
.meta{display:flex;flex-wrap:wrap;gap:2mm 7mm;font-size:8.5pt;
      color:var(--muted);border-top:.6pt solid var(--line);
      border-bottom:.6pt solid var(--line);padding:2mm 0;margin-bottom:6mm}
.meta b{color:var(--ink);font-weight:600}
.sum{border:.8pt solid var(--line);border-left:2.4pt solid var(--hi);
     padding:4mm 5mm;margin-bottom:7mm;page-break-inside:avoid}
.sum h2{font-size:9pt;font-weight:700;color:var(--hi);margin:0 0 2mm;
        letter-spacing:.05em}
.sum p{margin:0 0 1.5mm}
.sum p:last-child{margin-bottom:0}
h2.sec{font-size:12.5pt;font-weight:700;margin:7mm 0 0;
       page-break-after:avoid;page-break-inside:avoid}
h2.sec .n{color:var(--muted);font-weight:600;display:inline-block;min-width:6mm}
.q{font-size:8.5pt;color:var(--muted);margin:.5mm 0 3mm;
   page-break-after:avoid}
.sec-body{page-break-inside:avoid}
.sec-body p{margin:0 0 2mm}
.note{font-size:9pt;color:var(--muted)}
.num{font-variant-numeric:tabular-nums;font-weight:700}
.unit{font-size:.86em;font-weight:400}
.risk{color:var(--hi);font-weight:700}
figure{margin:3mm 0 0;page-break-inside:avoid}
table{border-collapse:collapse;width:100%;font-size:9pt;margin:3mm 0;
      page-break-inside:avoid}
th,td{border:0;border-bottom:.5pt solid var(--line);padding:1.6mm 2mm;
      text-align:left}
th{background:var(--soft);font-weight:600;font-size:8.5pt;color:var(--muted);
   border-bottom:.8pt solid var(--line)}
td.r,th.r{text-align:right;font-variant-numeric:tabular-nums}
footer{margin-top:8mm;padding-top:2mm;border-top:.6pt solid var(--line);
       font-size:8pt;color:var(--muted)}
@media screen{body{background:#f8fafc}
  .page{background:#fff;max-width:210mm;padding:18mm 16mm;margin:6mm auto;
        box-shadow:0 1px 3px rgba(0,0,0,.12)}}
"""

# 숫자를 굵게, 단위를 한 단계 작게. 문장을 고치지 않고 **표시만** 바꾼다.
_N = re.compile(r"(?<![\w.])(\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)\s*"
                r"(%p|%|건|일|배)?(?![\w])")


def _mark_numbers(s: str) -> str:
    def rep(m):
        n, unit = m.group(1), m.group(2) or ""
        u = f'<span class="unit">{unit}</span>' if unit else ""
        return f'<span class="num">{n}</span>{u}'
    return _N.sub(rep, s)


# ★ 사람이 쓸 자리가 빈 채로 나가면 **그 자리가 있었다는 것**을 보여준다.
#   채우면 아무도 빈 줄 모른다 (리포트 8장과 같다).
NOT_WRITTEN = "(작성되지 않음)"


def to_html(secs: list[dict], topic: dict | None = None) -> str:
    """제안서를 **단일 파일 HTML** 로. A4 인쇄 기준.

    ★ 맨 앞의 한 장 요약은 본문 여섯 절을 **압축한 것**이라 순서가 같다.
      (현황 → 원인 → 규모 → 제안 → 위험 → 요청)
    """
    import html as _h

    def esc(x) -> str:
        return _h.escape(str(x))

    topic = topic or {}
    body = []

    # ── 한 장 요약 — 절마다 **첫 문장 하나씩** ───────────────────
    #   이것만 읽고 결정할 수 있어야 하므로 읽을 것이 늘면 결정이 늦어진다.
    lines = []
    for s in secs:
        # ★ 사람 절은 **사람이 쓴 문장**을 올린다. 요청 절의 첫 문장은 규모라
        #   그대로 올리면 요약에 규모가 두 번 나오고 **결정 요구가 빠진다.**
        if s["kind"] == "human":
            first = s["사람"] or NOT_WRITTEN
        else:
            first = s["문장"][0] if s["문장"] else ""
        if not first:
            continue
        lines.append(f'<p><b>{esc(s["key"])}</b>　'
                     f'{_mark_numbers(esc(first))}</p>')
    if lines:
        body.append('<div class="sum"><h2>한 장 요약</h2>'
                    + "".join(lines) + "</div>")

    # ── 본문 ───────────────────────────────────────────────────
    for i, s in enumerate(secs, 1):
        문장 = s["문장"]
        if not 문장:
            if s["kind"] != "human":
                continue                  # 자동 절은 문장이 없으면 절이 없다
            # ★ **사람이 안 쓴 절은 빈 채로 드러낸다.** 조용히 빼면 읽는 사람은
            #   위험을 따지지 않은 문서인 줄 모른다. 리포트 8장과 같은 방식.
            문장 = [NOT_WRITTEN]
        elif s["kind"] == "human" and not s["사람"]:
            # 요청 절은 자동 문장이 있어 **비어도 안 빈 것처럼 보인다.**
            # 맨 뒤에 붙여 문서의 마지막 줄이 빈 자리임을 드러낸다.
            문장 = 문장 + [NOT_WRITTEN]
        ps = "".join(f'<p>{_mark_numbers(esc(x))}</p>' for x in 문장)
        fig = (f'<figure>{s["차트"]}</figure>' if s["차트"] else "")
        risk = ' class="risk"' if s["key"] == "요청" else ""
        body.append(
            f'<h2 class="sec"><span class="n">{i}</span>'
            f'<span{risk}>{esc(s["제목"])}</span></h2>'
            f'<p class="q">{esc(s["질문"])}</p>'
            f'<div class="sec-body">{ps}{fig}</div>')

    작성 = topic.get("작성") or C.TODAY
    # 합성 문구(footer)는 config.SHOW_SYNTHETIC_NOTE 가 켜졌을 때만 싣는다.
    # 2026-09-12 기쁨 결정으로 기본 False — 지우지 않고 플래그로 둔다(회사 결재로 나갈 땐 되돌린다).
    return (
        '<!DOCTYPE html>\n<html lang="ko">\n<head>\n<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f'<title>{esc(topic.get("제목") or "제안서")}</title>\n'
        f'<style>{_A4_CSS}</style>\n</head>\n<body>\n<div class="page">\n'
        f'<h1>{esc(topic.get("제목") or "제안서")}</h1>'
        f'<div class="sub">{esc(topic.get("한줄", ""))}</div>'
        f'<div class="meta">'
        f'<span>대상 <b>{esc(C.DATASET_PUBLIC)}</b></span>'
        f'<span>기간 <b>{C.PERIOD[0]} ~ {C.PERIOD[1]}</b></span>'
        f'<span>기준일 <b>{작성}</b></span>'
        # ★ **무엇을 하나로 세는지 문서에 적는다** (2026-09-12).
        #   7주차 함정 ① — 그레인이 문서에 없으면 읽는 사람은 숫자마다
        #   다른 모집단인 것을 모른다. 머리에 한 번 적으면 본문이 안 길어진다.
        f'<span>세는 단위 <b>{esc(C.GRAIN_UNIT)}</b></span></div>'
        + "".join(body)
        + (('<footer>데이터는 전부 합성입니다. 방법은 확인할 수 있으나 '
          '판정은 실제 데이터로만 할 수 있습니다. '
          '집단별 차이는 데이터를 만들 때 넣은 값이라, 실제로 같은 차이가 '
          '나올지는 확인되지 않았습니다.</footer>') if C.SHOW_SYNTHETIC_NOTE else '')
        +
        '</div>\n</body>\n</html>')
