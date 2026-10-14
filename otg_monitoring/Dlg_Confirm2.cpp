// Dlg_Confirm2.cpp: 두 단계 확인 창 (관제서버 [칸 수 변경] 창과 같은 모양)
//

#include "pch.h"
#include "resource.h"
#include "Dlg_Confirm2.h"
#include "afxdialogex.h"

#define ID_C2_NEXT    3802
#define ID_C2_BACK    3803
#define ID_C2_APPLY   3804
#define TIMER_C2_ARM  1

// 관제서버 settings.css 의 색과 같게
static const COLORREF C_BG        = RGB(255, 255, 255);
static const COLORREF C_TITLE     = RGB(31, 41, 55);
static const COLORREF C_INFO      = RGB(55, 65, 81);
static const COLORREF C_WARN_BG   = RGB(255, 251, 235);
static const COLORREF C_WARN_LINE = RGB(252, 211, 77);
static const COLORREF C_WARN_HEAD = RGB(146, 64, 14);
static const COLORREF C_WARN_TEXT = RGB(120, 53, 15);
static const COLORREF C_RED_BG    = RGB(254, 242, 242);
static const COLORREF C_RED_LINE  = RGB(252, 165, 165);
static const COLORREF C_RED_BIG   = RGB(185, 28, 28);
static const COLORREF C_RED_TEXT  = RGB(127, 29, 29);
static const COLORREF C_BTN_RED   = RGB(220, 38, 38);
static const COLORREF C_BTN_OFF   = RGB(239, 154, 154);

static const int DW = 500;           // 창 안쪽 너비
static const int P = 20;             // 바깥 여백
static const int BOX_PAD = 14;       // 상자 안 여백
static const int BTN_H = 34;

BEGIN_MESSAGE_MAP(CDlg_Confirm2, CDialogEx)
    ON_WM_PAINT()
    ON_WM_TIMER()
    ON_WM_DRAWITEM()
    ON_WM_CTLCOLOR()
    ON_WM_ERASEBKGND()

    ON_BN_CLICKED(ID_C2_NEXT, &CDlg_Confirm2::OnNext)
    ON_BN_CLICKED(ID_C2_BACK, &CDlg_Confirm2::OnBack)
    ON_BN_CLICKED(ID_C2_APPLY, &CDlg_Confirm2::OnApply)
END_MESSAGE_MAP()

bool CDlg_Confirm2::Ask(CFont* font, CWnd* parent, const Confirm2Text& text)
{
    CDlg_Confirm2 dlg(font, parent, text);
    return dlg.DoModal() == IDOK;
}

CDlg_Confirm2::CDlg_Confirm2(CFont* font, CWnd* parent, const Confirm2Text& text)
    : CDialogEx(), m_font(font), m_text(text)
{
    m_tpl.assign(64, 0);
    DLGTEMPLATE* t = reinterpret_cast<DLGTEMPLATE*>(m_tpl.data());
    t->style = DS_MODALFRAME | WS_POPUP | WS_CAPTION | WS_SYSMENU;
    t->cx = 300; t->cy = 200;
    WORD* p = reinterpret_cast<WORD*>(t + 1);
    *p++ = 0;
    *p++ = 0;
    // 창 제목은 비우고, 안의 제목을 크게 쓴다 (관제서버 창과 같게). 틀 제목줄은 "확인".
    const wchar_t* cap = L"\xD655\xC778";
    while (*cap) *p++ = (WORD)*cap++;
    *p++ = 0;
    InitModalIndirect(t, parent);
}

// 노란 상자 높이 (굵은 첫 줄 + 항목들)
int CDlg_Confirm2::MeasureWarn(CDC& dc, int width)
{
    int h = BOX_PAD;
    CRect r(0, 0, width, 0);
    dc.SelectObject(&m_fontBold);
    dc.DrawText(CString(m_text.warnHead), &r, DT_WORDBREAK | DT_CALCRECT);
    h += r.Height() + 6;
    dc.SelectObject(m_font);
    for (const CStringA& it : m_text.warnItems)
    {
        CRect ri(0, 0, width - 18, 0);
        dc.DrawText(CString(it), &ri, DT_WORDBREAK | DT_CALCRECT);
        h += ri.Height() + 3;
    }
    return h + BOX_PAD - 3;
}

BOOL CDlg_Confirm2::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    LOGFONT lf = {};
    if (m_font) m_font->GetLogFont(&lf);
    else ::GetObject(::GetStockObject(DEFAULT_GUI_FONT), sizeof(lf), &lf);
    const LONG base = lf.lfHeight < 0 ? -lf.lfHeight : (lf.lfHeight ? lf.lfHeight : 16);

    LOGFONT t = lf;
    t.lfWeight = FW_HEAVY;
    t.lfHeight = -(base * 6 / 5);
    m_fontTitle.CreateFontIndirect(&t);
    LOGFONT b = lf;
    b.lfWeight = FW_BOLD;
    m_fontBold.CreateFontIndirect(&b);
    LOGFONT g = lf;
    g.lfWeight = FW_HEAVY;
    g.lfHeight = -(base * 8 / 5);
    m_fontBig.CreateFontIndirect(&g);

    // 높이를 두 단계 중 큰 쪽에 맞춘다. 단계가 바뀔 때 창이 들썩이지 않게.
    const int boxW = DW - 2 * P;
    int warnH, redH;
    {
        CClientDC dc(this);
        CFont* old = dc.SelectObject(m_font);
        warnH = MeasureWarn(dc, boxW - 2 * BOX_PAD);

        CRect rb(0, 0, boxW - 2 * BOX_PAD, 0);
        dc.SelectObject(&m_fontBig);
        dc.DrawText(CString(m_text.big), &rb, DT_SINGLELINE | DT_CALCRECT);
        CRect rq(0, 0, boxW - 2 * BOX_PAD, 0);
        dc.SelectObject(m_font);
        dc.DrawText(CString(m_text.question), &rq, DT_WORDBREAK | DT_CALCRECT);
        redH = BOX_PAD + rb.Height() + 8 + rq.Height() + BOX_PAD + 4;
        dc.SelectObject(old);
    }

    const int titleH = base * 6 / 5 + 10;
    const int infoH = m_text.info.IsEmpty() ? 0 : base + 14;
    const int boxTop = P + titleH + 8 + infoH;
    const int boxH = warnH > redH ? warnH : redH;
    m_rcBox = CRect(P, boxTop, P + boxW, boxTop + boxH);
    m_W = DW;
    m_H = m_rcBox.bottom + 22 + BTN_H + P;

    CRect wr(0, 0, m_W, m_H);
    AdjustWindowRectEx(&wr, GetStyle(), FALSE, GetExStyle());
    SetWindowPos(nullptr, 0, 0, wr.Width(), wr.Height(), SWP_NOMOVE | SWP_NOZORDER);
    CenterWindow();

    const int yBtn = m_H - P - BTN_H;
    const int bw1 = 90, bw2 = 170;
    m_btnCancel.Create("취소", WS_CHILD | WS_TABSTOP | BS_PUSHBUTTON,
                       CRect(m_W - P - bw1 - 8 - bw1, yBtn, m_W - P - bw1 - 8, yBtn + BTN_H),
                       this, IDCANCEL);
    m_btnNext.Create("변경", WS_CHILD | WS_TABSTOP | BS_PUSHBUTTON,
                     CRect(m_W - P - bw1, yBtn, m_W - P, yBtn + BTN_H), this, ID_C2_NEXT);
    m_btnBack.Create("돌아가기", WS_CHILD | WS_TABSTOP | BS_PUSHBUTTON,
                     CRect(m_W - P - bw2 - 8 - 110, yBtn, m_W - P - bw2 - 8, yBtn + BTN_H),
                     this, ID_C2_BACK);
    m_btnApply.Create("최종 확인 · 변경", WS_CHILD | WS_TABSTOP | BS_OWNERDRAW,
                      CRect(m_W - P - bw2, yBtn, m_W - P, yBtn + BTN_H), this, ID_C2_APPLY);

    if (m_font) SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font->GetSafeHandle(), TRUE);
    m_btnApply.SetFont(&m_fontBold);

    SetStep(1);
    return FALSE;
}

void CDlg_Confirm2::SetStep(int step)
{
    m_step = step;
    KillTimer(TIMER_C2_ARM);

    const bool s1 = step == 1;
    m_btnCancel.ShowWindow(s1 ? SW_SHOW : SW_HIDE);
    m_btnNext.ShowWindow(s1 ? SW_SHOW : SW_HIDE);
    m_btnBack.ShowWindow(s1 ? SW_HIDE : SW_SHOW);
    m_btnApply.ShowWindow(s1 ? SW_HIDE : SW_SHOW);

    if (s1)
    {
        m_btnNext.SetFocus();
    }
    else
    {
        m_btnApply.EnableWindow(FALSE);
        SetTimer(TIMER_C2_ARM, 1000, nullptr);
        m_btnBack.SetFocus();
    }
    Invalidate();
}

void CDlg_Confirm2::OnNext() { SetStep(2); }
void CDlg_Confirm2::OnBack() { SetStep(1); }

void CDlg_Confirm2::OnApply()
{
    if (m_step != 2 || !m_btnApply.IsWindowEnabled()) return;
    EndDialog(IDOK);
}

// Enter: 1단계는 [변경], 2단계는 [돌아가기]. 최종 확인은 버튼을 직접 눌러야 한다.
void CDlg_Confirm2::OnOK()
{
    if (m_step == 1) SetStep(2);
    else SetStep(1);
}

void CDlg_Confirm2::OnTimer(UINT_PTR id)
{
    if (id == TIMER_C2_ARM)
    {
        KillTimer(TIMER_C2_ARM);
        m_btnApply.EnableWindow(TRUE);
        m_btnApply.Invalidate();
        return;
    }
    CDialogEx::OnTimer(id);
}

BOOL CDlg_Confirm2::OnEraseBkgnd(CDC* pDC)
{
    CRect rc;
    GetClientRect(&rc);
    pDC->FillSolidRect(&rc, C_BG);
    return TRUE;
}

HBRUSH CDlg_Confirm2::OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor)
{
    HBRUSH hbr = CDialogEx::OnCtlColor(pDC, pWnd, nCtlColor);
    if (nCtlColor == CTLCOLOR_DLG || nCtlColor == CTLCOLOR_BTN)
    {
        static CBrush white(C_BG);
        pDC->SetBkColor(C_BG);
        return white;
    }
    return hbr;
}

static void RoundBox(CDC& dc, const CRect& r, COLORREF fill, COLORREF line)
{
    CBrush br(fill);
    CPen pen(PS_SOLID, 1, line);
    CBrush* ob = dc.SelectObject(&br);
    CPen* op = dc.SelectObject(&pen);
    dc.RoundRect(&r, CPoint(14, 14));
    dc.SelectObject(ob);
    dc.SelectObject(op);
}

void CDlg_Confirm2::OnPaint()
{
    CPaintDC dc(this);
    CFont* old = dc.SelectObject(&m_fontTitle);
    dc.SetBkMode(TRANSPARENT);

    // 제목
    CRect rt(P, P, m_W - P, m_rcBox.top);
    dc.SetTextColor(C_TITLE);
    dc.DrawText(CString(m_text.title), &rt, DT_LEFT | DT_TOP | DT_SINGLELINE);

    // 안내 한 줄 (1단계만)
    if (m_step == 1 && !m_text.info.IsEmpty())
    {
        dc.SelectObject(&m_fontBold);
        dc.SetTextColor(C_INFO);
        CRect ri(P, m_rcBox.top - 34, m_W - P, m_rcBox.top - 6);
        dc.DrawText(CString(m_text.info), &ri, DT_LEFT | DT_VCENTER | DT_SINGLELINE);
    }

    const int inner = m_rcBox.Width() - 2 * BOX_PAD;

    if (m_step == 1)
    {
        // 노란 경고 상자. 내용 높이에 맞춘다.
        CRect box = m_rcBox;
        box.bottom = box.top + MeasureWarn(dc, inner);
        RoundBox(dc, box, C_WARN_BG, C_WARN_LINE);

        int y = box.top + BOX_PAD;
        dc.SelectObject(&m_fontBold);
        dc.SetTextColor(C_WARN_HEAD);
        CRect rh(box.left + BOX_PAD, y, box.right - BOX_PAD, box.bottom);
        y += dc.DrawText(CString(m_text.warnHead), &rh, DT_WORDBREAK) + 6;

        dc.SelectObject(m_font);
        dc.SetTextColor(C_WARN_TEXT);
        for (const CStringA& it : m_text.warnItems)
        {
            CRect rb(box.left + BOX_PAD, y, box.left + BOX_PAD + 18, y + 30);
            dc.DrawText(_T("·"), &rb, DT_LEFT | DT_TOP | DT_SINGLELINE);
            CRect rx(box.left + BOX_PAD + 18, y, box.right - BOX_PAD, box.bottom);
            y += dc.DrawText(CString(it), &rx, DT_WORDBREAK) + 3;
        }
    }
    else
    {
        // 빨간 확인 상자. 바뀌는 것을 크게.
        RoundBox(dc, m_rcBox, C_RED_BG, C_RED_LINE);

        int y = m_rcBox.top + BOX_PAD;
        dc.SelectObject(&m_fontBig);
        dc.SetTextColor(C_RED_BIG);
        CRect rb(m_rcBox.left + BOX_PAD, y, m_rcBox.right - BOX_PAD, m_rcBox.bottom);
        y += dc.DrawText(CString(m_text.big), &rb, DT_CENTER | DT_TOP | DT_SINGLELINE) + 8;

        dc.SelectObject(m_font);
        dc.SetTextColor(C_RED_TEXT);
        CRect rq(m_rcBox.left + BOX_PAD, y, m_rcBox.right - BOX_PAD, m_rcBox.bottom);
        dc.DrawText(CString(m_text.question), &rq, DT_CENTER | DT_WORDBREAK);
    }

    dc.SelectObject(old);
}

// [최종 확인 · 변경] 은 빨간 버튼. 막혀 있는 1초 동안은 옅게.
void CDlg_Confirm2::OnDrawItem(int id, LPDRAWITEMSTRUCT dis)
{
    if (id != ID_C2_APPLY)
    {
        CDialogEx::OnDrawItem(id, dis);
        return;
    }

    CDC* dc = CDC::FromHandle(dis->hDC);
    CRect r(dis->rcItem);
    dc->FillSolidRect(&r, C_BG);

    const bool off = (dis->itemState & ODS_DISABLED) != 0;
    const bool down = (dis->itemState & ODS_SELECTED) != 0;
    COLORREF fill = off ? C_BTN_OFF : (down ? RGB(185, 28, 28) : C_BTN_RED);
    RoundBox(*dc, r, fill, fill);

    dc->SetBkMode(TRANSPARENT);
    dc->SetTextColor(RGB(255, 255, 255));
    CFont* old = dc->SelectObject(&m_fontBold);
    CString text;
    m_btnApply.GetWindowText(text);
    dc->DrawText(text, &r, DT_CENTER | DT_VCENTER | DT_SINGLELINE);
    dc->SelectObject(old);

    if ((dis->itemState & ODS_FOCUS) && !off)
    {
        CRect f = r;
        f.DeflateRect(4, 4);
        dc->DrawFocusRect(&f);
    }
}
