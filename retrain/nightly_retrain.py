# -*- coding: utf-8 -*-
"""
재학습 (연속 학습)

밤에 저절로 돌지 않는다. 작업 스케줄러에 등록된 것이 없고, 시각을 보고 스스로
도는 코드도 없다. [재학습] 창에서 [예행연습] 이나 [재학습 적용] 을 눌러야 돈다.
파일 이름의 nightly 는 처음에 밤마다 돌릴 생각으로 붙인 흔적이다.

  python retrain/nightly_retrain.py kict1
  python retrain/nightly_retrain.py kict1 --dry-run     시험만, 교체 안 함
  python retrain/nightly_retrain.py kict1 --rollback    직전 세대로 되돌림
  python retrain/nightly_retrain.py kict1 --rollback 20260923_144613
  python retrain/nightly_retrain.py kict1 --list        세대 목록

되돌리기는 오토인코더 모델만 돌린다. 경험 임계값은 건드리지 않는다 -
기준선이 세는 것은 모델의 오차가 아니라 "이 칸이 평소 몇 도까지 올라갔나"
라서, 모델을 갈아도 그대로 맞는다.

  python retrain/nightly_retrain.py kict1 --reset-baseline

기준선을 치우는 것은 따로 있는 일이다. 모델이 바뀌어서가 아니라 카메라가
보는 것이 달라졌을 때 쓴다 - 마스크를 다시 떴거나, 카메라 자리를 옮겼거나,
이상한 장면을 한참 정상으로 배워 넣었을 때.

--dry-run 은 모델을 저장하지 않는다. 결과는 보고서로 다 나오고 그 모델을
나중에 쓸 일이 없다. 세대는 실제 재학습에서만 생긴다.

절차는 넷이다.

  1. 히스토리 DB 에서 재생 버퍼를 만든다        (replay_buffer)
  2. 후보 모델을 학습한다
  3. 감도 회귀 시험을 통과해야만 승격한다       (sensitivity_gate)
  4. 세대별로 보관해 언제든 되돌릴 수 있게 한다


[왜 서빙 환경(mmc)에서 학습하는가]

D:\\autoencoder 의 기존 학습은 otg 환경(numpy 2.x)에서 돌리고, 그래서
scaler.pkl 이 서빙 환경(numpy 1.x)에서 안 읽혀 scaler.npz 로 우회해야
했다. 여기서는 서빙과 같은 환경에서 학습하므로 그 문제가 아예 없다.
모델이 작아(파라미터 수천 개) CPU 로도 몇 분이면 끝난다.

호환을 위해 scaler.npz 도 함께 남긴다 — 기존 배포본과 파일 구성을
맞춰야 predict_machine 의 폴백 경로가 그대로 동작한다.


[왜 자동으로 교체하지 않고 관문을 두는가]

sensitivity_gate 의 설명을 참고할 것. 요약하면, 정상 데이터에 잘 맞는
모델과 이상을 잡아내는 모델은 같지 않다. 검증 없이 세대를 거듭하면
조용히 둔감해진다.
"""

import argparse
import os
import json
import re
import shutil
import sys
from datetime import datetime, timedelta

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
import joblib
from sklearn.preprocessing import StandardScaler

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, "source"))
sys.path.insert(0, os.path.join(_ROOT, "predict_machine"))
sys.path.insert(0, _HERE)

from db_utils import Set_Env_Config, Get_HistoryDB_Config, Connect_History_DB, position_since

# 서빙이 쓰는 것과 똑같은 모델 정의를 그대로 가져온다. 여기에 복사해 두면
# 한쪽만 고쳐졌을 때 state_dict 로드가 깨지는데, 그 증상이 원인을 전혀
# 가리키지 않아 찾기 어렵다.
#
# load_scaler 도 같이 가져온다. 기존 배포본의 scaler.pkl 은 otg(numpy 2.x)
# 에서 만들어져 이 환경(numpy 1.x)에서 joblib.load 로는 열리지 않는다.
# 그냥 실패시키면 현재 모델과의 감도 비교가 조용히 생략되는데, 그 비교가
# 세대별 둔감화를 막는 핵심 장치라 빠지면 안 된다. load_scaler 는 같은
# 폴더의 scaler.npz 로 폴백해 준다.
from predict_machine import AutoEncoder, load_scaler

# 기준선을 치울 때 사유를 남기는 쪽지. 감시 쪽이 다음에 올라오며 읽는다.
from online_baseline import write_reset_note

import replay_buffer
import model_contribution
import sensitivity_gate
import artifact_guard

# --- 학습 설정 ----------------------------------------------------------
TARGET_SAMPLES = 60000

# env.ini 의 RETRAIN_MIN_SAMPLES 가 없을 때 쓰는 기본값.
# Dlg_Set_MmCam_Env.cpp 의 DEF_AE_SAMPLES 와 반드시 같아야 한다.
MIN_SAMPLES_DEFAULT = 5000

# env.ini 의 RETRAIN_MIN_HOURS 가 없을 때 쓰는 기본값.
# Dlg_Set_MmCam_Env.cpp 의 DEF_AE_HOURS 와 반드시 같아야 한다.
#
# 개수 조건만으로는 "낮에만 아는 모델" 을 막을 수 없다. kict1 은 표본
# 15,352건으로 최소 기준의 세 배를 넘겼지만 새벽 02~07시가 통째로 비어
# 있었다. 그대로 학습하면 평범한 새벽 3시를 이상으로 판정한다.
#
# 2단계 기준선에는 같은 뜻의 조건(BASELINE_MIN_HOURS)이 처음부터 있었는데
# 재학습에만 빠져 있었다. 값을 2단계와 같은 18 로 맞춘다.
MIN_HOURS_DEFAULT = 18
HOLDOUT_RATIO = 0.15
EPOCHS = 400
BATCH_SIZE = 512
LEARNING_RATE = 1e-4

# 보관할 세대 수. 오래된 것부터 지운다.
KEEP_GENERATIONS = 10

GEN_DIR_NAME = "model_generations"
ARTIFACTS = ("autoencoder_final.pth", "scaler.pkl", "scaler.npz")

# 경험 임계값. 세대 산출물이 아니라 운용 중에 쌓이는 상태다.
BASELINE_NAME = "online_baseline.npz"
RETIRED_DIR_NAME = "_retired_baseline"

# 예행연습 결과를 잠깐 두는 곳.
#
# 세대 폴더가 아니다. 목록에 나오지 않고 되돌릴 대상도 아니다. [재학습 적용]
# 이 곧바로 집어 갈 자리일 뿐이다.
DRYRUN_DIR_NAME = ".dryrun"

# 이만큼 지난 예행연습 결과는 다시 쓰지 않는다. 그 사이 새 프레임이 쌓여
# 자료가 달라졌을 수 있다.
DRYRUN_MAX_AGE_H = 6

# 승격 기록.
#
# 세대 폴더만 보고는 무엇이 실제로 운용에 올라갔는지 알 수 없다. --dry-run
# 후보도 같은 곳에 보관되기 때문이다. cj_busan_1 은 세대가 10개인데 승격된
# 것은 20260923_145111 하나였다. 폴더 순서로 "직전" 을 고르면 운용된 적
# 없는 후보로 되돌아간다.
HISTORY_NAME = "generation_history.txt"

# 묶음을 가르는 가로줄.
#
# 창의 로그 칸은 열 몇 줄이라 한 화면에 세 묶음이 함께 들어온다 - 기여도,
# 재생버퍼, 학습. 줄바꿈만으로는 어디서 갈리는지 보이지 않는다.
RULE = "-" * 113


# ======================================================================
# 세대 관리
# ======================================================================

def bands(config):
    """
    기여 가중치의 두 끝점. env.ini 의 [CONSTANTS] 로 덮어쓸 수 있다.

        CONTRIB_BAND_HIGH = 0.85    이 위면 기여 1.00
        CONTRIB_BAND_LOW  = 0.20    이 아래면 기여 0.00

    사이는 직선으로 잇는다. CONTRIB_BAND_MID 는 더 이상 쓰지 않는다.

    현장마다 점수 수준 자체가 다르다. kict1 은 재학습 뒤 0.92 인데
    cj_busan_1 은 같은 조건에서 0.73~0.82 다. 코드에 박지 않는 이유다.
    """
    hi, lo = model_contribution.DEFAULT_HIGH, model_contribution.DEFAULT_LOW
    v = config.get("CONTRIB_BAND_HIGH")
    if v not in (None, ""):
        try: hi = float(v)
        except (TypeError, ValueError): pass
    v = config.get("CONTRIB_BAND_LOW")
    if v not in (None, ""):
        try: lo = float(v)
        except (TypeError, ValueError): pass
    return (hi, lo)


def gen_root(user_path):
    return os.path.join(user_path, GEN_DIR_NAME)


def history_path(user_path):
    return os.path.join(user_path, HISTORY_NAME)


def read_history(user_path):
    """[(언제, 세대, 어떻게)] 를 기록된 순서대로. '#' 로 시작하는 줄은 주석."""
    p = history_path(user_path)
    if not os.path.exists(p):
        return []

    out = []
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [c.strip() for c in line.split("\t")]
            if len(parts) < 2 or not GEN_STAMP_RE.match(parts[1]):
                continue
            out.append((parts[0], parts[1], parts[2] if len(parts) > 2 else ""))
    return out


def append_history(user_path, stamp, how):
    p = history_path(user_path)
    new = not os.path.exists(p)
    with open(p, "a", encoding="utf-8") as f:
        if new:
            f.write("# 운용에 올라간 세대의 기록. 되돌리기가 이 순서를 거슬러 "
                    "간다.\n")
            f.write("# 언제\t세대\t어떻게\n")
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S}\t{stamp}\t{how}\n")


def served_generations(user_path):
    """운용에 올라간 세대를 순서대로. 연달아 같은 것은 하나로 본다."""
    out = []
    for _when, stamp, _how in read_history(user_path):
        if not out or out[-1] != stamp:
            out.append(stamp)
    return out


# 세대 폴더 이름은 YYYYMMDD_HHMMSS 다. 기준선 보관함(_retired_baseline)
# 처럼 세대가 아닌 폴더가 같은 곳에 있으므로 이름으로 가린다.
GEN_STAMP_RE = re.compile(r"^\d{8}_\d{6}$")


def list_generations(user_path):
    root = gen_root(user_path)
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if GEN_STAMP_RE.match(d)
                  and os.path.isdir(os.path.join(root, d)))


def save_generation(user_path, files, report):
    """후보 산출물을 세대 폴더에 보관하고 폴더명을 돌려준다."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(gen_root(user_path), stamp)
    os.makedirs(dst, exist_ok=True)

    for name, path in files.items():
        shutil.copy2(path, os.path.join(dst, name))

    with open(os.path.join(dst, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")

    # 오래된 세대 정리. 단 운용에 올라간 적이 있는 것은 지우지 않는다 -
    # 그것을 지우면 되돌릴 곳이 사라진다.
    served = set(served_generations(user_path))
    gens = list_generations(user_path)
    for old in gens[:-KEEP_GENERATIONS]:
        if old in served:
            continue
        shutil.rmtree(os.path.join(gen_root(user_path), old), ignore_errors=True)

    return stamp


def dryrun_dir(user_path):
    return os.path.join(user_path, DRYRUN_DIR_NAME)


def save_dry_run(user_path, user_id, files, report, passed, incumbent):
    """
    예행연습 결과를 잠깐 둔다.

    [왜 두는가]

    학습에는 시드가 없다. DataLoader 의 shuffle 도, 웜스타트가 아닐 때의
    초기화도 매번 다르다. 그래서 같은 자료로 두 번 돌리면 다른 모델이
    나온다.

    예행연습에서 본 보고서와 [재학습 적용] 이 올리는 모델이 서로 다른
    모델이라는 뜻이다. 판정을 읽고 눌렀는데 다른 것이 올라간다. 본 것을
    그대로 올리는 편이 맞다.

    세대 폴더에는 두지 않는다. 승격되지 않은 후보로 목록이 차면 정작
    되돌릴 대상을 가린다.
    """
    d = dryrun_dir(user_path)
    shutil.rmtree(d, ignore_errors=True)
    os.makedirs(d, exist_ok=True)

    for name, path in files.items():
        shutil.copy2(path, os.path.join(d, name))

    with open(os.path.join(d, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")

    meta = {
        "user": user_id,
        "created": f"{datetime.now():%Y-%m-%d %H:%M:%S}",
        "passed": bool(passed),
        "incumbent": incumbent,
    }
    with open(os.path.join(d, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)

    return d


def clear_dry_run(user_path):
    shutil.rmtree(dryrun_dir(user_path), ignore_errors=True)


def load_dry_run(user_path, user_id):
    """
    다시 쓸 만한 예행연습 결과가 있으면 (폴더, meta) 를, 없으면 (None, 사유).

    까다롭게 본다. 조건이 하나라도 어긋나면 새로 학습하는 편이 안전하다.
    """
    d = dryrun_dir(user_path)
    mp = os.path.join(d, "meta.json")
    if not os.path.exists(mp):
        return None, "예행연습 결과가 없습니다"

    try:
        with open(mp, encoding="utf-8") as f:
            meta = json.load(f)
    except (OSError, ValueError) as e:
        return None, f"예행연습 기록을 읽지 못했습니다 ({e})"

    if meta.get("user") != user_id:
        return None, "다른 현장의 예행연습 결과입니다"

    if not meta.get("passed"):
        return None, "그 예행연습은 승격 판정이 아니었습니다"

    for name in ARTIFACTS:
        if not os.path.exists(os.path.join(d, name)):
            return None, f"예행연습 결과에 {name} 이 없습니다"

    cur = ""
    cp = os.path.join(user_path, "current_generation.txt")
    if os.path.exists(cp):
        cur = open(cp, encoding="utf-8").read().strip()
    if meta.get("incumbent", "") != cur:
        return None, (f"그 사이 운용 모델이 바뀌었습니다 "
                      f"({meta.get('incumbent') or '없음'} -> {cur or '없음'})")

    try:
        made = datetime.strptime(meta["created"], "%Y-%m-%d %H:%M:%S")
    except (KeyError, ValueError):
        return None, "예행연습 시각을 읽지 못했습니다"

    age_h = (datetime.now() - made).total_seconds() / 3600.0
    if age_h > DRYRUN_MAX_AGE_H:
        return None, (f"예행연습이 {age_h:.1f}시간 전이라 너무 오래됐습니다 "
                      f"(기준 {DRYRUN_MAX_AGE_H}시간)")

    meta["age_h"] = age_h
    return d, meta


def gen_score(user_path, stamp):
    """세대의 학습 직후 정상 평균 점수. 보고서에서 읽는다. 없으면 None."""
    if not stamp:
        return None
    p = os.path.join(gen_root(user_path), stamp, "report.txt")
    if not os.path.exists(p):
        return None
    try:
        for line in open(p, encoding="utf-8"):
            if "정상 평균 점수" in line:
                nums = re.findall(r"[0-9]+\.[0-9]+", line)
                if nums:
                    return float(nums[0])
    except OSError:
        pass
    return None


def print_base_info(user_path):
    """
    무엇에서 출발하는지 먼저 적는다.

    보고서 끝에만 적어 두면, 몇 분을 기다린 뒤에야 "무엇과 견준 결과인지" 를
    알게 된다. 시작할 때 보이면 잘못된 기준에서 출발하는 것을 바로 멈출 수
    있다 - 되돌린 직후처럼 운용 세대가 예상과 다를 때가 있다.

    한 줄에 세 가지만 적는다. 세대 수 · 기준일 · 문턱까지 붙였더니 줄이 길어
    정작 중요한 앞부분이 묻혔다. 기준일과 문턱은 실제로 작용할 때 따로
    적힌다 - 재생버퍼 경고와 기여도 줄에서.
    """
    cur = ""
    cp = os.path.join(user_path, "current_generation.txt")
    if os.path.exists(cp):
        cur = open(cp, encoding="utf-8").read().strip()

    when = ""
    for w, stamp, _how in reversed(read_history(user_path)):
        if stamp == cur:
            when = w
            break

    sc = gen_score(user_path, cur)

    line = (f"[기준모델] 세대 {cur or '없음'}"
            + (f" · 올린 때 {when[:16]}" if when else "")
            + (f" · 점수 {sc:.3f}" if sc is not None else " · 점수 -"))
    print(line)
    return line


def reset_baseline(user_path, why=""):
    """
    경험 임계값을 치운다. --reset-baseline 을 줄 때만 부른다.

    [모델을 갈았다고 치울 일이 아니다]

    예전에는 되돌릴 때마다 함께 치웠다. "기준선은 그 모델이 칸마다 내는
    오차의 분포라, 모델을 갈면 어긋난다" 는 것이 이유였는데 사실이 아니다.
    기준선이 세는 것은 오차가 아니라 **칸의 온도 그 자체**다 (0~255 도를
    256구간 히스토그램에 넣고 분위수를 뽑는다). 채점도 "이 칸이 평소 선보다
    몇 도 높은가" 로, 오토인코더가 끼어들지 않는다.

    그래서 모델을 되돌려도 기준선은 그대로 맞다. 치우면 3,000건·18시간대를
    다시 쌓는 동안(cj_busan_1 은 하루 넘게) 칸별 임계치 없이 돌 뿐이다.

    [그러면 언제 치우는가]

    카메라가 보는 것이 달라졌을 때다. 마스크를 다시 떴거나, 카메라 자리를
    옮겼거나, 이상한 장면을 한참 정상으로 배워 넣었을 때. 그때는 쌓인
    온도 분포가 지금 화면의 것이 아니다.

    [왜 지우지 않고 옮기는가]

    치운 것을 다시 되돌릴 수 있어야 한다. 기준선은 다시 쌓는 데 시간이
    걸리고(MIN_SAMPLES 3,000 · 시간대 조건) 그 동안 현장은 임계치 없이
    돈다. 잘못 판단해 치웠다면 파일을 되돌려 놓는 것이 가장 빠른 복구다.

    파일이 없으면 OnlineBaseline.load() 가 새로 시작하므로 따로 알릴 것은
    없다.
    """
    src = os.path.join(user_path, BASELINE_NAME)
    if not os.path.exists(src):
        print("[기준선] 쌓인 것이 없어 치울 것도 없습니다.")
        return None

    dst_dir = os.path.join(gen_root(user_path), RETIRED_DIR_NAME)
    os.makedirs(dst_dir, exist_ok=True)
    dst = os.path.join(dst_dir,
                       datetime.now().strftime("%Y%m%d_%H%M%S") + ".npz")
    shutil.move(src, dst)

    # 치운 것이 쌓이면 오래된 것부터 지운다.
    kept = sorted(f for f in os.listdir(dst_dir) if f.endswith(".npz"))
    for old_f in kept[:-KEEP_GENERATIONS]:
        try:
            os.remove(os.path.join(dst_dir, old_f))
        except OSError:
            pass

    # 왜 치웠는지를 쪽지로 남긴다.
    #
    # 치우고 나면 감시 쪽에서 보이는 것은 "파일이 없다" 뿐이라 설치 직후와
    # 구별되지 않는다. 사유를 아는 것은 치운 이쪽뿐이다.
    write_reset_note(user_path, why if why else "부터 쌓는 중")

    tail = f" ({why})" if why else ""
    print(f"[기준선] 치웠습니다{tail} - "
          f"{GEN_DIR_NAME}/{RETIRED_DIR_NAME}/{os.path.basename(dst)}")
    print("[기준선] 다시 쌓는 동안에는 칸별 임계치가 나오지 않습니다. "
          "절대 온도 임계치는 그대로 작동합니다.")
    return dst


def archive_incumbent(user_path):
    """
    물러나는 운용 모델을 세대로 떠 둔다. 덮어쓰기 전에 부른다.

    [왜 필요한가]

    activate() 는 산출물을 users/<id>/ 에 제자리 복사한다. 그래서 첫 승격
    때 그 전까지 돌던 모델이 흔적 없이 사라진다. cj_busan_1 이 그렇게
    되었다 - 2026-09-23 14:51 에 20260923_145111 이 올라가면서 점수 0.81
    짜리 모델이 사라졌고, 어디에도 남지 않았다.

    이미 세대로 보관된 것(current_generation.txt 가 가리키는 것)이면 다시
    뜰 필요가 없다.
    """
    cur = ""
    cp = os.path.join(user_path, "current_generation.txt")
    if os.path.exists(cp):
        cur = open(cp, encoding="utf-8").read().strip()
    if cur and cur in list_generations(user_path):
        return None

    live = [(n, os.path.join(user_path, n)) for n in ARTIFACTS]
    live = [(n, q) for n, q in live if os.path.exists(q)]
    if not live:
        return None

    # 이름은 모델 파일의 시각에서 딴다. 언제부터 돌던 것인지가 남는다.
    mp = os.path.join(user_path, "autoencoder_final.pth")
    base = datetime.fromtimestamp(os.path.getmtime(mp)) if os.path.exists(mp) \
        else datetime.now()
    # 이름이 겹치면 초를 밀어 비킨다. 접미사를 붙이면 세대 이름 형식
    # (YYYYMMDD_HHMMSS · 15자)에서 벗어나 목록에서 빠진다.
    stamp = base.strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(gen_root(user_path), stamp)
    tries = 0
    while os.path.isdir(dst):
        tries += 1
        if tries > 60:
            print("[경고] 보관할 이름을 찾지 못해 물러나는 운용 모델을 뜨지 "
                  "못했습니다.")
            return None
        stamp = (base + timedelta(seconds=tries)).strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(gen_root(user_path), stamp)

    os.makedirs(dst, exist_ok=True)
    for name, q in live:
        shutil.copy2(q, os.path.join(dst, name))

    with open(os.path.join(dst, "report.txt"), "w", encoding="utf-8") as f:
        f.write(f"보관 {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
                f"승격 전에 물러나는 운용 모델을 그대로 떠 둔 것입니다. 학습\n"
                f"후보가 아니므로 감도 회귀 시험 결과가 없습니다.\n\n"
                f"모델 파일 시각 {base:%Y-%m-%d %H:%M:%S}\n")

    print(f"[보관] 물러나는 운용 모델을 {GEN_DIR_NAME}/{stamp} 로 떠 두었습니다.")
    return stamp


def activate(user_path, stamp, how="승격"):
    """
    세대 하나를 운용 모델로 올리고 기록에 남긴다.

    기록이 없으면 무엇이 실제로 돌았는지 알 수 없다. 폴더에는 --dry-run
    후보가 섞여 있어 순서만으로는 구별되지 않는다.
    """
    # 아직 세대로 안 뜬 운용 모델이 있으면 먼저 뜬다. 그래야 되돌릴 곳이
    # 생기고, 그 모델이 기록의 첫 줄이 된다.
    kept = archive_incumbent(user_path)
    if kept:
        append_history(user_path, kept, "보관(기록 이전부터 운용 중)")

    src = os.path.join(gen_root(user_path), stamp)
    for name in ARTIFACTS:
        s = os.path.join(src, name)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(user_path, name))

    with open(os.path.join(user_path, "current_generation.txt"),
              "w", encoding="utf-8") as f:
        f.write(stamp + "\n")

    # 올린 것이 정말 올라갔는지 그 자리에서 확인한다.
    #
    # 2026-09-25 cj_busan_1 은 스케일러만 세대 것이고 모델은 엿새 전
    # 파일이었다. 어떻게 그렇게 됐는지는 끝내 알 수 없었다 - 복사가 조용히
    # 실패했거나 누가 덮어썼거나. 원인을 모르면 막을 수 없으니, 적어도
    # 어긋난 채로 끝나지는 않게 한다.
    #
    # 여기서 막지 않으면 감시가 틀린 점수를 내며 돈다. 화면에는 숫자가 떠
    # 있어 아무도 눈치채지 못한다.
    state, msg, rows = artifact_guard.check(user_path)
    if state == artifact_guard.MISMATCH:
        print(f"[ERROR] 올린 뒤 대조에 실패했습니다: {msg}")
        for name, a, b in rows:
            if a != b:
                print(f"        {name}  운용 {a}  세대 {b}")
        print("        다시 시도하거나, 다른 프로그램이 이 파일을 쥐고 "
              "있지 않은지 확인하십시오.")
        raise RuntimeError(f"activate 실패: {msg}")

    append_history(user_path, stamp, how)


# ======================================================================
# 학습
# ======================================================================

def train(X, input_dim, latent_dim, device, verbose=True,
          init_state=None, old_weight=1.0, dynamic_mix=False):
    """
    init_state   기존 모델의 가중치. 주면 거기서 출발한다(웜스타트).
    old_weight   기존 모델을 얼마나 물려받을지(0.0~1.0).
    dynamic_mix  재생버퍼 동적구성이 켜져 있는가. 꺼져 있으면 w 를 보지 않고 늘
                 웜스타트한다. 켜져 있을 때만 w=0 이 "새로 초기화" 를 뜻한다.

    웜스타트는 지난 세대가 찾아 놓은 자리에서 시작하므로 적은 자료로도 빨리
    수렴한다. 학습률은 w 와 무관하게 늘 LEARNING_RATE 로 고정한다. 예전에는
    물려받는 정도가 낮을수록 올렸으나, w 가 표본 구성과 학습률 두 곳에서 한꺼번에
    작용해 결과를 읽기 어려웠다.

    동적구성이 켜져 있고 old_weight = 0 이면 아예 새로 초기화한다. 카메라가 완전히
    다른 곳을 보고 있는데 그 자리에서 출발할 이유가 없다.
    """
    scaler = StandardScaler().fit(X)
    Xs = torch.tensor(scaler.transform(X), dtype=torch.float32)

    model = AutoEncoder(input_dim, latent_dim, input_dim).to(device)

    lr = LEARNING_RATE
    warm = init_state is not None and (not dynamic_mix or old_weight > 0.0)
    if warm:
        try:
            model.load_state_dict(init_state)
            if verbose:
                why = (f"동적구성 꺼짐, 기여 {old_weight:.2f} 와 무관"
                       if not dynamic_mix else f"기여 {old_weight:.2f}")
                print(f"[학습] 웜스타트 ({why}, 학습률 {lr:.5f})")
        except Exception as e:
            print(f"[경고] 웜스타트 실패, 새로 초기화합니다: {type(e).__name__} {e}")
    elif verbose:
        print(f"[학습] 새로 초기화 (기여 {old_weight:.2f})")

    opt = optim.Adam(model.parameters(), lr=lr)
    lossf = nn.MSELoss()

    loader = torch.utils.data.DataLoader(
        torch.utils.data.TensorDataset(Xs, Xs),
        batch_size=BATCH_SIZE, shuffle=True)

    model.train()
    for ep in range(EPOCHS):
        total = 0.0
        for xb, yb in loader:
            xb, yb = xb.to(device), yb.to(device)
            opt.zero_grad()
            loss = lossf(model(xb), yb)
            loss.backward()
            opt.step()
            total += loss.item() * len(xb)
        if verbose and (ep + 1) % 100 == 0:
            print(f"           epoch {ep+1}/{EPOCHS}  loss {total/len(Xs):.6f}")

    return model, scaler


def save_scaler(scaler, pkl_path):
    joblib.dump(scaler, pkl_path)
    np.savez(
        os.path.splitext(pkl_path)[0] + ".npz",
        mean_=scaler.mean_, scale_=scaler.scale_, var_=scaler.var_,
        n_features_in_=scaler.n_features_in_,
        n_samples_seen_=scaler.n_samples_seen_,
        with_mean=scaler.with_mean, with_std=scaler.with_std,
    )


def load_live_model(user_path, n_cells, latent_dim, device):
    """
    지금 운용 중인 모델과 스케일러를 읽는다.

    아직 모델이 없으면 (None, None). 첫 학습이라 정상이다.

    파일은 있는데 읽지 못하면 RuntimeError 를 낸다. 그 상태로 재학습하면
    안 되기 때문이다 - 표본은 옛 판단으로 거르고 웜스타트는 지금 가중치로
    하는, 짝이 맞지 않는 학습이 된다. 격자나 잠재 차원을 바꾼 경우라면 그
    가중치는 층 모양조차 다르다.

    세 곳에서 쓴다 - 기여도를 구할 때 프레임을 다시 매기는 데, 표본을 거를
    때, 그리고 감도 회귀 시험에서 새 후보와 견주는 데.
    """
    mp = os.path.join(user_path, "autoencoder_final.pth")
    sp = os.path.join(user_path, "scaler.pkl")

    if not os.path.exists(mp) and not os.path.exists(sp):
        return None, None               # 첫 학습

    if not os.path.exists(mp):
        raise RuntimeError("scaler 는 있는데 autoencoder_final.pth 가 없습니다")
    if not os.path.exists(sp):
        raise RuntimeError("모델은 있는데 scaler.pkl 이 없습니다")

    try:
        m = AutoEncoder(n_cells, latent_dim, n_cells).to(device)
        m.load_state_dict(torch.load(mp, map_location=device))
        sc = load_scaler(sp)
    except Exception as e:
        raise RuntimeError(f"{type(e).__name__} {e}")

    got = getattr(sc, "n_features_in_", None)
    if got != n_cells:
        raise RuntimeError(f"scaler 의 차원 {got} 이 격자 {n_cells} 와 다릅니다")

    return m, sc


def load_mask(user_path, n_cells):
    p = os.path.join(user_path, "hotlist_mask_local.ini")
    if not os.path.exists(p):
        return np.ones(n_cells, dtype=np.int32)
    rows = [l.split() for l in open(p, encoding="utf-8").read().splitlines()
            if l.strip()]
    return np.array([[int(v) for v in r] for r in rows]).flatten()


# ======================================================================
# main
# ======================================================================

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("user_id")
    ap.add_argument("--dry-run", action="store_true",
                    help="학습과 시험만 하고 운용 모델을 바꾸지 않는다")
    ap.add_argument("--rollback", nargs="?", const="__prev__",
                    help="지정 세대(없으면 운용 중인 것의 직전)로 되돌린다")
    ap.add_argument("--list", action="store_true", help="세대 목록")
    ap.add_argument("--fresh", action="store_true",
                    help="예행연습 결과를 다시 쓰지 않고 새로 학습한다")
    # 기준선 치우기. 되돌리기와 섞이지 않는 독립된 일이다.
    ap.add_argument("--reset-baseline", action="store_true",
                    help="경험 임계값을 치우고 처음부터 다시 쌓게 한다 "
                         "(마스크를 다시 떴거나 카메라를 옮겼을 때). "
                         "모델·세대는 건드리지 않는다")
    # 옛 이름. 되돌리기가 더 이상 기준선을 치우지 않아 할 일이 없지만,
    # 적어 둔 명령이 깨지지 않게 받기만 한다.
    ap.add_argument("--keep-baseline", action="store_true",
                    help=argparse.SUPPRESS)
    args = ap.parse_args()

    # 읽은 파일은 제목 아래에 적는다. 여기서 찍으면 제목 위로 올라간다.
    config = Set_Env_Config(args.user_id, verbose=False)
    user_path = config["LOCAL_USER_PATH"]
    n_cells = config["X_GRID"] * config["Y_GRID"]
    latent_dim = int(config["SZ_OF_LATENT_DIM_AUTOENCODER"])
    device = torch.device("cpu")

    # ---------------- 세대 목록 ----------------
    if args.list:
        gens = list_generations(user_path)
        cur = ""
        cp = os.path.join(user_path, "current_generation.txt")
        if os.path.exists(cp):
            cur = open(cp, encoding="utf-8").read().strip()
        if not gens:
            print("보관된 세대가 없습니다.")
            return 0
        served = set(served_generations(user_path))
        for g in gens:
            tag = "   <= 운용 중" if g == cur else \
                  ("   (운용된 적 있음)" if g in served else "   승격 안 됨")
            print(f"  {g}{tag}")
        if not served:
            print()
            print(f"  승격 기록({HISTORY_NAME})이 없습니다. 어느 것이 실제로 "
                  f"운용되었는지 알 수 없습니다.")
        return 0

    # ---------------- 기준선 치우기 ----------------
    #
    # 세대·모델과 아무 상관이 없는 일이다. 카메라가 보는 것이 달라졌을 때
    # 쌓인 온도 분포를 버리는 것뿐이라, 되돌리기에 얹지 않고 따로 둔다.
    if args.reset_baseline:
        reset_baseline(user_path, "부터 쌓는 중")
        return 0

    # ---------------- 되돌리기 ----------------
    if args.rollback:
        gens = list_generations(user_path)
        if not gens:
            print("[ERROR] 되돌릴 세대가 없습니다.")
            return 1

        if args.rollback != "__prev__":
            target = args.rollback
        else:
            # "직전" 은 폴더 순서가 아니라 **승격 기록** 을 거슬러 간다.
            #
            # --dry-run 후보가 같은 폴더에 보관되므로 순서로는 구별되지
            # 않는다. cj_busan_1 은 세대 10개 중 승격된 것이 20260923_145111
            # 하나였고, 폴더 기준으로 "직전" 을 고르면 운용된 적 없는
            # 20260923_144613 으로 갔다.
            served = served_generations(user_path)
            if not served:
                print(f"[ERROR] 승격 기록({HISTORY_NAME})이 없어 직전 세대를 "
                      f"알 수 없습니다.")
                print(f"        --list 로 세대를 확인한 뒤 "
                      f"--rollback <세대> 로 지정하십시오.")
                return 1

            cur = ""
            cp = os.path.join(user_path, "current_generation.txt")
            if os.path.exists(cp):
                cur = open(cp, encoding="utf-8").read().strip()
            if cur and served[-1] != cur:
                print(f"[경고] 기록의 마지막({served[-1]})과 운용 중인 "
                      f"세대({cur})가 다릅니다. 기록을 기준으로 삼습니다.")

            if len(served) < 2:
                print(f"[ERROR] 운용에 올라간 세대가 {served[-1]} 하나뿐이라 "
                      f"되돌릴 곳이 없습니다.")
                print(f"        나머지 세대는 감도 시험에서 막혀 운용된 적이 "
                      f"없습니다. --rollback <세대> 로 지정하면 그 후보를 "
                      f"올릴 수는 있습니다.")
                return 1

            target = served[-2]
            print(f"[되돌리기] 운용 중 {served[-1]} -> 직전 {target}")

        if target not in gens:
            print(f"[ERROR] 그런 세대가 없습니다: {target}")
            return 1
        activate(user_path, target, how="되돌림")

        # 되돌리기는 모델만 돌린다. 기준선은 칸의 온도 분포지 모델의
        # 산물이 아니라, 여기서 다룰 일이 아니다. 치워야 한다면 그것은
        # 모델이 아니라 카메라가 보는 것이 달라졌다는 뜻이고, 그때는
        # --reset-baseline 을 따로 돌린다.
        print(f"[OK] {target} 세대로 되돌렸습니다. "
              f"감시가 곧 알아채고 갈아 끼웁니다(10초 안).")
        return 0

    # ---------------- 재학습 ----------------
    print(RULE)
    print(f"재학습  {args.user_id}   {datetime.now():%Y-%m-%d %H:%M:%S}")
    print(RULE)

    # 이 판단을 좌우하는 파일을 적는다.
    #
    # 예전에는 env.ini 를 적었는데, 재학습에 쓰이는 값은 모두 여기로 옮겼다.
    # 무엇을 고쳐야 결과가 달라지는지 바로 알 수 있어야 한다.
    # normpath 로 고른다. LOCAL_USER_PATH 는 빗금 방향이 섞여 있고 끝에도
    # 빗금이 붙어 있어, 그냥 이으면 D:/A//users/... 처럼 보인다.
    print("[설정파일] " + os.path.normpath(
        os.path.join(user_path, "continual_learning.ini")))

    base_line = print_base_info(user_path)
    comp_line = ""
    print()
    print(RULE)

    # 예행연습에서 본 그 모델을 그대로 올린다.
    #
    # 학습에는 시드가 없어 같은 자료로 다시 돌리면 다른 모델이 나온다.
    # 판정을 읽고 [재학습 적용] 을 눌렀는데 다른 것이 올라가면 무엇을 보고
    # 결정한 것인지 알 수 없다. 본 것을 올린다.
    if not args.dry_run and not args.fresh:
        d, info = load_dry_run(user_path, args.user_id)
        if d:
            print(f"[예행연습] {info['created']} 결과를 그대로 올립니다 "
                  f"({info['age_h']*60:.0f}분 전).")
            print("           같은 자료로 다시 학습하면 다른 모델이 나옵니다. "
                  "보신 그 모델을 올립니다.")
            print("           새로 학습하려면 --fresh 를 붙이십시오.")

            files = {n: os.path.join(d, n) for n in ARTIFACTS
                     if os.path.exists(os.path.join(d, n))}
            report = ""
            rp = os.path.join(d, "report.txt")
            if os.path.exists(rp):
                report = open(rp, encoding="utf-8").read().rstrip("\n")
            print()
            print(report)
            print()

            stamp = save_generation(user_path, files, report)
            print(f"[보관] {GEN_DIR_NAME}/{stamp}")

            activate(user_path, stamp)
            clear_dry_run(user_path)
            print(f"[승격] {stamp} 을 운용 모델로 배치했습니다.")
            print("       감시가 곧 알아채고 갈아 끼웁니다(10초 안). "
                  "재시작하지 않아도 됩니다.")
            return 0

        print(f"[예행연습] 다시 쓸 결과가 없어 새로 학습합니다 - {info}")

    mask = load_mask(user_path, n_cells)

    # 운용 모델을 읽지 못하면 여기서 멈춘다.
    #
    # 읽지 못하는 모델로는 기여도도 못 재고 표본도 못 거른다. 그대로 가면
    # 그때그때 다른 모델의 판단이 섞인 표본으로, 뜻이 없는 가중치를 이어
    # 학습하게 된다. 무엇이 잘못됐는지 적고 멈추는 편이 낫다.
    try:
        live_model, live_scaler = load_live_model(user_path, n_cells,
                                                  latent_dim, device)
    except RuntimeError as e:
        print(f"[중단] 운용 모델을 읽지 못했습니다 - {e}")
        print()
        print("       흔한 까닭")
        print("         · scaler.pkl 이 이 환경의 numpy 로 안 풀리고 "
              "scaler.npz 도 낡았다")
        print("         · env.ini 의 격자(X_GRID/Y_GRID)나 "
              "잠재 차원을 바꿨다")
        print("         · 산출물이 복사 도중이거나 깨졌다")
        print()
        print("       [되돌리기] 로 멀쩡한 세대를 올린 뒤 다시 하십시오.")
        return 1

    history_db = Get_HistoryDB_Config(config)
    conn = Connect_History_DB(history_db)
    try:
        # ---------------- 기존 모델을 얼마나 물려받을지 ----------------
        #
        # 카메라가 밀렸는지가 아니라 '지금 몇 점을 내고 있는지' 로 정한다.
        # 실측에서 칸 수는 모델 손상을 예측하지 못했다 - 3칸을 밀어도 0.890
        # 이었고, kict1 은 1.3칸에 0.088 이었다.
        # DB 에 적힌 점수는 그때 돌던 모델의 것이다. 세대를 갈아 끼운 날이면
        # 여러 모델의 점수가 섞여 지금 모델의 성적이 아니다. 표본을 뽑아
        # 지금 모델로 다시 매긴다.
        rescore = None
        if live_model is not None:
            rescore = model_contribution.batch_scorer(
                live_model, live_scaler, mask, device)
        else:
            print("[기여도] 아직 운용 모델이 없어 DB 에 적힌 점수로 판단합니다.")

        n_tab, min_fr, max_sm = model_contribution.limits(config)
        dec_score, dec_info = model_contribution.decision_score(
            conn, history_db["database"], n_cells, mask=mask,
            temp_warn=config.get("ABS_TEMP_WARN"), score_fn=rescore,
            n_tables=n_tab, min_frames=min_fr, max_samples=max_sm,
            since=position_since(config))
        old_weight = model_contribution.weight_for(dec_score, bands(config))
        print(f"[기여도] {model_contribution.describe(dec_score, old_weight)}")
        print()
        print(RULE)

        # 표본을 고르는 잣대를 기여 가중치에 맞춘다.
        #
        # replay_buffer 는 원래 'mscore >= 0.5 인 정상 프레임' 만 담는다.
        # 그런데 그 점수를 매긴 것이 바로 지금 버리기로 한 모델이다.
        # kict1 은 모든 프레임이 0.085 라 정상 프레임이 0건이 되고 재학습이
        # 아예 멈춘다 - 망가진 모델이 자기 후임을 못 만들게 막는 꼴이다.
        #
        # 모델을 못 믿기로 했으면 그 판단으로 표본을 걸러서도 안 된다.
        # 대신 1단계 절대 임계값으로 거른다. 학습과 무관하게 늘 동작하는
        # 유일한 판단이고, 이상 프레임을 학습에 넣지 않는다는 목적도 지킨다.
        # 학습 표본 구성 규칙. [설정] 창에서 바꾼다.
        target = int(config.get("RETRAIN_TARGET_SAMPLES") or TARGET_SAMPLES)
        # 재생버퍼 동적 구성. 켜면 옛/새 비율을 기여 w 로 정하고(새 시기 = 판단 구간,
        # 곧 최근 N일), 끄면(기본) w 를 보지 않고 옛/새를 가르지 않은 채 전체에서 뽑는다.
        dynamic_mix = bool(int(config.get("RETRAIN_DYNAMIC_MIX") or 0))
        # 재생버퍼 수집 일수. 0 이거나 비어 있으면 DB 에 있는 전체.
        buffer_days = int(config.get("RETRAIN_BUFFER_DAYS") or 0)

        # 거르는 잣대는 기여와 무관하다.
        #
        # 예전에는 기여 1.00 이면 모델 점수로, 미만이면 절대 임계값으로
        # 걸렀다. 모델을 믿느냐에 따라 잣대를 바꾼 것인데, 믿는 쪽이 오히려
        # 위험했다 - 모델이 틀린 자리가 표본에서 빠져 다음 세대도 똑같이
        # 틀렸다. 이제 언제나 절대 임계값과 칸별 분위수로 거른다.
        temp_warn = config.get("ABS_TEMP_WARN")
        if temp_warn is None:
            print("[경고] ABS_TEMP_WARN 이 비어 있어 이상 프레임을 걸러낼")
            print("       잣대가 하나도 없습니다. 들어온 것을 모두 학습합니다.")
            print("       [설정] 창에서 절대 임계값을 지정하십시오.")
        else:
            print(f"[재생버퍼] 정상 판정 기준 : 절대 임계값 < {temp_warn:.0f}도")

        # 옛/새 표본 비율의 규칙을 적는다.
        #
        # 비율을 따로 정하는 곳이 없다는 것을 화면에서 알 수 있어야 한다.
        # 기여가 정해지면 비율은 따라온다. 그리고 가르지 않는 경우가 오히려
        # 흔한데(기여 1.00 이거나 기준일이 비어 있으면), 그때 무엇을 기준으로
        # 뽑는지가 지금까지 어디에도 없었다.
        _rule = "[재생버퍼] 옛샘플 (판단 구간 이전) 새샘플 = 기여 : 1-기여"
        if not dynamic_mix:
            print("[재생버퍼] 옛/새를 가르지 않고 전체에서 뽑음   "
                  "(동적구성 꺼짐 - 기여 w 를 보지 않음)")
        elif old_weight >= 1.0:
            print(f"{_rule}   (기여 1.00 이라 가르지 않고 전체에서 뽑음)")
        else:
            print(f"{_rule} = {old_weight:.2f} : {1.0 - old_weight:.2f} "
                  f"(새 시기 = 최근 {n_tab}일)")

        X, info = replay_buffer.collect(
            conn, history_db["database"], n_cells, target, mask=mask,
            split_days=n_tab, old_weight=old_weight,
            temp_warn=temp_warn, dynamic_mix=dynamic_mix,
            recent_days=buffer_days, since=position_since(config))
    finally:
        conn.close()

    # 최소 표본 수는 모니터링 프로그램의 [설정] 창에서 바꾼다.
    min_samples = config.get("RETRAIN_MIN_SAMPLES") or MIN_SAMPLES_DEFAULT

    min_hours = config.get("RETRAIN_MIN_HOURS") or MIN_HOURS_DEFAULT

    if len(X) < min_samples:
        print(f"[보류] 표본이 {len(X):,}건뿐입니다. 최소 {min_samples:,}건이 필요합니다.")
        print("       2단계 기준선이 채점을 시작한 뒤부터 정상 프레임이 쌓입니다.")
        return 2

    if info.get("hours", 0) < min_hours:
        print(f"[보류] 덮은 시간대가 {info.get('hours', 0)}개뿐입니다. "
              f"최소 {min_hours}개가 필요합니다.")
        print("       표본 수는 충분해도 특정 시간대만 배우면 나머지 시간을")
        print("       이상으로 판정합니다. 감시를 더 돌려 하루 주기를 덮으십시오.")
        return 2

    cut = int(len(X) * (1 - HOLDOUT_RATIO))
    X_train, X_hold = X[:cut], X[cut:]
    # 무엇으로 배우는지 한 자리에 모아 적는다. 위에 흩어진 줄만으로는
    # "이번 학습이 어떤 자료로 이뤄지는가" 를 한눈에 볼 수 없다.
    # 이것도 한 줄이다. 창이 집어 고정된 자리에 보인다.
    #
    # 표본은 날짜마다 같은 몫, 하루 안에서는 시간대마다 같은 몫으로 뽑는다.
    comp_line = (f"[재생버퍼] 표본 {info['drawn']:,}/{target:,}"
                 f" · 시간대 {info.get('hours', 0)}/{min_hours}"
                 f" · 기간 {info['period']}"
                 + f" · 기여 {old_weight:.2f}")
    print(comp_line)
    print()
    print(RULE)
    print()

    print(f"[학습] {len(X_train):,}건 학습 / {len(X_hold):,}건 검증 "
          f"({info.get('hours', 0)}/{min_hours} 시간대)")

    # 웜스타트는 위에서 읽어 둔 그 모델에서 시작한다.
    #
    # 예전에는 여기서 파일을 다시 읽었다. 그러면 스케일러를 못 읽어 기여도와
    # 표본에서 쓰지 못한 모델의 가중치를 웜스타트에만 쓰는 일이 생긴다.
    # 이제 읽지 못하면 위에서 멈추므로, 여기 오는 것은 온전히 읽힌 모델뿐이다.
    init_state = None
    if live_model is not None and (not dynamic_mix or old_weight > 0.0):
        init_state = live_model.state_dict()

    model, scaler = train(X_train, n_cells, latent_dim, device,
                          init_state=init_state, old_weight=old_weight,
                          dynamic_mix=dynamic_mix)

    # ---------------- 감도 회귀 시험 ----------------
    cand = sensitivity_gate.evaluate(model, scaler, X_hold, mask, device)

    # 짝이 어긋난 모델은 감도 비교의 기준이 될 수 없다.
    #
    # 그런 모델은 모든 것을 낮게 주므로 합성 이상을 넣어도 값이 움직이지
    # 않는다. 그걸 "감도가 좋다" 로 읽으면 멀쩡한 후보가 "둔해졌다" 로
    # 막힌다. 2026-09-25 cj_busan_1 의 예행연습이 그렇게 보류됐다.
    guard_state, guard_msg, _rows = artifact_guard.check(user_path)
    if guard_state == artifact_guard.MISMATCH:
        print(f"[경고] {guard_msg}")
        print("       현재 모델을 감도 비교 기준으로 쓰지 않습니다. "
              "절대 기준만 적용합니다.")
        print("       운용 모델을 먼저 바로잡으십시오 - "
              "--rollback <세대> 로 세대 폴더의 것을 올립니다.")

    incumbent = None
    if guard_state != artifact_guard.MISMATCH and live_model is not None:
        try:
            incumbent = sensitivity_gate.evaluate(
                live_model, live_scaler, X_hold, mask, device)
        except Exception as e:
            # 비교가 빠지면 '세대마다 조금씩 둔해지는 것' 을 못 잡는다.
            # 조용히 넘기지 말고 경고로 남긴다.
            print(f"[경고] 현재 모델을 시험하지 못했습니다: {type(e).__name__} {e}")
            print(f"       감도 악화 비교 없이 절대 기준만 적용합니다.")

    passed, gate_rows = sensitivity_gate.check(cand, incumbent)
    report = sensitivity_gate.format_report(cand, incumbent, passed, gate_rows)
    print()
    print(RULE)
    print(report)
    print(RULE)
    print()

    # 기준과 구성을 끝에서 되풀이하지 않는다.
    #
    # 로그가 밀려 올라가는 것을 걱정해 한 번 더 찍었는데, 줄을 줄이고 나니
    # 한 화면에 다 들어온다. 같은 줄이 두 번 나오면 어느 것이 결과인지
    # 헷갈린다.

    # ---------------- 보관 및 승격 ----------------
    #
    # 예행연습은 세대 폴더에 아무것도 남기지 않는다. 승격되지 않은 후보로
    # 목록이 차면 정작 되돌릴 대상을 가린다. cj_busan_1 이 세대 10개 중
    # 9개가 예행연습인 상태였다.
    #
    # 대신 .dryrun 에 잠깐 둔다. 목록에 나오지 않고 되돌릴 대상도 아니지만,
    # [재학습 적용] 이 곧바로 집어 갈 수 있다. 학습에 시드가 없어 다시
    # 돌리면 다른 모델이 나오기 때문이다 - 본 것을 올려야 한다.
    tmp = os.path.join(user_path, ".candidate")
    os.makedirs(tmp, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(tmp, "autoencoder_final.pth"))
    save_scaler(scaler, os.path.join(tmp, "scaler.pkl"))

    files = {n: os.path.join(tmp, n) for n in ARTIFACTS
             if os.path.exists(os.path.join(tmp, n))}
    # 보고서 머리에 "무엇에서 출발해 무엇으로 배웠는지" 를 적는다.
    #
    # 점수만 보면 세대끼리 견줄 수 없다. 0.970 이 0.965 보다 나은지는 같은
    # 자료로 배웠을 때 이야기고, 기간과 기여도가 다르면 다른 시험을 친
    # 것이다. 나중에 되돌릴 세대를 고를 때 이 줄이 판단 근거가 된다.
    #
    # 형식을 바꿀 때는 Dlg_Retrain.cpp 의 ReadGenMeta() 도 같이 고쳐야 한다.
    base_gen = ""
    _cp = os.path.join(user_path, "current_generation.txt")
    if os.path.exists(_cp):
        base_gen = open(_cp, encoding="utf-8").read().strip()

    header = (f"재학습 {datetime.now():%Y-%m-%d %H:%M:%S}  user={args.user_id}\n"
              f"기준 세대 {base_gen or '없음'}  기여 {old_weight:.2f}  "
              f"판단 {config.get('CONTRIB_WINDOW_TABLES') or '기본'}일\n"
              f"표본 {info['drawn']:,}건  기간 {info['period']}  "
              f"칸 {info['cells']}개  시간대 {info.get('hours', 0)}개\n\n")
    if args.dry_run:
        cur = ""
        cp = os.path.join(user_path, "current_generation.txt")
        if os.path.exists(cp):
            cur = open(cp, encoding="utf-8").read().strip()

        d = save_dry_run(user_path, args.user_id, files, header + report,
                         passed, cur)
        shutil.rmtree(tmp, ignore_errors=True)

        # 승격이면 아무 말도 덧붙이지 않는다. 판정 줄이 결론이고, 그 다음에
        # 무엇을 할지는 [재학습 적용] 단추가 켜지는 것으로 이미 보인다.
        if not passed:
            print("판정이 승격이 아니라 이 결과를 다시 쓰지 않습니다.")
        return 0

    stamp = save_generation(user_path, files, header + report)
    shutil.rmtree(tmp, ignore_errors=True)
    clear_dry_run(user_path)

    print(f"[보관] {GEN_DIR_NAME}/{stamp}")

    if not passed:
        print("[보류] 감도 회귀 시험을 통과하지 못해 운용 모델을 유지합니다.")
        print(f"       후보는 {GEN_DIR_NAME}/{stamp} 에 남아 있습니다 - "
              f"왜 막혔는지 보고서로 확인할 수 있습니다.")
        return 3

    activate(user_path, stamp)
    print(f"[승격] {stamp} 을 운용 모델로 배치했습니다.")
    print("       감시가 곧 알아채고 갈아 끼웁니다(10초 안). "
          "재시작하지 않아도 됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
