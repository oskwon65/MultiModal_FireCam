# db_utils.py
#
import numpy as np
import math
import os
import configparser
import sys
import time
import json
import mysql.connector
import datetime
from pathlib import Path

from constants import ENV_FILE_NAME, LEARN_FILE_NAME, SECRET_FILE_NAME, ERR_CODE, SVR_RGB_IMG_JPG, SVR_IR_IMG_CSV
from constants import PEOPLE_ANALYSIS_FOLDER, PEOPLE_SRCIMG_FOLDER, BASE_IMG_FOLDER
from constants import FIRE_ANALYSIS_FOLDER, FIRE_SRCIMG_FOLDER

X_GRID = 0
Y_GRID = 0
LENGTH_HOTLIST = 0

# ==================================================
# DB NAME HELPER
# ==================================================
def make_user_db_name(user_id, db_name):
    user_id = str(user_id)
    db_name = str(db_name)

    prefix = f"{user_id}_"

    if db_name.startswith(prefix):
        return db_name

    return prefix + db_name


# ==================================================
# DB CONNECTION (SENSOR_DB)
# ==================================================
def Connect_Sensor_DB(SENSOR_DB_CONFIG):
    return mysql.connector.connect(**SENSOR_DB_CONFIG)


# ==================================================
# DB READ (JSON) - NEW SCHEMA (current_value)
# ==================================================
def read_from_current_value_median(SENSOR_DB_CONFIG):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT median_hot_list, updated_at
        FROM current_value
        WHERE id = 1
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return np.empty((0, LENGTH_HOTLIST)), None

    raw = row[0]

    if raw is None:
        vec = []
    elif isinstance(raw, (dict, list)):
        vec = raw
    else:
        vec = json.loads(raw)

    return np.array([vec]), row[1]


# ----------------------------------------------

def read_db_current_status(SENSOR_DB_CONFIG):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT mscore, error_code
        FROM current_value
        WHERE id = 1
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    if row:
        return True, row[0], row[1]
    else:
        return False, None, None


# ----------------------------------------------
# smoke_list 제거 — fire_list 만 반환
def read_people_and_area(SENSOR_DB_CONFIG):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT people_count, fall_people, fire_list
        FROM current_value
        WHERE id = 1
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return 0, 0, []

    people_count, fall_people, fire_raw = row

    if fire_raw is None:
        fire_list = []
    elif isinstance(fire_raw, (dict, list)):
        fire_list = fire_raw
    else:
        fire_list = json.loads(fire_raw)

    return int(people_count), int(fall_people), fire_list


# ==================================================
# DB UPDATE (SENSOR_DB) - NEW SCHEMA (current_value)
# ==================================================
def update_db_current_status(SENSOR_DB_CONFIG, mscore):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE current_value
        SET mscore = %s
        WHERE id = 1
        """,
        (float(mscore),),
    )

    conn.commit()

    cur.close()
    conn.close()


# ----------------------------------------------

def update_db_error_code(SENSOR_DB_CONFIG, error_code):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    print(f"update_db_error_code : {error_code}")

    cur.execute(
        """
        UPDATE current_value
        SET error_code = %s
        WHERE id = 1
        """,
        (error_code,),
    )

    conn.commit()

    cur.close()
    conn.close()


# ----------------------------------------------

def read_db_error_code(SENSOR_DB_CONFIG):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT error_code
        FROM current_value
        WHERE id = 1
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row or row[0] is None:
        return None

    return row[0]


# ----------------------------------------------

def update_db_main_command(SENSOR_DB_CONFIG, new_code):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE current_value
        SET main_command = %s
        WHERE id = 1
        """,
        (new_code,),
    )

    conn.commit()

    cur.close()
    conn.close()


# ----------------------------------------------

def read_db_main_command(SENSOR_DB_CONFIG):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT main_command
        FROM current_value
        WHERE id = 1
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row or row[0] is None:
        return None

    return row[0]


# ----------------------------------------------
# smoke_list 제거 — fire_list 에 smoke 결과가 병합된 값을 받음
def update_sensor_db_table(SENSOR_DB_CONFIG, people_count, fall_people, fire_list):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE current_value
        SET people_count = %s,
            fall_people  = %s,
            fire_list    = %s
        WHERE id = 1
        """,
        (
            int(people_count),
            int(fall_people),
            json.dumps(fire_list, ensure_ascii=False),
        ),
    )

    conn.commit()

    cur.close()
    conn.close()


# ----------------------------------------------

def update_main_sensor(SENSOR_DB_CONFIG, temperature, humidity, voc, dust=0.0):
    """
    current_value 에 메인장치 센서값을 갱신한다.
      m0_gas  ← voc
      m0_tmp  ← temperature
      m0_hum  ← humidity
      m0_dust ← dust (pm2p5 등)
    """
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE current_value
        SET m0_tmp  = %s,
            m0_hum  = %s,
            m0_gas  = %s,
            m0_dust = %s
        WHERE id = 1
        """,
        (float(temperature), float(humidity), float(voc), float(dust)),
    )

    conn.commit()

    cur.close()
    conn.close()


# ----------------------------------------------

def read_main_sensor(SENSOR_DB_CONFIG):
    """
    current_value 에서 메인장치 센서값을 읽는다.
    return: (temperature, humidity, voc, dust)
    """
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT m0_tmp, m0_hum, m0_gas, m0_dust
        FROM current_value
        WHERE id = 1
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return 0.0, 0.0, 0.0, 0.0

    return float(row[0]), float(row[1]), float(row[2]), float(row[3])


# ----------------------------------------------

def update_slave_sensor(SENSOR_DB_CONFIG, gas_ppm, temper_c, humd_pct):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE current_value
        SET s0_gas = %s,
            s0_tmp = %s,
            s0_hum = %s
        WHERE id = 1
        """,
        (float(gas_ppm), float(temper_c), float(humd_pct)),
    )

    conn.commit()

    cur.close()
    conn.close()


# ----------------------------------------------

def read_slave_sensor(SENSOR_DB_CONFIG):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT s0_gas, s0_tmp, s0_hum
        FROM current_value
        WHERE id = 1
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row:
        return 0.0, 0.0, 0.0

    return float(row[0]), float(row[1]), float(row[2])


# ==================================================
# HISTORY_DB: DAILY TABLE SCHEMA
# ==================================================
def Connect_History_DB(HISTORY_DB_CONFIG):
    return mysql.connector.connect(**HISTORY_DB_CONFIG)


def _ensure_daily_results_history_table(cur, history_db: str, table_name: str):
    cur.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name = %s
          AND table_type = 'BASE TABLE'
        """,
        (history_db, table_name),
    )

    exists = cur.fetchone()[0] > 0

    if exists:
        return

    cur.execute(f"USE `{history_db}`")

    cur.execute(f"""
        CREATE TABLE `{table_name}` (
            id        BIGINT AUTO_INCREMENT PRIMARY KEY,
            time      DATETIME NOT NULL,
            mscore    DOUBLE,
            people    INT,
            fall      INT,
            hot_list  JSON NOT NULL,
            fire_list JSON NOT NULL,
            m0_gas    DOUBLE NOT NULL DEFAULT 0,
            m0_tmp    DOUBLE NOT NULL DEFAULT 0,
            m0_hum    DOUBLE NOT NULL DEFAULT 0,
            m0_dust   DOUBLE NOT NULL DEFAULT 0,
            s0_gas    DOUBLE NOT NULL DEFAULT 0,
            s0_tmp    DOUBLE NOT NULL DEFAULT 0,
            s0_hum    DOUBLE NOT NULL DEFAULT 0,
            INDEX idx_time (time)
        ) ENGINE=InnoDB
    """)


def Append_History_DB(HISTORY_DB_CONFIG, mscore, people, fall,
                      hot_list, fire_list,
                      m0_gas=0.0, m0_tmp=0.0, m0_hum=0.0, m0_dust=0.0,
                      s0_gas=0.0, s0_tmp=0.0, s0_hum=0.0):
    """
    HISTORY_DB.results_history_YYYYMMDD 에 INSERT
    fire_list 에 fire + smoke 감지 결과가 통합되어 전달된다.
    """
    conn = None
    cur = None

    history_db_name = HISTORY_DB_CONFIG["database"]

    try:
        conn = Connect_History_DB(HISTORY_DB_CONFIG)
        cur = conn.cursor()

        table_name = _get_daily_results_table_name()

        _ensure_daily_results_history_table(cur, history_db_name, table_name)

        insert_sql = f"""
            INSERT INTO `{history_db_name}`.`{table_name}` (
                time,
                mscore,
                people,
                fall,
                hot_list,
                fire_list,
                m0_gas, m0_tmp, m0_hum, m0_dust,
                s0_gas, s0_tmp, s0_hum
            )
            VALUES (
                NOW(), %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s
            )
        """

        cur.execute(
            insert_sql,
            (
                float(mscore),
                int(people), int(fall),
                json.dumps(hot_list,  ensure_ascii=False),
                json.dumps(fire_list, ensure_ascii=False),
                float(m0_gas), float(m0_tmp), float(m0_hum), float(m0_dust),
                float(s0_gas), float(s0_tmp), float(s0_hum),
            ),
        )

        conn.commit()

        print(f"[Append_History_DB] OK id={cur.lastrowid}  table={table_name}")

    except mysql.connector.Error as e:
        print(f"[Append_History_DB ERROR] {e}")

    finally:
        if cur is not None:
            cur.close()

        if conn is not None:
            conn.close()


# ==================================================

def _get_daily_results_table_name(now=None) -> str:
    if now is None:
        now = datetime.datetime.now()

    return f"results_history_{now.strftime('%Y%m%d')}"


# ==================================================
# machine mask: NEW SCHEMA (current_value.mask_list)
# ==================================================
def update_db_hotlist_mask(SENSOR_DB_CONFIG, hotlist_mask):

    print('-'*50)
    print(f"[update_db_hotlist_mask]")

    if isinstance(hotlist_mask, np.ndarray):
        mask_list = hotlist_mask.tolist()
    else:
        mask_list = list(hotlist_mask)

    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute(
        """
        UPDATE current_value
        SET mask_list = %s
        WHERE id = 1
        """,
        (json.dumps(mask_list, ensure_ascii=False),),
    )

    conn.commit()

    cur.close()
    conn.close()

    Get_db_hotlist_mask(SENSOR_DB_CONFIG)

# ----------------------------

def Read_GridMask_Inf_File(MACH_AREA_MASK, x_grid):

    print("Read_GridMask_Inf_File : ")
    print(MACH_AREA_MASK)

    if not os.path.exists(MACH_AREA_MASK):
        print(f"[ERROR] MACH_AREA_MASK file not found: {MACH_AREA_MASK}")
        return None

    with open(MACH_AREA_MASK, "r", encoding="utf-8") as f:
        tokens = f.read().strip().split()

    hotlist_mask = np.array(tokens, dtype=np.int32)

    print("======= Original hotlist_mask =======")
    if hotlist_mask is not None:
        for i in range(0, len(hotlist_mask), x_grid):
            print(hotlist_mask[i : i + x_grid])
    else:
        print("hotlist_mask is None")
    print("======================================")

    return hotlist_mask


# ----------------------------

def read_db_hotlist_mask(SENSOR_DB_CONFIG):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT mask_list
        FROM current_value
        WHERE id = 1
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row or row[0] is None:
        return []

    raw = row[0]

    if isinstance(raw, (dict, list)):
        return raw

    return json.loads(raw)


# ----------------------------

def Get_db_hotlist_mask(SENSOR_DB_CONFIG):
    cnt = 0

    while True:
        cnt += 1

        if cnt > 10:
            print("error: hotlist_mask is still empty after 10 retries")
            sys.exit(1)

        hotlist_mask = read_db_hotlist_mask(SENSOR_DB_CONFIG)

        if hotlist_mask == []:
            print(f"[WAIT] hotlist_mask empty (retry {cnt}/10), waiting 5 seconds...")
            time.sleep(10)
            continue

        print("-"*50)
        print("[Get_db_hotlist_mask] hotlist_mask from DB :")
            
        if len(hotlist_mask) != LENGTH_HOTLIST:
            print(
                f"[WARNING] hotlist_mask length mismatch "
                f"(expected {LENGTH_HOTLIST}, got {len(hotlist_mask)})"
            )

        for y in range(Y_GRID):
            start = y * X_GRID
            end = start + X_GRID
            row = hotlist_mask[start:end]
            print(" ".join(f"{int(v):2d}" for v in row))

        print("-"*50)
        break



    return hotlist_mask


# ----------------------------

def read_fire_list(SENSOR_DB_CONFIG):
    conn = Connect_Sensor_DB(SENSOR_DB_CONFIG)
    cur = conn.cursor()

    cur.execute("""
        SELECT fire_list
        FROM current_value
        WHERE id = 1
    """)

    row = cur.fetchone()

    cur.close()
    conn.close()

    if not row or row[0] is None:
        return []

    raw = row[0]

    if isinstance(raw, (dict, list)):
        return raw

    return json.loads(raw)


# ----------------------------

def delete_files_of_Base_Img(config):
    if "LOCAL_USER_PATH" not in config:
        sys.exit("[ERROR] LOCAL_USER_PATH is missing in config")

    base_dir = Path(config["LOCAL_USER_PATH"]) / BASE_IMG_FOLDER

    print(f"[INFO] base_img directory: {base_dir}")

    if not base_dir.exists():
        print(f'[WARN] "{base_dir}" 폴더가 존재하지 않습니다. 삭제할 이미지가 없습니다.')
        return

    if not base_dir.is_dir():
        print(f'[WARN] "{base_dir}"는 폴더가 아닙니다.')
        return

    patterns = [
        "*.jpg", "*.jpeg", "*.png", "*.bmp", "*.gif",
        "*.tif", "*.tiff", "*.webp"
    ]

    removed = 0

    for pattern in patterns:
        for img_path in base_dir.glob(pattern):
            try:
                img_path.unlink()
                removed += 1
            except Exception as e:
                print(f"[ERROR] 파일 삭제 실패: {img_path} ({e})")

    print(f"[OK] base_img 폴더에서 이미지 {removed}개를 삭제했습니다.")


# ----------------------------

def Set_Env_Config(user_ID, verbose=True):

    global X_GRID, Y_GRID, LENGTH_HOTLIST

    base_dir = os.getcwd()
    user_path = os.path.join(base_dir, "users", user_ID)
    env_path = os.path.join(user_path, ENV_FILE_NAME)

    if not os.path.isfile(env_path):
        print(f"[ERROR ] ENV_FILE_NAME not found: {env_path}")
        sys.exit(1)

    # 어느 파일을 읽었는지 알리는 줄.
    #
    # 재학습은 제목을 먼저 찍고 그 아래에 자기 형식으로 적으므로 끈다.
    # 설정을 읽는 것이 제목보다 먼저라, 켜 두면 제목 위에 얹힌다.
    if verbose:
        print(f"\n[ENV_FILE] = {env_path}")

    config = configparser.ConfigParser(
        interpolation=configparser.ExtendedInterpolation()
    )
    config.read(env_path, encoding="utf-8")

    # 연속학습 설정은 같은 폴더의 continual_learning.ini 에 둔다.
    #
    # env.ini 는 설치할 때 한 번 정하는 값(카메라 해상도, DB 이름, 경로)이고
    # continual_learning.ini 는 운영하며 계속 만지는 값(임계값, 단계 전환,
    # 기여도, 학습 표본)이다. 성격이 다른 둘이 한 파일에 있으면 현장에서
    # 무엇을 만져도 되는지 알기 어렵다.
    #
    # env.ini 뒤에 읽으므로 같은 열쇠가 양쪽에 있으면 이 파일이 이긴다.
    # 아직 옮기지 않은 현장은 env.ini 의 값으로 그대로 돈다.
    learn_path = os.path.join(user_path, LEARN_FILE_NAME)
    if os.path.isfile(learn_path):
        config.read(learn_path, encoding="utf-8")

    # DB 비밀번호는 저장소(git)에 올라가지 않도록 env.ini 에서 분리해
    # 같은 폴더의 db_secrets.ini 에 둔다. 이어서 읽으면 하나의 config 로 합쳐진다.
    secret_path = os.path.join(user_path, SECRET_FILE_NAME)
    if not os.path.isfile(secret_path):
        print(f"[ERROR ] SECRET_FILE_NAME not found: {secret_path}")
        print(f"[ERROR ] users/db_secrets.ini.sample 을 복사해 비밀번호를 채우세요.")
        sys.exit(1)

    config.read(secret_path, encoding="utf-8")

    # 읽었다는 사실은 적지 않는다.
    #
    # 알려 주는 것이 없다. db_secrets.ini 는 늘 env.ini 와 같은 폴더에
    # 있어 바로 위 [ENV_FILE] 줄과 같은 말이 되고, 예행연습 창처럼
    # 파이썬 출력을 그대로 보여 주는 화면에서는 본론을 밀어낸다.
    #
    # 없을 때는 위에서 [ERROR] 로 알리고 멈추므로 놓칠 일이 없다.

    local_config = {}

    try:
        local_config["ROOT_URL"]    = config["NETWORK"].get("ROOT_URL").rstrip("/")
        local_config["USER_ID"]     = user_ID
        local_config["SLAVE_NUM"]   = config.getint("NETWORK", "SLAVE_NUM")
        local_config["MONITOR_SEAT_ORDER"] = config.getint("NETWORK", "MONITOR_SEAT_ORDER")

        Server_User_Path = local_config["ROOT_URL"] + "/" + user_ID + "/"
        Local_Root_Path = config["PATHS"].get("ROOT_PATH") + "/"
        Local_User_Path = Local_Root_Path + "users/" + user_ID + "/"

        local_config["SVR_USER_PATH"] = Server_User_Path
        local_config["HOTLIST_URL"] = Server_User_Path + SVR_IR_IMG_CSV
        local_config["IMG_URL"]     = Server_User_Path + SVR_RGB_IMG_JPG

        fire_model = config["PATHS"].get("FIRE_MODEL")
        test_img   = config["PATHS"].get("TEST_IMG")

        local_config["FIRE_MODEL_PATH"] = Local_Root_Path + fire_model
        local_config["TEST_IMG"]        = Local_Root_Path + test_img

        local_config["LOCAL_USER_PATH"]      = Local_User_Path
        local_config["PEOPLE_OUTPUT_PATH"]   = Local_User_Path + "log/" + PEOPLE_ANALYSIS_FOLDER + "/"
        local_config["PEOPLE_SRCIMG_PATH"]   = Local_User_Path + "log/" + PEOPLE_SRCIMG_FOLDER + "/"
        local_config["FIRE_OUTPUT_PATH"]     = Local_User_Path + "log/" + FIRE_ANALYSIS_FOLDER + "/"
        local_config["FIRE_SRCIMG_PATH"]     = Local_User_Path + "log/" + FIRE_SRCIMG_FOLDER + "/"
        local_config["BASE_IMG_DIR"]         = Local_User_Path + BASE_IMG_FOLDER

        local_config["WAITING_TIME_GET_SVR_HOTLIST"] = config.getfloat("CONSTANTS", "WAITING_TIME_GET_SVR_HOTLIST")
        local_config["X_GRID"]              = config.getint("CONSTANTS", "X_GRID")
        local_config["Y_GRID"]              = config.getint("CONSTANTS", "Y_GRID")
        local_config["FLIR_WIDTH"]          = config.getint("CONSTANTS", "FLIR_WIDTH")
        local_config["FLIR_HEIGHT"]         = config.getint("CONSTANTS", "FLIR_HEIGHT")
        local_config["MAXNUM_THERMAL_FIFO"] = config.getint("CONSTANTS", "MAXNUM_THERMAL_FIFO")

        # 절대 임계값 (연속 학습 1단계). 학습이 전혀 없는 상태에서도 동작해야
        # 하는 안전망이라, 다른 항목처럼 없으면 죽이지 않고 None 으로 넘긴다.
        # 온도 임계값이 없으면 판정을 끄고 상승률만 쓴다. 설비마다 정상 온도가
        # 전혀 달라 추측한 기본값은 오경보만 낳기 때문이다.
        # 자세한 내용은 predict_machine/abs_threshold.py 참고.
        for _k in ("ABS_TEMP_WARN", "ABS_TEMP_ALARM",
                   "ABS_RISE_WARN", "ABS_RISE_ALARM",
                   # 기여 가중치를 가르는 점수 문턱. 없으면 None 을 넘겨
                   # model_contribution 의 기본값을 쓰게 한다.
                   "CONTRIB_BAND_HIGH", "CONTRIB_BAND_LOW"):
            # 빈칸도 '없음' 으로 본다.
            #
            # getfloat 은 '' 을 만나면 ValueError 로 죽는다. [설정] 창은
            # 절대 임계값 네 칸을 모두 비우는 것을 허용하고(1단계 끄기),
            # 가동 판정 온도도 비우면 자동이라 빈칸이 정상적으로 생긴다.
            _v = config.get("CONSTANTS", _k, fallback="").strip()
            try:
                local_config[_k] = float(_v) if _v else None
            except ValueError:
                print(f"[WARN] {_k} 값을 숫자로 읽지 못했습니다: {_v!r}")
                local_config[_k] = None

        # 연속 학습 단계 전환 조건. 모니터링 프로그램의 [설정] 창에서 바꾼다.
        # 현장마다 수집 주기가 달라(kict1 5초 / cj_busan_1 30초) 같은 표본 수를
        # 모으는 시간이 크게 차이나므로 코드에 박지 않는다. 없으면 None 을 넘겨
        # 파이썬 쪽 기본값(online_baseline.MIN_SAMPLES 등)을 쓰게 한다.
        # 기여도 판단 기준도 같이 읽는다. [설정] 창에서 바꾼다.
        #
        #   CONTRIB_WINDOW_TABLES  판단에 쓸 날짜 테이블 수
        #   CONTRIB_MIN_FRAMES     이 밑이면 판단 보류(기여 1.00)
        #   CONTRIB_MAX_SAMPLES    다시 매길 프레임 수의 상한
        # 학습 표본 구성도 같이 읽는다.
        #
        #   RETRAIN_TARGET_SAMPLES  목표 표본 수
        #   RETRAIN_DYNAMIC_MIX     옛/새 비율을 기여 w 로 정할지 (0/1, 기본 0=가르지 않고 전체에서)
        #   RETRAIN_BUFFER_DAYS     재생버퍼가 훑을 최근 일수 (0=전체)
        for _k in ("BASELINE_MIN_SAMPLES", "BASELINE_MIN_HOURS",
                   "RETRAIN_MIN_SAMPLES", "RETRAIN_MIN_HOURS",
                   "CONTRIB_WINDOW_TABLES", "CONTRIB_MIN_FRAMES",
                   "CONTRIB_MAX_SAMPLES",
                   "RETRAIN_TARGET_SAMPLES",
                   "RETRAIN_DYNAMIC_MIX", "RETRAIN_BUFFER_DAYS"):
            # 위 실수 항목과 같은 이유로 빈칸을 '없음' 으로 본다.
            _v = config.get("CONSTANTS", _k, fallback="").strip()
            try:
                local_config[_k] = int(_v) if _v else None
            except ValueError:
                print(f"[WARN] {_k} 값을 정수로 읽지 못했습니다: {_v!r}")
                local_config[_k] = None

        # 계산 기준일은 없앴다. 옛 ini 에 CALC_BASE_DATE 가 남아 있어도 읽지 않는다.
        # 옛/새 시기의 경계는 기여도 판단 구간(CONTRIB_WINDOW_TABLES 일)이 정한다.
        local_config["CALC_BASE_DATE"] = ""

        local_config["THR_CONF_FIRE"]   = config.getfloat("CONSTANTS", "THR_CONF_FIRE")
        local_config["THR_TEMPT_FIRE"]  = config.getfloat("CONSTANTS", "THR_TEMPT_FIRE")
        local_config["THR_CONF_SMOKE"]  = config.getfloat("CONSTANTS", "THR_CONF_SMOKE")
        local_config["THR_TEMPT_SMOKE"] = config.getfloat("CONSTANTS", "THR_TEMPT_SMOKE")

        local_config["WAITING_TIME_PEOPLE_DETECTION"] = config.getfloat("CONSTANTS", "WAITING_TIME_PEOPLE_DETECTION")
        local_config["THRESH_0_FALL_DOWN"] = config.getfloat("CONSTANTS", "THRESH_0_FALL_DOWN")
        local_config["THRESH_0_PERSON"]    = config.getfloat("CONSTANTS", "THRESH_0_PERSON")

        local_config["NUM_OF_MACHINE_CELLS"]         = config.getint("CONSTANTS", "NUM_OF_MACHINE_CELLS")
        local_config["SZ_OF_LATENT_DIM_AUTOENCODER"] = config.getint("CONSTANTS", "SZ_OF_LATENT_DIM_AUTOENCODER")

        local_config["DB_ADMIN_HOST"]     = config["DB_ADMIN"]["DB_ADMIN_HOST"]
        local_config["DB_ADMIN_PORT"]     = config.getint("DB_ADMIN", "DB_ADMIN_PORT")
        local_config["DB_ADMIN_USER"]     = config["DB_ADMIN"]["DB_ADMIN_USER"]
        local_config["DB_ADMIN_PASSWORD"] = config["DB_ADMIN"]["DB_ADMIN_PASSWORD"]

        local_config["DB_HOST"]         = config["DB_RUNTIME"]["DB_HOST"]
        local_config["DB_PORT"]         = config.getint("DB_RUNTIME", "DB_PORT")
        local_config["DB_USER"]         = config["DB_RUNTIME"]["DB_USER"]
        local_config["DB_PASSWORD"]     = config["DB_RUNTIME"]["DB_PASSWORD"]
        local_config["DB_NAME_SENSOR"]  = config["DB_RUNTIME"]["DB_NAME_SENSOR"]
        local_config["DB_NAME_HISTORY"] = config["DB_RUNTIME"]["DB_NAME_HISTORY"]

        local_config["SHOW_THERMAL_IMG"]  = config.getboolean("SHOW", "SHOW_THERMAL_IMG")
        local_config["ENABLE_SMS_ALERTS"] = config.getboolean("SHOW", "ENABLE_SMS_ALERTS")

        X_GRID = local_config["X_GRID"]
        Y_GRID = local_config["Y_GRID"]
        LENGTH_HOTLIST = X_GRID * Y_GRID

        return local_config

    except KeyError as e:
        sys.exit(f"[ERROR] Missing key in ENV_FILE_NAME section: {e}")


# ----------------------------

def Get_SensorDB_Config(local_config):

    user_ID = local_config.get('USER_ID')
    sensor_db_name = make_user_db_name(user_ID, local_config["DB_NAME_SENSOR"])

    SENSOR_DB_CONFIG = {
        "host":       local_config["DB_HOST"],
        "port":       local_config["DB_PORT"],
        "user":       local_config["DB_USER"],
        "password":   local_config["DB_PASSWORD"],
        "database":   sensor_db_name,
        "autocommit": True,
    }

    print(f"[SENSOR_DB_CONFIG.database]  = {SENSOR_DB_CONFIG['database']}")

    return SENSOR_DB_CONFIG


# ----------------------------

def Get_HistoryDB_Config(local_config):

    user_ID = local_config.get('USER_ID')
    history_db_name = make_user_db_name(user_ID, local_config["DB_NAME_HISTORY"])

    HISTORY_DB_CONFIG = {
        "host":       local_config["DB_HOST"],
        "port":       local_config["DB_PORT"],
        "user":       local_config["DB_USER"],
        "password":   local_config["DB_PASSWORD"],
        "database":   history_db_name,
        "autocommit": True,
    }

    # DB 이름은 적지 않는다.
    #
    # <현장>_<DB_NAME_HISTORY> 라는 규칙에서 바로 나오는 값이라 새로 알려
    # 주는 것이 없고, 접속이 안 되면 그때 오류가 이름과 함께 나온다.
    # 예행연습 창처럼 파이썬 출력을 그대로 보여 주는 화면에서는 본론을
    # 밀어낼 뿐이다.

    return HISTORY_DB_CONFIG