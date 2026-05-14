# from openai import AsyncOpenAI
from agents import Agent, Runner
# from agents import set_default_openai_client, set_tracing_disabled
# from api.trustedcloud_vm_creator import TrustedCloudVMBuilder
#from agent.agent_vm import VMAgentManager
import time
import threading


from agent.agent_llm import *
class SessionStore:
    """
    管理所有使用者的 Agent Session 實例，並自動移除超過閒置時間的 Session。
    :param token: 使用者的身份識別 token
    :return: 對應的 Agent 管理器實例
    """
    
    def __init__(self, timeout: int = 1800, cleanup_interval: int = 60):
        """
        初始化 SessionStore。

        :param timeout: session 閒置多久會被清除（秒）
        :param cleanup_interval: 多久檢查一次（秒）
        """
        self.store = {}
        self.timeout = timeout
        self.cleanup_interval = cleanup_interval
        self.lock = threading.Lock()
        self._start_cleanup_thread()

    def _start_cleanup_thread(self):
        """
        啟動背景執行緒，定期清理過期 session。
        """
        thread = threading.Thread(target=self.cleanup_expired_sessions, daemon=True)
        thread.start()
        print("🧼 Session Cleanup Thread 啟動完成")

    def get_or_create(self, token: str) -> VMAgentManager:
        
        """
        取得或創建一個對應使用者的 VMAgentManager。

        :param token: 使用者的識別 token
        :return: 對應的 VMAgentManager
        """
        with self.lock:
            if token in self.store:
                manager = self.store[token]
                manager.update_access_time()
            else:
                manager = VMAgentManager(token)
                self.store[token] = manager
                print(f"✅ 新增 session：{token}")
        return manager

    def cleanup_expired_sessions(self):
        """
        清理所有過期的 session，並顯示目前所有 session 剩餘時間。
        """
        while True:
            time.sleep(self.cleanup_interval)
            now = time.time()
            with self.lock:
                to_delete = []
                print(f"\n🧹 [Session Cleanup] {time.strftime('%X')} 開始檢查所有 session：")
                for token, manager in self.store.items():
                    idle_time = now - manager.last_access_time
                    remaining_time = self.timeout - idle_time
                    if remaining_time <= 0:
                        print(f"❌ Token: {token} - 已閒置 {int(idle_time)} 秒，將刪除")
                        to_delete.append(token)
                    else:
                        print(f"✅ Token: {token} - 尚有 {int(remaining_time)} 秒可以使用")

                for token in to_delete:
                    del self.store[token]
                    print(f"🗑️ 已刪除過期 session：{token}")

    def delete(self, token: str):
        """
        手動移除某個 session。
        :param token: 使用者 token
        :param project_id: 專案 ID
        """
        vm_manager = VMAgentManager(token)
        project_id = vm_manager.builder.project_id
        key = f"{token}_{project_id}"
        if key in self.store:
            del self.store[key]

session_store = SessionStore()


