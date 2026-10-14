import os
import sqlite3
import datetime
import configparser
import sys


# ----------------------------------------------
# Read HOTLIST_LOG_PATH
# ----------------------------------------------
env_path = "env.ini"
if not os.path.exists(env_path):
    sys.exit(f"[ERROR] env.ini not found: {env_path}")

config = configparser.ConfigParser()
config.read(env_path)

try:
    HOTLIST_LOG_PATH = config.get("PATHS", "HOTLIST_LOG_PATH")
except KeyError as e:
    sys.exit(f"[ERROR] Missing key in env.ini: {e}")

print("HOTLIST_LOG_PATH : ", HOTLIST_LOG_PATH);
# ----------------------------------------------

def read_log_db(target_date=None):
    """
    log 폴더 아래 날짜별 score_history.db 파일을 열어 내용 조회
    target_date: 'YYYYMMDD' 형식 문자열 (없으면 오늘 날짜 사용)
    """
    # 기본값: 오늘 날짜
    if target_date is None:
        target_date = datetime.datetime.now().strftime("%Y%m%d")

    # log 폴더 경로 및 DB 파일 경로 구성
    log_dir = os.path.join(os.getcwd(), HOTLIST_LOG_PATH)
    db_filename = f"{target_date}_score_history.db"
    db_path = os.path.join(log_dir, db_filename)

    # DB 존재 확인
    if not os.path.exists(db_path):
        print(f"❌ 지정한 DB 파일이 없음: {db_path}")
        return

    # DB 연결 및 데이터 읽기
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute("SELECT id, timestamp, score, mse FROM score_log ORDER BY id ASC")
        rows = cursor.fetchall()

        if not rows:
            print(f"⚠️ {db_filename} 파일에는 아직 기록된 로그가 없음")
            return

        print(f"📘 [{db_filename}] 데이터 내용:")
        print("-" * 60)
        for row in rows:
            log_id, timestamp, score, mse = row
            print(f"ID={log_id:<4} | {timestamp:<20} | score={score:.5f} | mse={mse:.5f}")

    except Exception as e:
        print(f"⚠️ DB 읽기 중 오류 발생: {e}")

    finally:
        if 'conn' in locals():
            conn.close()


# 실행 예시
if __name__ == "__main__":
    # 오늘 날짜 로그 조회
    read_log_db()

    # 또는 특정 날짜 지정 (예: 2025년 11월 10일 로그)
    # read_log_db("20251110")
