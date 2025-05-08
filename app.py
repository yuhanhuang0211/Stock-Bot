import os
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot.v3.messaging import MessagingApi
from linebot.v3.webhook import WebhookHandler, Event
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging.models import TextMessage
from linebot import LineBotApi, WebhookHandler
from linebot.models import (
    MessageEvent, 
    TextMessage, 
    TextSendMessage,
    ImageSendMessage)
from linebot.exceptions import InvalidSignatureError
from gpt import process_user_input, extract_stock_id, txt_to_img_url, get_stock_info
import logging
import re

# 加載 .env 文件中的變數
load_dotenv()

# 從環境變數中讀取 LINE 的 Channel Access Token 和 Channel Secret
line_token = os.getenv('LINE_TOKEN')
line_secret = os.getenv('LINE_SECRET')

# 檢查是否設置了環境變數
if not line_token or not line_secret:
    print(f"LINE_TOKEN: {line_token}")  # 調試輸出
    print(f"LINE_SECRET: {line_secret}")  # 調試輸出
    raise ValueError("LINE_TOKEN 或 LINE_SECRET 未設置")

# 初始化 LineBotApi 和 WebhookHandler
line_bot_api = LineBotApi(line_token)
handler = WebhookHandler(line_secret)

# 創建 Flask 應用
app = Flask(__name__)

app.logger.setLevel(logging.DEBUG)

# 設置一個路由來處理 LINE Webhook 的回調請求
@app.route("/", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 標頭
    signature = request.headers['X-Line-Signature']

    # 取得請求的原始內容
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    # 驗證簽名並處理請求
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return 'OK'

# 設置一個事件處理器來處理 TextMessage 事件
@handler.add(MessageEvent, message=TextMessage)
def handle_message(event: Event):
    if event.message.type == "text":
        user_message = event.message.text  # 使用者的訊息
        app.logger.info(f"收到的訊息: {user_message}")

        # 檢查是否包含特定關鍵字
        if "趨勢圖" in user_message:
            # 使用 GPT 生成回應
            stock_ids = extract_stock_id(user_message)

            if stock_ids:
                # Generate trend chart for the first stock ID
                stock_id = stock_ids[0]  # Use the first extracted stock ID
                try:
                    image_url = txt_to_img_url(stock_id)
                    if not image_url:
                        error_message = f"抱歉，沒有取得股票趨勢圖，{image_url}。"
                        line_bot_api.reply_message(
                            event.reply_token,
                            TextMessage(text=error_message)
                        )
                        return
                    line_bot_api.reply_message(
                        event.reply_token,
                        ImageSendMessage(
                            original_content_url=image_url,
                            preview_image_url=image_url
                        )
                    )
                except Exception as e:
                    error_message = f"抱歉，無法生成股票趨勢圖，錯誤原因：{e}"
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextMessage(text=error_message)
                    )
                return
            else:
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text="未能識別股票代號，請輸入正確的股票名稱或代號。")
                )
                return

        # 使用 GPT 生成回應
        reply_text = process_user_input(user_message)

        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=reply_text)
        )
# 應用程序入口點
if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)

