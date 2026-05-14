import sys
import os
sys.path.append(os.path.join(os.getcwd(), 'prompt'))

from prompt_formatter import PromptFormatter
from llama_index.core.schema import BaseNode, IndexNode, QueryBundle, NodeWithScore

class RetrieverHandler:
    def __init__(self, reranker, retrievers_with_weights: dict, reranker_top: int, prompt_formatter=None):
        """
        初始化檢索處理類別，支援多個檢索器與對應的權重。
        :param retrievers_with_weights: 包含檢索器名稱、物件與權重的字典，例如：
                {
                    "vector_retriever": (vector_retriever, 1.0),
                    "bm25_retriever": (bm25_retriever, 0.8)
                }
        :param reranker_top: 返回的 top K 檢索結果
        """
        self.retrievers = {}  # 存放檢索器
        self.weights = {}  # 存放檢索器的權重
        self.reranker_top = reranker_top
        self.reranker = reranker

        # 如果沒有提供 prompt_formatter，則預設使用 PromptFormatter
        self.prompt_formatter = prompt_formatter if prompt_formatter else PromptFormatter()
        
        # 初始化檢索器與對應權重
        self.initialize_retrievers(retrievers_with_weights)
    
    def initialize_retrievers(self, retrievers_with_weights: dict):
        """
        初始化並儲存檢索器及其權重。
        :param retrievers_with_weights: 檢索器與對應權重的字典
        """
        print('✅ 初始化檢索器與對應權重', retrievers_with_weights)
        for name, (retriever, weight) in retrievers_with_weights.items():
            self.retrievers[name] = retriever
            self.weights[name] = weight  # 儲存權重

    def display_retrieve_res(self, retrieve_res):
        """
        顯示 Qdrant 檢索結果的詳細資訊。
        :param retrieve_res: 檢索結果列表
        """
        print("\n📌 **Qdrant 檢索的原始數據**:")
        for idx, item in enumerate(retrieve_res):
            print(f"\n🔹 **結果 {idx+1}:**")
            print(f"🔍 item.node 屬性: {dir(item.node)}")

            if hasattr(item.node, "id_"):
                print(f"🔸 ID: {item.node.id_}")  
            elif hasattr(item.node, "doc_id"):
                print(f"🔸 ID: {item.node.doc_id}")
            else:
                print("⚠️ 無法找到向量 ID")

            print(f"🔸 Score: {item.score}")  
            print(f"🔸 Metadata: {item.node.metadata}")  
            print(f"🔸 Text: {item.node.text[:300]}...")  

    def _process_retrieve_file(self, retrieve_res):
        """
        從檢索結果中提取檔案資訊
        :param retrieve_res: 檢索結果列表
        :return: 檔案來源資訊
        """
        if not retrieve_res:
            return '尚未上傳文件'
        
        top_k = min(self.reranker_top, len(retrieve_res))  # 避免索引超過範圍
                
        retrieve_file = ''
        # for i in range(1, self.reranker_top):
        for i in range(1, top_k + 1):
            f = retrieve_res[i - 1].node.metadata
            try:
                retrieve_file = '回答出自此篇檔案 : ' + f['file']
            except KeyError:
                retrieve_file = '尚未上傳檔案'

        return retrieve_file

    def print_ranked_nodes(self, ranked_nodes) : 
        # ✅ 輸出結果
        print('print ranked nodes ✅ 輸出結果')
        for i in range(len(ranked_nodes)):
            
            print(f"Score: {ranked_nodes[i].score:.2f}")
            print(f"Text: {ranked_nodes[i].text[:100]}\n")

        if not ranked_nodes:  # 🛑 防止空值
            print("⚠️ 沒有檢索到任何結果，返回空列表")
            return []

        print('ranked_nodes NO.1', ranked_nodes[0].node.excluded_embed_metadata_keys[0])

    def retrieve_res_processing(self, prompt):
        """
        根據 prompt 執行檢索，並格式化結果。
        :param prompt: 使用者的查詢
        :return: 格式化後的問題字串與檢索文件來源
        """
        retrieve_res = []
        unique_docs = {}
        for name, retriever in self.retrievers.items():
            print(f"🔍 使用 {name} 檢索器 (權重: {self.weights[name]})...")
            res = retriever.retrieve(prompt)  # 執行檢索
            
            # ✅ 調整分數權重並去重
            for item in res:
                # 根據權重調整分數
                item.score *= self.weights[name]
                
                # 使用 doc_id 來去除重複項目
                if item.id_ not in unique_docs:
                    unique_docs[item.id_] = item

        # 將去重後的結果轉換為列表
        final_nodes = list(unique_docs.values())
        
        # ✅ 進行 reranker 排序
        query_bundle = QueryBundle(query_str=prompt)
        
        ranked_nodes = self.reranker._postprocess_nodes(final_nodes, query_bundle=query_bundle)
        
        self.print_ranked_nodes(ranked_nodes)

        # 顯示檢索結果
        # self.display_retrieve_res(retrieve_res)
        
        return ranked_nodes
        
        # context_str, retrieve_file = self._process_retrieve_results(retrieve_res)

        # return context_str, retrieve_file

    def _process_retrieve_results(self, retrieve_res):
        """
        處理檢索結果，提取 context_str 與 retrieve_file。
        :param retrieve_res: 檢索結果列表
        :return: (context_str, retrieve_file)
        """
        try:
            context_str = retrieve_res[0].node.excluded_embed_metadata_keys[0] if retrieve_res else "No relevant context found."
        except Exception as e:
            print(f"Failed to extract context_str: {e}")
            context_str = "No relevant context found."
        
        try:
            retrieve_file = retrieve_res[0].metadata.get('file')
        except Exception as e:
            print(f"Failed name to extract retrieve_file: {e}")
            retrieve_file = "No relevant retrieve_file found."
            
        # 這是舊的找file_name的方式
        # retrieve_file = self._process_retrieve_file(retrieve_res)
        
        return context_str, retrieve_file

    def format_retrieved_result(self, prompt, prompt_style="basic", return_nodes=False):
        """
        依據檢索結果格式化最終輸出
        :param prompt: 使用者查詢問題
        :return: 格式化後的問題字串
        """
        ranked_nodes = self.retrieve_res_processing(prompt)
        
        # 呼叫新的函數來處理檢索結果
        context_str, retrieve_file = self._process_retrieve_results(ranked_nodes)
        
        # context_str, retrieve_file = self.retrieve_res_processing(prompt)
        ques_str = self.prompt_formatter.format_prompt(context_str, prompt, prompt_style)

        if return_nodes :
            return ques_str, retrieve_file, ranked_nodes
        else:
            return ques_str, retrieve_file

        #return ques_str, retrieve_file
        
        
if __name__ == "__main__":
    """
    這段程式碼用於執行檢索處理並格式化輸出。
    以下是如何執行此功能的步驟：

    使用範例：

    1. 初始化 RetrieverHandler：
       假設 retriever_engine 是一個已經初始化的檢索引擎（例如 ModelHandler 中的檢索引擎），
       reranker_top 設置為返回的最相關檢索結果數量。

       retriever_handler = RetrieverHandler(retriever_engine, reranker_top=5)

    2. 執行檢索並格式化結果：
       使用 retrieve_res_processing 方法來處理查詢的檢索結果，
       並提取所需的上下文與文件來源：

       context_str, retrieve_file = retriever_handler.retrieve_res_processing(prompt)

    3. 格式化最終輸出：
       使用 format_retrieved_result 方法將檢索結果與查詢問題格式化為最終問題字串：

       formatted_question, retrieve_file = retriever_handler.format_retrieved_result(prompt)
    """

    # 載入必要的模組
    sys.path.append(os.path.join(os.getcwd(), 'rag'))
    from llama_index.postprocessor.flag_embedding_reranker import FlagEmbeddingReranker
    from qdrant_retriever import QdrantManager
    from retriever_handler import RetrieverHandler

    # 範例查詢
    prompt = "請問今天的天氣如何？"
    
    # 設置返回前 3 條最相關的檢索結果
    reranker_top = 3  

    # 假設已初始化的檢索引擎
    reranker_model = "BAAI/bge-reranker-large"
    
    # 初始化 QdrantManager
    qdrant_manager = QdrantManager()  
    
    # 設定集合名稱（根據需要調整）
    collection_name = '20250121_ly_256'
    
    # 初始化 FlagEmbeddingReranker，設定返回的最相關結果數量
    reranker = FlagEmbeddingReranker(top_n=reranker_top, model=reranker_model)
    
    # 取得 embed 模型設置
    embed_model = qdrant_manager.embed_model_settings()
    
    # 初始化 Qdrant 向量檢索索引
    index = qdrant_manager.qdrant_vector(embed_model, collection_name=collection_name)
    
    # 初始化 retriever_engine，設置檢索模式為嵌入式模式，並指定相關設置
    retriever_engine = index.as_retriever(
        retriever_mode='embeddings',  # 使用嵌入式檢索模式
        similarity_top_k=reranker_top,  # 設定返回的最相關結果數量
        node_postprocessors=[reranker] if reranker else [],  # 設定後處理器（如有）
        verbose=True  # 顯示詳細日誌
    )

    # 初始化 RetrieverHandler
    retriever_handler = RetrieverHandler(retriever_engine, reranker_top)
    
    # 執行檢索並取得格式化結果
    formatted_question, retrieve_file = retriever_handler.format_retrieved_result(prompt)
    
    # 顯示格式化後的問題字串與檢索文件來源
    print(f"格式化後的問題字串: {formatted_question}")
    print(f"檢索文件來源: {retrieve_file}")
