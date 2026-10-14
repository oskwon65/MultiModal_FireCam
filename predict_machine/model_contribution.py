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

[DB 에 적힌 점수를 그대로 쓰면 안 되는 이유]

results_history 의 mscore 는 '그 프레임이 지나갈 때 돌던 모델' 이 매긴 값이다.
세대를 갈아 끼우거나 되돌린 날이면 한 창 안에 여러 모델의 점수가 섞인다.
그것을 중앙값 하나로 묶어 "지금 모델이 얼마나 맞는가" 라고 부를 수는 없다.

2026-09-26 cj_busan_1 실측. 09-25~26 창에서 운용 모델이 아홉 번 바뀌었고, 그
중 상당 구간을 짝이 어긋난 산출물로 돌았다.

    저장된 값으로   판단 점수 0.0467  ->  기여 0.00  (모델을 통째로 버림)
    지금 모델로     판단 점수 0.9219  ->  기여 1.00  (멀쩡하다)

같은 프레임 2,016 건인데 결론이 반대다. 그래서 프레임을 다시 매긴다.

구간의 모든 프레임을 다시 매기면 하루 2만 건을 넘겨 시간이 아깝다. 고르게
뽑은 표본 MAX_SAMPLES 건으로 중앙값을 구한다 - 저수지 표집이라 뽑힐 확률이
모두 같고, 중앙값은 전체를 다 매긴 값으로 모인다.
"""

import datetime as dt
import json
import random

import numpy as np

# 기여 가중치를 정하는 두 끝점. env.ini 로 덮어쓸 수 있다.
#
# 처음에는 네 단계(1.0 / 0.5 / 0.2 / 0.0)로 끊었는데, 문턱 하나를 사이에 두고
# 기여가 0.5 씩 튀었다. 0.849 와 0.851 이 전혀 다른 학습이 되는데 그 차이를
# 정당화할 근거가 없다. 두 끝점 사이를 직선으로 잇는다.
#
#     점수 >= HIGH        기여 1.0   (모델이 멀쩡하다)
#     LOW < 점수 < HIGH   그 사이 비율
#     점수 <= LOW         기여 0.0   (새로 시작)
#
# 근거가 확실한 것은 양 끝뿐이다 - 정상 0.95, 망가진 kict1 0.09. 현장마다
# 점수 수준 자체가 달라(cj_busan_1 은 평소 0.73~0.82) 코드에 박지 않는다.
DEFAULT_HIGH = 0.85
DEFAULT_LOW = 0.20

# 판단에 쓸 날짜 테이블 수.
#
# 날짜 단위가 아니라 '테이블 몇 개' 다. results_history_YYYYMMDD 를 이름
# 내림차순으로 이만큼 자른다. time 에 조건이 없으니, 빈 날이 있으면 두 테이블이
# 붙어 있지 않다 - cj_busan_1 은 07-15 와 09-18 사이가 64일 비어 있다.
#
# 2 개였는데 7 개로 늘렸다. 짧은 창은 설비 상태를 골고루 담지 못한다.
# 2026-09-26 cj_busan_1 실측 (거르고 남은 프레임, 지금 모델로 다시 매긴 값):
#
#     테이블 2개    2,021건    가동  0.3%    중앙 0.922   가동일 때 0.704
#     테이블 7개    8,065건    가동 74.7%    중앙 0.961   가동일 때 0.965
#     테이블 23개  32,191건    가동 42.2%    중앙 0.977   가동일 때 0.972
#
# 2개짜리 창의 0.922 는 '멈춘 설비를 잘 맞힌다' 는 뜻이고, 가동 상태는 6건으로
# 판단한 것이다. 그 창으로는 설비가 다시 돌 때 몇 점이 나올지 알 수 없다.
#
# 더 늘리지 않는 이유는 기여도가 묻는 것이 '그동안 평균' 이 아니라 '지금도
# 맞는가' 이기 때문이다. 창이 길면 멀쩡했던 지난 두 달이 최근의 고장을 덮는다.
WINDOW_TABLES = 7

# 이 밑이면 판단을 포기한다(None -> 기여 1.00). 4건의 중앙값으로 모델을
# 버릴지 정할 수는 없다. kict1 은 열화상이 멈춘 탓에 실제로 이 상태다 -
# 17,714건을 봤지만 17,710건이 정지 프레임이라 4건만 남았다.
MIN_FRAMES = 500

# 다시 매길 프레임 수의 상한.
#
# 근거는 정확도다. 속도가 아니다 - 32,191건을 한 번에 매기는 데 0.04초였다.
# 실제 시간은 DB 에서 읽어 JSON 을 푸는 데 드는데, 그건 표본을 뽑든 말든
# 전부 다 한다. 표집으로 아끼는 시간은 없다.
#
# 32,191건을 모두 매긴 중앙값(0.9770)을 기준으로, n건씩 400번 뽑아 본 오차:
#
#     n=  200   최악 0.0044      n=2,000   최악 0.0014
#     n=  500   최악 0.0026      n=4,000   최악 0.0011
#     n=1,000   최악 0.0016      n=8,000   최악 0.0006
#
# 어느 n 에서도 기여 w 는 1.00 으로 같았다. 기여는 0.01 단위라 점수가 0.003
# 흔들려도 움직이지 않는다. 그래서 2,000 이면 넉넉하다.
#
# 상한이 실제로 하는 일은 메모리 제한이다. 2,000x64 는 1 MB, 창을 잘못
# 늘렸을 때의 수십만 건은 수백 MB 가 된다.
MAX_SAMPLES = 2000

# 표본을 고르는 난수의 씨앗을 고정한다.
#
# 기여 가중치는 학습 조건을 바꾼다. 같은 자료에 같은 모델로 두 번 물었을 때
# 답이 다르면 예행연습과 본 실행을 견줄 수 없다.
SAMPLE_SEED = 20260926


def limits(config):
    """
    판단 기준 셋을 config 에서 꺼낸다. 없거나 터무니없으면 기본값.

        CONTRIB_WINDOW_TABLES = 7      판단에 쓸 날짜 테이블 수
        CONTRIB_MIN_FRAMES    = 500    이 밑이면 판단 보류
        CONTRIB_MAX_SAMPLES   = 2000   다시 매길 프레임 수의 상한

    [설정] 창에서 바꾼다. 창에서 막는 범위와 같은 범위로 여기서도 한 번 더
    거른다 - 파일을 손으로 고칠 수도 있고, 그때 0 이나 음수가 들어오면
    기여도가 통째로 멈춘다.
    """
    def _i(key, default, lo, hi):
        v = config.get(key)
        if v in (None, ""):
            return default
        try:
            n = int(v)
        except (TypeError, ValueError):
            return default
        return n if lo <= n <= hi else default

    return (_i("CONTRIB_WINDOW_TABLES", WINDOW_TABLES, 1, 60),
            _i("CONTRIB_MIN_FRAMES", MIN_FRAMES, 10, 1000000),
            _i("CONTRIB_MAX_SAMPLES", MAX_SAMPLES, 100, 1000000))


def weight_for(score, bounds=None):
    """
    점수 -> 기여 가중치. 두 끝점 사이를 직선으로 잇는다.

        w = (점수 - LOW) / (HIGH - LOW)        LOW <= 점수 <= HIGH
        w = 1.0                                점수 >= HIGH
        w = 0.0                                점수 <= LOW

    소수 둘째 자리에서 끊는다. 점수가 0.0001 흔들릴 때마다 학습 조건이
    달라지면 세대끼리 견주기 어렵다.

    score 가 None(잴 수 없음)이면 1.0 을 돌려준다. 모르는 것을 이유로 모델을
    버리지 않는다. 버리는 쪽이 되돌리기 어렵다.
    """
    if score is None:
        return 1.0

    hi, lo = bounds or (DEFAULT_HIGH, DEFAULT_LOW)
    if hi <= lo:                      # 설정이 뒤집혔으면 기본값으로
        hi, lo = DEFAULT_HIGH, DEFAULT_LOW

    if score >= hi:
        return 1.0
    if score <= lo:
        return 0.0
    return round((float(score) - lo) / (hi - lo), 2)


def describe(score, w):
    if score is None:
        return "SCORE 없음 - (기여: 1.00)"
    if w >= 1.0:
        return f"SCORE (중앙값) {score:.3f} - (기여: 1.00)"
    if w <= 0.0:
        # 여기만 꼬리를 붙인다. 기여 0.00 은 기존 가중치를 통째로 버린다는
        # 뜻인데, 숫자만 보고 그것을 읽어 내기는 어렵다.
        return f"SCORE (중앙값) {score:.3f} - (기여: 0.00, 새로 시작)"
    return f"SCORE (중앙값) {score:.3f} - (기여: {w:.2f})"


def batch_scorer(model, scaler, mask, device):
    """
    프레임 묶음을 지금 모델로 매기는 함수를 만든다.

    predict_machine.normality_score 와 같은 계산이다 - 마스크 칸의 재구성
    오차 평균에 exp(-mse*10). 한 건씩 부르면 2,000 건에 수십 초가 걸리므로
    한 번에 넘긴다.

    짝이 어긋난 산출물이면 여기서 낮은 점수가 나오고 기여가 0 이 된다. 그것이
    맞는 결론이다 - 지금 운용 중인 그 모델이 실제로 못 맞히고 있다.
    """
    import torch

    sel = None
    if mask is not None:
        sel = torch.tensor(np.asarray(mask, dtype=np.int32).reshape(-1) == 1,
                           device=device)

    def _score(X):
        model.eval()
        with torch.no_grad():
            xt = torch.tensor(scaler.transform(X), dtype=torch.float32,
                              device=device)
            d = (xt - model(xt)) ** 2
            mse = d[:, sel].mean(dim=1) if sel is not None else d.mean(dim=1)
            return torch.exp(-mse * 10).cpu().numpy()

    return _score


def _abs_fires(v, mask, temp_warn):
    """절대 온도 임계값이 걸리는 프레임인가. 상승률은 프레임 단위로 알 수 없다."""
    if temp_warn is None:
        return False
    sel = v[mask == 1] if mask is not None else v
    return bool(sel.size and float(sel.max()) >= float(temp_warn))


def decision_score(conn, db_name, n_cells, mask=None, temp_warn=None,
                   n_tables=WINDOW_TABLES, min_frames=MIN_FRAMES, verbose=True,
                   score_fn=None, max_samples=MAX_SAMPLES, since=None):
    """
    최근 날짜 테이블 `n_tables` 개의 판단 점수(중앙값). 근거가 모자라면 None.

    히스토리 DB 만 읽는다. 따로 상태 파일을 두지 않는 편이 낫다 - 점수와
    프레임이 같은 곳에 있어야 걸러낸 이유를 나중에 확인할 수 있다.

    score_fn 을 주면 뽑은 표본을 그 함수로 다시 매긴다(batch_scorer 로 만든다).
    주지 않으면 DB 에 적힌 점수를 그대로 쓴다 - 기간 중에 모델이 바뀌었으면
    그 값은 지금 모델의 것이 아니다. 맨 위 [DB 에 적힌 점수를...] 를 보라.

    거르는 규칙은 어느 쪽이나 똑같다. 달라지는 것은 '어느 프레임을 세는가' 가
    아니라 '그 프레임에 몇 점을 주는가' 뿐이다.
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
            (db_name, n_tables),
        )
        tables = [r[0] for r in cur.fetchall()]
        if not tables:
            return None, {"reason": "히스토리 테이블이 없음"}

        # 빈 날을 건너뛰어 옛 테이블을 끌어오지 않는다.
        #
        # 이름으로만 잘라서는 창 길이를 정할 수 없다. kict1 은 07-14 와 09-21
        # 사이가 68일 비어 있어서, 7개를 자르면 7번째가 07-14 가 된다. 창이
        # 이레가 아니라 두 달이 되고, 7월의 망가진 모델 점수가 섞여 들어온다.
        #
        # 가장 새 테이블의 날짜에서 n_tables-1 일보다 옛것은 버린다. 시계를
        # 보지 않고 테이블 이름끼리만 견주므로, 며칠 뒤에 돌려도 같은 값이 나온다.
        newest = tables[0][-8:]
        try:
            edge = (dt.datetime.strptime(newest, "%Y%m%d")
                    - dt.timedelta(days=n_tables - 1)).strftime("%Y%m%d")
            kept = [t for t in tables if t[-8:] >= edge]
            if len(kept) < len(tables) and verbose:
                print(f"[기여도] 빈 날이 있어 테이블 "
                      f"{len(tables) - len(kept)}개를 뺐음 "
                      f"({edge} 보다 옛것)")
            tables = kept
        except ValueError:
            pass                      # 이름이 날짜가 아니면 그대로 쓴다

        scores = []
        n_seen = n_frozen = n_abs = n_unscored = 0
        prev_raw = None

        # 다시 매길 표본. 저수지 표집 - 전체 건수를 모른 채 한 번만 훑어서
        # 고르게 뽑는다. 상한을 넘으면 j 번째를 새 프레임으로 갈아 낀다.
        pool = []
        rng = random.Random(SAMPLE_SEED)

        for t in sorted(tables):
            cur.execute(
                f"SELECT time, mscore, hot_list FROM `{db_name}`.`{t}` ORDER BY time"
            )
            for _when, ms, raw in cur.fetchall():
                # 카메라 자리가 바뀌기 전 프레임은 칸마다 다른 곳을 보고 있었다.
                if since is not None and _when < since:
                    continue
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

                if score_fn is not None:
                    if len(pool) < max_samples:
                        pool.append(v)
                    else:
                        # len(scores) 가 지금까지 쓸 만했던 프레임 수다.
                        j = rng.randrange(len(scores))
                        if j < max_samples:
                            pool[j] = v

        info = {"seen": n_seen, "used": len(scores), "frozen": n_frozen,
                "abs": n_abs, "unscored": n_unscored,
                "period": f"{sorted(tables)[0][-8:]} ~ {sorted(tables)[-1][-8:]}"}

        if len(scores) < min_frames:
            info["reason"] = (f"쓸 만한 표본이 {len(scores)}건뿐임 "
                              f"(최소 {min_frames})")
            if verbose:
                print(f"[기여도] 판단 보류 - {info['reason']}")
            return None, info

        med = float(np.median(scores))
        info["stored"] = med

        if verbose:
            print(f"[기여도] {info['period']} · {n_seen:,}건 중 {len(scores):,}건 사용 "
                  f"(정지 {n_frozen:,} · 절대임계 {n_abs:,} · 미산출 {n_unscored:,})")

        if score_fn is not None and pool:
            try:
                sn = np.asarray(score_fn(np.asarray(pool, dtype=np.float64)),
                                dtype=np.float64)
                med = float(np.median(sn))
                info["rescored"] = len(pool)
                if verbose:
                    print(f"[기여도] 표본 {len(pool):,}건을 지금 모델로 다시 "
                          f"SCORE 계산함")
            except Exception as e:
                # 다시 매기지 못했으면 적힌 값으로 간다. 값이 없다는 이유로
                # 모델을 버리는 쪽이 더 위험하다.
                info["rescore_error"] = f"{type(e).__name__} {e}"
                if verbose:
                    print(f"[경고] 다시 매기지 못해 DB 에 적힌 점수를 씀: "
                          f"{info['rescore_error']}")
        elif score_fn is None and verbose:
            print("[기여도] DB 에 적힌 점수를 그대로 씀 - 기간 중에 모델이 "
                  "바뀌었으면 지금 모델의 점수가 아님")

        return med, info
    finally:
        cur.close()
