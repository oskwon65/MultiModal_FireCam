// Dlg_Retrain.cpp: 재학습 적용 창
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_Retrain.h"
#include "afxdialogex.h"

#include <string>
#include <vector>
#include <algorithm>
#include <cmath>
#include <shellapi.h>     // SHFileOperation - 세대 폴더를 휴지통으로

extern std::string gUserID;
extern const char* GetMmCamStartPath();
extern const char* GetAnacondaRootPub();
extern const char* GetAnacondaEnvPub();
extern std::string ini_read_utf8(const std::string&, const std::string&,
                                 const std::string&, const std::string&);
extern bool ini_write_utf8(const std::string&, const std::string&,
                           const std::string&, const std::string&);
extern bool ini_write_int_utf8(const std::string&, const std::string&,
                               const std::string&, int);

#define WM_LOG_LINE   (WM_APP + 21)
#define WM_RUN_DONE   (WM_APP + 22)

#define ID_BTN_DRY     3001
#define ID_BTN_APPLY   3002
#define ID_LOG_EDIT    3003
#define ID_PROGRESS    3004
#define ID_PNL_BUSY    3006
#define ID_LBL_BUSY    3007
#define ID_LBL_ELAPSED 3008
#define ID_RING        3009
#define ID_CBO_GEN     3010
#define WM_GENMGR_START (WM_APP + 23)

// 가운데 판 크기
#define BUSY_W  460
#define BUSY_H  248

// 눈금 애니메이션은 직접 돌린다.
//
// PBS_MARQUEE 를 써 봤으나 이 환경에서는 흐르지 않았다 - 비주얼 스타일과
// comctl32 판에 걸린다. SetPos 와 SetWindowText 는 어디서든 먹으므로 그
// 둘만으로 움직인다.
#define ANIM_MS      120      // 한 프레임
#define SWEEP_STEP    45      // 총량을 모를 때 한 프레임에 쓸어 가는 양
#define PANEL_BG  RGB(255, 255, 255)   // 판 · 글자 바탕 · 링 바탕

#define RING_D       116      // 링 지름
#define RING_DOTS     24      // 둘레의 점 수
#define RING_COMET     6      // 총량을 모를 때 꼬리 길이
#define TWO_PI    6.283185307179586

// 운용 중인 세대만 검정, 나머지는 진회색. 목록에서 눈이 먼저 가야 하는 줄이
// 하나뿐이기 때문이다.
#define COLOR_LOG_NORMAL  RGB(0, 0, 0)
#define COLOR_LOG_DIM     RGB(105, 105, 105)

// 파이썬은 UTF-8 로 내보내는데(PYTHONIOENCODING=utf-8) 이 빌드는 MBCS 라
// CEdit 가 CP949 를 기대한다. 그대로 넣으면 한글이 깨진다.
//
// UTF-8 을 쓰는 이유는 파이썬 쪽이다. 로그에 '·' 같은 CP949 에 없는 글자가
// 섞여 있어, 출력 인코딩을 CP949 로 두면 파이썬이 UnicodeEncodeError 로
// 죽는다. 받는 쪽에서 바꾸는 편이 안전하다.
//
// 줄 단위로만 부르므로 멀티바이트 문자가 중간에서 잘릴 일은 없다.
// 개행(0x0A)은 UTF-8 에서 언제나 단독 바이트이기 때문이다.
static CStringA Utf8ToAnsi(const char* utf8)
{
    if (!utf8 || !*utf8) return CStringA();

    int wn = MultiByteToWideChar(CP_UTF8, 0, utf8, -1, nullptr, 0);
    if (wn <= 0) return CStringA(utf8);      // UTF-8 이 아니면 그대로 둔다

    CStringW w;
    MultiByteToWideChar(CP_UTF8, 0, utf8, -1, w.GetBuffer(wn), wn);
    w.ReleaseBuffer();

    int an = WideCharToMultiByte(CP_ACP, 0, w, -1, nullptr, 0, nullptr, nullptr);
    if (an <= 0) return CStringA(utf8);

    CStringA a;
    WideCharToMultiByte(CP_ACP, 0, w, -1, a.GetBuffer(an), an, nullptr, nullptr);
    a.ReleaseBuffer();
    return a;
}

// 세대 폴더 이름은 YYYYMMDD_HHMMSS 다. 같은 곳에 기준선 보관함
// (_retired_baseline) 처럼 세대가 아닌 폴더가 있으므로 이름으로 가린다.
static bool IsGenStamp(const char* n)
{
    if (!n || strlen(n) != 15) return false;
    for (int i = 0; i < 15; ++i)
    {
        if (i == 8) { if (n[i] != '_') return false; }
        else if (n[i] < '0' || n[i] > '9') return false;
    }
    return true;
}

IMPLEMENT_DYNAMIC(CDlg_Retrain, CDialogEx)

CDlg_Retrain::CDlg_Retrain(CWnd* pParent /*=nullptr*/)
    : CDialogEx(IDD_DLG_RETRAIN, pParent)
{
}

CDlg_Retrain::~CDlg_Retrain()
{
}

void CDlg_Retrain::DoDataExchange(CDataExchange* pDX)
{
    CDialogEx::DoDataExchange(pDX);
}

BEGIN_MESSAGE_MAP(CDlg_Retrain, CDialogEx)
    ON_BN_CLICKED(ID_BTN_DRY, &CDlg_Retrain::OnBnClickedDryRun)
    ON_BN_CLICKED(ID_BTN_APPLY, &CDlg_Retrain::OnBnClickedApply)
    ON_MESSAGE(WM_GENMGR_START, &CDlg_Retrain::OnGenMgrStart)
    ON_MESSAGE(WM_LOG_LINE, &CDlg_Retrain::OnLogLine)
    ON_MESSAGE(WM_RUN_DONE, &CDlg_Retrain::OnRunDone)
    ON_WM_DESTROY()
    ON_WM_TIMER()
    ON_WM_DRAWITEM()
    ON_WM_CTLCOLOR()
END_MESSAGE_MAP()

//---------------------------------------------------------

BOOL CDlg_Retrain::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    // 창 안의 글자를 모두 같은 크기로 둔다. 안내와 로그 크기가 다르면
    // 안내가 곁다리처럼 보이는데, 여기서는 그 안내가 핵심이다.
    //
    // 프로그램 전체 공통 크기(UI_FONT_SIZE).
    m_font.CreateFont(UI_FONT_SIZE, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    // 로그도 안내와 같은 글꼴·같은 크기다. 가변폭이라 감도 시험 표의 열이
    // 정확히 맞지는 않지만, 파이썬 쪽에서 자리수를 맞춰 찍고 있어 크게
    // 어긋나지는 않는다.
    m_fontMono.CreateFont(UI_FONT_SIZE, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    // RichEdit 을 쓰려면 먼저 DLL 을 올려야 한다. 이걸 빠뜨리면 Create 가
    // 조용히 실패하고 로그 칸이 아예 안 보인다.
    AfxInitRichEdit2();

    CRect rc;
    GetClientRect(&rc);
    const int M = 12;
    const int btnW = 128, btnH = 32;
    const int btnWrun = 176;          // [재학습 적용] 은 글자가 길어 더 넓다
    const int headH = 84, stateH = 28;

    m_lblHead.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, M, rc.right - M, M + headH), this);

    // 위에서부터 쌓는다. 단추가 먼저고 로그가 그 아래다.
    //
    // 로그는 예전에 창 바닥까지 찼다. 읽는 것은 대개 끝 몇 줄이고, 실행
    // 중에는 가운데 판이 그 위를 덮는다. 절반으로 줄이고 창도 그만큼
    // 줄인다 - 빈자리를 남기면 고장으로 보인다.
    const int oldLogH = (rc.bottom - M - btnH - 6 - stateH - 8)
                        - (M + headH + 4);
    const int logH    = (oldLogH > 240) ? oldLogH / 2 : 200;

    const int yBtnTop   = M + headH + 8;
    // 동적구성 · 기여 문턱 줄은 [설정] 창으로, 자동 재학습 줄은 [자동학습 관리]
    // 창으로 옮겼다. 단추 줄 바로 아래가 상태줄이다.
    const int yStateTop = yBtnTop + btnH + 8;
    const int yLogTop   = yStateTop + stateH + 8;
    const int yLogBot   = yLogTop + logH;

    // 진행 판은 로그 칸 안에 가운데로 놓는다. 로그 아래로 내리면 창이
    // 그만큼 길어져 표식이 너무 멀어진다.
    int yBusyTop = yLogTop + (logH - BUSY_H) / 2;
    if (yBusyTop < yLogTop + 4) yBusyTop = yLogTop + 4;

    // 평소에는 상태줄까지만 보인다. 세대 목록은 [설정] 의 [학습모델관리] 로, 자동 재학습
    // 이력은 [자동학습 관리] 로 옮겨 로그 칸에 적을 것이 없다. 예행연습 · 재학습
    // 적용 · 되돌리기를 돌릴 때만 창을 늘려 진행 판과 파이썬 출력을 보인다.
    m_cliCompact = yStateTop + stateH + M;
    m_cliFull    = yLogBot + M;

    // WS_CLIPSIBLINGS 가 없으면, 줄이 들어와 다시 칠할 때마다 위에 떠 있는
    // 진행 판과 그 글자까지 덮는다.
    m_edLog.Create(WS_CHILD | WS_CLIPSIBLINGS          // 돌릴 때만 보인다
        | WS_BORDER | WS_VSCROLL | WS_HSCROLL
        | ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY,
        CRect(M, yLogTop, rc.right - M, yLogBot),
        this, ID_LOG_EDIT);

    // RichEdit 은 판에 따라 읽기전용이면 배경을 회색으로 칠한다. 그러면
    // 진회색 글자가 배경에 묻는다. 흰색으로 못 박는다.
    m_edLog.SetBackgroundColor(FALSE, RGB(255, 255, 255));

    // 가운데 진행 판. 로그 위에 뜨므로 로그보다 뒤에 만든다 - 나중에 만든
    // 자식이 z 순서에서 위로 온다.
    //
    // 자식 컨트롤의 ID 는 서로 달라야 한다. 앞서 로그와 진행바에 모두 0 을
    // 줘서 진행바가 화면에 나오지 않았다.
    const int bx0 = (rc.Width() - BUSY_W) / 2;
    const int by0 = yBusyTop;

    // 테두리를 두지 않는다. 뒤의 로그도 흰 바탕이라, 선을 그으면 표식이
    // 아니라 상자가 먼저 보인다.
    //
    // WS_CLIPSIBLINGS 가 없으면 이 판이 위에 있는 글자까지 덮어 칠한다.
    // 타이머가 매번 다시 쓰는 줄은 곧 되살아나지만, 한 번만 쓰는 안내 줄은
    // 그대로 사라진다.
    m_pnlBusy.Create("", WS_CHILD | WS_CLIPSIBLINGS | SS_WHITERECT,
        CRect(bx0, by0, bx0 + BUSY_W, by0 + BUSY_H), this, ID_PNL_BUSY);

    // 링을 위에 두고 그 아래로 말·눈금·단계를 쌓는다. 경과 시간은 링
    // 가운데에 있어 따로 줄을 차지하지 않는다.
    m_ring.Create("", WS_CHILD | WS_CLIPSIBLINGS | SS_OWNERDRAW,
        CRect(bx0 + (BUSY_W - RING_D) / 2, by0 + 18,
              bx0 + (BUSY_W + RING_D) / 2, by0 + 18 + RING_D),
        this, ID_RING);

    m_lblBusy.Create("", WS_CHILD | WS_CLIPSIBLINGS | SS_CENTER,
        CRect(bx0 + 16, by0 + 146, bx0 + BUSY_W - 16, by0 + 178),
        this, ID_LBL_BUSY);

    m_progress.Create(WS_CHILD | WS_CLIPSIBLINGS | PBS_SMOOTH,
        CRect(bx0 + 40, by0 + 184, bx0 + BUSY_W - 40, by0 + 202),
        this, ID_PROGRESS);
    m_progress.SetRange32(0, 1000);

    // 눈금 아래 줄은 시작할 때 적은 안내를 그대로 둔다. 몇 분 걸리는
    // 일이라, 기다려도 되는지를 판에서 바로 알 수 있어야 한다.
    m_lblElapsed.Create("", WS_CHILD | WS_CLIPSIBLINGS | SS_CENTER,
        CRect(bx0 + 16, by0 + 210, bx0 + BUSY_W - 16, by0 + 238),
        this, ID_LBL_ELAPSED);

    m_brPanel.CreateSolidBrush(PANEL_BG);

    // 링 가운데 시간은 더 크고 굵게 - 이 판에서 제일 먼저 눈에 와야 한다.
    m_fontRing.CreateFont(UI_FONT_SIZE + 10, 0, 0, 0, FW_BOLD, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    m_lblState.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, yStateTop, rc.right - M, yStateTop + stateH),
        this);

    // 단추 줄. 왼쪽부터 [예행연습] [재학습 적용]. 하는 순서대로 놓는다.
    // [닫기] 는 두지 않는다 - 창의 X 가 같은 일을 한다(OnCancel 이 실행 중이면 막는다).
    int bx = M;
    m_btnDry.Create("예행연습", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, yBtnTop, bx + btnW, yBtnTop + btnH), this, ID_BTN_DRY);
    bx += btnW + 8;
    m_btnApply.Create("재학습 적용", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, yBtnTop, bx + btnWrun, yBtnTop + btnH), this, ID_BTN_APPLY);




    SetFont(&m_font);
    SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font.GetSafeHandle(), TRUE);
    m_edLog.SetFont(&m_fontMono);


    // [재학습 적용] 이 왜 꺼져 있는지 화면에 적어 둔다. 눌리지 않는 버튼을 두고
    // 설명이 없으면 고장으로 오해한다.
    CStringA head;
    head.Format("[%s]  재학습은 운용 모델을 바꿉니다. 먼저 [예행연습] 으로 결과를 확인하십시오.\r\n"
                "[재학습 적용] 은 예행연습이 [판정] 승격 을 낸 경우에만 "
                "켜집니다.\r\n"
                "보관 세대로 되돌리거나 지우는 것은 [설정] 창의 [학습모델관리] 에서 합니다.",
                gUserID.c_str());
    m_lblHead.SetWindowTextA(head);

    // 되돌리기에 쓸 세대 목록만 채운다. 화면에 늘어놓지는 않는다.
    ScanGenerations();
    FillGenCombo();

    SetButtons();
    m_lblState.SetWindowTextA("");

    // 컨트롤을 다 만든 뒤에 줄인다. 먼저 줄이면 GetClientRect 가 바뀌어
    // 배치가 어긋난다. 진행 판 자리는 띄울 때 늘려서 낸다.
    SetClientHeight(m_cliCompact);

    CenterWindow(GetParent());

    // [설정] 창의 [학습모델관리] 로 열렸으면 창이 뜬 뒤 바로 관리 창을 띄운다.
    if (m_genMgrOnly) PostMessage(WM_GENMGR_START);
    return TRUE;
}

// [설정] 창의 [학습모델관리] 로 열린 경우.
//
// 되돌리기는 진행 판과 로그가 있는 이 창에서 돌아야 한다. 그래서 관리 창만
// 따로 떼지 않고 이 창을 띄운 채 관리 창을 연다. 되돌리기를 시작하지 않았으면
// 이 창도 함께 닫는다.
LRESULT CDlg_Retrain::OnGenMgrStart(WPARAM, LPARAM)
{
    OnBnClickedGenDelete();
    if (!m_bRunning) EndDialog(IDCANCEL);
    return 0;
}

//---------------------------------------------------------

std::string CDlg_Retrain::UserPath() const
{
    return std::string(GetMmCamStartPath()) + "users\\" + gUserID + "\\";
}

std::vector<std::string> CDlg_Retrain::ListGenerations() const
{
    std::vector<std::string> out;
    const std::string pat = UserPath() + "model_generations\\*";

    WIN32_FIND_DATAA fd = {};
    HANDLE h = FindFirstFileA(pat.c_str(), &fd);
    if (h == INVALID_HANDLE_VALUE) return out;
    do
    {
        if ((fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) &&
            IsGenStamp(fd.cFileName))
            out.push_back(fd.cFileName);
    } while (FindNextFileA(h, &fd));
    FindClose(h);

    std::sort(out.begin(), out.end());
    return out;
}

// 운용에 올라간 세대를 기록된 순서대로. 연달아 같은 것은 하나로 본다.
//
// generation_history.txt 한 줄은  언제<탭>세대<탭>어떻게  이고 '#' 로
// 시작하는 줄은 주석이다.
std::vector<std::string> CDlg_Retrain::ServedGenerations() const
{
    std::vector<std::string> out;

    CStdioFile f;
    if (!f.Open((UserPath() + "generation_history.txt").c_str(),
                CFile::modeRead | CFile::typeText))
        return out;

    CStringA line;
    while (f.ReadString(line))
    {
        line.Trim();
        if (line.IsEmpty() || line[0] == '#') continue;

        // 둘째 칸이 세대다.
        int pos = 0;
        CStringA tok = line.Tokenize("\t", pos);          // 언제
        if (pos < 0) continue;
        tok = line.Tokenize("\t", pos);                   // 세대
        tok.Trim();
        if (!IsGenStamp(tok)) continue;

        if (out.empty() || tok.Compare(out.back().c_str()) != 0)
            out.push_back((LPCSTR)tok);
    }
    f.Close();
    return out;
}

// 보고서 한 줄에서 "열쇠말 다음 값" 을 집는다. 값은 공백 둘에서 끊는다 -
// 한 줄에 여러 항목이 공백 둘로 나뉘어 적혀 있다.
static CStringA FieldAfter(const CStringA& line, const char* key)
{
    const int at = line.Find(key);
    if (at < 0) return CStringA();

    int i = at + (int)strlen(key);
    while (line[i] == ' ') ++i;

    int j = i;
    while (line[j] != 0 && !(line[j] == ' ' && line[j + 1] == ' ')) ++j;

    CStringA v = line.Mid(i, j - i);
    v.Trim();
    return v;
}

// 승격 기록에서 그 세대가 만들어질 무렵 운용 중이던 세대를 찾는다.
//
// 옛 보고서에는 기준 세대가 적혀 있지 않다. 기록의 시각과 견주면 알 수
// 있다 - 그 세대 이름(YYYYMMDD_HHMMSS)보다 앞선 마지막 승격이 그것이다.
CStringA CDlg_Retrain::IncumbentAt(const char* stamp) const
{
    CStdioFile f;
    if (!f.Open((UserPath() + "generation_history.txt").c_str(),
                CFile::modeRead | CFile::typeText))
        return CStringA();

    // 기록의 시각은 "YYYY-MM-DD HH:MM:SS" 다. 세대 이름 형식으로 바꿔 견준다.
    CStringA best, line;
    while (f.ReadString(line))
    {
        line.Trim();
        if (line.IsEmpty() || line[0] == '#') continue;

        int pos = 0;
        CStringA when = line.Tokenize("\t", pos);
        if (pos < 0) continue;
        CStringA who = line.Tokenize("\t", pos);
        when.Trim(); who.Trim();
        if (when.GetLength() < 19 || !IsGenStamp(who)) continue;

        CStringA key;
        key.Format("%s%s%s_%s%s%s",
                   (LPCSTR)when.Mid(0, 4), (LPCSTR)when.Mid(5, 2),
                   (LPCSTR)when.Mid(8, 2), (LPCSTR)when.Mid(11, 2),
                   (LPCSTR)when.Mid(14, 2), (LPCSTR)when.Mid(17, 2));

        if (key.Compare(stamp) < 0) best = who;   // 그 세대보다 앞선 것
        else break;                                // 기록은 시간 순이다
    }
    f.Close();
    return best;
}

// 세대 하나의 보고서를 읽는다.
CDlg_Retrain::GenMeta CDlg_Retrain::ReadGenMeta(const char* stamp) const
{
    GenMeta m;

    const std::string path =
        UserPath() + "model_generations\\" + stamp + "\\report.txt";

    CStdioFile f;
    if (f.Open(path.c_str(), CFile::modeRead | CFile::typeText))
    {
        CStringA line;
        while (f.ReadString(line))
        {
            // report.txt 는 UTF-8 이고 이 빌드는 MBCS 다.
            const CStringA t = Utf8ToAnsi(line);

            // 새 꼴과 옛 꼴을 모두 찾는다.
            int at = t.Find("평균점수");
            if (at < 0) at = t.Find("정상 평균 점수");
            if (at >= 0 && m.score.IsEmpty())
            {
                int i = at;
                while (t[i] != 0 && (t[i] < '0' || t[i] > '9')) ++i;
                const double v = atof((LPCSTR)t + i);
                if (v > 0.0) m.score.Format("%.3f", v);
                continue;
            }

            if (m.base.IsEmpty())     m.base     = FieldAfter(t, "기준 세대");
            if (m.contrib.IsEmpty())  m.contrib  = FieldAfter(t, "기여");
            if (m.baseDate.IsEmpty()) m.baseDate = FieldAfter(t, "계산기준일");
            if (m.samples.IsEmpty())  m.samples  = FieldAfter(t, "표본");
            if (m.period.IsEmpty())   m.period   = FieldAfter(t, "기간");
            if (m.cells.IsEmpty())    m.cells    = FieldAfter(t, "칸");
            if (m.hours.IsEmpty())    m.hours    = FieldAfter(t, "시간대");
        }
        f.Close();
    }

    // 옛 보고서에는 기준 세대가 없다. 승격 기록에서 찾아 본다.
    if (m.base.IsEmpty()) m.base = IncumbentAt(stamp);

    return m;
}

// 그 세대가 학습 직후에 낸 정상 평균 점수. report.txt 에서 읽는다.
//
// 감도 시험의 "평균점수" 줄에서 앞의 값(후보)을 쓴다. 뒤의 값은 괄호 안의
// 현재 모델 것이라 세대의 성질이 아니다.
//
// 2026-09-29 에 보고서 꼴이 "[평가] 평균점수 0.966 (현재 0.791) 통과" 로
// 바뀌었다. 옛 세대의 report.txt 는 "정상 평균 점수" 이므로 둘 다 찾는다.
//
// 물러나는 운용 모델을 떠 둔 세대에는 시험표가 없다. 그때는 빈 문자열이다.
CStringA CDlg_Retrain::GenScore(const char* stamp) const
{
    const std::string path =
        UserPath() + "model_generations\\" + stamp + "\\report.txt";

    CStdioFile f;
    if (!f.Open(path.c_str(), CFile::modeRead | CFile::typeText))
        return CStringA();

    CStringA line, out;
    while (f.ReadString(line))
    {
        // report.txt 는 UTF-8 이고 이 빌드는 MBCS 다. 줄마다 바꾸지 않으면
        // 한글로 찾을 수 없다.
        const CStringA t = Utf8ToAnsi(line);
        int at = t.Find("평균점수");
        if (at < 0) at = t.Find("정상 평균 점수");
        if (at < 0) continue;

        int i = at;
        while (t[i] != 0 && (t[i] < '0' || t[i] > '9')) ++i;
        const double cand = atof((LPCSTR)t + i);
        if (cand > 0.0) out.Format("%.3f", cand);
        break;
    }
    f.Close();
    return out;
}

// 되돌릴 대상을 정한다. 폴더 순서가 아니라 승격 기록을 거슬러 간다.
void CDlg_Retrain::ScanGenerations()
{
    m_curGen = ""; m_backGen = ""; m_backWhy = "";

    const std::vector<std::string> gens = ListGenerations();
    if (gens.empty())
    {
        m_backWhy = "보관된 세대가 없습니다. 재학습을 한 번도 하지 않았습니다.";
        return;
    }

    CStdioFile f;
    if (f.Open((UserPath() + "current_generation.txt").c_str(),
               CFile::modeRead | CFile::typeText))
    {
        CStringA line;
        if (f.ReadString(line)) { line.Trim(); m_curGen = line; }
        f.Close();
    }

    const std::vector<std::string> served = ServedGenerations();
    if (served.empty())
    {
        m_backWhy = "승격 기록(generation_history.txt)이 없어 어느 세대가 "
                    "실제로 운용되었는지 알 수 없습니다.";
        return;
    }
    if (served.size() < 2)
    {
        m_backWhy.Format("운용에 올라간 세대가 %s 하나뿐입니다. "
                         "되돌릴 곳이 없습니다.", served.back().c_str());
        return;
    }

    const std::string prev = served[served.size() - 2];

    // 기록이 가리키는 세대가 실제로 남아 있는지 본다. 오래된 세대는
    // 정리될 수 있다.
    bool onDisk = false;
    for (size_t k = 0; k < gens.size(); ++k)
        if (prev == gens[k]) { onDisk = true; break; }
    if (!onDisk)
    {
        m_backWhy.Format("직전에 운용한 세대 %s 의 폴더가 남아 있지 "
                         "않습니다.", prev.c_str());
        return;
    }

    m_backGen = prev.c_str();
}

// 어디로 되돌릴 수 있는지 로그 칸에 적는다. 창을 열면 로그가 비어 있으므로
// 따로 자리를 내지 않아도 된다.
//
// 운용에 올라간 세대만 보인다. 나머지는 보여 줘도 할 수 있는 것이 없다 -
// 되돌릴 대상이 아니다. 몇 개가 있는지만 한 줄로 적는다.
//
// 예행연습은 이제 세대를 만들지 않으므로, 여기 걸리는 것은 재학습을 실제로
// 돌렸으나 감도 시험에서 막힌 후보다.
// 고를 수 있는 세대를 채운다. 폴더가 남아 있고, 지금 돌고 있는 것이 아닌
// 세대다. [학습모델관리] 창이 이 목록으로 되돌리기와 삭제를 한다.
//
// 최근 것이 앞에 오게 둔다. 대개는 맨 위(직전)를 고르게 된다.
void CDlg_Retrain::FillGenCombo()
{
    m_cboStamps.clear();
    m_cboServed.clear();

    const std::vector<std::string> gens = ListGenerations();
    const std::vector<std::string> served = ServedGenerations();

    // 폴더에 있는 것은 모두 담는다. 승격된 적 없는 것도 고를 수 있어야
    // 한다 - 손으로 옛 산출물을 되돌려 놓는 복구가 실제로 필요했다.
    // 잘못 올려도 다시 되돌리면 되고, 감시는 시작 전에 짝을 대조한다.
    for (int i = (int)gens.size() - 1; i >= 0; --i)
    {
        if (m_curGen.Compare(gens[i].c_str()) == 0) continue;   // 지금 것

        bool wasServed = false;
        for (size_t k = 0; k < served.size(); ++k)
            if (served[k] == gens[i]) { wasServed = true; break; }

        m_cboStamps.push_back(gens[i]);
        m_cboServed.push_back(wasServed);
    }
}

void CDlg_Retrain::SetButtons()
{
    m_btnDry.EnableWindow(!m_bRunning);
    // 예행연습이 '승격' 판정을 낸 뒤에만 실행할 수 있다. 결과를 안 보고
    // 누르는 것을 막는 것이 이 창의 존재 이유다.
    m_btnApply.EnableWindow(!m_bRunning && m_bDryDone && m_bDryPassed);
}

void CDlg_Retrain::SetClientHeight(int cliH)
{
    if (cliH <= 0) return;

    CRect wr, cr;
    GetWindowRect(&wr);
    GetClientRect(&cr);
    if (cr.Height() == cliH) return;

    const int chrome = wr.Height() - cr.Height();
    SetWindowPos(nullptr, 0, 0, wr.Width(), cliH + chrome,
                 SWP_NOMOVE | SWP_NOZORDER);
}

void CDlg_Retrain::ShowProgress(bool bShow)
{
    const int cmd = bShow ? SW_SHOW : SW_HIDE;
    m_pnlBusy.ShowWindow(cmd);
    m_lblBusy.ShowWindow(cmd);
    m_progress.ShowWindow(cmd);
    m_ring.ShowWindow(cmd);
    m_lblElapsed.ShowWindow(cmd);

    if (bShow)
    {
        m_target = m_pos = m_sweep = m_frame = 0;
        m_tickStart = GetTickCount64();
        m_lastElapsed = "";
        m_lastBusy = "";
        m_phaseNote = "";
        m_progress.SetRange32(0, 1000);
        m_progress.SetPos(0);


        // 판을 로그 위로 올린다. z 순서는 만든 차례를 따르지만, 실행을
        // 거듭하면 어긋날 수 있어 띄울 때마다 못 박는다.
        m_pnlBusy.SetWindowPos(&wndTop, 0, 0, 0, 0,
                               SWP_NOMOVE | SWP_NOSIZE);
        m_lblBusy.SetWindowPos(&wndTop, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE);
        m_progress.SetWindowPos(&wndTop, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE);
        m_ring.SetWindowPos(&wndTop, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE);
        m_lblElapsed.SetWindowPos(&wndTop, 0, 0, 0, 0,
                                  SWP_NOMOVE | SWP_NOSIZE);

        // 안내는 z 순서를 정리한 뒤에 쓴다. 먼저 쓰면 판이 올라오면서
        // 덮어 버린다. 실행 내내 그대로 두고 타이머가 건드리지 않는다.
        m_lblElapsed.SetWindowTextA(m_notice);
        m_lblElapsed.Invalidate(FALSE);

        // 첫 프레임을 바로 그린다. 안 그리면 판이 잠깐 비어 보인다.
        AnimateBusy();
        UpdateElapsed();

        if (!m_timer) m_timer = SetTimer(1, ANIM_MS, nullptr);
    }
    else if (m_timer)
    {
        KillTimer(m_timer);
        m_timer = 0;
    }
}

// 단계가 바뀌면 상한을 올린다. 뒤로 가지는 않는다 - 되돌아가는 진행은
// 고장으로 보인다.
void CDlg_Retrain::SetPhase(int permille)
{
    if (permille <= m_target) return;

    // 쓸기에서 눈금으로 처음 넘어갈 때는 0 에서 다시 시작한다. 쓸기 위치는
    // 진행과 아무 상관이 없어 그대로 두면 눈금이 뒤로 가는 것처럼 보인다.
    if (m_target == 0) m_pos = 0;

    m_target = permille;
}

// 눈금과 회전자를 한 칸 옮긴다.
//
// 단계를 읽기 전에는 총량을 모르므로 눈금을 좌우로 쓸어 움직임만 보인다.
// 읽은 뒤에는 그 값으로 다가간다 - 단계 사이에도 조금씩 차올라 멈춘 것처럼
// 보이지 않는다.
void CDlg_Retrain::AnimateBusy()
{
    ++m_frame;

    if (m_target <= 0)
    {
        m_sweep += SWEEP_STEP;
        if (m_sweep > 2000) m_sweep = 0;
        m_progress.SetPos(m_sweep <= 1000 ? m_sweep : 2000 - m_sweep);
    }
    else if (m_pos < m_target)
    {
        m_pos += (m_target - m_pos) / 10 + 1;
        if (m_pos > m_target) m_pos = m_target;
        m_progress.SetPos(m_pos);
    }

    // 링. 점과 가운데 시간을 함께 다시 그린다. 글자 회전자는 없앴다 -
    // 링이 도는데 옆에서 또 돌면 어수선하다.
    if (m_ring.GetSafeHwnd()) m_ring.Invalidate(FALSE);

    // 안내 줄은 한 번만 쓰므로 무엇에 지워지면 돌아오지 않는다. 1초에
    // 한 번 다시 그린다. 글자는 컨트롤이 들고 있어 Invalidate 면 된다.
    if ((m_frame % 8) == 0 && m_lblElapsed.GetSafeHwnd())
        m_lblElapsed.Invalidate(FALSE);
}

// 눈금 위 줄. 경과 시간은 링 가운데에 있으므로 여기에는 무엇을 하는
// 중인지와 얼마나 왔는지를 적는다.
void CDlg_Retrain::UpdateElapsed()
{
    CStringA t = m_busyWhat;

    if (m_target > 0)
    {
        CStringA pct;
        pct.Format("   ·   %d%%", m_target / 10);
        t += pct;
    }
    if (!m_phaseNote.IsEmpty())
    {
        t += "   ·   ";
        t += m_phaseNote;
    }

    if (t != m_lastBusy)
    {
        m_lastBusy = t;
        m_lblBusy.SetWindowTextA(t);
    }
}

// 두 색 사이를 t(0~1) 로 섞는다.
static COLORREF Mix(COLORREF a, COLORREF b, double t)
{
    if (t < 0.0) t = 0.0;
    if (t > 1.0) t = 1.0;
    const int r = (int)(GetRValue(a) + (GetRValue(b) - GetRValue(a)) * t);
    const int g = (int)(GetGValue(a) + (GetGValue(b) - GetGValue(a)) * t);
    const int bb = (int)(GetBValue(a) + (GetBValue(b) - GetBValue(a)) * t);
    return RGB(r, g, bb);
}

// 진행 링.
//
// 점 24개를 둘레에 놓는다. 총량을 모르는 동안에는 밝은 점 여섯이 꼬리를
// 물고 돌고, 단계를 읽으면 진행만큼 점이 켜진다. 켜진 뒤에도 밝은 점
// 하나가 계속 돌아 멈춘 것으로 보이지 않는다.
//
// 가운데에는 경과 시간을 적는다. 이 판에서 제일 먼저 눈에 와야 하는 값이다.
//
// 메모리에 그려 한 번에 옮긴다. 바로 그리면 매 프레임 깜빡인다.
// 판 위 글자의 바탕을 판과 같은 흰색으로 돌려준다.
//
// 정적 컨트롤은 그릴 때 부모에게 바탕 브러시를 물어본다. 그냥 두면
// 대화상자 색(회색)을 받아, 흰 판 위에 글자 크기만 한 회색 네모가 생긴다.
HBRUSH CDlg_Retrain::OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor)
{
    if (nCtlColor == CTLCOLOR_STATIC && pWnd)
    {
        const int id = pWnd->GetDlgCtrlID();
        if (id == ID_LBL_BUSY || id == ID_LBL_ELAPSED ||
            id == ID_PNL_BUSY || id == ID_RING)
        {
            pDC->SetBkMode(TRANSPARENT);
            pDC->SetTextColor(RGB(0x1A, 0x24, 0x35));
            return (HBRUSH)m_brPanel.GetSafeHandle();
        }
    }
    return CDialogEx::OnCtlColor(pDC, pWnd, nCtlColor);
}

void CDlg_Retrain::OnDrawItem(int nIDCtl, LPDRAWITEMSTRUCT lpDIS)
{
    if (nIDCtl != ID_RING || !lpDIS)
    {
        CDialogEx::OnDrawItem(nIDCtl, lpDIS);
        return;
    }

    CDC* pDC = CDC::FromHandle(lpDIS->hDC);
    const int w = lpDIS->rcItem.right - lpDIS->rcItem.left;
    const int h = lpDIS->rcItem.bottom - lpDIS->rcItem.top;
    if (w <= 8 || h <= 8) return;

    CDC mem;
    if (!mem.CreateCompatibleDC(pDC)) return;
    CBitmap bmp;
    if (!bmp.CreateCompatibleBitmap(pDC, w, h)) return;
    CBitmap* pOldBmp = mem.SelectObject(&bmp);

    mem.FillSolidRect(0, 0, w, h, PANEL_BG);

    const COLORREF DIM  = RGB(0xDD, 0xE2, 0xE9);   // 꺼진 점
    const COLORREF DONE = RGB(0x2A, 0x9D, 0x8F);   // 지나온 점
    const COLORREF HEAD = RGB(0xE4, 0x57, 0x2E);   // 도는 점

    const int cx = w / 2, cy = h / 2;
    const int dotR = 5;
    const int R = (w < h ? w : h) / 2 - dotR - 3;

    const int head = (m_frame / 2) % RING_DOTS;
    const int lit = (m_target > 0) ? (m_pos * RING_DOTS + 500) / 1000 : 0;

    CBrush* pOldBr = nullptr;
    CPen penNone(PS_NULL, 0, (COLORREF)0);
    CPen* pOldPen = mem.SelectObject(&penNone);

    for (int i = 0; i < RING_DOTS; ++i)
    {
        const double a = (double)i / RING_DOTS * TWO_PI - TWO_PI / 4.0;
        const int x = cx + (int)(R * cos(a));
        const int y = cy + (int)(R * sin(a));

        // head 에서 뒤로 몇 칸인가
        const int back = (head - i + RING_DOTS) % RING_DOTS;

        COLORREF c = DIM;
        if (m_target > 0)
        {
            if (i < lit) c = DONE;
            if (back == 0) c = HEAD;                  // 도는 점 하나
        }
        else if (back < RING_COMET)
        {
            // 꼬리는 뒤로 갈수록 옅어진다
            c = Mix(HEAD, DIM, (double)back / RING_COMET);
        }

        // 도는 점은 조금 크게 - 색만으로는 덜 보인다
        const int rr = (back == 0) ? dotR + 1 : dotR;
        CBrush br(c);
        CBrush* prev = mem.SelectObject(&br);
        if (!pOldBr) pOldBr = prev;
        mem.Ellipse(x - rr, y - rr, x + rr, y + rr);
        mem.SelectObject(prev);
    }

    // 가운데 경과 시간
    const ULONGLONG ms = m_tickStart ? (GetTickCount64() - m_tickStart) : 0;
    const unsigned sec = (unsigned)(ms / 1000);
    CStringA t;
    if (sec < 3600) t.Format("%u:%02u", sec / 60, sec % 60);
    else            t.Format("%u:%02u:%02u", sec / 3600, (sec / 60) % 60,
                             sec % 60);

    CFont* pOldFont = mem.SelectObject(&m_fontRing);
    mem.SetBkMode(TRANSPARENT);
    mem.SetTextColor(RGB(0x1A, 0x24, 0x35));
    CRect rcT(0, 0, w, h);
    mem.DrawTextA(t, &rcT, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    mem.SelectObject(pOldFont);

    pDC->BitBlt(lpDIS->rcItem.left, lpDIS->rcItem.top, w, h, &mem, 0, 0,
                SRCCOPY);

    if (pOldBr) mem.SelectObject(pOldBr);
    mem.SelectObject(pOldPen);
    mem.SelectObject(pOldBmp);
}

void CDlg_Retrain::OnTimer(UINT_PTR nIDEvent)
{
    if (nIDEvent == 1 && m_bRunning)
    {
        AnimateBusy();
        UpdateElapsed();
    }
    CDialogEx::OnTimer(nIDEvent);
}

void CDlg_Retrain::AppendLog(const char* text)
{
    AppendLog(text, COLOR_LOG_NORMAL);
}

// 넣은 뒤에 그 범위만 물들인다. 빈 선택에 서식을 걸고 나중에 넣는 방식은
// RichEdit 판에 따라 먹지 않는 경우가 있다.
//
// 위치는 GetWindowTextLength() 로 잡으면 안 된다. 이 빌드는 MBCS 라 그것은
// **바이트 수** 를 주는데 SetSel() 은 **문자 위치** 를 받는다. 한글 한 자가
// CP949 에서 2바이트라 줄마다 어긋나고, 물들일 범위가 오른쪽으로 밀려 줄
// 앞부분이 색을 못 받는다. 날짜(yyyymmdd)가 검게 남은 것이 그 때문이다.
//
// 그래서 캐럿을 끝으로 보내고 GetSel() 로 문자 위치를 되묻는다.
void CDlg_Retrain::AppendLog(const char* text, COLORREF color)
{
    const long END = 0x7FFFFFFF;      // 끝으로. RichEdit 이 잘라서 맞춘다.
    long n0 = 0, n1 = 0, ignored = 0;

    m_edLog.SetSel(END, END);
    m_edLog.GetSel(n0, ignored);

    m_edLog.ReplaceSel(text);

    m_edLog.SetSel(END, END);
    m_edLog.GetSel(n1, ignored);

    if (n1 > n0)
    {
        m_edLog.SetSel(n0, n1);
        CHARFORMAT cf = {};
        cf.cbSize = sizeof(cf);
        cf.dwMask = CFM_COLOR;
        cf.crTextColor = color;
        m_edLog.SetSelectionCharFormat(cf);
        m_edLog.SetSel(n1, n1);
    }
}

//---------------------------------------------------------

UINT __cdecl CDlg_Retrain::ThreadProc(LPVOID param)
{
    RunCtx* ctx = reinterpret_cast<RunCtx*>(param);
    CDlg_Retrain* dlg = ctx->dlg;

    SECURITY_ATTRIBUTES sa = {};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = TRUE;

    HANDLE hRead = nullptr, hWrite = nullptr;
    DWORD exitCode = (DWORD)-1;

    if (!CreatePipe(&hRead, &hWrite, &sa, 0))
    {
        CStringA* m = new CStringA("[ERROR] 파이프를 만들지 못했습니다.\r\n");
        dlg->PostMessage(WM_LOG_LINE, 0, (LPARAM)m);
        dlg->PostMessage(WM_RUN_DONE, exitCode, 0);
        delete ctx;
        return 1;
    }
    SetHandleInformation(hRead, HANDLE_FLAG_INHERIT, 0);

    STARTUPINFOA si = {};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.hStdOutput = hWrite;
    si.hStdError = hWrite;
    si.wShowWindow = SW_HIDE;

    PROCESS_INFORMATION pi = {};
    std::string cmd = ctx->cmd;

    if (!CreateProcessA(nullptr, &cmd[0], nullptr, nullptr, TRUE,
                        CREATE_NO_WINDOW, nullptr, GetMmCamStartPath(), &si, &pi))
    {
        CStringA* m = new CStringA;
        m->Format("[ERROR] 실행하지 못했습니다 (err=%lu)\r\n", GetLastError());
        dlg->PostMessage(WM_LOG_LINE, 0, (LPARAM)m);
        CloseHandle(hWrite); CloseHandle(hRead);
        dlg->PostMessage(WM_RUN_DONE, exitCode, 0);
        delete ctx;
        return 1;
    }

    // 쓰기 쪽을 부모가 쥐고 있으면 자식이 끝나도 ReadFile 이 안 끝난다.
    CloseHandle(hWrite);
    dlg->m_hProc = pi.hProcess;

    char buf[4096];
    DWORD got = 0;
    std::string pending;

    while (ReadFile(hRead, buf, sizeof(buf) - 1, &got, nullptr) && got > 0)
    {
        buf[got] = 0;
        pending += buf;

        // 줄 단위로 넘긴다. 줄 중간에서 끊어 보내면 화면이 지저분해진다.
        size_t nl;
        while ((nl = pending.find('\n')) != std::string::npos)
        {
            std::string line = pending.substr(0, nl + 1);
            pending.erase(0, nl + 1);
            if (!line.empty() && line[line.size() - 1] == '\n' &&
                (line.size() < 2 || line[line.size() - 2] != '\r'))
                line.insert(line.size() - 1, "\r");
            dlg->PostMessage(WM_LOG_LINE, 0,
                             (LPARAM)new CStringA(Utf8ToAnsi(line.c_str())));
        }
    }
    if (!pending.empty())
        dlg->PostMessage(WM_LOG_LINE, 0,
                         (LPARAM)new CStringA(Utf8ToAnsi(pending.c_str())));

    WaitForSingleObject(pi.hProcess, INFINITE);
    GetExitCodeProcess(pi.hProcess, &exitCode);

    CloseHandle(hRead);
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    dlg->m_hProc = nullptr;

    dlg->PostMessage(WM_RUN_DONE, exitCode, (LPARAM)ctx->kind);
    delete ctx;
    return 0;
}

//---------------------------------------------------------

void CDlg_Retrain::Run(RunKind kind)
{
    if (m_bRunning) return;

    if (gUserID.empty())
    {
        AfxMessageBox(_T("현장(user)이 선택되지 않았습니다."));
        return;
    }

    const bool dryRun = (kind == RUN_DRY);
    const bool back = (kind == RUN_ROLLBACK);

    // conda 환경을 활성화한 뒤 실행한다. 감시 프로세스를 띄울 때와 같은
    // 방식이라, 파이썬 환경이 어긋나 생기는 문제가 따로 생기지 않는다.
    // 되돌리기는 세대를 직접 지정한다. 무인자 --rollback 도 운용 중인 것의
    // 앞을 고르지만, 확인 창에 적어 보인 것과 실제로 올라가는 것이 반드시
    // 같아야 한다.
    CStringA extra;
    if (dryRun)      extra = " --dry-run";
    else if (back)   extra = " --rollback " + m_backGen;

    CStringA cmd;
    cmd.Format("cmd.exe /c call \"%sScripts\\activate.bat\" %s "
               "&& cd /d \"%s\" && set PYTHONIOENCODING=utf-8 "
               "&& python retrain\\nightly_retrain.py \"%s\"%s",
               GetAnacondaRootPub(), GetAnacondaEnvPub(),
               GetMmCamStartPath(), gUserID.c_str(),
               (LPCSTR)extra);

    m_edLog.SetWindowTextA("");

    // 돌릴 때만 로그 칸을 보이고 창을 늘린다. 진행 판이 그 칸 가운데에 뜬다.
    SetClientHeight(m_cliFull);
    m_edLog.ShowWindow(SW_SHOW);

    // 시작 인사는 로그에 남기지 않는다.
    //
    // 가운데 진행 판이 "예행연습 중..." 과 경과 시간을 이미 보여 주고, 곧
    // 파이썬이 제목 줄을 찍는다. 같은 말이 세 번이면 정작 읽을 것이 밀린다.
    // 되돌리기는 진행 판을 띄우지 않으므로 그것만 남긴다.
    if (back)
    {
        CStringA msg;
        msg.Format("%s 세대로 되돌립니다.\r\n\r\n", (LPCSTR)m_backGen);
        AppendLog(msg);
    }

    m_bRunning = true;
    if (dryRun) { m_bDryDone = false; m_bDryPassed = false; }

    m_busyWhat = back   ? "되돌리는 중" :
                 dryRun ? "예행연습 중" : "재학습 중";
    m_notice = dryRun ? "예행연습을 시작합니다. 몇 분 걸립니다."
                      : "재학습을 시작합니다. 몇 분 걸립니다.";

    // 되돌리기는 파일 몇 개를 옮기고 끝난다. 판을 띄우면 차기도 전에
    // 사라져 오히려 무엇이 일어났는지 알기 어렵다.
    if (!back) ShowProgress(true);

    SetButtons();
    m_lblState.SetWindowTextA(
        back    ? "되돌리는 중..." :
        dryRun  ? "예행연습 중..." :
                  "재학습 중... 끝날 때까지 닫지 마십시오.");

    RunCtx* ctx = new RunCtx{ this, std::string((LPCSTR)cmd), (int)kind };
    CWinThread* th = AfxBeginThread(ThreadProc, ctx);
    m_hThread = th ? th->m_hThread : nullptr;
}

void CDlg_Retrain::OnBnClickedDryRun() { Run(RUN_DRY); }

void CDlg_Retrain::OnBnClickedApply()
{
    if (AfxMessageBox(_T("운용 모델을 새 모델로 바꿉니다.\n\n")
                      _T("감도 회귀 시험을 통과한 경우에만 교체되며,\n")
                      _T("이전 세대는 보관되어 되돌릴 수 있습니다.\n\n")
                      _T("진행할까요?"),
                      MB_YESNO | MB_ICONQUESTION) != IDYES)
        return;
    Run(RUN_APPLY);
}

//---------------------------------------------------------

// 학습모델관리 창. 보관 세대를 골라 되돌리거나 지운다.
//
// 세대가 스무 개를 넘으면 목록에서 고르기 어렵다. 재학습이 오래된
// 것을 열 개만 남기고 정리하지만, 운용에 올라간 적이 있는 것은 지우지 않아
// 그런 세대는 계속 쌓인다(nightly_retrain.save_generation).
//
// 운용 중인 세대는 목록에 넣지 않는다. 그것을 지우면 감시가 시작 전에 짝을
// 대조할 곳이 사라진다(artifact_guard).
//
// 지운 폴더는 휴지통으로 보낸다. 잘못 지웠으면 휴지통에서 되살리면 된다.
//
// 창 틀은 .rc 에 두지 않고 여기서 만든다. 이 창에서만 쓰는 작은 창이다.
#define ID_GD_LIST   3101
#define ID_GD_ALL    3102
#define ID_GD_NONE   3103
#define ID_GD_DEL    3104
#define ID_GD_BACK   3105

class CDlg_GenDelete : public CDialogEx
{
public:
    struct Item
    {
        std::string stamp;
        CStringA    label;     // 목록에 적는 한 줄
        bool        served;    // 운용에 올라간 적 있는가
        bool        isBack;    // 되돌리기의 기본 대상(직전)인가
    };

    CDlg_GenDelete(const std::string& genRoot, const std::vector<Item>& items,
                   const CStringA& live, CFont* font, CFont* mono, CWnd* parent)
        : CDialogEx(), m_root(genRoot), m_items(items), m_live(live),
          m_font(font), m_mono(mono)
    {
        // 빈 창 틀. 크기와 글꼴은 OnInitDialog 에서 정한다.
        m_tpl.assign(64, 0);
        DLGTEMPLATE* t = reinterpret_cast<DLGTEMPLATE*>(m_tpl.data());
        t->style = DS_MODALFRAME | WS_POPUP | WS_CAPTION | WS_SYSMENU;
        t->cx = 300; t->cy = 200;
        WORD* p = reinterpret_cast<WORD*>(t + 1);
        *p++ = 0;                                     // 메뉴 없음
        *p++ = 0;                                     // 기본 창 종류
        const wchar_t* cap = L"\xD559\xC2B5\xBAA8\xB378\xAD00\xB9AC";   // "학습모델관리"
        while (*cap) *p++ = (WORD)*cap++;
        *p++ = 0;
        InitModalIndirect(t, parent);
    }

    bool Deleted() const { return m_deleted > 0; }
    // [되돌리기] 로 닫았으면 고른 세대. 실제 되돌리기는 재학습 창이 한다 -
    // 진행 판과 로그가 거기에 있다.
    const CStringA& RollTo() const { return m_rollTo; }

protected:
    virtual BOOL OnInitDialog() override
    {
        CDialogEx::OnInitDialog();

        const int W = 560, H = 520, M = 12, bH = 32;
        CRect wr(0, 0, W, H);
        AdjustWindowRectEx(&wr, GetStyle(), FALSE, GetExStyle());
        SetWindowPos(nullptr, 0, 0, wr.Width(), wr.Height(),
                     SWP_NOMOVE | SWP_NOZORDER);
        CenterWindow();

        // 지금 운용 중인 세대. 목록에는 없으므로 따로 적는다 - 되돌리거나 지울 때
        // 무엇이 돌고 있는지를 함께 보아야 고를 수 있다.
        m_lblLive.Create(m_live, WS_CHILD | WS_VISIBLE | SS_LEFT,
                         CRect(M, M, W - M, M + 26), this);

        m_list.Create(WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL | WS_TABSTOP
                      | LBS_OWNERDRAWFIXED | LBS_HASSTRINGS | LBS_NOINTEGRALHEIGHT,
                      CRect(M, M + 30, W - M, H - M - bH - 10), this, ID_GD_LIST);

        const int yb = H - M - bH;
        m_btnAll.Create("모두 표시", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                        CRect(M, yb, M + 100, yb + bH), this, ID_GD_ALL);
        m_btnNone.Create("표시 해제", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                         CRect(M + 108, yb, M + 208, yb + bH), this, ID_GD_NONE);
        m_btnClose.Create("닫기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                          CRect(W - M - 100, yb, W - M, yb + bH), this, IDCANCEL);
        m_btnDel.Create("삭제", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                        CRect(W - M - 208, yb, W - M - 108, yb + bH), this, ID_GD_DEL);
        m_btnBack.Create("되돌리기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                         CRect(W - M - 316, yb, W - M - 216, yb + bH), this, ID_GD_BACK);

        if (m_font)
        {
            m_btnBack.SetFont(m_font);
            // 운용 중인 세대는 굵게. 목록 위에서 먼저 눈에 들어와야 한다.
            LOGFONT lf = {};
            m_font->GetLogFont(&lf);
            lf.lfWeight = FW_SEMIBOLD;
            m_fontLive.CreateFontIndirect(&lf);
            m_lblLive.SetFont(&m_fontLive);
            m_btnAll.SetFont(m_font);
            m_btnNone.SetFont(m_font);
            m_btnDel.SetFont(m_font);
            m_btnClose.SetFont(m_font);
        }
        // 세대 이름과 점수가 줄마다 같은 자리에 오도록 고정폭 글꼴을 쓴다.
        if (m_mono) m_list.SetFont(m_mono);
        else if (m_font) m_list.SetFont(m_font);
        m_list.SetItemHeight(0, 22);

        Fill();
        return TRUE;
    }

    void Fill()
    {
        m_list.ResetContent();
        for (size_t i = 0; i < m_items.size(); ++i)
            m_list.AddString(m_items[i].label);

        // 직전 세대를 미리 고른다. 되돌리기는 대개 그리로 간다.
        int sel = m_items.empty() ? -1 : 0;
        for (size_t i = 0; i < m_items.size(); ++i)
            if (m_items[i].isBack) { sel = (int)i; break; }
        m_list.SetCurSel(sel);

        m_btnBack.EnableWindow(!m_items.empty());
        m_btnDel.EnableWindow(!m_items.empty());
        m_btnAll.EnableWindow(!m_items.empty());
        m_btnNone.EnableWindow(!m_items.empty());
    }

    void CheckAll(int c)
    {
        for (int i = 0; i < m_list.GetCount(); ++i) m_list.SetCheck(i, c);
    }

    afx_msg void OnAll()  { CheckAll(BST_CHECKED); }
    afx_msg void OnNone() { CheckAll(BST_UNCHECKED); }

    // 되돌리기는 하나로만 간다. 표시가 아니라 고른 줄(파란 줄)을 쓴다.
    afx_msg void OnBack()
    {
        const int i = m_list.GetCurSel();
        if (i == LB_ERR || i < 0 || (size_t)i >= m_items.size())
        {
            AfxMessageBox("되돌릴 세대를 목록에서 한 줄 고르십시오.");
            return;
        }
        m_rollTo = m_items[(size_t)i].stamp.c_str();
        EndDialog(IDOK);
    }

    afx_msg void OnDel()
    {
        std::vector<size_t> pick;
        for (int i = 0; i < m_list.GetCount(); ++i)
            if (m_list.GetCheck(i) == BST_CHECKED) pick.push_back((size_t)i);

        if (pick.empty())
        {
            AfxMessageBox("지울 세대에 표시하십시오.");
            return;
        }

        // 무엇을 잃는지 적는다. 운용된 적 있는 세대는 지우면 그리로 되돌릴 수 없다.
        int nServed = 0;
        bool hasBack = false;
        CStringA names;
        for (size_t k = 0; k < pick.size(); ++k)
        {
            const Item& it = m_items[pick[k]];
            if (it.served) ++nServed;
            if (it.isBack) hasBack = true;
            if (k < 12) { names += "    "; names += it.stamp.c_str(); names += "\r\n"; }
        }
        if (pick.size() > 12)
        {
            CStringA more;
            more.Format("    ... 외 %d개\r\n", (int)(pick.size() - 12));
            names += more;
        }

        CStringA warn;
        if (hasBack)
            warn += "직전 세대가 들어 있습니다. 지우면 [되돌리기] 의 기본 대상이 "
                    "사라집니다.\r\n";
        if (nServed > 0)
        {
            CStringA w;
            w.Format("운용된 적 있는 세대 %d개가 들어 있습니다. 지우면 그 세대로 "
                     "되돌릴 수 없습니다.\r\n", nServed);
            warn += w;
        }
        if (!warn.IsEmpty()) warn += "\r\n";

        CStringA q;
        q.Format("세대 %d개를 휴지통으로 옮깁니다.\r\n\r\n%s\r\n%s진행할까요?",
                 (int)pick.size(), (LPCSTR)names, (LPCSTR)warn);
        if (AfxMessageBox(q, MB_YESNO | MB_ICONWARNING) != IDYES) return;

        // 폴더를 하나씩 보낸다. 한꺼번에 보내면 하나가 막혔을 때 어느 것이
        // 남았는지 알기 어렵다.
        CStringA failed;
        std::vector<bool> gone(m_items.size(), false);
        for (size_t k = 0; k < pick.size(); ++k)
        {
            const std::string dir = m_root + m_items[pick[k]].stamp;

            std::vector<char> from(dir.begin(), dir.end());
            from.push_back(0);
            from.push_back(0);                        // 두 번 끝나야 한다

            SHFILEOPSTRUCTA op = {};
            op.hwnd = GetSafeHwnd();
            op.wFunc = FO_DELETE;
            op.pFrom = from.data();
            op.fFlags = FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT
                      | FOF_NOERRORUI;
            const int rc = SHFileOperationA(&op);

            // 돌려준 값만 믿지 않는다. 폴더가 실제로 없어졌는지 본다.
            const DWORD a = GetFileAttributesA(dir.c_str());
            if (rc == 0 && !op.fAnyOperationsAborted && a == INVALID_FILE_ATTRIBUTES)
            {
                gone[pick[k]] = true;
                ++m_deleted;
            }
            else
            {
                failed += "    "; failed += m_items[pick[k]].stamp.c_str();
                failed += "\r\n";
            }
        }

        std::vector<Item> left;
        for (size_t i = 0; i < m_items.size(); ++i)
            if (!gone[i]) left.push_back(m_items[i]);
        m_items.swap(left);
        Fill();

        if (!failed.IsEmpty())
        {
            CStringA m;
            m.Format("다음 세대는 지우지 못했습니다. 다른 프로그램이 그 폴더의 "
                     "파일을 쓰고 있을 수 있습니다.\r\n\r\n%s", (LPCSTR)failed);
            AfxMessageBox(m, MB_ICONERROR);
        }
    }

    DECLARE_MESSAGE_MAP()

private:
    std::vector<WORD> m_tpl;
    std::string m_root;                 // ...\model_generations\ (끝에 \ 포함)
    std::vector<Item> m_items;
    CFont* m_font;
    CFont* m_mono;
    int m_deleted = 0;
    CStringA m_rollTo;

    CStatic m_lblLive;
    CStringA m_live;                    // 운용 중인 세대 한 줄
    CFont   m_fontLive;
    CCheckListBox m_list;
    CButton m_btnAll, m_btnNone, m_btnBack, m_btnDel, m_btnClose;
};

BEGIN_MESSAGE_MAP(CDlg_GenDelete, CDialogEx)
    ON_BN_CLICKED(ID_GD_BACK, &CDlg_GenDelete::OnBack)
    ON_BN_CLICKED(ID_GD_ALL, &CDlg_GenDelete::OnAll)
    ON_BN_CLICKED(ID_GD_NONE, &CDlg_GenDelete::OnNone)
    ON_BN_CLICKED(ID_GD_DEL, &CDlg_GenDelete::OnDel)
END_MESSAGE_MAP()

void CDlg_Retrain::OnBnClickedGenDelete()
{
    if (m_bRunning) return;

    // 창을 열어 둔 사이에 재학습이 돌았을 수 있다. 다시 훑어 운용 세대를 맞춘다.
    ScanGenerations();
    FillGenCombo();

    // 고를 수 있는 것은 운용 중이 아닌 세대 전부.
    // 최근 것이 위다.
    std::vector<CDlg_GenDelete::Item> items;
    for (size_t i = 0; i < m_cboStamps.size(); ++i)
    {
        CDlg_GenDelete::Item it;
        it.stamp  = m_cboStamps[i];
        it.served = (i < m_cboServed.size()) ? m_cboServed[i] : true;
        it.isBack = (m_backGen.Compare(it.stamp.c_str()) == 0);

        CStringA sc = GenScore(it.stamp.c_str());
        if (sc.IsEmpty()) sc = "  -  ";
        it.label.Format("%s   %s   %s", it.stamp.c_str(), (LPCSTR)sc,
                        it.isBack ? "직전" :
                        (it.served ? "운용된 적 있음" : "승격 안 됨"));
        items.push_back(it);
    }

    // 운용 중인 세대. 없으면(카메라 자리를 옮겨 내렸거나 아직 학습 전) 그렇게 적는다.
    CStringA live;
    if (m_curGen.IsEmpty())
        live = "운영 중인 모델   없음 (3단계 꺼짐)";
    else
    {
        CStringA sc = GenScore(m_curGen);
        live.Format("운영 중인 모델   %s   %s", (LPCSTR)m_curGen,
                    sc.IsEmpty() ? "-" : (LPCSTR)sc);
    }

    CDlg_GenDelete dlg(UserPath() + "model_generations\\", items, live,
                       &m_font, &m_fontMono, this);
    dlg.DoModal();

    if (dlg.Deleted())
    {
        ScanGenerations();
        FillGenCombo();
        SetButtons();
    }

    // 되돌리기는 이 창에서 돌린다. 진행 판과 로그가 여기에 있다.
    if (!dlg.RollTo().IsEmpty()) RollbackTo(dlg.RollTo());
}

//---------------------------------------------------------

// [학습모델관리] 창에서 고른 세대로 되돌린다.
void CDlg_Retrain::RollbackTo(const CStringA& picked)
{
    // 창을 열어 둔 채로 재학습을 돌렸을 수 있다. 다시 읽고, 고른 세대가
    // 아직 쓸 수 있는지 확인한다.
    ScanGenerations();
    FillGenCombo();

    bool ok = false;
    for (size_t i = 0; i < m_cboStamps.size(); ++i)
        if (picked.Compare(m_cboStamps[i].c_str()) == 0) { ok = true; break; }

    if (!ok)
    {
        CStringA m = "되돌릴 수 없습니다.\r\n\r\n";
        m += m_backWhy.IsEmpty()
             ? "고른 세대를 더는 쓸 수 없습니다. 목록에서 다시 고르십시오."
             : m_backWhy;
        AfxMessageBox(m);
        SetButtons();
        return;
    }
    m_backGen = picked;

    // 승격된 적 없는 세대는 감도 시험을 거치지 않았다. 고를 수는 있지만
    // 그 사실을 알고 눌러야 한다.
    bool pickedServed = true;
    for (size_t i = 0; i < m_cboStamps.size(); ++i)
        if (picked.Compare(m_cboStamps[i].c_str()) == 0)
        {
            pickedServed = (i < m_cboServed.size()) ? m_cboServed[i] : true;
            break;
        }

    CStringA warn;
    if (!pickedServed)
        warn = "이 세대는 운용에 올라간 적이 없습니다. 감도 시험을 거치지 "
               "않았거나 손으로 넣은 것입니다. 올린 뒤 점수를 확인하십시오."
               "\r\n\r\n";

    CStringA q;
    q.Format("고른 세대로 되돌립니다.\r\n\r\n"
             "    지금  %s\r\n"
             "    이후  %s\r\n\r\n"
             "경험 임계값(online_baseline.npz)은 그대로 둡니다. 기준선이 "
             "세는 것은 모델의 오차가 아니라 칸의 온도 그 자체라, 모델을 "
             "되돌려도 그대로 맞습니다.\r\n\r\n"
             "%s"
             "되돌린 뒤 감시를 다시 시작해야 반영됩니다. 진행할까요?",
             (LPCSTR)m_curGen, (LPCSTR)m_backGen, (LPCSTR)warn);

    if (AfxMessageBox(q, MB_YESNO | MB_ICONWARNING) != IDYES)
        return;
    Run(RUN_ROLLBACK);
}

//---------------------------------------------------------

LRESULT CDlg_Retrain::OnLogLine(WPARAM, LPARAM lp)
{
    CStringA* s = reinterpret_cast<CStringA*>(lp);
    if (s)
    {
        AppendLog(*s);

        // 예행연습 결과를 읽어 [재학습 적용] 을 열지 말지 정한다.
        //
        // 파이썬이 찍는 글자에 매달려 있다. 2026-09-27 에 보고서 꼴을
        // "판정: 승격" 에서 "[판정] 승격" 으로 바꾸면서 이 두 줄을 같이
        // 고치지 않아, 승격 판정이 나도 단추가 켜지지 않았다.
        // sensitivity_gate.format_report 를 고치면 여기도 함께 고쳐야 한다.
        if (s->Find("[판정] 승격") >= 0) m_bDryPassed = true;
        if (s->Find("[판정] 보류") >= 0 || s->Find("[보류]") >= 0)
            m_bDryPassed = false;

        // 같은 줄에서 진행 단계도 읽는다. 학습 구간(epoch)이 가장 길어
        // 거기만 실제 숫자로 채우고 나머지는 지점마다 올린다.
        if (s->Find("[기여도]") >= 0)   { SetPhase(60);  m_phaseNote = "기여도 판단"; }
        if (s->Find("[재생버퍼]") >= 0) { SetPhase(140); m_phaseNote = "재생버퍼 수집"; }
        if (s->Find("[학습]") >= 0)     { SetPhase(200); m_phaseNote = "학습 준비"; }

        int e = s->Find("epoch ");
        if (e >= 0)
        {
            int cur = 0, tot = 0;
            if (sscanf_s((LPCSTR)*s + e, "epoch %d/%d", &cur, &tot) == 2 && tot > 0)
            {
                SetPhase(200 + 600 * cur / tot);
                m_phaseNote.Format("epoch %d/%d", cur, tot);
            }
        }

        // 이 셋도 파이썬이 찍는 글자에 매달려 있다. 꼬리표를 바꾸면 함께
        // 고쳐야 한다. 어긋나도 조용히 지나가므로(진행 눈금만 멈춘다)
        // 알아채기 어렵다.
        if (s->Find("[평가]") >= 0) { SetPhase(850); m_phaseNote = "감도 시험"; }
        if (s->Find("[판정]") >= 0) { SetPhase(950); m_phaseNote = "판정"; }
        if (s->Find("[보관]") >= 0) { SetPhase(980); m_phaseNote = "보관"; }

        delete s;
    }
    return 0;
}

LRESULT CDlg_Retrain::OnRunDone(WPARAM wp, LPARAM lp)
{
    const DWORD code = (DWORD)wp;
    const RunKind kind = (RunKind)(int)lp;
    const bool wasDry = (kind == RUN_DRY);
    const bool wasBack = (kind == RUN_ROLLBACK);

    m_bRunning = false;
    m_hThread = nullptr;
    if (wasDry) m_bDryDone = true;

    // 끝났으면 판을 내린다. 남겨 두면 로그를 가려 결과를 못 읽는다.
    // 걸린 시간은 아래 상태줄에 적어 남긴다.
    const ULONGLONG ms = m_tickStart ? (GetTickCount64() - m_tickStart) : 0;
    const unsigned sec = (unsigned)(ms / 1000);
    ShowProgress(false);

    // 상태줄을 만들기 전에 다시 훑는다. 운용 세대가 바뀌었으면 그 이름을
    // 상태줄에 적어야 하는데, 뒤에 훑으면 옛 이름이 적힌다.
    ScanGenerations();

    CStringA st;
    if (wasDry)
    {
        if (code == 0 && m_bDryPassed)
            st = "예행연습 완료 · 승격 판정입니다. [재학습 적용] 을 누르면 실제로 교체합니다.";
        else if (code == 2)
            st = "예행연습 보류 · 조건이 아직 모자랍니다. 위 사유를 확인하십시오.";
        else
            st = "예행연습 완료 · 승격 판정이 아니어서 [재학습 적용] 을 켤 수 없습니다.";
    }
    else if (wasBack)
    {
        // 무엇으로 돌아갔는지 적는다.
        //
        // 이것이 없으면 창에 아무 변화가 없다. 아래 목록은 운용 중인 것을
        // 빼고 보여 주므로 거기서도 알 수 없다.
        if (code == 0)
            st.Format("되돌렸습니다 · 운용 중 %s · 기준선도 치웠습니다. "
                      "감시가 10초 안에 갈아 끼웁니다.", (LPCSTR)m_curGen);
        else
            st = "되돌리지 못했습니다. 위 내용을 확인하십시오.";
        // 모델이 바뀌었으니 앞서 받은 승격 판정은 그 모델 것이 아니다.
        m_bDryPassed = false;
        m_bDryDone = false;
    }
    else
    {
        if (code == 0)
            st.Format("재학습 완료 · 운용 중 %s 로 교체했습니다. "
                      "감시가 10초 안에 갈아 끼웁니다.", (LPCSTR)m_curGen);
        else
            st = "재학습이 정상적으로 끝나지 않았습니다. 위 내용을 확인하십시오.";
        m_bDryPassed = false;   // 한 번 적용한 뒤에는 다시 예행연습부터
        m_bDryDone = false;
    }
    if (m_tickStart && sec > 0)
    {
        CStringA took;
        if (sec < 60) took.Format("  (%u초)", sec);
        else          took.Format("  (%u분 %u초)", sec / 60, sec % 60);
        st += took;
    }
    m_tickStart = 0;
    m_lblState.SetWindowTextA(st);

    // 종료 코드는 로그에 적지 않는다. 위 상태줄이 사람 말로 알려 준다.
    // 운용 세대는 그 상태줄에 들어 있다.

    SetButtons();
    return 0;
}

//---------------------------------------------------------

void CDlg_Retrain::OnCancel()
{
    if (m_bRunning)
    {
        AfxMessageBox(_T("실행 중입니다. 끝난 뒤에 닫으십시오."));
        return;
    }
    CDialogEx::OnCancel();
}

void CDlg_Retrain::OnDestroy()
{
    // 창이 먼저 사라지면 작업 스레드가 죽은 창에 PostMessage 한다.
    if (m_bRunning && m_hProc)
        TerminateProcess(m_hProc, 1);
    if (m_timer) { KillTimer(m_timer); m_timer = 0; }
    if (m_hThread)
        WaitForSingleObject(m_hThread, 3000);
    CDialogEx::OnDestroy();
}
