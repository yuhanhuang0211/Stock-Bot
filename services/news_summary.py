import os
import requests
from newspaper import Article, Config as NewspaperConfig
from googlesearch import search as Google_Search_func
import google.generativeai as genai # 用於 Gemini 摘要
from dotenv import load_dotenv
import logging

# --- 基本設定 ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(module)s - %(funcName)s - %(message)s')

load_dotenv()

try:
    gemini_api_key = os.getenv("GEMINI_API_KEY")
    if not gemini_api_key:
        logging.warning("GEMINI_API_KEY not found in .env file. News summarization via Gemini will fail.")
    else:
        genai.configure(api_key=gemini_api_key)
except Exception as e:
    logging.error(f"Error configuring Gemini for news summary: {e}")

# --- 輔助函式 (Gemini 摘要) ---
# 注意：此函式理想情況下應從共享的 gemini_service.py 匯入
def summarize_text_with_gemini(title: str, text_content: str, query_context: str = "") -> str:
    """
    使用 Gemini API 對提供的文本內容進行摘要。
    參數:
        title (str): 文章標題。
        text_content (str): 文章完整內容。
        query_context (str): 使用者原始的查詢關鍵字，提供上下文。
    回傳:
        str: Gemini 生成的摘要，或錯誤訊息。
    """
    if not gemini_api_key:
        logging.error("Gemini API key not configured. Cannot summarize text.")
        return "錯誤：AI 摘要服務未設定。"

    # 移除過多的空白和換行，以優化 token 使用
    text_content_cleaned = "\n".join([line.strip() for line in text_content.splitlines() if line.strip()])
    
    # 限制內容長度以避免超出 Gemini 的 token 限制 (gemini-pro 通常有 32k token 限制)
    # 一個中文字符約等於 2-3 token，保守估計，例如限制 8000 字
    max_chars = 8000
    if len(text_content_cleaned) > max_chars:
        text_content_cleaned = text_content_cleaned[:max_chars]
        logging.warning(f"News content for title '{title}' was truncated to {max_chars} characters for Gemini summary.")

    if not text_content_cleaned.strip():
        logging.warning(f"No text content to summarize for title '{title}'.")
        return "錯誤：文章內容為空，無法摘要。"

    try:
        model = genai.GenerativeModel('gemini-pro')
        prompt = f"""
        請你扮演一個專業的新聞編輯。
        這是使用者原始的查詢意圖：「{query_context}」。
        以下是一則新聞：
        標題：{title}
        內容：
        {text_content_cleaned}

        請根據以上新聞內容，針對使用者的查詢意圖，提供一段約 150-250 字的中文摘要。
        摘要應當客觀、準確地反映新聞的核心資訊。
        如果內容不相關或無法有效摘要，請說明原因。
        """
        
        response = model.generate_content(prompt)
        summary = response.text.strip()
        
        # 有時 Gemini 可能會回傳無法摘要的訊息，這也是一種有效的「摘要」
        # 例如 "根據提供的內容，無法有效摘要..."
        if not summary:
            return "錯誤：AI 未能生成摘要。"
        return summary
        
    except Exception as e:
        logging.error(f"Gemini API 錯誤 (summarize_text_with_gemini for title '{title}'): {e}")
        # 檢查是否有 parts 且包含 'text' (來自 response.parts)
        # 有時錯誤物件可能包含部分 Gemini 的回應
        try:
            # response.prompt_feedback 會有 BLOCKED 的情況
            if response and response.prompt_feedback and str(response.prompt_feedback.block_reason) != "BLOCK_REASON_UNSPECIFIED":
                 logging.error(f"Gemini content blocked: {response.prompt_feedback.block_reason}")
                 return f"無法生成摘要：內容可能違反使用政策 ({response.prompt_feedback.block_reason})。"
        except AttributeError: # response 物件可能沒有 prompt_feedback
            pass
        return f"錯誤：AI 摘要時發生問題 ({type(e).__name__})。"

# --- 核心新聞處理函式 ---
def get_first_news_url_from_google(query: str, lang: str = "zh-TW") -> str | None:
    """
    使用 googlesearch-python 根據關鍵字搜尋 Google 並取得第一個看起來是新聞的網址。
    參數:
        query (str): 搜尋關鍵字。
        lang (str): 搜尋語言，預設為 'zh-TW'。
    回傳:
        str: 第一個新聞網址，或 None (若找不到或發生錯誤)。
    """
    try:
        # 增加 user_agent 可能有助於減少被阻擋的機率，但 googlesearch-python 可能內部已處理
        # 查詢時加入 "新聞" 或 "news" 字眼，並限定搜尋結果數量
        # tbs=nrt:8 (新聞類別)， qdr:d (過去一天) 或 qdr:w (過去一週) 可以增加時效性
        # 不過 googlesearch-python 可能不直接支援 tbs 參數，這通常是在 URL 中
        # 這裡的 'query' 參數是給 Google Search 的，不是給新聞網站的
        
        logging.info(f"開始搜尋新聞，關鍵字: '{query}', 語言: {lang}")
        # num_results 設為少量，例如 3-5，然後從中挑選
        # pause 參數可以減緩請求速率，避免被 Google 短期封鎖
        search_results_iterator = Google_Search_func(
            f"{query} site:news.google.com OR news", # 嘗試引導到新聞源，或在查詢中加入 "news"
            num=5,
            lang=lang,
            pause=2.0 # 每次請求間隔2秒
        )
        
        search_results = list(search_results_iterator) # 將迭代器轉為列表

        if search_results:
            # 可以加入一些簡單的 URL 過濾邏輯，例如排除社交媒體或影片網站
            # 但這會增加複雜性。目前直接取第一個。
            first_url = search_results[0]
            logging.info(f"找到第一個搜尋結果 URL: {first_url}")
            return first_url
        else:
            logging.warning(f"關鍵字 '{query}' 查無 Google 搜尋結果。")
            return None
            
    except requests.exceptions.HTTPError as e: # googlesearch-python 底層用 requests
        if e.response.status_code == 429:
            logging.error(f"Google 搜尋請求過於頻繁 (429 Client Error). Query: '{query}'. {e}")
            return "搜尋請求過於頻繁，請稍後再試。" # 特殊錯誤碼回傳給上層處理
        logging.error(f"Google 搜尋時發生 HTTP 錯誤. Query: '{query}'. {e}")
        return None
    except Exception as e:
        # 需要注意，如果 googlesearch-python 因 IP 被封鎖拋出特定例外，應在此處捕捉
        logging.error(f"Google 搜尋時發生未知錯誤. Query: '{query}'. Error: {e} ({type(e).__name__})")
        return None


def extract_and_summarize_news_article(url: str, user_query: str) -> str:
    """
    抓取指定 URL 的新聞文章內容，並使用 Gemini 進行摘要。
    參數:
        url (str): 新聞文章的 URL。
        user_query (str): 使用者原始的查詢關鍵字，用於摘要上下文。
    回傳:
        str: 包含標題和 Gemini 摘要的字串，或錯誤訊息。
    """
    if not url or not url.startswith(('http://', 'https://')):
        logging.error(f"提供的 URL 無效: {url}")
        return "錯誤：提供的網址無效。"

    try:
        # 設定 newspaper Article 的組態
        config = NewspaperConfig()
        config.browser_user_agent = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
        config.request_timeout = 15  # seconds for download
        config.memoize_articles = False # 禁用快取，確保每次都重新下載
        config.fetch_images = False # 不需要圖片
        # config.language = 'zh' # 如果確定是中文新聞，可以指定

        article = Article(url, config=config)
        
        logging.info(f"開始下載文章: {url}")
        article.download()
        
        logging.info(f"開始解析文章: {url}")
        article.parse()

        if not article.title or not article.text:
            logging.warning(f"無法從 {url} 提取到標題或內容。Title: '{article.title}', Text length: {len(article.text)}")
            return f"錯誤：無法從指定網址提取有效的文章內容。可能是網頁結構不支援或內容為空。"

        logging.info(f"文章提取成功: '{article.title}'，準備進行 Gemini 摘要。")
        
        # 使用 Gemini 進行摘要
        gemini_summary = summarize_text_with_gemini(article.title, article.text, user_query)
        
        # 組合最終回傳結果
        # 如果 Gemini 摘要本身就是一個錯誤訊息，直接回傳
        if gemini_summary.startswith("錯誤："):
            return f"標題：{article.title}\n{gemini_summary}"
        else:
            return f"標題：{article.title}\n摘要：\n{gemini_summary}\n\n來源：{url}"

    except Exception as e:
        logging.error(f"處理文章 {url} 時發生錯誤: {e} ({type(e).__name__})")
        # article.download() 或 article.parse() 可能會拋出各種錯誤
        return f"錯誤：讀取或分析文章失敗 ({type(e).__name__})。\n網址：{url}"

# --- 主要處理流程函式 ---
def process_news_query_and_get_summary(user_query: str) -> str:
    """
    處理使用者的新聞查詢：搜尋 -> 提取 -> Gemini 摘要。
    參數:
        user_query (str): 使用者的查詢關鍵字句。
    回傳:
        str: 新聞摘要結果或錯誤/提示訊息。
    """
    logging.info(f"接收到新聞查詢: '{user_query}'")
    
    # 1. 取得新聞 URL
    news_url = get_first_news_url_from_google(user_query)

    if news_url is None:
        return "抱歉，目前無法找到與「{user_query}」相關的新聞，請檢查關鍵字或稍後再試。"
    if news_url == "搜尋請求過於頻繁，請稍後再試。": # 特殊錯誤訊息
        return news_url

    # 2. 提取並摘要新聞
    summary_result = extract_and_summarize_news_article(news_url, user_query)
    
    return summary_result

# --- 主函式 (用於直接執行此檔案進行測試) ---
if __name__ == "__main__":
    logging.info("開始測試 news_summary.py...")

    # 設定測試用的 API Key (如果 .env 中沒有或想覆寫)
    # os.environ["GEMINI_API_KEY"] = "YOUR_GEMINI_API_KEY_HERE_FOR_TESTING"
    # genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

    if not gemini_api_key:
        print("警告: Gemini API Key 未設定，部分測試可能無法完整執行或會回傳錯誤。")
        print("請在 .env 檔案中設定 GEMINI_API_KEY，或在測試程式碼中臨時設定。")

    test_queries = [
        "台積電股價",
        "聯發科最新AI晶片發布",
        "長榮海運股東會",
        "一個不存在的奇異關鍵詞看看會發生什麼事" # 測試找不到新聞的情況
    ]

    for query in test_queries:
        print(f"\n--- 測試查詢: '{query}' ---")
        result = process_news_query_and_get_summary(query)
        print(result)
        print("--------------------------------------")
    
    # 測試特定 URL (假設有此新聞)
    # print("\n--- 測試特定 URL ---")
    # test_url = "https://udn.com/news/story/7238/7937680" # 請替換為一個有效的、不太會變動的新聞URL作測試
    # if gemini_api_key(): # 只有在 API Key 設定時才執行，因為會用到 Gemini
    #     url_summary = extract_and_summarize_news_article(test_url, "測試特定URL")
    #     print(url_summary)
    # else:
    #     print(f"跳過特定 URL 測試 ({test_url})，因為 Gemini API Key 未設定。")
    # print("--------------------------------------")

    # 測試無效URL
    print("\n--- 測試無效 URL ---")
    invalid_url_summary = extract_and_summarize_news_article("htp://not_a_valid_url.com/story", "測試無效URL")
    print(invalid_url_summary)
    print("--------------------------------------")
    
    logging.info("news_summary.py 測試結束。")
