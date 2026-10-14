// Dlg_MaskFetch.cpp: 관제서버 분석마스크 받기 창
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_MaskFetch.h"
#include "Dlg_Confirm2.h"
#include "afxdialogex.h"

#include <wininet.h>
#include <algorithm>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

#pragma comment(lib, "wininet.lib")

extern std::string gUserID;
extern const char* GetMmCamStartPath();
extern const char* GetAnacondaRootPub();
extern const char* GetAnacondaEnvPub();
extern std::string ini_read_utf8(const std::string&, const std::string&,
                                 const std::string&, const std::string&);

#define ID_MF_REPLACE  3701
#define ID_MF_PREV     3702

static const int GRID = 8;
static const int CELLS = GRID * GRID;

// 64칸이 모두 0/1 이어야 마스크로 본다. 아니면 빈 것을 돌려준다.
static std::vector<int> ParseMask(const std::string& text)
{
    std::vector<int> v;
    std::istringstream is(text);
    std::string tok;
    while (is >> tok)
    {
        if (tok != "0" && tok != "1") return {};
        v.push_back(tok[0] - '0');
    }
    if ((int)v.size() != CELLS) return {};
    return v;
}

static bool ReadText(const std::string& path, std::string& out)
{
    std::ifstream f(path, std::ios::binary);
    if (!f) return false;
    std::ostringstream ss;
    ss << f.rdbuf();
    out = ss.str();
    return true;
}

// 파일 수정 시각. 없으면 빈 글자.
static std::string FileTimeText(const std::string& path)
{
    WIN32_FILE_ATTRIBUTE_DATA fa;
    if (!GetFileAttributesExA(path.c_str(), GetFileExInfoStandard, &fa)) return "";
    FILETIME lt;
    SYSTEMTIME st;
    FileTimeToLocalFileTime(&fa.ftLastWriteTime, &lt);
    FileTimeToSystemTime(&lt, &st);
    char buf[32];
    sprintf_s(buf, "%04d-%02d-%02d %02d:%02d", st.wYear, st.wMonth, st.wDay,
              st.wHour, st.wMinute);
    return buf;
}

// 캐시를 거치지 않고 받는다. 방금 웹에서 저장한 것을 바로 봐야 한다.
static bool HttpGet(const std::string& url, std::string& out, CStringA& err)
{
    out.clear();
    HINTERNET hNet = ::InternetOpenA("MmCam", INTERNET_OPEN_TYPE_PRECONFIG,
                                     nullptr, nullptr, 0);
    if (!hNet) { err = "인터넷 연결을 열지 못했음"; return false; }

    bool ok = false;
    HINTERNET hUrl = ::InternetOpenUrlA(hNet, url.c_str(), nullptr, 0,
        INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE | INTERNET_FLAG_PRAGMA_NOCACHE, 0);
    if (!hUrl)
    {
        err.Format("관제서버에 연결하지 못했음 (err %lu)", ::GetLastError());
    }
    else
    {
        DWORD code = 0, len = sizeof(code), idx = 0;
        ::HttpQueryInfoA(hUrl, HTTP_QUERY_STATUS_CODE | HTTP_QUERY_FLAG_NUMBER,
                         &code, &len, &idx);
        if (code != 200)
        {
            err.Format("관제서버에 분석마스크가 없음 (HTTP %lu)", code);
        }
        else
        {
            char buf[1024];
            DWORD n = 0;
            while (::InternetReadFile(hUrl, buf, sizeof(buf), &n) && n > 0)
            {
                out.append(buf, n);
                if (out.size() > 64 * 1024) break;   // 마스크가 이렇게 클 리 없다
            }
            ok = true;
        }
        ::InternetCloseHandle(hUrl);
    }
    ::InternetCloseHandle(hNet);
    return ok;
}

static int CountOnes(const std::vector<int>& m)
{
    return (int)std::count(m.begin(), m.end(), 1);
}

BEGIN_MESSAGE_MAP(CDlg_MaskFetch, CDialogEx)
    ON_WM_PAINT()
    ON_BN_CLICKED(ID_MF_REPLACE, &CDlg_MaskFetch::OnReplace)
    ON_BN_CLICKED(ID_MF_PREV, &CDlg_MaskFetch::OnTogglePrev)
END_MESSAGE_MAP()

CDlg_MaskFetch::CDlg_MaskFetch(CFont* font, CWnd* parent, const std::string& userPath,
                               const std::string& url, int needCells)
    : CDialogEx(), m_font(font), m_userPath(userPath), m_url(url), m_need(needCells)
{
    m_tpl.assign(64, 0);
    DLGTEMPLATE* t = reinterpret_cast<DLGTEMPLATE*>(m_tpl.data());
    t->style = DS_MODALFRAME | WS_POPUP | WS_CAPTION | WS_SYSMENU;
    t->cx = 300; t->cy = 200;
    WORD* p = reinterpret_cast<WORD*>(t + 1);
    *p++ = 0;
    *p++ = 0;
    // "관제서버 분석마스크 받기"
    const wchar_t* cap = L"\xAD00\xC81C\xC11C\xBC84 \xBD84\xC11D\xB9C8\xC2A4\xD06C \xBC1B\xAE30";
    while (*cap) *p++ = (WORD)*cap++;
    *p++ = 0;
    InitModalIndirect(t, parent);
}

std::string CDlg_MaskFetch::LocalPath() const
{
    return m_userPath + "hotlist_mask_local.ini";
}

std::string CDlg_MaskFetch::HistoryDir() const
{
    return m_userPath + "mask_history";
}

// 창 크기와 그림 자리
static const int DW = 640, DH = 480, M = 16;
static const int CELL = 30, GX0 = 40, GX1 = 360, GY = 126;

BOOL CDlg_MaskFetch::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    CRect wr(0, 0, DW, DH);
    AdjustWindowRectEx(&wr, GetStyle(), FALSE, GetExStyle());
    SetWindowPos(nullptr, 0, 0, wr.Width(), wr.Height(), SWP_NOMOVE | SWP_NOZORDER);
    CenterWindow();

    const int bH = 32, yBtn = DH - M - bH;
    const int yFoot = GY + GRID * CELL + 14;
    m_lblHead.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
                     CRect(M, M, DW - M, M + 52), this);
    m_lblFoot.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
                     CRect(M, yFoot, DW - M, yBtn - 8), this);
    m_btnReplace.Create("관제서버 것으로 교체", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                        CRect(M, yBtn, M + 190, yBtn + bH), this, ID_MF_REPLACE);
    m_btnPrev.Create("이전 분석마스크 보기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                     CRect(M + 200, yBtn, M + 200 + 190, yBtn + bH), this, ID_MF_PREV);
    m_btnClose.Create("닫기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                      CRect(DW - M - 110, yBtn, DW - M, yBtn + bH), this, IDCANCEL);

    if (m_font) SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font->GetSafeHandle(), TRUE);

    CWaitCursor wait;
    LoadLocal();
    LoadPrev();
    Download();
    Refresh();
    m_btnClose.SetFocus();
    return FALSE;
}

void CDlg_MaskFetch::LoadLocal()
{
    std::string text;
    m_cur.clear();
    m_curAt.clear();
    if (ReadText(LocalPath(), text))
    {
        m_cur = ParseMask(text);
        m_curAt = FileTimeText(LocalPath());
    }
}

// 가장 최근에 남긴 옛 마스크. 이름에 시각이 붙어 있어 이름순 마지막이 최근 것이다.
// 이력 폴더를 두기 전에 남긴 hotlist_mask_local.bak 이 있으면 그것을 쓴다.
void CDlg_MaskFetch::LoadPrev()
{
    m_prev.clear();
    m_prevAt.clear();
    m_prevPath.clear();

    std::string newest;
    WIN32_FIND_DATAA fd;
    HANDLE h = FindFirstFileA((HistoryDir() + "\\hotlist_mask_local_*.ini").c_str(), &fd);
    if (h != INVALID_HANDLE_VALUE)
    {
        do {
            if (!(fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY) && newest < fd.cFileName)
                newest = fd.cFileName;
        } while (FindNextFileA(h, &fd));
        FindClose(h);
    }

    std::string path;
    if (!newest.empty())
        path = HistoryDir() + "\\" + newest;
    else if (GetFileAttributesA((m_userPath + "hotlist_mask_local.bak").c_str())
             != INVALID_FILE_ATTRIBUTES)
        path = m_userPath + "hotlist_mask_local.bak";

    std::string text;
    if (!path.empty() && ReadText(path, text))
    {
        m_prev = ParseMask(text);
        if (!m_prev.empty())
        {
            m_prevPath = path;
            m_prevAt = FileTimeText(path);
        }
    }
}

void CDlg_MaskFetch::Download()
{
    m_svr.clear();
    m_svrErr.Empty();
    std::string text;
    if (!HttpGet(m_url, text, m_svrErr)) return;
    m_svr = ParseMask(text);
    if (m_svr.empty())
        m_svrErr = "관제서버 파일이 8x8 의 0/1 형식이 아님";
}

void CDlg_MaskFetch::Refresh()
{
    const bool svrOk = !m_svr.empty();
    const bool same = svrOk && m_svr == m_cur;
    // 관제서버에서 설비 칸 수를 바꿨다. 교체하면 학습이 초기화된다.
    const bool recount = svrOk && !same && m_need > 0 && CountOnes(m_svr) != m_need;

    CStringA head;
    head.Format("관제서버 : %s\r\n", m_url.c_str());
    if (!svrOk)
        head += "[받기 실패] " + m_svrErr;
    else if (same)
        head += "관제서버 분석마스크가 지금 쓰는 것과 같음";
    else if (recount)
    {
        CStringA t;
        t.Format("[설비 칸 수 변경 %d -> %d 칸] 교체하면 모든 학습과 분석이 초기화됨",
                 m_need, CountOnes(m_svr));
        head += t;
    }
    else
        head += "관제서버 분석마스크가 지금 쓰는 것과 다름 · 다른 칸은 빨간 테두리임";
    if (m_showPrev)
        head.Format("이전 분석마스크 : %s\r\n지금 쓰는 분석마스크와 바로 전 분석마스크를 견줌 · "
                    "다른 칸은 빨간 테두리임", m_prevPath.c_str());
    m_lblHead.SetWindowText(head);

    CStringA foot = "주황 = 감시하는 설비 칸.  ";
    if (m_need > 0)
    {
        CStringA n;
        n.Format("지금 설비 칸 수는 %d 칸임 (env.ini NUM_OF_MACHINE_CELLS).", m_need);
        foot += n;
    }
    foot += "\r\n교체하면 지금 것은 mask_history 폴더에 남고, 감시를 다시 시작해야 반영됨";
    m_lblFoot.SetWindowText(foot);

    m_btnReplace.SetWindowText(recount ? "칸 수 변경 후 교체" : "관제서버 것으로 교체");
    m_btnReplace.EnableWindow(svrOk && !same && !m_showPrev);
    m_btnPrev.SetWindowText(m_showPrev ? "관제서버 분석마스크 보기" : "이전 분석마스크 보기");
    m_btnPrev.EnableWindow(m_showPrev || !m_prev.empty());

    Invalidate();
}

void CDlg_MaskFetch::OnTogglePrev()
{
    if (!m_showPrev && m_prev.empty()) return;
    m_showPrev = !m_showPrev;
    Refresh();
}

void CDlg_MaskFetch::OnReplace()
{
    if (m_svr.empty() || m_svr == m_cur) return;

    CMmCammonitoringDlg* main = dynamic_cast<CMmCammonitoringDlg*>(AfxGetMainWnd());
    const bool running = main != nullptr && main->IsPredictRunning(gUserID.c_str());

    // 칸 수가 바뀌었다 - 관제서버에서 admin 이 설비 칸 수를 바꾼 것이다. 감시하는
    // 칸이 달라지므로 2·3단계를 내리고 env.ini 의 칸 수를 고친 뒤에 교체한다.
    const int n = CountOnes(m_svr);
    const bool recount = m_need > 0 && n != m_need;
    CStringA recountAt;
    if (recount)
    {
        if (running)
        {
            CStringA msg;
            msg.Format("[설비 칸 수 변경  %d -> %d 칸]\r\n\r\n"
                       "감시가 돌고 있으면 메모리의 학습 결과가 그대로 남아 초기화가 "
                       "되지 않음\r\n감시를 정지한 뒤 다시 누를 것", m_need, n);
            AfxMessageBox(msg, MB_ICONWARNING);
            return;
        }

        // 관제서버 [칸 수 변경] 창과 같은 모양으로 두 번 묻는다.
        Confirm2Text t;
        t.title = "설비 칸 수 변경";
        t.info.Format("설비 칸 수  %d칸 → %d칸", m_need, n);
        t.warnHead = "분석마스크를 바꾸면 분석서버의 모든 학습과 분석 방식을 모두 초기화됨";
        t.warnItems.push_back("2단계 경험 임계값과 3단계 오토인코더 다시 학습 필요함");
        t.warnItems.push_back("[분석서버]에서 2단계, 3단계를 위한 새 학습과정을 진행해야 함");
        CStringA env;
        env.Format("env.ini 설비 칸 수를 %d 로 변경, 내린 모델과 기준선은 "
                   "model_generations 에 보관", n);
        t.warnItems.push_back(env);
        t.big.Format("%d칸 → %d칸", m_need, n);
        t.question = "변경 시 분석서버에서 2단계, 3단계 학습을 처음부터 다시 해야 함 · "
                     "최종 확인 필요";
        if (!CDlg_Confirm2::Ask(m_font, this, t))
            return;

        // 2·3단계를 먼저 내린다. 실패하면 마스크도 바꾸지 않는다.
        CWaitCursor wait;
        const std::string ri = m_userPath + "_recount.ini";
        DeleteFileA(ri.c_str());
        CStringA cmd;
        cmd.Format("cmd.exe /c call \"%sScripts\\activate.bat\" %s "
                   "&& cd /d \"%s\" && set PYTHONIOENCODING=utf-8 "
                   "&& python retrain\\base_ref_tool.py \"%s\" recount %d",
                   GetAnacondaRootPub(), GetAnacondaEnvPub(),
                   GetMmCamStartPath(), gUserID.c_str(), n);
        STARTUPINFOA si = { sizeof(si) };
        PROCESS_INFORMATION pi = { 0 };
        std::vector<char> line(cmd.GetString(), cmd.GetString() + cmd.GetLength() + 1);
        DWORD code = 1;
        if (CreateProcessA(nullptr, line.data(), nullptr, nullptr, FALSE,
                           CREATE_NO_WINDOW, nullptr, GetMmCamStartPath(), &si, &pi))
        {
            if (WaitForSingleObject(pi.hProcess, 120000) == WAIT_OBJECT_0)
                GetExitCodeProcess(pi.hProcess, &code);
            else
                TerminateProcess(pi.hProcess, 1);
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
        }
        if (code != 0 || ini_read_utf8(ri, "RESULT", "OK", "0") != "1")
        {
            CStringA msg;
            msg.Format("학습 초기화에 실패해 분석마스크를 바꾸지 않았음\r\n\r\n"
                       "명령 창에서 python retrain\\base_ref_tool.py %s recount %d 를 "
                       "돌려 원인을 확인할 것", gUserID.c_str(), n);
            AfxMessageBox(msg, MB_ICONERROR);
            return;
        }
        recountAt = ini_read_utf8(ri, "RESULT", "AT", "").c_str();
        m_need = n;
    }
    else
    {
        // 칸 수는 같고 고른 칸이 다르다. 감시하는 자리가 바뀌므로 경고하고 두 번 묻는다.
        int added = 0, removed = 0;
        for (int i = 0; i < CELLS; ++i)
        {
            const int was = m_cur.empty() ? 0 : m_cur[i];
            if (m_svr[i] && !was) ++added;
            if (!m_svr[i] && was) ++removed;
        }

        // 관제서버 [칸 수 변경] 창과 같은 모양으로 두 번 묻는다.
        Confirm2Text t;
        t.title = "분석마스크 변경";
        t.info.Format("새로 감시 %d칸 · 감시에서 빠짐 %d칸", added, removed);
        t.warnHead = "분석마스크 교체 시 감시 설비 칸 변경";
        t.warnItems.push_back("1단계 절대 임계값과 2·3단계 채점 기준이 새 칸으로 변경");
        t.warnItems.push_back("빠지는 칸의 이상은 더 이상 채점 안 함");
        t.warnItems.push_back("감시 재시작 후 반영, 지금 분석마스크는 mask_history 에 보관");
        t.big.Format("감시 칸 %d칸 변경", added + removed);
        t.question.Format("교체 시 %d칸 중 %d칸의 감시 여부 변경 · 최종 확인 필요",
                          CountOnes(m_svr), added + removed);
        if (!CDlg_Confirm2::Ask(m_font, this, t))
            return;
    }

    // 칸 수 변경으로 학습을 이미 내린 뒤 교체에 실패하면, 그 사실을 함께 알린다.
    // 칸 수는 이미 맞춰졌으므로 다시 누르면 보통 교체로 이어진다.
    const CStringA failTail = recount
        ? "\r\n\r\n학습은 이미 초기화되었고 칸 수도 바뀌었음 · 원인을 고친 뒤 "
          "[관제서버 것으로 교체] 를 다시 누를 것 · 그 전에는 감시가 시작하지 못함"
        : "";

    // 지금 것을 남긴다. 남기지 못하면 바꾸지 않는다 - 되돌릴 길이 없어진다.
    const std::string local = LocalPath();
    const bool hasLocal = GetFileAttributesA(local.c_str()) != INVALID_FILE_ATTRIBUTES;
    if (hasLocal)
    {
        CreateDirectoryA(HistoryDir().c_str(), nullptr);
        SYSTEMTIME st;
        GetLocalTime(&st);
        char name[64];
        sprintf_s(name, "hotlist_mask_local_%04d%02d%02d_%02d%02d%02d.ini",
                  st.wYear, st.wMonth, st.wDay, st.wHour, st.wMinute, st.wSecond);
        const std::string hist = HistoryDir() + "\\" + name;
        if (!CopyFileA(local.c_str(), hist.c_str(), FALSE))
        {
            CStringA msg;
            msg.Format("지금 분석마스크를 남기지 못해 교체하지 않았음 (err %lu)\r\n%s",
                       GetLastError(), hist.c_str());
            AfxMessageBox(msg + failTail, MB_ICONERROR);
            Refresh();
            return;
        }
        // 예전 [관제서버 분석마스크 받기] 가 남기던 자리에도 둔다.
        CopyFileA(local.c_str(), (m_userPath + "hotlist_mask_local.bak").c_str(), FALSE);
    }

    // 임시 파일에 쓴 뒤 바꿔 끼운다. 쓰다 끊겨 반쪽 마스크가 남지 않게.
    std::string text;
    for (int r = 0; r < GRID; ++r)
    {
        for (int c = 0; c < GRID; ++c)
        {
            if (c) text += ' ';
            text += char('0' + m_svr[r * GRID + c]);
        }
        text += "\r\n";
    }
    const std::string tmp = local + ".tmp";
    {
        std::ofstream f(tmp, std::ios::binary | std::ios::trunc);
        f << text;
        if (!f)
        {
            AfxMessageBox(CStringA("새 분석마스크를 쓰지 못했음") + failTail, MB_ICONERROR);
            Refresh();
            return;
        }
    }
    if (!MoveFileExA(tmp.c_str(), local.c_str(), MOVEFILE_REPLACE_EXISTING))
    {
        CStringA msg;
        msg.Format("새 분석마스크로 바꾸지 못했음 (err %lu)", GetLastError());
        AfxMessageBox(msg + failTail, MB_ICONERROR);
        DeleteFileA(tmp.c_str());
        Refresh();
        return;
    }

    LoadLocal();
    LoadPrev();
    Refresh();

    if (recount)
    {
        CStringA msg;
        msg.Format("설비 칸 수를 %d 칸으로 바꾸고 분석마스크를 교체했음\r\n\r\n"
                   "- 2·3단계는 초기화되어 다시 쌓임 · 그동안 1단계만 동작함\r\n"
                   "- 재학습은 %s 이후 자료만 씀\r\n\r\n"
                   "감시를 시작하면 새 분석마스크로 감시함",
                   n, recountAt.IsEmpty() ? "지금" : (LPCSTR)recountAt.Left(16));
        AfxMessageBox(msg, MB_ICONINFORMATION);
        return;
    }

    AfxMessageBox(running
        ? "교체했음\r\n감시가 돌고 있음 · '정지' 후 '시작'해야 새 분석마스크로 감시함"
        : "교체했음\r\n감시를 시작하면 새 분석마스크로 감시함",
        MB_ICONINFORMATION);
}

// 한 장의 8x8 그림. other 와 다른 칸은 빨간 테두리.
static void DrawGrid(CDC& dc, int x0, int y0, const std::vector<int>& m,
                     const std::vector<int>& other, const CStringA& title)
{
    // 제목은 두 줄 (이름 · 칸 수 / 시각). 한 줄이면 그림 폭을 넘는다.
    CRect tr(x0, y0 - 50, x0 + GRID * CELL + 40, y0 - 4);
    dc.DrawText(CString(title), &tr, DT_LEFT | DT_WORDBREAK);

    const COLORREF on = RGB(244, 158, 1), off = RGB(236, 238, 241), line = RGB(200, 204, 210);
    for (int r = 0; r < GRID; ++r)
    {
        for (int c = 0; c < GRID; ++c)
        {
            CRect rc(x0 + c * CELL, y0 + r * CELL, x0 + (c + 1) * CELL, y0 + (r + 1) * CELL);
            const int i = r * GRID + c;
            if (m.empty())
            {
                dc.FillSolidRect(&rc, RGB(250, 250, 250));
            }
            else
            {
                dc.FillSolidRect(&rc, m[i] ? on : off);
            }
            dc.Draw3dRect(&rc, line, line);
            if (!m.empty() && (int)other.size() == CELLS && other[i] != m[i])
            {
                CRect d = rc;
                d.DeflateRect(1, 1);
                dc.Draw3dRect(&d, RGB(220, 0, 0), RGB(220, 0, 0));
                d.DeflateRect(1, 1);
                dc.Draw3dRect(&d, RGB(220, 0, 0), RGB(220, 0, 0));
            }
        }
    }
    if (m.empty())
    {
        CRect rc(x0, y0, x0 + GRID * CELL, y0 + GRID * CELL);
        dc.DrawText(_T("없음"), &rc, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    }
}

void CDlg_MaskFetch::OnPaint()
{
    CPaintDC dc(this);
    CFont* old = m_font ? dc.SelectObject(m_font) : nullptr;
    dc.SetBkMode(TRANSPARENT);
    dc.SetTextColor(RGB(30, 30, 30));

    CStringA lt, rt;
    if (m_cur.empty())
        lt = "지금 쓰는 분석마스크 (없음)";
    else
        lt.Format("지금 쓰는 분석마스크 · %d칸\n%s", CountOnes(m_cur), m_curAt.c_str());

    const std::vector<int>& right = m_showPrev ? m_prev : m_svr;
    if (m_showPrev)
        rt.Format("이전 분석마스크 · %d칸\n%s", CountOnes(m_prev), m_prevAt.c_str());
    else if (m_svr.empty())
        rt = "관제서버 분석마스크 (받지 못함)";
    else
        rt.Format("관제서버 분석마스크 · %d칸\n방금 받음", CountOnes(m_svr));

    DrawGrid(dc, GX0, GY, m_cur, right, lt);
    DrawGrid(dc, GX1, GY, right, m_cur, rt);

    if (old) dc.SelectObject(old);
}
