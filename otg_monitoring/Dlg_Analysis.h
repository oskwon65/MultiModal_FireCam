#pragma once

#include <string>
#include <vector>

// 점수 추이 창
//
// 히스토리 DB(results_history_YYYYMMDD)의 mscore 를 시간 단위로 묶어 꺾은선
// 으로 보인다. 지금 점수 하나만 보면 "낮다/높다" 밖에 알 수 없지만, 며칠치를
// 늘어놓으면 서서히 나빠지는 중인지, 어느 시점부터 어긋났는지가 보인다.
//
// [왜 시간 단위인가]
//
// 프레임은 몇 초에 하나씩 쌓여 하루에 수천 건이다. 그대로 찍으면 점이 화면
// 폭보다 많아 선이 뭉개진다. 한 시간으로 묶으면 하루 24점이라 한 달도 한
// 화면에 들어온다.
//
// [평균인가 중앙값인가]
//
// 여기서는 시간별 평균이다. 재학습의 판단 점수는 중앙값을 쓰지만(치우친
// 프레임에 끌려가지 않으려고), 추이를 눈으로 볼 때는 평균이 낫다 - 한두
// 프레임이 튀어도 그 시간대에 무슨 일이 있었다는 것이 선에 남는다.
//
// 산출되지 않은 프레임(mscore < 0)은 뺀다.
//
// [왜 점수와 온도를 한 칸에 겹치지 않는가]
//
// 점수는 0~1, 온도는 20~150도다. 한 칸에 그리면서 오른쪽에 눈금을 하나 더
// 두면(축이 둘인 그림), 어느 선이 어느 눈금인지 읽을 때마다 되짚어야 하고
// 두 선의 기울기를 견줄 수 없다. 축 하나를 어디에 놓느냐로 "같이 움직인다"
// 는 인상을 만들어 낼 수도 있다.
//
// 위아래로 나누고 x 축만 함께 쓴다. 같은 시각이 같은 가로 위치에 오므로
// 눈으로 바로 이어진다.

class CDlg_Analysis : public CDialogEx
{
    DECLARE_DYNAMIC(CDlg_Analysis)

public:
    CDlg_Analysis(CWnd* pParent = nullptr);
    virtual ~CDlg_Analysis();

#ifdef AFX_DESIGN_TIME
    enum { IDD = IDD_DLG_ANALYSIS };
#endif

protected:
    virtual void DoDataExchange(CDataExchange* pDX);
    DECLARE_MESSAGE_MAP()

public:
    virtual BOOL OnInitDialog();
    afx_msg void OnSelchangeRange();
    afx_msg void OnBnClickedReload();
    afx_msg void OnDrawItem(int nIDCtl, LPDRAWITEMSTRUCT lpDIS);
    afx_msg HBRUSH OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor);
    afx_msg void OnMouseMove(UINT nFlags, CPoint point);
    afx_msg void OnMouseLeave();

private:
    // 한 시간 묶음 하나
    struct Point
    {
        std::string hour;    // YYYYMMDDHH
        double      avg;     // 그 시간의 평균 점수
        long        n;       // 센 프레임 수
        double      tmax;    // 마스크 칸의 최고 온도
        double      tavg;    // 마스크 칸의 평균 온도
        bool        hasT;    // 온도를 읽었는가
    };

    CStatic   m_lblHead;
    CStatic   m_chart;       // 꺾은선 (SS_OWNERDRAW)
    CStatic   m_lblState;
    CComboBox m_cboRange;
    CButton   m_btnReload, m_btnClose;
    CFont     m_font, m_fontSmall;
    CBrush    m_brWhite;

    std::vector<Point> m_pts;
    int    m_days = 7;
    bool   m_loading = false;
    double m_tempWarn = 0.0;    // 0단계 주의 임계값 (env.ini)
    double m_tempTop = 100.0;   // 온도 칸의 위 끝

    // 십자선.
    //
    // 두 칸이 x 축을 함께 쓰므로, 한 칸에서 가리킨 시각이 다른 칸에서도
    // 같은 자리다. 선 하나를 두 칸에 걸쳐 그으면 "이 시각의 점수와 온도" 를
    // 눈으로 잇지 않아도 된다.
    int  m_hover = -1;          // 가리키는 시간 묶음 (-1 이면 없음)
    bool m_tracking = false;    // WM_MOUSELEAVE 를 받으려고 걸어 둔 상태

    void Load();                      // DB 에서 다시 읽는다
    std::string MaskCellList() const; // 마스크 칸 번호를 SQL 용으로
    void SetState(const char* text);
    int  DaysFromCombo() const;
};
