#
# python predict_machine/predict_machine.py cj_busan_1
# JSON-based MySQL schema compatible version
#

import numpy as np
import torch
import torch.nn as nn
import joblib
import os
import time
import sys
import requests
import argparse
import re
import traceback
from datetime import datetime
from sklearn.preprocessing import StandardScaler

# ==================================================
# 프로젝트 모듈(source 폴더) 연결 : sys.path 를 직접 넣는 이유
# ==================================================
#
# 이 파일은 predict_machine/ 폴더에 있고, 쓰려는 모듈(db_utils, cv_utils 등)은
# source/ 폴더에 있다. 서로 다른 폴더다.
#
# 파이썬이 스크립트를 실행하면 sys.path[0] 에 "그 스크립트가 있는 폴더"를
# 자동으로 넣는다. 실행할 때 cd 로 이동한 현재 폴더가 아니다.
#   실행 : (D:/MultiModal_FireCam 에서) python predict_machine/predict_machine.py
#   결과 : sys.path[0] = D:/MultiModal_FireCam/predict_machine
# 즉 source/ 는 저절로 들어오지 않으므로 직접 넣어 주어야 한다.
#
# [ 경로를 상수로 박으면 안 되는 이유 ]
#   예전에는 이렇게 되어 있었다.
#       sys.path.insert(0, r"D:\multi_modal\source")
#   그 폴더가 사라지자 경로 추가가 무효가 되었고, import db_utils 가 계속
#   내려가다 site-packages 에 설치된 "동명의 무관한 PyPI 패키지 db_utils"를
#   집어버렸다. 이름이 같아 임포트 자체는 성공하고, 함수가 없어서 죽는다.
#       ImportError: cannot import name 'read_from_current_value_median'
#                    from 'db_utils' (.../site-packages/db_utils/__init__.py)
#   에러 메시지가 원인(경로가 틀림)을 전혀 가리키지 않아 찾기 어렵다.
#
# [ 그래서 실행 환경에서 찾아낸다 ]
#   아래 _resolve_source_dir() 는 후보를 순서대로 보며 db_utils.py 가 실제로
#   있는 폴더만 고른다. 잘못된 경로를 넣어 PyPI 패키지가 끼어드는 일을 막는다.
#     1) 환경변수 MMCAM_ROOT    2) 현재 작업 폴더    3) 이 파일 기준 상위 폴더
#
# 참고: source/ 안에 있는 파일들(server_to_db.py 등)은 sys.path[0] 이 곧
#       source/ 이므로 이런 처리가 필요 없다.
#
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

from db_utils import (
    read_from_current_value_median,
    read_people_and_area,
    read_slave_sensor,
    read_main_sensor,
    Append_History_DB,
    update_db_current_status,
    update_db_error_code,
    update_db_hotlist_mask,
    read_db_error_code,
    read_db_main_command,
    update_db_main_command,
    delete_files_of_Base_Img,
    Set_Env_Config,
    Get_SensorDB_Config,
    Get_HistoryDB_Config,
    Read_GridMask_Inf_File,
    Connect_History_DB,
)

from cv_utils import (
    Get_Adjusted_HotMask_Position,
    Get_Input_Image_URL,
    save_base_image
)

from constants import ERR_CODE, SVR_CMD, LOCAL_HOTLIST_MASK, SVR_HOTLIST_MASK

# 연속 학습 0~1단계. 이 둘은 predict_machine 폴더 안에 있으므로 sys.path[0]
# (= 이 스크립트의 폴더) 으로 그냥 잡힌다. source 폴더와 달리 경로 조작이
# 필요 없다.
from abs_threshold import AbsoluteThreshold, LEVEL_ALARM, LEVEL_WARN, level_name
from online_baseline import OnlineBaseline, SCENE_SHIFT_MIN
import stage_status
import thermal_shift


# ==============================================
# Download grid mask from server
# ==============================================

def Download_Grid_Mask_from_SVR(root_url, network_id, local_path):
    if not root_url or not network_id:
        print("[DOWNLOAD] Error: 'root_url' or 'network_id' is missing in config.")
        return False

    target_url = f"{root_url.rstrip('/')}/{network_id}/{SVR_HOTLIST_MASK}"

    print(f"[DOWNLOAD] SVR_HOTLIST_MASK from: {target_url}")

    try:
        response = requests.get(target_url, timeout=10)
        response.raise_for_status()

        with open(local_path, "wb") as f:
            f.write(response.content)

        print("[DOWNLOAD] Grid Mask from Server -> Success")
        print(f"[DOWNLOAD] Saved path: {local_path}")

        return True

    except requests.exceptions.HTTPError as http_err:
        print(f"[DOWNLOAD] HTTP Error occurred: {http_err}")

    except Exception as e:
        print(f"[DOWNLOAD] Failed to download grid mask: {e}")

    return False

# ==================================================
# Debug log redirection
# ==================================================

def setup_debug_print_log(user_id):
    log_dir = os.path.join(os.getcwd(), "debug_logs")
    os.makedirs(log_dir, exist_ok=True)

    safe_user_id = re.sub(r'[\\/:*?"<>|]', "_", str(user_id)) if user_id else "unknown"

    log_path = os.path.join(
        log_dir,
        f"predict_machine_{safe_user_id}.log"
    )

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
# Device
# ==================================================

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")


# ==================================================
# AutoEncoder global variables
# ==================================================

INPUT_DIM = 0
OUTPUT_DIM = 0
LATENT_DIM = 0
LENGTH_HOTLIST = 0
NUM_OF_MACHINE_CELLS = 0

# autoencoder-7.py와 반드시 동일해야 함 (다르면 state_dict 로드가 깨짐)
ENC_HIDDEN = [32, 16]

# 오토인코더 점수와 기준선 점수가 이만큼 갈리면 불일치로 본다.
SCORE_DIVERGENCE_WARN = 0.3

# 다만 차이가 크다고 다 불일치가 아니다. 한쪽이 0.0006, 다른 쪽이 0.35 면
# 차이는 크지만 **둘 다 이상을 말하고 있다** — 민감도가 다를 뿐이다.
# 여기에 "카메라를 확인하라" 는 안내를 띄우면 실제 과열을 오진하게 된다.
#
# 진짜 불일치는 한쪽이 이상이라 하는데 다른 쪽은 **멀쩡하다고** 할 때다.
# 그래서 높은 쪽이 이 값 이상일 때만 불일치로 판정한다.
SCORE_NORMAL_SIDE = 0.9


# ============================================================
# AutoEncoder
# ============================================================

class AutoEncoder(nn.Module):
    def __init__(self, input_dim, latent_dim, output_dim):
        super().__init__()

        # Encoder
        encoder_layers = []
        prev_dim = input_dim

        for h in ENC_HIDDEN:
            encoder_layers.append(nn.Linear(prev_dim, h))
            encoder_layers.append(nn.ReLU())
            prev_dim = h

        encoder_layers.append(nn.Linear(prev_dim, latent_dim))
        self.encoder = nn.Sequential(*encoder_layers)

        # Decoder
        decoder_layers = []
        prev_dim = latent_dim

        for h in reversed(ENC_HIDDEN):
            decoder_layers.append(nn.Linear(prev_dim, h))
            decoder_layers.append(nn.ReLU())
            prev_dim = h

        decoder_layers.append(nn.Linear(prev_dim, output_dim))
        self.decoder = nn.Sequential(*decoder_layers)

    def forward(self, x):
        z = self.encoder(x)
        out = self.decoder(z)
        return out


# ==================================================
# Scaler 로드
# ==================================================
# numpy 2.x 환경(otg 등)에서 저장된 scaler.pkl은 이 프로세스가 쓰는 numpy 1.x(mmc 환경)에서
# "No module named 'numpy._core'"로 unpickle이 실패한다. 이런 경우 같은 폴더의
# scaler.npz(mean_/scale_/var_ 등 순수 배열만 저장, numpy 버전 무관하게 로드 가능)로 대체한다.
def load_scaler(path):
    try:
        return joblib.load(path)
    except ModuleNotFoundError as e:
        if "numpy._core" not in str(e):
            raise

        npz_path = os.path.splitext(path)[0] + ".npz"
        if not os.path.exists(npz_path):
            raise RuntimeError(
                f"[scaler] {path} 는 이 환경의 numpy 버전과 호환되지 않는 pickle이고, "
                f"대체 파일 {npz_path} 도 없습니다."
            ) from e

        # npz가 pkl보다 "의미 있게" 오래됐다면(=pkl이 재학습으로 갱신된 뒤 npz를 안 만든 경우),
        # 차원이 우연히 같아도 실제 평균/분산 값은 이전 학습 결과일 수 있다.
        # 조용히 잘못된 스케일러를 쓰는 대신 명확히 실패시킨다.
        #
        # 단, 두 파일을 한 번에 복사하면 기록 순서 때문에 수십 밀리초 차이가 그냥 생긴다.
        # 그 정도로 실패시키면 배포할 때마다 멈추므로 여유를 둔다.
        # 실제 재학습이면 최소 몇 분은 차이가 나므로 이 여유로 놓치지 않는다.
        STALE_TOLERANCE_SEC = 60
        stale_by = os.path.getmtime(path) - os.path.getmtime(npz_path)
        if stale_by > STALE_TOLERANCE_SEC:
            raise RuntimeError(
                f"[scaler] {npz_path} 가 {path} 보다 {stale_by:.0f}초 오래됐습니다. "
                f"scaler.pkl이 재학습으로 갱신된 뒤 scaler.npz를 다시 만들지 않은 것으로 보입니다. "
                f"otg 환경에서 scaler.npz를 다시 생성하세요."
            )

        data = np.load(npz_path)
        scaler = StandardScaler()
        scaler.mean_ = data["mean_"]
        scaler.scale_ = data["scale_"]
        scaler.var_ = data["var_"]
        scaler.n_features_in_ = int(data["n_features_in_"])
        scaler.n_samples_seen_ = data["n_samples_seen_"].item()
        scaler.with_mean = bool(data["with_mean"])
        scaler.with_std = bool(data["with_std"])
        return scaler


# ==================================================
# Normality score
# ==================================================

def normality_score(x_input, mask, scaler, model):

    print(x_input)
    print('x_input.shape[1] : ', x_input.shape[1])

    if (
        not isinstance(x_input, np.ndarray)
        or x_input.ndim != 2
        or x_input.shape[1] != INPUT_DIM
    ):
        print(
            f"[WARN] Dimension mismatch in normality_score. "
            f"Expected {INPUT_DIM}, "
            f"got {x_input.shape if isinstance(x_input, np.ndarray) else type(x_input)}"
        )
        return 0.0, 0.0, False

    model.eval()

    # mask는 모델 입력이 아니라 채점 대상 셀만 고르는 데 쓰인다.
    # mask가 바뀌어도 모델(입력 64차원 전체)은 그대로 두고, 여기서 어떤 셀의
    # 재구성 오차를 평균낼지만 바뀌므로 재학습이 필요 없다.
    mask_bool = torch.tensor(
        np.asarray(mask, dtype=np.int32) == 1,
        dtype=torch.bool,
        device=device
    )

    with torch.no_grad():
        x_scaled = scaler.transform(x_input)
        x_tensor = torch.tensor(
            x_scaled,
            dtype=torch.float32,
            device=device
        )
        x_hat = model(x_tensor)
        diff = (x_tensor - x_hat) ** 2
        mse = diff[:, mask_bool].mean(dim=1)
        score = torch.exp(-mse * 10)

    return float(score.item()), float(mse.item()), True


# ==================================================
# SMS
# ==================================================

TARGET_URL = "https://sangchoo.com/kict_samsung_test/assets/send_sms.php"


def send_event_message(event_code: str) -> bool:
    try:
        r = requests.post(
            TARGET_URL,
            data={"smsTxt": event_code},
            timeout=10,
            verify=False,
        )
        return r.status_code == 200

    except Exception as e:
        print(f"[ERROR] send_event_message failed: {e}")
        return False


# ==================================================
# Machine Area 검증
# mask가 바뀌어도 재학습이 필요 없도록, 여기서는 더 이상 mask로 64차원을
# 16차원으로 잘라내지 않는다. median_hot(64)과 mask(64)를 검증만 하고
# 64차원 전체를 그대로 돌려주며, mask는 normality_score의 채점 단계에서만 쓰인다.
# ==================================================

def extract_mach_area(median_hot, mask):
    median_hot = np.asarray(median_hot, dtype=np.float32)

    if median_hot.ndim == 2:
        median_hot = median_hot.flatten()

    if median_hot.shape[0] != LENGTH_HOTLIST:
        print(
            f"[FATAL] median_hot length mismatch: "
            f"expected {LENGTH_HOTLIST}, got {median_hot.shape[0]}"
        )
        print("Program Terminated")
        sys.exit(1)

    mask = np.asarray(mask, dtype=np.int32)

    if mask.shape[0] != LENGTH_HOTLIST:
        print(
            f"[FATAL] MACH_AREA_MASK length mismatch: "
            f"\n expected {LENGTH_HOTLIST} (X_GRID*Y_GRID), got {mask.shape[0]}. "
            f"\n hotlist_mask_local.ini 또는 DB의 mask_list 길이를 확인하세요."
        )
        print("Program Terminated")
        sys.exit(1)

    if not np.all((mask == 0) | (mask == 1)):
        print("[FATAL] MACH_AREA_MASK values must be 0 or 1")
        print("Program Terminated")
        sys.exit(1)

    ones_count = int(np.sum(mask))

    # 학습 파이프라인(apply_mask_extract.py)과 동일한 기준: 1 개수가 NUM_OF_MACHINE_CELLS와
    # 정확히 일치해야 하며, 그렇지 않으면 패딩/자르기로 얼버무리지 않고 제외(FATAL)한다.
    if ones_count != NUM_OF_MACHINE_CELLS:
        print(
            f"[FATAL] MACH_AREA_MASK ones count ({ones_count}) != "
            f"\n NUM_OF_MACHINE_CELLS ({NUM_OF_MACHINE_CELLS}). "
            f"\n env.ini 의 NUM_OF_MACHINE_CELLS 값을 hotlist_mask 의 1 개수와 맞추거나, "
            f"\n hotlist_mask 를 다시 작성하세요."
        )
        print("Program Terminated")
        sys.exit(1)

    return median_hot.reshape(1, LENGTH_HOTLIST)


# ==================================================

def Check_Status_of_HotList_Mask(hotlist_mask, x_grid, BASE_IMG_DIR, input_img):

    print("-" * 50)

    if hotlist_mask is None:
        print("[ERROR] MACH_AREA_MASK file not found")
        sys.exit(1)

    y_grid = len(hotlist_mask) // x_grid

    bShifted, hotlist_mask, shift_x, shift_y = Get_Adjusted_HotMask_Position(BASE_IMG_DIR, input_img, hotlist_mask, x_grid, y_grid)

    MAX_SHIFT = 2
    if abs(shift_x) >= MAX_SHIFT or abs(shift_y) >= MAX_SHIFT:
        print("[ERROR] Check_Status_of_HotList_Mask - Camera Movement Error")
        print("Program Terminated")
        sys.exit(1)

    print(f"[Check_Status_of_HotList_Mask] bShifted {bShifted} "
          f"shift_x {shift_x} shift_y {shift_y}")
    print("-" * 50)

    # 이동량도 함께 돌려준다. 예전에는 여기서 버려서, 계산해 놓고도 화면에
    # 보여줄 방법이 없었다. [설정] 영역이 이 값을 읽어 버튼 옆에 적는다.
    return bShifted, hotlist_mask, shift_x, shift_y

# ==================================================

def write_file_hotlist_mask(local_path, hotlist_mask):
    values = np.asarray(hotlist_mask).flatten()

    with open(local_path, "w", newline="\n") as f:
        for v in values:
            f.write(f"{int(v)}\n")

# ==================================================
# Main loop
# ==================================================

def main_loop(config, sensor_db_config):

    global INPUT_DIM
    global OUTPUT_DIM
    global LATENT_DIM
    global LENGTH_HOTLIST
    global NUM_OF_MACHINE_CELLS

    NUM_OF_MACHINE_CELLS = int(config["NUM_OF_MACHINE_CELLS"])
    LATENT_DIM = int(config["SZ_OF_LATENT_DIM_AUTOENCODER"])

    X_GRID = int(config["X_GRID"])
    Y_GRID = int(config["Y_GRID"])
    LENGTH_HOTLIST = X_GRID * Y_GRID

    # 모델은 이제 mask로 미리 자르지 않은 64차원(LENGTH_HOTLIST) 전체를 학습/추론한다.
    # mask는 더 이상 모델 입력 크기를 바꾸지 않으므로, mask가 바뀌어도 재학습이 필요 없다.
    INPUT_DIM = LENGTH_HOTLIST
    OUTPUT_DIM = INPUT_DIM

    BASE_IMG_DIR = config["BASE_IMG_DIR"]

    IMG_URL = config["IMG_URL"]
    HotListMask_LocalPath = config["LOCAL_USER_PATH"] + LOCAL_HOTLIST_MASK
    WAITING_TIME = float(config.get("WAITING_TIME_GET_SVR_HOTLIST", 1.0))
    WAITING_TIME_PEOPLE_DETECTION = config.get("WAITING_TIME_PEOPLE_DETECTION")
    ENABLE_SMS_ALERTS = config.get("ENABLE_SMS_ALERTS", False)

    MODEL_PATH  = os.path.join(config["LOCAL_USER_PATH"], "autoencoder_final.pth")
    SCALER_PATH = os.path.join(config["LOCAL_USER_PATH"], "scaler.pkl")

    history_db_config = Get_HistoryDB_Config(config)

    print("============================================================")
    print("[CONFIG LOADED]")
    print(f"USER_ID              = {config.get('USER_ID')}")
    print(f"NUM_OF_MACHINE_CELLS = {NUM_OF_MACHINE_CELLS}")
    print(f"INPUT_DIM            = {INPUT_DIM}")
    print(f"LATENT_DIM           = {LATENT_DIM}")
    print(f"OUTPUT_DIM           = {OUTPUT_DIM}")
    print(f"X_GRID               = {X_GRID}")
    print(f"Y_GRID               = {Y_GRID}")
    print(f"LENGTH_HOTLIST       = {LENGTH_HOTLIST}")
    print(f"MODEL_PATH           = {MODEL_PATH}")
    print(f"SCALER_PATH          = {SCALER_PATH}")
    print(f"SENSOR_DB            = {sensor_db_config.get('database')}")
    print(f"HISTORY_DB           = {history_db_config.get('database')}")
    print(f"BASE_IMG_DIR         = {BASE_IMG_DIR}")
    print("============================================================")

    # ------------------------------------------------------------------
    # 단계별 기동 (연속 학습)
    #
    # 예전에는 모델 파일이 없으면 여기서 sys.exit(1) 로 죽었다. 그래서 새로
    # 설치한 현장은 수 주간 데이터를 모아 오토인코더를 만들기 전까지 감시
    # 자체가 불가능했다. 이제는 준비된 만큼만 쓰고 계속 동작한다.
    #
    #   0단계  절대 임계값        학습 0건. 설치 즉시.
    #   1단계  셀별 온라인 통계    수 시간 후. z-score 채점.
    #   2단계  오토인코더          모델이 준비되면. 셀 간 결합 분포까지.
    #
    # 0단계는 이후 단계에서도 계속 살아 있다. 학습 기반 판정이 모두 실패해도
    # 고정된 선 하나는 남아 있어야 하기 때문이다.
    # ------------------------------------------------------------------

    abs_guard = AbsoluteThreshold(config)
    print(f"[STAGE 0] {abs_guard.describe()}")

    if not abs_guard.enabled:
        print("[STAGE 0] 경고 — 절대 임계값이 지정되지 않아 0단계 경보가")
        print("          동작하지 않습니다. 설비의 정상 가동 온도를 확인해")
        print("          env.ini 의 [CONSTANTS] 에 ABS_TEMP_WARN/ALARM 과")
        print("          ABS_RISE_WARN/ALARM 을 지정하십시오.")
        print("          값을 모르면 하루쯤 돌려 기준선이 쌓이기를 기다리십시오.")
        print("          아래에 이 현장에서 관측된 권장값을 출력합니다.")

    BASELINE_PATH = os.path.join(config["LOCAL_USER_PATH"], "online_baseline.npz")
    baseline = OnlineBaseline.load(
        BASELINE_PATH, INPUT_DIM,
        min_samples=config.get("BASELINE_MIN_SAMPLES"),
        min_hours=config.get("BASELINE_MIN_HOURS"),
        base_date=config.get("CALC_BASE_DATE"),
    )
    print(f"[STAGE 1] 셀별 기준선 — {baseline.summary()}")

    # 열화상 기준 틀어짐 감시. RGB 검사와 별개로 둔다. 두 카메라가 같이
    # 움직인다는 보장이 없고(kict1 은 열화상만 밀렸다), RGB 검사는 기동할
    # 때 한 번뿐이라 운전 중에 밀린 것은 잡지 못한다.
    tshift = thermal_shift.ThermalShiftWatch(
        config["LOCAL_USER_PATH"], X_GRID, Y_GRID)

    model = None
    scaler = None

    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
        print("[STAGE 2] 오토인코더 없음 — 0~1단계로 동작합니다.")
        print("          데이터가 쌓이면 히스토리 DB로 학습해 배치하십시오.")
    else:
        try:
            m = AutoEncoder(INPUT_DIM, LATENT_DIM, OUTPUT_DIM).to(device)
            m.load_state_dict(torch.load(MODEL_PATH, map_location=device))
            sc = load_scaler(SCALER_PATH)

            # load_scaler()가 numpy 버전 문제로 scaler.pkl 대신 scaler.npz로 조용히
            # 폴백할 수 있는데, npz가 예전(다른 차원) 학습에서 남은 것이면 모델과
            # 안 맞는 스케일러를 쓰게 된다. 시작 시점에 한 번 명확히 걸러낸다.
            if getattr(sc, "n_features_in_", None) != INPUT_DIM:
                # 예전에는 여기서 종료했다. 이제는 오토인코더만 포기하고
                # 0~1단계로 계속 간다. 짝이 안 맞는 모델로 채점하는 것보다
                # 낫고, 감시를 통째로 멈추는 것보다도 낫다.
                print(
                    f"[STAGE 2] scaler 의 n_features_in_="
                    f"{getattr(sc, 'n_features_in_', None)} 가 INPUT_DIM({INPUT_DIM})과 "
                    f"다릅니다. 오토인코더를 쓰지 않고 0~1단계로 동작합니다."
                )
            else:
                model, scaler = m, sc
                print(f"[STAGE 2] 오토인코더 사용 "
                      f"(INPUT_DIM={INPUT_DIM}, LATENT_DIM={LATENT_DIM})")

        except Exception as e:
            print(f"[STAGE 2] 오토인코더를 읽지 못해 0~1단계로 동작합니다: {e}")

    baseline_dirty = 0
    suggested_once = False
    STATUS_PATH = os.path.join(config["LOCAL_USER_PATH"],
                               stage_status.STATUS_FILE_NAME)
    db_rows = db_tables = None
    db_counted_at = 0.0
    status_written_at = 0.0   # 0 이면 첫 프레임에서 바로 한 번 남긴다
    prev_fire_detected = False

    input_img = Get_Input_Image_URL(IMG_URL)

    if input_img is None:
        print("[ERROR] input_img not found")
        print("Program Terminated")
        sys.exit(1)

    # HotListMask 를 변경하는 경우 먼저 로컬에 존재하는 HotListMask_LocalPath 파일을 제거함
    # 해당 파일이 없는 경우 서버에서 자동으로 다운로드 받아서 사용함
    # HotListMask_LocalPath 이 존재하는 경우, NAS 에서 새로운 HotListMask 파일이 있어도 다운로드 하지 않음
    if not os.path.exists(HotListMask_LocalPath):
        Download_Grid_Mask_from_SVR(config["ROOT_URL"], config["USER_ID"], HotListMask_LocalPath)

    cur_hotlist_mask = Read_GridMask_Inf_File(HotListMask_LocalPath, X_GRID)

    # 마스크의 1 개수를 NUM_OF_MACHINE_CELLS 와 사전에 비교하여 조기에 명확히 종료
    if cur_hotlist_mask is not None:
        cur_ones_count = int(np.sum(np.asarray(cur_hotlist_mask, dtype=np.int32) == 1))
        if cur_ones_count != NUM_OF_MACHINE_CELLS:
            print(
                f"\n[FATAL] {HotListMask_LocalPath} 의 1 개수({cur_ones_count})가 "
                f"\nNUM_OF_MACHINE_CELLS({NUM_OF_MACHINE_CELLS})와 다릅니다. "
                f"\nenv.ini 의 NUM_OF_MACHINE_CELLS 값을 확인하거나 hotlist_mask 를 다시 작성하세요."
            )
            print("Program Terminated")
            sys.exit(1)

    bShifted, new_hotlist_mask, shift_x, shift_y = Check_Status_of_HotList_Mask(
        cur_hotlist_mask, X_GRID, BASE_IMG_DIR, input_img)

    # 이 검사는 기동할 때 한 번만 한다. 루프 안에서는 다시 재지 않으므로
    # 아래 값들은 "언제 잰 것인지" 와 함께 현황 파일에 그대로 실려 나간다.
    shift_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    if bShifted:
        main_command = read_db_main_command(sensor_db_config)
        print("Command from Server:", main_command)

        if main_command == SVR_CMD.ADJUST_MACHINE_GRID:  # 카메라 이동으로 이미지의 위치가 전과 다른 경우
            hotlist_mask = new_hotlist_mask
            write_file_hotlist_mask(HotListMask_LocalPath, hotlist_mask)
            delete_files_of_Base_Img(config)
            save_base_image(BASE_IMG_DIR, input_img)
            # 지금 보이는 화면이 앞으로의 정상이라는 뜻이므로, 열화상 기준
            # 패턴도 함께 버린다. RGB 기준 이미지만 새로 잡고 열화상 쪽을
            # 두면 보정한 그 순간부터 "밀렸다" 고 계속 짖는다.
            tshift.reset()
            update_db_error_code(sensor_db_config, ERR_CODE.NO_ERR)
            update_db_main_command(sensor_db_config, SVR_CMD.NO_ACTION)

        else:
            hotlist_mask = cur_hotlist_mask
            update_db_error_code(sensor_db_config, ERR_CODE.CAMERA_POSITION_SHIFT)
            print("[WARN] Camera position shifted — error_code updated")

    else:
        hotlist_mask = cur_hotlist_mask
        update_db_error_code(sensor_db_config, ERR_CODE.NO_ERR)

    update_db_hotlist_mask(sensor_db_config, hotlist_mask)

    # ---------- Real-time inference loop ----------
    while True:
        try:
            cur_error_code = read_db_error_code(sensor_db_config)

            median_hot, ts = read_from_current_value_median(sensor_db_config)

            if median_hot.size == 0:
                time.sleep(WAITING_TIME)
                continue

            machine_score = -1
            machine_mse   = -1
            valid         = False

            
            #print('---------------------')
            #print(median_hot)
            #median_hot[0,10]=36
            #median_hot[0,17]=36 
            #median_hot[0,18]=90       
            #median_hot[0,19]=90  

            #print(median_hot)
            print('cur_error_code ; ',cur_error_code)


            stage_used = 0
            abs_level = 0
            abs_reason = ""

            if cur_error_code == ERR_CODE.NO_ERR:
                x_full = extract_mach_area(median_hot, hotlist_mask)
                x_row = np.asarray(x_full, dtype=np.float64).reshape(-1)

                # --- 0단계. 학습과 무관하게 항상 먼저 본다 ---------------
                abs_level, abs_reason, peak_t, rise_t, abs_cell = abs_guard.check(
                    x_row, hotlist_mask, time.time()
                )

                if abs_level:
                    print(f"[절대임계] {level_name(abs_level)} — {abs_reason} "
                          f"(셀 {abs_cell})")

                # --- 두 판정을 함께 낸다 ---------------------------------
                #
                # 예전에는 오토인코더가 있으면 기준선 채점을 아예 건너뛰었다.
                # kict1 에서 그 설계의 약점이 드러났다. 카메라가 틀어진 뒤
                # 오토인코더가 0.003 을 계속 내놓았는데, 설비가 이상해서가
                # 아니라 모델이 보는 위치가 달라졌기 때문이었다. 그때 기준선이
                # 함께 채점하고 있었다면 "마스크 셀 온도 자체는 정상 범위" 라는
                # 두 번째 의견이 나와, 설비가 아니라 모델 쪽 문제라는 것을
                # 훨씬 일찍 가리켰을 것이다.
                #
                # 두 판정은 보는 것이 다르다.
                #   기준선     이 셀이 이렇게 뜨거운 적 있었나 (직접적, 해석 가능)
                #   오토인코더 셀들의 조합이 평소 같은가 (미묘하지만 통째로 틀릴 수 있음)
                #
                # 그래서 둘 다 계산하고 낮은 쪽을 점수로 쓴다. 화재 감지에서는
                # 보수적인 쪽이 안전하다. 기준선은 어차피 매 프레임 갱신되고
                # 있어 score() 한 번 더 부르는 비용뿐이다.
                ae_score = None
                bl_score = None
                exceed = 0.0
                worst = -1

                if model is not None and scaler is not None:
                    score_list, mse_list, valid = normality_score(
                        x_full, hotlist_mask, scaler, model
                    )
                    ae_score = float(np.mean(score_list))
                    machine_mse = float(np.mean(mse_list))

                if baseline.is_ready():
                    bl_score, exceed, worst = baseline.score(x_row, hotlist_mask)

                if ae_score is not None and bl_score is not None:
                    machine_score = min(ae_score, bl_score)
                    stage_used = 2
                    print(f"[채점] 오토인코더 {ae_score:.4f} / "
                          f"기준선 {bl_score:.4f} (초과 {exceed:+.1f}도, 셀 {worst}) "
                          f"→ {machine_score:.4f}")

                    # 두 값이 갈리되, 한쪽은 멀쩡하다고 할 때만 진단 신호다.
                    # 둘 다 낮으면 민감도 차이일 뿐 서로 어긋난 것이 아니다.
                    gap = ae_score - bl_score
                    if (abs(gap) >= SCORE_DIVERGENCE_WARN
                            and max(ae_score, bl_score) >= SCORE_NORMAL_SIDE):
                        if gap < 0:
                            print(f"[불일치] 오토인코더만 낮습니다({abs(gap):.2f}). "
                                  f"셀 온도는 정상 범위이므로 설비 이상보다 "
                                  f"카메라 조준·모델 쪽을 먼저 확인하십시오.")
                        else:
                            print(f"[불일치] 기준선만 낮습니다({abs(gap):.2f}). "
                                  f"셀 {worst} 가 전례 없는 온도인데 오토인코더는 "
                                  f"정상으로 봅니다. 모델 감도를 확인하십시오.")

                elif ae_score is not None:
                    machine_score = ae_score
                    stage_used = 2

                elif bl_score is not None:
                    machine_score = bl_score
                    machine_mse = float(exceed)
                    valid = machine_score >= 0.0
                    stage_used = 1
                    print(f"[기준선] 초과 {exceed:+.1f}도 (셀 {worst})")

                else:
                    # 0단계. 아직 채점할 근거가 없다. 절대 임계값 경보만
                    # 유효하므로 점수는 -1(미산출)로 둔다. 0.0 으로 두면
                    # "완전 이상" 으로 오해된다.
                    print(f"[기준선] 누적 중 — {baseline.summary()}")

                # 절대 온도 경보가 꺼져 있으면, 기준선이 쌓이는 대로 권장값을
                # 알려 준다. 설치자가 현장 온도를 몰라 못 적는 문제를 푼다.
                if not abs_guard.enabled and not suggested_once:
                    sug = baseline.suggest_temp_thresholds(hotlist_mask)
                    if sug:
                        print(f"[STAGE 0] 권장 임계값 — 관측된 정상 최고온도 기준으로 "
                              f"ABS_TEMP_WARN={sug[0]:.0f}, ABS_TEMP_ALARM={sug[1]:.0f} "
                              f"(env.ini 에 적은 뒤 재시작하십시오)")
                        suggested_once = True

                # --- 화면 이동 감시 --------------------------------------
                # 마스크 안의 셀만 보는 채점으로는 카메라가 밀린 것을 잡지
                # 못한다. 실제로 kict1 은 2026-07-13 에 화면이 위1칸·오른3칸
                # 밀렸는데, 가장 뜨거워진 셀이 마스크 밖이라 채점에는
                # 걸리지 않았다. 64셀 전체 패턴으로 따로 본다.
                corr = baseline.scene_shift()
                scene_ok = corr is None or corr >= SCENE_SHIFT_MIN

                if not scene_ok:
                    print(f"[화면이동] 기준 패턴과의 상관계수 {corr:.3f} "
                          f"(기준 {SCENE_SHIFT_MIN}). 카메라 조준을 확인하십시오.")

                # scene_shift 는 "달라졌다" 까지만 말한다. 몇 칸 밀렸는지는
                # 말해 주지 못하므로, 사람이 이동보정을 누를지 판단할 근거가
                # 되지 못한다. 굳혀 둔 기준 패턴과 칸 단위로 맞춰 본다.
                _now_t0 = time.time()
                tres = tshift.check(x_row, baseline, _now_t0,
                                    datetime.now().strftime("%Y-%m-%d %H:%M"))
                # 밀린 칸 수를 못 밝혀도(mismatch) 학습은 멈춘다. 기준과
                # 다른 화면을 "요즘의 정상" 으로 흡수하면 안 되는 것은
                # 방향을 아는지와 무관하다.
                thermal_ok = tres is None or not (tres["shifted"] or tres["mismatch"])

                # --- 기준선 누적 -----------------------------------------
                # [안전 규칙] 다음 두 경우는 기준선에 넣지 않는다.
                #
                #  1) 절대 임계값이 걸린 프레임
                #     서서히 커지는 열점을 "요즘의 정상" 으로 흡수해 버리면,
                #     정작 위험할 때 아무 경보도 나오지 않는다.
                #
                #  2) 화면이 밀린 것으로 보일 때
                #     그대로 배우면 며칠 만에 틀어진 조준을 정상으로 학습하고
                #     경보가 저절로 풀린다. 마스크가 엉뚱한 곳을 보는 채로
                #     고장이 조용히 묻히는 것이 가장 나쁜 결말이다.
                #     학습은 멈추되 EWMA 는 계속 움직여, 조준을 되돌리면
                #     경보가 자연히 풀리도록 한다.
                #  3) 열화상 격자가 칸 단위로 밀린 것으로 보일 때
                #     2) 와 같은 이유다. 이쪽은 몇 칸인지까지 알 수 있어
                #     사람이 조치할 수 있는 형태로 남는다.
                learn_ok = (abs_level == 0) and scene_ok and thermal_ok

                _now = datetime.now()
                if baseline.update(x_row, hour=_now.hour, learn=learn_ok,
                                   day=_now.strftime("%Y-%m-%d")):
                    baseline_dirty += 1

                # 매 프레임 저장하면 디스크만 혹사한다. 200건마다 남긴다.
                # 중간에 꺼져도 최대 200건만 잃는다.
                if baseline_dirty >= 200:
                    try:
                        baseline.save(BASELINE_PATH)
                        baseline_dirty = 0
                    except Exception as e:
                        print(f"[WARN] 기준선 저장 실패: {e}")

                # --- 단계 현황 기록 --------------------------------------
                # [설정] 창이 이 파일을 읽어 "지금 몇 단계이고 다음까지 얼마
                # 남았는지" 를 보여준다.
                #
                # 예전에는 기준선을 저장하는 김에 같이 썼는데, 저장 주기가
                # 200건이라 첫 기록까지 kict1 은 17분, cj_busan_1 은 100분이
                # 걸렸다. 그동안 설정 창에는 "확인 전" 만 떠서, 감시가 멀쩡히
                # 돌고 있는데도 안 도는 것처럼 보였다.
                #
                # 파일 쓰기는 텍스트 20줄이라 부담이 없다. 기준선 저장과
                # 떼어 내 짧은 주기로 남긴다. status_written_at 이 0 이라
                # 첫 프레임에서 바로 한 번 쓴다.
                _now_t = time.time()
                if (_now_t - status_written_at) >= stage_status.STATUS_WRITE_INTERVAL:

                    # 히스토리 DB 건수만은 날짜별 테이블마다 COUNT 를 돌려야
                    # 하므로 훨씬 드물게 센다.
                    if (_now_t - db_counted_at
                            >= stage_status.DB_COUNT_MIN_INTERVAL):
                        try:
                            _c = Connect_History_DB(history_db_config)
                            try:
                                db_rows, db_tables = stage_status.count_history_rows(
                                    _c, history_db_config["database"],
                                    base_date=baseline.base_date)
                            finally:
                                _c.close()
                            db_counted_at = _now_t
                        except Exception as e:
                            print(f"[WARN] 히스토리 건수 집계 실패: {e}")

                    stage_status.write(
                        STATUS_PATH, baseline,
                        model_ready=(model is not None and scaler is not None),
                        user_path=config["LOCAL_USER_PATH"],
                        db_rows=db_rows, db_tables=db_tables,
                        min_retrain=config.get("RETRAIN_MIN_SAMPLES"),
                        stage_used=stage_used,
                        abs_guard=abs_guard,
                        shift=(shift_x, shift_y, shift_checked_at),
                        tshift=tshift)
                    status_written_at = _now_t

            people, fall, fire_list = read_people_and_area(sensor_db_config)
            hot_list = median_hot.flatten().tolist()

            s0_gas, s0_tmp, s0_hum = read_slave_sensor(sensor_db_config)

            m0_tmp, m0_hum, m0_gas, m0_dust = read_main_sensor(sensor_db_config)

            Append_History_DB(
                history_db_config,
                machine_score,
                people,
                fall,
                hot_list,
                fire_list,
                m0_gas=m0_gas,
                m0_tmp=m0_tmp,
                m0_hum=m0_hum,
                m0_dust=m0_dust,
                s0_gas=s0_gas,
                s0_tmp=s0_tmp,
                s0_hum=s0_hum,
            )

            print(f"[machine_score] {machine_score:.4f} [valid] {valid} "
                  f"[stage] {stage_used}")

            update_db_current_status(sensor_db_config, machine_score)

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[TIME] {now}")

            # ---------- ALERT ----------
            FIRE_THRESHOLD = 0.5

            # 절대 임계값 경보는 학습 상태와 무관하게 화재 신호로 취급한다.
            # 0단계(모델도 기준선도 없는 설치 당일)에서 유일하게 동작하는
            # 경보 경로이기도 하다.
            fire_detected = (any(v > FIRE_THRESHOLD for v in fire_list)
                             or abs_level == LEVEL_ALARM)

            if ENABLE_SMS_ALERTS:
                if fire_detected and not prev_fire_detected:
                    send_event_message(f"F{people}{fall}")

            prev_fire_detected = fire_detected

            time.sleep(WAITING_TIME)

        except KeyboardInterrupt:
            print("[INFO] AutoEncoder stopped.")
            # 누적분을 잃지 않도록 종료 직전에 한 번 더 저장한다.
            if baseline_dirty:
                try:
                    baseline.save(BASELINE_PATH)
                    print(f"[INFO] 기준선 저장 — {baseline.summary()}")
                except Exception as e:
                    print(f"[WARN] 기준선 저장 실패: {e}")
            break

        except Exception as e:
            print(f"[ERROR] {e}")
            traceback.print_exc()
            time.sleep(WAITING_TIME)

# ==================================================
# Entry point
# ==================================================

if __name__ == "__main__":

    pre_user_id    = sys.argv[1] if len(sys.argv) > 1 else "unknown"
    debug_log_file = setup_debug_print_log(pre_user_id)

    try:
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "user_ID",
            help="user_ID under ./users, e.g. cj_busan_1"
        )
        args = parser.parse_args()

        print(f"[INFO] Device: {device}")
        print(f"[INFO] user_ID: {args.user_ID}")

        config = Set_Env_Config(args.user_ID)

        sensor_db_config = Get_SensorDB_Config(config)

        main_loop(config, sensor_db_config)

    except SystemExit:
        raise

    except Exception as e:
        print(f"[FATAL] predict_machine.py terminated by exception: {e}")
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