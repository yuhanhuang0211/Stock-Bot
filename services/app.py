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
from linebot.v3.webhooks import MessageEvent, TextMessageContent

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
    logging.warning(f"缺少關鍵環境變數: {', '.join(missing_vars)}。部分功能可能無法使用。")

# --- 初始化 LINE Bot SDK V3 ---
if LINE_CHANNEL_ACCESS_TOKEN and LINE_CHANNEL_SECRET:
    line_config = Configuration(access_token=LINE_CHANNEL_ACCESS_TOKEN)
    line_api_client = ApiClient(line_config)
    messaging_api = MessagingApi(line_api_client)
    webhook_handler = WebhookHandler(LINE_CHANNEL_SECRET)
    LINE_SDK_INITIALIZED = True
    logging.info("LINE Bot SDK V3 成功初始化。")
else:
    LINE_SDK_INITIALIZED = False
    logging.error("因缺少 LINE_TOKEN 或 LINE_SECRET，LINE Bot SDK V3 初始化失敗。")

# --- 初始化 Gemini ---
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    gemini_model = genai.GenerativeModel("gemini-1.5-flash")
    GEMINI_INITIALIZED = True
    logging.info("Gemini API 成功初始化。")
else:
    GEMINI_INITIALIZED = False
    gemini_model = None
    logging.warning("未設定 GEMINI_API_KEY。Gemini 聊天功能將無法使用。")

# --- Flask 應用程式設定 ---
app = Flask(__name__)
if not app.debug:
    app.logger.setLevel(logging.INFO)
else:
    app.logger.setLevel(logging.DEBUG)
if not app.logger.handlers:
    stream_handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    stream_handler.setFormatter(formatter)
    app.logger.addHandler(stream_handler)

# --- 多輪對話的使用者狀態管理 ---
user_next_action = {} # Key: user_id, Value: 預期的動作狀態

STATE_WAITING_STOCK_ID_FOR_PRICE = "WAITING_STOCK_ID_FOR_PRICE"
STATE_WAITING_STOCK_ID_FOR_CHART = "WAITING_STOCK_ID_FOR_CHART"
STATE_WAITING_KEYWORD_FOR_NEWS = "WAITING_KEYWORD_FOR_NEWS"

# --- Webhook 路由 ---
@app.route("/callback", methods=['POST'])
def callback():
    if not LINE_SDK_INITIALIZED:
        app.logger.error("LINE SDK 尚未初始化，無法處理 webhook。")
        abort(500) # 服務不可用

    signature = request.headers.get('X-Line-Signature')
    body = request.get_data(as_text=True)
    app.logger.debug(f"Webhook 請求內容: {body[:200]}...") # 只紀錄部分內容

    try:
        webhook_handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("簽章無效。請檢查您的 channel secret。")
        abort(400)
    except Exception as e:
        app.logger.error(f"處理 webhook 發生錯誤: {e}", exc_info=True)
        abort(500)
    return 'OK'

# --- 訊息處理器 ---
@webhook_handler.add(MessageEvent, message=TextMessageContent)
def handle_text_message(event: MessageEvent):
    if not LINE_SDK_INITIALIZED: # 若 /callback 已中止，理論上不會發生，但仍可檢查
        app.logger.error("Messaging API 無法使用。")
        return

    user_id = event.source.user_id
    if not isinstance(event.message, TextMessageContent): # 確保是文字訊息
        return
    user_message = event.message.text.strip()
    app.logger.info(f"收到來自 {user_id} 的訊息: '{user_message}'")

    reply_objects = [] # 儲存 V3TextMessage 或 ImageSendMessage 物件的列表
    current_action = user_next_action.pop(user_id, None) # 取得並清除目前狀態

    try:
        # 1. 優先處理多輪對話的狀態
        if current_action == STATE_WAITING_STOCK_ID_FOR_PRICE:
            stock_id_input = user_message
            price_info = get_stock_price(stock_id_input) # 例如輸入 "2330"
            reply_objects.append(V3TextMessage(text=price_info))
        
        elif current_action == STATE_WAITING_STOCK_ID_FOR_CHART:
            stock_identifier_input = user_message # 可為 "2330" 或 "台積電"
            chart_url = generate_stock_chart_url(stock_identifier_input)
            if chart_url:
                reply_objects.append(ImageSendMessage(
                    original_content_url=chart_url,
                    preview_image_url=chart_url # 對 LINE 而言，預覽與原始圖可相同
                ))
            else:
                reply_objects.append(V3TextMessage(text=f"抱歉，無法產生「{stock_identifier_input}」的走勢圖。"))

        elif current_action == STATE_WAITING_KEYWORD_FOR_NEWS:
            news_keyword = user_message
            news_summary_text = get_news_summary(news_keyword) # 輸入搜尋關鍵字
            reply_objects.append(V3TextMessage(text=news_summary_text))
            
        # 2. 處理從富功能選單或文字輸入觸發的初始命令
        elif user_message == "我想看股價": # 富選單動作傳送的文字
            user_next_action[user_id] = STATE_WAITING_STOCK_ID_FOR_PRICE
            reply_objects.append(V3TextMessage(text="好的！請輸入您想查詢的股票代號："))
            
        elif user_message == "我想看走勢圖":
            user_next_action[user_id] = STATE_WAITING_STOCK_ID_FOR_CHART
            reply_objects.append(V3TextMessage(text="沒問題～請輸入股票代號或公司全名："))
            
        elif user_message == "我想知道最近的股市時事":
            user_next_action[user_id] = STATE_WAITING_KEYWORD_FOR_NEWS
            reply_objects.append(V3TextMessage(text="交給我！請輸入您想查詢的股市時事關鍵字："))
            
        # 3. 預設轉交 Gemini 處理一般聊天
        else:
            if GEMINI_INITIALIZED and gemini_model:
                app.logger.info(f"轉交 Gemini 處理來自 {user_id} 的訊息: '{user_message}'")
                try:
                    response = gemini_model.generate_content(user_message)
                    gemini_reply = response.text.strip()
                    
                    # 檢查是否為被封鎖的內容
                    if not gemini_reply and hasattr(response, 'prompt_feedback') and response.prompt_feedback:
                        if str(response.prompt_feedback.block_reason) != "BLOCK_REASON_UNSPECIFIED":
                            app.logger.warning(f"Gemini 封鎖回覆內容: '{user_message}'。原因: {response.prompt_feedback.block_reason}")
                            gemini_reply = "抱歉，我無法回覆此內容，可能涉及敏感資訊。"
                    if not gemini_reply: # 若仍無回覆（例如回應為空）
                         gemini_reply = "嗯...我目前無法處理這個請求。"
                    reply_objects.append(V3TextMessage(text=gemini_reply))
                except Exception as e:
                    app.logger.error(f"Gemini API 發生錯誤（訊息: '{user_message}'）: {e}", exc_info=True)
                    reply_objects.append(V3TextMessage(text="抱歉，AI 聊天功能暫時出現問題，請稍後再試。"))
            else:
                app.logger.warning(f"GEMINI_API_KEY 未設定或 Gemini 尚未初始化，無法處理 '{user_message}'。")
                reply_objects.append(V3TextMessage(text="你好，想聊些什麼呢？（AI 聊天功能整備中）"))

        # 若建立了任何回覆訊息物件，則傳送回覆
        if reply_objects:
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=reply_objects # 傳送訊息物件列表
                )
            )
            app.logger.info(f"已回覆使用者 {user_id}，共 {len(reply_objects)} 筆訊息。")
        # 若無回覆物件（例如早先已過濾非文字訊息），則不回覆

    except Exception as e:
        app.logger.error(f"處理使用者 {user_id} 訊息 '{user_message}' 時發生未處理錯誤: {e}", exc_info=True)
        try: # 嘗試傳送通用錯誤訊息給使用者
            messaging_api.reply_message(
                ReplyMessageRequest(
                    reply_token=event.reply_token,
                    messages=[V3TextMessage(text="哎呀，系統發生了一點小狀況，請稍後再試！")]
                )
            )
        except Exception as api_err:
            app.logger.error(f"無法傳送通用錯誤訊息給 {user_id}: {api_err}")

# 健康檢查路由（適用於 Render 等平台）
@app.route("/health", methods=["GET"])
def health_check():
    return "OK", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080)) # Render 常用 8080 或 10000
    # debug=True 僅適用於本機開發，正式部署時 Render/Gunicorn 會處理設定
    app.run(host='0.0.0.0', port=port, debug=os.environ.get("FLASK_DEBUG", "false").lower() == "true")
