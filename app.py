import os
import logging
from flask import Flask, request, abort
from dotenv import load_dotenv
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import MessageEvent, TextMessage, TextSendMessage
import google.generativeai as genai

# 載入 .env 檔案
load_dotenv()

# 讀取環境變數
LINE_TOKEN = os.getenv("LINE_TOKEN")
LINE_SECRET = os.getenv("LINE_SECRET")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# 驗證設定是否齊全
if not LINE_TOKEN or not LINE_SECRET or not GEMINI_API_KEY:
    raise ValueError("請確認 LINE_TOKEN、LINE_SECRET 和 GEMINI_API_KEY 都已設定")

# 初始化 Flask App 與 LINE Bot
app = Flask(__name__)
app.logger.setLevel(logging.DEBUG)

line_bot_api = LineBotApi(LINE_TOKEN)
handler = WebhookHandler(LINE_SECRET)

# 初始化 Gemini AI
genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel("gemini-pro")

# Webhook 入口點
@app.route("/", methods=["POST"])
def callback():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)

    return "OK"

# 處理收到的文字訊息
@handler.add(MessageEvent, message=TextMessage)
def handle_text_message(event):
    user_message = event.message.text
    app.logger.info(f"使用者傳來：{user_message}")

    try:
        # 傳送訊息到 Gemini 並取得回覆
        response = model.generate_content(user_message)
        reply_text = response.text.strip()
    except Exception as e:
        app.logger.error(f"Gemini API 錯誤：{e}")
        reply_text = "抱歉，AI 回覆時發生錯誤，請稍後再試！"

    # 回覆使用者
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text)
    )

# 主程式執行點
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
