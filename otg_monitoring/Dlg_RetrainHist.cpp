// Dlg_RetrainHist.cpp: 재학습 이력 창
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_RetrainHist.h"
#include "afxdialogex.h"

#include <string>
#include <vector>

extern std::string gUserID;
extern const char* GetMmCamStartPath();
extern std::string ini_read_utf8(const std::string&, const std::string&,
                                 const std::string&, const std::string&);
extern bool ini_write_int_utf8(const std::string&, const std::string&,
                               const std::string&, int);

#define ID_RH_LOG     3601
#define ID_RH_RELOAD  3602
#define ID_RH_AUTO    3603
#define ID_RH_HOURS   3604
#define ID_RH_SAVE    3605

// 이력 파일은 UTF-8 이고 이 빌드는 MBCS 다.
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

BEGIN_MESSAGE_MAP(CDlg_RetrainHist, CDialogEx)
    ON_BN_CLICKED(ID_RH_RELOAD, &CDlg_RetrainHist::OnReload)
    ON_BN_CLICKED(ID_RH_AUTO, &CDlg_RetrainHist::OnAutoChanged)
    ON_EN_CHANGE(ID_RH_HOURS, &CDlg_RetrainHist::OnAutoChanged)
    ON_BN_CLICKED(ID_RH_SAVE, &CDlg_RetrainHist::OnSaveAuto)
END_MESSAGE_MAP()

CDlg_RetrainHist::CDlg_RetrainHist(CFont* font, CWnd* parent)
    : CDialogEx(), m_font(font)
{
    m_tpl.assign(64, 0);
    DLGTEMPLATE* t = reinterpret_cast<DLGTEMPLATE*>(m_tpl.data());
    t->style = DS_MODALFRAME | WS_POPUP | WS_CAPTION | WS_SYSMENU;
    t->cx = 300; t->cy = 200;
    WORD* p = reinterpret_cast<WORD*>(t + 1);
    *p++ = 0;
    *p++ = 0;
    const wchar_t* cap = L"\xC7AC\xD559\xC2B5 \xC774\xB825";   // "재학습 이력"
    while (*cap) *p++ = (WORD)*cap++;
    *p++ = 0;
    InitModalIndirect(t, parent);
}

BOOL CDlg_RetrainHist::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    const int M = 12, W = 820, H = 560, bH = 32, headH = 26;
    CRect wr(0, 0, W, H);
    AdjustWindowRectEx(&wr, GetStyle(), FALSE, GetExStyle());
    SetWindowPos(nullptr, 0, 0, wr.Width(), wr.Height(), SWP_NOMOVE | SWP_NOZORDER);
    CenterWindow();

    // [재학습] 창의 이력과 같은 글꼴. 고정폭 글꼴(D2Coding)을 시험했더니 없는 PC 에서
    // 한글이 없는 대체 글꼴로 바뀌어 글자가 겹쳤다. 시각 · 점수 · w 는 자릿수가 같아
    // 이 글꼴로도 줄이 맞는다.
    m_fontMono.CreateFont(UI_FONT_SIZE, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    // 자동 재학습 줄. 체크박스 - 간격 - 설명 - [설정저장].
    const int autoH = 32;
    {
        long chkW;
        {
            CClientDC dc(this);
            CFont* old = m_font ? dc.SelectObject(m_font) : nullptr;
            chkW = 24 + dc.GetTextExtent(CString("자동 재학습")).cx;
            if (old) dc.SelectObject(old);
        }
        const long edW = 56, sW = 120;
        const long x1 = M + chkW + 6, x2 = x1 + edW + 6;
        m_chkAuto.Create("자동 재학습", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX,
                         CRect(M, M + 4, x1 - 2, M + 4 + 22), this, ID_RH_AUTO);
        m_edHours.Create(WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_RIGHT | ES_NUMBER,
                         CRect(x1, M + 3, x1 + edW, M + 3 + 24), this, ID_RH_HOURS);
        m_lblAuto.Create("시간마다 · 기여 w < 1.00 이면 감도 시험을 거쳐 자동 교체",
                         WS_CHILD | WS_VISIBLE | SS_LEFT,
                         CRect(x2, M + 6, W - M - sW - 10, M + 6 + 22), this);
        m_btnSave.Create("설정저장", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                         CRect(W - M - sW, M, W - M, M + autoH), this, ID_RH_SAVE);
    }

    const int yHead = M + autoH + 10;
    m_lblHead.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT, CRect(M, yHead, W - M, yHead + headH), this);
    const int yLog = yHead + headH + 4, yBtn = H - M - bH;
    m_edLog.Create(WS_CHILD | WS_VISIBLE | WS_BORDER | WS_VSCROLL | WS_HSCROLL
                   | ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL | ES_AUTOHSCROLL,
                   CRect(M, yLog, W - M, yBtn - 10), this, ID_RH_LOG);
    m_btnReload.Create("다시 읽기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                       CRect(M, yBtn, M + 120, yBtn + bH), this, ID_RH_RELOAD);
    m_btnClose.Create("닫기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
                      CRect(W - M - 120, yBtn, W - M, yBtn + bH), this, IDCANCEL);

    if (m_font) SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font->GetSafeHandle(), TRUE);
    m_edLog.SetFont(&m_fontMono);


    LoadAuto();
    Fill();
    m_btnClose.SetFocus();
    return FALSE;
}

void CDlg_RetrainHist::OnReload() { Fill(); }

// 자동 재학습. 체크하면 감시가 기여 w 가 1.00 미만일 때 마지막 시작 뒤 간격(시간)이
// 지났으면 재학습을 띄운다(predict_machine/auto_retrain.py).
void CDlg_RetrainHist::LoadAuto()
{
    const std::string ini = std::string(GetMmCamStartPath()) + "users\\" + gUserID
                          + "\\continual_learning.ini";
    const std::string on = ini_read_utf8(ini, "CONSTANTS", "AUTO_RETRAIN", "0");
    std::string hrs = ini_read_utf8(ini, "CONSTANTS", "AUTO_RETRAIN_HOURS", "24");
    if (atoi(hrs.c_str()) < 1) hrs = "24";

    m_loading = true;
    m_chkAuto.SetCheck(atoi(on.c_str()) ? BST_CHECKED : BST_UNCHECKED);
    m_edHours.SetWindowTextA(hrs.c_str());
    m_loading = false;
    m_dirty = false;
    UpdateAutoEnable();
}

void CDlg_RetrainHist::UpdateAutoEnable()
{
    const BOOL on = (m_chkAuto.GetCheck() == BST_CHECKED) ? TRUE : FALSE;
    m_edHours.EnableWindow(on);
    m_lblAuto.EnableWindow(on);
    m_btnSave.EnableWindow(m_dirty);     // 고친 것이 있을 때만
}

void CDlg_RetrainHist::OnAutoChanged()
{
    if (m_loading) return;
    m_dirty = true;
    UpdateAutoEnable();
}

// [설정저장]. 무엇이 어떻게 바뀌는지 적어 보이고, 확인한 뒤에만 쓴다.
// 감시가 저장하는 즉시 따르므로 묻고 쓴다.
void CDlg_RetrainHist::OnSaveAuto()
{
    CString t;
    m_edHours.GetWindowTextA(t);
    int hrs = atoi(t);
    if (hrs < 1)   hrs = 1;
    if (hrs > 720) hrs = 720;
    const int on = (m_chkAuto.GetCheck() == BST_CHECKED) ? 1 : 0;

    CStringA ask;
    if (on)
        ask.Format("자동 재학습을 켬 (%d시간 간격).\r\n\r\n"
                   "기여 w 가 1.00 미만이면 학습하고, 감도 시험을 통과하면 모델을 바로 "
                   "교체함 · 감시가 저장하는 즉시 따름\r\n\r\n저장할지 확인", hrs);
    else
        ask = "자동 재학습을 끔\r\n\r\n저장할지 확인";
    if (AfxMessageBox(ask, MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2) != IDYES)
        return;

    const std::string ini = std::string(GetMmCamStartPath()) + "users\\" + gUserID
                          + "\\continual_learning.ini";
    if (!(ini_write_int_utf8(ini, "CONSTANTS", "AUTO_RETRAIN", on)
          && ini_write_int_utf8(ini, "CONSTANTS", "AUTO_RETRAIN_HOURS", hrs)))
    {
        AfxMessageBox("continual_learning.ini 를 쓰지 못했음", MB_ICONERROR);
        return;
    }
    LoadAuto();
}

// 저장하지 않고 닫으면 묻는다.
void CDlg_RetrainHist::OnCancel()
{
    if (m_dirty &&
        AfxMessageBox("자동 재학습 설정을 저장하지 않았음 · 그대로 닫을지 확인",
                      MB_YESNO | MB_ICONQUESTION | MB_DEFBUTTON2) != IDYES)
        return;
    CDialogEx::OnCancel();
}

// 최근 것부터 모두 적는다. 줄의 꼴은 [재학습] 창의 이력과 같다.
void CDlg_RetrainHist::Fill()
{
    std::vector<std::string> rows;
    CStdioFile f;
    const std::string path = std::string(GetMmCamStartPath()) + "users\\" + gUserID
                           + "\\auto_retrain_history.txt";
    if (f.Open(path.c_str(), CFile::modeRead | CFile::typeText | CFile::shareDenyNone))
    {
        CStringA ln;
        while (f.ReadString(ln))
        {
            ln.Trim();
            if (!ln.IsEmpty()) rows.push_back(std::string((LPCSTR)ln));
        }
        f.Close();
    }

    CStringA head;
    head.Format("[%s] 자동 재학습 이력   전체 %d건 · 최근 것부터", gUserID.c_str(),
                (int)rows.size());
    m_lblHead.SetWindowTextA(head);

    CStringA all;
    if (rows.empty())
        all = "    (아직 없음)\r\n";

    for (size_t n = 0; n < rows.size(); ++n)
    {
        const std::string& r = rows[rows.size() - 1 - n];
        std::vector<std::string> c;
        size_t b = 0;
        for (;;)
        {
            const size_t e = r.find('\t', b);
            if (e == std::string::npos) { c.push_back(r.substr(b)); break; }
            c.push_back(r.substr(b, e - b));
            b = e + 1;
        }
        while (c.size() < 6) c.push_back("");

        // 시작은 분까지, 종료는 시각만. 같은 날 안에 끝나는 것이 보통이다.
        const std::string st = c[0].substr(0, 16);
        const std::string en = (c[1].size() >= 16) ? c[1].substr(11, 5) : "";
        std::string sc = c[5];
        while (!sc.empty() && (sc.back() == '\r' || sc.back() == ' ')) sc.pop_back();
        if (sc.empty()) sc = "  -   ";

        // 파일 글(UTF-8)은 칸마다 화면 부호로 옮긴 뒤 붙인다. 여기 적은 한글은 이미
        // 화면 부호라, 한데 붙여 옮기면 그 글자가 깨진다.
        CStringA line;
        line.Format("    %s%s   점수 %s  w %s   %s", st.c_str(),
                    en.empty() ? "" : (" ~ " + en).c_str(), sc.c_str(), c[2].c_str(),
                    (LPCSTR)U8(c[3]));
        if (!c[4].empty()) line += "   " + CStringA(c[4].c_str());
        all += line + "\r\n";
    }
    m_edLog.SetWindowTextA(all);
}
