#pragma once

#include <vector>

// 두 단계 확인 창
//
// 관제서버 설정 화면의 [칸 수 변경] 창과 같은 모양이다.
//   1단계  제목 · 안내 한 줄 · 노란 경고 상자(굵은 첫 줄 + 항목들) · [취소] [변경]
//   2단계  빨간 상자에 바뀌는 것을 크게("16칸 -> 20칸") · 묻는 말 · [돌아가기] [최종 확인 · 변경]
// [최종 확인 · 변경] 은 2단계가 뜬 뒤 1초 동안 막아, [변경] 을 연달아 눌러 넘어가는 일을
// 막는다. 2단계에서 처음 잡히는 버튼은 [돌아가기] 다. Enter 는 1단계에서 [변경],
// 2단계에서 [돌아가기] 로 동작한다. 창 틀은 .rc 에 두지 않고 여기서 만든다.

struct Confirm2Text
{
    CStringA title;                  // 창 안 제목 (예: "설비 칸 수 변경")
    CStringA info;                   // 1단계 안내 한 줄 (예: "설비 칸 수  16칸 -> 20칸")
    CStringA warnHead;               // 노란 상자 굵은 첫 줄
    std::vector<CStringA> warnItems; // 노란 상자 항목
    CStringA big;                    // 2단계 큰 글자 (예: "16칸 -> 20칸")
    CStringA question;               // 2단계 묻는 말
};

class CDlg_Confirm2 : public CDialogEx
{
public:
    CDlg_Confirm2(CFont* font, CWnd* parent, const Confirm2Text& text);

    // 끝까지 확인하면 true
    static bool Ask(CFont* font, CWnd* parent, const Confirm2Text& text);

protected:
    virtual BOOL OnInitDialog() override;
    virtual void OnOK() override;
    afx_msg void OnPaint();
    afx_msg void OnTimer(UINT_PTR id);
    afx_msg void OnDrawItem(int id, LPDRAWITEMSTRUCT dis);
    afx_msg HBRUSH OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor);
    afx_msg BOOL OnEraseBkgnd(CDC* pDC);
    afx_msg void OnNext();
    afx_msg void OnBack();
    afx_msg void OnApply();
    DECLARE_MESSAGE_MAP()

private:
    std::vector<WORD> m_tpl;
    CFont* m_font;
    CFont  m_fontTitle, m_fontBold, m_fontBig;
    Confirm2Text m_text;
    int    m_step = 1;

    CButton m_btnCancel, m_btnNext, m_btnBack, m_btnApply;
    CRect   m_rcBox;                 // 노란/빨간 상자 자리
    int     m_W = 0, m_H = 0;

    void SetStep(int step);
    int  MeasureWarn(CDC& dc, int width);
};
