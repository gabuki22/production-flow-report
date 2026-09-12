# -*- coding: utf-8 -*-
"""로컬 parquet → BigQuery 적재.

  py -X utf8 _generator/to_bigquery.py            # 무엇을 올릴지만 보여준다
  py -X utf8 _generator/to_bigquery.py --apply    # 실제로 올린다

────────────────────────────────────────────────────────────────────
★ **dry-run 이 기본이다.** `--apply` 없이는 아무것도 안 올린다.
  BigQuery 는 쓰기가 과금되고 되돌리기가 번거롭다 —
  무엇이 올라갈지 눈으로 본 다음에 누른다.

★ 데이터는 **전부 합성**이다. 실 ERP 반출이 안 돼 스키마와 값 체계만
  복제했으므로 클라우드에 올려도 사내 정보가 나가지 않는다.
  ⚠️ 실데이터로 바꾸는 날에는 **이 전제가 깨진다.** 그때는 올리기 전에
     무엇이 나가는지 다시 세어야 한다.

★ 한글 컬럼명은 BigQuery 가 받아준다(유니코드 허용). 다만 SQL 에서
  백틱으로 감싸야 해서, 쿼리를 쓸 사람이 헷갈린다 —
  그래서 **원본 이름을 그대로 두되** 표마다 설명(description)에 적어 둔다.
────────────────────────────────────────────────────────────────────
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))

from core import config as C            # noqa: E402

# ★ 프로젝트·데이터셋·위치는 config 한 곳에서 읽는다 — 로더(load.py)와 같은 값이어야
#   올린 곳과 읽는 곳이 갈리지 않는다. (2026-09-12 · 전에는 여기 US 로 박혀 있었다)
PROJECT, DATASET, LOCATION = C.BQ_PROJECT, C.BQ_DATASET, C.BQ_LOCATION

# 올릴 표 — 앱이 읽는 것과 같다(config.TABLES). 목록을 여기 또 적지 않는다.
TABLES = list(C.TABLES)

NOTE = (f"{C.DATASET} (합성 데이터). "
        "실 ERP 반출 불가로 스키마·값 체계만 복제했다. "
        f"그레인 = {C.GRAIN}. 판정은 실데이터로만 할 수 있다.")


def _client():
    from google.cloud import bigquery
    return bigquery.Client(project=PROJECT)


def main(apply: bool) -> int:
    files = [(t, C.DATA_DIR / f"{t}.parquet") for t in TABLES]
    missing = [t for t, p in files if not p.exists()]
    if missing:
        print("🔴 없는 파일:", " · ".join(missing))
        return 1

    print(f"프로젝트 {PROJECT} · 데이터셋 {DATASET} · 위치 {LOCATION}")
    print(f"{'표':24} {'행':>10} {'열':>4}  {'크기':>8}")
    total = 0
    for t, p in files:
        d = pd.read_parquet(p)
        total += len(d)
        print(f"{t:24} {len(d):10,} {len(d.columns):4}  "
              f"{p.stat().st_size/1024/1024:7.1f}MB")
    print(f"{'합계':24} {total:10,}")

    if not apply:
        print("\n※ dry-run 입니다. 실제로 올리려면 --apply 를 붙이십시오.")
        return 0

    from google.cloud import bigquery
    c = _client()
    ds_id = f"{PROJECT}.{DATASET}"
    ds = bigquery.Dataset(ds_id)
    ds.location = LOCATION
    ds.description = NOTE
    c.create_dataset(ds, exists_ok=True)
    print(f"\n데이터셋 준비 완료 — {ds_id}")

    for t, p in files:
        d = pd.read_parquet(p)
        # 날짜 문자열은 문자열 그대로 둔다. 여기서 파싱해 타입을 바꾸면
        # **로컬 계산과 클라우드 계산이 갈린다** — 같은 값이어야 한다.
        job = c.load_table_from_dataframe(
            d, f"{ds_id}.{t}",
            job_config=bigquery.LoadJobConfig(
                write_disposition="WRITE_TRUNCATE"))
        job.result()
        tbl = c.get_table(f"{ds_id}.{t}")
        tbl.description = f"{NOTE} · 원본 {p.name}"
        c.update_table(tbl, ["description"])
        print(f"  ○ {t:24} {tbl.num_rows:10,}행")

    print(f"\n올렸습니다 — {ds_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main("--apply" in sys.argv))
