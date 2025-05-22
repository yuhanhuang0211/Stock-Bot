import os
import logging
from urllib.parse import urlparse
from dotenv import load_dotenv
from googleapiclient.discovery import build
from newspaper import Article, Config as NewspaperConfig # newspaper4k 也使用 Config
import requests

load_dotenv()

# --- 環境變數與初始化 ---
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

assert SEARCH_API_KEY, "缺少 SEARCH_API_KEY，news_summary 模組無法運行"
assert SEARCH_ENGINE_ID, "缺少 SEARCH_ENGINE_ID，news_summary 模組無法運行"

# 記錄器設定（與其他模組一致）
logger = logging.getLogger(__name__)
if not logger.handlers: # 若模組被多次匯入，避免重複添加 handler
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(module)s - %(funcName)s - %(message)s')


# --- 核心邏輯 ---
def _Google_Search_api_call(query: str):
    """內部函式：呼叫 Google Custom Search API。"""
    service = build("customsearch", "v1", developerKey=SEARCH_API_KEY)
    res = service.cse().list(
        q=query,
        cx=SEARCH_ENGINE_ID,
        num=5, # 抓取數筆結果以找到可用的連結
        # 若 CSE 有設置，可考慮加上 dateRestrict="d7" 或 sort="date"
    ).execute()
    return res

def _get_first_accessible_url(query_for_log: str, search_results_items: list | None):
    """內部函式：從搜尋結果中找出第一個可以正常連線的網址。"""
    if not search_results_items:
        return None, None
        
    for item in search_results_items:
        url = item.get("link")
        if not url:
            continue
        try:
            response = requests.head(url, timeout=5, allow_redirects=True)
            if response.status_code == 200:
                logger.info(f"查詢「{query_for_log}」找到可用連結：{url}")
                return url, item # 回傳網址與該項目以取得後續資訊
            else:
                logger.warning(f"連結 {url}（查詢：{query_for_log}）回應碼為 {response.status_code}，略過。")
        except requests.exceptions.RequestException as e:
            logger.warning(f"檢查連結 {url}（查詢：{query_for_log}）失敗：{e}，略過。")
            continue
    return None, None

def _summarize_article_with_newspaper(url: str, item_from_search=None) -> dict:
    """內部函式：使用 newspaper4k 擷取與摘要文章內容。"""
    try:
        # newspaper4k 設定
        config = NewspaperConfig()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        config.request_timeout = 15  # 秒數
        config.memoize_articles = False # 不快取文章
        config.fetch_images = False    # 不下載圖片
        config.language = 'zh'         # 指定語言以改善自然語言處理效果

        article = Article(url, config=config)
        article.download()
        article.parse()
        article.nlp() # 執行 NLP 分析（包括摘要）

        publish_date_str = None
        if article.publish_date:
            publish_date_str = article.publish_date.strftime('%Y-%m-%d')
        elif item_from_search: # 若無則回退使用搜尋結果中的日期
            meta = item_from_search.get("pagemap", {}).get("metatags", [{}])[0]
            pd_value = meta.get("article:published_time") or meta.get("publishdate") or meta.get("pubdate")
            if pd_value:
                publish_date_str = pd_value.split('T')[0]

        return {
            "title": article.title or (item_from_search.get("title", "N/A") if item_from_search else "N/A"),
            "summary": article.summary or (item_from_search.get("snippet", "N/A") if item_from_search else "N/A"), # newspaper4k 提供的摘要
            "publish_date": publish_date_str,
            "source": urlparse(url).netloc,
            "url": url
        }
    except Exception as e:
        logger.error(f"處理網址 {url} 時，newspaper4k 發生錯誤：{e}", exc_info=True)
        title = item_from_search.get("title", "無法取得標題") if item_from_search else "標題處理錯誤"
        summary = item_from_search.get("snippet", "無法取得摘要 (newspaper4k)") if item_from_search else "摘要處理錯誤"
        return {
            "title": title, "summary": summary, "publish_date": None,
            "source": urlparse(url).netloc if url else "未知來源", "url": url, "error": str(e)
        }

# --- 提供給 app.py 使用的公開函式 ---
def get_news_summary(query: str) -> str:
    """
    根據輸入查詢新聞，並回傳格式化後的摘要字串。
    使用 newspaper4k 執行摘要處理。
    """
    try:
        logger.info(f"接收到新聞摘要請求：'{query}'")
        search_response = _Google_Search_api_call(query)

        if "items" not in search_response or not search_response["items"]:
            logger.info(f"Google 搜尋「{query}」（新聞）未找到結果。")
            return f"抱歉，找不到與「{query}」相關的新聞。"

        url, item = _get_first_accessible_url(query, search_response["items"])
        
        if not url or not item:
            logger.warning(f"新聞查詢「{query}」未找到可讀取的連結。")
            return f"抱歉，目前找不到「{query}」相關且可讀取的新聞報導。"

        article_data = _summarize_article_with_newspaper(url, item)
        
        if "error" in article_data and not article_data.get("summary", "").strip():
             return f"抱歉，處理新聞「{article_data.get('title','未知標題')}」時遇到問題。"

        # 格式化回覆字串
        reply_parts = [
            f"📰 {article_data.get('title', '無標題')}",
            (f"📅 發布: {article_data['publish_date']}" if article_data['publish_date'] else "📅 發布日期未知"),
            f"🔍 來源: {article_data.get('source', '未知')}",
            "──────────────",
            f"📄 新聞摘要:\n{article_data.get('summary', '無法產生摘要。')}",
            "──────────────",
            f"🔗 完整新聞: {article_data.get('url', '#')}"
        ]
        result_string = "\n\n".join(part for part in reply_parts if part)
        logger.info(f"成功處理新聞查詢「{query}」。標題：{article_data.get('title')}")
        return result_string
            
    except Exception as e:
        logger.error(f"get_news_summary 處理查詢「{query}」時發生錯誤：{e}", exc_info=True)
        return "抱歉，新聞查詢服務目前遇到一些問題，請稍後再試。"

if __name__ == "__main__":
    logger.info("測試 news_summary.py...")
    test_query = "台積電股價"
    summary = get_news_summary(test_query)
    print(f"\n--- 測試查詢「{test_query}」 ---")
    print(summary)
