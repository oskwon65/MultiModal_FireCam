# -*- coding: utf-8 -*-
"""
경험 임계값을 히스토리 DB 에서 되쌓는다.

  python retrain/rebuild_baseline.py cj_busan_1
  python retrain/rebuild_baseline.py cj_busan_1 --from 20260918
  python retrain/rebuild_baseline.py cj_busan_1 --from 20260918 --to 20260930
  python retrain/rebuild_baseline.py cj_busan_1 --from 20260918 --dry-run

[무엇을 하는가]

감시가 도는 동안 한 프레임씩 쌓던 것을, 이미 DB 에 적혀 있는 프레임으로
한 번에 다시 쌓는다. 기준선이 보는 것은 칸의 온도뿐이고 그 온도는
results_history_YYYYMMDD.hot_list 에 그대로 남아 있으므로, 실시간으로
쌓은 것과 같은 값이 나온다.

[왜 필요한가]

기준선은 3,000건·18시간대를 채워야 서는데, 30초 주기 현장이면 꼬박
하루가 넘는다. 그동안 2단계는 꺼져 있다. 한 번 치워지면(마스크를 다시
떴거나, 예전에 되돌리기가 함께 치우던 때) 그 하루를 다시 기다려야 했다.
DB 에 자료가 있는데 기다릴 이유가 없다.

[무엇을 거르는가]

감시 쪽 accum_ok 와 같은 잣대를 쓴다 - 절대 임계값을 넘은 프레임은 넣지
않는다. 서서히 커지는 열점을 "요즘의 정상" 으로 흡수하면 정작 위험할 때
아무 경보도 나오지 않는다.

화면 틀어짐(scene_shift)은 여기서 가리지 않는다. 그 판정은
RGB 이미지와 그때그때의 기준 패턴이 있어야 하는데 DB 에는 격자만 남는다.
틀어진 구간이 섞일 수 있으므로, 카메라를 옮긴 적이 있으면 --from 을 그
뒤로 잡아야 한다.

[기간은 어떻게 잡는가]

기본은 자료가 있는 가장 최근 날부터 거슬러 올라가며 목표 표본수의 세 배를
채울 만큼이다. 넉넉히 잡는 이유는 고리 버퍼가 알아서 최근 것만 남기기
때문이다. 오래된 구간을 억지로 넣으면 그때의 온도가 "요즘의 정상" 에
섞인다 - 이 현장은 7월과 9월 사이가 64일 비어 있어서 특히 그렇다.
"""
import argparse
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "source"))
sys.path.insert(0, os.path.join(_ROOT, "predict_machine"))
sys.path.insert(0, _HERE)

from db_utils import Set_Env_Config, Get_HistoryDB_Config, Connect_History_DB, position_since
from online_baseline import OnlineBaseline, write_reset_note

BASELINE_NAME = "online_baseline.npz"
RETIRED_DIR = os.path.join("model_generations", "_retired_baseline")


def read_abs_temp_alarm(user_path):
    """절대 임계값(경보). 없으면 None - 그때는 거르지 않는다."""
    import configparser

    for name in ("continual_learning.ini", "env.ini"):
        p = os.path.join(user_path, name)
        if not os.path.exists(p):
            continue
        c = configparser.ConfigParser()
        try:
            c.read(p, encoding="utf-8")
        except (configparser.Error, OSError):
            continue
        v = c.get("CONSTANTS", "ABS_TEMP_ALARM", fallback="").strip()
        if v:
            try:
                return float(v)
            except ValueError:
                pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("user_id")
    ap.add_argument("--from", dest="d_from", default="",
                    help="시작 날짜 YYYYMMDD (없으면 알아서 잡는다)")
    ap.add_argument("--to", dest="d_to", default="",
                    help="끝 날짜 YYYYMMDD (없으면 끝까지)")
    ap.add_argument("--dry-run", action="store_true",
                    help="세어만 보고 저장하지 않는다")
    args = ap.parse_args()

    config = Set_Env_Config(args.user_id, verbose=False)
    user_path = config["LOCAL_USER_PATH"]
    n_cells = config["X_GRID"] * config["Y_GRID"]

    min_samples = int(config.get("BASELINE_MIN_SAMPLES") or 0) or None
    min_hours = int(config.get("BASELINE_MIN_HOURS") or 0) or None

    alarm = read_abs_temp_alarm(user_path)
    print(f"현장 {args.user_id} · 칸 {n_cells}개 · "
          f"절대 임계값(경보) {'없음' if alarm is None else f'{alarm:.0f}도'}")

    hdb = Get_HistoryDB_Config(config)
    conn = Connect_History_DB(hdb)
    cur = conn.cursor()

    db = hdb["database"]
    sql = ("SELECT table_name FROM information_schema.tables "
           "WHERE table_schema=%s AND table_name LIKE 'results_history_%%' "
           "AND table_type='BASE TABLE' ORDER BY table_name")
    cur.execute(sql, (db,))
    tables = [r[0] for r in cur.fetchall()]

    # 카메라 자리가 바뀐 뒤의 것만. 그 앞은 칸마다 다른 곳을 보고 있었다.
    since = position_since(config)
    if since is not None:
        tables = [t for t in tables if t[-8:] >= since.strftime("%Y%m%d")]
        print(f"카메라 자리가 바뀐 {since:%Y-%m-%d %H:%M} 이후만 씁니다")

    if args.d_from:
        tables = [t for t in tables if t[-8:] >= args.d_from]
    if args.d_to:
        tables = [t for t in tables if t[-8:] <= args.d_to]

    if not tables:
        print("[중단] 그 기간에 히스토리 테이블이 없습니다.")
        return 2

    # 기간을 안 주면 최근부터 거슬러 올라가며 넉넉히 잡는다.
    #
    # 고리 버퍼가 알아서 최근 것만 남기므로 많이 넣어도 해롭지 않지만,
    # 옛 구간을 통째로 넣으면 그때의 온도가 요즘의 정상에 섞인다.
    if not args.d_from:
        want = (min_samples or 3000) * 3
        keep, got = [], 0
        for t in reversed(tables):
            cur.execute(f"SELECT COUNT(*) FROM `{db}`.`{t}`")
            got += cur.fetchone()[0]
            keep.append(t)
            if got >= want:
                break
        tables = list(reversed(keep))
        print(f"기간을 정하지 않아 최근 {len(tables)}일로 잡습니다 "
              f"(약 {got:,}건, 목표의 3배)")

    print(f"테이블 {len(tables)}개 ({tables[0][-8:]} ~ {tables[-1][-8:]})")

    bl = OnlineBaseline(n_cells, min_samples, min_hours)

    seen = kept = n_abs = n_bad = 0
    for t in tables:
        cur.execute(f"SELECT `time`, hot_list FROM `{db}`.`{t}` ORDER BY `time`")
        for when, raw in cur.fetchall():
            if since is not None and when < since:
                continue
            seen += 1
            try:
                v = np.asarray(json.loads(raw), dtype=np.float64)
            except (TypeError, ValueError):
                n_bad += 1
                continue
            if v.size != n_cells or not np.all(np.isfinite(v)):
                n_bad += 1
                continue

            # 감시 쪽 accum_ok 와 같은 잣대. 절대 임계값을 넘으면 넣지 않는다.
            if alarm is not None and float(v.max()) >= alarm:
                n_abs += 1
                continue

            if bl.update(v, hour=when.hour, accum=True,
                         day=when.strftime("%Y-%m-%d")):
                kept += 1

    cur.close()
    conn.close()

    print(f"본 {seen:,}건 중 {kept:,}건 사용")
    print(f"절대 임계값 위반 [ {n_abs:,} ] 건 · 읽지 못한 것 [ {n_bad:,} ] 건")
    print(f"창 {bl.count:,}/{bl.min_samples:,}건 · "
          f"시간대 {bl.hours_covered}/{bl.min_hours} · "
          f"{'사용 가능' if bl.is_ready() else '모자람'}")
    print(f"처음 쌓은 날 {bl.started_at or '-'}")

    if args.dry_run:
        print("[예행] 저장하지 않았습니다.")
        return 0

    if not bl.is_ready():
        print("[경고] 이대로 저장해도 2단계는 아직 서지 않습니다. "
              "--from 을 더 앞으로 잡아 보십시오.")

    # 쓰고 있던 것은 지우지 않고 옮겨 둔다. 잘못 잡았으면 되돌릴 수 있어야 한다.
    live = os.path.join(user_path, BASELINE_NAME)
    if os.path.exists(live):
        import datetime
        import shutil

        dst_dir = os.path.join(user_path, RETIRED_DIR)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(
            dst_dir, datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            + "_before_rebuild.npz")
        shutil.move(live, dst)
        print(f"쓰던 기준선은 {os.path.basename(dst)} 로 옮겼습니다.")

    bl.save(live)
    write_reset_note(user_path,
                     f"DB 에서 되쌓음 ({tables[0][-8:]} ~ {tables[-1][-8:]})")
    print(f"저장 : {live}")
    print("       감시를 다시 시작해야 반영됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
