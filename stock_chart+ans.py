import os
import re
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import twstock
import cloudinary
import cloudinary.uploader
from datetime import datetime
from dotenv import load_dotenv
import google.generativeai as genai

# Server compatibility
matplotlib.use('Agg')

# Load .env variables
load_dotenv()
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# Cloudinary config
cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

# 常見台股公司對應代碼
default_data = {
    "中油": "6505",
    "台積電": "2330",
    "鴻海": "2317",
    "富邦金": "2881",
    # ...（可擴充完整 default_data）
}

# Gemini 聊天回應
def chat_with_gemini(prompt: str) -> str:
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        return f"Gemini API 錯誤: {e}"

# 提取股票代碼
def extract_stock_id(user_input: str) -> list:
    match = re.findall(r'\d{4,6}', user_input)
    if match:
        return match

    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = f"""請從這段文字中提取股票代號或是依據內容回答提到的公司的股票代號：{user_input}，常見代碼：{default_data}；如果沒有找到與公司相關的股票資訊的話，回傳“None”"""
        response = model.generate_content(prompt)
        ai_response = response.text
        match = re.findall(r'\d{4,6}', ai_response)
        return match if match else None
    except Exception as e:
        print(f"Error contacting Gemini API: {e}")
        return None

# 取得股票資訊
def get_stock_info(stock_id: str) -> str:
    try:
        stock = twstock.Stock(stock_id)
        recent_dates = stock.date[-5:]
        recent_prices = stock.price[-5:]
        recent_highs = stock.high[-5:]

        if None in recent_prices or None in recent_highs:
            return f"抱歉，無法取得 {stock_id} 的完整數據，請稍後再試。"

        result = f"股票代號：{stock_id}\n近五日數據：\n"
        for i in range(len(recent_dates)):
            date_str = recent_dates[i].strftime("%Y-%m-%d")
            result += f"- 日期：{date_str}，收盤價：{recent_prices[i]}，高點：{recent_highs[i]}\n"
        return result
    except Exception as e:
        return f"抱歉，無法取得股票代號 {stock_id} 的資訊。\n錯誤原因：{e}"

# 使用者輸入主流程
def process_user_input(user_input: str) -> str:
    stock_ids = extract_stock_id(user_input)
    if stock_ids:
        stock_info = ''
        for sid in stock_ids:
            stock_info += get_stock_info(sid) + '\n'
        return chat_with_gemini(f"使用者輸入：{user_input}。以下是股票 {stock_ids} 的資訊：\n{stock_info}\n。請先按照格式輸出資訊，再提供專業的分析或建議，並回答使用者問題。")
    else:
        return chat_with_gemini(user_input)

# 上傳圖片至 Cloudinary
def upload_to_cloudinary(file_path) -> str:
    try:
        response = cloudinary.uploader.upload(file_path)
        return response['secure_url']
    except Exception as e:
        print(f"Image upload failed: {e}")
        return None

# 生成股票收盤價圖
def txt_to_img_url(stock_id: str) -> str:
    try:
        stock = twstock.Stock(stock_id)
        file_name = f'{stock_id}.png'

        df = pd.DataFrame({
            'date': stock.date,
            'close': stock.close,
        })

        df.plot(x='date', y='close')
        plt.title(f'{stock_id} 股票走勢圖')
        plt.savefig(file_name)
        plt.close()

        image_url = upload_to_cloudinary(file_name)
        if image_url:
            os.remove(file_name)
            return image_url
        else:
            return None
    except Exception as e:
        print(f"Error generating stock trend chart: {e}")
        return None

