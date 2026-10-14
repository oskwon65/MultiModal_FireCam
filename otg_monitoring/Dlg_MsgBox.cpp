// Dlg_MsgBox.cpp: 알림창 (설정 영역과 같은 글꼴의 메시지 상자)
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"   // UI_FONT_NAME · UI_FONT_SIZE
#include "Dlg_MsgBox.h"
#include "afxdialogex.h"

static const int P = 20;            // 바깥 여백
static const int ICON = 32;
static const int BTN_W = 100, BTN_H = 32, BTN_GAP = 8;
static const int BAR_H = 56;        // 아래 버튼 띠
static const int TEXT_MIN = 260, TEXT_MAX = 560;

static int imax(int a, int b) { return a > b ? a : b; }

static const COLORREF C_BG  = RGB(255, 255, 255);
static const COLORREF C_BAR = RGB(240, 240, 240);

int KictMessageBox(CWnd* owner, LPCSTR text, LPCSTR caption, UINT type)
{
    CDlg_MsgBox dlg(owner, text, caption, type);
    return (int)dlg.DoModal();
}

BEGIN_MESSAGE_MAP(CDlg_MsgBox, CDialogEx)
    ON_WM_PAINT()
    ON_WM_ERASEBKGND()
    ON_WM_CTLCOLOR()
END_MESSAGE_MAP()

CDlg_MsgBox::CDlg_MsgBox(CWnd* owner, LPCSTR text, LPCSTR caption, UINT type)
    : CDialogEx(), m_text(text ? text : ""), m_type(type)
{
    m_caption = (caption && *caption) ? CStringA(caption) : CStringA(AfxGetAppName());

    m_tpl.assign(64, 0);
    DLGTEMPLATE* t = reinterpret_cast<DLGTEMPLATE*>(m_tpl.data());
    t->style = DS_MODALFRAME | WS_POPUP | WS_CAPTION | WS_SYSMENU;
    t->cx = 200; t->cy = 100;
    WORD* p = reinterpret_cast<WORD*>(t + 1);
    *p++ = 0;
    *p++ = 0;
    *p++ = 0;                       // 제목은 OnInitDialog 에서 넣는다
    InitModalIndirect(t, CWnd::GetSafeOwner(owner));

    // 버튼 묶음과 Esc 가 돌려줄 값. 기본 메시지 상자와 같게.
    switch (type & MB_TYPEMASK)
    {
    case MB_OKCANCEL:
        m_btns = { { IDOK, "확인" }, { IDCANCEL, "취소" } };
        break;
    case MB_YESNO:
        m_btns = { { IDYES, "예(Y)" }, { IDNO, "아니요(N)" } };
        m_escId = IDNO;
        break;
    case MB_YESNOCANCEL:
        m_btns = { { IDYES, "예(Y)" }, { IDNO, "아니요(N)" }, { IDCANCEL, "취소" } };
        break;
    case MB_RETRYCANCEL:
        m_btns = { { IDRETRY, "다시 시도(R)" }, { IDCANCEL, "취소" } };
        break;
    default:
        m_btns = { { IDOK, "확인" } };
        m_escId = IDOK;
        break;
    }

    switch (type & MB_ICONMASK)
    {
    case MB_ICONERROR:       m_icon = ::LoadIcon(nullptr, IDI_ERROR);       break;
    case MB_ICONWARNING:     m_icon = ::LoadIcon(nullptr, IDI_WARNING);     break;
    case MB_ICONINFORMATION: m_icon = ::LoadIcon(nullptr, IDI_INFORMATION); break;
    case MB_ICONQUESTION:    m_icon = ::LoadIcon(nullptr, IDI_QUESTION);    break;
    default: break;
    }
}

BOOL CDlg_MsgBox::OnInitDialog()
{
    CDialogEx::OnInitDialog();
    SetWindowText(CString(m_caption));

    // 설정 영역과 같은 글꼴 (Dlg_Set_MmCam_Env 의 m_stdFont 와 같은 값)
    m_font.CreateFont(UI_FONT_SIZE, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    // 글 크기를 재서 창 크기를 정한다. 너무 길면 TEXT_MAX 에서 줄을 바꾼다.
    CRect rt(0, 0, TEXT_MAX, 0);
    {
        CClientDC dc(this);
        CFont* old = dc.SelectObject(&m_font);
        dc.DrawText(CString(m_text), &rt,
                    DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX | DT_EXPANDTABS);
        dc.SelectObject(old);
    }
    const int textW = imax(TEXT_MIN, (int)rt.Width());
    const int textH = imax(ICON, (int)rt.Height());
    const int left = P + (m_icon ? ICON + 14 : 0);

    const int btnsW = (int)m_btns.size() * BTN_W + ((int)m_btns.size() - 1) * BTN_GAP;
    const int W = imax(left + textW + P, btnsW + 2 * P);
    m_rcText = CRect(left, P + 4, left + textW, P + 4 + textH);
    m_barTop = m_rcText.bottom + P;
    const int H = m_barTop + BAR_H;

    CRect wr(0, 0, W, H);
    AdjustWindowRectEx(&wr, GetStyle(), FALSE, GetExStyle());
    SetWindowPos(nullptr, 0, 0, wr.Width(), wr.Height(), SWP_NOMOVE | SWP_NOZORDER);
    CenterWindow();

    // 버튼은 오른쪽 아래부터
    int def = 0;
    if ((m_type & MB_DEFMASK) == MB_DEFBUTTON2) def = 1;
    if ((m_type & MB_DEFMASK) == MB_DEFBUTTON3) def = 2;
    if (def >= (int)m_btns.size()) def = 0;

    int x = W - P - btnsW;
    const int y = m_barTop + (BAR_H - BTN_H) / 2;
    for (size_t i = 0; i < m_btns.size(); ++i)
    {
        auto b = std::make_unique<CButton>();
        DWORD st = WS_CHILD | WS_VISIBLE | WS_TABSTOP |
                   ((int)i == def ? BS_DEFPUSHBUTTON : BS_PUSHBUTTON);
        b->Create(m_btns[i].label, st, CRect(x, y, x + BTN_W, y + BTN_H), this, m_btns[i].id);
        b->SetFont(&m_font);
        m_wnds.push_back(std::move(b));
        x += BTN_W + BTN_GAP;
    }
    m_wnds[def]->SetFocus();
    SetDefID(m_btns[def].id);

    // 기본 메시지 상자처럼 소리를 낸다
    UINT beep = MB_OK;
    switch (m_type & MB_ICONMASK)
    {
    case MB_ICONERROR:       beep = MB_ICONHAND;        break;
    case MB_ICONWARNING:     beep = MB_ICONEXCLAMATION; break;
    case MB_ICONINFORMATION: beep = MB_ICONASTERISK;    break;
    case MB_ICONQUESTION:    beep = MB_ICONQUESTION;    break;
    default: break;
    }
    ::MessageBeep(beep);

    return FALSE;   // 포커스를 직접 정했다
}

// 버튼 누르면 그 ID 로 닫는다
BOOL CDlg_MsgBox::OnCommand(WPARAM wParam, LPARAM lParam)
{
    const int id = LOWORD(wParam);
    if (HIWORD(wParam) == BN_CLICKED)
    {
        for (const Btn& b : m_btns)
        {
            if (b.id == id)
            {
                EndDialog(id);
                return TRUE;
            }
        }
    }
    return CDialogEx::OnCommand(wParam, lParam);
}

// Enter: 기본 버튼 (대화상자 관리자가 기본 버튼 ID 로 보낸다)
void CDlg_MsgBox::OnOK()
{
    const int id = (int)LOWORD(GetDefID());
    EndDialog(id ? id : IDOK);
}

// Esc / 닫기 단추
void CDlg_MsgBox::OnCancel()
{
    EndDialog(m_escId);
}

BOOL CDlg_MsgBox::OnEraseBkgnd(CDC* pDC)
{
    CRect rc;
    GetClientRect(&rc);
    pDC->FillSolidRect(CRect(0, 0, rc.right, m_barTop), C_BG);
    pDC->FillSolidRect(CRect(0, m_barTop, rc.right, rc.bottom), C_BAR);
    return TRUE;
}

HBRUSH CDlg_MsgBox::OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor)
{
    HBRUSH hbr = CDialogEx::OnCtlColor(pDC, pWnd, nCtlColor);
    if (nCtlColor == CTLCOLOR_BTN)
    {
        static CBrush bar(C_BAR);
        pDC->SetBkColor(C_BAR);
        return bar;
    }
    return hbr;
}

void CDlg_MsgBox::OnPaint()
{
    CPaintDC dc(this);
    if (m_icon)
        ::DrawIconEx(dc.GetSafeHdc(), P, P, m_icon, ICON, ICON, 0, nullptr, DI_NORMAL);

    CFont* old = dc.SelectObject(&m_font);
    dc.SetBkMode(TRANSPARENT);
    dc.SetTextColor(RGB(0, 0, 0));
    CRect r = m_rcText;
    dc.DrawText(CString(m_text), &r, DT_WORDBREAK | DT_NOPREFIX | DT_EXPANDTABS);
    dc.SelectObject(old);
}
