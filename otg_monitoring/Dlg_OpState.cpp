// Dlg_OpState.cpp: 운전 상태 관찰 창
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_OpState.h"
#include "afxdialogex.h"

extern "C" {
#include <mysql.h>
}

#include <map>
#include <string>
#include <vector>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <memory>
#include <algorithm>

extern std::string gUserID;
extern MYSQL* connect_history_db(std::string* dbNameOut);
extern const char* GetMmCamStartPath();

#define ID_CARDS        3201
#define ID_GRID         3202
#define ID_CBO_RANGE    3203
#define ID_BTN_RELOAD   3204
#define ID_LBL_STATE    3205
#define ID_LBL_HEAD     3206
#define ID_LBL_NOW      3207
#define ID_DT_FROM      3208
#define ID_DT_TO        3209
#define ID_CAP_FROM     3210
#define ID_CAP_TO       3211
#define ID_BTN_NAMES    3212

// 콤보의 자리. 마지막은 달력을 직접 건드렸을 때 넘어오는 자리다.
#define RANGE_7      0
#define RANGE_30     1
#define RANGE_90     2
#define RANGE_ALL    3
#define RANGE_PICK   4

#define PANEL_BG    RGB(255, 255, 255)
#define TEXT_COLOR  RGB(0x1A, 0x24, 0x35)
#define MUTED_COLOR RGB(0x66, 0x70, 0x85)
#define LINE_COLOR  RGB(0xDD, 0xD6, 0xCB)
#define ACCENT      RGB(0x8C, 0x3B, 0x16)

// 상태 색. 한 가지 색조, 옅음에서 짙음으로.
//
// 상태 번호는 make_op_states.py 가 온도가 낮은 쪽부터 매긴다. 색이 그
// 순서를 그대로 따르므로 띠가 어두워지면 뜨거워지는 중이다. 무지개로
// 칠하면 어느 쪽이 더운지를 색만 보고 알 수 없다.
//
// 밝기가 고르게 내려가도록 여덟 칸을 잡았다. 상태가 여섯이든 다섯이든
// 이 여덟 칸에 고루 펼쳐 쓴다 - 앞에서부터 차례로 쓰면 진한 쪽 서넛이
// 서로 구별되지 않는다.
static const COLORREF ST_COLOR[] = {
    RGB(0xF2, 0xEA, 0xE0), RGB(0xE8, 0xD4, 0xB8), RGB(0xDC, 0xB7, 0x8A),
    RGB(0xCE, 0x94, 0x59), RGB(0xBE, 0x74, 0x33), RGB(0xA2, 0x57, 0x1F),
    RGB(0x7E, 0x3C, 0x12), RGB(0x56, 0x23, 0x0A) };

#define NO_DATA_BG  RGB(0xFB, 0xF9, 0xF6)

// 그 색 위에 얹을 빗금 색. 어두운 칸에는 검은 빗금이 보이지 않는다.
static COLORREF InkOn(COLORREF bg)
{
    const int lum = (30 * GetRValue(bg) + 59 * GetGValue(bg)
                   + 11 * GetBValue(bg)) / 100;
    return (lum < 128) ? RGB(0xFF, 0xF3, 0xE6) : RGB(0x1A, 0x24, 0x35);
}

// 상태 n 가지 중 i 번째가 쓸 색.
static COLORREF ColorOf(int i, int n)
{
    if (i < 0) return NO_DATA_BG;

    const int last = _countof(ST_COLOR) - 1;
    if (n <= 1) return ST_COLOR[last];
    if (n > _countof(ST_COLOR)) return ST_COLOR[i % _countof(ST_COLOR)];

    return ST_COLOR[i * last / (n - 1)];
}

// 현황 파일은 UTF-8 이고 이 빌드는 MBCS 다. 거기서 읽은 한글을 옮긴다.
static CStringA U8(const char* u)
{
    if (!u || !*u) return CStringA();

    const int wn = MultiByteToWideChar(CP_UTF8, 0, u, -1, nullptr, 0);
    if (wn <= 0) return CStringA(u);

    CStringW w;
    MultiByteToWideChar(CP_UTF8, 0, u, -1, w.GetBuffer(wn), wn);
    w.ReleaseBuffer();

    const int an = WideCharToMultiByte(CP_ACP, 0, w, -1, nullptr, 0,
        nullptr, nullptr);
    if (an <= 0) return CStringA(u);

    CStringA a;
    WideCharToMultiByte(CP_ACP, 0, w, -1, a.GetBuffer(an), an, nullptr, nullptr);
    a.ReleaseBuffer();
    return a;
}

//---------------------------------------------------------
// op_states.json 을 읽는 만큼만의 파서
//
// 이 파일은 make_op_states.py 가 json.dump 로 적은 것이라 모양이 늘 같다.
// 필요한 것은 키 몇 개와 숫자 배열뿐이라, JSON 라이브러리를 들이는 대신
// 키를 찾아 그 뒤의 값을 읽는다.
//---------------------------------------------------------
static bool jSeek(const std::string& s, size_t& p, const char* key)
{
    std::string k = "\"";
    k += key;
    k += "\"";

    const size_t q = s.find(k, p);
    if (q == std::string::npos) return false;

    const size_t c = s.find(':', q + k.size());
    if (c == std::string::npos) return false;

    p = c + 1;
    return true;
}

static double jNum(const std::string& s, size_t& p)
{
    char* e = nullptr;
    const double v = strtod(s.c_str() + p, &e);
    if (e != nullptr) p = static_cast<size_t>(e - s.c_str());
    return v;
}

static std::string jStr(const std::string& s, size_t& p)
{
    const size_t a = s.find('\"', p);
    if (a == std::string::npos) return std::string();

    const size_t b = s.find('\"', a + 1);
    if (b == std::string::npos) return std::string();

    p = b + 1;
    return s.substr(a + 1, b - a - 1);
}

static void jArr(const std::string& s, size_t& p, std::vector<double>& out)
{
    out.clear();

    const size_t a = s.find('[', p);
    if (a == std::string::npos) return;
    const size_t b = s.find(']', a);
    if (b == std::string::npos) return;

    size_t q = a + 1;
    while (q < b)
    {
        while (q < b && s[q] != '-' && s[q] != '.'
               && !isdigit(static_cast<unsigned char>(s[q]))) ++q;
        if (q >= b) break;

        char* e = nullptr;
        const double v = strtod(s.c_str() + q, &e);
        if (e == nullptr || e <= s.c_str() + q) { ++q; continue; }

        out.push_back(v);
        q = static_cast<size_t>(e - s.c_str());
    }
    p = b + 1;
}

// SQL 을 이어 붙일 때 쓸 숫자 문자열.
static std::string Num(double v, int dec)
{
    char b[64];
    sprintf_s(b, sizeof(b), "%.*f", dec, v);
    return std::string(b);
}

static std::string Int(long v)
{
    char b[32];
    sprintf_s(b, sizeof(b), "%ld", v);
    return std::string(b);
}

IMPLEMENT_DYNAMIC(CDlg_OpState, CDialogEx)

CDlg_OpState::CDlg_OpState(CWnd* pParent /*=nullptr*/)
    : CDialogEx(IDD_DLG_OPSTATE, pParent)
{
}

CDlg_OpState::~CDlg_OpState()
{
}

void CDlg_OpState::DoDataExchange(CDataExchange* pDX)
{
    CDialogEx::DoDataExchange(pDX);
}

BEGIN_MESSAGE_MAP(CDlg_OpState, CDialogEx)
    ON_CBN_SELCHANGE(ID_CBO_RANGE, &CDlg_OpState::OnSelchangeRange)
    ON_BN_CLICKED(ID_BTN_RELOAD, &CDlg_OpState::OnBnClickedReload)
    ON_BN_CLICKED(ID_BTN_NAMES, &CDlg_OpState::OnBnClickedNames)
    ON_NOTIFY(DTN_DATETIMECHANGE, ID_DT_FROM, &CDlg_OpState::OnDateChanged)
    ON_NOTIFY(DTN_DATETIMECHANGE, ID_DT_TO, &CDlg_OpState::OnDateChanged)
    ON_WM_DRAWITEM()
    ON_WM_CTLCOLOR()
    ON_WM_MOUSEMOVE()
    ON_WM_MOUSELEAVE()
END_MESSAGE_MAP()

//---------------------------------------------------------

BOOL CDlg_OpState::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    m_font.CreateFont(UI_FONT_SIZE, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    m_fontSmall.CreateFont(UI_FONT_SIZE - 4, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        ANTIALIASED_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    m_fontBig.CreateFont(UI_FONT_SIZE + 1, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        ANTIALIASED_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    // 비율은 이 창에서 가장 먼저 눈에 들어와야 하는 값이다.
    m_fontNum.CreateFont(UI_FONT_SIZE + 12, 0, 0, 0, FW_SEMIBOLD, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        ANTIALIASED_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    m_fontTip.CreateFont((UI_FONT_SIZE - 4) * 125 / 100, 0, 0, 0, FW_NORMAL,
        FALSE, FALSE, 0, DEFAULT_CHARSET, OUT_DEFAULT_PRECIS,
        CLIP_DEFAULT_PRECIS, ANTIALIASED_QUALITY, DEFAULT_PITCH | FF_DONTCARE,
        _T(UI_FONT_NAME));

    m_brWhite.CreateSolidBrush(PANEL_BG);

    CRect rc;
    GetClientRect(&rc);
    const int M = 12;
    const int btnW = 112, btnH = 32;
    const int headH = 48, nowH = 36, stateH = 28;

    m_lblHead.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, M, rc.right - M, M + headH), this, ID_LBL_HEAD);

    int y = M + headH + 2;

    m_lblNow.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, y, rc.right - M, y + nowH), this, ID_LBL_NOW);

    y += nowH + 6;

    m_cboRange.Create(WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_VSCROLL
        | CBS_DROPDOWNLIST,
        CRect(M, y, M + 150, y + 220), this, ID_CBO_RANGE);
    m_cboRange.AddString("최근 7일");
    m_cboRange.AddString("최근 30일");
    m_cboRange.AddString("최근 90일");
    m_cboRange.AddString("전체");
    m_cboRange.AddString("직접 지정");
    m_cboRange.SetCurSel(RANGE_30);

    // 달력.
    //
    // 날짜를 타이핑하게 두면 2026-13-45 같은 값이 들어온다. 달력은 애초에
    // 잘못된 날짜를 고를 수 없다. 자리는 "2026-09-21" 열 글자와 드롭다운
    // 단추가 들어갈 만큼 잡는다.
    const int dtW = (UI_FONT_SIZE * 62 / 100) * 10 + 24;
    int dx = M + 160;

    m_capFrom.Create("기간", WS_CHILD | WS_VISIBLE | SS_LEFT | SS_CENTERIMAGE,
        CRect(dx, y, dx + 42, y + btnH), this, ID_CAP_FROM);
    dx += 46;

    m_dtFrom.Create(WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_BORDER
        | DTS_SHORTDATEFORMAT,
        CRect(dx, y + 2, dx + dtW, y + btnH - 2), this, ID_DT_FROM);
    dx += dtW + 6;

    m_capTo.Create("~", WS_CHILD | WS_VISIBLE | SS_CENTER | SS_CENTERIMAGE,
        CRect(dx, y, dx + 16, y + btnH), this, ID_CAP_TO);
    dx += 20;

    m_dtTo.Create(WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_BORDER
        | DTS_SHORTDATEFORMAT,
        CRect(dx, y + 2, dx + dtW, y + btnH - 2), this, ID_DT_TO);
    dx += dtW + 12;

    m_btnReload.Create("다시 읽기", WS_CHILD | WS_VISIBLE | WS_TABSTOP
        | BS_PUSHBUTTON,
        CRect(dx, y, dx + btnW, y + btnH), this, ID_BTN_RELOAD);
    dx += btnW + 8;

    // 이름은 스크립트가 온도 순서대로 붙인 짐작이다. 설비를 아는 사람이 고친다.
    m_btnNames.Create("운전상태명 변경", WS_CHILD | WS_VISIBLE | WS_TABSTOP
        | BS_PUSHBUTTON,
        CRect(dx, y, dx + 152, y + btnH), this, ID_BTN_NAMES);   // 글이 길어 조금 넓다

    const int bx = rc.right - M - btnW;
    m_btnClose.Create("닫기", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
        CRect(bx, y, bx + btnW, y + btnH), this, IDCANCEL);

    y += btnH + 8;

    // 상태 카드. 폭은 상태 수에 맞춰 나누므로 높이만 잡아 둔다.
    const int cardsH = 188;
    m_cards.Create("", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | SS_OWNERDRAW,
        CRect(M, y, rc.right - M, y + cardsH), this, ID_CARDS);

    y += cardsH + 8;

    const int yState = rc.bottom - M - stateH;
    m_grid.Create("", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | SS_OWNERDRAW,
        CRect(M, y, rc.right - M, yState - 6), this, ID_GRID);

    m_lblState.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
        CRect(M, yState, rc.right - M, yState + stateH), this, ID_LBL_STATE);

    SetFont(&m_font);
    SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font.GetSafeHandle(), TRUE);

    CenterWindow(GetParent());

    if (!LoadStates())
    {
        m_btnNames.EnableWindow(FALSE);
        m_lblHead.SetWindowTextA(m_madeInfo);
        SetState("운전 상태 분류표가 없습니다. retrain/make_op_states.py 로 "
                 "만든 뒤 다시 여십시오.");
        return TRUE;
    }

    CStringA head;
    head.Format("[%s]  열화상 마스크 %u칸의 온도 분포로 운전 상태를 %u가지로 "
                "나눴습니다. 가르는 것은 최고 온도와 칸 사이 벌어짐입니다.\r\n"
                "분류표 %s",
                gUserID.c_str(), (unsigned)m_cells.size(),
                (unsigned)m_states.size(), (LPCSTR)m_madeInfo);
    m_lblHead.SetWindowTextA(head);

    ShowNow();
    Load();
    return TRUE;
}

//---------------------------------------------------------
// 분류표를 읽는다
//---------------------------------------------------------
bool CDlg_OpState::LoadStates()
{
    m_cells.clear();
    m_states.clear();

    const std::string path = std::string(GetMmCamStartPath()) + "users\\"
                           + gUserID + "\\op_states.json";

    std::string txt;
    {
        FILE* f = nullptr;
        if (fopen_s(&f, path.c_str(), "rb") != 0 || f == nullptr)
        {
            m_madeInfo = "op_states.json 이 없습니다";
            return false;
        }
        char buf[4096];
        size_t n = 0;
        while ((n = fread(buf, 1, sizeof(buf), f)) > 0) txt.append(buf, n);
        fclose(f);
    }

    size_t p = 0;
    if (jSeek(txt, p, "period")) m_period = jStr(txt, p).c_str();

    long frames = 0;
    p = 0;
    if (jSeek(txt, p, "frames")) frames = (long)jNum(txt, p);

    CStringA made;
    p = 0;
    if (jSeek(txt, p, "made")) made = jStr(txt, p).c_str();

    m_madeInfo.Format("%s · %ld프레임 · %s 만듦",
        m_period.IsEmpty() ? "기간 모름" : (LPCSTR)m_period,
        frames, made.IsEmpty() ? "-" : (LPCSTR)made);

    // 점수가 보는 칸.
    p = 0;
    if (jSeek(txt, p, "cells"))
    {
        std::vector<double> v;
        jArr(txt, p, v);
        for (size_t i = 0; i < v.size(); ++i)
        {
            const int c = (int)v[i];
            if (c >= 0 && c < 64) m_cells.push_back(c);
        }
    }

    // 상태들. 한 덩이 안에서 name · center · max · min · spread 순으로 적힌다.
    p = 0;
    if (!jSeek(txt, p, "states"))
    {
        m_madeInfo = "op_states.json 에 상태가 없습니다";
        return false;
    }

    while (jSeek(txt, p, "name"))
    {
        State s;
        s.name = U8(jStr(txt, p).c_str());

        if (!jSeek(txt, p, "center")) break;
        jArr(txt, p, s.center);

        size_t q = p;
        if (jSeek(txt, q, "max"))     { s.tmax    = jNum(txt, q); p = q; }
        q = p;
        if (jSeek(txt, q, "min"))     { s.tmin    = jNum(txt, q); p = q; }
        q = p;
        if (jSeek(txt, q, "spread"))  { s.spread  = jNum(txt, q); p = q; }
        q = p;
        if (jSeek(txt, q, "dev"))     { s.dev     = jNum(txt, q); p = q; }
        q = p;
        if (jSeek(txt, q, "far"))     { s.farLine = jNum(txt, q); p = q; }

        if (s.center.size() != m_cells.size()) break;
        m_states.push_back(s);
    }

    if (m_cells.empty() || m_states.empty())
    {
        m_madeInfo = "op_states.json 을 읽지 못했습니다";
        return false;
    }
    return true;
}

//---------------------------------------------------------
// 지금 상태. 감시가 현황 파일에 적어 둔 것을 읽기만 한다.
//---------------------------------------------------------
void CDlg_OpState::ShowNow()
{
    const std::string st = std::string(GetMmCamStartPath()) + "users\\"
                         + gUserID + "\\stage_status.ini";

    char buf[256] = { 0 };
    GetPrivateProfileStringA("STATUS", "OP_STATE", "", buf,
        (DWORD)sizeof(buf), st.c_str());
    const CStringA name = U8(buf);

    GetPrivateProfileStringA("STATUS", "OP_MIX", "", buf,
        (DWORD)sizeof(buf), st.c_str());
    const CStringA mix = U8(buf);

    CStringA t;
    if (name.IsEmpty())
        t = "지금   감시가 돌고 있지 않습니다";
    else if (mix.IsEmpty())
        t.Format("지금   %s", (LPCSTR)name);
    else
        t.Format("지금   %s   ·   최근 %s", (LPCSTR)name, (LPCSTR)mix);

    m_lblNow.SetWindowTextA(t);
}

void CDlg_OpState::SetState(const char* text)
{
    m_lblState.SetWindowTextA(text);
    m_lblState.UpdateWindow();
}

//---------------------------------------------------------
// 상태 이름 바꾸기
//
// 이름은 make_op_states.py 가 최고 온도 순서대로 붙인 짐작이라 설비와 맞지
// 않을 수 있다. 여기서 고친 이름은 op_states.json 에 그대로 적으므로, 감시
// (predict_machine/op_state.py)도 같은 이름을 쓴다.
//
// 창 틀은 .rc 에 두지 않고 여기서 만든다. 이 창에서만 쓰는 작은 창이다.
//---------------------------------------------------------
#define ID_NM_EDIT0  3301          // 상태 수만큼 이어 붙는다

class CDlg_OpNames : public CDialogEx
{
public:
    struct Row
    {
        CStringA name;
        CStringA hint;     // 그 상태가 어떤 모양인지 (최고 · 최저 · 비율)
        COLORREF color;
        int      idx;      // 분류표에서 몇 번째 상태인가 (목록은 비율 순이다)
    };

    CDlg_OpNames(const std::vector<Row>& rows, const CStringA& period,
                 CFont* font, CFont* hintFont,
                 CWnd* parent)
        : CDialogEx(), m_rows(rows), m_period(period), m_font(font),
          m_small(hintFont)
    {
        m_tpl.assign(64, 0);
        DLGTEMPLATE* t = reinterpret_cast<DLGTEMPLATE*>(m_tpl.data());
        t->style = DS_MODALFRAME | WS_POPUP | WS_CAPTION | WS_SYSMENU;
        t->cx = 300; t->cy = 200;
        WORD* p = reinterpret_cast<WORD*>(t + 1);
        *p++ = 0;                                     // 메뉴 없음
        *p++ = 0;                                     // 기본 창 종류
        const wchar_t* cap = L"\xC6B4\xC804 \xC0C1\xD0DC \xC774\xB984";  // "운전 상태 이름"
        while (*cap) *p++ = (WORD)*cap++;
        *p++ = 0;
        InitModalIndirect(t, parent);
    }

    const std::vector<CStringA>& Names() const { return m_names; }

protected:
    virtual BOOL OnInitDialog() override
    {
        CDialogEx::OnInitDialog();

        const int M = 14, rowH = 40, edW = 220, chipW = 14, bH = 32;
        const int n = (int)m_rows.size();
        const int W = 620;
        const int top = M + 46 + 30;     // 안내 두 줄 + 기간 한 줄
        const int H = top + n * rowH + 12 + bH + M;

        CRect wr(0, 0, W, H);
        AdjustWindowRectEx(&wr, GetStyle(), FALSE, GetExStyle());
        SetWindowPos(nullptr, 0, 0, wr.Width(), wr.Height(),
                     SWP_NOMOVE | SWP_NOZORDER);
        CenterWindow();

        m_lbl.Create("비율이 큰 상태부터 차례입니다. 설비에 맞는 이름으로 고치십시오.\r\n"
                     "감시를 다시 시작하지 않아도 1분 안에 감시 쪽 이름도 바뀝니다.",
                     WS_CHILD | WS_VISIBLE | SS_LEFT, CRect(M, M, W - M, M + 42), this);
        if (m_font) m_lbl.SetFont(m_font);

        // 비율이 어느 기간의 것인지. 운전 상태 창에서 고른 기간이 그대로 온다.
        m_lblPeriod.Create(m_period, WS_CHILD | WS_VISIBLE | SS_LEFT,
                           CRect(M, M + 46, W - M, M + 46 + 26), this);
        if (m_font) m_lblPeriod.SetFont(m_font);

        m_chips.resize(n);
        m_edits.resize(n);
        m_hints.resize(n);
        for (int i = 0; i < n; ++i)
        {
            const int y = top + i * rowH;

            // 카드 윗변과 같은 색 표식. 어느 카드의 이름인지 색으로 잇는다.
            m_chips[i].reset(new CStatic);
            m_chips[i]->Create("", WS_CHILD | WS_VISIBLE | SS_OWNERDRAW,
                CRect(M, y + 6, M + chipW, y + 26), this, 3400 + i);

            m_edits[i].reset(new CEdit);
            m_edits[i]->CreateEx(WS_EX_CLIENTEDGE, "EDIT", m_rows[i].name,
                WS_CHILD | WS_VISIBLE | WS_TABSTOP | ES_AUTOHSCROLL,
                CRect(M + chipW + 8, y + 2, M + chipW + 8 + edW, y + 30),
                this, ID_NM_EDIT0 + i);
            m_edits[i]->LimitText(40);
            if (m_font) m_edits[i]->SetFont(m_font);

            m_hints[i].reset(new CStatic);
            m_hints[i]->Create(m_rows[i].hint,
                WS_CHILD | WS_VISIBLE | SS_LEFT | SS_CENTERIMAGE,
                CRect(M + chipW + 8 + edW + 12, y + 2, W - M, y + 30), this);
            if (m_small) m_hints[i]->SetFont(m_small);
        }

        const int yb = H - M - bH;
        m_btnOk.Create("저장", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_DEFPUSHBUTTON,
            CRect(W - M - 208, yb, W - M - 108, yb + bH), this, IDOK);
        m_btnCancel.Create("취소", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
            CRect(W - M - 100, yb, W - M, yb + bH), this, IDCANCEL);
        if (m_font) { m_btnOk.SetFont(m_font); m_btnCancel.SetFont(m_font); }

        if (n > 0) { m_edits[0]->SetFocus(); m_edits[0]->SetSel(0, -1); }
        return FALSE;     // 첫 칸에 초점을 두었다
    }

    afx_msg void OnDrawItem(int nIDCtl, LPDRAWITEMSTRUCT lpDIS)
    {
        const int i = nIDCtl - 3400;
        if (i >= 0 && i < (int)m_rows.size())
        {
            CDC* dc = CDC::FromHandle(lpDIS->hDC);
            dc->FillSolidRect(&lpDIS->rcItem, m_rows[i].color);
            return;
        }
        CDialogEx::OnDrawItem(nIDCtl, lpDIS);
    }

    virtual void OnOK() override
    {
        // 감시와 이 창이 이름을 따옴표로 끊어 읽는다. 따옴표와 역빗금은 받지 않는다.
        std::vector<CStringA> out;
        for (size_t i = 0; i < m_edits.size(); ++i)
        {
            CStringA s;
            m_edits[i]->GetWindowTextA(s);
            s.Trim();

            CStringA why;
            if (s.IsEmpty())
                why = "비어 있습니다.";
            else if (s.FindOneOf("\"\\") >= 0)
                why = "따옴표(\")와 역빗금(\\)은 쓸 수 없습니다.";
            else
                for (int c = 0; c < s.GetLength(); ++c)
                    if ((unsigned char)s[c] < 0x20) { why = "제어 문자가 있습니다."; break; }

            // 같은 이름이 둘이면 화면에서 두 상태를 가릴 수 없다.
            for (size_t k = 0; why.IsEmpty() && k < out.size(); ++k)
                if (out[k] == s) why.Format("%d번째와 이름이 같습니다.", (int)k + 1);

            if (!why.IsEmpty())
            {
                CStringA m;
                m.Format("%d번째 이름이 %s", (int)i + 1, (LPCSTR)why);
                AfxMessageBox(m, MB_ICONWARNING);
                m_edits[i]->SetFocus();
                m_edits[i]->SetSel(0, -1);
                return;
            }
            out.push_back(s);
        }
        m_names.swap(out);
        CDialogEx::OnOK();
    }

    DECLARE_MESSAGE_MAP()

private:
    std::vector<WORD> m_tpl;
    std::vector<Row> m_rows;
    CStringA m_period;     // 비율을 센 기간 한 줄
    std::vector<CStringA> m_names;
    CFont* m_font;
    CFont* m_small;

    CStatic m_lbl, m_lblPeriod;
    std::vector<std::unique_ptr<CStatic> > m_chips, m_hints;
    std::vector<std::unique_ptr<CEdit> > m_edits;
    CButton m_btnOk, m_btnCancel;
};

BEGIN_MESSAGE_MAP(CDlg_OpNames, CDialogEx)
    ON_WM_DRAWITEM()
END_MESSAGE_MAP()

// 화면 부호(CP_ACP) -> UTF-8. op_states.json 은 UTF-8 이다.
static std::string ToU8(const CStringA& a)
{
    if (a.IsEmpty()) return std::string();

    const int wn = MultiByteToWideChar(CP_ACP, 0, a, -1, nullptr, 0);
    if (wn <= 0) return std::string((LPCSTR)a);
    CStringW w;
    MultiByteToWideChar(CP_ACP, 0, a, -1, w.GetBuffer(wn), wn);
    w.ReleaseBuffer();

    const int un = WideCharToMultiByte(CP_UTF8, 0, w, -1, nullptr, 0,
        nullptr, nullptr);
    if (un <= 0) return std::string((LPCSTR)a);
    std::string u(un, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w, -1, &u[0], un, nullptr, nullptr);
    u.resize(un - 1);                  // 끝의 0
    return u;
}

// 이름 칸만 바꿔 쓴다. 나머지(중심 · 비율 · 기준선)는 한 글자도 건드리지 않는다.
//
// 파일 전체를 다시 쓰면 이 파서가 모르는 키가 사라질 수 있다. 그래서 상태
// 덩이마다 "name" 의 값 자리만 갈아 끼운다. 다 쓴 뒤 임시 파일에서 한 번에
// 바꿔 놓으므로, 쓰다가 멈춰도 감시가 반쪽 파일을 읽지 않는다.
static bool SaveOpStateNames(const std::vector<CStringA>& names, CStringA& err)
{
    const std::string path = std::string(GetMmCamStartPath()) + "users\\"
                           + gUserID + "\\op_states.json";

    std::string txt;
    {
        FILE* f = nullptr;
        if (fopen_s(&f, path.c_str(), "rb") != 0 || f == nullptr)
        {
            err = "op_states.json 을 열 수 없습니다.";
            return false;
        }
        char buf[4096];
        size_t n = 0;
        while ((n = fread(buf, 1, sizeof(buf), f)) > 0) txt.append(buf, n);
        fclose(f);
    }

    size_t p = 0;
    if (!jSeek(txt, p, "states"))
    {
        err = "op_states.json 에 상태가 없습니다.";
        return false;
    }

    size_t k = 0;
    while (k < names.size() && jSeek(txt, p, "name"))
    {
        const size_t a = txt.find('\"', p);
        if (a == std::string::npos) break;
        const size_t b = txt.find('\"', a + 1);
        if (b == std::string::npos) break;

        const std::string u = ToU8(names[k]);
        txt.replace(a + 1, b - a - 1, u);
        p = a + 1 + u.size() + 1;
        ++k;
    }
    if (k != names.size())
    {
        err.Format("op_states.json 의 상태 수(%d)가 화면(%d)과 다릅니다. "
                   "창을 다시 여십시오.", (int)k, (int)names.size());
        return false;
    }

    const std::string tmp = path + ".tmp";
    {
        FILE* f = nullptr;
        if (fopen_s(&f, tmp.c_str(), "wb") != 0 || f == nullptr)
        {
            err = "임시 파일을 만들 수 없습니다.";
            return false;
        }
        const size_t w = fwrite(txt.data(), 1, txt.size(), f);
        const bool ok = (fclose(f) == 0) && (w == txt.size());
        if (!ok)
        {
            DeleteFileA(tmp.c_str());
            err = "임시 파일을 다 쓰지 못했습니다.";
            return false;
        }
    }
    if (!MoveFileExA(tmp.c_str(), path.c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
    {
        DeleteFileA(tmp.c_str());
        err.Format("op_states.json 을 바꿔 놓지 못했습니다 (오류 %lu).",
                   GetLastError());
        return false;
    }
    return true;
}

void CDlg_OpState::OnBnClickedNames()
{
    if (m_states.empty()) return;

    // 비율이 큰 것부터. 이름을 고칠 때 먼저 보아야 할 것은 자주 나오는 상태다.
    // 비율은 카드와 같은 것 - 이 창에서 고른 기간에 그 상태였던 프레임의 몫이다.
    std::vector<int> order(m_states.size());
    for (size_t i = 0; i < order.size(); ++i) order[i] = (int)i;
    std::stable_sort(order.begin(), order.end(), [&](int a, int b) {
        return m_states[a].n > m_states[b].n; });

    std::vector<CDlg_OpNames::Row> rows;
    for (size_t k = 0; k < order.size(); ++k)
    {
        const int i = order[k];
        const State& s = m_states[i];
        CDlg_OpNames::Row r;
        r.name = s.name;
        CStringA pct = "-";
        if (m_total > 0) pct.Format("%.1f%%", 100.0 * s.n / m_total);
        r.hint.Format("%s  ·  최고 %.0f도 · 최저 %.0f도", (LPCSTR)pct, s.tmax, s.tmin);
        r.color = ColorOf(i, (int)m_states.size());
        r.idx = i;
        rows.push_back(r);
    }

    // 비율을 센 기간. 날짜는 자료가 있는 첫날과 끝날, 일수는 자료가 있는 날 수다.
    CStringA period;
    if (m_days.empty() || m_total <= 0)
        period = "기간 안에 읽은 프레임이 없어 비율을 셀 수 없습니다.";
    else
    {
        auto ymd = [](const std::string& d) {
            CStringA t;
            if (d.size() >= 8)
                t.Format("%s-%s-%s", d.substr(0, 4).c_str(), d.substr(4, 2).c_str(),
                         d.substr(6, 2).c_str());
            else t = d.c_str();
            return t;
        };
        period.Format("운전 기간  %s ~ %s  (%u일 · %ld프레임)",
                      (LPCSTR)ymd(m_days.front().ymd), (LPCSTR)ymd(m_days.back().ymd),
                      (unsigned)m_days.size(), m_total);
    }

    CDlg_OpNames dlg(rows, period, &m_font, &m_fontTip, this);
    if (dlg.DoModal() != IDOK) return;

    // 창은 비율 순으로 돌려준다. 분류표 순서로 되돌린다.
    const std::vector<CStringA>& shown = dlg.Names();
    if (shown.size() != m_states.size()) return;
    std::vector<CStringA> names(m_states.size());
    for (size_t k = 0; k < shown.size(); ++k) names[rows[k].idx] = shown[k];

    CStringA err;
    if (!SaveOpStateNames(names, err))
    {
        AfxMessageBox("이름을 저장하지 못했습니다.\r\n\r\n" + err, MB_ICONERROR);
        return;
    }

    // 비율과 점수는 DB 에서 센 그대로 두고 이름만 바꾼다.
    for (size_t i = 0; i < names.size(); ++i) m_states[i].name = names[i];
    m_cards.Invalidate();
    m_grid.Invalidate();
    SetState("상태 이름을 저장했습니다. 위 '지금' 줄은 감시가 새 이름을 읽은 뒤(1분 안) 바뀝니다.");
}

// 설정 창에서 부르는 길. DB 를 훑지 않고 op_states.json 만 읽는다.
//
// 비율은 분류표를 만들 때 센 것(share)이고, 기간도 그때의 것(period)이다.
// 운전 상태 창의 [운전상태명 변경] 은 그 창에서 고른 기간으로 센 비율을 쓴다.
bool EditOpStateNames(CWnd* parent, CFont* font, CFont* hintFont)
{
    const std::string path = std::string(GetMmCamStartPath()) + "users\\"
                           + gUserID + "\\op_states.json";

    std::string txt;
    {
        FILE* f = nullptr;
        if (fopen_s(&f, path.c_str(), "rb") != 0 || f == nullptr)
        {
            AfxMessageBox("운전 상태 분류표(op_states.json)가 없습니다.\r\n"
                          "retrain/make_op_states.py 로 만든 뒤 다시 하십시오.");
            return false;
        }
        char buf[4096];
        size_t n = 0;
        while ((n = fread(buf, 1, sizeof(buf), f)) > 0) txt.append(buf, n);
        fclose(f);
    }

    size_t p = 0;
    std::string period;
    if (jSeek(txt, p, "period")) period = jStr(txt, p);
    long frames = 0;
    p = 0;
    if (jSeek(txt, p, "frames")) frames = (long)jNum(txt, p);

    // 상태 덩이 안의 순서는 name · center · share · max · min 이다.
    struct S { CStringA name; double share = 0, tmax = 0, tmin = 0; };
    std::vector<S> st;
    p = 0;
    if (jSeek(txt, p, "states"))
    {
        while (jSeek(txt, p, "name"))
        {
            S s;
            s.name = U8(jStr(txt, p).c_str());
            size_t q = p;
            if (jSeek(txt, q, "share")) { s.share = jNum(txt, q); p = q; }
            q = p;
            if (jSeek(txt, q, "max"))   { s.tmax  = jNum(txt, q); p = q; }
            q = p;
            if (jSeek(txt, q, "min"))   { s.tmin  = jNum(txt, q); p = q; }
            st.push_back(s);
        }
    }
    if (st.empty())
    {
        AfxMessageBox("op_states.json 에서 상태를 읽지 못했습니다.");
        return false;
    }

    std::vector<int> order(st.size());
    for (size_t i = 0; i < order.size(); ++i) order[i] = (int)i;
    std::stable_sort(order.begin(), order.end(), [&](int a, int b) {
        return st[a].share > st[b].share; });

    std::vector<CDlg_OpNames::Row> rows;
    for (size_t k = 0; k < order.size(); ++k)
    {
        const int i = order[k];
        CDlg_OpNames::Row r;
        r.name = st[i].name;
        r.hint.Format("%.1f%%  ·  최고 %.0f도 · 최저 %.0f도",
                      st[i].share, st[i].tmax, st[i].tmin);
        r.color = ColorOf(i, (int)st.size());
        r.idx = i;
        rows.push_back(r);
    }

    // "20260702 ~ 20260930" -> 날짜와 달력 일수.
    CStringA line;
    {
        int y1, m1, d1, y2, m2, d2;
        if (sscanf_s(period.c_str(), "%4d%2d%2d ~ %4d%2d%2d",
                     &y1, &m1, &d1, &y2, &m2, &d2) == 6)
        {
            const CTime a(y1, m1, d1, 0, 0, 0), b(y2, m2, d2, 0, 0, 0);
            const long days = (long)((b - a).GetDays()) + 1;
            line.Format("운전 기간  %04d-%02d-%02d ~ %04d-%02d-%02d  "
                        "(%ld일 · %ld프레임 · 분류표를 만들 때)",
                        y1, m1, d1, y2, m2, d2, days, frames);
        }
        else
            line.Format("운전 기간  %s  (%ld프레임 · 분류표를 만들 때)",
                        period.empty() ? "모름" : period.c_str(), frames);
    }

    CDlg_OpNames dlg(rows, line, font, hintFont, parent);
    if (dlg.DoModal() != IDOK) return false;

    const std::vector<CStringA>& shown = dlg.Names();
    if (shown.size() != st.size()) return false;
    std::vector<CStringA> names(st.size());
    for (size_t k = 0; k < shown.size(); ++k) names[rows[k].idx] = shown[k];

    CStringA err;
    if (!SaveOpStateNames(names, err))
    {
        AfxMessageBox("이름을 저장하지 못했습니다.\r\n\r\n" + err, MB_ICONERROR);
        return false;
    }
    return true;
}

void CDlg_OpState::OnSelchangeRange() { Load(); }
void CDlg_OpState::OnBnClickedReload() { ShowNow(); Load(); }

// 달력을 직접 건드렸다. 콤보를 '직접 지정' 으로 넘기고 다시 읽는다.
void CDlg_OpState::OnDateChanged(NMHDR* /*pNMHDR*/, LRESULT* pResult)
{
    if (pResult) *pResult = 0;
    if (m_syncing) return;             // 콤보가 맞추는 중이면 내 일이 아니다

    m_cboRange.SetCurSel(RANGE_PICK);
    Load();
}

void CDlg_OpState::SetPickers(const std::string& from, const std::string& to)
{
    if (from.size() != 8 || to.size() != 8) return;
    if (!m_dtFrom.GetSafeHwnd() || !m_dtTo.GetSafeHwnd()) return;

    m_syncing = true;
    m_dtFrom.SetTime(&CTime(atoi(from.substr(0, 4).c_str()),
                            atoi(from.substr(4, 2).c_str()),
                            atoi(from.substr(6, 2).c_str()), 0, 0, 0));
    m_dtTo.SetTime(&CTime(atoi(to.substr(0, 4).c_str()),
                          atoi(to.substr(4, 2).c_str()),
                          atoi(to.substr(6, 2).c_str()), 0, 0, 0));
    m_syncing = false;
}

// 지금 무엇을 볼 것인가. YYYYMMDD 두 개. 빈 것은 그쪽 끝을 열어 둔다.
//
// 콤보에서 고르면 달력도 같이 맞춘다 - 두 자리가 서로 다른 기간을
// 가리키면 화면이 무엇을 보여 주는 것인지 알 수 없다.
void CDlg_OpState::RangeNow(std::string* from, std::string* to)
{
    from->clear();
    to->clear();

    const int sel = m_cboRange.GetCurSel();

    if (sel == RANGE_PICK)
    {
        CTime a, b;
        if (m_dtFrom.GetTime(a) != GDT_VALID || m_dtTo.GetTime(b) != GDT_VALID)
            return;
        if (a > b) { const CTime t = a; a = b; b = t; }   // 거꾸로 잡았으면 바꾼다
        *from = (LPCSTR)a.Format("%Y%m%d");
        *to   = (LPCSTR)b.Format("%Y%m%d");
        return;
    }

    if (sel == RANGE_ALL)
        return;                        // 양쪽 다 열어 둔다

    int days = 30;
    if (sel == RANGE_7)  days = 7;
    if (sel == RANGE_90) days = 90;

    const CTime b = CTime::GetCurrentTime();
    const CTime a = b - CTimeSpan(days - 1, 0, 0, 0);
    *from = (LPCSTR)a.Format("%Y%m%d");
    *to   = (LPCSTR)b.Format("%Y%m%d");
    SetPickers(*from, *to);
}

//---------------------------------------------------------
// DB 를 훑어 시간마다 어느 상태였는지 센다
//
// 어느 중심에 가까운지는 SQL 이 가린다. 프레임마다 중심까지의 제곱거리를
// 내고 그중 가장 작은 것을 고르는 셈이라, 여기서 할 일과 똑같은 것을
// DB 가 대신하는 것뿐이다. 그래야 수만 행을 끌어오지 않는다.
//---------------------------------------------------------
void CDlg_OpState::Load()
{
    if (m_loading || m_states.empty()) return;
    m_loading = true;

    m_days.clear();
    m_total = 0;
    m_hoverDay = m_hoverHour = -1;
    for (size_t i = 0; i < m_states.size(); ++i)
    {
        m_states[i].n = 0;
        m_states[i].scoreSum = 0;
        m_states[i].scoreN = 0;
        m_states[i].devSum = 0;
    }

    SetState("읽는 중...");

    std::string dbName;
    MYSQL* conn = connect_history_db(&dbName);
    if (conn == nullptr)
    {
        m_summary = "히스토리 DB 에 접속할 수 없습니다. env.ini 와 "
                    "db_secrets.ini 를 확인하십시오.";
        SetState(m_summary);
        m_cards.Invalidate();
        m_grid.Invalidate();
        m_loading = false;
        return;
    }

    // 1) 기간 안의 날짜 테이블
    //
    // 개수로 자르면 빈 날이 있는 현장에서 엉뚱하게 멀리 간다. 날짜로 자른다.
    // 이름이 자리수가 고정이라 글자 비교로도 날짜 비교가 된다.
    std::string cutFrom, cutTo;
    RangeNow(&cutFrom, &cutTo);

    std::vector<std::string> tables;
    {
        std::string sql =
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='" + dbName + "' "
            "AND table_name LIKE 'results_history_%' "
            "AND table_type='BASE TABLE' ";

        if (!cutFrom.empty())
            sql += "AND table_name >= 'results_history_" + cutFrom + "' ";
        if (!cutTo.empty())
            sql += "AND table_name <= 'results_history_" + cutTo + "' ";

        sql += "ORDER BY table_name ASC";

        if (mysql_query(conn, sql.c_str()) == 0)
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
        m_summary = "그 기간에 히스토리 테이블이 없습니다. 기간을 늘려 "
                    "보십시오.";
        SetState(m_summary);
        m_cards.Invalidate();
        m_grid.Invalidate();
        m_loading = false;
        return;
    }

    // 2) 질의를 미리 짠다. 테이블마다 이름만 갈아 끼운다.
    //
    // JSON_TABLE 로 마스크 칸만 뽑아 열로 세우고, 중심까지의 제곱거리를
    // 상태 수만큼 낸다. 바깥에서 그중 가장 작은 것을 골라 시간별로 센다.
    std::string cols;
    for (size_t c = 0; c < m_cells.size(); ++c)
    {
        if (!cols.empty()) cols += ", ";
        cols += "c" + Int((long)c) + " DOUBLE PATH '$[" + Int(m_cells[c]) + "]'";
    }

    std::string dist;
    for (size_t k = 0; k < m_states.size(); ++k)
    {
        dist += ", ";
        for (size_t c = 0; c < m_cells.size(); ++c)
        {
            if (c) dist += "+";
            dist += "POW(j.c" + Int((long)c) + "-"
                  + Num(m_states[k].center[c], 2) + ",2)";
        }
        dist += " d" + Int((long)k);
    }

    std::string least = "LEAST(";
    for (size_t k = 0; k < m_states.size(); ++k)
    {
        if (k) least += ",";
        least += "d" + Int((long)k);
    }
    least += ")";
    if (m_states.size() == 1) least = "d0";

    std::string pick;
    if (m_states.size() == 1)
    {
        pick = "0";
    }
    else
    {
        pick = "CASE " + least;
        for (size_t k = 0; k < m_states.size(); ++k)
            pick += " WHEN d" + Int((long)k) + " THEN " + Int((long)k);
        pick += " END";
    }

    // 고른 중심까지 얼마나 멀었나. 칸당 도로 고쳐야 사람이 읽는다.
    const std::string devCol =
        "AVG(SQRT(" + least + "/" + Int((long)m_cells.size()) + "))";

    // 시각 -> 그 시각에 상태별로 몇 건이었나. 가장 많은 것을 그 시간의
    // 상태로 삼는다. 평균을 내어 칠하지 않는다 - 정지와 전부하가 반씩
    // 섞인 시간의 평균은 어느 쪽도 아닌 엉뚱한 상태가 된다.
    std::map<std::string, Day> byDay;
    std::map<std::string, std::vector<long> > best;

    for (size_t i = 0; i < tables.size(); ++i)
    {
        const std::string sql =
            "SELECT h, " + pick + " st, COUNT(*) c, "
            "SUM(CASE WHEN m>=0 THEN m ELSE 0 END) ss, "
            "SUM(CASE WHEN m>=0 THEN 1 ELSE 0 END) sn, " + devCol + " dv FROM ("
            "SELECT DATE_FORMAT(t.`time`,'%Y%m%d%H') h, t.mscore m" + dist +
            " FROM `" + dbName + "`.`" + tables[i] + "` t, "
            "JSON_TABLE(t.hot_list,'$' COLUMNS(" + cols + ")) j"
            ") x GROUP BY h, st ORDER BY h, st";

        if (mysql_query(conn, sql.c_str()) != 0) continue;

        MYSQL_RES* res = mysql_store_result(conn);
        if (res == nullptr) continue;

        while (MYSQL_ROW row = mysql_fetch_row(res))
        {
            if (!row[0] || !row[1] || !row[2]) continue;
            if (strlen(row[0]) < 10) continue;

            const std::string ymd(row[0], row[0] + 8);
            const int hh = atoi(row[0] + 8);
            const int st = atoi(row[1]);
            const long c = atol(row[2]);
            if (hh < 0 || hh > 23) continue;
            if (st < 0 || st >= (int)m_states.size()) continue;

            std::map<std::string, Day>::iterator it = byDay.find(ymd);
            if (it == byDay.end())
            {
                Day d;
                d.ymd = ymd;
                for (int k = 0; k < 24; ++k)
                {
                    d.st[k] = -1;
                    d.n[k] = 0;
                    d.dev[k] = 0.0;
                }
                it = byDay.insert(std::make_pair(ymd, d)).first;
                best[ymd].assign(24, 0);
            }

            const double dv = row[5] ? atof(row[5]) : 0.0;

            Day& d = it->second;
            d.dev[hh] += dv * c;       // 뒤에서 그 시간의 건수로 나눈다
            d.n[hh] += c;
            std::vector<long>& b = best[ymd];
            if (c > b[hh]) { b[hh] = c; d.st[hh] = st; }

            m_total += c;
            m_states[st].n += c;
            m_states[st].devSum += dv * c;
            if (row[3] && row[4])
            {
                m_states[st].scoreSum += atof(row[3]);
                m_states[st].scoreN   += atol(row[4]);
            }
        }
        mysql_free_result(res);
    }

    mysql_close(conn);

    for (std::map<std::string, Day>::const_iterator it = byDay.begin();
         it != byDay.end(); ++it)
    {
        Day d = it->second;
        for (int k = 0; k < 24; ++k)
            if (d.n[k] > 0) d.dev[k] /= d.n[k];
        m_days.push_back(d);
    }

    if (m_days.empty())
    {
        m_summary = "그 기간에 읽을 프레임이 없습니다. 기간을 늘려 보십시오.";
    }
    else
    {
        // '전체' 로 읽었으면 달력에 실제로 자료가 있는 양 끝을 채운다.
        // 그래야 거기서 조금씩 좁혀 볼 수 있다.
        if (m_cboRange.GetCurSel() == RANGE_ALL)
            SetPickers(m_days.front().ymd, m_days.back().ymd);

        // 낯선 시간이 몇 칸인가. 띠에서 세지 않아도 되게 숫자로 적는다.
        int odd = 0, have = 0;
        for (size_t i = 0; i < m_days.size(); ++i)
            for (int h = 0; h < 24; ++h)
            {
                const int s = m_days[i].st[h];
                if (s < 0) continue;
                ++have;
                if (m_states[s].farLine > 0
                    && m_days[i].dev[h] > m_states[s].farLine) ++odd;
            }

        m_summary.Format("%s ~ %s  ·  %u일  ·  %ld프레임  ·  낯선 시간 "
                         "%d / %d  ·  칸에 마우스를 올리면 그 시간이 나옵니다",
                         m_days.front().ymd.c_str(), m_days.back().ymd.c_str(),
                         (unsigned)m_days.size(), m_total, odd, have);
    }
    SetState(m_summary);

    m_cards.Invalidate();
    m_grid.Invalidate();
    m_loading = false;
}

//---------------------------------------------------------
// 상태 카드
//
// 상태마다 한 장. 비율을 가장 크게 적는다 - 이 창에서 먼저 답해야 하는
// 물음이 "요즘 주로 어느 상태인가" 이기 때문이다. 온도 세 줄은 그 상태가
// 어떻게 생긴 것인지를 말한다.
//---------------------------------------------------------
void CDlg_OpState::DrawCards(CDC* pDC, const CRect& rc)
{
    pDC->FillSolidRect(rc, PANEL_BG);

    const int n = (int)m_states.size();
    if (n <= 0) return;

    const int gap = 8;
    const int cw = (rc.Width() - gap * (n - 1)) / n;
    if (cw < 60) return;

    CPen penLine(PS_SOLID, 1, LINE_COLOR);
    CPen* old = pDC->SelectObject(&penLine);

    for (int i = 0; i < n; ++i)
    {
        const State& s = m_states[i];
        CRect card(rc.left + i * (cw + gap), rc.top, 0, rc.bottom);
        card.right = card.left + cw;

        pDC->FillSolidRect(card, PANEL_BG);
        pDC->MoveTo(card.left, card.top);
        pDC->LineTo(card.right - 1, card.top);
        pDC->LineTo(card.right - 1, card.bottom - 1);
        pDC->LineTo(card.left, card.bottom - 1);
        pDC->LineTo(card.left, card.top);

        // 색 띠. 띠 색이 아래 날짜 띠의 칸 색과 같아서 둘이 이어진다.
        pDC->FillSolidRect(CRect(card.left, card.top, card.right, card.top + 5),
            ColorOf(i, n));

        const int lx = card.left + 10;
        const int rx = card.right - 10;
        int y = card.top + 12;

        pDC->SetBkMode(TRANSPARENT);
        pDC->SelectObject(&m_fontBig);
        pDC->SetTextColor(TEXT_COLOR);
        pDC->TextOutA(lx, y, s.name);
        y += 28;

        // 비율. 이 기간에 이 상태였던 프레임의 몫이다.
        CStringA pct;
        if (m_total > 0) pct.Format("%.1f", 100.0 * s.n / m_total);
        else             pct = "-";

        pDC->SelectObject(&m_fontNum);
        pDC->TextOutA(lx, y, pct);
        CSize sz = pDC->GetTextExtent(pct);

        pDC->SelectObject(&m_fontSmall);
        pDC->SetTextColor(MUTED_COLOR);
        pDC->TextOutA(lx + sz.cx + 3, y + sz.cy - 20, "%");
        y += sz.cy + 8;

        struct { const char* k; CStringA v; bool warn; } rows[5];
        for (int r = 0; r < 5; ++r) rows[r].warn = false;

        rows[0].k = "최고";   rows[0].v.Format("%.0f도", s.tmax);
        rows[1].k = "최저";   rows[1].v.Format("%.0f도", s.tmin);
        rows[2].k = "벌어짐"; rows[2].v.Format("%.0f도", s.spread);
        rows[3].k = "점수";
        if (s.scoreN > 0) rows[3].v.Format("%.3f", s.scoreSum / s.scoreN);
        else              rows[3].v = "-";

        // 벗어남. 이 기간 실제로 중심에서 얼마나 멀었나 / 평소 그만큼.
        //
        // 이름은 가장 가까운 중심에 무조건 붙으므로, 이 줄이 없으면
        // 닮지도 않은 프레임이 그 상태였던 것처럼 보인다.
        rows[4].k = "벗어남";
        if (s.n > 0 && s.dev > 0)
        {
            const double d = s.devSum / s.n;
            rows[4].v.Format("%.1f / %.1f도", d, s.dev);
            rows[4].warn = (s.farLine > 0 && d > s.farLine);
        }
        else if (s.n > 0)
        {
            rows[4].v.Format("%.1f도", s.devSum / s.n);
        }
        else
        {
            rows[4].v = "-";
        }

        for (int r = 0; r < 5; ++r)
        {
            pDC->SetTextColor(MUTED_COLOR);
            pDC->TextOutA(lx, y, rows[r].k);

            pDC->SetTextColor(rows[r].warn ? ACCENT : TEXT_COLOR);
            const CSize v = pDC->GetTextExtent(rows[r].v);
            pDC->TextOutA(rx - v.cx, y, rows[r].v);

            y += 19;
            if (r < 4)
            {
                pDC->MoveTo(lx, y - 3);
                pDC->LineTo(rx, y - 3);
            }
        }
    }

    pDC->SelectObject(old);
}

//---------------------------------------------------------
// 날짜x시각 띠
//
// 한 칸이 한 시간이고, 그 시간에 가장 많았던 상태로 칠한다. 자리가
// 모자라면 칸 높이를 줄이고, 그래도 모자라면 최근 날부터 들어가는
// 만큼만 그린다 - 오래된 쪽을 자르는 것이 보던 자리를 지키기 쉽다.
//---------------------------------------------------------
void CDlg_OpState::DrawGrid(CDC* pDC, const CRect& rc)
{
    pDC->FillSolidRect(rc, PANEL_BG);

    CPen penLine(PS_SOLID, 1, LINE_COLOR);
    CPen* old = pDC->SelectObject(&penLine);
    pDC->MoveTo(rc.left, rc.top);
    pDC->LineTo(rc.right - 1, rc.top);
    pDC->LineTo(rc.right - 1, rc.bottom - 1);
    pDC->LineTo(rc.left, rc.bottom - 1);
    pDC->LineTo(rc.left, rc.top);

    pDC->SetBkMode(TRANSPARENT);
    pDC->SelectObject(&m_fontSmall);

    const int pad = 10, labelW = 52, headH = 18, legendH = 26;
    const int x0 = rc.left + pad + labelW;
    const int y0 = rc.top + pad + headH;

    int cw = (rc.Width() - pad * 2 - labelW) / 24;
    if (cw > 34) cw = 34;
    if (cw < 8)  cw = 8;

    const int availH = rc.bottom - pad - legendH - y0;
    const int rows = (int)m_days.size();

    int rh = 0, first = 0, shown = 0;
    if (rows > 0 && availH > 8)
    {
        // 칸은 정사각형을 넘지 않는다. 날이 적다고 세로로만 늘리면 띠가
        // 아니라 막대가 되어 하루 안의 오르내림을 읽기 어렵다.
        rh = availH / rows;
        if (rh > cw) rh = cw;
        if (rh < 4)  rh = 4;

        shown = availH / rh;
        if (shown > rows) shown = rows;
        first = rows - shown;
    }

    m_gX0 = x0; m_gY0 = y0; m_gCellW = cw; m_gRowH = rh;
    m_gFirst = first; m_gRows = shown;

    // 시각 눈금. 세 시간마다 하나면 0시와 12시를 눈으로 찾을 수 있다.
    pDC->SetTextColor(MUTED_COLOR);
    for (int h = 0; h < 24; h += 3)
    {
        char b[8];
        sprintf_s(b, sizeof(b), "%d", h);
        pDC->TextOutA(x0 + h * cw, rc.top + pad, b);
    }


    for (int r = 0; r < shown; ++r)
    {
        const Day& d = m_days[first + r];
        const int ry = y0 + r * rh;

        // 날짜. 칸이 낮으면 글자가 겹치므로 며칠에 한 번만 적는다.
        const int every = (rh >= 14) ? 1 : (rh >= 9 ? 2 : (rh >= 6 ? 4 : 7));
        if (r % every == 0 && d.ymd.size() >= 8)
        {
            CStringA lab;
            lab.Format("%c%c-%c%c", d.ymd[4], d.ymd[5], d.ymd[6], d.ymd[7]);
            const CSize sz = pDC->GetTextExtent(lab);
            pDC->SetTextColor(MUTED_COLOR);
            pDC->TextOutA(x0 - 6 - sz.cx, ry + (rh - sz.cy) / 2, lab);
        }

        for (int h = 0; h < 24; ++h)
        {
            CRect cell(x0 + h * cw, ry, x0 + h * cw + cw - 1, ry + rh - 1);
            if (cell.Height() < 2) cell.bottom = cell.top + 2;

            if (d.st[h] < 0)
            {
                pDC->FillSolidRect(cell, RGB(0xFB, 0xF9, 0xF6));
                pDC->Draw3dRect(cell, LINE_COLOR, LINE_COLOR);
                continue;
            }

            const COLORREF bg = ColorOf(d.st[h], (int)m_states.size());
            pDC->FillSolidRect(cell, bg);

            // 낯선 시간에는 빗금을 친다.
            //
            // 이름은 가장 가까운 중심에 무조건 붙으므로, 색만으로는 그
            // 상태를 닮아서 그런 것인지 그나마 가까워서 그런 것인지
            // 갈리지 않는다. 빗금이 쳐진 자리가 곧 처음 보는 모양이다.
            const double lim = m_states[d.st[h]].farLine;
            if (lim > 0 && d.dev[h] > lim)
            {
                CBrush hatch(HS_BDIAGONAL, InkOn(bg));
                const int old = pDC->SetBkMode(TRANSPARENT);
                pDC->FillRect(cell, &hatch);
                pDC->SetBkMode(old);
            }
        }
    }

    // 짚고 있는 칸. 테두리를 두르고 그 옆에 쪽지를 붙인다.
    //
    // 아래줄에도 같은 글이 나가지만, 눈은 커서를 따라가지 화면 맨 밑을
    // 보지 않는다. 짚은 자리에 붙여야 칸과 글이 한눈에 이어진다.
    CRect tip(0, 0, 0, 0);
    CStringA tipText;
    int tipSt = -1;

    if (m_hoverDay >= first && m_hoverDay < first + shown
        && m_hoverHour >= 0 && m_hoverHour < 24)
    {
        CRect cell(x0 + m_hoverHour * cw, y0 + (m_hoverDay - first) * rh,
                   x0 + m_hoverHour * cw + cw - 1,
                   y0 + (m_hoverDay - first) * rh + rh - 1);
        cell.InflateRect(1, 1);
        pDC->Draw3dRect(cell, ACCENT, ACCENT);
        cell.InflateRect(1, 1);
        pDC->Draw3dRect(cell, ACCENT, ACCENT);

        tipText = HoverText();
        tipSt = m_days[m_hoverDay].st[m_hoverHour];

        pDC->SelectObject(&m_fontTip);
        const CSize sz = pDC->GetTextExtent(tipText);
        const int sw = (tipSt >= 0) ? 16 : 0;      // 색 조각 자리
        const int tw = sz.cx + sw + 20;
        const int th = sz.cy + 12;

        // 칸 오른쪽에 붙이되 판을 벗어나면 왼쪽으로 넘긴다.
        int tx = cell.right + 10;
        if (tx + tw > rc.right - pad) tx = cell.left - 10 - tw;
        if (tx < rc.left + pad) tx = rc.left + pad;

        int ty = cell.CenterPoint().y - th / 2;
        if (ty < rc.top + pad) ty = rc.top + pad;
        if (ty + th > rc.bottom - pad) ty = rc.bottom - pad - th;

        tip.SetRect(tx, ty, tx + tw, ty + th);
        pDC->SelectObject(&m_fontSmall);      // 범례는 다시 작은 글씨로
    }

    // 범례
    {
        int lx = rc.left + pad;
        const int ly = rc.bottom - pad - 14;

        for (int i = 0; i < (int)m_states.size(); ++i)
        {
            CRect sw(lx, ly + 2, lx + 12, ly + 14);
            pDC->FillSolidRect(sw, ColorOf(i, (int)m_states.size()));

            pDC->SetTextColor(MUTED_COLOR);
            pDC->TextOutA(lx + 17, ly, m_states[i].name);
            lx += 17 + pDC->GetTextExtent(m_states[i].name).cx + 16;
        }

        CRect sw(lx, ly + 2, lx + 12, ly + 14);
        pDC->Draw3dRect(sw, LINE_COLOR, LINE_COLOR);
        pDC->SetTextColor(MUTED_COLOR);
        pDC->TextOutA(lx + 17, ly, "자료 없음");
        lx += 17 + pDC->GetTextExtent("자료 없음").cx + 16;

        CRect hw(lx, ly + 2, lx + 12, ly + 14);
        pDC->FillSolidRect(hw, ColorOf(1, (int)m_states.size()));
        {
            CBrush hatch(HS_BDIAGONAL, TEXT_COLOR);
            const int old = pDC->SetBkMode(TRANSPARENT);
            pDC->FillRect(hw, &hatch);
            pDC->SetBkMode(old);
        }
        pDC->SetTextColor(MUTED_COLOR);
        pDC->TextOutA(lx + 17, ly, "낯섦 (이름은 붙었으나 어느 상태와도 멀다)");
    }

    if (shown < rows)
    {
        CStringA t;
        t.Format("(자리가 모자라 최근 %d일만 보입니다)", shown);
        pDC->SetTextColor(MUTED_COLOR);
        const CSize sz = pDC->GetTextExtent(t);
        pDC->TextOutA(rc.right - pad - sz.cx, rc.bottom - pad - 14, t);
    }

    // 쪽지는 맨 나중에. 범례든 다른 칸이든 가리고 위에 떠야 한다.
    if (!tip.IsRectEmpty())
    {
        pDC->FillSolidRect(tip, PANEL_BG);
        pDC->Draw3dRect(tip, TEXT_COLOR, TEXT_COLOR);

        int tx = tip.left + 10;
        if (tipSt >= 0)
        {
            CRect sw(tx, tip.top + (tip.Height() - 12) / 2, tx + 12, 0);
            sw.bottom = sw.top + 12;
            pDC->FillSolidRect(sw, ColorOf(tipSt, (int)m_states.size()));
            pDC->Draw3dRect(sw, LINE_COLOR, LINE_COLOR);
            tx += 16;
        }

        pDC->SelectObject(&m_fontTip);
        pDC->SetTextColor(TEXT_COLOR);
        const CSize sz = pDC->GetTextExtent(tipText);
        pDC->TextOutA(tx, tip.top + (tip.Height() - sz.cy) / 2, tipText);
        pDC->SelectObject(&m_fontSmall);
    }

    pDC->SelectObject(old);
}

//---------------------------------------------------------

void CDlg_OpState::OnDrawItem(int nIDCtl, LPDRAWITEMSTRUCT lpDIS)
{
    if ((nIDCtl != ID_CARDS && nIDCtl != ID_GRID) || !lpDIS)
    {
        CDialogEx::OnDrawItem(nIDCtl, lpDIS);
        return;
    }

    CDC* pDC = CDC::FromHandle(lpDIS->hDC);
    const int w = lpDIS->rcItem.right - lpDIS->rcItem.left;
    const int h = lpDIS->rcItem.bottom - lpDIS->rcItem.top;
    if (w <= 40 || h <= 20) return;

    // 메모리에 그려 한 번에 옮긴다. 바로 그리면 다시 그릴 때마다 깜빡인다.
    CDC mem;
    if (!mem.CreateCompatibleDC(pDC)) return;
    CBitmap bmp;
    if (!bmp.CreateCompatibleBitmap(pDC, w, h)) return;
    CBitmap* oldBmp = mem.SelectObject(&bmp);

    const CRect rc(0, 0, w, h);
    if (nIDCtl == ID_CARDS) DrawCards(&mem, rc);
    else                    DrawGrid(&mem, rc);

    pDC->BitBlt(lpDIS->rcItem.left, lpDIS->rcItem.top, w, h, &mem, 0, 0,
        SRCCOPY);
    mem.SelectObject(oldBmp);
}

HBRUSH CDlg_OpState::OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor)
{
    if (nCtlColor == CTLCOLOR_STATIC && pWnd)
    {
        const int id = pWnd->GetDlgCtrlID();
        if (id == ID_CARDS || id == ID_GRID || id == ID_LBL_STATE
            || id == ID_LBL_HEAD || id == ID_LBL_NOW)
        {
            pDC->SetBkMode(TRANSPARENT);
            pDC->SetTextColor(id == ID_LBL_NOW ? ACCENT : TEXT_COLOR);
            return (HBRUSH)m_brWhite.GetSafeHandle();
        }
    }
    return CDialogEx::OnCtlColor(pDC, pWnd, nCtlColor);
}

//---------------------------------------------------------
// 짚기
//
// 정적 컨트롤은 WM_NCHITTEST 에 HTTRANSPARENT 를 돌려주므로 마우스
// 메시지가 부모로 넘어온다. 컨트롤을 따로 서브클래싱하지 않아도 된다.
//---------------------------------------------------------
bool CDlg_OpState::GridCellAt(CPoint pt, int* day, int* hour) const
{
    if (!m_grid.GetSafeHwnd() || m_gCellW <= 0 || m_gRowH <= 0) return false;

    CRect rc;
    m_grid.GetWindowRect(&rc);
    const_cast<CDlg_OpState*>(this)->ScreenToClient(&rc);
    if (!rc.PtInRect(pt)) return false;

    const int x = pt.x - rc.left - m_gX0;
    const int y = pt.y - rc.top - m_gY0;
    if (x < 0 || y < 0) return false;

    const int h = x / m_gCellW;
    const int r = y / m_gRowH;
    if (h < 0 || h > 23 || r < 0 || r >= m_gRows) return false;

    *day = m_gFirst + r;
    *hour = h;
    return true;
}

CStringA CDlg_OpState::HoverText() const
{
    if (m_hoverDay < 0 || m_hoverDay >= (int)m_days.size()) return CStringA();

    const Day& d = m_days[m_hoverDay];
    if (d.ymd.size() < 8) return CStringA();

    CStringA ymd;
    ymd.Format("%c%c%c%c-%c%c-%c%c", d.ymd[0], d.ymd[1], d.ymd[2], d.ymd[3],
        d.ymd[4], d.ymd[5], d.ymd[6], d.ymd[7]);

    CStringA t;
    if (d.st[m_hoverHour] < 0)
    {
        t.Format("%s %02d시  ·  자료 없음", (LPCSTR)ymd, m_hoverHour);
        return t;
    }

    const State& s = m_states[d.st[m_hoverHour]];
    t.Format("%s %02d시  ·  %s  ·  %ld건", (LPCSTR)ymd, m_hoverHour,
        (LPCSTR)s.name, d.n[m_hoverHour]);

    // 얼마나 멀리서 그 이름이 붙었는가.
    if (s.dev > 0)
    {
        CStringA v;
        v.Format("  ·  벗어남 %.1f / 평소 %.1f도",
            d.dev[m_hoverHour], s.dev);
        t += v;
        if (s.farLine > 0 && d.dev[m_hoverHour] > s.farLine) t += "  ·  낯섦";
    }
    return t;
}

void CDlg_OpState::OnMouseMove(UINT nFlags, CPoint point)
{
    int day = -1, hour = -1;
    GridCellAt(point, &day, &hour);

    if (day != m_hoverDay || hour != m_hoverHour)
    {
        m_hoverDay = day;
        m_hoverHour = hour;
        m_grid.Invalidate();

        // 아래줄에도 같은 글을 둔다. 칸을 벗어나면 기간 요약으로 돌아간다.
        SetState(day >= 0 ? (LPCSTR)HoverText() : (LPCSTR)m_summary);
    }

    if (!m_tracking)
    {
        TRACKMOUSEEVENT tme = { sizeof(tme) };
        tme.dwFlags = TME_LEAVE;
        tme.hwndTrack = GetSafeHwnd();
        if (TrackMouseEvent(&tme)) m_tracking = true;
    }

    CDialogEx::OnMouseMove(nFlags, point);
}

void CDlg_OpState::OnMouseLeave()
{
    m_tracking = false;
    if (m_hoverDay >= 0 || m_hoverHour >= 0)
    {
        m_hoverDay = m_hoverHour = -1;
        m_grid.Invalidate();
        SetState(m_summary);
    }
    CDialogEx::OnMouseLeave();
}
