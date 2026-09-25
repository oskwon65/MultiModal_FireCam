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
extern const char* GetMmCamStartPath();

#define ID_CHART        3101
#define ID_CBO_RANGE    3102
#define ID_BTN_RELOAD   3103
#define ID_LBL_STATE    3104
#define ID_LBL_HEAD     3105

#define PANEL_BG    RGB(255, 255, 255)
#define AXIS_COLOR  RGB(0xB8, 0xC0, 0xCC)
#define GRID_COLOR  RGB(0xE8, 0xEC, 0xF1)
#define LINE_COLOR  RGB(0x2A, 0x9D, 0x8F)
#define TMAX_COLOR  RGB(0xEB, 0x68, 0x34)   // 최고 온도
#define TAVG_COLOR  RGB(0x2A, 0x78, 0xD6)   // 평균 온도
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
    head.Format("[%s]  히스토리 DB 를 한 시간 단위로 묶었습니다. 위는 점수, "
                "아래는 마스크 칸의 온도입니다.\r\n"
                "축이 다르므로 겹치지 않고 위아래로 나눕니다. 가로 위치가 "
                "같으면 같은 시각입니다.",
                gUserID.c_str());
    m_lblHead.SetWindowTextA(head);

    CenterWindow(GetParent());
    Load();
    return TRUE;
}

//---------------------------------------------------------

// 마스크 칸 번호를 SQL 의 IN 목록으로 만든다.
//
// 점수는 마스크 칸의 복원 오차만 본다. 온도도 같은 칸을 봐야 둘이 같은
// 것을 말한다. 마스크가 없으면 빈 문자열을 주고, 그때는 64칸을 다 본다.
//
// JSON_TABLE 의 FOR ORDINALITY 는 1부터 세므로 번호에 1을 더한다.
std::string CDlg_Analysis::MaskCellList() const
{
    const std::string path = std::string(GetMmCamStartPath()) + "users\\"
                           + gUserID + "\\hotlist_mask_local.ini";

    CStdioFile f;
    if (!f.Open(path.c_str(), CFile::modeRead | CFile::typeText))
        return std::string();

    std::string out;
    int idx = 0;
    CStringA line;
    while (f.ReadString(line))
    {
        int pos = 0;
        CStringA tok = line.Tokenize(" @T@", pos);
        while (!tok.IsEmpty())
        {
            ++idx;                       // 1부터
            if (atoi(tok) == 1)
            {
                if (!out.empty()) out += ",";
                char buf[16];
                sprintf_s(buf, sizeof(buf), "%d", idx);
                out += buf;
            }
            tok = line.Tokenize(" @T@", pos);
        }
    }
    f.Close();
    return out;
}

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

    const std::string maskIn = MaskCellList();

    // 목록은 오름차순이다. 그래프도 왼쪽이 옛것이라 그대로 훑는다.
    long total = 0;
    for (size_t i = 0; i < tables.size(); ++i)
    {
        // 점수와 온도를 한 번에 묻는다.
        //
        // hot_list 가 JSON 컬럼이라 JSON_TABLE 로 칸을 펼쳐 집계할 수 있다.
        // 그래야 40,000행을 통째로 끌어와 여기서 파싱하지 않아도 된다.
        std::string where = "t.mscore >= 0";
        if (!maskIn.empty()) where += " AND j.idx IN (" + maskIn + ")";

        char sql[1400];
        sprintf_s(sql, sizeof(sql),
            "SELECT DATE_FORMAT(t.`time`,'%%Y%%m%%d%%H') AS h, "
            "AVG(t.mscore), COUNT(DISTINCT t.id), MAX(j.v), AVG(j.v) "
            "FROM `%s`.`%s` t, "
            "JSON_TABLE(t.hot_list,'$[*]' "
            "COLUMNS(idx FOR ORDINALITY, v DOUBLE PATH '$')) j "
            "WHERE %s GROUP BY h ORDER BY h",
            dbName.c_str(), tables[i].c_str(), where.c_str());

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
            pt.hasT = (row[3] != nullptr && row[4] != nullptr);
            pt.tmax = pt.hasT ? atof(row[3]) : 0.0;
            pt.tavg = pt.hasT ? atof(row[4]) : 0.0;
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
    double tpeak = 0.0;
    for (size_t i = 0; i < m_pts.size(); ++i)
    {
        if (m_pts[i].avg < lo) lo = m_pts[i].avg;
        if (m_pts[i].avg > hi) hi = m_pts[i].avg;
        sum += m_pts[i].avg;
        if (m_pts[i].hasT && m_pts[i].tmax > tpeak) tpeak = m_pts[i].tmax;
    }

    // 온도 칸의 위 끝. 주의 임계값이 화면 밖에 있으면 얼마나 여유가 있는지
    // 알 수 없으므로, 임계값은 언제나 들어오게 잡는다.
    m_tempWarn = atof(read_ini_string("CONSTANTS", "ABS_TEMP_WARN", "0").c_str());
    double top = (tpeak > m_tempWarn) ? tpeak : m_tempWarn;
    if (top < 60.0) top = 60.0;
    m_tempTop = ceil(top * 1.08 / 20.0) * 20.0;

    CStringA st;
    st.Format("%s ~ %s  ·  %u시간 %ld건  ·  점수 최저 %.3f 평균 %.3f "
              "지금 %.3f  ·  온도 최고 %.1f도 지금 %.1f도%s",
              m_pts.front().hour.c_str(), m_pts.back().hour.c_str(),
              (unsigned)m_pts.size(), total,
              lo, sum / m_pts.size(), m_pts.back().avg,
              tpeak, m_pts.back().hasT ? m_pts.back().tmax : 0.0,
              maskIn.empty() ? "  (마스크 없음 · 64칸 전체)" : "");
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
    if (w <= 60 || h <= 90) return;

    CDC mem;
    if (!mem.CreateCompatibleDC(pDC)) return;
    CBitmap bmp;
    if (!bmp.CreateCompatibleBitmap(pDC, w, h)) return;
    CBitmap* pOldBmp = mem.SelectObject(&bmp);

    mem.FillSolidRect(0, 0, w, h, PANEL_BG);
    mem.SetBkMode(TRANSPARENT);
    CFont* pOldFont = mem.SelectObject(&m_fontSmall);

    // 두 칸이 x 축을 함께 쓴다. 날짜 눈금은 아래 칸에만 적는다.
    const int L = 52, R = 14, T = 16, B = 32;
    const int GAP = 34;                       // 두 칸 사이 (칸 이름 자리)
    const int px = L;
    const int pw = w - L - R;
    const int ph = (h - T - B - GAP) / 2;     // 칸 하나의 높이
    const int topY = T;                       // 점수 칸
    const int botY = T + ph + GAP;            // 온도 칸

    auto YScore = [&](double v) -> int {
        if (v < 0.0) v = 0.0;
        if (v > 1.0) v = 1.0;
        return topY + static_cast<int>((1.0 - v) * ph);
    };
    auto YTemp = [&](double v) -> int {
        double t = (m_tempTop > 0.0) ? v / m_tempTop : 0.0;
        if (t < 0.0) t = 0.0;
        if (t > 1.0) t = 1.0;
        return botY + static_cast<int>((1.0 - t) * ph);
    };

    // ---- 칸 이름 ----
    mem.SetTextColor(TEXT_COLOR);
    {
        CRect r1(px, topY - 15, px + 260, topY - 1);
        mem.DrawTextA("점수", &r1, DT_LEFT | DT_SINGLELINE);
        CRect r2(px, botY - 15, px + 260, botY - 1);
        mem.DrawTextA("마스크 칸 온도 (섭씨)", &r2, DT_LEFT | DT_SINGLELINE);
    }

    // ---- 가로 눈금과 y 글자 ----
    {
        CPen penGrid(PS_SOLID, 1, GRID_COLOR);
        CPen* pOld = mem.SelectObject(&penGrid);
        mem.SetTextColor(MUTED_COLOR);

        for (int k = 0; k <= 4; ++k)
        {
            const double v = k * 0.25;
            const int y = YScore(v);
            mem.MoveTo(px, y);
            mem.LineTo(px + pw, y);
            CStringA t;
            t.Format("%.2f", v);
            CRect rcT(0, y - 9, px - 6, y + 9);
            mem.DrawTextA(t, &rcT, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
        }
        for (int k = 0; k <= 4; ++k)
        {
            const double v = m_tempTop * k / 4.0;
            const int y = YTemp(v);
            mem.MoveTo(px, y);
            mem.LineTo(px + pw, y);
            CStringA t;
            t.Format("%.0f", v);
            CRect rcT(0, y - 9, px - 6, y + 9);
            mem.DrawTextA(t, &rcT, DT_RIGHT | DT_VCENTER | DT_SINGLELINE);
        }
        mem.SelectObject(pOld);
    }

    // ---- 문턱선 ----
    // 위 칸 : 재학습이 기존 모델을 그대로 물려받는 점수
    {
        const double band = atof(
            read_ini_string("CONSTANTS", "CONTRIB_BAND_HIGH", "0.85").c_str());
        if (band > 0.0 && band < 1.0)
        {
            CPen pen(PS_DOT, 1, BAND_COLOR);
            CPen* pOld = mem.SelectObject(&pen);
            const int y = YScore(band);
            mem.MoveTo(px, y);
            mem.LineTo(px + pw, y);
            mem.SelectObject(pOld);

            mem.SetTextColor(BAND_COLOR);
            CStringA t;
            t.Format("기여 문턱 %.2f", band);
            CRect rcT(px + pw - 110, y - 17, px + pw, y - 2);
            mem.DrawTextA(t, &rcT, DT_RIGHT | DT_SINGLELINE);
        }
    }
    // 아래 칸 : 0단계 절대 임계값
    if (m_tempWarn > 0.0 && m_tempWarn <= m_tempTop)
    {
        CPen pen(PS_DOT, 1, BAND_COLOR);
        CPen* pOld = mem.SelectObject(&pen);
        const int y = YTemp(m_tempWarn);
        mem.MoveTo(px, y);
        mem.LineTo(px + pw, y);
        mem.SelectObject(pOld);

        mem.SetTextColor(BAND_COLOR);
        CStringA t;
        t.Format("주의 %.0f도", m_tempWarn);
        CRect rcT(px + pw - 110, y - 17, px + pw, y - 2);
        mem.DrawTextA(t, &rcT, DT_RIGHT | DT_SINGLELINE);
    }

    // ---- 축 ----
    {
        CPen penAxis(PS_SOLID, 1, AXIS_COLOR);
        CPen* pOld = mem.SelectObject(&penAxis);
        mem.MoveTo(px, topY);           mem.LineTo(px, topY + ph);
        mem.MoveTo(px, topY + ph);      mem.LineTo(px + pw, topY + ph);
        mem.MoveTo(px, botY);           mem.LineTo(px, botY + ph);
        mem.MoveTo(px, botY + ph);      mem.LineTo(px + pw, botY + ph);
        mem.SelectObject(pOld);
    }

    if (m_pts.empty())
    {
        mem.SetTextColor(MUTED_COLOR);
        CRect rcT(px, topY, px + pw, botY + ph);
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
        return px + static_cast<int>(static_cast<double>(pw) * i / (n - 1));
    };

    // ---- 날짜가 바뀌는 자리 ----
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
            mem.MoveTo(x, topY);  mem.LineTo(x, topY + ph);
            mem.MoveTo(x, botY);  mem.LineTo(x, botY + ph);

            if (x - lastLabelX < 46) continue;
            lastLabelX = x;

            CStringA t;
            t.Format("%c%c-%c%c", day[4], day[5], day[6], day[7]);
            CRect rcT(x - 24, botY + ph + 6, x + 24, botY + ph + 24);
            mem.DrawTextA(t, &rcT, DT_CENTER | DT_SINGLELINE);
        }
        mem.SelectObject(pOld);
    }

    // ---- 선 하나를 긋는다 ----
    auto DrawSeries = [&](COLORREF clr, bool temp, bool useMax) {
        CPen pen(PS_SOLID, 2, clr);
        CPen* pOld = mem.SelectObject(&pen);
        bool started = false;
        for (size_t i = 0; i < n; ++i)
        {
            if (temp && !m_pts[i].hasT) { started = false; continue; }
            const int x = XAt(i);
            const int y = temp ? YTemp(useMax ? m_pts[i].tmax : m_pts[i].tavg)
                               : YScore(m_pts[i].avg);
            if (!started) { mem.MoveTo(x, y); started = true; }
            else          { mem.LineTo(x, y); }
        }
        mem.SelectObject(pOld);
    };

    DrawSeries(LINE_COLOR, false, false);
    DrawSeries(TAVG_COLOR, true, false);
    DrawSeries(TMAX_COLOR, true, true);

    // 점은 많지 않을 때만. 수백 개를 찍으면 선이 뭉개진다.
    if (n <= 90)
    {
        CPen penNone(PS_NULL, 0, (COLORREF)0);
        CPen* pOldPen = mem.SelectObject(&penNone);
        struct { COLORREF c; int kind; } dots[] = {
            { LINE_COLOR, 0 }, { TAVG_COLOR, 1 }, { TMAX_COLOR, 2 } };
        for (const auto& d : dots)
        {
            CBrush br(d.c);
            CBrush* pOldBr = mem.SelectObject(&br);
            for (size_t i = 0; i < n; ++i)
            {
                if (d.kind != 0 && !m_pts[i].hasT) continue;
                const int x = XAt(i);
                const int y = (d.kind == 0) ? YScore(m_pts[i].avg)
                            : (d.kind == 1) ? YTemp(m_pts[i].tavg)
                                            : YTemp(m_pts[i].tmax);
                mem.Ellipse(x - 3, y - 3, x + 3, y + 3);
            }
            mem.SelectObject(pOldBr);
        }
        mem.SelectObject(pOldPen);
    }

    // ---- 온도 칸 범례 ----
    // 선이 둘이면 색만으로는 무엇인지 알 수 없다.
    {
        int lx = px + 6;
        const int ly = botY + 6;
        struct { COLORREF c; const char* t; } leg[] = {
            { TMAX_COLOR, "최고" }, { TAVG_COLOR, "평균" } };
        for (const auto& e : leg)
        {
            CPen pen(PS_SOLID, 2, e.c);
            CPen* pOld = mem.SelectObject(&pen);
            mem.MoveTo(lx, ly + 7);
            mem.LineTo(lx + 16, ly + 7);
            mem.SelectObject(pOld);

            mem.SetTextColor(MUTED_COLOR);
            CRect rcT(lx + 21, ly, lx + 71, ly + 15);
            mem.DrawTextA(e.t, &rcT, DT_LEFT | DT_SINGLELINE);
            lx += 66;
        }
    }

    pDC->BitBlt(lpDIS->rcItem.left, lpDIS->rcItem.top, w, h, &mem, 0, 0,
                SRCCOPY);

    mem.SelectObject(pOldFont);
    mem.SelectObject(pOldBmp);
}
