from api.trustedcloud_vm_creator import TrustedCloudVMBuilder
import time
from rag.retriever_handler import *
from ruamel.yaml import YAML
from rag.retriever_handler import RetrieverHandler
from rag.qdrant_retriever import *
from rag.model_handler import *

class VMAgentManager:
    """
    專責處理 VM 建立流程的 Agent 管理器。
    :param token: 使用者身份識別 token
    :return: 封裝好指令工具與 Agent 的 VM 管理器
    """
    # def __init__(self, token: str, project_id: str):
        # builder = TrustedCloudVMBuilder(token, project_id)
        # self.resources = VMResources(builder, token, project_id)
    def __init__(self, token: str):
        
        self.last_access_time = time.time()
        # 基本參數初始化
        self.parameters_initializer() 


    def _read_yaml(self):
        """
        讀取 YAML 配置檔案。
        :return: 解析後的 YAML 參數
        """
        yaml = YAML()
        yaml_path = './config/settings.yaml'
        yaml.indent(mapping=2, sequence=4, offset=2)
        yaml.preserve_quotes = True
        with open(yaml_path, 'r') as file:
            return yaml.load(file)

    def parameters_initializer(self):
        """
        獲取加載的 YAML 參數，並以元組格式返回。
        :return: 包含 YAML 設定的變數元組
        """        
        parameters = self._read_yaml()  # 讀取 YAML 參數
        self.openai_base_url = str(parameters['openai_base_url'])
        self.api_key = str(parameters['api_key'])
        self.llm_model_name = [str(parameters['llm_model_name'])]
        self.prompt_style = str(parameters['prompt_style'])
        self.reranker_top = str(parameters['reranker_top'])
        self.trusted_cloud_Qdrant_vector_collection_name = str(parameters['trusted_cloud_Qdrant_vector_collection_name'])
        self.embed_model_name = str(parameters['embed_model_name'])
        self.temperature = float(parameters['temperature'])
        
        print(self.openai_base_url)
        print(self.api_key)
        print(self.llm_model_name)
        # 設定 llm
        self.model_handler = ModelHandler(
            self.trusted_cloud_Qdrant_vector_collection_name,
            self.temperature,
            self.api_key, 
            self.llm_model_name,  # 範例格式 ['llmam3.3']
            self.openai_base_url,
            embed_model_name = self.embed_model_name,
            reranker_top=self.reranker_top,)
        self.llm = self.model_handler.initialize_llm_openai(self.api_key)

        # retriever 基本設定
        # self.retriever_engine = self.model_handler.retriever_engine
        # self.bm25_retriever = self.model_handler.bm25_retriever
        self.reranker = self.model_handler.reranker

        # 初始化檢索處理器
        self.retriever = RetrieverHandler(
            self.reranker,
            retrievers_with_weights={
                "vector_retriever": (self.model_handler.retriever_engine, 1.0),  # retriever_engine 的權重為 1.0
                "bm25_retriever": (self.model_handler.bm25_retriever, 1.0)  # bm25_retriever 的權重為 1.0
            },
            reranker_top=self.reranker_top)
            
    def update_access_time(self):
        """
        更新此 manager 的最後存取時間，用於閒置檢查。
        """
        self.last_access_time = time.time()

    def denaturalize_input(self, query):
        """
        進入正式 llm 前口語化處理
        """
        print('query', query)
        # 設定 prompt
        prompt_formatter = self.retriever.prompt_formatter
        
        print('prompt_formatter', prompt_formatter)
        # 取得 prompt 格式（messages 結構，包含 system 和 user 的角色訊息）
        messages = prompt_formatter.format_prompt('', query, "query_rewriting")
        
        print('messages', messages)
        
        response = self.model_handler.ask_openai(self.llm, messages, False)
        print(response)
        
        rewritten_query = response.choices[0].message.content.strip()
        
        return rewritten_query

    def process_rewritten_query(self, text):
        """
        處理 LLM 改寫後的查詢輸出：
        1. 判斷是否為技術相關（開頭為 ✅）
        2. 僅去除第一個冒號前的部分（支援全形：與半形:）
        
        :param text: LLM 輸出文字（含標記與描述）
        :return: (is_technical: bool, cleaned_content: str)
        """

        is_technical = text.startswith("✅")

        # 找第一個冒號（全形或半形）
        full_index = text.find("：")  # 全形冒號
        half_index = text.find(":")  # 半形冒號

        # 取得第一個出現的冒號位置
        if full_index == -1 and half_index == -1:
            # 都沒找到，直接回傳原始
            return is_technical, text.strip()
        elif full_index == -1:
            colon_index = half_index
        elif half_index == -1:
            colon_index = full_index
        else:
            colon_index = min(full_index, half_index)

        # 僅去除第一個冒號前的部分（包括冒號本身）
        cleaned_content = text[colon_index + 1:].strip()
        print("cleaned_content")
        print(cleaned_content)
        return is_technical, cleaned_content

    async def chat(self, user_input: str):
        # 去口語化
        query = self.denaturalize_input(user_input)
        
        is_technical, cleaned_content = self.process_rewritten_query(query)
        # ToDo
        '''
        去冒號部分
        '''
        if is_technical :
            # retriever
            ques_str, retrieve_file = self.retriever.format_retrieved_result(cleaned_content, prompt_style=self.prompt_style)
            
            # llm
            response = self.model_handler.ask_openai(self.llm, ques_str, False)
            response = response.choices[0].message.content.strip()
            print(response)
            return response
        else:
            print(cleaned_content)
            return cleaned_content
            
        
        

        


