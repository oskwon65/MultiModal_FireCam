# -*- coding: utf-8 -*-
"""
기존 학습 모델을 재학습에 얼마나 물려줄지 정한다.

[왜 이렇게 정하는가]

카메라가 밀렸을 때 이미지·마스크를 되돌리는 방법을 먼저 검토했다. kict1
실측으로 그 길을 접었다.

  - 되돌려도 score 가 0.088 -> 0.365 에서 멈춘다 (정상은 0.952)
  - 되돌리면 가장자리에 공백이 생기고, 그 칸을 무엇으로 채우든 지어낸 값이
    64차원 입력에 들어가 완전연결 신경망 전체를 오염시킨다
  - 애초에 이동만으로는 모델이 잘 망가지지 않는다. 7월 자료를 3칸 밀어도
    score 가 0.890 이었다 (원래 0.957)

즉 "몇 칸 밀렸는가" 는 모델이 쓸 만한지를 예측하지 못한다. kict1 은 1.3칸
밀렸는데 0.088 이고, 모의로 1.0칸 민 자료는 0.916 이다. 열 배 넘게 다르다.

그래서 칸 수가 아니라 **지금 실제로 몇 점을 내고 있는가** 로 정한다.

[순간 점수를 쓰면 안 되는 이유]

서서히 뜨거워지는 설비가 score 를 끌어내리면, 시스템이 "모델이 낡았다" 고
보고 그 과열 데이터로 재학습한다. 경보가 스스로 사라진다. 가장 나쁜 결말이다.

그래서 판단에 쓰는 점수는 긴 창의 중앙값이고, 아래 프레임은 빼고 센다.

  1) 절대 임계값이 걸린 프레임      - 이상일 수 있는 구간은 판단 근거가 못 된다
  2) 열화상이 멈춘 프레임           - 같은 값이 반복되면 점수도 가짜다
                                    (kict1 은 09-19~21 이틀을 이렇게 보냈다)
"""

import json

import numpy as np

# 기여 가중치를 가르는 점수 문턱. env.ini 로 덮어쓸 수 있다.
#
# 근거가 확실한 것은 양 끝뿐이다 - 정상 0.95, 망가진 kict1 0.09. 가운데 두
# 문턱은 추정이므로 운영하며 조정한다.
DEFAULT_BANDS = (
    (0.85, 1.0),   # 이 위면 평소대로 - 옛 자료도 쓰고 가중치도 물려받는다
    (0.50, 0.5),
    (0.20, 0.2),
)
FLOOR_WEIGHT = 0.0     # 어느 문턱에도 못 미치면

# 판단에 쓸 기간(일)과 최소 표본 수.
WINDOW_DAYS = 1
MIN_FRAMES = 500


def weight_for(score, bands=None):
    """
    점수 -> 기여 가중치.

    score 가 None(잴 수 없음)이면 1.0 을 돌려준다. 모르는 것을 이유로 모델을
    버리지 않는다. 버리는 쪽이 되돌리기 어렵다.
    """
    if score is None:
        return 1.0
    for thr, w in (bands or DEFAULT_BANDS):
        if score >= thr:
            return w
    return FLOOR_WEIGHT


def describe(score, w):
    if score is None:
        return "판단 점수 없음 - 기존 모델을 그대로 물려받습니다 (w=1.0)"
    if w >= 1.0:
        return f"판단 점수 {score:.3f} - 평소 연속 학습 (w={w:.1f})"
    if w <= 0.0:
        return (f"판단 점수 {score:.3f} - 기존 가중치를 물려받지 않고 새로 "
                f"시작합니다 (w={w:.1f}). 감도 비교 대상으로는 계속 씁니다.")
    return f"판단 점수 {score:.3f} - 기존 모델 기여를 줄입니다 (w={w:.1f})"


def _abs_fires(v, mask, temp_warn):
    """절대 온도 임계값이 걸리는 프레임인가. 상승률은 프레임 단위로 알 수 없다."""
    if temp_warn is None:
        return False
    sel = v[mask == 1] if mask is not None else v
    return bool(sel.size and float(sel.max()) >= float(temp_warn))


def decision_score(conn, db_name, n_cells, mask=None, temp_warn=None,
                   days=WINDOW_DAYS, min_frames=MIN_FRAMES, verbose=True):
    """
    최근 `days` 일의 판단 점수(중앙값). 근거가 모자라면 None.

    히스토리 DB 만 읽는다. 따로 상태 파일을 두지 않는 편이 낫다 - 점수와
    프레임이 같은 곳에 있어야 걸러낸 이유를 나중에 확인할 수 있다.
    """
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT table_name FROM information_schema.tables
            WHERE table_schema = %s AND table_name LIKE 'results_history_%%'
              AND table_type = 'BASE TABLE'
            ORDER BY table_name DESC LIMIT %s
            """,
            (db_name, days + 1),
        )
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            return None, {"reason": "히스토리 테이블이 없습니다"}

        scores = []
        n_seen = n_frozen = n_abs = n_unscored = 0
        prev_raw = None

        for t in sorted(tables):
            cur.execute(
                f"SELECT time, mscore, hot_list FROM `{db_name}`.`{t}` ORDER BY time"
            )
            for _when, ms, raw in cur.fetchall():
                n_seen += 1

                # 1) 멈춘 프레임 - 직전과 글자까지 같으면 새 관측이 아니다
                if raw is not None and raw == prev_raw:
                    n_frozen += 1
                    continue
                prev_raw = raw

                if ms is None or float(ms) < 0:
                    n_unscored += 1
                    continue

                # 2) 절대 임계값이 걸린 프레임
                try:
                    v = np.asarray(json.loads(raw), dtype=np.float64)
                except (TypeError, ValueError):
                    continue
                if v.size != n_cells:
                    continue
                if _abs_fires(v, mask, temp_warn):
                    n_abs += 1
                    continue

                scores.append(float(ms))

        info = {"seen": n_seen, "used": len(scores), "frozen": n_frozen,
                "abs": n_abs, "unscored": n_unscored,
                "period": f"{sorted(tables)[0][-8:]} ~ {sorted(tables)[-1][-8:]}"}

        if len(scores) < min_frames:
            info["reason"] = (f"쓸 만한 프레임이 {len(scores)}건뿐입니다 "
                              f"(최소 {min_frames})")
            if verbose:
                print(f"[기여도] 판단 보류 - {info['reason']}")
            return None, info

        med = float(np.median(scores))
        if verbose:
            print(f"[기여도] {info['period']} · {n_seen:,}건 중 {len(scores):,}건 사용 "
                  f"(정지 {n_frozen:,} · 절대임계 {n_abs:,} · 미산출 {n_unscored:,})")
            print(f"[기여도] 판단 점수(중앙값) {med:.4f}")
        return med, info
    finally:
        cur.close()
