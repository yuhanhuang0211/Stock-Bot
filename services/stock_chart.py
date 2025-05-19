import os
import re
import twstock
import cloudinary
import cloudinary.uploader
import google.generativeai as genai
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

cloudinary.config(
    cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
    api_key=os.getenv('CLOUDINARY_API_KEY'),
    api_secret=os.getenv('CLOUDINARY_API_SECRET')
)

model = genai.GenerativeModel(model_name="models/gemini-1.5-flash")

default_data = { ... }  # 請使用你自己的股票代碼對照表

def extract_stock_id(user_input: str) -> list:
    match = re.findall(r'\d{4,6}', user_input)
    if match:
        return match

    try:
        prompt = f"""
        你是一個可以提取與辨識公司股票代號的助手。
        以下是使用者輸入：
        {user_input}
        常見代碼如下：
        {default_data}
        如果沒有找到與公司相關的股票資訊，請回答 "None"
        """
        response = model.generate_content([prompt])
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
            return f"抱歉，無法取得 {stock_id} 的完整數據。"

        result = f"股票代號：{stock_id}\n近五日數據：\n"
        for i in range(len(recent_dates)):
            date_str = recent_dates[i].strftime("%Y-%m-%d")
            result += f"- 日期：{date_str}，收盤價：{recent_prices[i]}，高點：{recent_highs[i]}\n"
        return result
    except Exception as e:
        return f"無法取得 {stock_id} 的資訊。\n錯誤原因：{e}"

def process_user_input(user_input: str) -> str:
    stock_ids = extract_stock_id(user_input)
    if stock_ids:
        stock_info = ''.join(get_stock_info(sid) + '\n' for sid in stock_ids)
        return chat_with_gpt(f"使用者輸入：{user_input}\n以下是股票 {stock_ids} 的資訊：\n{stock_info}\n請先整理資訊，再提供分析與建議。")
    return chat_with_gpt(user_input)

def chat_with_gpt(prompt: str) -> str:
    try:
        messages = [
            "你是一個使用繁體中文的聊天機器人，專門回答股票相關問題。",
            prompt
        ]
        response = model.generate_content([messages])
        return response.text.strip()
    except Exception as e:
        return f"Gemini 回應錯誤: {e}"

def upload_to_cloudinary(file_path: str) -> str:
    try:
        response = cloudinary.uploader.upload(file_path)
        return response['secure_url']
    except Exception as e:
        print(f"上傳失敗: {e}")
        return None

def txt_to_img_url(stock_id: str) -> str:
    try:
        stock = twstock.Stock(stock_id)
        file_name = f'{stock_id}.png'

        df = pd.DataFrame({
            'date': stock.date,
            'close': stock.close
        })

        df.plot(x='date', y='close')
        plt.title(f'{stock_id} Stock Price')
        plt.savefig(file_name)
        plt.close()

        image_url = upload_to_cloudinary(file_name)
        if image_url:
            os.remove(file_name)
        return image_url
    except Exception as e:
        print(f"產生圖表錯誤: {e}")
        return None

if __name__ == "__main__":
    # 測試 1：文字轉圖並上傳 Cloudinary
    stock_code = "006208"
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
