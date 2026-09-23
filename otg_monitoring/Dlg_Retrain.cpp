// Dlg_Retrain.cpp: 재학습 실행 창
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_Retrain.h"
#include "afxdialogex.h"

#include <string>

extern std::string gUserID;
extern const char* GetMmCamStartPath();
extern const char* GetAnacondaRootPub();
extern const char* GetAnacondaEnvPub();

#define WM_LOG_LINE   (WM_APP + 21)
#define WM_RUN_DONE   (WM_APP + 22)

#define ID_BTN_DRY     3001
#define ID_BTN_APPLY   3002

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
    ON_MESSAGE(WM_LOG_LINE, &CDlg_Retrain::OnLogLine)
    ON_MESSAGE(WM_RUN_DONE, &CDlg_Retrain::OnRunDone)
    ON_WM_DESTROY()
END_MESSAGE_MAP()

//---------------------------------------------------------

BOOL CDlg_Retrain::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    // 창 안의 글자를 모두 같은 크기로 둔다. 안내와 로그 크기가 다르면
    // 안내가 곁다리처럼 보이는데, 여기서는 그 안내가 핵심이다.
    //
    // 20 은 설정 창(17)보다 크되 이 창의 넓이에 견주어 과하지 않은 값이다.
    m_font.CreateFont(20, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    // 로그도 안내와 같은 글꼴·같은 크기다. 가변폭이라 감도 시험 표의 열이
    // 정확히 맞지는 않지만, 파이썬 쪽에서 자리수를 맞춰 찍고 있어 크게
    // 어긋나지는 않는다.
    m_fontMono.CreateFont(20, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    CRect rc;
    GetClientRect(&rc);
    const int M = 12;
    const int btnW = 128, btnH = 32;
    const int headH = 84, stateH = 28;

    m_lblHead.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, M, rc.right - M, M + headH), this);

    m_edLog.Create(WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL | WS_HSCROLL
        | ES_MULTILINE | ES_AUTOVSCROLL | ES_READONLY,
        CRect(M, M + headH + 4, rc.right - M, rc.bottom - M - btnH - stateH - 12),
        this, 0);

    m_lblState.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, rc.bottom - M - btnH - stateH - 6, rc.right - M, rc.bottom - M - btnH - 6),
        this);

    int bx = rc.right - M - btnW;
    m_btnClose.Create("닫기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, rc.bottom - M - btnH, bx + btnW, rc.bottom - M), this, IDCANCEL);
    bx -= (btnW + 8);
    m_btnApply.Create("진행", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, rc.bottom - M - btnH, bx + btnW, rc.bottom - M), this, ID_BTN_APPLY);
    bx -= (btnW + 8);
    m_btnDry.Create("예행연습", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, rc.bottom - M - btnH, bx + btnW, rc.bottom - M), this, ID_BTN_DRY);

    SetFont(&m_font);
    SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font.GetSafeHandle(), TRUE);
    m_edLog.SetFont(&m_fontMono);

    // [진행] 이 왜 꺼져 있는지 화면에 적어 둔다. 눌리지 않는 버튼을 두고
    // 설명이 없으면 고장으로 오해한다.
    CStringA head;
    head.Format("[%s]  재학습은 운용 모델을 바꿉니다. 먼저 [예행연습] 으로 결과를 확인하십시오.\r\n"
                "[진행] 은 예행연습이 \"판정: 승격\" 을 낸 경우에만 켜집니다. "
                "보류로 끝나면 사유가 아래에 남으며 진행할 수 없습니다.\r\n"
                "보류 사유는 대개 표본이나 시간대가 모자라거나, 새 모델이 지금 "
                "모델보다 둔해진 경우입니다.",
                gUserID.c_str());
    m_lblHead.SetWindowTextA(head);

    SetButtons();
    m_lblState.SetWindowTextA("[예행연습] 을 눌러 시작하십시오. 아직 [진행] 은 꺼져 있습니다.");

    CenterWindow(GetParent());
    return TRUE;
}

//---------------------------------------------------------

void CDlg_Retrain::SetButtons()
{
    m_btnDry.EnableWindow(!m_bRunning);
    // 예행연습이 '승격' 판정을 낸 뒤에만 진행할 수 있다. 결과를 안 보고
    // 누르는 것을 막는 것이 이 창의 존재 이유다.
    m_btnApply.EnableWindow(!m_bRunning && m_bDryDone && m_bDryPassed);
    m_btnClose.EnableWindow(!m_bRunning);
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

    dlg->PostMessage(WM_RUN_DONE, exitCode, ctx->dry ? 1 : 0);
    delete ctx;
    return 0;
}

//---------------------------------------------------------

void CDlg_Retrain::Run(bool dryRun)
{
    if (m_bRunning) return;

    if (gUserID.empty())
    {
        AfxMessageBox(_T("현장(user)이 선택되지 않았습니다."));
        return;
    }

    // conda 환경을 활성화한 뒤 실행한다. 감시 프로세스를 띄울 때와 같은
    // 방식이라, 파이썬 환경이 어긋나 생기는 문제가 따로 생기지 않는다.
    CStringA cmd;
    cmd.Format("cmd.exe /c call \"%sScripts\\activate.bat\" %s "
               "&& cd /d \"%s\" && set PYTHONIOENCODING=utf-8 "
               "&& python retrain\\nightly_retrain.py \"%s\"%s",
               GetAnacondaRootPub(), GetAnacondaEnvPub(),
               GetMmCamStartPath(), gUserID.c_str(),
               dryRun ? " --dry-run" : "");

    m_edLog.SetWindowTextA("");
    CStringA msg;
    msg.Format("%s 시작합니다. 몇 분 걸립니다.\r\n\r\n",
               dryRun ? "예행연습을" : "재학습을");
    AppendLog(msg);

    m_bRunning = true;
    if (dryRun) { m_bDryDone = false; m_bDryPassed = false; }
    SetButtons();
    m_lblState.SetWindowTextA(dryRun ? "예행연습 중..." : "재학습 중... 끝날 때까지 닫지 마십시오.");

    RunCtx* ctx = new RunCtx{ this, std::string((LPCSTR)cmd), dryRun };
    CWinThread* th = AfxBeginThread(ThreadProc, ctx);
    m_hThread = th ? th->m_hThread : nullptr;
}

void CDlg_Retrain::OnBnClickedDryRun() { Run(true); }

void CDlg_Retrain::OnBnClickedApply()
{
    if (AfxMessageBox(_T("운용 모델을 새 모델로 바꿉니다.\n\n")
                      _T("감도 회귀 시험을 통과한 경우에만 교체되며,\n")
                      _T("이전 세대는 보관되어 되돌릴 수 있습니다.\n\n")
                      _T("진행할까요?"),
                      MB_YESNO | MB_ICONQUESTION) != IDYES)
        return;
    Run(false);
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

        delete s;
    }
    return 0;
}

LRESULT CDlg_Retrain::OnRunDone(WPARAM wp, LPARAM lp)
{
    const DWORD code = (DWORD)wp;
    const bool wasDry = (lp != 0);

    m_bRunning = false;
    m_hThread = nullptr;
    if (wasDry) m_bDryDone = true;

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
    if (m_hThread)
        WaitForSingleObject(m_hThread, 3000);
    CDialogEx::OnDestroy();
}
