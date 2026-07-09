import time
import shutil
import subprocess
import time
import shutil
import subprocess
from qdrant_client import QdrantClient
from llama_index.vector_stores.qdrant import QdrantVectorStore
from qdrant_client.http.exceptions import UnexpectedResponse
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.embeddings.ollama import OllamaEmbedding
from llama_index.core.node_parser import SentenceSplitter

class QdrantManager :
    # def __init__(self, embed_model_name='chatfire/bge-m3:q8_0') :
    def __init__(self, embed_model_name='bge-m3') :
        """
        ***********************************************************
        *  注意, init判斷機制是是否有docker指令, 若無安裝docker會出問題  *
        ***********************************************************
        
        初始化 QdrantManager 並連接到指定的 Qdrant 伺服器。
        """
        # 儲存 URL 配置
        if self.is_docker_environment() :
            self.url = "http://localhost:6333"
            self.base_url = "http://localhost:11434"
        else:
            self.url = "http://qdrant:6333"
            self.base_url = "http://ollama:11434"
        print(f"Using URL: {self.url}")

        self.client = QdrantClient(url=self.url)
        self.embed_model_name = embed_model_name
        self.embed_model = self.embed_model_settings()
        
    def check_collection_exists(self, collection_name) :
        """
        判斷特定 Qdrant 集合是否存在。
        :param collection_name: 集合名稱
        :return True 表示集合存在，False 表示集合不存在
        """
        return self.client.collection_exists(collection_name=collection_name)

    def collection_name_exists(self, collection_name, chat_id) :
        '''
        判斷chat_id是否存在於現有的qdrant vector
        :param collection_name: 集合名稱, 這邊暫時用不到
        :param chat_id: 所要被判斷的集合名稱
        :return collection_names_threshold: True代表現有的qdrant vector內含有chat_id這個qdrant vector
        '''
        chat_id = chat_id.strip().split('_')[0]
        collection_names = self.get_all_collection_names()
        collection_names_threshold = False
        # print('===========================')
        for i in collection_names :
            if i.strip().split('_')[0] == chat_id :
                collection_names_threshold = True
        return collection_names_threshold
        
    def create_collection(self, collection_name, vector_size, distance="Cosine") :
        """
        創建新的 Qdrant 集合。
        :param collection_name: 集合名稱
        :param vector_size: 向量的維度大小
        :param distance: 相似度度量標準 ("Euclid", "Cosine", "Dot")
        """
        self.client.create_collection(
            collection_name=collection_name,
            vectors_config={
                "size": vector_size,
                "distance": distance
            }
        )
        print(f"Collection '{collection_name}' created with size {vector_size} and distance {distance}.")

    ###################
    # 在class內無法使用 #
    ###################
    def delete_collection_name(self, collection_name) :
        """
        刪除指定的 Qdrant 集合。
        :param collection_name: 集合名稱
        """
        # print(f"Client URL: {self.url}")  # 顯示傳遞給 QdrantClient 的 URL
        print(f"Checking if collection '{collection_name}' exists...")
        try :
            time.sleep(1)
            self.client.get_collection(collection_name=collection_name)
            print(f"Collection '{collection_name}' exists, deleting it.")

        except UnexpectedResponse as e :
            print(f"Error deleting collection: {e}")
        for i in range(2) :
            try :
                time.sleep(1)
                self.client.delete_collection(collection_name=collection_name)

                print(f"Collection '{collection_name}' deleted.")
            except UnexpectedResponse as e :
                print(f"Error deleting collection: {e}")

    def get_all_collection_names(self) :
        """
        獲取所有 Qdrant 集合的名稱。
        :return: 返回所有集合名稱的列表
        """
        collections = self.client.get_collections()
        collection_names = list(map(lambda collection: collection.name, collections.collections))
        return collection_names

    def user_qdrant_vector(self, collection_name, docs_chil):
        '''
        新增向量索引到 Qdrant

        :param embed_model: 文字嵌入模型
        :param collection_name: Qdrant 向量庫名稱
        :param docs_chil: 需存入的文件
        :return: VectorStoreIndex（已存入的向量索引）
        '''
        vector_store = QdrantVectorStore(client=self.client, collection_name=collection_name, batchSize=64)
        storage_context = StorageContext.from_defaults(vector_store=vector_store)
        index = VectorStoreIndex.from_documents(
            docs_chil,
            embed_model=self.embed_model,
            storage_context=storage_context,
            transformations=[SentenceSplitter(chunk_size=256, chunk_overlap=10)],
            show_progress=True
        )
        return index

    def qdrant_vector(self, embed_model, collection_name):
        '''
        從 Qdrant 向量庫讀取索引

        :param embed_model: 文字嵌入模型
        :param collection_name: Qdrant 向量庫名稱
        :return: VectorStoreIndex（載入的向量索引）
        '''
        vector_store = QdrantVectorStore(client=self.client, collection_name=collection_name, batchSize=64)
        index = VectorStoreIndex.from_vector_store(embed_model=embed_model, vector_store=vector_store)
        return index

    def qdrant_vector_connect(self, collection_name):
        '''
        檢查 Qdrant 向量庫是否存在

        :param collection_name: Qdrant 向量庫名稱
        :return: True（存在） / False（不存在）
        '''
        try:
            self.client.get_collection(collection_name)
            return True
        except UnexpectedResponse:
            return False

    @staticmethod
    def restart_qdrant_docker() :
        """
        在docker容器內不能啟動
        重啟 Qdrant 的 Docker 容器。
        """
        try :
            subprocess.run(["docker", "stop", "qdrant"], check=True)
            print("Qdrant 容器已停止")
            subprocess.run(["docker", "start", "qdrant"], check=True)
            print("Qdrant 容器已重新啟動")
        except subprocess.CalledProcessError as e :
            print(f"重啟 Qdrant 容器時發生錯誤: {e}")


    @staticmethod    
    def is_docker_environment() :
        '''
        判斷是否在 Docker 環境內
        :return: True（在 Docker 環境內） / False（不在）
        '''
        return shutil.which("docker") is not None
        
    def embed_model_settings(self):
        """
        初始化並返回嵌入模型設定。
        :return: 嵌入模型設定
        """
        return OllamaEmbedding(
            model_name=self.embed_model_name,
            base_url=self.base_url,
            ollama_additional_kwargs={"mirostat": 0}
        )
        
if __name__ == "__main__":
    """
    這段程式碼用於初始化並管理 Qdrant 資料庫。
    請根據需求傳入不同的參數來進行操作。
    
    使用範例：
    
    1. 初始化 QdrantManager
       使用預設嵌入模型 'chatfire/bge-m3:q8_0' 來初始化 QdrantManager, 要換嵌入模型建立class input就行。
       
       qdrant_manager = QdrantManager()
       qdrant_manager = QdrantManager('chatfire/bge-m3:q8_0')

    2. 創建新的 Qdrant 集合
       用以下方法創建一個新的 Qdrant 集合，並設置向量大小和距離度量標準。
       
       qdrant_manager.create_collection(collection_name='new_collection', vector_size=768, distance="Cosine")

    3. 檢查集合是否存在
       使用以下方法檢查某個集合是否已經存在於 Qdrant 中。
       
       exists = qdrant_manager.check_collection_exists(collection_name='existing_collection')
       print(exists)

    4. 新增向量索引到 Qdrant
       若需要新增文件到 Qdrant 向量庫，可以使用以下方式將文檔轉換為向量並保存：
       
       docs_chil = [...]  # 需要保存的文檔
       index = qdrant_manager.user_qdrant_vector(collection_name='existing_collection', docs_chil=docs_chil)

    5. 讀取 Qdrant 向量庫中的索引
       使用以下方法從 Qdrant 向量庫中讀取並載入索引：
       
       embed_model = OllamaEmbedding(...)  # 載入您需要的嵌入模型
       index = qdrant_manager.qdrant_vector(embed_model, collection_name='existing_collection')

    6. 刪除指定的集合
       若需要刪除某個集合，可以使用以下方法：
       
       qdrant_manager.delete_collection_name(collection_name='existing_collection')

    7. 重啟 Qdrant Docker 容器
       若遇到 Qdrant 容器異常，可以重啟 Docker 容器：
       
       QdrantManager.restart_qdrant_docker()

    8. 判斷是否在 Docker 環境
       若您想確認是否在 Docker 環境下執行，可以使用以下方法：
       
       is_docker = QdrantManager.is_docker_environment()
       print(is_docker)
    """
    
    # 範例使用
    qdrant_manager = QdrantManager()  # 初始化 QdrantManager
    collection_name = 'new_collection'
    
    # 創建新集合
    qdrant_manager.create_collection(collection_name=collection_name, vector_size=768, distance="Cosine")
    
    # 檢查集合是否存在
    exists = qdrant_manager.check_collection_exists(collection_name=collection_name)
    print(f"Collection exists: {exists}")
    
    # 假設這是您的文檔
    docs_chil = ["Example document 1.", "Example document 2."]
    
    # 新增向量索引
    index = qdrant_manager.user_qdrant_vector(collection_name=collection_name, docs_chil=docs_chil)
    
    # 讀取索引
    embed_model = qdrant_manager.embed_model_settings()
    index = qdrant_manager.qdrant_vector(embed_model, collection_name=collection_name)
    
    # 刪除集合
    qdrant_manager.delete_collection_name(collection_name)
    
    # 重啟 Docker 容器
    QdrantManager.restart_qdrant_docker()
    
    # 判斷是否在 Docker 環境
    is_docker = QdrantManager.is_docker_environment()
    print(f"Is Docker environment: {is_docker}")
