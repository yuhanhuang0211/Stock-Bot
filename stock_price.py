import requests

# 台積電（2330）的 TWSE API 資料來源
url = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp?ex_ch=tse_2330.tw&json=1&delay=0"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(url, headers=headers)
data = response.json()

# 檢查是否成功取得資料
if data.get('msgArray'):
    stock_info = data['msgArray'][0]

    fields = {
        "名稱": stock_info.get("n"),
        "今開": stock_info.get("o"),
        "最高": stock_info.get("h"),
        "最低": stock_info.get("l"),
        "昨收": stock_info.get("y"),
    }


    # 輸出結果（保留小數點 2 位）
    for key, value in fields.items():
        try:
            # 如果是數字就四捨五入
            value_float = float(value)
            print(f"{key}: {round(value_float, 2)}")
        except (ValueError, TypeError):
            # 無法轉換就原樣輸出（如成交量通常是整數字串）
            print(f"{key}: {value}")
else:
    print("無法取得股票資料，請稍後再試。")
