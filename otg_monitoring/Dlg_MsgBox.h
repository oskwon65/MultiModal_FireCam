#pragma once

#include <memory>
#include <vector>

// 알림창 (Windows 기본 메시지 상자 대신)
//
// 기본 메시지 상자는 시스템 글꼴 크기로만 그려져, 설정 영역 글꼴(UI_FONT_NAME ·
// UI_FONT_SIZE)과 크기가 달랐다. 이 창은 같은 글꼴로 그린다.
//
// AfxMessageBox 는 앱의 DoMessageBox 를 거치므로 CMmCammonitoringApp::DoMessageBox 가
// 여기로 돌린다 - 앱 안의 AfxMessageBox 는 모두 이 창이 된다. CWnd::MessageBox 처럼
// 직접 부르는 곳은 KictMessageBox 를 쓴다.
//
// 지원: MB_OK · MB_OKCANCEL · MB_YESNO · MB_YESNOCANCEL · MB_RETRYCANCEL,
//       MB_ICONERROR/WARNING/INFORMATION/QUESTION, MB_DEFBUTTON1~3.
// 돌려주는 값은 기본 메시지 상자와 같다 (IDOK · IDYES · IDNO · IDCANCEL · IDRETRY).

int KictMessageBox(CWnd* owner, LPCSTR text, LPCSTR caption, UINT type);

class CDlg_MsgBox : public CDialogEx
{
public:
    CDlg_MsgBox(CWnd* owner, LPCSTR text, LPCSTR caption, UINT type);

protected:
    virtual BOOL OnInitDialog() override;
    virtual void OnOK() override;
    virtual void OnCancel() override;
    virtual BOOL OnCommand(WPARAM wParam, LPARAM lParam) override;
    afx_msg void OnPaint();
    afx_msg BOOL OnEraseBkgnd(CDC* pDC);
    afx_msg HBRUSH OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor);
    DECLARE_MESSAGE_MAP()

private:
    std::vector<WORD> m_tpl;
    CStringA m_text, m_caption;
    UINT     m_type;
    CFont    m_font;
    HICON    m_icon = nullptr;
    CRect    m_rcText;
    int      m_barTop = 0;

    struct Btn { int id; const char* label; };
    std::vector<Btn> m_btns;
    std::vector<std::unique_ptr<CButton>> m_wnds;   // 창이 닫힐 때 함께 정리
    int      m_escId = IDCANCEL;
};
