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
현장이라면 낮 표본이 모자라고, 모델은 낮을 이상으로 본다. 날짜마다 시간대
(0~23)로 칸을 나눠 각 칸에서 고르게 뽑으면, 어느 시간대도 누락되지 않는다.

예전에는 시간대 안을 다시 가동/정지(마스크 칸 최고 온도가 자동으로 잡은
'가동 판정 온도' 이상인가)로 나눴다. 2026-10-07 에 뺐다. cj_busan_1 에서
그 온도(98도)는 가동과 정지가 아니라 드문 고온 구간과 나머지를 가르고
있었고, 표본 구성도 거의 바꾸지 못했다(고온 6.6% -> 표본 6.0%).


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
# 거르는 것은 절대 임계값 하나다.
#
# 한동안 '칸마다 상위 0.1% 를 자르는' 선을 함께 두었다. 절대 임계값 밑에도
# 이상이 있을 수 있다는 생각이었는데, 이 현장 자료에서 확인되지 않았다.
# 잘린 222건을 들여다보니 전부 가동이 많았던 날의 평소보다 몇 도 뜨거운
# 정상 프레임이었다 - 07-06·07 에 116건, 09-22·23 에 93건, 칸 23 이 선을
# 1도 넘긴 것 같은 것들. 이상을 막는 것이 아니라 모델이 배워야 할 상단부를
# 깎고 있었다.
#
# 모델 점수로 거르던 것도 앞서 뺐다. 그 잣대는 "내가 배운 것과 닮았나" 를
# 물어서, 모델이 못 배운 정상 상태를 스스로 표본에서 빼 버렸다.
#
# 남은 잣대는 사람이 정한 절대 임계값뿐이다. 그것이 실제로 일을 하려면
# 현장 실측에 맞게 잡혀 있어야 한다 - cj_busan_1 은 역대 최고 118도인데
# 임계값이 172도라 지금은 한 건도 걸리지 않는다.

# (날짜, 시간대) 칸마다 모아 둔 뒤 최종 표집한다. 목표 개수보다 넉넉히
# 잡아야 날짜·칸별 균형을 맞출 여지가 생긴다.
#
# 2배로 잡았더니 cj_busan_1 에서 칸당 몫이 모자라 목표 20,000건에 13,689건만
# 뽑혔다. 하루 24칸 기준으로 4배를 잡는다.
OVERSAMPLE = 4.0

# 다시 매길 때 한 번에 넘기는 프레임 수.
#
# 한 건씩 부르면 4만 건에 몇 분이 걸린다. 묶어 넘기면 0.05초다. 4,096 x 64 는
# 2 MB 라 메모리도 부담이 없다.
# (다시 매기기는 model_contribution 으로 옮겼다. 여기서는 모델 점수를
#  쓰지 않는다.)


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


def recent_tables(tables, days):
    """
    가장 새 테이블의 날짜에서 days-1 일보다 옛것을 뺀다. days 가 없거나 0 이면 전부.

    오늘 날짜가 아니라 테이블 이름끼리 견준다. 며칠 뒤에 돌려도 같은 결과가 나오고,
    감시가 한동안 멈춰 있었어도 마지막 자료에서 거슬러 센다. 중간에 빈 날이 있으면
    그만큼 테이블이 적게 남는다(기여도 구간과 같은 규칙).
    """
    if not tables or not days or int(days) <= 0:
        return list(tables)
    try:
        newest = max(t[-8:] for t in tables)
        edge = (dt.datetime.strptime(newest, "%Y%m%d")
                - dt.timedelta(days=int(days) - 1)).strftime("%Y%m%d")
    except ValueError:
        return list(tables)          # 이름이 날짜가 아니면 그대로
    return [t for t in tables if t[-8:] >= edge]


def _water_fill(total, caps):
    """
    total 을 caps 의 키들에 되도록 같게 나눈다. 용량(caps)이 모자란 키는 있는 만큼만
    받고, 남는 몫은 나머지에 다시 나눈다. 용량의 합이 total 보다 작으면 합만큼만.
    돌려주는 값: {키: 배정 수}
    """
    alloc = {}
    remaining = int(total)
    keys = sorted(caps, key=lambda k: caps[k])
    for i, k in enumerate(keys):
        share = remaining // (len(keys) - i)
        take = min(caps[k], share)
        alloc[k] = take
        remaining -= take
    return alloc


class StratifiedReservoir:
    """(날짜, 시간대) 칸마다 따로 저수지 표집을 돌린다."""

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

    def day_balanced_draw(self, total):
        """
        날짜마다 같은 몫으로, 하루 안에서는 시간대 칸마다 같은 몫으로
        최대 total 개를 뽑는다.

        날짜: total / 날짜 수. 프레임이 그보다 적은 날은 있는 만큼만 받고, 남는 몫은
              다른 날에 다시 나눈다. 하루 프레임 수가 몇 건이든 하루의 비중은 같다.
        하루 안: 그날 몫을 비어 있지 않은 칸에 같게 나눈다(역시 모자라면 다른 칸으로).

        [중복 금지] 같은 프레임을 두 번 담으면 안 된다. 학습 표본이
        부풀어 실제보다 많은 것처럼 보이고, 중복된 프레임에 가중치가
        실려 모델이 그쪽으로 기운다. 모아 둔 것보다 많이 요구받으면
        요구량을 줄일지언정 복제하지 않는다.
        """
        by_day = defaultdict(dict)                 # 날짜 -> {칸: 풀}
        for key, pool in self.cells.items():
            if pool:
                by_day[key[0]][key[1:]] = pool
        if not by_day:
            return np.empty((0, 0)), {}

        day_caps = {d: sum(len(p) for p in cells.values())
                    for d, cells in by_day.items()}
        day_alloc = _water_fill(total, day_caps)

        out = []
        for d, n_day in day_alloc.items():
            if n_day <= 0:
                continue
            cells = by_day[d]
            cell_alloc = _water_fill(n_day, {c: len(p) for c, p in cells.items()})
            for c, n_cell in cell_alloc.items():
                if n_cell <= 0:
                    continue
                pool = cells[c]
                for i in self.rng.sample(range(len(pool)), n_cell):
                    out.append(pool[i])

        self.rng.shuffle(out)
        return np.array(out, dtype=np.float64), dict(self.seen)


def collect(conn, db_name, n_cells, target, mask=None,
            seed=None, verbose=True,
            split_days=None, old_weight=None, temp_warn=None,
            dynamic_mix=True, recent_days=None, since=None):
    """
    히스토리 DB 를 훑어 학습용 표본을 만든다.

    recent_days
        가장 새 테이블부터 이 일수 안의 테이블만 훑는다. None 이거나 0 이면 전체.

    since (datetime)
        카메라 자리가 바뀐 시각. 그 앞의 프레임은 칸마다 다른 곳을 보고 있었으므로
        쓰지 않는다. None 이면 거르지 않는다.

    split_days
        옛 시기와 새 시기를 가르는 경계. 가장 새 테이블에서 이 일수 안이 새 시기
        (기여도를 재는 판단 구간과 같다)이고 그 앞이 옛 시기다. None 이면 가르지
        않는다.

    dynamic_mix
        True  옛/새 시기 비율을 old_weight(기여 w) 로 정한다. 아래 설명대로.
        False w 를 보지 않고 옛/새를 가르지 않은 채 전체 테이블에서 뽑는다
              (시기 비율은 자료량에 비례한다).

    old_weight (0.0 ~ 1.0)
        옛 시기 자료를 얼마나 섞을지. None 이면 옛 시기를 통째로 버린다.

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

    # 카메라 자리가 바뀐 뒤의 것만. 그날 테이블 안은 _collect_from 이 시각으로 거른다.
    if since is not None:
        day = since.strftime("%Y%m%d")
        n0 = len(tables)
        tables = [t for t in tables if t[-8:] >= day]
        if verbose:
            print(f"[재생버퍼] 카메라 자리가 바뀐 {since:%Y-%m-%d %H:%M} 이후만 씁니다 "
                  f"(테이블 {n0 - len(tables)}개 제외)")

    # 수집 일수. 옛 시기를 가르기 전에 먼저 자른다.
    if recent_days:
        kept_tables = recent_tables(tables, recent_days)
        if verbose:
            print(f"[재생버퍼] 최근 {int(recent_days)}일 이내 테이블 "
                  f"{len(kept_tables)}개만 사용 "
                  f"({len(tables) - len(kept_tables)}개 제외)")
        tables = kept_tables

    # 동적 구성이 꺼져 있으면 w 를 보지 않고 옛/새를 가르지 않은 채 전체에서 뽑는다.
    if not dynamic_mix:
        split_days = None
    mix_weight = old_weight

    # 판단 구간(가장 새 테이블에서 split_days 일 이내)을 새 시기로, 그 앞을 옛 시기로
    # 가른다. 히스토리 DB 는 날짜별 테이블이라 과거 구간을 정확히 잘라낼 수 있다.
    old_tables = []
    cutoff = None
    if split_days and tables:
        try:
            newest = max(t[-8:] for t in tables)
            edge = (dt.datetime.strptime(newest, "%Y%m%d")
                    - dt.timedelta(days=int(split_days) - 1)).strftime("%Y%m%d")
            cutoff = "results_history_" + edge
        except ValueError:
            cutoff = None

    if cutoff:
        old_tables = [t for t in tables if t < cutoff]
        new_tables = [t for t in tables if t >= cutoff]

        if mix_weight is None:
            # 옛 시기는 아예 읽지 않는다.
            if old_tables and verbose:
                print(f"[재생버퍼] 판단 구간({split_days}일) 이전 테이블 "
                      f"{len(old_tables)}개 제외")
            tables, old_tables = new_tables, []
        elif mix_weight >= 1.0:
            old_tables = []          # 가르지 않고 전체에서 뽑는다
        elif not new_tables:
            # 새 시기에 자료가 없으면 비율을 논할 수 없다. 있는 것으로 뽑는다.
            if verbose:
                print("[재생버퍼] 판단 구간에 자료가 없어 전체에서 뽑습니다")
            old_tables = []
        else:
            tables = new_tables

    if not tables and not old_tables:
        cur.close()
        return np.empty((0, n_cells)), {"tables": 0, "rows": 0, "kept": 0}

    # 옛 시기를 섞는 경우, 목표 수를 비율로 나눠 두 번 뽑고 합친다.
    if old_tables:
        n_old = int(round(target * float(mix_weight)))
        n_new = target - n_old
        if verbose:
            print(f"[재생버퍼] 옛 시기 {len(old_tables)}개 테이블에서 {n_old:,}건, "
                  f"새 시기(최근 {split_days}일) {len(tables)}개에서 {n_new:,}건 "
                  f"(기여 가중치 {float(mix_weight):.2f})")
        X_old, info_old = _collect_from(cur, db_name, old_tables, n_cells, n_old,
                                        mask, seed, verbose, temp_warn, since)
        X_new, info_new = _collect_from(cur, db_name, tables, n_cells, n_new,
                                        mask, seed, verbose, temp_warn, since)
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
            "old_rows": int(len(X_old)), "new_rows": int(len(X_new)),
            "mix_weight": float(mix_weight), "dynamic_mix": bool(dynamic_mix),
        }
        return X, info

    X, info = _collect_from(cur, db_name, tables, n_cells, target,
                            mask, seed, verbose, temp_warn, since)
    cur.close()
    info["mix_weight"] = 1.0 if mix_weight is None else float(mix_weight)
    return X, info


def _collect_from(cur, db_name, tables, n_cells, target, mask,
                  seed, verbose, temp_warn=None, since=None):
    """
    테이블 묶음 하나에서 target 건을 고르게 뽑는다.

    [무엇으로 거르는가]

    절대 임계값(temp_warn) 하나다.

    예전에는 모델 점수(mscore >= 0.5)로 걸렀다. 그 잣대는 "내가 배운 것과
    닮았나" 를 물어서, 모델이 못 배운 정상 상태와 진짜 이상을 구분하지
    못한다. 그래서 모델이 틀린 자리가 표본에서 빠지고, 다음 세대도 같은
    자리에서 틀렸다. 눈먼 자리가 자기를 지켜 냈다.

    2026-09-28 cj_busan_1. 칸 37 이 70도인 상태는 09-20·21 에 1,125번 있던
    정상인데, 운용 모델이 0.06 을 주어 표본에서 빠졌다. 세대가 거듭될수록
    그 상태의 점수가 0.84 -> 0.08 -> 0.06 으로 떨어졌다.
    """
    if not tables or target <= 0:
        return np.empty((0, n_cells)), {"tables": 0, "rows": 0, "kept": 0}

    # 날짜가 칸에 들어가므로 칸 수는 날짜 수 x 24 시간대다(날짜 테이블 하나가 하루).
    # 칸마다 최소 셋은 들고 있어야 한 날의 몫을 채울 여지가 있다.
    n_days = max(1, len(tables))
    n_keys_est = 24 * n_days
    per_cell = max(3, int(OVERSAMPLE * target / n_keys_est) + 1)
    res = StratifiedReservoir(per_cell, seed=seed)

    rows_seen = 0
    kept = 0
    # 덮은 시각(0~23) 비트마스크.
    #
    # 개수만으로는 "낮에만 아는 모델" 을 막지 못한다. kict1 은 표본
    # 15,352건으로 최소 기준(5,000)을 세 배 넘겼지만 새벽 02~07시가 통째로
    # 비어 있었다. 2단계 기준선에는 같은 뜻의 조건이 이미 있는데 재학습에만
    # 없었다.
    hours_seen = 0

    # ---- 훑으면서 (날짜, 시간대) 칸에 담는다 ----
    #
    # 여기서 거는 것은 절대 임계값 하나다.
    n_abs = 0            # 절대 임계값에 걸린 수

    for t in tables:
        cur.execute(f"SELECT time, hot_list FROM `{db_name}`.`{t}`")
        for when, raw in cur:
            if since is not None and when < since:
                continue                 # 카메라 자리가 바뀌기 전
            rows_seen += 1
            try:
                v = np.asarray(json.loads(raw), dtype=np.float64)
            except (TypeError, ValueError):
                continue
            if v.size != n_cells or not np.all(np.isfinite(v)):
                continue

            peak = float(v[mask == 1].max()) if mask is not None else float(v.max())
            if temp_warn is not None and peak >= float(temp_warn):
                n_abs += 1
                continue

            hour = int(when.hour)
            res.offer((t[-8:], hour), v)
            hours_seen |= (1 << hour)
            kept += 1

    cur.close()

    if not kept:
        return (np.empty((0, n_cells)),
                {"tables": len(tables), "rows": rows_seen, "kept": 0,
                 "period": f"{tables[0][-8:]} ~ {tables[-1][-8:]}",
                 "cells": 0, "drawn": 0, "hours": 0, "abs_cut": n_abs})

    X, seen = res.day_balanced_draw(target)

    info = {
        "tables": len(tables),
        "period": f"{tables[0][-8:]} ~ {tables[-1][-8:]}" if tables else "",
        "rows": rows_seen,
        "kept": kept,
        "cells": len({k[1:] for k in seen}),
        "days": len({k[0] for k in seen}),
        "drawn": int(X.shape[0]),
        "hours": bin(hours_seen).count("1"),
        "abs_cut": n_abs,
    }

    if verbose:
        print(f"[재생버퍼] 테이블 {info['tables']}개 ({info['period']})")
        # 0건도 적는다. 0 은 '그 잣대가 아무것도 걸러내지 않고 있다' 는
        # 뜻이고, 그것을 알아야 임계값이 맞게 잡혔는지 의심할 수 있다.
        print(f"           본 {rows_seen:,}건 중 {kept:,}건 사용")
        print(f"           절대 임계값 위반 [ {n_abs:,} ] 건")
        print(f"           {info['drawn']:,}건 표집, 날짜 {info['days']}일 균등 · "
              f"{info['hours']}개 시간대")
        if info["drawn"] < target:
            print(f"           (목표 {target:,}건에 못 미칩니다. 중복 복제 대신 "
                  f"있는 만큼만 씁니다)")

    return X, info
