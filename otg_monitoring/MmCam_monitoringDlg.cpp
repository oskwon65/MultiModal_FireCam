// MmCam_monitoringDlg.cpp: 구현 파일

#include "pch.h"
#include "framework.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"
#include "afxdialogex.h"

#include <mysql.h>
#include <vector>
#include <string>
#include <map>
#include <algorithm>
#include <TlHelp32.h>
#include <Psapi.h>
#include <tchar.h>
#include <windows.h>
#include <Wbemidl.h>
#include <comdef.h>
#include "Dlg_Set_MmCam_Env.h"

#pragma comment(lib, "wbemuuid.lib")

// ---------------------------------------------------------
// MmCam 실행 환경 설정
//   - 시작 폴더(ROOT_PATH) : exe 와 같은 폴더의 otg_monitoring.ini 에서 읽음
//   - 그 외 설정          : ROOT_PATH 아래의 users\<ID>\env.ini 에서 읽음
// ---------------------------------------------------------
static const char* DEFAULT_ANACONDA_ENV_NAME = "mfpcam";
static const char* DEFAULT_ANACONDA_ROOT = "C:\\Users\\KICT-SC\\anaconda3\\";
std::string  gUserID;

#define DEFAULT_RESTART_MINUTES   20
#define RESTART_INTERVAL_FILE     "monitoring_config.ini"
#define EXE_LOG_FILE              "monitoring.log"
// (표시 기준은 선택된 user의 스크립트 수 = SCRIPT_COUNT)

extern std::string read_ini_string(const char* section, const char* key, const char* default_value);

// 환경설정 파일(exe 와 같은 폴더의 otg_monitoring.ini) 접근 : MmCam_db_utils.cpp
extern std::string read_app_config_string(const char* section, const char* key, const char* default_value);
extern std::string normalize_dir_path(std::string path);
extern const char* GetMmCamRootPath();
extern const char* GetAppConfigPath();

static bool        g_MmCam_env_loaded = false;
static std::string g_anaconda_env = DEFAULT_ANACONDA_ENV_NAME;
static std::string g_anaconda_root = DEFAULT_ANACONDA_ROOT;
static std::string g_MmCam_start_path;

static void LoadMmCamEnvFromIni()
{
    if (g_MmCam_env_loaded) return;

    // 시작 폴더는 env.ini 가 놓인 위치 자체를 결정하므로 오직 환경설정 파일에서만 읽는다.
    // (env.ini 의 [PATHS] ROOT_PATH 는 참조하지 않는다 - 시작 폴더의 출처를 한 곳으로 유지)
    g_MmCam_start_path = GetMmCamRootPath();

    // Anaconda 설치 위치와 환경 이름은 PC마다 다른 "장비 고유" 설정이므로
    // exe 옆의 환경설정 파일을 우선한다. 값이 없을 때만 env.ini 를 참조하고,
    // 그것도 없으면 내장 기본값을 쓴다.
    const std::string cfg_anaconda_env = read_app_config_string("PYTHON", "ANACONDA_ENV", "");
    const std::string cfg_anaconda_root = read_app_config_string("PYTHON", "ANACONDA_ROOT", "");

    g_anaconda_env = cfg_anaconda_env.empty()
        ? read_ini_string("PYTHON", "ANACONDA_ENV", DEFAULT_ANACONDA_ENV_NAME)
        : cfg_anaconda_env;

    const std::string anaconda_root = cfg_anaconda_root.empty()
        ? read_ini_string("PYTHON", "ANACONDA_ROOT", DEFAULT_ANACONDA_ROOT)
        : cfg_anaconda_root;

    // env.ini 에는 'C:/Users/.../anaconda3' 처럼 슬래시·끝 구분자가 제각각이라
    // cmd 의 call 문에 그대로 넣으면 실패한다. 항상 '...\' 형태로 맞춘다.
    g_anaconda_root = normalize_dir_path(anaconda_root);

    g_MmCam_env_loaded = true;
}

static const char* GetAnacondaEnv() { LoadMmCamEnvFromIni(); return g_anaconda_env.c_str(); }
static const char* GetAnacondaRoot() { LoadMmCamEnvFromIni(); return g_anaconda_root.c_str(); }
const char* GetMmCamStartPath() { LoadMmCamEnvFromIni(); return g_MmCam_start_path.c_str(); }

// ---------------------------------------------------------

struct ConfigInfo {
    int  updateSeconds;
    BOOL cameraPositionCorrection;
};

void            SetConsolePosSize(const char* title, int x, int y, int width, int height);
HWND            FindConsoleByTitle(const char* title);
void            LogAutoRestart(void);
void            LogEvent(const char* reason);
void            ClearLogFile();
ConfigInfo      LoadConfigFromFile(void);
void            SaveRestartMinutesToFile(int minutes);
void            RunCmdHiddenWithLog(const char* title, const char* cmd, const std::string& logPath);
static std::map<DWORD, CString> QueryCommandLinesByExeName(const char* exeName);
static std::vector<PROCESSENTRY32> SnapshotProcesses();
static void     CollectDescendantPids(const std::vector<PROCESSENTRY32>& list, DWORD parentPid, std::vector<DWORD>& outPids);
static void     TerminateProcessTree(DWORD rootPid);

extern MYSQL* connect_db();
extern CurrentStatus   read_db_current_status();
extern void            update_db_main_command(const char* new_code);

#ifdef _DEBUG
#define new DEBUG_NEW
#endif

// ---------------------------------------------------------
// 컨트롤 ID
// ---------------------------------------------------------
// 프로세스별 "정지" 버튼: 행 수만큼 연속 ID를 쓴다 (1004,1005 는 리소스에서 사용 중이라 피함)
#define IDC_BTN_STOP_BASE       5000
#define IDC_BTN_STOP_LAST       5015
#define IDC_BTN_START_ALL     1100
#define IDC_BTN_KILL_ALL            1101
#define IDC_BTN_CMD                1102
#define IDC_BTN_FOLDER          1103
#define IDC_BTN_PROC_LIST       1104
#define IDC_BTN_CLOSE           2000
#define IDC_BTN_MINIMIZE        2001
#define IDC_PROGRESS_START      2002    // '시작' 진행바
#define IDC_BTN_SIGN            3000
#define IDC_EDIT_RESTART_MIN    4000

// ---------------------------------------------------------
// 타이머 ID
// ---------------------------------------------------------
#define SCAN_INTERVAL           2000
#define TIMER_ID_BLINK          1
#define TIMER_ID_UPTIME         2
#define TIMER_ID_SCAN_STATUS    3
#define TIMER_ID_RESTART        4

// ---------------------------------------------------------
// 화면에 표시할 프로세스 행 정의
//   행 = 실행 유저 × 스크립트 (현재 2 × 3 = 6행)
//   커맨드라인에 유저 ID와 스크립트 키워드가 모두 들어있는 python.exe를
//   그 행의 프로세스로 본다.
// ---------------------------------------------------------
static const char* START_USER_IDS[] = {
    "kict1",
    "cj_busan_1"
};

// 커맨드라인 매칭용 키워드
static const char* PROC_SCRIPT_KEYS[] = {
    "server_to_db",
    "predict_machine",
    "fall_detection"
};

// 화면 표시용 짧은 이름 (PROC_SCRIPT_KEYS와 같은 순서)
static const char* PROC_SCRIPT_NAMES[] = {
    "server_to_db",
    "predict_machine",
    "fall_detection"
};

static const int USER_COUNT     = _countof(START_USER_IDS);
static const int SCRIPT_COUNT   = _countof(PROC_SCRIPT_KEYS);
static const int PROC_ROW_COUNT = USER_COUNT * SCRIPT_COUNT;

static_assert(PROC_ROW_COUNT <= (IDC_BTN_STOP_LAST - IDC_BTN_STOP_BASE + 1),
    "정지 버튼 ID 범위가 행 수보다 작다");

// 프로세스 행 레이아웃 (픽셀)
//   목록은 전용 글꼴(PROC_ROW_FONT)을 쓰고, 행 높이를 글꼴 높이에 거의 붙여
//   줄 사이 여백을 최소화한다. (PROC_ROW_HEIGHT - PROC_ROW_CTRL_H = 줄 사이 여백)
#define PROC_ROW_TOP_Y      94
#define PROC_ROW_HEIGHT     23
#define PROC_ROW_CTRL_H     23
#define PROC_ROW_LABEL_X    20
#define PROC_ROW_LABEL_W    430
#define PROC_ROW_BTN_X      (PROC_ROW_LABEL_X + PROC_ROW_LABEL_W + 10)
#define PROC_ROW_BTN_W      60
#define PROC_ROW_SEP_H      2                       // 목록 상단 구분선 두께
#define PROC_ROW_SEP_GAP    8                       // 구분선과 첫 행 사이 간격
#define PROC_ROW_SEP_MARGIN 10                      // 구분선 좌우 여백 (창 끝에서)
#define PROC_ROW_FONT       UI_FONT_NAME
#define PROC_ROW_FONT_H     21
#define PROC_ROW_TEXT_COLOR RGB(0, 0, 0)            // 검정


// ---------------------------------------------------------
// 상단 버튼 외형 (CFancyButton)
// ---------------------------------------------------------
#define FANCY_BTN_RADIUS    10                  // 상단 버튼 모서리 둥글기(px)
#define FANCY_ROW_RADIUS    6                   // 목록 행 버튼(높이 23px) 둥글기
#define FANCY_FACE_BUTTON   RGB(105, 110, 118)  // 모든 버튼 공통 바탕 : 연한 진회색
#define FANCY_TEXT_LIGHT    RGB(255, 255, 255)  // 버튼 글자 : 흰색

// 토글이 켜졌을 때의 표현.
//
// 처음에는 호박색 테두리를 둘렀는데 화면에서는 붉은 테두리로 보였다.
// 색을 쓰지 않고 명암만으로 나타낸다. 안쪽은 어둡게, 테두리는 더 어둡게,
// 아래쪽에만 밝은 선을 한 줄 넣으면 눌려 들어간 것처럼 보인다.
#define FANCY_TOGGLE_EDGE   -0.45   // 켜짐 테두리 : 바탕보다 이만큼 어둡게
#define FANCY_TOGGLE_DOT     0.45   // 켜짐 표시등 : 바탕보다 이만큼 밝게

// 설정 영역이 차지하는 높이(px). Dlg_Set_MmCam_Env 의 내용이 들어갈 만큼.
// 그쪽 배치를 바꾸면 이 값도 같이 맞춰야 한다.
#define SETTING_AREA_H      420
// 목록과 설정 영역 사이 간격
#define AREA_GAP            8

// =========================================================
// CFancyButton 구현
// =========================================================

// 색을 밝게(f>0) 또는 어둡게(f<0) 조정. f는 -1.0 ~ 1.0
static COLORREF ShadeColor(COLORREF c, double f)
{
    int r = GetRValue(c), g = GetGValue(c), b = GetBValue(c);
    if (f >= 0.0)
    {
        r = static_cast<int>(r + (255 - r) * f);
        g = static_cast<int>(g + (255 - g) * f);
        b = static_cast<int>(b + (255 - b) * f);
    }
    else
    {
        const double k = 1.0 + f;
        r = static_cast<int>(r * k);
        g = static_cast<int>(g * k);
        b = static_cast<int>(b * k);
    }
    if (r < 0) r = 0; if (r > 255) r = 255;
    if (g < 0) g = 0; if (g > 255) g = 255;
    if (b < 0) b = 0; if (b > 255) b = 255;
    return RGB(r, g, b);
}

BEGIN_MESSAGE_MAP(CFancyButton, CButton)
    ON_WM_MOUSEMOVE()
    ON_MESSAGE(WM_MOUSELEAVE, &CFancyButton::OnMouseLeave)
    ON_WM_KEYDOWN()
    ON_WM_KEYUP()
END_MESSAGE_MAP()

CFancyButton::CFancyButton()
    : m_face(RGB(242, 244, 247))
    , m_text(RGB(52, 64, 84))
    , m_bHover(false)
    , m_bTracking(false)
    , m_radius(FANCY_BTN_RADIUS)
    , m_bNoKeyActivate(false)
    , m_bChecked(false)
{
}

void CFancyButton::SetNoKeyActivate(bool bNoKey)
{
    m_bNoKeyActivate = bNoKey;
}

void CFancyButton::SetChecked(bool bChecked)
{
    if (m_bChecked == bChecked) return;
    m_bChecked = bChecked;
    Invalidate();      // 눌린 모양으로 다시 그린다
}

// 키보드로는 눌리지 않게 한다 (마우스 클릭은 그대로 동작).
//   포커스를 쥔 버튼은 스페이스바나 엔터만으로도 눌린다. 종료처럼 되돌릴 수
//   없는 동작에 이 경로가 열려 있으면 오타 한 번에 감시가 중단된다.
//   실제로 X 버튼이 포커스를 가진 상태에서 눌린 기록이 otg_events.log 에 남았다.
//
//   포커스 자체를 거부하는 방법(OnSetFocus 에서 부모로 넘기기)은 쓰면 안 된다.
//   버튼은 WM_LBUTTONDOWN 에서 포커스를 잡고 WM_LBUTTONUP 에서 BN_CLICKED 를
//   보내는데, 그 사이에 포커스를 빼앗으면 클릭 처리가 취소되어 마우스로도
//   눌리지 않게 된다. 그래서 키 입력만 걸러낸다.
void CFancyButton::OnKeyDown(UINT nChar, UINT nRepCnt, UINT nFlags)
{
    if (m_bNoKeyActivate && (nChar == VK_SPACE || nChar == VK_RETURN))
        return;
    CButton::OnKeyDown(nChar, nRepCnt, nFlags);
}

void CFancyButton::OnKeyUp(UINT nChar, UINT nRepCnt, UINT nFlags)
{
    if (m_bNoKeyActivate && (nChar == VK_SPACE || nChar == VK_RETURN))
        return;
    CButton::OnKeyUp(nChar, nRepCnt, nFlags);
}

void CFancyButton::SetRadius(int radius)
{
    m_radius = (radius < 0) ? 0 : radius;
    if (GetSafeHwnd()) Invalidate();
}

void CFancyButton::SetAccent(COLORREF face, COLORREF text)
{
    m_face = face;
    m_text = text;
    if (GetSafeHwnd()) Invalidate();
}

// 마우스가 들어오면 다시 그리고, 나갈 때 알림(WM_MOUSELEAVE)을 예약한다
void CFancyButton::OnMouseMove(UINT nFlags, CPoint point)
{
    if (!m_bTracking)
    {
        TRACKMOUSEEVENT tme = {};
        tme.cbSize    = sizeof(tme);
        tme.dwFlags   = TME_LEAVE;
        tme.hwndTrack = GetSafeHwnd();
        if (::TrackMouseEvent(&tme))
            m_bTracking = true;

        m_bHover = true;
        Invalidate();
    }
    CButton::OnMouseMove(nFlags, point);
}

LRESULT CFancyButton::OnMouseLeave(WPARAM, LPARAM)
{
    m_bTracking = false;
    m_bHover    = false;
    Invalidate();
    return 0;
}

void CFancyButton::DrawItem(LPDRAWITEMSTRUCT lpDIS)
{
    CDC*  pDC = CDC::FromHandle(lpDIS->hDC);
    CRect rc  = lpDIS->rcItem;

    // 토글이 켜져 있으면 손을 뗀 뒤에도 계속 눌린 모양으로 그린다.
    const bool bDown     = (lpDIS->itemState & ODS_SELECTED) != 0;
    const bool bPressed  = bDown || m_bChecked;
    const bool bDisabled = (lpDIS->itemState & ODS_DISABLED) != 0;
    const bool bFocused  = (lpDIS->itemState & ODS_FOCUS) != 0;

    // 상태에 따른 바탕색: 눌림은 어둡게, 마우스 오버는 밝게, 비활성은 흐리게
    //
    // 토글이 켜진 상태는 실제로 누르고 있는 것보다 조금 더 어둡게 해서
    // "지금 켜져 있다" 가 분명히 보이게 한다. 마우스를 올렸을 때도 켜진
    // 상태라면 밝아지지 않아야 한다.
    COLORREF face = m_face;
    COLORREF text = m_text;
    if (bDisabled)      { face = ShadeColor(m_face, 0.55); text = RGB(160, 160, 160); }
    else if (m_bChecked){ face = ShadeColor(m_face, bDown ? -0.32 : -0.26); }
    else if (bDown)     { face = ShadeColor(m_face, -0.18); }
    else if (m_bHover)  { face = ShadeColor(m_face, 0.14); }

    // 모서리 바깥은 부모 배경색으로 지운다
    pDC->FillSolidRect(rc, ::GetSysColor(COLOR_3DFACE));

    // 둥근 사각형 본체
    //
    // 토글이 켜지면 색을 쓰지 않고 명암만으로 나타낸다. 테두리를 더 어둡게
    // 두르고, 위쪽 안쪽에 그림자를, 아래쪽 안쪽에 밝은 선을 넣으면 눌려
    // 들어간 것처럼 보인다.
    const bool bOn = m_bChecked && !bDisabled;

    CBrush brFace(face);
    CPen   penEdge(PS_SOLID, 1, ShadeColor(face, bDisabled ? -0.10 : -0.28));
    CPen   penOn(PS_SOLID, 2, ShadeColor(m_face, FANCY_TOGGLE_EDGE));
    CBrush* pOldBrush = pDC->SelectObject(&brFace);
    CPen*   pOldPen   = pDC->SelectObject(bOn ? &penOn : &penEdge);
    pDC->RoundRect(rc, CPoint(m_radius, m_radius));

    if (bOn)
    {
        // 위쪽 안쪽 그림자 두 줄. 아래로 갈수록 옅어지게 해 깊이를 만든다.
        CPen penSh1(PS_SOLID, 1, ShadeColor(face, -0.30));
        CPen penSh2(PS_SOLID, 1, ShadeColor(face, -0.16));
        pDC->SelectObject(&penSh1);
        pDC->MoveTo(rc.left + m_radius, rc.top + 2);
        pDC->LineTo(rc.right - m_radius, rc.top + 2);
        pDC->SelectObject(&penSh2);
        pDC->MoveTo(rc.left + m_radius, rc.top + 3);
        pDC->LineTo(rc.right - m_radius, rc.top + 3);

        // 아래쪽 안쪽에 밝은 선 하나. 오목한 바닥에 빛이 반사된 것처럼 보여
        // 위쪽 그림자와 짝을 이룬다.
        CPen penLit(PS_SOLID, 1, ShadeColor(face, 0.22));
        pDC->SelectObject(&penLit);
        pDC->MoveTo(rc.left + m_radius, rc.bottom - 3);
        pDC->LineTo(rc.right - m_radius, rc.bottom - 3);

        // 왼쪽 안쪽에 켜짐 표시등. 바탕보다 밝은 회색이라 색이 섞이지 않는다.
        const int d = 5;
        const COLORREF dot = ShadeColor(m_face, FANCY_TOGGLE_DOT);
        CBrush brDot(dot);
        CPen   penDot(PS_SOLID, 1, dot);
        pDC->SelectObject(&brDot);
        pDC->SelectObject(&penDot);
        const int cx = rc.left + m_radius - 1;
        const int cy = rc.CenterPoint().y;
        pDC->Ellipse(cx - d / 2, cy - d / 2, cx + d / 2 + 1, cy + d / 2 + 1);
        pDC->SelectObject(&brFace);
    }
    else if (!bPressed && !bDisabled)
    {
        // 눌리지 않은 상태에서는 위쪽에 옅은 하이라이트를 한 줄 넣어 입체감을 준다
        CPen penTop(PS_SOLID, 1, ShadeColor(face, 0.35));
        pDC->SelectObject(&penTop);
        pDC->MoveTo(rc.left + m_radius, rc.top + 1);
        pDC->LineTo(rc.right - m_radius, rc.top + 1);
    }

    pDC->SelectObject(pOldPen);
    pDC->SelectObject(pOldBrush);

    // 글자
    CString caption;
    GetWindowText(caption);

    CFont* pOldFont = nullptr;
    if (GetFont()) pOldFont = pDC->SelectObject(GetFont());

    CRect rcText = rc;
    if (bPressed) rcText.OffsetRect(0, 1);      // 눌리면 한 픽셀 내려 찍는다
    if (bOn) rcText.DeflateRect(6, 0, 0, 0);    // 표시등 자리를 비켜 준다

    pDC->SetBkMode(TRANSPARENT);
    pDC->SetTextColor(text);
    pDC->DrawText(caption, rcText, DT_CENTER | DT_VCENTER | DT_SINGLELINE);

    if (pOldFont) pDC->SelectObject(pOldFont);

    // 키보드 포커스 표시: 안쪽에 점선 테두리
    if (bFocused && !bDisabled)
    {
        CRect rcFocus = rc;
        rcFocus.DeflateRect(3, 3);
        pDC->DrawFocusRect(rcFocus);
    }
}

BEGIN_MESSAGE_MAP(CMmCammonitoringDlg, CDialogEx)
    ON_WM_SYSCOMMAND()
    ON_WM_PAINT()
    ON_WM_QUERYDRAGICON()
    ON_COMMAND_RANGE(IDC_BTN_STOP_BASE, IDC_BTN_STOP_LAST, &CMmCammonitoringDlg::OnStopButton)
    ON_BN_CLICKED(IDC_BTN_START_ALL, &CMmCammonitoringDlg::OnBnClickedStartAll)
    ON_BN_CLICKED(IDC_BTN_KILL_ALL, &CMmCammonitoringDlg::OnBnClickedKillAll)
    ON_BN_CLICKED(IDC_BTN_CMD, &CMmCammonitoringDlg::OnBnClickedCMD)
    ON_BN_CLICKED(IDC_BTN_FOLDER, &CMmCammonitoringDlg::OnBnClickedFolder)
    ON_BN_CLICKED(IDC_BTN_PROC_LIST, &CMmCammonitoringDlg::OnBnClickedProcList)
    ON_BN_CLICKED(IDC_BTN_CLOSE, &CMmCammonitoringDlg::OnBnClickedClose)
    ON_BN_CLICKED(IDC_BTN_MINIMIZE, &CMmCammonitoringDlg::OnBnClickedMinimize)
    ON_WM_LBUTTONDOWN()
    ON_WM_TIMER()
    ON_WM_CTLCOLOR()
    ON_WM_CLOSE()
    ON_WM_DESTROY()
    ON_CBN_SELCHANGE(IDC_COMBO_ID, &CMmCammonitoringDlg::OnSelchangeComboId)
END_MESSAGE_MAP()

// ---------------------------------------------------------

CMmCammonitoringDlg::CMmCammonitoringDlg(CWnd* pParent)
    : CDialogEx(IDD_OTG_MONITORING_DIALOG, pParent)
{
    m_hIcon = AfxGetApp()->LoadIcon(IDR_MAINFRAME);
    m_bRowsVisible = false;
    m_pDlgSet = nullptr;
    m_bSettingVisible = false;
    m_visibleRowCount = 0;
    m_startStep = 0;
    m_bStarting = false;
    m_wndChromeH = 0;
    m_baseWndH = 0;
    m_expandedWndH = 0;
}

void CMmCammonitoringDlg::DoDataExchange(CDataExchange* pDX)
{
    CDialogEx::DoDataExchange(pDX);
    DDX_Control(pDX, IDC_COMBO_ID, mComboBox_ID);
}

// ---------------------------------------------------------
// Minimize 버튼
// ---------------------------------------------------------
void CMmCammonitoringDlg::OnBnClickedMinimize()
{
    ShowWindow(SW_MINIMIZE);
}

// ---------------------------------------------------------
// OnInitDialog
// ---------------------------------------------------------
BOOL CMmCammonitoringDlg::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    ASSERT((IDM_ABOUTBOX & 0xFFF0) == IDM_ABOUTBOX);
    ASSERT(IDM_ABOUTBOX < 0xF000);
    CMenu* pSysMenu = GetSystemMenu(FALSE);
    if (pSysMenu != nullptr)
    {
        CString strAboutMenu;
        if (strAboutMenu.LoadString(IDS_ABOUTBOX) && !strAboutMenu.IsEmpty())
        {
            pSysMenu->AppendMenu(MF_SEPARATOR);
            pSysMenu->AppendMenu(MF_STRING, IDM_ABOUTBOX, strAboutMenu);
        }
    }

    CRect rcDlg;
    GetWindowRect(&rcDlg);
    int x = GetSystemMetrics(SM_CXSCREEN) - rcDlg.Width();
    SetWindowPos(nullptr, x, 3, 0, 0, SWP_NOSIZE | SWP_NOZORDER);

    m_stdFont.CreateFont(
        22, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME)
    );
    SetFont(&m_stdFont);
    SendMessageToDescendants(WM_SETFONT, (WPARAM)m_stdFont.GetSafeHandle(), TRUE);

    m_lblSign.Create("●", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(15, 20, 47, 40), this);

    mComboBox_ID.SetWindowPos(NULL, 45, 15, 160, 100, SWP_NOZORDER);
    mComboBox_ID.AddString("cj_busan_1");
    mComboBox_ID.AddString("kict1");
    mComboBox_ID.SetCurSel(0);

    CString tSel;
    mComboBox_ID.GetWindowText(tSel);
    gUserID = tSel.GetString();

    const long nBase_X = 160;
    const long ctrl_btn_hei = 40;
    const long ctrl_btn_top = 5;
    const long ctrl_btn_wid = 60;                       // 버튼 공통 너비 ("X" 닫기 버튼 제외)
    const long ctrl_btn_gap = 2;                         // 버튼 사이 간격
    const long ctrl_btn_step = ctrl_btn_wid + ctrl_btn_gap;
    const long ctrl_btn_group_X = nBase_X + 120;         // 버튼 그룹 시작 X
    const long ctrl_btn_close_wid = 40;                  // "X" 닫기 버튼 전용 너비

    // idx번째 버튼의 CRect 계산 (좌측 끝 = 그룹 시작 X + idx * (너비+간격))
    auto ButtonRect = [&](int idx) {
        long left = ctrl_btn_group_X + idx * ctrl_btn_step;
        return CRect(left, ctrl_btn_top, left + ctrl_btn_wid, ctrl_btn_top + ctrl_btn_hei);
    };

    m_editRestartMin.Create(
        WS_CHILD | WS_VISIBLE | WS_BORDER | ES_NUMBER | ES_CENTER,
        CRect(nBase_X + 50, ctrl_btn_top + 15, nBase_X + 100, ctrl_btn_top + 35),
        this, IDC_EDIT_RESTART_MIN);

    // 상단 버튼은 BS_OWNERDRAW로 만들어 CFancyButton::DrawItem()이 직접 그린다.
    const DWORD fancyStyle = WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON | BS_OWNERDRAW;

    m_btnStartAll.Create("시작", fancyStyle, ButtonRect(0), this, IDC_BTN_START_ALL);
    m_btnKillAll.Create("정지", fancyStyle, ButtonRect(1), this, IDC_BTN_KILL_ALL);
    m_btnCmd.Create("설정", fancyStyle, ButtonRect(2), this, IDC_BTN_CMD);
    m_btnFolder.Create("폴더", fancyStyle, ButtonRect(3), this, IDC_BTN_FOLDER);
    m_btnProcList.Create("목록", fancyStyle, ButtonRect(4), this, IDC_BTN_PROC_LIST);

    long closeLeft = ctrl_btn_group_X + 5 * ctrl_btn_step;
    m_btnClose.Create("X", fancyStyle,
        CRect(closeLeft, ctrl_btn_top, closeLeft + ctrl_btn_close_wid, ctrl_btn_top + ctrl_btn_hei),
        this, IDC_BTN_CLOSE);

    // 상단 버튼은 모두 연한 진회색 바탕에 흰 글자로 통일
    m_btnStartAll.SetAccent(FANCY_FACE_BUTTON, FANCY_TEXT_LIGHT);
    m_btnKillAll.SetAccent(FANCY_FACE_BUTTON,  FANCY_TEXT_LIGHT);
    m_btnCmd.SetAccent(FANCY_FACE_BUTTON,      FANCY_TEXT_LIGHT);
    m_btnFolder.SetAccent(FANCY_FACE_BUTTON,   FANCY_TEXT_LIGHT);
    m_btnProcList.SetAccent(FANCY_FACE_BUTTON, FANCY_TEXT_LIGHT);
    m_btnClose.SetAccent(FANCY_FACE_BUTTON,    FANCY_TEXT_LIGHT);

    // 종료 버튼은 키보드로 눌리지 않게 한다. 포커스를 쥐면 스페이스/엔터로도
    // 눌려서, 오타 한 번에 감시가 통째로 중단될 수 있다.
    m_btnClose.SetNoKeyActivate(true);
    int nBase_X_Msg = 50;
    int nBase_Y_Msg = 60;

    // 상태는 한 줄로 합쳐 표시한다(개수 → err → 시각). 문자열이 길어져
    // 가동시간 라벨과 겹치지 않도록 상태 줄은 좁히고 시계는 오른쪽 끝으로 뺀다.
    m_lbStatus_0.Create("ready", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(nBase_X_Msg, nBase_Y_Msg, nBase_X_Msg + 485, nBase_Y_Msg + 24), this);

    m_lblTimer.Create("00:00:00", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(nBase_X_Msg + 495, nBase_Y_Msg, nBase_X_Msg + 605, nBase_Y_Msg + 24), this);

    // '시작' 진행바. 평상시에는 숨겨 두고 기동하는 동안만 상태줄 자리에
    // 나타난다. 기동에 20초 안팎이 걸리는데 그동안 화면이 그대로면 눌린
    // 것인지 알 수 없어 다시 누르게 된다.
    m_rcStatusNormal = CRect(nBase_X_Msg, nBase_Y_Msg, nBase_X_Msg + 485, nBase_Y_Msg + 24);

    m_progress.Create(WS_CHILD | PBS_SMOOTH,
        CRect(nBase_X_Msg, nBase_Y_Msg + 3, nBase_X_Msg + 280, nBase_Y_Msg + 21),
        this, IDC_PROGRESS_START);
    m_progress.SetRange(0, 100);
    m_progress.SetPos(0);

    // 프로세스별 상태 행 생성.
    // 평상시에는 접어 두고 "목록" 버튼으로 펼친다. 보이는 행은 콤보박스에서
    // 고른 user의 것만이므로, 창 높이는 LayoutProcessRows()가 계산한다.
    CreateProcessRows(PROC_ROW_TOP_Y);
    {
        CRect rcClient, rcWnd;
        GetClientRect(&rcClient);
        GetWindowRect(&rcWnd);

        m_wndChromeH = rcWnd.Height() - rcClient.Height();   // 캡션+테두리 높이
        m_baseWndH   = rcWnd.Height();

        LayoutProcessRows();      // 선택된 user 기준으로 배치 + 창 높이 계산
        ShowProcessRows(false);   // 접은 상태로 시작
    }


    ConfigInfo env_conf = LoadConfigFromFile();
    CString    sDef;
    sDef.Format("%d", env_conf.updateSeconds);
    m_editRestartMin.SetWindowText(sDef);

    SetWindowText("멀티모달-화재감지-모니터링");
    m_nStatusLevel = STATUS_OK;
    m_elapsedSeconds = 0;

    SetIcon(m_hIcon, TRUE);
    SetIcon(m_hIcon, FALSE);

    SendMessageToDescendants(WM_SETFONT, (WPARAM)m_stdFont.GetSafeHandle(), TRUE);

    // 본문 글꼴을 일괄 적용한 뒤에 목록만 전용 글꼴로 되돌린다
    ApplyRowFont();

    ClearLogFile();

    LogEvent("--- 앱 시작 (OnInitDialog) ---");

    KillOrphanedProcesses();   // 이전 인스턴스가 남긴 유령 프로세스 정리

    return TRUE;
}

// ---------------------------------------------------------
// python.exe 프로세스 수 카운트
// ('시작' 버튼으로 실행한 프로세스(m_startedPids)의 자식으로 한정)
// ---------------------------------------------------------
int CMmCammonitoringDlg::CountPythonProcesses()
{
    m_lastPyProcesses.clear();

    std::vector<PROCESSENTRY32> list = SnapshotProcesses();

    // '시작' 버튼으로 실행한 launcher들의 자식(손자 포함) PID만 대상으로 삼는다
    std::vector<DWORD> trackedPids;
    for (DWORD rootPid : m_startedPids)
        CollectDescendantPids(list, rootPid, trackedPids);

    for (const auto& pe : list)
    {
        if (_stricmp(pe.szExeFile, "python.exe") != 0) continue;

        bool tracked = std::find(trackedPids.begin(), trackedPids.end(), pe.th32ProcessID) != trackedPids.end();
        if (!tracked) continue;

        PyProcessInfo info;
        info.pid = pe.th32ProcessID;

        char path[MAX_PATH] = { 0 };
        HANDLE hProc = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pe.th32ProcessID);
        if (hProc)
        {
            DWORD size = MAX_PATH;
            if (QueryFullProcessImageNameA(hProc, 0, path, &size))
                info.fullPath = path;
            CloseHandle(hProc);
        }
        if (info.fullPath.IsEmpty())
            info.fullPath = pe.szExeFile;

        m_lastPyProcesses.push_back(info);
    }

    // 커맨드라인은 WMI로만 얻을 수 있다. 화면의 행 매칭에 쓰이므로 여기서 한 번에 채운다.
    if (!m_lastPyProcesses.empty())
    {
        std::map<DWORD, CString> cmdLines = QueryCommandLinesByExeName("python.exe");
        for (auto& info : m_lastPyProcesses)
        {
            auto it = cmdLines.find(info.pid);
            if (it != cmdLines.end())
                info.cmdLine = it->second;
        }
    }

    return static_cast<int>(m_lastPyProcesses.size());
}

// ---------------------------------------------------------
// WMI(Win32_Process)로 exeName과 일치하는 프로세스들의
// 실제 커맨드라인(= 어떤 python 스크립트를 어떤 인자로 실행했는지)을 조회
// PID -> CommandLine
// ---------------------------------------------------------
static std::map<DWORD, CString> QueryCommandLinesByExeName(const char* exeName)
{
    std::map<DWORD, CString> result;

    HRESULT hrInit = CoInitializeEx(0, COINIT_APARTMENTTHREADED);
    bool comInitializedHere = (hrInit == S_OK || hrInit == S_FALSE);
    if (FAILED(hrInit) && hrInit != RPC_E_CHANGED_MODE)
        return result;  // COM 초기화 자체가 불가능한 경우만 포기

    IWbemLocator* pLoc = nullptr;
    HRESULT hr = CoCreateInstance(CLSID_WbemLocator, 0, CLSCTX_INPROC_SERVER,
        IID_IWbemLocator, reinterpret_cast<LPVOID*>(&pLoc));
    if (FAILED(hr) || !pLoc)
    {
        if (comInitializedHere) CoUninitialize();
        return result;
    }

    IWbemServices* pSvc = nullptr;
    hr = pLoc->ConnectServer(_bstr_t(L"ROOT\\CIMV2"), nullptr, nullptr,
        0, 0, 0, 0, &pSvc);
    if (FAILED(hr) || !pSvc)
    {
        pLoc->Release();
        if (comInitializedHere) CoUninitialize();
        return result;
    }

    // 이미 다른 곳에서 보안 설정을 했다면 실패해도 무시하고 계속 진행
    CoSetProxyBlanket(pSvc, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, nullptr,
        RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE, nullptr, EOAC_NONE);

    CString wql;
    wql.Format(_T("SELECT ProcessId, CommandLine FROM Win32_Process WHERE Name='%hs'"), exeName);

    IEnumWbemClassObject* pEnumerator = nullptr;
    hr = pSvc->ExecQuery(_bstr_t(L"WQL"), _bstr_t(wql),
        WBEM_FLAG_FORWARD_ONLY | WBEM_FLAG_RETURN_IMMEDIATELY, nullptr, &pEnumerator);

    if (SUCCEEDED(hr) && pEnumerator)
    {
        IWbemClassObject* pObj = nullptr;
        ULONG ret = 0;
        while (pEnumerator->Next(WBEM_INFINITE, 1, &pObj, &ret) == S_OK)
        {
            VARIANT vtPid, vtCmd;
            VariantInit(&vtPid);
            VariantInit(&vtCmd);

            DWORD   pid = 0;
            CString cmdLine;

            if (SUCCEEDED(pObj->Get(L"ProcessId", 0, &vtPid, 0, 0)) && vtPid.vt == VT_I4)
                pid = static_cast<DWORD>(vtPid.lVal);

            if (SUCCEEDED(pObj->Get(L"CommandLine", 0, &vtCmd, 0, 0)) && vtCmd.vt == VT_BSTR)
                cmdLine = vtCmd.bstrVal;

            if (pid != 0)
                result[pid] = cmdLine;

            VariantClear(&vtPid);
            VariantClear(&vtCmd);
            pObj->Release();
        }
        pEnumerator->Release();
    }

    pSvc->Release();
    pLoc->Release();
    if (comInitializedHere) CoUninitialize();

    return result;
}

// ---------------------------------------------------------
// 이전 인스턴스가 남기고 간 유령(고아) 프로세스 정리
// otg_monitoring.exe가 비정상 종료되면 그 프로세스가 띄운 python.exe들은
// 부모 프로세스 없이 계속 살아남는다. 새로 뜬 인스턴스는 그 PID를 전혀
// 모르므로(m_startedPids가 비어있는 채로 시작) '정지' 버튼으로도 종료할 수
// 없다. 시작 시 커맨드라인으로 알려진 스크립트를 찾아서 미리 정리한다.
// ---------------------------------------------------------
static const char* KNOWN_SCRIPT_PATTERNS[] = {
    "server_to_db.py",
    "predict_machine.py",
    "fall_detection.py"
};

void CMmCammonitoringDlg::KillOrphanedProcesses()
{
    std::map<DWORD, CString> cmdLines = QueryCommandLinesByExeName("python.exe");
    int killedCount = 0;

    for (const auto& kv : cmdLines)
    {
        const CString& cmdLine = kv.second;

        for (const char* pattern : KNOWN_SCRIPT_PATTERNS)
        {
            if (cmdLine.Find(CString(pattern)) >= 0)
            {
                TerminateProcessTree(kv.first);
                ++killedCount;
                break;
            }
        }
    }

    if (killedCount > 0)
    {
        // 예전에는 AfxMessageBox 로 알렸는데, 시작 시점(OnInitDialog)에 뜨면
        // 누군가 확인을 누를 때까지 프로그램 전체가 멈춘다. 무인 재시작이
        // 막히므로 모달 창 대신 로그와 상태줄에만 남긴다.
        CString msg;
        msg.Format(_T("[INFO] 이전 실행에서 남은 유령 프로세스 %d개를 정리했습니다."), killedCount);
        LogEvent(CStringA(msg));

        if (m_lbStatus_0.GetSafeHwnd())
            m_lbStatus_0.SetWindowText(msg);
    }
}

// ---------------------------------------------------------
// "목록" 버튼: 하단 프로세스 목록을 펼치거나 접는다
//   (예전에는 팝업 메시지 박스로 목록을 보여줬으나, 창 하단에
//    상시 표시할 수 있게 되어 팝업은 없앴다)
// ---------------------------------------------------------
void CMmCammonitoringDlg::OnBnClickedProcList()
{
    CountPythonProcesses();   // 클릭 시점 기준 최신 PID로 갱신
    RefreshProcessRows();

    ShowProcessRows(!m_bRowsVisible);
}

// ---------------------------------------------------------
// 재시작 주기(ms) 계산
// ---------------------------------------------------------
UINT CMmCammonitoringDlg::GetRestartIntervalMs(bool bSave)
{
    CString text;
    m_editRestartMin.GetWindowText(text);

    int minutes = _ttoi(text);
    if (minutes <= 0)   minutes = DEFAULT_RESTART_MINUTES;
    if (minutes > 1440) minutes = 1440;

    if (bSave) SaveRestartMinutesToFile(minutes);

    return static_cast<UINT>(minutes) * 60 * 1000;
}

// ---------------------------------------------------------
// 재시작 주기 파일 읽기/저장
// ---------------------------------------------------------
#define DEFAULT_UPDATE_SECONDS 120

ConfigInfo LoadConfigFromFile()
{
    ConfigInfo config;
    config.updateSeconds = DEFAULT_UPDATE_SECONDS;
    config.cameraPositionCorrection = FALSE;

    CString filePath;
    filePath.Format(_T("%s\\%s"), GetMmCamStartPath(), RESTART_INTERVAL_FILE);

    CStdioFile    file;
    CFileException ex;
    if (!file.Open(filePath, CFile::modeRead | CFile::typeText, &ex))
        return config;

    CString line;
    if (file.ReadString(line))
    {
        int s = _ttoi(line);
        config.updateSeconds = (s > 0) ? s : DEFAULT_UPDATE_SECONDS;
    }
    if (file.ReadString(line))
    {
        line.Trim(); line.MakeLower();
        config.cameraPositionCorrection = (line == _T("true")) ? TRUE : FALSE;
    }
    file.Close();
    return config;
}

void SaveRestartMinutesToFile(int minutes)
{
    if (minutes <= 0)   minutes = DEFAULT_RESTART_MINUTES;
    if (minutes > 1440) minutes = 1440;

    CString filePath;
    filePath.Format("%s\\%s", GetMmCamStartPath(), RESTART_INTERVAL_FILE);

    CStdioFile    file;
    CFileException ex;
    if (file.Open(filePath, CFile::modeWrite | CFile::modeCreate | CFile::typeText, &ex))
    {
        CString line;
        line.Format("%d\n", minutes);
        file.WriteString(line);
        file.Close();
    }
}

// ---------------------------------------------------------
// 버튼 핸들러
// ---------------------------------------------------------
// ---------------------------------------------------------
// [설정] — 설정 영역 보이기/숨기기
//
// 예전에는 여기서 DoModal() 을 불렀다. 모달 대화상자는 열려 있는 동안
// 부모 창의 메시지를 막으므로, 설정을 보는 중에는 시작·정지·목록 버튼이
// 하나도 눌리지 않았다. 감시 프로그램에서 설정을 확인하는 동안 정지조차
// 못 하는 것은 곤란하다.
//
// 모덜리스로 만들어 두고 이 버튼은 보이기/숨기기만 전환한다. 목록 버튼과
// 같은 방식이다.
// ---------------------------------------------------------
void CMmCammonitoringDlg::OnBnClickedCMD()
{
    if (m_pDlgSet == nullptr)
    {
        m_pDlgSet = new CDlg_Set_MmCam_Env(this);
        if (!m_pDlgSet->Create(IDD_DLG_CMD, this))
        {
            delete m_pDlgSet;
            m_pDlgSet = nullptr;
            AfxMessageBox(_T("[ERROR] 설정 영역을 열 수 없습니다."));
            return;
        }

        // 템플릿은 팝업(WS_POPUP | WS_CAPTION)으로 되어 있다. 메인 창 안에
        // 끼워 넣으려면 자식으로 바꾸고 제목줄·테두리를 걷어내야 한다.
        // 그래야 "목록" 처럼 창 아래가 늘어나며 펼쳐지는 영역이 된다.
        m_pDlgSet->ModifyStyle(WS_POPUP | WS_CAPTION | WS_SYSMENU | WS_BORDER
                               | WS_DLGFRAME | WS_THICKFRAME,
                               WS_CHILD, SWP_FRAMECHANGED);
        m_pDlgSet->ModifyStyleEx(WS_EX_TOOLWINDOW | WS_EX_DLGMODALFRAME
                                 | WS_EX_WINDOWEDGE | WS_EX_CLIENTEDGE,
                                 0, SWP_FRAMECHANGED);
        m_pDlgSet->SetParent(this);

        m_bSettingVisible = false;   // 아래에서 켠다
    }

    m_bSettingVisible = !m_bSettingVisible;

    // 열 때마다 현재 값과 진행 상황을 다시 읽는다. 감시가 도는 동안 표본
    // 수가 계속 늘기 때문에 처음 만든 시점의 값으로 두면 안 된다.
    if (m_bSettingVisible)
        m_pDlgSet->RefreshAll();

    m_btnCmd.SetWindowText(m_bSettingVisible ? "닫기" : "설정");
    m_btnCmd.SetChecked(m_bSettingVisible);

    ApplyExpandLayout();
}

// ---------------------------------------------------------
// 설정 영역이 스스로 닫혔을 때(창의 x 버튼) 버튼 문구를 되돌린다.
// ---------------------------------------------------------
void CMmCammonitoringDlg::OnSettingPanelClosed()
{
    m_bSettingVisible = false;
    m_btnCmd.SetWindowText("설정");
    m_btnCmd.SetChecked(false);
    ApplyExpandLayout();
}
// ---------------------------------------------------------

void CMmCammonitoringDlg::OnBnClickedFolder()
{
    // ini의 ROOT_PATH는 '/' 구분자·트레일링 슬래시 유무가 제각각일 수 있으므로 정규화
    std::string root_path = GetMmCamStartPath();
    std::replace(root_path.begin(), root_path.end(), '/', '\\');
    if (!root_path.empty() && root_path.back() != '\\')
        root_path += '\\';

    std::string log_path = root_path + "debug_logs";

    // explorer.exe에 경로를 인자로 넘기면 구분자 파싱 오류로 이동이 안 될 수 있어
    // 폴더 자체를 "open"으로 직접 실행
    HINSTANCE hr = ShellExecuteA(nullptr, "open", log_path.c_str(), nullptr, nullptr, SW_SHOWNORMAL);
    if (reinterpret_cast<INT_PTR>(hr) <= 32)
    {
        CString msg;
        msg.Format(_T("[ERROR] 폴더를 열 수 없습니다: %s"), CString(log_path.c_str()));
        AfxMessageBox(msg);
    }
}

// ---------------------------------------------------------
void CMmCammonitoringDlg::OnBnClickedClose()
{
    // 감시 중이면 한 번 되묻는다. 종료하면 python 프로세스까지 모두 내려가므로
    // 실수로 닫히면 감시에 구멍이 생긴다. 기본 선택은 "아니오"라서
    // 무심코 엔터를 눌러도 종료되지 않는다.
    int running = 0;
    for (DWORD pid : m_rowPids)
        if (pid != 0) ++running;

    if (running > 0)
    {
        CString ask;
        ask.Format(_T("실행 중인 프로세스 %d개가 함께 종료됩니다.\n\n정말 종료하시겠습니까?"), running);

        if (MessageBox(ask, _T("종료 확인"),
            MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2) != IDYES)
        {
            LogEvent("종료 취소 (사용자가 아니오 선택)");
            return;
        }
    }

    LogEvent("종료: 'X' 버튼 (OnBnClickedClose)");

    KillTimer(TIMER_ID_BLINK);
    KillTimer(TIMER_ID_UPTIME);
    KillTimer(TIMER_ID_SCAN_STATUS);
    KillTimer(TIMER_ID_RESTART);
    OnBnClickedKillAll();
    TerminateProcess(GetCurrentProcess(), 0);
}

// ---------------------------------------------------------
// 실수로 닫히는 경로 차단
//   대화상자는 기본적으로 Enter(IDOK)/ESC(IDCANCEL)에 EndDialog로 응답해
//   종료 코드 0으로 조용히 끝난다. 감시 프로그램에는 위험하므로 막고,
//   눌렸다는 사실만 기록한다. 종료는 'X' 버튼으로만 한다.
// ---------------------------------------------------------
void CMmCammonitoringDlg::OnOK()
{
    LogEvent("[무시] Enter(IDOK)로 닫기 시도");
    // CDialogEx::OnOK() 호출하지 않음
}

void CMmCammonitoringDlg::OnCancel()
{
    LogEvent("[무시] ESC(IDCANCEL)로 닫기 시도");
    // CDialogEx::OnCancel() 호출하지 않음
}

// 제목표시줄 X / Alt+F4 / 작업표시줄 닫기 → 정리 후 종료
void CMmCammonitoringDlg::OnClose()
{
    LogEvent("종료: WM_CLOSE (Alt+F4 또는 시스템 메뉴)");
    OnBnClickedClose();
}

void CMmCammonitoringDlg::OnDestroy()
{
    LogEvent("종료: WM_DESTROY (창 파괴)");

    // 모덜리스 창은 부모가 사라져도 저절로 정리되지 않는다.
    if (m_pDlgSet != nullptr)
    {
        if (::IsWindow(m_pDlgSet->GetSafeHwnd()))
            m_pDlgSet->DestroyWindow();
        delete m_pDlgSet;
        m_pDlgSet = nullptr;
    }

    CDialogEx::OnDestroy();
}

// ---------------------------------------------------------
// 진단용 : 종료로 이어지는 WM_COMMAND가 어디서 왔는지 기록
//   lParam == 0  이면 메뉴/단축키/코드에서 보낸 것
//   lParam == 닫기버튼 HWND 이면 실제 버튼 알림
//   그 밖의 HWND면 엉뚱한 컨트롤이 IDC_BTN_CLOSE로 통지한 것
// ---------------------------------------------------------
BOOL CMmCammonitoringDlg::OnCommand(WPARAM wParam, LPARAM lParam)
{
    const UINT id   = LOWORD(wParam);
    const UINT code = HIWORD(wParam);

    if (id == IDC_BTN_CLOSE)
    {
        char senderCls[64] = { 0 };
        if (lParam) ::GetClassNameA((HWND)lParam, senderCls, sizeof(senderCls));

        CString msg;
        msg.Format("[진단] WM_COMMAND id=%u code=%u sender=%p(%s) 닫기버튼=%p 포커스=%p",
            id, code, (void*)lParam, senderCls,
            (void*)m_btnClose.GetSafeHwnd(), (void*)::GetFocus());
        LogEvent(msg);
    }

    return CDialogEx::OnCommand(wParam, lParam);
}

// ---------------------------------------------------------
void CMmCammonitoringDlg::OnBnClickedStartAll()
{
    // Run_All_Processes()는 프로세스 사이에 PumpWait()로 약 18초를 대기하면서
    // 그동안 메시지를 계속 처리한다. 그 사이에 '시작'이 다시 눌리면 이 핸들러가
    // 중첩 실행되어 같은 프로세스가 두 벌씩 뜬다. 진행 중에는 재진입을 막는다.
    if (m_bStarting)
    {
        LogEvent("[WARN] '시작' 재진입 무시 (이미 기동 중)");
        return;
    }

    m_bStarting = true;
    LogEvent("기동 시작 (OnBnClickedStartAll)");

    m_startedPids.clear();
    m_startStep = 0;

    ShowStartProgress(true);

    for (const char* userId : START_USER_IDS)
        Run_All_Processes(userId);

    // 스크립트를 다 띄워도 뷰어가 바로 뜨지는 않는다. 파이썬이 torch 와
    // 모델을 읽는 동안 몇 초가 더 걸린다. 그 시간까지 진행바로 덮어야
    // "눌렀는데 아무 일도 없다" 는 구간이 사라진다.
    SetStartProgress(88, "이미지 뷰어 준비 중...");

    const DWORD viewerStart = GetTickCount();
    const DWORD viewerLimit = 40000;      // 그래도 안 뜨면 포기하고 넘어간다

    while (GetTickCount() - viewerStart < viewerLimit)
    {
        if (AnyViewerWindowUp()) break;

        PumpWait(700);

        const DWORD el = GetTickCount() - viewerStart;
        SetStartProgress(88 + static_cast<int>(11.0 * el / viewerLimit), nullptr);
    }

    SetStartProgress(100, "기동 완료");
    PumpWait(400);
    ShowStartProgress(false);

    m_elapsedSeconds = 0;
    m_lblTimer.SetWindowText(_T("00:00:00"));

    LogAutoRestart();

    SetTimer(TIMER_ID_BLINK, SCAN_INTERVAL, nullptr);
    SetTimer(TIMER_ID_UPTIME, 1000, nullptr);
    SetTimer(TIMER_ID_SCAN_STATUS, 2000, nullptr);
    SetTimer(TIMER_ID_RESTART, GetRestartIntervalMs(FALSE), nullptr);

    LogEvent("기동 완료");
    m_bStarting = false;
}
// ---------------------------------------------------------
// str_x 파라미터 제거 — 내부에서 사용하지 않음
void CMmCammonitoringDlg::Run_All_Processes(std::string sUserID)
{
    char cmd[1024];

    const char* anacondaRoot = GetAnacondaRoot();
    const char* anacondaEnv = GetAnacondaEnv();
    const char* MmCamStartPath = GetMmCamStartPath();

    DWORD pid;

    sprintf_s(cmd, sizeof(cmd),
        "call \"%sScripts\\activate.bat\" %s && cd /d \"%s\" && python source/server_to_db.py \"%s\"",
        anacondaRoot, anacondaEnv, MmCamStartPath, sUserID.c_str());
    // 진행바는 스크립트 6개(2현장 × 3개)를 0~85% 로 나눠 채운다.
    auto StepBand = [&](const char* name) {
        CStringA t;
        t.Format("%s  기동 중  (%d/%d)", name, m_startStep + 1,
                 USER_COUNT * SCRIPT_COUNT);
        SetStartProgress(m_startStep * 85 / (USER_COUNT * SCRIPT_COUNT), t);
    };

    StepBand("server_to_db");
    pid = RunCmdHidden("server_to_db", cmd);
    if (pid) m_startedPids.push_back(pid);
    PumpWait(3000, m_startStep * 85 / (USER_COUNT * SCRIPT_COUNT),
                   (m_startStep + 1) * 85 / (USER_COUNT * SCRIPT_COUNT));
    ++m_startStep;

    sprintf_s(cmd, sizeof(cmd),
        "call \"%sScripts\\activate.bat\" %s && cd /d \"%s\" && python predict_machine/predict_machine.py \"%s\"",
        anacondaRoot, anacondaEnv, MmCamStartPath, sUserID.c_str());
    StepBand("predict_machine");
    pid = RunCmdHidden("predict_machine", cmd);
    if (pid) m_startedPids.push_back(pid);
    PumpWait(3000, m_startStep * 85 / (USER_COUNT * SCRIPT_COUNT),
                   (m_startStep + 1) * 85 / (USER_COUNT * SCRIPT_COUNT));
    ++m_startStep;

    sprintf_s(cmd, sizeof(cmd),
        "call \"%sScripts\\activate.bat\" %s && cd /d \"%s\" && python fall_detection/fall_detection.py \"%s\"",
        anacondaRoot, anacondaEnv, MmCamStartPath, sUserID.c_str());
    StepBand("fall_detection");
    pid = RunCmdHidden("fall_detection", cmd);
    if (pid) m_startedPids.push_back(pid);
    PumpWait(3000, m_startStep * 85 / (USER_COUNT * SCRIPT_COUNT),
                   (m_startStep + 1) * 85 / (USER_COUNT * SCRIPT_COUNT));
    ++m_startStep;
}

void CMmCammonitoringDlg::PumpWait(DWORD ms, int pctFrom, int pctTo)
{
    const bool bTrack = (pctFrom >= 0 && pctTo >= 0 && ms > 0);

    DWORD start = GetTickCount();
    while (GetTickCount() - start < ms)
    {
        MSG msg;
        while (PeekMessage(&msg, NULL, 0, 0, PM_REMOVE))
        {
            TranslateMessage(&msg);
            DispatchMessage(&msg);
        }

        // 기다리는 동안 진행바를 조금씩 채운다. 단계마다 툭툭 뛰면 멈춘
        // 것처럼 보이지만, 계속 움직이면 진행 중이라는 것이 전해진다.
        if (bTrack && m_progress.GetSafeHwnd())
        {
            const DWORD el = GetTickCount() - start;
            const int pct = pctFrom + static_cast<int>(
                (pctTo - pctFrom) * static_cast<double>(el) / ms);
            m_progress.SetPos(pct);
        }

        Sleep(50);
    }
}

// ---------------------------------------------------------
// '시작' 진행 표시
//
// 진행바는 상태줄 자리에 겹쳐 놓고, 상태 문구는 그 오른쪽으로 잠시
// 밀어 두었다가 끝나면 제자리로 돌린다.
// ---------------------------------------------------------
void CMmCammonitoringDlg::ShowStartProgress(bool bShow)
{
    if (!m_progress.GetSafeHwnd()) return;

    if (bShow)
    {
        m_progress.SetPos(0);
        m_progress.ShowWindow(SW_SHOW);

        // 상태 문구를 진행바 오른쪽으로
        m_lbStatus_0.SetWindowPos(nullptr,
            m_rcStatusNormal.left + 292, m_rcStatusNormal.top,
            m_rcStatusNormal.Width() - 292, m_rcStatusNormal.Height(),
            SWP_NOZORDER);
    }
    else
    {
        m_progress.ShowWindow(SW_HIDE);

        m_lbStatus_0.SetWindowPos(nullptr,
            m_rcStatusNormal.left, m_rcStatusNormal.top,
            m_rcStatusNormal.Width(), m_rcStatusNormal.Height(),
            SWP_NOZORDER);
    }
    Invalidate();
}

void CMmCammonitoringDlg::SetStartProgress(int pct, const char* step)
{
    if (m_progress.GetSafeHwnd()) m_progress.SetPos(pct);
    if (step && m_lbStatus_0.GetSafeHwnd()) m_lbStatus_0.SetWindowText(step);
}

// ---------------------------------------------------------
// 이미지 뷰어 창이 떴는가
//
// 뷰어는 fall_detection 이 OpenCV 로 띄우므로, '시작' 으로 실행한
// 프로세스 중 하나가 보이는 최상위 창을 가지고 있으면 올라온 것으로 본다.
// ---------------------------------------------------------
namespace {
    struct ViewerProbe { const std::vector<DWORD>* pids; bool found; };

    BOOL CALLBACK ViewerProbeProc(HWND hWnd, LPARAM lp)
    {
        ViewerProbe* p = reinterpret_cast<ViewerProbe*>(lp);
        if (!::IsWindowVisible(hWnd)) return TRUE;

        DWORD pid = 0;
        ::GetWindowThreadProcessId(hWnd, &pid);
        if (pid == 0) return TRUE;

        for (DWORD started : *p->pids)
        {
            if (started == pid) { p->found = true; return FALSE; }
        }
        return TRUE;
    }
}

bool CMmCammonitoringDlg::AnyViewerWindowUp()
{
    CountPythonProcesses();   // '시작'으로 띄운 자손 PID 목록 갱신

    std::vector<DWORD> pids;
    for (const auto& info : m_lastPyProcesses)
    {
        if (info.cmdLine.Find("fall_detection") >= 0)
            pids.push_back(info.pid);
    }
    if (pids.empty()) return false;

    ViewerProbe probe = { &pids, false };
    EnumWindows(&ViewerProbeProc, reinterpret_cast<LPARAM>(&probe));
    return probe.found;
}

//윈도우즈 메시지 펌프를 유지하면서 ms 밀리초 대기
void RunCmdHiddenWithLog(const char* title, const char* cmd, const std::string& logPath)
{
    STARTUPINFOA        si{};
    PROCESS_INFORMATION pi{};
    si.cb = sizeof(si);

    std::string fullCmd = std::string("cmd.exe /c \"") + cmd + "\"";

    std::vector<char> buf(fullCmd.begin(), fullCmd.end());
    buf.push_back('\0');

    BOOL ok = CreateProcessA(nullptr, buf.data(), nullptr, nullptr,
        FALSE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi);
    if (!ok)
    {
        AfxMessageBox((std::string("[ERROR] Failed to start: ") + title).c_str());
        return;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
}

// 성공 시 새로 실행된 cmd.exe launcher의 PID를 반환, 실패 시 0
DWORD CMmCammonitoringDlg::RunCmdHidden(const char* name, const char* cmd)
{
    // lpParameters 는 ShellExecuteExA 가 반환할 때까지 유효해야 한다.
    // 임시 std::string 의 c_str() 을 그대로 대입하면 그 줄이 끝나는 순간
    // 임시 객체가 소멸되어 해제된 메모리를 가리키게 된다. (실행 실패 원인)
    const std::string params = std::string("/c ") + cmd;

    SHELLEXECUTEINFOA sei = {};
    sei.cbSize = sizeof(sei);
    sei.fMask = SEE_MASK_NOCLOSEPROCESS;
    sei.lpVerb = "open";
    sei.lpFile = "cmd.exe";
    sei.lpParameters = params.c_str();
    sei.nShow = SW_HIDE;

    if (!ShellExecuteExA(&sei))
    {
        DWORD  err = GetLastError();
        CString msg;
        msg.Format(_T("[ERROR] RunCmdHidden failed: %s (err=%lu)"), CString(name), err);
        AfxMessageBox(msg);
        return 0;
    }

    DWORD pid = 0;
    if (sei.hProcess)
    {
        pid = GetProcessId(sei.hProcess);
        CloseHandle(sei.hProcess);
    }
    return pid;
}

void CMmCammonitoringDlg::OnBnClickedKillAll()
{
    // '시작' 버튼으로 실행한 프로세스(및 그 자식들)만 종료
    for (DWORD pid : m_startedPids)
        TerminateProcessTree(pid);
    m_startedPids.clear();

    // 이전 인스턴스가 남긴 고아 프로세스, 혹은 위 트리 종료에서 놓친 프로세스까지
    // 커맨드라인 패턴으로 한 번 더 정리해서 '정지' 후에는 아무것도 안 남게 한다.
    KillOrphanedProcesses();

    KillTimer(TIMER_ID_BLINK);
    KillTimer(TIMER_ID_UPTIME);
    KillTimer(TIMER_ID_RESTART);
}

// ---------------------------------------------------------
// 프로세스 행 생성
//   유저 × 스크립트 조합마다 [상태 라벨] + [정지] 버튼을 한 줄씩 만든다.
//   topY 아래로 쌓이며, 필요한 높이는 호출부에서 계산해 창을 키운다.
// ---------------------------------------------------------
void CMmCammonitoringDlg::CreateProcessRows(int topY)
{
    m_rowPids.assign(PROC_ROW_COUNT, 0);

    // 목록 전용 글꼴. 본문(22)보다 작아 줄간격을 좁힐 수 있다. 글꼴 이름은
    // UI_FONT_NAME 하나로 통일되어 있다.
    m_rowFont.CreateFont(
        PROC_ROW_FONT_H, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        // ClearType은 작은 글자에 색 테두리(서브픽셀 프린징)를 만들어 회색이 붉게 보인다.
        // 회색조 안티에일리어싱을 써서 순수한 회색으로 렌더링한다.
        ANTIALIASED_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(PROC_ROW_FONT)
    );

    // 상태 줄과 목록을 나누는 가로 구분선 (목록 바로 위)
    //   목록 폭이 아니라 창 폭에 맞춰 좌우 여백만 남기고 끝까지 긋는다.
    CRect rcClientNow;
    GetClientRect(&rcClientNow);

    const int sepTop   = topY - PROC_ROW_SEP_GAP;
    const int sepLeft  = PROC_ROW_SEP_MARGIN;
    int       sepRight = rcClientNow.right - PROC_ROW_SEP_MARGIN;
    if (sepRight < PROC_ROW_BTN_X + PROC_ROW_BTN_W)   // 창이 예상보다 좁을 때 대비
        sepRight = PROC_ROW_BTN_X + PROC_ROW_BTN_W;

    m_lblRowsSeparator.Create("", WS_CHILD | SS_ETCHEDHORZ,
        CRect(sepLeft, sepTop, sepRight, sepTop + PROC_ROW_SEP_H),
        this);

    for (int row = 0; row < PROC_ROW_COUNT; ++row)
    {
        const int top = topY + row * PROC_ROW_HEIGHT;

        CStatic* pLabel = new CStatic();
        // 처음에는 숨김 상태(WS_VISIBLE 없음). "목록" 버튼이 펼칠 때 보인다.
        pLabel->Create("", WS_CHILD | SS_LEFT,
            CRect(PROC_ROW_LABEL_X, top,
                PROC_ROW_LABEL_X + PROC_ROW_LABEL_W, top + PROC_ROW_CTRL_H),
            this);
        m_labels.push_back(pLabel);

        // 행 버튼도 상단 버튼과 같은 CFancyButton(같은 색). 높이가 작아 둥글기만 줄인다.
        CFancyButton* pBtn = new CFancyButton();
        pBtn->Create("정지", WS_CHILD | BS_PUSHBUTTON | BS_OWNERDRAW,
            CRect(PROC_ROW_BTN_X, top,
                PROC_ROW_BTN_X + PROC_ROW_BTN_W, top + PROC_ROW_CTRL_H),
            this, IDC_BTN_STOP_BASE + row);
        pBtn->SetAccent(FANCY_FACE_BUTTON, FANCY_TEXT_LIGHT);
        pBtn->SetRadius(FANCY_ROW_RADIUS);
        m_stopButtons.push_back(pBtn);
    }

    RefreshProcessRows();
}

// ---------------------------------------------------------
// 목록 컨트롤에 전용 글꼴 적용
//   OnInitDialog가 SendMessageToDescendants로 본문 글꼴을 일괄 적용한 뒤에
//   호출해야 한다. 그 전에 걸면 덮어써진다.
// ---------------------------------------------------------
void CMmCammonitoringDlg::ApplyRowFont()
{
    HFONT hFont = (HFONT)m_rowFont.GetSafeHandle();
    if (hFont == nullptr) return;

    for (auto* pLabel : m_labels)
        if (pLabel) pLabel->SetFont(&m_rowFont);

    for (auto* pBtn : m_stopButtons)
        if (pBtn) pBtn->SetFont(&m_rowFont);
}

// ---------------------------------------------------------
// 선택된 user의 행만 위에서부터 차례로 재배치
//   행 자체는 user × 스크립트 조합만큼 미리 만들어 두고, 콤보박스에서 고른
//   user의 행만 골라 빈틈없이 쌓는다. 나머지는 자리만 두고 숨긴다.
//   펼쳤을 때의 창 높이도 보이는 행 수에 맞춰 다시 계산한다.
// ---------------------------------------------------------
void CMmCammonitoringDlg::LayoutProcessRows()
{
    if (static_cast<int>(m_labels.size()) < PROC_ROW_COUNT) return;

    const CString sel = GetSelectedUserId();
    m_shownUserId = sel;

    m_rowSelected.assign(PROC_ROW_COUNT, false);

    int visible = 0;
    for (int u = 0; u < USER_COUNT; ++u)
    {
        const bool bMine = (sel.CompareNoCase(START_USER_IDS[u]) == 0);

        for (int s = 0; s < SCRIPT_COUNT; ++s)
        {
            const int row = u * SCRIPT_COUNT + s;
            if (!bMine) continue;

            m_rowSelected[row] = true;

            const int top = PROC_ROW_TOP_Y + visible * PROC_ROW_HEIGHT;
            m_labels[row]->SetWindowPos(nullptr, PROC_ROW_LABEL_X, top, 0, 0,
                SWP_NOSIZE | SWP_NOZORDER);
            m_stopButtons[row]->SetWindowPos(nullptr, PROC_ROW_BTN_X, top, 0, 0,
                SWP_NOSIZE | SWP_NOZORDER);
            ++visible;
        }
    }

    // 보이는 행 수는 설정 영역 위치를 잡을 때도 필요하므로 남겨 둔다.
    m_visibleRowCount = visible;

    const int expandedClientH = PROC_ROW_TOP_Y + visible * PROC_ROW_HEIGHT + 10;
    m_expandedWndH = expandedClientH + m_wndChromeH;

    ApplyExpandLayout();
    ApplyImageWindowVisibility();   // user가 바뀌면 이미지 창도 즉시 교체
}

// ---------------------------------------------------------
// 펼침 여부와 선택 user를 함께 반영해 표시 상태와 창 높이를 맞춘다
//   행이 보이는 조건 : 목록이 펼쳐져 있고 + 그 행이 선택된 user의 것일 때
// ---------------------------------------------------------
// ---------------------------------------------------------
// 펼쳐지는 두 영역(목록·설정)을 함께 배치하고 창 높이를 맞춘다.
//
// 둘 다 같은 자리(기본 내용 아래)에서 시작하므로 한 곳에서 계산해야
// 서로 겹치지 않는다. 목록이 먼저, 설정이 그 아래다.
// ---------------------------------------------------------
void CMmCammonitoringDlg::ApplyExpandLayout()
{
    for (size_t i = 0; i < m_labels.size(); ++i)
    {
        const bool bMine = (i < m_rowSelected.size()) && m_rowSelected[i];
        const int  cmd   = (m_bRowsVisible && bMine) ? SW_SHOW : SW_HIDE;

        if (m_labels[i])      m_labels[i]->ShowWindow(cmd);
        if (m_stopButtons[i]) m_stopButtons[i]->ShowWindow(cmd);
    }

    m_lblRowsSeparator.ShowWindow(m_bRowsVisible ? SW_SHOW : SW_HIDE);

    // 기본 내용이 끝나는 자리에서 시작해 켜진 영역을 차례로 쌓는다.
    int y = PROC_ROW_TOP_Y;

    if (m_bRowsVisible)
        y += m_visibleRowCount * PROC_ROW_HEIGHT + AREA_GAP;

    if (m_bSettingVisible && m_pDlgSet != nullptr
        && ::IsWindow(m_pDlgSet->GetSafeHwnd()))
    {
        CRect rcClient;
        GetClientRect(&rcClient);
        m_pDlgSet->SetWindowPos(nullptr, 0, y, rcClient.Width(), SETTING_AREA_H,
            SWP_NOZORDER | SWP_SHOWWINDOW);
        y += SETTING_AREA_H;
    }
    else if (m_pDlgSet != nullptr && ::IsWindow(m_pDlgSet->GetSafeHwnd()))
    {
        m_pDlgSet->ShowWindow(SW_HIDE);
    }

    // 아무것도 펼치지 않았으면 원래 높이로 되돌린다.
    const bool bAnyOpen = m_bRowsVisible || m_bSettingVisible;
    const int  wndH = bAnyOpen ? (y + 10 + m_wndChromeH) : m_baseWndH;

    if (wndH > 0)
    {
        CRect rcWnd;
        GetWindowRect(&rcWnd);
        if (rcWnd.Height() != wndH)
            SetWindowPos(nullptr, 0, 0, rcWnd.Width(), wndH, SWP_NOMOVE | SWP_NOZORDER);
    }
}

// 예전 이름으로 부르던 곳을 그대로 두기 위한 얇은 껍데기
void CMmCammonitoringDlg::ApplyRowVisibility()
{
    ApplyExpandLayout();
}

// ---------------------------------------------------------
// 하단 프로세스 목록 펼치기/접기
//   접혀 있어도 타이머의 RefreshProcessRows()는 계속 돌아가므로
//   펼치는 즉시 최신 상태다.
// ---------------------------------------------------------
void CMmCammonitoringDlg::ShowProcessRows(bool bShow)
{
    m_bRowsVisible = bShow;

    // 버튼 문구로 현재 상태를 알린다
    m_btnProcList.SetWindowText(bShow ? "접기" : "목록");

    ApplyRowVisibility();
}

// ---------------------------------------------------------
// 콤보박스에서 고른 user ID
//   CBN_SELCHANGE 시점에는 편집창 텍스트가 아직 갱신 전이라 목록에서 읽는다.
//   직접 입력된 경우(CB_ERR)에는 편집창 텍스트를 쓴다.
// ---------------------------------------------------------
CString CMmCammonitoringDlg::GetSelectedUserId()
{
    CString sel;

    const int nSel = mComboBox_ID.GetCurSel();
    if (nSel != CB_ERR)
        mComboBox_ID.GetLBText(nSel, sel);
    else
        mComboBox_ID.GetWindowText(sel);

    sel.Trim();
    return sel;
}

// ---------------------------------------------------------
// 콤보박스에서 user를 바꾸면 그 user의 행만 남도록 다시 배치한다
// ---------------------------------------------------------
void CMmCammonitoringDlg::OnSelchangeComboId()
{
    LayoutProcessRows();
    gUserID = m_shownUserId.GetString();
}

// ---------------------------------------------------------
// 선택된 user의 창만 화면에 남긴다
//   fall_detection이 user마다 OpenCV 이미지 뷰어 창을 하나씩 띄우기 때문에
//   그냥 두면 모든 user의 창이 동시에 보인다. 행에서 이미 파악해 둔 PID로
//   창 주인을 가려내, 선택되지 않은 user의 창은 숨긴다.
//
//   cv2.imshow()는 이미 만들어진 창을 매 프레임 다시 SW_SHOW 하지 않으므로
//   (실측 확인) 숨긴 창이 되살아나지 않는다. 위치·크기는 파이썬이 계속
//   관리하므로 건드리지 않는다.
// ---------------------------------------------------------
struct ImageWndContext
{
    const std::vector<DWORD>* pRowPids;
    const std::vector<bool>*  pRowSelected;
};

static BOOL CALLBACK ApplyImageWndEnumProc(HWND hWnd, LPARAM lParam)
{
    ImageWndContext* ctx = reinterpret_cast<ImageWndContext*>(lParam);

    DWORD pid = 0;
    GetWindowThreadProcessId(hWnd, &pid);
    if (pid == 0) return TRUE;

    // 우리가 띄운 프로세스의 창만 건드린다
    for (size_t i = 0; i < ctx->pRowPids->size(); ++i)
    {
        if ((*ctx->pRowPids)[i] != pid) continue;

        const bool bMine = (i < ctx->pRowSelected->size()) && (*ctx->pRowSelected)[i];

        // 이미 원하는 상태면 건드리지 않는다 (불필요한 프로세스 간 메시지 방지)
        if (IsWindowVisible(hWnd) == (bMine ? TRUE : FALSE))
            break;

        // ShowWindow()는 다른 프로세스의 창에 대해 "동기" 호출이라, 대상 스레드가
        // 메시지를 처리할 때까지 이쪽 UI 스레드가 멈춘다. fall_detection은 추론 중
        // 수 초씩 메시지 루프를 못 도므로 그대로 쓰면 감시 창이 랙에 걸린다.
        // ShowWindowAsync()는 메시지만 보내고 즉시 돌아온다.
        ShowWindowAsync(hWnd, bMine ? SW_SHOWNA : SW_HIDE);
        break;
    }
    return TRUE;
}

void CMmCammonitoringDlg::ApplyImageWindowVisibility()
{
    if (m_rowPids.empty()) return;

    ImageWndContext ctx = { &m_rowPids, &m_rowSelected };
    EnumWindows(&ApplyImageWndEnumProc, reinterpret_cast<LPARAM>(&ctx));
}

// ---------------------------------------------------------
// 행별 실행 상태 갱신
//   CountPythonProcesses()가 채워 둔 커맨드라인과 대조해 PID를 찾는다.
//   '시작'으로 띄운 프로세스의 자손만 m_lastPyProcesses에 들어오므로,
//   다른 경로로 실행된 동명 프로세스는 여기에 잡히지 않는다.
// ---------------------------------------------------------
void CMmCammonitoringDlg::RefreshProcessRows()
{
    if (static_cast<int>(m_labels.size()) < PROC_ROW_COUNT) return;

    for (int u = 0; u < USER_COUNT; ++u)
    {
        for (int s = 0; s < SCRIPT_COUNT; ++s)
        {
            const int row = u * SCRIPT_COUNT + s;

            DWORD foundPid = 0;
            for (const auto& info : m_lastPyProcesses)
            {
                if (info.cmdLine.Find(PROC_SCRIPT_KEYS[s]) < 0) continue;
                if (info.cmdLine.Find(START_USER_IDS[u]) < 0) continue;
                foundPid = info.pid;
                break;
            }

            const bool wasRunning = (m_rowPids[row] != 0);
            m_rowPids[row] = foundPid;

            CString text;
            if (foundPid)
                text.Format("%s  |  %s  |  PID %lu",
                    START_USER_IDS[u], PROC_SCRIPT_NAMES[s], foundPid);
            else
                text.Format("%s  |  %s  |  중지됨",
                    START_USER_IDS[u], PROC_SCRIPT_NAMES[s]);

            CString current;
            m_labels[row]->GetWindowText(current);
            if (current != text)
                m_labels[row]->SetWindowText(text);

            // 실행 <-> 중지 전환 시에만 다시 그려서 색을 바꾼다
            if (wasRunning != (foundPid != 0))
                m_labels[row]->Invalidate();

            m_stopButtons[row]->EnableWindow(foundPid != 0);
        }
    }

    // 행 PID가 확정됐으니 이미지 뷰어 창 표시 여부도 같이 맞춘다
    ApplyImageWindowVisibility();
}

// ---------------------------------------------------------
// 행의 "정지" 버튼: 그 행의 PID만 트리째 종료
// ---------------------------------------------------------
void CMmCammonitoringDlg::OnStopButton(UINT nID)
{
    const int row = static_cast<int>(nID) - IDC_BTN_STOP_BASE;
    if (row < 0 || row >= PROC_ROW_COUNT) return;
    if (row >= static_cast<int>(m_rowPids.size())) return;

    const DWORD pid = m_rowPids[row];
    if (pid == 0) return;

    TerminateProcessTree(pid);

    // 종료 결과를 곧바로 화면에 반영
    CountPythonProcesses();
    RefreshProcessRows();
}

void CMmCammonitoringDlg::OnSysCommand(UINT nID, LPARAM lParam)
{
    CDialogEx::OnSysCommand(nID, lParam);
}

// ---------------------------------------------------------
// Paint / Icon / 드래그
// ---------------------------------------------------------
void CMmCammonitoringDlg::OnPaint()
{
    if (IsIconic())
    {
        CPaintDC dc(this);
        SendMessage(WM_ICONERASEBKGND, reinterpret_cast<WPARAM>(dc.GetSafeHdc()), 0);
        int  cxIcon = GetSystemMetrics(SM_CXICON);
        int  cyIcon = GetSystemMetrics(SM_CYICON);
        CRect rect;
        GetClientRect(&rect);
        dc.DrawIcon((rect.Width() - cxIcon + 1) / 2,
            (rect.Height() - cyIcon + 1) / 2, m_hIcon);
    }
    else
    {
        CDialogEx::OnPaint();
    }
}

HCURSOR CMmCammonitoringDlg::OnQueryDragIcon()
{
    return static_cast<HCURSOR>(m_hIcon);
}

void CMmCammonitoringDlg::OnLButtonDown(UINT nFlags, CPoint point)
{
    if (point.y < 40)
    {
        ReleaseCapture();
        SendMessage(WM_NCLBUTTONDOWN, HTCAPTION, 0);
        return;
    }
    CDialogEx::OnLButtonDown(nFlags, point);
}

// ---------------------------------------------------------
// 프로세스 검색/종료
// ---------------------------------------------------------
static const char* EXCLUDE_TITLE_STUDIO_CODE = "Studio Code";

struct EnumFindContext { const char* keyword; bool found; };

bool CMmCammonitoringDlg::IsProcessRunning(const char* keyword)
{
    EnumFindContext ctx{ keyword, false };
    EnumWindows([](HWND hWnd, LPARAM lParam)->BOOL {
        auto* ctx = reinterpret_cast<EnumFindContext*>(lParam);
        char title[256] = { 0 };
        ::GetWindowTextA(hWnd, title, sizeof(title));
        if (!title[0])                             return TRUE;
        if (strstr(title, EXCLUDE_TITLE_STUDIO_CODE)) return TRUE;
        if (strstr(title, "Anaconda Prompt"))      return TRUE;
        if (strstr(title, ctx->keyword)) { ctx->found = true; return FALSE; }
        return TRUE;
    }, reinterpret_cast<LPARAM>(&ctx));
    return ctx.found;
}

bool CMmCammonitoringDlg::KillProcess(const char* exeName)
{
    bool   killed = false;
    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return false;

    PROCESSENTRY32 pe;
    pe.dwSize = sizeof(PROCESSENTRY32);
    if (Process32First(snapshot, &pe))
    {
        do {
            if (_stricmp(pe.szExeFile, exeName) == 0)
            {
                HANDLE hProc = OpenProcess(PROCESS_TERMINATE, FALSE, pe.th32ProcessID);
                if (hProc) { TerminateProcess(hProc, 0); CloseHandle(hProc); killed = true; }
            }
        } while (Process32Next(snapshot, &pe));
    }
    CloseHandle(snapshot);
    return killed;
}

static std::vector<PROCESSENTRY32> SnapshotProcesses()
{
    std::vector<PROCESSENTRY32> list;

    HANDLE snapshot = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snapshot == INVALID_HANDLE_VALUE) return list;

    PROCESSENTRY32 pe;
    pe.dwSize = sizeof(PROCESSENTRY32);
    if (Process32First(snapshot, &pe))
    {
        do { list.push_back(pe); } while (Process32Next(snapshot, &pe));
    }
    CloseHandle(snapshot);
    return list;
}

// parentPid의 자식 프로세스를 재귀적으로 outPids에 추가 (자식 -> 손자 순)
static void CollectDescendantPids(const std::vector<PROCESSENTRY32>& list, DWORD parentPid, std::vector<DWORD>& outPids)
{
    for (const auto& pe : list)
    {
        if (pe.th32ParentProcessID == parentPid)
        {
            outPids.push_back(pe.th32ProcessID);
            CollectDescendantPids(list, pe.th32ProcessID, outPids);
        }
    }
}

// rootPid가 실행한 프로세스 트리(자식 포함)만 종료. 자식부터 종료 후 마지막에 root 종료
static void TerminateProcessTree(DWORD rootPid)
{
    std::vector<PROCESSENTRY32> list = SnapshotProcesses();

    std::vector<DWORD> pids;
    CollectDescendantPids(list, rootPid, pids);
    pids.push_back(rootPid);

    for (DWORD pid : pids)
    {
        HANDLE hProc = OpenProcess(PROCESS_TERMINATE, FALSE, pid);
        if (hProc) { TerminateProcess(hProc, 0); CloseHandle(hProc); }
    }
}

// ---------------------------------------------------------
// 콘솔 창 위치 조정
// ---------------------------------------------------------
HWND FindConsoleByTitle(const char* title)
{
    struct Ctx { const char* title; HWND hWnd; } ctx = { title, nullptr };
    EnumWindows([](HWND hWnd, LPARAM lParam)->BOOL {
        Ctx* ctx = reinterpret_cast<Ctx*>(lParam);
        char buf[256];
        ::GetWindowTextA(hWnd, buf, sizeof(buf));
        if (strstr(buf, ctx->title)) { ctx->hWnd = hWnd; return FALSE; }
        return TRUE;
    }, reinterpret_cast<LPARAM>(&ctx));
    return ctx.hWnd;
}

void SetConsolePosSize(const char* title, int x, int y, int width, int height)
{
    for (int i = 0; i < 50; ++i)
    {
        HWND hWnd = FindConsoleByTitle(title);
        if (hWnd)
        {
            SetWindowPos(hWnd, nullptr, x, y, width, height, SWP_NOZORDER | SWP_SHOWWINDOW);
            return;
        }
        Sleep(100);
    }
}

// ---------------------------------------------------------
// 자동 재시작 로그
// ---------------------------------------------------------
void ClearLogFile()
{
    CString logPath;
    logPath.Format("%s\\%s", GetMmCamStartPath(), EXE_LOG_FILE);

    CStdioFile    file;
    CFileException ex;
    if (file.Open(logPath, CFile::modeWrite | CFile::modeCreate | CFile::typeText, &ex))
        file.Close();
}

void LogAutoRestart()
{
    CString logPath;
    logPath.Format("%s\\%s", GetMmCamStartPath(), EXE_LOG_FILE);

    CTime   now = CTime::GetCurrentTime();
    CString line;
    line.Format(_T("%04d-%02d-%02d %02d:%02d:%02d - AUTO RESTART\n\r"),
        now.GetYear(), now.GetMonth(), now.GetDay(),
        now.GetHour(), now.GetMinute(), now.GetSecond());

    CStdioFile    file;
    CFileException ex;
    if (file.Open(logPath,
        CFile::modeWrite | CFile::modeCreate | CFile::modeNoTruncate | CFile::typeText, &ex))
    {
        file.SeekToEnd();
        file.WriteString(line);
        file.Close();
    }
}

// ---------------------------------------------------------
// 이벤트 기록 (기동/종료 경로)
//   앱이 조용히 사라지거나 프로세스가 중복 기동되는 일이 관찰되어,
//   기동과 종료의 모든 길목에 흔적을 남긴다. 로그만 보면 몇 번 돌았는지,
//   어느 경로로 끝났는지 알 수 있다.
//   (EXE_LOG_FILE과 달리 시작할 때 지우지 않고 계속 누적한다)
// ---------------------------------------------------------
#define EVENT_LOG_FILE      "otg_events.log"

void LogEvent(const char* reason)
{
    CString logPath;
    logPath.Format("%s\\%s", GetMmCamStartPath(), EVENT_LOG_FILE);

    CTime   now = CTime::GetCurrentTime();
    CString line;
    line.Format(_T("%04d-%02d-%02d %02d:%02d:%02d  pid=%lu  %s\n"),
        now.GetYear(), now.GetMonth(), now.GetDay(),
        now.GetHour(), now.GetMinute(), now.GetSecond(),
        GetCurrentProcessId(), reason);

    CStdioFile    file;
    CFileException ex;
    if (file.Open(logPath,
        CFile::modeWrite | CFile::modeCreate | CFile::modeNoTruncate | CFile::typeText, &ex))
    {
        file.SeekToEnd();
        file.WriteString(line);
        file.Close();
    }
}

// ---------------------------------------------------------
// 상태 레벨
// ---------------------------------------------------------
void CMmCammonitoringDlg::SetStatusLevel(int level)
{
    if (level < STATUS_OK || level > STATUS_ERROR) return;
    if (m_nStatusLevel != level)
    {
        m_nStatusLevel = level;
        m_lblSign.Invalidate();
    }
}

HBRUSH CMmCammonitoringDlg::OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor)
{
    HBRUSH hbr = CDialogEx::OnCtlColor(pDC, pWnd, nCtlColor);

    // 프로세스 행 라벨: 검정 고정
    for (size_t i = 0; i < m_labels.size(); ++i)
    {
        if (m_labels[i] == nullptr) continue;
        if (pWnd->GetSafeHwnd() != m_labels[i]->GetSafeHwnd()) continue;

        pDC->SetTextColor(PROC_ROW_TEXT_COLOR);
        pDC->SetBkMode(TRANSPARENT);

        // 여기서 돌려준 브러시로 컨트롤이 자기 배경을 지운다.
        // NULL_BRUSH를 주면 지우기가 생략되어 'PID 4000' 위에 이전 '중지됨'이
        // 그대로 남는다. 텍스트가 바뀌는 라벨이므로 기본 배경 브러시를 그대로 쓴다.
        return hbr;
    }


    if (pWnd->GetSafeHwnd() == m_lblSign.GetSafeHwnd())
    {
        COLORREF color;
        switch (m_nStatusLevel)
        {
        case STATUS_OK:    color = RGB(0, 180, 0); break;
        case STATUS_WARN:  color = RGB(255, 200, 0); break;
        case STATUS_ERROR: color = RGB(255, 0, 0); break;
        default:           color = RGB(128, 128, 128); break;
        }
        pDC->SetTextColor(color);
        pDC->SetBkMode(TRANSPARENT);
        return (HBRUSH)GetStockObject(NULL_BRUSH);
    }
    return hbr;
}

// ---------------------------------------------------------
// 타이머 핸들러
// ---------------------------------------------------------
void CMmCammonitoringDlg::OnTimer(UINT_PTR nIDEvent)
{
    // 콤보박스는 직접 입력도 되므로 CBN_SELCHANGE가 오지 않는 경우가 있다.
    // 선택값이 배치해 둔 것과 달라졌으면 그때만 목록을 다시 배치한다.
    const CString selectedID = GetSelectedUserId();
    gUserID = selectedID.GetString();

    if (selectedID != m_shownUserId)
        LayoutProcessRows();

    if (nIDEvent == TIMER_ID_SCAN_STATUS)
    {
        CountPythonProcesses();   // m_lastPyProcesses 갱신 (행 매칭에 필요)
        RefreshProcessRows();     // 행별 PID 확정

        // 표시 개수는 콤보박스에서 고른 user의 것만 센다.
        // 화면의 목록도 그 user의 행만 보이므로 숫자와 목록이 일치한다.
        int procCount = 0;
        for (size_t i = 0; i < m_rowPids.size(); ++i)
        {
            if (i >= m_rowSelected.size()) break;
            if (m_rowSelected[i] && m_rowPids[i] != 0) ++procCount;
        }

        if (procCount >= SCRIPT_COUNT)
            SetStatusLevel(STATUS_OK);
        else if (procCount > 0)
            SetStatusLevel(STATUS_WARN);
        else
            SetStatusLevel(STATUS_ERROR);

        // 프로세스 개수와 DB 상태를 한 줄로 합쳐 표시한다 (개수가 앞)
        CString status;
        status.Format("[%d] processes", procCount);

        CurrentStatus st = read_db_current_status();

        if (!st.valid)
        {
            SetStatusLevel(STATUS_ERROR);
            status += "  |  DB 연결 실패";
        }
        else
        {
            if (strcmp(st.error_code, "0000") == 0)
                SetStatusLevel(STATUS_OK);
            else if (strcmp(st.error_code, "0021") == 0)
                SetStatusLevel(STATUS_ERROR);
            else
                SetStatusLevel(STATUS_WARN);

            CString dbPart;
            dbPart.Format("  |  err=%s  |  %s", st.error_code, st.updated_at);
            status += dbPart;
        }

        m_lbStatus_0.SetWindowText(status);
    }
    else if (nIDEvent == TIMER_ID_BLINK)
    {
        BOOL bshow = !m_lblSign.IsWindowVisible();
        m_lblSign.ShowWindow(bshow);
        SetTimer(TIMER_ID_BLINK, bshow ? SCAN_INTERVAL : SCAN_INTERVAL / 4, nullptr);
    }
    else if (nIDEvent == TIMER_ID_UPTIME)
    {
        ++m_elapsedSeconds;
        int h = m_elapsedSeconds / 3600;
        int m = (m_elapsedSeconds % 3600) / 60;
        int s = m_elapsedSeconds % 60;
        CString t;
        t.Format("%02d:%02d:%02d", h, m, s);
        m_lblTimer.SetWindowText(t);
    }
    else if (nIDEvent == TIMER_ID_RESTART)
    {
        // 기동 시퀀스(약 18초) 도중에 주기가 돌아오면 중첩 실행이 되므로 건너뛴다.
        if (m_bStarting)
        {
            LogEvent("[WARN] 재시작 주기 건너뜀 (기동 중)");
        }
        else
        {
            OnBnClickedKillAll();
            OnBnClickedStartAll();
            KillTimer(TIMER_ID_RESTART);
            SetTimer(TIMER_ID_RESTART, GetRestartIntervalMs(FALSE), nullptr);
        }
    }

    CDialogEx::OnTimer(nIDEvent);
}