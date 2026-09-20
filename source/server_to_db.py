#
# python server_to_db.py cj_busan_1
# NEW SCHEMA + put_data_2_db.py call method
#
# SENSOR_DB:
#   - thermal_queue(id, hot_list, created_at)
#   - current_value(id=1, ..., mask_list, ...)
#

import requests
import re
import os
import sys
import time
import numpy as np
import mysql.connector
import argparse
import traceback


from put_data_2_db import put_data_to_db
from viewer_utils import show_flir_image
from db_utils import (
    Set_Env_Config,
    Get_SensorDB_Config,
    update_slave_sensor,
    update_main_sensor,
    read_from_current_value_median,
    Get_db_hotlist_mask,                 # ① db_utils 의 함수 재사용
)
from utils import _safe_int, Conv_LWIR_to_64_Vector

from constants import SVR_SLAVE_0_VALUES, SVR_MAIN_VALUES   # SVR_HOTLIST_MASK 미사용으로 제거

# ==============================================
# Global variables
# ==============================================

config = {}
SENSOR_DB_CONFIG = {}
LENGTH_HOTLIST = 0

# ==============================================
# Debug log redirection
# ==============================================

def setup_debug_print_log(user_id):
    log_dir = os.path.join(os.getcwd(), "debug_logs")
    os.makedirs(log_dir, exist_ok=True)

    safe_user_id = (
        re.sub(r'[\\/:*?"<>|]', "_", str(user_id))
        if user_id
        else "unknown"
    )

    log_path = os.path.join(
        log_dir,
        f"server_to_db_{safe_user_id}.log"
    )

    log_file = open(log_path, "w", encoding="utf-8", buffering=1)

    sys.stdout = log_file
    sys.stderr = log_file

    print("============================================================")
    print(f"[DEBUG LOG START] {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[DEBUG LOG FILE] {log_path}")
    print(f"[USER_ID] {user_id}")
    print(f"[ARGS] {' '.join(sys.argv)}")
    print("============================================================")

    return log_file


# ==============================================
# DB helpers
# ==============================================

def check_mysql_connection(sensor_db_config):
    try:
        conn = mysql.connector.connect(
            **sensor_db_config,
            connection_timeout=3,
        )
        conn.close()
        return True

    except mysql.connector.Error as e:
        print(f"[ERROR] MySQL connection failed: {e}")
        return False


# ==============================================
# HOTLIST fetch
# ==============================================

def fetch_hotlist_with_image(url, cfg, length_hotlist):
    flir_width  = _safe_int(cfg.get("FLIR_WIDTH"))
    flir_height = _safe_int(cfg.get("FLIR_HEIGHT"))
    x_grid      = _safe_int(cfg.get("X_GRID"))
    y_grid      = _safe_int(cfg.get("Y_GRID"))

    try:
        if flir_width <= 0 or flir_height <= 0 or x_grid <= 0 or y_grid <= 0:
            raise ValueError(
                f"invalid FLIR/grid config: FLIR_WIDTH={flir_width}, "
                f"FLIR_HEIGHT={flir_height}, X_GRID={x_grid}, Y_GRID={y_grid}"
            )

        response = requests.get(url, timeout=5)
        response.raise_for_status()

        hotlist, img = Conv_LWIR_to_64_Vector(response.text, flir_width, flir_height, x_grid, y_grid)

        return hotlist, img

    except Exception as e:
        # 실패 원인 로그는 의도적으로 남기지 않음 (zero-fallback으로 조용히 skip)
        hotlist = [0] * length_hotlist
        img     = np.zeros((max(flir_height, 0), max(flir_width, 0)), dtype=np.int32)

        return hotlist, img


# ==============================================
# Slave sensor fetch
# ==============================================

def fetch_slave_sensor_from_server(root_url, user_id):
    """
    File format (CSV, 2 lines):
        timestamp,seq,temperature,humidity,co_ppm
        2026-06-18 15:20:36,19342,30.75,56.01,5.0

    return:
        (gas_ppm, temper_c, humd_pct) or None on failure
    """
    url = f"{root_url.rstrip('/')}/{user_id}/{SVR_SLAVE_0_VALUES}"

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        lines = response.text.strip().splitlines()

        if len(lines) < 2:
            print(f"[SLAVE] Invalid file: too few lines ({len(lines)})")
            return None

        headers = [h.strip() for h in lines[0].split(",")]
        values  = [v.strip() for v in lines[1].split(",")]

        row = dict(zip(headers, values))

        gas_ppm  = float(row["co_ppm"])
        temper_c = float(row["temperature"])
        humd_pct = float(row["humidity"])

        print(
            f"[SLAVE] co={gas_ppm:.1f}ppm  "
            f"temp={temper_c:.1f}C  "
            f"humi={humd_pct:.1f}%  "
            f"ts={row.get('timestamp', '?')}"
        )

        return gas_ppm, temper_c, humd_pct

    except KeyError as e:
        print(f"[SLAVE] Missing column in file: {e}")
    except ValueError as e:
        print(f"[SLAVE] Value parse error: {e}")
    except Exception as e:
        print(f"[SLAVE] Fetch failed: {e}")

    return None


# ==============================================
# Main sensor fetch
# ==============================================

def fetch_main_sensor_from_server(root_url, user_id):
    """
    File format (CSV, 2 lines):
        timestamp,pm1p0,pm2p5,pm10p0,voc,temperature,humidity
        2026-06-29 15:42:20,13.5,14.1,14.1,167,33.2,44.3

    return:
        (pm1p0, pm2p5, pm10p0, voc, temper_c, humd_pct) or None on failure
    """
    url = f"{root_url.rstrip('/')}/{user_id}/{SVR_MAIN_VALUES}"

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()

        lines = response.text.strip().splitlines()

        if len(lines) < 2:
            print(f"[MAIN] Invalid file: too few lines ({len(lines)})")
            return None

        headers = [h.strip() for h in lines[0].split(",")]
        values  = [v.strip() for v in lines[1].split(",")]

        row = dict(zip(headers, values))

        pm1p0    = float(row["pm1p0"])
        pm2p5    = float(row["pm2p5"])
        pm10p0   = float(row["pm10p0"])
        voc      = float(row["voc"])
        temper_c = float(row["temperature"])
        humd_pct = float(row["humidity"])

        print(
            f"[MAIN] pm1p0={pm1p0:.1f}  pm2p5={pm2p5:.1f}  pm10p0={pm10p0:.1f}  "
            f"voc={voc:.0f}  temp={temper_c:.1f}C  humi={humd_pct:.1f}%  "
            f"ts={row.get('timestamp', '?')}"
        )

        return pm1p0, pm2p5, pm10p0, voc, temper_c, humd_pct

    except KeyError as e:
        print(f"[MAIN] Missing column in file: {e}")
    except ValueError as e:
        print(f"[MAIN] Value parse error: {e}")
    except Exception as e:
        print(f"[MAIN] Fetch failed: {e}")

    return None


# ==============================================
# Main loop
# ==============================================

def main(cfg, sensor_db_config):

    global LENGTH_HOTLIST

    waiting_time = cfg.get("WAITING_TIME_GET_SVR_HOTLIST")
    hotlist_url  = cfg.get("HOTLIST_URL")

    if waiting_time is None:
        print("[ERROR] WAITING_TIME_GET_SVR_HOTLIST is missing in config.")
        sys.exit(1)

    if not hotlist_url:
        print("[ERROR] HOTLIST_URL is missing in config.")
        sys.exit(1)

    X_GRID         = int(cfg["X_GRID"])
    Y_GRID         = int(cfg["Y_GRID"])
    LENGTH_HOTLIST = X_GRID * Y_GRID
    waiting_time   = int(waiting_time)
    slave_num      = int(cfg.get("SLAVE_NUM", 0))

    ZERO_ITEMS_ERR = int(LENGTH_HOTLIST * 0.7)

    hotlist_mask = Get_db_hotlist_mask(sensor_db_config)   # ② 루프 진입 전 1회 로드

    while True:
        if not check_mysql_connection(sensor_db_config):
            print("[WARN] MySQL unavailable. Retrying...")
            time.sleep(waiting_time)
            continue

        hotlist_values, img = fetch_hotlist_with_image(hotlist_url, cfg, LENGTH_HOTLIST)

        zero_count = sum(1 for v in hotlist_values if v == 0)

        if zero_count >= ZERO_ITEMS_ERR:
            print(
                f"[ERROR] hotlist invalid: "
                f"zero_count={zero_count}/{LENGTH_HOTLIST}"
            )
            time.sleep(waiting_time)
            continue

        if len(hotlist_values) != LENGTH_HOTLIST:
            print(
                f"[WARN] HOTLIST size mismatch "
                f"({len(hotlist_values)} != {LENGTH_HOTLIST})"
            )
            time.sleep(waiting_time)
            continue

        print(
            f"[HOTLIST] len={len(hotlist_values)}, "
            f"{hotlist_values[:5]} ... {hotlist_values[-5:]}"
        )

        try:
            put_data_to_db(cfg, hotlist_values)

            main_sensor = fetch_main_sensor_from_server(cfg["ROOT_URL"], cfg["USER_ID"])

            if main_sensor is not None:
                pm1p0, pm2p5, pm10p0, g_voc, g_tmp, g_hum = main_sensor
                update_main_sensor(sensor_db_config, g_tmp, g_hum, g_voc, pm2p5)
            else:
                print("[MAIN] fetch failed")

            if slave_num > 0:
                slave = fetch_slave_sensor_from_server(cfg["ROOT_URL"], cfg["USER_ID"])

                if slave is not None:
                    gas_ppm, temper_c, humd_pct = slave
                    update_slave_sensor(sensor_db_config, gas_ppm, temper_c, humd_pct)
                else:
                    print("[SLAVE] fetch failed")

            hotlist_values, timestamp = read_from_current_value_median(sensor_db_config)

            if cfg.get("SHOW_THERMAL_IMG"):
                show_flir_image(
                    cfg,
                    img,
                    hotlist_values,
                    hotlist_mask,
                    640,
                    480,
                    win_x=645,
                    win_y=0
                )

        except Exception as e:
            print(f"[ERROR] put_data_to_db failed: {e}")
            traceback.print_exc()

        time.sleep(waiting_time)



# ==============================================
# Entry point
# ==============================================

if __name__ == "__main__":

    pre_user_id    = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    debug_log_file = setup_debug_print_log(pre_user_id)

    try:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "user_ID",
            help="user_ID under ./users, e.g. cj_busan_1"
        )
        args = parser.parse_args()

        config           = Set_Env_Config(args.user_ID)
        SENSOR_DB_CONFIG = Get_SensorDB_Config(config)
        LENGTH_HOTLIST   = int(config["X_GRID"]) * int(config["Y_GRID"])

        print("============================================================")
        print("[CONFIG LOADED]")
        print(f"USER_ID             = {config.get('USER_ID')}")
        print(f"X_GRID              = {config.get('X_GRID')}")
        print(f"Y_GRID              = {config.get('Y_GRID')}")
        print(f"LENGTH_HOTLIST      = {LENGTH_HOTLIST}")
        print(f"SLAVE_NUM           = {config.get('SLAVE_NUM')}")
        print(f"SENSOR_DB           = {SENSOR_DB_CONFIG.get('database')}")
        print("============================================================")

        main(config, SENSOR_DB_CONFIG)

    except Exception as e:
        print(f"[FATAL] server_to_db.py terminated by exception: {e}")
        traceback.print_exc()
        sys.exit(1)

    finally:
        try:
            print("============================================================")
            print(f"[DEBUG LOG END] {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("============================================================")
            debug_log_file.close()
        except Exception:
            pass