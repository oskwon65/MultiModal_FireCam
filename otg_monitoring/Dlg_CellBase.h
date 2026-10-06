#pragma once

#include <string>
#include <vector>

// 경험 임계값 창
//
// 지금 각 칸이 몇 도이고, 그 칸의 평소 선이 몇 도이며, 얼마나 떨어져
// 있는지를 8x8 격자 그대로 보인다.
//
// [왜 따로 창이 필요한가]
//
// 2단계 점수는 마스크 칸 중 가장 많이 넘은 칸 하나만 돌려준다. 나머지
// 칸이 선에서 얼마나 떨어져 있는지는 계산해 놓고 버렸다. 그래서 "37번이
// 70도" 라는 것을 알아도 그게 이 칸에 높은 것인지 낮은 것인지 알 수
// 없었다. 모델이 어느 칸을 못 배웠는지 찾을 때 이 차이가 필요했다.
//
// [점수 추이 창과 무엇이 다른가]
//
// 저쪽 격자는 DB 에 적힌 온도다. 평소 선이 없으므로 높은지 낮은지 판단할
// 수 없다. 이쪽은 선과 지금 값을 나란히 둔다.
//
// [읽기만 한다]
//
// 감시가 stage_status.ini 에 적어 둔 세 줄(CELL_NOW · CELL_HI ·
// CELL_MASK)을 읽는다. 여기서 다시 재지 않는다.

class CDlg_CellBase : public CDialogEx
{
    DECLARE_DYNAMIC(CDlg_CellBase)

public:
    CDlg_CellBase(CWnd* pParent = nullptr);
    virtual ~CDlg_CellBase();

#ifdef AFX_DESIGN_TIME
    enum { IDD = IDD_DLG_CELLBASE };
#endif

protected:
    virtual void DoDataExchange(CDataExchange* pDX);
    DECLARE_MESSAGE_MAP()

public:
    virtual BOOL OnInitDialog();
    afx_msg void OnTimer(UINT_PTR nIDEvent);
    afx_msg void OnDrawItem(int nIDCtl, LPDRAWITEMSTRUCT lpDIS);
    afx_msg HBRUSH OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor);

private:
    CStatic m_lblHead, m_grid, m_lblState;
    CButton m_btnClose;
    CFont   m_font, m_fontSmall, m_fontBig;
    // 칸 안에 쓰는 글씨. 칸이 작아 따로 둔다.
    CFont   m_fontCell, m_fontTiny;
    CBrush  m_brWhite;

    std::vector<double> m_now;    // 지금 온도 64
    std::vector<double> m_hi;     // 경험 임계값 64
    std::vector<int>    m_mask;   // 점수가 보는 칸 64
    bool     m_ready = false;     // 2단계가 섰는가
    CStringA m_why;               // 못 읽을 때의 사유

    void Load();
    void DrawGrid(CDC* pDC, const CRect& rc);
};
