# 股往今LINE

GDG on Campus NTPU LINE Bot 小專案

這個專案旨在創建一個能夠即時分析股市的 LINE Bot，利用 Gemini API、twstock 和 Cloudinary 等工具提供服務，使用者可以查詢股市基礎資訊、查看股價走勢圖，或者讓 Bot 從網路上搜尋、統整出最新的新聞內容。

讓你的投資路不再孤單，我們在 LINE 等你！

## 功能簡介

1. **股市查詢**：根據股票代號或公司名稱查詢最新股市資訊。
2. **股價走勢圖**：根據股票代號生成股價走勢圖，並上傳至 Cloudinary。
3. **新聞摘要**：根據關鍵字搜尋新聞，並統整文章標題和摘要。
4. **Gemini 聊天**：利用 Gemini API 回應使用者的問題，並提供專業分析。

## 使用需求

1. Python 3.x
2. 安裝必要的 Python 套件：
   ```bash
   pip install -r requirements.txt
