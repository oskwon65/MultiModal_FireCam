
// mm_cam_monitoring.h: PROJECT_NAME 애플리케이션에 대한 주 헤더 파일입니다.
//

#pragma once

#ifndef __AFXWIN_H__
	#error "PCH에 대해 이 파일을 포함하기 전에 'pch.h'를 포함합니다."
#endif

#include "resource.h"		// 주 기호입니다.

// current_status 테이블 1행을 담는 구조체
struct CurrentStatus
{
    bool   valid;             // row 존재 여부

    double avg_score;
    double avg_mse;

    char   error_code[5];     // CHAR(4) + '\0'
    char   main_command[9];   // CHAR(8) + '\0'
    char   debug_msg[101];    // VARCHAR(100) + '\0'
};

// Cmm_cammonitoringApp:
// 이 클래스의 구현에 대해서는 mm_cam_monitoring.cpp을(를) 참조하세요.
//

class Cmm_cammonitoringApp : public CWinApp
{
public:
	Cmm_cammonitoringApp();

// 재정의입니다.
public:
	virtual BOOL InitInstance();

// 구현입니다.

	DECLARE_MESSAGE_MAP()
};

extern Cmm_cammonitoringApp theApp;
