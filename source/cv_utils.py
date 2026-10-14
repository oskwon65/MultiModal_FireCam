import cv2
import numpy as np
import os
import configparser
import sys
import requests
import time
from datetime import datetime

# ----------------------------
# 설정
# ----------------------------
BASE_IMG_PATH = "base.jpg"     # 기준 이미지

# ----------------------------------------------
# Image fetch
# ----------------------------------------------
def Get_Input_Image_URL(url):

    #print(f"[Get_Input_Image_URL] {url}")     
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        response = requests.get(url, timeout=5)
        response.raise_for_status()
        img_array = np.frombuffer(response.content, np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        print(f"[{now}] Get_Image OK")

        #cv2.imshow("Fetched Image", img)
        #cv2.waitKey(0)
        #cv2.destroyAllWindows()

        return img
    except Exception as e:
        print(f"[{now}] Image Fetch Failed")
        return None

# ----------------------------
# 유틸 함수들
# ----------------------------
def load_and_prepare_image(path):
    """이미지 로드 + 그레이스케일(float32) 반환, 컬러도 같이 반환."""
    img_color = cv2.imread(path)
    if img_color is None:
        raise FileNotFoundError(f"이미지를 읽을 수 없음: {path}")

    gray = cv2.cvtColor(img_color, cv2.COLOR_BGR2GRAY)
    gray_f = np.float32(gray)
    return gray_f, img_color

def crop_to_same_size(img1, img2):
    """두 이미지를 공통 최소 크기(h, w)로 좌측 상단 기준 크롭."""
    h1, w1 = img1.shape[:2]
    h2, w2 = img2.shape[:2]

    h = min(h1, h2)
    w = min(w1, w2)

    img1_cropped = img1[0:h, 0:w]
    img2_cropped = img2[0:h, 0:w]

    return img1_cropped, img2_cropped

def estimate_translation(base_gray_f, curr_gray_f):
    """phaseCorrelate를 이용해 (dx, dy) 이동량 추정."""
    base_gray_f, curr_gray_f = crop_to_same_size(base_gray_f, curr_gray_f)
    shift, response = cv2.phaseCorrelate(base_gray_f, curr_gray_f)
    dx, dy = shift  # (x, y)
    return dx, dy, response

def draw_grid(img, rows, cols, color=(0, 255, 0), thickness=1):
    h, w = img.shape[:2]
    cell_w = w / cols
    cell_h = h / rows

    # 세로 선
    for c in range(1, cols):
        x = int(round(c * cell_w))
        cv2.line(img, (x, 0), (x, h), color, thickness)

    # 가로 선
    for r in range(1, rows):
        y = int(round(r * cell_h))
        cv2.line(img, (0, y), (w, y), color, thickness)

    return img, cell_w, cell_h

def draw_shift_arrow(img, dx, dy, color=(0, 0, 255), thickness=2):
    """
    이미지 중앙에서 (dx, dy)만큼 이동한 위치까지 화살표 표시.
    dx, dy는 '현재 이미지가 기준 대비 오른쪽/아래로' 이동한 양.
    """
    h, w = img.shape[:2]
    cx, cy = w // 2, h // 2

    # 현재 이미지의 중심 위치 (기준 기준으로 이동한 위치)
    end_x = int(round(cx + dx))
    end_y = int(round(cy + dy))

    cv2.arrowedLine(img, (cx, cy), (end_x, end_y), color, thickness, tipLength=0.1)

    return img

def put_shift_text(img, dx, dy, cell_w, cell_h, response):
    """픽셀/셀 단위 이동량을 이미지 위에 텍스트로 표시."""
    # 셀 단위 이동량 (몇 셀만큼 이동했는지)
    dx_cells = dx / cell_w
    dy_cells = dy / cell_h

    text1 = f"dx: {dx:.2f}px ({dx_cells:.2f} cells)"
    text2 = f"dy: {dy:.2f}px ({dy_cells:.2f} cells)"
    text3 = f"response: {response:.4f}"

    # 좌측 상단에 텍스트 출력
    org1 = (10, 25)
    org2 = (10, 50)
    org3 = (10, 75)

    cv2.putText(img, text1, org1, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, text2, org2, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.putText(img, text3, org3, cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 255, 255), 2, cv2.LINE_AA)

    return img

#-----------------------------

def find_closest_base_image(base_dir, target_mean):
    # 파일명이 숫자로만 이루어진 것을 대상으로 함
    # "073.png"처럼 평균 밝기값을 파일명으로 저장하기 때문
    # return: target_mean과 가장 가까운 파일의 전체 경로 (없으면 None)

    best_path = None
    best_diff = float("inf")

    for fname in os.listdir(base_dir):
        stem, ext = os.path.splitext(fname)

        # 3자리 숫자가 아닌 파일은 무시 (예: thumbs, txt 등)
        if not stem.isdigit():
            continue

        try:
            val = int(stem)   # 파일명 '073' -> 73
        except ValueError:
            continue

        diff = abs(val - target_mean)
        if diff < best_diff:
            best_diff = diff
            best_path = os.path.join(base_dir, fname)

    return best_path, best_diff

# ----------------------------
# 폴더 내 파일 갯수를 구함 
def Count_Files_Of_Folder(BASE_IMG_DIR):

    if not os.path.isdir(BASE_IMG_DIR):
        return 0

    count = 0
    for filename in os.listdir(BASE_IMG_DIR):
            full_path = os.path.join(BASE_IMG_DIR, filename)
            if os.path.isfile(full_path):
                count += 1

    return count

# ----------------------------
def estimate_movement(input_img,base_img_path):
    """
    input_img    : 현재 프레임 (BGR, uint8)
    BASE_IMG_DIR : 기준 이미지들이 들어 있는 폴더 경로 (3자리 숫자 파일명)

    return:
        dx, dy, response
    """

    base_gray_f, base_img = load_and_prepare_image(base_img_path)

    input_gray = cv2.cvtColor(input_img, cv2.COLOR_BGR2GRAY)
    input_gray_f = np.float32(input_gray)

    # 5. phaseCorrelate를 위해 크기 맞추기
    base_gray_f, input_gray_f = crop_to_same_size(base_gray_f, input_gray_f)

    # 6. 이동량 추정
    dx, dy, response = estimate_translation(base_gray_f, input_gray_f)

    return dx, dy, response

# ----------------------------
# 카메라 틀어짐을 잰다. 마스크는 옮기지 않는다 (자동 이동보정은 2026-10-08 에 뺐다).
# ----------------------------
import sys
import os
import numpy as np

# ----------------------------
# 기준 1장 방식
#
# 예전에는 밝기별로 기준 이미지를 최대 256장까지 쌓아 두고, 지금 화면과
# 평균 밝기가 가장 가까운 것을 골라 견주었다. 실측해 보니 이 방식은 두 곳
# 모두에서 제 일을 못 하고 있었다.
#
#   cj_busan_1  18장이 서로 0.41px 안에서 일치했다. 첫 장 외에는 정보가
#               없는 중복이었다.
#   kict1       79장이 서로 15.6px 씩 어긋났다. 서로 다른 카메라 위치가
#               네 덩어리로 섞여, 어느 것을 골라도 기준이 되지 못했다.
#
# 섞인 원인은 저장 규칙이다. 밝기차 20 미만이면 이동량이 얼마든 저장했고,
# 밀린 화면이 새 기준으로 계속 추가되었다. 그래서 기준은 굳힌다. 자동으로
# 늘리지 않고, 사람이 [설정] 의 [기준 이미지] 에서 견주어 보고 바꾼다.
#
# 밝기를 맞출 필요도 없다. 위상 상관(phaseCorrelate)은 진폭을 정규화하므로
# 조명 변화에 이미 둔감하다. 조명 성분을 빼는 고역통과를 함께 시험했더니
# 소수점 셋째 자리까지 결과가 같았다.
#
# 밝기차 대신 phaseCorrelate 가 돌려주는 response 를 신뢰도로 쓴다. 이미
# 계산해서 화면에 찍고 있었는데 판정에는 쓰지 않던 값이다.
# ----------------------------

BASE_REF_NAME = "base_ref.png"

# response 가 이보다 낮으면 같은 장면이 아니라고 보고 판정하지 않는다.
# 같은 장면끼리는 0.90 언저리, 다른 장면과는 0.15 언저리로 뚜렷이 갈린다.
SHIFT_RESP_MIN = 0.30

# 틀어짐 판정 상태. stage_status 를 거쳐 [설정] 화면까지 그대로 간다.
SHIFT_STATE_LEGACY = -1   # 기준 1장이 없다 (예전 방식으로 돌고 있다)
SHIFT_STATE_UNSURE = 0    # 쟀으나 믿을 수 없다 (장면이 다름)
SHIFT_STATE_OK     = 1    # 틀어지지 않았다
SHIFT_STATE_SHIFT  = 2    # 틀어졌다


def shift_info(state, dx=None, dy=None, response=None):
    """
    틀어짐 측정 결과를 한 덩어리로 묶는다.

    칸 수만 돌려주면 한 칸(640/8 = 80px)보다 작은 흔들림이 통째로 0칸으로
    묻힌다. 실제로 kict1 의 기준 이미지 더미에는 10~20px 씩 조금씩 돌아간
    흔적이 남아 있었는데, 칸으로만 보면 전부 "이동 없음" 이다. 잰 픽셀 값을
    함께 들고 다녀 화면에 그대로 적는다.

    dx, dy 가 None 이면 재지 못했다는 뜻이다. 0.0 으로 채우면 "안 밀렸다" 로
    읽히므로 채우지 않는다.
    """
    return {"state": state, "dx": dx, "dy": dy, "response": response}


def base_ref_path(BASE_IMG_DIR):
    return os.path.join(BASE_IMG_DIR, BASE_REF_NAME)


def measure_shift_vs_ref(ref_img, input_img):
    """
    굳혀 둔 기준 1장에 대한 평행이동.

    돌려주는 값은 (dx, dy, response). 같은 장면으로 보기 어려우면 None.
    """
    a = np.float32(cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY))
    b = np.float32(cv2.cvtColor(input_img, cv2.COLOR_BGR2GRAY))
    a, b = crop_to_same_size(a, b)

    h, w = a.shape[:2]
    hann = cv2.createHanningWindow((w, h), cv2.CV_32F)

    # 반드시 복사본을 준다. cv2.phaseCorrelate 는 window 를 주면 입력 배열을
    # 제자리에서 창과 곱해 덮어쓴다. crop 결과는 원본의 view 일 수도 있어
    # 기준 이미지가 통째로 망가진다. (이 함정에 실제로 한 번 빠져, 기준
    # 배열을 312번 재사용한 시험 결과를 통째로 버렸다.)
    (dx, dy), response = cv2.phaseCorrelate(a.copy(), b.copy(), hann)

    if response < SHIFT_RESP_MIN:
        return None

    return dx, dy, response


def _adjust_with_frozen_ref(ref_path, input_img, hotlist_mask, X_GRID, Y_GRID):
    """기준 1장 방식. 반환 규약은 Get_Adjusted_HotMask_Position 과 같다."""
    ref_img = cv2.imread(ref_path)
    if ref_img is None:
        print(f"[WARN] 기준 이미지를 읽지 못했음: {ref_path}")
        return False, hotlist_mask.copy(), 0, 0, shift_info(SHIFT_STATE_UNSURE)

    m = measure_shift_vs_ref(ref_img, input_img)

    print("-" * 50)
    print(f"[기준 1장] {ref_path}")

    if m is None:
        # 여기서 "이상 없음" 이라고 말하면 안 된다. 잴 수 없었을 뿐이다.
        print(f"[기준 1장] 판정 불가 - 기준과 같은 장면으로 보기 어려움 "
              f"(response < {SHIFT_RESP_MIN}). 마스크는 그대로 둠")
        print("-" * 50)
        return False, hotlist_mask.copy(), 0, 0, shift_info(SHIFT_STATE_UNSURE)

    dx, dy, response = m

    h, w = input_img.shape[:2]
    cell_w = w / X_GRID
    cell_h = h / Y_GRID

    # 반올림한다. 예전 코드는 int() 로 잘라 내, 0.9칸 밀린 것을 0칸으로 봤다.
    shift_x = int(round(dx / cell_w))
    shift_y = int(round(dy / cell_h))

    print(f"[기준 1장] DX {dx:+.1f}px -> {shift_x}칸,  DY {dy:+.1f}px -> {shift_y}칸,  "
          f"response {response:.3f}")

    if shift_x == 0 and shift_y == 0:
        print("[기준 1장] 틀어짐 없음")
        print("-" * 50)
        return False, hotlist_mask.copy(), 0, 0, shift_info(SHIFT_STATE_OK, dx, dy, response)

    print(f"[기준 1장] 틀어짐 감지 - 가로 {shift_x:+d}칸, 세로 {shift_y:+d}칸")
    print("-" * 50)

    # 마스크는 옮기지 않는다. 잰 값만 돌려준다 (자동 이동보정은 2026-10-08 에 뺐다).
    return True, hotlist_mask.copy(), shift_x, shift_y, shift_info(SHIFT_STATE_SHIFT, dx, dy, response)


# ----------------------------

def Get_Adjusted_HotMask_Position(BASE_IMG_DIR, input_img, hotlist_mask, X_GRID, Y_GRID):

    LENGTH_HOTLIST       = X_GRID * Y_GRID
    NUM_OF_MACHINE_CELLS = LENGTH_HOTLIST

    # ---------- validation ----------
    if hotlist_mask.shape[0] != LENGTH_HOTLIST:
        sys.exit(
            f"[ERROR] MACH_AREA_MASK length must be {LENGTH_HOTLIST}, "
            f"got {hotlist_mask.shape[0]}"
        )

    if not np.all((hotlist_mask == 0) | (hotlist_mask == 1)):
        sys.exit("[ERROR] MACH_AREA_MASK must contain only 0 or 1")

    if np.sum(hotlist_mask) > NUM_OF_MACHINE_CELLS:
        sys.exit("[ERROR] MACH_AREA_MASK must contain equal or less than NUM_OF_MACHINE_CELLS ones")

    # 굳혀 둔 기준이 있으면 그것 하나만 본다. 없으면 예전 방식 그대로 돈다.
    # 현장마다 따로 넘어갈 수 있게 하려는 것이다. cj_busan_1 은 18장이 모두
    # 한 위치라 바로 굳혔지만, kict1 은 네 위치가 섞여 있어 어느 것을 골라도
    # 기준이 되지 못한다. 현장에서 조준을 맞춘 뒤에야 굳힐 수 있다.
    ref_path = base_ref_path(BASE_IMG_DIR)
    if os.path.exists(ref_path):
        return _adjust_with_frozen_ref(ref_path, input_img, hotlist_mask,
                                       X_GRID, Y_GRID)

    mean_val = Get_Image_MeanValue(input_img)
    base_img_path, diff = find_closest_base_image(BASE_IMG_DIR, mean_val)

    # base_img 폴더가 비어 있으면 현재 이미지를 첫 기준으로 저장 후 복귀
    if base_img_path is None:
        print("[INFO] No base image found. Saving current image as first base image.")
        save_base_image(BASE_IMG_DIR, input_img)
        return False, hotlist_mask.copy(), 0, 0, shift_info(SHIFT_STATE_LEGACY)

    dx, dy, response = estimate_movement(input_img, base_img_path)

    # ---------- 셀 크기 계산 ----------
    h, w = input_img.shape[:2]
    cell_w = w / X_GRID
    cell_h = h / Y_GRID

    # ---------- cell 단위 이동량 계산 ----------
    shift_x = int(dx / cell_w)
    shift_y = int(dy / cell_h)

    print("-" * 50)
    print("Estimated translation (current relative to base):")
    print(f"diff : {diff}")
    print(f"BASE_IMG_DIR : {BASE_IMG_DIR}")
    print(f"DX : {dx:.1f} pixels -> {shift_x} cell shift")
    print(f"DY : {dy:.1f} pixels -> {shift_y} cell shift")
    print(f"The correlation between the two images : {response:.4f}")
    print("-" * 50)

    #조금 흔들린 경우 조금 틀어진 이미지를 추가 저장하고 현 mask 상태 유지함
    if diff < 20: #평균 이미지 그레이값의 차이
            print(f"Num of Files of Base_Img: {base_img_path} [brightness diff.] {diff}")
            save_base_image(BASE_IMG_DIR, input_img)
            return False, hotlist_mask.copy(), 0, 0, shift_info(SHIFT_STATE_LEGACY, dx, dy, response)

    # 마스크는 옮기지 않는다. 잰 값만 돌려준다 (자동 이동보정은 2026-10-08 에 뺐다).
    return True, hotlist_mask.copy(), shift_x, shift_y, shift_info(SHIFT_STATE_LEGACY, dx, dy, response)

# ----------------------------

def save_base_image(BASE_IMG_DIR,input_img):
    mean_val = Get_Image_MeanValue(input_img)
    os.makedirs(BASE_IMG_DIR, exist_ok=True)
    filename = f"{mean_val:03d}.png"
    save_path = os.path.join(BASE_IMG_DIR, filename)
    cv2.imwrite(save_path, input_img)
    # 예전에는 "폴더가 비어 있어" 라고 적었는데, 이 함수는 폴더가 찬 상태에서
    # 밝기차 20 미만일 때도 불린다. 사실과 다른 안내였다.
    print(f"[예전 방식] 기준 이미지를 저장했음: {save_path}")

# ----------------------------

def Get_Image_MeanValue(input_img):
    # 평균 그레이값 기반으로 3자리 숫자 파일명 생성 (000 ~ 255)
    gray = cv2.cvtColor(input_img, cv2.COLOR_BGR2GRAY)
    mean_val = int(round(float(gray.mean())))
    mean_val = max(0, min(255, mean_val))  # 범위 클램핑
    return mean_val

# ------------------------------------
 
def Get_Input_Image_Local(TEST_IMG,WAITING_TIME) :
    input_img = None
    while True:
        input_img = cv2.imread(TEST_IMG)
        if input_img is None:
            print("[WARN] image fetch failed, retrying...")
            time.sleep(WAITING_TIME)
            continue
        break
    return input_img    