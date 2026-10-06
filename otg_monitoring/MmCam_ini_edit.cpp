// MmCam_ini_edit.cpp
//
// env.ini 의 값을 UTF-8 을 깨뜨리지 않고 읽고 쓴다.
//
// [ Win32 INI API 를 쓰지 않는 이유 ]
//   WritePrivateProfileStringA 는 파일을 ANSI(한국어 Windows 에서는 CP949)로
//   해석한다. 그런데 users/<id>/env.ini 는 UTF-8 이고 한글 주석이 들어 있다.
//   그 API 로 값 하나를 고치면 나머지 줄의 UTF-8 바이트가 CP949 로 재해석되어
//   다시 쓰이면서 주석이 깨질 수 있다. 파이썬 쪽은 configparser 가
//   encoding="utf-8" 로 읽으므로, 깨지면 그때부터 설정 파일 전체를 못 읽는다.
//
//   그래서 Win32 API 를 쓰지 않고 파일을 바이트 그대로 읽어 해당 줄만 바꾼 뒤
//   그대로 되쓴다. 손대지 않은 줄은 한 바이트도 건드리지 않는다.
//
// [ 섹션 안에서만 찾는다 ]
//   env.ini 에는 [NETWORK] [PATHS] [CONSTANTS] ... 여러 섹션이 있고 같은
//   이름의 키가 다른 섹션에 있을 수 있다. 반드시 지정한 섹션 범위 안에서만
//   찾고 넣는다.

#include "pch.h"

#include <string>
#include <vector>
#include <fstream>
#include <sstream>
#include <algorithm>
#include <cctype>

namespace {

std::string trim(const std::string& s)
{
    size_t b = s.find_first_not_of(" \t\r\n");
    if (b == std::string::npos) return "";
    size_t e = s.find_last_not_of(" \t\r\n");
    return s.substr(b, e - b + 1);
}

bool iequals(const std::string& a, const std::string& b)
{
    if (a.size() != b.size()) return false;
    for (size_t i = 0; i < a.size(); ++i)
        if (std::tolower((unsigned char)a[i]) != std::tolower((unsigned char)b[i]))
            return false;
    return true;
}

// 줄이 [SECTION] 형태면 이름을 돌려준다. 아니면 빈 문자열.
std::string section_of(const std::string& line)
{
    std::string t = trim(line);
    if (t.size() >= 2 && t.front() == '[' && t.back() == ']')
        return trim(t.substr(1, t.size() - 2));
    return "";
}

// 줄이 key = value 형태면 키 이름을 돌려준다. 주석(; #)은 키가 아니다.
std::string key_of(const std::string& line)
{
    std::string t = trim(line);
    if (t.empty() || t[0] == ';' || t[0] == '#') return "";
    size_t eq = t.find('=');
    if (eq == std::string::npos) return "";
    return trim(t.substr(0, eq));
}

bool read_lines(const std::string& path, std::vector<std::string>& out, bool& crlf)
{
    std::ifstream f(path.c_str(), std::ios::binary);
    if (!f) return false;

    std::ostringstream ss;
    ss << f.rdbuf();
    std::string all = ss.str();

    crlf = all.find("\r\n") != std::string::npos;

    out.clear();
    std::string cur;
    for (size_t i = 0; i < all.size(); ++i) {
        if (all[i] == '\n') {
            if (!cur.empty() && cur.back() == '\r') cur.pop_back();
            out.push_back(cur);
            cur.clear();
        } else {
            cur += all[i];
        }
    }
    if (!cur.empty()) out.push_back(cur);
    return true;
}

bool write_lines(const std::string& path, const std::vector<std::string>& lines, bool crlf)
{
    // 쓰다가 중단되어 설정 파일이 반만 남는 일을 막는다.
    const std::string tmp = path + ".tmp";
    {
        std::ofstream f(tmp.c_str(), std::ios::binary | std::ios::trunc);
        if (!f) return false;
        const char* eol = crlf ? "\r\n" : "\n";
        for (size_t i = 0; i < lines.size(); ++i)
            f << lines[i] << eol;
        if (!f) return false;
    }
    ::DeleteFileA(path.c_str());
    return ::MoveFileA(tmp.c_str(), path.c_str()) != 0;
}

} // namespace

// ---------------------------------------------------------------------------
// 지정 섹션의 키 값을 읽는다. 없으면 default_value.
// ---------------------------------------------------------------------------
std::string ini_read_utf8(const std::string& path,
                          const std::string& section,
                          const std::string& key,
                          const std::string& default_value)
{
    std::vector<std::string> lines;
    bool crlf = true;
    if (!read_lines(path, lines, crlf)) return default_value;

    bool in_section = false;
    for (size_t i = 0; i < lines.size(); ++i) {
        std::string sec = section_of(lines[i]);
        if (!sec.empty()) {
            in_section = iequals(sec, section);
            continue;
        }
        if (!in_section) continue;

        std::string k = key_of(lines[i]);
        if (!k.empty() && iequals(k, key)) {
            size_t eq = lines[i].find('=');
            return trim(lines[i].substr(eq + 1));
        }
    }
    return default_value;
}

int ini_read_int_utf8(const std::string& path,
                      const std::string& section,
                      const std::string& key,
                      int default_value)
{
    std::string v = ini_read_utf8(path, section, key, "");
    if (v.empty()) return default_value;
    try { return std::stoi(v); }
    catch (...) { return default_value; }
}

// ---------------------------------------------------------------------------
// 지정 섹션의 키 값을 바꾼다. 키가 없으면 그 섹션 끝에 추가하고,
// 섹션 자체가 없으면 파일 끝에 섹션과 함께 만든다.
//
// 손대지 않은 줄은 바이트 그대로 보존된다.
// ---------------------------------------------------------------------------
bool ini_write_utf8(const std::string& path,
                    const std::string& section,
                    const std::string& key,
                    const std::string& value)
{
    std::vector<std::string> lines;
    bool crlf = true;
    if (!read_lines(path, lines, crlf)) return false;

    bool in_section = false;
    int  section_end = -1;   // 해당 섹션의 마지막 내용 줄 다음 위치

    for (size_t i = 0; i < lines.size(); ++i) {
        std::string sec = section_of(lines[i]);
        if (!sec.empty()) {
            if (in_section) {          // 다음 섹션을 만났다 = 우리 섹션 끝
                section_end = (int)i;
                in_section = false;
            }
            if (iequals(sec, section)) {
                in_section = true;
                section_end = (int)i + 1;
            }
            continue;
        }
        if (!in_section) continue;

        std::string k = key_of(lines[i]);
        if (!k.empty() && iequals(k, key)) {
            lines[i] = key + " = " + value;     // 제자리 교체
            return write_lines(path, lines, crlf);
        }
        if (!trim(lines[i]).empty())
            section_end = (int)i + 1;           // 빈 줄 앞까지를 섹션 끝으로
    }

    if (section_end >= 0) {
        lines.insert(lines.begin() + section_end, key + " = " + value);
    } else {
        lines.push_back("");
        lines.push_back("[" + section + "]");
        lines.push_back(key + " = " + value);
    }
    return write_lines(path, lines, crlf);
}

bool ini_write_int_utf8(const std::string& path,
                        const std::string& section,
                        const std::string& key,
                        int value)
{
    return ini_write_utf8(path, section, key, std::to_string(value));
}

// stage_status.ini 의 UPDATED_AT("YYYY-MM-DD HH:MM:SS", 현지 시각)이 지금으로부터
// 몇 초 전인지 돌려준다. 읽을 수 없으면 -1.
//
// 파이썬은 30초마다 이 파일을 다시 쓴다. 프로세스가 죽으면 마지막 값이 그대로
// 남아, 화면이 죽은 감시의 단계 등을 계속 초록으로 보여 준다. 낡았는지는 이
// 시각으로만 알 수 있다.
long long status_age_seconds(const std::string& updated_at)
{
    int Y = 0, M = 0, D = 0, h = 0, m = 0, s = 0;
    if (sscanf_s(updated_at.c_str(), "%d-%d-%d %d:%d:%d", &Y, &M, &D, &h, &m, &s) != 6)
        return -1;

    SYSTEMTIME st = {};
    st.wYear = (WORD)Y; st.wMonth = (WORD)M; st.wDay = (WORD)D;
    st.wHour = (WORD)h; st.wMinute = (WORD)m; st.wSecond = (WORD)s;

    FILETIME ft_then, ft_now;
    if (!SystemTimeToFileTime(&st, &ft_then))
        return -1;

    SYSTEMTIME now;
    GetLocalTime(&now);
    SystemTimeToFileTime(&now, &ft_now);

    ULARGE_INTEGER a, b;
    a.LowPart = ft_then.dwLowDateTime; a.HighPart = ft_then.dwHighDateTime;
    b.LowPart = ft_now.dwLowDateTime;  b.HighPart = ft_now.dwHighDateTime;

    // 100ns 단위 -> 초. 시계가 뒤로 간 경우는 0 으로 본다.
    if (b.QuadPart < a.QuadPart) return 0;
    return (long long)((b.QuadPart - a.QuadPart) / 10000000ULL);
}
