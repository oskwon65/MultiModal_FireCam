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
    position_since,
    read_from_current_value_median,
    read_people_and_area,
    read_slave_sensor,
    read_main_sensor,
    Append_History_DB,
    update_db_current_status,
    update_db_error_code,
    update_db_hotlist_mask,
    read_db_error_code,
    Set_Env_Config,
    Get_SensorDB_Config,
    Get_HistoryDB_Config,
    Read_GridMask_Inf_File,
    Connect_History_DB,
)

from cv_utils import (
    Get_Adjusted_HotMask_Position,
    Get_Input_Image_URL,
)

from constants import ERR_CODE, LOCAL_HOTLIST_MASK, SVR_HOTLIST_MASK

# 연속 학습 1~2단계. 이 둘은 predict_machine 폴더 안에 있으므로 sys.path[0]
# (= 이 스크립트의 폴더) 으로 그냥 잡힌다. source 폴더와 달리 경로 조작이
# 필요 없다.
from abs_threshold import AbsoluteThreshold, LEVEL_ALARM, LEVEL_WARN, level_name
from online_baseline import OnlineBaseline, SCENE_SHIFT_MIN
import stage_status
import op_state
import op_sync
import model_contribution
import artifact_guard
from auto_retrain import AutoRetrain


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
                f"대체 파일 {npz_path} 도 없음"
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
                f"[scaler] {npz_path} 가 {path} 보다 {stale_by:.0f}초 오래됐음 · "
                f"scaler.pkl이 재학습으로 갱신된 뒤 scaler.npz를 다시 만들지 않은 것으로 보임 · "
                f"otg 환경에서 scaler.npz를 다시 생성할 것"
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
# 운용 모델 갈아 끼우기
# ==================================================
#
# 재학습이 새 모델을 올리면 여기서 알아채고 다시 읽는다. 예전에는 사람이
# predict_machine 을 껐다 켜야 반영됐다. 그 사이 감시는 옛 모델로 돌고,
# 껐다 켜는 동안에는 아예 멈춘다.
#
# 얼마나 자주 볼지. 파일 stat 세 번이라 부담이 없다.
MODEL_RELOAD_INTERVAL = 10.0


def artifact_fingerprint(user_path):
    """운용 산출물이 바뀌었는지 볼 지문 - 세대 이름과 세 파일의 크기·시각."""
    gen = ""
    gp = os.path.join(user_path, "current_generation.txt")
    try:
        if os.path.exists(gp):
            with open(gp, encoding="utf-8") as f:
                gen = f.read().strip()
    except OSError:
        pass

    parts = [gen]
    for name in ("autoencoder_final.pth", "scaler.pkl", "scaler.npz"):
        try:
            st = os.stat(os.path.join(user_path, name))
            parts.append(f"{name}:{st.st_size}:{int(st.st_mtime)}")
        except OSError:
            parts.append(f"{name}:-")
    return "|".join(parts)


def load_live_artifacts(user_path, input_dim, latent_dim, output_dim, device):
    """
    운용 중인 모델과 스케일러를 읽는다. (model, scaler, 사유).

    읽을 수 없으면 (None, None, 사유). 사유는 화면에 그대로 적는다.

    [복사 도중에 읽지 않는다]

    activate() 는 파일 셋을 하나씩 복사하고 마지막에 current_generation.txt
    를 쓴다. 그 사이에 읽으면 새 모델과 옛 스케일러가 짝이 된다 - 2026-09-25
    cj_busan_1 이 그 상태로 이틀을 돌며 모든 프레임에 0.05를 줬다.
    artifact_guard 가 세대 폴더의 것과 바이트까지 견주므로, 복사 도중이면
    어긋남으로 걸려 이번 차례를 거른다. 다음 차례에 다시 본다.
    """
    state, msg, _rows = artifact_guard.check(user_path)
    if state == artifact_guard.MISMATCH:
        return None, None, f"산출물 짝이 어긋남 - {msg}"

    mp = os.path.join(user_path, "autoencoder_final.pth")
    sp = os.path.join(user_path, "scaler.pkl")
    if not (os.path.exists(mp) and os.path.exists(sp)):
        return None, None, "모델 파일이 없음"

    try:
        m = AutoEncoder(input_dim, latent_dim, output_dim).to(device)
        m.load_state_dict(torch.load(mp, map_location=device))
        sc = load_scaler(sp)
    except Exception as e:
        return None, None, f"{type(e).__name__} {e}"

    if getattr(sc, "n_features_in_", None) != input_dim:
        return None, None, (f"scaler 의 차원이 {getattr(sc, 'n_features_in_', None)} "
                            f"로 INPUT_DIM({input_dim})과 다름")

    return m, sc, ""


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
            f"\n hotlist_mask_local.ini 또는 DB의 mask_list 길이를 확인할 것"
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
            f"\n hotlist_mask 를 다시 작성할 것"
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

    bShifted, hotlist_mask, shift_x, shift_y, shift_inf = \
        Get_Adjusted_HotMask_Position(BASE_IMG_DIR, input_img, hotlist_mask,
                                      x_grid, y_grid)

    MAX_SHIFT = 2
    if abs(shift_x) >= MAX_SHIFT or abs(shift_y) >= MAX_SHIFT:
        print(f"[ERROR] 카메라가 가로 {shift_x:+d}칸 · 세로 {shift_y:+d}칸 밀렸음 "
              f"({MAX_SHIFT}칸 이상). 마스크를 믿을 수 없어 중단함")
        print("        조준을 되돌린 뒤 다시 시작할 것 · 마스크는 자동으로 옮기지 않음")
        print("Program Terminated")
        sys.exit(1)

    print(f"[Check_Status_of_HotList_Mask] bShifted {bShifted} "
          f"shift_x {shift_x} shift_y {shift_y} state {shift_inf['state']}")
    print("-" * 50)

    # 이동량도 함께 돌려준다. 예전에는 여기서 버려서, 계산해 놓고도 화면에
    # 보여줄 방법이 없었다. [설정] 영역이 이 값을 읽어 버튼 옆에 적는다.
    #
    # state 를 따로 두는 까닭. 0칸이라는 값만으로는 "틀어지지 않았다" 와
    # "잴 수 없었다" 를 가를 수 없다. 둘은 전혀 다른 말이다.
    return bShifted, hotlist_mask, shift_x, shift_y, shift_inf

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

    # 모델과 스케일러의 짝이 어긋났으면 시작하지 않는다.
    #
    # 틀린 점수를 내는 것은 점수를 못 내는 것보다 나쁘다. 화면에는 숫자가
    # 떠 있으니 아무도 이상을 눈치채지 못한 채 진짜 이상을 놓친다.
    # 2026-09-25 cj_busan_1 이 그렇게 이틀을 보냈다.
    if artifact_guard.report(config["LOCAL_USER_PATH"]):
        stage_status.write_error(
            os.path.join(config["LOCAL_USER_PATH"], "stage_status.ini"),
            "모델과 스케일러의 짝이 맞지 않아 시작하지 않았음 · "
            "세대 폴더의 것으로 되돌릴 것")
        sys.exit(2)

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
    #   1단계  절대 임계값        학습 0건. 설치 즉시.
    #   2단계  셀별 온라인 통계    수 시간 후. z-score 채점.
    #   3단계  오토인코더          모델이 준비되면. 셀 간 결합 분포까지.
    #
    # 1단계는 이후 단계에서도 계속 살아 있다. 학습 기반 판정이 모두 실패해도
    # 고정된 선 하나는 남아 있어야 하기 때문이다.
    # ------------------------------------------------------------------

    abs_guard = AbsoluteThreshold(config)
    print(f"[STAGE 1] {abs_guard.describe()}")

    if not abs_guard.enabled:
        print("[STAGE 1] 경고 — 절대 임계값이 지정되지 않아 1단계 경보가")
        print("          동작하지 않음 · 설비의 정상 가동 온도를 확인해")
        print("          env.ini 의 [CONSTANTS] 에 ABS_TEMP_WARN/ALARM 과")
        print("          ABS_RISE_WARN/ALARM 을 지정할 것")
        print("          값을 모르면 하루쯤 돌려 기준선이 쌓이기를 기다릴 것")
        print("          아래에 이 현장에서 관측된 권장값을 출력함")

    BASELINE_PATH = os.path.join(config["LOCAL_USER_PATH"], "online_baseline.npz")
    baseline = OnlineBaseline.load(
        BASELINE_PATH, INPUT_DIM,
        min_samples=config.get("BASELINE_MIN_SAMPLES"),
        min_hours=config.get("BASELINE_MIN_HOURS"),
        base_date=config.get("CALC_BASE_DATE"),
    )
    print(f"[STAGE 2] 경험 임계값 — {baseline.summary()}")

    # 운전 상태. 미리 만들어 둔 군집 중심으로 매 프레임 이름을 붙인다.
    # 화면에 보여 주기만 하고 채점에는 쓰지 않는다.
    opst = op_state.OpStates(config["LOCAL_USER_PATH"], INPUT_DIM)
    print(f"[운전상태] {opst.info}")
    op_now = None

    # 관제서버와 운전 상태 맞추기 (지금 상태 올리기 · 분류표 주고받기). 따로 도는
    # 스레드라 관제서버가 느리거나 꺼져 있어도 감시는 막히지 않는다.
    opsync = op_sync.OpSync(config)
    opsync.start()

    model = None
    scaler = None

    if not os.path.exists(MODEL_PATH) or not os.path.exists(SCALER_PATH):
        print("[STAGE 3] 오토인코더 없음 — 1~2단계로 동작함")
        print("          데이터가 쌓이면 히스토리 DB로 학습해 배치할 것")
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
                # 1~2단계로 계속 간다. 짝이 안 맞는 모델로 채점하는 것보다
                # 낫고, 감시를 통째로 멈추는 것보다도 낫다.
                print(
                    f"[STAGE 3] scaler 의 n_features_in_="
                    f"{getattr(sc, 'n_features_in_', None)} 가 INPUT_DIM({INPUT_DIM})과 "
                    f"다름 · 오토인코더를 쓰지 않고 1~2단계로 동작함"
                )
            else:
                model, scaler = m, sc
                print(f"[STAGE 3] 오토인코더 사용 "
                      f"(INPUT_DIM={INPUT_DIM}, LATENT_DIM={LATENT_DIM})")

        except Exception as e:
            print(f"[STAGE 3] 오토인코더를 읽지 못해 1~2단계로 동작함: {e}")

    baseline_dirty = 0
    suggested_once = False
    STATUS_PATH = os.path.join(config["LOCAL_USER_PATH"],
                               stage_status.STATUS_FILE_NAME)
    db_rows = db_tables = None
    db_span = None
    db_counted_at = 0.0
    contrib = None          # (판단 점수, 기여 가중치) - 히스토리 집계와 같은 주기
    contrib_at = ""         # 위 값을 계산한 시각
    # [재학습] 창의 "자동 재학습" 이 켜져 있으면 w < 1.00 일 때 재학습을 띄운다.
    auto_rt = AutoRetrain(config["LOCAL_USER_PATH"], config["USER_ID"])
    status_written_at = 0.0   # 0 이면 첫 프레임에서 바로 한 번 남긴다
    prev_fire_detected = False

    # 운용 모델이 갈렸는지 보는 데 쓴다. 지금 읽어 둔 것을 지문으로 남긴다.
    model_fingerprint = artifact_fingerprint(config["LOCAL_USER_PATH"])
    model_checked_at = time.time()

    input_img = Get_Input_Image_URL(IMG_URL)

    if input_img is None:
        print("[ERROR] input_img not found")
        print("Program Terminated")
        sys.exit(1)

    # HotListMask 를 변경하는 경우 먼저 로컬에 존재하는 HotListMask_LocalPath 파일을 제거함
    # 해당 파일이 없는 경우 관제서버에서 자동으로 다운로드 받아서 사용함
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
                f"\nNUM_OF_MACHINE_CELLS({NUM_OF_MACHINE_CELLS})와 다름 · "
                f"\nenv.ini 의 NUM_OF_MACHINE_CELLS 값을 확인하거나 hotlist_mask 를 다시 작성할 것"
            )
            print("Program Terminated")
            sys.exit(1)

    bShifted, _unused_mask, shift_x, shift_y, shift_inf = \
        Check_Status_of_HotList_Mask(cur_hotlist_mask, X_GRID, BASE_IMG_DIR,
                                     input_img)

    # 이 검사는 기동할 때 한 번만 한다. 루프 안에서는 다시 재지 않으므로
    # 아래 값들은 "언제 잰 것인지" 와 함께 현황 파일에 그대로 실려 나간다.
    shift_checked_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 틀어져도 마스크는 옮기지 않는다. 오류 코드만 남긴다.
    #
    # 예전에는 관제서버에 ADJST-MG(이동보정 승인)가 들어와 있으면 여기서 마스크를
    # 그만큼 밀어 저장하고, base_img 를 지운 뒤 이 순간의 프레임을 새 기준으로
    # 삼았다. 사람이 보지 않는 기동 순간에 감시 대상과 잣대가 한꺼번에 바뀌고,
    # 승인이 관제서버에 남아 있으면 몇 달 뒤 1칸 밀린 기동에서도 저절로 일어났다.
    # 2026-10-08 에 뺐다. 마스크는 사람이 [관제서버 분석마스크 받기] 로, 기준 이미지는
    # [설정] 의 [기준 이미지] 에서 견주어 보고 바꾼다.
    hotlist_mask = cur_hotlist_mask
    if bShifted:
        update_db_error_code(sensor_db_config, ERR_CODE.CAMERA_POSITION_SHIFT)
        print("[WARN] 카메라가 밀렸음 - 마스크는 그대로 두고 오류 코드만 남김")
        print("[WARN] 재시작 전까지 2·3단계 판정과 학습을 멈춤 · 1단계만 동작함")
    else:
        update_db_error_code(sensor_db_config, ERR_CODE.NO_ERR)

    update_db_hotlist_mask(sensor_db_config, hotlist_mask)

    # ---------- Real-time inference loop ----------
    while True:
        try:
            # ---------- 운용 모델이 갈렸는지 본다 ----------
            #
            # 프레임을 읽기 전에 본다. 뒤에 두면 프레임이 없는 동안
            # (median_hot.size == 0 으로 continue) 영영 확인하지 않는다.
            _t_chk = time.time()
            if _t_chk - model_checked_at >= MODEL_RELOAD_INTERVAL:
                model_checked_at = _t_chk
                _fp = artifact_fingerprint(config["LOCAL_USER_PATH"])
                if _fp != model_fingerprint:
                    _m2, _sc2, _why = load_live_artifacts(
                        config["LOCAL_USER_PATH"], INPUT_DIM, LATENT_DIM,
                        OUTPUT_DIM, device)
                    if _m2 is not None:
                        model, scaler = _m2, _sc2
                        model_fingerprint = _fp

                        # 기준선도 파일에서 다시 읽는다.
                        #
                        # 되돌리기는 기준선 파일을 치운다 - 기준선은 그 모델의
                        # 오차 분포라 모델만 갈면 임계치가 남의 것이 된다.
                        # 메모리의 것을 그대로 두면 껐다 켠 것과 결과가 달라진다.
                        # 저장하지 않고 읽기만 한다. 저장하면 치워 둔 파일을
                        # 되살리게 된다. 마지막 저장 뒤의 누적(최대 200건)은
                        # 잃지만, 껐다 켤 때도 같은 만큼 잃는다.
                        baseline = OnlineBaseline.load(
                            BASELINE_PATH, INPUT_DIM,
                            min_samples=config.get("BASELINE_MIN_SAMPLES"),
                            min_hours=config.get("BASELINE_MIN_HOURS"),
                            base_date=config.get("CALC_BASE_DATE"),
                        )
                        baseline_dirty = 0

                        _gen = _fp.split("|")[0] or "이름 없음"
                        print(f"[STAGE 3] 운용 모델이 바뀌어 다시 읽었음 - "
                              f"세대 {_gen}")
                        print(f"[STAGE 2] 경험 임계값 — {baseline.summary()}")
                    else:
                        # 복사 도중이면 여기로 온다. 지문을 갱신하지 않으므로
                        # 다음 차례에 다시 본다.
                        print(f"[STAGE 3] 새 모델을 아직 읽지 못했음 - {_why}")

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
            accum_ok, accum_why = False, "확인 전"
            # 아래 가지를 타지 않으면(오류 코드가 있을 때) 그대로 남는다.
            # peak -1 은 "재지 못했다" 는 뜻이고 0도와 구별된다.
            peak_t, rise_t, abs_cell = -1.0, 0.0, -1

            # 카메라 이동 오류 코드는 이 프로그램이 기동할 때 남긴 것이다. 예전에는
            # 이 코드가 있으면 아래를 통째로 건너뛰어 1단계(절대 임계값)까지
            # 꺼지고 현황 파일도 멈췄다. 이동 때 멈출 것은 2·3단계뿐이다.
            if cur_error_code in (ERR_CODE.NO_ERR, ERR_CODE.CAMERA_POSITION_SHIFT):
                x_full = extract_mach_area(median_hot, hotlist_mask)
                x_row = np.asarray(x_full, dtype=np.float64).reshape(-1)

                # --- 1단계. 학습과 무관하게 항상 먼저 본다 ---------------
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

                # --- 화면 이동 감시 --------------------------------------
                # 마스크 안의 셀만 보는 채점으로는 카메라가 밀린 것을 잡지
                # 못한다. 실제로 kict1 은 2026-07-13 에 화면이 위1칸·오른3칸
                # 밀렸는데, 가장 뜨거워진 셀이 마스크 밖이라 채점에는
                # 걸리지 않았다. 64셀 전체 패턴으로 따로 본다.
                corr = baseline.scene_shift()
                scene_ok = corr is None or corr >= SCENE_SHIFT_MIN

                if not scene_ok:
                    print(f"[화면이동] 기준 패턴과의 상관계수 {corr:.3f} "
                          f"(기준 {SCENE_SHIFT_MIN}). 카메라 조준을 확인할 것")

                # 이동이 보이면 2·3단계는 판정도 학습도 하지 않는다. 마스크가
                # 설비의 다른 곳을 보는 채로 매긴 점수는 근거가 없다.
                #   기동 때 RGB 로 잰 이동  재시작 전까지 (루프에서 다시 재지 않는다)
                #   운전 중 열화상 패턴 이동 조준을 되돌려 상관계수가 회복되면 풀린다
                shift_halt = bool(bShifted) or not scene_ok
                if shift_halt:
                    print("[중지] 카메라 위치 이동 - 2·3단계 판정·학습 중지, "
                          "1단계만 동작")

                if not shift_halt and model is not None and scaler is not None:
                    score_list, mse_list, valid = normality_score(
                        x_full, hotlist_mask, scaler, model
                    )
                    ae_score = float(np.mean(score_list))
                    machine_mse = float(np.mean(mse_list))

                if baseline.is_ready() and not shift_halt:
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
                            print(f"[불일치] 오토인코더만 낮음({abs(gap):.2f}). "
                                  f"셀 온도는 정상 범위이므로 설비 이상보다 "
                                  f"카메라 조준·모델 쪽을 먼저 확인할 것")
                        else:
                            print(f"[불일치] 기준선만 낮음({abs(gap):.2f}). "
                                  f"셀 {worst} 가 전례 없는 온도인데 오토인코더는 "
                                  f"정상으로 봄 · 모델 감도를 확인할 것")

                elif ae_score is not None:
                    machine_score = ae_score
                    stage_used = 2

                elif bl_score is not None:
                    machine_score = bl_score
                    machine_mse = float(exceed)
                    valid = machine_score >= 0.0
                    stage_used = 1
                    print(f"[기준선] 초과 {exceed:+.1f}도 (셀 {worst})")

                elif not shift_halt:
                    # 1단계. 아직 채점할 근거가 없다. 절대 임계값 경보만
                    # 유효하므로 점수는 -1(미산출)로 둔다. 0.0 으로 두면
                    # "완전 이상" 으로 오해된다. 이동으로 멈췄을 때도 -1 이다.
                    print(f"[기준선] 누적 중 — {baseline.summary()}")

                # 절대 온도 경보가 꺼져 있으면, 기준선이 쌓이는 대로 권장값을
                # 알려 준다. 설치자가 현장 온도를 몰라 못 적는 문제를 푼다.
                if not abs_guard.enabled and not suggested_once:
                    sug = baseline.suggest_temp_thresholds(hotlist_mask)
                    if sug:
                        print(f"[STAGE 1] 권장 임계값 — 관측된 정상 최고온도 기준으로 "
                              f"ABS_TEMP_WARN={sug[0]:.0f}, ABS_TEMP_ALARM={sug[1]:.0f} "
                              f"(env.ini 에 적은 뒤 재시작할 것)")
                        suggested_once = True

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
                #
                #  3) 기동 때 RGB 로 카메라 이동이 잡혔을 때 (2) 와 같은 까닭
                accum_ok = (abs_level == 0) and not shift_halt

                # 왜 멈췄는지 화면에 적어야 한다. 누적이 멈춘 것은 숫자가
                # 늘지 않는 것으로만 드러나는데, 그것을 알아채려면 몇 분을
                # 지켜봐야 한다.
                #
                # scene_ok 를 "RGB" 라 적지 않는다. 이름이 scene_shift 일
                # 뿐 RGB 를 보지 않는다 - 열화상 64칸의 느린 EWMA 와 장기
                # 평균의 상관계수다.
                if accum_ok:
                    accum_why = ""
                elif bShifted:
                    accum_why = "카메라 위치 이동"
                elif not scene_ok:
                    accum_why = "열화상 화면 변함"
                else:
                    accum_why = "절대 임계값"

                _now = datetime.now()
                op_now = opst.classify(x_row)
                opsync.update_now(opst.name_of(op_now), op_now, opst.last_dev,
                                  opst.far_of(op_now), 100.0 * opst.recent_odd(),
                                  opst.recent_mix())

                if baseline.update(x_row, hour=_now.hour, accum=accum_ok,
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
                                db_span = stage_status.history_span(
                                    _c, history_db_config["database"])
                            finally:
                                _c.close()
                            db_counted_at = _now_t
                        except Exception as e:
                            print(f"[WARN] 히스토리 건수 집계 실패: {e}")

                        # 재학습이 기존 모델을 얼마나 물려받을지. 실제로 정하는
                        # 곳은 재학습이고, 여기서는 [설정] 화면에 미리
                        # 보여 주기 위해 같은 함수로 구한다.
                        try:
                            _c = Connect_History_DB(history_db_config)
                            try:
                                _rs = None
                                if model is not None and scaler is not None:
                                    _rs = model_contribution.batch_scorer(
                                        model, scaler, hotlist_mask, device)
                                _nt, _mf, _ms = model_contribution.limits(config)
                                _sc, _ = model_contribution.decision_score(
                                    _c, history_db_config["database"],
                                    LENGTH_HOTLIST, mask=hotlist_mask,
                                    temp_warn=config.get("ABS_TEMP_WARN"),
                                    verbose=False, score_fn=_rs,
                                    n_tables=_nt, min_frames=_mf,
                                    max_samples=_ms,
                                    since=position_since(config))
                            finally:
                                _c.close()
                            contrib = (_sc, model_contribution.weight_for(_sc))
                            contrib_at = datetime.now().strftime("%Y-%m-%d %H:%M")
                        except Exception as e:
                            print(f"[WARN] 기여 가중치 계산 실패: {e}")

                    # 이동 중에는 3단계 재학습도 띄우지 않는다. 틀어진 조준으로
                    # 쌓인 자료를 정상으로 배우게 된다.
                    if not shift_halt:
                        try:
                            auto_rt.tick(None if contrib is None else contrib[1],
                                         None if contrib is None else contrib[0])
                        except Exception as e:
                            print(f"[WARN] 자동 재학습 확인 실패: {e}")

                    stage_status.write(
                        STATUS_PATH, baseline,
                        model_ready=(model is not None and scaler is not None),
                        user_path=config["LOCAL_USER_PATH"],
                        db_rows=db_rows, db_tables=db_tables,
                        db_span=db_span,
                        min_retrain=config.get("RETRAIN_MIN_SAMPLES"),
                        stage_used=stage_used,
                        abs_guard=abs_guard,
                        abs_now=(peak_t, rise_t, abs_level, abs_cell),
                        accum=(accum_ok, accum_why),
                        cells=(x_row,
                               np.asarray(baseline.hi).reshape(-1),
                               np.asarray(hotlist_mask).reshape(-1)),
                        shift=(shift_x, shift_y, shift_checked_at, shift_inf),
                        shift_halt=shift_halt,
                        contrib=contrib, contrib_at=contrib_at,
                        op=opst, op_now=op_now)
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
                  f"[stage] {stage_used + 1}")

            update_db_current_status(sensor_db_config, machine_score)

            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"[TIME] {now}")

            # ---------- ALERT ----------
            FIRE_THRESHOLD = 0.5

            # 절대 임계값 경보는 학습 상태와 무관하게 화재 신호로 취급한다.
            # 1단계(모델도 기준선도 없는 설치 당일)에서 유일하게 동작하는
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