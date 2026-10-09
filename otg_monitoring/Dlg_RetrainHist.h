#pragma once

#include <string>
#include <vector>

// 재학습 이력 창
//
// 감시(predict_machine/auto_retrain.py)가 users/<현장>/auto_retrain_history.txt 에
// 한 줄씩 쌓는 자동 재학습 이력을 최근 것부터 모두 보인다.
//
//   한 줄  시작 <탭> 종료 <탭> 기여 w <탭> 결과 <탭> 승격된 세대 <탭> 판단 점수
//
// [재학습] 창 아래쪽에도 최근 10건이 나오지만, 그 창은 재학습을 돌리는 곳이라
// 이력만 보려고 열기에는 무겁다. 판단 점수는 2026-10-07 전 줄에는 없어 '-' 로 적는다.
//
// 맨 위 한 줄에서 자동 재학습을 켜고 끄고 간격을 정한다([재학습] 창에서 옮겨 왔다).
// 감시가 continual_learning.ini 의 AUTO_RETRAIN · AUTO_RETRAIN_HOURS 를 볼 때마다
// 읽으므로 [설정저장] 하는 즉시 따른다. 창 틀은 .rc 에 두지 않고 여기서 만든다.

class CDlg_RetrainHist : public CDialogEx
{
public:
    CDlg_RetrainHist(CFont* font, CWnd* parent);

protected:
    virtual BOOL OnInitDialog() override;
    afx_msg void OnReload();
    afx_msg void OnAutoChanged();
    afx_msg void OnSaveAuto();
    virtual void OnCancel() override;
    DECLARE_MESSAGE_MAP()

private:
    std::vector<WORD> m_tpl;
    CFont* m_font;
    CFont  m_fontMono;

    CStatic m_lblHead;
    CEdit   m_edLog;
    CButton m_btnReload, m_btnClose;

    // 자동 재학습 줄
    CButton m_chkAuto, m_btnSave;
    CEdit   m_edHours;
    CStatic m_lblAuto;
    bool    m_dirty = false;      // 저장하지 않은 변경이 있는가
    bool    m_loading = false;    // 읽어 넣는 동안의 EN_CHANGE 는 변경으로 세지 않는다

    void Fill();
    void LoadAuto();
    void UpdateAutoEnable();
};
