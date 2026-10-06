# -*- coding: utf-8 -*-
"""
절대 임계값 안전망 (연속 학습 1단계)

학습이 전혀 없는 상태 — 카메라를 설치한 바로 그 순간 — 에도 동작해야 하는
최소한의 감지 계층이다. 통상적인 열화상 화재 감지기가 하는 일과 같다.

  · 격자 64칸의 최대 온도가 임계값을 넘는가
  · 분당 상승률이 임계값을 넘는가

[중요] 이 계층은 어떤 단계에서도 학습하지 않고 적응하지 않는다.

오토인코더나 셀별 통계는 "이 현장의 평소"를 기준으로 판정하므로, 평소가
서서히 변하면 기준도 함께 따라간다. 그 특성은 오탐을 줄이는 데 유용하지만,
동시에 서서히 커지는 위험을 놓칠 수 있다는 뜻이기도 하다. 절대 임계값은
평소가 무엇이든 상관없이 고정된 선을 지키는 역할을 한다. 학습 기반 판정이
모두 실패해도 이것만은 남는다.

임계값은 설비마다 다르므로 users/<user>/env.ini 에서 지정한다. 값이 없으면
아래 기본값을 쓰되, 현장 설비의 정상 가동 온도를 확인해 반드시 조정해야 한다.
"""

from collections import deque

import numpy as np

# 절대 온도 임계값에는 기본값을 두지 않는다 (None = 사용 안 함).
#
# 처음에는 80/110 도를 기본값으로 두었는데, kict1 실측을 보니 정상 가동
# 중에도 격자 최고가 197도까지 올라간다. 그 기본값이면 설비가 돌 때마다
# 경보가 울리고, 이 경보는 SMS 발송까지 연결되어 있다. 울리는 경보를
# 사람이 무시하기 시작하면 경보 장치가 아니라 소음이 된다.
#
# 설비마다 정상 온도가 전혀 다르므로 추측하지 않는다. 지정되지 않으면
# 절대 온도 판정을 끄고 시작할 때 경고를 남긴다. 대신 상승률 판정은
# 현장 지식이 없어도 쓸 수 있으므로 기본값을 두고 계속 동작시킨다.
DEFAULT_TEMP_WARN = None
DEFAULT_TEMP_ALARM = None

# 분당 상승률에도 기본값을 두지 않는다 (None = 사용 안 함).
#
# 상승률은 절대 온도와 달리 현장 지식 없이도 쓸 수 있을 줄 알았는데,
# 실측해 보니 그렇지 않았다.
#
#   kict1       12도/분 초과가 정상 가동 중 0.15%   (최대 28도/분)
#   cj_busan_1  12도/분 초과가 정상 가동 중 99.05%  (중앙값 20도/분)
#
# 설비가 빠르게 달아오르는 것이 정상인 현장이 있다. cj_busan_1 에 12를
# 넣었다면 사실상 쉬지 않고 경보가 울렸을 것이다. 절대 온도와 마찬가지로
# 추측하지 않는다.
DEFAULT_RISE_WARN = None
DEFAULT_RISE_ALARM = None

# 상승률 계산에 쓰는 관측 구간 (초)
RISE_WINDOW_SEC = 180.0

LEVEL_NORMAL = 0
LEVEL_WARN = 1
LEVEL_ALARM = 2

_LEVEL_NAME = {LEVEL_NORMAL: "정상", LEVEL_WARN: "주의", LEVEL_ALARM: "경보"}


class AbsoluteThreshold:
    """학습과 무관하게 항상 동작하는 고정 임계값 판정기."""

    def __init__(self, config=None):
        config = config or {}

        def _f(key, default):
            raw = config.get(key, None)
            if raw is None or str(raw).strip() == "":
                return default
            try:
                return float(raw)
            except (TypeError, ValueError):
                return default

        self.temp_warn = _f("ABS_TEMP_WARN", DEFAULT_TEMP_WARN)
        self.temp_alarm = _f("ABS_TEMP_ALARM", DEFAULT_TEMP_ALARM)
        self.rise_warn = _f("ABS_RISE_WARN", DEFAULT_RISE_WARN)
        self.rise_alarm = _f("ABS_RISE_ALARM", DEFAULT_RISE_ALARM)

        # (시각, 격자 최대 온도) 이력. 상승률 계산용.
        self._hist = deque()

    def check(self, x, mask, now_sec):
        """
        반환: (level, reason, peak_temp, rise_per_min, worst_cell)

        level 은 LEVEL_NORMAL / LEVEL_WARN / LEVEL_ALARM.
        판정 불가(입력 이상)면 level 은 NORMAL, peak 는 -1 로 돌려준다.

        [왜 64칸 전부를 보는가]

        2·3단계는 마스크 안만 본다. 설비가 놓인 자리의 평소를 배우는 것이
        일이기 때문이다. 1단계까지 그러면 마스크 밖에서 시작한 불은 어느
        단계도 잡지 못한다. 마스크 밖을 보는 것은 화면 이동 감시뿐인데,
        그쪽은 64칸 패턴의 상관계수라 카메라가 밀렸는지를 볼 뿐 온도를
        보지 않는다. kict1 은 2026-07-13 에 화면이 밀렸을 때 가장
        뜨거워진 칸이 마스크 밖이라 채점에 걸리지 않았다.

        1단계는 학습과 무관한 안전망이므로 여기만은 격자 전체를 본다.

        넓혀도 임계값은 그대로 둔다. 두 현장의 전체 기간을 다시 재 보니
        64칸 전체 최고가 마스크 안 최고와 같았고(cj_busan_1 147도,
        kict1 196도) 지금 선을 넘는 프레임은 0건이다.

        mask 는 판정에 쓰지 않는다. 가장 뜨거운 칸이 마스크 밖일 때 사유에
        적어 주는 데만 쓴다 - 그 경우가 바로 전에는 못 보던 것이다.
        """
        x = np.asarray(x, dtype=np.float64).reshape(-1)
        sel = np.asarray(mask, dtype=np.int32).reshape(-1) == 1

        if x.size != sel.size or not sel.any() or not np.all(np.isfinite(x)):
            return LEVEL_NORMAL, "", -1.0, 0.0, -1

        worst = int(np.argmax(x))
        peak = float(x[worst])
        where = "" if sel[worst] else " · 마스크 밖"

        rise = self._update_rise(peak, now_sec)

        level = LEVEL_NORMAL
        reason = ""

        if self.temp_alarm is not None and peak >= self.temp_alarm:
            level = LEVEL_ALARM
            reason = (f"절대온도 {peak:.0f}도 "
                      f"(경보선 {self.temp_alarm:.0f}){where}")
        elif self.rise_alarm is not None and rise >= self.rise_alarm:
            level = LEVEL_ALARM
            reason = (f"급상승 {rise:.1f}도/분 "
                      f"(경보선 {self.rise_alarm:.1f}){where}")
        elif self.temp_warn is not None and peak >= self.temp_warn:
            level = LEVEL_WARN
            reason = (f"절대온도 {peak:.0f}도 "
                      f"(주의선 {self.temp_warn:.0f}){where}")
        elif self.rise_warn is not None and rise >= self.rise_warn:
            level = LEVEL_WARN
            reason = (f"상승 {rise:.1f}도/분 "
                      f"(주의선 {self.rise_warn:.1f}){where}")

        return level, reason, peak, rise, worst

    def _update_rise(self, peak, now_sec):
        """관측 구간 안에서의 분당 상승률을 구한다."""
        self._hist.append((now_sec, peak))

        while self._hist and (now_sec - self._hist[0][0]) > RISE_WINDOW_SEC:
            self._hist.popleft()

        if len(self._hist) < 2:
            return 0.0

        t0, p0 = self._hist[0]
        dt = now_sec - t0

        # 구간이 너무 짧으면 잡음이 상승률로 증폭된다.
        if dt < 30.0:
            return 0.0

        return (peak - p0) / (dt / 60.0)

    @property
    def temp_enabled(self):
        return self.temp_alarm is not None

    @property
    def rise_enabled(self):
        return self.rise_alarm is not None

    @property
    def enabled(self):
        return self.temp_enabled or self.rise_enabled

    def describe(self):
        if not self.enabled:
            return "절대 임계값  전부 꺼짐 (env.ini 의 ABS_* 미지정)"

        parts = []
        if self.temp_enabled:
            parts.append(f"온도 주의 {self.temp_warn:.0f} / 경보 {self.temp_alarm:.0f} 도")
        else:
            parts.append("온도 판정 꺼짐")
        if self.rise_enabled:
            parts.append(f"상승 주의 {self.rise_warn:.0f} / 경보 {self.rise_alarm:.0f} 도/분")
        else:
            parts.append("상승률 판정 꺼짐")
        return "절대 임계값  " + ",  ".join(parts)


def level_name(level):
    return _LEVEL_NAME.get(level, "?")
