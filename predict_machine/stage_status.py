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


def history_span(conn, db_name):
    """
    히스토리 DB 에 날짜 테이블이 몇 개, 어느 날부터 어느 날까지 있는지.

    count_history_rows 의 테이블 수는 계산기준일 이전을 뺀 것이라 DB 전체가
    아니다. [설정] 창의 "재학습 수집 일수" 옆에 DB 전체 기간을 보여 주려면
    따로 센다. 테이블 이름만 읽으므로 가볍다.

    반환: (테이블 수, 첫 날 "YYYY-MM-DD", 끝 날). 없으면 (0, "", "").
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
        names = [r[0][-8:] for r in cur.fetchall()]
    finally:
        cur.close()

    def _d(x):
        return f"{x[:4]}-{x[4:6]}-{x[6:8]}" if len(x) == 8 and x.isdigit() else ""

    if not names:
        return 0, "", ""
    return len(names), _d(names[0]), _d(names[-1])


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


def _cells(v, dec=1):
    """64칸 배열을 쉼표로 이은 한 줄로. 없으면 빈 칸."""
    if v is None:
        return ""
    try:
        return ",".join(f"{float(x):.{dec}f}" for x in v)
    except (TypeError, ValueError):
        return ""


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


def write(path, baseline, model_ready, user_path,
          db_rows=None, db_tables=None, min_retrain=None, stage_used=None,
          db_span=None,
          abs_guard=None, abs_now=None, cells=None, accum=None,
          shift=None, contrib=None, contrib_at=None,
          op=None, op_now=None, shift_halt=False):
    """
    현황을 통째로 덮어쓴다.

    stage_used 는 직전 프레임에서 실제로 채점에 쓰인 단계(0/1/2).
    "쓸 수 있다" 와 "지금 쓰고 있다" 는 다르므로 따로 적는다.
    """
    gen_name, gen_time = find_generation(user_path)

    # 파일 열쇠(STAGE0~2, STAGE_USED)의 번호는 0부터이고, 화면과 문서의
    # 단계 번호는 1부터다. 열쇠 이름은 C++ 이 읽고 있어 그대로 둔다.
    #   STAGE0 = 1단계 절대 임계값     STAGE1 = 2단계 경험 임계값
    #   STAGE2 = 3단계 오토인코더      STAGE3 = 재학습 세대 유무(번호 없음)
    #   STAGE_USED 0/1/2 = 화면의 1/2/3단계
    stage1 = baseline.is_ready()
    stage2 = bool(model_ready)
    stage3 = gen_name is not None

    # 1단계(절대 임계값)는 학습과 무관하게 늘 동작하지만, 임계값이 지정되지
    # 않으면 판정 자체를 끄고 있다. 그 구분을 화면에서도 볼 수 있어야 한다.
    stage0 = bool(abs_guard is not None and abs_guard.enabled)

    def _t(v):
        return "" if v is None else f"{float(v):.0f}"

    lines = [
        "; 이 파일은 predict_machine 이 자동으로 만듭니다. 직접 고치지 마십시오.",
        "[STATUS]",
        f"UPDATED_AT = {datetime.now():%Y-%m-%d %H:%M:%S}",
        f"BASE_DATE = {_esc(baseline.base_date)}",
        # 기준일은 사람이 정하는 정책이고, 이쪽은 실제로 언제부터 쌓았는지다.
        # 둘이 다를 수 있어 따로 보여줘야 표본 수를 해석할 수 있다.
        f"STARTED_AT = {_esc(getattr(baseline, 'started_at', ''))}",
        # 창이 실제로 들고 있는 양 끝. STARTED_AT 은 처음 넣은 날에 박혀
        # 다시 바뀌지 않으므로, 밀려난 뒤에는 창의 내용보다 길어진다.
        f"WINDOW_FROM = {_esc(getattr(baseline, 'window_from', ''))}",
        f"WINDOW_TO = {_esc(getattr(baseline, 'window_to', ''))}",
        # 지금 쌓고 있는 것이 왜 처음부터인가. 2단계가 "누적 중" 으로 멈춰
        # 있을 때 사람이 가장 먼저 묻는 것이다.
        f"RESET_WHY = {_esc(getattr(baseline, 'reset_why', ''))}",
        f"RESET_AT = {_esc(getattr(baseline, 'reset_at', ''))}",
        "",
        f"STAGE0 = {1 if stage0 else 0}",
        f"ABS_TEMP_WARN = {_t(getattr(abs_guard, 'temp_warn', None))}",
        f"ABS_TEMP_ALARM = {_t(getattr(abs_guard, 'temp_alarm', None))}",
        f"ABS_RISE_WARN = {_t(getattr(abs_guard, 'rise_warn', None))}",
        f"ABS_RISE_ALARM = {_t(getattr(abs_guard, 'rise_alarm', None))}",
        # 방금 잰 값. 선만 보여 주면 지금이 그 선에서 얼마나 떨어져 있는지
        # 알 수 없다. PEAK -1 은 재지 못했다는 뜻이다.
        f"ABS_PEAK = {'' if abs_now is None else f'{abs_now[0]:.1f}'}",
        f"ABS_RISE = {'' if abs_now is None else f'{abs_now[1]:.1f}'}",
        f"ABS_LEVEL = {'' if abs_now is None else int(abs_now[2])}",
        f"ABS_CELL = {'' if abs_now is None else int(abs_now[3])}",
        "",
        f"SAMPLES = {baseline.count}",
        f"MIN_SAMPLES = {baseline.min_samples}",
        f"HOURS = {baseline.hours_covered}",
        f"MIN_HOURS = {baseline.min_hours}",
        # 칸별 현황. 세 줄 모두 64개, 격자 순서 그대로.
        #
        # 점수는 가장 많이 넘은 칸 하나만 돌려주므로, 나머지 63칸이 선에서
        # 얼마나 떨어져 있는지는 어디에도 남지 않았다. 사람이 "이 칸이
        # 70도인 것이 이 칸에 높은 것인가" 를 물을 수 있어야 한다.
        f"CELL_NOW = {_cells(cells[0] if cells else None)}",
        f"CELL_HI = {_cells(cells[1] if cells else None)}",
        f"CELL_MASK = {_cells(cells[2] if cells else None, 0)}",
        # 지금 쌓고 있는가. 멈췄으면 왜 멈췄는가.
        #
        # 누적이 멈춘 것은 표본 수가 늘지 않는 것으로만 드러나는데, 그것을
        # 알아채려면 몇 분을 지켜봐야 한다. 이유까지 적어 둔다.
        f"ACCUM_OK = {'' if accum is None else (1 if accum[0] else 0)}",
        f"ACCUM_WHY = {_esc('' if accum is None else accum[1])}",
        "",
        f"STAGE1 = {1 if stage1 else 0}",
        f"STAGE2 = {1 if stage2 else 0}",
        f"STAGE3 = {1 if stage3 else 0}",
        f"STAGE_USED = {-1 if stage_used is None else int(stage_used)}",
        "",
        # 운전 상태. 보여 주기만 한다 - 경보에도 학습에도 쓰이지 않는다.
        #
        # 이름은 가장 가까운 중심에 무조건 붙으므로, 얼마나 멀리서 붙었는지
        # (OP_DEV)와 그 상태의 낯선 선(OP_FAR)을 함께 적는다. OP_DEV 가
        # OP_FAR 을 넘으면 이름은 붙었어도 처음 보는 모양이다.
        f"OP_STATE = {_esc('' if op is None else op.name_of(op_now))}",
        f"OP_MIX = {_esc('' if op is None else op.recent_mix())}",
        f"OP_INFO = {_esc('' if op is None else op.info)}",
        f"OP_DEV = {'' if op is None or op.last_dev is None else f'{op.last_dev:.1f}'}",
        f"OP_FAR = {'' if op is None else f'{op.far_of(op_now):.1f}'}",
        f"OP_ODD = {'' if op is None else f'{100.0 * op.recent_odd():.0f}'}",
        # OP_MIX 가 걸쳐 있는 시간 (분). 건수로 세므로 폭이 고정이 아니다.
        f"OP_SPAN = {'' if op is None else f'{op.recent_span_min():.0f}'}",
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
        # 카메라 이동으로 2·3단계 판정과 학습을 멈췄는가 (기동 때 RGB 이동
        # 또는 운전 중 열화상 패턴 이동). [설정] 창이 두 단계 줄에 적는다.
        f"SHIFT_HALT = {1 if shift_halt else 0}",
        "",
        f"DB_ROWS = {-1 if db_rows is None else int(db_rows)}",
        f"DB_TABLES = {-1 if db_tables is None else int(db_tables)}",
        # DB 전체 기간. DB_TABLES 는 계산기준일 이전을 뺀 수라 이쪽이 전체다.
        f"DB_ALL_TABLES = {-1 if not db_span else int(db_span[0])}",
        f"DB_FIRST = {'' if not db_span else db_span[1]}",
        f"DB_LAST = {'' if not db_span else db_span[2]}",
        f"MIN_RETRAIN = {-1 if min_retrain is None else int(min_retrain)}",
        "",
        # 재학습이 기존 모델을 얼마나 물려받을지. 칸 수가 아니라 지금 내고
        # 있는 점수로 정한다. 실측에서 3칸을 밀어도 score 0.890 이었고,
        # kict1 은 1.3칸에 0.088 이었다 - 칸 수는 손상을 예측하지 못한다.
        f"DECISION_SCORE = {'' if contrib is None else f'{float(contrib[0]):.4f}' if contrib[0] is not None else ''}",
        f"CONTRIB_W = {'' if contrib is None else f'{float(contrib[1]):.2f}'}",
        # 위 점수와 가중치를 계산한 시각. 값이 낡았는지 화면에서 알 수 있어야 한다.
        f"CONTRIB_AT = {_esc(contrib_at or '')}",
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


def write_error(path, message):
    """
    시작하지 못한 이유를 남긴다.

    감시 화면은 이 파일을 읽어 상태를 보인다. 프로세스가 그냥 죽으면
    "안 떠 있다" 만 보이고 왜인지 알 수 없다. 이유를 적어 두면 화면이
    그대로 보여 줄 수 있다.
    """
    import datetime
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("; 이 파일은 predict_machine 이 자동으로 만듭니다. "
                    "직접 고치지 마십시오.\n")
            f.write("[STATUS]\n")
            f.write(f"UPDATED_AT = {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
            f.write(f"FATAL = {message}\n")
    except OSError as e:
        print(f"[stage_status] 오류를 적지 못했습니다: {e}")
