# put_data_2_db.py

import json
import sys
import numpy as np
import mysql.connector

from utils import Conv_FIFO_to_Median


# ==================================================

def load_thermal_queue_matrix(cursor, length_hotlist, fallback_values) -> np.ndarray:
    cursor.execute("""
        SELECT hot_list
        FROM thermal_queue
        ORDER BY id ASC
    """)
    rows = cursor.fetchall()

    vecs = []
    for (raw,) in rows:
        if raw is None:
            continue

        if isinstance(raw, list):
            v = raw
        else:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="ignore")
            try:
                v = json.loads(raw)
            except json.JSONDecodeError:
                continue

        if isinstance(v, list) and len(v) == length_hotlist:
            vecs.append(v)

    if not vecs:
        vecs = [fallback_values]

    return np.array(vecs, dtype=float)


# ==================================================

def push_thermal_queue_fifo(cursor, hot_list_json: str, maxnum_thermal_fifo: int) -> None:
    cursor.execute(
        """
        INSERT INTO thermal_queue (hot_list)
        VALUES (%s)
        """,
        (hot_list_json,)
    )

    cursor.execute("SELECT COUNT(*) FROM thermal_queue")
    total = cursor.fetchone()[0]

    if total > maxnum_thermal_fifo:
        delete_count = total - maxnum_thermal_fifo
        cursor.execute(
            """
            DELETE FROM thermal_queue
            ORDER BY id ASC
            LIMIT %s
            """,
            (delete_count,)
        )


# ==================================================
# 레코드가 있는 경우는 median_hot_list 만 새롭게 갱신하고
# 나머지 필드는 그대로 둠

def upsert_median_hot_list(cursor, median_json: str) -> None:
    cursor.execute("""
        INSERT INTO current_value (
            id,
            median_hot_list,
            mscore,
            error_code, main_command,
            people_count, fall_people,
            fire_list,
            mask_list,
            m0_gas, m0_tmp, m0_hum, m0_dust,
            s0_gas, s0_tmp, s0_hum,
            updated_at
        )
        VALUES (
            1,
            %s,
            0.0,
            '0000', 'NOACTION',
            0, 0,
            '[]',
            '[]',
            0.0, 0.0, 0.0, 0.0,
            0.0, 0.0, 0.0,
            NOW()
        )
        ON DUPLICATE KEY UPDATE
            median_hot_list = VALUES(median_hot_list),
            updated_at      = NOW()
    """, (median_json,))


# ==================================================

def put_data_to_db(cfg, hotlist_values):
    x_grid         = int(cfg["X_GRID"])
    y_grid         = int(cfg["Y_GRID"])
    length_hotlist = x_grid * y_grid

    maxnum_thermal_fifo = int(cfg["MAXNUM_THERMAL_FIFO"])
    window_size         = 10

    if len(hotlist_values) != length_hotlist:
        raise ValueError(
            f"hotlist length mismatch: expected {length_hotlist}, got {len(hotlist_values)}"
        )

    values = [float(v) for v in hotlist_values]

    user_id      = cfg.get("USER_ID", "")
    db_name      = cfg["DB_NAME_SENSOR"]
    full_db_name = (
        f"{user_id}_{db_name}"
        if user_id and not db_name.startswith(f"{user_id}_")
        else db_name
    )

    db_config = {
        "host":       cfg["DB_HOST"],
        "port":       int(cfg["DB_PORT"]),
        "user":       cfg["DB_USER"],
        "password":   cfg["DB_PASSWORD"],
        "database":   full_db_name,
        "autocommit": True,
    }

    hot_list_json = json.dumps(values, ensure_ascii=False)

    conn   = mysql.connector.connect(**db_config)
    cursor = conn.cursor()

    try:
        push_thermal_queue_fifo(cursor, hot_list_json, maxnum_thermal_fifo)

        data_matrix = load_thermal_queue_matrix(cursor, length_hotlist, values)

        median_values = Conv_FIFO_to_Median(data_matrix, window=window_size)

        if median_values is None:
            print(f"[MEDIAN] warming up ({len(data_matrix)}/{window_size}) - skip")
        else:
            median_result = [round(float(v), 3) for v in median_values]
            median_json   = json.dumps(median_result, ensure_ascii=False)
            upsert_median_hot_list(cursor, median_json)

    finally:
        cursor.close()
        conn.close()