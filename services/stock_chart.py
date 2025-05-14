import os
import re
import pandas as pd
import matplotlib
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm # 用於字體管理
import twstock
import cloudinary
import cloudinary.uploader
from datetime import datetime, timedelta # timedelta 用於計算日期範圍
from dotenv import load_dotenv
import google.generativeai as genai
import logging # 引入 logging
import tempfile # 用於安全地處理臨時檔案

# --- 基本設定 ---
# Server compatibility for Matplotlib (headless)
matplotlib.use('Agg')

# 設定日誌
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s')

# Load .env variables
load_dotenv()

# Gemini Configuration
try:
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        logging.warning("GEMINI_API_KEY not found in .env file.")
        # 可以在此處決定是否拋出錯誤或讓依賴 Gemini 的功能 gracefully fail
    else:
        genai.configure(api_key=gemini_api_key)
except Exception as e:
    logging.error(f"Error configuring Gemini: {e}")
    # 根據需求處理 Gemini 設定失敗的情況

# Cloudinary Configuration
try:
    cloudinary.config(
        cloud_name=os.getenv('CLOUDINARY_CLOUD_NAME'),
        api_key=os.getenv('CLOUDINARY_API_KEY'),
        api_secret=os.getenv('CLOUDINARY_API_SECRET'),
        secure=True # 建議總是使用 HTTPS
    )
    if not all([os.getenv('CLOUDINARY_CLOUD_NAME'), os.getenv('CLOUDINARY_API_KEY'), os.getenv('CLOUDINARY_API_SECRET')]):
        logging.warning("Cloudinary configuration is incomplete. Check .env file.")
except Exception as e:
    logging.error(f"Error configuring Cloudinary: {e}")

# --- 字型設定 (針對 Matplotlib 中文顯示) ---
# 嘗試找到一個可用的中文字型
# 以下列表可根據您的伺服器環境調整
FONT_PATHS = [
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc', #常見 Linux 中文字型 (文泉驛微米黑)
    '/System/Library/Fonts/PingFang.ttc', # macOS (蘋方)
    'C:/Windows/Fonts/msyh.ttc', # Windows (微軟雅黑)
    'C:/Windows/Fonts/simhei.ttf', # Windows (黑體)
]

def get_available_font():
    for font_path in FONT_PATHS:
        if os.path.exists(font_path):
            logging.info(f"Using font: {font_path}")
            return fm.FontProperties(fname=font_path)
    logging.warning("No suitable Chinese font found in predefined paths. Chinese characters in charts might not display correctly.")
    return None # 回傳 None 表示使用 Matplotlib 預設字型

CHINESE_FONT = get_available_font()


# --- 常見台股公司對應代碼 (可考慮移至獨立設定檔或資料庫) ---
DEFAULT_STOCK_DATA = {
    "中油": "6505", "台積電": "2330", "鴻海": "2317", "台泥": "1101", "富邦金": "2881",
    "儒鴻": "1476", "技嘉": "2376", "潤泰全": "2915", "同欣電": "6271", "亞泥": "1102",
    "國泰金": "2882", "聚陽": "1477", "微星": "2377", "神基": "3005", "台表科": "6278",
    "統一": "1216", "玉山金": "2884", "東元": "1504", "台光電": "2383", "信邦": "3023",
    "啟碁": "6285", "台塑": "1301", "元大金": "2885", "華新": "1605", "群光": "2385",
    "欣興": "3037", "旭隼": "6409", "南亞": "1303", "兆豐金": "2886", "長興": "1717",
    "漢唐": "2404", "健鼎": "3044", "GIS-KY": "6456", "台化": "1326", "台新金": "2887",
    "台肥": "1722", "友達": "2409", "景碩": "3189", "愛普": "6531", "遠東新": "1402",
    "中信金": "2891", "台玻": "1802", "超豐": "2441", "緯創": "3231", "和潤企業": "6592",
    "亞德客-KY": "1590", "第一金": "2892", "永豐餘": "1907", "京元電子": "2449", "玉晶光": "3406",
    "富邦媒": "8454", "中鋼": "2002", "統一超": "2912", "大成鋼": "2027", "義隆": "2458",
    "創意": "3443", "億豐": "8464", "正新": "2105", "大立光": "3008", "上銀": "2049",
    "華新科": "2492", "群創": "3481", "寶成": "9904", "和泰車": "2207", "聯詠": "3034",
    "川湖": "2059", "興富發": "2542", "台勝科": "3532", "美利達": "9914", "聯電": "2303",
    "台灣大": "3045", "南港": "2101", "長榮": "2603", "嘉澤": "3533", "中保科": "9917",
    "台達電": "2308", "日月光投控": "3711", "裕隆": "2201", "裕民": "2606", "聯合再生": "3576",
    "巨大": "9921", "國巨": "2327", "遠傳": "4904", "裕日車": "2227", "陽明": "2609",
    "健策": "3653", "裕融": "9941", "台塑化": "6505", "聯強": "2347", "臺企銀": "2834",
    "臻鼎-KY": "4958", "南電": "8046", "佳世達": "2352", "遠東銀": "2845", "祥碩": "5269",
    "聯發科": "2454", "豐泰": "9910", "宏碁": "2353", "開發金": "2883", "遠雄": "5522",
    "可成": "2474", "大成": "1210", "鴻準": "2354", "新光金": "2888", "瑞儀": "6176",
    "台灣高鐵": "2633", "佳格": "1227", "英業達": "2356", "國票金": "2889", "聯茂": "6213",
    "彰銀": "2801", "聯華": "1229", "致茂": "2360", "永豐金": "2890", "力成": "6239",
}

# --- Gemini 相關函式 (可考慮移至 gemini_service.py) ---
def chat_with_gemini(prompt: str) -> str:
    """與 Gemini Pro 模型進行對話。"""
    if not genai.get_api_key():
        return "Gemini API 未設定，無法進行對話。"
    try:
        model = genai.GenerativeModel('gemini-pro')
        response = model.generate_content(prompt)
        return response.text.strip()
    except Exception as e:
        logging.error(f"Gemini API 錯誤: {e}")
        return f"與 AI 溝通時發生錯誤，請稍後再試。"

def extract_stock_id_from_text(user_input: str) -> list[str] | None:
    """
    從使用者輸入中提取股票代碼。
    優先使用正規表達式，若無匹配，則嘗試使用 Gemini 進行提取。
    回傳：股票代碼列表或 None。
    """
    # 1. 使用正規表達式提取純數字代碼
    #    常見台股代碼為 4-6 位數字
    matches = re.findall(r'\b\d{4,6}\b', user_input) # \b 確保是獨立的數字
    if matches:
        logging.info(f"透過 Regex 提取到股票代碼: {matches}")
        return list(set(matches)) # 去除重複

    # 2. 如果 regex 沒找到，且使用者輸入了非數字（可能是公司名稱），嘗試使用 Gemini
    #    僅在輸入看起來不是純粹的股票代碼時才調用 Gemini，以節省 API call
    if not user_input.isdigit() and genai.get_api_key():
        logging.info(f"Regex 未找到股票代碼，嘗試使用 Gemini 提取: '{user_input}'")
        try:
            model = genai.GenerativeModel('gemini-pro')
            # 優化後的 Prompt，更明確指示輸出格式，減少不必要的聊天內容
            # default_data 字串可能過長，這裡選擇不直接傳入整個字典，依賴模型的知識庫
            # 如果有必要，可以動態選擇部分相關的 default_data 傳入
            prompt = f"""
            請從以下使用者輸入文字中提取台灣股票的代號 (4到6位數字)。
            如果文字中包含明確的台灣公司名稱，請提供其對應的股票代號。
            如果找到多個，請都列出來，並用逗號分隔。
            如果沒有找到任何股票代號或相關公司，請只回覆 "None"。
            使用者輸入: "{user_input}"
            常見公司範例 (僅供參考，你應優先理解使用者意圖): 台積電是2330, 鴻海是2317, 中華電是2412。
            """
            response = model.generate_content(prompt)
            ai_response = response.text.strip()
            logging.info(f"Gemini 針對 '{user_input}' 的回應: '{ai_response}'")

            if ai_response.upper() == "NONE":
                return None
            
            # 從 Gemini 的回應中再次提取數字代碼
            ai_matches = re.findall(r'\b\d{4,6}\b', ai_response)
            if ai_matches:
                return list(set(ai_matches)) # 去除重複
            return None
        except Exception as e:
            logging.error(f"使用 Gemini 提取股票代碼時發生錯誤: {e}")
            return None
    return None

# --- 股票資料與圖表核心功能 ---
def get_stock_data_for_chart(stock_id: str, months: int = 6) -> pd.DataFrame | None:
    """
    使用 twstock 獲取指定股票特定月份的歷史數據。
    參數:
        stock_id (str): 股票代號。
        months (int): 要獲取的歷史數據月份數，預設為 6 個月。
    回傳:
        pd.DataFrame: 包含 'date', 'open', 'high', 'low', 'close', 'volume' 的 DataFrame，或 None。
    """
    try:
        stock = twstock.Stock(stock_id)
        # 計算起始日期
        end_date = datetime.now()
        start_date = end_date - timedelta(days=months * 30) # 近似月份，twstock 會處理

        # twstock.Stock.fetch_from(year, month)
        # 我們需要將 start_date 和 end_date 轉換為 year/month
        # 並且獲取這段時間內的所有數據
        # twstock 的 fetch_from 比較適合獲取某年某月起的資料
        # 為了簡化，這裡我們取用 stock 物件內建的歷史資料，然後再篩選
        
        if not stock.price: # 檢查是否有價格資料
            logging.warning(f"股票 {stock_id} 查無價格資料 (twstock)。")
            return None

        data = {
            'date': stock.date,
            'open': stock.open,
            'high': stock.high,
            'low': stock.low,
            'close': stock.close,
            'volume': stock.capacity # 容量通常指成交量
        }
        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date']) # 轉換日期格式

        # 篩選指定月份的數據
        df = df[df['date'] >= start_date]

        if df.empty:
            logging.warning(f"股票 {stock_id} 在最近 {months} 個月內無數據。")
            return None
        
        return df.sort_values(by='date') #確保日期排序

    except Exception as e:
        # twstock.Stock(stock_id) 可能會因為代號錯誤、網路問題等拋出例外
        logging.error(f"獲取股票 {stock_id} 的 twstock 資料時發生錯誤: {e}")
        return None

def generate_stock_chart_image(stock_id: str, stock_name: str | None = None, data_df: pd.DataFrame | None = None) -> str | None:
    """
    生成股票走勢圖並上傳至 Cloudinary。
    參數:
        stock_id (str): 股票代號。
        stock_name (str, optional): 股票名稱，用於圖表標題。
        data_df (pd.DataFrame, optional): 預先獲取的股票數據。如果為 None，則會重新獲取近6個月數據。
    回傳:
        str: Cloudinary 上的圖片 URL，或 None (若失敗)。
    """
    if data_df is None:
        data_df = get_stock_data_for_chart(stock_id, months=6)

    if data_df is None or data_df.empty:
        logging.warning(f"無法生成股票 {stock_id} 的圖表，因數據不足。")
        return None

    # 獲取股票名稱 (如果未提供)
    if stock_name is None:
        # 嘗試從 DEFAULT_STOCK_DATA 中查找
        for name, sid in DEFAULT_STOCK_DATA.items():
            if sid == stock_id:
                stock_name = name
                break
        if stock_name is None: # 如果還是沒找到，嘗試用 twstock 的 realtime 資訊 (可能不準確或耗時)
            try:
                realtime_info = twstock.realtime.get(stock_id)
                if realtime_info and realtime_info.get('info', {}).get('name'):
                    stock_name = realtime_info['info']['name']
                else:
                    stock_name = stock_id # 最後手段，用代號當名稱
            except Exception:
                stock_name = stock_id # 出錯也用代號

    plt.style.use('seaborn-v0_8-darkgrid') # 使用一個不錯的樣式
    fig, ax = plt.subplots(figsize=(12, 6)) # 調整圖片大小

    # 繪製收盤價折線圖
    ax.plot(data_df['date'], data_df['close'], label='收盤價', color='skyblue', linewidth=2)

    # 設定圖表標題和標籤
    title = f"{stock_name} ({stock_id}) 股價走勢圖 (近六個月)"
    ax.set_title(title, fontproperties=CHINESE_FONT, fontsize=16)
    ax.set_xlabel("日期", fontproperties=CHINESE_FONT, fontsize=12)
    ax.set_ylabel("價格 (TWD)", fontproperties=CHINESE_FONT, fontsize=12)

    # 格式化 X 軸日期顯示
    plt.xticks(rotation=45)
    ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter('%Y-%m-%d'))

    ax.legend(prop=CHINESE_FONT)
    ax.grid(True) # 加強網格線
    plt.tight_layout() # 自動調整子圖參數，使之相應地填充整個圖像區域

    # 使用 NamedTemporaryFile 來處理臨時圖片檔案，更安全
    # suffix='.png' 確保副檔名正確
    # delete=False 使得在 cloudinary 上傳前檔案不會被刪除 (Windows下需要)
    temp_image_file = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_image_file:
            plt.savefig(temp_image_file.name)
            image_file_path = temp_image_file.name
        
        plt.close(fig) # 關閉圖表，釋放資源

        # 上傳到 Cloudinary
        if not all([os.getenv('CLOUDINARY_CLOUD_NAME'), os.getenv('CLOUDINARY_API_KEY'), os.getenv('CLOUDINARY_API_SECRET')]):
            logging.error("Cloudinary 未設定完成，無法上傳圖片。")
            return None

        upload_response = cloudinary.uploader.upload(image_file_path, folder="stock_charts") # 可以指定資料夾
        logging.info(f"圖片 {image_file_path} 已成功上傳至 Cloudinary: {upload_response.get('secure_url')}")
        return upload_response.get('secure_url')

    except Exception as e:
        logging.error(f"生成或上傳股票 {stock_id} 圖表時發生錯誤: {e}")
        if fig: # 如果 fig 存在但未關閉
            plt.close(fig)
        return None
    finally:
        # 清理臨時檔案
        if temp_image_file and os.path.exists(temp_image_file.name):
            os.remove(temp_image_file.name)
            logging.info(f"已刪除臨時圖檔: {temp_image_file.name}")


# --- 原有的其他函式 (審閱與備註) ---

# `get_stock_info` : 這個函數獲取近五日文字數據。
# 如果您的 LINE Bot "股價" 功能是即時的 (如 stock_price.py)，
# 而 "走勢圖" 功能是圖片，那麼這個函數的角色需要釐清。
# 它可能是用於某種文字總結，或者可以整合到 Gemini 的分析中。
# 以下保留原函數結構，但建議考慮其必要性。
def get_formatted_recent_stock_data(stock_id: str) -> str:
    """
    獲取股票近五日數據的文字描述 (使用 twstock)。
    回傳: 格式化字串或錯誤訊息。
    """
    try:
        stock = twstock.Stock(stock_id)
        # 檢查數據是否存在且足夠
        if not stock.date or len(stock.date) < 5:
            logging.warning(f"股票 {stock_id} 的歷史數據不足五日 (twstock)。")
            # 可以嘗試獲取 realtime.get(stock_id).get('success') == False
            # 來判斷是否為無效代號，但 realtime.get 可能較慢
            rt_info = twstock.realtime.get(stock_id)
            if 'success' in rt_info and not rt_info['success']:
                return f"查無股票代號 {stock_id} 的有效資訊，請確認代號是否正確。"
            return f"抱歉，股票 {stock_id} 的歷史數據不足五日，無法提供近五日摘要。"

        # 取最新的五筆有效數據 (假設 stock.date, stock.price 等已按日期排序)
        recent_dates = stock.date[-5:]
        recent_prices = stock.price[-5:]
        recent_highs = stock.high[-5:]
        # recent_lows = stock.low[-5:]
        # recent_opens = stock.open[-5:]

        # 確保所有列表都有數據 (雖然上面檢查了 date，但 price 等也可能為空或長度不符)
        if not all([len(lst) == 5 for lst in [recent_prices, recent_highs]]):
             return f"抱歉，無法取得 {stock_id} 的完整五日數據，部分欄位缺失。"


        result = f"股票代號：{stock_id}\n近五日數據 (來自 twstock):\n"
        for i in range(len(recent_dates)):
            date_str = recent_dates[i].strftime("%Y-%m-%d")
            price_str = f"{recent_prices[i]:.2f}" if isinstance(recent_prices[i], (int, float)) else str(recent_prices[i])
            high_str = f"{recent_highs[i]:.2f}" if isinstance(recent_highs[i], (int, float)) else str(recent_highs[i])
            result += f"- 日期：{date_str}，收盤價：{price_str}，最高價：{high_str}\n"
        return result.strip()
    except Exception as e:
        # 更具體地捕獲 twstock 可能的錯誤會更好，但通常其錯誤不是很具體
        logging.error(f"使用 twstock 獲取股票 {stock_id} 近五日資訊時發生錯誤: {e}")
        return f"抱歉，查詢股票代號 {stock_id} 時發生問題，可能是代號無效或查無資料。"


# `process_user_input`: 這個函數的流程似乎是：
# 1. 提取股票 ID。
# 2. 如果有 ID，獲取每個 ID 的文字版股票資訊 (get_formatted_recent_stock_data)。
# 3. 將原始輸入和提取到的資訊一起發給 Gemini 進行分析和回答。
# 4. 如果沒有股票 ID，直接將用戶輸入發給 Gemini。
#
# 這個流程比較適合一個通用的股票問答或分析場景，而不是直接觸發「走勢圖」功能。
# 在您的 LINE Bot 流程中，當使用者點擊圖文選單的「走勢圖」並輸入代號後，
# 應該直接調用 `generate_stock_chart_image(stock_id)`。
# 如果「直接輸入訊息」是要跟 Gemini 對話，那這個 `process_user_input` 可能屬於該流程。
# 因此，我將此函數保留，但您需要根據 `app.py` 的實際調用邏輯來決定它的位置和用途。

def process_general_stock_query_with_gemini(user_input: str) -> str:
    """
    處理使用者關於股票的通用查詢，並使用 Gemini 進行分析和回覆。
    """
    stock_ids = extract_stock_id_from_text(user_input)
    if stock_ids:
        stock_info_parts = []
        for sid in stock_ids:
            info = get_formatted_recent_stock_data(sid) # 使用上面修改過的函數
            stock_info_parts.append(info)
        
        # 檢查是否有成功獲取到任何資訊
        valid_stock_info = [s for s in stock_info_parts if not s.startswith("抱歉") and not s.startswith("查無股票代號")]
        
        if not valid_stock_info:
            # 如果所有代號都查詢失敗
            error_messages = "\n".join(stock_info_parts)
            # 可以考慮直接回傳錯誤，或讓 Gemini 處理這個情況
            # return f"無法查詢到您指定的股票資訊：\n{error_messages}"
            # 或者，讓 Gemini 嘗試回答，但告知它查詢失敗
            gemini_prompt = f"""
            使用者輸入了「{user_input}」。
            我嘗試查詢相關股票 ({', '.join(stock_ids)}) 的近期數據，但都失敗了，可能是代號無效或暫無資料。
            請根據使用者原始問題「{user_input}」進行回覆，可以提醒使用者檢查股票代號，或詢問其他問題。
            """
            return chat_with_gemini(gemini_prompt)

        full_stock_info = "\n\n".join(valid_stock_info)
        
        # 為 Gemini 準備更結構化的 Prompt
        prompt_to_gemini = f"""
        使用者詢問了：「{user_input}」
        我查詢到的相關股票 ({', '.join(stock_ids)}) 近期資訊如下：
        --- 查詢到的數據開始 ---
        {full_stock_info}
        --- 查詢到的數據結束 ---
        請基於以上數據和我提供的「查詢到的數據」，並結合你對股市的知識：
        1.  簡要總結這些股票的近期表現 (如果數據允許)。
        2.  針對使用者的原始問題「{user_input}」提供專業的分析、見解或建議。
        3.  如果使用者問題與提供的數據關聯不大，請側重回答原始問題。
        請以友善和資訊豐富的方式回答。
        """
        return chat_with_gemini(prompt_to_gemini)
    else:
        # 如果沒有提取到股票代號，直接將用戶輸入交給 Gemini 處理 (可能是一般聊天或詢問時事)
        # 這個分支的 prompt 可能需要根據 "直接輸入訊息 -> 跟gemini對話" 的具體需求調整
        logging.info(f"未提取到股票代號，將 \"{user_input}\" 直接交由 Gemini 處理一般對話。")
        general_prompt = f"使用者說：「{user_input}」。請像一個財經助手一樣自然地回應。"
        return chat_with_gemini(general_prompt)

# --- 主函式 (用於直接執行此檔案進行測試) ---
if __name__ == "__main__":
    logging.info("開始測試 stock_chart.py...")

    # 測試股票代碼提取
    print("\n--- 測試股票代碼提取 ---")
    test_inputs = ["我想看2330的走勢", "台積電和鴻海的股價如何？", "0050最近表現", "今天天氣真好", "6446"]
    for tin in test_inputs:
        extracted = extract_stock_id_from_text(tin)
        print(f"輸入: '{tin}' -> 提取結果: {extracted}")

    # 測試獲取近五日數據
    print("\n--- 測試獲取近五日數據 ---")
    test_stock_id_data = "2330" # 台積電
    print(f"獲取 {test_stock_id_data} 的近五日數據:")
    recent_data_output = get_formatted_recent_stock_data(test_stock_id_data)
    print(recent_data_output)
    
    test_invalid_stock_data = "99999" # 無效代號
    print(f"\n獲取 {test_invalid_stock_data} 的近五日數據:")
    recent_data_output_invalid = get_formatted_recent_stock_data(test_invalid_stock_data)
    print(recent_data_output_invalid)

    # 測試生成股票圖表 (會實際產生圖片並嘗試上傳)
    print("\n--- 測試生成股票圖表 ---")
    test_stock_id_chart = "2330"
    print(f"生成 {test_stock_id_chart} (台積電) 的走勢圖...")
    # 確保 Cloudinary 環境變數已設定，否則上傳會失敗但本地仍會產生圖
    if os.getenv('CLOUDINARY_CLOUD_NAME'):
        chart_url = generate_stock_chart_image(test_stock_id_chart, stock_name="台積電")
        if chart_url:
            print(f"圖表已生成並上傳至: {chart_url}")
        else:
            print(f"圖表生成或上傳失敗 for {test_stock_id_chart}.")
        
        chart_url_0050 = generate_stock_chart_image("0050", stock_name="元大台灣50")
        if chart_url_0050:
            print(f"0050 圖表已生成並上傳至: {chart_url_0050}")
        else:
            print(f"圖表生成或上傳失敗 for 0050.")

        # 測試無效代號的圖表生成
        chart_url_invalid = generate_stock_chart_image("99999")
        if chart_url_invalid:
             print(f"圖表已生成並上傳至 (預期失敗): {chart_url_invalid}")
        else:
            print(f"圖表生成或上傳失敗 (預期) for 99999.")

    else:
        print("Cloudinary 未設定，跳過圖表上傳測試。僅測試本地生成 (如啟用)。")
        # 若想測試本地生成而不上傳，可以暫時修改 generate_stock_chart_image 內部邏輯

    # 測試通用股票查詢與 Gemini 分析
    # print("\n--- 測試通用股票查詢與 Gemini 分析 ---")
    # if gemini_api_key:
    #     # query1 = "台積電最近怎麼樣？"
    #     # print(f"查詢: {query1}\nGemini回覆:\n{process_general_stock_query_with_gemini(query1)}")
        
    #     # query2 = "我想知道0050和2317的未來趨勢"
    #     # print(f"\n查詢: {query2}\nGemini回覆:\n{process_general_stock_query_with_gemini(query2)}")

    #     query3 = "你覺得現在適合買進電子股嗎？"
    #     print(f"\n查詢: {query3}\nGemini回覆:\n{process_general_stock_query_with_gemini(query3)}")
    # else:
    #     print("Gemini API Key 未設定，跳過通用股票查詢測試。")

    logging.info("stock_chart.py 測試結束。")
