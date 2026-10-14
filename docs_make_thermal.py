# -*- coding: utf-8 -*-
"""cj_busan_1 열패턴 비교 PPTX 생성

step_0(원래 학습 자료) 954,629 프레임에서 6,365개를 표집해 8x8 로 줄이고
k-means 로 여섯 갈래로 묶은 결과를, 오늘(2026-09-25) 상태와 나란히 놓는다.

수치는 scratchpad/patterns.json 이 아니라 이 파일에 박아 둔다. 자료를 다시
뽑을 때마다 문서가 조용히 달라지면 어느 판을 보고 말한 것인지 알 수 없다.
"""

import json
import os

from docs_style import *   # 팔레트 · 글꼴 · 상자 · 카드 · 제목줄

# ------------------------------------------------------------------ 자료
DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "docs_thermal_data.json")
with open(DATA, encoding="utf-8") as f:
    D = json.load(f)

PAT = D["patterns"]
TEN = D["ten"]
CMP = D["today_cmp"]
CROSS = D["cross"]
TODAY = D["today"]
X = Y = 8

# 두 구역 (행, 열)
BLOCK = [(2, 5), (2, 6), (3, 6), (3, 7)]     # 오른쪽 발열부
SPINE = [(2, 2), (3, 3), (4, 2), (4, 3)]     # 가운데 등줄기

BLOCK_CLR = EMBER
SPINE_CLR = RGBColor(0x2A, 0x78, 0xD6)

# 표본 수로 가중한 기준. 평균 대비 보기의 0점.
_N = sum(p["n"] for p in PAT)
BASE = [sum(p["grid"][i] * p["n"] for p in PAT) / _N for i in range(64)]


def zavg(grid, cells):
    return sum(grid[r * X + c] for r, c in cells) / len(cells)


# ------------------------------------------------------------------ 색
# 한 가지 색조, 옅음에서 짙음으로. 무지개는 크기를 읽을 수 없다.
HEAT_BINS = [25, 32, 40, 50, 62, 75, 100]
HEAT = [RGBColor(*v) for v in [
    (0xFD, 0xF1, 0xE6), (0xFB, 0xDC, 0xC0), (0xF8, 0xC1, 0x96),
    (0xF3, 0xA0, 0x6C), (0xEA, 0x7A, 0x44), (0xD1, 0x5A, 0x25),
    (0xA5, 0x3F, 0x14), (0x6D, 0x27, 0x0C)]]

# 평균 대비는 양끝이 뜻이 다르므로 두 색 + 가운데 회색.
DIFF_BINS = [-20, -10, -3, 3, 10, 20, 40]
DIFF = [RGBColor(*v) for v in [
    (0x16, 0x52, 0x8F), (0x2A, 0x78, 0xD6), (0x86, 0xB6, 0xEF),
    (0xEC, 0xE7, 0xE0),
    (0xF6, 0xCF, 0xC4), (0xE5, 0x8F, 0x7C), (0xD0, 0x52, 0x3A),
    (0x8F, 0x23, 0x14)]]


def pick(v, bins, ramp):
    i = 0
    while i < len(bins) and v >= bins[i]:
        i += 1
    return ramp[i]


# ------------------------------------------------------------------ 격자
def heat_grid(slide, x, y, cell, grid, diff=False, zones=True):
    """8x8 격자를 그린다. 반환값은 (폭, 높이)."""
    for r in range(Y):
        for c in range(X):
            raw = grid[r * X + c]
            v = raw - BASE[r * X + c] if diff else raw
            sh = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(x + c * cell), Inches(y + r * cell),
                Inches(cell), Inches(cell))
            sh.fill.solid()
            sh.fill.fore_color.rgb = pick(v, DIFF_BINS if diff else HEAT_BINS,
                                          DIFF if diff else HEAT)
            # 칸 사이를 흰 실선으로 띄운다. 붙여 두면 덩어리가 뭉개진다.
            sh.line.color.rgb = WHITE
            sh.line.width = Pt(0.75)
            sh.shadow.inherit = False
            sh.text_frame.text = ""

    if zones:
        for cells, clr in ((BLOCK, BLOCK_CLR), (SPINE, SPINE_CLR)):
            r0 = min(r for r, _ in cells)
            r1 = max(r for r, _ in cells)
            c0 = min(c for _, c in cells)
            c1 = max(c for _, c in cells)
            box = slide.shapes.add_shape(
                MSO_SHAPE.RECTANGLE,
                Inches(x + c0 * cell), Inches(y + r0 * cell),
                Inches((c1 - c0 + 1) * cell), Inches((r1 - r0 + 1) * cell))
            box.fill.background()
            box.line.color.rgb = clr
            box.line.width = Pt(1.75)
            box.shadow.inherit = False
            box.text_frame.text = ""

    return X * cell, Y * cell


def ramp_legend(slide, x, y, w, bins, ramp, caption):
    """색 띠와 눈금. 띠만 두면 무슨 온도인지 알 수 없다."""
    n = len(ramp)
    sw = w / n
    for i, clr in enumerate(ramp):
        sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                    Inches(x + i * sw), Inches(y),
                                    Inches(sw), Inches(0.16))
        sh.fill.solid()
        sh.fill.fore_color.rgb = clr
        sh.line.fill.background()
        sh.shadow.inherit = False
        sh.text_frame.text = ""
    for i, b in enumerate(bins):
        tf = textbox(slide, x + (i + 1) * sw - 0.3, y + 0.18, 0.6, 0.2,
                     align=PP_ALIGN.CENTER)
        write(tf, [(f"{b:+d}" if bins is DIFF_BINS else str(b),
                    dict(name=MONO, size=8, color=MUTED), dict(space_after=0))])
    tf = textbox(slide, x, y - 0.24, w, 0.2)
    write(tf, [(caption, dict(size=10, color=MUTED), dict(space_after=0))])


def zone_key(slide, x, y):
    for i, (clr, lab) in enumerate(
            ((BLOCK_CLR, "오른쪽 발열부  행2-3 · 열5-7"),
             (SPINE_CLR, "가운데 등줄기  행2-5 · 열2-3"))):
        bx = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                    Inches(x + i * 3.1), Inches(y),
                                    Inches(0.22), Inches(0.16))
        bx.fill.background()
        bx.line.color.rgb = clr
        bx.line.width = Pt(1.75)
        bx.shadow.inherit = False
        bx.text_frame.text = ""
        tf = textbox(slide, x + i * 3.1 + 0.32, y - 0.05, 2.7, 0.26)
        write(tf, [(lab, dict(size=10, color=MUTED), dict(space_after=0))])


# ------------------------------------------------------------------ 문서
prs = Presentation()
prs.slide_width = Inches(W)
prs.slide_height = Inches(H)

# =================================================================== 1 표지
s = slide_dark(prs)
tf = textbox(s, M, 2.05, 9.0, 0.5)
write(tf, [("cj_busan_1 · 학습 자료 분석", dict(size=15, bold=True, color=AMBER),
            dict(space_after=0))])
tf = textbox(s, M, 2.6, 10.5, 1.5)
write(tf, [("열패턴 여섯 가지", dict(size=46, bold=True, color=WHITE),
            dict(space_after=4)),
           ("그리고 그 어디에도 없는 오늘",
            dict(size=46, bold=True, color=EMBER), dict(space_after=0))])
tf = textbox(s, M, 4.6, 10.5, 0.4)
write(tf, [("step_0 954,629 프레임에서 6,365개를 표집 · 8x8 격자 · k-means (k=6, k=10)",
            dict(size=15, color=RGBColor(0xA8, 0xB6, 0xCC)), dict(space_after=0))])
for i, (lab, val) in enumerate([("자료 기간", "2026-01-04 ~ 07-04"),
                                ("견주는 시점", "2026-09-25 09시"),
                                ("작성일", "2026-09-25")]):
    x = M + i * 3.4
    tf = textbox(s, x, 5.9, 3.2, 0.3)
    write(tf, [(lab, dict(size=10.5, bold=True, color=EMBER), dict(space_after=2))])
    tf = textbox(s, x, 6.23, 3.2, 0.32)
    write(tf, [(val, dict(size=13, color=WHITE), dict(space_after=0))])

# =================================================================== 2 방법
s = slide_light(prs)
title_bar(s, "01  METHOD", "어떻게 묶었는가")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("운용이 점수를 내는 것과 같은 모양으로 줄인 뒤 묶었음 · "
            "그래야 \"모델이 무엇을 정상으로 배웠는가\" 와 이어짐",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

steps = [
    ("1", "표집", "954,629개에서 150개마다 하나씩, 6,365개. 날짜가 고르게 들어가도록 "
     "파일 이름 순으로 건너뛰며 뽑음"),
    ("2", "8x8 로 줄이기", "160x120 원본을 20x15 블록으로 나눠 블록마다 최댓값을 "
     "고름 · source/utils.py 의 Conv_LWIR_to_64_Vector 와 같은 규칙임"),
    ("3", "묶기", "64칸 벡터를 그대로 k-means 에 넣음 · 오토인코더가 보는 것이 "
     "이 벡터라 같은 것으로 묶어야 함"),
    ("4", "k 고르기", "3~7 을 다 돌려 실루엣으로 봄 · 눈대중으로 정하지 않음"),
]
yy = 2.3
for num, name, desc in steps:
    circle(s, M, yy, 0.38, TEAL, num, WHITE, 12)
    tf = textbox(s, M + 0.56, yy - 0.02, 3.0, 0.28)
    write(tf, [(name, dict(size=13, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, M + 0.56, yy + 0.3, 6.3, 0.62)
    write(tf, [(desc, dict(size=10.5, color=MUTED), dict(space_after=0, line=1.2))])
    yy += 1.02

bx = M + 7.5
tf = textbox(s, bx, 2.26, 4.1, 0.3)
write(tf, [("실루엣", dict(size=13, bold=True, color=INK), dict(space_after=0))])
tf = textbox(s, bx, 2.58, 4.1, 0.3)
write(tf, [("높을수록 잘 갈린 것임", dict(size=10.5, color=MUTED),
            dict(space_after=0))])

sil = [(3, 0.553), (4, 0.453), (5, 0.323), (6, 0.348), (7, 0.319)]
yy = 2.98
for k, v in sil:
    tf = textbox(s, bx, yy, 0.6, 0.26)
    write(tf, [(f"k={k}", dict(name=MONO, size=11,
                               color=INK if k == 6 else MUTED),
                dict(space_after=0))])
    bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(bx + 0.62), Inches(yy + 0.04),
                             Inches(2.4 * v / 0.6), Inches(0.17))
    bar.fill.solid()
    bar.fill.fore_color.rgb = EMBER if k == 6 else RGBColor(0xC3, 0xCC, 0xD9)
    bar.line.fill.background()
    bar.shadow.inherit = False
    bar.text_frame.text = ""
    tf = textbox(s, bx + 3.15, yy, 0.8, 0.26)
    write(tf, [(f"{v:.3f}", dict(name=MONO, size=10.5, color=MUTED),
                dict(space_after=0))])
    yy += 0.34

card(s, bx, 4.85, 4.1, 1.5, fill=RGBColor(0xFD, 0xF1, 0xEC))
tf = textbox(s, bx + 0.26, 5.0, 3.6, 0.3)
write(tf, [("셋이 가장 잘 갈림", dict(size=12, bold=True, color=EMBER),
            dict(space_after=0))])
tf = textbox(s, bx + 0.26, 5.34, 3.6, 0.9)
write(tf, [("자료가 말하는 것은 \"정지 / 가동 / 과열\" 셋임 · "
            "여섯으로 나눈 것은 그 안을 더 들여다보려는 것이고, "
            "새 무늬가 나오지는 않음",
            dict(size=10.5, color=INK), dict(space_after=0, line=1.25))])
page_num(s, 1)

# =================================================================== 3 한눈에
s = slide_light(prs)
title_bar(s, "02  SIX PATTERNS", "여섯 가지를 나란히")

tf = textbox(s, M, 1.68, 8.0, 0.3)
write(tf, [("칸 색은 그 패턴의 칸별 평균 섭씨임 · 짙을수록 뜨거움",
            dict(size=12, color=MUTED), dict(space_after=0))])
ramp_legend(s, W - M - 3.2, 1.86, 3.2, HEAT_BINS, HEAT, "섭씨")
zone_key(s, M, 2.16)

cell = 0.19
gw = X * cell
SIDE = 1.9                       # 격자 옆 수치 칸
colw = gw + 0.16 + SIDE
gap = (W - 2 * M - 3 * colw) / 2
for i, p in enumerate(PAT):
    col, row = i % 3, i // 3
    gx = M + col * (colw + gap)
    gy = 2.72 + row * 2.28

    tf = textbox(s, gx, gy - 0.34, colw - 1.5, 0.28)
    write(tf, [(f"{i+1}. {p['name']}", dict(size=12.5, bold=True, color=INK),
                dict(space_after=0))])
    tf = textbox(s, gx + gw + 0.12, gy - 0.34, 1.4, 0.28, align=PP_ALIGN.RIGHT)
    write(tf, [(f"{p['pct']}%", dict(name=MONO, size=11, color=EMBER),
                dict(space_after=0))])

    heat_grid(s, gx, gy, cell, p["grid"])

    tf = textbox(s, gx + gw + 0.16, gy + 0.02, 1.9, 1.5)
    write(tf, [("전체 평균", dict(size=9, color=MUTED), dict(space_after=0)),
               (f"{sum(p['grid'])/64:.1f}도", dict(name=MONO, size=12, bold=True,
                                                 color=INK), dict(space_after=5)),
               ("오른쪽", dict(size=9, color=MUTED), dict(space_after=0)),
               (f"{zavg(p['grid'], BLOCK):.1f}도", dict(name=MONO, size=11,
                                                      color=EMBER), dict(space_after=5)),
               ("등줄기", dict(size=9, color=MUTED), dict(space_after=0)),
               (f"{zavg(p['grid'], SPINE):.1f}도", dict(name=MONO, size=11,
                                                      color=SPINE_CLR),
                dict(space_after=0))])
page_num(s, 2)

# =================================================================== 4 평균 대비
s = slide_light(prs)
title_bar(s, "03  DEVIATION", "평균 대비로 보면 무엇이 도는지 보인다")

tf = textbox(s, M, 1.68, 8.2, 0.3)
write(tf, [("여섯을 표본 수로 가중한 기준에서 얼마나 벗어났는지임 · "
            "붉으면 그 패턴에서 유독 뜨거운 칸임",
            dict(size=12, color=MUTED), dict(space_after=0))])
ramp_legend(s, W - M - 3.2, 1.86, 3.2, DIFF_BINS, DIFF, "기준과의 차이 (도)")
zone_key(s, M, 2.16)

for i, p in enumerate(PAT):
    col, row = i % 3, i // 3
    gx = M + col * (colw + gap)
    gy = 2.72 + row * 2.28

    tf = textbox(s, gx, gy - 0.34, colw - 1.5, 0.28)
    write(tf, [(f"{i+1}. {p['name']}", dict(size=12.5, bold=True, color=INK),
                dict(space_after=0))])
    heat_grid(s, gx, gy, cell, p["grid"], diff=True)

    d = [p["grid"][j] - BASE[j] for j in range(64)]
    hot = sorted(range(64), key=lambda j: -d[j])[:2]
    cold = sorted(range(64), key=lambda j: d[j])[:1]
    tf = textbox(s, gx + gw + 0.16, gy + 0.08, 1.9, 1.4)
    write(tf, [("가장 뜨거운 칸", dict(size=9, color=MUTED), dict(space_after=0))]
          + [(f"({j//X},{j%X})  {d[j]:+.0f}도",
              dict(name=MONO, size=10, color=RGBColor(0xD0, 0x52, 0x3A)),
              dict(space_after=1)) for j in hot]
          + [("가장 찬 칸", dict(size=9, color=MUTED), dict(space_after=0, space_before=5))]
          + [(f"({j//X},{j%X})  {d[j]:+.0f}도",
              dict(name=MONO, size=10, color=RGBColor(0x2A, 0x78, 0xD6)),
              dict(space_after=0)) for j in cold])
page_num(s, 3)

# =================================================================== 5 표
s = slide_light(prs)
title_bar(s, "04  NUMBERS", "수치로 견주기")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("여섯 중 다섯이 오른쪽 발열부 68~84도임 · 변하는 것은 "
            "가운데 등줄기임", dict(size=13.5, color=MUTED), dict(space_after=0))])

cols = [(0.0, 2.7, "패턴", PP_ALIGN.LEFT),
        (2.7, 1.1, "표본", PP_ALIGN.RIGHT),
        (3.8, 1.0, "비중", PP_ALIGN.RIGHT),
        (4.8, 1.3, "전체 평균", PP_ALIGN.RIGHT),
        (6.1, 1.2, "최고 칸", PP_ALIGN.RIGHT),
        (7.3, 1.5, "오른쪽 발열부", PP_ALIGN.RIGHT),
        (8.8, 1.5, "가운데 등줄기", PP_ALIGN.RIGHT),
        (10.25, 1.6, "기간", PP_ALIGN.RIGHT)]

yy = 2.32
for dx, cw, lab, al in cols:
    tf = textbox(s, M + dx, yy, cw, 0.26, align=al)
    write(tf, [(lab, dict(size=10, bold=True, color=MUTED), dict(space_after=0))])
yy += 0.32

rows = [(p["name"], f"{p['n']:,}", f"{p['pct']}%",
         f"{sum(p['grid'])/64:.1f}", f"{max(p['grid']):.1f}",
         f"{zavg(p['grid'], BLOCK):.1f}", f"{zavg(p['grid'], SPINE):.1f}",
         f"{p['span'][0][4:6]}-{p['span'][0][6:]} ~ "
         f"{p['span'][1][4:6]}-{p['span'][1][6:]}  ({p['days']}일)")
        for p in PAT]
rows.append(("오늘 09-25 09시", "14", "-",
             f"{sum(TODAY)/64:.1f}", f"{max(TODAY):.1f}",
             f"{zavg(TODAY, BLOCK):.1f}", f"{zavg(TODAY, SPINE):.1f}", "09-25"))

for i, r in enumerate(rows):
    last = (i == len(rows) - 1)
    if last:
        card(s, M - 0.12, yy - 0.06, W - 2 * M + 0.24, 0.42,
             fill=RGBColor(0xFD, 0xF1, 0xEC))
    elif i % 2 == 0:
        card(s, M - 0.12, yy - 0.06, W - 2 * M + 0.24, 0.42, fill=PAPER)
    for (dx, cw, _lab, al), v in zip(cols, r):
        clr = EMBER if last else INK
        tf = textbox(s, M + dx, yy, cw, 0.3, align=al)
        write(tf, [(v, dict(name=KR if dx == 0.0 else MONO, size=11,
                            bold=last, color=clr), dict(space_after=0))])
    yy += 0.48
page_num(s, 4)

# =================================================================== 6 시간대
s = slide_light(prs)
title_bar(s, "05  WHEN", "언제 나타나는가")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("0시부터 23시까지 그 패턴이 관측된 표본 수임 · "
            "같은 설비라도 도는 시간대가 다름",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

bw = (W - 2 * M - 1.2) / 2
for i, p in enumerate(PAT):
    col, row = i % 2, i // 2
    bx = M + col * (bw + 1.2)
    by = 2.28 + row * 1.52

    tf = textbox(s, bx, by, bw, 0.28)
    write(tf, [(f"{i+1}. {p['name']}", dict(size=12, bold=True, color=INK),
                dict(space_after=0))])
    tf = textbox(s, bx, by + 0.26, bw, 0.22)
    write(tf, [(p["note"], dict(size=9.5, color=MUTED), dict(space_after=0))])

    mx = max(p["hours"])
    hw = bw / 24
    for h, n in enumerate(p["hours"]):
        hh = max(0.02, 0.62 * n / mx)
        bar = s.shapes.add_shape(MSO_SHAPE.RECTANGLE,
                                 Inches(bx + h * hw), Inches(by + 1.18 - hh),
                                 Inches(hw * 0.82), Inches(hh))
        bar.fill.solid()
        bar.fill.fore_color.rgb = TEAL
        bar.line.fill.background()
        bar.shadow.inherit = False
        bar.text_frame.text = ""
    for h, lab in ((0, "0시"), (12, "12시"), (23, "23시")):
        tf = textbox(s, bx + h * hw - 0.2, by + 1.2, 0.5, 0.2,
                     align=PP_ALIGN.CENTER)
        write(tf, [(lab, dict(name=MONO, size=8, color=MUTED), dict(space_after=0))])
page_num(s, 5)

# =================================================================== 7 열 갈래
s = slide_light(prs)
title_bar(s, "06  TEN", "열 갈래로 늘리면")

tf = textbox(s, M, 1.68, 8.2, 0.3)
write(tf, [("갈래를 늘려 물을 것은 하나임 · 새 무늬가 나오는가, "
            "아니면 온도 구간만 쪼개지는가.",
            dict(size=12, color=MUTED), dict(space_after=0))])
ramp_legend(s, W - M - 3.2, 1.86, 3.2, HEAT_BINS, HEAT, "섭씨")

tcell = 0.155
tgw = X * tcell
tcolw = tgw + 1.05
tgap = (W - 2 * M - 5 * tcolw) / 4
for i, t in enumerate(TEN):
    col, row = i % 5, i // 5
    gx = M + col * (tcolw + tgap)
    gy = 2.62 + row * 2.28

    tf = textbox(s, gx, gy - 0.5, tcolw, 0.24)
    write(tf, [(f"{i+1}. {t['name']}", dict(size=10, bold=True, color=INK),
                dict(space_after=0))])
    tf = textbox(s, gx, gy - 0.27, tcolw, 0.22)
    write(tf, [(f"{t['pct']}% · {t['n']:,}개", dict(name=MONO, size=8.5,
                                                   color=MUTED),
                dict(space_after=0))])

    heat_grid(s, gx, gy, tcell, t["grid"])

    if t["isnew"]:
        mark = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(gx - 0.05),
                                  Inches(gy - 0.05), Inches(tgw + 0.1),
                                  Inches(tgw + 0.1))
        mark.fill.background()
        mark.line.color.rgb = EMBER
        mark.line.width = Pt(2.5)
        mark.shadow.inherit = False
        mark.text_frame.text = ""

    tf = textbox(s, gx, gy + tgw + 0.08, tcolw, 0.6)
    write(tf, [(f"오른쪽 {zavg(t['grid'], BLOCK):.0f} · 등줄기 "
                f"{zavg(t['grid'], SPINE):.0f}",
                dict(name=MONO, size=8.5, color=MUTED), dict(space_after=1)),
               (("새 무늬" if t["isnew"]
                 else f"= {PAT[t['nearest6']]['name']}"),
                dict(size=8.5, bold=t["isnew"],
                     color=EMBER if t["isnew"] else TEAL),
                dict(space_after=1)),
               (f"무늬 상관 {t['nearest_corr']:.2f}",
                dict(name=MONO, size=8.5, color=MUTED), dict(space_after=0))])

tf = textbox(s, M, 6.88, 11.5, 0.26)
write(tf, [("무늬 상관은 평균을 빼고 정규화한 뒤 여섯 갈래와 견준 값임 · "
            "1.00 이면 무늬는 그대로고 온도만 다른 것임",
            dict(size=9.5, color=MUTED), dict(space_after=0))])
page_num(s, 6)

# =================================================================== 8 새 무늬
s = slide_light(prs)
title_bar(s, "07  WHAT IS NEW", "열로 늘려 새로 얻은 것은 하나")

NEWI = next(i for i, t in enumerate(TEN) if t["isnew"])
NT = TEN[NEWI]

tf = textbox(s, M, 1.7, 6.6, 0.3)
write(tf, [("여섯 갈래가 어떻게 쪼개졌는가", dict(size=13, bold=True, color=INK),
            dict(space_after=0))])

hx = M + 2.05
for b in range(10):
    tf = textbox(s, hx + b * 0.63, 2.04, 0.6, 0.22, align=PP_ALIGN.CENTER)
    write(tf, [(str(b + 1), dict(name=MONO, size=9,
                                 bold=(b == NEWI), color=EMBER if b == NEWI else MUTED),
                dict(space_after=0))])

yy = 2.3
for a, p in enumerate(PAT):
    if a % 2 == 0:
        card(s, M - 0.08, yy - 0.04, 8.55, 0.36, fill=PAPER)
    tf = textbox(s, M, yy, 2.0, 0.26)
    write(tf, [(f"{a+1}. {p['name']}", dict(size=9.5, color=INK),
                dict(space_after=0))])
    for b in range(10):
        v = CROSS[a][b]
        if not v:
            continue
        tf = textbox(s, hx + b * 0.63, yy, 0.6, 0.26, align=PP_ALIGN.CENTER)
        write(tf, [(f"{v}%", dict(name=MONO, size=9.5, bold=(v >= 50),
                                  color=EMBER if b == NEWI else
                                  (INK if v >= 50 else MUTED)),
                    dict(space_after=0))])
    yy += 0.42

tf = textbox(s, M, 5.05, 8.4, 0.9)
write(tf, [("전부 정지는 그대로 남음 · 평소 가동(61%)이 넷으로 쪼개졌는데 "
            "넷 다 무늬 상관 0.99~1.00 임 · 나뉜 기준은 시간대임 - "
            "새벽 · 낮 · 저녁. 같은 설비가 같은 방식으로 도는데 주변 온도만 "
            "다름", dict(size=11, color=INK), dict(space_after=6, line=1.3)),
           ("등줄기 가동이 셋으로 갈리면서 그중 하나가 새 무늬로 떨어져 "
            "나왔음", dict(size=11, bold=True, color=EMBER),
            dict(space_after=0, line=1.3))])

# 오른쪽 - 새 무늬
rx = W - M - 4.1
card(s, rx - 0.2, 1.62, 4.3, 5.1, fill=RGBColor(0xFD, 0xF1, 0xEC))

tf = textbox(s, rx, 1.8, 3.9, 0.3)
write(tf, [(f"{NEWI+1}. {NT['name']}", dict(size=14, bold=True, color=EMBER),
            dict(space_after=0))])
tf = textbox(s, rx, 2.12, 3.9, 0.26)
write(tf, [(f"{NT['n']}개 · {NT['pct']}% · "
            f"등줄기 가동과 무늬 상관 {NT['nearest_corr']:.2f}",
            dict(name=MONO, size=9.5, color=MUTED), dict(space_after=0))])

ncell = 0.22
heat_grid(s, rx + 0.95, 2.48, ncell, NT["grid"])

tf = textbox(s, rx, 4.42, 3.9, 1.15)
write(tf, [("오른쪽 발열부가 세로로 길어짐",
            dict(size=11.5, bold=True, color=INK), dict(space_after=4)),
           ("평소에는 행 2-3 에만 있던 열이 행 1 부터 행 6 까지 이어짐 · "
            "\"오른쪽 확장\" 과 달리 등줄기도 함께 올라옴 - 두 계통이 "
            "동시에 도는 상태임",
            dict(size=10, color=INK), dict(space_after=0, line=1.25))])

tf = textbox(s, rx, 5.62, 3.9, 0.24)
write(tf, [("나타난 날", dict(size=9.5, bold=True, color=MUTED),
            dict(space_after=0))])
tf = textbox(s, rx, 5.84, 3.9, 0.24)
write(tf, [(" · ".join(d[4:6] + "-" + d[6:] for d in NT["dates"]),
            dict(name=MONO, size=9, color=INK), dict(space_after=0))])
tf = textbox(s, rx, 6.12, 3.9, 0.24)
write(tf, [("많은 시간  15시 · 16시 · 17시", dict(name=MONO, size=9,
                                              color=INK), dict(space_after=0))])
page_num(s, 7)

# =================================================================== 9 세 가지로
s = slide_light(prs)
title_bar(s, "08  WHICH ONE", "점수 0.05 는 어느 패턴인가")

tf = textbox(s, M, 1.7, 11.5, 0.3)
write(tf, [("하나로만 재면 틀린 답이 나옴 · 무늬 · 크기 · 실제 프레임 "
            "셋으로 봄", dict(size=13, color=MUTED), dict(space_after=0))])

# 왼쪽 - 오늘 격자
ccell = 0.26
heat_grid(s, M, 2.35, ccell, TODAY)
tf = textbox(s, M, 2.35 + Y * ccell + 0.1, X * ccell, 0.26, align=PP_ALIGN.CENTER)
write(tf, [("오늘 09-25 09시", dict(size=11, bold=True, color=EMBER),
            dict(space_after=0))])
tf = textbox(s, M, 2.35 + Y * ccell + 0.34, X * ccell, 0.6, align=PP_ALIGN.CENTER)
write(tf, [(f"전체 {sum(TODAY)/64:.1f}도", dict(name=MONO, size=10, color=INK),
            dict(space_after=1)),
           (f"오른쪽 {zavg(TODAY, BLOCK):.1f}도",
            dict(name=MONO, size=10, color=EMBER), dict(space_after=0))])

card(s, M - 0.1, 4.85, X * ccell + 0.2, 1.75, fill=PAPER)
tf = textbox(s, M + 0.06, 5.0, X * ccell - 0.1, 1.5)
write(tf, [("재는 법", dict(size=10.5, bold=True, color=INK), dict(space_after=4)),
           ("무늬 - 평균을 빼고 정규화한 상관. 전체가 몇 도인지는 지움",
            dict(size=9, color=MUTED), dict(space_after=3, line=1.2)),
           ("크기 - 칸별 차이. 그 무리 표본의 95%보다 멀면 밖임",
            dict(size=9, color=MUTED), dict(space_after=3, line=1.2)),
           ("실제 프레임 - 중심은 평균이라 실제로는 없는 모습일 수 있음",
            dict(size=9, color=MUTED), dict(space_after=0, line=1.2))])

# 오른쪽 - 열 갈래 표
tx = M + X * ccell + 0.55
cols = [(0.0, 2.35, "패턴", PP_ALIGN.LEFT),
        (2.35, 1.15, "무늬 상관", PP_ALIGN.RIGHT),
        (3.50, 0.95, "거리", PP_ALIGN.RIGHT),
        (4.45, 1.25, "그 무리 95%", PP_ALIGN.RIGHT),
        (5.70, 0.85, "판정", PP_ALIGN.RIGHT)]
yy = 2.3
for dx, cw, lab, al in cols:
    tf = textbox(s, tx + dx, yy, cw, 0.24, align=al)
    write(tf, [(lab, dict(size=9.5, bold=True, color=MUTED), dict(space_after=0))])
yy += 0.3

best_corr = max(range(10), key=lambda i: CMP["rows"][i]["corr"])
best_dist = min(range(10), key=lambda i: CMP["rows"][i]["dist"])
for i, r in enumerate(CMP["rows"]):
    if i % 2 == 0:
        card(s, tx - 0.1, yy - 0.04, 6.75, 0.36, fill=PAPER)
    vals = [f"{i+1}. {TEN[i]['name']}", f"{r['corr']:.3f}",
            f"{r['dist']:.1f}", f"{r['p95']:.1f}", "밖"]
    for (dx, cw, _l, al), v, j in zip(cols, vals, range(5)):
        hot = (j == 1 and i == best_corr) or (j == 2 and i == best_dist)
        tf = textbox(s, tx + dx, yy, cw, 0.28, align=al)
        write(tf, [(v, dict(name=KR if j == 0 else MONO, size=9.5,
                            bold=hot or j == 4,
                            color=EMBER if (hot or j == 4) else INK),
                    dict(space_after=0))])
    yy += 0.4

card(s, tx - 0.1, 6.42, 6.75, 0.5, fill=RGBColor(0xFD, 0xF1, 0xEC))
tf = textbox(s, tx + 0.06, 6.54, 6.5, 0.3)
write(tf, [("열 갈래가 모두 밖임 · 무늬로 가장 닮은 9번도 등줄기가 "
            "90~96도인데 오늘은 53~59도임",
            dict(size=10.5, bold=True, color=EMBER), dict(space_after=0))])
page_num(s, 8)

# =================================================================== 10 실제 프레임
s = slide_light(prs)
title_bar(s, "09  NEAREST", "가장 가까운 실제 프레임은 자료의 마지막 이틀")

tf = textbox(s, M, 1.7, 11.5, 0.3)
write(tf, [("중심이 아니라 표본 6,365개와 하나씩 견줬음",
            dict(size=13, color=MUTED), dict(space_after=0))])

ncell = 0.24
heat_grid(s, M, 2.3, ncell, TODAY)
tf = textbox(s, M, 2.3 + Y * ncell + 0.1, X * ncell, 0.24, align=PP_ALIGN.CENTER)
write(tf, [("오늘 09-25", dict(size=10.5, bold=True, color=EMBER),
            dict(space_after=0))])
tf = textbox(s, M, 2.3 + Y * ncell + 0.32, X * ncell, 0.24, align=PP_ALIGN.CENTER)
write(tf, [(f"오른쪽 {zavg(TODAY, BLOCK):.0f}도", dict(name=MONO, size=10,
                                                    color=EMBER),
            dict(space_after=0))])

nx = M + X * ncell + 0.45
heat_grid(s, nx, 2.3, ncell, CMP["nearest_grid"])
tf = textbox(s, nx, 2.3 + Y * ncell + 0.1, X * ncell, 0.24, align=PP_ALIGN.CENTER)
write(tf, [("07-03 09:14 (가장 가까움)", dict(size=10.5, color=INK),
            dict(space_after=0))])
tf = textbox(s, nx, 2.3 + Y * ncell + 0.32, X * ncell, 0.24, align=PP_ALIGN.CENTER)
write(tf, [(f"오른쪽 {zavg(CMP['nearest_grid'], BLOCK):.0f}도",
            dict(name=MONO, size=10, color=INK), dict(space_after=0))])

rx = nx + X * ncell + 0.6
tf = textbox(s, rx, 2.26, 6.0, 0.28)
write(tf, [("가까운 여섯 프레임", dict(size=12.5, bold=True, color=INK),
            dict(space_after=0))])
yy = 2.62
for i, n in enumerate(CMP["near"]):
    if i % 2 == 0:
        card(s, rx - 0.08, yy - 0.04, 5.9, 0.34, fill=PAPER)
    st = n["stamp"]
    txt = f"{st[4:6]}-{st[6:8]} {st[9:11]}:{st[11:13]}"
    for dx, cw, v, al, mono in (
            (0.0, 1.5, txt, PP_ALIGN.LEFT, True),
            (1.5, 0.85, f"{n['dist']:.1f}", PP_ALIGN.RIGHT, True),
            (2.4, 1.0, f"{n['blk']:.1f}도", PP_ALIGN.RIGHT, True),
            (3.5, 2.3, f"{n['pat']+1}. {TEN[n['pat']]['name']}",
             PP_ALIGN.RIGHT, False)):
        tf = textbox(s, rx + dx, yy, cw, 0.28, align=al)
        write(tf, [(v, dict(name=MONO if mono else KR, size=9.5, color=INK),
                    dict(space_after=0))])
    yy += 0.38

for dx, cw, lab, al in ((0.0, 1.5, "날짜", PP_ALIGN.LEFT),
                        (1.5, 0.85, "거리", PP_ALIGN.RIGHT),
                        (2.4, 1.0, "오른쪽", PP_ALIGN.RIGHT),
                        (3.5, 2.3, "패턴", PP_ALIGN.RIGHT)):
    tf = textbox(s, rx + dx, 2.58 - 0.26, cw, 0.22, align=al)
    write(tf, [(lab, dict(size=9, bold=True, color=MUTED), dict(space_after=0))])

card(s, M, 5.0, W - 2 * M, 1.62, fill=RGBColor(0xFD, 0xF1, 0xEC))
tf = textbox(s, M + 0.3, 5.16, W - 2 * M - 0.6, 0.3)
write(tf, [("어느 패턴도 아님 · 방향만 말하면 자료가 끝나는 무렵의 "
            "\"식어 가던 평소 가동\" 쪽임",
            dict(size=13, bold=True, color=EMBER), dict(space_after=0))])
tf = textbox(s, M + 0.3, 5.52, W - 2 * M - 0.6, 1.0)
write(tf, [(f"가까운 여섯이 모두 07-03 과 07-04 - 자료의 마지막 이틀이고, "
            f"그 칸 평균이 전체 기간 중 가장 낮았던 날임 · 그때 오른쪽이 "
            f"48~53도였고 오늘은 {zavg(TODAY, BLOCK):.0f}도임",
            dict(size=11.5, color=INK), dict(space_after=5, line=1.3)),
           (f"다만 가장 가까운 것도 거리 {CMP['near'][0]['dist']:.1f} 임 · "
            f"표본끼리의 거리가 중앙값 {CMP['pair_median']:.0f}, 하위 25%가 "
            f"{CMP['pair_q25']:.0f} 이니 아무 두 프레임을 집어 온 것과 비슷한 "
            f"정도임 · 07-04 이후 두 달 반 동안 이 구간의 자료가 없어 "
            f"모델이 아래쪽을 배울 기회가 없었음",
            dict(size=11.5, color=INK), dict(space_after=0, line=1.3))])
page_num(s, 9)

# =================================================================== 10 정리
s = slide_dark(prs)
title_bar(s, "10  CONCLUSION", "정리", dark=True)

items = [
    ("여섯 중 다섯이 오른쪽 발열부 68~84도",
     "변하는 것은 가운데 등줄기임 · 오른쪽이 식는 경우는 전부 정지(8.1%)뿐임"),
    ("식은 자료는 있지만 종류가 다름",
     "05-18~21 나흘은 화면 전체가 21도임 · 오늘과 무늬 상관이 0 임"),
    ("오늘은 열 갈래 모두에서 밖임",
     "무늬로 가장 닮은 것도 등줄기가 90도대인데 오늘은 50도대임 · "
     "가장 가까운 실제 프레임은 자료 마지막 이틀(07-03·04)이고 거리 51.8 임"),
    ("열로 늘려도 새 무늬는 하나뿐임",
     "오른쪽이 세로로 길어지는 오후 상태(3.8%). 나머지 아홉은 온도 구간만 "
     "쪼갠 것이고, 아홉이 오른쪽 발열부 66~84도임"),
    ("게다가 지금 모델은 step_0 로 배우지 않았음",
     "재학습은 히스토리 DB(07-02~09-24)에서만 재생 버퍼를 만듦 · "
     "step_0 는 07-04 에 끝남"),
]
yy = 1.95
for i, (head, body) in enumerate(items):
    circle(s, M, yy + 0.02, 0.34, EMBER, str(i + 1), WHITE, 11)
    tf = textbox(s, M + 0.52, yy, 11.0, 0.3)
    write(tf, [(head, dict(size=14.5, bold=True, color=WHITE), dict(space_after=0))])
    tf = textbox(s, M + 0.52, yy + 0.34, 11.0, 0.4)
    write(tf, [(body, dict(size=11.5, color=RGBColor(0xA8, 0xB6, 0xCC)),
                dict(space_after=0, line=1.25))])
    yy += 0.94

card(s, M, 6.45, W - 2 * M, 0.62, fill=NAVY_SOFT)
tf = textbox(s, M + 0.3, 6.6, W - 2 * M - 0.6, 0.34)
write(tf, [("점수 0.05 는 모델이 고장난 것이 아니라 처음 보는 모양이라고 "
            "말하는 중임 · 설비를 꺼 둔 채로 운용한다면 그 상태 자료가 "
            "쌓인 뒤에 재학습해야 함",
            dict(size=12, bold=True, color=AMBER), dict(space_after=0))])
page_num(s, 10, dark=True)

# ------------------------------------------------------------------ 저장
import sys
out = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\MultiModal_FireCam\cj_busan_1_열패턴_비교.pptx"
prs.save(out)
print("저장 완료:", out)
print("슬라이드 수:", len(prs.slides.__iter__.__self__._sldIdLst))
