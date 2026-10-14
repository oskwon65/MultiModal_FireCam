# clear_reset_db.py
# python clear_reset_db.py cj_busan_1

import sys
import os
import mysql.connector

sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "source")))
from db_utils import Set_Env_Config, Get_HistoryDB_Config, Get_SensorDB_Config


# ==================================================

def clear_history_db(history_db_config):
    db_name = history_db_config["database"]

    conn = mysql.connector.connect(**history_db_config)
    cur  = conn.cursor()

    cur.execute("""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = %s
          AND table_name LIKE 'results_history_%%'
        ORDER BY table_name
    """, (db_name,))

    tables = [row[0] for row in cur.fetchall()]

    if not tables:
        print("[INFO] 삭제할 history 테이블이 없음")
        cur.close(); conn.close()
        return

    print(f"\n[HISTORY DB] 삭제 대상 테이블 ({len(tables)}개):")
    for t in tables:
        print(f"  {t}")

    answer = input("\n위 테이블을 모두 삭제할지 확인 [y/N]: ").strip().lower()

    if answer not in ("y", "yes"):
        print("[SKIP] 취소되었음")
        cur.close(); conn.close()
        return

    for t in tables:
        cur.execute(f"DROP TABLE IF EXISTS `{db_name}`.`{t}`")
        print(f"[OK] Dropped: `{t}`")

    cur.close()
    conn.close()
    print(f"[DONE] {len(tables)}개 history 테이블 삭제 완료")


# ==================================================
# current_value 컬럼 — db_utils.py 함수별 사용 컬럼
# --------------------------------------------------
# read_from_current_value_median : median_hot_list, updated_at
# read_db_current_status         : mscore, error_code
# read_people_and_area           : people_count, fall_people, fire_list
# update_db_current_status       : mscore
# update_db_error_code           : error_code
# update_db_main_command         : main_command
# read_db_main_command           : main_command
# update_sensor_db_table         : people_count, fall_people, fire_list
# update_main_sensor             : m0_gas, m0_tmp, m0_hum, m0_dust
# read_main_sensor               : m0_gas, m0_tmp, m0_hum, m0_dust
# update_slave_sensor            : s0_gas, s0_tmp, s0_hum
# read_slave_sensor              : s0_gas, s0_tmp, s0_hum
# write_dbtable_hotlist_mask     : mask_list
# read_db_hotlist_mask           : mask_list
# read_fire_list                 : fire_list
# ==================================================

def reset_sensor_db(sensor_db_config):
    db_name = sensor_db_config["database"]

    print(f"\n[SENSOR DB] current_value 테이블 재생성: {db_name}")

    answer = input(
        "current_value 테이블을 DROP 후 새 스키마로 재생성하고 "
        "thermal_queue를 비울지 확인 [y/N]: "
    ).strip().lower()

    if answer not in ("y", "yes"):
        print("[SKIP] 취소되었음")
        return

    conn = mysql.connector.connect(**sensor_db_config)
    cur  = conn.cursor()

    cur.execute(f"TRUNCATE TABLE `{db_name}`.`thermal_queue`")
    print("[OK] Truncated: thermal_queue")

    cur.execute(f"DROP TABLE IF EXISTS `{db_name}`.`current_value`")
    print("[OK] Dropped: current_value")

    cur.execute(f"""
        CREATE TABLE `{db_name}`.`current_value` (
            id              TINYINT       NOT NULL,
            median_hot_list JSON          NOT NULL,
            people_count    INT           NOT NULL DEFAULT 0,
            fall_people     INT           NOT NULL DEFAULT 0,
            fire_list       JSON,
            mask_list       JSON,
            mscore          DOUBLE        NOT NULL DEFAULT 0,
            error_code      CHAR(4)       NOT NULL DEFAULT '0000',
            main_command    CHAR(8)       NOT NULL DEFAULT 'NOACTION',
            m0_gas          DOUBLE        NOT NULL DEFAULT 0,
            m0_tmp          DOUBLE        NOT NULL DEFAULT 0,
            m0_hum          DOUBLE        NOT NULL DEFAULT 0,
            m0_dust         DOUBLE        NOT NULL DEFAULT 0,
            s0_gas          DOUBLE        NOT NULL DEFAULT 0,
            s0_tmp          DOUBLE        NOT NULL DEFAULT 0,
            s0_hum          DOUBLE        NOT NULL DEFAULT 0,
            updated_at      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP
                            ON UPDATE CURRENT_TIMESTAMP,
            PRIMARY KEY (id)
        ) ENGINE=InnoDB
    """)
    print("[OK] Created: current_value (new schema)")

    cur.execute(f"""
        INSERT INTO `{db_name}`.`current_value`
            (id, median_hot_list, fire_list, mask_list)
        VALUES
            (1, '[]', '[]', '[]')
    """)
    print("[OK] Inserted default row (id=1)")

    conn.commit()
    cur.close()
    conn.close()
    print("[DONE] current_value 재생성 및 thermal_queue 초기화 완료")


# ==================================================

if __name__ == "__main__":
    user_id = sys.argv[1] if len(sys.argv) > 1 else "cj_busan_1"

    config = Set_Env_Config(user_id)

    history_db_config = Get_HistoryDB_Config(config)
    sensor_db_config  = Get_SensorDB_Config(config)

    clear_history_db(history_db_config)
    reset_sensor_db(sensor_db_config)