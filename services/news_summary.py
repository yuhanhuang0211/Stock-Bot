import os
import logging
from urllib.parse import urlparse

from flask import Flask, request, abort
from dotenv import load_dotenv
from googleapiclient.discovery import build
from newspaper import Article, Config as NewspaperConfig # 引入 NewspaperConfig
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
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_TOKEN") # 通常稱為 Channel Access Token
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

# --- Flask App 初始化 ---
app = Flask(__name__)
if not app.debug:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]')

# --- 使用者狀態管理 ---
user_states = {}
user_contexts = {}

# --- 新聞搜尋與摘要核心邏輯---
def Google_search_news(query):
    try:
        service = build("customsearch", "v1", developerKey=SEARCH_API_KEY)
        res = service.cse().list(
            q=query,
            cx=SEARCH_ENGINE_ID,
            num=5, # 取得5筆結果
            # dateRestrict="w1", # 例如限制在一週內，d7也可以
            # sort="date", # 按日期排序
        ).execute()

        if "items" not in res or not res["items"]: # 確保 items 存在且不為空
            app.logger.info(f"Google 搜尋 '{query}' 未找到項目。")
            return None, None

        # 嘗試找到第一個可訪問的連結
        for item in res["items"]:
            url = item.get("link")
            if not url:
                continue
            try:
                # 使用 HEAD 請求快速檢查 URL 狀態，設定合理的 timeout
                response = requests.head(url, timeout=5, allow_redirects=True) # 允許重定向並檢查最終 URL
                if response.status_code == 200:
                    app.logger.info(f"找到可訪問新聞 URL: {url} for query '{query}'")
                    return url, item
                else:
                    app.logger.warning(f"URL {url} 狀態碼 {response.status_code}, 跳過。")
            except requests.exceptions.RequestException as e:
                app.logger.warning(f"檢查 URL {url} 失敗: {e}, 跳過。")
                continue
        
        app.logger.warning(f"Google 搜尋 '{query}' 的前 {len(res['items'])} 個結果都無法訪問或連結無效。")
        return None, None # 如果所有連結都檢查失敗

    except Exception as e:
        app.logger.error(f"Google 搜尋新聞時發生錯誤 (query: '{query}'): {e}")
        return None, None


def summarize_article(url, item=None):
    try:
        # Newspaper3k Config
        config = NewspaperConfig()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        config.request_timeout = 15
        config.memoize_articles = False
        config.fetch_images = False
        config.language = 'zh'

        article = Article(url, config=config)
        article.download()
        article.parse()
        
        article.nlp()

        publish_date_str = None
        if article.publish_date:
            publish_date_str = article.publish_date.strftime('%Y-%m-%d')
        elif item:
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
        app.logger.error(f"文章摘要失敗 (URL: {url}): {e}")
        return {
            "title": (item.get("title", "無法取得標題") if item else "無標題") if url else "無有效網址",
            "summary": (item.get("snippet", "無法取得摘要") if item else "無摘要") if url else "摘要失敗",
            "publish_date": None,
            "source": urlparse(url).netloc if url else "未知來源",
            "url": url or "無效網址",
            "error": str(e)
        }

# --- LINE Bot Webhook 事件處理 ---
@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    user_id = event.source.user_id
    if not isinstance(event.message, TextMessageContent):
        return
        
    msg = event.message.text.strip()
    app.logger.info(f"收到訊息：'{msg}' 來自 {user_id}")

    reply_text = "" # 初始化回覆文字

    try:
        if msg == "我想知道最新時事！":
            user_states[user_id] = "waiting_for_keyword"
            reply_text = "交給我吧！請輸入您想查詢的股市時事關鍵字句："
        
        elif user_states.get(user_id) == "waiting_for_keyword":
            user_states.pop(user_id, None) # 清除狀態
            user_contexts[user_id] = {"last_query": msg}
            app.logger.info(f"使用者 {user_id} 輸入新聞關鍵字: '{msg}'")

            url, item = Google_search_news(msg)

            if url and item:
                article_data = summarize_article(url, item)
                
                if "error" in article_data: # 摘要過程發生錯誤
                    app.logger.error(f"摘要文章 {url} 時發生錯誤: {article_data['error']}")
                    reply_text = f"抱歉，處理「{article_data['title']}」時遇到問題，請稍後再試。"
                else:
                    reply_parts = [
                        f"📰 {article_data['title']}",
                        (f"📅 發布: {article_data['publish_date']}" if article_data['publish_date'] else "📅 發布日期未知"),
                        f"🔍 來源: {article_data['source']}",
                        "─────────────────",
                        f"📄 新聞摘要:\n{article_data['summary']}",
                        "─────────────────",
                        f"🔗 完整新聞: {article_data['url']}"
                    ]
                    reply_text = "\n\n".join(part for part in reply_parts if part)
            else:
                reply_text = f"抱歉，找不到與「{msg}」相關的股市新聞，請換個關鍵字再試看看！"
        
        else:
            app.logger.info(f"使用者 {user_id} 輸入非新聞查詢指令: '{msg}', 暫不處理。")
            return # 不回覆非預期訊息

        # 發送回覆
        if reply_text:
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[V3TextMessage(text=reply_text)]
                )
            )
            app.logger.info(f"已回覆訊息給 {user_id}")
        else:
            app.logger.info(f"沒有產生回覆內容給 {user_id} for message '{msg}'")

    except Exception as e:
        app.logger.error(f"處理訊息時發生未預期錯誤 (user_id: {user_id}, msg: '{msg}'): {e}", exc_info=True)
        # 通用的錯誤訊息
        try:
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[V3TextMessage(text="處理請求時發生問題，請稍後再試。")]
                )
            )
        except Exception as api_e:
            app.logger.error(f"回覆通用錯誤訊息失敗: {api_e}")


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    app.logger.info(f"Webhook 請求內容: {body[:500]}...") # 只記錄前500字元

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("簽名驗證失敗，請檢查您的 Channel Secret。")
        abort(400)
    except Exception as e:
        app.logger.error(f"處理 webhook 時發生錯誤: {e}", exc_info=True)
        abort(500) # 內部伺服器錯誤

    return "OK"

@app.route("/health", methods=["GET"])
def health_check():
    """健康檢查端點，用於 Render 等平台"""
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080)) # Render 通常使用 8080 或 10000
    app.logger.info(f"啟動 LINE Bot 服務於埠 {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
