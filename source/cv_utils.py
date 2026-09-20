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
        raise FileNotFoundError(f"이미지를 읽을 수 없습니다: {path}")

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
# get_new_hotlist_mask : 카메라 위치 조정에 따른 hotlist_mask 의 내용을 조정함
# ----------------------------
import sys
import os
import numpy as np

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

    mean_val = Get_Image_MeanValue(input_img)
    base_img_path, diff = find_closest_base_image(BASE_IMG_DIR, mean_val)

    # base_img 폴더가 비어 있으면 현재 이미지를 첫 기준으로 저장 후 복귀
    if base_img_path is None:
        print("[INFO] No base image found. Saving current image as first base image.")
        save_base_image(BASE_IMG_DIR, input_img)
        return False, hotlist_mask.copy(), 0, 0

    dx, dy, response = estimate_movement(input_img, base_img_path)

    # ---------- 셀 크기 계산 ----------
    h, w = input_img.shape[:2]
    cell_w = w / X_GRID
    cell_h = h / Y_GRID

    # ---------- 1D → 2D ----------
    mask_grid = hotlist_mask.reshape(Y_GRID, X_GRID)

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
            return False, hotlist_mask.copy(), 0, 0

    # ---------- 마스크 이동 보정 ----------           

    shifted = np.zeros_like(mask_grid)  
    for r in range(Y_GRID):
        for c in range(X_GRID):
            src_r = r - shift_y
            src_c = c - shift_x

            if 0 <= src_r < Y_GRID and 0 <= src_c < X_GRID:
                shifted[r, c] = mask_grid[src_r, src_c]

    shifted_flat = shifted.flatten()

    return True, shifted_flat, shift_x, shift_y

# ----------------------------

def save_base_image(BASE_IMG_DIR,input_img):
    mean_val = Get_Image_MeanValue(input_img)
    os.makedirs(BASE_IMG_DIR, exist_ok=True)
    filename = f"{mean_val:03d}.png"
    save_path = os.path.join(BASE_IMG_DIR, filename)
    cv2.imwrite(save_path, input_img)
    print(f"[INFO] BASE_IMG_DIR가 비어 있어 현재 이미지를 base로 저장했습니다: {save_path}")  

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