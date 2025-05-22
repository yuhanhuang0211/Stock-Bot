import os
import logging
from urllib.parse import urlparse
from dotenv import load_dotenv
from googleapiclient.discovery import build
from newspaper import Article, Config
import requests

# LINE Bot SDK V3 Imports
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage as V3TextMessage # Renamed to avoid conflict if any other TextMessage is used
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent # For type hinting and access
)

load_dotenv()

# --- 環境變數與設定 ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_SECRET")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

assert LINE_CHANNEL_ACCESS_TOKEN, "缺少 LINE_TOKEN (Channel Access Token)"
assert LINE_CHANNEL_SECRET, "缺少 LINE_SECRET"
assert SEARCH_API_KEY, "缺少 SEARCH_API_KEY"
assert SEARCH_ENGINE_ID, "缺少 SEARCH_ENGINE_ID"

# --- LINE Bot API & Webhook 初始化 (V3) ---
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)        # 發送訊息
handler = WebhookHandler(LINE_CHANNEL_SECRET)   # 處理 webhook 事件

# --- 設定日誌 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# --- 核心邏輯 ---
def google_search_news(query):
    """搜尋新聞並返回第一個可訪問的URL"""
    try:
        service = build("customsearch", "v1", developerKey=SEARCH_API_KEY)
        res = service.cse().list(
            q=query,
            cx=SEARCH_ENGINE_ID,
            num=5,
        ).execute()

        if "items" not in res or not res["items"]:
            logger.info(f"Google 搜尋 '{query}' 未找到項目。")
            return None, None

        # 找到第一個可訪問的連結
        for item in res["items"]:
            url = item.get("link")
            if not url:
                continue
            try:
                response = requests.head(url, timeout=5, allow_redirects=True)
                if response.status_code == 200:
                    logger.info(f"找到可訪問新聞 URL: {url}")
                    return url, item
                else:
                    logger.warning(f"URL {url} 狀態碼 {response.status_code}, 跳過。")
            except requests.exceptions.RequestException as e:
                logger.warning(f"檢查 URL {url} 失敗: {e}, 跳過。")
                continue
        
        logger.warning(f"搜尋 '{query}' 的結果都無法訪問。")
        return None, None

    except Exception as e:
        logger.error(f"Google 搜尋新聞錯誤: {e}")
        return None, None

def summarize_article(url, item=None):
    """使用 newspaper4k 提取文章摘要"""
    try:
        # newspaper4k 配置
        config = Config()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        config.request_timeout = 15
        config.memoize_articles = False
        config.fetch_images = False
        config.language = 'zh'

        article = Article(url, config=config)
        article.download()
        article.parse()
        
        # newspaper4k 的 NLP 處理
        article.nlp()

        publish_date_str = None
        if article.publish_date:
            publish_date_str = article.publish_date.strftime('%Y-%m-%d')
        elif item:
            # 嘗試從 meta 標籤獲取日期
            meta = item.get("pagemap", {}).get("metatags", [{}])[0]
            pd_value = meta.get("article:published_time") or meta.get("publishdate") or meta.get("pubdate")
            if pd_value:
                publish_date_str = pd_value.split('T')[0]

        return {
            "title": article.title or (item.get("title", "") if item else ""),
            "summary": article.summary or (item.get("snippet", "") if item else ""),
            "publish_date": publish_date_str,
            "source": urlparse(url).netloc,
            "url": url
        }

    except Exception as e:
        logger.error(f"文章摘要失敗 (URL: {url}): {e}")
        return {
            "title": item.get("title", "無法取得標題") if item else "無標題",
            "summary": item.get("snippet", "無法取得摘要") if item else "無摘要",
            "publish_date": None,
            "source": urlparse(url).netloc if url else "未知來源",
            "url": url,
            "error": str(e)
        }

def Google_search_news(query):
    """主要對外接口函式 - 完整的新聞搜尋和摘要流程"""
    try:
        logger.info(f"開始搜尋新聞關鍵字: '{query}'")
        
        # 搜尋新聞
        url, item = google_search_news(query)
        
        if url and item:
            # 提取文章摘要
            article_data = summarize_article(url, item)
            
            if "error" in article_data:
                logger.error(f"摘要文章時發生錯誤: {article_data['error']}")
                return f"抱歉，處理「{article_data['title']}」時遇到問題，請稍後再試。"
            else:
                # 格式化回覆
                reply_parts = [
                    f"📰 {article_data['title']}",
                    (f"📅 發布: {article_data['publish_date']}" if article_data['publish_date'] else "📅 發布日期未知"),
                    f"🔍 來源: {article_data['source']}",
                    "─────────────────",
                    f"📄 新聞摘要:\n{article_data['summary']}",
                    "─────────────────",
                    f"🔗 完整新聞: {article_data['url']}"
                ]
                result = "\n\n".join(part for part in reply_parts if part)
                logger.info(f"成功處理新聞查詢: {query}")
                return result
        else:
            logger.info(f"找不到與 '{query}' 相關的新聞")
            return f"抱歉，找不到與「{query}」相關的新聞，請換個關鍵字再試看看！"
            
    except Exception as e:
        logger.error(f"新聞搜尋處理錯誤: {e}")
        return "抱歉，新聞查詢功能暫時無法使用。"

if __name__ == "__main__":
    # 測試功能
    test_query = "台積電股價"
    result = Google_search_news(test_query)
    print("測試結果：")
    print(result)
