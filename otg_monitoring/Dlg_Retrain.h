#pragma once

#include <string>
#include <vector>

// 재학습 실행 창
//
// 재학습은 운용 모델을 바꾸는 일이라 눌러서 바로 돌리게 두면 위험하다.
// 먼저 예행연습(--dry-run)으로 결과를 보여 주고, 그 결과를 읽은 뒤에만
// [재학습 실행] 을 누를 수 있게 한다.
//
// 학습이 몇 분 걸리므로 UI 스레드에서 돌릴 수 없다. 자식 프로세스의 출력을
// 파이프로 받아 작업 스레드가 읽고, 메시지로 넘겨 창에 이어 붙인다.
//
// [되돌리기]
//
// 새 모델이 감도 시험을 통과했어도 현장에서 겪어 보면 아닌 경우가 있다.
// 그럴 때 직전에 운용하던 세대로 돌아간다.
//
// 어디로 갈지는 폴더 순서로 알 수 없다. 예행연습 후보가 같은 곳에 보관되기
// 때문이다. cj_busan_1 은 세대가 10개인데 실제로 올라간 것은 하나였고,
// 폴더 기준으로 "직전" 을 고르면 운용된 적 없는 후보로 갔다. 그래서
// generation_history.txt(승격 기록)를 읽어 정한다.
//
// 정한 세대는 확인 창에 적어 보인 뒤 --rollback <세대> 로 넘긴다. 무인자에
// 맡기면 보여 준 것과 실제로 올라가는 것이 어긋날 수 있다.

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
    afx_msg void OnBnClickedRollback();
    afx_msg void OnDestroy();
    afx_msg void OnTimer(UINT_PTR nIDEvent);
    virtual void OnCancel();

    // 작업 스레드 -> 창. WPARAM 없음, LPARAM 은 new CStringA (창이 지운다)
    afx_msg LRESULT OnLogLine(WPARAM, LPARAM);
    // 자식 프로세스가 끝났다. WPARAM 은 종료 코드
    afx_msg LRESULT OnRunDone(WPARAM, LPARAM);

private:
    // 무엇을 돌리고 있는가. 끝난 뒤 상태 문구와 단추 상태가 달라진다.
    enum RunKind { RUN_DRY = 0, RUN_APPLY = 1, RUN_ROLLBACK = 2 };

    // 로그 칸은 RichEdit 이다. 일반 CEdit 은 글자색을 칸 전체에만 줄 수
    // 있어, 운용 중인 세대와 나머지를 줄 단위로 구분할 수 없다.
    CRichEditCtrl m_edLog;
    CButton  m_btnDry, m_btnApply, m_btnBack, m_btnClose;
    CStatic  m_lblHead, m_lblState;
    CFont    m_font, m_fontMono;

    // 진행 표식.
    //
    // 학습이 몇 분 걸리는데 화면이 가만히 있으면 멈춘 것으로 오해한다.
    //
    // 처음에는 창 아래에 14px 띠를 두었는데 눈에 띄지 않았다. 그래서 창
    // 가운데에 판을 띄우고 그 위에 경과 시간을 돌린다. 시간은 파이썬 출력을
    // 읽지 않고도 늘 움직이므로, 표식이 살아 있는지가 출력 형식에 걸리지
    // 않는다.
    //
    // 단계는 출력에서 읽어(재생버퍼 -> 학습 -> epoch N/400 -> 감도 시험)
    // 백분율로 함께 적는다. 못 읽으면 시간만 나온다.
    CStatic   m_pnlBusy;         // 흰 판 - 뒤의 로그를 가린다
    CStatic   m_lblBusy;         // "예행연습 중"
    CStatic   m_lblElapsed;      // "경과 2분 14초 · 34%"
    CProgressCtrl m_progress;
    int       m_target = 0;      // 출력에서 읽은 진행 (0~1000)
    int       m_pos = 0;         // 눈금이 실제로 가 있는 곳
    int       m_sweep = 0;       // 총량을 모를 때 좌우로 쓸기
    int       m_frame = 0;       // 회전자 프레임
    UINT_PTR  m_timer = 0;
    ULONGLONG m_tickStart = 0;
    CStringA  m_busyWhat;        // 판에 적을 말
    CStringA  m_phaseNote;       // "재생버퍼" · "epoch 143/400" 같은 것
    CStringA  m_lastElapsed;     // 같은 글자를 다시 쓰지 않으려고
    CStringA  m_lastBusy;

    HANDLE   m_hThread = nullptr;
    HANDLE   m_hProc = nullptr;
    volatile bool m_bRunning = false;
    bool     m_bDryDone = false;      // 예행연습을 한 번이라도 끝냈는가
    bool     m_bDryPassed = false;    // 그 결과가 '승격' 이었는가

    // 되돌릴 대상. 창을 열 때와 실행이 끝날 때마다 다시 구한다.
    CStringA m_curGen;                // 운용 중인 세대
    CStringA m_backGen;               // 그 바로 앞 세대 (없으면 빈 문자열)
    CStringA m_backWhy;               // 되돌릴 수 없는 이유

    std::string UserPath() const;
    std::vector<std::string> ListGenerations() const;
    std::vector<std::string> ServedGenerations() const;   // 승격 기록 순서
    void ScanGenerations();           // m_curGen · m_backGen · m_backWhy 갱신
    void ShowGenerations();           // 세대 목록을 로그에 적는다

    void Run(RunKind kind);
    void SetPhase(int permille);     // 단계가 바뀔 때 목표치를 올린다
    void ShowProgress(bool bShow);
    void UpdateElapsed();
    void AnimateBusy();          // 눈금과 회전자를 한 칸 옮긴다
    void AppendLog(const char* text);
    void AppendLog(const char* text, COLORREF color);
    void SetButtons();

    struct RunCtx { CDlg_Retrain* dlg; std::string cmd; int kind; };
    static UINT __cdecl ThreadProc(LPVOID param);
};
