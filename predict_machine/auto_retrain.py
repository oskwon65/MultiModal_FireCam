# -*- coding: utf-8 -*-
"""
자동 재학습.

[재학습] 창의 "자동 재학습" 을 체크하면, 감시가 구한 기여 w 가 1.00 미만일 때 재학습을
스스로 돌린다. w 가 1.00 이면 "기존 모델을 그대로 믿어도 된다" 는 뜻이라 돌리지 않는다.

[어떻게 도는가]

  - 기여 w 는 감시가 약 10분마다 구한다. 그 직후에 이 모듈이 조건을 본다.
  - 재학습은 별도 프로세스(retrain/nightly_retrain.py --fresh)로 띄운다. 감시 루프는
    기다리지 않는다. 학습이 몇 분 걸려도 감시는 그대로 돈다.
  - 새 모델을 올리는 것은 재학습 스크립트다. 감도 시험을 통과하면 승격하고, 못 통과하면
    운용 모델을 그대로 둔다(사람이 [재학습 적용] 을 누를 때와 같은 시험).
    감시는 운용 모델이 갈리면 10초 안에 스스로 다시 읽는다.
  - --fresh 를 붙인다. 안 붙이면 사람이 예전에 돌려 본 예행연습 결과가 남아 있을 때 그것을
    그대로 올려 버린다.

[얼마나 자주]

  마지막으로 시작한 때부터 AUTO_RETRAIN_HOURS(기본 24) 시간이 지나야 다시 돈다. 조건이
  계속 맞아도(w=0.99 처럼 늘 1 미만인 현장도 있다) 그 사이에는 돌리지 않는다. 시작한 때는
  users/<현장>/auto_retrain.ini 에 남기므로 감시를 껐다 켜도 이어진다. 시험에서 막히거나
  표본이 모자라 보류되어도 시작한 것으로 센다 - 안 그러면 10분마다 같은 학습이 돈다.

[이력]

  auto_retrain_history.txt 에 한 건이 끝날 때마다 한 줄씩 쌓는다(지우지 않는다).

    시작 <탭> 종료 <탭> 기여 w <탭> 결과 <탭> 승격된 세대

  결과는 "승격 · 세대", "완료 (변경 없음)", "보류 …", "실패 …" 중 하나다. 감시가 학습 도중에
  꺼지면 끝난 뒤의 결과를 볼 수 없어 "결과 미확인" 으로 적는다. 승격 여부는 끝난 뒤
  current_generation.txt 가 시작 때와 달라졌는지로 가린다.

  시작하지 않은 판별도 간격(AUTO_RETRAIN_HOURS)마다 한 줄 남긴다. "건너뜀 (재학습 불필요 ·
  w 1.00)" 처럼 사유를 적는다. 이력이 비어 있으면 자동 재학습이 살아서 판별하고 있는지
  알 수 없기 때문이다. 약 10분마다 보지만 줄은 간격마다 한 줄이다.

[값을 읽는 곳]

  continual_learning.ini 의 AUTO_RETRAIN(0/1), AUTO_RETRAIN_HOURS. 감시를 다시 켜지 않아도
  반영되도록 조건을 볼 때마다 파일에서 읽는다.
"""

import configparser
import os
import subprocess
import sys
import time
from datetime import datetime

STATE_NAME = "auto_retrain.ini"
HISTORY_NAME = "auto_retrain_history.txt"
LOG_NAME = "auto_retrain.log"

DEFAULT_HOURS = 24
MIN_HOURS = 1
MAX_HOURS = 720

# 감시 옆에서 도는 일이라 감시를 밀어내지 않게 우선순위를 낮춘다.
_WIN_NO_WINDOW = 0x08000000
_WIN_BELOW_NORMAL = 0x00004000

_EXIT_TEXT = {
    0: "완료 (승격되었거나 변경 없음)",
    2: "보류 (표본 또는 시간대가 모자람)",
    3: "보류 (감도 시험 미통과 · 운용 모델 유지)",
}


def _read_ini(path):
    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    try:
        cp.read(path, encoding="utf-8-sig")
    except (OSError, configparser.Error):
        pass
    return cp


class AutoRetrain:

    def __init__(self, user_path, user_id, root=None):
        self.user_path = user_path
        self.user_id = str(user_id)
        self.root = root or os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))
        self.proc = None
        self.log = None
        self._started = ""        # 지금 도는 학습의 시작 시각
        self._w = 0.0
        self._gen_before = ""

        # 이전 감시가 학습 도중에 꺼졌다면 그 학습의 끝을 보지 못했다. 이력에 그렇게 남긴다.
        cp = _read_ini(self._state_path())
        if cp.get("LAST", "RESULT", fallback="") == "진행 중":
            self._history(cp.get("LAST", "AT", fallback=""), "",
                          cp.get("LAST", "W", fallback=""),
                          "결과 미확인 (학습 도중 감시가 꺼짐)", "")
            self._write_state(RESULT="결과 미확인")

    # ---- 설정과 기록 ------------------------------------------------

    def settings(self):
        """(켜짐, 간격 시간). 파일을 읽을 수 없으면 꺼진 것으로 본다."""
        cp = _read_ini(os.path.join(self.user_path, "continual_learning.ini"))
        sec = cp["CONSTANTS"] if cp.has_section("CONSTANTS") else {}

        try:
            on = int(str(sec.get("AUTO_RETRAIN", "0")).strip() or 0) != 0
        except ValueError:
            on = False
        try:
            hours = int(str(sec.get("AUTO_RETRAIN_HOURS", "")).strip() or DEFAULT_HOURS)
        except ValueError:
            hours = DEFAULT_HOURS
        hours = max(MIN_HOURS, min(MAX_HOURS, hours))
        return on, hours

    def _state_path(self):
        return os.path.join(self.user_path, STATE_NAME)

    def last_started(self):
        """마지막으로 시작한 시각(epoch 초). 없으면 0."""
        cp = _read_ini(self._state_path())
        try:
            at = cp.get("LAST", "AT")
            return datetime.strptime(at.strip(), "%Y-%m-%d %H:%M:%S").timestamp()
        except (configparser.Error, ValueError):
            return 0.0

    def _last_check(self):
        """마지막으로 이력에 판별 결과를 적은 시각(epoch 초). 없으면 0."""
        cp = _read_ini(self._state_path())
        try:
            at = cp.get("CHECK", "AT")
            return datetime.strptime(at.strip(), "%Y-%m-%d %H:%M:%S").timestamp()
        except (configparser.Error, ValueError):
            return 0.0

    def _note_skip(self, w, why, hours):
        """시작하지 않았다는 판별을 간격마다 한 번 이력에 적는다."""
        now = time.time()
        if now - self._last_check() < hours * 3600.0:
            return
        at = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")
        wtxt = "" if w is None else f"{float(w):.2f}"
        self._history(at, "", wtxt, why, "")
        self._write_state("CHECK", AT=at, W=wtxt, RESULT=why)

    def _generation(self):
        try:
            with open(os.path.join(self.user_path, "current_generation.txt"),
                      encoding="utf-8-sig") as f:
                return f.read().strip()
        except OSError:
            return ""

    def _history(self, started, ended, w, result, gen):
        try:
            with open(os.path.join(self.user_path, HISTORY_NAME), "a",
                      encoding="utf-8") as f:
                f.write(f"{started}\t{ended}\t{w}\t{result}\t{gen}\n")
        except OSError as e:
            print(f"[WARN] 자동 재학습 이력을 쓰지 못했습니다: {e}")

    def _write_state(self, section="LAST", **kv):
        cp = _read_ini(self._state_path())
        if not cp.has_section(section):
            cp.add_section(section)
        for k, v in kv.items():
            cp.set(section, k, str(v))
        try:
            with open(self._state_path(), "w", encoding="utf-8") as f:
                f.write("; 자동 재학습이 남기는 기록입니다. 직접 고치지 마십시오.\n")
                cp.write(f)
        except OSError as e:
            print(f"[WARN] 자동 재학습 기록을 쓰지 못했습니다: {e}")

    # ---- 돌리기 -----------------------------------------------------

    def running(self):
        return self.proc is not None and self.proc.poll() is None

    def _reap(self):
        """끝난 자식을 거두고 결과를 남긴다."""
        if self.proc is None or self.proc.poll() is None:
            return
        code = self.proc.returncode
        self.proc = None
        if self.log is not None:
            try:
                self.log.close()
            except OSError:
                pass
            self.log = None

        text = _EXIT_TEXT.get(code, f"실패 (종료 코드 {code})")
        ended = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 승격되었는지는 운용 세대가 달라졌는지로 가린다.
        gen_after = self._generation()
        promoted = (code == 0 and gen_after and gen_after != self._gen_before)
        if promoted:
            text = "승격"
        elif code == 0:
            text = "완료 (변경 없음)"
        self._history(self._started, ended, f"{self._w:.2f}", text,
                      gen_after if promoted else "")

        self._write_state(DONE_AT=ended, RESULT=text)
        print(f"[자동 재학습] 끝났습니다 - {text}  (자세한 내용 {LOG_NAME})")

    def tick(self, w):
        """
        w 는 감시가 구한 기여 가중치(없으면 None). 조건이 맞으면 재학습을 띄운다.
        감시 루프에서 부르므로 오래 걸리면 안 된다 - 띄우기만 하고 기다리지 않는다.
        """
        self._reap()

        on, hours = self.settings()
        if not on or self.running():
            return
        if w is None:
            # 아직 기여를 못 구했다(감시를 막 켠 직후) - 모르면 돌리지 않는다. 곧 구해지므로
            # 이력에는 적지 않는다. 적으면 그 한 줄이 간격을 써 버려 진짜 판별이 한 시간 밀린다.
            return
        if float(w) >= 1.0:
            # 기존 모델을 믿어도 된다
            self._note_skip(w, f"건너뜀 (재학습 불필요 · w {float(w):.2f})", hours)
            return

        # 필요하지만 방금 돌렸다. 시작 줄이 이미 이력에 있으므로 따로 적지 않는다.
        if time.time() - self.last_started() < hours * 3600.0:
            return

        self._start(w, hours)

    def _start(self, w, hours):
        script = os.path.join(self.root, "retrain", "nightly_retrain.py")
        cmd = [sys.executable, script, self.user_id, "--fresh"]

        env = dict(os.environ)
        env["PYTHONIOENCODING"] = "utf-8"

        self._started = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._w = float(w)
        self._gen_before = self._generation()

        flags = 0
        if os.name == "nt":
            flags = _WIN_NO_WINDOW | _WIN_BELOW_NORMAL

        try:
            self.log = open(os.path.join(self.user_path, LOG_NAME), "wb")
            self.proc = subprocess.Popen(
                cmd, cwd=self.root, env=env,
                stdout=self.log, stderr=subprocess.STDOUT,
                creationflags=flags)
        except OSError as e:
            self.proc = None
            self.log = None
            print(f"[WARN] 자동 재학습을 시작하지 못했습니다: {e}")
            # 시작하지 못한 것도 시도로 센다. 안 그러면 10분마다 같은 실패가 되풀이된다.
            self._write_state(AT=self._started, W=f"{float(w):.2f}",
                              RESULT=f"시작 실패: {e}")
            self._history(self._started, self._started, f"{float(w):.2f}",
                          f"실패 (시작하지 못함: {e})", "")
            return

        self._write_state(AT=self._started, W=f"{float(w):.2f}", RESULT="진행 중")
        print(f"[자동 재학습] 시작합니다 - 기여 w {float(w):.2f} < 1.00, "
              f"간격 {hours}시간  (기록 {LOG_NAME})")
