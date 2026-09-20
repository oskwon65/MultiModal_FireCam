#pragma once

// CDlg_Set_MmCam_Env 대화 상자

class CDlg_Set_MmCam_Env : public CDialogEx
{
    DECLARE_DYNAMIC(CDlg_Set_MmCam_Env)

public:
    CDlg_Set_MmCam_Env(CWnd* pParent = nullptr);
    virtual ~CDlg_Set_MmCam_Env();

#ifdef AFX_DESIGN_TIME
    enum { IDD = IDD_DLG_CMD };
#endif

protected:
    virtual void DoDataExchange(CDataExchange* pDX);

    DECLARE_MESSAGE_MAP()

public:
    CButton m_btnClose, m_btnGetMask_Server, m_btnSetMask_CamPos;
    CFont   m_stdFont;
    CStatic m_cap_0;

    virtual BOOL OnInitDialog();
    afx_msg void OnLButtonDown(UINT nFlags, CPoint point);
    afx_msg void OnBnClickedButtonChangeMask();
    afx_msg void OnBnClickedButtonGetMask();
    afx_msg void OnBnClickedClose();
};