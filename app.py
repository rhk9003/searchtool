import google.generativeai as genai
import requests
import json
import time

# 設定你的 API Keys
GOOGLE_SEARCH_API_KEY = "YOUR_SEARCH_API_KEY"
SEARCH_ENGINE_ID = "YOUR_SEARCH_ENGINE_ID" # cx value
GENAI_API_KEY = "YOUR_GEMINI_API_KEY"

genai.configure(api_key=GENAI_API_KEY)

# 初始化模型：使用 gemini-2.5-flash 以求速度與成本效益
model = genai.GenerativeModel('gemini-2.5-flash')

def search_google(query, num_results=5):
    """
    呼叫 Google Custom Search API 獲取前 N 筆搜尋結果
    """
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': GOOGLE_SEARCH_API_KEY,
        'cx': SEARCH_ENGINE_ID,
        'q': query,
        'num': num_results
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        results = response.json().get('items', [])
        
        # 簡化資料結構，只保留 AI 判斷需要的欄位，節省 Token
        simplified_results = [
            {"title": item.get("title"), "link": item.get("link"), "snippet": item.get("snippet")}
            for item in results
        ]
        return simplified_results
    except Exception as e:
        print(f"Search Error: {e}")
        return []

def identify_official_url(product_name, search_results):
    """
    將搜尋結果丟給 Gemini 進行邏輯判斷
    """
    if not search_results:
        return "無搜尋結果", "N/A"

    prompt = f"""
    任務：你是專業的電商數據分析師。請從以下搜尋結果中，為商品「{product_name}」找出最佳的連結。
    
    搜尋結果清單 (JSON 格式):
    {json.dumps(search_results, ensure_ascii=False)}
    
    判斷邏輯優先級（由高到低）：
    1. **官方網站的商品頁面** (Official Brand Product Page)。
    2. **官方網站的首頁** (若找不到具體商品頁)。
    3. **大型可信電商平台** (如 momo, PChome, 屈臣氏等) 的商品頁。
    4. 若以上皆非，回傳 "Not Found"。

    請嚴格依照以下 JSON 格式輸出，不要包含其他文字：
    {{
        "selected_url": "網址",
        "source_type": "官網/電商/其他",
        "reasoning": "簡短理由"
    }}
    """

    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        return {"selected_url": "Error", "reasoning": str(e)}

# --- 模擬批次執行 ---
keywords = [
    "大研生醫 葉黃素 官網",
    "Suntory 芝麻明EX 價格",
    "娘家 大紅麴 哪裡買"
]

results_table = []

for kw in keywords:
    print(f"正在處理：{kw}...")
    # 1. 搜尋
    search_data = search_google(kw)
    
    # 2. AI 判斷 (提取商品名稱做為 Context，這裡簡單用關鍵字本身)
    ai_judgment = identify_official_url(kw, search_data)
    
    results_table.append({
        "Keyword": kw,
        "URL": ai_judgment.get("selected_url"),
        "Type": ai_judgment.get("source_type"),
        "Reason": ai_judgment.get("reasoning")
    })
    
    # 避免觸發 Search API Rate Limit
    time.sleep(1)

# 輸出結果
print(json.dumps(results_table, indent=2, ensure_ascii=False))
