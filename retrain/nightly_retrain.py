# -*- coding: utf-8 -*-
"""
재학습 (연속 학습)

밤에 저절로 돌지 않는다. 작업 스케줄러에 등록된 것이 없고, 시각을 보고 스스로
도는 코드도 없다. [재학습] 창에서 [예행연습] 이나 [재학습 실행] 을 눌러야 돈다.
파일 이름의 nightly 는 처음에 밤마다 돌릴 생각으로 붙인 흔적이다.

  python retrain/nightly_retrain.py kict1
  python retrain/nightly_retrain.py kict1 --dry-run     시험만, 교체 안 함
  python retrain/nightly_retrain.py kict1 --rollback    직전 세대로 되돌림
  python retrain/nightly_retrain.py kict1 --rollback 20260923_144613
  python retrain/nightly_retrain.py kict1 --list        세대 목록

되돌리면 칸별 기준선도 함께 치운다. 기준선은 그 모델의 오차 분포이므로
모델만 갈면 임계치가 어긋난다. --keep-baseline 으로 막을 수 있다.

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

from db_utils import Set_Env_Config, Get_HistoryDB_Config, Connect_History_DB

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
# 1단계 기준선에는 같은 뜻의 조건(BASELINE_MIN_HOURS)이 처음부터 있었는데
# 재학습에만 빠져 있었다. 값을 1단계와 같은 18 로 맞춘다.
MIN_HOURS_DEFAULT = 18
HOLDOUT_RATIO = 0.15
EPOCHS = 400
BATCH_SIZE = 512
LEARNING_RATE = 1e-4

# 보관할 세대 수. 오래된 것부터 지운다.
KEEP_GENERATIONS = 10

GEN_DIR_NAME = "model_generations"
ARTIFACTS = ("autoencoder_final.pth", "scaler.pkl", "scaler.npz")

# 칸별 기준선. 세대 산출물이 아니라 운용 중에 쌓이는 상태다.
BASELINE_NAME = "online_baseline.npz"
RETIRED_DIR_NAME = "_retired_baseline"

# 예행연습 결과를 잠깐 두는 곳.
#
# 세대 폴더가 아니다. 목록에 나오지 않고 되돌릴 대상도 아니다. [재학습 실행]
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

    예행연습에서 본 보고서와 [재학습 실행] 이 올리는 모델이 서로 다른
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

    line = (f"[기준] 세대 {cur or '없음'}"
            + (f" · 올린 때 {when[:16]}" if when else "")
            + (f" · 점수 {sc:.3f}" if sc is not None else " · 점수 -"))
    print(line)
    return line


def reset_baseline(user_path, why=""):
    """
    칸별 기준선을 치운다. 되돌리기와 함께 쓴다.

    [왜 치워야 하는가]

    기준선은 "이 모델이 이 칸에서 내는 오차" 의 분포다. 칸마다 256구간
    히스토그램으로 0.999 분위를 잡아 임계치로 쓴다. 모델을 갈면 오차의
    크기 자체가 달라지므로, 남은 분포는 다른 모델의 것이다. 임계치가 너무
    느슨하면 놓치고 너무 빡빡하면 오경보가 쏟아진다.

    [왜 지우지 않고 옮기는가]

    되돌리기를 또 되돌릴 수 있어야 한다. 기준선은 다시 쌓는 데 시간이
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
          init_state=None, old_weight=1.0):
    """
    init_state  기존 모델의 가중치. 주면 거기서 출발한다(웜스타트).
    old_weight  기존 모델을 얼마나 물려받을지(0.0~1.0).

    웜스타트는 지난 세대가 찾아 놓은 자리에서 시작하므로 적은 자료로도 빨리
    수렴한다. 다만 옛 모습에 붙들리는 대가가 있다. 그래서 물려받는 정도가
    낮을수록 학습률을 올려 옛 흔적을 빨리 벗게 한다.

    old_weight = 0 이면 아예 새로 초기화한다. 카메라가 완전히 다른 곳을 보고
    있는데 그 자리에서 출발할 이유가 없다.
    """
    scaler = StandardScaler().fit(X)
    Xs = torch.tensor(scaler.transform(X), dtype=torch.float32)

    model = AutoEncoder(input_dim, latent_dim, input_dim).to(device)

    lr = LEARNING_RATE
    if init_state is not None and old_weight > 0.0:
        try:
            model.load_state_dict(init_state)
            # 적게 물려받을수록 크게 흔든다. w=1 이면 그대로, w=0.2 면 약 3배.
            lr = LEARNING_RATE * (1.0 + 2.0 * (1.0 - old_weight))
            if verbose:
                print(f"[학습] 웜스타트 (기여 {old_weight:.2f}, 학습률 {lr:.5f})")
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
    지금 운용 중인 모델과 스케일러를 읽는다. 못 읽으면 (None, None).

    두 곳에서 쓴다 - 기여도를 구할 때 프레임을 다시 매기는 데, 그리고 감도
    회귀 시험에서 새 후보와 견주는 데. 같은 파일을 두 번 읽을 일이 없다.
    """
    mp = os.path.join(user_path, "autoencoder_final.pth")
    sp = os.path.join(user_path, "scaler.pkl")
    if not (os.path.exists(mp) and os.path.exists(sp)):
        return None, None
    try:
        m = AutoEncoder(n_cells, latent_dim, n_cells).to(device)
        m.load_state_dict(torch.load(mp, map_location=device))
        sc = load_scaler(sp)
        if getattr(sc, "n_features_in_", None) != n_cells:
            print(f"[경고] 현재 scaler 의 차원이 {n_cells} 와 다릅니다 "
                  f"({getattr(sc, 'n_features_in_', None)}).")
            return None, None
        return m, sc
    except Exception as e:
        print(f"[경고] 운용 모델을 읽지 못했습니다: {type(e).__name__} {e}")
        return None, None


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
    ap.add_argument("--keep-baseline", action="store_true",
                    help="되돌릴 때 칸별 기준선을 그대로 둔다 "
                         "(기본은 치우고 다시 쌓게 한다)")
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

        # 기준선은 갈아 낸 모델의 오차 분포다. 모델만 되돌리면 임계치가
        # 다른 모델 것이라 어긋난다. --keep-baseline 으로 막을 수 있다.
        if args.keep_baseline:
            print("[기준선] --keep-baseline 이므로 그대로 둡니다. "
                  "임계치가 한동안 어긋날 수 있습니다.")
        else:
            reset_baseline(user_path, f"{target} 로 되돌림")

        print(f"[OK] {target} 세대로 되돌렸습니다. predict_machine 을 재시작하십시오.")
        return 0

    # ---------------- 재학습 ----------------
    print("=" * 62)
    print(f"재학습  {args.user_id}   {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 62)

    # 이 판단을 좌우하는 파일을 적는다.
    #
    # 예전에는 env.ini 를 적었는데, 재학습에 쓰이는 값은 모두 여기로 옮겼다.
    # 무엇을 고쳐야 결과가 달라지는지 바로 알 수 있어야 한다.
    # normpath 로 고른다. LOCAL_USER_PATH 는 빗금 방향이 섞여 있고 끝에도
    # 빗금이 붙어 있어, 그냥 이으면 D:/A//users/... 처럼 보인다.
    print("[설정] " + os.path.normpath(
        os.path.join(user_path, "continual_learning.ini")))

    base_line = print_base_info(user_path)
    comp_line = ""
    print()

    # 예행연습에서 본 그 모델을 그대로 올린다.
    #
    # 학습에는 시드가 없어 같은 자료로 다시 돌리면 다른 모델이 나온다.
    # 판정을 읽고 [재학습 실행] 을 눌렀는데 다른 것이 올라가면 무엇을 보고
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
            print("       predict_machine 을 재시작해야 반영됩니다.")
            return 0

        print(f"[예행연습] 다시 쓸 결과가 없어 새로 학습합니다 - {info}")

    mask = load_mask(user_path, n_cells)
    live_model, live_scaler = load_live_model(user_path, n_cells,
                                             latent_dim, device)

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
            print("[기여도] 운용 모델을 읽지 못해 DB 에 적힌 점수로 판단합니다.")

        n_tab, min_fr, max_sm = model_contribution.limits(config)
        dec_score, dec_info = model_contribution.decision_score(
            conn, history_db["database"], n_cells, mask=mask,
            temp_warn=config.get("ABS_TEMP_WARN"), score_fn=rescore,
            n_tables=n_tab, min_frames=min_fr, max_samples=max_sm)
        old_weight = model_contribution.weight_for(dec_score, bands(config))
        print(f"[기여도] {model_contribution.describe(dec_score, old_weight)}")
        print()

        # 표본을 고르는 잣대를 기여 가중치에 맞춘다.
        #
        # replay_buffer 는 원래 'mscore >= 0.5 인 정상 프레임' 만 담는다.
        # 그런데 그 점수를 매긴 것이 바로 지금 버리기로 한 모델이다.
        # kict1 은 모든 프레임이 0.085 라 정상 프레임이 0건이 되고 재학습이
        # 아예 멈춘다 - 망가진 모델이 자기 후임을 못 만들게 막는 꼴이다.
        #
        # 모델을 못 믿기로 했으면 그 판단으로 표본을 걸러서도 안 된다.
        # 대신 0단계 절대 임계값으로 거른다. 학습과 무관하게 늘 동작하는
        # 유일한 판단이고, 이상 프레임을 학습에 넣지 않는다는 목적도 지킨다.
        # 표본을 거르는 점수도 다시 매긴다.
        #
        # 기여도만 고쳐 놓으면 앞뒤가 맞지 않는다. "지금 모델을 믿는다"(기여
        # 1.00)고 판단해 놓고, 정작 표본은 그때그때 다른 모델이 매긴 점수로
        # 거르게 된다. 09-25~26 이 그래서 3,000건 중 102건만 들어왔다.
        # 학습 표본 구성 규칙. [설정] 창에서 바꾼다.
        target = int(config.get("RETRAIN_TARGET_SAMPLES") or TARGET_SAMPLES)
        normal_min = config.get("RETRAIN_NORMAL_MIN_SCORE")
        normal_min = (replay_buffer.NORMAL_MIN_SCORE if normal_min in (None, "")
                      else float(normal_min))
        run_temp = config.get("RETRAIN_RUN_TEMP")
        run_temp = None if run_temp in (None, "") else float(run_temp)
        era_balance = bool(int(config.get("RETRAIN_ERA_BALANCE") or 0))

        replay_score = None
        if old_weight >= 1.0:
            min_score = normal_min
            temp_warn = None
            replay_score = rescore
            if replay_score is not None:
                print(f"[재생버퍼] 정상 판정 기준 : 모델 점수 >= {min_score} "
                      f"(지금 모델로 다시 매기고, 그 시절 판단도 함께 본다)")
            else:
                print(f"[재생버퍼] 정상 판정 기준 : 모델 점수 >= {min_score} "
                      f"(운용 모델을 읽지 못해 적힌 점수를 쓴다)")
        else:
            min_score = 0.0
            temp_warn = config.get("ABS_TEMP_WARN")
            if temp_warn is None:
                print("[경고] 모델 점수를 믿지 않기로 했는데 ABS_TEMP_WARN 이")
                print("       비어 있어 이상 프레임을 걸러낼 수단이 없습니다.")
                print("       [설정] 창에서 절대 임계값을 먼저 지정하십시오.")
            else:
                print(f"[재생버퍼] 정상 판정 기준 : 절대 임계값 < {temp_warn:.0f}도 "
                      f"(모델 점수는 믿지 않음)")

        X, info = replay_buffer.collect(
            conn, history_db["database"], n_cells, target, mask=mask,
            base_date=config.get("CALC_BASE_DATE"), old_weight=old_weight,
            min_score=min_score, temp_warn=temp_warn, score_fn=replay_score,
            run_temp=run_temp, era_balance=era_balance)
    finally:
        conn.close()

    # 최소 표본 수는 모니터링 프로그램의 [설정] 창에서 바꾼다.
    min_samples = config.get("RETRAIN_MIN_SAMPLES") or MIN_SAMPLES_DEFAULT

    min_hours = config.get("RETRAIN_MIN_HOURS") or MIN_HOURS_DEFAULT

    if len(X) < min_samples:
        print(f"[보류] 표본이 {len(X):,}건뿐입니다. 최소 {min_samples:,}건이 필요합니다.")
        print("       1단계 기준선이 채점을 시작한 뒤부터 정상 프레임이 쌓입니다.")
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
    # split 은 재생버퍼가 앞쪽 2,000건의 중앙값으로 잡은 가동 판정 온도다.
    # 마스크 칸 최고가 이 위면 "돌고 있다" 로 보고 시간대x가동상태 48칸에
    # 고르게 담는다. 옛/새 시기 비율이 아니다.
    comp_line = (f"[재생버퍼] 표본 {info['drawn']:,}/{target:,}"
                 f" · 시간대 {info.get('hours', 0)}/{min_hours}"
                 f" · 기간 {info['period']}"
                 f" · 칸 {info['cells']}"
                 + (f" · 시기 {info['eras']}" if info.get("eras", 1) > 1 else "")
                 + f" · 기여 {old_weight:.2f}"
                 + (f" · 가동판정 {info['split']:.0f}도"
                    if info.get("split") else ""))
    print(comp_line)
    print()

    print(f"[학습] {len(X_train):,}건 학습 / {len(X_hold):,}건 검증 "
          f"({info.get('hours', 0)}/{min_hours} 시간대)")

    init_state = None
    _mp = os.path.join(user_path, "autoencoder_final.pth")
    if old_weight > 0.0 and os.path.exists(_mp):
        try:
            init_state = torch.load(_mp, map_location=device)
        except Exception as e:
            print(f"[경고] 기존 모델을 읽지 못했습니다: {type(e).__name__} {e}")

    model, scaler = train(X_train, n_cells, latent_dim, device,
                          init_state=init_state, old_weight=old_weight)

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

    passed, reasons = sensitivity_gate.check(cand, incumbent)
    report = sensitivity_gate.format_report(cand, incumbent, passed, reasons)
    print()
    print(report)
    print()

    # 창의 로그 칸은 열 몇 줄이다. 30줄 넘는 출력이 지나가면 맨 위가 밀려
    # 사라지므로, 무엇에서 출발해 무엇으로 배웠는지 끝에 한 번 더 적는다.
    # 판정 바로 아래라 결과와 함께 눈에 들어온다.
    print(base_line)
    print(comp_line)
    print()

    # ---------------- 보관 및 승격 ----------------
    #
    # 예행연습은 세대 폴더에 아무것도 남기지 않는다. 승격되지 않은 후보로
    # 목록이 차면 정작 되돌릴 대상을 가린다. cj_busan_1 이 세대 10개 중
    # 9개가 예행연습인 상태였다.
    #
    # 대신 .dryrun 에 잠깐 둔다. 목록에 나오지 않고 되돌릴 대상도 아니지만,
    # [재학습 실행] 이 곧바로 집어 갈 수 있다. 학습에 시드가 없어 다시
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

    _cbd = (config.get("CALC_BASE_DATE") or "").strip()

    header = (f"재학습 {datetime.now():%Y-%m-%d %H:%M:%S}  user={args.user_id}\n"
              f"기준 세대 {base_gen or '없음'}  기여 {old_weight:.2f}  "
              f"계산기준일 {_cbd or '없음'}\n"
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

        print(f"[중단] --dry-run 이므로 운용 모델을 바꾸지 않았습니다.")
        if passed:
            print(f"       이 결과를 {DRYRUN_MAX_AGE_H}시간 안에 [재학습 실행] "
                  f"하면 보신 그 모델이 그대로 올라갑니다.")
        else:
            print("       판정이 승격이 아니라 다시 쓰지 않습니다.")
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
    print("       predict_machine 을 재시작해야 반영됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
