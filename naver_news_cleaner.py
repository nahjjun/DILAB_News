
import re
import json
import requests
import urllib.parse
import html
from bs4 import BeautifulSoup

# ─── 설정 ───
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 "
        "Mobile/15A5341f Safari/604.1"
    )
}



# ─── 1) 검색결과에서 페이지별로 데이터 뽑기 ───
def fetch_search_links(keyword: str, pages: int = 5):
    seen = set() # 중복된 기사 url 제거를 위한 set 자료형
    results = [] # 최종으로 반환할 (제목, url) 구조의 튜플 리스트

    # 페이지 단위로 데이터 크롤링
    for page in range(1, pages+1):
        # 검색 결과의 시작 위치 인덱스 지정
        start = 1 + (page-1) * 10

        # 네이버 모바일 뉴스 검색 결과 페이지를 구성하는 URL 쿼리 파라미터 지정
        url = (
            "https://m.search.naver.com/search.naver"
            "?ssc=tab.m_news.all" # 네이버 모바일의 검색 옵션을 틀었을 때 나오는 파라미터.
            f"&query={urllib.parse.quote(keyword)}"
            f"&start={start}"
            "&pd=4"  # 기간 조건을 활성화
            "&nso=so:r,p:1d"  # nso파라미터 최신순 정렬(nso=so:{정렬방식},p:{기간지정},a{기타옵션}) + 최근 1일
        )

        # Naver모바일 뉴스 검색 결과 페이지의 HTML을 불러와서 BeautifulSoup객체로 파싱
          # get 요청 보낼 url, header, timeout 설정
          # timeout : 요청 제한 시간 설정(초 단위)
        resp = requests.get(url, headers=HEADERS, timeout=5)
        resp.raise_for_status() # raise_for_status() => Response가 오류일 경우, 예외를 발생시키는 함수
        soup = BeautifulSoup(resp.text, "html.parser") # response로 온 text 본문(html 코드) 'html.parser' 타입 지정 후 BeautifulSoup 객체 생성

				# 링크<a href="...">요소만 골라냄
        for a in soup.find_all("a", href=True):
            # a["href"]로 URL을 / a.get_text(strip=True)로 태그 안의 보이는 텍스트(제목)을 가져옴
				    # strip=True는 양쪽 공백을 자동으로 제거
            href, text = a["href"], a.get_text(strip=True)

            # 링크 URL이 Naver뉴스 도메인인지, 그리고 제목에 키워드가 포함되었는지 확인
            if href.startswith("https://n.news.naver.com/article/") and keyword in text:
                if href not in seen:
                    seen.add(href)
                    results.append((text, href))
    return results

# ─── 2) URL → 모바일 읽기 페이지 → 본문 추출 ───
# 입력을 url이라는 stirng형식을 받아서, 결과로 string으로 반환하는 함수를 정의
def fetch_article_body(url: str) -> str:   # -> 파이썬의 함수 어노테이션 함수. 함수의 인자, 반환값의 타입 권장을 지정할 수 있음
    # 1) 데스크탑용 URL → 모바일 읽기용 URL로 변환
    # 데스크탑(n.news.naver.com) -> 모바일(m.news.naver.com)형식으로 변환
    m = re.match(r"https://n\.news\.naver\.com/article/(\d+)/(\d+)", url)
        # re.match(pattern, string) => 지정한 패턴이 string의 시작부터 맞는지 확인하는 함수
        # https://n.news.naver.com/article/ + 숫자가 1번 이상 반복 + "/" + 숫자가 한번 이상 반복이라는 정규식
        # Match 객체를 반환하는데, 해당 객체로 patter과 string이 일치한 부분들을 가져올 수 있다.

    # 만약 받은 문자열이 해당 모바일 읽기용 url이 맞다면, 해당 기사의 ID를 추출해서 모바일 url로 재구성한다.
    if m:
        # 기사 ID(oid, aid)를 추출해서 모바일 URL로 재구성
        # oid : 언론사 ID / aid : 기사 ID
        oid, aid = m.groups()
        url = f"https://m.news.naver.com/read.nhn?oid={oid}&aid={aid}"
        # ㄴ> read.nhn : 네이버 뉴스 모바일 웹의 "기사 보기 뷰 핸들러(legacy 엔드포인트)"

    # 2) 페이지 요청 & 파싱
    # requests.get()으로 해당 URL페이지 HTML을 가져옴, HEADERS는 브라우저처럼 보이기 위한
    # User-Agent 포함헤더
    resp = requests.get(url, headers=HEADERS, timeout=5)
    # 요청 실패시 에러 발생
    resp.raise_for_status()
    # BeautifulSoup으로 HTML파싱
    soup = BeautifulSoup(resp.text, "html.parser")

    # 3) 사용 가능한 본문 컨테이너를 가져오기
    container = (
        soup.select_one("div#newsct_article")
        or soup.select_one("div#articleBodyContents") # 위에거가 없으면 이거라도
        or soup.select_one("div#newsEndContents") # 위에거가 없으면 이거라도
    )
    if not container:
        return ""
    # ㄴ> 여기서 container는 Tag 객체이다.


    # 4) 컨테이너 전체 텍스트를 줄 단위로 가져오기
    # HTML태그를 제거하고 순수 텍스트만 추출
    # 문단 구분을 위해 \n으로 나눔
    raw = container.get_text(separator="\n", strip=True)


    # 5) 줄별 필터링: 짧거나 안내 문구 제거
    # 길이가 30자 미만인 줄은 대부분 광고나 잡다한 문구이므로 제외
    # bad_tokens에 포함된 단어가 있는 줄도 제외
    bad_tokens = ["구독", "언론사", "댓글", "프리미엄", "beta"]
    lines = []
    # .splitlines() 해당 텍스트를 줄바꿈 기준으로 나눠서 리스트 형태로 반환
    for line in raw.splitlines():
        txt = line.strip() # 공백 제거
        if len(txt) < 30:
            continue

        # bad_tokens에서 token을 하나씩 빼서 확인하는데, 해당 token이 txt에 들어있는지(in) 확인한다.
        # 만약 해당 경우(전체 조건) 중 하나라도 True이면(any) => 전체 결과가 True이다.
        if any(token in txt for token in bad_tokens):
            continue
        # bad_tokens에 포함되는 단어가 들어가지 않은 txt라면, return할 lines 배열에 결과 append
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
    # ㄴ> t에서 해당 기호들 중 하나에 해당하는 부분이 있다면 ''로 치환

    # 5) 괄호 속 설명 제거
    t = re.sub(r'''
        \[        # 대괄호 열기
        [^\]]*    # [...] 중 하나 & "]"가 아닌 문자들이 0개 이상
        \]        # 대괄호 닫기
        |         # or
        \(        # 소괄호 열기
        [^\)]*    # [...] 중 하나 & ")"가 아닌 문자들이 0개 이상
        \)        # 소괄호 닫기
    ''', '', t, flags=re.X)

    # 6) 제어문자 제거
    t = re.sub(r'[\t\r]', ' ', t) # \t, \r 중 하나

    # 7) 추가 정규화
    t = re.sub(r'\b네이버뉴스\b', '', t)
    t = re.sub(r'[\w\.-]+@[\w\.-]+', '', t)
    t = re.sub(r'(사진=?|=사진|/사진)', '', t)

    # 8) 연속 공백/개행 통일
    t = re.sub(r'\n{3,}', '\n\n', t) # \n이 3번 이상 반복하면 \n\n으로 치환
    t = re.sub(r' {2,}', ' ', t) # 공백이 2번 이상 반복하면 공백 1칸으로 치환

    # 9) strip (공백 제거)
    return t.strip()




# 몇개의 데이터가 저장되었는지 반환한다.
def save_articles_to_jsonl(keyword: str, output_path: str, pages: int = 5):
    """
      (이전: TXT 저장) → (변경: JSONL 저장)
      한 줄에 하나의 JSON 객체를 기록: {"title": "...", "body": "..."}
      Hugging Face datasets.load_dataset("json", data_files=..., split="train")로 바로 로드 가능.
      반환값: 실제로 기록된 레코드 수
    """
    links = fetch_search_links(keyword, pages) # 제공받은 키워드, 페이지 수로 기사 제목, 링크 가져옴
    
    written = 0
    with open(output_path, "w", encoding="utf-8") as f:
      for title, href in links:
        try:
          body = fetch_article_body(href)
        except Exception:# 개별 기사 parsing 실패는 건너뛰도록 설정
          continue

        clean_title = clean_text(title)
        clean_body = clean_text(body)

        j = {"title": clean_title, "body": clean_body}
        f.write(json.dumps(j, ensure_ascii=False))
        f.write("\n")
        written += 1

    return written

