# LLM 相關庫
from llama_index.llms.ollama import Ollama
from openai import OpenAI

# 系統工具庫
import shutil
import os


# 時間
import time

    #---------------------------------------------------------------------
    # 處理Qd & llm連線
class ModelHandler:
    # ========================================
    # ✅ 1. 初始化基本變數
    # ========================================
    def __init__(
        self,
        temp:float,
        api_key, 
        llm_model_name,  # 範例格式 ['llmam3.3']
        openai_base_url,
        
        ) :
        """
        初始化 ModelHandler 類，設置 LLM 模型、Qdrant 向量集合、reranker 及其他參數。
        :param Qdrant_vector_collection_name: Qdrant 向量集合名稱
        :param temp: 模型的溫度參數
        :param api_key: 用於 OpenAI 或 Claude 的 API 密鑰
        :param embed_model_name: 預設嵌入模型名稱
        :param reranker_model: Reranker 模型名稱
        """
        
        self.llm_model_name = llm_model_name
        self.temp = temp
        self.api_key = api_key
        self.openai_base_url = openai_base_url

    # ========================================
    # ✅ 2. LLM 初始化
    # ========================================
    def initialize_llm_openai(self, api_key='sk-SpAIVtz3qqbTXoBOJ-7O9A'):
        """
        初始化 OpenAI 模型。
        :return: llm -> OpenAI 物件
        """
        llm = OpenAI(
            base_url=self.openai_base_url,
            api_key=api_key
            )
        return llm


    # ========================================
    # ✅ 5. 問 OpenAI 的問題
    # ========================================
    def ask_openai(self, llm, question, stream=True):
        """
        使用已初始化的 OpenAI LLM 來問問題
        :param question: 使用者的問題 (str)
        :return: OpenAI 回應的內容 (str)
        """
        try:
            # 測試llm時間用
            llm_start_time = time.time()
            
            response_stream = llm.chat.completions.create(
                model=self.llm_model_name[0],
                messages=question,
                temperature=self.temp,
                stream=stream,
            )
            
            print(f"🔹 LLM 時間: {time.time() - llm_start_time:.2f} 秒")
            print(response_stream)
            return response_stream

        except Exception as e:
            print(f"❌ OpenAI 回應錯誤: {e}")
            return "發生錯誤，請稍後再試"
            

if __name__ == "__main__":
    # 設定相關參數
    QDRANT_COLLECTION_NAME = "20250121_ly_256"
    TEMPERATURE = 0.7
    API_KEY = ""  # 如果使用 OpenAI 或 Claude，請提供 API Key
    MODEL_NAME = "chatfire/bge-m3:q8_0"
    RERANKER_MODEL = "BAAI/bge-reranker-large"
    RERANKER_TOP_N = 5
    SIMILARITY_TOP_K = 10

    # 初始化 ModelHandler
    model_handler = ModelHandler(
        Qdrant_vector_collection_name=QDRANT_COLLECTION_NAME,
        temp=TEMPERATURE,
        api_key=API_KEY,
        model_name=MODEL_NAME,
        reranker_model=RERANKER_MODEL,
        reranker_top=RERANKER_TOP_N,
        similarity_top_k=SIMILARITY_TOP_K,
        llm_model_name='llama3.3:latest'
    )

    # 初始化 LLM


    # 初始化檢索引擎
    retriever_engine = model_handler.initialize_retriever_core()
    print("✅ 向量檢索引擎初始化完成")

    bm25_retriever = model_handler.initialize_bm25retriever_core()
    print("✅ BM25 檢索引擎初始化完成")

    # 測試提問與回答
    query = "請問量子計算與傳統計算的區別是什麼？"
    print(f"🔍 測試問題: {query}")

    # 釋放資源
    model_handler.release_resources()
    print("✅ 資源釋放完成")