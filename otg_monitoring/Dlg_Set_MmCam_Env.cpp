// Dlg_Set_MmCam_Env.cpp: 구현 파일
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "Dlg_Set_MmCam_Env.h"
#include "afxdialogex.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_Retrain.h"
#include "Dlg_CellBase.h"
#include "Dlg_OpState.h"
#include "Dlg_BaseRef.h"
#include "Dlg_RetrainHist.h"
#include "Dlg_MaskFetch.h"

#include <vector>

extern const char* GetAnacondaRootPub();
extern const char* GetAnacondaEnvPub();

#include <wininet.h>
#pragma comment(lib, "wininet.lib")

// CDlg_Set_MmCam_Env 대화 상자

IMPLEMENT_DYNAMIC(CDlg_Set_MmCam_Env, CDialogEx)

extern const char* GetMmCamStartPath();

#define ID_BTN_GET_MASK_SVR				2010
#define ID_BTN_CLOSE							2000

// 연속 학습 단계 전환 조건
#define ID_ED_BASE_SAMPLES				2100
#define ID_ED_BASE_HOURS					2101
#define ID_ED_AE_SAMPLES					2102
#define ID_ED_AE_HOURS						2104
#define ID_BTN_SAVE_STAGE					2110
#define ID_BTN_RETRAIN						2205

// 1단계 절대 임계값
#define ID_ED_ABS_TEMP_W					2120
#define ID_ED_ABS_TEMP_A					2121
#define ID_ED_ABS_RISE_W					2122
#define ID_ED_ABS_RISE_A					2123

// 기여도 판단 기준
#define ID_ED_CT_WINDOW						2130
#define ID_ED_CT_MIN_FRAMES					2131
#define ID_ED_CT_MAX_SAMPLES				2132
#define ID_ED_CT_BAND_LOW					2133
#define ID_ED_CT_BAND_HIGH					2134

// 기여도 판단 기준의 기본값. model_contribution.py 의 것과 같아야 한다.
#define DEF_CT_WINDOW						7
#define DEF_CT_MIN_FRAMES					500
#define DEF_CT_MAX_SAMPLES					2000
#define DEF_CT_BAND_LOW						"0.20"
#define DEF_CT_BAND_HIGH					"0.85"

// 학습 표본 구성
// [현재 진행] 2단계 줄 옆의 작은 버튼. 칸별 기준값을 띄운다.
#define ID_BTN_CELLBASE						2150
#define ID_BTN_OPNAMES						2153
#define ID_BTN_GENMGR						2154
#define ID_BTN_BASEREF						2155
#define ID_BTN_RTHIST						2156
#define ID_BTN_BASE_FRESH					2151
#define ID_BTN_BASE_REBUILD					2152

#define ID_ED_SP_TARGET						2140
#define ID_ED_SP_RUNTEMP					2142
#define ID_CHK_SP_DYN						2144
#define ID_ED_SP_DAYS						2145
#define ID_CHK_DYN							2146

// DB 기간 조회 스레드가 끝났음을 알리는 메시지
#define WM_SPAN_DONE						(WM_APP + 41)

// 기본값. replay_buffer.py 의 것과 같아야 한다.
#define DEF_SP_TARGET						60000

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

extern std::string ini_read_utf8(const std::string&, const std::string&,
                                 const std::string&, const std::string&);
extern int  ini_read_int_utf8(const std::string&, const std::string&,
                              const std::string&, int);
extern long long status_age_seconds(const std::string&);
extern bool read_history_span(unsigned int timeoutSec, int* nTables,
                              std::string* first, std::string* last);

// 이 시간 안에 다시 쓰이지 않은 현황 파일은 감시가 멈춘 것으로 본다.
// 파이썬이 30초마다 쓰므로 두 번을 놓친 셈이다.
static const long long STATUS_STALE_SEC = 60;
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
	ON_BN_CLICKED(ID_BTN_GET_MASK_SVR, &CDlg_Set_MmCam_Env::OnBnClickedButtonGetMask)
	ON_BN_CLICKED(ID_BTN_CLOSE, &CDlg_Set_MmCam_Env::OnBnClickedClose)
	ON_BN_CLICKED(ID_BTN_SAVE_STAGE, &CDlg_Set_MmCam_Env::OnBnClickedSaveStage)
	ON_BN_CLICKED(ID_BTN_RETRAIN, &CDlg_Set_MmCam_Env::OnBnClickedRetrain)
	ON_BN_CLICKED(ID_BTN_CELLBASE, &CDlg_Set_MmCam_Env::OnBnClickedCellBase)
	ON_BN_CLICKED(ID_BTN_OPNAMES, &CDlg_Set_MmCam_Env::OnBnClickedOpNames)
	ON_BN_CLICKED(ID_BTN_GENMGR, &CDlg_Set_MmCam_Env::OnBnClickedGenMgr)
	ON_BN_CLICKED(ID_BTN_BASEREF, &CDlg_Set_MmCam_Env::OnBnClickedBaseRef)
	ON_BN_CLICKED(ID_BTN_RTHIST, &CDlg_Set_MmCam_Env::OnBnClickedRetrainHist)
	ON_BN_CLICKED(ID_BTN_BASE_FRESH, &CDlg_Set_MmCam_Env::OnBnClickedBaseFresh)
	ON_BN_CLICKED(ID_BTN_BASE_REBUILD, &CDlg_Set_MmCam_Env::OnBnClickedBaseRebuild)
	ON_WM_CTLCOLOR()
	ON_MESSAGE(WM_SPAN_DONE, &CDlg_Set_MmCam_Env::OnSpanDone)
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
	// 처럼 보였다. 실제로는 하나는 감시 대상(어느 셀을 볼지)을 관제서버 것으로
	// 갈아치우고, 다른 하나는 같은 선택을 카메라가 밀린 만큼 옮긴다.
	// 전혀 다른 일이다.
	//
	// 너비는 250 -> 141 로 줄였다. 글꼴은 다른 컨트롤과 같은 크기를 쓴다.
	//
	// 그 폭에 들어가도록 이름을 줄였다. 긴 이름을 두 줄로 접어 보았더니
	// 좁아진 대신 높아져 오히려 커 보였다. 한 줄에 들어가는 길이로 맞추고
	// 자세한 내용은 누른 뒤 안내 문구로 설명한다.
	//
	//   서버에서 Mask 받기            -> 서버 Mask 받기 -> 관제서버 분석마스크 받기
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

		// 머리줄(현황 · [저장 완료] 같은 알림)은 두 줄까지 쓴다. .rc 의 자리(위 15 ·
		// 높이 34)로는 둘째 줄이 이 구분선에 걸려 잘렸다. 조금 올리고 선 바로 위까지 늘린다.
		if (m_cap_0.GetSafeHwnd())
			m_cap_0.SetWindowPos(NULL, nBase_X + 2, 4, sepRight - nBase_X - 2,
				(ctrl_btn_top - 12) - 4, SWP_NOZORDER | SWP_NOACTIVATE);
	}

	// 맨 윗줄은 "카메라가 지금 어떤가" 하나로 묶는다.
	//
	// 잰 값이 왼쪽, 손볼 버튼이 오른쪽이다. [관제서버 분석마스크 받기] 는 감시 대상을
	// 관제서버 것으로 갈아치우는 전혀 다른 일이라 맨 아래로 내렸다.
	long topRight;
	{
		CRect rcC;
		GetClientRect(&rcC);
		topRight = rcC.right - nBase_X;
		if (topRight < nBase_X + 520) topRight = nBase_X + 520;
	}

	// 이 버튼은 높이가 30% 작다. 다른 버튼과 줄을 맞추는 자리가 아니라, 잰 값
	// 옆에 붙어 "이걸 손본다" 는 뜻으로 서 있기 때문이다.
	const long cam_w = btn_w * 92 / 100;          // 141 -> 129 ("기준 이미지 변경" 이 들어갈 폭)
	const long cam_h = mask_btn_h * 70 / 100;     // 30 -> 21

	// [기준 이미지]. RGB 틀어짐을 재는 잣대(base_ref.png)를 지금 화면과 견주어
	// 보고, 사람이 확인한 뒤에만 바꾼다.
	//
	// 이 자리에 있던 [카메라 보정] 은 2026-10-08 에 뺐다. 승인해 두면 다음 기동 때
	// 틀어진 만큼 마스크를 저절로 옮기고 기준 이미지까지 갈아 치웠다. 사람이 보지
	// 않는 순간에 감시 대상이 바뀌는 것은 너무 민감하다.
	m_btnBaseRef.Create("기준 이미지 변경", mask_btn_style,
		CRect(topRight - cam_w, ctrl_btn_top,
		      topRight, ctrl_btn_top + cam_h),
		this, ID_BTN_BASEREF);

	// 잰 틀어짐 값. 계산은 이미 하고 있었는데 화면에 나오지 않아, 지금
	// 밀려 있는지 알 길이 없었다.
	//
	// 두 줄인 이유는 재는 대상이 둘이기 때문이다. 위는 RGB, 아래는 열화상.
	// 한 줄로 합치면 어느 카메라가 밀렸는지가 사라지는데, 바로 그 구분이
	// kict1 에서 두 달을 놓치게 만든 지점이었다.
	m_lblShift.Create("", WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X, ctrl_btn_top - 1,
		      topRight - cam_w - 14, ctrl_btn_top - 1 + 56), this);

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
	// [카메라 위치 이동] 줄을 맨 아래로 내렸으므로 설정 영역은 머리줄 구분선 바로
	// 아래에서 시작한다.
	const long stage_top = ctrl_btn_top + 8;
	long y = stage_top;


	// 두 칸으로 가른다.
	//
	// 한 칸에 2단계 관문과 재학습 관문이 섞여 있었고, 이름은 '연속학습
	// 조건' 이라 전체 구조의 이름을 한 칸에 붙인 꼴이었다. 나머지 세
	// 묶음은 저마다 하는 일을 말하는데 여기만 포괄적이었다.
	struct Row { CStatic* lbl; CEdit* ed; const char* text; UINT id; };

	auto drawRows = [&](const Row* rr, int n)
	{
		for (int i = 0; i < n; ++i)
		{
			rr[i].lbl->Create(rr[i].text, WS_CHILD | WS_VISIBLE | SS_LEFT,
				CRect(nBase_X, y + 3, nBase_X + lbl_w, y + 3 + 20), this);

			rr[i].ed->Create(WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP
				| ES_NUMBER | ES_RIGHT,
				CRect(nBase_X + lbl_w + 10, y, nBase_X + lbl_w + 10 + ed_w,
				      y + 22), this, rr[i].id);

			y += row_h;
		}
	};

	// -------------------------------------------------------------
	// 1단계 절대 임계값
	//
	// 맨 위에 둔다. 학습과 무관하게 늘 동작하는 유일한 안전망이라,
	// 2·3단계가 아직 서지 않은 현장에서는 이것만이 경보를 낸다.
	// 아래쪽에 두었더니 설치할 때 지나치기 쉬웠다.
	//
	// 설비마다 값이 전혀 다르다.
	// kict1 은 정상 가동 중 격자 최고가 197도까지 오르고, cj_busan_1 은
	// 정상 가동의 99%가 12도/분을 넘는다. 추측한 기본값은 쉬지 않고 경보를
	// 울리므로 현장에서 직접 넣어야 한다.
	//
	// 주의와 경보를 한 줄에 둘씩 묶어 두 줄로 줄였다. 넷을 따로 늘어놓으면
	// 설정 영역이 지나치게 길어진다.
	// -------------------------------------------------------------
	// 왼쪽 열 구역 제목의 폭. 오른쪽 [현재 진행] 열(col2_x = nBase_X + 360) 앞에서
	// 끊는다. 520 으로 두었더니 오른쪽 칸 글상자와 겹쳐 그 윗줄을 가렸다.
	const long CAP_W = 355;
	const long ed2_w = 70;
	const long ed2_x1 = nBase_X + lbl_w + 10;
	const long ed2_x2 = ed2_x1 + ed2_w + 10;

	m_capAbs.Create("[ 1단계 절대 임계값 ]   주의 / 경보",
		WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X, y, nBase_X + 330, y + 22), this);
	y += 26;

	struct ARow { CStatic* lbl; CEdit* w; CEdit* a; const char* text; UINT idw; UINT ida; };
	ARow arows[] = {
		{ &m_lblAbsTemp, &m_edAbsTempWarn, &m_edAbsTempAlarm,
		  "격자 최고 온도 (도)", ID_ED_ABS_TEMP_W, ID_ED_ABS_TEMP_A },
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

	y += 10;

	m_capStage.Create("[ 2단계 전환 조건 ]   경험 임계값으로 채점을 시작할 때",
		WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X, y, nBase_X + CAP_W, y + 22), this);
	y += 26;

	Row rows1[] = {
		{ &m_lblBaseSamples, &m_edBaseSamples, "기준선 최소 표본수", ID_ED_BASE_SAMPLES },
		{ &m_lblBaseHours,   &m_edBaseHours,   "기준선 최소 시간대", ID_ED_BASE_HOURS   },
	};
	drawRows(rows1, 2);

	y += 10;

	// -------------------------------------------------------------
	// 기여도 판단 기준
	//
	// "지금 이 모델이 몇 점을 내고 있는가" 를 재는 방법이다. 그 점수로
	// 재학습이 기존 가중치를 얼마나 물려받을지(기여 w) 정한다.
	//
	//   테이블 N개 -> 셋을 거름 -> 표본 M건 -> 지금 모델로 다시 매김
	//   -> 중앙값 -> w = (점수 - 하) / (상 - 하)
	//
	// 아래 [재생 버퍼] 와 헷갈리기 쉬운데 다른 것이다. 저쪽은 '무엇으로
	// 학습할지', 이쪽은 '기존 모델을 믿을지' 다. 여기서 나온 w 를 아래
	// 재생버퍼 동적구성과 기여 문턱이 쓴다.
	//
	// 판단 최소 일수를 화면에 올린 이유가 있다. 짧으면 설비 상태를 골고루 담지
	// 못한다. cj_busan_1 을 테이블 2개로 재 보니 가동 프레임이 0.3% 뿐이라,
	// 0.922 라는 점수가 사실은 "멈춘 설비를 잘 맞힌다" 는 뜻이었다. 7개로
	// 늘리면 가동이 74.7% 가 된다. 현장 가동 주기에 따라 달라지는 값이라
	// 코드에 박아 둘 수 없다.
	// -------------------------------------------------------------
	m_capContrib.Create("[ 3단계·기여도 ]   현 모델이 최근 데이터를 잘 측정하는지",
		WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X, y, nBase_X + CAP_W, y + 22), this);
	y += 26;

	{
		const DWORD est_n = WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP
			| ES_NUMBER | ES_RIGHT;

		m_lblCtWindow.Create("판단 최소 일수",
			WS_CHILD | WS_VISIBLE | SS_LEFT,
			CRect(nBase_X, y + 3, nBase_X + lbl_w, y + 3 + 20), this);
		m_edCtWindow.Create(est_n,
			CRect(ed2_x1, y, ed2_x1 + ed2_w, y + 22), this, ID_ED_CT_WINDOW);
		y += row_h;

		m_lblCtFrames.Create("표본 수 (최소 / 최대)",
			WS_CHILD | WS_VISIBLE | SS_LEFT,
			CRect(nBase_X, y + 3, nBase_X + lbl_w, y + 3 + 20), this);
		m_edCtMinFrames.Create(est_n,
			CRect(ed2_x1, y, ed2_x1 + ed2_w, y + 22), this, ID_ED_CT_MIN_FRAMES);
		m_edCtMaxSamples.Create(est_n,
			CRect(ed2_x2, y, ed2_x2 + ed2_w, y + 22), this, ID_ED_CT_MAX_SAMPLES);
		y += row_h;

		// 지금 모델의 기여도와 그것을 계산한 일시. 입력하는 값이 아니라 감시가 구해 둔
		// 결과라 읽기 전용으로 입력칸 바로 아래에 둔다(LoadStageStatus 가 고친다).
		m_lblCtStatus.Create("기여도 점수   계산 전",
			WS_CHILD | WS_VISIBLE | SS_LEFT,
			CRect(nBase_X, y + 3, nBase_X + 340, y + 3 + 70), this);
		y += 74;
	}

	y += 10;

	m_capStage2.Create("[ 3단계·재생 버퍼 ]   재학습이 무엇을 모아 배울지",
		WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X, y, nBase_X + CAP_W, y + 22), this);
	y += 26;

	Row rows2[] = {
		{ &m_lblAeSamples, &m_edAeSamples, "재학습 최소 표본수", ID_ED_AE_SAMPLES },
		{ &m_lblSpTarget,  &m_edSpTarget,  "재학습 최대 표본 수", ID_ED_SP_TARGET },
		{ &m_lblSpDays,    &m_edSpDays,    "재학습 수집 일수", ID_ED_SP_DAYS },
		{ &m_lblAeHours,   &m_edAeHours,   "재학습 최소 시간대", ID_ED_AE_HOURS   },
	};
	drawRows(rows2, 3);

	// 수집 일수 바로 아래에 뜻과 DB 전체 기간을 적는다. 0 이 "수집하지 않음" 으로
	// 읽히기 쉽고, 지금 DB 가 며칠치인지 알아야 일수를 정할 수 있다. 값은 감시가
	// 남기는 stage_status.ini 에서 읽어 2초마다 고친다(LoadStageStatus).
	m_lblSpDaysHint.Create("0 = 전체",
		WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(nBase_X + 24, y - 8, nBase_X + 24 + 340, y - 8 + 20), this);
	y += 16;
	drawRows(rows2 + 3, 1);

	// 재생버퍼 동적구성과 기여 문턱. [재학습] 창에 있던 것을 재학습 조건과 한자리에
	// 모았다. [설정 저장] 으로 함께 저장한다.
	//
	// 기여 문턱은 기여 w 를 정한다. w 는 동적구성을 켰을 때 옛/새 표본 비율을 정하고,
	// 자동 재학습을 켰을 때는 돌릴지를 정한다(w < 1.00).
	m_chkDyn.Create("재생버퍼 동적구성 [ w : 1-w ]",
		WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_AUTOCHECKBOX,
		CRect(nBase_X, y + 2, nBase_X + CAP_W, y + 2 + 22), this, ID_CHK_DYN);
	y += row_h;
	{
		const DWORD est_f = WS_CHILD | WS_VISIBLE | WS_BORDER | WS_TABSTOP | ES_RIGHT;
		m_lblBand.Create("기여 문턱 w (상 / 하)", WS_CHILD | WS_VISIBLE | SS_LEFT,
			CRect(nBase_X, y + 3, nBase_X + lbl_w, y + 3 + 20), this);
		m_edBandHigh.Create(est_f, CRect(ed2_x1, y, ed2_x1 + ed2_w, y + 22), this,
			ID_ED_CT_BAND_HIGH);
		m_edBandLow.Create(est_f, CRect(ed2_x2, y, ed2_x2 + ed2_w, y + 22), this,
			ID_ED_CT_BAND_LOW);
		y += row_h;
	}

	// -------------------------------------------------------------
	// 재생 버퍼 (이어서)
	//
	// 위 네 줄에 이어 재생 버퍼를 어떻게 구성할지를 정한다. 기여도(아래 패널)는
	// '기존 모델을 믿을지' 이고 여기는 '무엇으로 학습할지' 다.
	//
	// 정상 판정선(모델 점수)은 두지 않는다. 모델이 못 배운 정상 상태와
	// 진짜 이상을 구분하지 못해, 모델이 틀린 자리가 표본에서 빠지고 다음
	// 세대도 똑같이 틀렸다. 이제 절대 임계값과 칸별 분위수로 거른다.
	// -------------------------------------------------------------
	y += 10;

	// 적용 버튼 하나로 네 묶음을 함께 저장한다.
	//
	// 처음에는 묶음마다 버튼을 두었는데, 화면에 적용 버튼이 둘이면 어느
	// 것을 눌러야 하는지 매번 판단해야 하고 한쪽만 누르고 끝내기도 쉽다.
	//
	// 파일에 쓰는 것으로 끝이 아니라 파이썬을 다시 기동해야 실제로 반영된다.
	m_btnSaveStage.Create("설정 저장", WS_CHILD | WS_VISIBLE | WS_TABSTOP | BS_PUSHBUTTON,
		CRect(nBase_X, y + 6, nBase_X + btn_w, y + 6 + 26),
		this, ID_BTN_SAVE_STAGE);

	// 관제서버 분석마스크 받기.
	//
	// 맨 윗줄에 [카메라 이동보정] 과 나란히 있었는데, 둘은 하는 일이
	// 전혀 다르다. 저쪽은 같은 선택을 밀린 만큼 옮기는 것이고, 이쪽은
	// 감시 대상(어느 칸을 볼지) 자체를 관제서버 것으로 갈아치운다. 자주
	// 누를 일도 아니라 맨 아래로 내렸다.
	//
	// 이름이 "관제서버 분석마스크 받기" 로 길어져 다른 버튼 너비(btn_w)에 들어가지
	// 않는다. 이 버튼만 글자 폭에 맞춰 넓힌다. 오른쪽은 비어 있다.
	{
		const CStringA cap = "관제서버 분석마스크 받기";
		long w = btn_w;
		{
			CClientDC dc(this);
			CFont* old = dc.SelectObject(&m_stdFont);
			const long need = dc.GetTextExtent(CString(cap)).cx + 28;
			if (old) dc.SelectObject(old);
			if (need > w) w = need;
		}
		m_btnGetMask_Server.Create(cap, mask_btn_style | WS_TABSTOP,
			CRect(nBase_X + btn_w + 10, y + 6,
			      nBase_X + btn_w + 10 + w, y + 6 + 26),
			this, ID_BTN_GET_MASK_SVR);
	}

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

	// 이 영역이 실제로 필요로 하는 높이. 메인 창이 고정값 대신 이 값으로 펼친다.
	// 항목을 늘릴 때마다 고정값을 고쳐야 했고, 잊으면 맨 아래 버튼이 잘렸다.
	m_nContentH = (int)(y + 44 + 12);

	// -------------------------------------------------------------
	// 현재 진행 상황 — 설정란 오른편
	//
	// 설정값만 보여주면 "그래서 지금 몇 단계인가" 를 알 수 없다. 조건과
	// 진행 상황을 나란히 두어 한눈에 비교하게 한다.
	//
	// 메인 창 너비가 678 이라 오른편에 300 남짓 쓸 수 있다. 그런데
	// "2단계 사용 중  표본 12,345/3,000 · 시간대 20/18" 은 한 줄로 400 이
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

	// 1~3단계, 곧 "지금 무엇으로 채점할 수 있는가" 를 적는다.
	m_capNow.Create("[ 현재 진행 ]", WS_CHILD | WS_VISIBLE | SS_LEFT,
		CRect(col2_x, stage_top, col2_x + col2_w, stage_top + 22), this);

	// 1단계(절대 임계값)도 늘 동작하므로 함께 보여준다.
	long ny = stage_top + 26;
	CStatic* stg[3] = { &m_lblStage0, &m_lblStage1, &m_lblStage2 };
	// 칸마다 줄 수가 다르다. 한 값으로 두면 긴 칸의 마지막 줄이 잘린다.
	//
	//   0 절대임계값   제목 · 온도/상승률 · 지금 잰 값     3줄
	//   1 경험임계값   제목 · 표본/시간대 · 언제부터 왜    4줄 (사유가 접힌다)
	//   2 오토인코더   제목 · 세대 · 모델 파일 시각        3줄
	//
	// 연속학습과 운전 상태는 메인 창 위에 이미 나오므로 여기에 다시 적지 않는다.
	// 운전 상태 이름을 고치는 [운전상태명 변경] 버튼만 맨 아래에 둔다.
	static const long STAGE_H[3] = { 78, 102, 78 };
	const long STAGE1_TEXT_H = 68;       // 2단계 글상자 높이(세 줄). 나머지는 버튼 줄(위 0 · 아래 8)
	const long STAGE_GAP = 8;

	// 단계마다 등을 하나씩 단다.
	//
	// 세 칸의 글 시작 자리는 모두 같은 만큼 밀어 줄을 맞춘다.
	const long LAMP_W = 20;
	long stage1_y = ny;

	for (int i = 0; i < 3; ++i)
	{
		m_lampStage[i].Create("●", WS_CHILD | WS_VISIBLE | SS_LEFT,
			CRect(col2_x, ny - 1, col2_x + LAMP_W, ny + 21), this);

		if (i == 1) stage1_y = ny;      // 버튼은 글상자 뒤에 만든다

		// 2단계 글상자는 첫 줄 끝 버튼([임계값]) 자리까지 넓다.
		// 글상자가 먼저 만들어져 z 순서가 버튼보다 위라, 그대로 두면 글을 고칠 때마다 버튼을
		// 덮어 칠했다(버튼 윗변 2px 만 남았다). WS_CLIPSIBLINGS 로 위에 올린 버튼 자리를 비켜
		// 칠하게 하고, 글상자는 z 순서 맨 아래로 내린다. 글상자는 탭으로 가지 않으므로 버튼의
		// 탭 순서는 그대로다.
		stg[i]->Create("", WS_CHILD | WS_VISIBLE | WS_CLIPSIBLINGS | SS_LEFT,
			CRect(col2_x + LAMP_W, ny, col2_x + col2_w,
				ny + (i == 1 ? STAGE1_TEXT_H : STAGE_H[i])), this);
		ny += STAGE_H[i] + STAGE_GAP;
	}

	// 버튼 네 줄. [운전상태명 변경] · [학습모델관리] · [자동학습 관리] · [재학습 관리].
	const long opstate_y = ny;
	ny += 26 + STAGE_GAP;
	const long genmgr_y = ny;
	ny += 26 + STAGE_GAP;
	const long rthist_y = ny;
	ny += 26 + STAGE_GAP;
	const long retrain_y = ny;
	ny += 26 + STAGE_GAP;

	// 2단계 줄 끝에 칸별 기준값을 여는 작은 버튼.
	//
	// 이 칸은 표본 수밖에 말하지 못한다. "어느 칸이 선에 가까운가" 는
	// 격자로 봐야 하는데, 좁은 칸에 64개를 넣을 수는 없다.
	//
	// 글상자는 위에서 z 순서 맨 아래로 내렸고 WS_CLIPSIBLINGS 라 이 버튼을 덮지 않는다.
	{
		const long bw = 64;
		m_btnCellBase.Create("임계값", WS_CHILD | WS_VISIBLE | WS_TABSTOP
			| BS_PUSHBUTTON,
			CRect(col2_x + col2_w - bw, stage1_y - 2,
			      col2_x + col2_w, stage1_y + 20), this, ID_BTN_CELLBASE);

		// 경험 임계값을 손으로 다시 세우는 두 가지 길. 2단계 글 바로 아래에 둔다.
		//
		// 둘 다 쓰던 것을 _retired_baseline 으로 옮기므로 되돌릴 수 있지만,
		// 감시가 돌고 있으면 메모리에 든 기준선이 200건마다 다시 저장되어
		// 고친 것을 덮어쓴다. 눌렀을 때 그 상태면 막는다.
		const long bw1 = 118, bw2 = 128, gap = 8;
		const long bx = col2_x + LAMP_W;
		const long by = stage1_y + STAGE1_TEXT_H;

		m_btnBaseFresh.Create("현재부터쌓기", WS_CHILD | WS_VISIBLE | WS_TABSTOP
			| BS_PUSHBUTTON, CRect(bx, by, bx + bw1, by + 26), this,
			ID_BTN_BASE_FRESH);

		m_btnBaseRebuild.Create("DB에서되쌓기", WS_CHILD | WS_VISIBLE | WS_TABSTOP
			| BS_PUSHBUTTON,
			CRect(bx + bw1 + gap, by, bx + bw1 + gap + bw2, by + 26), this,
			ID_BTN_BASE_REBUILD);

		// 운전 상태 이름을 고치는 버튼. 글 칸들과 같은 자리에서 시작한다.
		// 이름은 스크립트가 온도 순서로 붙인 짐작이라 설비를 아는 사람이 고친다.
		const long bwn = 144;
		m_btnOpNames.Create("운전상태명 변경", WS_CHILD | WS_VISIBLE | WS_TABSTOP
			| BS_PUSHBUTTON,
			CRect(bx, opstate_y, bx + bwn, opstate_y + 26), this, ID_BTN_OPNAMES);

		// 보관된 학습모델(세대)을 골라 되돌리거나 지운다. [운전상태명 변경] 과 같은 꼴.
		m_btnGenMgr.Create("학습모델관리", WS_CHILD | WS_VISIBLE | WS_TABSTOP
			| BS_PUSHBUTTON,
			CRect(bx, genmgr_y, bx + bwn, genmgr_y + 26), this, ID_BTN_GENMGR);

		// 자동 재학습 이력. 판단 점수 · w · 결과를 최근 것부터 모두 본다. 같은 꼴.
		m_btnRetrainHist.Create("자동학습 관리", WS_CHILD | WS_VISIBLE | WS_TABSTOP
			| BS_PUSHBUTTON,
			CRect(bx, rthist_y, bx + bwn, rthist_y + 26), this, ID_BTN_RTHIST);

		// [재학습]. 학습모델 · 이력과 한 무리라 그 아래에 둔다. 운용 모델을 바꾸는
		// 일이라 여기서 바로 돌리지 않고 창을 띄워 예행연습 결과를 먼저 보여 준다.
		m_btnRetrain.Create("재학습 관리", WS_CHILD | WS_VISIBLE | WS_TABSTOP
			| BS_PUSHBUTTON,
			CRect(bx, retrain_y, bx + bwn, retrain_y + 26), this, ID_BTN_RETRAIN);
	}

	// 글상자를 z 순서 맨 아래로. 버튼을 다 만든 뒤에 해야 한다 - 자식 창은 만든
	// 순서대로 아래에 쌓여서, 먼저 내려 두면 뒤에 만든 버튼이 다시 그 밑으로 간다.
	for (int i = 0; i < 3; ++i)
		stg[i]->SetWindowPos(&CWnd::wndBottom, 0, 0, 0, 0,
			SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE);

	LoadStageSettings();
	LoadAbsSettings();
	LoadContribSettings();
	LoadSampleSettings();
	// 오른쪽 열이 왼쪽 입력 열보다 길면 아래 구분선이 열을 가로지른다.
	{
		const long need = ny + 4;
		CRect rs;
		m_sepBottom.GetWindowRect(&rs);
		ScreenToClient(&rs);
		if (rs.top < need)
		{
			m_sepBottom.SetWindowPos(NULL, rs.left, need, rs.Width(), rs.Height(),
				SWP_NOZORDER);
			m_nContentH = (int)(need + 2 + 12);
		}
	}

	// [카메라 위치 이동] 줄은 맨 아래, [설정 저장] 줄과 그 아래 구분선보다 밑에 둔다.
	//
	// 설정할 값이 아니라 지금 상태를 알리는 줄이고, 손볼 일([기준 이미지 변경])도
	// 드물다. 맨 위에 있으면 설정을 고치러 온 사람의 눈을 먼저 잡는다. 구분선이
	// 오른쪽 열 길이에 따라 내려갈 수 있어, 그 위치가 정해진 뒤에 놓는다.
	{
		CRect rs;
		m_sepBottom.GetWindowRect(&rs);
		ScreenToClient(&rs);
		const long sy = rs.bottom + 10;

		CRect rl, rb;
		m_lblShift.GetWindowRect(&rl);
		ScreenToClient(&rl);
		m_btnBaseRef.GetWindowRect(&rb);
		ScreenToClient(&rb);
		m_lblShift.SetWindowPos(NULL, rl.left, sy, rl.Width(), rl.Height(),
			SWP_NOZORDER | SWP_NOACTIVATE);
		m_btnBaseRef.SetWindowPos(NULL, rb.left, sy + 1, rb.Width(), rb.Height(),
			SWP_NOZORDER | SWP_NOACTIVATE);

		m_nContentH = (int)(sy + rl.Height() + 4);
	}

	LoadStageStatus();

	// 다이알로그와 하위개체까지 Font 지정 효과 전달하기 위함
	SendMessageToDescendants(WM_SETFONT, (WPARAM)m_stdFont.GetSafeHandle(), TRUE);

	return TRUE;  // return TRUE unless you set the focus to a control
}

//---------------------------------------------------------

// 현황 파일의 UTF-8 한글을 화면 부호(CP_ACP)로 옮긴다.
//
// stage_status.ini 는 UTF-8 이고 이 빌드는 MBCS 다. ini_read_utf8 은 파일
// 바이트를 그대로 돌려주므로, 숫자·날짜·세대 이름처럼 ASCII 인 값은 문제가
// 없었다. 운전 상태가 그 파일에서 읽는 첫 한글이다.
static CStringA StatusUtf8(const std::string& u)
{
	if (u.empty()) return CStringA();

	const int wn = MultiByteToWideChar(CP_UTF8, 0, u.c_str(), -1, nullptr, 0);
	if (wn <= 0) return CStringA(u.c_str());     // UTF-8 이 아니면 그대로

	CStringW w;
	MultiByteToWideChar(CP_UTF8, 0, u.c_str(), -1, w.GetBuffer(wn), wn);
	w.ReleaseBuffer();

	const int an = WideCharToMultiByte(CP_ACP, 0, w, -1, nullptr, 0,
		nullptr, nullptr);
	if (an <= 0) return CStringA(u.c_str());

	CStringA a;
	WideCharToMultiByte(CP_ACP, 0, w, -1, a.GetBuffer(an), an, nullptr, nullptr);
	a.ReleaseBuffer();
	return a;
}

// 글이 그대로면 다시 쓰지 않는다.
//
// [현재 진행] 은 2초마다 다시 읽는다. 값이 같은데도 매번 쓰면 글자가
// 쉬지 않고 깜빡여 읽을 수 없다.
static void SetIfChanged(CStatic& w, const CStringA& s)
{
	if (!w.GetSafeHwnd()) return;

	CString cur;
	w.GetWindowText(cur);
	if (cur.Compare(s) != 0) w.SetWindowTextA(s);
}

// 단계 등의 색.
//
// 메인 창 현장 콤보 앞의 표식과 같은 색을 쓴다. 두 화면이 다른 색으로
// 같은 말을 하면 하나를 더 외워야 한다.
HBRUSH CDlg_Set_MmCam_Env::OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor)
{
	HBRUSH hbr = CDialogEx::OnCtlColor(pDC, pWnd, nCtlColor);

	// [카메라 위치 이동] 줄은 이동이 있을 때 적색으로 적는다. 맨 아래에 있어
	// 눈에 덜 띈다.
	if (m_shiftAlert && m_lblShift.GetSafeHwnd() &&
		pWnd->GetSafeHwnd() == m_lblShift.GetSafeHwnd())
	{
		pDC->SetTextColor(RGB(220, 0, 0));
		return hbr;
	}

	for (int i = 0; i < 3; ++i)
	{
		if (!m_lampStage[i].GetSafeHwnd()) continue;
		if (pWnd->GetSafeHwnd() != m_lampStage[i].GetSafeHwnd()) continue;

		COLORREF c;
		switch (m_lampLevel[i])
		{
		case 2:  c = RGB(0, 180, 0);     break;   // 사용 중
		case 1:  c = RGB(255, 200, 0);   break;   // 준비 중
		default: c = RGB(170, 170, 170); break;   // 꺼짐 · 확인 전
		}
		pDC->SetTextColor(c);
		pDC->SetBkMode(TRANSPARENT);
		return (HBRUSH)GetStockObject(NULL_BRUSH);
	}
	return hbr;
}

// [카메라 위치 이동] 줄의 적색 여부. 달라졌을 때만 다시 그린다.
void CDlg_Set_MmCam_Env::SetShiftAlert(bool on)
{
	if (m_shiftAlert == on) return;
	m_shiftAlert = on;
	if (m_lblShift.GetSafeHwnd()) m_lblShift.Invalidate();
}

// 등을 새 값으로 바꾼다. 달라졌을 때만 다시 그린다 - 2초마다 부르므로
// 그냥 Invalidate 하면 쉬지 않고 깜빡인다.
static void SetLamp(CStatic& w, int& cur, int want)
{
	if (cur == want) return;
	cur = want;
	if (w.GetSafeHwnd()) w.Invalidate();
}

std::string CDlg_Set_MmCam_Env::StageIniPath() const
{
	return std::string(GetMmCamStartPath()) + "users\\" + gUserID + "\\env.ini";
}

// 연속학습 설정 파일. 이 창이 읽고 쓰는 값은 모두 여기로 간다.
//
// env.ini 에는 설치할 때 한 번 정하는 값(카메라 해상도, DB 이름, 경로)만
// 남긴다. 성격이 다른 둘이 한 파일에 있으면 현장에서 무엇을 만져도 되는지
// 알기 어렵다.
std::string CDlg_Set_MmCam_Env::LearnIniPath() const
{
	return std::string(GetMmCamStartPath()) + "users\\" + gUserID
		+ "\\continual_learning.ini";
}

// continual_learning.ini 에서 읽고, 없으면 env.ini 에서 찾는다.
//
// 현장 분석서버가 아직 옮기기 전일 수 있다. 그때 기본값으로 떨어지면 화면에
// 엉뚱한 값이 뜨고, 그대로 [설정 저장] 을 누르면 실제 설정이 바뀐다.
std::string CDlg_Set_MmCam_Env::LearnRead(const char* key,
                                          const char* def) const
{
	// 있는지 없는지를 가리려고 아무도 쓰지 않을 값을 기본으로 넣는다.
	static const char* MISSING = "\x01";
	const std::string v = ini_read_utf8(LearnIniPath(), "CONSTANTS", key, MISSING);
	if (v != MISSING) return v;
	return ini_read_utf8(StageIniPath(), "CONSTANTS", key, def);
}

int CDlg_Set_MmCam_Env::LearnReadInt(const char* key, int def) const
{
	const std::string v = LearnRead(key, "");
	if (v.empty()) return def;
	try { return std::stoi(v); }
	catch (...) { return def; }
}

//---------------------------------------------------------

void CDlg_Set_MmCam_Env::LoadStageSettings()
{
	CString s;
	s.Format("%d", LearnReadInt("BASELINE_MIN_SAMPLES", DEF_BASE_SAMPLES));
	m_edBaseSamples.SetWindowTextA(s);

	s.Format("%d", LearnReadInt("BASELINE_MIN_HOURS", DEF_BASE_HOURS));
	m_edBaseHours.SetWindowTextA(s);

	s.Format("%d", LearnReadInt("RETRAIN_MIN_SAMPLES", DEF_AE_SAMPLES));
	m_edAeSamples.SetWindowTextA(s);

	s.Format("%d", LearnReadInt("RETRAIN_MIN_HOURS", DEF_AE_HOURS));
	m_edAeHours.SetWindowTextA(s);
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
// 2단계 글 바로 아래에 [현재부터쌓기] [DB에서되쌓기] 를 붙인다. 글이 두 줄일 때와 세 줄일
// 때 높이가 달라, 고정 위치로 두면 짧은 쪽에서 위 여백이 커진다.
static void PlaceBaseButtons(CWnd* parent, CStatic& lbl, CButton& b1, CButton& b2)
{
	if (!lbl.GetSafeHwnd() || !b1.GetSafeHwnd() || !b2.GetSafeHwnd()) return;

	CString txt;
	lbl.GetWindowText(txt);
	CRect rc;
	lbl.GetClientRect(&rc);

	int textH;
	{
		CClientDC dc(&lbl);
		CFont* f = lbl.GetFont();
		CFont* old = f ? dc.SelectObject(f) : NULL;
		CRect m(0, 0, rc.Width(), 0);
		dc.DrawText(txt, &m, DT_CALCRECT | DT_WORDBREAK | DT_NOPREFIX);
		textH = m.Height();
		if (old) dc.SelectObject(old);
	}

	CRect rl;
	lbl.GetWindowRect(&rl);
	parent->ScreenToClient(&rl);

	// 글상자를 글 높이로 줄인다. 글상자가 버튼보다 먼저 만들어져 z 순서가 위라,
	// 고정 높이(68)로 두면 글이 짧을 때 버튼 위로 겹쳐 글을 고칠 때마다 버튼을 덮었다.
	if (rl.Height() != textH)
	{
		lbl.SetWindowPos(NULL, 0, 0, rl.Width(), textH,
			SWP_NOMOVE | SWP_NOZORDER);
		parent->InvalidateRect(CRect(rl.left, rl.top + min(textH, rl.Height()),
			rl.right, rl.top + max(textH, rl.Height()) + 30));
	}

	CButton* bs[2] = { &b1, &b2 };
	for (int i = 0; i < 2; ++i)
	{
		CRect rb;
		bs[i]->GetWindowRect(&rb);
		parent->ScreenToClient(&rb);
		bs[i]->SetWindowPos(NULL, rb.left, rl.top + textH + 2, 0, 0,
			SWP_NOSIZE | SWP_NOZORDER);
	}
}

void CDlg_Set_MmCam_Env::LoadStageStatus()
{
	const std::string st =
		std::string(GetMmCamStartPath()) + "users\\" + gUserID + "\\stage_status.ini";

	const std::string updated = ini_read_utf8(st, "STATUS", "UPDATED_AT", "");

	// 마지막 기록이 낡았으면 파일에 남은 값을 믿지 않는다. 프로세스가 죽어도
	// 마지막 값이 남아 등이 계속 초록으로 보였다.
	const long long age = updated.empty() ? -1 : status_age_seconds(updated);
	const bool stale = !updated.empty() && (age < 0 || age > STATUS_STALE_SEC);

	// [3단계·기여도] 아래의 현모델 기여도와 계산 일시. 감시가 멈춰 있으면 값을 믿지 않는다.
	{
		CStringA h = "기여도 점수   계산 전";
		if (!updated.empty() && !stale)
		{
			const std::string ds = ini_read_utf8(st, "STATUS", "DECISION_SCORE", "");
			const std::string cw = ini_read_utf8(st, "STATUS", "CONTRIB_W", "");
			if (!ds.empty() && !cw.empty())
			{
				// 기여는 점수에 비례하는 연속값이다. 말로만 "기여 축소" 라고 하면 0.62 와
				// 0.13 이 구별되지 않는다. 옛 자료 비중을 그대로 적는다.
				const double w = atof(cw.c_str());
				CStringA how;
				if (w >= 1.0)      how = "재학습 불필요";
				else if (w <= 0.0) how = "새로 시작";
				else               how.Format("옛 자료 %.0f%%", w * 100.0);

				// 기여도 점수는 지금 모델로 판단 구간을 다시 채점한 중앙값이고, 현모델
				// 기여도(w)는 그 점수를 문턱으로 환산한 값이다.
				h.Format("기여도 점수 %s\r\n현모델 기여도 %s · %s",
					ds.c_str(), cw.c_str(), (LPCSTR)how);

				// 이 점수와 기여도를 계산한 시각. 감시가 약 10분마다 다시 구한다.
				const std::string cat = ini_read_utf8(st, "STATUS", "CONTRIB_AT", "");
				if (!cat.empty())
					h.AppendFormat("\r\n기여도 계산 %s", cat.c_str());
			}
		}
		SetIfChanged(m_lblCtStatus, h);
	}

	// 재학습 수집 일수 아래의 DB 전체 기간. 먼저 DB 에서 직접 읽은 값을 쓰고,
	// 아직 못 읽었으면 감시가 남긴 값으로 대신한다(감시가 멈춰 있으면 믿지 않는다).
	{
		CStringA h = "0 = 전체";
		if (m_spanOk)
		{
			h.Format("0 = 전체 · DB %d일 (%s ~ %s)", m_spanTables,
				(LPCSTR)m_spanFirst.Mid(5), (LPCSTR)m_spanLast.Mid(5));
		}
		else if (m_spanBusy)
		{
			h = "0 = 전체 · DB 확인 중";
		}
		else if (!updated.empty() && !stale)
		{
			const int n = ini_read_int_utf8(st, "STATUS", "DB_ALL_TABLES", -1);
			const std::string f = ini_read_utf8(st, "STATUS", "DB_FIRST", "");
			const std::string l = ini_read_utf8(st, "STATUS", "DB_LAST", "");
			if (n > 0 && f.size() >= 10 && l.size() >= 10)
				h.Format("0 = 전체 · DB %d일 (%s ~ %s)", n,
					f.substr(5).c_str(), l.substr(5).c_str());
		}
		SetIfChanged(m_lblSpDaysHint, h);
	}
	RequestSpan(false);

	if (stale) {
		CStringA down;
		down.Format("감시 중단\r\n    마지막 기록 %s", updated.c_str());
		SetShiftAlert(false);
		SetIfChanged(m_lblShift, "[카메라 위치 이동]  확인 전");
		SetIfChanged(m_lblStage0, "1단계 절대임계값   " + down);
		SetIfChanged(m_lblStage1, "2단계 경험임계값   " + down);
		PlaceBaseButtons(this, m_lblStage1, m_btnBaseFresh, m_btnBaseRebuild);
		SetIfChanged(m_lblStage2, "3단계 오토인코더   " + down);
		for (int i = 0; i < 3; ++i)
			SetLamp(m_lampStage[i], m_lampLevel[i], 0);
		return;
	}

	if (updated.empty()) {
		SetShiftAlert(false);
		SetIfChanged(m_lblShift, "[카메라 위치 이동]  확인 전");
		SetIfChanged(m_lblStage0, "1단계 절대임계값   집계 대기\r\n    감시 시작 후 첫 기록까지 잠시 걸림");
		SetIfChanged(m_lblStage1, "2단계 경험임계값   집계 대기");
		PlaceBaseButtons(this, m_lblStage1, m_btnBaseFresh, m_btnBaseRebuild);
		SetIfChanged(m_lblStage2, "3단계 오토인코더   집계 대기");
		for (int i = 0; i < 3; ++i)
			SetLamp(m_lampStage[i], m_lampLevel[i], 0);
		return;
	}

	const int samples = ini_read_int_utf8(st, "STATUS", "SAMPLES", 0);
	const int min_smp = ini_read_int_utf8(st, "STATUS", "MIN_SAMPLES", 0);
	const int hours   = ini_read_int_utf8(st, "STATUS", "HOURS", 0);
	const int min_hr  = ini_read_int_utf8(st, "STATUS", "MIN_HOURS", 0);
	const int s1      = ini_read_int_utf8(st, "STATUS", "STAGE1", 0);
	const int s2      = ini_read_int_utf8(st, "STATUS", "STAGE2", 0);
	const int used    = ini_read_int_utf8(st, "STATUS", "STAGE_USED", -1);
	const int db_rows = ini_read_int_utf8(st, "STATUS", "DB_ROWS", -1);
	// 카메라 이동으로 2·3단계 판정과 학습이 멈췄다.
	const bool halt   = ini_read_int_utf8(st, "STATUS", "SHIFT_HALT", 0) != 0;


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
			line = "[카메라 위치 이동]  확인 전";
		else if (sstate == 0)
			line.Format("[카메라 위치 이동]  판정 불가 (기준과 다른 장면)   (%s 기동 시)",
				sat.c_str());
		else if (atoi(sx.c_str()) == 0 && atoi(sy.c_str()) == 0)
			// 짧게 쓴다. 이 줄이 접히면 아래 열화상 줄이 상자 밖으로
			// 밀려 나가, 2단계가 왜 멈췄는지 화면에서 사라졌다.
			line.Format("[카메라 위치 이동]  없음   (0칸 · %s · %s%s)",
				px.IsEmpty() ? "-" : (LPCSTR)px,
				sat.size() > 11 ? sat.substr(11).c_str() : sat.c_str(),
				old_way);
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
			line.Format("[카메라 위치 이동]  %s   (가로 %+d칸 · 세로 %+d칸 · %s 측정%s)%s",
				px.IsEmpty() ? "이동" : (LPCSTR)px,
				atoi(sx.c_str()), atoi(sy.c_str()), sat.c_str(), old_way, warn);
		}

		// 이동이 있을 때만 적색. 기동 때 RGB 로 칸 단위 이동을 쟀거나, 운전 중
		// 열화상 패턴 이동으로 2·3단계가 멈췄을 때다. 뒤의 것은 RGB 줄이
		// "없음" 이어도 멈춰 있으므로 그 까닭을 덧붙인다.
		const bool rgb_moved = !sx.empty() && !sy.empty() && sstate != 0 &&
			(atoi(sx.c_str()) != 0 || atoi(sy.c_str()) != 0);
		if (halt && !rgb_moved)
			line += "  · 열화상 이동";
		SetShiftAlert(rgb_moved || halt);

		sh = line;
		SetIfChanged(m_lblShift, sh);
	}

	// 1단계 — 학습과 무관하게 늘 동작한다. 다만 임계값을 지정하지 않으면
	// 판정 자체가 꺼져 있으므로 그 구분을 보여준다.
	const int s0 = ini_read_int_utf8(st, "STATUS", "STAGE0", 0);
	if (s0)
	{
		t.Format("1단계 절대임계값   사용 중\r\n    온도 %s/%s도 · 상승 %s/%s도/분",
			ini_read_utf8(st, "STATUS", "ABS_TEMP_WARN", "-").c_str(),
			ini_read_utf8(st, "STATUS", "ABS_TEMP_ALARM", "-").c_str(),
			ini_read_utf8(st, "STATUS", "ABS_RISE_WARN", "-").c_str(),
			ini_read_utf8(st, "STATUS", "ABS_RISE_ALARM", "-").c_str());
	}
	else
	{
		t.Format("1단계 절대임계값   꺼짐\r\n    env.ini 에 ABS_TEMP · ABS_RISE 미지정");
	}

	// 지금 잰 값. 선만 보여 주면 지금이 그 선에서 얼마나 떨어져 있는지
	// 알 수 없다. 선을 너무 높게 잡아 평생 걸리지 않는 상태가 바로 그렇게
	// 숨는다 - cj_busan_1 은 경보선 187도에 관측 최고가 146도였다.
	if (s0)
	{
		const std::string pk = ini_read_utf8(st, "STATUS", "ABS_PEAK", "");
		const std::string rs = ini_read_utf8(st, "STATUS", "ABS_RISE", "");
		const int lv = ini_read_int_utf8(st, "STATUS", "ABS_LEVEL", 0);

		if (!pk.empty() && atof(pk.c_str()) >= 0.0)
		{
			CStringA now;
			now.Format("\r\n    지금 %.0f도 · %+.1f도/분   %s",
				atof(pk.c_str()), atof(rs.c_str()),
				lv >= 2 ? "경보" : (lv == 1 ? "주의" : "정상"));
			t += now;
		}
		else
		{
			t += "\r\n    지금 측정 전";
		}
	}
	SetIfChanged(m_lblStage0, t);

	// 1단계는 중간이 없다. 네 값이 있으면 켜지고 없으면 꺼진다.
	SetLamp(m_lampStage[0], m_lampLevel[0], s0 ? 2 : 0);

	// 단계 번호만으로는 그것이 무엇인지 알 수 없다. 이름을 함께 적는다.
	// 좁은 열에 맞추려고 두 줄로 나눈다. 첫 줄은 이름과 상태, 둘째 줄은 근거.
	//
	// 2단계는 채점에 쓰이는 중인지까지 구분한다. 준비됐어도 3단계가 있으면
	// 둘이 함께 쓰이므로 "사용 중" 이 맞다.
	// 쌓고 있는가를 상태와 함께 적는다.
	//
	// "사용 중" 만으로는 누적이 멈춘 것이 드러나지 않는다. 표본 수가 늘지
	// 않는 것으로만 알 수 있어, 알아채려면 몇 분을 지켜봐야 했다.
	CStringA stop;
	{
		const std::string lo = ini_read_utf8(st, "STATUS", "ACCUM_OK", "");
		const CStringA lw = StatusUtf8(
			ini_read_utf8(st, "STATUS", "ACCUM_WHY", ""));
		if (lo == "0")
			stop.Format(" · 누적 멈춤 (%s)",
				lw.IsEmpty() ? "사유 미상" : (LPCSTR)lw);
	}

	t.Format("2단계 경험임계값   %s%s\r\n    표본 %d/%d · 시간대 %d/%d",
		s1 ? "사용 중" : "누적 중", (LPCSTR)stop,
		samples, min_smp, hours, min_hr);

	// 왜 처음부터 쌓고 있는가.
	//
	// "누적 중" 만 보고는 설치 직후인지, 되돌리기로 치운 것인지, 파일이
	// 깨져 다시 시작한 것인지 알 수 없다. 셋은 할 일이 전혀 다르다 -
	// 앞은 기다리면 되고, 뒤는 사람이 손을 대야 한다.
	{
		const CStringA why = StatusUtf8(
			ini_read_utf8(st, "STATUS", "RESET_WHY", ""));
		const CStringA at = StatusUtf8(
			ini_read_utf8(st, "STATUS", "RESET_AT", ""));
		const CStringA from = StatusUtf8(
			ini_read_utf8(st, "STATUS", "STARTED_AT", ""));

		// 사유가 없는 것과 "사유가 없음을 확인했다" 는 다르다. 쪽지를
		// 남기기 전에 시작된 누적이면 왜 그때 처음부터였는지 알 길이
		// 없으므로, 모른다고 적는다.
		CStringA line;
		if (!why.IsEmpty() && !at.IsEmpty())
			line.Format("\r\n    %s %s", (LPCSTR)at, (LPCSTR)why);
		else if (!why.IsEmpty())
			line.Format("\r\n    %s", (LPCSTR)why);
		else if (!from.IsEmpty())
			line.Format("\r\n    %s 부터 이어 쌓는 중 (초기화 기록 없음)",
				(LPCSTR)from);
		else
			line = "\r\n    초기화 기록 없음";

		t += line;
	}
	if (halt)
		t.Format("2단계 경험임계값   중지 (카메라 위치 이동)\r\n"
			"    판정·누적 멈춤 · 표본 %d/%d · 시간대 %d/%d",
			samples, min_smp, hours, min_hr);
	SetIfChanged(m_lblStage1, t);
	PlaceBaseButtons(this, m_lblStage1, m_btnBaseFresh, m_btnBaseRebuild);
	if (m_btnCellBase.GetSafeHwnd()) m_btnCellBase.RedrawWindow();

	// 2단계는 중간이 있다. 아직 모자라도 쌓고 있으면 노랑이다 - 꺼진
	// 것과 차오르는 중인 것은 할 일이 다르다.
	SetLamp(m_lampStage[1], m_lampLevel[1],
		halt ? 0 : (s1 ? 2 : (samples > 0 ? 1 : 0)));

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
		t.Format("3단계 오토인코더   사용 중\r\n    세대 %s\r\n    모델 %s",
			gen.empty() ? "-" : gen.c_str(),
			mat.empty() ? "-" : mat.c_str());
	}
	else
	{
		t.Format("3단계 오토인코더   없음\r\n    모델 파일이 아직 없음\r\n");
	}
	if (halt)
		t = "3단계 오토인코더   중지 (카메라 위치 이동)\r\n"
			"    판정·자동 재학습 멈춤\r\n";
	SetIfChanged(m_lblStage2, t);

	// 3단계도 중간이 있다. 모델은 없지만 재학습에 쓸 자료가 차오르는 중이면
	// 노랑이다 (DB 행 수를 최소 재학습 조건과 견준다).
	SetLamp(m_lampStage[2], m_lampLevel[2],
		halt ? 0 : (s2 ? 2 : (db_rows > 0 ? 1 : 0)));

	// 갱신 시각은 상단 안내줄에 함께 보여준다. 기준선 창의 기간과 건수는 [2단계
	// 경험임계값] 칸의 "표본 N/3,000" 과 겹쳐서 여기에는 적지 않는다.
	//
	// 채점에 쓰이는 단계를 모두 적는다.
	//
	//   1단계  절대 임계값이 켜져 있으면 늘 본다 (STAGE0)
	//   2단계  경험 임계값이 섰으면(STAGE1) 채점에 함께 들어간다
	//   3단계  오토인코더가 있으면(STAGE_USED 2) 채점한다
	//
	// 2·3단계가 다 있으면 predict_machine 이 둘 다 매기고 낮은 쪽을 점수로 쓴다.
	// STAGE_USED 는 그때도 2 라서, 그 값만 보면 2단계가 빠진 것처럼 읽혔다.
	CStringA scoring;
	auto add = [&](const char* n) {
		if (!scoring.IsEmpty()) scoring += ", ";
		scoring += n;
	};
	if (s0) add("1");
	if (s1 && used >= 1) add("2");
	if (used == 2) add("3");
	scoring = scoring.IsEmpty() ? CStringA("-") : scoring + " 단계";

	CStringA head;
	head.Format("[%s]  ·  현황 %s  ·  현재 채점 %s",
		gUserID.c_str(),
		updated.c_str(),
		(LPCSTR)scoring);

	// 머리줄은 결과 메시지와 자리를 함께 쓴다. 방금 [설정 저장] 이 남긴
	// 글이 2초 만에 지워지면 무엇이 저장됐는지 읽을 틈이 없다.
	if (GetTickCount() >= m_msgHoldUntil)
		SetIfChanged(m_cap_0, head);
}

//---------------------------------------------------------

// (형식 검사 함수는 달력 컨트롤 도입으로 불필요해져 제거)

//---------------------------------------------------------

void CDlg_Set_MmCam_Env::OnBnClickedSaveStage()
{
	if (gUserID.empty()) {
		Msg("[ERROR] 현장(user)이 선택되지 않았음");
		return;
	}

	CString a, b, c;
	m_edBaseSamples.GetWindowTextA(a);
	m_edBaseHours.GetWindowTextA(b);
	m_edAeSamples.GetWindowTextA(c);
	const int base_samples = atoi(a);
	const int base_hours   = atoi(b);
	const int ae_samples   = atoi(c);
	m_edAeHours.GetWindowTextA(c);
	const int ae_hours     = atoi(c);

	// 터무니없는 값이 들어가면 감시가 영영 시작되지 않거나(너무 큼),
	// 아무것도 못 배운 상태로 채점을 시작한다(너무 작음). 여기서 막는다.
	if (base_samples < 100 || base_samples > 1000000) {
		Msg("[ERROR] 기준선 최소 표본은 100 ~ 1,000,000 사이여야 함");
		return;
	}
	if (base_hours < 1 || base_hours > 24) {
		Msg("[ERROR] 기준선 최소 시간대는 1 ~ 24 사이여야 함");
		return;
	}
	if (ae_samples < 1000 || ae_samples > 1000000) {
		Msg("[ERROR] 재학습 최소 표본은 1,000 ~ 1,000,000 사이여야 함");
		return;
	}
	if (ae_hours < 1 || ae_hours > 24) {
		Msg("[ERROR] 재학습 최소 시간대는 1 ~ 24 사이여야 함");
		return;
	}

	// --- 1단계 절대 임계값 -----------------------------------------
	// 버튼 하나로 두 묶음을 함께 저장하므로 여기서 같이 검사한다.
	CString at, aa, ar, arA;
	m_edAbsTempWarn.GetWindowTextA(at);
	m_edAbsTempAlarm.GetWindowTextA(aa);
	m_edAbsRiseWarn.GetWindowTextA(ar);
	m_edAbsRiseAlarm.GetWindowTextA(arA);

	// 네 칸을 모두 비우면 1단계를 끈다. 일부만 비우는 것은 어중간한 상태라
	// 막는다 — 온도만 넣고 상승률을 비우면 어느 쪽이 의도인지 알 수 없다.
	const bool bAbsAllEmpty = at.IsEmpty() && aa.IsEmpty() && ar.IsEmpty() && arA.IsEmpty();
	const bool bAbsAnyEmpty = at.IsEmpty() || aa.IsEmpty() || ar.IsEmpty() || arA.IsEmpty();

	if (!bAbsAllEmpty && bAbsAnyEmpty) {
		Msg("[ERROR] 절대 임계값 네 칸을 모두 채우거나 모두 비울 것 · "
			"모두 비우면 1단계 경보가 꺼짐");
		return;
	}

	if (!bAbsAllEmpty)
	{
		const int tw = atoi(at), ta = atoi(aa), rw = atoi(ar), ra = atoi(arA);

		// 격자 온도는 0~255 범위다(utils.Conv_LWIR_to_64_Vector 와 같은 기준).
		if (tw < 1 || tw > 255 || ta < 1 || ta > 255) {
			Msg("[ERROR] 온도는 1 ~ 255 도 사이여야 함");
			return;
		}
		if (rw < 1 || rw > 500 || ra < 1 || ra > 500) {
			Msg("[ERROR] 상승률은 1 ~ 500 도/분 사이여야 함");
			return;
		}
		// 주의선이 경보선보다 높으면 주의가 영영 뜨지 않는다.
		if (tw >= ta || rw >= ra) {
			Msg("[ERROR] 주의선은 경보선보다 낮아야 함");
			return;
		}
	}

	// --- 기여도 판단 기준 -------------------------------------------
	// 여기 값이 틀리면 기여도가 통째로 멈추거나(기간 0) 4건의 중앙값으로
	// 모델을 버릴지 정하게 된다(최소 표본 1). 범위를 좁게 막는다.
	CString cw, cf, cs;
	m_edCtWindow.GetWindowTextA(cw);
	m_edCtMinFrames.GetWindowTextA(cf);
	m_edCtMaxSamples.GetWindowTextA(cs);

	const int ct_window  = atoi(cw);
	const int ct_frames  = atoi(cf);
	const int ct_samples = atoi(cs);

	// 날짜 테이블 수. 60 이면 두 달이라 "지금도 맞는가" 를 묻는 뜻이 사라진다.
	if (ct_window < 1 || ct_window > 60) {
		Msg("[ERROR] 판단 최소 일수는 1 ~ 60 (날짜 테이블 수) 사이여야 함");
		return;
	}
	if (ct_frames < 10 || ct_frames > 1000000) {
		Msg("[ERROR] 기여도 최소 표본은 10 ~ 1,000,000 사이여야 함");
		return;
	}
	if (ct_samples < 100 || ct_samples > 1000000) {
		Msg("[ERROR] 표본 상한은 100 ~ 1,000,000 사이여야 함");
		return;
	}
	// 상한이 최소보다 작으면, 판단에 쓰기로 한 최소치보다 적은 표본으로
	// 점수를 매기게 된다. 앞뒤가 맞지 않는다.
	if (ct_samples < ct_frames) {
		Msg("[ERROR] 기여도 최대 표본이 최소 표본보다 작음");
		return;
	}

	// --- 학습 표본 구성 ---------------------------------------------
	CString sp_t, sp_d;
	m_edSpTarget.GetWindowTextA(sp_t);
	m_edSpDays.GetWindowTextA(sp_d);

	const int sp_target = atoi(sp_t);
	const int sp_days   = sp_d.IsEmpty() ? 0 : atoi(sp_d);

	// 목표가 너무 작으면 시간대를 다 덮지 못하고, 너무 크면 모으는 데만
	// 오래 걸린다.
	if (sp_target < 1000 || sp_target > 1000000) {
		Msg("[ERROR] 재학습 최대 표본 수는 1,000 ~ 1,000,000 사이여야 함");
		return;
	}
	// 0 은 전체. 너무 짧으면 24개 시간대를 다 채우지 못한다.
	if (sp_days < 0 || sp_days > 3650) {
		Msg("[ERROR] 재학습 수집 일수는 0(전체) 또는 1 ~ 3650 사이여야 함");
		return;
	}

	// --- 재생버퍼 동적구성 · 기여 문턱 ------------------------------
	// 점수는 exp(-mse*10) 이라 0 ~ 1 범위다. '하' 가 '상' 보다 낮아야 그 사이에서 w 가
	// 1 에서 0 으로 내려간다.
	CString bh, bl;
	m_edBandHigh.GetWindowTextA(bh);
	m_edBandLow.GetWindowTextA(bl);
	const double band_hi = atof(bh), band_lo = atof(bl);
	if (band_lo <= 0.0 || band_lo >= 1.0 || band_hi <= 0.0 || band_hi > 1.0) {
		Msg("[ERROR] 기여 문턱은 0 초과 1 이하여야 함");
		return;
	}
	if (band_lo >= band_hi) {
		Msg("[ERROR] 기여 문턱의 '하' 는 '상' 보다 낮아야 함");
		return;
	}
	const int dyn_mix = (m_chkDyn.GetCheck() == BST_CHECKED) ? 1 : 0;
	CStringA bhs, bls;
	bhs.Format("%.2f", band_hi);
	bls.Format("%.2f", band_lo);

	// 쓰는 곳은 continual_learning.ini 하나다. env.ini 에 옛 값이 남아 있어도 파이썬과
	// C++ 모두 continual_learning.ini 를 먼저 보므로 이쪽이 이긴다.
	const std::string ini = LearnIniPath();

	bool ok = ini_write_int_utf8(ini, "CONSTANTS", "BASELINE_MIN_SAMPLES", base_samples)
		&& ini_write_int_utf8(ini, "CONSTANTS", "BASELINE_MIN_HOURS", base_hours)
		&& ini_write_int_utf8(ini, "CONSTANTS", "RETRAIN_MIN_SAMPLES", ae_samples)
		&& ini_write_int_utf8(ini, "CONSTANTS", "RETRAIN_MIN_HOURS", ae_hours)
		&& ini_write_utf8(ini, "CONSTANTS", "ABS_TEMP_WARN",  (const char*)CStringA(at))
		&& ini_write_utf8(ini, "CONSTANTS", "ABS_TEMP_ALARM", (const char*)CStringA(aa))
		&& ini_write_utf8(ini, "CONSTANTS", "ABS_RISE_WARN",  (const char*)CStringA(ar))
		&& ini_write_utf8(ini, "CONSTANTS", "ABS_RISE_ALARM", (const char*)CStringA(arA))
		&& ini_write_int_utf8(ini, "CONSTANTS", "CONTRIB_WINDOW_TABLES", ct_window)
		&& ini_write_int_utf8(ini, "CONSTANTS", "CONTRIB_MIN_FRAMES", ct_frames)
		&& ini_write_int_utf8(ini, "CONSTANTS", "CONTRIB_MAX_SAMPLES", ct_samples)
		&& ini_write_int_utf8(ini, "CONSTANTS", "RETRAIN_TARGET_SAMPLES", sp_target)
		// 빈칸 그대로 쓴다. 파이썬 쪽이 빈칸을 '자동' 으로 읽는다.
		&& ini_write_int_utf8(ini, "CONSTANTS", "RETRAIN_BUFFER_DAYS", sp_days)
		&& ini_write_int_utf8(ini, "CONSTANTS", "RETRAIN_DYNAMIC_MIX", dyn_mix)
		&& ini_write_utf8(ini, "CONSTANTS", "CONTRIB_BAND_HIGH", (LPCSTR)bhs)
		&& ini_write_utf8(ini, "CONSTANTS", "CONTRIB_BAND_LOW", (LPCSTR)bls);

	CStringA msg;
	if (ok) {
		// 파이썬 프로세스는 기동할 때 설정을 읽는다. 저장만으로는 반영되지 않는다.
		CStringA absPart;
		if (bAbsAllEmpty)
			absPart = "임계값 꺼짐";
		else
			absPart.Format("임계값 %s/%s도·%s/%s도분",
				(const char*)CStringA(at), (const char*)CStringA(aa),
				(const char*)CStringA(ar), (const char*)CStringA(arA));

		// 기여도 판단 기준도 한 토막으로 덧붙인다. "기간/최소/상한" 꼴로 압축한다.
		CStringA ctPart;
		ctPart.Format("기여 %d개/%d/%d", ct_window, ct_frames, ct_samples);

		CStringA spPart;
		CStringA daysPart;
		if (sp_days > 0) daysPart.Format("·최근%d일", sp_days);
		spPart.Format("표본 최대 %d%s", sp_target, (LPCSTR)daysPart);

		msg.Format("[저장 완료] 2단계 %d건/%d시간대, 3단계 %d건, %s, %s, %s"
			"   -  '정지' 후 '시작'을 눌러야 반영됨",
			base_samples, base_hours, ae_samples,
			(const char*)absPart, (const char*)ctPart, (const char*)spPart);
	}
	else {
		msg.Format("[ERROR] continual_learning.ini 를 쓰지 못했음: %s", ini.c_str());
	}
	Msg(msg);
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
// [관제서버 분석마스크 받기]
//
// 관제서버의 hotlist_mask_svr.ini 를 받아 지금 쓰는 로컬 마스크와 나란히 보이고,
// 사람이 견주어 본 뒤 그 자리에서 교체한다(CDlg_MaskFetch). 바꾸기 전 것은
// users/<현장>/mask_history/ 에 시각을 붙여 남기고, 창의 [이전 마스크 보기] 로
// 지금 것과 견주어 볼 수 있다.
//
// [예전 구현]
//   로컬 마스크를 지워 두고 다음 기동 때 predict_machine 이 받게 했다. 무엇을
//   받게 될지 보지 못한 채 지웠고, 남긴 것도 .bak 한 벌뿐이라 두 번 바꾸면
//   처음 것이 사라졌다.
//---------------------------------------------------------
void CDlg_Set_MmCam_Env::OnBnClickedButtonGetMask()
{
	if (gUserID.empty()) {
		Msg("[ERROR] 현장(user)이 선택되지 않았음");
		return;
	}

	// 관제서버 주소는 현장 설정에서 읽는다.
	const std::string root_url =
		ini_read_utf8(StageIniPath(), "NETWORK", "ROOT_URL", "");
	if (root_url.empty()) {
		Msg("[ERROR] env.ini 의 [NETWORK] ROOT_URL 이 비어 있음");
		return;
	}

	std::string url = root_url;
	while (!url.empty() && (url.back() == '/' || url.back() == ' ')) url.pop_back();
	url += "/" + gUserID + "/hotlist_mask_svr.ini";

	const std::string user_path =
		std::string(GetMmCamStartPath()) + "users\\" + gUserID + "\\";
	const int need = atoi(ini_read_utf8(StageIniPath(), "CONSTANTS",
		"NUM_OF_MACHINE_CELLS", "0").c_str());

	CDlg_MaskFetch dlg(&m_stdFont, this, user_path, url, need);
	dlg.DoModal();
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

// 칸별 기준값 창을 띄운다.
//
// [현재 진행] 2단계 칸은 표본 수와 시간대밖에 말하지 못한다. 어느 칸이
// 선에 가까운지는 8x8 격자로 봐야 알 수 있다.
void CDlg_Set_MmCam_Env::OnBnClickedCellBase()
{
	if (gUserID.empty())
	{
		Msg("[ERROR] 현장(user)이 선택되지 않았음");
		return;
	}

	CDlg_CellBase dlg(this);
	dlg.DoModal();
}

// 운전 상태 이름을 고친다.
//
// 메인 창 위의 운전 상태 줄은 감시가 stage_status.ini 에 적은 것이라, 저장한 뒤
// 감시가 새 이름을 읽을 때까지(1분 안) 옛 이름이 보인다.
void CDlg_Set_MmCam_Env::OnBnClickedOpNames()
{
	if (gUserID.empty())
	{
		Msg("[ERROR] 현장(user)이 선택되지 않았음");
		return;
	}

	if (EditOpStateNames(this, &m_stdFont, &m_stdFont))
		Msg("운전 상태 이름을 저장했음 · 감시가 새 이름을 읽으면(1분 안) 메인 창에도 반영됨");
}

// ---------------------------------------------------------
// 경험 임계값을 손으로 다시 세운다
//
// 두 버튼이 같은 틀을 쓴다. 다른 것은 돌리는 스크립트와 확인 문구뿐이다.
//
// 감시가 돌고 있으면 막는다. predict_machine 은 기준선을 메모리에 들고
// 200건마다 파일에 다시 쓰므로, 돌려 둔 채로 고치면 조용히 덮어쓰고
// 아무 일도 없었던 것처럼 보인다.
//
// 콘솔 창을 띄워 그대로 보여 준다. 두 도구 모두 무엇을 몇 건 읽어 어떻게
// 되었는지 찍으므로, 그 글을 사람이 읽는 것이 요약을 다시 만드는 것보다
// 낫다.
// ---------------------------------------------------------
// action 은 확인 창 첫 줄의 동작 이름("재구성" 등), warn 은 "- " 로 시작하는 항목 줄들.
void CDlg_Set_MmCam_Env::RunBaseTool(const char* title, const char* action, const char* script,
                                     const char* args, const char* warn)
{
	if (gUserID.empty())
	{
		Msg("[ERROR] 현장(user)이 선택되지 않았음");
		return;
	}

	CMmCammonitoringDlg* main = dynamic_cast<CMmCammonitoringDlg*>(GetParent());
	if (main != nullptr && main->IsPredictRunning(gUserID.c_str()))
	{
		CStringA m;
		m.Format("감시가 돌고 있어 할 수 없음\r\n\r\n"
			"predict_machine 이 경험 임계값을 메모리에 들고 있어, 지금 "
			"고치면 200건 뒤에 덮어씀\r\n\r\n"
			"[목록] 에서 %s 의 predict_machine 을 멈춘 뒤 다시 누를 것",
			gUserID.c_str());
		AfxMessageBox(CString(m), MB_OK | MB_ICONWARNING);
		return;
	}

	// 짧게: 첫 줄에 동작, 그 아래 항목 몇 줄. [예]/[아니오] 가 묻는 말을 대신한다.
	// 지금 표본 수는 [설정] 창 2단계 줄에 늘 보이므로 여기 다시 적지 않는다.
	CStringA q;
	q.Format("[%s] 경험 임계값 %s\r\n\r\n"
		"%s\r\n"
		"- 기존 값은 _retired_baseline 에 보관 (복구 가능)",
		gUserID.c_str(), action, warn);

	if (AfxMessageBox(CString(q), MB_YESNO | MB_ICONWARNING | MB_DEFBUTTON2)
	    != IDYES)
		return;

	CStringA cmd;
	cmd.Format("cmd.exe /c call \"%sScripts\\activate.bat\" %s "
		"&& cd /d \"%s\" && set PYTHONIOENCODING=utf-8 "
		"&& python %s \"%s\"%s & echo. & pause",
		GetAnacondaRootPub(), GetAnacondaEnvPub(),
		GetMmCamStartPath(), script, gUserID.c_str(), args);

	STARTUPINFOA si = { sizeof(si) };
	PROCESS_INFORMATION pi = { 0 };
	std::vector<char> line(cmd.GetString(), cmd.GetString() + cmd.GetLength() + 1);

	if (!CreateProcessA(nullptr, line.data(), nullptr, nullptr, FALSE,
		CREATE_NEW_CONSOLE, nullptr, GetMmCamStartPath(), &si, &pi))
	{
		Msg("[ERROR] 도구를 실행하지 못했음");
		return;
	}
	CloseHandle(pi.hThread);
	CloseHandle(pi.hProcess);

	CStringA done;
	done.Format("%s 를 시작했음 · 창에서 결과를 확인할 것\r\n\r\n"
		"끝난 뒤 [시작] 으로 감시를 다시 켜야 반영됨", title);
	Msg(done);
}

void CDlg_Set_MmCam_Env::OnBnClickedBaseFresh()
{
	RunBaseTool("현재부터쌓기", "초기화", "retrain\\nightly_retrain.py",
		" --reset-baseline",
		"- 비우고 지금부터 다시 쌓음 → 다시 설 때까지 2단계 꺼짐 (30초 주기면 하루 남짓)\r\n"
		"- 분석마스크를 다시 떴거나 카메라를 옮겼을 때 사용");
}

void CDlg_Set_MmCam_Env::OnBnClickedBaseRebuild()
{
	RunBaseTool("DB에서되쌓기", "재구성", "retrain\\rebuild_baseline.py", "",
		"- 히스토리 DB 에서 재구성 → 2단계 바로 사용\r\n"
		"- 카메라 이동 후 사용 금지 (DB 로 틀어짐 판별 불가)");
}

// ---------------------------------------------------------
// 히스토리 DB 전체 기간 조회.
//
// UI 스레드에서 DB 에 붙으면 DB 가 느리거나 꺼져 있을 때 창이 멈춘다. 별도 스레드가
// 짧은 제한 시간(2초)으로 읽고 결과를 메시지로 돌려준다. 실패하면 조용히 남겨 두고
// 창은 영향받지 않는다. 결과는 5분 동안 보관한다 - 2초 타이머마다 부르지 않는다.
// ---------------------------------------------------------
struct SpanResult
{
	bool ok = false;
	int  tables = 0;
	std::string first, last, user;
};

struct SpanCtx
{
	HWND        hwnd;
	std::string user;
};

static UINT SpanThreadProc(LPVOID p)
{
	SpanCtx* ctx = (SpanCtx*)p;
	SpanResult* r = new SpanResult();
	r->user = ctx->user;
	r->ok = read_history_span(2, &r->tables, &r->first, &r->last);
	const HWND hwnd = ctx->hwnd;
	delete ctx;

	// 창이 이미 닫혔으면 받을 곳이 없다. 결과를 버린다.
	if (!::IsWindow(hwnd) || !::PostMessage(hwnd, WM_SPAN_DONE, 0, (LPARAM)r))
		delete r;
	return 0;
}

void CDlg_Set_MmCam_Env::RequestSpan(bool force)
{
	if (m_spanBusy) return;

	// 현장이 바뀌면 이전 현장의 값은 버린다.
	if (m_spanUser != gUserID.c_str())
	{
		m_spanOk = false;
		force = true;
		m_spanUser = gUserID.c_str();      // 실패해도 5분 동안은 다시 시도하지 않는다
	}

	const DWORD now = GetTickCount();
	if (!force && m_spanAt != 0 && (now - m_spanAt) < 300000)
		return;

	m_spanBusy = true;
	m_spanAt = now;

	SpanCtx* ctx = new SpanCtx{ GetSafeHwnd(), gUserID };
	if (!AfxBeginThread(SpanThreadProc, ctx))
	{
		delete ctx;
		m_spanBusy = false;
	}
}

LRESULT CDlg_Set_MmCam_Env::OnSpanDone(WPARAM, LPARAM lp)
{
	SpanResult* r = (SpanResult*)lp;
	m_spanBusy = false;
	if (r)
	{
		// 조회하는 사이 현장이 바뀌었으면 버린다.
		if (r->ok && r->user == gUserID && r->tables > 0)
		{
			m_spanOk = true;
			m_spanTables = r->tables;
			m_spanFirst = r->first.c_str();
			m_spanLast = r->last.c_str();
			m_spanUser = r->user.c_str();
		}
		delete r;
	}
	LoadStageStatus();
	return 0;
}

void CDlg_Set_MmCam_Env::RefreshAll()
{
	// 창을 열 때는 5분 보관을 무시하고 다시 읽는다.
	RequestSpan(true);

	// 현장(콤보박스)이 바뀌었을 수도 있으므로 제목줄부터 다시 만든다.
	m_msgHoldUntil = 0;         // 다른 현장의 결과 메시지를 붙들 이유가 없다
	LoadHeader();
	LoadStageSettings();
	LoadAbsSettings();
	LoadContribSettings();
	LoadSampleSettings();
	LoadStageStatus();
}

// 2초마다. 입력칸은 건드리지 않는다.
//
// [현재 진행] 은 "지금 무엇이 돌고 있는가" 인데 창을 열 때만 읽으면
// 띄워 둔 채로는 몇 분 전 값이 그대로 남는다. 다만 RefreshAll 을 그대로
// 쓸 수는 없다 - 그쪽은 설정 입력칸까지 다시 채우므로, 사람이 고치던
// 숫자가 2초마다 되돌려진다.
void CDlg_Set_MmCam_Env::RefreshStatus()
{
	LoadStageStatus();
}

// 사람에게 하는 말. 머리줄 자리를 쓰되 잠시 붙들어 둔다.
//
// 머리줄은 2초마다 다시 쓰이므로, 그냥 적으면 [설정 저장] 결과가 눈에
// 들어오기도 전에 사라진다.
void CDlg_Set_MmCam_Env::Msg(const char* s)
{
	if (!m_cap_0.GetSafeHwnd()) return;
	m_cap_0.SetWindowTextA(s);
	m_msgHoldUntil = GetTickCount() + MSG_HOLD_MS;
}

//---------------------------------------------------------

// 1단계 임계값을 continual_learning.ini 에서 읽어 넣는다.
//
// 지정되지 않은 값은 빈칸으로 둔다. 0 을 적으면 "0도에서 경보" 로 읽혀
// 미지정과 구분되지 않는다.
void CDlg_Set_MmCam_Env::LoadAbsSettings()
{
	struct Item { CEdit* ed; const char* key; };
	const Item items[] = {
		{ &m_edAbsTempWarn,  "ABS_TEMP_WARN"  },
		{ &m_edAbsTempAlarm, "ABS_TEMP_ALARM" },
		{ &m_edAbsRiseWarn,  "ABS_RISE_WARN"  },
		{ &m_edAbsRiseAlarm, "ABS_RISE_ALARM" },
	};

	for (const Item& it : items)
	{
		// 적힌 그대로 보여준다. 빈칸은 빈칸으로 둔다 - 네 칸을 모두 비우면
		// 1단계를 끄는 것이라, 비어 있음과 0 을 구별해야 한다.
		it.ed->SetWindowTextA(LearnRead(it.key, "").c_str());
	}
}

//---------------------------------------------------------

// 기여도 판단 기준을 continual_learning.ini 에서 읽어 넣는다.
//
// 절대 임계값과 달리 빈칸을 허용하지 않는다. 비우면 판단 자체가 안 되므로
// 지정하지 않은 상태가 성립하지 않는다. 값이 없으면 기본값을 적어 보여준다 -
// 파이썬 쪽도 없을 때 같은 기본값을 쓴다.
void CDlg_Set_MmCam_Env::LoadContribSettings()
{
	CString t;
	t.Format("%d", LearnReadInt("CONTRIB_WINDOW_TABLES", DEF_CT_WINDOW));
	m_edCtWindow.SetWindowTextA(t);

	t.Format("%d", LearnReadInt("CONTRIB_MIN_FRAMES", DEF_CT_MIN_FRAMES));
	m_edCtMinFrames.SetWindowTextA(t);

	t.Format("%d", LearnReadInt("CONTRIB_MAX_SAMPLES", DEF_CT_MAX_SAMPLES));
	m_edCtMaxSamples.SetWindowTextA(t);
}

//---------------------------------------------------------

// 학습 표본 구성을 continual_learning.ini 에서 읽어 넣는다.
void CDlg_Set_MmCam_Env::LoadSampleSettings()
{
	CString t;
	t.Format("%d", LearnReadInt("RETRAIN_TARGET_SAMPLES", DEF_SP_TARGET));
	m_edSpTarget.SetWindowTextA(t);

	t.Format("%d", LearnReadInt("RETRAIN_BUFFER_DAYS", 0));
	m_edSpDays.SetWindowTextA(t);

	m_chkDyn.SetCheck(LearnReadInt("RETRAIN_DYNAMIC_MIX", 0) ? BST_CHECKED : BST_UNCHECKED);
	m_edBandHigh.SetWindowTextA(LearnRead("CONTRIB_BAND_HIGH", DEF_CT_BAND_HIGH).c_str());
	m_edBandLow.SetWindowTextA(LearnRead("CONTRIB_BAND_LOW", DEF_CT_BAND_LOW).c_str());
}

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
		Msg("[ERROR] 현장(user)이 선택되지 않았음");
		return;
	}

	CDlg_Retrain dlg(this);
	dlg.DoModal();

	// 재학습이 끝났으면 세대·모델 시각이 바뀌었을 수 있다.
	LoadStageStatus();
}

// 자동 재학습 이력을 본다. 읽기만 한다.
void CDlg_Set_MmCam_Env::OnBnClickedRetrainHist()
{
	if (gUserID.empty()) {
		Msg("[ERROR] 현장(user)이 선택되지 않았음");
		return;
	}

	CDlg_RetrainHist dlg(&m_stdFont, this);
	dlg.DoModal();
}

// RGB 기준 이미지를 지금 화면과 견주어 보고 바꾼다.
//
// 감시가 돌고 있어도 된다. 기준은 감시가 기동할 때 한 번 읽을 뿐이라, 바꾸면
// 다음 시작부터 쓰인다.
void CDlg_Set_MmCam_Env::OnBnClickedBaseRef()
{
	if (gUserID.empty()) {
		Msg("[ERROR] 현장(user)이 선택되지 않았음");
		return;
	}

	CDlg_BaseRef dlg(&m_stdFont, this);
	dlg.DoModal();
}

// 보관된 학습모델(세대)을 되돌리거나 지운다.
//
// 관리 창은 재학습 창의 것을 그대로 쓴다. 되돌리기는 진행 판과 로그가 있는
// 재학습 창에서 돌아야 해서, 재학습 창을 '관리만' 으로 열면 그 창이 곧바로
// 관리 창을 띄운다. 되돌리기를 고르지 않으면 재학습 창도 함께 닫힌다.
void CDlg_Set_MmCam_Env::OnBnClickedGenMgr()
{
	if (gUserID.empty()) {
		Msg("[ERROR] 현장(user)이 선택되지 않았음");
		return;
	}

	CDlg_Retrain dlg(this);
	dlg.OpenGenManagerOnly();
	dlg.DoModal();

	// 되돌렸으면 세대·모델 시각이 바뀌었을 수 있다.
	LoadStageStatus();
}
