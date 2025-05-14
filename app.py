from flask import Flask, request, jsonify
from stock_chart import extract_stock_id, process_user_input, txt_to_img_url
from stock_price import get_stock_price
from news_summary import process_news_query  # 假設你有這個模組
from dotenv import load_dotenv
import os
import google.generativeai as genai

load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

app = Flask(__name__)

# Gemini 基本聊天功能
def chat_with_gemini(prompt: str) -> str:
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Gemini API 錯誤：{e}"

@app.route('/')
def index():
    return "🎉 歡迎使用股市分析 API（整合 Gemini + twstock + Cloudinary）"

@app.route('/chat', methods=['POST'])
def chat():
    try:
        user_input = request.json.get('message')
        if not user_input:
            return jsonify({'error': '請提供輸入訊息'}), 400

        stock_ids = extract_stock_id(user_input)

        # 如果提到股票代碼或公司名稱
        if stock_ids:
            reply_text = process_user_input(user_input)
            chart_urls = []

            for sid in stock_ids:
                url = txt_to_img_url(sid)
                if url:
                    chart_urls.append(url)

            return jsonify({
                'reply': reply_text,
                'charts': chart_urls
            })

        # 純粹問 Gemini 的問題
        reply = chat_with_gemini(user_input)
        return jsonify({'reply': reply})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/price', methods=['POST'])
def price():
    try:
        user_input = request.json.get('message')
        if not user_input:
            return jsonify({'error': '請提供輸入訊息'}), 400

        stock_ids = extract_stock_id(user_input)

        if stock_ids:
            results = {}
            for sid in stock_ids:
                results[sid] = get_stock_price(sid)
            return jsonify({'price_info': results})
        else:
            return jsonify({'error': '找不到股票代碼'}), 400

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/news_summary', methods=['POST'])
def news_summary():
    try:
        user_input = request.json.get('message')
        if not user_input:
            return jsonify({'error': '請提供輸入訊息'}), 400

        # 處理新聞摘要
        summary = process_news_query(user_input)
        return jsonify({'summary': summary})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
