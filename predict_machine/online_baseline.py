# -*- coding: utf-8 -*-
"""
셀별 온라인 기준선 (연속 학습 2단계)

오토인코더는 수 주간의 데이터가 쌓여야 만들 수 있다. 그 전까지 현장이
무방비로 남는 문제를 없애기 위해, 설치 직후부터 셀마다 정상 범위를 누적해
두고 그 범위를 얼마나 벗어났는지로 채점한다.

과거 데이터를 보관하지 않고 매 프레임 O(64) 연산으로 끝나며, 상태는 npz
한 개로 저장되어 프로그램을 껐다 켜도 이어진다.


[왜 z-score 가 아니라 분위수인가]

처음에는 평균·표준편차로 z-score 를 냈는데, 실제 kict1 데이터로 시험해
보니 정상 프레임 0.686 / 카메라 이동 프레임 0.677 로 거의 구분이 되지
않았다. 두 가지 이유였다.

첫째, 설비 데이터는 가동/정지로 분포가 둘로 갈린다. 이런 데이터에서
표준편차는 두 봉우리 사이 거리까지 삼켜 크게 부풀고, 그만큼 둔감해진다.

둘째, 16개 셀 중 최대값을 쓰면 정상 프레임에서도 최대 z 가 2 안팎까지
예사로 올라간다. 표본을 여럿 뽑으면 그중 하나쯤은 튀기 때문이다. 그래서
정상인데도 점수가 0.7 밖에 안 나왔다.

지금은 "이 셀이 평소보다 몇 표준편차 위인가" 대신 **"이 셀이 지금까지
이렇게 뜨거운 적이 있었는가"** 를 본다. 셀마다 상위 분위수를 구해 두고,
그 선을 넘은 만큼만 점수를 깎는다. 분포가 둘로 갈려 있어도 상관없고,
넘지 않으면 점수가 1.0 이라 정상일 때 깨끗하다.


[왜 히스토그램인가]

분위수를 확률적 경사하강(pinball loss)으로 추정해 봤더니 폭주했다.
상위 0.999 분위수는 올라갈 때 보폭의 0.999배, 내려올 때 0.001배로
움직인다. 초반에 값이 한 번 크게 튀어 선이 올라가면, 1도 내려오는 데
표본 1,000건이 필요하다. 8,000건을 넣어도 회복이 안 돼 사실상 최대값
추적이 되어 버렸다 (어떤 셀은 199도로 고정, 데이터 최대가 197도).

격자 온도는 0~255 정수로 제한되어 있다(utils.Conv_LWIR_to_64_Vector 가
범위를 벗어나면 프레임을 버린다). 그래서 셀마다 256칸 히스토그램을
두면 **근사가 아니라 정확한 분위수**를 얻는다. 메모리는 64셀 × 256칸 ×
4바이트 = 64KB 로 무시할 수준이고, 갱신은 O(1), 수렴 문제도 없다.

덤으로 "이 온도 이상이었던 적이 전체의 몇 %" 를 그대로 읽을 수 있어
판정 근거를 사람이 확인하기 쉽다.


[이 방식의 한계]

마스크 안의 셀 하나하나만 본다. "13번은 뜨거운데 29번은 차다" 처럼 각
셀은 정상 범위인데 조합이 이상한 경우는 잡지 못한다. 그건 셀 간 결합
분포를 배우는 오토인코더(3단계)의 몫이다. 이 기준선은 오토인코더를
대체하는 것이 아니라, 준비되기 전까지의 발판이다.

마스크 밖의 셀도 보지 못한다. 그래서 화면 전체가 밀리는 카메라 이동은
scene_shift() 로 따로 감시한다.


[안전 규칙] 이상으로 판정된 프레임은 update() 에 넣지 않는다. 넣으면
서서히 커지는 열점을 기준선이 "요즘의 정상" 으로 흡수해 버려, 정작 위험할
때 아무 경보도 나오지 않는다. 호출부에서 반드시 걸러서 넣어야 한다.
"""

import os
import numpy as np

# 기준선이 의미를 가지려면 최소한 이 정도 표본은 모여야 한다.
MIN_SAMPLES = 3000

# 표본 수만으로는 부족하다. 어느 하루 오후 데이터만 5만 건 모아 봐야
# 기준선은 그 시간대만 정상으로 안다. 하루의 몇 개 시간대를 보았는지까지
# 조건으로 걸어, 주야 변화를 한 바퀴 본 뒤에 활성화한다.
MIN_HOURS_COVERED = 18

# 셀별 상위 분위수. 0.999 면 "천 번에 한 번 있을까 말까 한 온도".
HI_QUANTILE = 0.999

# 격자 온도의 유효 범위 (utils.Conv_LWIR_to_64_Vector 와 동일 기준)
TEMP_BINS = 256

# 히스토그램에서 분위수를 다시 계산하는 주기. 매 프레임 계산할 필요가 없다.
HI_REFRESH_EVERY = 500

# 분위수 선을 넘은 정도를 점수로 바꿀 때의 기준. 섭씨 몇 도를 1.0 으로
# 볼 것인가.
#
# 처음에는 셀의 표준편차로 나눴는데, 가동/정지로 분포가 갈린 셀은 표준편차가
# 크게 부풀어 80도를 넘겨도 0.32배로밖에 잡히지 않았다. 도 단위로 고정하는
# 편이 민감도가 일정하고 사람이 읽기도 쉽다.
EXCEED_SCALE_C = 10.0

# 넘지 않으면 1.0, 20도 넘으면 0.33 근처가 된다.
EXCEED_DECAY = 0.55

# 표준편차가 0 에 가까운 셀(항상 같은 값)에서 발산하는 것을 막는다.
MIN_STD = 1.0

# 화면 이동 감시용 EWMA 계수. 가동/정지 주기를 평균으로 지우기 위해
# 수 시간 규모로 느리게 움직인다.
SCENE_EWMA_ALPHA = 0.001

# 이 상관계수 아래로 떨어지면 화면이 밀린 것으로 본다.
#
# kict1 실측: 카메라 그대로면 0.9998~1.0000 로 붙어 있고, 실제 있었던
# 이동량(위1칸·오른3칸)을 모사하면 500프레임 만에 0.88, 2,000프레임에
# 0.57 까지 떨어진다. 두 영역이 확실히 갈려 0.95 면 오경보 없이 잡힌다.
SCENE_SHIFT_MIN = 0.95

# 고리 버퍼가 들고 있을 수 있는 최대 프레임 수.
#
# 창은 최소 표본수와 최소 시간대를 채우는 만큼만 자란다(아래 _evict 참고).
# 여기 상한은 설비가 멈춰 같은 시각만 들어오는 것처럼, 시간대가 영영 안
# 차는 경우에 메모리가 무한정 늘지 않게 하는 마지막 그물이다.
# 5만 x 64 = 3.2 MB (칸마다 1바이트). kict1 5초 주기로 약 2.9일치다.
MAX_WINDOW = 50000

# 왜 처음부터 다시 쌓고 있는지를 적어 두는 쪽지.
#
# 기준선 파일 옆에 둔다. 되돌리기는 기준선 파일을 아예 옮겨 버리므로,
# 사유를 기준선 안에 적어 두면 함께 사라진다. 따로 남겨야 다음에 올라올
# 때 "되돌리기로 치웠다" 와 "설치 직후다" 를 가릴 수 있다.
RESET_NOTE = "baseline_reset.ini"


def write_reset_note(user_path, why, at=None):
    """기준선을 치운 쪽에서 사유를 남긴다. 실패해도 조용히 넘어간다."""
    import datetime as _dt

    stamp = at or _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(os.path.join(user_path, RESET_NOTE), "w",
                  encoding="utf-8") as f:
            f.write("[RESET]\n")
            f.write(f"AT = {stamp}\n")
            f.write(f"WHY = {why}\n")
    except OSError:
        pass


def read_reset_note(user_path):
    """(사유, 시각). 쪽지가 없으면 빈 값 둘."""
    p = os.path.join(user_path, RESET_NOTE)
    if not os.path.exists(p):
        return "", ""
    why = at = ""
    try:
        with open(p, encoding="utf-8") as f:
            for line in f:
                k, _, v = line.partition("=")
                k = k.strip().upper()
                if k == "WHY":
                    why = v.strip()
                elif k == "AT":
                    at = v.strip()
    except OSError:
        return "", ""
    return why, at


def _day_num(day):
    """'2026-09-27' -> 20260927. 못 읽으면 0(모름)."""
    if not day:
        return 0
    t = str(day).replace("-", "").strip()
    if len(t) != 8 or not t.isdigit():
        return 0
    return int(t)


def _day_str(num):
    """20260927 -> '2026-09-27'. 0 이면 빈 문자열."""
    n = int(num or 0)
    if n < 10000101:
        return ""
    return f"{n // 10000:04d}-{n // 100 % 100:02d}-{n % 100:02d}"


class OnlineBaseline:
    """셀별 정상 범위를 누적하고 초과 정도로 채점한다."""

    def __init__(self, n_cells, min_samples=None, min_hours=None, base_date=None):
        # 전환 조건은 현장마다 다르다. kict1 은 5초, cj_busan_1 은 30초 주기라
        # 같은 표본 수를 모으는 데 걸리는 시간이 6배 차이난다. 그래서 코드에
        # 박지 않고 env.ini 에서 받는다 (모니터링 프로그램의 [설정] 창).
        self.min_samples = int(min_samples) if min_samples else MIN_SAMPLES
        self.min_hours = int(min_hours) if min_hours else MIN_HOURS_COVERED

        # 계산 기준일은 2단계에서 쓰지 않는다.
        #
        # 기준선이 누적이던 때는 잊는 수단이 이것뿐이었다 - 날짜를 바꾸면
        # 쌓은 것을 버리고 처음부터 다시 쌓았다. 고리 버퍼로 바뀌면서 창이
        # 스스로 최근 것만 들고 있으므로 지시할 이유가 없어졌다. 오히려
        # 값을 바꿀 때마다 멀쩡한 최근 창을 버려 2단계가 꺼졌다.
        #
        # 인자는 남겨 둔다. 부르는 쪽(predict_machine)이 넘기고 있고, 저장
        # 파일에도 적혀 있어 갑자기 빼면 옛 파일과 어긋난다. 받아서 적어만
        # 둘 뿐 판단에 쓰지 않는다. 3단계(재학습 표본)에서는 그대로 쓴다.
        self.base_date = (str(base_date).strip() if base_date else "")

        self.n_cells = int(n_cells)

        # ---- 최근 창(고리 버퍼) ----
        #
        # 예전에는 Welford 로 기준일 이후 전부를 평균에 담았다. count 가
        # 커질수록 새 프레임의 몫이 1/count 로 줄어, 10만 건이 쌓이면 새 값
        # 하나가 평균을 10만분의 1 움직인다. 시간이 갈수록 굳어서 계절이나
        # 설비 변화를 못 따라간다. 잊는 방법이 '기준일을 바꿔 통째로 버리기'
        # 하나뿐이었다.
        #
        # 프레임마다 값 자체가 아니라 히스토그램 칸 번호(0~255)를 들고 있다.
        # 채점에 쓰는 것은 분위수 선(hi)이고 그것은 히스토그램에서 나오므로,
        # 나가는 프레임의 칸을 -1 하고 들어오는 칸을 +1 하면 창이 그대로
        # 유지된다. 칸마다 1바이트라 18시간치(kict1 약 13,000건)가 830KB다.
        #
        # 합은 정수의 합이라 부동소수 오차가 쌓이지 않는다. 다시 계산해
        # 바로잡을 필요가 없다.
        self.ring = np.zeros((0, self.n_cells), dtype=np.uint8)
        self.ring_hour = np.zeros(0, dtype=np.int8)
        # 프레임마다의 날짜(YYYYMMDD). 0 은 모름(날짜 없이 올라온 옛 파일).
        #
        # started_at 은 처음 넣은 날에 박혀 다시 바뀌지 않는다. 창은 오래된
        # 것부터 밀어내므로 그 값은 금세 창의 내용보다 길어진다. 창이 실제로
        # 들고 있는 기간을 말하려면 프레임마다 날짜를 들고 있어야 한다.
        self.ring_day = np.zeros(0, dtype=np.int32)
        self._n = 0            # 창에 든 프레임 수
        self._head = 0         # 다음에 쓸 자리
        # 지나간 프레임 수. 창은 고정되므로 갱신 주기는 이것으로 잰다.
        self._seen = 0
        self.s1 = np.zeros(self.n_cells, dtype=np.float64)   # 칸 번호의 합
        self.s2 = np.zeros(self.n_cells, dtype=np.float64)   # 제곱의 합
        self.hour_cnt = np.zeros(24, dtype=np.int64)

        # 셀별 온도 히스토그램. 여기서 분위수를 정확히 뽑는다.
        self.hist = np.zeros((self.n_cells, TEMP_BINS), dtype=np.uint32)
        # 히스토그램에서 계산해 둔 분위수 선 (캐시)
        self._hi = np.full(self.n_cells, float(TEMP_BINS - 1), dtype=np.float64)
        self._hi_at = -1

        # ---- 옛 파일에서 읽은 누적값 ----
        #
        # 옛 기준선 파일에는 프레임이 남아 있지 않아 창을 복원할 수 없다.
        # 그대로 버리면 창이 찰 때까지(cj_busan_1 은 하루 넘게) 2단계가 꺼진다.
        # 창이 스스로 설 때까지는 옛 값으로 계속 채점한다.
        self._legacy = None

        # 처음 누적한 날짜(YYYY-MM-DD).
        #
        # 계산 기준일이 바뀌었을 때 정말 버려야 하는지 가리는 데 쓴다.
        # 쌓기 시작한 날이 이미 새 기준일 이후라면 뺄 과거가 없으므로
        # 그대로 이어간다. 화면에도 "언제부터 쌓은 값인지" 를 보여준다.
        self.started_at = ""
        # 최근 프레임의 느린 평균. 화면 이동 감시용.
        self.scene_ewma = np.zeros(self.n_cells, dtype=np.float64)

        # 지금 쌓고 있는 것이 왜 처음부터인가. (사유, 시각) 또는 빈 값.
        #
        # 2단계가 "누적 중" 으로 멈춰 있을 때 사람이 가장 먼저 묻는 것이
        # "왜 처음부터 다시 쌓고 있나" 다. 되돌리기로 치운 것인지, 파일이
        # 깨진 것인지, 그냥 설치 직후인지에 따라 할 일이 전혀 다르다.
        self.reset_why = ""
        self.reset_at = ""

    # ------------------------------------------------------------------ 누적

    def update(self, x, hour=None, accum=True, day=None):
        """
        프레임 하나를 반영한다.

        accum=False 면 화면 이동 감시용 EWMA 만 움직이고 기준선(평균·분산·
        히스토그램)은 건드리지 않는다. 카메라가 밀린 것으로 보일 때 쓴다.

        EWMA 를 계속 움직이는 이유: 여기서 멈추면 상관계수가 낮은 채로
        굳어 버려, 나중에 조준을 원위치로 되돌려도 경보가 풀리지 않는다.
        EWMA 만 따라가게 두면 복구 시 상관계수가 자연히 회복된다.

        day 는 이 프레임의 날짜(YYYY-MM-DD). 계산 기준일보다 이르면
        누적하지 않는다. 기준일을 앞날로 잡아 두면 그날이 올 때까지
        기다렸다가 쌓기 시작한다.
        """
        x = np.asarray(x, dtype=np.float64).reshape(-1)

        if x.size != self.n_cells or not np.all(np.isfinite(x)):
            return False

        first = self.count == 0

        if first:
            self.scene_ewma = x.copy()
        else:
            self.scene_ewma += SCENE_EWMA_ALPHA * (x - self.scene_ewma)

        if not accum:
            return False

        bins = np.clip(np.rint(x), 0, TEMP_BINS - 1).astype(np.uint8)
        self._push(bins, -1 if hour is None else int(hour), _day_num(day))

        if not self.started_at and day:
            self.started_at = str(day)

        return True

    # ---- 고리 버퍼 ----

    def _grow(self):
        """자리가 모자라면 넓힌다. 창 크기는 스스로 정해진다."""
        cap = self.ring.shape[0]
        new_cap = min(MAX_WINDOW, max(int(self.min_samples), cap * 2, 1024))
        if new_cap <= cap:
            return False
        # 오래된 것부터 차례로 펴서 옮긴다. 자주 있는 일이 아니다.
        order = [(self._head + i) % cap for i in range(self._n)] if cap else []
        ring = np.zeros((new_cap, self.n_cells), dtype=np.uint8)
        hours = np.zeros(new_cap, dtype=np.int8)
        days = np.zeros(new_cap, dtype=np.int32)
        for i, k in enumerate(order):
            ring[i] = self.ring[k]
            hours[i] = self.ring_hour[k]
            days[i] = self.ring_day[k]
        self.ring, self.ring_hour, self.ring_day = ring, hours, days
        self._head = self._n
        return True

    @property
    def window_from(self):
        """창에 남아 있는 가장 오래된 날 (YYYY-MM-DD). 모르면 빈 문자열."""
        return _day_str(self._day_edge(min))

    @property
    def window_to(self):
        """창에 남아 있는 가장 최근 날."""
        return _day_str(self._day_edge(max))

    def _day_edge(self, pick):
        if self._n <= 0 or self.ring_day.size == 0:
            return 0
        cap = self.ring.shape[0]
        tail = (self._head - self._n) % cap
        if tail + self._n <= cap:
            seg = self.ring_day[tail:tail + self._n]
        else:
            seg = np.concatenate(
                (self.ring_day[tail:], self.ring_day[:self._head]))
        seg = seg[seg > 0]
        if seg.size == 0:
            return 0
        return int(pick(seg))

    def _can_evict(self):
        """
        가장 오래된 것을 버려도 두 조건이 남는가.

        건수만으로 창을 잡으면 안 된다. kict1 은 5초 주기라 3,000건이
        4.2시간뿐이고, 18시간대 조건을 영영 못 채운다. 두 조건을 채우는
        동안은 버리지 않고 창을 늘린다.

        처음에는 '그 시각에 다른 프레임이 남아 있으면 버려도 된다' 로
        두었는데, 그러면 시간대가 4개뿐이어도 계속 버려 창이 최소 표본수에서
        자라지 못했다. 고치려던 문제가 그대로 남았다.
        """
        if self._n <= self.min_samples:
            return False

        tail = (self._head - self._n) % self.ring.shape[0]
        h = int(self.ring_hour[tail])
        cov = int((self.hour_cnt > 0).sum())
        if 0 <= h and self.hour_cnt[h] == 1:
            cov -= 1                         # 이 프레임이 그 시각의 마지막
        return cov >= self.min_hours

    def _pop_oldest(self):
        cap = self.ring.shape[0]
        tail = (self._head - self._n) % cap
        old = self.ring[tail].astype(np.intp)
        self.hist[np.arange(self.n_cells), old] -= 1
        self.s1 -= old
        self.s2 -= old.astype(np.float64) ** 2
        h = int(self.ring_hour[tail])
        if h >= 0:
            self.hour_cnt[h] -= 1
        self._n -= 1

    def _push(self, bins, hour, day=0):
        while self._n >= self.ring.shape[0]:
            if self._can_evict():
                self._pop_oldest()
            elif not self._grow():
                self._pop_oldest()          # 상한까지 찼다. 오래된 것을 버린다
        # 창이 넉넉해도 조건을 넘는 만큼은 계속 버린다
        while self._can_evict():
            self._pop_oldest()

        cap = self.ring.shape[0]
        self.ring[self._head] = bins
        self.ring_hour[self._head] = hour
        self.ring_day[self._head] = day
        idx = bins.astype(np.intp)
        self.hist[np.arange(self.n_cells), idx] += 1
        self.s1 += idx
        self.s2 += idx.astype(np.float64) ** 2
        if hour >= 0:
            self.hour_cnt[hour] += 1
        self._head = (self._head + 1) % cap
        self._n += 1
        self._seen += 1

    # ------------------------------------------------------------------ 상태

    def _use_legacy(self):
        """
        지금 옛 누적값으로 채점하는가.

        건수·평균·시간대·히스토그램이 반드시 같은 곳을 봐야 한다. 분위수
        선은 0.999 * count 를 히스토그램 누적합에 대어 찾으므로, 둘이
        어긋나면 선이 엉뚱한 자리에 잡힌다. 창 500건과 옛 9,999건을 섞으면
        5퍼센타일쯤에 선이 서고 정상 온도가 전부 초과로 보인다.
        """
        return bool(self._legacy) and not self._ring_ready()

    @property
    def count(self):
        """채점에 쓰는 프레임 수."""
        if self._use_legacy():
            return int(self._legacy["count"])
        return self._n

    @property
    def window(self):
        """지금 창에 든 프레임 수 (옛 값과 섞이지 않는 순수한 값)."""
        return self._n

    @property
    def mean(self):
        if self._use_legacy():
            return self._legacy["mean"]
        if self._n == 0:
            return np.zeros(self.n_cells, dtype=np.float64)
        return self.s1 / self._n

    @property
    def std(self):
        if self._n < 2:
            return np.full(self.n_cells, MIN_STD, dtype=np.float64)
        var = (self.s2 - self.s1 ** 2 / self._n) / (self._n - 1)
        return np.maximum(np.sqrt(np.maximum(var, 0.0)), MIN_STD)

    @property
    def hi(self):
        """
        셀별 상위 분위수 선. 히스토그램 누적합에서 정확히 구한다.

        매 프레임 계산할 필요가 없으므로 HI_REFRESH_EVERY 건마다 갱신한다.
        """
        # 창이 고정되면 count 가 더 이상 늘지 않는다. 지나간 프레임 수로
        # 잰다. 이걸 count 로 두었다가, 현장이 30도에서 70도로 바뀌어도
        # 분위수 선이 옛 값에 머무는 것을 시험에서 잡았다.
        if self._hi_at < 0 or self._seen - self._hi_at >= HI_REFRESH_EVERY:
            self._recompute_hi()
        return self._hi

    def _recompute_hi(self):
        if self.count <= 0:
            return
        hist = self._hist_for_scoring()
        target = HI_QUANTILE * self.count
        cum = np.cumsum(hist, axis=1)
        # 누적도수가 target 을 처음 넘는 칸 = 그 분위수의 온도
        idx = np.argmax(cum >= target, axis=1)
        self._hi = idx.astype(np.float64)
        self._hi_at = self._seen

    def exceed_ratio(self, cell, temp):
        """해당 셀에서 이 온도 이상이었던 표본의 비율. 판정 근거 확인용."""
        if self.count <= 0:
            return None
        hist = self._hist_for_scoring()
        b = int(np.clip(round(temp), 0, TEMP_BINS - 1))
        return float(hist[int(cell), b:].sum()) / self.count

    @property
    def hours_covered(self):
        if self._use_legacy():
            return bin(int(self._legacy["hours_seen"])).count("1")
        return int((self.hour_cnt > 0).sum())

    def _hist_for_scoring(self):
        """
        채점에 쓸 히스토그램.

        창이 서면 창의 것, 아직이면 옛 누적값. 옛 값도 없으면 창의 것을
        그대로 쓴다 - 비어 있을 뿐 None 은 아니다. 이 마지막 갈래를
        빠뜨려 kict1 이 기준선을 읽다 죽었다.
        """
        return self._legacy["hist"] if self._use_legacy() else self.hist

    def _ring_ready(self):
        """창만으로 채점할 수 있는가."""
        return (self._n >= self.min_samples
                and int((self.hour_cnt > 0).sum()) >= self.min_hours)

    def is_ready(self):
        """채점에 쓸 만큼 모였는지. 창이 아직이면 옛 누적값으로 본다."""
        if self._ring_ready():
            return True
        if self._legacy:
            return (int(self._legacy["count"]) >= self.min_samples
                    and bin(int(self._legacy["hours_seen"])).count("1")
                    >= self.min_hours)
        return False

    # ------------------------------------------------------------------ 채점

    def score(self, x, mask):
        """
        마스크 셀 중 정상 범위를 가장 크게 벗어난 정도로 채점한다.

        평균이 아니라 최대를 쓰는 이유: 화재는 한 지점에서 시작한다.
        16셀 평균을 쓰면 한 셀이 크게 뜨거워져도 나머지에 희석되어 묻힌다.

        반환: (score, exceed_c, worst_cell)
          exceed_c 는 분위수 선을 섭씨 몇 도 넘었는지. 0 이하면 정상 범위.
        """
        x = np.asarray(x, dtype=np.float64).reshape(-1)
        sel = np.asarray(mask, dtype=np.int32).reshape(-1) == 1

        if x.size != self.n_cells or not sel.any():
            return -1.0, -1.0, -1

        over = x - self.hi
        over_sel = over[sel]


        k = int(np.argmax(over_sel))
        exceed = float(over_sel[k])
        worst = int(np.flatnonzero(sel)[k])
        score = float(np.exp(-EXCEED_DECAY * max(0.0, exceed) / EXCEED_SCALE_C))

        return score, exceed, worst

    def suggest_temp_thresholds(self, mask):
        """
        관측된 정상 범위로부터 절대 온도 임계값을 제안한다.

        새로 설치한 현장은 설비가 몇 도까지 오르는지 알 수 없어 env.ini 에
        임계값을 적을 수가 없다. 며칠 돌려 정상 범위를 본 뒤 이 값을 참고해
        적으면 된다. 자동으로 적용하지는 않는다 — 안전 경계선은 사람이
        확인하고 정하는 것이 맞다.

        반환: (warn, alarm) 또는 표본이 모자라면 None
        """
        if not self.is_ready():
            return None

        sel = np.asarray(mask, dtype=np.int32).reshape(-1) == 1
        if not sel.any():
            return None

        # 마스크 셀이 정상 가동 중 올라간 최고 온도
        observed = float(self.hi[sel].max())
        return observed + 10.0, observed + 25.0

    def scene_shift(self):
        """
        화면이 통째로 밀렸는지 본다 (카메라 이동 감시).

        느린 EWMA 와 장기 평균의 상관계수를 돌려준다. 가동/정지 주기는
        EWMA 가 평균으로 지우므로, 설비가 켜졌다 꺼졌다 하는 것만으로는
        값이 크게 흔들리지 않는다. 카메라가 밀리면 두 패턴이 어긋나
        상관계수가 뚜렷이 떨어진다.

        마스크 안팎을 가리지 않고 64셀 전부를 본다. 마스크 밖에서 일어난
        변화가 오히려 이동의 첫 신호이기 때문이다.

        반환: 상관계수 (-1.0 ~ 1.0). 표본이 모자라면 None.
        """
        if self.count < self.min_samples:
            return None

        a = self.scene_ewma - self.scene_ewma.mean()
        b = self.mean - self.mean.mean()
        denom = np.linalg.norm(a) * np.linalg.norm(b)

        if denom < 1e-9:
            return None

        return float(np.dot(a, b) / denom)

    # ------------------------------------------------------------------ 저장

    def save(self, path):
        # np.savez 는 확장자가 .npz 가 아니면 멋대로 붙인다. 임시 이름에도
        # .npz 를 포함시켜 실제 생성 경로를 예측 가능하게 만든다.
        tmp = path + ".tmp.npz"
        # 히스토그램은 64x256 uint32 = 64KB. 압축하면 훨씬 작아진다.
        # 창을 오래된 것부터 펴서 담는다. 되읽을 때 그대로 밀어 넣으면 된다.
        cap = self.ring.shape[0]
        if self._n and cap:
            order = [(self._head - self._n + i) % cap for i in range(self._n)]
            ring = self.ring[order]
            hours = self.ring_hour[order]
            days = self.ring_day[order]
        else:
            ring = np.zeros((0, self.n_cells), dtype=np.uint8)
            hours = np.zeros(0, dtype=np.int8)

        # 옛 누적값은 제 이름으로 따로 적는다.
        #
        # 예전에는 count/mean/hist 칸에 섞어 적었다. count 는 창의 것,
        # hist 는 옛 것이 되어 되읽으면 앞뒤가 맞지 않았고, 옛 값이라는
        # 표시가 없어 복원할 수도 없었다.
        lg = self._legacy or {}
        np.savez_compressed(
            tmp,
            n_cells=self.n_cells,
            ring=ring,
            ring_hour=hours,
            ring_day=days,
            scene_ewma=self.scene_ewma,
            base_date=self.base_date,
            started_at=self.started_at,
            legacy_count=int(lg.get("count", 0)),
            legacy_mean=lg.get("mean", np.zeros(self.n_cells)),
            legacy_hist=lg.get("hist",
                               np.zeros((self.n_cells, TEMP_BINS),
                                        dtype=np.uint32)),
            legacy_hours=int(lg.get("hours_seen", 0)),
        )
        # 저장 도중 종료되어 파일이 반만 남는 것을 막는다.
        os.replace(tmp, path)

    def _hours_mask(self):
        """시각 비트마스크."""
        if self._use_legacy():
            return int(self._legacy["hours_seen"])
        m = 0
        for h in range(24):
            if self.hour_cnt[h] > 0:
                m |= (1 << h)
        return m

    @classmethod
    def load(cls, path, n_cells, min_samples=None, min_hours=None, base_date=None):
        """
        없거나 깨졌거나 격자 크기가 달라졌으면 새로 시작한다.

        계산 기준일이 달라도 그대로 이어간다. 창이 최근 것만 들고 있어
        과거를 따로 끊어 낼 이유가 없다.
        """
        obj = cls(n_cells, min_samples, min_hours, base_date)

        # 사유 쪽지는 기준선 파일과 따로 산다. 지금 쌓고 있는 것이 왜
        # 처음부터인지를 말해 주므로, 성공해서 이어받을 때도 그대로 들고
        # 간다 - 사유는 "이번 누적이 언제 왜 시작됐나" 이지 "이번에 읽다가
        # 무슨 일이 있었나" 가 아니다.
        user_path = os.path.dirname(path)
        obj.reset_why, obj.reset_at = read_reset_note(user_path)

        def fresh(why):
            o = cls(n_cells, min_samples, min_hours, base_date)
            write_reset_note(user_path, why)
            o.reset_why, o.reset_at = read_reset_note(user_path)
            return o

        if not os.path.exists(path):
            # 되돌리기가 치웠다면 그쪽이 이미 쪽지를 남겼다. 그 사유가
            # 우선이다 - 여기서 보이는 것은 "파일이 없다" 뿐이라, 왜
            # 없는지는 치운 쪽만 안다.
            if not obj.reset_why:
                return fresh("파일이 없어 처음부터 (설치 직후)")
            return obj

        try:
            d = np.load(path)

            if int(d["n_cells"]) != n_cells:
                print(f"[WARN] {path} 의 셀 수가 달라 기준선을 새로 시작합니다.")
                return fresh(f"격자 칸 수가 달라짐 "
                             f"({int(d['n_cells'])} → {n_cells})")

            saved_started = str(d["started_at"]) if "started_at" in d.files else ""

            obj.scene_ewma = d["scene_ewma"].astype(np.float64)
            obj.started_at = saved_started

            if "ring" in d.files:
                ring = d["ring"].astype(np.uint8)
                hours = d["ring_hour"].astype(np.int8)
                # 옛 파일에는 날짜가 없다. 0(모름)으로 채운다 - 창이 한 바퀴
                # 돌면 저절로 채워진다.
                if "ring_day" in d.files:
                    days = d["ring_day"].astype(np.int32)
                else:
                    days = np.zeros(ring.shape[0], dtype=np.int32)
                for i in range(ring.shape[0]):
                    obj._push(ring[i], int(hours[i]), int(days[i]))

                # 창이 아직 서지 않았으면 옛 누적값도 되살린다.
                if ("legacy_count" in d.files
                        and int(d["legacy_count"]) > 0):
                    obj._legacy = {
                        "count": int(d["legacy_count"]),
                        "mean": d["legacy_mean"].astype(np.float64),
                        "hist": d["legacy_hist"].astype(np.uint32),
                        "hours_seen": int(d["legacy_hours"]),
                    }
                print(f"[INFO] 기준선 최근 창 {obj.window:,}건 "
                      f"({obj.hours_covered}시간대)"
                      + (f" · 옛 누적값 {obj._legacy['count']:,}건 함께"
                         if obj._legacy else ""))
            else:
                # 옛 판. 프레임이 없어 창을 복원할 수 없다. 창이 스스로 설
                # 때까지 이 누적값으로 채점한다.
                obj._legacy = {
                    "count": int(d["count"]),
                    "mean": d["mean"].astype(np.float64),
                    "hist": d["hist"].astype(np.uint32),
                    "hours_seen": int(d["hours_seen"]),
                }
                print(f"[INFO] 옛 기준선({obj._legacy['count']:,}건)을 읽었습니다. "
                      f"최근 창이 찰 때까지 이 값으로 채점합니다.")
            obj._recompute_hi()

        except Exception as e:
            print(f"[WARN] 기준선을 읽지 못해 새로 시작합니다: {e}")
            return fresh(f"파일을 읽지 못함 ({type(e).__name__})")

        return obj

    def summary(self):
        # 기준일은 적지 않는다. 2단계와 무관해졌다.
        tail = ""
        if self._legacy and not self._ring_ready():
            tail = f" · 옛 누적값 사용 중(창 {self._n:,}건)" + tail
        return (f"표본 {self.count:,}/{self.min_samples:,}건 · "
                f"시간대 {self.hours_covered}/{self.min_hours} · "
                f"{'사용 가능' if self.is_ready() else '누적 중'}{tail}")
