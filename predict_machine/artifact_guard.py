# -*- coding: utf-8 -*-
"""
운용 산출물이 서로 짝이 맞는지 확인한다.

[왜 필요한가]

모델(autoencoder_final.pth)과 스케일러(scaler.pkl)는 한 벌이다. 스케일러는
입력을 어떤 크기로 바꿔 모델에 넣을지 정한 표이고, 모델은 자기가 배울 때
쓰던 표를 전제로 답을 낸다. 다른 표를 끼우면 멀쩡한 모델도 엉뚱한 값을
낸다.

2026-09-25 에 cj_busan_1 이 그 상태였다.

    current_generation.txt   20260923_145111
    scaler.pkl               그 세대 것이 맞음
    autoencoder_final.pth    어느 세대 것도 아님 (09-18 짜리)

아무 소리 없이 돌면서 7월 프레임의 100% 를 "이상" 이라고 불렀다. 전 기간
오탐 52%. 화면에는 점수 0.00 만 보이니 설비 문제인지 모델 문제인지 가릴
길이 없었다.

[어떻게 보는가]

세대 폴더가 원본이다. current_generation.txt 가 가리키는 폴더의 파일과
운용 파일을 바이트로 대조한다. 따로 지문 파일을 두지 않는다 - 그 파일이
또 어긋나면 무엇을 믿을지 정할 수 없다.

세대가 아직 없으면(재학습 전) 대조할 것이 없으므로 통과시킨다. 없는 것과
어긋난 것은 다르다.
"""

import hashlib
import os

GEN_DIR_NAME = "model_generations"
ARTIFACTS = ("autoencoder_final.pth", "scaler.pkl", "scaler.npz")

OK = "ok"                 # 짝이 맞는다
NO_GEN = "no_gen"         # 대조할 세대가 없다 (재학습 전)
MISMATCH = "mismatch"     # 어긋났다


def _md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def check(user_path):
    """
    (상태, 메시지, 자세한 내용) 을 돌려준다.

    상태가 MISMATCH 면 감시를 시작해서는 안 된다. 틀린 점수를 내는 것은
    점수를 못 내는 것보다 나쁘다 - 아무도 이상을 눈치채지 못한다.
    """
    cur = ""
    cp = os.path.join(user_path, "current_generation.txt")
    if os.path.exists(cp):
        with open(cp, encoding="utf-8") as f:
            cur = f.read().strip()

    if not cur:
        return NO_GEN, "승격된 세대가 없음 · 대조를 건너뜀", []

    gen = os.path.join(user_path, GEN_DIR_NAME, cur)
    if not os.path.isdir(gen):
        return NO_GEN, f"세대 폴더 {cur} 가 없어 대조를 건너뜀", []

    rows, bad = [], []
    for name in ARTIFACTS:
        live = os.path.join(user_path, name)
        ref = os.path.join(gen, name)

        if not os.path.exists(ref):
            # 세대에 없는 산출물은 따지지 않는다. scaler.npz 는 없을 수 있다.
            continue
        if not os.path.exists(live):
            rows.append((name, "없음", _md5(ref)[:12]))
            bad.append(name)
            continue

        a, b = _md5(live), _md5(ref)
        rows.append((name, a[:12], b[:12]))
        if a != b:
            bad.append(name)

    if not bad:
        return OK, f"운용 산출물이 세대 {cur} 와 일치함", rows

    return (MISMATCH,
            f"운용 산출물이 세대 {cur} 와 다름: {', '.join(bad)}",
            rows)


def report(user_path, prefix="[산출물]"):
    """확인하고 사람이 읽을 줄로 찍는다. 어긋났으면 True."""
    state, msg, rows = check(user_path)

    if state == OK:
        print(f"{prefix} {msg}")
        return False

    if state == NO_GEN:
        print(f"{prefix} {msg}")
        return False

    print("=" * 62)
    print(f"{prefix} 모델과 스케일러의 짝이 맞지 않음")
    print("=" * 62)
    print(f"  {msg}")
    print()
    print(f"  {'파일':<24}{'지금 쓰는 것':>14}{'세대에 있는 것':>16}")
    for name, a, b in rows:
        mark = "" if a == b else "   <= 다름"
        print(f"  {name:<24}{a:>14}{b:>16}{mark}")
    print()
    print("  스케일러는 입력을 어떤 크기로 바꿔 모델에 넣을지 정한 표임")
    print("  짝이 어긋나면 멀쩡한 모델도 엉뚱한 점수를 냄 · 정상 화면을")
    print("  이상이라고 부르므로, 그대로 두면 진짜 이상을 놓침")
    print()
    print("  세대 폴더의 것으로 되돌릴 것")
    print("    python retrain/nightly_retrain.py <현장> --rollback <세대>")
    print("=" * 62)
    return True
