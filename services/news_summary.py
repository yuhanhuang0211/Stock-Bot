import requests
from newspaper import Article
from googlesearch import search  # 使用 googlesearch-python 來搜尋 Google

# 根據關鍵字搜尋並取得新聞第一個網址
def get_first_news_url(query: str) -> str:
    try:
        # 使用 googlesearch 來搜尋關鍵字
        search_results = search(query, num_results=5)  # 取得前五筆搜尋結果
        if search_results:
            return search_results[0]  # 取得第一個結果的網址
        return None
    except Exception as e:
        return f"搜尋錯誤: {e}"

# 抓取並統整新聞內容
def summarize_news(url: str) -> str:
    try:
        # 解析新聞文章
        article = Article(url)
        article.download()
        article.parse()
        article.nlp()  # 自動處理摘要

        # 回傳標題與摘要
        return f"標題: {article.title}\n摘要: {article.summary}"
    except Exception as e:
        return f"無法讀取或分析文章: {e}"

# 使用者輸入處理流程
def process_news_query(query: str) -> str:
    url = get_first_news_url(query)
    if url:
        return summarize_news(url)
    else:
        return "無法找到符合的新聞，請稍後再試。"
