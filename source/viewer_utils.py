import numpy as np
import math
import cv2
import os
import configparser
import sys
from PIL import Image, ImageDraw, ImageFont



# ==================================================
# COCO keypoint index
# ==================================================
COCO_KP = {
    "nose":          0,
    "left_eye":      1,
    "right_eye":     2,
    "left_ear":      3,
    "right_ear":     4,
    "left_shoulder": 5,
    "right_shoulder": 6,
    "left_elbow":    7,
    "right_elbow":   8,
    "left_wrist":    9,
    "right_wrist":   10,
    "left_hip":      11,
    "right_hip":     12,
    "left_knee":     13,
    "right_knee":    14,
    "left_ankle":    15,
    "right_ankle":   16,
}

# ---------------- 신체 부위 그룹 정의 ----------------
BODY_GROUPS = {
    "left_leg": [
        (COCO_KP["left_ankle"], COCO_KP["left_knee"]),
        (COCO_KP["left_knee"],  COCO_KP["left_hip"]),
    ],
    "right_leg": [
        (COCO_KP["right_ankle"], COCO_KP["right_knee"]),
        (COCO_KP["right_knee"],  COCO_KP["right_hip"]),
    ],
    "torso": [
        (COCO_KP["left_hip"],       COCO_KP["right_hip"]),
        (COCO_KP["left_shoulder"],  COCO_KP["left_hip"]),
        (COCO_KP["right_shoulder"], COCO_KP["right_hip"]),
        (COCO_KP["left_shoulder"],  COCO_KP["right_shoulder"]),
    ],
    "left_arm": [
        (COCO_KP["left_shoulder"], COCO_KP["left_elbow"]),
        (COCO_KP["left_elbow"],    COCO_KP["left_wrist"]),
    ],
    "right_arm": [
        (COCO_KP["right_shoulder"], COCO_KP["right_elbow"]),
        (COCO_KP["right_elbow"],    COCO_KP["right_wrist"]),
    ],
    "head": [
        (COCO_KP["left_eye"],  COCO_KP["right_eye"]),
        (COCO_KP["nose"],      COCO_KP["left_eye"]),
        (COCO_KP["nose"],      COCO_KP["right_eye"]),
        (COCO_KP["left_eye"],  COCO_KP["left_ear"]),
        (COCO_KP["right_eye"], COCO_KP["right_ear"]),
    ],
}

# ---------------- 신체 부위별 색상 정의 (BGR) ----------------
BODY_COLORS = {
    "head": (0, 255, 255),
    "torso": (255, 200, 0),
    "left_arm": (0, 255, 0),
    "right_arm": (30, 144, 255),
    "left_leg": (255, 0, 255),
    "right_leg": (255, 100, 0),
}
# -------------------------------------------------------------
# PIL / Font Helpers
def find_default_font_path():
    """
    Windows 우선으로 보기 좋은 기본 폰트를 자동 탐색한다.
    환경에 따라 존재하는 첫 번째 폰트를 사용한다.
    """
    candidates = [
        r"C:\Windows\Fonts\malgun.ttf",          # Malgun Gothic
        r"C:\Windows\Fonts\malgunbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\seguisb.ttf",
        r"C:\Windows\Fonts\calibri.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
    ]

    for path in candidates:
        if os.path.exists(path):
            return path

    return None


FONT_PATH = find_default_font_path()

# -------------------------------------------------------------
def get_pil_font(font_size, bold=False):
    """
    truetype 폰트를 불러온다.
    폰트를 찾지 못하면 Pillow 기본 폰트로 fallback 한다.
    """
    if FONT_PATH and os.path.exists(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, font_size)
        except Exception:
            pass

    return ImageFont.load_default()

# -------------------------------------------------------------
def cv2_to_pil(img_bgr):
    return Image.fromarray(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB))

# -------------------------------------------------------------
def pil_to_cv2(img_pil):
    return cv2.cvtColor(np.array(img_pil), cv2.COLOR_RGB2BGR)

# -------------------------------------------------------------
def bgr_to_rgb_tuple(color_bgr):
    b, g, r = color_bgr
    return (r, g, b)

# -------------------------------------------------------------
def draw_text_pil(
    img_bgr,
    text,
    xy,
    font_size=20,
    color=(255, 255, 255),
    anchor="lt",
    shadow=True,
    shadow_color=(0, 0, 0),
    shadow_offset=(1, 1),
):
    """
    OpenCV BGR 이미지에 Pillow truetype 폰트로 텍스트를 그린다.
    color / shadow_color 는 BGR 기준으로 받는다.
    anchor 예시:
      - "lt": left-top
      - "mm": middle-middle
      - "ls": left-baseline 비슷한 효과는 Pillow anchor에 제한 있음
    """
    pil_img = cv2_to_pil(img_bgr)
    draw = ImageDraw.Draw(pil_img)
    font = get_pil_font(font_size)

    rgb_color = bgr_to_rgb_tuple(color)
    rgb_shadow = bgr_to_rgb_tuple(shadow_color)

    x, y = xy

    if shadow:
        draw.text(
            (x + shadow_offset[0], y + shadow_offset[1]),
            text,
            font=font,
            fill=rgb_shadow,
            anchor=anchor
        )

    draw.text(
        (x, y),
        text,
        font=font,
        fill=rgb_color,
        anchor=anchor
    )

    return pil_to_cv2(pil_img)

# -------------------------------------------------------------
def get_text_bbox(text, font_size=20, anchor="lt"):
    """
    Pillow 기준 텍스트 bounding box 크기 계산
    """
    font = get_pil_font(font_size)
    dummy_img = Image.new("RGB", (10, 10), (0, 0, 0))
    draw = ImageDraw.Draw(dummy_img)
    bbox = draw.textbbox((0, 0), text, font=font, anchor=anchor)
    w = bbox[2] - bbox[0]
    h = bbox[3] - bbox[1]
    return w, h

# -------------------------------------------------------------
def fit_text_font_size(text, max_width, start_size=22, min_size=10):
    """
    주어진 max_width 안에 들어갈 수 있는 최대 font size를 찾는다.
    """
    for size in range(start_size, min_size - 1, -1):
        w, _ = get_text_bbox(text, font_size=size, anchor="lt")
        if w <= max_width:
            return size
    return min_size

# -------------------------------------------------------------
# Fall keypoint builder
def build_fall_keypoints(person_pred, conf_thresh=0.3):
    kps = person_pred.data if hasattr(person_pred, "data") else person_pred
    if not isinstance(kps, np.ndarray) or kps.shape[1] != 3:
        return None

    def valid(i):
        x, y, s = kps[i]
        return None if s < conf_thresh else (float(x), float(y))

    def midpoint(a, b):
        return None if a is None or b is None else (
            (a[0] + b[0]) / 2.0,
            (a[1] + b[1]) / 2.0,
        )

    shoulder = midpoint(valid(COCO_KP["left_shoulder"]), valid(COCO_KP["right_shoulder"]))
    hip = midpoint(valid(COCO_KP["left_hip"]), valid(COCO_KP["right_hip"]))
    knee = midpoint(valid(COCO_KP["left_knee"]), valid(COCO_KP["right_knee"]))
    ankle = midpoint(valid(COCO_KP["left_ankle"]), valid(COCO_KP["right_ankle"]))

    if shoulder is None or hip is None:
        return None

    return {
        "shoulder": shoulder,
        "hip": hip,
        "knee": knee,
        "ankle": ankle,
    }

# -------------------------------------------------------------
# Fall 판단
def angle_from_vertical(p1, p2):
    dx = p2[0] - p1[0]
    dy = p2[1] - p1[1]
    return abs(math.degrees(math.atan2(dx, dy))) if dx or dy else None


def is_fall(fall_kps, thresh=45.0):
    if not fall_kps:
        return 0, None

    angle = angle_from_vertical(
        fall_kps["shoulder"],
        fall_kps["hip"]
    )

    if angle is None:
        return 0, None

    is_fall_flag = 1 if angle > thresh else 0
    return is_fall_flag, angle

# -------------------------------------------------------------

def draw_fire_smoke_detections(img, fire_results, class_names):
    """
    Fire / Smoke 라벨을 Pillow truetype 폰트로 렌더링한다.
    """
    detections = []

    COLOR_MAP = {
        "fire":  (0, 0, 255),      # red
        "smoke": (128, 128, 128)   # gray
    }

    LABEL_BG_COLOR = (0, 0, 0)
    LABEL_TEXT_COLOR = (255, 255, 255)

    for r in fire_results:
        if r.boxes is None:
            continue

        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            cls_name = class_names[cls_id]

            if cls_name not in ("fire", "smoke"):
                continue

            detections.append((cls_name, conf))

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            color = COLOR_MAP[cls_name]

            label = f"{cls_name.upper()} {conf:.1f}"

            # 검출 영역 박스 표시
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 2)

            label_font_size = 18
            pad_x = 6
            pad_y = 4

            tw, th = get_text_bbox(label, font_size=label_font_size, anchor="lt")

            bg_x1 = x1
            bg_y1 = max(0, y1 - th - pad_y * 2 - 4)
            bg_x2 = x1 + tw + pad_x * 2
            bg_y2 = bg_y1 + th + pad_y * 2

            # 라벨 배경
            cv2.rectangle(
                img,
                (bg_x1, bg_y1),
                (bg_x2, bg_y2),
                LABEL_BG_COLOR,
                -1
            )

            # 상단 강조선
            cv2.rectangle(
                img,
                (bg_x1, bg_y1),
                (bg_x2, bg_y1 + 2),
                color,
                -1
            )

            # Pillow 텍스트
            img = draw_text_pil(
                img,
                label,
                (bg_x1 + pad_x, bg_y1 + pad_y),
                font_size=label_font_size,
                color=LABEL_TEXT_COLOR,
                anchor="lt",
                shadow=False
            )

    return detections

# -------------------------------------------------------------
# 부위별 스켈레톤 그리기 
def draw_skeletons(image, preds, show_kp=True,
                   kp_radius=3, kp_thickness=-1, line_thickness=3,
                   verbose=False):

    h, w = image.shape[:2]

    for person_idx, pred in enumerate(preds):
        kps = get_keypoints_from_pred(pred)
        if kps is None:
            if verbose:
                print(f"[Person {person_idx}] No keypoints detected")
            continue

        if np.max(kps[:, :2]) <= 1.0:
            kps[:, 0] *= w
            kps[:, 1] *= h

        if verbose:
            print(f"\n[Person {person_idx}] Keypoints (x, y, confidence)")
            for i, (x, y, s) in enumerate(kps):
                print(f"  KP[{i:02d}] = ({x:.1f}, {y:.1f}), score={s:.3f}")

        for part_name, connections in BODY_GROUPS.items():
            color = BODY_COLORS.get(part_name, (255, 255, 255))

            if verbose:
                print(f"\n  [Body Part: {part_name}] color={color}")
                print("   connections:")

            for a, b in connections:
                if a < len(kps) and b < len(kps):
                    xa, ya, sa = kps[a]
                    xb, yb, sb = kps[b]

                    if verbose:
                        print(
                            f"    ({a} -> {b}) | "
                            f"A=({xa:.1f}, {ya:.1f}, score={sa:.2f}) , "
                            f"B=({xb:.1f}, {yb:.1f}, score={sb:.2f})"
                        )

                    if sa > 0.05 and sb > 0.05:
                        cv2.line(
                            image,
                            (int(xa), int(ya)),
                            (int(xb), int(yb)),
                            color,
                            line_thickness,
                            lineType=cv2.LINE_AA
                        )

        if show_kp:
            for i, (x, y, s) in enumerate(kps):
                if s > 0.05:
                    cv2.circle(
                        image,
                        (int(x), int(y)),
                        kp_radius,
                        (255, 255, 255),
                        kp_thickness,
                        lineType=cv2.LINE_AA
                    )

# -------------------------------------------------------------
# pred에서 keypoints 추출
def get_keypoints_from_pred(pred):
    for attr in ('keypoints', 'keypoint', 'data', 'predictions', 'instances'):
        if hasattr(pred, attr):
            try:
                arr = np.asarray(getattr(pred, attr))
                if arr.ndim == 2 and arr.shape[1] >= 2:
                    if arr.shape[1] == 2:
                        arr = np.hstack([arr, np.ones((arr.shape[0], 1))])
                    return arr[:, :3].astype(float)
            except Exception:
                pass

    try:
        j = pred.json_data()
        if 'keypoints' in j:
            flat = j['keypoints']
            arr = np.array(flat).reshape(-1, 3)
            return arr
    except Exception:
        pass

    return None

# -------------------------------------------------------------
# FIRE / SMOKE MAP
def get_overlapping_cells_vector(X_GRID,Y_GRID,x1, y1, x2, y2, width, height):
    LENGTH_HOTLIST = X_GRID * Y_GRID
    cell_w = width / X_GRID
    cell_h = height / Y_GRID
    result = [0.0] * LENGTH_HOTLIST

    col_start = max(0, min(X_GRID - 1, int(x1 // cell_w)))
    col_end   = max(0, min(X_GRID - 1, int(x2 // cell_w)))
    row_start = max(0, min(Y_GRID - 1, int(y1 // cell_h)))
    row_end   = max(0, min(Y_GRID - 1, int(y2 // cell_h)))

    for r in range(row_start, row_end + 1):
        for c in range(col_start, col_end + 1):
            result[r * X_GRID + c] = 1.0

    return result

# -------------------------------------------------------------

def make_fire_smoke_map(X_GRID,Y_GRID,height, width, img, fire_results, class_names):
    LENGTH_HOTLIST = X_GRID * Y_GRID;
    fire_vec = [0.0] * LENGTH_HOTLIST
    smoke_vec = [0.0] * LENGTH_HOTLIST

    for r in fire_results:
        if r.boxes is None:
            continue
        for box in r.boxes:
            cls_id = int(box.cls[0])
            conf = float(box.conf[0])
            cls_name = class_names[cls_id]

            if cls_name not in ("fire", "smoke"):
                continue

            x1, y1, x2, y2 = map(int, box.xyxy[0])
            mask = get_overlapping_cells_vector(X_GRID,Y_GRID,x1, y1, x2, y2, width, height)

            for i in range(LENGTH_HOTLIST):
                if mask[i]:
                    if cls_name == "fire":
                        fire_vec[i] = max(fire_vec[i], conf)
                    else:
                        smoke_vec[i] = max(smoke_vec[i], conf)

    return fire_vec, smoke_vec

# -------------------------------------------------------------

def ensure_dir(path):
    if path:
        os.makedirs(path, exist_ok=True)
    return path

# -------------------------------------------------------------

def get_person_confidence(person_pred):
    """
    사람 검출 confidence를 안전하게 추출
    return: float or None
    """
    for attr in ("score", "conf", "confidence"):
        if hasattr(person_pred, attr):
            try:
                return float(getattr(person_pred, attr))
            except Exception:
                pass

    try:
        kps = person_pred.data if hasattr(person_pred, "data") else None
        if isinstance(kps, np.ndarray) and kps.shape[1] == 3:
            return float(np.mean(kps[:, 2]))
    except Exception:
        pass

    return None

# -------------------------------------------------------------

def show_flir_image(cfg,img, hotlist_values, hotlist_mask, width=640, height=480, win_x=100, win_y=100, WINDOW_NAME ="FLIR Image"):
    if img is None or img.size == 0:
        print("[WARN] Empty image")
        return

    SCALE_MIN = 0.0
    SCALE_MAX = 50.0

    img_f = img.astype(np.float32)
    img_clipped = np.clip(img_f, SCALE_MIN, SCALE_MAX)
    img_u8 = ((img_clipped - SCALE_MIN) / (SCALE_MAX - SCALE_MIN) * 255.0).astype(np.uint8)

    resized = cv2.resize(img_u8, (width, height), interpolation=cv2.INTER_NEAREST)
    resized_bgr = cv2.cvtColor(resized, cv2.COLOR_GRAY2BGR)

    new_img = draw_image_grid(
        cfg,
        resized_bgr,
        None,
        None,
        hotlist_values,
        hotlist_mask,
        (250, 250, 250),
        fire_color=(255, 0, 0),
        smoke_color=(0, 0, 255),    
        thickness=1,
        font_size=20
    )

    zoom_out = 0.7
    new_img = cv2.resize(new_img,None,fx=zoom_out,fy=zoom_out,interpolation=cv2.INTER_AREA)
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)    
    cv2.resizeWindow(WINDOW_NAME, new_img.shape[1], new_img.shape[0])
    cv2.moveWindow(WINDOW_NAME, win_x, win_y)
    cv2.imshow(WINDOW_NAME, new_img)
    cv2.waitKey(1)

# -------------------------------------------------------------

def draw_image_grid(
    cfg,
    img,
    fire_area,
    smoke_area,
    hotlist_values,
    hotlist_mask,
    base_color=(100, 100, 100),
    fire_color=(255, 0, 0),
    smoke_color=(0, 0, 255),
    thickness=1,
    font_size=20,
):

    X_GRID = cfg.get("X_GRID")
    Y_GRID = cfg.get("Y_GRID")
    THR_CONF_FIRE = cfg.get("THR_CONF_FIRE")
    THR_TEMPT_FIRE = cfg.get("THR_TEMPT_FIRE")
    THR_TEMPT_SMOKE = cfg.get("THR_TEMPT_SMOKE")
    THR_CONF_SMOKE = cfg.get("THR_CONF_SMOKE")

    grid_color = (200, 100, 100)
    mask_color = (100, 100, 250)

    h, w = img.shape[:2]
    cell_w = w // X_GRID
    cell_h = h // Y_GRID
    cell_w_half = cell_w // 2

    total_cells = X_GRID * Y_GRID

    # fire_area / smoke_area가 없으면 0으로 초기화
    if fire_area is None:
        fire_area = np.zeros(total_cells, dtype=float)

    if smoke_area is None:
        smoke_area = np.zeros(total_cells, dtype=float)

    fire_area = np.asarray(fire_area, dtype=float)
    smoke_area = np.asarray(smoke_area, dtype=float)
    hotlist_values = np.asarray(hotlist_values, dtype=float)

    if hotlist_mask is not None:
        hotlist_mask = np.asarray(hotlist_mask)

    # 길이 검증
    if fire_area.size != total_cells:
        raise ValueError(
            f"fire_area length must be {total_cells}, got {fire_area.size}"
        )

    if smoke_area.size != total_cells:
        raise ValueError(
            f"smoke_area length must be {total_cells}, got {smoke_area.size}"
        )

    if hotlist_values.size != total_cells:
        raise ValueError(
            f"hotlist_values length must be {total_cells}, got {hotlist_values.size}"
        )

    if hotlist_mask is not None and hotlist_mask.size != total_cells:
        raise ValueError(
            f"hotlist_mask length must be {total_cells}, got {hotlist_mask.size}"
        )

    for gy in range(Y_GRID):
        for gx in range(X_GRID):
            idx = gy * X_GRID + gx

            x0 = gx * cell_w
            y0 = gy * cell_h
            x1 = (gx + 1) * cell_w
            y1 = (gy + 1) * cell_h

            text_color = base_color
            if hotlist_mask is not None and hotlist_mask[idx] == 1:
                text_color = mask_color

            draw_color = (100,100,100)
            cur_thickness = thickness

            if (fire_area[idx] > THR_CONF_FIRE) and (hotlist_values[idx] > THR_TEMPT_FIRE):
                draw_color = fire_color
                cur_thickness = thickness * 2
            elif (smoke_area[idx] > THR_CONF_SMOKE) and (hotlist_values[idx] > THR_TEMPT_SMOKE):
                draw_color = smoke_color
                cur_thickness = thickness * 2

            cv2.rectangle(
                img,
                (int(x0), int(y0)),
                (int(x1), int(y1)),
                draw_color,
                cur_thickness
            )

            val = int(hotlist_values[idx])
            text = str(val)
            ty = y0 + int(cell_h * 0.6)

            img = draw_text_pil(
                img,
                text,
                (x0 + cell_w_half, ty),
                font_size=font_size,
                color=text_color,
                anchor="mm",
                shadow=False,
                shadow_color=(0, 0, 0),
                shadow_offset=(1, 1),
            )

    return img

# -------------------------------------------------------------

def draw_texts_on_image(
    env_conf,
    image,
    score_value,
    mse_value,
    error_code,
    people_count,
    fall_people
):
    X_GRID                        = env_conf.get("X_GRID")
    Y_GRID                        = env_conf.get("Y_GRID")

    # 색상 정의 (BGR)
    COLOR_MASKED = (100, 100, 255)            # red
    COLOR_UNMASKED = (190, 190, 190)      # gray
    COLOR_BOTTOM_TEXT = (255, 255, 255)   # white
    COLOR_SHADOW = (0, 0, 0)
    COLOR_BOTTOM_BAR = (0, 0, 0)          # black

    BOTTOM_BAR_H = 50

    h, w = image.shape[:2]

    # 먼저 출력 이미지를 복사
    image_out = image.copy()

    # 하단 바 추가 (기존 이미지 하단 영역 덮어쓰기)
    bottom_y0 = max(0, h - BOTTOM_BAR_H)
    image_out[bottom_y0:h, :, :] = COLOR_BOTTOM_BAR

    step_x = w / X_GRID
    step_y = h / Y_GRID

    # HOTLIST 숫자 폰트 크기 자동 조절
    hot_font_size = max(24, int(min(step_x, step_y) * 0.28))

    err_str = str(error_code) if error_code is not None else "-"

    if score_value is not None and mse_value is not None:
        bottom_text = (
            f"SCORE: {float(score_value):.2f}   "
            f"MSE: {float(mse_value):.2f}   "
            f"ERR: {err_str}   "
            f"PERSON: {people_count}   "
            f"FALL: {fall_people}"
        )
    else:
        bottom_text = (
            f"ERR: {err_str}   "
            f"PERSON: {people_count}   "
            f"FALL: {fall_people}"
        )

    # 하단 바 너비에 맞춰 폰트 크기 자동 조절
    bottom_font_size = fit_text_font_size(
        bottom_text,
        max_width=w - 40,
        start_size=24,
        min_size=12
    )

    # 하단 검은 바 중앙에 배치
    text_x = 20
    text_y = bottom_y0 + (BOTTOM_BAR_H // 2)

    image_out = draw_text_pil(
        image_out,
        bottom_text,
        (text_x, text_y),
        font_size=bottom_font_size,
        color=COLOR_BOTTOM_TEXT,
        anchor="lm",   # left-middle
        shadow=False,
        shadow_color=COLOR_SHADOW,
        shadow_offset=(1, 1),
    )

    return image_out