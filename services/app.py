import os
from dotenv import load_dotenv
from flask import Flask, request, abort
import logging

# 匯入 LINE Bot SDK V3
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage as V3TextMessage,
    ImageSendMessage
)
from linebot.v3.webhooks import (
    MessageEvent,
    TextMessageContent
)

import google.generativeai as genai

# 匯入三大功能模組
from stock_price import get_stock_price
from stock_chart import generate_stock_chart_url
from news_summary import get_news_summary

# 載入 .env 變數
load_dotenv()

# --- 環境變數設定與檢查 ---
LINE_CHANNEL_ACCESS_TOKEN = os.getenv('LINE_TOKEN')
LINE_CHANNEL_SECRET = os.getenv('LINE_SECRET')
GEMINI_API_KEY = os.getenv('GEMINI_API_KEY')

missing_vars = []
if not LINE_CHANNEL_ACCESS_TOKEN: missing_vars.append("LINE_TOKEN")
if not LINE_CHANNEL_SECRET: missing_vars.append("LINE_SECRET")
if not GEMINI_API_KEY: missing_vars.append("GEMINI_API_KEY")

if missing_vars:
    raise ValueError(f"環境變數未設定完全: {', '.join(missing_vars)}")

# --- 初始化 LINE Bot SDK V3 ---
line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
line_api_client = ApiClient(line_config)
messaging_api = MessagingApi(line_api_client)
webhook_handler = WebhookHandler(LINE_CHANNEL_SECRET)

# --- 初始化 Gemini ---
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# --- Flask 應用程式設定 ---
app = Flask(__name__)
# Flask 日誌紀錄
if not app.debug:
    app.logger.setLevel(logging.INFO) # 一般資訊等級
else:
    app.logger.setLevel(logging.DEBUG)

# --- 使用者狀態管理 ---
user_next_action = {}   # 儲存使用者動作或狀態

STATE_WAITING_STOCK_ID_FOR_PRICE = "WAITING_STOCK_ID_FOR_PRICE"
STATE_WAITING_STOCK_ID_FOR_CHART = "WAITING_STOCK_ID_FOR_CHART"
STATE_WAITING_KEYWORD_FOR_NEWS = "WAITING_KEYWORD_FOR_NEWS"

# --- Webhook 路由 ---
@app.route("/callback", methods=['POST']) # 確保 LINE Webhook URL 指向此路由
def callback():
    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body[:500]}...") # 僅記錄部分請求內文

    try:
        webhook_handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("簽名無效。請確認你的 channel secret 是否正確。")
        abort(400)
    except Exception as e:
        app.logger.error(f"處理 webhook 發生錯誤: {e}", exc_info=True)
        abort(500)
    return 'OK'

# --- 訊息處理器 ---
@webhook_handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent):
    user_id = event.source.user_id
    user_message = event.message.text.strip()
    app.logger.info(f"收到來自 {user_id} 的訊息: {user_message}")

    reply_messages = [] # 可一次回覆最多 5 則訊息
    current_action = user_next_action.pop(user_id, None) # 取得並清除當前動作

    try:
        if current_action == STATE_WAITING_STOCK_ID_FOR_PRICE:
            stock_id_input = user_message
            price_info = get_stock_price(stock_id_input)
            reply_messages.append(V3TextMessage(text=price_info))
        
        elif current_action == STATE_WAITING_STOCK_ID_FOR_CHART:
            stock_identifier_input = user_message # 可以是代號或公司名稱
            chart_url = generate_stock_chart_url(stock_identifier_input)
            if chart_url:
                reply_messages.append(ImageSendMessage(
                    original_content_url=chart_url,
                    preview_image_url=chart_url
                ))
            else:
                reply_messages.append(V3TextMessage(text=f"抱歉，無法產生「{stock_identifier_input}」的走勢圖。"))

        elif current_action == STATE_WAITING_KEYWORD_FOR_NEWS:
            news_keyword = user_message
            news_summary_text = get_news_summary(news_keyword)
            reply_messages.append(V3TextMessage(text=news_summary_text))
            
        # --- 圖文選單關鍵訊息 ---
        elif user_message == "我想看股價！":
            user_next_action[user_id] = STATE_WAITING_STOCK_ID_FOR_PRICE
            reply_messages.append(V3TextMessage(text="好的！我們目前提供多數台股的股價查詢，請輸入股票代號或公司名稱"))
            
        elif user_message == "我想看走勢圖！":
            user_next_action[user_id] = STATE_WAITING_STOCK_ID_FOR_CHART
            reply_messages.append(V3TextMessage(text="沒問題～目前可以查詢多數台股的走勢圖，請輸入股票代號或公司名稱"))
            
        elif user_message == "我想知道最新時事！":
            user_next_action[user_id] = STATE_WAITING_KEYWORD_FOR_NEWS
            reply_messages.append(V3TextMessage(text="交給我吧！請輸入您想查詢的股市時事關鍵字句"))
            
        else:
            # 預設使用 Gemini 處理一般聊天
            app.logger.info(f"轉交 Gemini 處理 {user_id} 的訊息: {user_message}")
            try:
                # 簡單的文字輸入輸出（適用 gemini-1.5-flash 或 gemini-pro）
                response = gemini_model.generate_content(user_message)
                gemini_reply = response.text.strip()
                if not gemini_reply and response.prompt_feedback and str(response.prompt_feedback.block_reason) != "BLOCK_REASON_UNSPECIFIED":
                    # 處理因安全設定而被擋下的內容
                    app.logger.warning(f"Gemini 封鎖內容：'{user_message}'。原因：{response.prompt_feedback.block_reason}")
                    gemini_reply = "抱歉，我無法回覆這個內容。"
                elif not gemini_reply:
                    gemini_reply = "嗯...我好像不知道該怎麼回應這個。"

                reply_messages.append(V3TextMessage(text=gemini_reply))
            except Exception as e:
                app.logger.error(f"Gemini API 錯誤，訊息為 '{user_message}': {e}", exc_info=True)
                reply_messages.append(V3TextMessage(text="抱歉，AI聊天功能暫時無法回應，請稍後再試。"))

        # 如果有產生回覆訊息，就送出
        if reply_messages:
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=reply_messages
                )
            )
            app.logger.info(f"已回覆 {user_id} 共 {len(reply_messages)} 則訊息。")
        else:
            # 理論上應該不會進到這個狀況，除非邏輯錯漏
            app.logger.info(f"未產生回覆訊息：使用者 {user_id}，訊息內容：'{user_message}'")


    except Exception as api_err:
            app.logger.error(f"Failed to send error reply to {user_id}: {api_err}")

# --- Render 健康檢查 ---
@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200

if __name__ == "__main__":
    # Get port from environment variable or default to 8080 for Render compatibility
    port = int(os.environ.get("PORT", 8080))
    # When running locally using `python app.py`, Flask's dev server is used.
    # For Render, it will use your Procfile (e.g., `web: gunicorn app:app`).
    # debug=True should only be for local development. Render sets FLASK_DEBUG or similar.
    app.run(host='0.0.0.0', port=port, debug=os.environ.get("FLASK_DEBUG", "False").lower() == "true")
