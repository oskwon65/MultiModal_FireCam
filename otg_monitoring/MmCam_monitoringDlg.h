
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

// CountPythonProcesses()가 스캔할 때마다 찾아낸 python.exe 프로세스 정보
struct PyProcessInfo
{
	DWORD   pid;
	CString fullPath;   // 실행 파일 전체 경로 (조회 실패 시 "python.exe")
	CString cmdLine;    // 실행 커맨드라인 (어떤 스크립트를 어떤 유저로 띄웠는지 판별용)
};


// ---------------------------------------------------------
// CFancyButton : 둥근 모서리 + 색상 + 마우스 오버/눌림 상태를 직접 그리는 버튼
//   기본 푸시 버튼 대신 BS_OWNERDRAW로 만들고 DrawItem()에서 전부 그린다.
//   SetAccent()로 버튼마다 바탕색/글자색을 달리 준다.
// ---------------------------------------------------------
class CFancyButton : public CButton
{
public:
	CFancyButton();

	// 바탕색과 글자색 지정 (생성 후 한 번 호출)
	void SetAccent(COLORREF face, COLORREF text);

	// 모서리 둥글기 지정 (작은 버튼은 작게)
	void SetRadius(int radius);

	// 키보드(스페이스/엔터)로는 눌리지 않게 한다. 마우스 클릭은 그대로.
	void SetNoKeyActivate(bool bNoKey);

	virtual void DrawItem(LPDRAWITEMSTRUCT lpDIS);

protected:
	COLORREF m_face;        // 기본 바탕색
	COLORREF m_text;        // 글자색
	bool     m_bHover;      // 마우스가 위에 있는가
	bool     m_bTracking;   // WM_MOUSELEAVE 추적 중인가
	int      m_radius;      // 모서리 둥글기(px)
	bool     m_bNoKeyActivate;  // 키보드로 눌리는 것을 막는가

	afx_msg void    OnMouseMove(UINT nFlags, CPoint point);
	afx_msg LRESULT OnMouseLeave(WPARAM wParam, LPARAM lParam);
	afx_msg void    OnKeyDown(UINT nChar, UINT nRepCnt, UINT nFlags);
	afx_msg void    OnKeyUp(UINT nChar, UINT nRepCnt, UINT nFlags);
	DECLARE_MESSAGE_MAP()
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

	CFancyButton m_btnStartAll, m_btnKillAll, m_btnCmd, m_btnFolder, m_btnClose;
	CButton m_btnMinimize;
	CFancyButton m_btnProcList;

	std::vector<PyProcessInfo> m_lastPyProcesses;  // 최근 스캔에서 발견된 python.exe 목록
	std::vector<DWORD> m_startedPids;              // '시작' 버튼으로 실행한 launcher(cmd.exe) PID 목록

	CComboBox mComboBox_ID;

	CFont m_stdFont;
	CFont m_rowFont;                       // 프로세스 목록 전용 글꼴 (Noto Sans KR)
	CStatic m_lblRowsSeparator;            // 목록 상단 구분선

	std::vector<CFancyButton*> m_stopButtons;
	std::vector<CStatic*> m_labels;        // 프로세스 행 상태 라벨
	std::vector<DWORD>    m_rowPids;       // 행별 현재 PID (0 = 미실행)
	bool m_bRowsVisible;                   // 하단 프로세스 목록이 펼쳐져 있는가
	CString m_shownUserId;                 // 현재 목록에 배치된 user ID (콤보박스 선택값)
	std::vector<bool> m_rowSelected;       // 행이 선택된 user의 것인가
	int  m_wndChromeH;                     // 캡션+테두리 높이(px)
	bool m_bStarting;                      // Run_All_Processes 진행 중 (재진입 방지)
	int  m_baseWndH;                       // 접었을 때 창 전체 높이(px)
	int  m_expandedWndH;                   // 펼쳤을 때 창 전체 높이(px)

	CStatic m_lblTitle, m_lblSign, m_lbStatus_0;
	CStatic m_lblTimer;
	CEdit   m_editRestartMin;   // ★ 재시작 주기 입력 CEdit
	int m_elapsedSeconds;;
	int m_nStatusLevel;

	void SetStatusLevel(int level);
	void OnStopButton(UINT nID);
	bool KillProcess(const char* keyword);
	bool IsProcessRunning(const char* keyword);
	void CreateProcessRows(int topY);       // 프로세스 행(라벨+정지 버튼) 생성
	void RefreshProcessRows();             // 행별 실행 상태 갱신
	void ShowProcessRows(bool bShow);      // 하단 목록 펼치기/접기
	CString GetSelectedUserId();           // 콤보박스에서 고른 user ID
	void LayoutProcessRows();              // 선택된 user의 행만 위에서부터 재배치
	void ApplyRowVisibility();             // 펼침 상태 + 선택 user에 맞춰 표시/창 높이 반영
	void ApplyImageWindowVisibility();     // 선택된 user의 이미지 뷰어 창만 표시
	afx_msg void OnSelchangeComboId();     // 콤보박스에서 user를 바꿨을 때
	void ApplyRowFont();                   // 목록 컨트롤에 전용 글꼴 적용
	void OnBnClickedStartAll();
	void Run_All_Processes(std::string sUserID);
	void OnBnClickedKillAll();
	void OnBnClickedClose();
	void OnBnClickedCMD();
	void OnBnClickedFolder();
	void RunCmdWithTitle(const char* title, const char* command);
	int  CountPythonProcesses();
	DWORD RunCmdHidden(const char* name, const char* cmd);
	void PumpWait(DWORD ms);
	afx_msg void OnBnClickedProcList();
	void KillOrphanedProcesses();

	UINT GetRestartIntervalMs(bool bSave = FALSE);


	afx_msg HBRUSH OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor);

	afx_msg void OnBnClickedMinimize(); //ON_WM_CTLCOLOR() 에서 호출

	// 종료 경로 (모두 LogEvent로 기록)
	virtual void OnOK();
	virtual void OnCancel();
	afx_msg void OnClose();
	afx_msg void OnDestroy();
	virtual BOOL OnCommand(WPARAM wParam, LPARAM lParam);   // 진단용 로깅

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
