// Dlg_CamPos.cpp: 카메라 이동보정 확인 창
//

#include "pch.h"
#include "resource.h"
#include "MmCam_monitoring.h"
#include "MmCam_monitoringDlg.h"
#include "Dlg_CamPos.h"
#include "afxdialogex.h"

IMPLEMENT_DYNAMIC(CDlg_CamPos, CDialogEx)

CDlg_CamPos::CDlg_CamPos(CWnd* pParent /*=nullptr*/)
    : CDialogEx(IDD_DLG_CAMPOS, pParent)
{
}

CDlg_CamPos::~CDlg_CamPos()
{
}

void CDlg_CamPos::DoDataExchange(CDataExchange* pDX)
{
    CDialogEx::DoDataExchange(pDX);
    DDX_Control(pDX, IDC_CHK_CAMPOS, m_chk);
}

BEGIN_MESSAGE_MAP(CDlg_CamPos, CDialogEx)
END_MESSAGE_MAP()

//---------------------------------------------------------

BOOL CDlg_CamPos::OnInitDialog()
{
    CDialogEx::OnInitDialog();

    // 프로그램 전체와 같은 글꼴을 쓴다. 창마다 글꼴이 다르면 같은
    // 프로그램인데 화면마다 인상이 달라진다.
    m_font.CreateFont(16, 0, 0, 0, FW_NORMAL, FALSE, FALSE, 0,
        DEFAULT_CHARSET, OUT_DEFAULT_PRECIS, CLIP_DEFAULT_PRECIS,
        DEFAULT_QUALITY, DEFAULT_PITCH | FF_DONTCARE, _T(UI_FONT_NAME));

    SetFont(&m_font);
    SendMessageToDescendants(WM_SETFONT, (WPARAM)m_font.GetSafeHandle(), TRUE);

    m_chk.SetCheck(m_bAdjust ? BST_CHECKED : BST_UNCHECKED);

    // 부모(메인 창) 가운데에 띄운다.
    CenterWindow(GetParent());

    return TRUE;
}

//---------------------------------------------------------

void CDlg_CamPos::OnOK()
{
    m_bAdjust = (m_chk.GetCheck() == BST_CHECKED);
    CDialogEx::OnOK();
}
