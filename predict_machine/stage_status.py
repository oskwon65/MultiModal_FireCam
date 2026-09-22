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

# 현황 파일을 다시 쓰는 최소 간격(초).
#
# 기준선 저장(200건마다)에 묶어 두었더니 첫 기록까지 kict1 은 17분,
# cj_busan_1 은 100분이 걸렸다. 그동안 [설정] 창에는 아무 값도 없어,
# 감시가 멀쩡히 돌고 있는데도 안 도는 것처럼 보였다.
#
# 텍스트 20줄을 쓰는 일이라 부담이 없다. 짧게 잡아 시작 직후부터 값이
# 보이게 한다.
STATUS_WRITE_INTERVAL = 30

# 히스토리 DB 건수를 다시 세는 최소 간격(초). 날짜별 테이블마다 COUNT 를
# 돌리므로 현황 기록보다 훨씬 드물게 센다.
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


def model_timestamp(user_path):
    """
    지금 적재되어 있는 오토인코더 파일의 시각.

    모델은 프로그램이 기동할 때 한 번만 읽는다. 새 파일로 바꿔 놓아도
    재시작 전까지는 옛 모델이 계속 도는데, 화면에 "사용 중" 만 떠 있으면
    바뀐 줄 알기 쉽다. 파일 시각을 함께 보여주면 바로 알아챌 수 있다.
    """
    p = os.path.join(user_path, "autoencoder_final.pth")
    if not os.path.exists(p):
        return ""
    try:
        return datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return ""


def _esc(v):
    """ini 값으로 안전하게 쓰기 위해 줄바꿈만 없앤다."""
    return str(v).replace("\r", " ").replace("\n", " ")


def _sf(shift, key, default=""):
    """
    RGB 틀어짐 측정 결과에서 한 항목을 꺼낸다.

    shift 는 (shift_x, shift_y, 잰시각, info) 이고 info 가 dict 다. 아직 재지
    못했으면 빈 칸으로 둔다. 0 으로 채우면 "안 밀렸다" 로 읽힌다.
    """
    if shift is None or len(shift) < 4 or not isinstance(shift[3], dict):
        return default
    v = shift[3].get(key)
    if v is None:
        return default
    if key == "state":
        return int(v)
    if key == "response":
        return f"{float(v):.3f}"
    return f"{float(v):.1f}"


def _tstate(tshift):
    """
    열화상 틀어짐 상태를 한 글자로 줄인다.

      -1  아직 기준 패턴이 없다 (표본을 모으는 중)
       0  잴 수는 있었으나 판정할 수 없었다 (화면이 밋밋함)
       1  틀어지지 않았다
       2  틀어졌다 (몇 칸인지까지 안다)
       3  기준 패턴과 안 맞는다 (방향은 못 밝혔다)
    """
    if tshift is None or not getattr(tshift, "has_ref", False):
        return -1
    res = getattr(tshift, "result", None)
    if res is None:
        return 0
    if res["shifted"]:
        return 2
    if res["mismatch"]:
        return 3
    return 1


def _tv(tshift, key):
    res = getattr(tshift, "result", None) if tshift is not None else None
    return "" if res is None else int(res[key])


def _tcorr(tshift):
    res = getattr(tshift, "result", None) if tshift is not None else None
    if res is None:
        return ""
    # 틀어졌다고 볼 때는 그 자리의 상관, 아니면 제자리의 상관을 적는다.
    return f"{(res['corr'] if res['shifted'] else res['corr0']):.3f}"


def _tcorr0(tshift):
    """제자리 상관. 틀어졌을 때 "원래 자리와는 얼마나 안 맞았나" 가 된다."""
    res = getattr(tshift, "result", None) if tshift is not None else None
    return "" if res is None else f"{res['corr0']:.3f}"


def write(path, baseline, model_ready, user_path,
          db_rows=None, db_tables=None, min_retrain=None, stage_used=None,
          abs_guard=None, shift=None, tshift=None):
    """
    현황을 통째로 덮어쓴다.

    stage_used 는 직전 프레임에서 실제로 채점에 쓰인 단계(0/1/2).
    "쓸 수 있다" 와 "지금 쓰고 있다" 는 다르므로 따로 적는다.
    """
    gen_name, gen_time = find_generation(user_path)

    stage1 = baseline.is_ready()
    stage2 = bool(model_ready)
    stage3 = gen_name is not None

    # 0단계(절대 임계값)는 학습과 무관하게 늘 동작하지만, 임계값이 지정되지
    # 않으면 판정 자체를 끄고 있다. 그 구분을 화면에서도 볼 수 있어야 한다.
    stage0 = bool(abs_guard is not None and abs_guard.enabled)

    def _t(v):
        return "" if v is None else f"{float(v):.0f}"

    lines = [
        "; 이 파일은 predict_machine 이 자동으로 만듭니다. 직접 고치지 마십시오.",
        "[STATUS]",
        f"UPDATED_AT = {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"BASE_DATE = {_esc(baseline.base_date)}",
        "",
        f"STAGE0 = {1 if stage0 else 0}",
        f"ABS_TEMP_WARN = {_t(getattr(abs_guard, 'temp_warn', None))}",
        f"ABS_TEMP_ALARM = {_t(getattr(abs_guard, 'temp_alarm', None))}",
        f"ABS_RISE_WARN = {_t(getattr(abs_guard, 'rise_warn', None))}",
        f"ABS_RISE_ALARM = {_t(getattr(abs_guard, 'rise_alarm', None))}",
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
        f"MODEL_AT = {_esc(model_timestamp(user_path))}",
        "",
        # 카메라 틀어짐은 기동할 때 RGB 이미지를 기준 이미지와 대조해 한 번만
        # 잰다. 루프 안에서는 다시 재지 않으므로 잰 시각을 함께 남긴다.
        f"SHIFT_X = {'' if shift is None else int(shift[0])}",
        f"SHIFT_Y = {'' if shift is None else int(shift[1])}",
        f"SHIFT_AT = {_esc('' if shift is None else shift[2])}",
        # 0칸이라는 값만으로는 "틀어지지 않았다" 와 "잴 수 없었다" 를 가를
        # 수 없다. 상태를 따로 적는다.
        #  -1 예전 방식(밝기별 기준 더미)으로 돌고 있다
        #   0 쟀으나 믿을 수 없다 (기준과 다른 장면)
        #   1 틀어지지 않았다
        #   2 틀어졌다
        f"SHIFT_STATE = {_sf(shift, 'state', -1)}",
        # 잰 픽셀 값. 칸 수만 적으면 한 칸(80px)보다 작은 흔들림이 통째로
        # 0칸으로 묻힌다. 서서히 돌아가는 것은 그 구간에서 먼저 보인다.
        f"SHIFT_DX = {_sf(shift, 'dx')}",
        f"SHIFT_DY = {_sf(shift, 'dy')}",
        f"SHIFT_RESP = {_sf(shift, 'response')}",
        "",
        # 열화상 틀어짐. RGB 와 달리 운전 중에도 주기적으로 다시 잰다.
        # TSHIFT_STATE 로 "기준 없음 / 판정 불가 / 없음 / 밀렸음" 을 가른다.
        f"TSHIFT_STATE = {_tstate(tshift)}",
        f"TSHIFT_X = {_tv(tshift, 'dx')}",
        f"TSHIFT_Y = {_tv(tshift, 'dy')}",
        f"TSHIFT_CORR = {_tcorr(tshift)}",
        f"TSHIFT_CORR0 = {_tcorr0(tshift)}",
        f"TSHIFT_AT = {_esc(getattr(tshift, 'checked_at', '') or '')}",
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
