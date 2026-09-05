# -*- coding: utf-8 -*-
"""파일 지도 — 어떤 파일이 무엇을 하는가.

  py -X utf8 파일지도.py            # 화면에 보기
  py -X utf8 파일지도.py --write    # 파일지도.md 로 저장

────────────────────────────────────────────────────────────────────
★ 왜 이걸 만들었나 (2026-09-04 강사 코멘트)

  *"개발 전공이 아니면 어떤 파일이 무엇을 하는지 따로 공부해야 한다.
    시키기만 하면 고칠 곳을 못 찾는다."*

강사는 VS Code 로 강의한다 — 파일 트리와 코드가 늘 눈에 보이는 편집기다.
나는 Claude Code 데스크탑 앱 + 옵시디언이라 **파일 트리를 늘 보고 있지 않다.**
그래서 "무엇이 어디 있는가"를 문서로 갖고 있어야 한다.

★ **손으로 적지 않는다.** 손으로 적은 목록은 파일이 늘거나 역할이 바뀔 때
  반드시 어긋난다 — 그리고 어긋난 지도는 없는 것보다 나쁘다.
  각 파일 맨 위의 설명(docstring)을 **코드에서 그대로 읽어** 만든다.
  설명이 없는 파일은 🔴 로 드러난다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent

# 폴더가 무엇을 맡는가 — 이건 사람이 정하는 것이라 여기 적는다
ZONES = {
    "": ("진입", "앱을 켜면 처음 뜨는 화면"),
    "core": ("계산과 규칙", "숫자가 만들어지는 곳. **화면은 여기를 부르기만 한다**"),
    "pages": ("화면", "사람이 보는 것. 계산하지 않는다"),
    "report": ("문서", "숫자를 문장과 파일로 바꾼다"),
    "viz": ("그림", "차트와 공용 UI. 계산하지 않는다"),
    "tests": ("검사", "바꾸기 전에 돌린다"),
}

SKIP = ("__pycache__", "_generator", "_참고자료")


def scan() -> list[dict]:
    out = []
    for f in sorted(ROOT.rglob("*.py")):
        rel = f.relative_to(ROOT).as_posix()
        if any(s in rel for s in SKIP) or rel == Path(__file__).name:
            continue
        src = f.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src)
        except SyntaxError:
            out.append({"path": rel, "lines": len(src.splitlines()),
                        "doc": "", "api": [], "zone": rel.split("/")[0]
                        if "/" in rel else ""})
            continue
        doc = (ast.get_docstring(tree) or "").strip()
        api = [n.name for n in tree.body
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
               and not n.name.startswith("_")]
        out.append({
            "path": rel,
            "lines": len(src.splitlines()),
            "doc": doc,
            "api": api,
            "zone": rel.split("/")[0] if "/" in rel else "",
        })
    return out


def render(files: list[dict]) -> str:
    L = ["# 파일 지도 — 어떤 파일이 무엇을 하는가", "",
         "> **이 파일은 손으로 고치지 않는다.** `py -X utf8 파일지도.py --write` 로 다시 만든다.",
         "> 설명은 각 `.py` 맨 위에서 그대로 읽어 온다 — 코드를 고치면 여기도 따라온다.", ""]

    total = sum(f["lines"] for f in files)
    L += [f"`.py` **{len(files)}개 · {total:,}줄**", "", "---", ""]

    for zone, (name, why) in ZONES.items():
        group = [f for f in files if f["zone"] == zone]
        if not group:
            continue
        head = f"`{zone}/`" if zone else "루트"
        L += [f"## {head} — {name}", "", why, "",
              "| 파일 | 줄 | 하는 일 |", "|---|---:|---|"]
        for f in group:
            first = f["doc"].split("\n")[0] if f["doc"] else "🔴 **설명 없음**"
            L.append(f"| `{f['path'].split('/')[-1]}` | {f['lines']:,} | {first} |")
        L.append("")

    # 바깥에서 부를 수 있는 것 — "고칠 곳"을 찾을 때 여기부터 본다
    L += ["---", "", "## 바깥에서 부르는 것", "",
          "함수 이름으로 찾으면 어느 파일을 열지 알 수 있다.", ""]
    for f in files:
        if f["api"]:
            L.append(f"- **`{f['path']}`** — " + " · ".join(f"`{a}()`" for a in f["api"]))
    L.append("")

    missing = [f["path"] for f in files if not f["doc"]]
    if missing:
        L += ["---", "", "## 🔴 설명이 없는 파일", "",
              "맨 위에 이 파일이 무엇을 하는지 한 줄 적으십시오.", ""]
        L += [f"- `{m}`" for m in missing] + [""]

    return "\n".join(L)


if __name__ == "__main__":
    files = scan()
    md = render(files)
    if "--write" in sys.argv:
        out = ROOT / "파일지도.md"
        out.write_text(md, encoding="utf-8")
        print(f"저장: {out.name} · {len(md.splitlines())}줄")
    else:
        print(md)
    # 설명 없는 파일이 있으면 exit 1 — 커밋 전 게이트로 쓸 수 있다
    sys.exit(1 if any(not f["doc"] for f in files) else 0)
