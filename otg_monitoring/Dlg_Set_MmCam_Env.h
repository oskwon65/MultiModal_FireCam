#pragma once

#include <string>
#include <afxdtctl.h>   // CDateTimeCtrl

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
    CButton m_btnClose, m_btnGetMask_Server;
    CFont   m_stdFont;
    CStatic m_cap_0;
    // 기동 시 잰 카메라 틀어짐. 버튼 옆에 적는다.
    CStatic m_lblShift;

    // 연속 학습 단계 전환 조건 (users\<id>\env.ini 의 [CONSTANTS])
    CStatic m_sepTop;                                    // 안내줄과 마스크 버튼을 가르는 구분선
    CStatic m_sepBottom;                                 // 설정 영역의 끝을 긋는 구분선
    CStatic m_capStage;                                  // [ 2단계 전환 조건 ]
    CStatic m_capStage2;                                 // [ 3단계·재생 버퍼 ]
    CStatic m_lblBaseSamples, m_lblBaseHours, m_lblAeSamples, m_lblAeHours;
    CEdit   m_edBaseSamples, m_edBaseHours, m_edAeSamples, m_edAeHours;
    CButton m_btnSaveStage, m_btnRetrain;

    // 1단계 절대 임계값. 적용 버튼은 연속학습 조건과 하나를 같이 쓴다.
    CStatic m_capAbs, m_lblAbsTemp, m_lblAbsRise;
    CEdit   m_edAbsTempWarn, m_edAbsTempAlarm, m_edAbsRiseWarn, m_edAbsRiseAlarm;

    // 기여도 판단 기준. 재학습이 기존 모델을 얼마나 물려받을지 정하는 방법이다.
    // 학습 표본을 뽑는 기준(위 연속학습 조건)과는 다른 것이라 따로 묶는다.
    CStatic m_capContrib, m_lblCtWindow, m_lblCtFrames;
    CStatic m_lblCtStatus;      // 현모델 기여도와 계산 일시 (읽기 전용)
    CEdit   m_edCtWindow, m_edCtMinFrames, m_edCtMaxSamples;
    // 문턱은 0.85 같은 소수라 ES_NUMBER 를 걸 수 없다. 점을 못 찍는다.

    // 학습 표본 구성. 무엇을 배울지 정한다. 위 기여도 판단(지금 모델을
    // 얼마나 믿을지)과는 다른 것이라 따로 묶는다.
    int     m_nContentH = 0;
    // 히스토리 DB 전체 기간. 별도 스레드에서 조회한다(RequestSpan).
    void    RequestSpan(bool force);
    bool    m_spanBusy = false;
    bool    m_spanOk = false;
    DWORD   m_spanAt = 0;                 // 마지막으로 조회를 시작한 GetTickCount
    int     m_spanTables = 0;
    CStringA m_spanFirst, m_spanLast, m_spanUser;
    CStatic m_lblSpTarget, m_lblSpDays, m_lblSpDaysHint;
    CEdit   m_edSpTarget, m_edSpDays;

    // 현재 진행 상황 (predict_machine 이 남긴 stage_status.ini 를 읽는다)
    CStatic m_capNow, m_lblStage0, m_lblStage1, m_lblStage2;

    // 단계마다 켜지는 등. 메인 창 현장 콤보 앞의 것과 같은 표식이다.
    //
    // 글만으로는 "사용 중" 과 "누적 중" 을 한눈에 가릴 수 없다. 색이
    // 먼저 들어오고 글은 그 다음에 읽힌다.
    CButton m_btnCellBase;        // 2단계 줄 옆. 칸별 기준값을 띄운다
    CButton m_btnOpNames;         // [현재 진행] 맨 아래. 운전 상태 이름을 고친다
    CButton m_btnGenMgr;          // 그 아래. 보관된 학습모델을 되돌리거나 지운다
    CButton m_btnRetrainHist;     // 그 아래. 자동 재학습 이력을 본다
    // 재생버퍼 동적구성과 기여 문턱 (상/하). [재학습] 창에서 옮겨 왔다.
    CButton m_chkDyn;
    CStatic m_lblBand;
    CEdit   m_edBandHigh, m_edBandLow;
    CButton m_btnBaseRef;         // 맨 윗줄 오른쪽. RGB 기준 이미지를 견주어 보고 바꾼다
    // 경험 임계값을 손으로 다시 세우는 두 가지 길.
    CButton m_btnBaseFresh, m_btnBaseRebuild;
    CStatic m_lampStage[3];
    int     m_lampLevel[3] = { 0, 0, 0 };   // 0 꺼짐 · 1 준비 중 · 2 사용 중
    bool    m_shiftAlert = false;           // [카메라 위치 이동] 줄을 적색으로
    void    SetShiftAlert(bool on);

    virtual BOOL OnInitDialog();
    afx_msg void OnLButtonDown(UINT nFlags, CPoint point);
    afx_msg void OnBnClickedButtonGetMask();
    afx_msg void OnBnClickedClose();
    afx_msg void OnBnClickedSaveStage();
    afx_msg void OnBnClickedRetrain();   // 재학습 창을 띄운다   // 연속학습 조건 + 절대 임계값을 함께 저장

    // 모덜리스로 쓰므로 OK/취소가 창을 없애면 안 된다. 숨기기만 한다.
    virtual void OnOK();
    virtual void OnCancel();

    // 다시 열 때 설정값과 진행 상황을 새로 읽는다. 감시가 도는 동안
    // 표본 수가 계속 늘어나므로 만든 시점의 값으로 두면 안 된다.
    void RefreshAll();
    int  ContentHeight() const { return m_nContentH; }   // 내용이 필요로 하는 높이(px)

    // 2초마다. [현재 진행] 만 다시 읽고 입력칸은 그대로 둔다.
    void RefreshStatus();

    afx_msg HBRUSH OnCtlColor(CDC* pDC, CWnd* pWnd, UINT nCtlColor);
    afx_msg void OnBnClickedCellBase();
    afx_msg void OnBnClickedOpNames();
    afx_msg void OnBnClickedGenMgr();
    afx_msg void OnBnClickedBaseRef();
    afx_msg void OnBnClickedRetrainHist();
    afx_msg void OnBnClickedBaseFresh();
    afx_msg void OnBnClickedBaseRebuild();
    afx_msg LRESULT OnSpanDone(WPARAM wp, LPARAM lp);   // DB 기간 조회가 끝났다
    void RunBaseTool(const char* title, const char* action, const char* script,
                     const char* args, const char* warn);

private:
    // 결과 메시지를 머리줄에 띄우고 잠시 붙들어 둔다. 머리줄은 2초마다
    // 다시 쓰이므로, 그냥 적으면 읽기도 전에 사라진다.
    void Msg(const char* s);
    static const DWORD MSG_HOLD_MS = 15000;
    DWORD m_msgHoldUntil = 0;

    std::string StageIniPath() const;
    // 연속학습 설정은 env.ini 에서 떼어 continual_learning.ini 에 둔다.
    std::string LearnIniPath() const;
    std::string LearnRead(const char* key, const char* def) const;
    int         LearnReadInt(const char* key, int def) const;
    void        LoadHeader();
    void        LoadStageSettings();
    void        LoadStageStatus();
    void        LoadAbsSettings();
    void        LoadContribSettings();
    void        LoadSampleSettings();
};