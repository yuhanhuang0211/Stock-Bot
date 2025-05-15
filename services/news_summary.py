import os
import datetime
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from googleapiclient.discovery import build
from newspaper import Article
import requests
from urllib.parse import urlparse
import logging

# 設置日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 載入 .env 環境變數
load_dotenv()

# 讀取環境變數
LINE_TOKEN = os.getenv('LINE_TOKEN')
LINE_SECRET = os.getenv('LINE_SECRET')
SEARCH_API_KEY = os.getenv('SEARCH_API_KEY')
SEARCH_ENGINE_ID = os.getenv('SEARCH_ENGINE_ID')

# 確保所有環境變數都有值
assert LINE_TOKEN, "缺少 LINE_TOKEN"
assert LINE_SECRET, "缺少 LINE_SECRET"
assert SEARCH_API_KEY, "缺少 SEARCH_API_KEY"
assert SEARCH_ENGINE_ID, "缺少 SEARCH_ENGINE_ID"

# 初始化 LINE Bot
line_bot_api = LineBotApi(LINE_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# 記錄使用者狀態與上下文
user_states = {}
user_contexts = {}

# 建立 Flask App
app = Flask(__name__)

# Google 搜尋新聞
def google_search_news(query):
    try:
        service = build("customsearch", "v1", developerKey=SEARCH_API_KEY)
        res = service.cse().list(
            q=query,
            cx=SEARCH_ENGINE_ID,
            num=5,  # 獲取更多結果以便篩選
            dateRestrict="d7",  # 限制為最近7天的新聞
            sort="date",  # 按日期排序
            searchType="news"  # 指定搜索新聞
        ).execute()
        
        # 檢查是否有搜索結果
        if "items" not in res or len(res["items"]) == 0:
            logger.info(f"搜尋 '{query}' 沒有找到任何結果")
            return None, None
        
        # 遍歷結果，找到合適的新聞
        for item in res["items"]:
            url = item.get("link", "")
            domain = urlparse(url).netloc
            
            # 檢查URL是否可訪問
            try:
                head_response = requests.head(url, timeout=3)
                if head_response.status_code == 200:
                    return url, item
            except Exception as e:
                logger.warning(f"檢查URL時發生錯誤: {url}, {str(e)}")
                continue
        
        # 如果沒有找到可訪問的URL，返回第一個結果
        if len(res["items"]) > 0:
            return res["items"][0]["link"], res["items"][0]
            
        return None, None
    except Exception as e:
        logger.error(f"Google搜尋時發生錯誤: {str(e)}")
        return None, None

# 文章摘要
def summarize_article(url, item=None):
    try:
        article = Article(url, language='zh')
        article.download()
        article.parse()
        article.nlp()
        
        # 提取發佈日期
        publish_date = None
        if article.publish_date:
            publish_date = article.publish_date.strftime("%Y-%m-%d")
        elif item and "pagemap" in item and "metatags" in item["pagemap"] and len(item["pagemap"]["metatags"]) > 0:
            meta = item["pagemap"]["metatags"][0]
            if "article:published_time" in meta:
                publish_date = meta["article:published_time"].split('T')[0]
                
        # 提取來源
        source = urlparse(url).netloc
        
        # 取得標題
        title = article.title
        
        # 如果無法從文章獲取標題，嘗試從搜索結果獲取
        if not title and item:
            title = item.get("title", "")
            
        # 取得摘要
        summary = article.summary
        
        return {
            "title": title,
            "summary": summary,
            "publish_date": publish_date,
            "source": source,
            "url": url
        }
    except Exception as e:
        logger.error(f"摘要文章時發生錯誤: {url}, {str(e)}")
        # 如果處理失敗但有搜索結果項目，提供基本信息
        if item:
            return {
                "title": item.get("title", "無法獲取標題"),
                "summary": item.get("snippet", "無法獲取摘要"),
                "publish_date": None,
                "source": urlparse(url).netloc,
                "url": url,
                "error": str(e)
            }
        raise e

# 處理 LINE 訊息事件
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_id = event.source.user_id
    msg = event.message.text.strip()

    try:
        logger.info(f"收到來自用戶 {user_id} 的訊息: {msg}")
        
        if msg == "我想知道最新時事！":
            user_states[user_id] = "waiting_for_keyword"
            reply = "交給我吧！請輸入欲查詢的關鍵字句"
        elif user_states.get(user_id) == "waiting_for_keyword":
            user_states[user_id] = "idle"  # 重置狀態
            
            # 記錄搜索關鍵字
            user_contexts[user_id] = {"last_query": msg}
            
            logger.info(f"搜尋關鍵字: {msg}")
            news_url, item = google_search_news(msg)
            
            if news_url:
                try:
                    article_data = summarize_article(news_url, item)
                    
                    # 格式化回覆訊息
                    reply_parts = []
                    
                    # 添加標題
                    if article_data.get("title"):
                        reply_parts.append(f"📰 {article_data['title']}")
                    
                    # 添加發布日期
                    if article_data.get("publish_date"):
                        reply_parts.append(f"📅 發布日期: {article_data['publish_date']}")
                    
                    # 添加來源
                    if article_data.get("source"):
                        reply_parts.append(f"🔍 來源: {article_data['source']}")
                    
                    # 添加分隔線
                    reply_parts.append("─────────────────")
                    
                    # 添加摘要
                    if article_data.get("summary"):
                        reply_parts.append(f"📄 新聞摘要:\n{article_data['summary']}")
                    
                    # 添加分隔線
                    reply_parts.append("─────────────────")
                    
                    # 添加URL (確保在最後)
                    reply_parts.append(f"🔗 完整新聞: {news_url}")
                    
                    reply = "\n\n".join(reply_parts)
                    
                except Exception as e:
                    logger.error(f"處理文章時發生錯誤: {str(e)}")
                    reply = f"找到新聞了，但內容無法完整解析。\n\n🔗 新聞連結: {news_url}\n\n💡 您可以嘗試換個關鍵字，再次輸入「我想知道最新時事！」"
            else:
                reply = "找不到相關新聞，請換個關鍵字再試看看！"
        else:
            # 如果不是預期的指令或狀態，保持安靜不回應
            # 不回覆任何訊息，但仍記錄操作
            logger.info(f"用戶 {user_id} 發送了非預期訊息，不進行回覆")
            return
    
    except Exception as e:
        logger.error(f"處理訊息時發生錯誤: {str(e)}")
        reply = "處理您的請求時發生錯誤，請稍後再試。"

    # 發送回覆
    try:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply)
        )
        logger.info(f"成功回覆用戶 {user_id}")
    except Exception as e:
        logger.error(f"發送回覆時發生錯誤: {str(e)}")

# Webhook 路由
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)

    logger.info("收到 webhook 請求")
    
    try:
        handler.handle(body, signature)
    except Exception as e:
        logger.error(f"處理 webhook 時發生錯誤: {str(e)}")
        abort(400)

    return 'OK'

# 健康檢查路由
@app.route("/health", methods=['GET'])
def health_check():
    return "OK", 200

# 本地啟動用
if __name__ == "__main__":
    logger.info("啟動 LINE Bot 服務")
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
