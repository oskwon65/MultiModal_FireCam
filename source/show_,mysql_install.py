import mysql.connector
from mysql.connector import Error

# ================================
# MySQL connection config
# ================================
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "otg_user",
    "password": "otg_password",
}

TARGET_DATABASES = ["sensor_queue", "score_log"]

def print_div(title):
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)

def main():
    try:
        conn = mysql.connector.connect(**DB_CONFIG)
        cur = conn.cursor()
        print("[OK] Connected to MySQL\n")

        # -------------------------------------------------
        # 1. Current user & grants
        # -------------------------------------------------
        print_div("CURRENT USER / GRANTS")
        cur.execute("SELECT USER(), CURRENT_USER()")
        print("USER():", cur.fetchone())

        cur.execute("SHOW GRANTS")
        for row in cur.fetchall():
            print(row[0])

        # -------------------------------------------------
        # 2. Databases
        # -------------------------------------------------
        print_div("DATABASE LIST")
        cur.execute("SHOW DATABASES")
        databases = [r[0] for r in cur.fetchall()]
        for db in databases:
            print("-", db)

        # -------------------------------------------------
        # 3. Inspect target databases
        # -------------------------------------------------
        for db in TARGET_DATABASES:
            if db not in databases:
                print_div(f"[WARN] DATABASE NOT FOUND: {db}")
                continue

            print_div(f"DATABASE: {db}")
            cur.execute(f"USE {db}")

            # Tables
            cur.execute("SHOW TABLES")
            tables = [r[0] for r in cur.fetchall()]
            print("Tables:", tables)

            for table in tables:
                print_div(f"{db}.{table} : DESCRIBE")
                cur.execute(f"DESCRIBE {table}")
                cols = cur.fetchall()
                for c in cols:
                    print(c)

                print(f"\nColumn count: {len(cols)}")

                print_div(f"{db}.{table} : CREATE TABLE")
                cur.execute(f"SHOW CREATE TABLE {table}")
                create_sql = cur.fetchone()[1]
                print(create_sql)

        cur.close()
        conn.close()
        print("\n[OK] Inspection complete")

    except Error as e:
        print("[ERROR]", e)


if __name__ == "__main__":
    main()
