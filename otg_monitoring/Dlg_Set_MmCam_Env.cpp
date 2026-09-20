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
		int newHeight = 200;

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

	// 다이알로그와 하위개체까지 Font 지정 효과 전달하기 위함
	SendMessageToDescendants(WM_SETFONT, (WPARAM)m_stdFont.GetSafeHandle(), TRUE);

	return TRUE;  // return TRUE unless you set the focus to a control
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