// Dlg_BaseRef.cpp: RGB 기준 이미지 창
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_BaseRef.h"
#include "afxdialogex.h"

#include <string>
#include <vector>
#include <cstdio>
#include <cstdlib>

extern std::string gUserID;
extern const char* GetMmCamStartPath();
extern const char* GetAnacondaRootPub();
extern const char* GetAnacondaEnvPub();
extern std::string ini_read_utf8(const std::string&, const std::string&,
                                 const std::string&, const std::string&);

#define ID_BR_REF      3501
#define ID_BR_CUR      3502
#define ID_BR_CAPTURE  3503
#define ID_BR_REPLACE  3504
#define ID_BR_CHECKS   3505      // 화질 적합도
#define ID_BR_CHECKS2  3506      // 틀어짐 기준
#define WM_BR_AUTOCAP  (WM_APP + 31)

#define PIC_W   480        // 그림 한 장의 자리. 640x480 을 3/4 로 줄인다
#define PIC_H   360

static const COLORREF GRID_INK = RGB(0, 255, 0);       // 격자 (감시 화면과 같은 초록)
static const COLORREF MASK_INK = RGB(255, 64, 64);     // 점수가 보는 칸

// 현황 파일은 UTF-8 이고 이 빌드는 MBCS 다.
static CStringA U8(const std::string& u)
{
    if (u.empty()) return CStringA();
    const int wn = MultiByteToWideChar(CP_UTF8, 0, u.c_str(), -1, nullptr, 0);
    if (wn <= 0) return CStringA(u.c_str());
    CStringW w;
    MultiByteToWideChar(CP_UTF8, 0, u.c_str(), -1, w.GetBuffer(wn), wn);
    w.ReleaseBuffer();
    const int an = WideCharToMultiByte(CP_ACP, 0, w, -1, nullptr, 0, nullptr, nullptr);
    if (an <= 0) return CStringA(u.c_str());
    CStringA a;
    WideCharToMultiByte(CP_ACP, 0, w, -1, a.GetBuffer(an), an, nullptr, nullptr);
    a.ReleaseBuffer();
    return a;
}

BEGIN_MESSAGE_MAP(CDlg_BaseRef, CDialogEx)
    ON_WM_DRAWITEM()
    ON_BN_CLICKED(ID_BR_CAPTURE, &CDlg_BaseRef::OnCapture)
    ON_BN_CLICKED(ID_BR_REPLACE, &CDlg_BaseRef::OnReplace)
    ON_MESSAGE(WM_BR_AUTOCAP, &CDlg_BaseRef::OnAutoCapture)
    ON_NOTIFY(NM_CUSTOMDRAW, ID_BR_CHECKS, &CDlg_BaseRef::OnCustomDrawChecks)
    ON_NOTIFY(NM_CUSTOMDRAW, ID_BR_CHECKS2, &CDlg_BaseRef::OnCustomDrawChecks)
END_MESSAGE_MAP()

CDlg_BaseRef::CDlg_BaseRef(CFont* font, CWnd* parent)
    : CDialogEx(), m_font(font)
{
    // 창 틀은 .rc 에 두지 않고 여기서 만든다. 크기와 글꼴은 OnInitDialog 에서 정한다.
    m_tpl.assign(64, 0);
    DLGTEMPLATE* t = reinterpret_cast<DLGTEMPLATE*>(m_tpl.data());
    t->style = DS_MODALFRAME | WS_POPUP | WS_CAPTION | WS_SYSMENU;
    t->cx = 300; t->cy = 200;
    WORD* p = reinterpret_cast<WORD*>(t + 1);
    *p++ = 0;
    *p++ = 0;
    const wchar_t* cap = L"RGB \xAE30\xC900 \xC774\xBBF8\xC9C0";   // "RGB 기준 이미지"
    while (*cap) *p++ = (WORD)*cap++;
    *p++ = 0;
    InitModalIndirect(t, parent);
}

std::string CDlg_BaseRef::BaseDir() const
{
    return std::string(GetMmCamStartPath()) + "users\\" + gUserID + "\\base_img\\";
}

// 점수가 보는 칸. 두 그림에 같은 테두리를 그려, 그 칸이 같은 물체를 덮는지 본다.
void CDlg_BaseRef::LoadMask()
{
    m_mask.clear();
    const std::string env = std::string(GetMmCamStartPath()) + "users\\" + gUserID
                          + "\\env.ini";
    const int gx = atoi(ini_read_utf8(env, "CONSTANTS", "X_GRID", "8").c_str());
    const int gy = atoi(ini_read_utf8(env, "CONSTANTS", "Y_GRID", "8").c_str());
    if (gx > 0 && gy > 0) { m_gx = gx; m_gy = gy; }

    const std::string p = std::string(GetMmCamStartPath()) + "users\\" + gUserID
                        + "\\hotlist_mask_local.ini";
    FILE* f = nullptr;
    if (fopen_s(&f, p.c_str(), "rb") != 0 || f == nullptr) return;
    int c;
    while ((c = fgetc(f)) != EOF)
        if (c == '0' || c == '1') m_mask.push_back(c - '0');
    fclose(f);
    if ((int)m_mask.size() != m_gx * m_gy) m_mask.clear();
}

void CDlg_BaseRef::LoadImages()
{
    if (!m_imgRef.IsNull()) m_imgRef.Destroy();
    if (!m_imgCur.IsNull()) m_imgCur.Destroy();

    const std::string dir = BaseDir();
    m_haveRef = (GetFileAttributesA((dir + "base_ref.png").c_str()) != INVALID_FILE_ATTRIBUTES)
             && SUCCEEDED(m_imgRef.Load((dir + "base_ref.png").c_str()));
    m_haveCur = (GetFileAttributesA((dir + "_candidate.png").c_str()) != INVALID_FILE_ATTRIBUTES)
             && SUCCEEDED(m_imgCur.Load((dir + "_candidate.png").c_str()));
}

void CDlg_BaseRef::ReadResult()
{
    const std::string ini = BaseDir() + "_candidate.ini";
    m_curAt   = U8(ini_read_utf8(ini, "RESULT", "AT", ""));
    m_refAt   = U8(ini_read_utf8(ini, "RESULT", "REF_AT", ""));
    m_msg     = U8(ini_read_utf8(ini, "RESULT", "MSG", ""));
    m_dx      = atof(ini_read_utf8(ini, "RESULT", "DX", "0").c_str());
    m_dy      = atof(ini_read_utf8(ini, "RESULT", "DY", "0").c_str());
    m_resp    = atof(ini_read_utf8(ini, "RESULT", "RESP", "0").c_str());
    m_respMin = atof(ini_read_utf8(ini, "RESULT", "RESP_MIN", "0.30").c_str());
    m_cellX   = atoi(ini_read_utf8(ini, "RESULT", "CELL_X", "0").c_str());
    m_cellY   = atoi(ini_read_utf8(ini, "RESULT", "CELL_Y", "0").c_str());
    m_mean    = atoi(ini_read_utf8(ini, "RESULT", "MEAN", "-1").c_str());
    m_refMean = atoi(ini_read_utf8(ini, "RESULT", "REF_MEAN", "-1").c_str());

    m_chkQ.clear();
    m_chkS.clear();
    const int n = atoi(ini_read_utf8(ini, "RESULT", "N_CHECK", "0").c_str());
    for (int i = 1; i <= n && i <= 20; ++i)
    {
        char k[16];
        auto get = [&](const char* f) {
            sprintf_s(k, "C%d_%s", i, f);
            return U8(ini_read_utf8(ini, "RESULT", k, ""));
        };
        Check c;
        c.name = get("NAME"); c.rule = get("RULE"); c.ref = get("REF"); c.cur = get("CUR");
        c.ok = (get("OK") == "1");
        (get("GROUP") == "S" ? m_chkS : m_chkQ).push_back(c);
    }
    m_qualityOk = !m_chkQ.empty()
               && ini_read_utf8(ini, "RESULT", "QUALITY_OK", "0") == "1";

    // 기준 시각은 측정 파일이 없어도 보인다.
    if (m_refAt.IsEmpty() && m_haveRef)
    {
        WIN32_FILE_ATTRIBUTE_DATA fa;
        if (GetFileAttributesExA((BaseDir() + "base_ref.png").c_str(),
                                 GetFileExInfoStandard, &fa))
        {
            const CTime t(fa.ftLastWriteTime);
            m_refAt = CStringA(t.Format(_T("%Y-%m-%d %H:%M")));
        }
    }
}

void CDlg_BaseRef::ShowResult()
{
    CStringA a, b;
    a.Format("기준 이미지%s%s", m_refAt.IsEmpty() ? "" : "   ", (LPCSTR)m_refAt);
    if (m_refMean >= 0) a.AppendFormat("   (밝기 %d)", m_refMean);
    b.Format("현재 화면%s%s", m_curAt.IsEmpty() ? "" : "   ", (LPCSTR)m_curAt);
    if (m_mean >= 0 && m_haveCur) b.AppendFormat("   (밝기 %d)", m_mean);
    m_capRef.SetWindowTextA(a);
    m_capCur.SetWindowTextA(b);

    m_lstQ.DeleteAllItems();
    for (size_t i = 0; i < m_chkQ.size(); ++i)
    {
        const Check& c = m_chkQ[i];
        const int at = m_lstQ.InsertItem((int)i, CString(c.name));
        m_lstQ.SetItemText(at, 1, CString(c.rule));
        m_lstQ.SetItemText(at, 2, CString(c.ref));
        m_lstQ.SetItemText(at, 3, CString(c.cur));
        m_lstQ.SetItemText(at, 4, c.ok ? _T("적합") : _T("부적합"));
    }
    // 틀어짐 기준은 지금 화면을 기준과 견준 값이라 '기준 이미지' 칸이 없다.
    m_lstS.DeleteAllItems();
    for (size_t i = 0; i < m_chkS.size(); ++i)
    {
        const Check& c = m_chkS[i];
        const int at = m_lstS.InsertItem((int)i, CString(c.name));
        m_lstS.SetItemText(at, 1, CString(c.rule));
        m_lstS.SetItemText(at, 2, CString(c.cur));
        m_lstS.SetItemText(at, 3, c.ok ? _T("적합") : _T("부적합"));
    }

    CStringA r;
    if (!m_haveCur)
        r = m_msg.IsEmpty() ? CStringA("[현재 화면 찍기] 를 누르면 지금 RGB 화면을 받아 기준과 견줍니다.")
                            : "찍지 못했습니다 - " + m_msg;
    else if (!m_haveRef)
        r = "기준 이미지가 없습니다. 현재 화면을 보고 괜찮으면 기준으로 정하십시오.";
    else
    {
        r.Format("이동  가로 %+.1fpx (%+d칸) · 세로 %+.1fpx (%+d칸)    일치도 %.3f",
                 m_dx, m_cellX, m_dy, m_cellY, m_resp);
    }
    if (m_haveCur && !m_chkQ.empty())
    {
        int badQ = 0, badS = 0;
        for (const Check& c : m_chkQ) if (!c.ok) ++badQ;
        for (const Check& c : m_chkS) if (!c.ok) ++badS;
        if (badQ > 0)
            r.AppendFormat("\r\n화질 조건 %d개를 맞추지 못해 기준으로 쓸 수 없습니다 (왼쪽 표). "
                           "화면이 나아진 뒤 [현재 화면 찍기] 로 다시 찍으십시오.", badQ);
        else if (badS > 0)
            r += "\r\n위치 이동 기준을 맞추지 못합니다 (오른쪽 표). 바꾸면 카메라 자리가 바뀐 것으로 보고 "
                 "2·3단계를 내립니다.";
        else
            r += "\r\n조건을 모두 맞춥니다. 두 그림이 같은 설비를 같은 자리에 담고 있는지 눈으로 보고 바꾸십시오.";
    }
    m_lblResult.SetWindowTextA(r);
    // 화질이 기준으로 쓸 수 없으면 바꾸지 못한다. 그런 기준으로는 다음 기동부터
    // '판정 불가' 가 되기 쉽고, 카메라가 실제로 밀려도 잡지 못한다.
    m_btnReplace.EnableWindow(m_haveCur && m_qualityOk);

    m_picRef.Invalidate();
    m_picCur.Invalidate();
}

BOOL CDlg_BaseRef::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    const int M = 14, gap = 16, capH = 24, resH = 48, bH = 32, lstH = 156;
    const int W = M + PIC_W + gap + PIC_W + M;
    const int headH = 44;
    const int yCap = M + headH + 6;
    const int yPic = yCap + capH + 4;
    const int yRes = yPic + PIC_H + 10;
    const int yLstCap = yRes + resH + 4;
    const int yLst = yLstCap + capH;
    const int yBtn = yLst + lstH + 10;
    const int H = yBtn + bH + M;

    CRect wr(0, 0, W, H);
    AdjustWindowRectEx(&wr, GetStyle(), FALSE, GetExStyle());
    SetWindowPos(nullptr, 0, 0, wr.Width(), wr.Height(), SWP_NOMOVE | SWP_NOZORDER);
    CenterWindow();

    LOGFONT lf = {};
    if (m_font) m_font->GetLogFont(&lf);
    lf.lfWeight = FW_SEMIBOLD;
    m_fontBig.CreateFontIndirect(&lf);

    CStringA head;
    head.Format("[%s]  카메라 위치 이동을 재는 잣대입니다. 두 그림을 견주어 보고, 현재 화면이 "
                "기준으로 알맞을 때만 바꾸십시오.\r\n초록 선은 격자, 붉은 테두리는 점수가 "
                "보는 칸입니다. 바꾼 기준은 감시를 다시 시작할 때부터 쓰입니다.",
                gUserID.c_str());
    m_lblHead.Create(head, WS_CHILD | WS_VISIBLE | SS_LEFT, CRect(M, M, W - M, M + headH), this);

    const int x2 = M + PIC_W + gap;
    m_capRef.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT, CRect(M, yCap, M + PIC_W, yCap + capH), this);
    m_capCur.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT, CRect(x2, yCap, x2 + PIC_W, yCap + capH), this);
    m_picRef.Create("", WS_CHILD | WS_VISIBLE | SS_OWNERDRAW,
                    CRect(M, yPic, M + PIC_W, yPic + PIC_H), this, ID_BR_REF);
    m_picCur.Create("", WS_CHILD | WS_VISIBLE | SS_OWNERDRAW,
                    CRect(x2, yPic, x2 + PIC_W, yPic + PIC_H), this, ID_BR_CUR);
    m_lblResult.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT, CRect(M, yRes, W - M, yRes + resH), this);

    // 표 둘. 왼쪽은 화질 적합도(현재 화면이 기준으로 쓸 만한가), 오른쪽은 틀어짐
    // 기준(지금 기준과 견주어 카메라가 그대로인가).
    const DWORD lst = WS_CHILD | WS_VISIBLE | WS_BORDER | LVS_REPORT | LVS_NOSORTHEADER
                    | LVS_SINGLESEL;
    const DWORD lstx = LVS_EX_FULLROWSELECT | LVS_EX_GRIDLINES | LVS_EX_DOUBLEBUFFER;
    const int wQ = (W - 2 * M - gap) * 58 / 100;
    const int xS = M + wQ + gap;

    m_capQ.Create("화질 적합도   하나라도 부적합이면 기준으로 쓸 수 없습니다",
                  WS_CHILD | WS_VISIBLE | SS_LEFT, CRect(M, yLstCap, M + wQ, yLstCap + capH), this);
    m_lstQ.Create(lst, CRect(M, yLst, M + wQ, yLst + lstH), this, ID_BR_CHECKS);
    m_lstQ.SetExtendedStyle(lstx);
    {
        const int cw = wQ - 4;
        m_lstQ.InsertColumn(0, _T("항목"), LVCFMT_LEFT, cw * 18 / 100);
        m_lstQ.InsertColumn(1, _T("적합 조건"), LVCFMT_LEFT, cw * 24 / 100);
        m_lstQ.InsertColumn(2, _T("기준 이미지"), LVCFMT_RIGHT, cw * 20 / 100);
        m_lstQ.InsertColumn(3, _T("현재 화면"), LVCFMT_RIGHT, cw * 20 / 100);
        m_lstQ.InsertColumn(4, _T("판정"), LVCFMT_CENTER, cw * 18 / 100);
    }

    m_capS.Create("위치 이동 기준   부적합이면 2·3단계를 내리고 바꿉니다",
                  WS_CHILD | WS_VISIBLE | SS_LEFT, CRect(xS, yLstCap, W - M, yLstCap + capH), this);
    m_lstS.Create(lst, CRect(xS, yLst, W - M, yLst + lstH), this, ID_BR_CHECKS2);
    m_lstS.SetExtendedStyle(lstx);
    {
        const int cw = (W - M - xS) - 4;
        m_lstS.InsertColumn(0, _T("항목"), LVCFMT_LEFT, cw * 17 / 100);
        m_lstS.InsertColumn(1, _T("적합 조건"), LVCFMT_LEFT, cw * 33 / 100);
        m_lstS.InsertColumn(2, _T("현재 화면"), LVCFMT_RIGHT, cw * 35 / 100);
        m_lstS.InsertColumn(3, _T("판정"), LVCFMT_CENTER, cw * 15 / 100);
    }

    m_btnCapture.Create("현재 화면 찍기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                        CRect(M, yBtn, M + 160, yBtn + bH), this, ID_BR_CAPTURE);
    m_btnClose.Create("닫기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                      CRect(W - M - 120, yBtn, W - M, yBtn + bH), this, IDCANCEL);
    m_btnReplace.Create("기준으로 교체", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                        CRect(W - M - 120 - 8 - 160, yBtn, W - M - 128, yBtn + bH), this, ID_BR_REPLACE);

    if (m_font) SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font->GetSafeHandle(), TRUE);
    m_capRef.SetFont(&m_fontBig);
    m_capCur.SetFont(&m_fontBig);
    m_capQ.SetFont(&m_fontBig);
    m_capS.SetFont(&m_fontBig);

    // 지난번에 찍어 둔 것은 쓰지 않는다. 언제 찍은 것인지 헷갈린다.
    DeleteFileA((BaseDir() + "_candidate.png").c_str());
    DeleteFileA((BaseDir() + "_candidate.ini").c_str());

    LoadMask();
    LoadImages();
    ReadResult();
    ShowResult();

    // 열자마자 현재 화면을 받아 견준다. 창이 뜬 뒤에 돌려야 '받는 중' 이 보인다.
    PostMessage(WM_BR_AUTOCAP);
    return TRUE;
}

LRESULT CDlg_BaseRef::OnAutoCapture(WPARAM, LPARAM)
{
    OnCapture();
    return 0;
}

// 판정 칸만 칠한다. 적합은 연한 연두 바탕에 검정, 부적합은 진회색 바탕에 흰 글씨.
// 표를 훑어 어긋난 것부터 눈에 들어오게 한다. 나머지 칸은 기본 색 그대로다.
void CDlg_BaseRef::OnCustomDrawChecks(NMHDR* pNMHDR, LRESULT* pResult)
{
    static const COLORREF OK_BK  = RGB(214, 245, 190), OK_TX  = RGB(0, 0, 0);
    static const COLORREF BAD_BK = RGB(80, 80, 80),    BAD_TX = RGB(255, 255, 255);

    NMLVCUSTOMDRAW* cd = reinterpret_cast<NMLVCUSTOMDRAW*>(pNMHDR);
    *pResult = CDRF_DODEFAULT;
    switch (cd->nmcd.dwDrawStage)
    {
    case CDDS_PREPAINT:
        *pResult = CDRF_NOTIFYITEMDRAW;
        break;
    case CDDS_ITEMPREPAINT:
        // 고른 줄의 파란 칠이 판정 색을 덮지 않게 한다. 이 표는 고를 일이 없다.
        cd->nmcd.uItemState &= ~(CDIS_SELECTED | CDIS_FOCUS);
        *pResult = CDRF_NOTIFYSUBITEMDRAW;
        break;
    case CDDS_ITEMPREPAINT | CDDS_SUBITEM:
    {
        const bool shift = (pNMHDR->idFrom == ID_BR_CHECKS2);
        const std::vector<Check>& v = shift ? m_chkS : m_chkQ;
        const int judgeCol = shift ? 3 : 4;              // '판정' 열
        const size_t i = (size_t)cd->nmcd.dwItemSpec;

        // 칸마다 색을 다시 정한다. 정하지 않으면 앞 칸의 색이 뒤 칸으로 번진다.
        cd->clrText = GetSysColor(COLOR_WINDOWTEXT);
        cd->clrTextBk = GetSysColor(COLOR_WINDOW);
        if (cd->iSubItem == judgeCol && i < v.size())
        {
            cd->clrText = v[i].ok ? OK_TX : BAD_TX;
            cd->clrTextBk = v[i].ok ? OK_BK : BAD_BK;
        }
        break;
    }
    }
}

// 지금 RGB 화면을 받아 기준과 견준다. 몇 초 걸린다(파이썬과 OpenCV 를 띄운다).
void CDlg_BaseRef::OnCapture()
{
    m_lblResult.SetWindowTextA("현재 화면을 받아 기준과 견주는 중입니다 ...");
    m_lblResult.UpdateWindow();
    m_btnCapture.EnableWindow(FALSE);
    m_btnReplace.EnableWindow(FALSE);
    CWaitCursor wait;

    CStringA cmd;
    cmd.Format("cmd.exe /c call \"%sScripts\\activate.bat\" %s "
               "&& cd /d \"%s\" && set PYTHONIOENCODING=utf-8 "
               "&& python retrain\\base_ref_tool.py \"%s\" capture",
               GetAnacondaRootPub(), GetAnacondaEnvPub(),
               GetMmCamStartPath(), gUserID.c_str());

    STARTUPINFOA si = { sizeof(si) };
    PROCESS_INFORMATION pi = { 0 };
    std::vector<char> line(cmd.GetString(), cmd.GetString() + cmd.GetLength() + 1);
    bool ran = false;
    if (CreateProcessA(nullptr, line.data(), nullptr, nullptr, FALSE,
                       CREATE_NO_WINDOW, nullptr, GetMmCamStartPath(), &si, &pi))
    {
        ran = (WaitForSingleObject(pi.hProcess, 60000) == WAIT_OBJECT_0);
        if (!ran) TerminateProcess(pi.hProcess, 1);
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }

    LoadImages();
    ReadResult();
    if (!ran && m_msg.IsEmpty())
        m_msg = "도구를 실행하지 못했거나 1분 안에 끝나지 않았습니다";
    m_btnCapture.EnableWindow(TRUE);
    ShowResult();
}

// 현재 화면을 새 기준으로. 쓰던 기준은 unused 로 옮겨 되살릴 수 있게 둔다.
void CDlg_BaseRef::OnReplace()
{
    if (!m_haveCur || !m_qualityOk) return;     // 화질이 기준으로 쓸 수 없으면 바꾸지 않는다
    m_relocated.Empty();

    // 맞추지 못한 틀어짐 기준을 다시 보여 준다. 표를 지나쳤어도 여기서는 읽게 된다.
    CStringA warn;
    for (const Check& c : m_chkS)
        if (!c.ok)
            warn.AppendFormat("    %s  %s  (조건 %s)\r\n", (LPCSTR)c.name, (LPCSTR)c.cur,
                              (LPCSTR)c.rule);
    if (!warn.IsEmpty())
        warn = "다음 조건을 맞추지 못합니다.\r\n" + warn + "\r\n";

    // 칸 단위로 밀렸거나 같은 장면으로 볼 수 없으면, 기준을 바꾸는 것은 카메라
    // 자리를 새로 정하는 일이다. 같은 칸이 설비의 다른 곳을 보므로 옛 자리로 배운
    // 2단계(칸마다 평소 온도)와 3단계(칸들의 조합)는 뜻을 잃는다. 함께 내린다.
    const bool relocate = m_haveRef &&
        (m_cellX != 0 || m_cellY != 0 || m_resp < m_respMin);

    if (relocate)
    {
        // 감시가 돌고 있으면 메모리의 기준선과 모델이 그대로 남아, 내린 것을
        // 200건 뒤에 다시 써 놓는다.
        CMmCammonitoringDlg* main = dynamic_cast<CMmCammonitoringDlg*>(AfxGetMainWnd());
        if (main != nullptr && main->IsPredictRunning(gUserID.c_str()))
        {
            AfxMessageBox("[카메라 위치 이동 발견됨]\r\n\r\n"
                          "- 2·3 분석 단계 초기화\r\n"
                          "- 기준 이미지 교체\r\n"
                          "감시 프로그램을 정지한 뒤 [기준으로 교체]를 다시 누르십시오.",
                          MB_ICONWARNING);
            return;
        }

        CStringA q;
        // 짧게 쓴다. 자세한 것은 창의 '위치 이동 기준' 표와 끝난 뒤 알림에 있다.
        q.Format("[카메라 위치 이동 발견됨]\r\n"
                 "가로 %+d칸 · 세로 %+d칸 · 일치도 %.3f\r\n\r\n"
                 "교체하면\r\n"
                 "- 2·3 분석 단계 초기화 (다시 설 때까지 1단계만 동작)\r\n"
                 "- 재학습은 지금 이후 자료만 사용\r\n"
                 "- 기준 이미지 교체\r\n\r\n"
                 "진행할까요?",
                 m_cellX, m_cellY, m_resp);
        if (AfxMessageBox(q, MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2) != IDYES)
            return;

        // 2·3단계를 먼저 내린다. 실패하면 기준도 바꾸지 않는다 - 기준만 바뀌면
        // 경고가 꺼진 채 틀린 점수로 돈다.
        CWaitCursor wait;
        CStringA cmd;
        cmd.Format("cmd.exe /c call \"%sScripts\\activate.bat\" %s "
                   "&& cd /d \"%s\" && set PYTHONIOENCODING=utf-8 "
                   "&& python retrain\\base_ref_tool.py \"%s\" relocate",
                   GetAnacondaRootPub(), GetAnacondaEnvPub(),
                   GetMmCamStartPath(), gUserID.c_str());
        STARTUPINFOA si = { sizeof(si) };
        PROCESS_INFORMATION pi = { 0 };
        std::vector<char> line(cmd.GetString(), cmd.GetString() + cmd.GetLength() + 1);
        DWORD code = 1;
        DeleteFileA((BaseDir() + "_relocate.ini").c_str());
        if (CreateProcessA(nullptr, line.data(), nullptr, nullptr, FALSE,
                           CREATE_NO_WINDOW, nullptr, GetMmCamStartPath(), &si, &pi))
        {
            if (WaitForSingleObject(pi.hProcess, 60000) == WAIT_OBJECT_0)
                GetExitCodeProcess(pi.hProcess, &code);
            else
                TerminateProcess(pi.hProcess, 1);
            CloseHandle(pi.hThread);
            CloseHandle(pi.hProcess);
        }
        const std::string ri = BaseDir() + "_relocate.ini";
        if (code != 0 || ini_read_utf8(ri, "RESULT", "OK", "0") != "1")
        {
            AfxMessageBox("2·3단계를 내리지 못했습니다. 기준 이미지도 바꾸지 않았습니다.\r\n\r\n"
                          "명령 창에서 python retrain\\base_ref_tool.py <현장> relocate 를 "
                          "돌려 원인을 확인하십시오.", MB_ICONERROR);
            return;
        }
        // 끝난 뒤 알림에는 언제부터의 자료를 쓰는지만 적는다. 옮긴 곳의 경로는
        // 도구가 남긴 _relocate.ini 와 각 폴더의 note.txt 에 있다.
        m_relocated = U8(ini_read_utf8(ri, "RESULT", "AT", ""));
        if (m_relocated.GetLength() > 16) m_relocated = m_relocated.Left(16);   // 초는 뺀다
        if (m_relocated.IsEmpty()) m_relocated = "지금";
    }
    else
    {
        CStringA q;
        q.Format("현재 화면(%s)을 RGB 기준 이미지로 정합니다.\r\n\r\n%s"
                 "쓰던 기준은 base_img\\unused 로 옮겨 둡니다. 새 기준은 감시를 다시 "
                 "시작할 때부터 쓰입니다.\r\n\r\n진행할까요?",
                 (LPCSTR)m_curAt, (LPCSTR)warn);
        if (AfxMessageBox(q, MB_YESNO | (warn.IsEmpty() ? MB_ICONQUESTION : MB_ICONWARNING)
                          | MB_DEFBUTTON2) != IDYES)
            return;
    }

    // 그림을 놓아야 파일을 옮길 수 있다.
    if (!m_imgRef.IsNull()) m_imgRef.Destroy();
    if (!m_imgCur.IsNull()) m_imgCur.Destroy();

    const std::string dir = BaseDir();
    const std::string ref = dir + "base_ref.png";
    const std::string cand = dir + "_candidate.png";

    CStringA backup;
    if (GetFileAttributesA(ref.c_str()) != INVALID_FILE_ATTRIBUTES)
    {
        CreateDirectoryA((dir + "unused").c_str(), nullptr);
        const CTime now = CTime::GetCurrentTime();
        backup.Format("%sunused\\base_ref_%s.png", dir.c_str(),
                      (LPCSTR)CStringA(now.Format(_T("%Y%m%d_%H%M%S"))));
        if (!MoveFileExA(ref.c_str(), backup, MOVEFILE_WRITE_THROUGH))
        {
            CStringA m;
            m.Format("쓰던 기준을 옮기지 못했습니다 (오류 %lu). 아무것도 바꾸지 않았습니다.",
                     GetLastError());
            AfxMessageBox(m, MB_ICONERROR);
            LoadImages(); ShowResult();
            return;
        }
    }
    if (!MoveFileExA(cand.c_str(), ref.c_str(), MOVEFILE_WRITE_THROUGH))
    {
        const DWORD e = GetLastError();
        if (!backup.IsEmpty()) MoveFileExA(backup, ref.c_str(), 0);   // 되돌린다
        CStringA m;
        m.Format("새 기준을 놓지 못했습니다 (오류 %lu). 쓰던 기준을 되돌려 놓았습니다.", e);
        if (!m_relocated.IsEmpty())
            m += "\r\n\r\n2·3단계는 이미 내렸습니다. 기준 이미지를 다시 바꾸거나, 치운 파일을 model_generations 에서 되돌려 놓으십시오.";
        AfxMessageBox(m, MB_ICONERROR);
        LoadImages(); ShowResult();
        return;
    }
    DeleteFileA((dir + "_candidate.ini").c_str());

    LoadImages();
    m_curAt.Empty(); m_msg.Empty(); m_mean = -1; m_refMean = -1; m_refAt.Empty();
    ReadResult();
    ShowResult();

    // 짧게 쓴다. 쓰던 것을 어디로 옮겼는지는 묻지 않는 한 필요 없다 - 지우지 않았다는
    // 것만 알면 된다.
    CStringA done = "기준 이미지를 바꿨습니다.\r\n\r\n";
    if (!m_relocated.IsEmpty())
        done += "- 2·3 분석 단계 초기화\r\n"
                "- 재학습은 " + m_relocated + " 이후 자료만 사용\r\n";
    if (!backup.IsEmpty() || !m_relocated.IsEmpty())
        done += "- 쓰던 것은 지우지 않고 보관\r\n";
    done += "\r\n감시를 다시 시작하면 새 기준으로 잽니다.";
    if (!m_relocated.IsEmpty())
        done += "\r\n3단계는 새 자리 자료가 모인 뒤 [재학습] 으로 다시 세우십시오.";
    AfxMessageBox(done, MB_ICONINFORMATION);
}

// 그림을 칸에 맞춰 줄이고, 격자와 마스크 칸을 겹쳐 그린다.
void CDlg_BaseRef::DrawPic(CDC* dc, const CRect& rc, CImage& img, const char* empty)
{
    dc->FillSolidRect(rc, RGB(40, 40, 40));
    if (img.IsNull())
    {
        dc->SetBkMode(TRANSPARENT);
        dc->SetTextColor(RGB(220, 220, 220));
        CRect r = rc;
        dc->DrawTextA(empty, -1, &r, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        return;
    }

    // 가로세로 비를 지킨다. 틀어짐을 보는 그림이 찌그러지면 안 된다.
    const double s = min((double)rc.Width() / img.GetWidth(),
                         (double)rc.Height() / img.GetHeight());
    const int w = (int)(img.GetWidth() * s), h = (int)(img.GetHeight() * s);
    const CRect d(rc.left + (rc.Width() - w) / 2, rc.top + (rc.Height() - h) / 2,
                  rc.left + (rc.Width() - w) / 2 + w, rc.top + (rc.Height() - h) / 2 + h);

    dc->SetStretchBltMode(HALFTONE);
    img.StretchBlt(dc->GetSafeHdc(), d, SRCCOPY);

    CPen grid(PS_SOLID, 1, GRID_INK);
    CPen* old = dc->SelectObject(&grid);
    for (int i = 1; i < m_gx; ++i)
    {
        const int x = d.left + d.Width() * i / m_gx;
        dc->MoveTo(x, d.top); dc->LineTo(x, d.bottom);
    }
    for (int j = 1; j < m_gy; ++j)
    {
        const int y = d.top + d.Height() * j / m_gy;
        dc->MoveTo(d.left, y); dc->LineTo(d.right, y);
    }

    if ((int)m_mask.size() == m_gx * m_gy)
    {
        CPen pm(PS_SOLID, 2, MASK_INK);
        dc->SelectObject(&pm);
        dc->SelectStockObject(NULL_BRUSH);
        for (int j = 0; j < m_gy; ++j)
            for (int i = 0; i < m_gx; ++i)
                if (m_mask[j * m_gx + i])
                    dc->Rectangle(d.left + d.Width() * i / m_gx + 1,
                                  d.top + d.Height() * j / m_gy + 1,
                                  d.left + d.Width() * (i + 1) / m_gx,
                                  d.top + d.Height() * (j + 1) / m_gy);
        dc->SelectObject(&grid);
    }
    dc->SelectObject(old);
}

void CDlg_BaseRef::OnDrawItem(int nIDCtl, LPDRAWITEMSTRUCT lpDIS)
{
    if (nIDCtl == ID_BR_REF || nIDCtl == ID_BR_CUR)
    {
        CDC* dc = CDC::FromHandle(lpDIS->hDC);
        const CRect rc(lpDIS->rcItem);
        if (nIDCtl == ID_BR_REF)
            DrawPic(dc, rc, m_imgRef, "기준 이미지가 없습니다");
        else
            DrawPic(dc, rc, m_imgCur, "아직 찍지 않았습니다");
        return;
    }
    CDialogEx::OnDrawItem(nIDCtl, lpDIS);
}
