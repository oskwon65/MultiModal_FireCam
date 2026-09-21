# -*- coding: utf-8 -*-
"""
연속 학습 단계 현황을 파일로 남긴다.

모니터링 프로그램([설정] 창)이 "지금 몇 단계까지 쓰고 있고, 다음 단계까지
얼마나 남았는지" 를 보여주려면 그 값을 알아야 한다. 그런데 기준선 상태는
online_baseline.npz 안에 있고, npz 는 zip 안에 .npy 가 든 형식이라 C++ 에서
읽으려면 파서를 새로 만들어야 한다.

그래서 파이썬이 사실을 아는 쪽에서 평범한 ini 한 장으로 적어 두고, C++ 은
이미 있는 ini_read_utf8 로 읽는다. 값을 계산하는 곳과 보여주는 곳이 갈리지
않는다는 이점도 있다.

이 파일은 사람이 직접 고칠 대상이 아니다. 매번 통째로 덮어쓴다.
"""

import os
from datetime import datetime

STATUS_FILE_NAME = "stage_status.ini"

# 히스토리 DB 건수를 다시 세는 최소 간격(초). 날짜별 테이블마다 COUNT 를
# 돌리므로 매번 할 일은 아니다. 기준선 저장 주기(수십 분)보다 짧게 두면
# 사실상 저장할 때마다 한 번씩 세게 된다.
DB_COUNT_MIN_INTERVAL = 600


def count_history_rows(conn, db_name, min_score=0.5, base_date=None):
    """
    재학습에 쓸 수 있는 정상 프레임이 몇 건인지 센다.

    기준일 이전 테이블은 제외한다. 재학습 표집(replay_buffer)이 쓰는 기준과
    같아야 화면의 숫자와 실제 동작이 맞는다.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = %s
              AND table_name LIKE 'results_history_%%'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
            (db_name,),
        )
        tables = [r[0] for r in cur.fetchall()]

        if base_date:
            cutoff = "results_history_" + str(base_date).replace("-", "")
            tables = [t for t in tables if t >= cutoff]

        total = 0
        for t in tables:
            try:
                cur.execute(
                    f"SELECT COUNT(*) FROM `{db_name}`.`{t}` WHERE mscore >= %s",
                    (min_score,),
                )
                total += int(cur.fetchone()[0] or 0)
            except Exception:
                # 테이블 하나가 잘못되어도 전체 집계를 포기하지 않는다.
                continue
        return total, len(tables)
    finally:
        cur.close()


def find_generation(user_path):
    """마지막으로 승격된 모델 세대. 없으면 (None, None)."""
    p = os.path.join(user_path, "current_generation.txt")
    if not os.path.exists(p):
        return None, None
    try:
        name = open(p, encoding="utf-8").read().strip()
    except Exception:
        return None, None
    if not name:
        return None, None
    # 20260921_081843 -> 2026-09-21 08:18
    try:
        t = datetime.strptime(name, "%Y%m%d_%H%M%S")
        return name, t.strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return name, ""


def _esc(v):
    """ini 값으로 안전하게 쓰기 위해 줄바꿈만 없앤다."""
    return str(v).replace("\r", " ").replace("\n", " ")


def write(path, baseline, model_ready, user_path,
          db_rows=None, db_tables=None, min_retrain=None, stage_used=None):
    """
    현황을 통째로 덮어쓴다.

    stage_used 는 직전 프레임에서 실제로 채점에 쓰인 단계(0/1/2).
    "쓸 수 있다" 와 "지금 쓰고 있다" 는 다르므로 따로 적는다.
    """
    gen_name, gen_time = find_generation(user_path)

    stage1 = baseline.is_ready()
    stage2 = bool(model_ready)
    stage3 = gen_name is not None

    lines = [
        "; 이 파일은 predict_machine 이 자동으로 만듭니다. 직접 고치지 마십시오.",
        "[STATUS]",
        f"UPDATED_AT = {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"BASE_DATE = {_esc(baseline.base_date)}",
        "",
        f"SAMPLES = {baseline.count}",
        f"MIN_SAMPLES = {baseline.min_samples}",
        f"HOURS = {baseline.hours_covered}",
        f"MIN_HOURS = {baseline.min_hours}",
        "",
        f"STAGE1 = {1 if stage1 else 0}",
        f"STAGE2 = {1 if stage2 else 0}",
        f"STAGE3 = {1 if stage3 else 0}",
        f"STAGE_USED = {-1 if stage_used is None else int(stage_used)}",
        "",
        f"GENERATION = {_esc(gen_name or '')}",
        f"GENERATION_AT = {_esc(gen_time or '')}",
        "",
        f"DB_ROWS = {-1 if db_rows is None else int(db_rows)}",
        f"DB_TABLES = {-1 if db_tables is None else int(db_tables)}",
        f"MIN_RETRAIN = {-1 if min_retrain is None else int(min_retrain)}",
    ]

    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, path)
        return True
    except Exception as e:
        print(f"[WARN] 단계 현황을 쓰지 못했습니다: {e}")
        return False
