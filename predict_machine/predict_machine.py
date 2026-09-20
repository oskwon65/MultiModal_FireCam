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
)

from cv_utils import (
    Get_Adjusted_HotMask_Position,
    Get_Input_Image_URL,
    save_base_image
)

from constants import ERR_CODE, SVR_CMD, LOCAL_HOTLIST_MASK, SVR_HOTLIST_MASK


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

    print(f"[Check_Status_of_HotList_Mask] bShifted {bShifted}")
    print("-" * 50)

    return bShifted, hotlist_mask

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

    if not os.path.exists(MODEL_PATH):
        print("[ERROR] autoencoder_final.pth not found")
        sys.exit(1)

    if not os.path.exists(SCALER_PATH):
        print("[ERROR] scaler.pkl not found")
        sys.exit(1)

    model = AutoEncoder(INPUT_DIM, LATENT_DIM, OUTPUT_DIM).to(device)
    model.load_state_dict(torch.load(MODEL_PATH, map_location=device))
    scaler = load_scaler(SCALER_PATH)

    # load_scaler()가 numpy 버전 문제로 scaler.pkl 대신 scaler.npz로 조용히 폴백할 수 있는데,
    # npz가 예전(다른 차원) 학습에서 남은 것이면 모델과 안 맞는 스케일러를 쓰게 된다.
    # 매 루프에서 반복적으로 실패하며 트레이스백만 쌓이는 대신, 시작 시점에 한 번 명확히 걸러낸다.
    if getattr(scaler, "n_features_in_", None) != INPUT_DIM:
        print(
            f"[FATAL] scaler({SCALER_PATH})의 n_features_in_="
            f"{getattr(scaler, 'n_features_in_', None)} 가 INPUT_DIM({INPUT_DIM})과 다릅니다. "
            f"\n scaler.pkl/scaler.npz가 현재 모델과 다른 차원으로 학습된 상태입니다. "
            f"\n autoencoder-7.py로 재학습하거나 scaler.npz를 다시 생성하세요."
        )
        print("Program Terminated")
        sys.exit(1)

    print(
        f"[INFO] Model & scaler loaded. "
        f"(INPUT_DIM={INPUT_DIM}, LATENT_DIM={LATENT_DIM})"
    )

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

    bShifted, new_hotlist_mask = Check_Status_of_HotList_Mask(cur_hotlist_mask, X_GRID, BASE_IMG_DIR, input_img)

    if bShifted:
        main_command = read_db_main_command(sensor_db_config)
        print("Command from Server:", main_command)

        if main_command == SVR_CMD.ADJUST_MACHINE_GRID:  # 카메라 이동으로 이미지의 위치가 전과 다른 경우
            hotlist_mask = new_hotlist_mask
            write_file_hotlist_mask(HotListMask_LocalPath, hotlist_mask)
            delete_files_of_Base_Img(config)
            save_base_image(BASE_IMG_DIR, input_img)
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


            if cur_error_code == ERR_CODE.NO_ERR:
                x_full = extract_mach_area(median_hot, hotlist_mask)

                score_list, mse_list, valid = normality_score(x_full, hotlist_mask, scaler, model)

                machine_score = float(np.mean(score_list))
                machine_mse   = float(np.mean(mse_list))

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

            print(f"[machine_score] {machine_score:.4f} [valid] {valid}")

            update_db_current_status(sensor_db_config, machine_score)

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[TIME] {now}")

            # ---------- ALERT ----------
            FIRE_THRESHOLD = 0.5

            fire_detected = any(v > FIRE_THRESHOLD for v in fire_list)

            if ENABLE_SMS_ALERTS:
                if fire_detected and not prev_fire_detected:
                    send_event_message(f"F{people}{fall}")

            prev_fire_detected = fire_detected

            time.sleep(WAITING_TIME)

        except KeyboardInterrupt:
            print("[INFO] AutoEncoder stopped.")
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