import os
import logging
from urllib.parse import urlparse

from flask import Flask, request, abort
from dotenv import load_dotenv
from googleapiclient.discovery import build
from newspaper import Article
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import requests

# ---------- 基本設定 ----------
load_dotenv()

LINE_TOKEN = os.getenv("LINE_TOKEN")
LINE_SECRET = os.getenv("LINE_SECRET")
SEARCH_API_KEY = os.getenv("SEARCH_API_KEY")
SEARCH_ENGINE_ID = os.getenv("SEARCH_ENGINE_ID")

assert LINE_TOKEN, "缺少 LINE_TOKEN"
assert LINE_SECRET, "缺少 LINE_SECRET"
assert SEARCH_API_KEY, "缺少 SEARCH_API_KEY"
assert SEARCH_ENGINE_ID, "缺少 SEARCH_ENGINE_ID"

line_bot_api = LineBotApi(LINE_TOKEN)
handler = WebhookHandler(LINE_SECRET)

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

user_states = {}
user_contexts = {}

# ---------- 功能函式 ----------

def google_search_news(query):
    try:
        service = build("customsearch", "v1", developerKey=SEARCH_API_KEY)
        res = service.cse().list(
            q=query,
            cx=SEARCH_ENGINE_ID,
            num=5,
            dateRestrict="d7",
            sort="date",
            searchType="news"
        ).execute()

        if "items" not in res:
            return None, None

        for item in res["items"]:
            url = item.get("link", "")
            try:
                r = requests.head(url, timeout=3)
                if r.status_code == 200:
                    return url, item
            except Exception:
                continue

        return res["items"][0]["link"], res["items"][0] if res["items"] else (None, None)

    except Exception as e:
        logger.error(f"搜尋新聞錯誤：{e}")
        return None, None


def summarize_article(url, item=None):
    try:
        article = Article(url, language='zh')
        article.download()
        article.parse()
        article.nlp()

        publish_date = article.publish_date.strftime('%Y-%m-%d') if article.publish_date else None
        if not publish_date and item:
            meta = item.get("pagemap", {}).get("metatags", [{}])[0]
            publish_date = meta.get("article:published_time", "").split('T')[0]

        return {
            "title": article.title or item.get("title", ""),
            "summary": article.summary or item.get("snippet", ""),
            "publish_date": publish_date,
            "source": urlparse(url).netloc,
            "url": url
        }

    except Exception as e:
        logger.error(f"文章摘要失敗：{e}")
        return {
            "title": item.get("title", "無法取得標題") if item else "無標題",
            "summary": item.get("snippet", "無法取得摘要") if item else "無摘要",
            "publish_date": None,
            "source": urlparse(url).netloc,
            "url": url,
            "error": str(e)
        }

# ---------- LINE Bot 處理 ----------

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()
    logger.info(f"收到訊息：{msg} 來自 {user_id}")

    reply = ""

    try:
        if msg == "我想知道最新時事！":
            user_states[user_id] = "waiting_for_keyword"
            reply = "交給我吧！請輸入欲查詢的關鍵字句"

        elif user_states.get(user_id) == "waiting_for_keyword":
            user_states[user_id] = "idle"
            user_contexts[user_id] = {"last_query": msg}

            url, item = google_search_news(msg)

            if url:
                article_data = summarize_article(url, item)

                reply_parts = [
                    f"📰 {article_data['title']}",
                    f"📅 發布日期: {article_data['publish_date']}" if article_data['publish_date'] else "",
                    f"🔍 來源: {article_data['source']}",
                    "─────────────────",
                    f"📄 新聞摘要:\n{article_data['summary']}",
                    "─────────────────",
                    f"🔗 完整新聞: {article_data['url']}"
                ]

                reply = "\n\n".join(part for part in reply_parts if part)

            else:
                reply = "找不到相關新聞，請換個關鍵字再試看看！"

        else:
            logger.info(f"非預期訊息，略過回覆：{msg}")
            return

    except Exception as e:
        logger.error(f"處理訊息錯誤：{e}")
        reply = "處理您的請求時發生錯誤，請稍後再試。"

    try:
        line_bot_api.reply_message(event.reply_token, TextSendMessage(text=reply))
    except Exception as e:
        logger.error(f"回覆失敗：{e}")

# ---------- 路由與啟動 ----------

@app.route("/callback", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature")
    body = request.get_data(as_text=True)

    try:
        handler.handle(body, signature)
    except Exception as e:
        logger.error(f"處理 webhook 失敗：{e}")
        abort(400)

    return "OK"


@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200


if __name__ == "__main__":
    logger.info("啟動 LINE Bot 服務")
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
