// Dlg_CellBase.cpp: 경험 임계값 창
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_CellBase.h"
#include "afxdialogex.h"

#include <string>
#include <vector>
#include <cstdlib>

extern std::string gUserID;
extern const char* GetMmCamStartPath();
extern std::string ini_read_utf8(const std::string&, const std::string&,
                                 const std::string&, const std::string&);
extern int ini_read_int_utf8(const std::string&, const std::string&,
                             const std::string&, int);

#define ID_GRID         3301
#define ID_LBL_HEAD     3302
#define ID_LBL_STATE    3303
#define TIMER_REFRESH   1

#define PANEL_BG    RGB(255, 255, 255)
#define TEXT_COLOR  RGB(0x1A, 0x24, 0x35)
#define MUTED_COLOR RGB(0x66, 0x70, 0x85)
#define LINE_COLOR  RGB(0xDD, 0xD6, 0xCB)

// 칸 색은 "선까지 얼마나 남았는가" 로 정한다. 절대 온도로 칠하면 뜨거운
// 설비는 온통 붉고 찬 설비는 온통 희어, 어느 칸이 평소와 다른지 안 보인다.
#define C_OVER      RGB(0xE4, 0x57, 0x2E)   // 선을 넘음
#define C_NEAR      RGB(0xF4, 0xA2, 0x61)   // 여유 10% 미만
#define C_WATCH     RGB(0xFA, 0xE3, 0xC6)   // 여유 30% 미만
#define C_OK        RGB(0xEC, 0xF6, 0xF4)   // 넉넉함
#define C_OFFMASK   RGB(0xF7, 0xF7, 0xF7)   // 점수가 보지 않는 칸

// 칸 한 변. 창 크기는 이 값에 맞춰 잡았다(.rc 의 IDD_DLG_CELLBASE).
// 번호 · 지금 · 선 세 줄이 들어가야 한다.
#define CELL_PX     53

IMPLEMENT_DYNAMIC(CDlg_CellBase, CDialogEx)

CDlg_CellBase::CDlg_CellBase(CWnd* pParent /*=nullptr*/)
    : CDialogEx(IDD_DLG_CELLBASE, pParent)
{
}

CDlg_CellBase::~CDlg_CellBase()
{
}

void CDlg_CellBase::DoDataExchange(CDataExchange* pDX)
{
    CDialogEx::DoDataExchange(pDX);
}

BEGIN_MESSAGE_MAP(CDlg_CellBase, CDialogEx)
    ON_WM_TIMER()
    ON_WM_DRAWITEM()
    ON_WM_CTLCOLOR()
END_MESSAGE_MAP()

//---------------------------------------------------------

// "12.0,13.5,..." 를 숫자 배열로. 개수가 64가 아니면 빈 배열.
static bool ParseCells(const std::string& s, std::vector<double>& out)
{
    out.clear();
    size_t p = 0;
    while (p <= s.size())
    {
        const size_t c = s.find(',', p);
        const std::string tok = s.substr(p, (c == std::string::npos)
            ? std::string::npos : c - p);
        if (!tok.empty()) out.push_back(atof(tok.c_str()));
        if (c == std::string::npos) break;
        p = c + 1;
    }
    if (out.size() != 64) { out.clear(); return false; }
    return true;
}

BOOL CDlg_CellBase::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    m_font.CreateFont(UI_FONT_SIZE - 1, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    m_fontSmall.CreateFont(UI_FONT_SIZE - 2, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        ANTIALIASED_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    m_fontBig.CreateFont(UI_FONT_SIZE + 3, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        ANTIALIASED_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    // 칸 안에 쓰는 글씨. 칸 높이에 세 줄(번호 · 지금 · 선)이 들어가야 한다.
    //
    // 10px·보통 굵기로 두었더니 검정을 넣어도 회색으로 번져 읽히지 않았다.
    // 작은 글씨는 색이 아니라 획 굵기가 밝기를 정한다. 키우고 굵혔으며,
    // 안티앨리어싱을 끄고 기본 품질(ClearType)로 그린다.
    m_fontCell.CreateFont(UI_FONT_SIZE, 0, 0, 0, FW_BOLD, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    m_fontTiny.CreateFont(UI_FONT_SIZE - 6, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    m_brWhite.CreateSolidBrush(PANEL_BG);

    CRect rc;
    GetClientRect(&rc);
    const int M = 12;
    const int btnW = 112, btnH = 32;
    const int headH = 54, stateH = 30;

    m_lblHead.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, M, rc.right - M - btnW - 10, M + headH), this, ID_LBL_HEAD);

    m_btnClose.Create("닫기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(rc.right - M - btnW, M, rc.right - M, M + btnH), this, IDCANCEL);

    const int yState = rc.bottom - M - stateH;

    m_grid.Create("", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | SS_OWNERDRAW,
        CRect(M, M + headH + 6, rc.right - M, yState - 6), this, ID_GRID);

    m_lblState.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, yState, rc.right - M, yState + stateH), this, ID_LBL_STATE);

    SetFont(&m_font);
    SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font.GetSafeHandle(), TRUE);

    CStringA head;
    // 둘째 줄의 칸 수는 Load() 가 읽고 나서 채운다.
    head.Format("[%s]  최저기준 / 현재온도 / 최고기준\r\n"
                "전체 - 셀, 분석마스크 - 셀",
                gUserID.c_str());
    m_lblHead.SetWindowTextA(head);

    CenterWindow(GetParent());
    Load();

    // 감시가 현황 파일을 다시 쓰는 주기보다 조금 짧게 둔다.
    SetTimer(TIMER_REFRESH, 2000, nullptr);
    return TRUE;
}

//---------------------------------------------------------
// 현황 파일에서 세 줄을 읽는다. 여기서 다시 재지 않는다.
//---------------------------------------------------------
void CDlg_CellBase::Load()
{
    m_now.clear();
    m_hi.clear();
    m_mask.clear();
    m_why.Empty();
    m_ready = false;

    const std::string st = std::string(GetMmCamStartPath()) + "users\\"
                         + gUserID + "\\stage_status.ini";

    const std::string updated = ini_read_utf8(st, "STATUS", "UPDATED_AT", "");
    if (updated.empty())
    {
        m_why = "감시가 아직 기록을 남기지 않았음";
        return;
    }

    std::vector<double> mk;
    const bool okNow = ParseCells(
        ini_read_utf8(st, "STATUS", "CELL_NOW", ""), m_now);
    const bool okHi = ParseCells(
        ini_read_utf8(st, "STATUS", "CELL_HI", ""), m_hi);
    const bool okMk = ParseCells(
        ini_read_utf8(st, "STATUS", "CELL_MASK", ""), mk);

    if (!okNow || !okHi || !okMk)
    {
        m_why = "칸별 값이 아직 없음 · 감시를 다시 시작하면 나타남";
        return;
    }

    m_mask.assign(64, 0);
    for (int i = 0; i < 64; ++i) m_mask[i] = (mk[i] >= 0.5) ? 1 : 0;

    m_ready = (ini_read_int_utf8(st, "STATUS", "STAGE1", 0) != 0);

    // 아래줄. 몇 칸이 선을 넘었고 가장 아슬아슬한 칸이 어디인가.
    int over = 0, nmask = 0, worst = -1;
    double worstGap = 1e9;
    for (int i = 0; i < 64; ++i)
    {
        if (!m_mask[i]) continue;
        ++nmask;
        const double gap = m_hi[i] - m_now[i];
        if (gap < 0) ++over;
        if (gap < worstGap) { worstGap = gap; worst = i; }
    }

    // 머리글 둘째 줄의 칸 수를 채운다. 읽고 나서야 알 수 있다.
    {
        CStringA h;
        h.Format("[%s]  최저기준 / 현재온도 / 최고기준\r\n"
                 "전체 %u 셀, 분석마스크 %d 셀",
                 gUserID.c_str(), (unsigned)m_now.size(), nmask);

        CString cur;
        m_lblHead.GetWindowText(cur);
        if (cur.Compare(h) != 0) m_lblHead.SetWindowTextA(h);
    }

    CStringA s;
    if (!m_ready)
    {
        s = "2단계가 아직 서지 않아 선이 잠정값임 · ";
    }
    if (worst >= 0)
    {
        // 좁은 창이라 짧게. 현황 시각은 시:분:초만 남긴다.
        const std::string hhmmss = (updated.size() > 11)
            ? updated.substr(11) : updated;

        CStringA t;
        t.Format("분석마스크 %d칸 · 넘은 칸 %d개 · 여유 최저 %d번 "
                 "%.0f/%.0f도 (%+.1f) · %s",
                 nmask, over, worst, m_now[worst], m_hi[worst], worstGap,
                 hhmmss.c_str());
        s += t;
    }
    else
    {
        s += "분석마스크로 지정된 칸이 없음";
    }
    m_lblState.SetWindowTextA(s);
}

void CDlg_CellBase::OnTimer(UINT_PTR nIDEvent)
{
    if (nIDEvent == TIMER_REFRESH)
    {
        Load();
        m_grid.Invalidate();
    }
    CDialogEx::OnTimer(nIDEvent);
}

//---------------------------------------------------------
// 8x8 격자
//---------------------------------------------------------
void CDlg_CellBase::DrawGrid(CDC* pDC, const CRect& rc)
{
    pDC->FillSolidRect(rc, PANEL_BG);
    pDC->SetBkMode(TRANSPARENT);

    if (m_now.size() != 64)
    {
        pDC->SelectObject(&m_font);
        pDC->SetTextColor(MUTED_COLOR);
        pDC->TextOutA(rc.left + 14, rc.top + 14,
            m_why.IsEmpty() ? "읽을 값이 없음" : (LPCSTR)m_why);
        return;
    }

    const int pad = 10, legendH = 30;
    const int availW = rc.Width() - pad * 2;
    const int availH = rc.Height() - pad * 2 - legendH;

    // 칸 크기는 못 박는다. 자리에 맞춰 늘리면 창을 키울 때마다 칸이 커져
    // 격자가 한눈에 들어오지 않는다. 창이 더 좁으면 그만큼만 줄인다.
    int cw = CELL_PX, ch = CELL_PX;
    if (cw * 8 > availW) cw = ch = availW / 8;
    if (ch * 8 > availH) cw = ch = availH / 8;
    if (cw < 16) return;

    const int x0 = rc.left + pad + (availW - cw * 8) / 2;
    const int y0 = rc.top + pad + (availH - ch * 8) / 2;

    // 테두리는 모두 같은 굵기. 색만 바탕을 따라간다.
    //
    // 점수를 보지 않는 칸(회색 바탕)까지 검정으로 두르면, 보지도 않는
    // 칸이 보는 칸만큼 또렷해 격자에서 눈이 나뉘지 않는다. 그쪽은
    // 테두리도 흐리게 둔다.
    CPen penLine(PS_SOLID, 1, RGB(0, 0, 0));
    CPen penOff(PS_SOLID, 1, LINE_COLOR);

    for (int r = 0; r < 8; ++r)
    {
        for (int c = 0; c < 8; ++c)
        {
            const int i = r * 8 + c;
            CRect cell(x0 + c * cw, y0 + r * ch,
                       x0 + c * cw + cw - 2, y0 + r * ch + ch - 2);

            const double gap = m_hi[i] - m_now[i];
            COLORREF bg = C_OFFMASK;

            if (m_mask[i])
            {
                // 여유를 선 높이에 견준 비율로 본다. 100도 선에서 5도 남은
                // 것과 20도 선에서 5도 남은 것은 뜻이 다르다.
                const double room = (m_hi[i] > 1.0) ? gap / m_hi[i] : 0.0;
                if (gap < 0)          bg = C_OVER;
                else if (room < 0.10) bg = C_NEAR;
                else if (room < 0.30) bg = C_WATCH;
                else                  bg = C_OK;
            }
            pDC->FillSolidRect(cell, bg);

            CPen* old = pDC->SelectObject(
                (bg == C_OFFMASK) ? &penOff : &penLine);
            pDC->MoveTo(cell.left, cell.top);
            pDC->LineTo(cell.right, cell.top);
            pDC->LineTo(cell.right, cell.bottom);
            pDC->LineTo(cell.left, cell.bottom);
            pDC->LineTo(cell.left, cell.top);
            pDC->SelectObject(old);

            // 칸 번호 · 지금 / 선
            CStringA num, now, hi;
            num.Format("%d", i);
            now.Format("%.0f", m_now[i]);
            hi.Format("/ %.0f", m_hi[i]);

            // 세 줄을 칸 높이에 비례해 놓는다. 칸 크기를 바꿔도 따라간다.
            //
            // 글자는 모두 검정이다. 칸 번호와 선을 회색으로 흐려 두었더니
            // 작은 칸에서 읽히지 않았다. 색으로 가릴 것은 칸 바탕이고,
            // 글자는 읽히는 것이 먼저다.
            const int tx = cell.left + 4;
            const COLORREF ink = (bg == C_OVER) ? RGB(255, 255, 255)
                                                : RGB(0, 0, 0);

            pDC->SetTextColor(ink);

            pDC->SelectObject(&m_fontTiny);
            pDC->TextOutA(tx, cell.top + 1, num);

            pDC->SelectObject(&m_fontCell);
            pDC->TextOutA(tx, cell.top + ch / 2 - 13, now);

            pDC->SelectObject(&m_fontTiny);
            pDC->TextOutA(tx, cell.bottom - 19, hi);
        }
    }

    // 범례
    pDC->SelectObject(&m_fontSmall);
    struct { COLORREF c; const char* t; } leg[] = {
        { C_OVER,    "선을 넘음" },
        { C_NEAR,    "여유 10% 미만" },
        { C_WATCH,   "여유 30% 미만" },
        { C_OK,      "넉넉함" },
        { C_OFFMASK, "분석마스크 밖" },
    };
    int lx = x0;
    const int ly = rc.bottom - pad - legendH + 4;
    for (int i = 0; i < 5; ++i)
    {
        CRect sw(lx, ly + 3, lx + 12, ly + 15);
        pDC->FillSolidRect(sw, leg[i].c);
        pDC->Draw3dRect(sw, LINE_COLOR, LINE_COLOR);
        pDC->SetTextColor(MUTED_COLOR);
        pDC->TextOutA(lx + 17, ly, leg[i].t);
        lx += 17 + pDC->GetTextExtent(leg[i].t).cx + 16;
    }
}

void CDlg_CellBase::OnDrawItem(int nIDCtl, LPDRAWITEMSTRUCT lpDIS)
{
    if (nIDCtl != ID_GRID || !lpDIS)
    {
        CDialogEx::OnDrawItem(nIDCtl, lpDIS);
        return;
    }

    CDC* pDC = CDC::FromHandle(lpDIS->hDC);
    const int w = lpDIS->rcItem.right - lpDIS->rcItem.left;
    const int h = lpDIS->rcItem.bottom - lpDIS->rcItem.top;
    if (w <= 40 || h <= 40) return;

    // 메모리에 그려 한 번에 옮긴다. 2초마다 다시 그리므로 바로 그리면
    // 쉬지 않고 깜빡인다.
    CDC mem;
    if (!mem.CreateCompatibleDC(pDC)) return;
    CBitmap bmp;
    if (!bmp.CreateCompatibleBitmap(pDC, w, h)) return;
    CBitmap* oldBmp = mem.SelectObject(&bmp);

    DrawGrid(&mem, CRect(0, 0, w, h));

    pDC->BitBlt(lpDIS->rcItem.left, lpDIS->rcItem.top, w, h, &mem, 0, 0,
        SRCCOPY);
    mem.SelectObject(oldBmp);
}

HBRUSH CDlg_CellBase::OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor)
{
    if (nCtlColor == CTLCOLOR_STATIC && pWnd)
    {
        const int id = pWnd->GetDlgCtrlID();
        if (id == ID_GRID || id == ID_LBL_HEAD || id == ID_LBL_STATE)
        {
            pDC->SetBkMode(TRANSPARENT);
            pDC->SetTextColor(TEXT_COLOR);
            return (HBRUSH)m_brWhite.GetSafeHandle();
        }
    }
    return CDialogEx::OnCtlColor(pDC, pWnd, nCtlColor);
}
