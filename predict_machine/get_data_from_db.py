import sqlite3
import numpy as np

# ==============================================
# (1) 이동 중앙값 필터 함수
# ==============================================
def moving_median(data, window=10):
    """현재 시점을 포함하여 과거 데이터 window개로 median 계산"""
    filtered = []
    for i in range(len(data)):
        start = max(0, i - window + 1)
        end = i + 1
        filtered.append(np.median(data[start:end]))
    return np.array(filtered)


# ==============================================
# (2) DB 연결 및 sensor_data 읽기
# ==============================================
db_path = "sensor_queue.db"
conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute("SELECT * FROM sensor_data ORDER BY id ASC")
rows = cursor.fetchall()

if len(rows) == 0:
    print("⚠️ sensor_data 테이블에 데이터가 없음")
    conn.close()
    exit()

print(f"📊 읽은 데이터 개수: {len(rows)} (각 {len(rows[0]) - 1} 필드)")

# ==============================================
# (3) 각 열(0~15)에 대해 미디언 필터링 수행
# ==============================================
data_array = np.array([row[1:] for row in rows], dtype=float)
num_features = data_array.shape[1]

median_result = []
for col in range(num_features):
    col_values = data_array[:, col]
    filtered = moving_median(col_values, window=10)
    median_value = filtered[-1]
    median_result.append(round(median_value, 3))

print("\n✅ [열별 미디언 필터링 결과]")
print(median_result)

# ==============================================
# (4) median_result 테이블 확인 및 생성
# ==============================================
cursor.execute("""
SELECT name FROM sqlite_master
WHERE type='table' AND name='median_result';
""")
exists = cursor.fetchone()

if not exists:
    print("\n🧱 median_result 테이블이 존재하지 않아 새로 생성함")
    columns = ", ".join([f"d{i} REAL" for i in range(1, 17)])
    cursor.execute(f"""
    CREATE TABLE median_result (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        {columns},
        created_at TEXT DEFAULT (datetime('now', 'localtime'))
    )
    """)
    conn.commit()
    print("✅ median_result 테이블 생성 완료 (timestamp 포함)")

# ==============================================
# (5) 기존 데이터 모두 삭제 후 새 데이터만 저장
# ==============================================
cursor.execute("DELETE FROM median_result")
conn.commit()
print("🧹 기존 median_result 데이터 모두 삭제 완료 (현재값만 유지 예정)")

placeholders = ",".join(["?"] * 16)
insert_sql = f"""
INSERT INTO median_result ({','.join([f'd{i}' for i in range(1,17)])})
VALUES ({placeholders})
"""
cursor.execute(insert_sql, median_result)
conn.commit()

print("\n💾 median_result 테이블에 새 결과 저장 완료! (이전 데이터 제거됨)")

# ==============================================
# (6) 저장된 최신 결과 확인
# ==============================================
cursor.execute("SELECT * FROM median_result ORDER BY id DESC LIMIT 1")
row = cursor.fetchone()

if row:
    values = row[1:-1]  # d1~d16
    created_at = row[-1]
    formatted = ", ".join(f"{v:.3f}" for v in values)
    print("\n📊 DB에 저장된 최신 median_result:")
    print(f"[{formatted}]")
    print(f"🕒 생성 시간: {created_at}")
else:
    print("⚠️ median_result 테이블이 비어 있음")

# ==============================================
# (7) 연결 종료
# ==============================================
conn.close()
print("\n✅ DB 연결 종료 완료")
