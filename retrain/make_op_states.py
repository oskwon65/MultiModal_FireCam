# -*- coding: utf-8 -*-
"""
운전 상태 분류표를 만든다.

  python retrain/make_op_states.py cj_busan_1
  python retrain/make_op_states.py cj_busan_1 --k 5

히스토리 DB 의 열화상 격자를 k-means 로 나누고, 군집 중심을 사람이 읽을
이름과 함께 users/<현장>/op_states.json 에 적는다. predict_machine 이 그
파일을 읽어 매 프레임 어느 상태인지 가린다.

[왜 미리 만들어 두는가]

감시 쪽에서 매번 군집을 다시 내면 프레임마다 답이 달라진다. 중심을 한 번
정해 파일로 굳혀 두고, 감시는 가장 가까운 중심을 고르기만 한다. 설비가
바뀌면 이 스크립트를 다시 돌린다.

[이름]

온도가 낮은 것부터 다섯 가지로 부른다. 가르는 것은 마스크 칸의 최고 온도와
칸 사이 벌어짐(최고-최저)이다. '편중 발열' 과 '전부하 운전' 은 최고가
비슷한데 벌어짐이 다르다 - 앞은 일부 칸만, 뒤는 여러 칸이 함께 뜨겁다.

[평소 벗어남]

이름은 가장 가까운 중심에 무조건 붙는다. 어느 상태와도 닮지 않은 프레임도
다섯 중 하나를 받으므로, 이름만 보면 늘 아는 상태처럼 보인다. 그래서 상태
마다 '평소 이만큼은 벗어난다'(far)를 함께 적는다 - 그 상태에 속한 프레임이
중심에서 칸당 몇 도나 떨어져 있었는지의 95백분위다. 이 선을 넘으면 이름은
붙었어도 낯선 것이고, 설비가 달라졌거나 분류표가 낡은 것이다.

  python retrain/make_op_states.py cj_busan_1 --stats-only

중심은 그대로 두고 기준선만 다시 재려면 --stats-only 를 쓴다. 중심이
움직이면 어제와 오늘 같은 프레임이 다른 이름을 받는다.
"""
import argparse
import configparser
import json
import os
import sys

import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "source"))
sys.path.insert(0, os.path.join(_ROOT, "predict_machine"))
sys.path.insert(0, _ROOT)

from db_utils import Set_Env_Config, Get_HistoryDB_Config, Connect_History_DB

# 이름. 최고 온도가 낮은 무리부터 차례로 붙는다.
#
# 몇으로 나누느냐에 따라 같은 자리에 다른 이름이 와야 한다. k=5 에서
# '편중 발열' 이던 자리가 k=6 에서는 고르게 조금 더운 무리(중부하)로
# 갈라지고, 편중은 한 칸 뒤로 밀린다. 그래서 k 마다 따로 적어 둔다.
#
# 이름은 짐작이다. 스크립트가 찍어 주는 표(최고·최저·벌어짐)를 보고 맞는지
# 확인해야 한다 - 벌어짐이 큰 무리가 '편중 발열' 이고, 최고가 비슷한데
# 벌어짐이 작으면 여러 칸이 함께 뜨거운 '부하' 쪽이다.
NAMES_BY_K = {
    4: ["정지·저부하", "정상 운전", "전부하 운전", "과열 의심"],
    5: ["정지·저부하", "정상 운전", "편중 발열", "전부하 운전", "과열 의심"],
    6: ["정지·저부하", "정상 운전", "중부하 운전", "편중 발열", "전부하 운전",
        "과열 의심"],
}


def names_for(k):
    if k in NAMES_BY_K:
        return list(NAMES_BY_K[k])
    return [f"상태 {i + 1}" for i in range(k)]

FILE_NAME = "op_states.json"


def load_mask(user_path, n_cells):
    p = os.path.join(user_path, "hotlist_mask_local.ini")
    with open(p, encoding="utf-8") as f:
        v = [int(x) for x in f.read().replace(",", " ").split()]
    if len(v) != n_cells:
        raise RuntimeError(f"마스크 칸 수가 {len(v)} 로 격자 {n_cells} 와 다릅니다")
    return np.asarray(v, dtype=np.int32)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("user_id")
    ap.add_argument("--k", type=int, default=5, help="나눌 상태 수 (기본 5)")
    ap.add_argument("--sample", type=int, default=8000,
                    help="군집을 낼 때 뽑을 프레임 수")
    ap.add_argument("--stats-only", action="store_true",
                    help="중심은 그대로 두고 비율·온도·평소 벗어남만 다시 잰다")
    args = ap.parse_args()

    config = Set_Env_Config(args.user_id, verbose=False)
    user_path = config["LOCAL_USER_PATH"]
    n_cells = config["X_GRID"] * config["Y_GRID"]
    mask = load_mask(user_path, n_cells)
    sel = mask.reshape(-1) == 1

    history_db = Get_HistoryDB_Config(config)
    conn = Connect_History_DB(history_db)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT table_name FROM information_schema.tables
        WHERE table_schema = %s AND table_name LIKE 'results_history_%%'
          AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """,
        (history_db["database"],),
    )
    tables = [r[0] for r in cur.fetchall()]

    X = []
    for t in tables:
        cur.execute(f"SELECT hot_list FROM `{history_db['database']}`.`{t}`")
        for (raw,) in cur.fetchall():
            try:
                v = np.asarray(json.loads(raw), dtype=np.float64)
            except (TypeError, ValueError):
                continue
            if v.size == n_cells and np.all(np.isfinite(v)):
                X.append(v)
    cur.close()
    conn.close()

    if len(X) < args.sample // 2:
        print(f"[중단] 프레임이 {len(X):,}건뿐입니다. 더 모은 뒤 다시 하십시오.")
        return 2

    X = np.asarray(X)
    Z = X[:, sel]
    print(f"프레임 {len(X):,}건 · 마스크 칸 {int(sel.sum())}개 · "
          f"기간 {tables[0][-8:]} ~ {tables[-1][-8:]}")

    peak = Z.max(axis=1)
    p = os.path.join(user_path, FILE_NAME)

    if args.stats_only:
        # 중심을 그대로 쓴다. 기준선만 다시 재는 길이다.
        with open(p, encoding="utf-8") as f:
            old = json.load(f)
        if [int(i) for i in old["cells"]] != [int(i) for i in np.flatnonzero(sel)]:
            print("[중단] 지금 마스크가 분류표를 만들 때와 다릅니다.")
            return 2
        centers = np.asarray([s["center"] for s in old["states"]],
                             dtype=np.float64)
        names = [s["name"] for s in old["states"]]
        print(f"중심 {len(names)}개를 그대로 둡니다 ({old.get('made', '?')} 만듦)")
    else:
        from sklearn.cluster import KMeans

        rng = np.random.default_rng(0)
        S = Z[rng.choice(len(Z), size=min(args.sample, len(Z)), replace=False)]
        km = KMeans(n_clusters=args.k, n_init=10, random_state=0).fit(S)

        # 최고 온도가 낮은 것부터 번호를 다시 매긴다. 이름이 순서를 따른다.
        lab0 = km.predict(Z)
        order = sorted(range(args.k),
                       key=lambda i: np.median(peak[lab0 == i]))
        centers = km.cluster_centers_[order]
        names = names_for(args.k)

    # 프레임마다 가장 가까운 중심과 그 거리.
    #
    # 거리는 칸당 도로 고친다 - 칸 수가 다른 현장끼리도, 사람이 읽기에도
    # 제곱합보다 "칸마다 평균 몇 도쯤 어긋났나" 가 뜻이 통한다.
    d2 = ((Z[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
    lab = d2.argmin(axis=1)
    dev = np.sqrt(d2[np.arange(len(Z)), lab] / Z.shape[1])

    states = []
    for i in range(len(centers)):
        m = lab == i
        if not m.any():
            print(f"[경고] '{names[i]}' 에 속한 프레임이 없습니다.")
        states.append({
            "id": i,
            "name": names[i],
            "center": [round(float(x), 2) for x in centers[i]],
            "share": round(100.0 * float(m.mean()), 1),
            "max": int(np.median(peak[m])) if m.any() else 0,
            "min": int(np.median(Z[m].min(axis=1))) if m.any() else 0,
            "spread": int(np.median(peak[m] - Z[m].min(axis=1))) if m.any() else 0,
            # 평소 이만큼은 벗어난다(중앙값)와, 여기를 넘으면 낯선 선(95%).
            #
            # 둘 다 적는 것은 무리가 헐거운 상태가 있기 때문이다. '과열
            # 의심' 처럼 닮지 않은 것들이 모여 드는 자리는 평소 선 자체가
            # 넓어서, 선 하나만 보면 무엇이 낯선지 가려지지 않는다.
            "dev": round(float(np.median(dev[m])), 1) if m.any() else 0.0,
            "far": round(float(np.percentile(dev[m], 95)), 1) if m.any() else 0.0,
        })

    out = {
        "user": args.user_id,
        "made": tables[-1][-8:],
        "frames": int(len(X)),
        "period": f"{tables[0][-8:]} ~ {tables[-1][-8:]}",
        # 마스크가 바뀌면 중심이 뜻을 잃는다. 어느 칸으로 잰 것인지 남긴다.
        "cells": [int(i) for i in np.flatnonzero(sel)],
        "states": states,
    }
    with open(p, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print()
    print(f"{'상태':<14}{'비율':>7}{'최고':>6}{'최저':>6}{'벌어짐':>8}"
          f"{'평소 벗어남':>13}{'낯선 선':>10}")
    print("-" * 65)
    for s in states:
        print(f"{s['name']:<14}{s['share']:>6.1f}%{s['max']:>6}"
              f"{s['min']:>6}{s['spread']:>8}{s['dev']:>11.1f}도"
              f"{s['far']:>8.1f}도")
    print()
    print(f"저장 : {p}")
    print("       predict_machine 을 다시 시작하면 화면에 나타납니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
