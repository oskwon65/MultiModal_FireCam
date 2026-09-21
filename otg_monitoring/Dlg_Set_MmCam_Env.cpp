// Dlg_Set_MmCam_Env.cpp: 구현 파일
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "Dlg_Set_MmCam_Env.h"
#include "afxdialogex.h"
#include "MmCam_monitoringDlg.h"

// CDlg_Set_MmCam_Env 대화 상자

IMPLEMENT_DYNAMIC(CDlg_Set_MmCam_Env, CDialogEx)

extern const char* GetMmCamStartPath();

#define ID_BTN_GET_MASK_SVR				2010
#define ID_BTN_SET_MASK_CAM_POS		2020
#define ID_BTN_CLOSE							2000

// 연속 학습 단계 전환 조건
#define ID_ED_BASE_SAMPLES				2100
#define ID_ED_BASE_HOURS					2101
#define ID_ED_AE_SAMPLES					2102
#define ID_BTN_SAVE_STAGE					2110

// 파이썬 쪽 기본값과 반드시 같아야 한다.
//   BASELINE_MIN_SAMPLES / BASELINE_MIN_HOURS : predict_machine/online_baseline.py
//   RETRAIN_MIN_SAMPLES                       : retrain/nightly_retrain.py
// 값이 없을 때 양쪽이 서로 다른 기본값을 쓰면, 화면에 보이는 숫자와 실제
// 동작이 어긋나면서 원인을 찾기 어려워진다.
#define DEF_BASE_SAMPLES	3000
#define DEF_BASE_HOURS		18
#define DEF_AE_SAMPLES		5000

extern std::string ini_read_utf8(const std::string&, const std::string&,
                                 const std::string&, const std::string&);
extern int  ini_read_int_utf8(const std::string&, const std::string&,
                              const std::string&, int);
extern bool ini_write_int_utf8(const std::string&, const std::string&,
                               const std::string&, int);

CDlg_Set_MmCam_Env::CDlg_Set_MmCam_Env(CWnd* pParent /*=nullptr*/)
	: CDialogEx(IDD_DLG_CMD, pParent)
{

}

CDlg_Set_MmCam_Env::~CDlg_Set_MmCam_Env()
{
}

void CDlg_Set_MmCam_Env::DoDataExchange(CDataExchange* pDX)
{
	CDialogEx::DoDataExchange(pDX);
	DDX_Control(pDX, IDC_CAP_0, m_cap_0);
}

BEGIN_MESSAGE_MAP(CDlg_Set_MmCam_Env, CDialogEx)
	ON_WM_LBUTTONDOWN()
	ON_BN_CLICKED(ID_BTN_SET_MASK_CAM_POS, &CDlg_Set_MmCam_Env::OnBnClickedButtonChangeMask)
	ON_BN_CLICKED(ID_BTN_GET_MASK_SVR, &CDlg_Set_MmCam_Env::OnBnClickedButtonGetMask)
	ON_BN_CLICKED(ID_BTN_CLOSE, &CDlg_Set_MmCam_Env::OnBnClickedClose)
	ON_BN_CLICKED(ID_BTN_SAVE_STAGE, &CDlg_Set_MmCam_Env::OnBnClickedSaveStage)
END_MESSAGE_MAP()

extern void update_db_main_command(const char* new_code);
extern CurrentStatus read_db_current_status();
extern std::string gUserID;

//---------------------------------------------------------

BOOL CDlg_Set_MmCam_Env::OnInitDialog()
{
	CDialogEx::OnInitDialog();

	CWnd* pParent = GetParent(); // 부모 창(this로 전달받은 메인 다이얼로그) 가져오기
	if (pParent != nullptr)
	{
		CRect rectParent;
		pParent->GetWindowRect(&rectParent); // 부모 창의 전체 화면 좌표(좌,우,상,하) 구하기

		CRect rectMe;
		GetWindowRect(&rectMe); // 현재 내 다이얼로그의 크기 구하기

		// 새 위치 계산: 
		// 좌측 X 좌표는 부모 창의 좌측(left)과 일치시킴
		// 상단 Y 좌표는 부모 창의 하단(bottom)에 딱 붙임
		int newX = rectParent.left;
		int newY = rectParent.bottom-70;
		int newWidth = rectParent.Width();
		// 연속 학습 단계 설정란이 아래에 붙으면서 200 -> 330 으로 늘렸다.
		int newHeight = 330;

		// 내 다이얼로그 위치 이동 (크기는 유지, 위치만 변경)
		// SWP_NOZORDER: 윈도우 겹침 순서 유지, SWP_NOSIZE: 원래 리소스 뷰 크기 유지
		::SetWindowPos(m_hWnd, HWND_TOP, newX, newY, newWidth, newHeight, SWP_NOZORDER );
	}

	SetWindowText("[설정]");

	// -------------------------------------------------------------

	m_stdFont.CreateFont(
		22,                         // 폰트 높이 (픽셀 단위 크기)
		0, 0, 0,
		FW_NORMAL, //FW_BOLD,                  
		FALSE, FALSE, 0,
		DEFAULT_CHARSET,
		OUT_DEFAULT_PRECIS,
		CLIP_DEFAULT_PRECIS,
		DEFAULT_QUALITY,
		DEFAULT_PITCH | FF_DONTCARE,
		_T("맑은 고딕")             // ◀ 여기에 "Segoe UI" 나 "Tahoma"를 넣으셔도 됩니다.
	);

	SetFont(&m_stdFont);
	SendMessageToDescendants(WM_SETFONT, (WPARAM)m_stdFont.GetSafeHandle(), TRUE); // TRUE :  현 다이알로그 하위 컨트롤 전체까지 폰트 지정함

	long ctrl_btn_hei = 40;
	long ctrl_btn_top = 65;
	const long nBase_X = 10;

	m_btnClose.Create("x", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, CRect(nBase_X + 530, ctrl_btn_top, nBase_X + 530 + 50, ctrl_btn_top + ctrl_btn_hei), this, ID_BTN_CLOSE);
	m_btnGetMask_Server.Create("격자 마스크 초기화 : SVR지정", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, CRect(nBase_X, ctrl_btn_top, nBase_X + 250, ctrl_btn_top + ctrl_btn_hei), this, ID_BTN_GET_MASK_SVR);
	m_btnSetMask_CamPos.Create("격자 마스크 초기화 : 위치이동", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON, CRect(nBase_X + 250 + 10, ctrl_btn_top, nBase_X + 250 +10 +250, ctrl_btn_top + ctrl_btn_hei), this, ID_BTN_SET_MASK_CAM_POS);

	CurrentStatus current_status = read_db_current_status();
	std::string tmsg = "[" + gUserID + "]  ";
	if (current_status.valid) {
		tmsg = tmsg + current_status.debug_msg;
	}

	m_cap_0.SetWindowTextA(tmsg.c_str());

	// -------------------------------------------------------------
	// 연속 학습 단계 전환 조건
	//
	// 현장마다 수집 주기가 다르다. kict1 은 5초, cj_busan_1 은 30초라
	// 같은 표본 수를 모으는 데 걸리는 시간이 6배 차이난다. 설비 가동 주기도
	// 다르다. 그래서 전환 조건을 코드에 박지 않고 여기서 조정한다.
	// -------------------------------------------------------------

	const long lbl_w = 200, ed_w = 90, row_h = 32;
	long y = ctrl_btn_top + ctrl_btn_hei + 20;

	m_capStage.Create("[ 연속 학습 단계 전환 조건 ]",
		WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X, y, nBase_X + 520, y + 26), this);
	y += 32;

	struct Row { CStatic* lbl; CEdit* ed; const char* text; UINT id; };
	Row rows[] = {
		{ &m_lblBaseSamples, &m_edBaseSamples, "1단계 기준선 최소 표본 (건)",  ID_ED_BASE_SAMPLES },
		{ &m_lblBaseHours,   &m_edBaseHours,   "1단계 최소 관측 시간대 (0~24)", ID_ED_BASE_HOURS   },
		{ &m_lblAeSamples,   &m_edAeSamples,   "2단계 재학습 최소 표본 (건)",  ID_ED_AE_SAMPLES   },
	};

	for (int i = 0; i < 3; ++i)
	{
		rows[i].lbl->Create(rows[i].text, WS_CHILD | WS_VISIBLE | SS_LEFT,
			CRect(nBase_X, y + 4, nBase_X + lbl_w, y + 4 + 24), this);

		rows[i].ed->Create(WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP
			| ES_NUMBER | ES_RIGHT,
			CRect(nBase_X + lbl_w + 10, y, nBase_X + lbl_w + 10 + ed_w, y + 26),
			this, rows[i].id);

		y += row_h;
	}

	m_btnSaveStage.Create("저장", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
		CRect(nBase_X + lbl_w + 10 + ed_w + 20, ctrl_btn_top + ctrl_btn_hei + 52,
		      nBase_X + lbl_w + 10 + ed_w + 20 + 90, ctrl_btn_top + ctrl_btn_hei + 52 + 36),
		this, ID_BTN_SAVE_STAGE);

	LoadStageSettings();

	// 다이알로그와 하위개체까지 Font 지정 효과 전달하기 위함
	SendMessageToDescendants(WM_SETFONT, (WPARAM)m_stdFont.GetSafeHandle(), TRUE);

	return TRUE;  // return TRUE unless you set the focus to a control
}

//---------------------------------------------------------

std::string CDlg_Set_MmCam_Env::StageIniPath() const
{
	return std::string(GetMmCamStartPath()) + "users\\" + gUserID + "\\env.ini";
}

//---------------------------------------------------------

void CDlg_Set_MmCam_Env::LoadStageSettings()
{
	const std::string ini = StageIniPath();

	CString s;
	s.Format("%d", ini_read_int_utf8(ini, "CONSTANTS", "BASELINE_MIN_SAMPLES", DEF_BASE_SAMPLES));
	m_edBaseSamples.SetWindowTextA(s);

	s.Format("%d", ini_read_int_utf8(ini, "CONSTANTS", "BASELINE_MIN_HOURS", DEF_BASE_HOURS));
	m_edBaseHours.SetWindowTextA(s);

	s.Format("%d", ini_read_int_utf8(ini, "CONSTANTS", "RETRAIN_MIN_SAMPLES", DEF_AE_SAMPLES));
	m_edAeSamples.SetWindowTextA(s);
}

//---------------------------------------------------------

void CDlg_Set_MmCam_Env::OnBnClickedSaveStage()
{
	if (gUserID.empty()) {
		m_cap_0.SetWindowTextA("[ERROR] 현장(user)이 선택되지 않았습니다.");
		return;
	}

	CString a, b, c;
	m_edBaseSamples.GetWindowTextA(a);
	m_edBaseHours.GetWindowTextA(b);
	m_edAeSamples.GetWindowTextA(c);

	const int base_samples = atoi(a);
	const int base_hours   = atoi(b);
	const int ae_samples   = atoi(c);

	// 터무니없는 값이 들어가면 감시가 영영 시작되지 않거나(너무 큼),
	// 아무것도 못 배운 상태로 채점을 시작한다(너무 작음). 여기서 막는다.
	if (base_samples < 100 || base_samples > 1000000) {
		m_cap_0.SetWindowTextA("[ERROR] 1단계 최소 표본은 100 ~ 1,000,000 사이여야 합니다.");
		return;
	}
	if (base_hours < 1 || base_hours > 24) {
		m_cap_0.SetWindowTextA("[ERROR] 최소 관측 시간대는 1 ~ 24 사이여야 합니다.");
		return;
	}
	if (ae_samples < 1000 || ae_samples > 1000000) {
		m_cap_0.SetWindowTextA("[ERROR] 2단계 최소 표본은 1,000 ~ 1,000,000 사이여야 합니다.");
		return;
	}

	const std::string ini = StageIniPath();

	bool ok = ini_write_int_utf8(ini, "CONSTANTS", "BASELINE_MIN_SAMPLES", base_samples)
		&& ini_write_int_utf8(ini, "CONSTANTS", "BASELINE_MIN_HOURS", base_hours)
		&& ini_write_int_utf8(ini, "CONSTANTS", "RETRAIN_MIN_SAMPLES", ae_samples);

	CStringA msg;
	if (ok) {
		// 파이썬 프로세스는 기동할 때 설정을 읽는다. 저장만으로는 반영되지 않는다.
		msg.Format("[저장 완료] 1단계 %d건/%d시간대, 2단계 %d건"
			"   -  '정지' 후 '시작'을 눌러야 반영됩니다.",
			base_samples, base_hours, ae_samples);
	}
	else {
		msg.Format("[ERROR] env.ini 를 쓰지 못했습니다: %s", ini.c_str());
	}
	m_cap_0.SetWindowTextA(msg);
}

//---------------------------------------------------------

void CDlg_Set_MmCam_Env::OnLButtonDown(UINT nFlags, CPoint point)
{
	if (point.y < 40)
	{
		ReleaseCapture();
		SendMessage(WM_NCLBUTTONDOWN, HTCAPTION, 0);
		return;
	}

	CDialogEx::OnLButtonDown(nFlags, point);
}

//---------------------------------------------------------

void CDlg_Set_MmCam_Env::OnBnClickedButtonChangeMask()
{
	m_cap_0.SetWindowTextA("조정된 격자마스크 [격자초기화] 명령 전달함 : ADJST-MG");
	update_db_main_command("ADJST-MG");
}

//---------------------------------------------------------

void CDlg_Set_MmCam_Env::OnBnClickedButtonGetMask()
{
	if (gUserID.empty()) {
		m_cap_0.SetWindowTextA("[ERROR] gUserID is not set.");
		return;
	}

	std::string user_path = std::string(GetMmCamStartPath()) + "users\\" + gUserID + "\\";

	std::string src_file = user_path + "grid_select.txt";
	std::string target_file = user_path + "mach_area_mask.ini";

	int bSuccess = CopyFileA(src_file.c_str(), target_file.c_str(), FALSE);

	CStringA msg;
	if (bSuccess) {
		msg.Format("[ Success ] Copy new grid mask from server");
		m_cap_0.SetWindowTextA(msg);
	}
	else {
		DWORD err_code = GetLastError();
		msg.Format("[ Fail Err:%lu ] - Check if 'grid_select.txt' exists.\r\nPath: %s",
			err_code, src_file.c_str());
		m_cap_0.SetWindowTextA(msg);
	}
}

//---------------------------------------------------------

void CDlg_Set_MmCam_Env::OnBnClickedClose()
{
	OnOK();
}

//---------------------------------------------------------