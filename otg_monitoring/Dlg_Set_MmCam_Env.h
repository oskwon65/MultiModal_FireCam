#pragma once

#include <string>

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
    CStatic m_lblBaseSamples, m_lblBaseHours, m_lblAeSamples;
    CEdit   m_edBaseSamples, m_edBaseHours, m_edAeSamples;
    CButton m_btnSaveStage;

    virtual BOOL OnInitDialog();
    afx_msg void OnLButtonDown(UINT nFlags, CPoint point);
    afx_msg void OnBnClickedButtonChangeMask();
    afx_msg void OnBnClickedButtonGetMask();
    afx_msg void OnBnClickedClose();
    afx_msg void OnBnClickedSaveStage();

private:
    std::string StageIniPath() const;
    void        LoadStageSettings();
};