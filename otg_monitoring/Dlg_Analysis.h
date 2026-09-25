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

private:
    // 한 시간 묶음 하나
    struct Point
    {
        std::string hour;    // YYYYMMDDHH
        double      avg;     // 그 시간의 평균 점수
        long        n;       // 센 프레임 수
    };

    CStatic   m_lblHead;
    CStatic   m_chart;       // 꺾은선 (SS_OWNERDRAW)
    CStatic   m_lblState;
    CComboBox m_cboRange;
    CButton   m_btnReload, m_btnClose;
    CFont     m_font, m_fontSmall;
    CBrush    m_brWhite;

    std::vector<Point> m_pts;
    int  m_days = 7;
    bool m_loading = false;

    void Load();                      // DB 에서 다시 읽는다
    void SetState(const char* text);
    int  DaysFromCombo() const;
};
