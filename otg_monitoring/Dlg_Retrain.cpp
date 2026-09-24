// Dlg_Retrain.cpp: 재학습 실행 창
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

extern std::string gUserID;
extern const char* GetMmCamStartPath();
extern const char* GetAnacondaRootPub();
extern const char* GetAnacondaEnvPub();

#define WM_LOG_LINE   (WM_APP + 21)
#define WM_RUN_DONE   (WM_APP + 22)

#define ID_BTN_DRY     3001
#define ID_BTN_APPLY   3002
#define ID_LOG_EDIT    3003
#define ID_PROGRESS    3004
#define ID_BTN_BACK    3005
#define ID_PNL_BUSY    3006
#define ID_LBL_BUSY    3007
#define ID_LBL_ELAPSED 3008

// 가운데 판 크기
#define BUSY_W  460
#define BUSY_H  150

// 눈금 애니메이션은 직접 돌린다.
//
// PBS_MARQUEE 를 써 봤으나 이 환경에서는 흐르지 않았다 - 비주얼 스타일과
// comctl32 판에 걸린다. SetPos 와 SetWindowText 는 어디서든 먹으므로 그
// 둘만으로 움직인다.
#define ANIM_MS      120      // 한 프레임
#define SWEEP_STEP    45      // 총량을 모를 때 한 프레임에 쓸어 가는 양

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
    ON_BN_CLICKED(ID_BTN_BACK, &CDlg_Retrain::OnBnClickedRollback)
    ON_MESSAGE(WM_LOG_LINE, &CDlg_Retrain::OnLogLine)
    ON_MESSAGE(WM_RUN_DONE, &CDlg_Retrain::OnRunDone)
    ON_WM_DESTROY()
    ON_WM_TIMER()
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
    const int btnWrun = 176;          // [재학습 실행] 은 글자가 길어 더 넓다
    const int headH = 84, stateH = 28;

    m_lblHead.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, M, rc.right - M, M + headH), this);

    // 아래에서부터 쌓아 올린다. 서로 겹치지 않게 y 를 한 번씩만 계산한다.
    const int yBtnTop   = rc.bottom - M - btnH;
    const int yStateTop = yBtnTop - 6 - stateH;
    const int yLogBot   = yStateTop - 8;

    m_edLog.Create(WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL | WS_HSCROLL
        | ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY,
        CRect(M, M + headH + 4, rc.right - M, yLogBot),
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
    const int by0 = (rc.Height() - BUSY_H) / 2;

    m_pnlBusy.Create("", WS_CHILD | SS_WHITERECT | SS_SUNKEN,
        CRect(bx0, by0, bx0 + BUSY_W, by0 + BUSY_H), this, ID_PNL_BUSY);

    m_lblBusy.Create("", WS_CHILD | SS_CENTER,
        CRect(bx0 + 16, by0 + 22, bx0 + BUSY_W - 16, by0 + 54),
        this, ID_LBL_BUSY);

    m_progress.Create(WS_CHILD | PBS_SMOOTH,
        CRect(bx0 + 32, by0 + 64, bx0 + BUSY_W - 32, by0 + 88),
        this, ID_PROGRESS);
    m_progress.SetRange32(0, 1000);

    m_lblElapsed.Create("", WS_CHILD | SS_CENTER,
        CRect(bx0 + 16, by0 + 98, bx0 + BUSY_W - 16, by0 + 130),
        this, ID_LBL_ELAPSED);

    m_lblState.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, yStateTop, rc.right - M, yStateTop + stateH),
        this);

    int bx = rc.right - M - btnW;
    m_btnClose.Create("닫기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, yBtnTop, bx + btnW, yBtnTop + btnH), this, IDCANCEL);
    bx -= (btnWrun + 8);
    m_btnApply.Create("재학습 실행", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, yBtnTop, bx + btnWrun, yBtnTop + btnH), this, ID_BTN_APPLY);
    bx -= (btnW + 8);
    m_btnDry.Create("예행연습", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, yBtnTop, bx + btnW, yBtnTop + btnH), this, ID_BTN_DRY);

    // [되돌리기] 는 왼쪽 끝에 따로 둔다. 예행연습 - 재학습 실행 흐름에 붙이면
    // 그 다음 단계처럼 보인다. 하는 일은 반대다.
    m_btnBack.Create("되돌리기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(M, yBtnTop, M + btnW, yBtnTop + btnH), this, ID_BTN_BACK);

    SetFont(&m_font);
    SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font.GetSafeHandle(), TRUE);
    m_edLog.SetFont(&m_fontMono);

    // [재학습 실행] 이 왜 꺼져 있는지 화면에 적어 둔다. 눌리지 않는 버튼을 두고
    // 설명이 없으면 고장으로 오해한다.
    CStringA head;
    head.Format("[%s]  재학습은 운용 모델을 바꿉니다. 먼저 [예행연습] 으로 결과를 확인하십시오.\r\n"
                "[재학습 실행] 은 예행연습이 \"판정: 승격\" 을 낸 경우에만 "
                "켜집니다. 보류로 끝나면 사유가 아래에 남으며 실행할 수 없습니다.\r\n"
                "[되돌리기] 는 직전에 운용하던 세대로 돌리고, 칸별 기준선도 "
                "함께 치웁니다. 예행연습은 아무것도 남기지 않습니다.",
                gUserID.c_str());
    m_lblHead.SetWindowTextA(head);

    // 어느 세대를 쓰고 있고 어디로 되돌릴 수 있는지 먼저 보여 준다.
    ScanGenerations();
    ShowGenerations();

    SetButtons();
    m_lblState.SetWindowTextA("[예행연습] 을 눌러 시작하십시오. 아직 [재학습 실행] 은 꺼져 있습니다.");

    CenterWindow(GetParent());
    return TRUE;
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
void CDlg_Retrain::ShowGenerations()
{
    const std::vector<std::string> gens = ListGenerations();
    const std::vector<std::string> served = ServedGenerations();

    // 기록에는 같은 세대가 여러 번 나올 수 있다(올렸다 내렸다 다시 올림).
    // 폴더가 남아 있는 것만 한 번씩 이름 순으로 모은다.
    std::vector<std::string> shown;
    for (size_t i = 0; i < gens.size(); ++i)
    {
        for (size_t k = 0; k < served.size(); ++k)
            if (served[k] == gens[i]) { shown.push_back(gens[i]); break; }
    }

    // 줄마다 색이 달라 한 덩어리로 넣을 수 없다. 한 줄씩 넣고 물들인다.
    m_edLog.SetWindowTextA("");

    CStringA head;
    head.Format("[%s] 운용에 올라간 세대\r\n", gUserID.c_str());
    AppendLog(head);

    for (size_t i = 0; i < shown.size(); ++i)
    {
        const bool live = (m_curGen.Compare(shown[i].c_str()) == 0);
        CStringA line;
        line.Format("    %s   %s\r\n", shown[i].c_str(),
                    live ? "운영중" : "운용된 적 있음");
        AppendLog(line, live ? COLOR_LOG_NORMAL : COLOR_LOG_DIM);
    }
    if (shown.empty()) AppendLog("    (없음)\r\n", COLOR_LOG_DIM);

    const size_t hidden = gens.size() - shown.size();
    if (hidden > 0)
    {
        CStringA h;
        h.Format("\r\n승격되지 않은 후보 %u개는 숨겼습니다. 되돌릴 대상이 "
                 "아닙니다.\r\n", (unsigned)hidden);
        AppendLog(h, COLOR_LOG_DIM);
    }

    if (!m_backGen.IsEmpty())
    {
        CStringA b;
        b.Format("\r\n[되돌리기] 대상은 %s 입니다.\r\n", (LPCSTR)m_backGen);
        AppendLog(b);
    }
    else
    {
        CStringA b;
        b.Format("\r\n[되돌리기] 할 수 없습니다 · %s\r\n", (LPCSTR)m_backWhy);
        AppendLog(b);
    }
}

void CDlg_Retrain::SetButtons()
{
    m_btnDry.EnableWindow(!m_bRunning);
    // 예행연습이 '승격' 판정을 낸 뒤에만 실행할 수 있다. 결과를 안 보고
    // 누르는 것을 막는 것이 이 창의 존재 이유다.
    m_btnApply.EnableWindow(!m_bRunning && m_bDryDone && m_bDryPassed);
    m_btnBack.EnableWindow(!m_bRunning && !m_backGen.IsEmpty());
    m_btnClose.EnableWindow(!m_bRunning);
}

void CDlg_Retrain::ShowProgress(bool bShow)
{
    const int cmd = bShow ? SW_SHOW : SW_HIDE;
    m_pnlBusy.ShowWindow(cmd);
    m_lblBusy.ShowWindow(cmd);
    m_progress.ShowWindow(cmd);
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
        m_lblElapsed.SetWindowPos(&wndTop, 0, 0, 0, 0,
                                  SWP_NOMOVE | SWP_NOSIZE);

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

    // 글자 회전자. SetWindowText 만 쓰므로 어떤 환경에서도 돈다.
    static const char* SPIN[4] = { "|", "/", "-", "\\" };
    CStringA t;
    t.Format("%s   %s", (LPCSTR)m_busyWhat, SPIN[(m_frame / 3) % 4]);
    if (t != m_lastBusy)
    {
        m_lastBusy = t;
        m_lblBusy.SetWindowTextA(t);
    }
}

void CDlg_Retrain::UpdateElapsed()
{
    const ULONGLONG ms = GetTickCount64() - m_tickStart;
    const unsigned sec = (unsigned)(ms / 1000);

    CStringA t;
    if (sec < 60) t.Format("경과 %u초", sec);
    else          t.Format("경과 %u분 %u초", sec / 60, sec % 60);

    // 단계를 읽었으면 얼마나 왔는지, 무엇을 하는 중인지 함께 적는다.
    if (m_target > 0)
    {
        CStringA pct;
        pct.Format("  ·  %d%%", m_target / 10);
        t += pct;
    }
    if (!m_phaseNote.IsEmpty())
    {
        t += "  ·  ";
        t += m_phaseNote;
    }

    if (t != m_lastElapsed)
    {
        m_lastElapsed = t;
        m_lblElapsed.SetWindowTextA(t);
    }
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
    CStringA msg;
    if (back)
        msg.Format("%s 세대로 되돌립니다.\r\n\r\n", (LPCSTR)m_backGen);
    else
        msg.Format("%s 시작합니다. 몇 분 걸립니다.\r\n\r\n",
                   dryRun ? "예행연습을" : "재학습을");
    AppendLog(msg);

    m_bRunning = true;
    if (dryRun) { m_bDryDone = false; m_bDryPassed = false; }

    m_busyWhat = back   ? "되돌리는 중" :
                 dryRun ? "예행연습 중" : "재학습 중";

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

void CDlg_Retrain::OnBnClickedRollback()
{
    // 누를 때마다 다시 읽는다. 창을 열어 둔 채로 재학습을 돌렸을 수 있다.
    ScanGenerations();
    if (m_backGen.IsEmpty())
    {
        CStringA m = "되돌릴 수 없습니다.\r\n\r\n" + m_backWhy;
        AfxMessageBox(m);
        SetButtons();
        return;
    }

    CStringA q;
    q.Format("직전에 운용하던 세대로 되돌립니다.\r\n\r\n"
             "    지금  %s\r\n"
             "    이후  %s\r\n\r\n"
             "칸별 기준선(online_baseline.npz)도 함께 치웁니다. 기준선은 "
             "그 모델이 칸마다 내는 오차의 분포이므로, 모델만 갈면 임계치가 "
             "다른 모델 것이 되어 어긋납니다.\r\n\r\n"
             "치운 기준선은 지우지 않고 보관하므로 되돌릴 수 있습니다. "
             "다시 쌓는 동안에는 칸별 임계치가 나오지 않고 절대 온도 "
             "임계치만 작동합니다.\r\n\r\n"
             "되돌린 뒤 감시를 다시 시작해야 반영됩니다. 진행할까요?",
             (LPCSTR)m_curGen, (LPCSTR)m_backGen);

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

        // 예행연습 결과를 읽어 [재학습 실행] 을 열지 말지 정한다.
        if (s->Find("판정: 승격") >= 0) m_bDryPassed = true;
        if (s->Find("판정: 보류") >= 0 || s->Find("[보류]") >= 0) m_bDryPassed = false;

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

        if (s->Find("감도 회귀 시험") >= 0) { SetPhase(850); m_phaseNote = "감도 시험"; }
        if (s->Find("판정:") >= 0)          { SetPhase(950); m_phaseNote = "판정"; }
        if (s->Find("[보관]") >= 0)         { SetPhase(980); m_phaseNote = "보관"; }

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

    CStringA st;
    if (wasDry)
    {
        if (code == 0 && m_bDryPassed)
            st = "예행연습 완료 · 승격 판정입니다. [재학습 실행] 을 누르면 실제로 교체합니다.";
        else if (code == 2)
            st = "예행연습 보류 · 조건이 아직 모자랍니다. 위 사유를 확인하십시오.";
        else
            st = "예행연습 완료 · \"판정: 승격\" 이 아니어서 [재학습 실행] 을 켤 수 없습니다.";
    }
    else if (wasBack)
    {
        st = (code == 0)
            ? "되돌렸습니다 · 기준선도 치웠습니다. 감시를 다시 시작해야 반영됩니다."
            : "되돌리지 못했습니다. 위 내용을 확인하십시오.";
        // 모델이 바뀌었으니 앞서 받은 승격 판정은 그 모델 것이 아니다.
        m_bDryPassed = false;
        m_bDryDone = false;
    }
    else
    {
        st = (code == 0)
            ? "재학습 완료 · 새 모델로 교체했습니다. 감시를 다시 시작해야 반영됩니다."
            : "재학습이 정상적으로 끝나지 않았습니다. 위 내용을 확인하십시오.";
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

    CStringA tail;
    tail.Format("\r\n---- 종료 코드 %lu ----\r\n", code);
    AppendLog(tail);

    // 운용 세대가 바뀌었을 수 있다. 다음 [되돌리기] 대상을 다시 구한다.
    ScanGenerations();
    if (!m_backGen.IsEmpty())
    {
        CStringA n;
        n.Format("운용 중 %s · 다음 [되돌리기] 대상 %s\r\n",
                 (LPCSTR)m_curGen, (LPCSTR)m_backGen);
        AppendLog(n);
    }

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
