
// MmCam_monitoringDlg.h: 헤더 파일
//

#pragma once

#include <vector>
#include <string>

enum
{
	STATUS_OK = 0,      // 정상 (초록)
	STATUS_WARN = 1,    // 경고 (노랑)
	STATUS_ERROR = 2    // 오류 (빨강)
};

// CMmCammonitoringDlg 대화 상자
class CMmCammonitoringDlg : public CDialogEx
{
// 생성입니다.
public:
	CMmCammonitoringDlg(CWnd* pParent = nullptr);	// 표준 생성자입니다.

// 대화 상자 데이터입니다.
#ifdef AFX_DESIGN_TIME
	enum { IDD = IDD_MmCam_MONITORING_DIALOG };
#endif

	protected:
	virtual void DoDataExchange(CDataExchange* pDX);	// DDX/DDV 지원입니다.


// 구현입니다.
protected:
	HICON m_hIcon;

	CButton m_btnStartAll, m_btnKillAll, m_btnCmd, m_btnClose;
	CButton m_btnMinimize;

	CComboBox mComboBox_ID;

	CFont m_stdFont;

	std::vector<CButton*> m_stopButtons;
	std::vector<CStatic*> m_labels;

	CStatic m_lblTitle, m_lblSign, m_lbStatus;
	CStatic m_lblTimer;
	CEdit   m_editRestartMin;   // ★ 재시작 주기 입력 CEdit
	int m_elapsedSeconds;;
	int m_nStatusLevel;

	void SetStatusLevel(int level);
	void OnStopButton(UINT nID);
	bool KillProcess(const char* keyword);
	bool IsProcessRunning(const char* keyword);
	void RefreshButtons();
	void OnBnClickedStartAll();
	void OnBnClickedKillAll();
	void OnBnClickedClose();
	void OnBnClickedCMD();
	void RunCmdWithTitle(const char* title, const char* command);
	UINT GetRestartIntervalMs(bool bSave = FALSE);


	afx_msg HBRUSH OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor);

	afx_msg void OnBnClickedMinimize(); //ON_WM_CTLCOLOR() 에서 호출

	// 생성된 메시지 맵 함수
	virtual BOOL OnInitDialog();
	afx_msg void OnSysCommand(UINT nID, LPARAM lParam);
	afx_msg void OnPaint();
	afx_msg HCURSOR OnQueryDragIcon();
	DECLARE_MESSAGE_MAP()
public:
	afx_msg void OnLButtonDown(UINT nFlags, CPoint point);
	afx_msg void OnTimer(UINT_PTR nIDEvent);
};
