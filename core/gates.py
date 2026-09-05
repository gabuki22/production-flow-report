# -*- coding: utf-8 -*-
"""게이트와 실행 상태.

게이트는 **사람이 판단하는 지점**이다. 앱은 판단하지 않고 판단할 재료만 놓는다.
누가 언제 무엇을 보고 통과시켰는지 run_log에 남긴다 — 이것이 거버넌스 기록이 된다.

  1 입구  프로파일 후   되돌릴 수 있다
  2 출구  계산 후       되돌릴 수 있다
  3 발송  초안 후       **되돌릴 수 없다**
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from core import config as C

STEPS = ["적재", "프로파일", "검증", "게이트1", "계산", "대시보드", "리포트", "발송"]

GATES = {
    1: {"after": "검증", "name": "입구", "reversible": True,
        "question": "이 데이터로 분석을 시작해도 되는가?"},
    2: {"after": "계산", "name": "출구", "reversible": True,
        "question": "계산 결과가 말이 되는가?"},
    3: {"after": "리포트", "name": "발송", "reversible": False,
        "question": "이대로 내보내도 되는가?"},
}


def new_run(dataset: str = C.DATASET) -> dict:
    return {
        "run_id": datetime.now().strftime("%Y%m%d-%H%M%S"),
        "dataset": dataset,
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "step": 0,
        "log": [],
        "gates": {},
        "status": "진행중",
    }


def log(run: dict, msg: str, level: str = "ok") -> None:
    run["log"].append({
        "at": datetime.now().strftime("%H:%M:%S"),
        "msg": msg, "level": level,
    })


def advance(run: dict, to_step: str) -> None:
    run["step"] = max(run["step"], STEPS.index(to_step) + 1)


def pass_gate(run: dict, n: int, note: str = "", by: str = "사용자") -> None:
    """게이트 통과를 기록한다. 되돌릴 수 없는 게이트는 여기서 확정된다."""
    run["gates"][str(n)] = {
        "passed_at": datetime.now().isoformat(timespec="seconds"),
        "by": by, "note": note,
        "reversible": GATES[n]["reversible"],
    }
    log(run, f"게이트 {n}({GATES[n]['name']}) 통과" +
        (f" — {note}" if note else ""), "ok")


def revert_gate(run: dict, n: int) -> bool:
    """되돌린다. 게이트 3은 되돌릴 수 없다."""
    if not GATES[n]["reversible"]:
        return False
    run["gates"].pop(str(n), None)
    run["step"] = STEPS.index(GATES[n]["after"])
    log(run, f"게이트 {n}({GATES[n]['name']}) 되돌림", "warn")
    return True


def is_passed(run: dict, n: int) -> bool:
    return str(n) in run.get("gates", {})


# ── 실행 이력 저장 ────────────────────────────────────────────────
def save(run: dict) -> Path:
    C.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    p = C.RUNS_DIR / f"{run['run_id']}.json"
    p.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_all() -> list[dict]:
    if not C.RUNS_DIR.exists():
        return []
    out = []
    for p in sorted(C.RUNS_DIR.glob("*.json"), reverse=True):
        try:
            out.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return out


# ── 사람이 쓴 장 — 디스크에 남긴다 (2026-09-05) ───────────────────
# ⚠️ **이걸 안 하고 있었다.** st.session_state 는 메모리뿐이라 서버를
#    다시 켜면 사라진다. 2026-09-05 에 사람이 써 둔 배경·해석·제안이
#    내가 서버를 재시작하면서 **통째로 날아갔다.**
#
#    이 앱에서 가장 값진 것이 사람이 쓴 장이다 — 자동화하지 않는 이유가
#    "틀렸을 때 누가 책임지는가"이고, 그래서 사람이 시간을 들여 쓴다.
#    그 글이 새로고침 한 번에 사라지면 다음부터 아무도 안 쓴다.
#
# ★ 자동 저장은 하지 않는다. 교안 프롬프트 10 이 "저장을 누를 때만 저장된다"
#   고 했고, 폼의 목적이 그것이다. **누른 것만 남긴다.**
def save_human(human: dict) -> Path:
    """사람이 쓴 장을 파일로. 저장을 누를 때마다 덮어쓴다."""
    C.DRAFTS_DIR.mkdir(parents=True, exist_ok=True)
    p = C.DRAFTS_DIR / "human.json"
    p.write_text(json.dumps(
        {"saved_at": datetime.now().isoformat(timespec="seconds"),
         "dataset": C.DATASET, "sections": human},
        ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_human() -> tuple[dict, str | None]:
    """저장해 둔 것을 돌려준다. (본문, 저장시각) · 없으면 ({}, None)."""
    p = C.DRAFTS_DIR / "human.json"
    if not p.exists():
        return {}, None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}, None
    # ⚠️ 데이터셋이 바뀌었으면 남의 글이다. 숫자가 달라진 리포트에 옛 해석이
    #    그대로 붙으면 **사실과 다른 문서**가 된다.
    if d.get("dataset") != C.DATASET:
        return {}, None
    return d.get("sections", {}), d.get("saved_at")
