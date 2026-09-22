
// MmCam_monitoringDlg.h: 헤더 파일
//

#pragma once

// 프로그램 전체가 쓰는 글꼴. 창마다 다른 글꼴을 쓰면 같은 프로그램인데
// 화면마다 인상이 달라진다. 한 곳에서만 바꾸도록 여기에 둔다.
#define UI_FONT_NAME        "Noto Sans KR"


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

	// 토글 버튼: 켜져 있는 동안 계속 눌린 모양으로 그린다.
	// 문구만 바뀌면(설정 -> 닫기) 지금 켜진 상태인지 한눈에 안 들어온다.
	void SetChecked(bool bChecked);
	bool IsChecked() const { return m_bChecked; }

	virtual void DrawItem(LPDRAWITEMSTRUCT lpDIS);

protected:
	COLORREF m_face;        // 기본 바탕색
	COLORREF m_text;        // 글자색
	bool     m_bHover;      // 마우스가 위에 있는가
	bool     m_bTracking;   // WM_MOUSELEAVE 추적 중인가
	int      m_radius;      // 모서리 둥글기(px)
	bool     m_bNoKeyActivate;  // 키보드로 눌리는 것을 막는가
	bool     m_bChecked;        // 토글이 켜져 있는가 (계속 눌린 모양)

	afx_msg void    OnMouseMove(UINT nFlags, CPoint point);
	afx_msg LRESULT OnMouseLeave(WPARAM wParam, LPARAM lParam);
	afx_msg void    OnKeyDown(UINT nChar, UINT nRepCnt, UINT nFlags);
	afx_msg void    OnKeyUp(UINT nChar, UINT nRepCnt, UINT nFlags);
	DECLARE_MESSAGE_MAP()
};
// CMmCammonitoringDlg 대화 상자
class CDlg_Set_MmCam_Env;   // 설정 영역 (모덜리스). 순환 참조를 피한 전방 선언

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

	// 설정 영역. 예전에는 DoModal() 로 띄웠는데, 모달이라 열려 있는 동안
	// 메인 창의 시작·정지·목록 버튼이 전혀 눌리지 않았다. 감시 프로그램에서
	// 설정을 보는 동안 정지도 못 하는 것은 곤란하다. 모덜리스로 바꾸고
	// [설정] 버튼이 보이기/숨기기를 토글한다.
	//
	// 순환 참조를 피하려고 전방 선언 + 포인터로 둔다.
	CDlg_Set_MmCam_Env* m_pDlgSet;
	bool m_bSettingVisible;

public:
	// 설정 창이 스스로 닫혔을 때 버튼 문구를 되돌리기 위해 호출한다.
	void OnSettingPanelClosed();

private:
	CString m_shownUserId;                 // 현재 목록에 배치된 user ID (콤보박스 선택값)
	std::vector<bool> m_rowSelected;       // 행이 선택된 user의 것인가
	int  m_wndChromeH;                     // 캡션+테두리 높이(px)
	bool m_bStarting;                      // Run_All_Processes 진행 중 (재진입 방지)
	int  m_baseWndH;                       // 접었을 때 창 전체 높이(px)
	int  m_expandedWndH;                   // 펼쳤을 때 창 전체 높이(px)
	int  m_visibleRowCount;                // 현재 보이는 프로세스 행 수 (설정 영역 위치 계산용)

	CProgressCtrl m_progress;              // '시작' 진행바
	int  m_startStep;                      // 지금까지 띄운 스크립트 수
	CRect m_rcStatusNormal;                // 진행바가 없을 때의 상태줄 자리

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
	void ApplyRowVisibility();             // 아래 ApplyExpandLayout 을 부르는 껍데기
	void ApplyExpandLayout();              // 목록·설정 두 영역을 함께 배치하고 창 높이 반영
	void ApplyImageWindowVisibility();     // 선택된 user의 이미지 뷰어 창만 표시
	afx_msg void OnSelchangeComboId();     // 콤보박스에서 user를 바꿨을 때
	void RefreshSettingPanel();            // 설정 영역을 지금 고른 현장 값으로
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
	// pctFrom/pctTo 를 주면 기다리는 동안 진행바를 그 구간만큼 채운다.
	// -1 이면 진행바를 건드리지 않는다(기존 호출부 그대로).
	void PumpWait(DWORD ms, int pctFrom = -1, int pctTo = -1);

	// '시작' 진행 표시. 기동에 20초 안팎이 걸리는데 그동안 아무 반응이
	// 없으면 눌린 것인지 알 수 없어 다시 누르게 된다.
	void ShowStartProgress(bool bShow);
	void SetStartProgress(int pct, const char* step);
	bool AnyViewerWindowUp();              // 이미지 뷰어 창이 떴는가
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
