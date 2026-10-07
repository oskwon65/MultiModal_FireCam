# -*- coding: utf-8 -*-
"""멀티모달 화재감지 모니터링 시스템 - 설치/구성 매뉴얼 PPTX 생성"""

from docs_style import *   # 팔레트 · 글꼴 · 상자 · 카드 · 제목줄

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
page_num(s, 1)

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

cw2 = (W - 2 * M - 0.3) / 2

card(s, M, 5.22, cw2, 1.5, fill=RGBColor(0xFD, 0xF1, 0xEC))
tf = textbox(s, M + 0.3, 5.42, cw2 - 0.6, 1.1)
write(tf, [("수집 주기는 현장마다 다릅니다", dict(size=12.5, bold=True, color=EMBER),
            dict(space_after=5)),
           ("서버의 파일이 갱신되지 않으면 같은 값이 반복 입력되어 점수가 고정됩니다. "
            "센서 타임스탬프(ts)가 최신인지 debug_logs 에서 확인하십시오.",
            dict(size=11, color=INK), dict(space_after=0, line=1.25))], first=False)

# 데이터가 어디까지 가는지 명시한다. 그림만 보면 분석 결과도 서버로
# 돌아가는 것처럼 오해하기 쉽고, 실제로 SMS 만 밖으로 나간다.
rx2 = M + cw2 + 0.3
card(s, rx2, 5.22, cw2, 1.5, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, rx2 + 0.3, 5.42, cw2 - 0.6, 1.1)
write(tf, [("분석 결과는 서버로 올라가지 않습니다", dict(size=12.5, bold=True, color=TEAL),
            dict(space_after=5)),
           ("점수와 판정 이력은 이 PC 의 MySQL 에만 쌓입니다. 밖으로 나가는 것은 화재 감지 "
            "시의 SMS 발송뿐입니다. 서버에는 raw 원본이 남으므로 PC 이력이 사라져도 "
            "재분석은 가능합니다.",
            dict(size=11, color=INK), dict(space_after=0, line=1.25))], first=False)
page_num(s, 2)

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
    "    env.ini        현장 설정 (DB · 네트워크 · 격자)",
    "    continual_learning.ini      연속학습 설정 (임계값 · 단계 · 기여도 · 표본)",
    "    db_secrets.ini    DB 비밀번호  (git 제외)",
    "    scaler.pkl / scaler.npz / autoencoder_final.pth",
    "",
    "  debug_logs\\                    실행 로그 (프로세스별)",
    "  otg_monitoring\\                C++ 소스 · Visual Studio 프로젝트",
]
code_block(s, M, 1.78, 7.55, tree, size=11)

bx = M + 7.95
notes = [
    ("ROOT_PATH 가 기준점", "모든 경로는 이 폴더를 기준으로 계산됩니다. exe 와 데이터가 같은 폴더에 놓입니다.", EMBER),
    ("user 별 폴더 분리", "현장을 추가하려면 users 아래에 폴더를 만들고 env.ini · continual_learning.ini · db_secrets.ini 를 넣습니다.", AMBER),
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
page_num(s, 3)

# =================================================================== 5 설정 파일
s = slide_light(prs)
title_bar(s, "04  CONFIGURATION", "설정 파일 네 가지")

tf = textbox(s, M, 1.68, 11.5, 0.35)
write(tf, [("장비 고유 · 현장 고유 · 운영 중 조정 · 비밀 정보를 나눴습니다. "
            "읽는 순서가 정해져 있습니다.",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

cfgs = [
    ("otg_monitoring.ini", "exe 와 같은 폴더", EMBER, "장비(PC) 고유",
     ["[PATHS] ROOT_PATH = D:\\MultiModal_FireCam\\",
      "[PYTHON] ANACONDA_ROOT = C:\\Users\\<계정>\\anaconda3\\",
      "[PYTHON] ANACONDA_ENV = mmc"],
     "가장 먼저 읽습니다. ROOT_PATH 가 env.ini 의 위치를 결정하기 때문입니다."),
    ("users\\<user>\\env.ini", "현장 폴더", AMBER, "설치할 때 정함",
     ["[NETWORK] ROOT_URL · MONITOR_SEAT_ORDER",
      "[DB_RUNTIME] DB_HOST · DB_USER · DB_NAME_SENSOR",
      "[CONSTANTS] 격자 크기 · 카메라 해상도"],
     "한 번 정하면 거의 바꾸지 않는 값입니다."),
    ("users\\<user>\\continual_learning.ini", "현장 폴더", TEAL, "운영 중 조정",
     ["[CONSTANTS] 절대 임계값 · 단계 전환 조건",
      "[CONSTANTS] 기여도 판단 · 학습 표본"],
     "[설정] 창이 읽고 씁니다. env.ini 뒤에 읽어 같은 열쇠면 이깁니다."),
    ("users\\<user>\\db_secrets.ini", "현장 폴더", EMBER, "비밀 정보",
     ["[DB_RUNTIME] DB_PASSWORD = ...",
      "[DB_ADMIN] DB_ADMIN_PASSWORD = ..."],
     "git 추적 제외. users\\db_secrets.ini.sample 을 복사해 만듭니다."),
]
# 넷이 들어가야 한다. 쪽 번호가 6.88 이므로 7.06 에서 끝나도 겹치지 않는다
# (번호는 오른쪽 끝에 있고 카드 글은 왼쪽 절반에만 있다).
y = 2.06
for name, where, col, kind, keys, note in cfgs:
    hh = 1.16
    card(s, M, y, W - 2 * M, hh, fill=PAPER)
    circle(s, M + 0.3, y + 0.26, 0.42, col)
    tf = textbox(s, M + 0.92, y + 0.22, 4.2, 0.3)
    write(tf, [(name, dict(name=MONO, size=13, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, M + 0.92, y + 0.56, 4.2, 0.26)
    write(tf, [(kind + "  ·  " + where, dict(size=10, color=col), dict(space_after=0))])
    tf = textbox(s, M + 5.35, y + 0.20, 4.6, 0.76)
    write(tf, [(k, dict(name=MONO, size=9.5, color=MUTED), dict(space_after=3, line=1.1)) for k in keys])
    tf = textbox(s, M + 0.92, y + 0.82, 4.3, 0.32)
    write(tf, [(note, dict(size=10, color=MUTED), dict(space_after=0, line=1.15))])
    y += hh + 0.12
page_num(s, 4)

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
page_num(s, 5)

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
page_num(s, 6)

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
page_num(s, 7)

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
    ("3", "users\\<user>\\db_secrets.ini", "비밀번호만 따로 읽습니다.", TEAL),
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
page_num(s, 8)

# =================================================================== 10 설치 5
s = slide_light(prs)
title_bar(s, "09  INSTALL  STEP 5", "비밀번호 분리 — db_secrets.ini")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("DB 비밀번호는 env.ini 에 두지 않습니다. 저장소에 올라가지 않도록 별도 파일로 분리했습니다.",
            dict(size=14, color=MUTED), dict(space_after=0))])

code_block(s, M, 2.26, 7.3, [
    "# 견본을 복사해 현장 폴더에 만듭니다",
    "$ copy users\\db_secrets.ini.sample users\\kict1\\db_secrets.ini",
    "$ copy users\\db_secrets.ini.sample users\\cj_busan_1\\db_secrets.ini",
    "",
    "; users\\kict1\\db_secrets.ini",
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
write(tf, [("파이썬은 env.ini 와 db_secrets.ini 를 이어서 읽어 하나로 합칩니다. "
            "C++ 은 비밀번호만 db_secrets.ini 에서 읽습니다.",
            dict(size=11, color=MUTED), dict(space_after=0, line=1.25))])

card(s, bx, 4.3, 3.91, 2.2, fill=RGBColor(0xFD, 0xEC, 0xEA))
circle(s, bx + 0.3, 4.56, 0.38, EMBER, "!", WHITE, 15)
tf = textbox(s, bx + 0.78, 4.58, 2.8, 0.3)
write(tf, [("빠뜨리면 즉시 중단됩니다", dict(size=12.5, bold=True, color=EMBER), dict(space_after=0))])
tf = textbox(s, bx + 0.3, 5.06, 3.31, 1.1)
write(tf, [("db_secrets.ini 가 없으면 파일 경로와 함께 오류가 표시되고 프로그램이 멈춥니다. "
            "조용히 잘못 동작하지 않으므로 원인 파악이 쉽습니다.",
            dict(size=11, color=INK), dict(space_after=0, line=1.25))])
page_num(s, 9)

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
page_num(s, 10)

# =================================================================== 12 화면 사용법
s = slide_light(prs)
title_bar(s, "11  OPERATION", "화면 사용법")

btns = [
    ("시작", "두 현장의 프로세스 6개를 차례로 기동합니다. 진행바가 뜨고, 이미지 뷰어가 "
             "올라오면 사라집니다. 기동 중에는 다시 눌러도 무시됩니다.", EMBER),
    ("정지", "기동한 프로세스를 모두 종료합니다.", AMBER),
    ("설정", "설정 영역을 펼칩니다. 목록과 같은 토글이라 펼친 채로 다른 버튼을 쓸 수 "
             "있습니다.", TEAL),
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
page_num(s, 11)

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
    ("autoencoder-7.py", "step_2 → saved_models", "마스크 적용 전인 64차원을 그대로 학습합니다."),
]
y = 2.42
for i, (name, io, desc) in enumerate(pipe):
    circle(s, M, y, 0.36, EMBER if i < 4 else TEAL, str(i + 1), WHITE, 12)
    tf = textbox(s, M + 0.52, y - 0.02, 2.5, 0.28)
    write(tf, [(name, dict(name=MONO, size=11.5, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, M + 3.1, y - 0.01, 2.35, 0.28)
    write(tf, [(io, dict(name=MONO, size=10, color=EMBER if i < 4 else TEAL), dict(space_after=0))])
    tf = textbox(s, M + 0.52, y + 0.3, 6.6, 0.28)
    write(tf, [(desc, dict(size=11, color=MUTED), dict(space_after=0))])
    y += 0.7

card(s, M, 6.02, 7.2, 0.76, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, M + 0.3, 6.18, 6.6, 0.48)
write(tf, [("예전 5단계였던 apply_mask_extract.py (step_2 → step_3) 는 제거했습니다. "
            "마스크는 학습이 아니라 채점에서만 쓰이기 때문입니다.",
            dict(size=11, color=TEAL), dict(space_after=0, line=1.25))])

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
           ("  step_0  step_1  step_2", dict(name=MONO, size=10, color=MUTED), dict(space_after=3)),
           ("  saved_models", dict(name=MONO, size=10, color=TEAL), dict(space_after=0))])
page_num(s, 12)

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
           ("5단계 파이프라인으로 모델을 만듭니다.", dict(size=11.5, color=MUTED), dict(space_after=7)),
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
page_num(s, 13)

# =================================================================== 15 학습 실행
s = slide_light(prs)
title_bar(s, "14  TRAINING RUN", "학습을 실행합니다")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("학습은 운영과 분리된 D:\\autoencoder 에서 conda 환경 otg 로 실행합니다. 현장 이름을 인자로 넘깁니다.",
            dict(size=14, color=MUTED), dict(space_after=0))])

lw2 = 7.0
tf = textbox(s, M, 2.24, lw2, 0.3)
write(tf, [("실행 절차", dict(size=14, bold=True, color=INK), dict(space_after=0))])
code_block(s, M, 2.62, lw2, [
    "# 1. 학습 환경으로 전환",
    "$ conda activate otg",
    "$ cd /d D:\\autoencoder",
    "",
    "# 2. 5단계를 한 번에 실행",
    "$ run_pipeline.bat kict1",
    "",
    "# 단계별 실행 (필요할 때만)",
    "$ python download_ir_raw.py kict1",
    "$ python conv_raw.py kict1",
    "$ python gen-samples.py kict1",
    "$ python apply_median.py kict1",
    "$ python autoencoder-7.py kict1",
], size=11)

card(s, M, 6.2, lw2, 0.58, fill=PAPER)
tf = textbox(s, M + 0.28, 6.36, lw2 - 0.56, 0.3)
write(tf, [("주요 설정값  ·  입력 64 · 잠재 16 · 배치 512 · 600 epoch · Adam lr 1e-4",
            dict(size=11, color=MUTED), dict(space_after=0))])

rx2 = M + lw2 + 0.32
rw2 = 4.57

card(s, rx2, 2.24, rw2, 1.92, fill=PAPER)
tf = textbox(s, rx2 + 0.28, 2.44, rw2 - 0.56, 0.3)
write(tf, [("실제 학습 규모", dict(size=13, bold=True, color=INK), dict(space_after=0))])
sites = [
    ("kict1", "2025-08-27 ~ 2026-02-10", "167,677"),
    ("cj_busan_1", "2026-01-06 ~ 2026-07-04", "954,601"),
]
yy = 2.84
for nm, period, cnt in sites:
    tf = textbox(s, rx2 + 0.28, yy, 2.2, 0.28)
    write(tf, [(nm, dict(name=MONO, size=11, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, rx2 + 0.28, yy + 0.28, 3.0, 0.26)
    write(tf, [(period, dict(size=9.5, color=MUTED), dict(space_after=0))])
    tf = textbox(s, rx2 + rw2 - 1.7, yy + 0.04, 1.42, 0.28, align=PP_ALIGN.RIGHT)
    write(tf, [(cnt, dict(name=MONO, size=12, bold=True, color=EMBER), dict(space_after=0))])
    yy += 0.62

card(s, rx2, 4.3, rw2, 2.43, fill=PAPER)
tf = textbox(s, rx2 + 0.28, 4.5, rw2 - 0.56, 0.3)
write(tf, [("산출물", dict(size=13, bold=True, color=INK), dict(space_after=0))])
tf = textbox(s, rx2 + 0.28, 4.88, rw2 - 0.56, 1.3)
write(tf, [("<user>\\saved_models\\", dict(name=MONO, size=10, color=INK), dict(space_after=5)),
           ("  autoencoder_final.pth", dict(name=MONO, size=10, color=TEAL), dict(space_after=3)),
           ("  scaler.pkl   scaler.npz", dict(name=MONO, size=10, color=TEAL), dict(space_after=3)),
           ("  autoencoder_epoch_N.pth", dict(name=MONO, size=10, color=MUTED), dict(space_after=3)),
           ("  training_log.csv", dict(name=MONO, size=10, color=MUTED), dict(space_after=0))])
tf = textbox(s, rx2 + 0.28, 6.18, rw2 - 0.56, 0.44)
write(tf, [("scaler.npz 는 학습이 자동으로 함께 만듭니다. 운영 환경의 numpy 1.x 대비용입니다.",
            dict(size=10, color=EMBER), dict(space_after=0, line=1.2))])
page_num(s, 14)

# =================================================================== 16 모델과 점수
s = slide_light(prs)
title_bar(s, "15  MODEL", "모델 구조와 점수 계산")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("정상 상태만 학습시켜, 처음 보는 열 분포는 복원에 실패하도록 만드는 방식입니다.",
            dict(size=14, color=MUTED), dict(space_after=0))])

dims = ["64", "32", "16", "32", "64"]
bw, gap = 1.5, 0.62
total = len(dims) * bw + (len(dims) - 1) * gap
sx = (W - total) / 2
for i, d in enumerate(dims):
    x = sx + i * (bw + gap)
    is_mid = (i == 2)
    card(s, x, 2.34, bw, 0.82, fill=EMBER if is_mid else PAPER)
    tf = textbox(s, x, 2.56, bw, 0.4, align=PP_ALIGN.CENTER)
    write(tf, [(d, dict(size=19, bold=True, color=WHITE if is_mid else INK), dict(space_after=0))])
    if i < len(dims) - 1:
        ar2 = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW,
                                 Inches(x + bw + 0.1), Inches(2.63), Inches(0.42), Inches(0.24))
        ar2.fill.solid()
        ar2.fill.fore_color.rgb = AMBER
        ar2.line.fill.background()
        ar2.shadow.inherit = False
tf = textbox(s, M, 3.28, 11.89, 0.3, align=PP_ALIGN.CENTER)
write(tf, [("인코더가 64개 값을 16개로 압축하고, 디코더가 다시 64개로 되돌립니다.",
            dict(size=11.5, color=MUTED), dict(space_after=0))])

lw3 = 5.78
tf = textbox(s, M, 3.84, lw3, 0.3)
write(tf, [("정확한 계층 구성", dict(size=13, bold=True, color=INK), dict(space_after=0))])
code_block(s, M, 4.2, lw3, [
    "encoder : 64 -> 32 -> 16 -> 16",
    "decoder : 16 -> 16 -> 32 -> 64",
    "활성함수 : ReLU (마지막 층 제외)",
], size=11)

rx3 = M + lw3 + 0.33
tf = textbox(s, rx3, 3.84, lw3, 0.3)
write(tf, [("점수 계산", dict(size=13, bold=True, color=INK), dict(space_after=0))])
code_block(s, rx3, 4.2, lw3, [
    "mse   = 마스크 16셀의 재구성 오차 평균",
    "score = exp(-mse * 10)",
    "# 1.0 에 가까울수록 정상, 0 에 가까울수록 이상",
], size=11)

card(s, M, 5.44, W - 2 * M, 1.3, fill=RGBColor(0xEC, 0xF6, 0xF4))
circle(s, M + 0.3, 5.68, 0.38, TEAL, "✓", WHITE, 14)
tf = textbox(s, M + 0.82, 5.68, 10.6, 0.3)
write(tf, [("마스크는 학습에 쓰이지 않습니다 — 가변 패턴 방식",
            dict(size=13.5, bold=True, color=TEAL), dict(space_after=0))])
tf = textbox(s, M + 0.82, 6.08, 10.6, 0.56)
write(tf, [("학습은 64셀 전부를 그대로 씁니다. 마스크는 채점할 때 어느 셀의 오차를 평균낼지 고르는 데만 쓰입니다. "
            "따라서 16셀 지정을 바꾸더라도 hotlist_mask_local.ini 파일만 교체하면 되고, 재학습은 필요 없습니다.",
            dict(size=11.5, color=INK), dict(space_after=0, line=1.25))])
page_num(s, 15)

# =================================================================== 17 재학습 판단
s = slide_light(prs)
title_bar(s, "16  RETRAINING", "다시 학습해야 할 때")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("증상이 비슷해 보여도 원인이 다릅니다. 재학습이 답이 아닌 경우를 먼저 가려내십시오.",
            dict(size=14, color=MUTED), dict(space_after=0))])

cw4 = 5.78
need = [
    "설비를 교체하거나 공정이 바뀌어 열 분포 자체가 달라진 경우",
    "학습 구간에 없던 계절·환경 조건이 생긴 경우",
    "오탐 또는 미탐이 눈에 띄게 누적되는 경우",
]
noneed = [
    "마스크 16셀만 바꾼 경우 — 파일 교체로 즉시 반영됩니다",
    "카메라 조준이 틀어진 경우 — 원위치 복원이 정답입니다",
    "현장 데이터가 끊긴 경우 — 장비 점검이 먼저입니다",
]
for col_i, (head, items, col, bg) in enumerate([
        ("재학습이 필요합니다", need, EMBER, RGBColor(0xFD, 0xF1, 0xEC)),
        ("재학습이 필요 없습니다", noneed, TEAL, RGBColor(0xEC, 0xF6, 0xF4))]):
    x = M + col_i * (cw4 + 0.33)
    card(s, x, 2.24, cw4, 2.5, fill=bg)
    tf = textbox(s, x + 0.3, 2.44, cw4 - 0.6, 0.3)
    write(tf, [(head, dict(size=13.5, bold=True, color=col), dict(space_after=0))])
    yy = 2.86
    for it in items:
        circle(s, x + 0.32, yy + 0.05, 0.16, col)
        tf = textbox(s, x + 0.64, yy - 0.04, cw4 - 1.0, 0.56)
        write(tf, [(it, dict(size=11.5, color=INK), dict(space_after=0, line=1.25))])
        yy += 0.58

card(s, M, 4.96, W - 2 * M, 1.78, fill=PAPER)
circle(s, M + 0.3, 5.2, 0.4, EMBER, "사례", WHITE, 10)
tf = textbox(s, M + 0.86, 5.22, 10.5, 0.3)
write(tf, [("kict1 — 2026-07-13, 점수가 0.003 까지 떨어졌지만 모델은 정상이었습니다",
            dict(size=13.5, bold=True, color=INK), dict(space_after=0))])
tf = textbox(s, M + 0.86, 5.64, 10.5, 0.96)
write(tf, [("설비와 무관하게 늘 뜨거운 고정 열점이 격자 (4,1) 에 있었는데, 13:48~13:56 사이 (3,4) 로 옮겨갔습니다. "
            "카메라가 위 1칸·오른쪽 3칸 밀린 것입니다. 마스크 16셀이 엉뚱한 곳을 보게 되어 점수가 떨어졌을 뿐, "
            "모델과 마스크 자체는 멀쩡했습니다.",
            dict(size=11.5, color=INK), dict(space_after=6, line=1.25)),
           ("점검 방법 — 학습 데이터 평균에서 주변보다 뚜렷이 뜨거운 셀을 기준점으로 정해 두고, "
            "그 셀이 계속 같은 자리인지만 보면 조준 이상을 바로 알 수 있습니다.",
            dict(size=11.5, bold=True, color=EMBER), dict(space_after=0, line=1.25))])
page_num(s, 16)

# =================================================================== 18 연속 학습 개요
s = slide_light(prs)
title_bar(s, "17  CONTINUAL LEARNING", "설치 당일부터 동작시키기")

tf = textbox(s, M, 1.72, 11.5, 0.6)
write(tf, [("예전에는 모델 파일이 없으면 프로그램이 종료되어, 새 현장은 수 주간 데이터를 모아 "
            "오토인코더를 만들기 전까지 감시 자체가 불가능했습니다. 이제는 준비된 만큼만 쓰고 "
            "계속 동작하며, 상위 단계가 준비되면 자동으로 올라갑니다.",
            dict(size=13.5, color=MUTED), dict(space_after=0, line=1.3))])

stages = [
    ("1", "절대 임계값", "설치 즉시", "학습 0건", EMBER,
     "고정된 온도·상승률 선. 학습 기반 판정이 모두 실패해도 이것만은 남습니다."),
    ("2", "경험 임계값", "약 하루 후", "표본 3,000건 + 18시간", AMBER,
     "셀마다 정상 범위를 누적해 그 선을 넘은 만큼 채점합니다."),
    ("3", "오토인코더", "수 일~수 주", "히스토리 DB", TEAL,
     "셀 사이의 결합 분포까지 봅니다. 2단계가 놓치는 조합 이상을 잡습니다."),
    # 0~2 는 '지금 무엇으로 채점할 수 있는가'(상태)이고 연속학습은 '모델을
    # 어떻게 갱신하는가'(활동)다. 성격이 달라 번호를 붙이지 않는다.
    ("", "연속학습", "지속", "감도 시험 통과 시", RGBColor(0x3D, 0x6B, 0xA8),
     "쌓인 데이터로 3단계 모델을 스스로 갱신하며, 검증을 통과해야만 교체됩니다."),
]

bw5 = 2.78
for i, (num, name, when, cond, col, desc) in enumerate(stages):
    x = M + i * (bw5 + 0.26)
    card(s, x, 2.62, bw5, 2.62, fill=PAPER)
    if num:
        circle(s, x + 0.26, 2.86, 0.52, col, num, WHITE, 17)
        tf = textbox(s, x + 0.9, 2.94, bw5 - 1.1, 0.3)
    else:
        tf = textbox(s, x + 0.26, 2.94, bw5 - 0.52, 0.3)
    write(tf, [(name, dict(size=14, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, x + 0.26, 3.54, bw5 - 0.52, 0.55)
    write(tf, [(when, dict(size=12.5, bold=True, color=col), dict(space_after=3)),
               (cond, dict(size=10, color=MUTED), dict(space_after=0))])
    tf = textbox(s, x + 0.26, 4.18, bw5 - 0.52, 0.95)
    write(tf, [(desc, dict(size=10.5, color=INK), dict(space_after=0, line=1.25))])

    if i < len(stages) - 1:
        ar3 = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW,
                                 Inches(x + bw5 + 0.02), Inches(3.82),
                                 Inches(0.2), Inches(0.2))
        ar3.fill.solid()
        ar3.fill.fore_color.rgb = RGBColor(0xC3, 0xCC, 0xD9)
        ar3.line.fill.background()
        ar3.shadow.inherit = False

card(s, M, 5.46, W - 2 * M, 1.28, fill=RGBColor(0xEC, 0xF6, 0xF4))
circle(s, M + 0.3, 5.7, 0.38, TEAL, "!", WHITE, 14)
tf = textbox(s, M + 0.82, 5.7, 10.6, 0.3)
write(tf, [("하위 단계는 상위 단계가 생겨도 계속 살아 있습니다",
            dict(size=13.5, bold=True, color=TEAL), dict(space_after=0))])
tf = textbox(s, M + 0.82, 6.1, 10.6, 0.55)
write(tf, [("오토인코더나 경험 임계값은 '이 현장의 평소'를 기준으로 판정하므로, 평소가 서서히 변하면 "
            "기준도 따라갑니다. 그 특성은 오탐을 줄이지만 서서히 커지는 위험을 놓칠 수 있다는 뜻이기도 "
            "합니다. 1단계의 고정선이 그 마지막 안전망입니다.",
            dict(size=11.5, color=INK), dict(space_after=0, line=1.25))])
page_num(s, 17)

# =================================================================== 19 1~2단계
s = slide_light(prs)
title_bar(s, "18  STAGE 1-2", "학습 전에도 감시한다")

lw6 = 5.78

# --- 1단계 ---
tf = textbox(s, M, 1.76, lw6, 0.3)
write(tf, [("1단계 · 절대 임계값", dict(size=14, bold=True, color=EMBER), dict(space_after=0))])
tf = textbox(s, M, 2.12, lw6, 0.5)
write(tf, [("격자 64칸의 최대 온도와 분당 상승률을 고정선과 비교합니다. "
            "학습이 전혀 없어도 동작합니다.",
            dict(size=11.5, color=MUTED), dict(space_after=0, line=1.25))])

card(s, M, 2.72, lw6, 1.72, fill=RGBColor(0xFD, 0xF1, 0xEC))
tf = textbox(s, M + 0.28, 2.9, lw6 - 0.56, 0.3)
write(tf, [("기본값을 두지 않습니다", dict(size=12.5, bold=True, color=EMBER),
            dict(space_after=0))])
tf = textbox(s, M + 0.28, 3.26, lw6 - 0.56, 1.05)
write(tf, [("설비마다 정상 온도가 전혀 다릅니다. 실측 결과입니다.",
            dict(size=10.5, color=INK), dict(space_after=5, line=1.2)),
           ("kict1          정상 가동 중 격자 최고가 197도까지",
            dict(name=MONO, size=9.5, color=INK), dict(space_after=3)),
           ("cj_busan_1     정상 가동의 99.05% 가 12도/분 초과",
            dict(name=MONO, size=9.5, color=INK), dict(space_after=5)),
           ("추측한 기본값은 쉬지 않고 경보를 울립니다. 미지정이면 "
            "1단계를 끄고 시작 시 경고합니다.",
            dict(size=10.5, color=EMBER), dict(space_after=0, line=1.2))])

code_block(s, M, 4.50, lw6, [
    "# users/<user>/continual_learning.ini  [CONSTANTS]",
    "ABS_TEMP_WARN = 172",
    "ABS_TEMP_ALARM = 187",
    "ABS_RISE_WARN = 90",
    "ABS_RISE_ALARM = 120",
], size=9.5)

# --- 2단계 ---
rx6 = M + lw6 + 0.33
tf = textbox(s, rx6, 1.76, lw6, 0.3)
write(tf, [("2단계 · 경험 임계값", dict(size=14, bold=True, color=AMBER), dict(space_after=0))])
tf = textbox(s, rx6, 2.12, lw6, 0.5)
write(tf, [("\"이 셀이 지금까지 이렇게 뜨거운 적이 있었는가\" 를 봅니다. "
            "평균에서 몇 σ 위인지가 아닙니다.",
            dict(size=11.5, color=MUTED), dict(space_after=0, line=1.25))])

card(s, rx6, 2.72, lw6, 1.72, fill=PAPER)
tf = textbox(s, rx6 + 0.28, 2.9, lw6 - 0.56, 0.3)
write(tf, [("셀별 256칸 히스토그램", dict(size=12.5, bold=True, color=INK),
            dict(space_after=0))])
tf = textbox(s, rx6 + 0.28, 3.26, lw6 - 0.56, 1.05)
write(tf, [("격자 온도가 0~255 정수라 근사가 아니라 정확한 상위 분위수를 얻습니다. "
            "64KB, 저장 시 12KB.",
            dict(size=10.5, color=INK), dict(space_after=5, line=1.2)),
           ("설비는 가동/정지로 분포가 둘로 갈립니다. 표준편차 기반 판정은 "
            "그 사이 거리까지 삼켜 둔해집니다. 분위수는 분포 모양과 무관합니다.",
            dict(size=10.5, color=MUTED), dict(space_after=0, line=1.2))])

tf = textbox(s, rx6, 4.50, lw6, 0.3)
write(tf, [("실측 검증 (kict1 데이터)", dict(size=12, bold=True, color=INK),
            dict(space_after=0))])
vals = [("정상 프레임 500장", "오탐 0.00%", TEAL),
        ("마스크 셀 +20도", "score 0.680", INK),
        ("마스크 셀 +40도", "score 0.227", INK),
        ("마스크 셀 +100도", "score 0.008", EMBER)]
yv = 4.90
for label, val, col in vals:
    tf = textbox(s, rx6 + 0.06, yv, 3.2, 0.28)
    write(tf, [(label, dict(size=10.5, color=MUTED), dict(space_after=0))])
    tf = textbox(s, rx6 + 3.3, yv, 2.4, 0.28, align=PP_ALIGN.RIGHT)
    write(tf, [(val, dict(name=MONO, size=10.5, bold=True, color=col),
                dict(space_after=0))])
    yv += 0.26

card(s, M, 5.98, W - 2 * M, 0.76, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, M + 0.3, 6.08, W - 2 * M - 0.6, 0.3)
write(tf, [("경험 임계값은 3단계 이후에도 은퇴하지 않습니다",
            dict(size=12.5, bold=True, color=TEAL), dict(space_after=0))])
tf = textbox(s, M + 0.3, 6.40, W - 2 * M - 0.6, 0.32)
write(tf, [("오토인코더가 준비되면 두 점수를 함께 내고 낮은 쪽을 씁니다. 한쪽만 이상이라 하면 "
            "불일치로 기록해 원인을 가리킵니다. 화면 이동 감시(정상 0.9998 / 이동 시 0.23)와 "
            "통계 누적도 계속됩니다.",
            dict(size=11, color=INK), dict(space_after=0, line=1.2))])
page_num(s, 18)

# =================================================================== 19-1 단계 조건
s = slide_light(prs)
title_bar(s, "19  STAGE CONDITIONS", "단계는 언제 서는가")

tf = textbox(s, M, 1.72, 11.6, 0.35)
write(tf, [("세 단계는 차례로 서고, 선 뒤에도 물러나지 않습니다. 조건은 모두 "
            "[설정] 창에서 바꿉니다.",
            dict(size=14, color=MUTED), dict(space_after=0))])

cw9, gap9 = 3.85, 0.29
cols = [
    ("1단계", "절대 임계값", EMBER, "설치 즉시 동작",
     [("서는 조건", "네 값을 모두 채우면 그 순간부터"),
      ("걸리는 조건", "격자 64칸 최고 온도 >= 선"),
      ("", "또는 분당 상승률 >= 선"),
      ("끄는 법", "네 칸을 모두 비운다")],
     ["ABS_TEMP_WARN  = 172", "ABS_TEMP_ALARM = 187",
      "ABS_RISE_WARN  = 90", "ABS_RISE_ALARM = 120"],
     "네 칸을 모두 채우거나 모두 비웁니다. 섞이면 저장을 막습니다."),
    ("2단계", "경험 임계값", AMBER, "서기까지 하루 남짓",
     [("서는 조건", "표본 >= 3,000 그리고"),
      ("", "시간대 >= 18 (둘 다)"),
      ("걸리는 조건", "셀 온도 > 그 셀의 상위 분위선"),
      ("쌓는 곳", "online_baseline.npz")],
     ["BASELINE_MIN_SAMPLES = 3000", "BASELINE_MIN_HOURS   = 18"],
     "시간대 조건이 있는 이유: 낮만 모은 임계값은 밤을 모릅니다."),
    ("3단계", "오토인코더", TEAL, "자료가 모여야 만듦",
     [("만드는 조건", "DB 행 >= 5,000 그리고"),
      ("", "시간대 >= 18"),
      ("쓰는 조건", "예행연습이 승격 판정을 내고"),
      ("", "[재학습 적용] 을 누를 때")],
     ["RETRAIN_MIN_SAMPLES = 5000", "RETRAIN_MIN_HOURS   = 18"],
     "승격해도 2단계는 함께 돕니다. 두 점수 중 낮은 쪽을 씁니다."),
]

for i, (num, name, col, when, rows, keys, note) in enumerate(cols):
    x = M + i * (cw9 + gap9)
    card(s, x, 2.25, cw9, 4.42, fill=PAPER)

    circle(s, x + 0.26, 2.48, 0.46, col, num[0], WHITE, 13)
    tf = textbox(s, x + 0.84, 2.52, cw9 - 1.1, 0.28)
    write(tf, [(num + " · " + name, dict(size=12.5, bold=True, color=INK),
                dict(space_after=0))])
    tf = textbox(s, x + 0.84, 2.80, cw9 - 1.1, 0.24)
    write(tf, [(when, dict(size=9.5, color=MUTED),
                dict(space_after=0))])

    y = 3.22
    for lab, val in rows:
        if lab:
            tf = textbox(s, x + 0.26, y, 1.25, 0.24)
            write(tf, [(lab, dict(size=9.5, bold=True, color=col),
                        dict(space_after=0))])
        tf = textbox(s, x + 1.52, y, cw9 - 1.78, 0.24)
        write(tf, [(val, dict(size=9.5, color=INK), dict(space_after=0))])
        y += 0.265

    code_block(s, x + 0.26, y + 0.12, cw9 - 0.52, keys, size=8.0, pad=0.16)

    tf = textbox(s, x + 0.26, 6.02, cw9 - 0.52, 0.55)
    write(tf, [(note, dict(size=9.5, color=MUTED),
                dict(space_after=0, line=1.2))])

page_num(s, 19)

# =================================================================== 19-2 경험 임계값 변경
s = slide_light(prs)
title_bar(s, "20  BASELINE LIFECYCLE", "2단계 경험 임계값은 언제 바뀌는가")

tf = textbox(s, M, 1.72, 11.6, 0.35)
write(tf, [("경험 임계값이 세는 것은 모델의 오차가 아니라 칸의 온도 그 자체입니다. "
            "그래서 모델을 갈아도 그대로 맞습니다.",
            dict(size=14, color=MUTED), dict(space_after=0))])

lwB = 6.05
rxB = M + lwB + 0.33

# --- 왼쪽: 쌓이는 조건과 창 ---
tf = textbox(s, M, 2.24, lwB, 0.3)
write(tf, [("쌓이는 조건", dict(size=14, bold=True, color=AMBER),
            dict(space_after=0))])

card(s, M, 2.62, lwB, 1.52, fill=PAPER)
tf = textbox(s, M + 0.28, 2.80, lwB - 0.56, 1.2)
write(tf, [("두 가지가 모두 맞을 때만 한 프레임이 들어갑니다.",
            dict(size=10.5, color=INK), dict(space_after=5, line=1.2)),
           ("절대 임계값에 걸리지 않았다", dict(size=10.5, color=INK),
            dict(space_after=3)),
           ("화면이 밀리지 않았다 (기준 패턴과의 상관 0.95 이상)",
            dict(size=10.5, color=INK), dict(space_after=5)),
           ("이상으로 본 프레임을 넣으면 서서히 커지는 열점을 "
            "\"요즘의 정상\" 으로 흡수합니다.",
            dict(size=10, color=EMBER), dict(space_after=0, line=1.2))])

tf = textbox(s, M, 4.28, lwB, 0.3)
write(tf, [("창은 최근 것만 듭니다 (고리 버퍼)", dict(size=14, bold=True, color=AMBER),
            dict(space_after=0))])

card(s, M, 4.66, lwB, 1.62, fill=PAPER)
tf = textbox(s, M + 0.28, 4.84, lwB - 0.56, 1.3)
write(tf, [("최소 조건(3,000건 · 18시간대)을 지키는 선까지만 들고, 그 위로는 "
            "오래된 것부터 밀어냅니다. 상한 50,000건.",
            dict(size=10.5, color=INK), dict(space_after=5, line=1.2)),
           ("그래서 기간을 길게 잡아도 내용은 같습니다. 7월부터 넣든 최근 "
            "5일만 넣든 남는 것은 최근 3,000건입니다.",
            dict(size=10.5, color=MUTED), dict(space_after=5, line=1.2)),
           ("200건마다 저장합니다. 비정상 종료 시 최대 199건을 잃습니다.",
            dict(size=10, color=MUTED), dict(space_after=0, line=1.2))])

# --- 오른쪽: 처음부터 다시 쌓는 네 가지 ---
tf = textbox(s, rxB, 2.24, lwB, 0.3)
write(tf, [("처음부터 다시 쌓는 경우는 네 가지뿐", dict(size=14, bold=True, color=EMBER),
            dict(space_after=0))])

resets = [
    ("--reset-baseline", "사람이 치울 때. 마스크를 다시 떴거나 카메라를 옮겼을 때"),
    ("파일 없음", "설치 직후"),
    ("격자 칸 수 바뀜", "마스크 격자가 64칸이 아니게 되었을 때"),
    ("읽기 실패", "저장 도중 꺼져 파일이 깨졌을 때"),
]
yR = 2.68
for lab, why in resets:
    card(s, rxB, yR, lwB, 0.56, fill=PAPER)
    tf = textbox(s, rxB + 0.24, yR + 0.09, 2.1, 0.24)
    write(tf, [(lab, dict(name=MONO, size=9.5, bold=True, color=EMBER),
                dict(space_after=0))])
    tf = textbox(s, rxB + 2.42, yR + 0.09, lwB - 2.66, 0.4)
    write(tf, [(why, dict(size=9.5, color=INK), dict(space_after=0, line=1.15))])
    yR += 0.64

card(s, rxB, yR + 0.06, lwB, 0.86, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, rxB + 0.26, yR + 0.18, lwB - 0.52, 0.26)
write(tf, [("되돌리기는 경험 임계값을 건드리지 않습니다",
            dict(size=11.5, bold=True, color=TEAL), dict(space_after=0))])
tf = textbox(s, rxB + 0.26, yR + 0.46, lwB - 0.52, 0.4)
write(tf, [("[되돌리기] 는 오토인코더 모델만 세대 단위로 돌립니다. 치운 임계값은 "
            "지우지 않고 _retired_baseline 에 보관합니다.",
            dict(size=9.5, color=INK), dict(space_after=0, line=1.2))])

tf = textbox(s, rxB, yR + 1.06, lwB, 0.26)
write(tf, [("사유는 baseline_reset.ini 에 남고 [설정] 창 [현재 진행] 에 나옵니다.",
            dict(size=9.5, color=MUTED), dict(space_after=0))])

# --- 아래: DB 에서 되쌓기 ---
card(s, M, 6.44, W - 2 * M, 0.62, fill=RGBColor(0xFD, 0xF1, 0xEC))
tf = textbox(s, M + 0.3, 6.53, 3.6, 0.26)
write(tf, [("기다리지 않고 되쌓기", dict(size=11.5, bold=True, color=EMBER),
            dict(space_after=0))])
tf = textbox(s, M + 3.95, 6.53, W - 2 * M - 4.25, 0.26)
write(tf, [("python retrain/rebuild_baseline.py <user>   "
            "— 히스토리 DB 의 프레임으로 한 번에 다시 쌓습니다 (하루 대기 불필요)",
            dict(size=10, color=INK), dict(space_after=0))])
page_num(s, 20)

# =================================================================== 20 재학습
s = slide_light(prs)
title_bar(s, "21  RETRAIN", "재학습 - 창에서 눌러 돌립니다")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("히스토리 DB 에 이미 64셀 값이 쌓이고 있어, 별도 수집 장치 없이 갱신합니다. "
            "정해진 시각에 저절로 돌지는 않습니다 - [재학습] 창에서 눌러야 돌고, "
            "가운데에 진행 판이 떠 경과 시간과 단계를 보여 줍니다.",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

steps4 = [
    ("1", "재생 버퍼", "날짜마다 같은 몫으로, 하루 안에서는 시각 24칸에 "
     "고르게 표집합니다. 최근 것만 쓰면 여름에 겨울 패턴을 잊습니다."),
    ("2", "후보 학습", "서빙과 같은 환경에서 학습하므로 numpy 버전 문제가 없습니다. "
     "모델이 작아 CPU 로 수 분입니다. 다음 장에 전체 흐름도가 있습니다."),
    ("3", "감도 회귀 시험", "정상 적합도만 보면 절반만 본 것입니다. 합성 이상을 주입해 "
     "여전히 잡아내는지 함께 봅니다."),
    ("4", "세대 보관", "재학습을 실제로 돌린 경우만 보관합니다(10세대). 예행연습은 "
     "아무것도 남기지 않습니다. 되돌리기는 다음 장에서 다룹니다."),
]
y4 = 2.28
for num, name, desc in steps4:
    circle(s, M, y4, 0.38, TEAL, num, WHITE, 12)
    tf = textbox(s, M + 0.56, y4 - 0.02, 2.5, 0.28)
    write(tf, [(name, dict(size=13, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, M + 0.56, y4 + 0.3, 6.5, 0.5)
    write(tf, [(desc, dict(size=10.5, color=MUTED), dict(space_after=0, line=1.2))])
    y4 += 0.92

bx7 = M + 7.4
tf = textbox(s, bx7, 2.24, 4.21, 0.3)
write(tf, [("실행", dict(size=13, bold=True, color=INK), dict(space_after=0))])
code_block(s, bx7, 2.6, 4.21, [
    "$ python retrain/nightly_retrain.py <user>",
    "  --dry-run     시험만, 교체 안 함",
    "  --fresh       예행연습을 안 쓰고 새로",
    "  --list        세대 목록",
    "  --rollback [세대]  되돌리기",
    "  --reset-baseline  기준선 치우기",
], size=10)

tf = textbox(s, bx7, 4.5, 4.21, 0.3)
write(tf, [("실측 — cj_busan_1", dict(size=13, bold=True, color=INK), dict(space_after=0))])
rows7 = [("", "후보", "현재"),
         ("정상 평균 점수", "0.931", "0.816"),
         ("정상 오탐 비율", "0.8%", "3.8%"),
         ("+20도 주입", "0.039", "0.433"),
         ("+40도 주입", "0.004", "0.112")]
y7 = 4.88
for i, (a, b, c) in enumerate(rows7):
    hd = (i == 0)
    tf = textbox(s, bx7 + 0.04, y7, 2.1, 0.26)
    write(tf, [(a, dict(size=10, color=MUTED), dict(space_after=0))])
    tf = textbox(s, bx7 + 2.1, y7, 1.0, 0.26, align=PP_ALIGN.RIGHT)
    write(tf, [(b, dict(name=MONO, size=10, bold=True,
                        color=MUTED if hd else TEAL), dict(space_after=0))])
    tf = textbox(s, bx7 + 3.15, y7, 1.0, 0.26, align=PP_ALIGN.RIGHT)
    write(tf, [(c, dict(name=MONO, size=10, color=MUTED), dict(space_after=0))])
    y7 += 0.3

tf = textbox(s, bx7 + 0.04, 6.42, 4.1, 0.44)
write(tf, [("검증 구간이 최근이라 후보에 유리한 비교입니다. "
            "\"지금 데이터에 어느 쪽이 맞는가\" 로 보십시오.",
            dict(size=9.5, color=MUTED), dict(space_after=0, line=1.2))])
page_num(s, 21)

# =================================================================== 재학습 흐름도
s = slide_light(prs)
title_bar(s, "22  RETRAIN FLOW", "재학습은 이렇게 흐릅니다")

tf = textbox(s, M, 1.72, 11.6, 0.35)
write(tf, [("[재학습] 창에서 [예행연습] 이나 [재학습 적용] 을 눌러 시작합니다. "
            "위 줄은 준비, 아래 줄은 학습과 승격입니다.",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

from pptx.enum.shapes import MSO_CONNECTOR
from pptx.oxml.ns import qn
from lxml import etree

FL_BG = RGBColor(0xFD, 0xF3, 0xE3)       # 분기
FL_OK = RGBColor(0xEC, 0xF6, 0xF4)       # 승격
FL_LN = RGBColor(0x8A, 0x94, 0xA6)


def fl_line(x1, y1, x2, y2, arrow=False):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT,
                               Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = FL_LN
    c.line.width = Pt(1.5)
    if arrow:
        ln = c.line._get_or_add_ln()
        te = etree.SubElement(ln, qn("a:tailEnd"))
        te.set("type", "triangle")
        te.set("w", "med")
        te.set("len", "med")
    return c


def fl_node(x, y, w, h, title, sub="", branch="", kind="step", bcol=None):
    fill = {"step": PAPER, "ask": FL_BG, "ok": FL_OK}[kind]
    card(s, x, y, w, h, fill=fill, radius=0.16 if kind == "ask" else 0.06)
    tf = textbox(s, x + 0.1, y + 0.08, w - 0.2, 0.3)
    write(tf, [(title, dict(size=11.5, bold=True, color=INK), dict(space_after=0))])
    lines = []
    if sub:
        lines.append((sub, dict(size=9, color=MUTED), dict(space_after=3, line=1.15)))
    if branch:
        lines.append((branch, dict(size=9, bold=True, color=bcol or EMBER),
                      dict(space_after=0, line=1.15)))
    if lines:
        tf = textbox(s, x + 0.1, y + 0.42, w - 0.2, h - 0.5)
        write(tf, lines)


bw, bh, gp = 1.62, 1.45, 0.376
yA, yB = 2.22, 4.55
xs = [M + i * (bw + gp) for i in range(6)]

rowA = [
    ("재학습 실행", "[예행연습]\n[재학습 적용]", "", "step", None),
    ("예행연습 결과", "적용 때, 6시간 이내", "있으면 그 모델 승격", "ask", TEAL),
    ("운용 모델 읽기", "점수와 표본 선별에 씁니다", "못 읽으면 중단", "ask", EMBER),
    ("기여도 판단", "최근 판단 구간에서 2,000건을 채점해 w 계산", "", "step", None),
    ("재생 버퍼", "날짜마다 같은 몫 · 하루 안은 시각 24칸 균등 · 최대 20,000건", "", "step", None),
    ("표본 충분?", "5,000건 · 18시간대 이상", "모자라면 보류", "ask", EMBER),
]
rowB = [
    ("후보 학습", "85% 학습 · 15% 검증. 웜스타트 (켬: w=0 이면 새로)", "", "step", None),
    ("감도 회귀 시험", "정상 점수 · 오탐 · 합성 이상", "", "step", None),
    ("예행연습인가", "", "예이면 .dryrun 임시 저장", "ask", EMBER),
    ("세대로 보관", "10세대까지 남깁니다", "", "step", None),
    ("시험 통과?", "현재 모델보다 둔하면 불합격", "불합격이면 보류", "ask", EMBER),
    ("승격", "운용 모델로 배치, 10초 안에 교체", "", "ok", None),
]

for row, y in ((rowA, yA), (rowB, yB)):
    for i, (t, sub, br, kind, bcol) in enumerate(row):
        fl_node(xs[i], y, bw, bh, t, sub.replace("\\n", "\n"), br, kind, bcol)
        if i < len(row) - 1:
            fl_line(xs[i] + bw, y + bh / 2, xs[i + 1], y + bh / 2, arrow=True)

# 윗줄 끝에서 아랫줄 처음으로
ymid = yA + bh + (yB - yA - bh) / 2
fl_line(xs[5] + bw / 2, yA + bh, xs[5] + bw / 2, ymid)
fl_line(xs[5] + bw / 2, ymid, xs[0] + bw / 2, ymid)
fl_line(xs[0] + bw / 2, ymid, xs[0] + bw / 2, yB, arrow=True)

tf = textbox(s, M, 6.22, W - 2 * M - 1.1, 0.5)
write(tf, [("둥근 칸은 갈림길입니다. 보류로 끝나도 운용 모델은 그대로이고, 적용 중 시험에서 막힌 "
            "후보는 세대로 남아 왜 막혔는지 보고서로 볼 수 있습니다. 예행연습은 세대를 만들지 않습니다.",
            dict(size=10.5, color=MUTED), dict(space_after=3, line=1.25)),
           ("[자동 재학습] 을 켜 두면 감시가 기여 w < 1.00 일 때 이 흐름을 스스로 시작하고, 시험을 통과하면 "
            "바로 승격합니다. 간격(기본 24시간)을 두고 돌며 결과는 auto_retrain_history.txt 에 쌓입니다. "
            "켜고 끄는 것은 [저장] 으로 확인한 뒤 반영됩니다.",
            dict(size=10.5, bold=True, color=TEAL), dict(space_after=0, line=1.25))])
page_num(s, 22)

# =================================================================== 카메라 이동
s = slide_light(prs)
title_bar(s, "23  CAMERA SHIFT", "카메라가 밀렸을 때")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("이동은 재서 알려 주기만 합니다. 이미지도 마스크도 자동으로 되돌리지 않습니다.",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

tf = textbox(s, M, 2.2, 5.6, 0.3)
write(tf, [("무엇을 재는가", dict(size=13, bold=True, color=INK), dict(space_after=0))])
shift_rows = [
    ("RGB", "base_img/base_ref.png 한 장과 위상 상관. 기동할 때 한 번."),
    ("열화상", "64칸의 느린 EWMA 와 장기 평균의 상관. 0.95 미만이면 누적을 멈춥니다."),
    ("믿을 수 있나", "response 가 0.30 미만이면 '판정 불가'. 거짓말보다 낫습니다."),
]
ys = 2.6
for a, b in shift_rows:
    tf = textbox(s, M + 0.04, ys, 1.5, 0.28)
    write(tf, [(a, dict(size=11.5, bold=True, color=TEAL), dict(space_after=0))])
    tf = textbox(s, M + 1.6, ys, 4.1, 0.5)
    write(tf, [(b, dict(size=10.5, color=MUTED), dict(space_after=0, line=1.2))])
    ys += 0.62

card(s, M, 4.6, 5.6, 1.5, fill=RGBColor(0xFD, 0xF3, 0xE3))
tf = textbox(s, M + 0.3, 4.78, 5.0, 0.3)
write(tf, [("왜 보정하지 않는가", dict(size=12, bold=True, color=INK), dict(space_after=0))])
tf = textbox(s, M + 0.3, 5.12, 5.0, 0.9)
write(tf, [("되돌려도 score 가 0.088 에서 0.365 까지밖에 오르지 않습니다(정상 0.952). "
            "게다가 가장자리에 공백이 생기고, 무엇으로 채우든 지어낸 값이 64차원 "
            "입력 전체를 흐립니다.",
            dict(size=10, color=MUTED), dict(space_after=0, line=1.25))])

bx = M + 6.1
tf = textbox(s, bx, 2.2, 5.4, 0.3)
write(tf, [("칸 수로는 모델 상태를 알 수 없다",
            dict(size=13, bold=True, color=INK), dict(space_after=0))])
rows_sh = [("이동량", "score"),
           ("0칸", "0.957"),
           ("1칸", "0.916"),
           ("2칸", "0.940"),
           ("3칸", "0.890"),
           ("kict1 실제 1.3칸", "0.088")]
ysh = 2.62
for i, (a, b) in enumerate(rows_sh):
    hd = (i == 0)
    last = (i == len(rows_sh) - 1)
    tf = textbox(s, bx + 0.04, ysh, 3.2, 0.26)
    write(tf, [(a, dict(size=10.5, bold=last,
                        color=MUTED if hd else (INK if last else MUTED)),
                dict(space_after=0))])
    tf = textbox(s, bx + 3.3, ysh, 1.4, 0.26, align=PP_ALIGN.RIGHT)
    write(tf, [(b, dict(name=MONO, size=10.5, bold=not hd,
                        color=MUTED if hd else (RGBColor(0xC0, 0x39, 0x2B) if last else TEAL)),
                dict(space_after=0))])
    ysh += 0.32

tf = textbox(s, bx + 0.04, 4.66, 5.3, 0.8)
write(tf, [("7월 자료를 일부러 밀어 잰 값입니다. 3칸을 밀어도 0.890 인데 kict1 은 "
            "1.3칸에 0.088 입니다. 칸 수는 모델 손상을 예측하지 못합니다.",
            dict(size=10, color=MUTED), dict(space_after=0, line=1.25))])

card(s, bx, 5.5, 5.4, 0.9, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, bx + 0.3, 5.66, 4.8, 0.6)
write(tf, [("그래서 2칸 이상이면 [설정] 화면에 '현장 조준 확인' 을 띄웁니다. "
            "자동 보정이 아니라 사람에게 알리는 용도입니다.",
            dict(size=10.5, bold=True, color=TEAL), dict(space_after=0, line=1.25))])
page_num(s, 23)

# =================================================================== 모델 기여도
s = slide_light(prs)
title_bar(s, "24  MODEL CONTRIBUTION", "기존 모델을 얼마나 물려받는가")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("몇 칸 밀렸는지가 아니라 지금 몇 점을 내고 있는지로 정합니다. "
            "점수는 표본을 지금 모델로 다시 매겨 구합니다.",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

tf = textbox(s, M, 2.2, 5.6, 0.3)
write(tf, [("판단 점수", dict(size=13, bold=True, color=INK), dict(space_after=0))])
tf = textbox(s, M + 0.04, 2.56, 5.5, 0.8)
write(tf, [("판단 구간(다음 장)에서 최대 2,000건을 뽑아 지금 모델로 다시 매긴 점수의 "
            "중앙값입니다. DB 에 적힌 점수는 그때 돌던 모델의 것이라 쓰지 않습니다. "
            "순간값 대신 중앙값을 쓰는 것은, 서서히 뜨거워지는 설비의 점수 하락을 "
            "그대로 재학습하면 경보가 사라지기 때문입니다.",
            dict(size=10.5, color=MUTED), dict(space_after=0, line=1.25))])
tf = textbox(s, M + 0.04, 3.52, 5.5, 0.3)
write(tf, [("다음 프레임은 빼고 셉니다", dict(size=11, bold=True, color=INK),
            dict(space_after=0))])
excl = ["절대 임계값이 걸린 프레임 — 이상일 수 있는 구간은 근거가 못 됩니다",
        "열화상이 멈춘 프레임 — 같은 값이 반복되면 점수도 가짜입니다"]
ye = 3.86
for e in excl:
    circle(s, M + 0.08, ye, 0.18, TEAL)
    tf = textbox(s, M + 0.4, ye - 0.05, 5.2, 0.44)
    write(tf, [(e, dict(size=10, color=MUTED), dict(space_after=0, line=1.2))])
    ye += 0.5

bx = M + 6.1
tf = textbox(s, bx, 2.2, 5.4, 0.3)
write(tf, [("점수 → 기여 가중치", dict(size=13, bold=True, color=INK), dict(space_after=0))])
bands = [("점수", "w", "동적구성을 켰을 때"),
         ("0.85 이상", "1.00", "웜스타트 · 옛 자료 w 비율"),
         ("0.70", "0.77", "두 끝 사이는 직선으로 잇습니다"),
         ("0.50", "0.46", "웜스타트 · 옛 자료 46%"),
         ("0.20 이하", "0.00", "새로 초기화 · 새 시기만")]
yb = 2.62
for i, (a, b, c) in enumerate(bands):
    hd = (i == 0)
    tf = textbox(s, bx + 0.04, yb, 1.5, 0.26)
    write(tf, [(a, dict(size=10.5, color=MUTED), dict(space_after=0))])
    tf = textbox(s, bx + 1.6, yb, 0.5, 0.26, align=PP_ALIGN.RIGHT)
    write(tf, [(b, dict(name=MONO, size=10.5, bold=not hd,
                        color=MUTED if hd else TEAL), dict(space_after=0))])
    tf = textbox(s, bx + 2.3, yb, 3.1, 0.26)
    write(tf, [(c, dict(size=10, color=MUTED), dict(space_after=0))])
    yb += 0.32

tf = textbox(s, bx + 0.04, 4.22, 5.3, 0.42)
write(tf, [("두 끝 사이는 직선으로 이어 0.849 와 0.851 이 딴 학습이 되지 않게 합니다. "
            "값은 [설정] 창에서, 기여 문턱은 [재학습] 창의 재생버퍼 동적구성 줄에서 바꿉니다.",
            dict(size=10, color=MUTED), dict(space_after=0, line=1.2))])

card(s, M, 4.7, W - 2 * M, 1.45, fill=RGBColor(0xFD, 0xF3, 0xE3))
tf = textbox(s, M + 0.3, 4.86, 11.0, 0.3)
write(tf, [("w = 0 이어도 옛 모델을 잊지는 않습니다",
            dict(size=12, bold=True, color=INK), dict(space_after=0))])
tf = textbox(s, M + 0.3, 5.2, 11.0, 0.85)
write(tf, [("가중치를 물려받지 않을 뿐, 감도 회귀 게이트의 비교 대상으로는 계속 씁니다. "
            "새 모델이 옛 모델보다 둔해지면 승격을 막는 장치인데, 비교 대상이 없으면 "
            "그 장치가 무력해집니다.  또한 모델을 못 믿기로 했으면 그 모델의 점수로 "
            "학습 표본을 고르지도 않습니다 — 1단계 절대 임계값으로 거릅니다.",
            dict(size=10.5, color=MUTED), dict(space_after=0, line=1.3))])

card(s, M, 6.28, W - 2 * M, 0.55, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, M + 0.34, 6.42, W - 2 * M - 0.68, 0.32)
write(tf, [("기여 문턱과 w 는 재생버퍼 동적구성을 켰을 때만 쓰입니다. 끄면 늘 웜스타트하고 "
            "옛/새를 가르지 않습니다. 학습률은 w 와 무관하게 고정입니다.",
            dict(size=11, bold=True, color=TEAL), dict(space_after=0))])
page_num(s, 24)

# =================================================================== 기여도 판단 구간
s = slide_light(prs)
title_bar(s, "25  CONTRIBUTION WINDOW", "기여도는 어느 구간을 재는가")

tf = textbox(s, M, 1.72, 11.6, 0.35)
write(tf, [("지금 모델이 최근 변화를 잘 받아들이는지 보는 구간입니다. "
            "학습 표본을 뽑는 구간과 같을 필요가 없습니다.",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

# --- 왼쪽 : 규칙 ---
tf = textbox(s, M, 2.2, 5.8, 0.3)
write(tf, [("구간을 정하는 규칙", dict(size=13, bold=True, color=INK), dict(space_after=0))])

win_rules = [
    ("가장 새 테이블부터 N개",
     "N 은 [설정] 창의 판단 최소 일수입니다. 날짜별 테이블(results_history_YYYYMMDD)을 "
     "새것부터 N개 가져옵니다."),
    ("그중 N일보다 오래된 것은 뺀다",
     "가장 새 테이블 날짜에서 N-1일보다 앞선 것을 버립니다. 시계가 아니라 테이블 "
     "이름끼리 견주고, 빈 날이 있으면 N개보다 적게 남습니다."),
    ("이 구간이 재생 버퍼의 새 시기다",
     "동적구성을 켜면 재생 버퍼가 이 구간을 새 시기, 그 앞을 옛 시기로 가르고 "
     "w : 1-w 로 섞습니다. 표본이 모자라면 판단을 보류합니다."),
]
yw = 2.6
for i, (t, d) in enumerate(win_rules):
    circle(s, M + 0.04, yw, 0.26, TEAL, text=str(i + 1), tsize=11)
    tf = textbox(s, M + 0.42, yw - 0.04, 5.4, 0.26)
    write(tf, [(t, dict(size=11.5, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, M + 0.42, yw + 0.24, 5.4, 0.6)
    write(tf, [(d, dict(size=10, color=MUTED), dict(space_after=0, line=1.2))])
    yw += 0.82

# --- 오른쪽 : 날짜 테이블 위에서 두 구간이 겹치는 모양 ---
bx = M + 6.1
tf = textbox(s, bx, 2.2, 5.6, 0.3)
write(tf, [("예 - 판단 최소 일수 7, 가장 새 테이블 10-04", dict(size=13, bold=True, color=INK),
            dict(space_after=0))])

from pptx.enum.dml import MSO_LINE

PUR_BG = RGBColor(0xEE, 0xED, 0xFE)
PUR_TX = RGBColor(0x3C, 0x34, 0x89)
GRY_BG = RGBColor(0xE3, 0xE6, 0xEB)
TEA_BG = RGBColor(0xDD, 0xF1, 0xEA)

cw, n_days = 0.36, 15                  # 09-20 ~ 10-04
days = ["20", "21", "22", "23", "24", "25", "26", "27", "28", "29", "30",
        "1", "2", "3", "4"]

tf = textbox(s, bx, 2.58, 1.0, 0.22)
write(tf, [("9월", dict(size=9, color=MUTED), dict(space_after=0))])
tf = textbox(s, bx + 11 * cw + 0.04, 2.58, 2.0, 0.22)
write(tf, [("10월", dict(size=9, color=MUTED), dict(space_after=0))])

for i, d in enumerate(days):
    card(s, bx + i * cw + 0.02, 2.82, cw - 0.04, 0.3, fill=PAPER, radius=0.2)
    tf = textbox(s, bx + i * cw, 2.85, cw, 0.26, align=PP_ALIGN.CENTER)
    write(tf, [(d, dict(size=8.5, color=MUTED), dict(space_after=0))])

# 판단 구간의 시작 = 옛/새 시기의 경계
x_base = bx + 8 * cw
ln = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x_base), Inches(2.76),
                            Inches(x_base), Inches(4.12))
ln.line.color.rgb = FL_LN
ln.line.width = Pt(1.25)
ln.line.dash_style = MSO_LINE.DASH

# 재생 버퍼 : 전체를 훑고 판단 구간을 새 시기, 그 앞을 옛 시기로 가른다(켬일 때)
card(s, bx, 3.28, 8 * cw - 0.03, 0.34, fill=GRY_BG, radius=0.15)
tf = textbox(s, bx + 0.08, 3.31, 8 * cw - 0.2, 0.28)
write(tf, [("재생 버퍼 - 옛 시기 (켬 w)", dict(size=10, bold=True, color=INK),
            dict(space_after=0))])
card(s, x_base + 0.03, 3.28, 7 * cw - 0.03, 0.34, fill=TEA_BG, radius=0.15)
tf = textbox(s, x_base + 0.1, 3.31, 7 * cw - 0.12, 0.28)
write(tf, [("새 시기 (켬 1-w)", dict(size=10, bold=True, color=TEAL),
            dict(space_after=0))])

# 기여도 : 가장 최근 N일
x_ct = bx + 8 * cw
card(s, x_ct, 3.72, 7 * cw - 0.03, 0.34, fill=PUR_BG, radius=0.15)
tf = textbox(s, x_ct + 0.08, 3.75, 7 * cw - 0.2, 0.28)
write(tf, [("기여도 - 최근 N일", dict(size=10, bold=True, color=PUR_TX),
            dict(space_after=0))])
tf = textbox(s, bx + 0.02, 3.76, 8 * cw - 0.1, 0.26)
write(tf, [("기여도는 이 구간을 보지 않음", dict(size=9, color=MUTED),
            dict(space_after=0))])

# 겹치는 구간
ov = s.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x_ct - 0.03), Inches(3.2),
                        Inches(7 * cw + 0.03), Inches(0.94))
ov.fill.background()
ov.line.color.rgb = RGBColor(0x7F, 0x77, 0xDD)
ov.line.width = Pt(1.5)
ov.line.dash_style = MSO_LINE.DASH
ov.shadow.inherit = False
tf = textbox(s, x_ct - 0.03, 4.17, 7 * cw + 0.03, 0.26, align=PP_ALIGN.CENTER)
write(tf, [("겹치는 구간 09-28 ~ 10-04 (= 새 시기)", dict(size=9.5, color=PUR_TX),
            dict(space_after=0))])
tf = textbox(s, bx, 4.5, 5.5, 0.26)
write(tf, [("켬 / 끔 = 재생버퍼 동적구성 (기본 끔). 끄면 옛/새를 가르지 않고 전체에서 뽑습니다.", dict(size=9, color=MUTED),
            dict(space_after=0))])

# --- 아래 : 왜 이렇게 두는가 ---
cR = (W - 2 * M - 0.3) / 2

card(s, M, 4.95, cR, 1.78, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, M + 0.28, 5.1, cR - 0.56, 0.3)
write(tf, [("재생 버퍼 기간과 같을 필요가 없다", dict(size=12.5, bold=True, color=TEAL),
            dict(space_after=0))])
tf = textbox(s, M + 0.28, 5.44, cR - 0.56, 1.25)
write(tf, [("기여도는 '최근 변화를 받아들이나' 를 재므로 짧고 최근이어야 합니다. "
            "재생 버퍼는 '무엇을 배울까' 라서 계절·가동 패턴을 잊지 않도록 수집 일수(기본 전체) "
            "만큼 넓게 뽑습니다.",
            dict(size=10.5, color=INK), dict(space_after=4, line=1.2)),
           ("동적구성을 켜면 판단 구간이 재생 버퍼의 새 시기가 되어 w : 1-w 로 섞이고, 끄면 구간과 상관없이 전체에서 뽑습니다.",
            dict(size=10.5, color=INK), dict(space_after=0, line=1.2))])

rR = M + cR + 0.3
card(s, rR, 4.95, cR, 1.78, fill=RGBColor(0xFD, 0xF3, 0xE3))
tf = textbox(s, rR + 0.28, 5.1, cR - 0.56, 0.3)
write(tf, [("w 는 동적구성을 켰을 때만 쓰인다", dict(size=12.5, bold=True, color=INK),
            dict(space_after=0))])
tf = textbox(s, rR + 0.28, 5.44, cR - 0.56, 1.25)
write(tf, [("재학습은 사람이 [재학습] 창에서 시작하거나, [자동 재학습] 을 켜면 w < 1.00 일 때 감시가 "
            "시작합니다. 동적구성을 켜면 w 가 웜스타트 여부(w=0 이면 새로 초기화)와 옛 : 새 비율을 "
            "정하고, 끄면 늘 웜스타트합니다. 학습률은 고정입니다.",
            dict(size=10.5, color=INK), dict(space_after=4, line=1.2)),
           ("구간 안에 근거가 모자라면(표본 500건 미만) 판단을 보류하고 w 는 1.00 으로 "
            "둡니다. 모르는 것을 이유로 모델을 버리지 않기 위해서입니다.",
            dict(size=10.5, color=INK), dict(space_after=0, line=1.2))])
page_num(s, 25)

# =================================================================== 22 되돌리기
s = slide_light(prs)
title_bar(s, "26  ROLLBACK", "되돌리기 - 무엇으로 돌아가는가")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("감도 시험을 통과한 모델도 현장에서 겪어 보면 아닐 수 있습니다. "
            "[재학습] 창에서 세대를 골라 되돌립니다.",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

code_block(s, M, 2.2, W - 2 * M, two_col([
    ("[ 재학습 창 ]",                                    "[ generation_history.txt ]"),
    ("[되돌리기] [20260924_145528 (직전) v]",            "09-23 14:51  20260923_145111  승격"),
    ("        [예행연습] [재학습 적용] [닫기]",          "09-24 12:14  20260924_121452  승격"),
    ("[v] 재생버퍼 동적구성 [0.85][0.20] [저장]",       "09-24 12:54  20260923_145111  되돌림"),
    ("[v] 자동 재학습 [ 24 ] 시간마다",                  "09-24 14:55  20260924_145528  승격"),
    ("",                                                 "09-24 22:27  20260924_222750  승격"),
    ("[cj_busan_1] 운용에 올라간 세대",                  ""),
    ("   20260923_145111   운용된 적 있음",              "승격과 되돌림을 남깁니다. 목록에"),
    ("   20260924_121452   운용된 적 있음",              "담는 것은 여기 있는 세대뿐입니다."),
    ("   20260924_145528   운용된 적 있음",              ""),
    ("   20260924_222750   운영중",                      ""),
]), size=10)

cR = (W - 2 * M - 0.3) / 2

card(s, M, 5.16, cR, 1.58, fill=PAPER)
tf = textbox(s, M + 0.28, 5.32, cR - 0.56, 0.3)
write(tf, [("한 걸음 뒤가 아니라 골라서 간다", dict(size=12.5, bold=True, color=INK),
            dict(space_after=0))])
tf = textbox(s, M + 0.28, 5.66, cR - 0.56, 1.0)
write(tf, [("되돌리기도 승격으로 기록되므로, 늘 한 걸음 뒤로만 가면 두 세대 사이를 "
            "왕복할 뿐 더 앞으로는 못 갑니다. 그래서 목록에서 고릅니다.",
            dict(size=11, color=INK), dict(space_after=5, line=1.25)),
           ("목록에는 운용에 올라간 적이 있는 세대만 담깁니다. 예행연습은 아무것도 "
            "남기지 않고, 시험에서 막힌 후보는 운용된 적이 없습니다.",
            dict(size=11, color=INK), dict(space_after=0, line=1.25))])

rR = M + cR + 0.3
card(s, rR, 5.16, cR, 1.58, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, rR + 0.28, 5.32, cR - 0.56, 0.3)
write(tf, [("되돌려도 경험 임계값은 그대로 둡니다",
            dict(size=12.5, bold=True, color=TEAL), dict(space_after=0))])
tf = textbox(s, rR + 0.28, 5.66, cR - 0.56, 1.0)
write(tf, [("경험 임계값이 세는 것은 모델의 오차가 아니라 칸의 온도 그 자체라, "
            "모델을 되돌려도 그대로 맞습니다.",
            dict(size=11, color=INK), dict(space_after=5, line=1.25)),
           ("되돌리기는 오토인코더 모델만 세대 단위로 돌립니다. 되돌린 뒤 "
            "[정지] -> [시작] 이 필요합니다.",
            dict(size=11, bold=True, color=EMBER), dict(space_after=0, line=1.25))])
page_num(s, 26)

# =================================================================== 23 단계 설정
s = slide_light(prs)
title_bar(s, "27  STAGE SETTINGS", "설정 창 - 네 묶음")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("[설정] 버튼을 누르면 창 아래가 펼쳐집니다. "
            "값은 users\\<현장>\\continual_learning.ini 에 저장됩니다.",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

# 20줄 x 8.0pt · pad 0.16 -> 0.32 + 20 * 0.172 = 3.76 인치. 1.98 에서 5.74 까지.
code_block(s, M, 1.98, W - 2 * M, two_col([
    ("[ 1단계 절대 임계값 ]  주의/경보",       "[ 현재 진행 ]"),
    ("격자 최고 온도      [ 172 ][ 187 ]",    "● 1단계 절대임계값   사용 중"),
    ("분당 상승률          [  90 ][ 120 ]",    "     온도 172/187도 · 상승 90/120도/분"),
    ("",                                       ""),
    ("[ 2단계 전환 조건 ]",                    "● 2단계 경험임계값   사용 중        [임계값]"),
    ("기준선 최소 표본수  [ 3000 ]",           "     표본 3,001/3,000 · 시간대 21/18"),
    ("기준선 최소 시간대  [   18 ]",           "     2026-10-01 15:31 DB 에서 되쌓음"),
    ("",                                       "  [현재부터쌓기] [DB에서되쌓기]"),
    ("[ 3단계·기여도 ]",                       "● 3단계 오토인코더   사용 중"),
    ("판단 최소 일수        [    7 ]",      "     세대 20260929_115231"),
    ("표본 수 (최소/최대)  [500][2000]",          "     모델 2026-09-29 11:48"),
    ("기여도 점수 0.9468",                     ""),
    ("현모델 기여도 1.00 · 재학습 불필요",       "  연속학습          현황"),
    ("기여도 계산 2026-10-05 16:59",           "     최근 승격 2026-09-29 11:52"),
    ("",                                       ""),
    ("[ 3단계·재생 버퍼 ]",                    "  운전 상태         전부하 운전"),
    ("재학습 최소 표본수  [ 5000 ]",           "     최근 전부하 운전 100%"),
    ("재학습 최대 표본 수 [ 20000 ]",          ""),
    ("재학습 수집 일수    [    0 ]  0 = 전체",  ""),
    ("재학습 최소 시간대  [   18 ]",           ""),
]), size=8.0, pad=0.16)

# --- 등 색 ---
#
# 모의 화면에서는 ● 가 모두 같은 색이라, 무슨 뜻인지는 여기서 밝힌다.
tf = textbox(s, M, 6.42, 1.5, 0.26)
write(tf, [("등 색", dict(size=11.5, bold=True, color=INK), dict(space_after=0))])

lamps = [(RGBColor(0x00, 0xB4, 0x00), "사용 중"),
         (RGBColor(0xFF, 0xC8, 0x00), "준비 중 — 차오르는 중"),
         (RGBColor(0xAA, 0xAA, 0xAA), "꺼짐 · 집계 대기")]
lx = M + 0.95
for col, lab in lamps:
    circle(s, lx, 6.47, 0.15, col)
    tf = textbox(s, lx + 0.24, 6.44, 2.6, 0.26)
    write(tf, [(lab, dict(size=10.5, color=INK), dict(space_after=0))])
    lx += 0.24 + (2.55 if "차오르는" in lab else 1.35)

# 쪽 번호가 오른쪽 아래(6.88)에 있다. 글상자를 그만큼 좁혀 겹치지 않게 한다.
tf = textbox(s, M, 6.72, W - 2 * M - 1.1, 0.52)
write(tf, [("메인 창 현장 콤보 앞의 등은 이 셋을 접은 것입니다. 노랑이 하나라도 "
            "있으면 노랑, 셋 다 회색일 때만 회색, 그 밖에는 초록입니다. "
            "프로세스가 죽었거나 DB 가 끊기면 그쪽이 이겨 빨강이 됩니다.",
            dict(size=10.5, color=INK), dict(space_after=4, line=1.2)),
           ("네 묶음은 [설정 저장] 하나로 함께 저장하고, 값이 하나라도 "
            "잘못되면 아무것도 쓰지 않습니다. 동적구성·문턱·자동 재학습은 [재학습] 창의 [저장] 으로 저장합니다.",
            dict(size=10.5, color=MUTED), dict(space_after=0, line=1.2))])
page_num(s, 27)


# =================================================================== 24 학습 표본
s = slide_light(prs)
title_bar(s, "28  TRAINING SAMPLE", "학습 표본 - 무엇을 배우는가")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("히스토리 DB 에서 학습에 쓸 프레임을 골라 모읍니다. 앞쪽 [3단계·기여도] 이 "
            "'기존 모델을 믿을지' 라면, 여기는 '무엇으로 학습할지' 입니다.",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

# --- 왼쪽 : 흐름 ---
tf = textbox(s, M, 2.2, 5.6, 0.3)
write(tf, [("고르는 차례", dict(size=13, bold=True, color=INK), dict(space_after=0))])

flow = [("날짜 테이블 (수집 일수)", "results_history_YYYYMMDD 를 훑습니다 (수집 일수가 있으면 그 안의 것만)"),
        ("절대 임계값으로만 거른다", "모델 점수로 거르면 모델이 못 맞히는 "
                                    "구간이 학습에서 빠져 맹점이 고착됩니다"),
        ("날짜마다 같은 몫", "하루 몫 = 최대 표본 수 / 일수. 모자란 날의 몫은 "
                            "다른 날로 넘깁니다"),
        ("하루 안은 시각 24칸에 고르게", "하루 몫을 24개 시각에 같게 나눕니다. 모자라면 복제하지 않고 "
                                    "있는 만큼만")]
yf = 2.58
for i, (t, d) in enumerate(flow):
    circle(s, M + 0.04, yf, 0.26, TEAL, text=str(i + 1), tsize=11)
    tf = textbox(s, M + 0.42, yf - 0.04, 5.2, 0.26)
    write(tf, [(t, dict(size=11.5, bold=True, color=INK), dict(space_after=0))])
    tf = textbox(s, M + 0.42, yf + 0.24, 5.2, 0.44)
    write(tf, [(d, dict(size=10, color=MUTED), dict(space_after=0, line=1.2))])
    yf += 0.68

# --- 오른쪽 : 설정 ---
bx = M + 6.1
tf = textbox(s, bx, 2.2, 5.4, 0.3)
write(tf, [("[설정] · [재학습] 창에서 정합니다", dict(size=13, bold=True, color=INK),
            dict(space_after=0))])

rows = [("항목", "기본", "무엇"),
        ("재학습 최대 표본 수", "60000", "최대 이만큼 모읍니다"),
        ("재학습 수집 일수", "0", "최근 N일 테이블만 훑음, 0 = 전체"),
        ("동적구성 ([재학습] 창)", "끔", "켜면 옛:새 = w:1-w, 끄면 전체에서")]
yb = 2.62
for i, (a, b, c) in enumerate(rows):
    hd = (i == 0)
    tf = textbox(s, bx + 0.04, yb, 1.9, 0.26)
    write(tf, [(a, dict(size=10.5, color=MUTED), dict(space_after=0))])
    tf = textbox(s, bx + 2.0, yb, 0.8, 0.26, align=PP_ALIGN.RIGHT)
    write(tf, [(b, dict(name=MONO, size=10.5, bold=not hd,
                        color=MUTED if hd else TEAL), dict(space_after=0))])
    tf = textbox(s, bx + 3.0, yb, 2.4, 0.26)
    write(tf, [(c, dict(size=10, color=MUTED), dict(space_after=0))])
    yb += 0.34

tf = textbox(s, bx + 0.04, 4.55, 5.3, 0.62)
write(tf, [("가동/정지는 따로 나누지 않습니다. 온도로 갈라 보니 가동과 정지가 아니라 드문 "
            "고온 구간만 떨어져 나왔고(cj_busan_1: 98도, 고온 프레임이 자료의 6.6% -> 표본의 6.0%), "
            "표본 구성도 거의 바뀌지 않았습니다. 날짜와 시각만 고르게 맞춥니다.",
            dict(size=10, color=MUTED), dict(space_after=0, line=1.2))])

# --- 아래 : 표본이 고르게 뽑히는 방식 (쪽 번호가 6.88) ---
card(s, M, 5.38, W - 2 * M, 1.30, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, M + 0.3, 5.50, 11.0, 0.3)
write(tf, [("날짜마다 같은 몫이고, 하루 안에서는 시각마다 고르게 뽑습니다",
            dict(size=12, bold=True, color=TEAL), dict(space_after=0))])
tf = textbox(s, M + 0.3, 5.82, 11.4, 0.78)
write(tf, [("하루에 프레임이 몇 건 쌓였든 하루의 비중은 같습니다. 그날 몫 안에서는 시각 24칸이 "
            "같은 몫을 받고, 칸 안에서는 모든 프레임이 같은 확률입니다.",
            dict(size=10.5, color=INK), dict(space_after=4, line=1.2)),
           ("기간이 길수록 하루의 몫이 작아집니다(180일이면 하루 약 110건). 오래된 자료의 "
            "비중을 줄이려면 재학습 수집 일수로 기간을 자르거나 재생버퍼 동적구성을 쓰십시오.",
            dict(size=10.5, color=EMBER), dict(space_after=0, line=1.2))])
page_num(s, 28)

# =================================================================== 22 안전 규칙
s = slide_dark(prs)
title_bar(s, "29  SAFETY RULES", "연속 학습의 안전 규칙", dark=True)

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("적응(무엇이 정상인가 배우기)과 탐지(이상을 알리기)는 반드시 분리되어야 합니다.",
            dict(size=13.5, color=AMBER), dict(space_after=0))])

rules = [
    ("이상 프레임은 학습하지 않는다",
     "서서히 커지는 열점을 '요즘의 정상' 으로 흡수하면, 정작 위험할 때 경보가 나오지 않습니다."),
    ("절대 임계값은 적응하지 않는다",
     "평소가 무엇이든 상관없이 고정된 선을 지킵니다. 학습 기반 판정이 모두 실패해도 남습니다."),
    ("급격한 변화는 배우지 말고 알린다",
     "카메라가 밀리면 학습을 멈추고 경보합니다. 조준을 되돌리면 자동으로 해제됩니다."),
    ("현재 모델보다 둔해지면 승격하지 않는다",
     "절대 기준만으로는 세대마다 조금씩 나빠지는 것을 못 잡습니다."),
]
y8 = 2.3
for i, (head, body) in enumerate(rules):
    card(s, M, y8, W - 2 * M, 0.88, fill=NAVY_SOFT)
    circle(s, M + 0.3, y8 + 0.25, 0.4, EMBER, str(i + 1), WHITE, 13)
    tf = textbox(s, M + 0.88, y8 + 0.16, 4.3, 0.3)
    write(tf, [(head, dict(size=13, bold=True, color=WHITE), dict(space_after=0))])
    tf = textbox(s, M + 5.4, y8 + 0.2, 6.2, 0.55)
    write(tf, [(body, dict(size=11, color=RGBColor(0xC8, 0xD3, 0xE3)),
                dict(space_after=0, line=1.25))])
    y8 += 0.98

card(s, M, 6.22, W - 2 * M, 0.56, fill=RGBColor(0x2A, 0x3C, 0x30))
tf = textbox(s, M + 0.3, 6.36, W - 2 * M - 0.6, 0.32)
write(tf, [("kict1 사례 — 카메라가 틀어진 뒤 모든 프레임이 이상으로 판정되어, "
            "재생 버퍼가 비고 재학습이 자동 보류되었습니다. 규칙 1이 동작한 것입니다.",
            dict(size=11, bold=True, color=TEAL), dict(space_after=0))])
page_num(s, 29, dark=True)

# =================================================================== 22 시운전 도입
s = slide_light(prs)
title_bar(s, "30  COMMISSIONING", "신규 현장 도입 절차")

tf = textbox(s, M, 1.72, 11.5, 0.35)
write(tf, [("오토인코더는 그 현장을 본 적이 있어야 만들 수 있습니다. 첫날부터 3단계로 "
            "시작하려면 시운전 기간을 학습 기간으로 함께 쓰십시오.",
            dict(size=13.5, color=MUTED), dict(space_after=0))])

phases = [
    ("D+0", "설치 당일", EMBER, [
        "카메라 설치, 배선 점검",
        "env.ini · continual_learning.ini · db_secrets.ini 작성",
        "ABS_TEMP · ABS_RISE 지정",
    ], "1단계 경보 즉시 동작"),
    ("D+0~1", "경험 임계값 누적", AMBER, [
        "하루를 한 바퀴 돌 때까지 대기",
        "표본 3,000건 + 시간대 18개",
        "주야 변화를 모두 관측",
    ], "2단계 채점 시작"),
    ("D+1~3", "첫 모델", TEAL, [
        "nightly_retrain.py 실행",
        "감도 회귀 시험 통과 시 승격",
        "predict_machine 재시작",
    ], "3단계 시작"),
    ("D+3~", "정식 가동", RGBColor(0x3D, 0x6B, 0xA8), [
        "세 단계가 함께 동작",
        "필요할 때 재학습",
        "세대 보관으로 언제든 복귀",
    ], "연속 학습 정상 운영"),
]

bw9 = 2.78
for i, (day, name, col, items, result) in enumerate(phases):
    x = M + i * (bw9 + 0.26)
    card(s, x, 2.34, bw9, 2.26, fill=PAPER)
    tf = textbox(s, x + 0.26, 2.5, bw9 - 0.52, 0.28)
    write(tf, [(day, dict(name=MONO, size=12, bold=True, color=col),
                dict(space_after=0))])
    tf = textbox(s, x + 0.26, 2.82, bw9 - 0.52, 0.3)
    write(tf, [(name, dict(size=13.5, bold=True, color=INK), dict(space_after=0))])
    yy9 = 3.20
    for it in items:
        circle(s, x + 0.3, yy9 + 0.06, 0.13, col)
        tf = textbox(s, x + 0.56, yy9 - 0.03, bw9 - 0.82, 0.3)
        write(tf, [(it, dict(size=9.5, color=MUTED), dict(space_after=0, line=1.2))])
        yy9 += 0.30
    card(s, x + 0.2, 4.18, bw9 - 0.4, 0.3, fill=WHITE)
    tf = textbox(s, x + 0.2, 4.22, bw9 - 0.4, 0.26, align=PP_ALIGN.CENTER)
    write(tf, [(result, dict(size=10, bold=True, color=col), dict(space_after=0))])

    if i < len(phases) - 1:
        ar9 = s.shapes.add_shape(MSO_SHAPE.RIGHT_ARROW,
                                 Inches(x + bw9 + 0.02), Inches(3.37),
                                 Inches(0.2), Inches(0.2))
        ar9.fill.solid()
        ar9.fill.fore_color.rgb = RGBColor(0xC3, 0xCC, 0xD9)
        ar9.line.fill.background()
        ar9.shadow.inherit = False

cw9 = (W - 2 * M - 0.3) / 2

card(s, M, 4.84, cw9, 1.9, fill=RGBColor(0xFD, 0xF1, 0xEC))
circle(s, M + 0.3, 5.08, 0.38, EMBER, "!", WHITE, 14)
tf = textbox(s, M + 0.82, 5.1, cw9 - 1.1, 0.3)
write(tf, [("다른 현장의 모델을 복사하지 마십시오",
            dict(size=13, bold=True, color=EMBER), dict(space_after=0))])
tf = textbox(s, M + 0.3, 5.54, cw9 - 0.6, 1.1)
write(tf, [("모델이 아는 것은 \"22번 칸은 보통 60도\" 같은 칸 번호와 온도의 대응입니다. "
            "같은 번호라도 현장마다 가리키는 실제 위치가 다릅니다.",
            dict(size=11, color=INK), dict(space_after=6, line=1.25)),
           ("복사해도 오류 없이 돌아가고 점수도 나옵니다. 다만 그 값에 의미가 없습니다 — "
            "조용히 틀린 답을 자신 있게 내놓는 상태입니다. 같은 카메라·같은 설비에서 "
            "PC만 교체하는 경우만 예외입니다.",
            dict(size=11, color=EMBER), dict(space_after=0, line=1.25))])

rx9 = M + cw9 + 0.3
card(s, rx9, 4.84, cw9, 1.9, fill=RGBColor(0xEC, 0xF6, 0xF4))
circle(s, rx9 + 0.3, 5.08, 0.38, TEAL, "✓", WHITE, 14)
tf = textbox(s, rx9 + 0.82, 5.1, cw9 - 1.1, 0.3)
write(tf, [("시운전 기간과 겹쳐 쓰십시오",
            dict(size=13, bold=True, color=TEAL), dict(space_after=0))])
tf = textbox(s, rx9 + 0.3, 5.54, cw9 - 0.6, 1.1)
write(tf, [("현장 배선과 시험 운전에 어차피 며칠이 듭니다. 카메라를 먼저 올려 두면 "
            "그 기간에 학습이 끝나, 정식 가동 시점에는 이미 3단계로 시작할 수 있습니다.",
            dict(size=11, color=INK), dict(space_after=6, line=1.25)),
           ("시운전 중 설비를 세워 두면 '정지 상태' 만 배웁니다. 가동과 정지를 "
            "모두 겪게 하십시오.",
            dict(size=11, color=TEAL), dict(space_after=0, line=1.25))])
page_num(s, 30)

# =================================================================== 23 문제 해결
s = slide_dark(prs)
title_bar(s, "31  TROUBLESHOOTING", "자주 겪는 문제", dark=True)

probs = [
    ("점수가 계속 같은 값", "현장 서버의 파일이 갱신되지 않는 경우입니다.",
     "debug_logs 의 ts 값을 확인하십시오. 며칠 전 날짜라면 현장 장비의 업로드를 점검합니다."),
    ("점수가 낮게만 유지됨", "카메라 조준이 틀어진 경우입니다.",
     "학습 데이터에서 늘 뜨거웠던 고정 셀이 같은 자리인지 확인합니다. "
     "자리가 옮겨졌다면 재학습이 아니라 조준 복원이 필요합니다."),
    ("db_utils 임포트 오류", "PyPI 의 동명 패키지가 대신 잡힌 경우입니다.",
     "pip uninstall db_utils 로 제거하고, ROOT_PATH 가 올바른지 확인합니다."),
    ("env.ini 를 찾을 수 없음", "otg_monitoring.ini 의 ROOT_PATH 가 잘못된 경우입니다.",
     "메시지에 표시된 경로와 실제 폴더를 대조합니다."),
    ("프로세스가 6개보다 적음", "특정 스크립트만 기동 직후 종료된 경우입니다.",
     "debug_logs 에서 해당 프로세스 로그의 마지막 줄을 확인합니다."),
]
y = 1.9
for i, (title, cause, fix) in enumerate(probs):
    card(s, M, y, W - 2 * M, 0.93, fill=NAVY_SOFT)
    circle(s, M + 0.28, y + 0.27, 0.4, EMBER, str(i + 1), WHITE, 13)
    tf = textbox(s, M + 0.88, y + 0.14, 3.6, 0.3)
    write(tf, [(title, dict(size=13.5, bold=True, color=WHITE), dict(space_after=0))])
    tf = textbox(s, M + 0.88, y + 0.48, 3.6, 0.38)
    write(tf, [(cause, dict(size=10.5, color=AMBER), dict(space_after=0, line=1.15))])
    tf = textbox(s, M + 4.7, y + 0.2, 6.9, 0.58)
    write(tf, [(fix, dict(size=11.5, color=RGBColor(0xC8, 0xD3, 0xE3)), dict(space_after=0, line=1.25))])
    y += 1.0
page_num(s, 31, dark=True)

# =================================================================== 19 체크리스트
s = slide_light(prs)
title_bar(s, "32  CHECKLIST", "설치 점검표")

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
    "users\\<user>\\env.ini · continual_learning.ini 배치",
    "users\\<user>\\db_secrets.ini 작성",
    "절대 임계값 ABS_TEMP · ABS_RISE 지정 (1단계)",
    "Release x64 빌드 후 시작 버튼으로 6개 기동 확인",
    "신규 현장은 시운전 2~3일 후 첫 모델 승격",
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
        y += 0.62

card(s, M, 6.2, W - 2 * M, 0.6, fill=RGBColor(0xEC, 0xF6, 0xF4))
tf = textbox(s, M + 0.34, 6.36, W - 2 * M - 0.68, 0.32)
write(tf, [("모두 완료되면 현장 두 곳 합쳐 6개가 기동하고, 상태줄에는 선택한 현장 기준으로 [3] processes | err=0000 이 표시됩니다.",
            dict(size=12.5, bold=True, color=TEAL), dict(space_after=0))])
page_num(s, 32)

# 출력 경로는 인자로 바꿀 수 있다 (PowerPoint 가 원본을 열고 있을 때 임시본 생성용)
import sys
out = sys.argv[1] if len(sys.argv) > 1 else \
    r"D:\MultiModal_FireCam\멀티모달_화재감지_모니터링_설치매뉴얼.pptx"
prs.save(out)
print("저장 완료:", out)
print("슬라이드 수:", len(prs.slides.__iter__.__self__._sldIdLst))
