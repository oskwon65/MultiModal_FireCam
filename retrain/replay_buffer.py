# -*- coding: utf-8 -*-
"""
경험 재생 버퍼 (연속 학습 3단계)

히스토리 DB(results_history_YYYYMMDD)에 쌓인 정상 프레임에서 학습용 표본을
뽑는다. 별도의 수집 장치가 필요 없다 — predict_machine 이 매 주기마다
hot_list(64셀 값)를 이미 기록하고 있다.


[왜 최근 것만 쓰면 안 되는가]

재학습할 때마다 최근 데이터만 쓰면 모델은 옛 패턴을 잊는다. 여름에
재학습한 모델은 겨울 외기의 정상 범위를 모르고, 첫 추위에 온 셀을
이상이라 판정한다. 파국적 망각(catastrophic forgetting)이다.

그래서 전체 기간에서 고르게 뽑는다. 저수지 표집(reservoir sampling)은
전체 개수를 미리 몰라도, 한 번만 훑으면서 고정 크기의 균일 표본을
만들어 준다. 몇 달치가 쌓여도 메모리는 일정하다.


[왜 시간대로 층화하는가]

단순 균일 표집은 데이터가 많은 기간에 끌려간다. 설비가 밤에만 도는
현장이라면 낮 표본이 모자라고, 모델은 낮을 이상으로 본다. 시간대(0~23)와
가동 상태(가동/정지)로 칸을 나눠 각 칸에서 고르게 뽑으면, 어느 조건도
누락되지 않는다.


[안전 규칙] 정상으로 판정된 프레임만 담는다. mscore 가 기준 미만인
프레임을 학습에 넣으면, 서서히 커지는 이상을 모델이 정상으로 배운다.
아직 채점되지 않은 프레임(mscore = -1)도 담지 않는다 — 정상인지 알 수
없는 것은 정상으로 취급하지 않는다.
"""

import json
import random
from collections import defaultdict

import numpy as np

# 이 점수 이상이어야 "정상으로 판정된 프레임" 으로 본다.
NORMAL_MIN_SCORE = 0.5

# 시간대(24) × 가동상태(2) = 48칸. 칸마다 이만큼씩 모아 둔 뒤 최종 표집한다.
# 목표 개수보다 넉넉히 잡아야 칸별 균형을 맞출 여지가 생긴다.
OVERSAMPLE = 2.0


def list_history_tables(cur, db_name):
    """results_history_YYYYMMDD 테이블을 오래된 순으로 돌려준다."""
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
    return [r[0] for r in cur.fetchall()]


class StratifiedReservoir:
    """(시간대, 가동상태) 칸마다 따로 저수지 표집을 돌린다."""

    def __init__(self, per_cell, seed=None):
        self.per_cell = int(per_cell)
        self.cells = defaultdict(list)
        self.seen = defaultdict(int)
        self.rng = random.Random(seed)

    def offer(self, key, value):
        self.seen[key] += 1
        pool = self.cells[key]

        if len(pool) < self.per_cell:
            pool.append(value)
            return

        # 저수지 표집: n 번째 항목을 per_cell/n 확률로 받아들인다.
        # 이렇게 하면 전체를 다 보관하지 않고도 균일 표본이 된다.
        j = self.rng.randrange(self.seen[key])
        if j < self.per_cell:
            pool[j] = value

    def balanced_draw(self, total):
        """
        칸들에서 고르게 뽑아 최대 total 개를 만든다.

        [중복 금지] 같은 프레임을 두 번 담으면 안 된다. 학습 표본이
        부풀어 실제보다 많은 것처럼 보이고, 중복된 프레임에 가중치가
        실려 모델이 그쪽으로 기운다. 모아 둔 것보다 많이 요구받으면
        요구량을 줄일지언정 복제하지 않는다.
        """
        keys = [k for k, v in self.cells.items() if v]
        if not keys:
            return np.empty((0, 0)), {}

        # 칸별로 색인을 섞어 두고, 앞에서부터 꺼내 쓴다.
        order = {k: self.rng.sample(range(len(self.cells[k])), len(self.cells[k]))
                 for k in keys}
        taken = {k: 0 for k in keys}
        out = []

        # 1) 칸마다 할당량만큼
        quota = max(1, total // len(keys))
        for k in keys:
            take = min(quota, len(order[k]))
            out.extend(self.cells[k][i] for i in order[k][:take])
            taken[k] = take

        # 2) 아직 안 쓴 것만 모아 남는 자리를 메운다 (중복 없음)
        if len(out) < total:
            rest = [self.cells[k][i] for k in keys for i in order[k][taken[k]:]]
            self.rng.shuffle(rest)
            out.extend(rest[:total - len(out)])

        self.rng.shuffle(out)
        return np.array(out, dtype=np.float64), dict(self.seen)


def collect(conn, db_name, n_cells, target, mask=None,
            min_score=NORMAL_MIN_SCORE, seed=None, verbose=True):
    """
    히스토리 DB 전체를 한 번 훑어 학습용 표본을 만든다.

    반환: (X, info)
      X    : (target, n_cells) 배열
      info : 수집 통계 (표본 수, 칸 수, 기간 등)
    """
    cur = conn.cursor()
    tables = list_history_tables(cur, db_name)

    if not tables:
        cur.close()
        return np.empty((0, n_cells)), {"tables": 0, "rows": 0, "kept": 0}

    n_keys_est = 24 * 2
    per_cell = int(OVERSAMPLE * target / n_keys_est) + 1
    res = StratifiedReservoir(per_cell, seed=seed)

    # 가동/정지를 가르는 기준. 마스크 셀 최고 온도의 중앙값을 쓰는데,
    # 한 번 훑는 동안은 알 수 없으므로 앞쪽 표본으로 잡고 간다.
    warmup_peaks = []
    split = None

    rows_seen = 0
    kept = 0

    for t in tables:
        cur.execute(
            f"SELECT time, mscore, hot_list FROM `{db_name}`.`{t}` "
            f"WHERE mscore >= %s",
            (min_score,),
        )
        for when, score, raw in cur:
            rows_seen += 1
            try:
                v = np.asarray(json.loads(raw), dtype=np.float64)
            except (TypeError, ValueError):
                continue
            if v.size != n_cells or not np.all(np.isfinite(v)):
                continue

            peak = float(v[mask == 1].max()) if mask is not None else float(v.max())

            if split is None:
                warmup_peaks.append(peak)
                if len(warmup_peaks) >= 2000:
                    split = float(np.median(warmup_peaks))
                running = 0
            else:
                running = 1 if peak >= split else 0

            res.offer((when.hour, running), v)
            kept += 1

    cur.close()

    X, seen = res.balanced_draw(target)

    info = {
        "tables": len(tables),
        "period": f"{tables[0][-8:]} ~ {tables[-1][-8:]}" if tables else "",
        "rows": rows_seen,
        "kept": kept,
        "cells": len(seen),
        "drawn": int(X.shape[0]),
        "split": split,
    }

    if verbose:
        print(f"[재생버퍼] 테이블 {info['tables']}개 ({info['period']})")
        print(f"           정상 프레임 {kept:,}건 중 {info['drawn']:,}건 표집, "
              f"{info['cells']}개 칸(시간대x가동상태)")
        if info["drawn"] < target:
            print(f"           (목표 {target:,}건에 못 미칩니다. 중복 복제 대신 "
                  f"있는 만큼만 씁니다)")

    return X, info
