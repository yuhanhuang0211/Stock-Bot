import requests
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def get_stock_price(stock_id: str) -> str:
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw&json=1&delay=0"
    headers = {
        "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data.get('msgArray'):
            stock_info = data['msgArray'][0]

            if not all(k in stock_info for k in ["n", "z", "o", "h", "l", "y"]):
                logging.warning(f"股票 {stock_id} 的回傳資料欄位不完整: {stock_info}")
                return f"代號 {stock_id} 的資料格式有誤，部分資訊可能缺失。"

            name = stock_info["n"]
            price_fields = {
                "即時": stock_info["z"],
                "開盤": stock_info["o"],
                "最高": stock_info["h"],
                "最低": stock_info["l"],
                "昨收": stock_info["y"]
            }

            formatted = {}
            for k, v in price_fields.items():
                try:
                    formatted[k] = f"{float(v):.2f}" if v != '-' else "-"
                except ValueError:
                    formatted[k] = "-"

            return (
                f"📈【{name}】({stock_id})\n"
                f"即時：{formatted['即時']}\n"
                f"開盤：{formatted['開盤']}\n"
                f"最高：{formatted['最高']}\n"
                f"最低：{formatted['最低']}\n"
                f"昨收：{formatted['昨收']}"
            )
        else:
            logging.info(f"查無 TSE 上市股票代號 {stock_id} 的資料。API 回傳: {data}")
            return f"查無代號 {stock_id} 的上市股票資料，請確認輸入是否正確，或該股票是否為上市股票。"

    except requests.exceptions.HTTPError as e:
        logging.error(f"HTTP 錯誤: {e}")
        return f"無法取得股票資料({stock_id})，網路請求錯誤。"
    except requests.exceptions.ConnectionError:
        logging.error(f"網路連接錯誤")
        return f"無法取得股票資料({stock_id})，網路連接失敗。"
    except requests.exceptions.Timeout:
        logging.error(f"請求超時")
        return f"無法取得股票資料({stock_id})，請求超時。"
    except requests.exceptions.RequestException as e:
        logging.error(f"其他網路錯誤: {e}")
        return f"無法取得股票資料({stock_id})，發生未知的網路請求問題。"
    except ValueError:
        logging.error(f"JSON 解析錯誤")
        return f"無法解析股票資料({stock_id})，資料格式可能不正確。"
    except Exception as e:
        logging.exception(f"未預期錯誤: {e}")
        return f"無法取得股票資料({stock_id})，發生未預期錯誤。"

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
    # print(get_stock_price("xxxx")) # 假設一個會回傳但資料不全的代號
