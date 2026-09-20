# -*- coding: utf-8 -*-
"""멀티모달 화재감지 모니터링 시스템 - 설치/구성 매뉴얼 PPTX 생성"""

import copy
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.oxml.ns import qn

# ---------------------------------------------------------------- 팔레트
NAVY      = RGBColor(0x0F, 0x1B, 0x2D)   # 어두운 배경
NAVY_SOFT = RGBColor(0x1C, 0x2B, 0x45)   # 어두운 카드
EMBER     = RGBColor(0xE4, 0x57, 0x2E)   # 강조 (불꽃)
AMBER     = RGBColor(0xF4, 0xA2, 0x61)   # 보조 강조
TEAL      = RGBColor(0x2A, 0x9D, 0x8F)   # 정상/완료
WHITE     = RGBColor(0xFF, 0xFF, 0xFF)
PAPER     = RGBColor(0xF2, 0xF4, 0xF7)   # 밝은 카드
INK       = RGBColor(0x1A, 0x24, 0x35)   # 본문
MUTED     = RGBColor(0x66, 0x70, 0x85)   # 보조 텍스트
CODE_BG   = RGBColor(0x14, 0x20, 0x33)
CODE_FG   = RGBColor(0xD6, 0xDF, 0xEA)

KR   = "맑은 고딕"
MONO = "Consolas"

W, H = 13.333, 7.5
M    = 0.72          # 좌우 여백


def font_of(run, name=KR, size=14, bold=False, color=INK, italic=False):
    f = run.font
    f.name = name
    f.size = Pt(size)
    f.bold = bold
    f.italic = italic
    f.color.rgb = color
    rPr = run._r.get_or_add_rPr()
    for tag in ("a:ea", "a:cs"):
        el = rPr.find(qn(tag))
        if el is None:
            el = rPr.makeelement(qn(tag), {})
            rPr.append(el)
        el.set("typeface", name)


def textbox(slide, x, y, w, h, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    tf.paragraphs[0].alignment = align
    tf._default_align = align          # 뒤에 추가되는 문단도 같은 정렬을 따르게 한다
    return tf


def para(tf, first=False, space_after=0, space_before=0, line=None, align=None):
    p = tf.paragraphs[0] if first else tf.add_paragraph()
    p.alignment = align if align is not None else getattr(tf, "_default_align", PP_ALIGN.LEFT)
    p.space_after = Pt(space_after)
    p.space_before = Pt(space_before)
    if line:
        p.line_spacing = line
    return p


def write(tf, lines, first=True):
    """lines: [(text, dict(font kwargs), dict(para kwargs)), ...]"""
    is_first = first
    for item in lines:
        txt, fkw, pkw = item
        p = para(tf, first=is_first, **pkw)
        is_first = False
        r = p.add_run()
        r.text = txt
        font_of(r, **fkw)


def card(slide, x, y, w, h, fill=PAPER, radius=0.06, line=None, shadow=False):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                Inches(x), Inches(y), Inches(w), Inches(h))
    sh.adjustments[0] = radius
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    if line is None:
        sh.line.fill.background()
    else:
        sh.line.color.rgb = line
        sh.line.width = Pt(1)
    sh.shadow.inherit = False
    sh.text_frame.text = ""
    return sh


def circle(slide, x, y, d, fill, text=None, tcolor=WHITE, tsize=16, tbold=True):
    sh = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    sh.fill.solid()
    sh.fill.fore_color.rgb = fill
    sh.line.fill.background()
    sh.shadow.inherit = False
    if text is not None:
        tf = sh.text_frame
        tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        p = tf.paragraphs[0]
        p.alignment = PP_ALIGN.CENTER
        r = p.add_run()
        r.text = text
        font_of(r, KR, tsize, tbold, tcolor)
    return sh


def code_block(slide, x, y, w, lines, size=12.5, pad=0.22):
    h = pad * 2 + len(lines) * (size * 1.55 / 72.0)
    card(slide, x, y, w, h, fill=CODE_BG, radius=0.05)
    tf = textbox(slide, x + pad, y + pad, w - pad * 2, h - pad * 2)
    items = []
    for i, ln in enumerate(lines):
        col = MUTED if ln.strip().startswith("#") else CODE_FG
        if ln.strip().startswith("$"):
            col = AMBER
        items.append((ln if ln else " ",
                      dict(name=MONO, size=size, color=col),
                      dict(space_after=1.5, line=1.0)))
    write(tf, items)
    return y + h


def slide_dark(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = NAVY
    return s


def slide_light(prs):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bg = s.background.fill
    bg.solid()
    bg.fore_color.rgb = WHITE
    return s


def title_bar(slide, kicker, title, dark=False):
    """슬라이드 상단 제목 (장식선 없이 여백으로 구분)"""
    tf = textbox(slide, M, 0.52, W - 2 * M, 0.34)
    write(tf, [(kicker, dict(size=12.5, bold=True, color=EMBER),
                dict(space_after=0))])
    tf2 = textbox(slide, M, 0.88, W - 2 * M, 0.68)
    write(tf2, [(title, dict(size=30, bold=True, color=WHITE if dark else INK),
                 dict(space_after=0))])


def page_num(slide, n, dark=False):
    tf = textbox(slide, W - M - 1.0, H - 0.62, 1.0, 0.3, align=PP_ALIGN.RIGHT)
    write(tf, [(str(n), dict(size=10.5, color=MUTED), dict(space_after=0))])


ICON = r"D:\MultiModal_FireCam\otg_monitoring\icons8-web-camera-100.png"

prs = Presentation()
prs.slide_width = Inches(W)
prs.slide_height = Inches(H)

# =================================================================== 1 표지
s = slide_dark(prs)
circle(s, M, 1.95, 1.5, WHITE)
s.shapes.add_picture(ICON, Inches(M + 0.33), Inches(1.95 + 0.33), height=Inches(0.84))

tf = textbox(s, M + 2.05, 2.02, 9.0, 0.5)
write(tf, [("설치 및 구성 매뉴얼", dict(size=15, bold=True, color=AMBER), dict(space_after=0))])

tf = textbox(s, M + 2.05, 2.55, 9.6, 1.5)
write(tf, [("멀티모달", dict(size=44, bold=True, color=WHITE), dict(space_after=4)),
           ("화재감지 모니터링 시스템", dict(size=44, bold=True, color=WHITE), dict(space_after=0))])

tf = textbox(s, M + 2.05, 4.42, 9.6, 0.4)
write(tf, [("열화상 · 자세추정 · 이상탐지 통합 감시", dict(size=15, color=RGBColor(0xA8, 0xB6, 0xCC)),
            dict(space_after=0))])

for i, (lab, val) in enumerate([("대상 현장", "kict1 · cj_busan_1"),
                                ("실행 환경", "Windows · Anaconda mmc"),
                                ("작성일", "2026-09-20")]):
    x = M + i * 3.4
    tf = textbox(s, x, 5.85, 3.2, 0.3)
    write(tf, [(lab, dict(size=10.5, bold=True, color=EMBER), dict(space_after=2))])
    tf = textbox(s, x, 6.18, 3.2, 0.32)
    write(tf, [(val, dict(size=13, color=WHITE), dict(space_after=0))])

# =================================================================== 2 개요
s = slide_light(prs)
title_bar(s, "01  SYSTEM OVERVIEW", "시스템은 무엇으로 이루어지는가")

tf = textbox(s, M, 1.72, 11.0, 0.35)
write(tf, [("감시 프로그램 1개가 현장(user)마다 파이썬 프로세스 3개를 띄워 관리합니다.",
            dict(size=14, color=MUTED), dict(space_after=0))])

items = [
    ("otg_monitoring.exe", "감시 프로그램", EMBER,
     ["C++ / MFC 데스크톱 앱", "프로세스 기동 · 정지 · 감시", "DB 상태와 화면 표시"]),
    ("server_to_db.py", "데이터 수집", AMBER,
     ["서버에서 열화상 · 센서 수신", "8x8 = 64셀로 축약", "MySQL 에 적재"]),
    ("predict_machine.py", "이상 점수 산출", TEAL,
     ["오토인코더 복원 오차 기반", "scaler + autoencoder 사용", "results_history 에 기록"]),
    ("fall_detection.py", "낙상 · 화재 검출", RGBColor(0x6A, 0x5A, 0xCD),
     ["openpifpaf 자세추정", "YOLO 화재 · 연기 검출", "이미지 뷰어 표시"]),
]
cw, gap = 2.82, 0.28
for i, (name, role, col, bullets) in enumerate(items):
    x = M + i * (cw + gap)
    card(s, x, 2.35, cw, 3.05, fill=PAPER)
    circle(s, x + 0.28, 2.63, 0.52, col, str(i + 1), WHITE, 15)
    tf = textbox(s, x + 0.28, 3.32, cw - 0.56, 0.3)
    write(tf, [(role, dict(size=15, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, x + 0.28, 3.68, cw - 0.56, 0.3)
    write(tf, [(name, dict(name=MONO, size=10.5, color=col), dict(space_after=0))])
    tf = textbox(s, x + 0.28, 4.18, cw - 0.56, 1.5)
    write(tf, [(b, dict(size=11.5, color=MUTED), dict(space_after=7, line=1.15)) for b in bullets])

card(s, M, 5.72, W - 2 * M, 0.78, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, M + 0.34, 5.94, W - 2 * M - 0.68, 0.36)
write(tf, [("현장이 2곳이므로 정상 가동 시 파이썬 프로세스는 3 x 2 = 6개가 실행됩니다.",
            dict(size=13, bold=True, color=RGBColor(0x1B, 0x6B, 0x60)), dict(space_after=0))])
page_num(s, 2)

# =================================================================== 3 데이터 흐름
s = slide_light(prs)
title_bar(s, "02  DATA FLOW", "데이터는 이렇게 흐릅니다")

flow = [
    ("현장 서버", "sangchoo.com", "ir_img.csv\nmain_sensor.inf\nrgb_img.jpg", NAVY_SOFT),
    ("수집", "server_to_db.py", "64셀 축약\nFIFO median", EMBER),
    ("저장", "MySQL 8.0", "<user>_sensor_data\ncurrent_value", AMBER),
    ("분석", "predict_machine\nfall_detection", "이상 점수\n낙상 · 화재", TEAL),
    ("표시", "otg_monitoring.exe", "상태줄 · 목록\n이미지 뷰어", RGBColor(0x6A, 0x5A, 0xCD)),
]
bw, bgap = 2.06, 0.42
for i, (stage, name, detail, col) in enumerate(flow):
    x = M + i * (bw + bgap)
    card(s, x, 2.45, bw, 2.35, fill=PAPER)
    circle(s, x + bw / 2 - 0.2, 2.18, 0.4, col)
    tf = textbox(s, x + 0.18, 2.78, bw - 0.36, 0.3, align=PP_ALIGN.CENTER)
    write(tf, [(stage, dict(size=14, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, x + 0.14, 3.16, bw - 0.28, 0.5, align=PP_ALIGN.CENTER)
    write(tf, [(name, dict(name=MONO, size=9.5, color=col), dict(space_after=0, line=1.1))])
    tf = textbox(s, x + 0.14, 3.78, bw - 0.28, 0.9, align=PP_ALIGN.CENTER)
    write(tf, [(detail, dict(size=10.5, color=MUTED), dict(space_after=0, line=1.2))])
    if i < len(flow) - 1:
        ar = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW,
                                Inches(x + bw + 0.07), Inches(3.42), Inches(0.28), Inches(0.22))
        ar.fill.solid()
        ar.fill.fore_color.rgb = RGBColor(0xC3, 0xCC, 0xD9)
        ar.line.fill.background()
        ar.shadow.inherit = False

card(s, M, 5.28, W - 2 * M, 1.15, fill=RGBColor(0xFD, 0xF1, 0xEC))
tf = textbox(s, M + 0.34, 5.52, W - 2 * M - 0.68, 0.7)
write(tf, [("수집 주기는 현장마다 다릅니다. ", dict(size=13, bold=True, color=EMBER), dict(space_after=4)),
           ("서버의 파일이 갱신되지 않으면 같은 값이 반복 입력되어 점수가 고정됩니다. "
            "센서 타임스탬프(ts)가 최신인지 debug_logs 에서 확인하십시오.",
            dict(size=12.5, color=INK), dict(space_after=0, line=1.25))], first=False)
page_num(s, 3)

# =================================================================== 4 폴더 구조
s = slide_light(prs)
title_bar(s, "03  LAYOUT", "폴더 구조")

tree = [
    "D:\\MultiModal_FireCam\\          <- ROOT_PATH",
    "  otg_monitoring.exe             감시 프로그램 (빌드 산출물)",
    "  otg_monitoring.ini             시작 폴더 · Anaconda 지정",
    "  libmysql.dll                   MySQL 클라이언트",
    "",
    "  source\\                        공통 파이썬 모듈",
    "    server_to_db.py  db_utils.py  viewer_utils.py",
    "    cv_utils.py      utils.py     constants.py",
    "",
    "  predict_machine\\predict_machine.py",
    "  fall_detection\\fall_detection.py",
    "  fire_detection\\best_epoch_31_fire_smoke_person.pt",
    "",
    "  users\\<user_ID>\\",
    "    env.ini        현장 설정 (DB · 네트워크 · 임계값)",
    "    secrets.ini    DB 비밀번호  (git 제외)",
    "    scaler.pkl / scaler.npz / autoencoder_final.pth",
    "",
    "  debug_logs\\                    실행 로그 (프로세스별)",
    "  otg_monitoring\\                C++ 소스 · Visual Studio 프로젝트",
]
code_block(s, M, 1.78, 7.55, tree, size=11)

bx = M + 7.95
notes = [
    ("ROOT_PATH 가 기준점", "모든 경로는 이 폴더를 기준으로 계산됩니다. exe 와 데이터가 같은 폴더에 놓입니다.", EMBER),
    ("user 별 폴더 분리", "현장을 추가하려면 users 아래에 폴더를 만들고 env.ini 와 secrets.ini 를 넣습니다.", AMBER),
    ("모델 파일은 재생성 불가", "scaler 와 autoencoder 가중치는 재학습 없이 복구할 수 없습니다. 반드시 백업하십시오.", TEAL),
]
y = 1.78
for head, body, col in notes:
    card(s, bx, y, 3.66, 1.56, fill=PAPER)
    circle(s, bx + 0.26, y + 0.26, 0.34, col)
    tf = textbox(s, bx + 0.72, y + 0.28, 2.7, 0.3)
    write(tf, [(head, dict(size=13, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, bx + 0.26, y + 0.72, 3.14, 0.75)
    write(tf, [(body, dict(size=11, color=MUTED), dict(space_after=0, line=1.2))])
    y += 1.72
page_num(s, 4)

# =================================================================== 5 설정 파일
s = slide_light(prs)
title_bar(s, "04  CONFIGURATION", "설정 파일 세 가지")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("장비 고유 · 현장 고유 · 비밀 정보를 분리했습니다. 읽는 순서가 정해져 있습니다.",
            dict(size=14, color=MUTED), dict(space_after=0))])

cfgs = [
    ("otg_monitoring.ini", "exe 와 같은 폴더", EMBER, "장비(PC) 고유",
     ["[PATHS] ROOT_PATH = D:\\MultiModal_FireCam\\",
      "[PYTHON] ANACONDA_ROOT = C:\\Users\\<계정>\\anaconda3\\",
      "[PYTHON] ANACONDA_ENV = mmc"],
     "가장 먼저 읽습니다. ROOT_PATH 가 env.ini 의 위치를 결정하기 때문입니다."),
    ("users\\<user>\\env.ini", "현장 폴더", AMBER, "현장 고유",
     ["[NETWORK] ROOT_URL · MONITOR_SEAT_ORDER",
      "[DB_RUNTIME] DB_HOST · DB_USER · DB_NAME_SENSOR",
      "[CONSTANTS] 임계값 · 격자 크기"],
     "현장마다 다른 값. 비밀번호는 여기에 두지 않습니다."),
    ("users\\<user>\\secrets.ini", "현장 폴더", TEAL, "비밀 정보",
     ["[DB_RUNTIME] DB_PASSWORD = ...",
      "[DB_ADMIN] DB_ADMIN_PASSWORD = ..."],
     "git 추적 제외. users\\secrets.ini.sample 을 복사해 만듭니다."),
]
y = 2.24
for name, where, col, kind, keys, note in cfgs:
    hh = 1.24 if len(keys) < 3 else 1.42
    card(s, M, y, W - 2 * M, hh, fill=PAPER)
    circle(s, M + 0.3, y + 0.3, 0.42, col)
    tf = textbox(s, M + 0.92, y + 0.26, 4.2, 0.3)
    write(tf, [(name, dict(name=MONO, size=13.5, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, M + 0.92, y + 0.62, 4.2, 0.28)
    write(tf, [(kind + "  ·  " + where, dict(size=10.5, color=col), dict(space_after=0))])
    tf = textbox(s, M + 5.35, y + 0.24, 4.3, hh - 0.4)
    write(tf, [(k, dict(name=MONO, size=9.5, color=MUTED), dict(space_after=4, line=1.1)) for k in keys])
    tf = textbox(s, M + 0.92, y + 0.94, 4.3, 0.5)
    write(tf, [(note, dict(size=10.5, color=MUTED), dict(space_after=0, line=1.2))])
    y += hh + 0.2
page_num(s, 5)

# =================================================================== 6 설치 1
s = slide_light(prs)
title_bar(s, "05  INSTALL  STEP 1", "사전 준비 — 세 가지를 먼저 설치")

pre = [
    ("Visual Studio", "MFC 포함 설치", "C++ 데스크톱 개발 워크로드와\nMFC 구성 요소를 반드시 포함합니다.\nopenpifpaf 빌드에도 필요합니다.", EMBER),
    ("MySQL 8.0", "mysql-installer-web-community", "Server 와 Connector/C 를 설치합니다.\nroot 비밀번호를 기억해 두십시오.\nlibmysql.dll 경로가 필요합니다.", AMBER),
    ("Anaconda", "Python 3.9 환경용", "conda 명령이 동작하는지\nconda -V 로 확인합니다.", TEAL),
]
for i, (name, sub, body, col) in enumerate(pre):
    x = M + i * (3.86 + 0.26)
    card(s, x, 1.95, 3.86, 2.62, fill=PAPER)
    circle(s, x + 0.3, 2.25, 0.5, col, str(i + 1), WHITE, 15)
    tf = textbox(s, x + 0.96, 2.3, 2.7, 0.3)
    write(tf, [(name, dict(size=16, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, x + 0.3, 2.92, 3.26, 0.28)
    write(tf, [(sub, dict(size=10.5, color=col), dict(space_after=0))])
    tf = textbox(s, x + 0.3, 3.3, 3.26, 1.1)
    write(tf, [(body, dict(size=11.5, color=MUTED), dict(space_after=0, line=1.25))])

tf = textbox(s, M, 4.92, 11.9, 0.32)
write(tf, [("설치 확인", dict(size=14, bold=True, color=INK), dict(space_after=0))])
code_block(s, M, 5.3, W - 2 * M, [
    "$ conda -V                    # conda 24.x 처럼 버전이 나오면 정상",
    "$ mysql --version             # mysql  Ver 8.0.x",
], size=12.5)
page_num(s, 6)

# =================================================================== 7 설치 2
s = slide_light(prs)
title_bar(s, "06  INSTALL  STEP 2", "파이썬 환경 (conda: mmc)")

code_block(s, M, 1.82, 7.55, [
    "# 환경 생성",
    "$ conda create -n mmc python=3.9 -y",
    "$ conda activate mmc",
    "",
    "# 딥러닝 · 영상",
    "$ pip install torch==1.10.2 torchvision==0.11.3",
    "$ pip install openpifpaf==0.12.14",
    "$ pip install opencv-python  ultralytics",
    "",
    "# 수치 · 이상탐지",
    "$ pip install numpy==1.26.4  \"scipy<1.10\"",
    "$ pip install scikit-learn  joblib",
    "",
    "# DB",
    "$ pip install mysql-connector-python",
], size=11.5)

bx = M + 7.95
card(s, bx, 1.82, 3.66, 1.9, fill=RGBColor(0xFD, 0xEC, 0xEA))
circle(s, bx + 0.26, 2.08, 0.38, EMBER, "!", WHITE, 15)
tf = textbox(s, bx + 0.74, 2.1, 2.66, 0.3)
write(tf, [("db_utils 를 설치하지 마십시오", dict(size=12.5, bold=True, color=EMBER), dict(space_after=0))])
tf = textbox(s, bx + 0.26, 2.62, 3.14, 0.95)
write(tf, [("PyPI 에 같은 이름의 무관한 패키지가 있습니다. 설치하면 프로젝트의 "
            "source\\db_utils.py 대신 그쪽이 임포트되어 원인을 찾기 어려운 오류가 납니다.",
            dict(size=10.5, color=INK), dict(space_after=0, line=1.2))])

card(s, bx, 3.9, 3.66, 2.4, fill=PAPER)
tf = textbox(s, bx + 0.26, 4.14, 3.14, 0.3)
write(tf, [("설치 후 확인", dict(size=12.5, bold=True, color=INK), dict(space_after=0))])
vers = [("python", "3.9.x"), ("numpy", "1.25 ~ 1.26"), ("torch", "1.10.2"),
        ("openpifpaf", "0.12.14"), ("opencv", "4.x"), ("mysql-connector", "9.x")]
y = 4.56
for k, v in vers:
    tf = textbox(s, bx + 0.26, y, 1.75, 0.26)
    write(tf, [(k, dict(name=MONO, size=10, color=MUTED), dict(space_after=0))])
    tf = textbox(s, bx + 2.0, y, 1.4, 0.26)
    write(tf, [(v, dict(name=MONO, size=10, bold=True, color=TEAL), dict(space_after=0))])
    y += 0.29
page_num(s, 7)

# =================================================================== 8 설치 3
s = slide_light(prs)
title_bar(s, "07  INSTALL  STEP 3", "MySQL 데이터베이스 준비")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("현장(user)마다 별도의 데이터베이스를 씁니다. 이름 규칙은 <user_ID>_sensor_data 입니다.",
            dict(size=14, color=MUTED), dict(space_after=0))])

code_block(s, M, 2.24, W - 2 * M, [
    "$ mysql -u root -p                      # root 비밀번호 입력",
    "",
    "mysql> CREATE DATABASE kict1_sensor_data",
    "       CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;",
    "",
    "mysql> CREATE USER 'otg_user'@'localhost' IDENTIFIED BY '<비밀번호>';",
    "mysql> GRANT ALL PRIVILEGES ON kict1_sensor_data.* TO 'otg_user'@'localhost';",
    "mysql> FLUSH PRIVILEGES;",
    "",
    "mysql> SHOW GRANTS FOR 'otg_user'@'localhost';   # 권한 확인",
], size=12)

card(s, M, 5.92, W - 2 * M, 0.96, fill=PAPER)
tf = textbox(s, M + 0.34, 6.16, W - 2 * M - 0.68, 0.55)
p = tf.paragraphs[0]
p.line_spacing = 1.25
for txt, fkw in [
    ("현장을 추가할 때마다 ", dict(size=12.5, color=INK)),
    ("CREATE DATABASE", dict(name=MONO, size=12, bold=True, color=EMBER)),
    (" 와 ", dict(size=12.5, color=INK)),
    ("GRANT", dict(name=MONO, size=12, bold=True, color=EMBER)),
    (" 를 반복합니다. 이력 테이블은 프로그램이 날짜별로 자동 생성합니다.",
     dict(size=12.5, color=INK)),
]:
    r = p.add_run()
    r.text = txt
    font_of(r, **fkw)
page_num(s, 8)

# =================================================================== 9 설치 4
s = slide_light(prs)
title_bar(s, "08  INSTALL  STEP 4", "프로젝트 배치와 otg_monitoring.ini")

steps = [
    ("프로젝트 폴더를 배치", "D:\\MultiModal_FireCam\\ 아래에 source, predict_machine, fall_detection, users 를 둡니다."),
    ("DLL 을 함께 둡니다", "libmysql.dll, libcrypto-3-x64.dll, libssl-3-x64.dll 을 exe 와 같은 폴더에 둡니다."),
    ("otg_monitoring.ini 작성", "exe 와 같은 폴더에 둡니다. 이 파일이 없으면 exe 가 있는 폴더를 기준으로 동작합니다."),
]
y = 1.88
for i, (head, body) in enumerate(steps):
    circle(s, M, y, 0.44, EMBER, str(i + 1), WHITE, 14)
    tf = textbox(s, M + 0.66, y + 0.02, 6.6, 0.3)
    write(tf, [(head, dict(size=14.5, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, M + 0.66, y + 0.36, 6.6, 0.5)
    write(tf, [(body, dict(size=11.5, color=MUTED), dict(space_after=0, line=1.2))])
    y += 1.0

code_block(s, M, 5.0, 7.3, [
    "; otg_monitoring.ini  (exe 와 같은 폴더)",
    "[PATHS]",
    "ROOT_PATH = D:\\MultiModal_FireCam\\",
    "",
    "[PYTHON]",
    "ANACONDA_ROOT = C:\\Users\\<계정>\\anaconda3\\",
    "ANACONDA_ENV  = mmc",
], size=11.5)

bx = M + 7.7
card(s, bx, 1.88, 3.91, 4.6, fill=PAPER)
tf = textbox(s, bx + 0.3, 2.14, 3.31, 0.3)
write(tf, [("읽는 순서", dict(size=14, bold=True, color=INK), dict(space_after=0))])
order = [
    ("1", "otg_monitoring.ini", "ROOT_PATH 를 먼저 정합니다.", EMBER),
    ("2", "users\\<user>\\env.ini", "ROOT_PATH 아래에서 찾습니다.", AMBER),
    ("3", "users\\<user>\\secrets.ini", "비밀번호만 따로 읽습니다.", TEAL),
]
y = 2.62
for num, name, desc, col in order:
    circle(s, bx + 0.3, y, 0.34, col, num, WHITE, 12)
    tf = textbox(s, bx + 0.76, y - 0.02, 2.85, 0.28)
    write(tf, [(name, dict(name=MONO, size=10.5, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, bx + 0.76, y + 0.3, 2.85, 0.5)
    write(tf, [(desc, dict(size=10.5, color=MUTED), dict(space_after=0, line=1.2))])
    y += 1.05

tf = textbox(s, bx + 0.3, 5.86, 3.31, 0.5)
write(tf, [("ROOT_PATH 가 잘못되면 env.ini 를 찾지 못했다는 메시지와 함께 프로그램이 즉시 종료됩니다.",
            dict(size=10.5, color=EMBER), dict(space_after=0, line=1.2))])
page_num(s, 9)

# =================================================================== 10 설치 5
s = slide_light(prs)
title_bar(s, "09  INSTALL  STEP 5", "비밀번호 분리 — secrets.ini")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("DB 비밀번호는 env.ini 에 두지 않습니다. 저장소에 올라가지 않도록 별도 파일로 분리했습니다.",
            dict(size=14, color=MUTED), dict(space_after=0))])

code_block(s, M, 2.26, 7.3, [
    "# 견본을 복사해 현장 폴더에 만듭니다",
    "$ copy users\\secrets.ini.sample users\\kict1\\secrets.ini",
    "$ copy users\\secrets.ini.sample users\\cj_busan_1\\secrets.ini",
    "",
    "; users\\kict1\\secrets.ini",
    "[DB_ADMIN]",
    "DB_ADMIN_PASSWORD = <root 비밀번호>",
    "",
    "[DB_RUNTIME]",
    "DB_PASSWORD = <otg_user 비밀번호>",
], size=11.5)

bx = M + 7.7
card(s, bx, 2.26, 3.91, 1.86, fill=PAPER)
tf = textbox(s, bx + 0.3, 2.5, 3.31, 0.3)
write(tf, [("누가 읽는가", dict(size=13, bold=True, color=INK), dict(space_after=0))])
tf = textbox(s, bx + 0.3, 2.88, 3.31, 1.0)
write(tf, [("파이썬은 env.ini 와 secrets.ini 를 이어서 읽어 하나로 합칩니다. "
            "C++ 은 비밀번호만 secrets.ini 에서 읽습니다.",
            dict(size=11, color=MUTED), dict(space_after=0, line=1.25))])

card(s, bx, 4.3, 3.91, 2.2, fill=RGBColor(0xFD, 0xEC, 0xEA))
circle(s, bx + 0.3, 4.56, 0.38, EMBER, "!", WHITE, 15)
tf = textbox(s, bx + 0.78, 4.58, 2.8, 0.3)
write(tf, [("빠뜨리면 즉시 중단됩니다", dict(size=12.5, bold=True, color=EMBER), dict(space_after=0))])
tf = textbox(s, bx + 0.3, 5.06, 3.31, 1.1)
write(tf, [("secrets.ini 가 없으면 파일 경로와 함께 오류가 표시되고 프로그램이 멈춥니다. "
            "조용히 잘못 동작하지 않으므로 원인 파악이 쉽습니다.",
            dict(size=11, color=INK), dict(space_after=0, line=1.25))])
page_num(s, 10)

# =================================================================== 11 빌드 · 실행
s = slide_light(prs)
title_bar(s, "10  BUILD & RUN", "빌드와 실행")

tf = textbox(s, M, 1.78, 5.6, 0.32)
write(tf, [("감시 프로그램 빌드", dict(size=15, bold=True, color=INK), dict(space_after=0))])
code_block(s, M, 2.16, 5.6, [
    "# Visual Studio 에서 열기",
    "otg_monitoring\\otg_monitoring.sln",
    "",
    "# 구성 선택 후 빌드",
    "Release  |  x64",
    "",
    "# 산출물",
    "D:\\MultiModal_FireCam\\otg_monitoring.exe",
], size=11.5)

tf = textbox(s, M, 5.12, 5.6, 0.32)
write(tf, [("개별 실행 (문제 확인용)", dict(size=15, bold=True, color=INK), dict(space_after=0))])
code_block(s, M, 5.5, 5.6, [
    "$ conda activate mmc",
    "$ cd /d D:\\MultiModal_FireCam",
    "$ python source\\server_to_db.py \"kict1\"",
], size=11.5)

bx = M + 6.0
tf = textbox(s, bx, 1.78, 5.6, 0.32)
write(tf, [("정상 동작 확인 순서", dict(size=15, bold=True, color=INK), dict(space_after=0))])
checks = [
    ("프로그램 실행", "제목표시줄에 웹캠 아이콘이 보입니다."),
    ("user 선택", "콤보박스에서 현장을 고릅니다. 해당 현장의 목록만 표시됩니다."),
    ("시작 버튼", "약 18초에 걸쳐 프로세스가 차례로 기동합니다."),
    ("상태 확인", "[3] processes  |  err=0000 이 표시되면 정상입니다."),
    ("로그 확인", "debug_logs 폴더에 프로세스별 로그가 쌓입니다."),
]
y = 2.2
for i, (head, body) in enumerate(checks):
    circle(s, bx, y, 0.36, TEAL, str(i + 1), WHITE, 12)
    tf = textbox(s, bx + 0.52, y - 0.01, 5.1, 0.28)
    write(tf, [(head, dict(size=13, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, bx + 0.52, y + 0.3, 5.1, 0.5)
    write(tf, [(body, dict(size=11, color=MUTED), dict(space_after=0, line=1.2))])
    y += 0.92
page_num(s, 11)

# =================================================================== 12 화면 사용법
s = slide_light(prs)
title_bar(s, "11  OPERATION", "화면 사용법")

btns = [
    ("시작", "두 현장의 프로세스 6개를 차례로 기동합니다. 기동 중에는 다시 눌러도 무시됩니다.", EMBER),
    ("정지", "기동한 프로세스를 모두 종료합니다.", AMBER),
    ("설정", "격자 마스크 등 현장 설정 창을 엽니다.", TEAL),
    ("폴더", "debug_logs 폴더를 탐색기로 엽니다.", RGBColor(0x6A, 0x5A, 0xCD)),
    ("목록", "하단 프로세스 목록을 펼칩니다. 펼치면 문구가 접기 로 바뀝니다.", RGBColor(0x2F, 0x6F, 0xED)),
    ("X", "프로그램을 종료합니다. 감시 중이면 확인을 한 번 묻습니다.", RGBColor(0xB4, 0x23, 0x18)),
]
cw2, gp2 = 3.86, 0.26
for i, (name, desc, col) in enumerate(btns):
    x = M + (i % 3) * (cw2 + gp2)
    y = 1.9 + (i // 3) * 1.66
    card(s, x, y, cw2, 1.46, fill=PAPER)
    bt = card(s, x + 0.26, y + 0.28, 0.92, 0.46, fill=col, radius=0.22)
    tfb = bt.text_frame
    tfb.margin_left = tfb.margin_right = tfb.margin_top = tfb.margin_bottom = 0
    tfb.vertical_anchor = MSO_ANCHOR.MIDDLE
    pb = tfb.paragraphs[0]
    pb.alignment = PP_ALIGN.CENTER
    rb = pb.add_run()
    rb.text = name
    font_of(rb, KR, 13, True, WHITE)
    tf = textbox(s, x + 1.34, y + 0.26, cw2 - 1.6, 1.0)
    write(tf, [(desc, dict(size=11.5, color=MUTED), dict(space_after=0, line=1.25))])

card(s, M, 5.42, W - 2 * M, 1.0, fill=PAPER)
tf = textbox(s, M + 0.34, 5.64, W - 2 * M - 0.68, 0.6)
write(tf, [("선택한 현장의 목록과 이미지 뷰어만 화면에 표시됩니다. "
            "콤보박스에서 현장을 바꾸면 목록도 이미지 창도 함께 교체됩니다.",
            dict(size=12.5, color=INK), dict(space_after=0, line=1.25))])
page_num(s, 12)

# =================================================================== 13 학습 파이프라인
s = slide_light(prs)
title_bar(s, "12  TRAINING PIPELINE", "모델은 어디서 만들어지는가")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("운영 시스템이 쓰는 모델은 별도 폴더 D:\\autoencoder 에서 만듭니다. conda 환경도 otg 로 다릅니다.",
            dict(size=14, color=MUTED), dict(space_after=0))])

pipe = [
    ("download_ir_raw.py", "서버 → ir_raw", "현장 서버에서 raw 파일을 내려받습니다."),
    ("conv_raw.py", "ir_raw → step_0", "raw 값을 온도 값으로 변환합니다."),
    ("gen-samples.py", "step_0 → step_1", "160x120 을 64개 격자 값으로 축약합니다."),
    ("apply_median.py", "step_1 → step_2", "median 필터로 노이즈를 제거합니다."),
    ("apply_mask_extract.py", "step_2 → step_3", "mach_area_mask.ini 의 설비 영역만 추출합니다."),
    ("autoencoder-7.py", "step_3 → saved_models", "오토인코더를 학습해 모델을 저장합니다."),
]
y = 2.3
for i, (name, io, desc) in enumerate(pipe):
    circle(s, M, y, 0.36, EMBER if i < 5 else TEAL, str(i + 1), WHITE, 12)
    tf = textbox(s, M + 0.52, y - 0.02, 2.5, 0.28)
    write(tf, [(name, dict(name=MONO, size=11.5, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, M + 3.1, y - 0.01, 2.35, 0.28)
    write(tf, [(io, dict(name=MONO, size=10, color=EMBER if i < 5 else TEAL), dict(space_after=0))])
    tf = textbox(s, M + 0.52, y + 0.3, 6.6, 0.28)
    write(tf, [(desc, dict(size=11, color=MUTED), dict(space_after=0))])
    y += 0.7

bx = M + 7.7
tf = textbox(s, bx, 2.24, 3.91, 0.3)
write(tf, [("한 번에 실행", dict(size=14, bold=True, color=INK), dict(space_after=0))])
code_block(s, bx, 2.62, 3.91, [
    "$ conda activate otg",
    "$ cd /d D:\\autoencoder",
    "$ run_pipeline.bat kict1",
], size=11)

card(s, bx, 4.34, 3.91, 2.18, fill=PAPER)
tf = textbox(s, bx + 0.28, 4.56, 3.35, 0.3)
write(tf, [("현장별 데이터 폴더", dict(size=13, bold=True, color=INK), dict(space_after=0))])
tf = textbox(s, bx + 0.28, 4.96, 3.35, 1.4)
write(tf, [("D:\\autoencoder\\<user>\\", dict(name=MONO, size=10, color=INK), dict(space_after=5)),
           ("  ir_raw  raw", dict(name=MONO, size=10, color=MUTED), dict(space_after=3)),
           ("  step_0  step_1  step_2  step_3", dict(name=MONO, size=10, color=MUTED), dict(space_after=3)),
           ("  saved_models", dict(name=MONO, size=10, color=TEAL), dict(space_after=0))])
page_num(s, 13)

# =================================================================== 14 학습과 운영
s = slide_light(prs)
title_bar(s, "13  HANDOVER", "학습과 운영의 관계")

lw = 4.7
card(s, M, 1.9, lw, 2.9, fill=PAPER)
circle(s, M + 0.3, 2.18, 0.46, EMBER, "학습", WHITE, 11)
tf = textbox(s, M + 0.9, 2.24, 3.5, 0.3)
write(tf, [("D:\\autoencoder", dict(name=MONO, size=13, bold=True, color=INK), dict(space_after=0))])
tf = textbox(s, M + 0.3, 2.86, lw - 0.6, 1.8)
write(tf, [("conda 환경 : otg  (numpy 2.x)", dict(size=11.5, color=MUTED), dict(space_after=7)),
           ("6단계 파이프라인으로 모델을 만듭니다.", dict(size=11.5, color=MUTED), dict(space_after=7)),
           ("산출물은 saved_models 에 쌓입니다.", dict(size=11.5, color=MUTED), dict(space_after=7)),
           ("프로젝트 폴더 밖이라 git 추적 대상이 아닙니다.", dict(size=11.5, color=EMBER), dict(space_after=0, line=1.2))])

rx = M + lw + 2.5
card(s, rx, 1.9, lw, 2.9, fill=PAPER)
circle(s, rx + 0.3, 2.18, 0.46, TEAL, "운영", WHITE, 11)
tf = textbox(s, rx + 0.9, 2.24, 3.5, 0.3)
write(tf, [("D:\\MultiModal_FireCam", dict(name=MONO, size=13, bold=True, color=INK), dict(space_after=0))])
tf = textbox(s, rx + 0.3, 2.86, lw - 0.6, 1.8)
write(tf, [("conda 환경 : mmc  (numpy 1.x)", dict(size=11.5, color=MUTED), dict(space_after=7)),
           ("predict_machine.py 가 모델을 읽습니다.", dict(size=11.5, color=MUTED), dict(space_after=7)),
           ("users\\<user>\\ 에 모델을 둡니다.", dict(size=11.5, color=MUTED), dict(space_after=7)),
           ("git 으로 백업됩니다.", dict(size=11.5, color=TEAL), dict(space_after=0, line=1.2))])

ar = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW,
                        Inches(M + lw + 0.42), Inches(3.14), Inches(1.66), Inches(0.42))
ar.fill.solid()
ar.fill.fore_color.rgb = AMBER
ar.line.fill.background()
ar.shadow.inherit = False
tf = textbox(s, M + lw + 0.2, 2.62, 2.1, 0.5, align=PP_ALIGN.CENTER)
write(tf, [("복사", dict(size=12, bold=True, color=INK), dict(space_after=2)),
           ("scaler.pkl", dict(name=MONO, size=9, color=MUTED), dict(space_after=0))])
tf = textbox(s, M + lw + 0.2, 3.66, 2.1, 0.3, align=PP_ALIGN.CENTER)
write(tf, [("autoencoder_final.pth", dict(name=MONO, size=8.5, color=MUTED), dict(space_after=0))])

cautions = [
    ("같은 회차의 짝을 유지", "scaler 와 autoencoder 는 한 번의 학습에서 함께 나온 것이어야 합니다. "
     "따로 복사하면 점수가 조용히 틀어집니다."),
    ("numpy 버전 차이", "otg(2.x)에서 만든 scaler.pkl 은 mmc(1.x)에서 읽히지 않아, "
     "같은 폴더의 scaler.npz 로 대체합니다."),
    ("학습 폴더도 백업", "D:\\autoencoder 는 프로젝트 밖이라 백업에서 빠지기 쉽습니다. "
     "스크립트만이라도 보관하십시오."),
]
cw3 = 3.86
for i, (head, body) in enumerate(cautions):
    x = M + i * (cw3 + 0.26)
    card(s, x, 5.06, cw3, 1.56, fill=RGBColor(0xFD, 0xF1, 0xEC))
    circle(s, x + 0.26, 5.3, 0.34, EMBER, "!", WHITE, 12)
    tf = textbox(s, x + 0.72, 5.32, 2.9, 0.3)
    write(tf, [(head, dict(size=12.5, bold=True, color=EMBER), dict(space_after=0))])
    tf = textbox(s, x + 0.26, 5.76, cw3 - 0.52, 0.75)
    write(tf, [(body, dict(size=10.5, color=INK), dict(space_after=0, line=1.2))])
page_num(s, 14)

# =================================================================== 15 문제 해결
s = slide_dark(prs)
title_bar(s, "14  TROUBLESHOOTING", "자주 겪는 문제", dark=True)

probs = [
    ("점수가 계속 같은 값", "현장 서버의 파일이 갱신되지 않는 경우입니다.",
     "debug_logs 의 ts 값을 확인하십시오. 며칠 전 날짜라면 현장 장비의 업로드를 점검합니다."),
    ("db_utils 임포트 오류", "PyPI 의 동명 패키지가 대신 잡힌 경우입니다.",
     "pip uninstall db_utils 로 제거하고, ROOT_PATH 가 올바른지 확인합니다."),
    ("env.ini 를 찾을 수 없음", "otg_monitoring.ini 의 ROOT_PATH 가 잘못된 경우입니다.",
     "메시지에 표시된 경로와 실제 폴더를 대조합니다."),
    ("프로세스가 6개보다 적음", "특정 스크립트만 기동 직후 종료된 경우입니다.",
     "debug_logs 에서 해당 프로세스 로그의 마지막 줄을 확인합니다."),
]
y = 1.95
for i, (title, cause, fix) in enumerate(probs):
    card(s, M, y, W - 2 * M, 1.14, fill=NAVY_SOFT)
    circle(s, M + 0.3, y + 0.34, 0.44, EMBER, str(i + 1), WHITE, 14)
    tf = textbox(s, M + 0.94, y + 0.2, 3.5, 0.3)
    write(tf, [(title, dict(size=14, bold=True, color=WHITE), dict(space_after=0))])
    tf = textbox(s, M + 0.94, y + 0.58, 3.5, 0.4)
    write(tf, [(cause, dict(size=10.5, color=AMBER), dict(space_after=0, line=1.15))])
    tf = textbox(s, M + 4.7, y + 0.32, 6.9, 0.6)
    write(tf, [(fix, dict(size=12, color=RGBColor(0xC8, 0xD3, 0xE3)), dict(space_after=0, line=1.25))])
    y += 1.26
page_num(s, 15, dark=True)

# =================================================================== 14 체크리스트
s = slide_light(prs)
title_bar(s, "15  CHECKLIST", "설치 점검표")

left = [
    "Visual Studio (MFC 포함) 설치",
    "MySQL 8.0 Server 설치 및 root 비밀번호 확보",
    "Anaconda 설치, conda -V 확인",
    "conda 환경 mmc 생성 (python 3.9)",
    "패키지 설치 완료 (db_utils 는 제외)",
    "현장별 데이터베이스 · otg_user 계정 생성",
]
right = [
    "프로젝트 폴더 배치 및 DLL 3개 복사",
    "otg_monitoring.ini 작성 (ROOT_PATH · ANACONDA)",
    "users\\<user>\\env.ini 배치",
    "users\\<user>\\secrets.ini 작성",
    "scaler · autoencoder 복사 (D:\\autoencoder 에서)",
    "Release x64 빌드 후 시작 버튼으로 6개 기동 확인",
]
for col_i, items in enumerate([left, right]):
    x = M + col_i * 6.1
    y = 1.95
    for it in items:
        bx2 = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE,
                                 Inches(x), Inches(y), Inches(0.3), Inches(0.3))
        bx2.adjustments[0] = 0.18
        bx2.fill.solid()
        bx2.fill.fore_color.rgb = WHITE
        bx2.line.color.rgb = RGBColor(0xC3, 0xCC, 0xD9)
        bx2.line.width = Pt(1.25)
        bx2.shadow.inherit = False
        tf = textbox(s, x + 0.48, y - 0.01, 5.2, 0.55)
        write(tf, [(it, dict(size=12.5, color=INK), dict(space_after=0, line=1.2))])
        y += 0.7

card(s, M, 6.2, W - 2 * M, 0.6, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, M + 0.34, 6.36, W - 2 * M - 0.68, 0.32)
write(tf, [("모두 완료되면 상태줄에 [3] processes | err=0000 이 표시됩니다.",
            dict(size=12.5, bold=True, color=TEAL), dict(space_after=0))])
page_num(s, 16)

out = r"D:\MultiModal_FireCam\멀티모달_화재감지_모니터링_설치매뉴얼.pptx"
prs.save(out)
print("저장 완료:", out)
print("슬라이드 수:", len(prs.slides.__iter__.__self__._sldIdLst))
