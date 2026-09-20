# show_db.py
# python show_db.py cj_busan_1
# python show_db.py cj_busan_1 20

import sys
import json
import mysql.connector
import datetime
import os

sys.path.append(os.path.abspath(os.path.join(os.getcwd(), "source")))

import db_utils
db_utils._SILENT = True

from db_utils import Set_Env_Config, Get_HistoryDB_Config, Get_SensorDB_Config


# ==================================================
# 컬럼별 출력 너비 지정
# ==================================================

COL_WIDTH = {
    "id":      6,
    "time":   20,
    "mscore":  7,
    "people":  4,
    "fall":    4,
    "m0_gas":  7,
    "m0_tmp":  7,
    "m0_hum":  7,
    "m0_dust": 7,
    "s0_gas":  7,
    "s0_tmp":  7,
    "s0_hum":  7,
}
DEFAULT_WIDTH = 10


def col_w(name):
    return COL_WIDTH.get(name, DEFAULT_WIDTH)


# ==================================================

def check_sensor_db(sensor_db_config, x_grid=8):

    print()
    print("=" * 80)
    print(f"  SENSOR DB : {sensor_db_config['database']}.current_value")
    print("=" * 80)

    conn = mysql.connector.connect(**sensor_db_config)
    cur  = conn.cursor()

    cur.execute("""
        SELECT
            id, updated_at,
            mscore,
            error_code, main_command,
            people_count, fall_people,
            m0_gas, m0_tmp, m0_hum, m0_dust,
            s0_gas, s0_tmp, s0_hum
        FROM current_value
        WHERE id = 1
    """)

    row = cur.fetchone()

    if row is None:
        print("[WARN] current_value has no row (id=1)")
        cur.close(); conn.close()
        return

    (id_, updated_at, mscore,
     err_code, main_cmd,
     people, fall,
     m0_gas, m0_tmp, m0_hum, m0_dust,
     s0_gas, s0_tmp, s0_hum) = row

    print(f"  updated_at    : {updated_at}")
    print(f"  mscore        : {mscore:.4f}" if mscore is not None else "  mscore        : N/A")
    print(f"  error_code    : {err_code}")
    print(f"  main_command  : {main_cmd}")
    print(f"  people_count  : {people}   fall_people : {fall}")
    print(f"  m0_gas(voc)   : {m0_gas:.2f}  m0_tmp : {m0_tmp:.2f}  m0_hum : {m0_hum:.2f}  m0_dust : {m0_dust:.2f}")
    print(f"  s0_gas(co)    : {s0_gas:.2f}  s0_tmp : {s0_tmp:.2f}  s0_hum : {s0_hum:.2f}")

    # ---- fire_list (fire+smoke 통합) ----
    cur.execute("SELECT fire_list FROM current_value WHERE id = 1")
    fire_row = cur.fetchone()

    if fire_row and fire_row[0] is not None:
        vals = fire_row[0] if isinstance(fire_row[0], list) else json.loads(fire_row[0])
        print(f"\n  fire_list (fire+smoke 통합, {x_grid} per line):")
        if not vals:
            print("    []")
        else:
            for i in range(0, len(vals), x_grid):
                chunk = vals[i:i + x_grid]
                line  = "  ".join(f"{v:5.1f}" for v in chunk)
                print(f"    [{i:>4}]  {line}")

    # ---- hotlist_mask (mask_list) ----
    cur.execute("SELECT mask_list FROM current_value WHERE id = 1")
    mask_row = cur.fetchone()

    if mask_row and mask_row[0] is not None:
        mask_vals = mask_row[0] if isinstance(mask_row[0], list) else json.loads(mask_row[0])
        print(f"\n  hotlist_mask ({x_grid} per line):")
        if not mask_vals:
            print("    []")
        else:
            for i in range(0, len(mask_vals), x_grid):
                chunk = mask_vals[i:i + x_grid]
                line  = "  ".join(f"{int(v):2d}" for v in chunk)
                print(f"    [{i:>4}]  {line}")
    else:
        print("\n  hotlist_mask: N/A (empty)")

    # ---- thermal_queue ----
    cur.execute("SELECT COUNT(*) FROM thermal_queue")
    q_count = cur.fetchone()[0]

    cur.execute("""
        SELECT id, created_at, hot_list
        FROM thermal_queue
        ORDER BY id DESC
        LIMIT 5
    """)
    q_rows = cur.fetchall()

    print()
    print(f"  thermal_queue : {q_count} rows  (latest {len(q_rows)} shown)")
    print(f"  {'id':>6}  {'created_at':>20}  hot_list ({x_grid} per line, 1dp)")
    print("  " + "-" * 70)

    for q_id, q_ts, q_raw in q_rows:
        if q_raw is None:
            print(f"  {q_id:>6}  {str(q_ts):>20}  None")
            continue

        vals = json.loads(q_raw) if isinstance(q_raw, str) else q_raw
        print(f"  {q_id:>6}  {str(q_ts):>20}")
        for i in range(0, len(vals), x_grid):
            chunk = vals[i:i + x_grid]
            line  = "  ".join(f"{v:5.1f}" for v in chunk)
            print(f"  {'':>6}  {'':>20}  [{i:>4}]  {line}")

    print("=" * 80)
    cur.close()
    conn.close()


# ==================================================

def get_table_columns(cur, db_name, table_name):
    cur.execute("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = %s
          AND table_name   = %s
        ORDER BY ordinal_position
    """, (db_name, table_name))

    return [(row[0], row[1]) for row in cur.fetchall()]


# ==================================================

def check_history_db(history_db_config, limit=10, x_grid=8):
    table_name = f"results_history_{datetime.datetime.now().strftime('%Y%m%d')}"
    db_name    = history_db_config["database"]

    print()
    print("=" * 80)
    print(f"  HISTORY DB : {db_name}.{table_name}")
    print("=" * 80)

    conn = mysql.connector.connect(**history_db_config)
    cur  = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
    """, (db_name, table_name))

    if cur.fetchone()[0] == 0:
        print(f"[WARN] Table not found: {table_name}")
        cur.close(); conn.close()
        return

    # ---- 컬럼 자동 조회 ----
    all_columns = get_table_columns(cur, db_name, table_name)
    json_types  = {"json", "longtext", "mediumtext", "text"}
    columns     = [(name, dtype) for name, dtype in all_columns
                   if dtype.lower() not in json_types]
    json_cols   = [name for name, dtype in all_columns
                   if dtype.lower() in json_types]
    col_names   = [name for name, _ in columns]

    # ---- SELECT (숫자/텍스트 컬럼 + JSON 컬럼) ----
    json_sql = (", " + ", ".join(f"`{c}`" for c in json_cols)) if json_cols else ""
    col_sql  = ", ".join(f"`{c}`" for c in col_names)
    cur.execute(f"""
        SELECT {col_sql}{json_sql}
        FROM `{table_name}`
        ORDER BY id DESC
        LIMIT {limit}
    """)
    rows = cur.fetchall()

    n_scalar = len(col_names)

    # ---- 헤더 ----
    total_w = sum(col_w(n) for n in col_names) + 2 * (len(col_names) - 1)
    sep     = "-" * total_w

    header = "  ".join(f"{n:>{col_w(n)}}" for n in col_names)
    print(header)
    print(sep)

    # ---- 행 ----
    for row in rows:
        scalar_vals = row[:n_scalar]
        json_vals   = row[n_scalar:]

        cells = []
        for val, (name, dtype) in zip(scalar_vals, columns):
            w = col_w(name)
            if val is None:
                cells.append(f"{'N/A':>{w}}")
            elif dtype.lower() in ("double", "float"):
                cells.append(f"{float(val):>{w}.3f}")
            elif dtype.lower() in ("int", "bigint", "tinyint", "smallint"):
                cells.append(f"{int(val):>{w}}")
            else:
                cells.append(f"{str(val):>{w}}")
        print("  ".join(cells))

        # JSON 컬럼: x_grid 개씩 한 줄, 소수점 1자리
        for jcol, jval in zip(json_cols, json_vals):
            if jval is None:
                parsed = []
            else:
                parsed = json.loads(jval) if isinstance(jval, str) else jval

            if not parsed:
                print(f"    {jcol}: []")
                continue

            label = f"{jcol} (fire+smoke 통합)" if jcol == "fire_list" else jcol
            print(f"    {label}:")
            for i in range(0, len(parsed), x_grid):
                chunk = parsed[i:i + x_grid]
                line  = "  ".join(f"{v:5.1f}" for v in chunk)
                print(f"      [{i:>4}]  {line}")

    cur.execute(f"SELECT COUNT(*) FROM `{table_name}`")
    total = cur.fetchone()[0]
    print(sep)
    print(f"  Total rows today: {total}")
    print("=" * 80)

    cur.close()
    conn.close()


# ==================================================

if __name__ == "__main__":
    print("[START] show_db.py")

    try:
        user_id = sys.argv[1] if len(sys.argv) > 1 else "cj_busan_1"
        limit   = int(sys.argv[2]) if len(sys.argv) > 2 else 10

        print(f"[INFO] user_id={user_id}, limit={limit}")

        config = Set_Env_Config(user_id)
        print(f"[INFO] config loaded")

        sensor_db_config  = Get_SensorDB_Config(config)
        history_db_config = Get_HistoryDB_Config(config)
        print(f"[INFO] sensor_db : {sensor_db_config['database']}")
        print(f"[INFO] history_db: {history_db_config['database']}")

        x_grid = int(config["X_GRID"])

        check_sensor_db(sensor_db_config, x_grid=x_grid)
        check_history_db(history_db_config, limit, x_grid=x_grid)

    except Exception as e:
        import traceback
        traceback.print_exc()