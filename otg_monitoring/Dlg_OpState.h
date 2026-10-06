#pragma once

#include <afxdtctl.h>   // CDateTimeCtrl
#include <string>
#include <vector>

// 운전 상태 관찰 창
//
// 지금 설비가 어떤 상황인지를 이름으로 부르고, 그 이름이 지난 며칠 동안
// 어떻게 오갔는지를 한 화면에 늘어놓는다.
//
// [단계와 무엇이 다른가]
//
// 1~3단계는 "감시가 어디까지 준비되었는가" 다. 운전 상태는 "설비가 지금
// 무엇을 하고 있는가" 다. 경보에도 학습에도 쓰이지 않는다 - 사람이 화면을
// 보고 상황을 읽으라고 있는 것이다.
//
// [이름은 어디서 오는가]
//
// retrain/make_op_states.py 가 미리 군집을 내어 users/<현장>/op_states.json
// 에 중심을 굳혀 둔다. 여기서는 그 중심만 읽어 쓴다. 창을 열 때마다 군집을
// 다시 내면 같은 프레임이 어제와 오늘 다른 이름을 받아, 화면을 믿을 수
// 없게 된다.
//
// [날짜x시각 띠]
//
// 한 칸이 한 시간이고, 그 시간에 가장 많았던 상태로 칠한다. 평균을 내어
// 칠하지 않는다 - 정지와 전부하가 반씩 섞인 시간의 평균은 어느 쪽도
// 아닌 엉뚱한 상태가 된다.
//
// 상태를 가리는 셈은 DB 에서 한다. 프레임마다 어느 중심에 가까운지를
// SQL 이 세어 시간별 개수로 돌려주므로, 수만 행을 여기로 끌어오지 않는다.

class CDlg_OpState : public CDialogEx
{
    DECLARE_DYNAMIC(CDlg_OpState)

public:
    CDlg_OpState(CWnd* pParent = nullptr);
    virtual ~CDlg_OpState();

#ifdef AFX_DESIGN_TIME
    enum { IDD = IDD_DLG_OPSTATE };
#endif

protected:
    virtual void DoDataExchange(CDataExchange* pDX);
    DECLARE_MESSAGE_MAP()

public:
    virtual BOOL OnInitDialog();
    afx_msg void OnSelchangeRange();
    afx_msg void OnBnClickedReload();
    afx_msg void OnDateChanged(NMHDR* pNMHDR, LRESULT* pResult);
    afx_msg void OnDrawItem(int nIDCtl, LPDRAWITEMSTRUCT lpDIS);
    afx_msg HBRUSH OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor);
    afx_msg void OnMouseMove(UINT nFlags, CPoint point);
    afx_msg void OnMouseLeave();

private:
    // 상태 하나. 이름과 중심은 파일에서, 비율과 점수는 DB 에서 온다.
    struct State
    {
        CStringA            name;
        std::vector<double> center;   // 마스크 칸 수만큼
        double tmax = 0, tmin = 0, spread = 0;   // 중심이 그리는 온도 모양

        // 평소 이만큼은 중심에서 벗어난다(칸당 도)와, 넘으면 낯선 선.
        // 분류표에 적혀 온다. 옛 파일이면 0 이고, 그때는 낯섦을 말하지 않는다.
        double dev = 0, farLine = 0;

        long   n = 0;          // 이 기간에 이 상태였던 프레임
        double scoreSum = 0;   // 점수 평균을 내려고 들고 있는다
        long   scoreN = 0;
        double devSum = 0;     // 이 기간 실제 벗어남의 평균을 내려고
    };

    // 하루. 24칸 각각에 그 시간 가장 많았던 상태와 프레임 수.
    struct Day
    {
        std::string ymd;       // YYYYMMDD
        int    st[24];         // -1 이면 자료 없음
        long   n[24];
        double dev[24];        // 그 시간 중심에서 벗어난 정도 (칸당 도)
    };

    CStatic   m_lblHead, m_lblNow, m_cards, m_grid, m_lblState;
    CComboBox m_cboRange;

    // 기간. 흔한 것은 콤보에서 고르고, 그 밖은 달력에서 직접 잡는다.
    //
    // 달력을 직접 건드리면 콤보가 '직접 지정' 으로 넘어간다. 두 자리가
    // 서로 다른 기간을 가리키고 있으면 화면이 무엇을 보여 주는 것인지
    // 알 수 없다.
    CDateTimeCtrl m_dtFrom, m_dtTo;
    CStatic   m_capFrom, m_capTo;

    CButton   m_btnReload, m_btnClose;
    CFont     m_font, m_fontSmall, m_fontBig, m_fontNum;

    // 짚은 칸 옆에 뜨는 쪽지 전용. 눈금(m_fontSmall)보다 25% 크다 - 눈금은
    // 그림을 읽는 보조지만 이 쪽지는 지금 짚은 값 그 자체다.
    CFont     m_fontTip;
    CBrush    m_brWhite;

    std::vector<int>    m_cells;    // 점수가 보는 칸 번호 (0부터)
    std::vector<State>  m_states;
    std::vector<Day>    m_days;
    CStringA            m_period;   // op_states.json 을 만든 기간
    CStringA            m_madeInfo;
    CStringA            m_summary;  // 칸을 짚지 않을 때 아래줄에 둘 글
    long                m_total = 0;

    bool m_loading = false;
    bool m_syncing = false;   // 콤보가 달력을 맞추는 중 (되울림 막기)
    bool m_tracking = false;
    int  m_hoverDay = -1;           // 짚고 있는 칸
    int  m_hoverHour = -1;

    // 그리는 쪽과 짚는 쪽이 같은 자리를 봐야 한다. 그릴 때 적어 둔다.
    int m_gX0 = 0, m_gY0 = 0, m_gCellW = 0, m_gRowH = 0, m_gFirst = 0,
        m_gRows = 0;

    bool LoadStates();              // op_states.json
    void Load();                    // DB 를 훑는다
    void ShowNow();                 // stage_status.ini 의 지금 상태
    void SetState(const char* text);
    CStringA HoverText() const;

    // 지금 무엇을 볼 것인가. 빈 문자열이면 그쪽 끝은 제한하지 않는다.
    void RangeNow(std::string* from, std::string* to);
    void SetPickers(const std::string& from, const std::string& to);

    void DrawCards(CDC* pDC, const CRect& rc);
    void DrawGrid(CDC* pDC, const CRect& rc);
    bool GridCellAt(CPoint pt, int* day, int* hour) const;
};
