# -*- coding: utf-8 -*-
"""
셀별 온라인 기준선 (연속 학습 1단계)

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
분포를 배우는 오토인코더(2단계)의 몫이다. 이 기준선은 오토인코더를
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


class OnlineBaseline:
    """셀별 정상 범위를 누적하고 초과 정도로 채점한다."""

    def __init__(self, n_cells, min_samples=None, min_hours=None, base_date=None):
        # 전환 조건은 현장마다 다르다. kict1 은 5초, cj_busan_1 은 30초 주기라
        # 같은 표본 수를 모으는 데 걸리는 시간이 6배 차이난다. 그래서 코드에
        # 박지 않고 env.ini 에서 받는다 (모니터링 프로그램의 [설정] 창).
        self.min_samples = int(min_samples) if min_samples else MIN_SAMPLES
        self.min_hours = int(min_hours) if min_hours else MIN_HOURS_COVERED

        # 계산 기준일 (YYYY-MM-DD). 이 날짜 이전 프레임은 누적하지 않는다.
        #
        # 히스토그램에는 표본별 시각이 남지 않으므로 과거 구간만 골라 빼낼 수
        # 없다. 그래서 기준일이 바뀌면 누적을 버리고 처음부터 다시 쌓는다.
        # 카메라를 옮겼거나 설비를 바꾼 뒤 "그 전에 배운 것은 잊으라" 고
        # 지시하는 수단이다. 빈 값이면 제한 없이 계속 쌓는다.
        self.base_date = (str(base_date).strip() if base_date else "")

        self.n_cells = int(n_cells)
        self.count = 0
        self.mean = np.zeros(self.n_cells, dtype=np.float64)
        self.m2 = np.zeros(self.n_cells, dtype=np.float64)
        # 셀별 온도 히스토그램. 여기서 분위수를 정확히 뽑는다.
        self.hist = np.zeros((self.n_cells, TEMP_BINS), dtype=np.uint32)
        # 히스토그램에서 계산해 둔 분위수 선 (캐시)
        self._hi = np.full(self.n_cells, float(TEMP_BINS - 1), dtype=np.float64)
        self._hi_at = -1
        # 관측한 시각(0~23) 비트마스크. 커버리지 판정용.
        self.hours_seen = 0
        # 최근 프레임의 느린 평균. 화면 이동 감시용.
        self.scene_ewma = np.zeros(self.n_cells, dtype=np.float64)

    # ------------------------------------------------------------------ 누적

    def update(self, x, hour=None, learn=True, day=None):
        """
        프레임 하나를 반영한다.

        learn=False 면 화면 이동 감시용 EWMA 만 움직이고 기준선(평균·분산·
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

        if not learn:
            return False

        if self.base_date and day and str(day) < self.base_date:
            return False

        # 평균·분산 (Welford)
        self.count += 1
        delta = x - self.mean
        self.mean += delta / self.count
        self.m2 += delta * (x - self.mean)

        # 셀별 온도 히스토그램
        bins = np.clip(np.rint(x), 0, TEMP_BINS - 1).astype(np.intp)
        self.hist[np.arange(self.n_cells), bins] += 1

        if hour is not None:
            self.hours_seen |= (1 << int(hour))

        return True

    # ------------------------------------------------------------------ 상태

    @property
    def std(self):
        if self.count < 2:
            return np.full(self.n_cells, MIN_STD, dtype=np.float64)
        return np.maximum(np.sqrt(self.m2 / (self.count - 1)), MIN_STD)

    @property
    def hi(self):
        """
        셀별 상위 분위수 선. 히스토그램 누적합에서 정확히 구한다.

        매 프레임 계산할 필요가 없으므로 HI_REFRESH_EVERY 건마다 갱신한다.
        """
        if self.count != self._hi_at and (
                self._hi_at < 0
                or self.count - self._hi_at >= HI_REFRESH_EVERY):
            self._recompute_hi()
        return self._hi

    def _recompute_hi(self):
        if self.count <= 0:
            return
        target = HI_QUANTILE * self.count
        cum = np.cumsum(self.hist, axis=1)
        # 누적도수가 target 을 처음 넘는 칸 = 그 분위수의 온도
        idx = np.argmax(cum >= target, axis=1)
        self._hi = idx.astype(np.float64)
        self._hi_at = self.count

    def exceed_ratio(self, cell, temp):
        """해당 셀에서 이 온도 이상이었던 표본의 비율. 판정 근거 확인용."""
        if self.count <= 0:
            return None
        b = int(np.clip(round(temp), 0, TEMP_BINS - 1))
        return float(self.hist[int(cell), b:].sum()) / self.count

    @property
    def hours_covered(self):
        return bin(self.hours_seen).count("1")

    def is_ready(self):
        """채점에 쓸 만큼 모였는지."""
        return (self.count >= self.min_samples
                and self.hours_covered >= self.min_hours)

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
        np.savez_compressed(
            tmp,
            n_cells=self.n_cells,
            count=self.count,
            mean=self.mean,
            m2=self.m2,
            hist=self.hist,
            hours_seen=self.hours_seen,
            scene_ewma=self.scene_ewma,
            base_date=self.base_date,
        )
        # 저장 도중 종료되어 파일이 반만 남는 것을 막는다.
        os.replace(tmp, path)

    @classmethod
    def load(cls, path, n_cells, min_samples=None, min_hours=None, base_date=None):
        """
        없거나 깨졌거나 격자 크기가 달라졌으면 새로 시작한다.

        계산 기준일이 저장된 것과 다를 때도 새로 시작한다. 기준일을 바꾸는
        것은 "그 전에 배운 것은 잊으라" 는 지시이기 때문이다.
        """
        obj = cls(n_cells, min_samples, min_hours, base_date)

        if not os.path.exists(path):
            return obj

        try:
            d = np.load(path)

            if int(d["n_cells"]) != n_cells:
                print(f"[WARN] {path} 의 셀 수가 달라 기준선을 새로 시작합니다.")
                return obj

            saved_base = str(d["base_date"]) if "base_date" in d.files else ""
            if saved_base != obj.base_date:
                print(f"[INFO] 계산 기준일이 바뀌어("
                      f"{saved_base or '없음'} -> {obj.base_date or '없음'}) "
                      f"기준선을 새로 시작합니다.")
                return obj

            obj.count = int(d["count"])
            obj.mean = d["mean"].astype(np.float64)
            obj.m2 = d["m2"].astype(np.float64)
            obj.hist = d["hist"].astype(np.uint32)
            obj.hours_seen = int(d["hours_seen"])
            obj.scene_ewma = d["scene_ewma"].astype(np.float64)
            obj._recompute_hi()

        except Exception as e:
            print(f"[WARN] 기준선을 읽지 못해 새로 시작합니다: {e}")
            return cls(n_cells, min_samples, min_hours, base_date)

        return obj

    def summary(self):
        tail = f" · 기준일 {self.base_date}" if self.base_date else ""
        return (f"표본 {self.count:,}/{self.min_samples:,}건 · "
                f"시간대 {self.hours_covered}/{self.min_hours} · "
                f"{'사용 가능' if self.is_ready() else '누적 중'}{tail}")
