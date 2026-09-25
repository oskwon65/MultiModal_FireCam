// Dlg_Analysis.cpp: 점수 추이 창
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_Analysis.h"
#include "afxdialogex.h"

extern "C" {
#include <mysql.h>
}

#include <string>
#include <vector>
#include <cstdlib>

extern std::string gUserID;
extern MYSQL* connect_history_db(std::string* dbNameOut);
extern std::string read_ini_string(const char* section, const char* key,
                                  const char* default_value);

#define ID_CHART        3101
#define ID_CBO_RANGE    3102
#define ID_BTN_RELOAD   3103
#define ID_LBL_STATE    3104
#define ID_LBL_HEAD     3105

#define PANEL_BG    RGB(255, 255, 255)
#define AXIS_COLOR  RGB(0xB8, 0xC0, 0xCC)
#define GRID_COLOR  RGB(0xE8, 0xEC, 0xF1)
#define LINE_COLOR  RGB(0x2A, 0x9D, 0x8F)
#define BAND_COLOR  RGB(0xE4, 0x57, 0x2E)
#define TEXT_COLOR  RGB(0x1A, 0x24, 0x35)
#define MUTED_COLOR RGB(0x66, 0x70, 0x85)

IMPLEMENT_DYNAMIC(CDlg_Analysis, CDialogEx)

CDlg_Analysis::CDlg_Analysis(CWnd* pParent /*=nullptr*/)
    : CDialogEx(IDD_DLG_ANALYSIS, pParent)
{
}

CDlg_Analysis::~CDlg_Analysis()
{
}

void CDlg_Analysis::DoDataExchange(CDataExchange* pDX)
{
    CDialogEx::DoDataExchange(pDX);
}

BEGIN_MESSAGE_MAP(CDlg_Analysis, CDialogEx)
    ON_CBN_SELCHANGE(ID_CBO_RANGE, &CDlg_Analysis::OnSelchangeRange)
    ON_BN_CLICKED(ID_BTN_RELOAD, &CDlg_Analysis::OnBnClickedReload)
    ON_WM_DRAWITEM()
    ON_WM_CTLCOLOR()
END_MESSAGE_MAP()

//---------------------------------------------------------

BOOL CDlg_Analysis::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    m_font.CreateFont(UI_FONT_SIZE, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    // 축 글자는 본문보다 작다. 눈금이 본문만큼 크면 그래프가 글자에 묻힌다.
    m_fontSmall.CreateFont(UI_FONT_SIZE - 4, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        ANTIALIASED_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    m_brWhite.CreateSolidBrush(PANEL_BG);

    CRect rc;
    GetClientRect(&rc);
    const int M = 12;
    const int btnW = 112, btnH = 32;
    const int headH = 52, stateH = 28;

    m_lblHead.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, M, rc.right - M, M + headH), this, ID_LBL_HEAD);

    const int yTop = M + headH + 4;

    // 기간 고르기와 다시 읽기를 위에 둔다. 아래에 두면 그래프가 잘린다.
    m_cboRange.Create(WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL
        | CBS_DROPDOWNLIST,
        CRect(M, yTop, M + 150, yTop + 200), this, ID_CBO_RANGE);
    m_cboRange.AddString("최근 1일");
    m_cboRange.AddString("최근 3일");
    m_cboRange.AddString("최근 7일");
    m_cboRange.AddString("최근 30일");
    m_cboRange.SetCurSel(2);          // 7일

    m_btnReload.Create("다시 읽기", WS_CHILD | WS_VISIBLE | WS_TABSTOP
        | BS_PUSHBUTTON,
        CRect(M + 160, yTop, M + 160 + btnW, yTop + btnH), this, ID_BTN_RELOAD);

    int bx = rc.right - M - btnW;
    m_btnClose.Create("닫기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, yTop, bx + btnW, yTop + btnH), this, IDCANCEL);

    const int yChart = yTop + btnH + 10;
    const int yState = rc.bottom - M - stateH;

    m_chart.Create("", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | SS_OWNERDRAW,
        CRect(M, yChart, rc.right - M, yState - 8), this, ID_CHART);

    m_lblState.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, yState, rc.right - M, yState + stateH), this, ID_LBL_STATE);

    SetFont(&m_font);
    SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font.GetSafeHandle(), TRUE);

    CStringA head;
    head.Format("[%s]  히스토리 DB 의 mscore 를 한 시간 단위로 묶어 평균을 "
                "그립니다.\r\n"
                "산출되지 않은 프레임은 뺐습니다. 붉은 선은 재학습이 기존 "
                "모델을 그대로 물려받는 문턱입니다.",
                gUserID.c_str());
    m_lblHead.SetWindowTextA(head);

    CenterWindow(GetParent());
    Load();
    return TRUE;
}

//---------------------------------------------------------

int CDlg_Analysis::DaysFromCombo() const
{
    switch (m_cboRange.GetCurSel())
    {
    case 0:  return 1;
    case 1:  return 3;
    case 3:  return 30;
    default: return 7;
    }
}

void CDlg_Analysis::SetState(const char* text)
{
    m_lblState.SetWindowTextA(text);
    m_lblState.UpdateWindow();
}

void CDlg_Analysis::OnSelchangeRange() { Load(); }
void CDlg_Analysis::OnBnClickedReload() { Load(); }

//---------------------------------------------------------
// DB 에서 시간별 평균을 읽는다
//
// 날짜별 테이블이라 한 번에 물을 수 없다. 최근 것부터 필요한 날 수만큼
// 골라 테이블마다 한 번씩 묻고 이어 붙인다.
//---------------------------------------------------------
void CDlg_Analysis::Load()
{
    if (m_loading) return;
    m_loading = true;

    m_days = DaysFromCombo();
    m_pts.clear();

    SetState("읽는 중...");

    std::string dbName;
    MYSQL* conn = connect_history_db(&dbName);
    if (conn == nullptr)
    {
        SetState("히스토리 DB 에 접속할 수 없습니다. env.ini 와 secrets.ini 를 "
                 "확인하십시오.");
        m_chart.Invalidate();
        m_loading = false;
        return;
    }

    // 1) 기간 안의 날짜 테이블 목록
    //
    // 개수로 자르면("최근 7개 테이블") 빈 날이 있는 현장에서 엉뚱하게 멀리
    // 간다. kict1 은 09-19~20 자료를 지웠고 7월 것이 남아 있어, 7개를 세면
    // 7월 테이블까지 끌어왔다. 날짜로 자른다.
    //
    // 이름이 results_history_YYYYMMDD 로 자리수가 고정이라 글자 비교로도
    // 날짜 비교가 된다.
    std::vector<std::string> tables;
    {
        CTime from = CTime::GetCurrentTime() - CTimeSpan(m_days - 1, 0, 0, 0);
        const CStringA cut = from.Format("%Y%m%d");

        char sql[640];
        sprintf_s(sql, sizeof(sql),
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='%s' AND table_name LIKE 'results_history_%%' "
            "AND table_type='BASE TABLE' "
            "AND table_name >= 'results_history_%s' "
            "ORDER BY table_name ASC",
            dbName.c_str(), (LPCSTR)cut);

        if (mysql_query(conn, sql) == 0)
        {
            if (MYSQL_RES* res = mysql_store_result(conn))
            {
                while (MYSQL_ROW row = mysql_fetch_row(res))
                    if (row[0]) tables.push_back(row[0]);
                mysql_free_result(res);
            }
        }
    }

    if (tables.empty())
    {
        mysql_close(conn);
        SetState("그 기간에 히스토리 테이블이 없습니다. 기간을 늘려 "
                 "보십시오.");
        m_chart.Invalidate();
        m_loading = false;
        return;
    }

    // 목록은 오름차순이다. 그래프도 왼쪽이 옛것이라 그대로 훑는다.
    long total = 0;
    for (size_t i = 0; i < tables.size(); ++i)
    {
        char sql[768];
        sprintf_s(sql, sizeof(sql),
            "SELECT DATE_FORMAT(`time`,'%%Y%%m%%d%%H') AS h, "
            "AVG(mscore), COUNT(*) "
            "FROM `%s`.`%s` WHERE mscore >= 0 GROUP BY h ORDER BY h",
            dbName.c_str(), tables[i].c_str());

        if (mysql_query(conn, sql) != 0) continue;

        MYSQL_RES* res = mysql_store_result(conn);
        if (res == nullptr) continue;

        while (MYSQL_ROW row = mysql_fetch_row(res))
        {
            if (!row[0] || !row[1]) continue;
            Point pt;
            pt.hour = row[0];
            pt.avg  = atof(row[1]);
            pt.n    = row[2] ? atol(row[2]) : 0;
            m_pts.push_back(pt);
            total += pt.n;
        }
        mysql_free_result(res);
    }

    mysql_close(conn);

    if (m_pts.empty())
    {
        SetState("그 기간에 산출된 점수가 없습니다.");
        m_chart.Invalidate();
        m_loading = false;
        return;
    }

    double lo = m_pts[0].avg, hi = m_pts[0].avg, sum = 0.0;
    for (size_t i = 0; i < m_pts.size(); ++i)
    {
        if (m_pts[i].avg < lo) lo = m_pts[i].avg;
        if (m_pts[i].avg > hi) hi = m_pts[i].avg;
        sum += m_pts[i].avg;
    }

    CStringA st;
    st.Format("%s ~ %s   ·   %u시간 %ld건   ·   "
              "최저 %.3f  평균 %.3f  최고 %.3f  ·  지금 %.3f",
              m_pts.front().hour.c_str(), m_pts.back().hour.c_str(),
              (unsigned)m_pts.size(), total,
              lo, sum / m_pts.size(), hi, m_pts.back().avg);
    SetState(st);

    m_chart.Invalidate();
    m_loading = false;
}

//---------------------------------------------------------

HBRUSH CDlg_Analysis::OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor)
{
    if (nCtlColor == CTLCOLOR_STATIC && pWnd)
    {
        const int id = pWnd->GetDlgCtrlID();
        if (id == ID_CHART || id == ID_LBL_STATE || id == ID_LBL_HEAD)
        {
            pDC->SetBkMode(TRANSPARENT);
            pDC->SetTextColor(TEXT_COLOR);
            return (HBRUSH)m_brWhite.GetSafeHandle();
        }
    }
    return CDialogEx::OnCtlColor(pDC, pWnd, nCtlColor);
}

//---------------------------------------------------------
// 꺾은선을 그린다
//
// y 는 0~1 로 못 박는다. 값 범위에 맞춰 늘리면 0.96 과 0.97 의 차이가 화면
// 절반이 되어 대단한 변화처럼 보인다. 점수는 원래 0~1 이므로 그대로 둔다.
//
// x 는 점 하나에 같은 폭을 준다. 시간에 비례하지 않으므로 통신이 끊긴
// 구간은 그래프에서 좁아진다. 대신 날짜가 바뀌는 자리에 눈금을 찍어
// 언제인지 읽을 수 있게 한다.
//
// 메모리에 그려 한 번에 옮긴다. 바로 그리면 다시 그릴 때마다 깜빡인다.
//---------------------------------------------------------
void CDlg_Analysis::OnDrawItem(int nIDCtl, LPDRAWITEMSTRUCT lpDIS)
{
    if (nIDCtl != ID_CHART || !lpDIS)
    {
        CDialogEx::OnDrawItem(nIDCtl, lpDIS);
        return;
    }

    CDC* pDC = CDC::FromHandle(lpDIS->hDC);
    const int w = lpDIS->rcItem.right - lpDIS->rcItem.left;
    const int h = lpDIS->rcItem.bottom - lpDIS->rcItem.top;
    if (w <= 40 || h <= 40) return;

    CDC mem;
    if (!mem.CreateCompatibleDC(pDC)) return;
    CBitmap bmp;
    if (!bmp.CreateCompatibleBitmap(pDC, w, h)) return;
    CBitmap* pOldBmp = mem.SelectObject(&bmp);

    mem.FillSolidRect(0, 0, w, h, PANEL_BG);
    mem.SetBkMode(TRANSPARENT);
    CFont* pOldFont = mem.SelectObject(&m_fontSmall);

    const int L = 52, R = 14, T = 14, B = 32;
    const int px = L, py = T;
    const int pw = w - L - R, ph = h - T - B;

    auto YAt = [&](double v) -> int {
        if (v < 0.0) v = 0.0;
        if (v > 1.0) v = 1.0;
        return py + static_cast<int>((1.0 - v) * ph);
    };

    // 가로 눈금과 y 글자
    {
        CPen penGrid(PS_SOLID, 1, GRID_COLOR);
        CPen* pOld = mem.SelectObject(&penGrid);
        mem.SetTextColor(MUTED_COLOR);

        for (int k = 0; k <= 4; ++k)
        {
            const double v = k * 0.25;
            const int y = YAt(v);
            mem.MoveTo(px, y);
            mem.LineTo(px + pw, y);

            CStringA t;
            t.Format("%.2f", v);
            CRect rcT(0, y - 9, px - 6, y + 9);
            mem.DrawTextA(t, &rcT, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
        }
        mem.SelectObject(pOld);
    }

    // 기여 문턱 (env.ini 의 CONTRIB_BAND_HIGH). 이 아래로 내려가면 재학습이
    // 기존 모델의 기여를 줄인다.
    {
        const double band =
            atof(read_ini_string("CONSTANTS", "CONTRIB_BAND_HIGH", "0.85").c_str());
        if (band > 0.0 && band < 1.0)
        {
            CPen penBand(PS_DOT, 1, BAND_COLOR);
            CPen* pOld = mem.SelectObject(&penBand);
            const int y = YAt(band);
            mem.MoveTo(px, y);
            mem.LineTo(px + pw, y);
            mem.SelectObject(pOld);

            mem.SetTextColor(BAND_COLOR);
            CStringA t;
            t.Format("%.2f", band);
            CRect rcT(px + pw - 40, y - 18, px + pw, y - 2);
            mem.DrawTextA(t, &rcT, DT_RIGHT | DT_SINGLELINE);
        }
    }

    // 축
    {
        CPen penAxis(PS_SOLID, 1, AXIS_COLOR);
        CPen* pOld = mem.SelectObject(&penAxis);
        mem.MoveTo(px, py);
        mem.LineTo(px, py + ph);
        mem.LineTo(px + pw, py + ph);
        mem.SelectObject(pOld);
    }

    if (m_pts.empty())
    {
        mem.SetTextColor(MUTED_COLOR);
        CRect rcT(px, py, px + pw, py + ph);
        mem.DrawTextA("보여 줄 점수가 없습니다.", &rcT,
                      DT_CENTER | DT_VCENTER | DT_SINGLELINE);
        pDC->BitBlt(lpDIS->rcItem.left, lpDIS->rcItem.top, w, h, &mem, 0, 0,
                    SRCCOPY);
        mem.SelectObject(pOldFont);
        mem.SelectObject(pOldBmp);
        return;
    }

    const size_t n = m_pts.size();
    auto XAt = [&](size_t i) -> int {
        if (n <= 1) return px + pw / 2;
        return px + static_cast<int>(
            static_cast<double>(pw) * i / (n - 1));
    };

    // 날짜가 바뀌는 자리에 눈금과 MM-DD
    {
        CPen penGrid(PS_SOLID, 1, GRID_COLOR);
        CPen* pOld = mem.SelectObject(&penGrid);
        mem.SetTextColor(MUTED_COLOR);

        std::string lastDay;
        int lastLabelX = -9999;
        for (size_t i = 0; i < n; ++i)
        {
            const std::string day = m_pts[i].hour.substr(0, 8);
            if (day == lastDay) continue;
            lastDay = day;

            const int x = XAt(i);
            mem.MoveTo(x, py);
            mem.LineTo(x, py + ph);

            // 글자가 겹칠 만큼 가까우면 찍지 않는다
            if (x - lastLabelX < 46) continue;
            lastLabelX = x;

            CStringA t;
            t.Format("%c%c-%c%c", day[4], day[5], day[6], day[7]);
            CRect rcT(x - 24, py + ph + 6, x + 24, py + ph + 24);
            mem.DrawTextA(t, &rcT, DT_CENTER | DT_SINGLELINE);
        }
        mem.SelectObject(pOld);
    }

    // 꺾은선
    {
        CPen penLine(PS_SOLID, 2, LINE_COLOR);
        CPen* pOld = mem.SelectObject(&penLine);
        for (size_t i = 0; i < n; ++i)
        {
            const int x = XAt(i), y = YAt(m_pts[i].avg);
            if (i == 0) mem.MoveTo(x, y);
            else        mem.LineTo(x, y);
        }
        mem.SelectObject(pOld);
    }

    // 점은 많지 않을 때만 찍는다. 수백 개를 찍으면 선이 뭉개진다.
    if (n <= 90)
    {
        CBrush brDot(LINE_COLOR);
        CPen penNone(PS_NULL, 0, (COLORREF)0);
        CBrush* pOldBr = mem.SelectObject(&brDot);
        CPen* pOldPen = mem.SelectObject(&penNone);
        for (size_t i = 0; i < n; ++i)
        {
            const int x = XAt(i), y = YAt(m_pts[i].avg);
            mem.Ellipse(x - 3, y - 3, x + 3, y + 3);
        }
        mem.SelectObject(pOldBr);
        mem.SelectObject(pOldPen);
    }

    pDC->BitBlt(lpDIS->rcItem.left, lpDIS->rcItem.top, w, h, &mem, 0, 0,
                SRCCOPY);

    mem.SelectObject(pOldFont);
    mem.SelectObject(pOldBmp);
}
