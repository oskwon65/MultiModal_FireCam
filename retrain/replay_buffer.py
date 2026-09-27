# -*- coding: utf-8 -*-
"""
경험 재생 버퍼 (연속 학습)

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

import datetime as dt
import json
import random
from collections import defaultdict

import numpy as np

# 이 점수 이상이어야 "정상으로 판정된 프레임" 으로 본다.
NORMAL_MIN_SCORE = 0.5

# 시간대(24) × 가동상태(2) = 48칸. 칸마다 이만큼씩 모아 둔 뒤 최종 표집한다.
# 목표 개수보다 넉넉히 잡아야 칸별 균형을 맞출 여지가 생긴다.
OVERSAMPLE = 2.0

# 시기를 가르는 공백. 자료가 이만큼 끊기면 다른 시기로 본다.
#
# 날짜를 코드나 설정에 적지 않으려고 이렇게 잡았다. 현장마다 언제 멈췄는지
# 다르고, 그 날짜를 사람이 적어 넣게 하면 반드시 낡는다. 끊긴 자리는 자료가
# 스스로 알려 준다.
#
# 7일로 둔 이유는 하루 이틀 빠진 것까지 다른 시기로 보면 시기가 잘게 쪼개져
# 칸마다 자료가 바닥나기 때문이다. 설비를 고치거나 카메라를 옮겨 한동안 멈춘
# 경우만 갈라진다.
ERA_GAP_DAYS = 7

# 시기 수의 상한. 넘으면 오래된 것끼리 하나로 묶는다.
#
# 칸 수가 24 x 2 x 시기 라, 시기가 늘수록 칸마다 자료가 얇아진다. 여섯을
# 넘기면 나누는 이득보다 얇아지는 손해가 크다.
ERA_MAX = 6

# 다시 매길 때 한 번에 넘기는 프레임 수.
#
# 한 건씩 부르면 4만 건에 몇 분이 걸린다. 묶어 넘기면 0.05초다. 4,096 x 64 는
# 2 MB 라 메모리도 부담이 없다.
RESCORE_BATCH = 4096


def split_eras(tables, gap_days=ERA_GAP_DAYS, era_max=ERA_MAX):
    """
    테이블 이름을 보고 시기를 나눈다. {테이블: 시기번호}, 시기 수를 돌려준다.

    끊긴 적이 없으면 시기가 하나다. 그때는 시기 축을 넣어도 칸이 그대로라
    아무 일도 일어나지 않는다 - 그것이 이 방식의 이점이다. 현장을 가리지
    않고 같은 규칙을 쓸 수 있다.
    """
    if not tables:
        return {}, 0

    era = {}
    k = 0
    prev = None
    for t in tables:
        d = t[-8:]
        try:
            cur_d = dt.date(int(d[:4]), int(d[4:6]), int(d[6:]))
        except ValueError:
            era[t] = k                # 이름이 날짜가 아니면 앞 시기에 붙인다
            continue
        if prev is not None and (cur_d - prev).days >= gap_days:
            k += 1
        era[t] = k
        prev = cur_d

    n = k + 1
    if n > era_max:
        # 오래된 쪽을 하나로 묶는다. 최근 시기를 쪼개 두는 편이 쓸모 있다.
        merge = n - era_max
        era = {t: max(0, v - merge) for t, v in era.items()}
        n = era_max
    return era, n


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
            min_score=NORMAL_MIN_SCORE, seed=None, verbose=True,
            base_date=None, old_weight=None, temp_warn=None,
            score_fn=None, run_temp=None, era_balance=False):
    """
    히스토리 DB 를 훑어 학습용 표본을 만든다.

    old_weight (0.0 ~ 1.0)
        기준일 이전(옛 시기) 자료를 얼마나 섞을지. None 이면 예전처럼 기준일
        이전을 통째로 버린다.

        카메라가 밀리거나 설비가 바뀌어도 옛 자료가 전부 쓸모없어지는 것은
        아니다. 지금 모델이 몇 점을 내고 있느냐에 따라 옛 시기를 조금 남길지
        다 버릴지가 달라진다. 그 비율을 model_contribution 이 정하고 여기로
        넘어온다.

        old_weight = 0.0  -> 새 시기만
        old_weight = 0.5  -> 절반씩
        old_weight = 1.0  -> 시기를 가르지 않고 전체에서 뽑는다

    반환: (X, info)
      X    : (target, n_cells) 배열
      info : 수집 통계 (표본 수, 칸 수, 기간 등)
    """
    cur = conn.cursor()
    tables = list_history_tables(cur, db_name)

    # 계산 기준일로 옛 시기와 새 시기를 가른다. 기준선과 달리 히스토리 DB 는
    # 날짜별 테이블이라 과거 구간을 정확히 잘라낼 수 있다.
    old_tables = []

    # 기여 가중치를 낮추기로 해 놓고 기준일이 없으면, 옛 시기와 새 시기를
    # 가를 방법이 없어 그냥 전체에서 뽑게 된다. 가중치가 조용히 무시되는
    # 것이라 반드시 알려야 한다.
    if old_weight is not None and old_weight < 1.0 and not base_date:
        print("[경고] 기여 가중치가 "
              f"{float(old_weight):.2f} 인데 계산 기준일(CALC_BASE_DATE)이 "
              "비어 있습니다.")
        print("       옛 시기와 새 시기를 가를 수 없어 전체 기간에서 뽑습니다.")
        print("       [설정] 창에서 계산 기준일을 지정해야 가중치가 적용됩니다.")

    if base_date:
        cutoff = "results_history_" + str(base_date).replace("-", "")
        old_tables = [t for t in tables if t < cutoff]
        new_tables = [t for t in tables if t >= cutoff]

        if old_weight is None:
            # 예전 방식: 기준일 이전은 아예 읽지 않는다.
            if old_tables and verbose:
                print(f"[재생버퍼] 기준일({base_date}) 이전 테이블 "
                      f"{len(old_tables)}개 제외")
            tables, old_tables = new_tables, []
        elif old_weight >= 1.0:
            old_tables = []          # 가르지 않고 전체에서 뽑는다
        elif not new_tables:
            # 새 시기에 자료가 없으면 비율을 논할 수 없다. 있는 것으로 뽑는다.
            if verbose:
                print(f"[재생버퍼] 기준일({base_date}) 이후 자료가 없어 "
                      f"전체에서 뽑습니다")
            old_tables = []
        else:
            tables = new_tables

    if not tables and not old_tables:
        cur.close()
        return np.empty((0, n_cells)), {"tables": 0, "rows": 0, "kept": 0}

    # 옛 시기를 섞는 경우, 목표 수를 비율로 나눠 두 번 뽑고 합친다.
    if old_tables:
        n_old = int(round(target * float(old_weight)))
        n_new = target - n_old
        if verbose:
            print(f"[재생버퍼] 옛 시기 {len(old_tables)}개 테이블에서 {n_old:,}건, "
                  f"새 시기 {len(tables)}개에서 {n_new:,}건 "
                  f"(기여 가중치 {float(old_weight):.2f})")
        X_old, info_old = _collect_from(cur, db_name, old_tables, n_cells, n_old,
                                        mask, min_score, seed, verbose, temp_warn,
                                        score_fn, run_temp, era_balance)
        X_new, info_new = _collect_from(cur, db_name, tables, n_cells, n_new,
                                        mask, min_score, seed, verbose, temp_warn,
                                        score_fn, run_temp, era_balance)
        cur.close()
        X = np.concatenate([a for a in (X_old, X_new) if len(a)]) \
            if (len(X_old) or len(X_new)) else np.empty((0, n_cells))
        info = {
            "tables": info_old["tables"] + info_new["tables"],
            "period": f"{info_old.get('period','')} + {info_new.get('period','')}",
            "rows": info_old["rows"] + info_new["rows"],
            "kept": info_old["kept"] + info_new["kept"],
            "cells": max(info_old.get("cells", 0), info_new.get("cells", 0)),
            # drawn 은 보고서가 쓰는 키다. 두 시기를 합칠 때 빠뜨리면
            # 학습이 다 끝난 뒤 보고서에서 KeyError 로 죽는다.
            "drawn": int(len(X)),
            # 두 시기를 합치면 시간대도 합집합이어야 하나, 여기서는 개수만
            # 들고 있어 정확히 합칠 수 없다. 많은 쪽을 쓴다 — 적게 잡는 것이
            # 관문을 느슨하게 만들지는 않는다.
            "hours": max(info_old.get("hours", 0), info_new.get("hours", 0)),
            "split": info_new.get("split", info_old.get("split")),
            "old_rows": int(len(X_old)), "new_rows": int(len(X_new)),
            "old_weight": float(old_weight),
        }
        return X, info

    X, info = _collect_from(cur, db_name, tables, n_cells, target,
                            mask, min_score, seed, verbose, temp_warn, score_fn,
                            run_temp, era_balance)
    cur.close()
    info["old_weight"] = 1.0 if old_weight is None else float(old_weight)
    return X, info


def _collect_from(cur, db_name, tables, n_cells, target, mask,
                  min_score, seed, verbose, temp_warn=None, score_fn=None,
                  run_temp=None, era_balance=False):
    """
    테이블 묶음 하나에서 target 건을 고르게 뽑는다.

    temp_warn 이 주어지면 마스크 칸 최고 온도가 그 값 이상인 프레임을 뺀다.
    모델 점수를 믿을 수 없을 때(min_score 를 낮췄을 때) 정상 여부를 가리는
    유일한 근거다.

    [score_fn - 지금 모델로 다시 매긴다]

    DB 의 mscore 는 그 프레임이 지나갈 때 돌던 모델이 매긴 값이다. 세대를
    갈아 끼운 날이면 한 구간 안에 여러 모델의 판단이 섞이고, 그 중에 망가진
    모델이 있으면 멀쩡한 프레임이 통째로 빠진다.

    2026-09-26 cj_busan_1 실측. 짝이 어긋난 산출물로 이틀을 돈 구간이다.

        09-25   1,713건 중 정상 49건 (2.9%)
        09-26   1,287건 중 정상 53건 (4.1%)

    그 바람에 학습 표본의 79%가 두 달 전 7월 것이 됐다.

    [지금 모델 하나로 가른다]

    한동안 '적힌 점수와 다시 매긴 점수 중 하나만 넘으면 받는' 식으로 두었다.
    지금 모델이 못 보던 상태를 스스로 빼 버리는 것을 막으려 했는데, 그 경우
    적힌 점수도 같은 망가진 모델이 매긴 것이라 함께 버려진다. 실제로 적힌
    점수로만 들어온 것은 43,687건 중 19건뿐이었다.

    손해는 분명하다. 지나치게 너그러웠던 옛 모델이 통과시킨 프레임이 그 길로
    들어온다 - 감도 회귀 시험이 막으려는 바로 그것이다.

    모델을 못 믿을 때의 답은 이미 따로 있다. 기여가 1.00 미만이면 부르는 쪽이
    min_score 를 0 으로 내려 모델 판단을 아예 쓰지 않고 절대 임계값으로만
    거른다. 믿기로 한 모델이면 그 모델 하나로 가르는 것이 앞뒤가 맞는다.

    [run_temp - 가동 판정 온도]

    주지 않으면 앞쪽 2,000건 최고 온도의 중앙값으로 잡는다. 그 방식은 앞쪽
    2,000건이 어느 시간대인지에 끌려가고, 그 2,000건 자체는 판정선이 아직
    없어 전부 정지로 들어간다. 값을 주면 처음부터 같은 선으로 가른다.

    [era_balance - 시기를 나누어 담기]

    켜면 칸이 (시각 x 가동상태) 에서 (시각 x 가동상태 x 시기) 로 늘어난다.
    끄면 자료가 많은 시기가 그만큼 많이 뽑힌다 - 칸 안에서는 모두 같은
    확률이라 비율이 그대로 보존되기 때문이다.

    시기는 날짜가 아니라 자료가 끊긴 자리로 나눈다(split_eras 참고).
    """
    if not tables or target <= 0:
        return np.empty((0, n_cells)), {"tables": 0, "rows": 0, "kept": 0}

    era_of, n_eras = split_eras(tables)
    if not era_balance:
        n_eras = 1

    n_keys_est = 24 * 2 * n_eras
    per_cell = int(OVERSAMPLE * target / n_keys_est) + 1
    res = StratifiedReservoir(per_cell, seed=seed)

    if era_balance and verbose:
        if n_eras > 1:
            print(f"[재생버퍼] 시기 {n_eras}개로 나누어 담습니다 "
                  f"(자료가 {ERA_GAP_DAYS}일 이상 끊긴 자리가 경계)")
        else:
            print(f"[재생버퍼] 자료가 끊긴 자리가 없어 시기가 하나입니다")

    # 가동/정지를 가르는 기준. 값을 주면 그대로 쓰고, 없으면 마스크 셀 최고
    # 온도의 중앙값으로 잡는다 - 한 번 훑는 동안은 알 수 없으므로 앞쪽
    # 표본으로 잡고 간다.
    warmup_peaks = []
    split = None if run_temp is None else float(run_temp)
    if split is not None and verbose:
        print(f"[재생버퍼] 가동 판정 온도 {split:.0f}도 (지정값)")

    rows_seen = 0
    kept = 0
    # 덮은 시각(0~23) 비트마스크.
    #
    # 개수만으로는 "낮에만 아는 모델" 을 막지 못한다. kict1 은 표본
    # 15,352건으로 최소 기준(5,000)을 세 배 넘겼지만 새벽 02~07시가 통째로
    # 비어 있었다. 1단계 기준선에는 같은 뜻의 조건이 이미 있는데 재학습에만
    # 없었다.
    hours_seen = 0

    n_by_now = n_by_old = 0
    # 적힌 점수는 이제 판정에 쓰지 않는다. 자리만 남겨 둔다 - 다시 매기지
    # 못한 경우를 로그로 남길 때 쓸 수 있고, 튜플 모양을 바꾸면 위아래가
    # 함께 흔들린다.
    pending = []            # (시각, 적힌 점수, 값, 가동여부, 시기)

    def cell_key(hour, running, era):
        return (hour, running, era) if era_balance else (hour, running)

    def flush():
        """모아 둔 프레임을 한 번에 매기고 받을 것만 담는다."""
        nonlocal kept, hours_seen, n_by_now, n_by_old
        if not pending:
            return
        try:
            now = np.asarray(
                score_fn(np.asarray([q[2] for q in pending], dtype=np.float64)),
                dtype=np.float64)
        except Exception as e:
            # 못 매기면 이 묶음을 거른다. 적힌 점수로 대신하지 않는다 -
            # 그 값을 믿지 않기로 한 것이 이 함수의 전제다. 표본이 모자라면
            # 최소 표본 관문이 재학습을 멈춘다.
            print(f"[경고] 재생버퍼를 다시 매기지 못해 이 묶음을 거릅니다: "
                  f"{type(e).__name__} {e}")
            pending.clear()
            return

        for (hour, _stored, v, running, era), sc_now in zip(pending, now):
            if sc_now < min_score:
                continue
            n_by_now += 1
            res.offer(cell_key(hour, running, era), v)
            hours_seen |= (1 << int(hour))
            kept += 1
        pending.clear()

    for t in tables:
        era = era_of.get(t, 0)
        if score_fn is None:
            cur.execute(
                f"SELECT time, mscore, hot_list FROM `{db_name}`.`{t}` "
                f"WHERE mscore >= %s",
                (min_score,),
            )
        else:
            # 여기서 걸러 버리면 다시 매길 기회조차 없어진다. 다 가져온다.
            cur.execute(
                f"SELECT time, mscore, hot_list FROM `{db_name}`.`{t}`"
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

            # 0단계 절대 임계값. 모델을 못 믿을 때 남는 유일한 판단이다.
            if temp_warn is not None and peak >= float(temp_warn):
                continue

            if split is None:
                warmup_peaks.append(peak)
                if len(warmup_peaks) >= 2000:
                    split = float(np.median(warmup_peaks))
                running = 0
            else:
                running = 1 if peak >= split else 0

            if score_fn is None:
                res.offer(cell_key(when.hour, running, era), v)
                hours_seen |= (1 << int(when.hour))
                kept += 1
            else:
                pending.append((when.hour, score, v, running, era))
                if len(pending) >= RESCORE_BATCH:
                    flush()

    flush()
    cur.close()

    X, seen = res.balanced_draw(target)

    info = {
        "tables": len(tables),
        "period": f"{tables[0][-8:]} ~ {tables[-1][-8:]}" if tables else "",
        "rows": rows_seen,
        "kept": kept,
        "cells": len(seen),
        "drawn": int(X.shape[0]),
        "hours": bin(hours_seen).count("1"),
        "split": split,
        "by_now": n_by_now,
        "by_old": n_by_old,
        "eras": n_eras,
    }

    if verbose:
        print(f"[재생버퍼] 테이블 {info['tables']}개 ({info['period']})")
        print(f"           정상 프레임 {kept:,}건 중 {info['drawn']:,}건 표집, "
              f"{info['cells']}개 칸(시간대x가동상태) · {info['hours']}개 시간대")
        if info["drawn"] < target:
            print(f"           (목표 {target:,}건에 못 미칩니다. 중복 복제 대신 "
                  f"있는 만큼만 씁니다)")

    return X, info
