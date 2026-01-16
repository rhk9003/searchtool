import streamlit as st
import google.generativeai as genai
import requests
import json
import pandas as pd
import time

# --- 1. 頁面配置 ---
st.set_page_config(
    page_title="AI 智能網址捕手",
    page_icon="🕸️",
    layout="wide"
)

# --- 2. 核心功能函式 ---

def search_google(query, search_api_key, cx_id, num_results=5):
    """
    呼叫 Google Custom Search API
    """
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        'key': search_api_key,
        'cx': cx_id,
        'q': query,
        'num': num_results
    }
    try:
        response = requests.get(url, params=params)
        response.raise_for_status() # 檢查 HTTP 錯誤
        results = response.json().get('items', [])
        
        # 精簡資料以節省 Token
        simplified = [
            {"title": item.get("title"), "link": item.get("link"), "snippet": item.get("snippet")}
            for item in results
        ]
        return simplified
    except Exception as e:
        st.error(f"搜尋錯誤 ({query}): {e}")
        return []

def identify_official_url(product_name, search_results, model):
    """
    使用 Gemini 判斷最佳網址
    """
    # [CRITICAL FIX] 修正之前的 AttributeError
    # 當沒有搜尋結果時，必須回傳字典 (Dictionary)，而非 Tuple
    if not search_results:
        return {
            "selected_url": "",
            "source_type": "Not Found",
            "reasoning": "Google Search 未回傳任何結果 (可能無關聯或 API 配額耗盡)"
        }

    prompt = f"""
    任務：你是專業的電商數據分析師。請從以下搜尋結果中，為商品「{product_name}」找出最佳的連結。
    
    搜尋結果清單:
    {json.dumps(search_results, ensure_ascii=False)}
    
    判斷邏輯優先級（由高到低）：
    1. **官方網站的商品頁面** (Official Brand Product Page)。
    2. **官方網站的首頁** (若找不到具體商品頁)。
    3. **大型可信電商平台** (如 momo, PChome, 屈臣氏, 蝦皮商城) 的商品頁。
    4. 若以上皆非，或連結看似內容農場/無效，回傳 "Not Found"。

    請嚴格輸出純 JSON 格式：
    {{
        "selected_url": "網址 (若無則留空)",
        "source_type": "官網 / 電商平台 / 其他",
        "reasoning": "簡短判斷理由 (繁體中文)"
    }}
    """

    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        return {
            "selected_url": "", 
            "source_type": "Error", 
            "reasoning": f"AI 解析錯誤: {str(e)}"
        }

# --- 3. Streamlit UI 介面 ---

st.title("🕸️ AI 智能網址捕手 (Auto-URL Finder)")
st.markdown("""
此工具結合 **Google Search** 與 **Gemini AI**，自動判斷並抓取商品的「官方網站」或「主要銷售頁面」。
""")

# --- 側邊欄：設定 ---
with st.sidebar:
    st.header("🔧 API 設定")
    
    # 優先嘗試從 st.secrets 讀取，如果沒有則讓使用者輸入
    default_gemini_key = st.secrets.get("GEMINI_API_KEY", "")
    default_search_key = st.secrets.get("GOOGLE_SEARCH_API_KEY", "")
    default_cx_id = st.secrets.get("GOOGLE_SEARCH_CX", "")

    gemini_key = st.text_input("Gemini API Key", value=default_gemini_key, type="password")
    search_key = st.text_input("Google Search API Key", value=default_search_key, type="password")
    cx_id = st.text_input("Search Engine ID (CX)", value=default_cx_id, type="password")
    
    st.info("💡 建議使用 `gemini-2.5-flash` 以獲得最佳速度與成本效益。")

# --- 主畫面：輸入資料 ---
col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("1. 輸入關鍵字清單")
    input_method = st.radio("選擇輸入方式", ["直接貼上文字", "上傳 CSV 檔案"])
    
    keywords = []
    
    if input_method == "直接貼上文字":
        raw_text = st.text_area("請輸入關鍵字 (一行一個)", height=200, 
                               placeholder="大研生醫 葉黃素 官網\nSuntory 芝麻明EX\nNike Air Force 1 官網")
        if raw_text:
            keywords = [line.strip() for line in raw_text.split('\n') if line.strip()]
            
    elif input_method == "上傳 CSV 檔案":
        uploaded_file = st.file_uploader("上傳 CSV (需包含 'keyword' 欄位)", type=["csv"])
        if uploaded_file:
            df_upload = pd.read_csv(uploaded_file)
            if 'keyword' in df_upload.columns:
                keywords = df_upload['keyword'].tolist()
            else:
                st.error("CSV 檔案中找不到 'keyword' 欄位，請檢查標題。")

with col2:
    st.subheader("2. 執行狀態")
    if not keywords:
        st.info("👈 請先在左側輸入關鍵字")
    else:
        st.write(f"已載入 **{len(keywords)}** 筆關鍵字。")
        start_btn = st.button("🚀 開始自動抓取", type="primary")

# --- 執行邏輯 ---
if keywords and 'start_btn' in locals() and start_btn:
    if not (gemini_key and search_key and cx_id):
        st.error("❌ 請先在側邊欄填寫完整的 API Key 資訊！")
    else:
        # 初始化模型
        genai.configure(api_key=gemini_key)
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        results_data = []
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        # 建立一個容器來即時顯示結果
        result_container = st.container()

        for i, kw in enumerate(keywords):
            status_text.text(f"正在處理 ({i+1}/{len(keywords)}): {kw} ...")
            
            # Step 1: Search
            search_res = search_google(kw, search_key, cx_id)
            
            # Step 2: AI Reason
            ai_res = identify_official_url(kw, search_res, model)
            
            # 整合結果
            row = {
                "關鍵字": kw,
                "網址": ai_res.get("selected_url", ""),
                "類型": ai_res.get("source_type", "N/A"),
                "判斷理由": ai_res.get("reasoning", "")
            }
            results_data.append(row)
            
            # 更新進度條
            progress_bar.progress((i + 1) / len(keywords))
            
            # 避免觸發 API Rate Limit (建議至少停 0.5~1秒)
            time.sleep(1) 

        status_text.text("✅ 處理完成！")
        
        # 顯示結果
        df_results = pd.DataFrame(results_data)
        st.success("抓取完成！結果如下：")
        st.dataframe(df_results, use_container_width=True)
        
        # 下載按鈕
        csv = df_results.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            label="📥 下載 Excel/CSV 結果",
            data=csv,
            file_name='url_search_results.csv',
            mime='text/csv',
        )
