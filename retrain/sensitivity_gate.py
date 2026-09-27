# -*- coding: utf-8 -*-
"""
감도 회귀 시험 (연속 학습 승격 관문)

재학습한 모델을 배치하기 전에 통과해야 하는 시험이다. 연속 학습에서
가장 중요한 안전장치이며, 이것이 없으면 연속 학습을 해서는 안 된다.


[무엇을 막는가]

새 모델이 정상 데이터에 잘 맞는지만 확인하면 절반만 본 것이다. 정상에
잘 맞으면서 **이상도 정상이라고 답하는** 모델이 얼마든지 나온다. 극단적
으로는 무엇을 넣어도 1.0 을 내놓는 모델이 정상 데이터 적합도 시험을
만점으로 통과한다.

연속 학습에서 이 실패는 한 번에 오지 않는다. 세대마다 조금씩 둔해지고,
각 세대의 변화는 눈에 띄지 않는다. 반 년이 지나 아무것도 잡지 못하게
되어도 로그에는 언제나 "정상" 만 찍혀 있다. 화재 감시 시스템에서 가장
나쁜 결말이다.

그래서 두 가지를 함께 본다.

  1. 정상을 정상이라 하는가   (검증용 정상 프레임, 학습에 쓰지 않은 것)
  2. 이상을 이상이라 하는가   (합성 이상 주입)

그리고 **현재 운용 중인 모델보다 나빠졌으면 승격하지 않는다.** 절대
기준만 두면 조금씩 나빠지는 것을 못 잡는다. 이전 세대와의 비교가
둔감화를 막는 실질적인 장치다.
"""

import numpy as np
import torch

# --- 합격선 -------------------------------------------------------------
# 검증용 정상 프레임에서 요구하는 최소 평균 점수
NORMAL_MEAN_MIN = 0.85

# 정상인데 0.5 미만으로 떨어지는(오탐) 비율의 상한
NORMAL_FALSE_MAX = 0.05

# 합성 이상 주입량 (섭씨). 마스크 셀 하나에 더한다.
INJECT_LEVELS = (20.0, 40.0, 60.0)

# +40도 주입 시 요구하는 최대 평균 점수 (이보다 높으면 둔감한 것)
ANOMALY_MEAN_MAX = 0.50

# 현재 모델 대비 허용하는 감도 악화 폭.
# 합성 이상 점수가 이보다 더 올라가면(= 더 둔해지면) 승격하지 않는다.
REGRESSION_TOLERANCE = 0.10


def _scores(model, scaler, X, mask, device):
    """normality_score 와 같은 계산. 배치로 한 번에 처리한다."""
    sel = np.asarray(mask, dtype=np.int32).reshape(-1) == 1
    model.eval()
    with torch.no_grad():
        xs = scaler.transform(X)
        xt = torch.tensor(xs, dtype=torch.float32, device=device)
        diff = (xt - model(xt)) ** 2
        mse = diff[:, torch.tensor(sel, device=device)].mean(dim=1)
        return torch.exp(-mse * 10).cpu().numpy()


def inject(X, mask, amount, rng):
    """정상 프레임의 마스크 셀 하나를 골라 온도를 올린다."""
    idx = np.flatnonzero(np.asarray(mask).reshape(-1) == 1)
    out = X.copy()
    pick = rng.choice(idx, size=len(X))
    out[np.arange(len(X)), pick] += amount
    return out


def evaluate(model, scaler, X_holdout, mask, device, seed=0):
    """모델 하나의 감도를 재서 돌려준다."""
    rng = np.random.default_rng(seed)

    normal = _scores(model, scaler, X_holdout, mask, device)
    result = {
        "normal_mean": float(normal.mean()),
        "normal_false": float(np.mean(normal < 0.5)),
    }

    for lv in INJECT_LEVELS:
        s = _scores(model, scaler, inject(X_holdout, mask, lv, rng), mask, device)
        result[f"anomaly_{int(lv)}"] = float(s.mean())

    return result


def check(candidate, incumbent=None):
    """
    합격 여부를 판정한다.

    candidate / incumbent 는 evaluate() 의 결과.
    incumbent 가 None 이면(첫 모델) 절대 기준만 본다.

    반환: (passed, reasons)  reasons 는 사람이 읽을 판정 사유 목록
    """
    reasons = []
    ok = True

    if candidate["normal_mean"] < NORMAL_MEAN_MIN:
        ok = False
        reasons.append(
            f"정상 평균 점수 {candidate['normal_mean']:.3f} < {NORMAL_MEAN_MIN} "
            f"(정상을 이상이라 판정)")
    else:
        reasons.append(f"정상 평균 점수 {candidate['normal_mean']:.3f}  통과")

    if candidate["normal_false"] > NORMAL_FALSE_MAX:
        ok = False
        reasons.append(
            f"정상 오탐 비율 {100*candidate['normal_false']:.1f}% > "
            f"{100*NORMAL_FALSE_MAX:.0f}%")
    else:
        reasons.append(f"정상 오탐 비율 {100*candidate['normal_false']:.1f}%  통과")

    a40 = candidate["anomaly_40"]
    if a40 > ANOMALY_MEAN_MAX:
        ok = False
        reasons.append(
            f"+40도 주입 시 평균 {a40:.3f} > {ANOMALY_MEAN_MAX} (이상을 못 잡음)")
    else:
        reasons.append(f"+40도 주입 시 평균 {a40:.3f}  통과")

    if incumbent is not None:
        # 절대 기준만으로는 세대마다 조금씩 둔해지는 것을 못 잡는다.
        for lv in INJECT_LEVELS:
            k = f"anomaly_{int(lv)}"
            drift = candidate[k] - incumbent[k]
            if drift > REGRESSION_TOLERANCE:
                ok = False
                reasons.append(
                    f"+{int(lv)}도 감도 악화 {incumbent[k]:.3f} -> {candidate[k]:.3f} "
                    f"(+{drift:.3f} > {REGRESSION_TOLERANCE})")
            else:
                reasons.append(
                    f"+{int(lv)}도 감도 {incumbent[k]:.3f} -> {candidate[k]:.3f}  통과")

    return ok, reasons


# 묶음을 가르는 가로줄. nightly_retrain 의 RULE 과 같은 길이여야 한다.
RULE = "-" * 113


def format_report(candidate, incumbent, passed, reasons):
    """
    감도 시험 결과를 두 묶음으로 적는다 - 잰 값([평가])과 판정([판정]).

    예전에는 표로 그렸다. 줄 머리에 표가 없으면 로그가 길어졌을 때 어느
    묶음의 줄인지 알 수 없고, 창의 글꼴이 가변폭이라 열도 맞지 않았다.
    다른 줄과 같이 [꼬리표] 를 앞에 둔다.
    """
    lines = ["[평가] 항목(후보, 현재)"]

    rows = [("평균점수", "normal_mean"),
            ("오탐비율", "normal_false")]
    rows += [(f"+{int(l)} 변형", f"anomaly_{int(l)}") for l in INJECT_LEVELS]

    for label, key in rows:
        # 이름을 채우지 않는다. 다섯 이름이 모두 여덟 칸이라 그대로 맞고,
        # 파이썬의 :<8 은 한글 한 자를 한 칸으로 세어 오히려 어긋난다
        # ('평균점수' 는 네 자 여덟 칸, '+20 변형' 은 일곱 자 여덟 칸).
        if incumbent:
            lines.append(f"[평가] {label}  ( {candidate[key]:.3f}   "
                         f"{incumbent[key]:.3f} )")
        else:
            # 첫 모델이라 견줄 것이 없다. 빈칸으로 두면 자리만 비어 무엇이
            # 빠졌는지 알 수 없으므로 까닭을 적는다.
            lines.append(f"[평가] {label}  ( {candidate[key]:.3f}   "
                         f"현재 없음 )")

    lines.append("")
    lines.append(RULE)
    lines.append("[판정] " + ("승격" if passed else "보류"))
    for r in reasons:
        lines.append("[판정] " + r)
    return "\n".join(lines)
