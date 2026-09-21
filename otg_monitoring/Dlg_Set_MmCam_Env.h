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
    CButton m_btnClose, m_btnGetMask_Server, m_btnSetMask_CamPos;
    CFont   m_stdFont;
    CStatic m_cap_0;

    // 연속 학습 단계 전환 조건 (users\<id>\env.ini 의 [CONSTANTS])
    CStatic m_capStage;                                  // 안내 문구
    CStatic m_lblBaseSamples, m_lblBaseHours, m_lblAeSamples, m_lblBaseDate;
    CEdit   m_edBaseSamples, m_edBaseHours, m_edAeSamples;
    // 날짜는 직접 입력받지 않고 달력에서 고른다. DTS_SHOWNONE 체크박스가
    // "기준일 없음(전체 기간)" 상태를 표현한다.
    CDateTimeCtrl m_dtBaseDate;
    CButton m_btnSaveStage;

    // 0단계 절대 임계값. 적용 버튼은 연속학습 조건과 하나를 같이 쓴다.
    CStatic m_capAbs, m_lblAbsTemp, m_lblAbsRise;
    CEdit   m_edAbsTempWarn, m_edAbsTempAlarm, m_edAbsRiseWarn, m_edAbsRiseAlarm;

    // 현재 진행 상황 (predict_machine 이 남긴 stage_status.ini 를 읽는다)
    CStatic m_capNow, m_lblStage0, m_lblStage1, m_lblStage2, m_lblStage3;

    virtual BOOL OnInitDialog();
    afx_msg void OnLButtonDown(UINT nFlags, CPoint point);
    afx_msg void OnBnClickedButtonChangeMask();
    afx_msg void OnBnClickedButtonGetMask();
    afx_msg void OnBnClickedClose();
    afx_msg void OnBnClickedSaveStage();   // 연속학습 조건 + 절대 임계값을 함께 저장

    // 모덜리스로 쓰므로 OK/취소가 창을 없애면 안 된다. 숨기기만 한다.
    virtual void OnOK();
    virtual void OnCancel();

    // 다시 열 때 설정값과 진행 상황을 새로 읽는다. 감시가 도는 동안
    // 표본 수가 계속 늘어나므로 만든 시점의 값으로 두면 안 된다.
    void RefreshAll();

private:
    std::string StageIniPath() const;
    void        LoadStageSettings();
    void        LoadStageStatus();
    void        LoadAbsSettings();
};