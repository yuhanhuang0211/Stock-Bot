import requests
import logging # 建議加入 logging 模組，方便追蹤和除錯

# 設定日誌記錄
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_stock_price(stock_id: str) -> str:
    """
    根據台股代碼取得即時股價資訊
    目前主要支援上市股票 (tse)
    參數：stock_id (str): 股票代號，例如 "2330"
    回傳 (str): 格式化的股票資訊字串，或錯誤訊息
    """
    # 嘗試上市股票 (TSE)
    # 您也可以考慮增加一個參數來指定市場別 (tse/otc)，或者進行更複雜的判斷邏輯
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw&json=1&delay=0"
    headers = {
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7", # 增加 Accept-Language 標頭，模擬更真實的瀏覽器行為
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36" # 更新 User-Agent
    }

    try:
        response = requests.get(url, headers=headers, timeout=10) # 稍微增加 timeout 時間
        response.raise_for_status() # 檢查 HTTP 請求是否成功 (狀態碼 2xx)
        data = response.json()

        # 更嚴謹地檢查 'msgArray' 是否存在且非空
        if data.get('msgArray') and len(data['msgArray']) > 0:
            stock_info = data['msgArray'][0]

            # 確認必要的欄位是否存在，提供更明確的錯誤資訊
            if not all(k in stock_info for k in ["n", "z", "o", "h", "l", "y"]):
                logging.warning(f"股票 {stock_id} 的回傳資料欄位不完整: {stock_info}")
                return f"代號 {stock_id} 的資料格式有誤，部分資訊可能缺失。"

            name = stock_info.get("n", "未知名稱")
            current_price = stock_info.get("z", "-") # 即時價格
            open_price = stock_info.get("o", "-")
            high = stock_info.get("h", "-")
            low = stock_info.get("l", "-")
            prev_close = stock_info.get("y", "-")
            # 可以考慮加入漲跌 (c, p) 和漲跌幅 (ch)
            # change = stock_info.get("c", "-")
            # change_percent = stock_info.get("p", "-")

            # 檢查價格是否為有效的數值，如果不是，則顯示 "-"
            price_fields = {
                "即時": current_price,
                "開盤": open_price,
                "最高": high,
                "最低": low,
                "昨收": prev_close
            }
            formatted_prices = {}
            for key, value in price_fields.items():
                try:
                    # 如果值是 '-' 或無法轉換為浮點數，則保持原樣
                    if value == '-':
                        formatted_prices[key] = '-'
                    else:
                        float_val = float(value)
                        formatted_prices[key] = f"{float_val:.2f}" # 格式化到小數點後兩位
                except ValueError:
                    formatted_prices[key] = "-" # 如果轉換失敗，也顯示 "-"

            return (
                f"📈【{name}】({stock_id})\n"
                f"即時：{formatted_prices['即時']}\n"
                f"開盤：{formatted_prices['開盤']}\n"
                f"最高：{formatted_prices['最高']}\n"
                f"最低：{formatted_prices['最低']}\n"
                f"昨收：{formatted_prices['昨收']}"
                # f"漲跌：{change} ({change_percent}%)" # 若要加入漲跌資訊
            )
        else:
            # 這裡可以嘗試查詢上櫃股票 (OTC)
            # url_otc = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=otc_{stock_id}.tw&json=1&delay=0"
            # ... (類似的 requests 和處理邏輯) ...
            # 如果查詢 OTC 也失敗，才回傳查無資料
            logging.info(f"查無 TSE 上市股票代號 {stock_id} 的資料。API 回傳: {data}")
            return f"查無代號 {stock_id} 的上市股票資料，請確認輸入是否正確，或該股票是否為上市股票。"

    except requests.exceptions.HTTPError as e:
        logging.error(f"請求股票 {stock_id} 資料時發生 HTTP 錯誤: {e}")
        return f"無法取得股票資料({stock_id})，網路請求錯誤：{e.response.status_code}"
    except requests.exceptions.ConnectionError as e:
        logging.error(f"請求股票 {stock_id} 資料時發生連接錯誤: {e}")
        return f"無法取得股票資料({stock_id})，網路連接失敗。"
    except requests.exceptions.Timeout as e:
        logging.error(f"請求股票 {stock_id} 資料時發生超時錯誤: {e}")
        return f"無法取得股票資料({stock_id})，請求超時。"
    except requests.exceptions.RequestException as e: # 捕獲 requests 可能引發的其他所有異常
        logging.error(f"請求股票 {stock_id} 資料時發生未知請求錯誤: {e}")
        return f"無法取得股票資料({stock_id})，發生未知的網路請求問題。"
    except ValueError as e: # JSON 解析錯誤
        logging.error(f"解析股票 {stock_id} 的 JSON 資料時發生錯誤: {e}")
        return f"無法解析股票資料({stock_id})，資料格式可能不正確。"
    except Exception as e: # 捕獲所有其他未預期的錯誤
        logging.exception(f"取得股票 {stock_id} 資料時發生未預期錯誤") # 使用 logging.exception 會記錄堆疊追蹤
        return f"無法取得股票資料({stock_id})，發生未預期錯誤，請稍後再試。"

# --- 測試代碼 ---
if __name__ == "__main__":
    # 測試上市股票
    print(get_stock_price("2330")) # 台積電
    print("-" * 30)
    print(get_stock_price("0050")) # 元大台灣50
    print("-" * 30)
    # 測試不存在的股票代號
    print(get_stock_price("99999"))
    print("-" * 30)
    # 測試可能回傳資料但欄位不完整的狀況 (假設)
    # 這部分需要依賴實際 API 可能的回傳狀況來模擬
    # print(get_stock_price("xxxx")) # 假設一個會回傳但資料不全的代號
