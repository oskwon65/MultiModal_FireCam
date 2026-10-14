# -*- coding: utf-8 -*-
"""
운전 상태를 관제서버와 맞춘다.

[주고받는 것]

  분석서버 -> 관제서버
    지금 상태      이름 · 번호 · 중심까지 거리 · 낯선 선 · 최근 구성. 관제 화면이 보인다.
    분류표         op_states.json 이 이쪽에서 바뀌면(make_op_states.py · [운전 상태] 창의
                   이름 바꾸기) 통째로 올린다. 관제서버 설정 화면이 이것을 고친다.
    단계 현황      stage_status.ini (1·2·3단계 작동 현황). 관제 화면이 [설정] 창과
                   같은 것을 보인다.
  관제서버 -> 분석서버
    분류표         설정 화면에서 이름 · 온도 패턴을 고치면 source=web 으로 저장된다.
                   여기서 받아 op_states.json 에 쓰면 op_state.py 가 1분 안에 다시 읽는다
                   (감시를 다시 시작하지 않아도 된다).

[언제]

감시 루프를 막지 않도록 따로 도는 스레드가 1분마다 한다. 관제서버가 느리거나
꺼져 있어도 감시는 그대로 돈다 - 운전 상태는 보여 주기만 하고 채점과 무관하다.

[누가 이기나]

양쪽에서 동시에 고쳤으면 관제서버(웹) 것을 먼저 받는다. 받은 뒤의 파일 시각을
기억해 두어, 받은 것을 다시 올리지 않는다.

[보안]

올리는 요청은 env.ini [NETWORK] OP_SYNC_KEY 를 X-OP-KEY 머리글로 보낸다. 키는
관제서버 설정 화면 [운전 상태] 탭에서 만든다. 키가 없으면 받기만 한다.
분류표 받기는 현장 폴더의 공개 파일(op_states_svr.json)을 읽으므로 키가 필요 없다.
"""
import json
import os
import threading
import time

import requests

FILE_NAME = "op_states.json"
SYNC_STATE = "op_sync_state.json"
SVR_FILE = "op_states_svr.json"
STAGE_FILE = "stage_status.ini"     # predict_machine/stage_status.py 가 씀
INTERVAL = 60.0
TIMEOUT = 5.0
MAX_STATES = 12
MAX_NAME = 30


def _now_text():
    return time.strftime("%Y-%m-%d %H:%M:%S")


class OpSync:
    def __init__(self, config):
        self.user = config["USER_ID"]
        self.user_path = config["LOCAL_USER_PATH"]
        self.root_url = config["ROOT_URL"].rstrip("/")
        self.viewer_url = (config.get("VIEWER_URL") or "").rstrip("/")
        self.key = config.get("OP_SYNC_KEY") or ""
        self.local = os.path.join(self.user_path, FILE_NAME)
        self.state_path = os.path.join(self.user_path, SYNC_STATE)
        self._now = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._warned = set()
        self._stage_at = ""     # 마지막으로 올린 단계 현황의 UPDATED_AT
        self.state = self._load_state()

    # ------------------------------------------------------------ 바깥에서 부름

    def start(self):
        if not self.key:
            print("[운전상태 동기화] env.ini OP_SYNC_KEY 가 비어 받기만 함 "
                  "(관제서버 설정 화면 [운전 상태] 탭에서 키를 만들 것)")
        self._thread = threading.Thread(target=self._run, name="op_sync", daemon=True)
        self._thread.start()

    def update_now(self, name, index, dev, far, odd, mix):
        """감시 루프가 프레임마다 부른다. 값만 바꿔 두고 바로 돌아간다."""
        with self._lock:
            self._now = {
                "name": name or "",
                "index": -1 if index is None else int(index),
                "dev": None if dev is None else round(float(dev), 1),
                "far": None if far is None else round(float(far), 1),
                "odd": bool(far and dev is not None and dev > far),
                "recent_odd": round(float(odd), 1) if odd is not None else None,
                "mix": mix or "",
                "at": _now_text(),
            }

    # ------------------------------------------------------------ 스레드

    def _run(self):
        # 기동 직후 첫 상태가 생기도록 잠깐 기다린다
        self._stop.wait(15)
        while not self._stop.is_set():
            try:
                self._pull_table()
                self._push_table()
                self._push_now()
                self._push_stage()
            except Exception as e:      # 동기화가 감시를 멈추게 하지 않는다
                self._warn_once("loop", f"[운전상태 동기화] 오류: {type(e).__name__} {e}")
            self._stop.wait(INTERVAL)

    def _warn_once(self, key, msg):
        if key not in self._warned:
            self._warned.add(key)
            print(msg)

    def _api(self, action):
        return f"{self.viewer_url}/assets/op_state_api.php?site={self.user}&action={action}"

    def _post(self, action, body):
        r = requests.post(self._api(action), json=body, timeout=TIMEOUT,
                          headers={"X-OP-KEY": self.key})
        r.raise_for_status()
        d = r.json()
        if not d.get("ok"):
            raise RuntimeError(d.get("message") or "관제서버 거부")
        return d

    # 관제서버에서 고친 분류표 받기
    def _pull_table(self):
        url = f"{self.root_url}/{self.user}/{SVR_FILE}?t={int(time.time())}"
        try:
            r = requests.get(url, timeout=TIMEOUT)
        except requests.RequestException:
            return
        if r.status_code != 200:
            return
        try:
            svr = r.json()
        except ValueError:
            return
        rev = str(svr.get("rev") or "")
        if svr.get("source") != "web" or not rev or rev == self.state.get("pulled_rev"):
            return

        why = self._apply(svr)
        if why:
            self._warn_once("apply:" + rev, f"[운전상태 동기화] 관제서버 분류표를 쓰지 않음 - {why}")
            return
        self.state["pulled_rev"] = rev
        self.state["pushed_mtime"] = self._mtime()
        self._save_state()
        print(f"[운전상태 동기화] 관제서버에서 고친 분류표 받음 ({rev}, "
              f"{svr.get('edited_by') or '-'}) · 1분 안에 적용")

    def _apply(self, svr):
        """받은 분류표를 검사해 op_states.json 에 쓴다. 문제가 있으면 그 이유."""
        cells = svr.get("cells")
        states = svr.get("states")
        if not isinstance(cells, list) or not cells or not isinstance(states, list):
            return "형식 오류"
        if not 1 <= len(states) <= MAX_STATES:
            return f"상태 수 {len(states)}"
        try:
            cells = [int(c) for c in cells]
        except (TypeError, ValueError):
            return "칸 번호 오류"

        old = {}
        if os.path.exists(self.local):
            try:
                with open(self.local, encoding="utf-8") as f:
                    old = json.load(f)
            except Exception:
                old = {}
        old_states = old.get("states") if isinstance(old.get("states"), list) else []

        out_states = []
        for i, s in enumerate(states):
            name = str(s.get("name") or "").strip()
            # 따옴표 · 역빗금은 분석서버 [운전 상태] 창의 이름 고치기가 다루지 못한다
            bad_char = any(ord(ch) < 32 for ch in name) or '"' in name or "\\" in name
            if not name or len(name) > MAX_NAME or bad_char:
                return f"{i + 1}번째 이름"
            center = s.get("center")
            if not isinstance(center, list) or len(center) != len(cells):
                return f"{i + 1}번째 패턴 칸 수"
            try:
                center = [round(float(v), 2) for v in center]
            except (TypeError, ValueError):
                return f"{i + 1}번째 패턴 값"
            if any(v < -40 or v > 400 for v in center):
                return f"{i + 1}번째 패턴 범위"
            # 같은 자리의 옛 통계(비율 · 기준선)는 상태 수가 같을 때만 물려준다
            base = dict(old_states[i]) if len(old_states) == len(states) else {}
            base.update({"id": i, "name": name, "center": center})
            out_states.append(base)

        out = dict(old) if old else {"user": self.user}
        out.update({"cells": cells, "states": out_states,
                    "rev": str(svr.get("rev")), "source": "web",
                    "edited_by": svr.get("edited_by") or ""})
        tmp = self.local + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=1)
        os.replace(tmp, self.local)
        return ""

    # 이쪽에서 바뀐 분류표 올리기
    def _push_table(self):
        if not self.key or not os.path.exists(self.local):
            return
        m = self._mtime()
        if m is None or m == self.state.get("pushed_mtime"):
            return
        try:
            with open(self.local, encoding="utf-8") as f:
                table = json.load(f)
        except Exception:
            return              # 쓰는 중이면 다음에
        try:
            d = self._post("push_table", {"table": table})
        except Exception as e:
            self._warn_once("push_table", f"[운전상태 동기화] 분류표를 올리지 못함: {e}")
            return
        self.state["pushed_mtime"] = m
        self.state["pulled_rev"] = str(d.get("rev") or self.state.get("pulled_rev") or "")
        self._save_state()
        print("[운전상태 동기화] 분류표를 관제서버에 올림")

    def _push_now(self):
        if not self.key:
            return
        with self._lock:
            now = dict(self._now) if self._now else None
        if not now:
            return
        try:
            self._post("push_now", now)
        except Exception as e:
            self._warn_once("push_now", f"[운전상태 동기화] 지금 상태를 올리지 못함: {e}")

    # 1·2·3단계 현황 올리기 (stage_status.ini 를 그대로)
    #
    # 관제 화면이 [설정] 창과 같은 것을 보이게 한다. 파일은 predict_machine 이
    # 30초마다 덮어쓰므로 바뀐 때(UPDATED_AT)만 올린다. 64칸 줄(CELL_*)은
    # 관제 화면이 쓰지 않아 뺀다.
    def _push_stage(self):
        if not self.key:
            return
        path = os.path.join(self.user_path, STAGE_FILE)
        try:
            with open(path, encoding="utf-8") as f:
                lines = f.read().splitlines()
        except OSError:
            return
        status = {}
        for line in lines:
            if not line or line[0] in ";[" or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k = k.strip()
            if k.startswith("CELL_"):
                continue
            status[k] = v.strip()
        at = status.get("UPDATED_AT", "")
        if not at or at == self._stage_at:
            return
        try:
            self._post("push_stage", {"status": status})
        except Exception as e:
            self._warn_once("push_stage", f"[운전상태 동기화] 단계 현황을 올리지 못함: {e}")
            return
        self._stage_at = at

    # ------------------------------------------------------------ 기록

    def _mtime(self):
        try:
            return os.path.getmtime(self.local)
        except OSError:
            return None

    def _load_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _save_state(self):
        try:
            tmp = self.state_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.state, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.state_path)
        except Exception as e:
            self._warn_once("state", f"[운전상태 동기화] 기록을 남기지 못함: {e}")
