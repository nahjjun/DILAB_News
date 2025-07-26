
import re
import requests
import urllib.parse
import html
from bs4 import BeautifulSoup

# ─── 설정 ───
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
    )
}

        # "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
        # "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 "
        # "Mobile/15A5341f Safari/604.1"



# ─── 1) 검색결과에서 페이지별로 데이터 뽑기 ───
def fetch_search_links(keyword: str, pages: int = 5):
    seen = set()
    results = []

    # 페이지 단위로 데이터 크롤링
    for page in range(1, pages+1):
        start = 1 + (page-1) * 10
        url = (
            "https://m.search.naver.com/search.naver"
            "?where=m_news"
            f"&query={urllib.parse.quote(keyword)}"
            f"&start={start}"
        )
        resp = requests.get(url, headers=HEADERS, timeout=5)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")

        for a in soup.find_all("a", href=True):
            href, text = a["href"], a.get_text(strip=True)
            if href.startswith("https://n.news.naver.com/article/") and keyword in text:
                if href not in seen:
                    seen.add(href)
                    results.append((text, href))
    return results

# ─── 2) URL → 모바일 읽기 페이지 → 본문 추출 ───
# 입력을 url이라는 stirng형식을 받아서, 결과로 string으로 반환하는 함수를 정의
def fetch_article_body(url: str) -> str:
    # 1) 데스크탑용 URL → 모바일 읽기용 URL로 변환
    # 데스크탑(n.news.naver.com) -> 모바일(m.news.naver.com)형식으로 변환
    m = re.match(r"https://n\.news\.naver\.com/article/(\d+)/(\d+)", url)
    if m:
        # 기사 ID(oid, aid)를 추출해서 모바일 URL로 재구성
        oid, aid = m.groups()
        url = f"https://m.news.naver.com/read.nhn?oid={oid}&aid={aid}"

    # 2) 페이지 요청 & 파싱
    # requests.get()으로 해당 URL페이지 HTML을 가져옴, HEADERS는 브라우저처럼 보이기 위한
    # User-Agent 포함헤더
    resp = requests.get(url, headers=HEADERS, timeout=5)
    # 요청 실패시 에러 발생
    resp.raise_for_status()
    # BeautifulSoup으로 HTML파싱
    soup = BeautifulSoup(resp.text, "html.parser")

    # 3) 가능한 본문 컨테이너들
    container = (
        soup.select_one("div#newsct_article")
        or soup.select_one("div#articleBodyContents")
        or soup.select_one("div#newsEndContents")
    )
    if not container:
        return ""

    # 4) 컨테이너 전체 텍스트를 줄 단위로 가져오기
    # HTML태그를 제거하고 순수 텍스트만 추출
    # 문단 구분을 위해 \n으로 나눔
    raw = container.get_text(separator="\n", strip=True)
    bad_tokens = ["구독", "언론사", "댓글", "프리미엄", "beta"]
    lines = []

    # 5) 줄별 필터링: 짧거나 안내 문구 제거
    # 길이가 30자 미만인 줄은 대부분 광고나 잡다한 문구이므로 제외
    # bad_tokens에 포함된 단어가 있는 줄도 제외
    for line in raw.splitlines():
        txt = line.strip()
        if len(txt) < 30:
            continue
        if any(token in txt for token in bad_tokens):
            continue
        lines.append(txt)

    # 6) 빈 줄 한 줄씩 넣어서 합치기
    # 문단 사이에 빈 줄을 넣어서 가독성 향상
    return "\n\n".join(lines)



# 3) 정제 (Cleaning)

def clean_text(text):
    # 1) HTML 엔티티(특수문자) 디코딩
    t = html.unescape(text)

    # 2) 스마트따옴표·전각문자 통일
    t = t.replace('“', '"').replace('”', '"')

    # 3) 이메일·URL·숫자 플레이스홀더
    # re.X 플래그를 지정해줌으로써, 패턴 내 공백, 주석 허용

    t = re.sub(r'''
        \b  # 단어 경계 (앵커)
        [\w\.-]+ # (문자들(A-Za-z0-9), ".", "-") 중 하나가 1회 이상 반복됨
        @[\w\.-]+ # 위와 동일
        \.\w+ # "." 다음에 단어가 1개 이상 반복됨
        \b  # 단어 경계 종료
    ''', '<EMAIL>', t, re.X) # 해당 형태의 단어 "<EMAIL>" 태그로 변경


    t = re.sub(r'https?://\S+|www\.\S+', '<URL>', t)

    # 4) 불필요 기호 제거
    t = re.sub(r'[※■▶★♡♥]', '', t)
    # 5) 괄호 속 설명 제거
    t = re.sub(r'\[[^\]]*\]|\([^)]*\)', '', t)
    # 6) 제어문자 제거
    t = re.sub(r'[\t\r]', ' ', t)
    # 7) 연속 공백/개행 통일
    t = re.sub(r'\n{3,}', '\n\n', t)
    t = re.sub(r' {2,}', ' ', t)
    # 8) strip
    return t.strip()





def save_articles_to_txt(keyword: str, output_path: str, pages: int = 5):
    links = fetch_search_links(keyword, pages)
    with open(output_path, "w", encoding="utf-8") as f:
        for i, (title, href) in enumerate(links, 1):
            body = fetch_article_body(href)
            clean_title = clean_text(title)
            clean_body = clean_text(body)

            f.write(f"### 기사 {i}\n")
            f.write(clean_title + "\n\n")
            f.write(clean_title + "\n")
            f.write("=" * 80 + "\n\n")
    return len(links)

