import os
import re
import twstock
import cloudinary
import cloudinary.uploader
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd
from dotenv import load_dotenv
import logging
import tempfile

# --- 基本設定 ---
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s')

# Cloudinary 設定
CLOUDINARY_CLOUD_NAME = os.getenv('CLOUDINARY_CLOUD_NAME')
CLOUDINARY_API_KEY = os.getenv('CLOUDINARY_API_KEY')
CLOUDINARY_API_SECRET = os.getenv('CLOUDINARY_API_SECRET')

if all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
    cloudinary.config(
        cloud_name=CLOUDINARY_CLOUD_NAME,
        api_key=CLOUDINARY_API_KEY,
        api_secret=CLOUDINARY_API_SECRET,
        secure=True
    )
    logging.info("Cloudinary API (stock_chart) 已設定。")
else:
    logging.warning("Cloudinary API (stock_chart) 未完整設定，圖片上傳功能將無法使用。")

# --- 字型設定 (針對 Matplotlib 中文顯示) ---
FONT_PATHS = [
    'C:/Windows/Fonts/msyh.ttc',
    'C:/Windows/Fonts/simhei.ttf',
    '/System/Library/Fonts/PingFang.ttc',
    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
]
CHINESE_FONT = None
for font_path in FONT_PATHS:
    if os.path.exists(font_path):
        try:
            CHINESE_FONT = fm.FontProperties(fname=font_path)
            logging.info(f"成功載入中文字型 (stock_chart): {font_path}")
            break
        except Exception as e:
            logging.warning(f"嘗試載入字型 {font_path} 失敗 (stock_chart): {e}")
if not CHINESE_FONT:
    logging.warning("未找到任何預設的中文字型 (stock_chart)，圖表中的中文可能無法正常顯示。")

# --- 股票代碼資料 ---
default_stock_data = {
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
    "彰銀": "2801", "聯華": "1229", "致茂": "2360", "永豐金": "2890", "力成": "6239"
}

# --- 輔助函式 ---
def _resolve_stock_identifier(identifier: str) -> tuple[str | None, str | None]:
    identifier = identifier.strip()
    match_digits = re.fullmatch(r'(\d{4,6})', identifier)
    if match_digits:
        stock_id = match_digits.group(1)
        stock_name = next((name for name, code in default_stock_data.items() if code == stock_id), None)
        logging.info(f"Input '{identifier}' resolved to stock ID: {stock_id}, Name: {stock_name}")
        return stock_id, stock_name
    if identifier in default_stock_data:
        stock_id = default_stock_data[identifier]
        logging.info(f"Input '{identifier}' (company name) resolved to stock ID: {stock_id}")
        return stock_id, identifier
    logging.warning(f"Could not resolve '{identifier}' to a valid stock ID or known company name.")
    return None, None

def _upload_to_cloudinary(file_path: str) -> str | None:
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        logging.error("Cloudinary 未設定完成，無法上傳檔案。")
        return None
    try:
        response = cloudinary.uploader.upload(file_path, folder="stock_charts_minimal_v2")
        logging.info(f"檔案 {file_path} 成功上傳至 Cloudinary: {response.get('secure_url')}")
        return response.get('secure_url')
    except Exception as e:
        logging.error(f"上傳 Cloudinary 失敗 {file_path}: {e}", exc_info=True)
        return None

def _generate_chart_image_and_upload(stock_id: str, stock_name_for_title: str | None = None) -> str | None:
    temp_file_path = None
    fig = None
    try:
        stock = twstock.Stock(stock_id)

        if not stock.date or not stock.close or len(stock.date) < 2:
            logging.warning(f"股票 {stock_id} 的 twstock 資料不足 (缺少 date 或 close)")
            return None

        # 建立 DataFrame
        df = pd.DataFrame({
            'date': pd.to_datetime(stock.date),
            'close': pd.to_numeric(stock.close, errors='coerce')
        })
        df.dropna(subset=['close'], inplace=True)

        df_recent = df.tail(252)

        if df_recent.empty or len(df_recent) < 2:
            logging.warning(f"股票 {stock_id} 的資料在過濾後不足以繪圖。")
            return None

        plt.style.use('seaborn-v0_8-darkgrid')
        fig, ax = plt.subplots(figsize=(10, 5.625))

        ax.plot(df_recent['date'], df_recent['close'], marker='.', linestyle='-', linewidth=1.5, label='收盤價')

        title_text = f"{stock_name_for_title} ({stock_id})" if stock_name_for_title else stock_id
        ax.set_title(f"{title_text} 股價走勢圖 (近一年)", fontproperties=CHINESE_FONT, fontsize=16, pad=15)
        ax.set_xlabel("日期", fontproperties=CHINESE_FONT, fontsize=12)
        ax.set_ylabel("價格 (TWD)", fontproperties=CHINESE_FONT, fontsize=12)

        plt.xticks(rotation=30, ha='right', fontproperties=CHINESE_FONT, fontsize=9)
        plt.yticks(fontproperties=CHINESE_FONT, fontsize=9)

        ax.legend(prop=CHINESE_FONT, fontsize=10)
        ax.grid(True, linestyle='--', alpha=0.6)
        plt.tight_layout()

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as temp_image_file:
            plt.savefig(temp_image_file.name, dpi=90)
            temp_file_path = temp_image_file.name

        plt.close(fig)
        fig = None

        return _upload_to_cloudinary(temp_file_path)

    except Exception as e:
        logging.error(f"產生股票圖表時發生錯誤 {stock_id}: {e}", exc_info=True)
        if fig: plt.close(fig)
        return None
    finally:
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.remove(temp_file_path)
                logging.info(f"已刪除暫存圖表檔案: {temp_file_path}")
            except Exception as e_remove:
                logging.error(f"刪除暫存圖表檔案失敗 {temp_file_path}: {e_remove}")

# --- 提供給 app.py 呼叫的主函式 ---
def generate_stock_chart_url(identifier: str) -> str | None:
    """
    提供給 app.py 呼叫的主函式。
    接收股票識別碼（代碼或名稱），回傳其股價趨勢圖的 URL。
    """
    logging.info(f"收到繪圖請求：'{identifier}'")
    stock_id, stock_name = _resolve_stock_identifier(identifier)

    if not stock_id:
        return None # 識別碼無法解析

    return _generate_chart_image_and_upload(stock_id, stock_name_for_title=stock_name)

# --- 測試程式碼 ---
if __name__ == "__main__":
    logging.info("開始執行 stock_chart.py 最小測試...")
    test_ids = ["2330", "台積電", "0050", "聯發科", "InvalidName", "99999"]
    if not all([CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET]):
        logging.warning("Cloudinary 設定不完整，上傳將會失敗（URL 會是 None）。")
    for tid in test_ids:
        logging.info(f"\n--- 測試識別碼：'{tid}' ---")
        url = generate_stock_chart_url(tid)
        if url:
            logging.info(f"'{tid}' 的圖表網址為：{url}")
        else:
            logging.warning(f"無法產生 '{tid}' 的圖表網址。")
    logging.info("stock_chart.py 測試完成。")
