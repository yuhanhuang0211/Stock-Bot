import requests

def get_stock_price(stock_id: str) -> str:
    """
    根據台股代碼取得即時股價資訊
    參數：stock_id，例如 "2330"
    回傳：格式化字串
    """
    url = f"https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_{stock_id}.tw&json=1&delay=0"
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=5)
        response.raise_for_status()
        data = response.json()

        if data.get('msgArray'):
            stock_info = data['msgArray'][0]

            name = stock_info.get("n", "未知名稱")
            open_price = stock_info.get("o", "-")
            high = stock_info.get("h", "-")
            low = stock_info.get("l", "-")
            prev_close = stock_info.get("y", "-")

            return (
                f"📈【{name}】({stock_id})\n"
                f"開盤：{open_price}\n"
                f"最高：{high}\n"
                f"最低：{low}\n"
                f"昨收：{prev_close}"
            )
        else:
            return f"查無代號 {stock_id} 的資料，請確認輸入是否正確。"

    except Exception as e:
        return f"無法取得股票資料，錯誤訊息：{e}"
