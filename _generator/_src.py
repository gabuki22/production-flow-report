# -*- coding: utf-8 -*-
"""값 풀(원천 자료)이 어디 있는지 찾는다 — 이름을 코드에 박지 않는다.

합성 데이터는 실제 도번·색상·거래처 코드의 **값 분포**를 흉내 내려고
강의 폴더의 raw/ 를 값 풀로 쓴다. 그 폴더는 **이 저장소에 없다**
(원천 자료는 공개하지 않는다) — 그래서 `data/*.parquet` 을 커밋해 둔다.
앱을 돌리는 데는 필요 없고, **다시 만들 때만** 필요하다.

찾는 순서
  1. 환경변수 `MYDATA_SRC` — 사람이 직접 넘긴 것이 언제나 이긴다
  2. 옆에 있는 강의 폴더의 `raw/` — PC 마다 폴더 이름이 달라 glob 으로 찾는다
  3. 못 찾으면 `_원천/raw` 를 돌려준다. 없는 경로라 읽을 때 바로 터진다 —
     조용히 빈 값으로 넘어가면 **엉뚱한 분포의 데이터가 만들어진다.**
"""
from __future__ import annotations

import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
SIBLINGS = HERE.parent.parent          # 강의 폴더들이 나란히 있는 자리


def find_src() -> Path:
    env = os.environ.get("MYDATA_SRC")
    if env:
        return Path(env)
    for p in sorted(SIBLINGS.glob("EDATA*")):
        if (p / "raw").is_dir():
            return p / "raw"
    return SIBLINGS / "_원천" / "raw"


SRC = find_src()
