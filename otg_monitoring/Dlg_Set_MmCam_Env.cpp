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
#define ID_ED_BASE_DATE						2103
#define ID_BTN_SAVE_STAGE					2110

// 파이썬 쪽 기본값과 반드시 같아야 한다.
//   BASELINE_MIN_SAMPLES / BASELINE_MIN_HOURS : predict_machine/online_baseline.py
//   RETRAIN_MIN_SAMPLES                       : retrain/nightly_retrain.py
// 값이 없을 때 양쪽이 서로 다른 기본값을 쓰면, 화면에 보이는 숫자와 실제
// 동작이 어긋나면서 원인을 찾기 어려워진다.
#define DEF_BASE_SAMPLES	3000
#define DEF_BASE_HOURS		18
#define DEF_AE_SAMPLES		5000
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
		17,                         // 폰트 높이. 설정 항목이 늘어 25% 줄였다 (22 -> 17)
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

	// 폰트를 25% 줄였으므로 라벨 폭과 행 높이도 같이 줄인다.
	const long lbl_w = 155, ed_w = 80, row_h = 34;
	const long stage_top = ctrl_btn_top + ctrl_btn_hei + 16;
	long y = stage_top;

	m_capStage.Create("[ 연속학습 조건 ]",
		WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X, y, nBase_X + 520, y + 22), this);
	y += 26;

	struct Row { CStatic* lbl; CEdit* ed; const char* text; UINT id; };
	Row rows[] = {
		{ &m_lblBaseSamples, &m_edBaseSamples, "1단계 필터링 표본수",   ID_ED_BASE_SAMPLES },
		{ &m_lblBaseHours,   &m_edBaseHours,   "1단계 관측 시간",       ID_ED_BASE_HOURS     },
		{ &m_lblAeSamples,   &m_edAeSamples,   "2단계 필터링 표본수",   ID_ED_AE_SAMPLES    },
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
		CRect(nBase_X + lbl_w + 10, y, nBase_X + lbl_w + 10 + ed_w + 60, y + 22),
		this, ID_ED_BASE_DATE);

	// 지역 설정에 따라 표시 형식이 달라지면 env.ini 에 쓰는 값과 화면이
	// 어긋나 보인다. 저장 형식과 똑같이 맞춘다.
	m_dtBaseDate.SetFormat(_T("yyyy-MM-dd"));

	y += row_h;

	// 적용 버튼은 설정란 마지막 줄 아래, 라벨과 같은 왼쪽 끝에 둔다.
	// 오른쪽은 현황 열이 차지하므로 비워 두어야 한다.
	//
	// 캡션이 "적용" 인 이유: 파일에 쓰는 것으로 끝이 아니라 파이썬을 다시
	// 기동해야 실제로 반영된다. "저장" 이라고 하면 눌렀으니 됐다고 여기기
	// 쉽다.
	m_btnSaveStage.Create("연속학습 적용", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
		CRect(nBase_X, y + 4, nBase_X + 135, y + 4 + 24),
		this, ID_BTN_SAVE_STAGE);

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
	const long col2_x = nBase_X + 320;
	const long col2_w = 320;

	m_capNow.Create("[ 현재 진행 ]", WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(col2_x, stage_top, col2_x + col2_w, stage_top + 22), this);

	long ny = stage_top + 26;
	CStatic* stg[3] = { &m_lblStage1, &m_lblStage2, &m_lblStage3 };
	for (int i = 0; i < 3; ++i)
	{
		stg[i]->Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
			CRect(col2_x, ny, col2_x + col2_w, ny + 54), this);
		ny += 62;
	}

	LoadStageSettings();
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
// 이 파일이 없을 수 있다. 감시를 아직 한 번도 돌리지 않았거나, 기준선
// 저장 주기(200건)에 아직 도달하지 않은 경우다. 그때는 "확인 전" 으로
// 표시한다 — 0 건이라고 적으면 정말 0 건인 것과 구분이 안 된다.
void CDlg_Set_MmCam_Env::LoadStageStatus()
{
	const std::string st =
		std::string(GetMmCamStartPath()) + "users\\" + gUserID + "\\stage_status.ini";

	const std::string updated = ini_read_utf8(st, "STATUS", "UPDATED_AT", "");

	if (updated.empty()) {
		m_lblStage1.SetWindowTextA("1단계  확인 전\r\n    감시를 돌리면 표시됩니다");
		m_lblStage2.SetWindowTextA("2단계  확인 전");
		m_lblStage3.SetWindowTextA("3단계  확인 전");
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

	CStringA t;

	// 1단계 — 채점에 쓰이는 중인지까지 구분한다. 준비됐어도 2단계가 있으면
	// 둘이 함께 쓰이므로 "사용 중" 이 맞다.
	// 좁은 열에 맞추려고 두 줄로 적는다. 첫 줄은 상태, 둘째 줄은 근거.
	t.Format("1단계  %s\r\n    표본 %d/%d · 시간대 %d/%d",
		s1 ? "사용 중" : "누적 중", samples, min_smp, hours, min_hr);
	m_lblStage1.SetWindowTextA(t);

	t.Format("2단계  %s\r\n    %s",
		s2 ? "사용 중" : "없음",
		s2 ? "오토인코더 적재됨" : "모델 파일이 아직 없습니다");
	m_lblStage2.SetWindowTextA(t);

	if (s3 && !gen_at.empty())
		t.Format("3단계  적용됨\r\n    최근 승격 %s", gen_at.c_str());
	else if (db_rows >= 0 && min_rtr > 0)
		t.Format("3단계  대기\r\n    재학습 가능 %d/%d건", db_rows, min_rtr);
	else
		t.Format("3단계  대기\r\n    아직 재학습 이력이 없습니다");
	m_lblStage3.SetWindowTextA(t);

	// 기준일과 갱신 시각은 상단 안내줄에 함께 보여준다.
	CStringA head;
	head.Format("[%s]  기준일 %s  ·  현황 %s  ·  현재 채점 %s",
		gUserID.c_str(),
		bdate.empty() ? "전체" : bdate.c_str(),
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
		&& ini_write_utf8(ini, "CONSTANTS", "CALC_BASE_DATE", new_date);

	CStringA msg;
	if (ok) {
		// 파이썬 프로세스는 기동할 때 설정을 읽는다. 저장만으로는 반영되지 않는다.
		// 기준일이 바뀌면 기준선 누적을 버리고 처음부터 다시 쌓는다.
		// 며칠치 누적이 사라지는 일이라 화면에 분명히 알린다.
		const char* warn = (prev_date != new_date)
			? "  *기준일이 바뀌어 셀별 기준선을 새로 시작합니다*" : "";
		msg.Format("[적용 완료] 1단계 %d건/%d시간대, 2단계 %d건, 기준일 %s%s"
			"   -  '정지' 후 '시작'을 눌러야 반영됩니다.",
			base_samples, base_hours, ae_samples,
			new_date.empty() ? "전체" : new_date.c_str(), warn);
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

void CDlg_Set_MmCam_Env::RefreshAll()
{
	// 현장(콤보박스)이 바뀌었을 수도 있으므로 제목줄도 다시 만든다.
	LoadStageSettings();
	LoadStageStatus();
}

//---------------------------------------------------------