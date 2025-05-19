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

# Load environment variables
load_dotenv()
LINE_CHANNEL_ACCESS_TOKEN = os.getenv("LINE_TOKEN")
LINE_CHANNEL_SECRET = os.getenv("LINE_SECRET")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")
NEWS_UA = os.getenv("NEWS_USER_AGENT", 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)')

# Validate env
for var, name in [(LINE_CHANNEL_ACCESS_TOKEN, "LINE_TOKEN"),
                  (LINE_CHANNEL_SECRET, "LINE_SECRET"),
                  (SEARCH_API_KEY, "SEARCH_API_KEY"),
                  (SEARCH_ENGINE_ID, "SEARCH_ENGINE_ID")]:
    assert var, f"缺少 {name}"

# Logger setup
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# LINE API init
configuration = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
api_client = ApiClient(configuration)
messaging_api = MessagingApi(api_client)
handler = WebhookHandler(LINE_CHANNEL_SECRET)

# Flask app
app = Flask(__name__)

# User state
user_states = {}

# --- News search & summary ---

def google_search_news(query):
    try:
        service = build("customsearch", "v1", developerKey=SEARCH_API_KEY)
        res = service.cse().list(
            q=query,
            cx=SEARCH_ENGINE_ID,
            num=5,
            dateRestrict="d7",
            sort="date"
        ).execute()
        items = res.get("items", [])
        if not items:
            logger.info(f"Google 搜尋 '{query}' 未找到結果。")
            return None, None
        for item in items:
            url = item.get("link")
            if not url:
                continue
            try:
                resp = requests.head(url, timeout=5, allow_redirects=True)
                if resp.status_code == 200:
                    logger.info(f"找到可訪問 URL: {url}")
                    return url, item
                else:
                    logger.warning(f"URL {url} 狀態 {resp.status_code}，跳過。")
            except Exception as e:
                logger.warning(f"檢查 URL {url} 失敗: {e}")
        logger.warning(f"所有搜尋結果皆不可用。")
        return None, None
    except Exception as e:
        logger.error(f"Google 搜尋錯誤: {e}")
        return None, None


def summarize_article(url, item=None):
    try:
        config = NewspaperConfig()
        config.browser_user_agent = NEWS_UA
        config.request_timeout = 15
        config.memoize_articles = False
        config.fetch_images = False
        config.language = 'zh'

        article = Article(url, config=config)
        for _ in range(2):
            try:
                article.download()
                article.parse()
                break
            except Exception:
                time.sleep(1)
        article.nlp()

        summary = article.summary or (item.get("snippet", "") if item else "")
        summary = ' '.join(summary.split())

        publish_date = None
        if article.publish_date:
            publish_date = article.publish_date.strftime('%Y-%m-%d')
        elif item:
            meta = item.get("pagemap", {}).get("metatags", [{}])[0]
            pd = meta.get("article:published_time") or meta.get("pubdate")
            if pd:
                publish_date = pd.split('T')[0]

        return {
            "title": article.title or (item.get("title", "") if item else ""),
            "summary": summary,
            "publish_date": publish_date,
            "source": urlparse(url).netloc,
            "url": url
        }
    except Exception as e:
        logger.error(f"文章摘要失敗 ({url}): {e}")
        return {
            "title": item.get("title", "無標題") if item else "無標題",
            "summary": "摘要失敗，請稍後再試。",
            "publish_date": None,
            "source": urlparse(url).netloc if url else "未知",
            "url": url or "無效網址",
        }


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event: MessageEvent):
    user_id = event.source.user_id
    msg = event.message.text.strip()
    logger.info(f"收到訊息: '{msg}' 來自 {user_id}")

    reply = None
    try:
        if msg == "我想知道最新時事！":
            user_states[user_id] = "waiting_for_keyword"
            reply = V3TextMessage(text="交給我吧！請輸入您想查詢的時事關鍵字：")

        elif user_states.get(user_id) == "waiting_for_keyword":
            user_states.pop(user_id, None)
            url, item = google_search_news(msg)
            if url:
                data = summarize_article(url, item)
                bubble = BubbleContainer(
                    body=BoxComponent(layout='vertical', contents=[
                        TextComponent(text=data['title'], weight='bold', size='md'),
                        TextComponent(text=data['summary'], wrap=True, size='sm'),
                        TextComponent(text=f"{data['source']} | {data['publish_date'] or '日期未知'}", size='xs', color='#AAAAAA'),
                        TextComponent(text=data['url'], size='xs', wrap=True),
                    ])
                )
                reply = FlexMessage(alt_text="新聞摘要", contents=bubble)
            else:
                reply = V3TextMessage(text=f"抱歉，找不到「{msg}」相關新聞，請換關鍵字再試！")

        else:
            return

        if reply:
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[reply]
                )
            )
            logger.info(f"回覆 {user_id}")
    except InvalidSignatureError:
        logger.error("簽名驗證失敗。")
        abort(400)
    except Exception as e:
        logger.error(f"處理訊息錯誤: {e}")
        messaging_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[V3TextMessage(text="處理請求時發生錯誤，請稍後再試。")]
            )
        )


@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)
    logger.info(f"Webhook Body: {body[:200]}")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("簽名驗證失敗。")
        abort(400)
    except Exception as e:
        logger.error(f"Webhook 處理錯誤: {e}")
        abort(500)
    return "OK"

@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"啟動於埠 {port}")
    app.run(host="0.0.0.0", port=port, debug=False)
