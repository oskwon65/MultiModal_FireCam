#pragma once

#include <atlimage.h>
#include <string>
#include <vector>

// RGB 기준 이미지 창
//
// 기준 이미지(base_img/base_ref.png)와 지금 RGB 화면을 나란히 놓고, 둘을 견준
// 이동량과 일치도를 보인 뒤 사람이 확인하고서만 기준을 바꾼다.
//
// [왜 필요한가]
//
// 기준 이미지는 RGB 틀어짐을 재는 잣대다. 예전에는 이동보정을 승인하면 그 뒤
// 감시를 처음 켤 때 찍힌 프레임 하나가 그대로 기준이 되었다. 밤이거나 무엇이
// 가렸거나 이미 틀어진 화면이어도 걸러지지 않았다.
//
// [어떻게 찍고 재는가]
//
// retrain/base_ref_tool.py capture 를 돌린다. 감시가 기동할 때와 같은 위상
// 상관으로 재서 base_img/_candidate.png · _candidate.ini 로 남긴다. 여기서는
// 그 둘을 읽기만 한다.
//
// [알맞은가]
//
// 밝기 · 대비 · 선명도 · 어두운/밝은 곳 · 같은 장면 · 밀림을 조건과 함께 표로 보인다.
// 화질 적합도(밝기 · 대비 · 선명도 · 어두운/밝은 곳)를 하나라도 못 맞추면 교체를 막는다.
// 틀어짐 기준(같은 장면 · 밀림)을 못 맞추면 막지 않고 카메라 자리가 바뀐 것으로 다룬다.
//
// [바꾸면]
//
// 쓰던 기준은 base_img/unused/base_ref_<시각>.png 로 옮겨 둔다. 마스크는 옮기지
// 않는다. 새 기준은 감시를 다시 시작할 때부터 쓰인다.

class CDlg_BaseRef : public CDialogEx
{
public:
    CDlg_BaseRef(CFont* font, CWnd* parent);

protected:
    virtual BOOL OnInitDialog() override;
    afx_msg void OnDrawItem(int nIDCtl, LPDRAWITEMSTRUCT lpDIS);
    afx_msg void OnCapture();
    afx_msg void OnReplace();
    afx_msg LRESULT OnAutoCapture(WPARAM, LPARAM);
    afx_msg void OnCustomDrawChecks(NMHDR* pNMHDR, LRESULT* pResult);
    DECLARE_MESSAGE_MAP()

private:
    std::vector<WORD> m_tpl;
    CFont* m_font;
    CFont  m_fontBig;

    CStatic m_lblHead, m_capRef, m_capCur, m_picRef, m_picCur, m_lblResult;
    CButton m_btnCapture, m_btnReplace, m_btnClose;
    // 조건별 판정을 두 표로 나눈다. 다루는 법이 달라서다.
    //   화질 적합도  하나라도 부적합이면 기준으로 쓸 수 없다 - 교체를 막는다
    //   틀어짐 기준  부적합이면 카메라 자리가 바뀐 것으로 보고 2·3단계를 내린다
    CStatic   m_capQ, m_capS;
    CListCtrl m_lstQ, m_lstS;

    CImage  m_imgRef, m_imgCur;
    std::vector<int> m_mask;       // 점수가 보는 칸 (X_GRID x Y_GRID)
    int     m_gx = 8, m_gy = 8;

    // 지난 측정
    bool    m_haveCur = false, m_haveRef = false;
    double  m_dx = 0, m_dy = 0, m_resp = 0, m_respMin = 0.30;
    int     m_cellX = 0, m_cellY = 0;
    CStringA m_curAt, m_refAt, m_msg;
    int     m_mean = -1, m_refMean = -1;

    // 조건별 판정. 조건과 판정은 base_ref_tool.py 가 정한다 - 여기서는 읽기만 한다.
    struct Check { CStringA name, rule, ref, cur; bool ok; };
    std::vector<Check> m_chkQ, m_chkS;   // 화질 적합도 · 틀어짐 기준
    bool    m_qualityOk = false;          // 화질 적합도를 모두 맞추는가
    CStringA m_relocated;          // 2·3단계를 내렸으면 그 내역 (relocate 결과)

    std::string BaseDir() const;
    void LoadMask();
    void LoadImages();
    void ReadResult();
    void ShowResult();
    void DrawPic(CDC* dc, const CRect& rc, CImage& img, const char* empty);
};
