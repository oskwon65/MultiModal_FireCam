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

    CRect rc;
    GetClientRect(&rc);
    const int M = 12;
    const int btnW = 128, btnH = 32;
    const int headH = 84, stateH = 28;
    const int progH = 14;

    m_lblHead.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, M, rc.right - M, M + headH), this);

    // 아래에서부터 쌓아 올린다. 서로 겹치지 않게 y 를 한 번씩만 계산한다.
    const int yBtnTop   = rc.bottom - M - btnH;
    const int yStateTop = yBtnTop - 6 - stateH;
    const int yProgTop  = yStateTop - 6 - progH;
    const int yLogBot   = yProgTop - 8;

    m_edLog.Create(WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL | WS_HSCROLL
        | ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY,
        CRect(M, M + headH + 4, rc.right - M, yLogBot),
        this, ID_LOG_EDIT);

    // 자식 컨트롤의 ID 는 서로 달라야 한다. 앞서 로그와 진행바에 모두 0 을
    // 줘서 진행바가 화면에 나오지 않았다.
    m_progress.Create(WS_CHILD | PBS_SMOOTH,
        CRect(M, yProgTop, rc.right - M, yProgTop + progH),
        this, ID_PROGRESS);
    m_progress.SetRange32(0, 1000);

    m_lblState.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, yStateTop, rc.right - M, yStateTop + stateH),
        this);

    int bx = rc.right - M - btnW;
    m_btnClose.Create("닫기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, yBtnTop, bx + btnW, yBtnTop + btnH), this, IDCANCEL);
    bx -= (btnW + 8);
    m_btnApply.Create("진행", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, yBtnTop, bx + btnW, yBtnTop + btnH), this, ID_BTN_APPLY);
    bx -= (btnW + 8);
    m_btnDry.Create("예행연습", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, yBtnTop, bx + btnW, yBtnTop + btnH), this, ID_BTN_DRY);

    // [되돌리기] 는 왼쪽 끝에 따로 둔다. 예행연습 - 진행 흐름에 붙이면
    // 그 다음 단계처럼 보인다. 하는 일은 반대다.
    m_btnBack.Create("되돌리기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(M, yBtnTop, M + btnW, yBtnTop + btnH), this, ID_BTN_BACK);

    SetFont(&m_font);
    SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font.GetSafeHandle(), TRUE);
    m_edLog.SetFont(&m_fontMono);

    // [진행] 이 왜 꺼져 있는지 화면에 적어 둔다. 눌리지 않는 버튼을 두고
    // 설명이 없으면 고장으로 오해한다.
    CStringA head;
    head.Format("[%s]  재학습은 운용 모델을 바꿉니다. 먼저 [예행연습] 으로 결과를 확인하십시오.\r\n"
                "[진행] 은 예행연습이 \"판정: 승격\" 을 낸 경우에만 켜집니다. "
                "보류로 끝나면 사유가 아래에 남으며 진행할 수 없습니다.\r\n"
                "[되돌리기] 는 운용 모델을 직전 세대로 돌리고, 칸별 기준선도 "
                "함께 치워 그 모델 기준으로 다시 쌓게 합니다.",
                gUserID.c_str());
    m_lblHead.SetWindowTextA(head);

    // 어느 세대를 쓰고 있고 어디로 되돌릴 수 있는지 먼저 보여 준다.
    ScanGenerations();
    ShowGenerations();

    SetButtons();
    m_lblState.SetWindowTextA("[예행연습] 을 눌러 시작하십시오. 아직 [진행] 은 꺼져 있습니다.");

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

// 되돌릴 대상을 정한다.
//
// 목록의 뒤에서 두 번째가 아니라 운용 중인 것의 바로 앞이다. 예행연습은
// 후보를 보관만 하고 올리지 않으므로, 운용 중인 세대보다 새로운 폴더가
// 남아 있을 수 있다. 끝에서 세면 승격된 적 없는 후보로 되돌아가 버린다.
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

    if (m_curGen.IsEmpty())
    {
        m_backWhy = "운용 중인 세대를 알 수 없습니다 "
                    "(current_generation.txt 가 없거나 비었습니다).";
        return;
    }

    size_t i = 0;
    bool found = false;
    for (; i < gens.size(); ++i)
        if (m_curGen.Compare(gens[i].c_str()) == 0) { found = true; break; }

    if (!found)
    {
        m_backWhy.Format("운용 중인 세대 %s 가 보관 목록에 없습니다.",
                         (LPCSTR)m_curGen);
        return;
    }
    if (i == 0)
    {
        m_backWhy = "가장 오래된 세대를 쓰고 있어 되돌릴 곳이 없습니다.";
        return;
    }
    m_backGen = gens[i - 1].c_str();
}

// 어느 세대를 쓰고 있고 어디로 되돌릴 수 있는지 로그 칸에 적는다. 창을
// 열면 로그가 비어 있으므로 따로 자리를 내지 않아도 된다.
void CDlg_Retrain::ShowGenerations()
{
    const std::vector<std::string> gens = ListGenerations();

    CStringA t;
    t.Format("[%s] 보관된 세대\r\n", gUserID.c_str());
    for (size_t i = 0; i < gens.size(); ++i)
    {
        t += "    ";
        t += gens[i].c_str();
        if (m_curGen.Compare(gens[i].c_str()) == 0) t += "   <= 운용 중";
        t += "\r\n";
    }
    if (gens.empty()) t += "    (없음)\r\n";

    t += "\r\n";
    if (!m_backGen.IsEmpty())
    {
        CStringA b;
        b.Format("[되돌리기] 대상은 %s 입니다. 운용 중인 %s 의 바로 앞 "
                 "세대입니다.\r\n", (LPCSTR)m_backGen, (LPCSTR)m_curGen);
        t += b;
    }
    else
    {
        t += "[되돌리기] 할 수 없습니다 · ";
        t += m_backWhy;
        t += "\r\n";
    }
    m_edLog.SetWindowTextA(t);
}

void CDlg_Retrain::SetButtons()
{
    m_btnDry.EnableWindow(!m_bRunning);
    // 예행연습이 '승격' 판정을 낸 뒤에만 진행할 수 있다. 결과를 안 보고
    // 누르는 것을 막는 것이 이 창의 존재 이유다.
    m_btnApply.EnableWindow(!m_bRunning && m_bDryDone && m_bDryPassed);
    m_btnBack.EnableWindow(!m_bRunning && !m_backGen.IsEmpty());
    m_btnClose.EnableWindow(!m_bRunning);
}

void CDlg_Retrain::ShowProgress(bool bShow)
{
    m_progress.ShowWindow(bShow ? SW_SHOW : SW_HIDE);
    if (bShow)
    {
        m_pos = m_target = 0;
        m_progress.SetPos(0);
        if (!m_timer) m_timer = SetTimer(1, 400, nullptr);
    }
    else if (m_timer)
    {
        KillTimer(m_timer);
        m_timer = 0;
    }
}

// 단계가 바뀌면 상한을 올린다. 뒤로 가지는 않는다 - 되돌아가는 진행바는
// 고장으로 보인다.
void CDlg_Retrain::SetPhase(int permille)
{
    if (permille > m_target) m_target = permille;
}

void CDlg_Retrain::OnTimer(UINT_PTR nIDEvent)
{
    if (nIDEvent == 1 && m_bRunning)
    {
        // 상한까지 남은 거리의 1/12 씩 좁힌다. 단계 안에서도 계속 움직여
        // 멈춘 것처럼 보이지 않으면서, 상한을 넘지는 않는다.
        if (m_pos < m_target)
        {
            m_pos += (m_target - m_pos) / 12 + 1;
            if (m_pos > m_target) m_pos = m_target;
            m_progress.SetPos(m_pos);
        }
    }
    CDialogEx::OnTimer(nIDEvent);
}

void CDlg_Retrain::AppendLog(const char* text)
{
    int n = m_edLog.GetWindowTextLengthA();
    m_edLog.SetSel(n, n);
    m_edLog.ReplaceSel(text);
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

    // 되돌리기는 파일 몇 개를 옮기고 끝난다. 진행바를 띄우면 차기도 전에
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
    q.Format("운용 모델을 직전 세대로 되돌립니다.\r\n\r\n"
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

        // 예행연습 결과를 읽어 [진행] 을 열지 말지 정한다.
        if (s->Find("판정: 승격") >= 0) m_bDryPassed = true;
        if (s->Find("판정: 보류") >= 0 || s->Find("[보류]") >= 0) m_bDryPassed = false;

        // 같은 줄에서 진행 단계도 읽는다. 학습 구간(epoch)이 가장 길어
        // 거기만 실제 숫자로 채우고 나머지는 지점마다 올린다.
        if (s->Find("[기여도]") >= 0)        SetPhase(60);
        if (s->Find("[재생버퍼]") >= 0)      SetPhase(140);
        if (s->Find("[학습]") >= 0)          SetPhase(200);

        int e = s->Find("epoch ");
        if (e >= 0)
        {
            int cur = 0, tot = 0;
            if (sscanf_s((LPCSTR)*s + e, "epoch %d/%d", &cur, &tot) == 2 && tot > 0)
                SetPhase(200 + 600 * cur / tot);
        }

        if (s->Find("감도 회귀 시험") >= 0)  SetPhase(850);
        if (s->Find("판정:") >= 0)           SetPhase(950);
        if (s->Find("[보관]") >= 0)          SetPhase(980);

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

    // 끝났으면 끝까지 채운 채로 둔다. 감추면 무엇이 끝났는지 흔적이 없다.
    // 타이머만 멈춘다.
    if (m_timer) { KillTimer(m_timer); m_timer = 0; }
    m_target = m_pos = 1000;
    m_progress.SetPos(1000);

    CStringA st;
    if (wasDry)
    {
        if (code == 0 && m_bDryPassed)
            st = "예행연습 완료 · 승격 판정입니다. [진행] 을 누르면 실제로 교체합니다.";
        else if (code == 2)
            st = "예행연습 보류 · 조건이 아직 모자랍니다. 위 사유를 확인하십시오.";
        else
            st = "예행연습 완료 · \"판정: 승격\" 이 아니어서 [진행] 을 켤 수 없습니다.";
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
