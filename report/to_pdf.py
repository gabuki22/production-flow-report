# -*- coding: utf-8 -*-
"""PDF 생성 (fpdf2).

한글 폰트는 Noto Sans KR(OFL)을 쓴다. 맑은 고딕은 재배포가 불가능하므로
앱에 동봉할 수 없다 — 라이선스는 배포 단계에서 실제로 문제가 된다.

fpdf2는 상태 저장형이다. set_font / set_text_color를 바꾸면 이후 계속 유지되므로
블록마다 명시적으로 지정한다.

────────────────────────────────────────────────────────────────────
★ 2026-09-05 전면 재설계 — 요청: *"PPT처럼 짜임새 있는 위치와 비주얼로"*

전에는 제목 → 가는 선 → 본문 텍스트가 전부였다. 내용은 다 있는데
**어디가 중요한지, 어디서 덩어리가 갈리는지 눈이 못 잡았다.**

바꾼 것 넷
  1. 표지  — 색 띠 · 큰 제목 · **지표 넷을 카드로**. 한 장만 봐도 상태를 안다
  2. 목차  — 자동/사람을 구분해 표시하고 쪽 번호를 단다
  3. 장    — 왼쪽에 **번호 블록**, 오른쪽에 제목. 슬라이드 머리처럼 고정된 자리
  4. 본문  — `· 불릿`·`**소제목**`·`[주의]` 를 각각 다르게 그린다.
             전에는 셋 다 같은 크기 같은 색이라 눈이 훑을 수가 없었다

⚠️ **지면 규격을 한곳에 모았다**(아래 상수). 여백·줄높이·색이 함수마다
   흩어져 있으면 한 곳만 고치는 날이 오고, 그때부터 장마다 조금씩 어긋난다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import io
import re
from datetime import datetime

from fpdf import FPDF

from core import config as C

FONT_DIR = C.ROOT / "fonts"

# ── 지면 규격 — 여기만 고친다 ────────────────────────────────────
MARGIN = 18            # mm · 좌우 여백
BAND_H = 13            # 장 머리 색 띠 높이
NUM_W = 15             # 장 번호 블록 너비
LEAD = 6.0             # 본문 줄 높이
GAP = 3.2              # 문단 사이
BODY_PT = 10.2
HEAD_PT = 14.5

INK = (15, 23, 42)
MUTED = (100, 116, 139)
LINE = (226, 232, 240)
PAPER = (248, 250, 252)


def _hex(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


PRIMARY = _hex(C.BRAND["primary"])
OKC = _hex(C.COLORS["ok"])
WARNC = _hex(C.COLORS["warn"])
BLOCKC = _hex(C.COLORS["block"])


class Report(FPDF):
    def __init__(self):
        super().__init__(orientation="P", unit="mm", format="A4")
        self.set_margins(MARGIN, MARGIN, MARGIN)
        self.set_auto_page_break(True, margin=22)
        self.has_kr = False
        reg, bold = FONT_DIR / "NotoSansKR-Regular.ttf", FONT_DIR / "NotoSansKR-Bold.ttf"
        if reg.exists():
            self.add_font("Noto", "", str(reg))
            self.add_font("Noto", "B", str(bold) if bold.exists() else str(reg))
            self.has_kr = True
        self.base = "Noto" if self.has_kr else "Helvetica"
        self.body_start = 3        # 본문이 시작하는 물리 쪽 (build_pdf 가 갱신)

    @property
    def inner(self) -> float:
        """본문 가로 폭."""
        return self.w - self.l_margin - self.r_margin

    def header(self):
        # ⚠️ self.cover 플래그로 가르면 안 된다 — 머리글·발치는 페이지가
        #    **닫힐 때** 그려지는데, 그때는 플래그가 이미 바뀌어 있다.
        #    실제로 목차 쪽 발치에 "0" 이 찍혔다. **쪽 번호로 가른다.**
        if self.page_no() < self.body_start:
            return
        self.set_font(self.base, "", 7.5)
        self.set_text_color(*MUTED)
        self.set_y(9)
        self.cell(0, 5, f"{C.APP_NAME}  ·  {C.DATASET}", align="L")
        self.cell(0, 5, f"{C.PERIOD[0]} ~ {C.PERIOD[1]}", align="R")
        self.set_draw_color(*LINE)
        self.set_line_width(0.2)
        self.line(self.l_margin, 15.5, self.w - self.r_margin, 15.5)
        self.set_y(MARGIN + 3)

    def footer(self):
        if self.page_no() < self.body_start:
            return
        self.set_y(-14)
        self.set_font(self.base, "", 7.5)
        self.set_text_color(*MUTED)
        # ★ 합성 데이터라는 사실을 **모든 쪽 발치에** 둔다. 표지에만 적으면
        #   중간부터 읽는 사람은 실측으로 읽는다.
        self.cell(0, 5, "합성 데이터 — 판정은 실데이터로만", align="L")
        # ⚠️ page_no() - 2 로 박아 뒀더니 표지가 한 장 늘자 목차 번호와
        #    어긋났다. **본문이 실제로 시작한 쪽**을 기억해서 뺀다.
        self.cell(0, 5, str(self.page_no() - self.body_start + 1), align="R")


# ── 조각들 ────────────────────────────────────────────────────────
def _kpi_cards(pdf: Report, kpis: list[tuple[str, str, str]]) -> None:
    """지표 카드 한 줄. (이름, 값, 상태) · 상태는 ok/warn/block/none."""
    if not kpis:
        return
    gap = 4
    w = (pdf.inner - gap * (len(kpis) - 1)) / len(kpis)
    h = 26
    y = pdf.get_y()
    tone = {"ok": OKC, "warn": WARNC, "block": BLOCKC, "none": MUTED}
    for i, (name, value, level) in enumerate(kpis):
        x = pdf.l_margin + i * (w + gap)
        pdf.set_fill_color(*PAPER)
        pdf.rect(x, y, w, h, style="F")
        # 왼쪽 세로 막대로 상태를 말한다 — 글자색으로만 하면 흑백 인쇄에서 사라진다
        pdf.set_fill_color(*tone.get(level, MUTED))
        pdf.rect(x, y, 1.6, h, style="F")
        pdf.set_xy(x + 5, y + 4.5)
        pdf.set_font(pdf.base, "", 8)
        pdf.set_text_color(*MUTED)
        pdf.cell(w - 8, 4, name)
        pdf.set_xy(x + 5, y + 10.5)
        pdf.set_font(pdf.base, "B", 16)
        pdf.set_text_color(*INK)
        pdf.cell(w - 8, 9, value)
    pdf.set_y(y + h)


def _chapter_head(pdf: Report, num: str, title: str, kind: str) -> None:
    """장 머리 — 왼쪽 번호 블록 + 오른쪽 제목. 자리를 고정해 슬라이드처럼 읽힌다."""
    y = pdf.get_y()
    pdf.set_fill_color(*PRIMARY)
    pdf.rect(pdf.l_margin, y, NUM_W, BAND_H, style="F")
    pdf.set_xy(pdf.l_margin, y + 2.6)
    pdf.set_font(pdf.base, "B", 12)
    pdf.set_text_color(255, 255, 255)
    pdf.cell(NUM_W, 8, num, align="C")

    pdf.set_xy(pdf.l_margin + NUM_W + 5, y + 2.2)
    pdf.set_font(pdf.base, "B", HEAD_PT)
    pdf.set_text_color(*INK)
    pdf.cell(pdf.inner - NUM_W - 40, 9, title)

    # 자동/사람 표시 — 이 문서에서 가장 중요한 구분이라 장마다 되풀이한다
    label = {"auto": "자동 생성", "human": "사람 작성"}.get(kind, kind)
    pdf.set_font(pdf.base, "", 8)
    pdf.set_text_color(*(PRIMARY if kind == "human" else MUTED))
    pdf.set_xy(pdf.w - pdf.r_margin - 30, y + 4.4)
    pdf.cell(30, 5, label, align="R")

    pdf.set_y(y + BAND_H + 6)


def _note_box(pdf: Report, text: str, tone=WARNC) -> None:
    """[주의] 같은 줄은 배경 있는 상자로. 본문과 같은 크기면 그냥 지나친다."""
    pdf.set_font(pdf.base, "", 9.2)
    x, y = pdf.l_margin, pdf.get_y()
    pad = 3.2
    lines = pdf.multi_cell(pdf.inner - 10, LEAD - 0.6, text, dry_run=True,
                           output="LINES", markdown=True)
    h = len(lines) * (LEAD - 0.6) + pad * 2
    if y + h > pdf.h - 24:
        pdf.add_page()
        y = pdf.get_y()
    pdf.set_fill_color(253, 250, 244)
    pdf.rect(x, y, pdf.inner, h, style="F")
    pdf.set_fill_color(*tone)
    pdf.rect(x, y, 1.4, h, style="F")
    pdf.set_xy(x + 5, y + pad)
    pdf.set_text_color(*INK)
    pdf.multi_cell(pdf.inner - 10, LEAD - 0.6, text, markdown=True,
                   new_x="LMARGIN", new_y="NEXT")
    pdf.set_y(y + h + GAP)


_SUBHEAD = re.compile(r"^\*\*(.+?)\*\*$")


def _body(pdf: Report, text: str) -> None:
    """본문 — 소제목·불릿·주의를 **다르게** 그린다.

    전에는 셋 다 같은 크기 같은 색이라 눈이 훑을 수가 없었다.
    본문 표기는 화면과 같은 마크다운이다(`**강조**` · `· 불릿`).
    """
    for block in text.strip().split("\n\n"):
        # ★ [주의] 는 **문단 통째로** 상자에 넣는다.
        #   줄 단위로 갈랐더니 첫 줄만 상자에 들어가고 둘째 줄이 밖으로
        #   튀어나왔다 — 한 문장이 두 모양으로 그려져 오히려 어수선했다.
        head = block.strip()
        if head.startswith("[주의]") or head.startswith("⚠"):
            _note_box(pdf, head.replace("[주의]", "", 1).strip().replace("\n", " "))
            continue

        for raw in block.split("\n"):
            s = raw.strip()
            if not s:
                continue

            m = _SUBHEAD.match(s)
            if m:                                   # **소제목**
                pdf.ln(1.5)
                pdf.set_font(pdf.base, "B", 11)
                pdf.set_text_color(*PRIMARY)
                pdf.multi_cell(0, LEAD, m.group(1),
                               new_x="LMARGIN", new_y="NEXT")
                pdf.ln(0.8)
                continue

            if s.startswith("[주의]") or s.startswith("⚠"):
                _note_box(pdf, s.replace("[주의]", "").strip())
                continue

            if s.startswith("·"):                   # 불릿 — 들여쓰고 점을 따로
                body = s[1:].strip()
                # ⚠️ 점과 본문을 **따로** 그리므로 그 사이에 페이지가 넘어가면
                #    점만 다음 쪽에 홀로 남는다(실제로 점 하나뿐인 쪽이 나왔다).
                #    y 를 잡기 전에 자리가 있는지 먼저 본다.
                need = LEAD * (1 + len(body) // 60)
                if pdf.get_y() + need > pdf.h - 24:
                    pdf.add_page()
                y = pdf.get_y()
                pdf.set_font(pdf.base, "B", BODY_PT)
                pdf.set_text_color(*PRIMARY)
                pdf.set_xy(pdf.l_margin + 1.5, y)
                pdf.cell(4, LEAD, "·")
                pdf.set_font(pdf.base, "", BODY_PT)
                pdf.set_text_color(*INK)
                pdf.set_xy(pdf.l_margin + 6, y)
                # ⚠️ new_x 를 안 주면 x 가 오른쪽 끝에 남는다. 다음 문단이
                #    multi_cell(0, ...) 로 "현재 x → 우측 여백" 폭을 잡는데
                #    그게 0 이 되어 "Not enough horizontal space" 로 죽는다.
                pdf.multi_cell(pdf.inner - 6, LEAD, body, markdown=True,
                               new_x="LMARGIN", new_y="NEXT")
                continue

            pdf.set_font(pdf.base, "", BODY_PT)     # 보통 문단
            pdf.set_text_color(*INK)
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(0, LEAD, s, markdown=True,
                           new_x="LMARGIN", new_y="NEXT")
        pdf.ln(GAP)


def build_pdf(sections: list[dict], charts: dict[str, bytes],
              title: str | None = None,
              kpis: list[tuple[str, str, str]] | None = None) -> bytes:
    """리포트 PDF.

    kpis — 표지에 실을 (이름, 값, 상태) 목록. 없으면 카드를 안 그린다.
           **여기서 계산하지 않는다** — 화면과 다른 값이 실리면 안 된다.
    """
    title = title or C.APP_NAME
    pdf = Report()

    # ── 표지 ──────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_fill_color(*PRIMARY)
    pdf.rect(0, 0, pdf.w, 6, style="F")          # 위쪽 색 띠

    pdf.ln(46)
    pdf.set_font(pdf.base, "", 11)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 7, C.DATASET, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.set_font(pdf.base, "B", 30)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 14, title, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)
    pdf.set_font(pdf.base, "", 11.5)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(0, 7, C.APP_TAGLINE, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(4)
    pdf.set_draw_color(*PRIMARY)
    pdf.set_line_width(1.4)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.l_margin + 34, pdf.get_y())
    pdf.ln(12)

    if kpis:
        pdf.set_font(pdf.base, "", 9)
        pdf.set_text_color(*MUTED)
        pdf.cell(0, 6, "지표", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)
        _kpi_cards(pdf, kpis)
        pdf.ln(10)

    pdf.set_font(pdf.base, "", 9.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, f"기간  {C.PERIOD[0]} ~ {C.PERIOD[1]}",
             new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"그레인  {C.GRAIN}", new_x="LMARGIN", new_y="NEXT")
    pdf.cell(0, 6, f"생성  {datetime.now():%Y-%m-%d %H:%M}",
             new_x="LMARGIN", new_y="NEXT")

    # 표지 발치 — 이 문서의 성격
    # ⚠️ 자리를 -32 로 잡았더니 상자가 **2쪽으로 밀려났다.** 표지에 있어야 하는
    #    문장이 혼자 한 장을 차지했다. 높이를 재서 그만큼 위로 올린다.
    pdf.set_y(pdf.h - 24 - 20)
    _note_box(pdf, "**데이터는 전부 합성입니다.** 스키마와 값 체계만 복제했으므로 "
                   "**판정은 실데이터로만** 할 수 있습니다.")

    # ── 목차 ──────────────────────────────────────────────────────
    pdf.add_page()
    pdf.set_font(pdf.base, "B", 17)
    pdf.set_text_color(*INK)
    pdf.cell(0, 11, "목차", new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*PRIMARY)
    pdf.set_line_width(1.2)
    pdf.line(pdf.l_margin, pdf.get_y() + 1, pdf.l_margin + 24, pdf.get_y() + 1)
    pdf.ln(9)

    for i, s in enumerate(sections, 1):
        num = s["title"].split(".")[0].strip()
        name = s["title"].split(".", 1)[-1].strip()
        y = pdf.get_y()
        pdf.set_font(pdf.base, "B", 10.5)
        pdf.set_text_color(*PRIMARY)
        pdf.cell(9, 8, num)
        pdf.set_font(pdf.base, "", 11)
        pdf.set_text_color(*INK)
        pdf.cell(pdf.inner - 45, 8, name)
        # 자동/사람 · 빈 장이면 그렇다고 적는다 — 목차에서 이미 보여야 한다
        empty = s["kind"] == "human" and not (s.get("body") or "").strip()
        tag = ("작성되지 않음" if empty
               else {"auto": "자동 생성", "human": "사람 작성"}.get(s["kind"], ""))
        pdf.set_font(pdf.base, "", 8.5)
        pdf.set_text_color(*(WARNC if empty else MUTED))
        pdf.cell(26, 8, tag, align="R")
        pdf.set_font(pdf.base, "", 9)
        pdf.set_text_color(*MUTED)
        # 본문 기준 쪽 번호 — 발치에 찍히는 것과 같아야 한다(요약이 1쪽)
        pdf.cell(10, 8, str(i), align="R", new_x="LMARGIN", new_y="NEXT")
        pdf.set_draw_color(*LINE)
        pdf.set_line_width(0.2)
        pdf.line(pdf.l_margin, y + 8.4, pdf.w - pdf.r_margin, y + 8.4)

    # ── 본문 ──────────────────────────────────────────────────────
    pdf.body_start = pdf.page_no() + 1        # 다음 add_page 가 본문 1쪽
    for s in sections:
        pdf.add_page()
        num = s["title"].split(".")[0].strip()
        name = s["title"].split(".", 1)[-1].strip()
        _chapter_head(pdf, num, name, s["kind"])

        body = (s.get("body") or "").strip()
        if not body:
            _note_box(pdf,
                      "**작성되지 않음** — " + (s.get("placeholder") or
                      "사람이 쓰는 장입니다."), tone=WARNC)
            continue

        _body(pdf, body)

        for key in s.get("charts", []):
            png = charts.get(key)
            if not png:
                continue
            if pdf.get_y() > 195:
                pdf.add_page()
            pdf.ln(2)
            pdf.image(io.BytesIO(png), w=pdf.inner)
            pdf.ln(4)

    return bytes(pdf.output())
