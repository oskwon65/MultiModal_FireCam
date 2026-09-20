#pragma once


// CDlg_Set_mm_cam_Env 대화 상자

class CDlg_Set_mm_cam_Env : public CDialogEx
{
	DECLARE_DYNAMIC(CDlg_Set_mm_cam_Env)

public:
	CDlg_Set_mm_cam_Env(CWnd* pParent = nullptr);   // 표준 생성자입니다.
	virtual ~CDlg_Set_mm_cam_Env();

// 대화 상자 데이터입니다.
#ifdef AFX_DESIGN_TIME
	enum { IDD = IDD_DLG_CMD };
#endif

protected:
	virtual void DoDataExchange(CDataExchange* pDX);    // DDX/DDV 지원입니다.

	DECLARE_MESSAGE_MAP()
public:
	CButton m_btnClose, m_btnGetMask_Server, m_btnSetMask_CamPos;
	CFont m_stdFont;

	afx_msg void OnBnClickedButtonDoCmd1();
	afx_msg void OnBnClickedButtonDoCmd2();
	CStatic m_cap_0;
	virtual BOOL OnInitDialog();
	afx_msg void OnLButtonDown(UINT nFlags, CPoint point);
	afx_msg void OnBnClickedButtonChangeMask();
	afx_msg void OnBnClickedButtonGetMask();
	afx_msg void OnBnClickedClose();
};
