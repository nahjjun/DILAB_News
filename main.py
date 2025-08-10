
from datetime import datetime
import os
from naver_news_cleaner import save_articles_to_jsonl

def run_daily_news_crawler(keyword: str, base_dir: str = "./news_data", pages: int = 6):
    # 오늘 날짜 형식
    today = datetime.now().strftime("%Y-%m-%d")
    filename = f"news_articles_{today}.jsonl"
    os.makedirs(base_dir, exist_ok=True)
    output_path = os.path.join(base_dir, filename)

    count = save_articles_to_jsonl(keyword, output_path, pages=pages)
    print(f"[{today}] '{keyword}' 관련 뉴스 {count}건 저장 완료 → {output_path}")

if __name__ == "__main__":
    run_daily_news_crawler("IT", pages=6)
