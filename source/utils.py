#
# utils.py
#

import re
import numpy as np

#----------------------------------------------------------

def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

#----------------------------------------------------------

def Conv_LWIR_to_64_Vector(lwir_data, flir_width, flir_height, x_grid, y_grid):
    # 응답 값이 "39.00,37.00,..." 형태의 소수라서 "-?\d+"로는 소수점 앞뒤가
    # 별개 숫자로 쪼개져 개수가 2배로 늘어나고 데이터가 밀리는 문제가 있었다.
    # 소수부까지 하나의 토큰으로 매칭한 뒤 반올림하여 정수화한다.
    nums   = re.findall(r"-?\d+(?:\.\d+)?", lwir_data)
    pixels = [int(round(float(v))) for v in nums]

    print(f"[HotList] {len(pixels)} values ok")

    expected_len = flir_width * flir_height

    # gen-samples.py(학습 파이프라인)와 동일한 기준: 개수가 정확히 맞지 않거나
    # 값이 0~255 범위를 벗어나면 채우거나 자르지 않고 이 프레임 전체를 스킵한다
    # (호출부 except에서 zero-fallback을 반환하면 main() 쪽 zero_count 체크가
    # 이를 걸러내 DB에 쓰지 않고 넘어간다).
    if len(pixels) != expected_len:
        raise ValueError(
            f"invalid value count: got {len(pixels)}, expected {expected_len}"
        )

    if any(v < 0 or v > 255 for v in pixels):
        raise ValueError("pixel value out of range (expected 0~255)")

    img = np.array(pixels, dtype=np.int32).reshape((flir_height, flir_width))

    cell_w = flir_width  // x_grid
    cell_h = flir_height // y_grid

    hotlist = []

    for gy in range(y_grid):
        y0 = gy * cell_h
        y1 = flir_height if gy == y_grid - 1 else y0 + cell_h
        for gx in range(x_grid):
            x0 = gx * cell_w
            x1 = flir_width if gx == x_grid - 1 else x0 + cell_w

            cell = img[y0:y1, x0:x1]
            hotlist.append(int(cell.max()))

    print(f"[LWIR_Img] {len(hotlist)} cells ok")

    return hotlist, img

#----------------------------------------------------------

def Conv_FIFO_to_Median(fifo_matrix, window=10):
    # apply_median.py(학습 파이프라인)와 동일한 기준: FIFO에 window개(기본 10개)가
    # 다 쌓이기 전까지는 median을 계산하지 않고 건너뛴다(None 반환).
    # window개가 차면 가장 최근 window개에 대해 필드별 median을 계산한다.
    # apply_median.py와 달리 정수로 반올림하지 않고 실수형(float) 그대로 반환한다.
    if len(fifo_matrix) < window:
        return None

    recent = np.asarray(fifo_matrix, dtype=float)[-window:]
    return np.median(recent, axis=0)

#----------------------------------------------------------