#pragma once

#include <string>
#include <vector>

// 관제서버 분석마스크 받기 창
//
// 관제서버의 hotlist_mask_svr.ini 를 내려받아 지금 쓰는 로컬 마스크
// (users/<현장>/hotlist_mask_local.ini) 와 나란히 그려 보이고, [관제서버 것으로
// 교체] 를 누르면 그 자리에서 바꾼다. 바꾸기 전 것은 users/<현장>/mask_history/
// 에 시각을 붙여 남긴다.
//
// [이전 분석마스크 보기] 는 오른쪽 그림을 가장 최근에 남긴 옛 마스크로 바꿔, 지금 것과
// 견주어 보게 한다. 다시 누르면 관제서버 것으로 돌아온다.
//
// 관제서버 마스크의 설비 칸 수가 env.ini 의 NUM_OF_MACHINE_CELLS 와 다르면 관제서버에서
// admin 이 칸 수를 바꾼 것이다. 이때는 [칸 수 변경 후 교체] 가 되어, 모든 학습과 분석이
// 초기화됨을 알리고 확인을 받은 뒤 base_ref_tool.py recount 로 2·3단계를 내리고
// 칸 수를 고친 다음 교체한다. 감시가 돌고 있으면 하지 않는다.
//
// 감시(predict_machine)는 기동할 때만 마스크를 읽는다. 교체한 뒤에는 감시를
// 다시 시작해야 반영된다. 창 틀은 .rc 에 두지 않고 여기서 만든다.

class CDlg_MaskFetch : public CDialogEx
{
public:
    CDlg_MaskFetch(CFont* font, CWnd* parent, const std::string& userPath,
                   const std::string& url, int needCells);

protected:
    virtual BOOL OnInitDialog() override;
    afx_msg void OnPaint();
    afx_msg void OnReplace();
    afx_msg void OnTogglePrev();
    DECLARE_MESSAGE_MAP()

private:
    std::vector<WORD> m_tpl;
    CFont* m_font;

    std::string m_userPath;     // users\<현장>\ (끝에 \)
    std::string m_url;          // 관제서버 hotlist_mask_svr.ini 주소
    int         m_need;         // env.ini 의 NUM_OF_MACHINE_CELLS (모르면 0)

    // 마스크 64칸. 비어 있으면 없거나 읽지 못한 것.
    std::vector<int> m_cur, m_svr, m_prev;
    std::string m_curAt, m_prevAt, m_prevPath;
    CStringA    m_svrErr;
    bool        m_showPrev = false;

    CStatic m_lblHead, m_lblFoot;
    CButton m_btnReplace, m_btnPrev, m_btnClose;

    void LoadLocal();
    void LoadPrev();
    void Download();
    void Refresh();
    std::string LocalPath() const;
    std::string HistoryDir() const;
};
