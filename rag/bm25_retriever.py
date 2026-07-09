import itertools
import jieba
import bm25s
from typing import List, Optional
from llama_index.core import VectorStoreIndex
from llama_index.core.schema import BaseNode, IndexNode, QueryBundle, NodeWithScore
from llama_index.core.retrievers import BaseRetriever
from llama_index.core.callbacks.base import CallbackManager
from llama_index.core.vector_stores.utils import node_to_metadata_dict, metadata_dict_to_node


class ChineseBM25Retriever(BaseRetriever):
    """ 
    一個基於 BM25 演算法的中文檢索器，透過 BM25 方法從節點中檢索相關內容。
    """

    def __init__(
        self,
        nodes: Optional[List[BaseNode]] = None,
        similarity_top_k: int = 10,
        callback_manager: Optional[CallbackManager] = None,
        objects: Optional[List[IndexNode]] = None,
        object_map: Optional[dict] = None,
        verbose: bool = False,
    ) -> None:
        """
        初始化 BM25 檢索器。
        :param nodes: 節點列表（可選）
        :param similarity_top_k: 取回的最相似前 K 筆資料
        :param callback_manager: 回調管理器（可選）
        :param objects: 用於索引的對象列表（可選）
        :param object_map: 用於存儲對象的字典（可選）
        :param verbose: 是否啟用詳細日誌
        """
        super().__init__(
            callback_manager=callback_manager,
            object_map=object_map,
            objects=objects,
            verbose=verbose,
        )

        self.similarity_top_k = similarity_top_k
        self.stop_words = self._load_stopwords("./utils/stopwords.txt")  # ✅ 加載停用詞
        self.bm25, self.corpus = self._initialize_bm25(nodes)  # ✅ 初始化 BM25 檢索模型

    def _load_stopwords(self, filepath: str) -> set:
        """
        加載停用詞表，避免影響檢索結果。
        :param filepath: 停用詞文件的路徑
        :return: 停用詞集合
        """
        with open(filepath, encoding="utf-8") as f:
            return {line.strip() for line in f}

    def _chinese_tokenizer(self, texts: List[str]) -> List[str]:
        """
        使用 Jieba 進行中文分詞，並過濾停用詞。
        :param texts: 待處理的文本列表
        :return: 分詞後的詞語列表
        """
        return [
            word for word in itertools.chain.from_iterable(jieba.cut_for_search(text) for text in texts)
            if word not in self.stop_words
        ]

    def _initialize_bm25(self, nodes: List[BaseNode]) -> tuple[bm25s.BM25, list]:
        """
        初始化 BM25 檢索器，建立索引。
        :param nodes: 節點列表
        :return: BM25 物件與對應的文本庫
        """
        if not nodes:  # 如果 nodes 為空，返回空的 BM25 物件
            print("⚠️ 警告：BM25 初始化時發現 Qdrant 沒有數據，將返回空索引")
            return bm25s.BM25(), []
        
        corpus = [node_to_metadata_dict(node) for node in nodes]
        corpus_tokens = [self._chinese_tokenizer([node.get_content()]) for node in nodes]

        bm25 = bm25s.BM25()
        bm25.corpus = corpus
        
        if corpus_tokens:  # 確保有內容再執行 index
            bm25.index(corpus_tokens, show_progress=True)
        else:
            print("⚠️ 警告：BM25 未建立索引，因為沒有可用的文本！")
        
        return bm25, corpus

    def _retrieve(self, query_bundle: QueryBundle) -> List[NodeWithScore]:
        """
        執行 BM25 搜索，從文本庫中找出最相關的節點。
        :param query_bundle: 查詢請求包（包含用戶輸入的查詢字串）
        :return: 匹配的節點與相似度分數列表
        """
        query = query_bundle.query_str
        tokenized_query = [self._chinese_tokenizer([query])]

        # 🛑 防止 BM25 無數據時檢索報錯
        if not hasattr(self.bm25, "vocab_dict") or not self.bm25.vocab_dict:
            print("⚠️ BM25 無索引數據，返回空結果")
            return []

        # ✅ 確保 k 不會超過 corpus 長度，避免超出索引範圍
        actual_k = min(self.similarity_top_k, len(self.corpus))
        print('✅actual', actual_k)
        
        # retrieve_result = self.bm25.retrieve(
            # tokenized_query, k=self.similarity_top_k, show_progress=self._verbose
        # )
        retrieve_result = self.bm25.retrieve(
            tokenized_query, k=actual_k, show_progress=self._verbose
        )
        # if not retrieve_result or len(retrieve_result) < 2:
        if not retrieve_result :
            print("⚠️ BM25 未找到匹配結果")
            return []

        indexes, scores = retrieve_result
        actual_k = min(self.similarity_top_k, len(indexes[0]))
        print(f"🔍 BM25 檢索到 {len(indexes[0])} 筆資料，設定的 k={actual_k}")
        '''
        if not indexes or not scores:
            print("⚠️ BM25 檢索結果為空")
            return []
        '''
        indexes, scores = indexes[0], scores[0]  # 只處理單一查詢
        nodes = [
            NodeWithScore(
                node=metadata_dict_to_node(self.corpus[idx] if isinstance(idx, int) else idx),
                score=float(score),
            )
            for idx, score in zip(indexes, scores)
        ]
        return nodes


if __name__ == "__main__":
    """
    主程式，負責初始化模型、檢索器，並進行文本檢索與重排序。
    """
    from llama_index.embeddings.ollama import OllamaEmbedding
    # LLM 相關庫
    from llama_index.llms.ollama import Ollama
    from openai import OpenAI
    from anthropic import Anthropic

    # Qdrant 相關庫
    # import qdrant_client
    # from qdrant_client.http.exceptions import UnexpectedResponse
    import sys
    import os
    sys.path.insert(0, './rag')  # 設定容器路徑，方便導入其他檔案

    from qdrant_retriever import *
    from bm25_retriever import *
    # 嵌入模型
    from llama_index.embeddings.ollama import OllamaEmbedding

    # Streamlit 相關庫
    import streamlit as st

    # 系統工具庫
    import shutil
    import os

    # 自定義庫
    from llama_index.postprocessor.flag_embedding_reranker import FlagEmbeddingReranker

    from qdrant_client import QdrantClient
    import qdrant_client
    # ✅ 初始化嵌入模型
    embed_model = OllamaEmbedding(
        model_name="chatfire/bge-m3:q8_0",
        base_url="http://localhost:11434",
        ollama_additional_kwargs={"mirostat": 0}
    )

    # ✅ 連接 Qdrant 向量資料庫
    client = qdrant_client.QdrantClient(url="http://localhost:6333")
    
    # ✅ 加載向量存儲
    vector_store = QdrantVectorStore(client=client, collection_name="20250121_ly_256")
    index = VectorStoreIndex.from_vector_store(embed_model=embed_model, vector_store=vector_store)

    # ✅ 初始化重排序器
    reranker = FlagEmbeddingReranker(
        top_n=5,
        model="BAAI/bge-reranker-large",
    )

    # ✅ 設置 LLM 參數
    llm = OpenAI(
        base_url='https://medusa-poc.genai.nchc.org.tw/v1',
        api_key='sk-DEPQ9SbU_AwW8zZTD13EHQ',  # 必須提供但不會實際使用
    )

    # ✅ 初始化向量檢索器
    vector_retriever = index.as_retriever(
        retriever_mode='embeddings',
        similarity_top_k=20,
        verbose=True
    )

    # ✅ 初始化 BM25 檢索器
    bm25_retriever = ChineseBM25Retriever(
        nodes=index.vector_store.get_nodes(),
        similarity_top_k=20
    )

    # ✅ 設定查詢內容
    user_message = "大巨蛋"

    # ✅ 執行向量檢索
    vector_nodes = vector_retriever.retrieve(user_message)

    # ✅ 執行 BM25 檢索
    bm25_nodes = bm25_retriever.retrieve(user_message)

    # ✅ 合併兩種檢索結果並去重
    merge_nodes = vector_nodes + bm25_nodes
    unique_nodes = {}
    for doc in merge_nodes:
        doc_id = doc.id_  # 使用 `id_` 作為唯一識別碼
        if doc_id not in unique_nodes:
            unique_nodes[doc_id] = doc

    # ✅ 最終去重後的節點
    final_nodes = list(unique_nodes.values())

    # ✅ 進行 reranker 排序
    query_bundle = QueryBundle(query_str=user_message)
    ranked_nodes = reranker._postprocess_nodes(final_nodes, query_bundle=query_bundle)

    # ✅ 輸出結果
    for i in range(len(ranked_nodes)):
        print(f"Score: {ranked_nodes[i].score:.2f}")
        print(f"Text: {ranked_nodes[i].text[:100]}\n")

    print(ranked_nodes[0].node.excluded_embed_metadata_keys[0])
