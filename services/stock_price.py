import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s')

def get_stock_price(stock_id: str) -> str:
    """
    根據台股代碼取得即時股價資訊 (主要支援上市股票 TSE)。
    回傳格式化的股價資訊字串，或錯誤訊息。
    """
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw&json=1&delay=0"
    headers = {
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36" # 保持User-Agent更新
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status() # 檢查 HTTP 錯誤 (如 404, 500)
        data = response.json()

        # 確保 'msgArray' 存在且至少有一個元素
        if data.get('msgArray') and len(data['msgArray']) > 0:
            stock_info = data['msgArray'][0]

            # 檢查必要欄位是否存在
            required_keys = ["n", "z", "o", "h", "l", "y"]
            if not all(k in stock_info for k in required_keys):
                logging.warning(f"股票 {stock_id} 的回傳資料欄位不完整: {stock_info}")
                return f"代號 {stock_id} 的資料格式有誤，部分資訊可能缺失。"

            name = stock_info.get("n", "N/A")
            
            price_fields = {
                "即時": stock_info.get("z", "-"),
                "開盤": stock_info.get("o", "-"),
                "最高": stock_info.get("h", "-"),
                "最低": stock_info.get("l", "-"),
                "昨收": stock_info.get("y", "-")
            }

            formatted_prices = {}
            for key, value in price_fields.items():
                try:
                    # 如果值是 '-' 或無法轉換為浮點數，則保持原樣
                    if str(value) == '-' or value is None: # API 可能回傳 None 或 '-'
                        formatted_prices[key] = "-"
                    else:
                        float_val = float(value)
                        formatted_prices[key] = f"{float_val:.2f}"
                except ValueError:
                    formatted_prices[key] = "-" # 如果轉換失敗，也顯示 "-"
            
            return (
                f"📈【{name}】({stock_id})\n"
                f"即時：{formatted_prices['即時']}\n"
                f"開盤：{formatted_prices['開盤']}\n"
                f"最高：{formatted_prices['最高']}\n"
                f"最低：{formatted_prices['最低']}\n"
                f"昨收：{formatted_prices['昨收']}"
            )
        else:
            # API 可能回傳空 msgArray 或其他代碼 (如 '0501' 代表查無資料)
            api_error_code = data.get('rtcode')
            logging.info(f"查無股票代號 {stock_id} (TSE) 的資料。API回應: {data}")
            if api_error_code == '0501' or (data.get('msgArray') and not data['msgArray']):
                 return f"查無上市股票代號 {stock_id} 的資料，請確認代號是否正確。"
            return f"無法取得 {stock_id} 股價，可能是代號錯誤或非上市股票。"

    except requests.exceptions.HTTPError as e:
        logging.error(f"請求股票 {stock_id} 資料時發生 HTTP 錯誤: {e.response.status_code} - {e.response.text}")
        return f"無法取得股票資料({stock_id})，網路請求錯誤 ({e.response.status_code})。"
    except requests.exceptions.ConnectionError as e:
        logging.error(f"請求股票 {stock_id} 資料時發生連接錯誤: {e}")
        return f"無法取得股票資料({stock_id})，網路連接失敗。"
    except requests.exceptions.Timeout as e:
        logging.error(f"請求股票 {stock_id} 資料時發生超時錯誤: {e}")
        return f"無法取得股票資料({stock_id})，請求超時。"
    except requests.exceptions.RequestException as e:
        logging.error(f"請求股票 {stock_id} 資料時發生未知網路錯誤: {e}")
        return f"無法取得股票資料({stock_id})，發生未知的網路請求問題。"
    except ValueError as e: # JSON 解析錯誤
        logging.error(f"解析股票 {stock_id} 的 JSON 資料時發生錯誤: {e}")
        return f"無法解析股票資料({stock_id})，資料格式可能不正確。"
    except Exception as e:
        logging.exception(f"取得股票 {stock_id} 資料時發生未預期錯誤") # logging.exception 會記錄堆疊追蹤
        return f"無法取得股票資料({stock_id})，發生未預期錯誤，請稍後再試。"

# --- 測試代碼 ---
if __name__ == "__main__":
    print(get_stock_price("2330")) # 台積電
    print("-" * 30)
    print(get_stock_price("0050")) # 元大台灣50
    print("-" * 30)
    print(get_stock_price("99999")) # 不存在的股票代號
    print("-" * 30)
    print(get_stock_price("6446")) # 測試上櫃股票 (預期會查不到，因為目前僅支援上市)
