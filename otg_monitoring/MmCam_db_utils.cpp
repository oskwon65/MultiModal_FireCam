// MmCam_db_utils.cpp
#include "pch.h"
#include "MmCam_monitoring.h"

extern "C" {
#include <mysql.h>
}

#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
#include <iostream>
#include <windows.h>

void update_db_main_command(const char* new_code);

// =====================================
// 전역 변수
// =====================================
extern std::string gUserID;

// =====================================
// 파일 존재 여부 확인
// =====================================
static bool file_exists(const char* path)
{
    DWORD attrib = GetFileAttributesA(path);
    return (attrib != INVALID_FILE_ATTRIBUTES && !(attrib & FILE_ATTRIBUTE_DIRECTORY));
}

// =====================================
// 실행 환경설정 파일 (exe와 같은 폴더의 otg_monitoring.ini)
//
//   [PATHS]
//   ROOT_PATH=D:\MultiModal_FireCam\
//
// 시작 폴더(ROOT_PATH)는 env.ini 가 놓인 위치 자체를 결정하므로
// env.ini 가 아니라 이 환경설정 파일에서 먼저 읽어온다.
// 값이 없으면 exe 가 놓인 폴더를 시작 폴더로 사용한다.
// =====================================
#define APP_CONFIG_FILE     "otg_monitoring.ini"

static const char* FALLBACK_ROOT_PATH = "D:\\multi_modal\\";

// 경로 구분자를 역슬래시로 통일하고 끝에 역슬래시를 보장
std::string normalize_dir_path(std::string path)
{
    for (size_t i = 0; i < path.size(); ++i) {
        if (path[i] == '/') path[i] = '\\';
    }
    while (!path.empty() && (path.back() == ' ' || path.back() == '\t'))
        path.pop_back();
    if (!path.empty() && path.back() != '\\')
        path += '\\';
    return path;
}

// exe 가 위치한 폴더 (끝에 역슬래시 포함)
static std::string get_exe_dir()
{
    char exe_path[MAX_PATH] = { 0 };
    if (GetModuleFileNameA(nullptr, exe_path, MAX_PATH) == 0)
        return std::string();

    std::string dir(exe_path);
    const size_t pos = dir.find_last_of("\\/");
    return (pos == std::string::npos) ? std::string() : dir.substr(0, pos + 1);
}

// 환경설정 파일 전체 경로
const char* GetAppConfigPath()
{
    static std::string cfg_path;
    if (cfg_path.empty())
        cfg_path = get_exe_dir() + APP_CONFIG_FILE;
    return cfg_path.c_str();
}

// 환경설정 파일 문자열 읽기 (파일/키가 없으면 default_value 반환)
std::string read_app_config_string(const char* section, const char* key, const char* default_value)
{
    char buffer[MAX_PATH * 2] = { 0 };
    GetPrivateProfileStringA(
        section, key, default_value ? default_value : "",
        buffer, static_cast<DWORD>(sizeof(buffer)),
        GetAppConfigPath()
    );

    std::string value(buffer);
    while (!value.empty() && (value.front() == ' ' || value.front() == '\t'))
        value.erase(value.begin());
    while (!value.empty() && (value.back() == ' ' || value.back() == '\t'))
        value.pop_back();
    return value;
}

// 시작 폴더(ROOT_PATH) : 환경설정 파일에서 읽어오고 최초 1회만 캐시
//   1) exe 와 같은 폴더의 otg_monitoring.ini 의 [PATHS] ROOT_PATH
//   2) 값이 없으면 exe 가 놓인 폴더 자체
//   3) exe 경로조차 알 수 없을 때만 FALLBACK_ROOT_PATH
const char* GetMmCamRootPath()
{
    static std::string root_path;
    if (root_path.empty())
    {
        std::string value = read_app_config_string("PATHS", "ROOT_PATH", "");
        if (value.empty()) value = get_exe_dir();
        if (value.empty()) value = FALLBACK_ROOT_PATH;
        root_path = normalize_dir_path(value);
    }
    return root_path.c_str();
}

// =====================================
// env.ini 경로 생성
// =====================================
static std::string make_ini_path()
{
    if (gUserID.empty()) {
        AfxMessageBox("gUserID is empty.");
        std::exit(EXIT_FAILURE);
    }
    return std::string(GetMmCamRootPath()) + "users\\" + gUserID + "\\env.ini";
}

// =====================================
// env.ini 문자열 읽기
// =====================================
std::string read_ini_string(const char* section, const char* key, const char* default_value)
{
    const std::string ini_path = make_ini_path();

    if (!file_exists(ini_path.c_str())) {
        char current_dir[MAX_PATH] = { 0 };
        GetCurrentDirectoryA(MAX_PATH, current_dir);
        std::string msg = "(read_ini_string) File Not Found: "
            + std::string(current_dir) + " | " + ini_path
            + " | config: " + GetAppConfigPath();
        AfxMessageBox(msg.c_str());
        std::exit(EXIT_FAILURE);
    }

    char buffer[256] = { 0 };
    GetPrivateProfileStringA(
        section, key, default_value,
        buffer, static_cast<DWORD>(sizeof(buffer)),
        ini_path.c_str()
    );
    return std::string(buffer);
}

// =====================================
// continual_learning.ini 문자열 읽기
//
// 연속학습 설정은 env.ini 에서 떼어 같은 폴더의 continual_learning.ini 에
// 둔다.
// 설치할 때 한 번 정하는 값과 운영하며 만지는 값을 가르기 위해서다.
//
// 없으면 env.ini 에서 찾는다. 현장 PC 가 아직 옮기기 전일 수 있고, 그때
// 기본값으로 떨어지면 임계값이 통째로 달라진다.
// =====================================
std::string read_learn_string(const char* section, const char* key,
                              const char* default_value)
{
    if (gUserID.empty()) {
        AfxMessageBox("gUserID is empty.");
        std::exit(EXIT_FAILURE);
    }
    const std::string learn_path = std::string(GetMmCamRootPath())
        + "users\\" + gUserID + "\\continual_learning.ini";

    if (file_exists(learn_path.c_str())) {
        // 있는지 없는지를 가리려고 아무도 쓰지 않을 값을 기본으로 넣는다.
        const char* MISSING = "\x01";
        char buffer[256] = { 0 };
        GetPrivateProfileStringA(section, key, MISSING, buffer,
            static_cast<DWORD>(sizeof(buffer)), learn_path.c_str());
        if (std::string(buffer) != MISSING) return std::string(buffer);
    }
    return read_ini_string(section, key, default_value);
}

// =====================================
// db_secrets.ini 경로 생성
//   DB 비밀번호는 저장소(git)에 올라가지 않도록 env.ini 에서 분리해
//   같은 폴더의 db_secrets.ini 에 둔다.
// =====================================
static std::string make_secret_path()
{
    if (gUserID.empty()) {
        AfxMessageBox("gUserID is empty.");
        std::exit(EXIT_FAILURE);
    }
    return std::string(GetMmCamRootPath()) + "users\\" + gUserID + "\\db_secrets.ini";
}

// =====================================
// db_secrets.ini 문자열 읽기
// =====================================
std::string read_secret_string(const char* section, const char* key, const char* default_value)
{
    const std::string secret_path = make_secret_path();

    if (!file_exists(secret_path.c_str())) {
        std::string msg = "(read_secret_string) File Not Found: " + secret_path
            + "\n\nusers\\db_secrets.ini.sample 을 복사해 비밀번호를 채우세요.";
        AfxMessageBox(msg.c_str());
        std::exit(EXIT_FAILURE);
    }

    char buffer[256] = { 0 };
    GetPrivateProfileStringA(
        section, key, default_value,
        buffer, static_cast<DWORD>(sizeof(buffer)),
        secret_path.c_str()
    );
    return std::string(buffer);
}

// =====================================
// DB 설정 전역 변수 (env.ini에서 로드)
// =====================================
static std::string   g_db_loaded_user_id;   // 마지막으로 로드한 유저 ID
static std::string   g_db_host;
static std::string   g_db_user;
static std::string   g_db_pass;
static std::string   g_db_name;
static unsigned int  g_db_port = 3306;

// =====================================
static void load_db_config()
{
    // 유저 ID가 바뀌면 DB 설정 재로드
    if (!g_db_loaded_user_id.empty() && g_db_loaded_user_id == gUserID)
        return;

    const std::string ini_path = make_ini_path();

    if (!file_exists(ini_path.c_str())) {
        char current_dir[MAX_PATH] = { 0 };
        GetCurrentDirectoryA(MAX_PATH, current_dir);
        std::string msg = "(load_db_config) File Not Found: "
            + std::string(current_dir) + " | " + ini_path
            + " | config: " + GetAppConfigPath();
        AfxMessageBox(msg.c_str());
        std::exit(EXIT_FAILURE);
    }

    g_db_host = read_ini_string("DB_RUNTIME", "DB_HOST", "");
    g_db_user = read_ini_string("DB_RUNTIME", "DB_USER", "");
    g_db_pass = read_secret_string("DB_RUNTIME", "DB_PASSWORD", "");

    std::string db_name_base = read_ini_string("DB_RUNTIME", "DB_NAME_SENSOR", "");
    std::string prefix = gUserID + "_";
    g_db_name = (db_name_base.find(prefix) == 0)
        ? db_name_base
        : prefix + db_name_base;   // cj_busan_1_sensor_data

    g_db_port = static_cast<unsigned int>(
        GetPrivateProfileIntA("DB_RUNTIME", "DB_PORT", 3306, ini_path.c_str())
        );

    g_db_loaded_user_id = gUserID;   // 로드 완료 마킹
}

// =====================================
// MySQL 연결
// =====================================
MYSQL* connect_db()
{
    load_db_config();

    MYSQL* conn = mysql_init(nullptr);
    if (!conn) return nullptr;

    if (!mysql_real_connect(
        conn,
        g_db_host.c_str(),
        g_db_user.c_str(),
        g_db_pass.c_str(),
        g_db_name.c_str(),
        g_db_port,
        nullptr, 0))
    {
        mysql_close(conn);
        return nullptr;
    }
    return conn;
}

// =====================================
// 히스토리 DB 연결
//
// connect_db() 는 센서 DB(DB_NAME_SENSOR)에 붙는다. 점수 추이는 날짜별
// results_history_YYYYMMDD 테이블에 있어 다른 DB(DB_NAME_HISTORY)를 봐야
// 한다.
//
// 설정 캐시(g_db_*)를 건드리지 않으려고 값을 그때그때 읽는다. 분석 창을
// 열 때만 부르므로 몇 번 더 읽는 비용은 문제가 되지 않는다.
//
// 성공하면 dbNameOut 에 실제로 붙은 DB 이름을 담아 준다. SQL 에서 테이블을
// 지목할 때 필요하다.
// =====================================
MYSQL* connect_history_db(std::string* dbNameOut)
{
    const std::string host = read_ini_string("DB_RUNTIME", "DB_HOST", "");
    const std::string user = read_ini_string("DB_RUNTIME", "DB_USER", "");
    const std::string pass = read_secret_string("DB_RUNTIME", "DB_PASSWORD", "");

    std::string base = read_ini_string("DB_RUNTIME", "DB_NAME_HISTORY", "");
    if (base.empty()) return nullptr;

    // 파이썬 쪽과 같은 규칙 - 이미 현장 이름이 붙어 있으면 그대로 쓴다.
    const std::string prefix = gUserID + "_";
    const std::string dbName =
        (base.find(prefix) == 0) ? base : prefix + base;

    const std::string ini_path = make_ini_path();
    const unsigned int port = static_cast<unsigned int>(
        GetPrivateProfileIntA("DB_RUNTIME", "DB_PORT", 3306, ini_path.c_str()));

    MYSQL* conn = mysql_init(nullptr);
    if (!conn) return nullptr;

    if (!mysql_real_connect(conn, host.c_str(), user.c_str(), pass.c_str(),
                            dbName.c_str(), port, nullptr, 0))
    {
        mysql_close(conn);
        return nullptr;
    }

    if (dbNameOut) *dbNameOut = dbName;
    return conn;
}

// =====================================
// 히스토리 DB 의 날짜 테이블 수와 첫 날·끝 날
//
// [설정] 창이 "재학습 수집 일수" 옆에 DB 전체 기간을 보여 주려고 부른다. 테이블
// 이름만 읽고 행은 세지 않는다.
//
// 접속·읽기 제한 시간을 짧게 둔다. 기본값으로 두면 DB 가 꺼져 있거나 네트워크가
// 막혔을 때 수 초에서 수십 초를 기다린다. 호출하는 쪽이 UI 스레드가 아니어도
// 오래 붙들려 있을 이유가 없다.
//
// 실패하면 false. 성공하면 first/last 는 "YYYY-MM-DD".
// =====================================
bool read_history_span(unsigned int timeoutSec, int* nTables,
                       std::string* first, std::string* last)
{
    const std::string host = read_ini_string("DB_RUNTIME", "DB_HOST", "");
    const std::string user = read_ini_string("DB_RUNTIME", "DB_USER", "");
    const std::string pass = read_secret_string("DB_RUNTIME", "DB_PASSWORD", "");

    std::string base = read_ini_string("DB_RUNTIME", "DB_NAME_HISTORY", "");
    if (base.empty()) return false;

    const std::string prefix = gUserID + "_";
    const std::string dbName =
        (base.find(prefix) == 0) ? base : prefix + base;

    const std::string ini_path = make_ini_path();
    const unsigned int port = static_cast<unsigned int>(
        GetPrivateProfileIntA("DB_RUNTIME", "DB_PORT", 3306, ini_path.c_str()));

    MYSQL* conn = mysql_init(nullptr);
    if (!conn) return false;

    unsigned int to = timeoutSec;
    mysql_options(conn, MYSQL_OPT_CONNECT_TIMEOUT, &to);
    mysql_options(conn, MYSQL_OPT_READ_TIMEOUT, &to);
    mysql_options(conn, MYSQL_OPT_WRITE_TIMEOUT, &to);

    if (!mysql_real_connect(conn, host.c_str(), user.c_str(), pass.c_str(),
                            dbName.c_str(), port, nullptr, 0))
    {
        mysql_close(conn);
        return false;
    }

    std::string esc(dbName.size() * 2 + 1, '\0');
    const unsigned long n = mysql_real_escape_string(
        conn, &esc[0], dbName.c_str(), (unsigned long)dbName.size());
    esc.resize(n);

    const std::string sql =
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = '" + esc + "' "
        "AND table_name LIKE 'results_history_%' "
        "AND table_type = 'BASE TABLE' ORDER BY table_name";

    bool ok = false;
    if (mysql_query(conn, sql.c_str()) == 0)
    {
        MYSQL_RES* res = mysql_store_result(conn);
        if (res)
        {
            int cnt = 0;
            std::string f, l;
            while (MYSQL_ROW row = mysql_fetch_row(res))
            {
                if (!row[0]) continue;
                const std::string nm = row[0];
                if (nm.size() < 8) continue;
                const std::string d8 = nm.substr(nm.size() - 8);
                const std::string iso =
                    d8.substr(0, 4) + "-" + d8.substr(4, 2) + "-" + d8.substr(6, 2);
                if (cnt == 0) f = iso;
                l = iso;
                ++cnt;
            }
            mysql_free_result(res);
            if (nTables) *nTables = cnt;
            if (first) *first = f;
            if (last)  *last = l;
            ok = true;
        }
    }

    mysql_close(conn);
    return ok;
}

// =====================================
// current_value(id=1) 읽기
//
// 컬럼 순서:
//   row[0] mscore       DOUBLE
//   row[1] error_code   CHAR(4)
//   row[2] main_command CHAR(8)
//   row[3] updated_at   DATETIME
// =====================================
CurrentStatus read_db_current_status()
{
    CurrentStatus result{};
    result.valid = false;
    result.mscore = 0.0;
    result.error_code[0] = '\0';
    result.main_command[0] = '\0';
    result.updated_at[0] = '\0';

    MYSQL* conn = connect_db();
    if (!conn) return result;

    const char* sql =
        "SELECT mscore, error_code, main_command, "
        "DATE_FORMAT(updated_at, '%Y-%m-%d %H:%i:%s') "
        "FROM current_value "
        "WHERE id = 1";

    if (mysql_query(conn, sql) != 0) {
        mysql_close(conn);
        return result;
    }

    MYSQL_RES* res = mysql_store_result(conn);
    if (!res) {
        mysql_close(conn);
        return result;
    }

    MYSQL_ROW row = mysql_fetch_row(res);
    if (row) {
        result.valid = true;
        result.mscore = row[0] ? atof(row[0]) : 0.0;

        if (row[1]) strncpy_s(result.error_code, sizeof(result.error_code), row[1], _TRUNCATE);
        else        result.error_code[0] = '\0';

        if (row[2]) strncpy_s(result.main_command, sizeof(result.main_command), row[2], _TRUNCATE);
        else        result.main_command[0] = '\0';

        if (row[3]) strncpy_s(result.updated_at, sizeof(result.updated_at), row[3], _TRUNCATE);
        else        result.updated_at[0] = '\0';
    }

    mysql_free_result(res);
    mysql_close(conn);
    return result;
}

// =====================================
// main_command 업데이트
// =====================================
void update_db_main_command(const char* new_code)
{
    if (!new_code) return;

    MYSQL* conn = connect_db();
    if (!conn) return;

    char escaped[32] = { 0 };
    mysql_real_escape_string(
        conn, escaped, new_code,
        static_cast<unsigned long>(strlen(new_code))
    );

    char sql[256] = { 0 };
    std::snprintf(
        sql, sizeof(sql),
        "UPDATE current_value SET main_command='%s' WHERE id=1",
        escaped
    );

    mysql_query(conn, sql);
    mysql_close(conn);
}