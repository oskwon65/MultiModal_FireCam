# -*- coding: utf-8 -*-
"""
열화상 기준으로 카메라가 밀렸는지 본다.

지금까지 틀어짐 검사는 RGB 이미지(rgb_img.jpg)만 보았다. 그런데 2026-07-13
kict1 에서 실제로 밀린 것은 열화상 카메라였다. 두 카메라가 한 하우징에
붙어 함께 움직였다면 RGB 검사로도 잡혔겠지만, 열화상만 틀어지면 RGB 쪽은
끝까지 "이상 없음" 이다. 실제로 그랬고, 그래서 두 달을 모르고 지나갔다.

또 하나. RGB 검사는 기동할 때 한 번만 한다. kict1 의 이동은 낮 13:48 에
일어났다. 재시작 전까지는 잴 기회조차 없다. 열화상 격자는 매 프레임
DB 에서 읽고 있으므로, 여기서는 운전 중에도 주기적으로 다시 본다.

판정은 두 가지를 따로 말한다.

  1) 몇 칸 밀렸는가
     64셀 온도 패턴을 한 칸씩 밀어 가며 기준 패턴과의 상관계수를 재고,
     제자리보다 뚜렷하게 잘 맞는 자리가 있으면 그만큼 밀린 것으로 본다.
     실제 kict1 프레임에 평행이동을 주입해 시험했을 때 201/201 을 맞혔다.

  2) 애초에 같은 화면인가
     칸 수를 못 밝혀도 화면이 달라진 것은 알 수 있다. 그리고 kict1 의
     7월 기록이 정확히 그런 경우였다 — 어느 방향으로도 잘 맞는 자리가
     없었고, 화면 전체가 최고 56도에서 196도로 바뀌었다. 곱게 평행이동한
     것이 아니라 보는 대상 자체가 달라진 것이다. 1)만 있었다면 이 사고는
     "이상 없음" 으로 적혔다.

기준 패턴은 online_baseline 의 셀별 평균에서 한 번 떠서 파일로 굳힌다.
기준선을 그대로 쓰면 안 된다. 카메라가 밀린 뒤에도 기준선은 계속 배우므로
새 위치가 서서히 "평소" 가 되고, 틀어짐이 저절로 0 으로 돌아간다. 조준이
틀어진 채 경보가 조용히 풀리는 것이 가장 나쁜 결말이다.
"""

import os

import numpy as np

REF_FILE_NAME = "thermal_ref.npy"

# 기준 패턴을 굳히기 전에 모아야 할 프레임 수. 하루 치가 안 되면 설비가
# 도는 시간대만 담긴 반쪽 패턴이 굳어 버린다.
MIN_REF_SAMPLES = 3000

# 한 방향으로 몇 칸까지 볼 것인가. 8x8 격자에서 3칸이면 겹치는 셀이
# 최소 25개 남는다. 더 밀린 것은 조준이 통째로 바뀐 것이라 칸 단위로
# 맞춰 볼 일이 아니다.
MAX_SHIFT = 3

# 겹치는 셀이 이보다 적으면 상관계수를 믿지 않는다.
MIN_OVERLAP = 20

# 패턴이 밋밋하면(어디나 같은 온도) 어느 자리든 상관이 비슷하게 나온다.
# 그런 화면에서는 아예 판정하지 않는다.
MIN_PATTERN_STD = 1.0

# 밀린 자리가 제자리보다 이만큼은 잘 맞아야 이동으로 본다. kict1 은
# 0.84 차이였다. 설비가 켜지고 꺼지는 정도로는 이만큼 벌어지지 않는다.
CORR_GAIN = 0.15

# 밀린 자리의 상관계수 자체도 이 정도는 되어야 한다. 둘 다 엉망인데
# 한쪽이 조금 덜 엉망인 경우를 이동이라고 부르지 않기 위한 조건이다.
#
# MIN_MATCH 와 같은 값을 쓴다. 뜻이 하나로 모인다 — "밀린 자리가 평소
# 날만큼은 맞아야 몇 칸이라고 말한다". 처음에 0.60 으로 두었더니 kict1 의
# 9월 기록에서 0.613 짜리 자리를 잡아 "가로 -1칸 · 세로 +3칸" 이라고
# 단언했다. 그 숫자대로 마스크를 옮기면 더 나빠진다. 어설프게 아는 것보다
# "안 맞는다" 고만 말하는 편이 낫다.
MIN_CORR = 0.85

# 제자리 상관이 이보다 낮으면 "화면이 달라졌다" 고 본다. 몇 칸 밀렸는지
# 못 밝혀도 이 사실만은 알려야 한다.
#
# kict1 의 실제 7월 기록이 이 조건의 이유다. 이동 전 열흘은 날마다
# 0.976~0.990 으로 붙어 있다가, 사고 당일 0.661, 다음 날부터는 -0.11 로
# 떨어졌다. 그런데 어느 방향으로도 잘 맞는 자리가 없었다. 화면 전체가
# 최고 56도에서 196도로 바뀌었기 때문이다. 카메라가 곱게 평행이동한 것이
# 아니라 보는 대상 자체가 달라진 것이다.
#
# 칸 수를 못 밝히면 "이상 없음" 이라고 적는 설계였다면, 이 경우가 그대로
# 묻힌다. 실제로 두 달을 묻혔다.
MIN_MATCH = 0.85

# 운전 중 다시 재는 간격(초).
RECHECK_INTERVAL = 1800


def ref_path(user_path):
    return os.path.join(user_path, REF_FILE_NAME)


def load_ref(user_path, n_cells):
    """굳혀 둔 기준 패턴. 없거나 길이가 안 맞으면 None."""
    p = ref_path(user_path)
    if not os.path.exists(p):
        return None
    try:
        ref = np.load(p)
    except Exception as e:
        print(f"[WARN] 열화상 기준 패턴을 읽지 못했습니다: {e}")
        return None
    ref = np.asarray(ref, dtype=np.float64).reshape(-1)
    if ref.size != n_cells:
        print(f"[WARN] 열화상 기준 패턴의 길이({ref.size})가 셀 수({n_cells})와 "
              f"다릅니다. 무시합니다.")
        return None
    return ref


def save_ref(user_path, pattern):
    """기준 패턴을 굳힌다. 이미 있으면 덮어쓴다."""
    p = ref_path(user_path)
    tmp = p + ".tmp"
    try:
        # 파일 객체로 넘긴다. 경로 문자열로 주면 확장자가 .npy 가 아닐 때
        # numpy 가 멋대로 붙여 엉뚱한 이름으로 남는다.
        with open(tmp, "wb") as f:
            np.save(f, np.asarray(pattern, dtype=np.float64).reshape(-1))
        os.replace(tmp, p)
        return True
    except Exception as e:
        print(f"[WARN] 열화상 기준 패턴을 쓰지 못했습니다: {e}")
        return False


def clear_ref(user_path):
    """
    기준 패턴을 버린다.

    사람이 "카메라 이동보정" 을 승인했다는 것은 지금 보이는 화면이 앞으로의
    정상이라는 뜻이다. RGB 쪽에서 base_img 를 지우고 현재 이미지를 새
    기준으로 저장하는 것과 같은 처리를, 열화상 쪽에도 해 준다.
    """
    p = ref_path(user_path)
    try:
        if os.path.exists(p):
            os.remove(p)
            print("[열화상틀어짐] 기준 패턴을 지웠습니다. 다시 쌓아 굳힙니다.")
        return True
    except Exception as e:
        print(f"[WARN] 열화상 기준 패턴을 지우지 못했습니다: {e}")
        return False


def _corr(a, b):
    """두 배열의 피어슨 상관계수. 한쪽이라도 변화가 없으면 None."""
    a = a.reshape(-1)
    b = b.reshape(-1)
    if a.size < MIN_OVERLAP:
        return None
    a = a - a.mean()
    b = b - b.mean()
    da = float(np.sqrt((a * a).sum()))
    db = float(np.sqrt((b * b).sum()))
    if da <= 0.0 or db <= 0.0:
        return None
    return float((a * b).sum() / (da * db))


def estimate(cur, ref, x_grid, y_grid, max_shift=MAX_SHIFT):
    """
    현재 열화상 격자가 기준 패턴에서 몇 칸 밀렸는지 본다.

    cur, ref : 길이 x_grid*y_grid 의 셀 온도 (행 우선)

    돌려주는 값은 dict 이며, 잴 수 없으면 None.
        dx, dy   : 화면이 오른쪽/아래로 밀린 칸 수
        corr     : 그 자리에서의 상관계수
        corr0    : 제자리(0,0)에서의 상관계수
        shifted  : 이동으로 볼 만한가
    """
    cur = np.asarray(cur, dtype=np.float64).reshape(-1)
    ref = np.asarray(ref, dtype=np.float64).reshape(-1)

    n = x_grid * y_grid
    if cur.size != n or ref.size != n:
        return None
    if not np.all(np.isfinite(cur)) or not np.all(np.isfinite(ref)):
        return None

    # 밋밋한 화면에서는 판정하지 않는다.
    if float(ref.std()) < MIN_PATTERN_STD or float(cur.std()) < MIN_PATTERN_STD:
        return None

    R = ref.reshape(y_grid, x_grid)
    C = cur.reshape(y_grid, x_grid)

    best = None
    corr0 = None

    for dy in range(-max_shift, max_shift + 1):
        for dx in range(-max_shift, max_shift + 1):
            # 화면이 (dx, dy) 만큼 밀렸다면, 기준에서 (r, c) 에 있던 것이
            # 지금은 (r+dy, c+dx) 에 있다. 그 겹치는 부분만 견준다.
            r0, r1 = max(0, dy), min(y_grid, y_grid + dy)
            c0, c1 = max(0, dx), min(x_grid, x_grid + dx)
            if (r1 - r0) * (c1 - c0) < MIN_OVERLAP:
                continue

            sub_c = C[r0:r1, c0:c1]
            sub_r = R[r0 - dy:r1 - dy, c0 - dx:c1 - dx]

            v = _corr(sub_r, sub_c)
            if v is None:
                continue

            if dx == 0 and dy == 0:
                corr0 = v
            if best is None or v > best[2]:
                best = (dx, dy, v)

    if best is None or corr0 is None:
        return None

    dx, dy, corr = best
    shifted = (
        (dx != 0 or dy != 0)
        and corr >= MIN_CORR
        and (corr - corr0) >= CORR_GAIN
    )

    # 밀린 자리를 못 찾았는데 제자리도 안 맞으면, 방향은 몰라도 화면이
    # 달라진 것은 맞다.
    mismatch = (not shifted) and corr0 < MIN_MATCH

    return {"dx": int(dx), "dy": int(dy), "corr": corr,
            "corr0": corr0, "shifted": bool(shifted),
            "mismatch": bool(mismatch)}


def describe(res):
    """사람이 읽을 한 줄."""
    if res is None:
        return "열화상 틀어짐 : 판정 불가"
    if res["shifted"]:
        return (f"열화상 틀어짐 : 가로 {res['dx']:+d}칸 · 세로 {res['dy']:+d}칸 "
                f"(제자리 {res['corr0']:.3f} → {res['corr']:.3f})")
    if res["mismatch"]:
        return (f"열화상 화면 불일치 : 기준 패턴과 {res['corr0']:.3f} "
                f"(기준 {MIN_MATCH}). 밀린 방향은 특정되지 않음")
    return f"열화상 틀어짐 : 없음 (일치도 {res['corr0']:.3f})"


class ThermalShiftWatch:
    """
    기준 패턴을 굳히고, 주기적으로 다시 재는 일을 한군데 모은다.

    호출하는 쪽은 매 프레임 check() 를 부르기만 하면 된다. 아직 잴 때가
    아니면 직전 결과를 그대로 돌려준다.
    """

    def __init__(self, user_path, x_grid, y_grid,
                 interval=RECHECK_INTERVAL, min_ref_samples=MIN_REF_SAMPLES):
        self.user_path = user_path
        self.x_grid = int(x_grid)
        self.y_grid = int(y_grid)
        self.n_cells = self.x_grid * self.y_grid
        self.interval = float(interval)
        self.min_ref_samples = int(min_ref_samples)

        self.ref = load_ref(user_path, self.n_cells)
        self.result = None
        self.checked_at = ""     # 사람이 읽을 시각 문자열
        self._last_t = 0.0       # 0 이면 첫 프레임에서 바로 한 번 잰다

        # 한 프레임만 보고 판정하면 결과가 춤춘다. kict1 의 07-04 를
        # 프레임 단위로 돌려 보면 정상 46% · 밀림 29% · 불일치 23% 로
        # 갈렸는데, 같은 날 평균으로는 깨끗하게 "없음" 이 나왔다. 설비가
        # 켜지고 꺼지는 순간이 섞이기 때문이다.
        #
        # 이 판정은 학습을 멈출지까지 정한다. 춤추는 신호로 학습을 껐다
        # 켰다 할 수는 없다. 검사 간격 동안 들어온 프레임을 모아 평균으로
        # 본다.
        self._acc = np.zeros(self.n_cells, dtype=np.float64)
        self._acc_n = 0

        if self.ref is None:
            print(f"[열화상틀어짐] 기준 패턴 없음 — 표본 {self.min_ref_samples}건이 "
                  f"쌓이면 굳힙니다.")
        else:
            print("[열화상틀어짐] 기준 패턴을 읽었습니다.")

    @property
    def has_ref(self):
        return self.ref is not None

    def check(self, cur, baseline, now_t, now_str):
        """
        cur      : 이번 프레임의 64셀 온도
        baseline : OnlineBaseline (기준 패턴을 뜰 곳)
        now_t    : time.time()
        now_str  : 화면에 적을 시각 문자열

        돌려주는 값은 estimate() 의 dict 또는 None.
        """
        # 아직 기준이 없으면, 충분히 쌓였을 때 한 번 굳힌다. 모으기보다
        # 먼저 본다. 기준이 없는 동안 모아 둔 프레임은 견줄 상대가 없어
        # 쓸모가 없고, 굳힌 직후에 그 한 장으로 판정해 버리면 평균을 쓰는
        # 뜻이 사라진다.
        if self.ref is None:
            if baseline.count < self.min_ref_samples:
                return None
            pattern = np.asarray(baseline.mean, dtype=np.float64).reshape(-1)
            if pattern.size != self.n_cells:
                return None
            if float(pattern.std()) < MIN_PATTERN_STD:
                # 패턴이 밋밋하면 굳혀 봐야 쓸모가 없다. 다음 기회를 본다.
                return None
            if not save_ref(self.user_path, pattern):
                return None
            self.ref = pattern
            self._last_t = now_t       # 여기서부터 한 주기를 모은다
            print(f"[열화상틀어짐] 표본 {baseline.count}건으로 기준 패턴을 "
                  f"굳혔습니다.")
            return None

        # 들어온 프레임을 모은다. 판정할 때가 되면 이 평균을 쓴다.
        x = np.asarray(cur, dtype=np.float64).reshape(-1)
        if x.size == self.n_cells and np.all(np.isfinite(x)):
            self._acc += x
            self._acc_n += 1

        if self._last_t and (now_t - self._last_t) < self.interval:
            return self.result

        if self._acc_n <= 0:
            return self.result

        avg = self._acc / self._acc_n
        n_used = self._acc_n
        self._acc[:] = 0.0
        self._acc_n = 0

        self._last_t = now_t
        res = estimate(avg, self.ref, self.x_grid, self.y_grid)

        if res is not None:
            self.result = res
            self.checked_at = now_str
            if res["shifted"] or res["mismatch"]:
                print(f"[열화상틀어짐] {describe(res)} — 최근 {n_used}프레임 "
                      f"평균. 카메라 조준을 확인하십시오.")

        return self.result

    def reset(self):
        """이동보정을 승인했을 때. 기준을 버리고 처음부터 다시 굳힌다."""
        clear_ref(self.user_path)
        self.ref = None
        self.result = None
        self.checked_at = ""
        self._last_t = 0.0
        self._acc[:] = 0.0
        self._acc_n = 0
