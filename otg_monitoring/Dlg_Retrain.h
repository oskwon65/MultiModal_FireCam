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
    afx_msg void OnTimer(UINT_PTR nIDEvent);
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

    // 진행바.
    //
    // 학습이 몇 분 걸리는데 화면이 가만히 있으면 멈춘 것으로 오해한다.
    // 정확한 총량을 알 수는 없지만 출력에 단계가 드러나므로(재생버퍼 ->
    // 학습 -> epoch N/400 -> 감도 시험 -> 판정) 그 지점마다 목표치를 올린다.
    // 사이사이는 타이머가 조금씩 채워 멈춰 보이지 않게 한다.
    CProgressCtrl m_progress;
    int       m_pos = 0;         // 지금 위치 (0~1000)
    int       m_target = 0;      // 이번 단계의 상한
    UINT_PTR  m_timer = 0;

    HANDLE   m_hThread = nullptr;
    HANDLE   m_hProc = nullptr;
    volatile bool m_bRunning = false;
    bool     m_bDryDone = false;      // 예행연습을 한 번이라도 끝냈는가
    bool     m_bDryPassed = false;    // 그 결과가 '승격' 이었는가

    void Run(bool dryRun);
    void SetPhase(int permille);     // 단계가 바뀔 때 목표치를 올린다
    void ShowProgress(bool bShow);
    void AppendLog(const char* text);
    void SetButtons();

    struct RunCtx { CDlg_Retrain* dlg; std::string cmd; bool dry; };
    static UINT __cdecl ThreadProc(LPVOID param);
};
