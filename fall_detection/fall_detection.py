#
# python fall_detection/fall_detection.py cj_busan_1
#

import argparse
import json
import logging
import os
import time
import tempfile
import re
import datetime
import sys
import warnings

import cv2
import numpy as np
import requests
import torch

# ==================================================
# sys.path : db_utils, cv_utils path setup
# ==================================================

# 프로젝트 source 폴더를 import 경로 맨 앞에 넣는다.
# 경로를 상수로 박으면 설치 위치가 바뀔 때마다 동명의 PyPI 패키지(db_utils)가
# 대신 임포트되어 조용히 죽으므로, 실행 환경에서 찾아낸다.
#   1) 환경변수 MMCAM_ROOT   2) 현재 작업 폴더   3) 이 파일 기준 상위 폴더
def _resolve_source_dir():
    candidates = []
    env_root = os.environ.get("MMCAM_ROOT")
    if env_root:
        candidates.append(os.path.join(env_root, "source"))
    candidates.append(os.path.join(os.getcwd(), "source"))
    candidates.append(
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "source")
    )
    for path in candidates:
        if os.path.isfile(os.path.join(path, "db_utils.py")):
            return os.path.abspath(path)
    return os.path.abspath(candidates[-1])

sys.path.insert(0, _resolve_source_dir())
print(f"[SYS.PATH] added : {sys.path[0]}")
print(f"[CWD]      cwd   : {os.getcwd()}")

# ==================================================
# Warning filter
# ==================================================

warnings.filterwarnings("ignore", message="torch.meshgrid")

from db_utils import (
    read_from_current_value_median,
    read_db_current_status,
    update_sensor_db_table,
    update_db_error_code,
    Get_db_hotlist_mask,
    read_fire_list,
    read_slave_sensor,
    Set_Env_Config,
    Get_SensorDB_Config,
)

from viewer_utils import (
    build_fall_keypoints,
    is_fall,
    draw_texts_on_image,
    draw_fire_smoke_detections,
    draw_skeletons,
    make_fire_smoke_map,
    ensure_dir,
    get_person_confidence,
    draw_image_grid,
)

from cv_utils import (
    Get_Input_Image_URL,
    Get_Input_Image_Local,
)

from constants import MIN_WINDOW_WIDTH

# ==================================================
# openpifpaf 라이브러리 연결 : 절대 임포트를 쓰는 이유
# ==================================================
#
#   from . import decoder            # 예전 - 실패
#   from openpifpaf import decoder   # 지금 - 성공
#
# 두 문장은 "찾는 방법"이 근본적으로 다르다.
#
# [ from . import ... ]  상대 임포트
#   '.' 은 "내가 속한 패키지"를 뜻하며, 파이썬은 이를 __package__ 변수로만
#   판단한다. sys.path 는 아예 쳐다보지 않는다.
#   이 파일을 스크립트로 직접 실행하면 __name__ 은 "__main__", __package__ 는
#   None 이 되어 '.' 이 가리킬 대상이 없다. 그래서 openpifpaf 가 site-packages
#   에 멀쩡히 설치되어 있어도 경로를 찾아보지도 않고 즉시 거부한다.
#       ImportError: attempted relative import with no known parent package
#   과거에 이 파일이 site-packages/openpifpaf/ 안에 있어야만 했고
#   'python -m openpifpaf.fall_detection' 으로만 실행되던 이유가 이것이다.
#   -m 으로 적재하면 __package__ 가 "openpifpaf" 로 설정되기 때문이다.
#
# [ from openpifpaf import ... ]  절대 임포트
#   패키지를 "이름"으로 찾으므로 sys.path 를 순서대로 뒤진다.
#   activate.bat 로 conda 환경(mmc)을 켜면 그 환경의 site-packages 가
#   sys.path 에 들어가고, openpifpaf 는 거기에 pip 으로 설치되어 있다.
#   즉 파일이 패키지 폴더 "안"에 있을 필요가 없고, 패키지를 "찾을 수만"
#   있으면 된다.
#
# 이 차이 덕분에 이 파일을 프로젝트 폴더에 둘 수 있게 되었다.
# conda 환경을 다시 만들어도 파일이 사라지지 않는다.
#
#   실행 : python fall_detection/fall_detection.py "<user_ID>"
#
from openpifpaf import decoder, logger, network, show, visualizer
from openpifpaf.predictor import Predictor

# ==================================================
# Debug log redirection
# ==================================================

def setup_debug_print_log(user_id):
    log_dir = os.path.join(os.getcwd(), "debug_logs")
    os.makedirs(log_dir, exist_ok=True)

    safe_user_id = re.sub(r'[\\/:*?"<>|]', "_", str(user_id)) if user_id else "unknown"

    log_path = os.path.join(log_dir, f"fall_detection_{safe_user_id}.log")

    log_file = open(log_path, "w", encoding="utf-8", buffering=1)

    sys.stdout = log_file
    sys.stderr = log_file

    print("============================================================")
    print(f"[DEBUG LOG START] {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"[DEBUG LOG FILE] {log_path}")
    print(f"[USER_ID] {user_id}")
    print(f"[ARGS] {' '.join(sys.argv)}")
    print("============================================================")

    return log_file

# ==================================================
# Global variables
# ==================================================

prev_score_value = 0.0
prev_error_code  = "0000"
prev_s0_gas      = 0.0
prev_s0_tmp      = 0.0

IMG_URL                       = None
TEST_IMG                      = None
PEOPLE_OUTPUT_PATH            = None
PEOPLE_SRCIMG_PATH            = None
FIRE_OUTPUT_PATH              = None
FIRE_SRCIMG_PATH              = None
FIRE_MODEL_PATH               = None
WAITING_TIME_PEOPLE_DETECTION = 1.0
THRESH_0_FALL_DOWN            = 45.0
THRESH_0_PERSON               = 0.3
LENGTH_HOTLIST                = 0

# ==================================================
# Logging
# ==================================================

LOG = logging.getLogger("openpifpaf")
LOG.setLevel(logging.ERROR)
LOG.propagate = False

# ==================================================
# Main loop
# ==================================================

def hide_window_by_title(title):
    """
    제목으로 창을 찾아 숨긴다. 윈도우에서만 동작한다.

    OpenCV 는 창을 숨기는 길을 내주지 않으므로 Win32 를 직접 부른다.
    실패해도 그냥 넘어간다 - 창이 잠깐 보이는 것뿐이고, 여기서 죽으면
    감시가 통째로 멎는다.
    """
    if os.name != "nt":
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.FindWindowW(None, ctypes.c_wchar_p(title))
        if not hwnd:
            return False
        SW_HIDE = 0
        user32.ShowWindow(hwnd, SW_HIDE)
        return True
    except Exception as e:
        print(f"[WARN] 뷰어 창을 숨기지 못했음: {e}")
        return False


# ==================================================

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("user_ID", help="user_ID under ./users, e.g. cj_busan_1")
    # 감시 프로그램(otg_monitoring)이 띄웠다는 표시.
    #
    # 이 표시가 있으면 뷰어 창을 만들자마자 숨긴다. 보일지 말지는 감시
    # 프로그램이 정한다. 사람이 터미널에서 직접 돌릴 때는 표시가 없으므로
    # 창이 평소대로 보인다.
    parser.add_argument("--managed", action="store_true",
                        help=argparse.SUPPRESS)

    decoder.cli(parser)
    network.Factory.cli(parser)
    Predictor.cli(parser)
    show.cli(parser)
    visualizer.cli(parser)

    args = parser.parse_args()

    env_conf         = Set_Env_Config(args.user_ID)
    sensor_db_config = Get_SensorDB_Config(env_conf)

    IMG_URL                       = env_conf.get("IMG_URL")
    TEST_IMG                      = env_conf.get("TEST_IMG")
    PEOPLE_OUTPUT_PATH            = env_conf.get("PEOPLE_OUTPUT_PATH")
    PEOPLE_SRCIMG_PATH            = env_conf.get("PEOPLE_SRCIMG_PATH")
    FIRE_OUTPUT_PATH              = env_conf.get("FIRE_OUTPUT_PATH")
    FIRE_SRCIMG_PATH              = env_conf.get("FIRE_SRCIMG_PATH")
    FIRE_MODEL_PATH               = env_conf.get("FIRE_MODEL_PATH")
    WAITING_TIME_PEOPLE_DETECTION = float(env_conf.get("WAITING_TIME_PEOPLE_DETECTION", 1.0))
    THRESH_0_FALL_DOWN            = float(env_conf.get("THRESH_0_FALL_DOWN", 45.0))
    THRESH_0_PERSON               = float(env_conf.get("THRESH_0_PERSON", 0.3))

    X_GRID         = int(env_conf["X_GRID"])
    Y_GRID         = int(env_conf["Y_GRID"])
    LENGTH_HOTLIST = X_GRID * Y_GRID

    print("============================================================")
    print("[CONFIG LOADED]")
    print(f"USER_ID                       : {args.user_ID}")
    print(f"IMG_URL                       : {IMG_URL}")
    print(f"PEOPLE_OUTPUT_PATH            : {PEOPLE_OUTPUT_PATH}")
    print(f"PEOPLE_SRCIMG_PATH            : {PEOPLE_SRCIMG_PATH}")
    print(f"FIRE_OUTPUT_PATH              : {FIRE_OUTPUT_PATH}")
    print(f"FIRE_SRCIMG_PATH              : {FIRE_SRCIMG_PATH}")
    print(f"FIRE_MODEL_PATH               : {FIRE_MODEL_PATH}")
    print(f"WAITING_TIME_PEOPLE_DETECTION : {WAITING_TIME_PEOPLE_DETECTION}")
    print(f"THRESH_0_FALL_DOWN            : {THRESH_0_FALL_DOWN}")
    print(f"THRESH_0_PERSON               : {THRESH_0_PERSON}")
    print(f"X_GRID                        : {X_GRID}")
    print(f"Y_GRID                        : {Y_GRID}")
    print(f"LENGTH_HOTLIST                : {LENGTH_HOTLIST}")
    print(f"SENSOR_DB                     : {sensor_db_config.get('database')}")
    print("============================================================")

    os.makedirs(PEOPLE_OUTPUT_PATH, exist_ok=True)
    os.makedirs(PEOPLE_SRCIMG_PATH, exist_ok=True)
    os.makedirs(FIRE_OUTPUT_PATH, exist_ok=True)
    os.makedirs(FIRE_SRCIMG_PATH, exist_ok=True)

    args.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[INFO] Device : {args.device}")

    decoder.configure(args)
    network.Factory.configure(args)
    Predictor.configure(args)
    show.configure(args)
    visualizer.configure(args)

    predictor = Predictor(
        visualize_image=False,
        visualize_processed_image=False
    )

    hotlist_mask = Get_db_hotlist_mask(sensor_db_config)

    from ultralytics import YOLO
    fire_model = YOLO(FIRE_MODEL_PATH)

    WINDOW_NAME = "HotList+Fire+Worker"
    cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)

    # 감시 프로그램이 띄운 경우에는 만들어지자마자 숨긴다.
    #
    # 현장이 둘이라 '시작' 을 누르면 뷰어도 둘 생긴다. 감시 프로그램은
    # 고르지 않은 현장의 창을 숨기지만, 그러려면 창이 먼저 있어야 해서
    # 몇 초간 두 창이 다 보였다가 하나가 사라졌다. 만들 때부터 숨겨 두면
    # 그 중간 과정이 없어진다. 보일 창은 감시 프로그램이 곧 띄운다.
    if getattr(args, "managed", False):
        hide_window_by_title(WINDOW_NAME)

    while True:
        try:
            now_time = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

            # ---------------- image input ----------------
            input_img = Get_Input_Image_URL(IMG_URL)

            if input_img is None:
                #print(f"[ERROR] ({now_time}) input_img is None")
                time.sleep(WAITING_TIME_PEOPLE_DETECTION)
                continue

            # ---------------- fire / smoke ----------------

            fire_results = fire_model.predict(
                source=input_img,
                conf=0.25,
                iou=0.7,
                verbose=False,
            )

            fire_detections = draw_fire_smoke_detections(
                input_img,
                fire_results,
                fire_model.names
            )

            for cls_name, conf in fire_detections:
                print(f"[FIRE DETECT] ({now_time}) {cls_name} conf={conf:.2f}")

            # ---------------- fire / smoke area map ----------------

            h, w = input_img.shape[:2]
            fire_area, smoke_area = make_fire_smoke_map(
                X_GRID, Y_GRID, h, w, input_img, fire_results, fire_model.names
            )

            # ---------------- HOTLIST (MySQL) ----------------

            hotlist_values, timestamp = read_from_current_value_median(sensor_db_config)

            if hotlist_values.size == LENGTH_HOTLIST:
                hotlist_values = hotlist_values.flatten()
            else:
                print(
                    f"[WARN] hotlist_values size mismatch. "
                    f"got={hotlist_values.size}, expected={LENGTH_HOTLIST}"
                )
                hotlist_values = np.zeros(LENGTH_HOTLIST, dtype=np.float32)

            # ---------------- person detection ----------------

            tmp_name = None

            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                tmp_name = tmp.name
                cv2.imwrite(tmp_name, input_img)

            try:
                pred         = None
                people_count = 0
                fall_people  = 0

                for pred, _, meta in predictor.images([tmp_name]):

                    if isinstance(pred, (list, tuple)):
                        for idx, person_pred in enumerate(pred, start=1):

                            person_conf = get_person_confidence(person_pred)

                            if person_conf is None:
                                print(f"{now_time} skip! Conf: None")
                                continue

                            if person_conf < THRESH_0_PERSON:
                                print(f"{now_time} skip! Conf:{person_conf:.2f}")
                                continue

                            people_count += 1

                            fall_kps = build_fall_keypoints(person_pred)
                            bFallDown, fall_angle = is_fall(fall_kps, THRESH_0_FALL_DOWN)

                            angle_str = f"{fall_angle:.2f}" if fall_angle is not None else "N/A"

                            if fall_kps and bFallDown:
                                fall_people += 1

                            print(
                                f"{now_time} "
                                f"[Person #{idx} Conf:{person_conf:.2f} "
                                f"Fall_Down:{bFallDown} "
                                f"Angle:{angle_str}]"
                            )

                # ---------------- visualization ----------------

                image_vis, should_quit = show_analysis_results(
                    env_conf,
                    sensor_db_config,
                    input_img.copy(),
                    WINDOW_NAME,
                    pred,
                    hotlist_values,
                    hotlist_mask,
                    people_count,
                    fall_people,
                    fire_area,
                    smoke_area
                )

                if people_count > 0:
                    cv2.imwrite(
                        os.path.join(PEOPLE_OUTPUT_PATH, f"result_{now_time}.jpg"),
                        image_vis,
                    )
                    cv2.imwrite(
                        os.path.join(PEOPLE_SRCIMG_PATH, f"src_{now_time}.jpg"),
                        input_img,
                    )

                if fire_detections:
                    # fire/smoke가 함께 검출되면 "fire_smoke"처럼 둘 다 파일명에 남긴다
                    detected_classes = sorted({cls_name for cls_name, _ in fire_detections})
                    tag = "_".join(detected_classes)

                    cv2.imwrite(
                        os.path.join(FIRE_OUTPUT_PATH, f"result_{tag}_{now_time}.jpg"),
                        image_vis,
                    )
                    cv2.imwrite(
                        os.path.join(FIRE_SRCIMG_PATH, f"src_{tag}_{now_time}.jpg"),
                        input_img,
                    )

                if should_quit:
                    print("[INFO] ESC pressed. fall_detection stopped.")
                    break

            finally:
                if tmp_name is not None and os.path.exists(tmp_name):
                    os.remove(tmp_name)

            # ---------------- MySQL write ----------------
            # fire_area 와 smoke_area 를 element-wise max 로 병합하여
            # fire_list 하나에 저장 (원래 크기 유지)

            merged_fire_list = [max(f, s) for f, s in zip(fire_area, smoke_area)]

            update_sensor_db_table(
                sensor_db_config,
                people_count,
                fall_people,
                merged_fire_list,
            )

            time.sleep(WAITING_TIME_PEOPLE_DETECTION)

        except KeyboardInterrupt:
            print("[INFO] KeyboardInterrupt. fall_detection stopped.")
            break

        except Exception as e:
            print(f"[ERROR] Main loop exception: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(WAITING_TIME_PEOPLE_DETECTION)


# ==================================================

def show_analysis_results(
    env_conf,
    sensor_db_config,
    image_vis,
    WINDOW_NAME,
    pred,
    hotlist_values,
    hotlist_mask,
    people_count,
    fall_people,
    fire_area,
    smoke_area
):
    global prev_score_value
    global prev_error_code
    global prev_s0_gas
    global prev_s0_tmp

    if people_count > 0:
        draw_skeletons(image_vis, pred)

    OK, score_value, error_code = read_db_current_status(sensor_db_config)

    if not OK:
        score_value = prev_score_value
        error_code  = prev_error_code
    else:
        prev_score_value = score_value
        prev_error_code  = error_code

    image_vis = draw_image_grid(
        env_conf,
        image_vis,
        fire_area,
        smoke_area,
        hotlist_values,
        hotlist_mask,
        (250, 250, 250),
        (0, 0, 255),
        (255, 0, 0),
        1
    )

    jobID   = env_conf.get("USER_ID")
    err_str = error_code if error_code is not None else "None"

    # caption의 F=는 낙상(fall) 인원수이며 fire와는 무관하다.
    # fire/smoke 검출 여부를 caption에서도 바로 볼 수 있도록 최대 confidence를 표시한다.
    fire_conf  = max(fire_area, default=0.0)
    smoke_conf = max(smoke_area, default=0.0)

    if int(env_conf.get("SLAVE_NUM", 0)) > 0:
        s0_gas, s0_tmp, s0_hum = read_slave_sensor(sensor_db_config)

        prev_s0_gas = s0_gas if s0_gas is not None else prev_s0_gas
        prev_s0_tmp = s0_tmp if s0_tmp is not None else prev_s0_tmp
        s0_gas      = prev_s0_gas
        s0_tmp      = prev_s0_tmp

        t_score = f"{score_value:.2f}"
        if(score_value<0) : t_score = '[ERROR]'

        caption = (
            f"[{jobID:>5s}]  "
            f"S={t_score}  "
            f"E={err_str}  "
            f"P={people_count}  "
            f"F={fall_people}  "
            f"FR={fire_conf:.1f}  "
            f"SM={smoke_conf:.1f}  "
            f"SG={s0_gas:.1f}  "
            f"ST={s0_tmp:.1f}"
        )
        print(f"[SLAVE] gas={s0_gas:.1f}ppm  temp={s0_tmp:.1f}C  humi={s0_hum:.1f}%")

    else:
        caption = (
            f"[{jobID:>5s}]  "
            f"S={score_value:.2f}  "
            f"E={err_str}  "
            f"P={people_count}  "
            f"F={fall_people}  "
            f"FR={fire_conf:.1f}  "
            f"SM={smoke_conf:.1f}"
        )

    zoom_out = 0.7

    cv2.setWindowTitle(WINDOW_NAME, caption)

    h0, w0 = image_vis.shape[:2]
    aspect_ratio = h0 / w0

    # caption에 항목(S/E/P/F/FR/SM 등)이 늘어나면 타이틀바 폭 제한으로 잘리므로,
    # 창 폭을 MIN_WINDOW_WIDTH 이상으로 넓히되, 원본 이미지의 종횡비를 그대로 유지해
    # 높이도 같은 비율로 늘린다.
    window_width  = max(int(w0 * zoom_out), MIN_WINDOW_WIDTH)
    window_height = int(window_width * aspect_ratio)

    display_img = cv2.resize(
        image_vis,
        (window_width, window_height),
        interpolation=cv2.INTER_AREA
    )

    cv2.resizeWindow(WINDOW_NAME, window_width, window_height)

    # 감시 프로그램(otg_monitoring)이 선택된 user의 창만 남기고 나머지는 숨기므로,
    # 좌석 번호(MONITOR_SEAT_ORDER)만큼 오른쪽으로 밀 이유가 없다.
    # 보이는 창을 항상 화면 왼쪽 끝부터 채우도록 x=0에 붙인다.
    # 같은 user의 열화상 창(server_to_db, SHOW_THERMAL_IMG)이 그 오른쪽에 이어진다.
    cv2.moveWindow(WINDOW_NAME, 0, 0)
    cv2.imshow(WINDOW_NAME, display_img)

    if cv2.waitKey(1) & 0xFF == 27:
        return image_vis, True

    return image_vis, False


# ==================================================

if __name__ == "__main__":

    pre_user_id    = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    debug_log_file = setup_debug_print_log(pre_user_id)

    time.sleep(5)

    try:
        main()

    except SystemExit:
        raise

    except Exception as e:
        print(f"[FATAL] fall_detection terminated by exception: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        try:
            print("============================================================")
            print(f"[DEBUG LOG END] {time.strftime('%Y-%m-%d %H:%M:%S')}")
            print("============================================================")
            debug_log_file.close()
        except Exception:
            pass