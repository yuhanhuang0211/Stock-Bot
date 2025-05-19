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

default_data = {
    "中油": "6505",
    "台積電": "2330",
    "鴻海": "2317",
    "台泥": "1101",
    "富邦金": "2881",
    "儒鴻": "1476",
    "技嘉": "2376",
    "潤泰全": "2915",
    "同欣電": "6271",
    "亞泥": "1102",
    "國泰金": "2882",
    "聚陽": "1477",
    "微星": "2377",
    "神基": "3005",
    "台表科": "6278",
    "統一": "1216",
    "玉山金": "2884",
    "東元": "1504",
    "台光電": "2383",
    "信邦": "3023",
    "啟碁": "6285",
    "台塑": "1301",
    "元大金": "2885",
    "華新": "1605",
    "群光": "2385",
    "欣興": "3037",
    "旭隼": "6409",
    "南亞": "1303",
    "兆豐金": "2886",
    "長興": "1717",
    "漢唐": "2404",
    "健鼎": "3044",
    "GIS-KY": "6456",
    "台化": "1326",
    "台新金": "2887",
    "台肥": "1722",
    "友達": "2409",
    "景碩": "3189",
    "愛普": "6531",
    "遠東新": "1402",
    "中信金": "2891",
    "台玻": "1802",
    "超豐": "2441",
    "緯創": "3231",
    "和潤企業": "6592",
    "亞德客-KY": "1590",
    "第一金": "2892",
    "永豐餘": "1907",
    "京元電子": "2449",
    "玉晶光": "3406",
    "富邦媒": "8454",
    "中鋼": "2002",
    "統一超": "2912",
    "大成鋼": "2027",
    "義隆": "2458",
    "創意": "3443",
    "億豐": "8464",
    "正新": "2105",
    "大立光": "3008",
    "上銀": "2049",
    "華新科": "2492",
    "群創": "3481",
    "寶成": "9904",
    "和泰車": "2207",
    "聯詠": "3034",
    "川湖": "2059",
    "興富發": "2542",
    "台勝科": "3532",
    "美利達": "9914",
    "聯電": "2303",
    "台灣大": "3045",
    "南港": "2101",
    "長榮": "2603",
    "嘉澤": "3533",
    "中保科": "9917",
    "台達電": "2308",
    "日月光投控": "3711",
    "裕隆": "2201",
    "裕民": "2606",
    "聯合再生": "3576",
    "巨大": "9921",
    "國巨": "2327",
    "遠傳": "4904",
    "裕日車": "2227",
    "陽明": "2609",
    "健策": "3653",
    "裕融": "9941",
    "台塑化": "6505",
    "聯強": "2347",
    "臺企銀": "2834",
    "臻鼎-KY": "4958",
    "南電": "8046",
    "佳世達": "2352",
    "遠東銀": "2845",
    "祥碩": "5269",
    "聯發科": "2454",
    "豐泰": "9910",
    "宏碁": "2353",
    "開發金": "2883",
    "遠雄": "5522",
    "可成": "2474",
    "大成": "1210",
    "鴻準": "2354",
    "新光金": "2888",
    "瑞儀": "6176",
    "台灣高鐵": "2633",
    "佳格": "1227",
    "英業達": "2356",
    "國票金": "2889",
    "聯茂": "6213",
    "彰銀": "2801",
    "聯華": "1229",
    "致茂": "2360",
    "永豐金": "2890",
    "力成": "6239"
}

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
        return chat_with_gemini(f"使用者輸入：{user_input}\n以下是股票 {stock_ids} 的資訊：\n{stock_info}\n請先整理資訊，再提供分析與建議。")
    return chat_with_gemini(user_input)

def chat_with_gemini(prompt: str) -> str:
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
