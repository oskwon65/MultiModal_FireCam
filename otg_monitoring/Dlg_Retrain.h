#pragma once

#include <string>

// 재학습 실행 창
//
// 재학습은 운용 모델을 바꾸는 일이라 눌러서 바로 돌리게 두면 위험하다.
// 먼저 예행연습(--dry-run)으로 결과를 보여 주고, 그 결과를 읽은 뒤에만
// [진행] 을 누를 수 있게 한다.
//
// 학습이 몇 분 걸리므로 UI 스레드에서 돌릴 수 없다. 자식 프로세스의 출력을
// 파이프로 받아 작업 스레드가 읽고, 메시지로 넘겨 창에 이어 붙인다.

class CDlg_Retrain : public CDialogEx
{
    DECLARE_DYNAMIC(CDlg_Retrain)

public:
    CDlg_Retrain(CWnd* pParent = nullptr);
    virtual ~CDlg_Retrain();

#ifdef AFX_DESIGN_TIME
    enum { IDD = IDD_DLG_RETRAIN };
#endif

protected:
    virtual void DoDataExchange(CDataExchange* pDX);
    DECLARE_MESSAGE_MAP()

public:
    virtual BOOL OnInitDialog();
    afx_msg void OnBnClickedDryRun();
    afx_msg void OnBnClickedApply();
    afx_msg void OnDestroy();
    virtual void OnCancel();

    // 작업 스레드 -> 창. WPARAM 없음, LPARAM 은 new CStringA (창이 지운다)
    afx_msg LRESULT OnLogLine(WPARAM, LPARAM);
    // 자식 프로세스가 끝났다. WPARAM 은 종료 코드
    afx_msg LRESULT OnRunDone(WPARAM, LPARAM);

private:
    CEdit    m_edLog;
    CButton  m_btnDry, m_btnApply, m_btnClose;
    CStatic  m_lblHead, m_lblState;
    CFont    m_font, m_fontMono;

    HANDLE   m_hThread = nullptr;
    HANDLE   m_hProc = nullptr;
    volatile bool m_bRunning = false;
    bool     m_bDryDone = false;      // 예행연습을 한 번이라도 끝냈는가
    bool     m_bDryPassed = false;    // 그 결과가 '승격' 이었는가

    void Run(bool dryRun);
    void AppendLog(const char* text);
    void SetButtons();

    struct RunCtx { CDlg_Retrain* dlg; std::string cmd; bool dry; };
    static UINT __cdecl ThreadProc(LPVOID param);
};
