import os
from dotenv import load_dotenv
load_dotenv()
import google.generativeai as genai
import twstock
import re
import cloudinary
import cloudinary.uploader
import matplotlib
matplotlib.use('Agg')  # For server compatibility
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime

# 設定 Gemini API 金鑰
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

# 建立 Gemini 模型
gemini_model = genai.GenerativeModel('gemini-pro')

default_data = { ... }  # 原本的股票代碼 dict 照樣保留（已省略，請用你的版本補上）

def extract_stock_id(user_input: str) -> list:
    match = re.findall(r'\d{4,6}', user_input)
    if match:
        return match

    try:
        prompt = f"""
        你是一個可以提取與辨識公司股票代號的助手。
        功能一：提取句子中的數字代碼，或是，
        功能二：回答句子中提及的可辨識的公司名稱所對應的股票代號，只輸出純數字。
        以下是使用者輸入：
        {user_input}
        常見代碼如下：
        {default_data}
        如果沒有找到與公司相關的股票資訊的話，請只回答 "None"
        """

        response = gemini_model.generate_content(prompt)
        ai_response = response.text.strip()

        match = re.findall(r'\d{4,6}', ai_response)
        return match if match else None
    except Exception as e:
        print(f"Gemini API 錯誤: {e}")
        return None

def get_stock_info(stock_id: str) -> str:
    try:
        stock = twstock.Stock(stock_id)
        recent_dates = stock.date[-25:]
        recent_prices = stock.price[-25:]
        recent_highs = stock.high[-25:]

        if None in recent_prices or None in recent_highs:
            return f"抱歉，無法取得 {stock_id} 的完整數據，請稍後再試。"

        result = f"股票代號：{stock_id}\n近五日數據：\n"
        for i in range(len(recent_dates)):
            date_str = recent_dates[i].strftime("%Y-%m-%d")
            result += f"- 日期：{date_str}，收盤價：{recent_prices[i]}，高點：{recent_highs[i]}\n"
        return result
    except Exception as e:
        return f"抱歉，無法取得股票代號 {stock_id} 的資訊。\n錯誤原因：{e}"

def process_user_input(user_input: str) -> str:
    stock_ids = extract_stock_id(user_input)
    if stock_ids:
        stock_info = ''
        for sid in stock_ids:
            stock_info += get_stock_info(sid) + '\n'
        return chat_with_gpt(f"使用者輸入：{user_input}\n以下是股票 {stock_ids} 的資訊：\n{stock_info}\n請先整理資訊，再提供分析與建議。")
    else:
        return chat_with_gpt(user_input)

def chat_with_gpt(prompt: str) -> str:
    try:
        messages = [
            "你是一個使用繁體中文的聊天機器人，專門回答股票相關問題。若沒有收到股票資訊，可以建議使用者提供股票代碼。",
            prompt
        ]
        response = gemini_model.generate_content(messages)
        return response.text.strip()
    except Exception as e:
        return f"Gemini 回應錯誤: {e}"

def upload_to_cloudinary(file_path) -> str:
    try:
        response = cloudinary.uploader.upload(file_path)
        return response['secure_url']
    except Exception as e:
        print(f"Image upload failed: {e}")
        return None

def txt_to_img_url(stock_ids: str) -> str:
    try:
        sid = stock_ids
        stock = twstock.Stock(sid)
        file_name = f'{sid}.png'

        # 準備股票資料
        stock_data = {
            'close': stock.close,
            'date': stock.date,
            'high': stock.high,
            'low': stock.low,
            'open': stock.open
        }

        df = pd.DataFrame.from_dict(stock_data)

        # 畫圖
        df.plot(x='date', y='close')
        plt.title(f'{sid} stock price')
        plt.savefig(file_name)
        plt.close()

        # 上傳到 Cloudinary
        image_url = upload_to_cloudinary(file_name)

        if image_url:
            os.remove(file_name)
            return image_url
        else:
            return None

    except Exception as e:
        print(f"Error generating stock trend chart: {e}")
        return None

if __name__ == "__main__":
    # 測試 1：文字轉圖並上傳 Cloudinary
    stock_code = "2330"  # 台積電
    img_url = txt_to_img_url(stock_code)
    if img_url:
        print(f"圖片已上傳：{img_url}")
    else:
        print("圖表產生或上傳失敗")

    # 測試 2：處理自然語言輸入
    user_text = "幫我查一下台積電最近的走勢"
    response = process_user_input(user_text)
    print("\nAI 回應：")
    print(response)
