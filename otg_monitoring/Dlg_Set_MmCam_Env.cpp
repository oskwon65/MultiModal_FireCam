// Dlg_Set_MmCam_Env.cpp: 구현 파일
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "Dlg_Set_MmCam_Env.h"
#include "afxdialogex.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_CamPos.h"
#include "Dlg_Retrain.h"

#include <wininet.h>
#pragma comment(lib, "wininet.lib")

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
#define ID_ED_BASE_DATE						2103
#define ID_ED_AE_HOURS						2104
#define ID_BTN_SAVE_STAGE					2110
#define ID_BTN_RETRAIN						2205

// 0단계 절대 임계값
#define ID_ED_ABS_TEMP_W					2120
#define ID_ED_ABS_TEMP_A					2121
#define ID_ED_ABS_RISE_W					2122
#define ID_ED_ABS_RISE_A					2123

// 임계값은 지정되지 않을 수 있다(신규 현장). 그때 화면에는 빈칸을 보여
// 주어야 "0으로 설정됨" 과 구분된다.
#define ABS_UNSET							-1

// 파이썬 쪽 기본값과 반드시 같아야 한다.
//   BASELINE_MIN_SAMPLES / BASELINE_MIN_HOURS : predict_machine/online_baseline.py
//   RETRAIN_MIN_SAMPLES                       : retrain/nightly_retrain.py
// 값이 없을 때 양쪽이 서로 다른 기본값을 쓰면, 화면에 보이는 숫자와 실제
// 동작이 어긋나면서 원인을 찾기 어려워진다.
#define DEF_BASE_SAMPLES	3000
#define DEF_BASE_HOURS		18
#define DEF_AE_SAMPLES		5000
// 재학습에도 시간대 다양성 조건을 둔다. 개수만으로는 "낮에만 아는
// 모델" 을 막지 못한다 — kict1 은 표본 15,352건으로 최소 기준의 세 배를
// 넘겼지만 새벽 02~07시가 통째로 비어 있었다.
// retrain/nightly_retrain.py 의 MIN_HOURS_DEFAULT 와 같아야 한다.
#define DEF_AE_HOURS		18
// 계산 기준일은 기본값이 없다. 빈 값 = 제한 없이 전체 기간 사용.
#define DEF_CALC_BASE_DATE	""

// 체크박스를 없앴으므로 "전체 기간" 을 날짜로 나타내야 한다. 이 시스템이
// 수집을 시작(2025-08)하기 한참 전이라 이 날짜 이후를 쓰면 전체와 같다.
// 이 값이 그대로 저장되면 env.ini 에는 빈 값(= 전체)으로 적는다.
#define ALL_PERIOD_Y	2000
#define ALL_PERIOD_M	1
#define ALL_PERIOD_D	1

extern std::string ini_read_utf8(const std::string&, const std::string&,
                                 const std::string&, const std::string&);
extern int  ini_read_int_utf8(const std::string&, const std::string&,
                              const std::string&, int);
extern bool ini_write_int_utf8(const std::string&, const std::string&,
                               const std::string&, int);
extern bool ini_write_utf8(const std::string&, const std::string&,
                           const std::string&, const std::string&);

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
	ON_BN_CLICKED(ID_BTN_RETRAIN, &CDlg_Set_MmCam_Env::OnBnClickedRetrain)
END_MESSAGE_MAP()

extern void update_db_main_command(const char* new_code);
extern CurrentStatus read_db_current_status();
extern std::string gUserID;

//---------------------------------------------------------

BOOL CDlg_Set_MmCam_Env::OnInitDialog()
{
	CDialogEx::OnInitDialog();

	// 위치와 크기는 정하지 않는다.
	//
	// 예전에는 여기서 부모 창 아래에 붙는 팝업으로 스스로 자리를 잡았다.
	// 지금은 메인 창 안에 자식으로 끼워 넣어 "목록" 처럼 펼쳐지는 영역으로
	// 쓰므로, 배치는 전적으로 메인 창(ApplyExpandLayout)이 맡는다.
	//
	// 내용이 차지하는 높이는 SETTING_AREA_H 로 메인 창과 맞춰 두었다.

	SetWindowText("[설정]");

	// -------------------------------------------------------------

	m_stdFont.CreateFont(
		UI_FONT_SIZE,               // 프로그램 전체 공통 크기
		0, 0, 0,
		FW_NORMAL, //FW_BOLD,                  
		FALSE, FALSE, 0,
		DEFAULT_CHARSET,
		OUT_DEFAULT_PRECIS,
		CLIP_DEFAULT_PRECIS,
		DEFAULT_QUALITY,
		DEFAULT_PITCH | FF_DONTCARE,
		_T(UI_FONT_NAME)            // 프로그램 전체 공통 (MmCam_monitoringDlg.h)
	);

	SetFont(&m_stdFont);
	SendMessageToDescendants(WM_SETFONT, (WPARAM)m_stdFont.GetSafeHandle(), TRUE); // TRUE :  현 다이알로그 하위 컨트롤 전체까지 폰트 지정함

	long ctrl_btn_hei = 40;
	long ctrl_btn_top = 65;
	const long nBase_X = 10;

	// x 버튼은 두지 않는다. 메인 창의 [설정] 버튼이 토글이라 닫는 길이
	// 이미 있고, 영역 안에 또 닫기 버튼이 있으면 어느 쪽이 무엇을 닫는지
	// 헷갈린다.
	// 두 버튼의 이름을 하는 일로 바꿨다.
	//
	// 예전에는 둘 다 "격자 마스크 초기화 : ..." 로 시작해 같은 기능의 변형
	// 처럼 보였다. 실제로는 하나는 감시 대상(어느 셀을 볼지)을 서버 것으로
	// 갈아치우고, 다른 하나는 같은 선택을 카메라가 밀린 만큼 옮긴다.
	// 전혀 다른 일이다.
	//
	// 너비는 250 -> 141 로 줄였다. 글꼴은 다른 컨트롤과 같은 크기를 쓴다.
	//
	// 그 폭에 들어가도록 이름을 줄였다. 긴 이름을 두 줄로 접어 보았더니
	// 좁아진 대신 높아져 오히려 커 보였다. 한 줄에 들어가는 길이로 맞추고
	// 자세한 내용은 누른 뒤 안내 문구로 설명한다.
	//
	//   서버에서 Mask 받기            -> 서버 Mask 받기
	//   카메라 이동 검사 및 Mask 조정 -> 카메라 이동보정
	// 설정 영역의 버튼은 모두 같은 너비를 쓴다. 폭이 제각각이면 줄이
	// 맞지 않아 어수선해 보인다.
	const long btn_w = 141;
	const long mask_btn_h = 30;

	const DWORD mask_btn_style = WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON;

	// 위쪽 안내줄(상태 문구)과 버튼 구역을 가른다. 아래 [연속학습 조건]
	// 위에도 같은 선이 있어, 설정 영역이 세 덩어리로 나뉘어 보인다.
	{
		CRect rcC;
		GetClientRect(&rcC);
		long sepRight = rcC.right - nBase_X;
		if (sepRight < nBase_X + 520) sepRight = nBase_X + 520;

		m_sepTop.Create("", WS_CHILD | WS_VISIBLE | SS_ETCHEDHORZ,
			CRect(nBase_X, ctrl_btn_top - 10, sepRight, ctrl_btn_top - 8), this);
	}

	m_btnGetMask_Server.Create("서버 Mask 받기", mask_btn_style,
		CRect(nBase_X, ctrl_btn_top, nBase_X + btn_w, ctrl_btn_top + mask_btn_h),
		this, ID_BTN_GET_MASK_SVR);

	m_btnSetMask_CamPos.Create("카메라 이동보정", mask_btn_style,
		CRect(nBase_X + btn_w + 10, ctrl_btn_top,
		      nBase_X + btn_w + 10 + btn_w, ctrl_btn_top + mask_btn_h),
		this, ID_BTN_SET_MASK_CAM_POS);

	// 잰 틀어짐 값을 버튼 옆에 적는다. 계산은 이미 하고 있었는데 화면에
	// 나오지 않아, 지금 밀려 있는지 알 길이 없었다.
	//
	// 두 줄인 이유는 재는 대상이 둘이기 때문이다. 위는 RGB, 아래는 열화상.
	// 한 줄로 합치면 어느 카메라가 밀렸는지가 사라지는데, 바로 그 구분이
	// kict1 에서 두 달을 놓치게 만든 지점이었다.
	m_lblShift.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X + (btn_w + 10) * 2, ctrl_btn_top - 1,
		      nBase_X + (btn_w + 10) * 2 + 330, ctrl_btn_top - 1 + 36), this);

	LoadHeader();

	// -------------------------------------------------------------
	// 연속 학습 단계 전환 조건
	//
	// 현장마다 수집 주기가 다르다. kict1 은 5초, cj_busan_1 은 30초라
	// 같은 표본 수를 모으는 데 걸리는 시간이 6배 차이난다. 설비 가동 주기도
	// 다르다. 그래서 전환 조건을 코드에 박지 않고 여기서 조정한다.
	// -------------------------------------------------------------

	// 폰트를 25% 줄였으므로 라벨 폭과 행 높이도 같이 줄인다.
	//
	// row_h 는 연속학습 조건 네 줄의 간격이다. 34 로 두었더니 헐거워 보여
	// 27 로 좁혔다. 입력 칸 높이가 22 이므로 5px 만 남는 셈이지만, 항목이
	// 넷뿐이라 빽빽해 보이지 않는다.
	// 절대 임계값 줄도 같은 간격을 쓴다. 두 묶음이 바로 위아래에 있어
	// 간격이 다르면 눈에 거슬린다.
	// 글자가 17 에서 20 으로 커진 만큼 넓힌다. 그대로 두면 "기준선 최소
	// 표본수" 같은 라벨이 잘린다.
	const long lbl_w = 184, ed_w = 92, row_h = 31;
	const long stage_top = ctrl_btn_top + mask_btn_h + 16;
	long y = stage_top;

	// 위쪽 마스크 버튼과 성격이 다른 구역이라 선으로 가른다.
	// 메인 창의 프로세스 목록 구분선과 같은 방식(SS_ETCHEDHORZ)이다.
	{
		CRect rcC;
		GetClientRect(&rcC);
		long sepRight = rcC.right - nBase_X;
		if (sepRight < nBase_X + 520) sepRight = nBase_X + 520;

		m_sepStage.Create("", WS_CHILD | WS_VISIBLE | SS_ETCHEDHORZ,
			CRect(nBase_X, y - 8, sepRight, y - 6), this);
	}

	m_capStage.Create("[ 연속학습 조건 ]",
		WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X, y, nBase_X + 520, y + 22), this);
	y += 26;

	struct Row { CStatic* lbl; CEdit* ed; const char* text; UINT id; };
	Row rows[] = {
		{ &m_lblBaseSamples, &m_edBaseSamples, "기준선 최소 표본수",  ID_ED_BASE_SAMPLES },
		{ &m_lblBaseHours,   &m_edBaseHours,   "기준선 최소 시간대",  ID_ED_BASE_HOURS     },
		{ &m_lblAeSamples,   &m_edAeSamples,   "재학습 최소 표본수",  ID_ED_AE_SAMPLES    },
		{ &m_lblAeHours,     &m_edAeHours,     "재학습 최소 시간대",  ID_ED_AE_HOURS       },
	};

	const int nRows = (int)(sizeof(rows) / sizeof(rows[0]));

	for (int i = 0; i < nRows; ++i)
	{
		rows[i].lbl->Create(rows[i].text, WS_CHILD | WS_VISIBLE | SS_LEFT,
			CRect(nBase_X, y + 3, nBase_X + lbl_w, y + 3 + 20), this);

		rows[i].ed->Create(WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP
			| ES_NUMBER | ES_RIGHT,
			CRect(nBase_X + lbl_w + 10, y, nBase_X + lbl_w + 10 + ed_w, y + 22),
			this, rows[i].id);

		y += row_h;
	}

	// 계산 기준일은 달력에서 고른다.
	//
	// 직접 타이핑하게 두면 2026-13-45 같은 값이나 오타가 들어오고, 형식을
	// 검사해 막아도 사용자는 무엇이 틀렸는지 알기 어렵다. 달력은 애초에
	// 잘못된 날짜를 고를 수 없다.
	//
	// 체크박스(DTS_SHOWNONE)는 쓰지 않는다. 체크를 풀면 날짜가 흐리게
	// 표시되어 지금 어느 날짜가 잡혀 있는지 읽기 어려웠다. 항상 선택된
	// 날짜를 또렷하게 보여준다.
	//
	// 대신 "전체 기간" 을 표현할 자리가 없어진다. 그 경우는 데이터가
	// 시작되기 전 날짜를 고르면 된다. 기준일은 "이 날짜 이전을 버린다" 는
	// 뜻이므로, 충분히 이른 날짜는 전체를 쓰는 것과 같다.
	m_lblBaseDate.Create("계산기준일",
		WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X, y + 3, nBase_X + lbl_w, y + 3 + 20), this);

	m_dtBaseDate.Create(WS_CHILD | WS_VISIBLE | WS_TABSTOP | WS_BORDER
		| DTS_SHORTDATEFORMAT,
		// "2026-09-21" 열 글자와 드롭다운 단추가 들어갈 만큼.
		//
		// 예전에 25% 줄여 두었는데 글꼴이 17 에서 20 으로 커지면서 날짜가
		// 잘렸다. 글자 폭에 맞춰 잡아야 글꼴을 또 바꿔도 깨지지 않는다.
		// 한 글자를 대략 글꼴 높이의 0.62배로 보고, 단추 몫 24px 을 더한다.
		CRect(nBase_X + lbl_w + 10, y,
		      nBase_X + lbl_w + 10 + (UI_FONT_SIZE * 62 / 100) * 10 + 24,
		      y + row_h - 5),
		this, ID_ED_BASE_DATE);

	// 지역 설정에 따라 표시 형식이 달라지면 env.ini 에 쓰는 값과 화면이
	// 어긋나 보인다. 저장 형식과 똑같이 맞춘다.
	m_dtBaseDate.SetFormat(_T("yyyy-MM-dd"));

	y += row_h;

	y += 10;

	// -------------------------------------------------------------
	// 0단계 절대 임계값
	//
	// 학습과 무관하게 늘 동작하는 안전망이라 설비마다 값이 전혀 다르다.
	// kict1 은 정상 가동 중 마스크 셀이 197도까지 오르고, cj_busan_1 은
	// 정상 가동의 99%가 12도/분을 넘는다. 추측한 기본값은 쉬지 않고 경보를
	// 울리므로 현장에서 직접 넣어야 한다.
	//
	// 주의와 경보를 한 줄에 둘씩 묶어 두 줄로 줄였다. 넷을 따로 늘어놓으면
	// 설정 영역이 지나치게 길어진다.
	// -------------------------------------------------------------
	const long ed2_w = 70;
	const long ed2_x1 = nBase_X + lbl_w + 10;
	const long ed2_x2 = ed2_x1 + ed2_w + 10;

	m_capAbs.Create("[ 절대 임계값 (0단계) ]   주의 / 경보",
		WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X, y, nBase_X + 330, y + 22), this);
	y += 26;

	struct ARow { CStatic* lbl; CEdit* w; CEdit* a; const char* text; UINT idw; UINT ida; };
	ARow arows[] = {
		{ &m_lblAbsTemp, &m_edAbsTempWarn, &m_edAbsTempAlarm,
		  "마스크 셀 최고 온도 (도)", ID_ED_ABS_TEMP_W, ID_ED_ABS_TEMP_A },
		{ &m_lblAbsRise, &m_edAbsRiseWarn, &m_edAbsRiseAlarm,
		  "분당 상승률 (도/분)",      ID_ED_ABS_RISE_W, ID_ED_ABS_RISE_A },
	};

	for (int i = 0; i < 2; ++i)
	{
		arows[i].lbl->Create(arows[i].text, WS_CHILD | WS_VISIBLE | SS_LEFT,
			CRect(nBase_X, y + 3, nBase_X + lbl_w, y + 3 + 20), this);

		const DWORD est = WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP
			| ES_NUMBER | ES_RIGHT;

		arows[i].w->Create(est, CRect(ed2_x1, y, ed2_x1 + ed2_w, y + 22),
			this, arows[i].idw);
		arows[i].a->Create(est, CRect(ed2_x2, y, ed2_x2 + ed2_w, y + 22),
			this, arows[i].ida);

		y += row_h;
	}

	// 적용 버튼 하나로 두 묶음을 함께 저장한다.
	//
	// 처음에는 묶음마다 버튼을 두었는데, 화면에 적용 버튼이 둘이면 어느
	// 것을 눌러야 하는지 매번 판단해야 하고 한쪽만 누르고 끝내기도 쉽다.
	//
	// 캡션이 "저장" 이 아닌 이유: 파일에 쓰는 것으로 끝이 아니라 파이썬을
	// 다시 기동해야 실제로 반영된다. "저장" 이라고 하면 눌렀으니 됐다고
	// 여기기 쉽다.
	m_btnSaveStage.Create("설정 적용", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
		CRect(nBase_X, y + 6, nBase_X + btn_w, y + 6 + 26),
		this, ID_BTN_SAVE_STAGE);

	// 재학습은 운용 모델을 바꾸는 일이라 여기서 바로 돌리지 않는다.
	// 창을 띄워 예행연습 결과를 먼저 보여 준다.
	m_btnRetrain.Create("재학습", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
		CRect(nBase_X + btn_w + 10, y + 6, nBase_X + btn_w * 2 + 10, y + 6 + 26),
		this, ID_BTN_RETRAIN);

	// 설정 영역의 끝을 긋는다. 위쪽 두 구분선과 짝을 이뤄 영역이 어디서
	// 끝나는지 분명해진다.
	//
	// 오른쪽 현재 진행 열(네 항목, 353 근처에서 끝)보다 아래에 와야 열을
	// 가로지르지 않는다. 적용 버튼이 394 에서 끝나므로 그 아래에 둔다.
	{
		CRect rcC;
		GetClientRect(&rcC);
		long sepRight = rcC.right - nBase_X;
		if (sepRight < nBase_X + 520) sepRight = nBase_X + 520;

		m_sepBottom.Create("", WS_CHILD | WS_VISIBLE | SS_ETCHEDHORZ,
			CRect(nBase_X, y + 42, sepRight, y + 44), this);
	}

	// -------------------------------------------------------------
	// 현재 진행 상황 — 설정란 오른편
	//
	// 설정값만 보여주면 "그래서 지금 몇 단계인가" 를 알 수 없다. 조건과
	// 진행 상황을 나란히 두어 한눈에 비교하게 한다.
	//
	// 메인 창 너비가 678 이라 오른편에 300 남짓 쓸 수 있다. 그런데
	// "1단계 사용 중  표본 12,345/3,000 · 시간대 20/18" 은 한 줄로 400 이
	// 넘어 잘린다. 그래서 단계마다 두 줄로 적는다. 컨트롤을 6개로 늘리는
	// 대신 라벨 하나를 두 줄 높이로 만들고 \r\n 으로 줄을 나눈다.
	// -------------------------------------------------------------
	const long col2_x = nBase_X + 360;

	// 열 폭을 창에서 구한다. 380 으로 박아 두었더니 창(약 660px)보다 넓어
	// 오른쪽이 잘렸다. 글꼴 크기를 바꿀 때마다 다시 틀어지는 종류의 값이라
	// 숫자로 두지 않는다.
	long col2_w;
	{
		CRect rcC;
		GetClientRect(&rcC);
		col2_w = rcC.right - col2_x - nBase_X;
		if (col2_w < 260) col2_w = 260;       // 너무 좁으면 최소치로
	}

	// 0~2 는 "지금 무엇으로 채점할 수 있는가"(상태)이고, 연속학습은
	// "모델을 어떻게 갱신하는가"(활동)다. 성격이 달라 번호를 붙이지 않는다.
	m_capNow.Create("[ 현재 진행 ]", WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(col2_x, stage_top, col2_x + col2_w, stage_top + 22), this);

	// 0단계(절대 임계값)도 늘 동작하므로 함께 보여준다. 네 항목이 되면서
	// 간격을 62 -> 54 로 줄였다.
	long ny = stage_top + 26;
	CStatic* stg[4] = { &m_lblStage0, &m_lblStage1, &m_lblStage2, &m_lblStage3 };
	// 칸마다 줄 수가 다르다. 한 값으로 두면 긴 칸의 마지막 줄이 잘린다.
	//
	//   0 절대임계값   제목 · 온도/상승률                  2줄
	//   1 셀별기준선   제목 · 표본/시간대                  2줄
	//   2 오토인코더   제목 · 세대 · 모델 파일 시각        3줄
	//   3 연속학습     제목 · 재학습 가능 · 점수 · 기여    4줄
	static const long STAGE_H[4] = { 52, 52, 78, 108 };
	const long STAGE_GAP = 8;

	for (int i = 0; i < 4; ++i)
	{
		stg[i]->Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
			CRect(col2_x, ny, col2_x + col2_w, ny + STAGE_H[i]), this);
		ny += STAGE_H[i] + STAGE_GAP;
	}

	LoadStageSettings();
	LoadAbsSettings();
	LoadStageStatus();

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

	s.Format("%d", ini_read_int_utf8(ini, "CONSTANTS", "RETRAIN_MIN_HOURS", DEF_AE_HOURS));
	m_edAeHours.SetWindowTextA(s);

	// 저장된 기준일이 있으면 그 날짜를, 없으면 오늘을 보여준다.
	//
	// 오늘을 띄우면 다른 항목만 고치고 [적용] 을 눌렀을 때 기준일이 오늘로
	// 박혀 그동안 쌓은 기준선이 날아갈 수 있다. 그래서 적용 단계에서
	// 기준일이 바뀌는 경우 한 번 물어본다 (OnBnClickedSaveStage 참고).
	const std::string d = ini_read_utf8(ini, "CONSTANTS", "CALC_BASE_DATE", DEF_CALC_BASE_DATE);

	int yy = 0, mm = 0, dd = 0;
	if (d.size() == 10 && sscanf_s(d.c_str(), "%d-%d-%d", &yy, &mm, &dd) == 3
		&& yy >= 1970 && mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31)
	{
		CTime t(yy, mm, dd, 0, 0, 0);
		m_dtBaseDate.SetTime(&t);
	}
	else
	{
		CTime today = CTime::GetCurrentTime();
		m_dtBaseDate.SetTime(&today);
	}
}

//---------------------------------------------------------

// predict_machine 이 남긴 stage_status.ini 를 읽어 현재 단계를 보여준다.
//
// 이 파일이 없을 수 있다. 감시를 아직 돌리지 않았거나, 막 시작해서 첫
// 기록이 나오기 전이다. 그때 0 건이라고 적으면 정말 0 건인 것과 구분이
// 안 되므로 "집계 대기" 로 표시한다.
//
// 예전 문구는 "감시를 돌리면 표시됩니다" 였는데, 이미 돌리고 있는
// 사용자에게는 사실과 어긋나는 안내였다. 파일이 없는 이유가 "안 돌려서"
// 인지 "아직 안 써서" 인지 여기서는 알 수 없으므로, 둘 다 맞는 말로 적는다.
void CDlg_Set_MmCam_Env::LoadStageStatus()
{
	const std::string st =
		std::string(GetMmCamStartPath()) + "users\\" + gUserID + "\\stage_status.ini";

	const std::string updated = ini_read_utf8(st, "STATUS", "UPDATED_AT", "");

	if (updated.empty()) {
		m_lblShift.SetWindowTextA("RGB 틀어짐 : 확인 전\r\n열화상 틀어짐 : 확인 전");
		m_lblStage0.SetWindowTextA("0단계 절대임계값   집계 대기\r\n    감시 시작 후 첫 기록까지 잠시 걸립니다");
		m_lblStage1.SetWindowTextA("1단계 셀별기준선   집계 대기");
		m_lblStage2.SetWindowTextA("2단계 오토인코더   집계 대기");
		m_lblStage3.SetWindowTextA("연속학습   집계 대기");
		return;
	}

	const int samples = ini_read_int_utf8(st, "STATUS", "SAMPLES", 0);
	const int min_smp = ini_read_int_utf8(st, "STATUS", "MIN_SAMPLES", 0);
	const int hours   = ini_read_int_utf8(st, "STATUS", "HOURS", 0);
	const int min_hr  = ini_read_int_utf8(st, "STATUS", "MIN_HOURS", 0);
	const int s1      = ini_read_int_utf8(st, "STATUS", "STAGE1", 0);
	const int s2      = ini_read_int_utf8(st, "STATUS", "STAGE2", 0);
	const int s3      = ini_read_int_utf8(st, "STATUS", "STAGE3", 0);
	const int used    = ini_read_int_utf8(st, "STATUS", "STAGE_USED", -1);
	const int db_rows = ini_read_int_utf8(st, "STATUS", "DB_ROWS", -1);
	const int min_rtr = ini_read_int_utf8(st, "STATUS", "MIN_RETRAIN", -1);
	const std::string gen_at = ini_read_utf8(st, "STATUS", "GENERATION_AT", "");
	const std::string bdate  = ini_read_utf8(st, "STATUS", "BASE_DATE", "");
	// 기준일은 사람이 정하는 정책이고, 누적 시작일은 실제로 쌓기 시작한 날이다.
	// 둘이 다를 수 있어 따로 보여줘야 표본 수를 해석할 수 있다.
	const std::string sdate  = ini_read_utf8(st, "STATUS", "STARTED_AT", "");

	CStringA t;

	// 카메라 틀어짐 — RGB 와 열화상을 따로 적는다.
	//
	// RGB 는 기동할 때 한 번만 재고 루프 안에서는 다시 재지 않는다. 열화상
	// 쪽은 격자를 매 프레임 읽으므로 운전 중에도 주기적으로 다시 잰다. 잰
	// 시각을 함께 적어야 몇 시간 전 값을 지금 값으로 오해하지 않는다.
	{
		CStringA sh, line;

		const std::string sx = ini_read_utf8(st, "STATUS", "SHIFT_X", "");
		const std::string sy = ini_read_utf8(st, "STATUS", "SHIFT_Y", "");
		const std::string sat = ini_read_utf8(st, "STATUS", "SHIFT_AT", "");

		// SHIFT_STATE 를 따로 두는 까닭. 0칸이라는 값만으로는 "틀어지지
		// 않았다" 와 "잴 수 없었다" 를 가를 수 없다.
		//  -1 예전 방식(밝기별 기준 더미)으로 돌고 있다
		//   0 쟀으나 믿을 수 없다 (기준과 다른 장면)
		//   1 틀어지지 않았다
		//   2 틀어졌다
		const int sstate = ini_read_int_utf8(st, "STATUS", "SHIFT_STATE", -1);

		// 잰 픽셀 값. 칸 수만 적으면 한 칸(640/8 = 80px)보다 작은 흔들림이
		// 통째로 "0칸" 으로 묻힌다. kict1 의 기준 이미지 더미에 10~20px 씩
		// 조금씩 돌아간 흔적이 남아 있었는데, 칸으로만 보면 전부 이동 없음
		// 이었다. 서서히 돌아가는 것은 이 자리에서 먼저 드러난다.
		const std::string sdx = ini_read_utf8(st, "STATUS", "SHIFT_DX", "");
		const std::string sdy = ini_read_utf8(st, "STATUS", "SHIFT_DY", "");

		CStringA px;
		if (!sdx.empty() && !sdy.empty())
			px.Format("가로 %+.1f · 세로 %+.1f px",
				atof(sdx.c_str()), atof(sdy.c_str()));

		const char* old_way = (sstate < 0) ? " · 예전 방식" : "";

		if (sx.empty() || sy.empty())
			line = "RGB 틀어짐 : 확인 전";
		else if (sstate == 0)
			line.Format("RGB 틀어짐 : 판정 불가 (기준과 다른 장면)   (%s 기동 시)",
				sat.c_str());
		else if (atoi(sx.c_str()) == 0 && atoi(sy.c_str()) == 0)
			line.Format("RGB 틀어짐 : %s   (0칸 · %s 기동 시 측정%s)",
				px.IsEmpty() ? "없음" : (LPCSTR)px, sat.c_str(), old_way);
		else
		{
			// 이동은 자동으로 보정하지 않는다. 되돌려도 score 가 0.088 에서
			// 0.365 까지밖에 안 올랐고(정상 0.952), 가장자리 공백을 무엇으로
			// 채우든 지어낸 값이 64차원 입력 전체를 오염시킨다.
			//
			// 대신 크게 밀리면 사람에게 알린다. 2칸이면 마스크 16칸 중
			// 4칸이, 3칸이면 7칸이 감시에서 빠진다.
			const int nx = abs(atoi(sx.c_str())), ny = abs(atoi(sy.c_str()));
			const char* warn = (nx >= 2 || ny >= 2) ? "  ※ 현장 조준 확인" : "";
			line.Format("RGB 틀어짐 : %s   (가로 %+d칸 · 세로 %+d칸 · %s 측정%s)%s",
				px.IsEmpty() ? "틀어짐" : (LPCSTR)px,
				atoi(sx.c_str()), atoi(sy.c_str()), sat.c_str(), old_way, warn);
		}

		sh = line + "\r\n";

		// 열화상. TSHIFT_STATE 가 상태를 가른다.
		//  -1 기준 패턴을 아직 못 굳혔다 (표본을 모으는 중)
		//   0 화면이 밋밋해 판정할 수 없었다
		//   1 틀어지지 않았다
		//   2 틀어졌다 — 몇 칸인지까지 안다
		//   3 기준 패턴과 안 맞는다 — 방향은 못 밝혔다
		//
		// 3 을 따로 두는 이유. kict1 의 실제 사고가 3 이었다. 칸 수를 못
		// 밝혔다고 "이상 없음" 으로 적으면 그 사고가 그대로 묻힌다.
		const int tstate = ini_read_int_utf8(st, "STATUS", "TSHIFT_STATE", -1);
		const std::string tx = ini_read_utf8(st, "STATUS", "TSHIFT_X", "");
		const std::string ty = ini_read_utf8(st, "STATUS", "TSHIFT_Y", "");
		const std::string tc = ini_read_utf8(st, "STATUS", "TSHIFT_CORR", "");
		const std::string tc0 = ini_read_utf8(st, "STATUS", "TSHIFT_CORR0", "");
		const std::string tat = ini_read_utf8(st, "STATUS", "TSHIFT_AT", "");

		if (tstate < 0)
			line = "열화상 틀어짐 : 기준 패턴 준비 중";
		else if (tstate == 0)
			line = "열화상 틀어짐 : 판정 불가 (화면 온도차 부족)";
		else if (tstate == 1)
			line.Format("열화상 틀어짐 : 없음   (일치도 %s · %s 측정)",
				tc.c_str(), tat.c_str());
		else if (tstate == 2)
			line.Format("열화상 틀어짐 : 가로 %+d칸 · 세로 %+d칸   (일치도 %s · %s 측정)",
				atoi(tx.c_str()), atoi(ty.c_str()), tc.c_str(), tat.c_str());
		else
			// 문자열 상수는 CP949 로 저장된다. em dash(U+2014) 는 CP949 에
			// 없어 C4566 이 난다. 가운뎃점은 있다.
			line.Format("열화상 화면 불일치 : 일치도 %s · 조준 확인 필요   (%s 측정)",
				tc0.c_str(), tat.c_str());

		sh += line;
		m_lblShift.SetWindowTextA(sh);
	}

	// 0단계 — 학습과 무관하게 늘 동작한다. 다만 임계값을 지정하지 않으면
	// 판정 자체가 꺼져 있으므로 그 구분을 보여준다.
	const int s0 = ini_read_int_utf8(st, "STATUS", "STAGE0", 0);
	if (s0)
	{
		t.Format("0단계 절대임계값   사용 중\r\n    온도 %s/%s도 · 상승 %s/%s도/분",
			ini_read_utf8(st, "STATUS", "ABS_TEMP_WARN", "-").c_str(),
			ini_read_utf8(st, "STATUS", "ABS_TEMP_ALARM", "-").c_str(),
			ini_read_utf8(st, "STATUS", "ABS_RISE_WARN", "-").c_str(),
			ini_read_utf8(st, "STATUS", "ABS_RISE_ALARM", "-").c_str());
	}
	else
	{
		t.Format("0단계 절대임계값   꺼짐\r\n    env.ini 에 ABS_TEMP · ABS_RISE 미지정");
	}
	m_lblStage0.SetWindowTextA(t);

	// 단계 번호만으로는 그것이 무엇인지 알 수 없다. 이름을 함께 적는다.
	// 좁은 열에 맞추려고 두 줄로 나눈다. 첫 줄은 이름과 상태, 둘째 줄은 근거.
	//
	// 1단계는 채점에 쓰이는 중인지까지 구분한다. 준비됐어도 2단계가 있으면
	// 둘이 함께 쓰이므로 "사용 중" 이 맞다.
	t.Format("1단계 셀별기준선   %s\r\n    표본 %d/%d · 시간대 %d/%d",
		s1 ? "사용 중" : "누적 중", samples, min_smp, hours, min_hr);
	m_lblStage1.SetWindowTextA(t);

	// 지금 쓰고 있는 세대와 모델 파일의 시각을 적는다.
	//
	// 세대 이름은 되돌리기나 재학습에서 그대로 쓰는 이름이다. 설정 창에서
	// 바로 읽을 수 있어야 "지금 무엇이 돌고 있는가" 를 묻지 않아도 된다.
	//
	// 파일 시각을 함께 두는 이유가 있다. 세대 이름은 승격할 때 적어 둔 것이고
	// 파일 시각은 실제로 적재된 파일의 것이라, 둘이 어긋나면 산출물이 뒤바뀐
	// 것이다. 2026-09-25 cj_busan_1 이 그 상태로 이틀을 돌았다.
	//
	// 모델은 기동할 때 한 번만 읽는다. 새 파일로 바꿔 놓고 재시작하지 않으면
	// 여기 값이 그대로다 - 그것만으로 바로 알아챈다.
	if (s2)
	{
		const std::string gen = ini_read_utf8(st, "STATUS", "GENERATION", "");
		const std::string mat = ini_read_utf8(st, "STATUS", "MODEL_AT", "");
		t.Format("2단계 오토인코더   사용 중\r\n    세대 %s\r\n    모델 %s",
			gen.empty() ? "-" : gen.c_str(),
			mat.empty() ? "-" : mat.c_str());
	}
	else
	{
		t.Format("2단계 오토인코더   없음\r\n    모델 파일이 아직 없습니다\r\n");
	}
	m_lblStage2.SetWindowTextA(t);

	if (s3 && !gen_at.empty())
		t.Format("연속학습   적용됨\r\n    최근 승격 %s", gen_at.c_str());
	else if (db_rows >= 0 && min_rtr > 0)
		t.Format("연속학습   대기\r\n    재학습 가능 %d/%d건", db_rows, min_rtr);
	else
		t.Format("연속학습   대기\r\n    아직 재학습 이력이 없습니다");

	// 재학습이 기존 모델을 얼마나 물려받을지.
	//
	// 카메라가 몇 칸 밀렸는지로는 모델이 쓸 만한지 알 수 없다. 실측에서
	// 3칸을 밀어도 score 가 0.890 이었고, kict1 은 1.3칸 밀린 상태로
	// 0.088 이었다. 그래서 지금 내고 있는 점수로 정한다.
	{
		const std::string ds = ini_read_utf8(st, "STATUS", "DECISION_SCORE", "");
		const std::string cw = ini_read_utf8(st, "STATUS", "CONTRIB_W", "");
		if (!ds.empty() && !cw.empty())
		{
			// 기여는 이제 네 단계가 아니라 점수에 비례하는 연속값이다.
			// 말로만 "기여 축소" 라고 하면 0.62 와 0.13 이 구별되지 않는다.
			// 옛 자료 비중을 그대로 적는다.
			const double w = atof(cw.c_str());
			CStringA how;
			if (w >= 1.0)      how = "평소대로 이어감";
			else if (w <= 0.0) how = "새로 시작";
			else               how.Format("옛 자료 %.0f%%", w * 100.0);
			// 한 줄에 다 넣으면 열 폭을 넘어 잘린다. 두 줄로 나눈다.
			CStringA c2;
			c2.Format("\r\n    판단 점수 %s"
			          "\r\n    기존 모델 기여 %s · %s",
				ds.c_str(), cw.c_str(), (LPCSTR)how);
			t += c2;
		}
	}
	m_lblStage3.SetWindowTextA(t);

	// 기준일과 갱신 시각은 상단 안내줄에 함께 보여준다.
	CStringA head;
	CStringA sfrom;
	if (!sdate.empty() && sdate != bdate)
		sfrom.Format(" (누적 %s~)", sdate.c_str());

	head.Format("[%s]  기준일 %s%s  ·  현황 %s  ·  현재 채점 %s",
		gUserID.c_str(),
		bdate.empty() ? "전체" : bdate.c_str(),
		(LPCSTR)sfrom,
		updated.c_str(),
		used < 0 ? "-" : (used == 2 ? "2단계" : (used == 1 ? "1단계" : "0단계")));
	m_cap_0.SetWindowTextA(head);
}

//---------------------------------------------------------

// (형식 검사 함수는 달력 컨트롤 도입으로 불필요해져 제거)

//---------------------------------------------------------

void CDlg_Set_MmCam_Env::OnBnClickedSaveStage()
{
	if (gUserID.empty()) {
		m_cap_0.SetWindowTextA("[ERROR] 현장(user)이 선택되지 않았습니다.");
		return;
	}

	CString a, b, c, d;
	m_edBaseSamples.GetWindowTextA(a);
	m_edBaseHours.GetWindowTextA(b);
	m_edAeSamples.GetWindowTextA(c);
	// 달력에는 늘 날짜가 들어 있다. 다만 "전체 기간" 표시용으로 쓰는
	// 아주 이른 날짜라면 env.ini 에는 빈 값으로 적는다. 그래야 파이썬 쪽이
	// 지금처럼 "제한 없음" 으로 동작하고, 기준일이 바뀌었다고 오해해
	// 기준선을 헛되이 버리는 일도 없다.
	CTime dt;
	if (m_dtBaseDate.GetTime(dt) == GDT_VALID)
	{
		const CTime all(ALL_PERIOD_Y, ALL_PERIOD_M, ALL_PERIOD_D, 0, 0, 0);
		if (dt > all) d = dt.Format("%Y-%m-%d");
	}

	const int base_samples = atoi(a);
	const int base_hours   = atoi(b);
	const int ae_samples   = atoi(c);
	m_edAeHours.GetWindowTextA(c);
	const int ae_hours     = atoi(c);

	// 터무니없는 값이 들어가면 감시가 영영 시작되지 않거나(너무 큼),
	// 아무것도 못 배운 상태로 채점을 시작한다(너무 작음). 여기서 막는다.
	if (base_samples < 100 || base_samples > 1000000) {
		m_cap_0.SetWindowTextA("[ERROR] 기준선 최소 표본은 100 ~ 1,000,000 사이여야 합니다.");
		return;
	}
	if (base_hours < 1 || base_hours > 24) {
		m_cap_0.SetWindowTextA("[ERROR] 기준선 최소 시간대는 1 ~ 24 사이여야 합니다.");
		return;
	}
	if (ae_samples < 1000 || ae_samples > 1000000) {
		m_cap_0.SetWindowTextA("[ERROR] 재학습 최소 표본은 1,000 ~ 1,000,000 사이여야 합니다.");
		return;
	}
	if (ae_hours < 1 || ae_hours > 24) {
		m_cap_0.SetWindowTextA("[ERROR] 재학습 최소 시간대는 1 ~ 24 사이여야 합니다.");
		return;
	}

	// --- 0단계 절대 임계값 -----------------------------------------
	// 버튼 하나로 두 묶음을 함께 저장하므로 여기서 같이 검사한다.
	CString at, aa, ar, arA;
	m_edAbsTempWarn.GetWindowTextA(at);
	m_edAbsTempAlarm.GetWindowTextA(aa);
	m_edAbsRiseWarn.GetWindowTextA(ar);
	m_edAbsRiseAlarm.GetWindowTextA(arA);

	// 네 칸을 모두 비우면 0단계를 끈다. 일부만 비우는 것은 어중간한 상태라
	// 막는다 — 온도만 넣고 상승률을 비우면 어느 쪽이 의도인지 알 수 없다.
	const bool bAbsAllEmpty = at.IsEmpty() && aa.IsEmpty() && ar.IsEmpty() && arA.IsEmpty();
	const bool bAbsAnyEmpty = at.IsEmpty() || aa.IsEmpty() || ar.IsEmpty() || arA.IsEmpty();

	if (!bAbsAllEmpty && bAbsAnyEmpty) {
		m_cap_0.SetWindowTextA("[ERROR] 절대 임계값 네 칸을 모두 채우거나 모두 비우십시오. "
			"모두 비우면 0단계 경보가 꺼집니다.");
		return;
	}

	if (!bAbsAllEmpty)
	{
		const int tw = atoi(at), ta = atoi(aa), rw = atoi(ar), ra = atoi(arA);

		// 격자 온도는 0~255 범위다(utils.Conv_LWIR_to_64_Vector 와 같은 기준).
		if (tw < 1 || tw > 255 || ta < 1 || ta > 255) {
			m_cap_0.SetWindowTextA("[ERROR] 온도는 1 ~ 255 도 사이여야 합니다.");
			return;
		}
		if (rw < 1 || rw > 500 || ra < 1 || ra > 500) {
			m_cap_0.SetWindowTextA("[ERROR] 상승률은 1 ~ 500 도/분 사이여야 합니다.");
			return;
		}
		// 주의선이 경보선보다 높으면 주의가 영영 뜨지 않는다.
		if (tw >= ta || rw >= ra) {
			m_cap_0.SetWindowTextA("[ERROR] 주의선은 경보선보다 낮아야 합니다.");
			return;
		}
	}

	const std::string ini = StageIniPath();

	const std::string prev_date = ini_read_utf8(ini, "CONSTANTS", "CALC_BASE_DATE", "");
	const std::string new_date  = (const char*)CStringA(d);

	// 기준일이 바뀌면 셀별 기준선을 버리고 처음부터 다시 쌓는다. 며칠치
	// 누적이 사라지는 일이라 그냥 진행하지 않고 한 번 물어본다.
	//
	// 지정된 값이 없을 때 달력에 오늘이 떠 있으므로, 다른 항목만 고치고
	// [적용] 을 눌러도 기준일이 오늘로 바뀌는 상황이 생긴다. 그 경우를
	// 사용자가 알아채지 못한 채 지나가게 두면 안 된다.
	if (prev_date != new_date)
	{
		const std::string st = std::string(GetMmCamStartPath())
			+ "users\\" + gUserID + "\\stage_status.ini";
		const int samples = ini_read_int_utf8(st, "STATUS", "SAMPLES", -1);

		CStringA q;
		q.Format("계산기준일을 %s -> %s 로 바꿉니다.\r\n\r\n"
			"셀별 기준선을 버리고 처음부터 다시 쌓습니다.\r\n",
			prev_date.empty() ? "전체" : prev_date.c_str(),
			new_date.empty() ? "전체" : new_date.c_str());

		if (samples > 0) {
			CStringA add;
			add.Format("지금까지 쌓인 표본 %d건이 사라집니다.\r\n", samples);
			q += add;
		}
		q += "\r\n진행할까요?";

		if (AfxMessageBox(q, MB_YESNO | MB_ICONWARNING) != IDYES) {
			m_cap_0.SetWindowTextA("[취소] 아무것도 바꾸지 않았습니다.");
			return;
		}
	}

	bool ok = ini_write_int_utf8(ini, "CONSTANTS", "BASELINE_MIN_SAMPLES", base_samples)
		&& ini_write_int_utf8(ini, "CONSTANTS", "BASELINE_MIN_HOURS", base_hours)
		&& ini_write_int_utf8(ini, "CONSTANTS", "RETRAIN_MIN_SAMPLES", ae_samples)
		&& ini_write_int_utf8(ini, "CONSTANTS", "RETRAIN_MIN_HOURS", ae_hours)
		&& ini_write_utf8(ini, "CONSTANTS", "CALC_BASE_DATE", new_date)
		&& ini_write_utf8(ini, "CONSTANTS", "ABS_TEMP_WARN",  (const char*)CStringA(at))
		&& ini_write_utf8(ini, "CONSTANTS", "ABS_TEMP_ALARM", (const char*)CStringA(aa))
		&& ini_write_utf8(ini, "CONSTANTS", "ABS_RISE_WARN",  (const char*)CStringA(ar))
		&& ini_write_utf8(ini, "CONSTANTS", "ABS_RISE_ALARM", (const char*)CStringA(arA));

	CStringA msg;
	if (ok) {
		// 파이썬 프로세스는 기동할 때 설정을 읽는다. 저장만으로는 반영되지 않는다.
		// 기준일이 바뀌면 기준선 누적을 버리고 처음부터 다시 쌓는다.
		// 며칠치 누적이 사라지는 일이라 화면에 분명히 알린다.
		const char* warn = (prev_date != new_date)
			? "  *기준일이 바뀌어 셀별 기준선을 새로 시작합니다*" : "";
		CStringA absPart;
		if (bAbsAllEmpty)
			absPart = "임계값 꺼짐";
		else
			absPart.Format("임계값 %s/%s도·%s/%s도분",
				(const char*)CStringA(at), (const char*)CStringA(aa),
				(const char*)CStringA(ar), (const char*)CStringA(arA));

		msg.Format("[적용 완료] 1단계 %d건/%d시간대, 2단계 %d건, 기준일 %s, %s%s"
			"   -  '정지' 후 '시작'을 눌러야 반영됩니다.",
			base_samples, base_hours, ae_samples,
			new_date.empty() ? "전체" : new_date.c_str(),
			(const char*)absPart, warn);
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
	// 예전에는 누르는 즉시 명령을 넣었다. 되돌릴 방법이 없고 무엇이
	// 일어나는지도 알 수 없었다. 확인 창에서 켤지 끌지 고르게 한다.
	CDlg_CamPos dlg(this);
	dlg.m_bAdjust = TRUE;   // 버튼을 누른 뜻이 보통 "켜겠다" 이므로 미리 켜 둔다

	if (dlg.DoModal() != IDOK) {
		m_cap_0.SetWindowTextA("[취소] 아무것도 바꾸지 않았습니다.");
		return;
	}

	if (dlg.m_bAdjust)
	{
		update_db_main_command("ADJST-MG");
		m_cap_0.SetWindowTextA("[전달] 카메라 위치 보정을 켰습니다 (ADJST-MG). "
			"'정지' 후 '시작' 시 검사하며, 밀렸으면 Mask 를 함께 옮깁니다. "
			"이동량이 2칸 이상이면 조정할 수 없습니다.");
	}
	else
	{
		// 넣어 둔 명령을 거둔다. 켠 뒤 마음이 바뀌었을 때 되돌릴 길이 있어야 한다.
		update_db_main_command("NOACTION");
		m_cap_0.SetWindowTextA("[전달] 카메라 위치 보정을 껐습니다 (NOACTION). "
			"이동이 감지되어도 Mask 를 옮기지 않고 오류로만 기록합니다.");
	}
}

//---------------------------------------------------------

// 서버에 해당 URL 이 실제로 있는지 확인한다.
//
// 로컬 마스크를 지우기 전에 반드시 봐야 한다. 서버에 파일이 없는데 지우면
// 다음 기동 때 받아오지 못하고, 마스크 없이 채점이 멈춘다.
static bool UrlExists(const std::string& url)
{
	HINTERNET hNet = ::InternetOpenA("MmCam", INTERNET_OPEN_TYPE_PRECONFIG,
		nullptr, nullptr, 0);
	if (!hNet) return false;

	bool ok = false;

	HINTERNET hUrl = ::InternetOpenUrlA(hNet, url.c_str(), nullptr, 0,
		INTERNET_FLAG_RELOAD | INTERNET_FLAG_NO_CACHE_WRITE, 0);
	if (hUrl)
	{
		DWORD code = 0, len = sizeof(code), idx = 0;
		if (::HttpQueryInfoA(hUrl, HTTP_QUERY_STATUS_CODE | HTTP_QUERY_FLAG_NUMBER,
			&code, &len, &idx))
		{
			ok = (code == 200);
		}
		::InternetCloseHandle(hUrl);
	}

	::InternetCloseHandle(hNet);
	return ok;
}

//---------------------------------------------------------
// [격자 마스크 초기화 : SVR지정]
//
// 로컬 마스크를 지워, 다음 기동 때 서버에서 새로 받게 한다.
//
// predict_machine 은 로컬 파일이 있으면 서버에 새 마스크가 올라와도
// 내려받지 않는다. 그래서 마스크를 바꾸려면 로컬 파일을 먼저 지우는 것이
// 정해진 절차다.
//
// [예전 구현]
//   grid_select.txt -> mach_area_mask.ini 로 복사했다. 그런데 원본은
//   서버에도 로컬에도 존재한 적이 없고(HTTP 404), 대상 파일을 읽는
//   파이썬 코드도 없었다. 눌러도 실패 메시지만 뜨는, 동작한 적 없는
//   경로였다. 화면에 있는 버튼이 아무 일도 하지 않는 것이 가장 나쁘다.
//---------------------------------------------------------
void CDlg_Set_MmCam_Env::OnBnClickedButtonGetMask()
{
	if (gUserID.empty()) {
		m_cap_0.SetWindowTextA("[ERROR] 현장(user)이 선택되지 않았습니다.");
		return;
	}

	const std::string user_path =
		std::string(GetMmCamStartPath()) + "users\\" + gUserID + "\\";
	const std::string local_mask = user_path + "hotlist_mask_local.ini";

	// 서버 주소는 현장 설정에서 읽는다.
	const std::string root_url =
		ini_read_utf8(StageIniPath(), "NETWORK", "ROOT_URL", "");
	if (root_url.empty()) {
		m_cap_0.SetWindowTextA("[ERROR] env.ini 의 [NETWORK] ROOT_URL 이 비어 있습니다.");
		return;
	}

	std::string url = root_url;
	while (!url.empty() && (url.back() == '/' || url.back() == ' ')) url.pop_back();
	url += "/" + gUserID + "/hotlist_mask_svr.ini";

	m_cap_0.SetWindowTextA("서버에 격자 마스크가 있는지 확인 중...");
	if (!UrlExists(url)) {
		CStringA msg;
		msg.Format("[중단] 서버에서 마스크를 찾지 못했습니다. 지우지 않았습니다.\r\n%s",
			url.c_str());
		m_cap_0.SetWindowTextA(msg);
		return;
	}

	const bool bHasLocal = (::GetFileAttributesA(local_mask.c_str()) != INVALID_FILE_ATTRIBUTES);

	if (bHasLocal)
	{
		CStringA q;
		q.Format("현재 격자 마스크를 지우고 서버 것으로 다시 받습니다.\r\n\r\n"
			"서버 : %s\r\n\r\n"
			"지금 쓰던 마스크는 hotlist_mask_local.bak 로 남겨 둡니다.\r\n"
			"'정지' 후 '시작'을 눌러야 실제로 받아옵니다.\r\n\r\n진행할까요?",
			url.c_str());

		if (AfxMessageBox(q, MB_YESNO | MB_ICONQUESTION) != IDYES) {
			m_cap_0.SetWindowTextA("[취소] 마스크를 그대로 두었습니다.");
			return;
		}

		// 되돌릴 수 있도록 한 벌 남긴다. 서버 마스크가 엉뚱한 것이었을 때
		// 현장에서 복구할 길이 있어야 한다.
		const std::string bak = user_path + "hotlist_mask_local.bak";
		::CopyFileA(local_mask.c_str(), bak.c_str(), FALSE);

		if (!::DeleteFileA(local_mask.c_str())) {
			CStringA msg;
			msg.Format("[ERROR] 마스크를 지우지 못했습니다 (err %lu): %s",
				::GetLastError(), local_mask.c_str());
			m_cap_0.SetWindowTextA(msg);
			return;
		}
	}

	m_cap_0.SetWindowTextA("[완료] 로컬 마스크를 지웠습니다. "
		"'정지' 후 '시작'을 누르면 서버에서 새로 받습니다.");
}

//---------------------------------------------------------

void CDlg_Set_MmCam_Env::OnBnClickedClose()
{
	OnCancel();
}

//---------------------------------------------------------
// 모덜리스로 쓰므로 OK/취소가 창을 없애면 안 된다.
//
// 기본 구현은 EndDialog 를 부르는데, 모덜리스 창에는 맞지 않아 창이
// 이상한 상태로 남는다. 숨기기만 하고 부모에게 알려 [설정] 버튼 문구를
// 되돌리게 한다. Enter·ESC 도 이리로 들어오므로 실수로 닫혀도 안전하다.
//---------------------------------------------------------

void CDlg_Set_MmCam_Env::OnOK()
{
	OnCancel();
}

void CDlg_Set_MmCam_Env::OnCancel()
{
	ShowWindow(SW_HIDE);

	CMmCammonitoringDlg* pMain = (CMmCammonitoringDlg*)GetParent();
	if (pMain != nullptr && ::IsWindow(pMain->GetSafeHwnd()))
		pMain->OnSettingPanelClosed();
}

//---------------------------------------------------------

// 제목줄. 어느 현장을 보고 있는지를 여기서만 알 수 있으므로, 현장이 바뀌면
// 반드시 같이 바뀌어야 한다.
//
// 예전에는 이 내용을 OnInitDialog 안에 적어 두어, 설정 영역을 한 번 만든
// 뒤에는 콤보박스로 현장을 바꿔도 제목이 그대로였다. 아래 값들은 새 현장
// 것으로 바뀌는데 제목만 옛 현장 이름이라, 어느 쪽 값을 보고 있는지
// 화면만으로는 알 수 없었다.
void CDlg_Set_MmCam_Env::LoadHeader()
{
	CurrentStatus current_status = read_db_current_status();
	std::string tmsg = "[" + gUserID + "]  ";
	if (current_status.valid) {
		tmsg = tmsg + current_status.debug_msg;
	}

	m_cap_0.SetWindowTextA(tmsg.c_str());
}

void CDlg_Set_MmCam_Env::RefreshAll()
{
	// 현장(콤보박스)이 바뀌었을 수도 있으므로 제목줄부터 다시 만든다.
	LoadHeader();
	LoadStageSettings();
	LoadAbsSettings();
	LoadStageStatus();
}

//---------------------------------------------------------

// 0단계 임계값을 env.ini 에서 읽어 넣는다.
//
// 지정되지 않은 값은 빈칸으로 둔다. 0 을 적으면 "0도에서 경보" 로 읽혀
// 미지정과 구분되지 않는다.
void CDlg_Set_MmCam_Env::LoadAbsSettings()
{
	const std::string ini = StageIniPath();

	struct Item { CEdit* ed; const char* key; };
	const Item items[] = {
		{ &m_edAbsTempWarn,  "ABS_TEMP_WARN"  },
		{ &m_edAbsTempAlarm, "ABS_TEMP_ALARM" },
		{ &m_edAbsRiseWarn,  "ABS_RISE_WARN"  },
		{ &m_edAbsRiseAlarm, "ABS_RISE_ALARM" },
	};

	for (const Item& it : items)
	{
		const int v = ini_read_int_utf8(ini, "CONSTANTS", it.key, ABS_UNSET);
		CString s;
		if (v != ABS_UNSET) s.Format("%d", v);
		it.ed->SetWindowTextA(s);
	}
}

//---------------------------------------------------------

//---------------------------------------------------------
//---------------------------------------------------------
// 재학습 창을 띄운다.
//
// 버튼을 누르자마자 학습이 돌지 않는다. 운용 모델을 바꾸는 일이라
// 예행연습 결과를 먼저 보여 주고, 승격 판정이 난 경우에만 [진행] 이 열린다.
//---------------------------------------------------------

void CDlg_Set_MmCam_Env::OnBnClickedRetrain()
{
	if (gUserID.empty()) {
		m_cap_0.SetWindowTextA("[ERROR] 현장(user)이 선택되지 않았습니다.");
		return;
	}

	CDlg_Retrain dlg(this);
	dlg.DoModal();

	// 재학습이 끝났으면 세대·모델 시각이 바뀌었을 수 있다.
	LoadStageStatus();
}
