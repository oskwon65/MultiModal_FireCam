# -*- coding: utf-8 -*-
"""
지금 설비가 어느 운전 상태인지 가린다.

retrain/make_op_states.py 가 만들어 둔 군집 중심을 읽고, 프레임마다 가장
가까운 중심을 고른다. 그게 전부다 - 여기서 군집을 다시 내지 않는다.

[왜 미리 굳혀 두는가]

감시 쪽에서 매번 군집을 내면 같은 프레임이 어제와 오늘 다른 이름을 받는다.
상태 이름은 사람이 화면을 보고 "지금 무슨 상황인가" 를 읽는 것이므로,
자료가 조금 늘었다고 이름이 흔들리면 안 된다. 중심은 파일에 있고, 설비가
바뀌면 사람이 make_op_states.py 를 다시 돌린다.

[이름만으로는 모자란다]

가장 가까운 중심을 고르므로 이름은 무조건 붙는다. 어느 상태와도 닮지 않은
프레임도 다섯 중 하나를 받아, 화면만 보면 늘 아는 상태처럼 보인다. 그래서
중심까지의 거리(칸당 도)를 함께 내보낸다. 분류표에 적힌 '낯선 선'(far)을
넘으면 이름은 붙었어도 처음 보는 모양이고, 설비가 달라졌거나 분류표가
낡은 것이다.

[채점과는 무관하다]

이것은 보여 주기만 한다. 경보에도, 학습 표본을 고르는 데에도 쓰이지 않는다.
분류가 틀려도 감시는 그대로 돈다.
"""
import json
import os
import time

import numpy as np

FILE_NAME = "op_states.json"

# 최근 몇 건으로 '요즘 어떤 상태인지' 를 셀지.
#
# 한 프레임만 보면 경계에서 이름이 깜빡인다. 30초 주기면 120건이 한 시간,
# 5초 주기면 10분이다. 화면에 두 줄로 적을 값이라 이 정도면 충분하다.
RECENT = 120


class OpStates:
    """운전 상태 분류표. 파일이 없으면 아무것도 하지 않는다."""

    def __init__(self, user_path, n_cells):
        self.ok = False
        self.names = []
        self.centers = None
        self.cells = None
        self.info = ""
        self.dev = []        # 상태마다 평소 벗어남 (칸당 도)
        self.far = []        # 이 선을 넘으면 낯설다
        self.last_dev = None  # 마지막 프레임이 중심에서 얼마나 멀었나
        self._recent = []
        self._recent_dev = []
        self._recent_t = []
        self._path = os.path.join(user_path, FILE_NAME)
        self._mtime = None
        self._names_checked = 0.0

        p = self._path
        if not os.path.exists(p):
            self.info = f"{FILE_NAME} 이 없습니다 (retrain/make_op_states.py 로 만듭니다)"
            return

        try:
            with open(p, encoding="utf-8") as f:
                d = json.load(f)
            cells = np.asarray(d["cells"], dtype=np.intp)
            names = [s["name"] for s in d["states"]]
            cen = np.asarray([s["center"] for s in d["states"]], dtype=np.float64)
        except Exception as e:
            self.info = f"{FILE_NAME} 을 읽지 못했습니다: {type(e).__name__} {e}"
            return

        if cen.ndim != 2 or cen.shape[1] != cells.size:
            self.info = f"{FILE_NAME} 의 중심 차원이 칸 수와 맞지 않습니다"
            return
        if cells.size and int(cells.max()) >= n_cells:
            self.info = f"{FILE_NAME} 이 다른 격자 크기로 만들어졌습니다"
            return

        # 기준선이 없는 옛 파일도 받는다. 그때는 낯섦을 말하지 않는다.
        self.dev = [float(s.get("dev", 0.0)) for s in d["states"]]
        self.far = [float(s.get("far", 0.0)) for s in d["states"]]

        self.names = names
        self.centers = cen
        self.cells = cells
        try:
            self._mtime = os.path.getmtime(p)
        except OSError:
            self._mtime = None
        self._names_checked = time.time()
        self.info = f"{len(names)}가지 · {d.get('period', '')} 자료"
        self.ok = True

    def classify(self, x):
        """프레임 하나가 어느 상태인지. 못 가리면 None.

        고른 중심까지의 거리는 last_dev 에 남긴다 - 이름만으로는 억지로
        붙은 것인지 알 수 없기 때문이다.
        """
        if not self.ok:
            return None
        v = np.asarray(x, dtype=np.float64).reshape(-1)
        if v.size <= int(self.cells.max()):
            return None
        d = self.centers - v[self.cells]
        d2 = (d * d).sum(axis=1)
        i = int(np.argmin(d2))

        # 칸당 도로 고친다. 제곱합은 칸 수에 따라 커져 사람이 읽지 못한다.
        self.last_dev = float(np.sqrt(d2[i] / self.centers.shape[1]))

        self._recent.append(i)
        self._recent_dev.append(self.last_dev)
        self._recent_t.append(time.time())
        if len(self._recent) > RECENT:
            del self._recent[:-RECENT]
            del self._recent_dev[:-RECENT]
            del self._recent_t[:-RECENT]
        return i

    def far_of(self, i):
        """그 상태의 낯선 선. 모르면 0."""
        if i is None or not (0 <= i < len(self.far)):
            return 0.0
        return self.far[i]

    def dev_of(self, i):
        """그 상태의 평소 벗어남. 모르면 0."""
        if i is None or not (0 <= i < len(self.dev)):
            return 0.0
        return self.dev[i]

    def is_odd(self, i):
        """이름은 붙었지만 낯선가."""
        f = self.far_of(i)
        return bool(f > 0 and self.last_dev is not None and self.last_dev > f)

    def recent_odd(self):
        """최근 RECENT 건 중 낯선 것의 몫 (0~1). 기준선이 없으면 0."""
        if not self._recent_dev or not self.far:
            return 0.0
        n = 0
        for i, dv in zip(self._recent, self._recent_dev):
            f = self.far_of(i)
            if f > 0 and dv > f:
                n += 1
        return n / len(self._recent_dev)

    def _refresh_names(self):
        """사람이 화면에서 고친 이름을 다시 읽는다. 1분에 한 번만 본다.

        이름은 운전 상태 창의 [이름 바꾸기] 로 op_states.json 에 고쳐 쓴다.
        중심은 그대로이므로 이름만 갈아 끼운다 - 상태 수가 달라졌으면 분류표
        자체가 바뀐 것이라 손대지 않는다(감시를 다시 시작해야 한다).
        """
        now = time.time()
        if not self.ok or now - self._names_checked < 60:
            return
        self._names_checked = now
        try:
            m = os.path.getmtime(self._path)
            if m == self._mtime:
                return
            with open(self._path, encoding="utf-8") as f:
                names = [s["name"] for s in json.load(f)["states"]]
        except Exception:
            return              # 쓰는 중이거나 깨졌으면 다음에 다시 본다
        self._mtime = m
        if len(names) == len(self.names):
            self.names = names

    def name_of(self, i):
        self._refresh_names()
        if i is None or not (0 <= i < len(self.names)):
            return ""
        return self.names[i]

    def recent_mix(self, top=2):
        """최근 RECENT 건의 상태 구성. '전부하 운전 82% · 편중 발열 18%'."""
        self._refresh_names()
        if not self._recent:
            return ""
        n = len(self._recent)
        cnt = {}
        for i in self._recent:
            cnt[i] = cnt.get(i, 0) + 1
        best = sorted(cnt.items(), key=lambda kv: -kv[1])[:top]
        return " · ".join(f"{self.names[i]} {100 * c / n:.0f}%" for i, c in best)

    def recent_count(self):
        return len(self._recent)

    def recent_span_min(self):
        """최근 구성이 걸쳐 있는 시간 (분).

        건수로 세는 것이라 시간 폭은 고정이 아니다. 30초 주기면 120건이
        한 시간이지만, 통신이 끊겨 프레임이 빠지면 같은 120건이 훨씬 긴
        시간에 걸친다. 몇 건인지보다 '언제부터 지금까지'가 읽기 쉬우므로
        실제로 흐른 시간을 잰다.
        """
        if len(self._recent_t) < 2:
            return 0.0
        return (self._recent_t[-1] - self._recent_t[0]) / 60.0
