# constants.py

ENV_FILE_NAME          = "env.ini"
SECRET_FILE_NAME        = "secrets.ini"   # DB 비밀번호 (git 제외, env.ini 와 같은 폴더)
SVR_SLAVE_0_VALUES     = "slave_0_sensor.inf"
SVR_MAIN_VALUES         = "main_sensor.inf"
SVR_IR_IMG_CSV          = "ir_img.csv"
SVR_RGB_IMG_JPG         = "rgb_img.jpg"

PEOPLE_ANALYSIS_FOLDER  = "event_img_result"
PEOPLE_SRCIMG_FOLDER    = "event_img_input"
FIRE_ANALYSIS_FOLDER    = "fire_result"
FIRE_SRCIMG_FOLDER      = "fire_img"
BASE_IMG_FOLDER         = "base_img"

SVR_HOTLIST_MASK       = "hotlist_mask_svr.ini"
LOCAL_HOTLIST_MASK      = "hotlist_mask_local.ini"

# caption(창 제목)이 길어져도 잘리지 않도록 fall_detection 미리보기 창의 최소 폭을 보장
MIN_WINDOW_WIDTH        = 600

class ERR_CODE:
    NO_ERR                = "0000"
    CAMERA_POSITION_SHIFT = "0021"

class SVR_CMD:
    ADJUST_MACHINE_GRID = "ADJST-MG"
    NO_ACTION           = "NOACTION"