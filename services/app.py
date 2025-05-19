import os
from dotenv import load_dotenv
from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.models import MessageEvent, TextMessage, TextSendMessage
from linebot.exceptions import InvalidSignatureError
import google.generativeai as genai
import logging

# 載入 .env
load_dotenv()

# LINE Token / Secret
line_token = os.getenv('LINE_TOKEN')
line_secret = os.getenv('LINE_SECRET')

# Gemini API 金鑰
gemini_api_key = os.getenv('GEMINI_API_KEY')

if not line_token:
    raise ValueError("環境變數未設定完全 - LINE token")

if not line_secret:
    raise ValueError("環境變數未設定完全 - LINE secret")

if not gemini_api_key:
    raise ValueError("環境變數未設定完全 - Gemini API")

# 初始化 LINE bot
line_bot_api = LineBotApi(line_token)
handler = WebhookHandler(line_secret)

# 初始化 Gemini
genai.configure(api_key=gemini_api_key)
model = genai.GenerativeModel("gemini-1.5-flash")

# 啟動 Flask App
app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

@app.route("/", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return 'OK'

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    user_message = event.message.text
    app.logger.info(f"收到訊息: {user_message}")

    # 使用 Gemini 回覆
    try:
        response = model.generate_content(user_message)
        reply_text = response.text.strip()
    except Exception as e:
        app.logger.error(f"Gemini 回應錯誤: {e}")
        reply_text = "抱歉，我現在無法處理您的請求。"

    # 傳送回覆給使用者
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
