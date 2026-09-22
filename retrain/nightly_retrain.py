# -*- coding: utf-8 -*-
"""
야간 재학습 (연속 학습 3단계)

  python retrain/nightly_retrain.py kict1
  python retrain/nightly_retrain.py kict1 --dry-run     시험만, 교체 안 함
  python retrain/nightly_retrain.py kict1 --rollback    직전 세대로 되돌림
  python retrain/nightly_retrain.py kict1 --list        세대 목록

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
import shutil
import sys
from datetime import datetime

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

# --- 학습 설정 ----------------------------------------------------------
TARGET_SAMPLES = 60000

# env.ini 의 RETRAIN_MIN_SAMPLES 가 없을 때 쓰는 기본값.
# Dlg_Set_MmCam_Env.cpp 의 DEF_AE_SAMPLES 와 반드시 같아야 한다.
MIN_SAMPLES_DEFAULT = 5000
HOLDOUT_RATIO = 0.15
EPOCHS = 400
BATCH_SIZE = 512
LEARNING_RATE = 1e-4

# 보관할 세대 수. 오래된 것부터 지운다.
KEEP_GENERATIONS = 10

GEN_DIR_NAME = "model_generations"
ARTIFACTS = ("autoencoder_final.pth", "scaler.pkl", "scaler.npz")


# ======================================================================
# 세대 관리
# ======================================================================

def bands(config):
    """
    기여 가중치 문턱. env.ini 의 [CONSTANTS] 로 덮어쓸 수 있다.

        CONTRIB_BAND_HIGH = 0.85
        CONTRIB_BAND_MID  = 0.50
        CONTRIB_BAND_LOW  = 0.20

    근거가 확실한 것은 양 끝(정상 0.95, 망가진 0.09)뿐이라 가운데는 추정이다.
    현장마다 다를 수 있으므로 코드에 박지 않는다.
    """
    d = dict(zip(("hi", "mid", "lo"),
                 (b[0] for b in model_contribution.DEFAULT_BANDS)))
    for key, name in (("hi", "CONTRIB_BAND_HIGH"), ("mid", "CONTRIB_BAND_MID"),
                      ("lo", "CONTRIB_BAND_LOW")):
        v = config.get(name)
        if v not in (None, ""):
            try:
                d[key] = float(v)
            except (TypeError, ValueError):
                pass
    return ((d["hi"], 1.0), (d["mid"], 0.5), (d["lo"], 0.2))


def gen_root(user_path):
    return os.path.join(user_path, GEN_DIR_NAME)


def list_generations(user_path):
    root = gen_root(user_path)
    if not os.path.isdir(root):
        return []
    return sorted(d for d in os.listdir(root)
                  if os.path.isdir(os.path.join(root, d)))


def save_generation(user_path, files, report):
    """후보 산출물을 세대 폴더에 보관하고 폴더명을 돌려준다."""
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst = os.path.join(gen_root(user_path), stamp)
    os.makedirs(dst, exist_ok=True)

    for name, path in files.items():
        shutil.copy2(path, os.path.join(dst, name))

    with open(os.path.join(dst, "report.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")

    # 오래된 세대 정리
    gens = list_generations(user_path)
    for old in gens[:-KEEP_GENERATIONS]:
        shutil.rmtree(os.path.join(gen_root(user_path), old), ignore_errors=True)

    return stamp


def activate(user_path, stamp):
    """세대 하나를 운용 모델로 올린다."""
    src = os.path.join(gen_root(user_path), stamp)
    for name in ARTIFACTS:
        s = os.path.join(src, name)
        if os.path.exists(s):
            shutil.copy2(s, os.path.join(user_path, name))

    with open(os.path.join(user_path, "current_generation.txt"),
              "w", encoding="utf-8") as f:
        f.write(stamp + "\n")


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
                    help="지정 세대(없으면 직전)로 되돌린다")
    ap.add_argument("--list", action="store_true", help="세대 목록")
    args = ap.parse_args()

    config = Set_Env_Config(args.user_id)
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
        for g in gens:
            print(f"  {g}{'   <= 운용 중' if g == cur else ''}")
        return 0

    # ---------------- 되돌리기 ----------------
    if args.rollback:
        gens = list_generations(user_path)
        if len(gens) < 1:
            print("[ERROR] 되돌릴 세대가 없습니다.")
            return 1
        target = gens[-2] if args.rollback == "__prev__" and len(gens) >= 2 \
            else (gens[-1] if args.rollback == "__prev__" else args.rollback)
        if target not in gens:
            print(f"[ERROR] 그런 세대가 없습니다: {target}")
            return 1
        activate(user_path, target)
        print(f"[OK] {target} 세대로 되돌렸습니다. predict_machine 을 재시작하십시오.")
        return 0

    # ---------------- 재학습 ----------------
    print("=" * 62)
    print(f"야간 재학습  {args.user_id}   {datetime.now():%Y-%m-%d %H:%M:%S}")
    print("=" * 62)

    mask = load_mask(user_path, n_cells)

    history_db = Get_HistoryDB_Config(config)
    conn = Connect_History_DB(history_db)
    try:
        # ---------------- 기존 모델을 얼마나 물려받을지 ----------------
        #
        # 카메라가 밀렸는지가 아니라 '지금 몇 점을 내고 있는지' 로 정한다.
        # 실측에서 칸 수는 모델 손상을 예측하지 못했다 - 3칸을 밀어도 0.890
        # 이었고, kict1 은 1.3칸에 0.088 이었다.
        dec_score, dec_info = model_contribution.decision_score(
            conn, history_db["database"], n_cells, mask=mask,
            temp_warn=config.get("ABS_TEMP_WARN"))
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
        if old_weight >= 1.0:
            min_score = replay_buffer.NORMAL_MIN_SCORE
            temp_warn = None
            print(f"[재생버퍼] 정상 판정 기준 : 모델 점수 >= {min_score}")
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
            conn, history_db["database"], n_cells, TARGET_SAMPLES, mask=mask,
            base_date=config.get("CALC_BASE_DATE"), old_weight=old_weight,
            min_score=min_score, temp_warn=temp_warn)
    finally:
        conn.close()

    # 최소 표본 수는 모니터링 프로그램의 [설정] 창에서 바꾼다.
    min_samples = config.get("RETRAIN_MIN_SAMPLES") or MIN_SAMPLES_DEFAULT

    if len(X) < min_samples:
        print(f"[보류] 표본이 {len(X):,}건뿐입니다. 최소 {min_samples:,}건이 필요합니다.")
        print("       1단계 기준선이 채점을 시작한 뒤부터 정상 프레임이 쌓입니다.")
        return 2

    cut = int(len(X) * (1 - HOLDOUT_RATIO))
    X_train, X_hold = X[:cut], X[cut:]
    print(f"[학습] {len(X_train):,}건 학습 / {len(X_hold):,}건 검증")

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

    incumbent = None
    mp = os.path.join(user_path, "autoencoder_final.pth")
    sp = os.path.join(user_path, "scaler.pkl")
    if os.path.exists(mp) and os.path.exists(sp):
        try:
            old = AutoEncoder(n_cells, latent_dim, n_cells).to(device)
            old.load_state_dict(torch.load(mp, map_location=device))
            old_scaler = load_scaler(sp)
            if getattr(old_scaler, "n_features_in_", None) == n_cells:
                incumbent = sensitivity_gate.evaluate(
                    old, old_scaler, X_hold, mask, device)
            else:
                print(f"[경고] 현재 scaler 의 차원이 {n_cells} 와 달라 비교를 "
                      f"건너뜁니다. 절대 기준만 적용합니다.")
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

    # ---------------- 보관 및 승격 ----------------
    tmp = os.path.join(user_path, ".candidate")
    os.makedirs(tmp, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(tmp, "autoencoder_final.pth"))
    save_scaler(scaler, os.path.join(tmp, "scaler.pkl"))

    files = {n: os.path.join(tmp, n) for n in ARTIFACTS
             if os.path.exists(os.path.join(tmp, n))}
    header = (f"재학습 {datetime.now():%Y-%m-%d %H:%M:%S}  user={args.user_id}\n"
              f"표본 {info['drawn']:,}건  기간 {info['period']}  "
              f"칸 {info['cells']}개\n\n")
    stamp = save_generation(user_path, files, header + report)
    shutil.rmtree(tmp, ignore_errors=True)

    print(f"[보관] {GEN_DIR_NAME}/{stamp}")

    if args.dry_run:
        print("[중단] --dry-run 이므로 운용 모델을 바꾸지 않았습니다.")
        return 0

    if not passed:
        print("[보류] 감도 회귀 시험을 통과하지 못해 운용 모델을 유지합니다.")
        print(f"       후보는 {GEN_DIR_NAME}/{stamp} 에 남아 있습니다.")
        return 3

    activate(user_path, stamp)
    print(f"[승격] {stamp} 을 운용 모델로 배치했습니다.")
    print("       predict_machine 을 재시작해야 반영됩니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
