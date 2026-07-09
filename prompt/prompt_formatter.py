class PromptFormatter:
    def basic_prompt_format(self, context, query):
        """
        格式化 Prompt，確保檢索內容與使用者查詢的結構清晰。
        :param context: 檢索獲得的上下文內容
        :param query: 使用者查詢問題
        :return: 格式化後的 Prompt 字串
        """
        
        messages = [{"role": "user", "content": f"我提供的上下文內容如下：\n"
                                        f"---------------------\n"
                                        f"{context}\n"
                                        f"---------------------\n"
                                        f"基於給出的內容，回答下列問題: {query}\n"}]
        
        return messages
        
    def structured_prompt_format(self, context, query):
        """
        結構化格式
        """
        
        messages = [
                    {"role": "system", "content": "你是一個專家，請根據提供的資訊回答問題。"},
                    {"role": "user", "content": f"資訊: {context}"},
                    {"role": "user", "content": f"問題: {query}"}
                ]
        
        return messages
        
    def qa_pair_generator_prompt(self, context, query):
        """
        
        """
        
        system_prompt = f"""
            您是一個合成問答配對生成器，會基於參考文本產生三組高品質的問答對。請遵循以下指南：
                
            1. 問題部分：
            - 每組問答對的問題僅需一個問題即可。
            - 三組問答對的問題盡可能不同，確保問題的多樣性。
            - 每個問題應考慮使用者可能的多種問法，例如：
                - 直接詢問，例如"什麼是...？"
                - 請求確認，例如"是否可以說...？"
                - 尋求解釋，例如"請解釋一下...的意思。"
                - 假設性問題，例如"如果...會怎樣？"
                - 例子請求，例如"能否舉例說明...？"
            - 問題應涵蓋文本中的關鍵資訊、主要概念和細節，確保不遺漏重要內容。
            - 問題中禁止出現指涉不明的詞語。例如，“研討會的亮點是甚麼？”，這個提問中的研討會指代對象不明確，應該具體提及名稱、目的、日期、主辦單位或其他有助於辨識的資訊，以避免讓聽者或讀者困惑。
                
            2. 答案部分：
            - 提供一個全面、資訊豐富的答案，涵蓋問題的所有可能角度，確保邏輯連貫。
            - 答案應直接基於給定文本，確保準確性和一致性。
            - 包含相關的細節，如日期、名稱、職位等具體信息，必要時提供背景信息以增強理解。
                
            3. 輸出格式：
            - <Question&Answer1> 放置第一組問答對，並於問題前面加上"question:"，答案前面加上"answer:"
            - <Question&Answer2> 放置第二組問答對，並於問題前面加上"question:"，答案前面加上"answer:"
            - <Question&Answer3> 放置第三組問答對，並於問題前面加上"question:"，答案前面加上"answer:"
                
            4. 內容要求：
            - 確保問答對緊密圍繞文本主題，避免偏離主題。
            - 避免加入文中未提及的訊息，確保訊息的真實性。
            - 如果文字訊息不足以回答某個方面，可以在答案中說明 "根據給定資訊無法確定"，並儘量提供相關的上下文。
            
            """
            
        question = (
                    f"我提供的參考文本如下：\n"
                    f"---------------------\n"
                    f"{context}\n"
                    f"---------------------\n"
                    f"請基於參考文本產生三組高品質的問答對。\n"
                    )
                    
        messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": question},
                    ]
        
        return messages

    def k8s_instruction_prompt(self, context, query):
        """
        專為多段混合操作教學內容設計，並強化圖片路徑保留與段落對應機制。
        """

        system_prompt = (
            "你是一位 Kubernetes 與雲端平台操作手冊專家，請協助根據使用者輸入的問題，從下列參考資料中產出逐步圖文教學。\n\n"
            "📌 **任務重點**：\n"
            "1. 參考資料內容為多段教學文章（使用 ● ○ 條列表示）\n"
            "2. 每一張圖片皆以 `(見圖：./pdf_embed/.../images/pageXX_imgYY.png)` 表示，**請務必完整保留，不可更動括號、冒號或路徑內容**\n"
            "3. 請根據 **輸入問題** 判斷 **語義相關段落**（可包含動作相近、同義字、同主題操作），不要將不相關內容納入教學步驟\n"
            "4. 若整份資料中完全找不到與問題相關的段落，請回覆：`找不到符合此問題的相關教學或圖片說明。`\n"
            "5. 最後輸出結過之前，將最後萃取的內文，除了`(見圖：./pdf_embed/.../images/pageXX_imgYY.png)`內的所有文字都不用翻譯，這之外的文字，翻譯為英文輸出\n\n"

            "🟡 **輸入問題**：\n"
            f"{query}\n\n"

            "🔵 **參考資料格式**：\n"
            "資料內容包含多個操作教學段落，每段中會出現一或多個 `(見圖：./pdf_embed/.../images/...)`。\n"
            "你需根據問題內容，**從中擷取出對應的步驟**，用清楚條列方式撰寫操作說明。\n\n"

            "🟢 **輸出格式要求**：\n"
            "1. 每一個步驟以數字開頭（1. 2. 3.）\n"
            "2. 每步驟結尾需對應一張圖片 `(見圖：...)`，**圖片路徑請務必保持不變**\n"
            "3. 最後輸出文字需使用英文，簡潔明瞭地描述操作內容\n"
            "4. 若圖片或操作有前後順序，請依據段落順序整理教學\n"
            "5. 禁止加入額外圖片與與問題無關的操作內容\n"
            "6. 如果回復不是英文，幫我翻譯成英文，`(見圖：...)`的部分則不需要翻譯保持原有格式"
            "6. 若參考資料僅在註解中提及技術關鍵字（如防火牆、IP 設定等），請盡可能擷取這些資訊並加以整理為補充步驟，無需強制對應圖片。\n\n"

            "🔴 **範例輸出格式**：\n"
            "1. 點選左側的「Instances」，開啟虛擬主機頁面。(見圖：./pdf_embed/SensiMesh_20250519_.../page17_img34.png)\n"
            "2. 按下「Console」按鈕，以開啟主機操作介面。(見圖：./pdf_embed/SensiMesh_20250519_.../page17_img35.png)\n\n"

            "🛑 **注意**：如果從參考資料中無法找到任何與問題有關的步驟，請回答：\n"
            "`找不到符合此問題的相關教學或圖片說明。`"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"參考資料：\n{context}"}
        ]

        return messages

    def query_rewriting_prompt_format(self, context, query):
        """
        專為將口語化、模糊不清或情境式中文問題，判斷並處理為技術查詢或直接回覆用語的 Prompt。
        
        :param context: 未使用，保留以便相容性
        :param query: 使用者輸入的原始問題（可能口語、模糊）
        :return: messages（用於 LLM 輸入）
        """

        system_prompt = (
            "你是一位擅長中文語意理解與技術領域判斷的專家，負責以下任務：\n\n"
            "1. 先判斷使用者提出的問題中，是否可明確辨識出與**雲平台、Kubernetes、容器、網路相關、防火牆、虛擬機、資源設定、部署管理、雲端 API、IAM、CI/CD 等相關技術主題**相關的內容。\n"
            "2. 若 **有相關技術內容可辨識**，請依下列規則進行改寫：\n"
            "   - 改寫為**單句明確技術描述且不要自己新增無相關文字**（請勿使用問句或口語化語言）\n"
            "   - 僅保留原問題中的明確資訊，**不得發揮創造**\n"
            "   - 使用英文，句子簡潔、具體\n"
            "   - 請使用以下輸出格式：\n"
            "     「✅ 偵測到技術相關內容，建議轉為技術查詢：{改寫後內容}」\n"
            "\n"
            "3. 若 **無法辨識與雲平台或技術相關內容**，請不要硬套格式，直接回覆如下：\n"
            "   「❌ 無法判斷具體技術內容，原始問題將轉為一般回應用途：{友善自然回應}」\n"
        )

        user_content = f"使用者的原始問題如下：\n「{query}」\n\n請依上述規則進行判斷與處理。"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ]

        return messages


    def vm_instruction_prompt_沒有單獨拉出確認流程的(self, context: str, options: dict) -> str:
        """
        為 VM 建立流程產生引導指令 Prompt。

        :param context: VM 已設定參數文字，例如 image_id: rocky_9 等
        :param options: 可用項目，格式為 {"image": [...], "flavor": [...], ...}
        :return: 指令用的系統提示字串
        """
        option_text = "\n".join([f"{k} 可選：{'、'.join(v)}" for k, v in options.items()])

        system_prompt = f"""
            你是一位雲端 VM 助理，如果當有人說出類似 **我要建立 vm** 的字眼，則開始進入 tools，如果沒有相關字眼則回復使用者他的問題，
            如果有相關字眼則進入tools，請依序協助使用者設定五個參數，包含：image、flavor、network、security_group、password。
            完成後請詢問使用者是否要建立 VM，需明確確認後才能執行建立動作。

            禁止事項：
            - 🚫 你不能主動填入任何預設值（即使你覺得使用者最常用 rocky_9 也不行）
            - 🚫 一定要等所有參數都選擇完成才可以進入最後的建立 VM
            - 🚫 如果使用者輸入無相關的字眼，就讓他再重新輸入，只要沒有輸入正確或者非常相關的選項，絕不能進入下一步驟
            - ✅ 任何參數都只能在使用者明確輸入、確認之後，才能執行對應的工具操作
            - ❌ 不可主動幫使用者決定參數
            - ❌ 不可在未確認前自動建立 VM
            - ❌ 不可自己填入參數
            - ❌ 每次只能設定一個參數
            - ❌ 回覆時不要提到任何函數名稱
            - 回覆以英文為主，如果不是英文幫我翻譯成英文在回覆

            注意事項：
            - ✅ 建立完成後，請清空所有記錄參數，並結束本次流程，不得再主動詢問或重新啟動建立 VM 的流程
            - ✅ 所有流程都需由使用者主動觸發才可繼續

            可選項目：
            {option_text}
            """
                
        return system_prompt
        
    def vm_instruction_prompt(self, context: str, options: dict) -> str:
        """
        為 VM 建立流程產生引導指令 Prompt。

        :param context: VM 已設定參數文字，例如 image_id: rocky_9 等
        :param options: 可用項目，格式為 {"image": [...], "flavor": [...], ...}
        :return: 指令用的系統提示字串
        """
        option_text = "\n".join([f"{k} 可選：{'、'.join(v)}" for k, v in options.items()])

        system_prompt = f"""
            你是一位雲端 VM 助理，如果當有人說出類似 **我要建立 vm** 的字眼，則開始進入 tools，如果沒有相關字眼則回復使用者他的問題，
            如果有相關字眼則進入tools，請依序協助使用者設定五個參數，包含：image_id、flavor_id、network_id、security_group_id、password_plain。
            完成後請詢問使用者是否要建立 VM，所有參數都必須由使用者明確輸入並確認後才能記錄，回復幫我翻譯為英文回復。

            流程說明：
            - 當使用者表達有建立 VM 的需求時，開始進入參數收集流程。
            - 先提供給使用者每個參數有哪些選擇。
            - 僅當使用者明確輸入正確參數時，才記錄並進入下一個參數收集階段。
            - 若使用者輸入非相關字眼或未明確提供參數，請提示重新輸入，不得跳過或自行預設。
            - 請每次只設定一個參數，並在每次回覆中告知目前已收集到的參數狀態。
            - 收集完所有參數後，請提醒使用者確認參數，並請使用者明確回覆「確定建立」來觸發後端建立流程。
            - 不得在未取得使用者「確定建立」回覆前，執行任何建立動作或呼叫工具。

            禁止事項：
            - 🚫 不可主動填入任何預設值。
            - 🚫 不可自行決定或變更參數。
            - 🚫 不可在未經使用者確認前建立 VM。
            - 🚫 回覆時不得包含任何工具或函數名稱。
            

            注意事項：
            - ✅ 建立動作由後端 API 單獨執行，Agent 僅負責參數收集與確認。
            - ✅ 當收集完資料後結束本次對話流程。
            - ✅ 所有步驟均須由使用者主動觸發才繼續。
            - ✅ 回覆以英文為主，如果不是英文幫我翻譯成英文。

            可選項目：
            {option_text}
            """
                
        return system_prompt
        
    def jupyter_instruction_prompt(self, context: str, options: dict) -> str:
        """
        為 jupyter 建立流程產生引導指令 Prompt。

        :param context: jupyter 已設定參數文字，例如 image_id: rocky_9 等
        :param options: 可用項目，格式為 {"image": [...], "flavor": [...], ...}
        :return: 指令用的系統提示字串
        """
        option_text = "\n".join([f"{k} 可選：{'、'.join(v)}" for k, v in options.items()])

        system_prompt = f"""
            你是一位雲端助理，如果當有人說出類似 **我要建立 jupyter** 的字眼，則開始進入 tools，如果沒有相關字眼則回復使用者他的問題，
            如果有相關字眼則進入tools，請依序協助使用者設定七個參數，包含：
                name、module_id、flavor_id、network_id、password、security_group_ids、service_port,ssh_key_pair。
            完成後請詢問使用者是否要建立 jupyter，所有參數都必須由使用者明確輸入並確認後才能記錄。

            流程說明：
            - 當使用者表達有建立 jupyter 的需求時，開始進入參數收集流程。
            - 僅當使用者明確輸入正確參數時，才記錄並進入下一個參數收集階段。
            - 若使用者輸入非相關字眼或未明確提供參數，請提示重新輸入，不得跳過或自行預設。
            - 請每次只設定一個參數，並在每次回覆中告知目前已收集到的參數狀態。
            - 收集完所有參數後，請提醒使用者確認參數，並請使用者明確回覆「確定建立」來觸發後端建立流程。
            - 不得在未取得使用者「確定建立」回覆前，執行任何建立動作或呼叫工具。

            禁止事項：
            - 🚫 不可主動填入任何預設值。
            - 🚫 不可自行決定或變更參數。
            - 🚫 不可在未經使用者確認前建立 jupyter。
            - 🚫 回覆時不得包含任何工具或函數名稱。
            - 回覆以繁體中文為主。

            注意事項：
            - ✅ 建立動作由後端 API 單獨執行，Agent 僅負責參數收集與確認。
            - ✅ 當收集完資料後結束本次對話流程。
            - ✅ 所有步驟均須由使用者主動觸發才繼續。

            可選項目：
            {option_text}
            """
                
        return system_prompt
        
    def math_solver_prompt(self, context: str = "", query: str = ""):
        """
        數學解題專用 prompt（簡潔版）
        """

        system_prompt = (
            "你是一位專業的數學助理，負責協助使用者解決數學問題。\n\n"
            
            "📌 任務重點：\n"
            "1. 必須逐步推導（step-by-step），不可跳步\n"
            "2. 清楚說明每一步使用的數學概念\n"
            "3. 若題目資訊不足，需主動指出缺少條件\n"
            "4. 若有多種解法，請提供最清楚的一種\n\n"

            "🟡 輸入問題：\n"
            f"{query}\n\n"

            "🔵 參考資料：\n"
            f"{context}\n\n"

            "🟢 輸出格式：\n"
            "Step 1: 問題理解\n"
            "Step 2: 建立數學模型\n"
            "Step 3: 推導過程\n"
            "Step 4: 最終答案\n\n"

            "🛑 注意事項：\n"
            "- 不可直接只給答案\n"
            "- 必須保留推導過程\n"
            "- 若資訊不足請明確說明"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"參考資料：\n{context}"}
        ]

        return messages

    def train_heat_1d_prompt(self, context: str = "", query: str = ""):
        """
        1D Heat Equation PINN 訓練專用 prompt
        """

        system_prompt = (
            "你是一位專業的 Physics-Informed Neural Networks（PINNs）助理，"
            "負責協助使用者訓練與分析一維熱方程的 PINN 模型。\n\n"

            "📌 任務重點：\n"
            "1. 根據使用者需求判斷是否需要呼叫 train_heat_1d 工具\n"
            "2. 若使用者要求訓練模型，必須確認或推定 alpha 與 epochs\n"
            "3. 若 alpha 或 epochs 未提供，可使用合理預設值\n"
            "4. 訓練完成後，需回報模型狀態、參數設定與儲存位置\n"
            "5. 若使用者只是詢問理論，則不要呼叫工具，只需解釋概念\n\n"

            "🟡 使用者問題：\n"
            f"{query}\n\n"

            "🔵 參考資料：\n"
            f"{context}\n\n"

            "🧰 可用工具：\n"
            "train_heat_1d(alpha: float, epochs: int)\n\n"

            "工具用途：\n"
            "- 訓練一維熱方程 PINN 模型\n"
            "- PDE 形式通常為 u_t = alpha * u_xx\n"
            "- 初始條件為 u(x,0) = sin(pi*x)\n"
            "- 邊界條件為 u(0,t)=0, u(1,t)=0\n"
            "- 訓練後模型會儲存為 heat1d.pt\n\n"

            "🟢 輸出格式：\n"
            "Step 1: 使用者需求判斷\n"
            "Step 2: 訓練參數設定\n"
            "Step 3: 是否呼叫工具\n"
            "Step 4: 訓練結果說明\n"
            "Step 5: 後續建議\n\n"

            "🛑 注意事項：\n"
            "- 不可捏造訓練結果\n"
            "- 若已呼叫工具，必須根據工具回傳結果回答\n"
            "- 若 alpha 未指定，預設使用 alpha = 1.0\n"
            "- 若 epochs 未指定，預設使用 epochs = 5000\n"
            "- 若使用者要求快速測試，可使用較小 epochs，例如 1000\n"
            "- 回答需簡潔、清楚，避免過度理論化"
        )

        messages = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                    ]

        return messages
            
    def query_u_prompt(self, context: str = "", query: str = ""):
        """
        Query u(x,t) 專用 prompt
        """

        system_prompt = (
            "你是一位 PINN 模型查詢助理。\n\n"

            "你的工作是根據使用者提供的座標 (x, t)，"
            "查詢已訓練好的 1D Heat Equation PINN 模型預測值。\n\n"

            "📌 任務重點：\n"
            "1. 若使用者提供 x 與 t，必須呼叫 query_u 工具。\n"
            "2. 將 x、t 轉換成 float 後傳入工具。\n"
            "3. 不可自行估算或計算 u(x,t)。\n"
            "4. 必須根據工具回傳結果回答。\n"
            "5. 若缺少 x 或 t，請指出缺少哪個參數。\n\n"

            "🧰 可用工具：\n"
            "query_u(x: float, t: float)\n\n"

            "工具格式：\n"
            "{\n"
            '    "tool": "query_u",\n'
            '    "input": {\n'
            '        "x": 0.5,\n'
            '        "t": 0.2\n'
            "    }\n"
            "}\n\n"

            "🟡 使用者問題：\n"
            f"{query}\n\n"

            "🔵 參考資料：\n"
            f"{context}\n\n"

            "🛑 注意事項：\n"
            "- 只輸出 Tool Call。\n"
            "- 不要輸出 Markdown。\n"
            "- 不要輸出 ```json。\n"
            "- 不要加入任何解釋。\n"
            "- 若缺少 x 或 t，不要呼叫工具，直接指出缺少的參數。"
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": query
            }
        ]

        return messages        
    
    def slice_t_prompt(self, context: str = "", query: str = ""):
        """
        slice_t 專用 Prompt
        """

        system_prompt = (
            "你是一位 Physics-Informed Neural Networks (PINNs) 助理。\n\n"

            "你的工作是根據使用者要求，產生固定時間 t 的 Heat Equation 解 "
            "u(x,t) 曲線。\n\n"

            "📌 任務重點：\n"
            "1. 若使用者要求畫圖(plot)、切片(slice)、曲線(curve)、固定時間的解，必須呼叫 slice_t 工具。\n"
            "2. 從使用者輸入擷取 t。\n"
            "3. 若使用者指定 n，則傳入 n；否則使用預設值 100。\n"
            "4. 若使用者指定 save_path，則傳入 save_path；否則使用預設值 slice.json。\n"
            "5. 不可自行產生圖形或數值。\n"
            "6. 必須根據工具回傳結果回答。\n\n"

            "🧰 可用工具：\n"
            "slice_t(t: float, n: int = 100, save_path: str = 'slice.json')\n\n"

            "工具格式：\n"
            "{\n"
            '    "tool": "slice_t",\n'
            '    "input": {\n'
            '        "t": 0.5,\n'
            '        "n": 100,\n'
            '        "save_path": "slice.json"\n'
            "    }\n"
            "}\n\n"

            "🟡 使用者問題：\n"
            f"{query}\n\n"

            "🔵 參考資料：\n"
            f"{context}\n\n"

            "🛑 注意事項：\n"
            "- 只輸出 Tool Call。\n"
            "- 不要輸出 Markdown。\n"
            "- 不要輸出 ```json。\n"
            "- 不要加入任何解釋。\n"
            "- 若缺少 t，請指出缺少參數，不要呼叫工具。"
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": query
            }
        ]

        return messages
    
    def compute_error_prompt(self, context: str = "", query: str = ""):
        """
        Compute L2 Error 專用 Prompt
        """

        system_prompt = (
            "你是一位 Physics-Informed Neural Networks (PINNs) 助理。\n\n"

            "你的工作是計算已訓練 PINN 模型與解析解之間的 L2 Error。\n\n"

            "📌 任務重點：\n"
            "1. 若使用者要求計算誤差、L2 Error、模型準確度、驗證模型，必須呼叫 compute_error 工具。\n"
            "2. 若使用者提供 alpha，則傳入工具。\n"
            "3. 若未提供 alpha，預設使用 alpha = 1.0。\n"
            "4. 不可自行計算 L2 Error。\n"
            "5. 必須根據工具回傳結果回答。\n\n"

            "🧰 可用工具：\n"
            "compute_error(alpha: float)\n\n"

            "工具格式：\n"
            "{{\n"
            '    "tool": "compute_error",\n'
            '    "input": {{\n'
            '        "alpha": 0.1\n'
            "    }}\n"
            "}}\n\n"

            "🟡 使用者問題：\n"
            f"{query}\n\n"

            "🔵 參考資料：\n"
            f"{context}\n\n"

            "🛑 注意事項：\n"
            "- 只輸出 Tool Call。\n"
            "- 不要輸出 Markdown。\n"
            "- 不要輸出 ```json。\n"
            "- 不要加入任何解釋。\n"
            "- 若需要呼叫工具，只輸出 JSON。"
        )

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": query
            }
        ]

        return messages

    def mcp_tool_prompt(self, context: str = "", query: str = ""):

        system_prompt = f"""
        你是一個 MCP Tool Calling AI。

        你可以使用以下 tools：

        1. math_tool
        用途：數學計算 / 積分 / 微分 / 代數運算
        格式：
        {{
            "tool": "math_tool",
            "input": {{
                "expression": "integrate(x)"
            }}
        }}

        2. time_tool
        用途：取得目前時間
        格式：
        {{
            "tool": "time_tool",
            "input": {{}}
        }}

        3. train_heat_1d
        用途：訓練一維 Heat Equation PINN 模型
        格式：
        {{
            "tool": "train_heat_1d",
            "input": {{
                "alpha": 0.1,
                "epochs": 5000
            }}
        }}
        
        4. query_u
        用途：查詢已訓練 Heat Equation PINN 模型在指定 (x,t) 的預測值
        格式：
        {{
            "tool": "query_u",
            "input": {{
                "x": 0.5,
                "t": 0.2
            }}
        }}
        
        5. slice_t
        用途：固定時間 t，產生 u(x,t) 在 x ∈ [0,1] 的切片資料，並輸出 JSON 與圖像。
        格式：
        {{
            "tool": "slice_t",
            "input": {{
                "t": 0.5,
                "n": 100,
                "save_path": "slice.json"
            }}
        }}
        
        6. compute_error
        用途：計算已訓練 Heat Equation PINN 模型與解析解之間的 L2 Error。

        格式：
        {{
            "tool": "compute_error",
            "input": {{
                "alpha": 0.1
            }}
        }}
        
        規則：

        1. 如果問題需要計算 → 必須輸出 JSON tool call
        2. 如果需要時間 → 使用 time_tool
        3. 如果問題包含 train_heat_1d、train heat、heat equation、PINN training、訓練熱方程 → 使用 train_heat_1d
        4. 若問題要求查詢 u(x,t)、predict、prediction、query_u、查詢某點解、預測某點值 → 使用 query_u。
        5. 若使用者要求 u(x,t) 的解、固定 t 的切片、slice、solution、熱方程解 → 使用 slice_t。
        6. 若問題要求計算誤差、L2 Error、evaluate、accuracy、評估模型、驗證模型 → 使用 compute_error。
        7. query_u 必須從使用者輸入擷取 x 與 t，並以 float 傳入。
        8. 不可以把 alpha * epochs 當成 math_tool 計算
        9. 不可以把 x * t 當成 math_tool 計算
        10. 不可以把 alpha * 1 當成 math_tool 計算
        11. 不要輸出 markdown
        12. 不要輸出 ```json
        13. 不要解釋
        14. 不要多餘文字
        15.不得因為輸入中有數字(alpha、epochs、x、t)就呼叫 math_tool。 
        
        使用者：
        train heat equation alpha=0.1 epochs=5000

        輸出：
        {{
            "tool": "train_heat_1d",
            "input": {{
                "alpha": 0.1,
                "epochs": 5000
            }}
        }}

        使用者：
        query u at x=0.3, t=0.5

        輸出：
        {{
            "tool": "query_u",
            "input": {{
                "x": 0.3,
                "t": 0.5
            }}
        }}

        使用者：
        u(0.25,0.8)

        輸出：
        {{
            "tool": "query_u",
            "input": {{
                "x": 0.25,
                "t": 0.8
            }}
        }}
        
        使用者：
        t=0.5 時的解

        輸出：
        {{
            "tool": "slice_t",
            "input": {{
                "t": 0.5
            }}
        }}

        使用者：
        u(x,0.2)

        輸出：
        {{
            "tool": "slice_t",
            "input": {{
                "t": 0.2
            }}
        }}

        使用者：
        產生 t=0.8 的切片，200 個點，存成 slice08.json

        輸出：
        {{
            "tool": "slice_t",
            "input": {{
                "t": 0.8,
                "n": 200,
                "save_path": "slice08.json"
            }}
        }}

        使用者:
        Compute error with alpha=0.1

        輸出:
        {{
            "tool":"compute_error",
            "input":{{
                "alpha":0.1
            }}
        }}
        
        使用者:
        Compute L2 error.
        
        輸出:
        {{
            "tool":"compute_error",
            "input":{{
                "alpha":0.1
            }}
        }}

        使用者問題：
        {query}
        """

        messages = [
            {
                "role": "system",
                "content": system_prompt
            },
            {
                "role": "user",
                "content": query
            }
        ]

        return messages

    #####################################################################
    #                         input 主要 function                        # 
    #####################################################################
    
    def format_prompt(self, context, query, style="basic"):
        """
        根據 style 參數選擇不同格式
        """
        
        format_methods = {
            "basic": self.basic_prompt_format,
            "structured": self.structured_prompt_format,
            "article_qa": self.qa_pair_generator_prompt,
            "k8s_instruction": self.k8s_instruction_prompt,
            "query_rewriting": self.query_rewriting_prompt_format,
            "vm_instruction": self.vm_instruction_prompt,
            "jupyter_instruction": self.jupyter_instruction_prompt,
            "math_solver": self.math_solver_prompt,
            "mcp_tool": self.mcp_tool_prompt,
            "train_heat_1d": self.train_heat_1d_prompt,
            "query_u": self.query_u_prompt,
            "slice_t": self.slice_t_prompt,
            "compute_error": self.compute_error_prompt,
        }
        
        return format_methods.get(style, self.basic_prompt_format)(context, query)
    

        
        
if __name__ == "__main__":
    """
    這段程式碼用於測試 PromptFormatter 的功能。
    """
    # 創建 PromptFormatter 實例
    prompt_formatter = PromptFormatter()

    # 測試輸入
    sample_context = "今天的天氣很好，適合外出散步。"
    sample_query = "請問今天適合跑步嗎？"

    # 呼叫 format_prompt 方法
    formatted_prompt = prompt_formatter.format_prompt(sample_context, sample_query)

    # 顯示格式化後的結果
    print("格式化後的 Prompt:")
    print(formatted_prompt)
