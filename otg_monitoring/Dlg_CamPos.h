#pragma once

// 카메라 이동보정 확인 창
//
// [설정] 영역의 "카메라 이동보정" 버튼을 누르면 뜬다.
//
// 예전에는 버튼을 누르는 즉시 DB 에 ADJST-MG 명령을 넣었다. 되돌릴 방법이
// 없고, 무엇이 일어나는지도 알 수 없었다. 체크박스 하나를 놓고 켤지 끌지
// 고르게 한다. 체크를 풀고 확인하면 이미 넣어 둔 명령을 거둔다.
class CDlg_CamPos : public CDialogEx
{
    DECLARE_DYNAMIC(CDlg_CamPos)

public:
    CDlg_CamPos(CWnd* pParent = nullptr);
    virtual ~CDlg_CamPos();

    enum { IDD = IDD_DLG_CAMPOS };

    // 들어올 때는 초기 상태, 나갈 때는 사용자가 고른 값.
    BOOL m_bAdjust = FALSE;

protected:
    virtual void DoDataExchange(CDataExchange* pDX);
    virtual BOOL OnInitDialog();
    virtual void OnOK();

    CFont   m_font;
    CButton m_chk;

    DECLARE_MESSAGE_MAP()
};
