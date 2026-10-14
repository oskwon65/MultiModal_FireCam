# -*- coding: utf-8 -*-
"""
RGB 기준 이미지(base_img/base_ref.png)를 사람이 보고 바꾸기 위한 도구.

  python retrain/base_ref_tool.py cj_busan_1 capture
  python retrain/base_ref_tool.py cj_busan_1 relocate
  python retrain/base_ref_tool.py cj_busan_1 recount 20

지금 RGB 화면을 관제서버에서 한 장 받아 base_img/_candidate.png 로 두고, 기준
이미지와 견준 결과를 base_img/_candidate.ini 에 적는다. [설정] 창의 [기준 이미지]
가 이 둘을 읽어 기준과 나란히 보여 주고, 사람이 확인한 뒤에만 교체한다.

[왜 사람이 보고 바꾸는가]

기준 이미지는 RGB 틀어짐을 재는 잣대다. 예전에는 이동보정을 승인하면 그 뒤 감시를
처음 켤 때 찍힌 프레임 하나가 그대로 기준이 되었다. 밤이거나 무엇이 가렸거나 이미
틀어진 화면이어도 걸러지지 않았다. 잣대가 틀리면 그 뒤의 모든 측정이 틀린다.

[기준 이미지에 알맞은가]

화면 품질을 몇 가지로 재서 조건과 함께 적는다. 조건은 두 현장의 지난 기준
이미지 99장(2026-10-08)을 재어 정했다. 좋은 화면과 꺼지거나 가린 화면이 뚜렷이
갈리는 자리에 선을 두었다.

  밝기       평균 회색값 40~200      좋은 화면 65~108, 꺼진 화면 0~1
  대비       표준편차 25 이상         좋은 화면 48~62, 꺼진 화면 1~4
  선명도     라플라시안 분산 100 이상  좋은 화면 208~704, 꺼진 화면 2
  어두운 곳  회색값 10 미만 10% 이하   좋은 화면 0~3.4%, 꺼진 화면 99%
  밝은 곳    회색값 245 초과 10% 이하  좋은 화면 1~4%
  같은 장면  지금 기준과 일치도 0.30 이상 (감시가 판정을 버리는 선과 같다)
  밀림       지금 기준과 0칸           칸이 밀린 채 기준만 바꾸면 마스크가 어긋난다

앞의 다섯은 화질 적합도다. 하나라도 어긋나면 기준으로 쓸 수 없어 [설정] 창이 교체를
막는다. 뒤의 둘은 틀어짐 기준이고 기준이 이미 있을 때만 본다. 어긋나면 막지 않고
카메라 자리가 바뀐 것으로 다룬다(아래 [relocate]). 판정은 C++ 창이 아니라 여기서
한다 - 조건을 한 곳에만 둔다.

[칸 단위로 밀린 채 기준을 바꾸면 - relocate]

기준을 바꾼다는 것은 '지금 보이는 자리가 앞으로의 정상' 이라는 뜻이다. 그런데
칸이 밀렸으면 같은 칸이 설비의 다른 곳을 본다. 2단계(칸마다 평소 몇 도였나)와
3단계(칸들의 온도 조합)는 옛 자리로 배운 것이라, 새 자리를 채점하면 점수가 뜻을
잃는다. 경고만 꺼지고 감시는 틀린 채로 돈다. 그래서 둘을 함께 내린다.

  2단계  경험 임계값을 치운다(model_generations/_retired_baseline). 새 자리에서
         처음부터 다시 쌓는다.
  3단계  운용 모델 세 파일을 model_generations/_retired_position/<시각>/ 으로 옮기고
         current_generation.txt 를 비운다. 새 자리 자료로 재학습해 승격할 때까지
         채점하지 않는다.
  기간   continual_learning.ini 에 POSITION_SINCE 를 적는다. 재생버퍼 · 기여도 ·
         DB 에서 되쌓기가 그 앞의 프레임을 쓰지 않는다.

그동안은 1단계(절대 임계값)만 남는다. 지우지 않고 옮기므로 되돌릴 수 있다.
감시를 멈춘 상태에서만 한다 - 돌고 있으면 메모리의 기준선과 모델이 그대로 남는다.
[설정] 창이 그것을 확인한 뒤 부른다.

[설비 칸 수를 바꾸면 - recount]

관제서버 설정 화면에서 admin 이 칸 수를 바꾸고 그 칸 수로 마스크를 다시 저장하면,
[관제서버 분석마스크 받기] 창이 칸 수가 달라진 것을 보고 사람에게 확인한 뒤 부른다.
감시하는 칸이 바뀌므로 relocate 와 같이 2 · 3단계를 내리고 POSITION_SINCE 를 적은
뒤 env.ini 의 NUM_OF_MACHINE_CELLS 를 새 칸 수로 고친다. 옮긴 모델은
model_generations/_retired_recount/<시각>/ 에 둔다. 결과는 users/<현장>/_recount.ini.

[재는 방법]

감시가 기동할 때와 같다(cv_utils.measure_shift_vs_ref - 위상 상관). 다만 일치도가
낮아도 값을 그대로 적는다. 감시는 0.30 미만이면 '판정 불가' 로 버리지만, 여기서는
사람이 그 숫자를 보고 판단해야 한다.
"""
import argparse
import configparser
import os
import shutil
import sys
from datetime import datetime

import cv2
import numpy as np

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "source"))
sys.path.insert(0, _ROOT)

from db_utils import Set_Env_Config
sys.path.insert(0, os.path.join(_ROOT, "predict_machine"))
from online_baseline import write_reset_note
from cv_utils import (Get_Input_Image_URL, base_ref_path, crop_to_same_size,
                      SHIFT_RESP_MIN)

CANDIDATE_IMG = "_candidate.png"
CANDIDATE_INI = "_candidate.ini"
RELOCATE_INI = "_relocate.ini"     # relocate 결과. [설정] 창이 읽는다
RECOUNT_INI = "_recount.ini"       # recount 결과 (users/<현장>/). [관제서버 분석마스크 받기] 창이 읽는다

MODEL_FILES = ("autoencoder_final.pth", "scaler.pkl", "scaler.npz")
BASELINE_FILE = "online_baseline.npz"

# 기준 이미지에 알맞은 화면의 조건. 근거는 위 [기준 이미지에 알맞은가].
MEAN_MIN, MEAN_MAX = 40, 200
STD_MIN = 25
SHARP_MIN = 100
DARK_MAX = 10.0      # %
BRIGHT_MAX = 10.0    # %


def quality(img):
    """화면 품질 다섯 가지. (밝기, 대비, 선명도, 어두운 곳 %, 밝은 곳 %)"""
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return (float(g.mean()), float(g.std()),
            float(cv2.Laplacian(g, cv2.CV_64F).var()),
            float((g < 10).mean() * 100), float((g > 245).mean() * 100))


def checks(cur_q, ref_q=None, resp=None, cell=None):
    """
    (묶음, 이름, 조건, 기준 이미지 값, 현재 값, 맞는가) 목록. 맞는가는 현재 화면에 대한 것.

    묶음은 둘이다. 창이 표를 둘로 나눠 보이고, 다루는 법도 다르다.
      Q  화질 적합도   하나라도 어긋나면 기준으로 쓸 수 없다 (교체를 막는다)
      S  틀어짐 기준   어긋나면 카메라 자리가 바뀐 것으로 보고 2·3단계를 내린 뒤 바꾼다
    """
    out = []
    grp = ["Q"]
    def row(name, rule, rv, cv, ok):
        out.append((grp[0], name, rule, rv, cv, bool(ok)))

    m, sd, sh, dk, br = cur_q
    r = ref_q or (None,) * 5
    f = lambda v, fmt: "-" if v is None else fmt.format(v)
    row("밝기", f"{MEAN_MIN} ~ {MEAN_MAX}", f(r[0], "{:.0f}"), f"{m:.0f}",
        MEAN_MIN <= m <= MEAN_MAX)
    row("대비", f"{STD_MIN} 이상", f(r[1], "{:.0f}"), f"{sd:.0f}", sd >= STD_MIN)
    row("선명도", f"{SHARP_MIN} 이상", f(r[2], "{:.0f}"), f"{sh:.0f}", sh >= SHARP_MIN)
    row("어두운 곳", f"{DARK_MAX:.0f}% 이하", f(r[3], "{:.1f}%"), f"{dk:.1f}%", dk <= DARK_MAX)
    row("밝은 곳", f"{BRIGHT_MAX:.0f}% 이하", f(r[4], "{:.1f}%"), f"{br:.1f}%", br <= BRIGHT_MAX)
    grp[0] = "S"
    if resp is not None:
        row("같은 장면", f"일치도 {SHIFT_RESP_MIN:.2f} 이상", "-", f"{resp:.3f}",
            resp >= SHIFT_RESP_MIN)
    if cell is not None:
        cx, cy = cell
        row("밀림", "0칸", "-", f"가로 {cx:+d} · 세로 {cy:+d}", cx == 0 and cy == 0)
    return out


def check_fields(rows):
    """checks() 결과를 ini 칸으로 편다."""
    kv = {"N_CHECK": len(rows), "ALL_OK": int(all(r[5] for r in rows)),
          "QUALITY_OK": int(all(r[5] for r in rows if r[0] == "Q"))}
    for i, (group, name, rule, rv, cv, ok) in enumerate(rows, 1):
        kv[f"C{i}_GROUP"] = group
        kv[f"C{i}_NAME"] = name
        kv[f"C{i}_RULE"] = rule
        kv[f"C{i}_REF"] = rv
        kv[f"C{i}_CUR"] = cv
        kv[f"C{i}_OK"] = int(ok)
    return kv


def measure(ref_img, img):
    """(dx, dy, response). measure_shift_vs_ref 와 같은 셈이되 일치도로 거르지 않는다."""
    a = np.float32(cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY))
    b = np.float32(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
    a, b = crop_to_same_size(a, b)
    h, w = a.shape[:2]
    hann = cv2.createHanningWindow((w, h), cv2.CV_32F)
    # 복사본을 준다. 창을 주면 phaseCorrelate 가 입력을 제자리에서 덮어쓴다.
    (dx, dy), resp = cv2.phaseCorrelate(a.copy(), b.copy(), hann)
    return float(dx), float(dy), float(resp)


def write_result(path, **kv):
    cp = configparser.ConfigParser(interpolation=None)   # 값에 % 가 들어간다
    cp.optionxform = str
    cp["RESULT"] = {k: str(v) for k, v in kv.items()}
    with open(path, "w", encoding="utf-8") as f:
        cp.write(f)


def capture(user_id):
    config = Set_Env_Config(user_id, verbose=False)
    base_dir = config["BASE_IMG_DIR"]
    os.makedirs(base_dir, exist_ok=True)
    out_img = os.path.join(base_dir, CANDIDATE_IMG)
    out_ini = os.path.join(base_dir, CANDIDATE_INI)
    at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 지난 결과가 남아 있으면 이번 것으로 오해한다. 먼저 지운다.
    for p in (out_img, out_ini):
        try:
            os.remove(p)
        except OSError:
            pass

    img = Get_Input_Image_URL(config["IMG_URL"])
    if img is None:
        write_result(out_ini, OK=0, AT=at,
                     MSG="현재 화면을 받지 못했음 (관제서버 RGB 이미지)")
        print("[실패] 현재 화면을 받지 못했음")
        return 2

    if not cv2.imwrite(out_img, img):
        write_result(out_ini, OK=0, AT=at, MSG="현재 화면을 저장하지 못했음")
        return 2

    h, w = img.shape[:2]
    gx, gy = int(config["X_GRID"]), int(config["Y_GRID"])
    mean = float(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).mean())

    ref_p = base_ref_path(base_dir)
    ref = cv2.imread(ref_p) if os.path.exists(ref_p) else None
    cur_q = quality(img)
    if ref is None:
        write_result(out_ini, OK=1, AT=at, HAS_REF=0, W=w, H=h, MEAN=f"{mean:.0f}",
                     MSG="기준 이미지가 없음", **check_fields(checks(cur_q)))
        print("[알림] 기준 이미지가 없음 · 현재 화면만 받았음")
        return 0

    dx, dy, resp = measure(ref, img)
    cx, cy = int(round(dx / (w / gx))), int(round(dy / (h / gy)))
    rmean = float(cv2.cvtColor(ref, cv2.COLOR_BGR2GRAY).mean())
    ref_at = datetime.fromtimestamp(os.path.getmtime(ref_p)).strftime("%Y-%m-%d %H:%M")

    write_result(out_ini, OK=1, AT=at, HAS_REF=1, W=w, H=h,
                 DX=f"{dx:.1f}", DY=f"{dy:.1f}", RESP=f"{resp:.3f}",
                 CELL_X=cx, CELL_Y=cy, RESP_MIN=f"{SHIFT_RESP_MIN:.2f}",
                 MEAN=f"{mean:.0f}", REF_MEAN=f"{rmean:.0f}", REF_AT=ref_at,
                 MSG="", **check_fields(checks(cur_q, quality(ref), resp, (cx, cy))))
    print(f"[비교] 가로 {dx:+.1f}px({cx:+d}칸) · 세로 {dy:+.1f}px({cy:+d}칸) · "
          f"일치도 {resp:.3f} · 밝기 {rmean:.0f} -> {mean:.0f}")
    return 0


def set_position_since(ini_path, stamp):
    """continual_learning.ini 의 POSITION_SINCE 를 고친다. 주석과 순서는 그대로 둔다."""
    set_const_value(ini_path, "POSITION_SINCE", stamp)


def set_const_value(ini_path, name, value):
    """ini 의 [CONSTANTS] 안 name 값을 고친다. 주석과 순서는 그대로 둔다."""
    stamp = value
    with open(ini_path, "rb") as f:
        data = f.read()
    eol = "\r\n" if b"\r\n" in data else "\n"       # 원래 줄끝을 지킨다
    lines = data.decode("utf-8-sig").replace("\r\n", "\n").split("\n")
    out, done, in_const = [], False, False
    for ln in lines:
        key = ln.split("=", 1)[0].strip()
        if ln.strip().startswith("["):
            if in_const and not done:
                out.append(f"{name} = {stamp}")
                done = True
            in_const = ln.strip().upper() == "[CONSTANTS]"
        if in_const and key == name:
            if not done:
                out.append(f"{name} = {stamp}")
                done = True
            continue
        out.append(ln)
    if not done:
        if in_const:
            while out and out[-1] == "":
                out.pop()
            out.append(f"{name} = {stamp}")
            out.append("")
        else:
            out += ["[CONSTANTS]", f"{name} = {stamp}", ""]
    with open(ini_path, "w", encoding="utf-8", newline="") as f:
        f.write(eol.join(out))


def relocate(user_id):
    """칸 단위로 밀린 채 기준을 바꾼 뒤 2 · 3단계를 내린다. 위 [relocate] 참고."""
    config = Set_Env_Config(user_id, verbose=False)
    return _retire(config, "_retired_position", "카메라 자리가 바뀌어",
                   os.path.join(config["BASE_IMG_DIR"], RELOCATE_INI))


def recount(user_id, cells):
    """
    설비 칸 수(마스크의 1 개수)를 바꾼다. 위 [recount] 참고.

    2 · 3단계를 relocate 와 같이 내리고, POSITION_SINCE 를 적고, env.ini 의
    NUM_OF_MACHINE_CELLS 를 cells 로 고친다. 마스크 교체는 부른 쪽([관제서버 Mask
    받기] 창)이 이 도구가 성공한 뒤에 한다.
    """
    if not 1 <= cells <= 64:
        print(f"[recount] 칸 수는 1~64 여야 함: {cells}")
        return 2
    config = Set_Env_Config(user_id, verbose=False)
    up = config["LOCAL_USER_PATH"]
    old = int(config.get("NUM_OF_MACHINE_CELLS") or 0)
    rc = _retire(config, "_retired_recount", f"설비 칸 수가 바뀌어({old} -> {cells})",
                 os.path.join(up, RECOUNT_INI),
                 extra=lambda: (set_const_value(os.path.join(up, "env.ini"),
                                                "NUM_OF_MACHINE_CELLS", str(cells)),
                                f"설비 칸 수를 {old} -> {cells} 칸으로 바꿨음 (env.ini)")[1])
    return rc


def _retire(config, retired_dir, why, result_path, extra=None):
    """2 · 3단계를 내리고 POSITION_SINCE 를 적는다. relocate · recount 가 같이 쓴다."""
    up = config["LOCAL_USER_PATH"]
    now = datetime.now()
    stamp = now.strftime("%Y%m%d_%H%M%S")
    since = now.strftime("%Y-%m-%d %H:%M:%S")
    gen_root = os.path.join(up, "model_generations")
    done = []

    # 3단계 - 운용 모델을 옮기고 세대 표시를 비운다. 세대를 그대로 두면 감시가
    # 시작할 때 파일과 세대를 대조하다 어긋남으로 멈춘다.
    dst = os.path.join(gen_root, retired_dir, stamp)
    moved = []
    for name in MODEL_FILES:
        src = os.path.join(up, name)
        if os.path.exists(src):
            os.makedirs(dst, exist_ok=True)
            shutil.move(src, os.path.join(dst, name))
            moved.append(name)
    cg = os.path.join(up, "current_generation.txt")
    gen_was = ""
    if os.path.exists(cg):
        with open(cg, encoding="utf-8-sig") as f:
            gen_was = f.read().strip()
        with open(cg, "w", encoding="utf-8") as f:
            f.write("")
    if moved:
        with open(os.path.join(dst, "note.txt"), "w", encoding="utf-8") as f:
            f.write(f"{since} {why} 내렸다. 운용 세대 {gen_was or '-'}\n")
        done.append(f"3단계 모델을 내렸음 (세대 {gen_was or '-'} -> "
                    f"model_generations\\{retired_dir}\\{stamp})")
    else:
        done.append("3단계 모델이 없어 내릴 것이 없음")

    # 2단계 - 경험 임계값을 치우고 사유를 남긴다.
    bl = os.path.join(up, BASELINE_FILE)
    if os.path.exists(bl):
        rd = os.path.join(gen_root, "_retired_baseline")
        os.makedirs(rd, exist_ok=True)
        shutil.move(bl, os.path.join(rd, stamp + ".npz"))
        done.append(f"2단계 경험 임계값을 치웠음 (model_generations\\_retired_baseline\\{stamp}.npz)")
    else:
        done.append("2단계 경험 임계값이 없어 치울 것이 없음")
    write_reset_note(up, f"{why} 처음부터 쌓는 중", since)

    # 기간 - 그 앞의 프레임은 쓰지 않는다.
    set_position_since(os.path.join(up, "continual_learning.ini"), since)
    done.append(f"재학습 · 기여도 · 되쌓기는 {since} 이후 자료만 씀")

    if extra is not None:
        done.append(extra())

    cp = configparser.ConfigParser(interpolation=None)
    cp.optionxform = str
    cp["RESULT"] = {"OK": "1", "AT": since, "N": str(len(done))}
    for i, d in enumerate(done, 1):
        cp["RESULT"][f"L{i}"] = d
        print(f"[{retired_dir.strip('_')}]", d)
    with open(result_path, "w", encoding="utf-8") as f:
        cp.write(f)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("user_id")
    ap.add_argument("action", choices=["capture", "relocate", "recount"])
    ap.add_argument("cells", nargs="?", type=int, help="recount 의 새 칸 수")
    args = ap.parse_args()
    if args.action == "relocate":
        return relocate(args.user_id)
    if args.action == "recount":
        if args.cells is None:
            ap.error("recount 에는 새 칸 수가 필요함")
        return recount(args.user_id, args.cells)
    return capture(args.user_id)


if __name__ == "__main__":
    sys.exit(main())
