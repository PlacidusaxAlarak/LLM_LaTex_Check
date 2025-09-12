
# --- START OF FILE llm_agent.py ---

import os
import json
from dotenv import load_dotenv
from openai import AsyncOpenAI
# MODIFIED: 移除了对 JSON_VALIDATOR_PROMPT 的导入
from prompts import LATEX_REFERENCE_PARSER_PROMPT, get_latex_extraction_prompt, HTML_CORRECTOR_PROMPT
from json_repair import repair_json
import cache_handler

load_dotenv()


class LLMAgent:
    """封装了与大语言模型 (LLM) 交互的所有逻辑。"""

    def __init__(self, api_key: str):
        """初始化异步LLM客户端。"""
        base_url = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
        if not api_key:
            self.client = None
            print("⚠️ 警告: 未提供 API_KEY。LLM 智能体将无法工作。\n")
        else:
            self.client = AsyncOpenAI(api_key=api_key, base_url=base_url)

    async def run_reference_parser(self, references_text: str) -> list[dict]:
        if not self.client: return []
        cache_key = cache_handler.get_cache_key(references_text)
        cached_data = cache_handler.get_from_cache(cache_key)
        if cached_data:
            return cached_data

        print("--- (异步) 正在调用 LLM 精确解析参考文献列表... --- ")
        user_content = f"请根据你的指令，精确解析以下 LaTeX 文本中的所有参考文献：\n--- 参考文献文本开始 ---\n{references_text}\n--- 参考文献文本结束 ---"
        try:
            response = await self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": LATEX_REFERENCE_PARSER_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.0,
                max_tokens=8192,
                timeout=180.0,
                response_format={"type": "json_object"}
            )
            response_content = response.choices[0].message.content
            repaired_json_string = repair_json(response_content)
            parsed_json = json.loads(repaired_json_string)

            if isinstance(parsed_json, dict) and "references" in parsed_json and isinstance(parsed_json["references"], list):
                result = parsed_json["references"]
                cache_handler.set_to_cache(cache_key, result)
                return result
            else:
                raise ValueError("返回的JSON格式不符合预期。")
        except Exception as e:
            print(f"❌ 错误: 解析或修复 LLM 参考文献响应失败: {e}")
            return []

    # _run_json_validation_checker 函数已彻底移除

    async def run_extraction_batch(self, full_latex_source: str, references_batch: list[dict]) -> dict | None:
        """
        运行核心的上下文抽取智能体。
        此版本已简化，移除了第二阶段验证。
        """
        if not self.client: return None

        references_batch_str = json.dumps(references_batch, sort_keys=True)
        # 使用 v5 最终版缓存键
        cache_key_data_generate = f"generate_v5_{full_latex_source}{references_batch_str}"
        cache_key_generate = cache_handler.get_cache_key(cache_key_data_generate)

        start_key = references_batch[0]['key']
        end_key = references_batch[-1]['key']

        # 尝试从缓存中获取生成结果
        response_content = cache_handler.get_from_cache(cache_key_generate)

        if not response_content:
            print(f"--- (异步) 调用 LLM 分析参考文献 {start_key} 到 {end_key}... ---")
            system_prompt = get_latex_extraction_prompt(start_key, end_key)
            user_content = (
                f"这是你需要分析的完整LaTeX源码:\n--- LaTeX源码开始 ---\n{full_latex_source}\n--- LaTeX源码结束 ---\n\n"
                f"这是当前批次需要你处理的参考文献列表 (JSON格式):\n--- 参考文献批次开始 ---\n{json.dumps(references_batch, indent=2, ensure_ascii=False)}\n--- 参考文献批次结束 ---"
            )
            try:
                response = await self.client.chat.completions.create(
                    model="deepseek-chat",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_content}
                    ],
                    temperature=0.0, # 使用0.0以获得最确定性的结果
                    max_tokens=8192,
                    timeout=300.0,
                    response_format={"type": "json_object"}
                )
                response_content = response.choices[0].message.content
                cache_handler.set_to_cache(cache_key_generate, response_content)
            except Exception as e:
                print(f"\n❌ 错误: 调用LLM分析批次 {start_key} - {end_key} 时发生错误: {e}")
                return None
        else:
            print(f"--- 命中生成缓存: {start_key} 到 {end_key} ---")

        # 直接处理并返回结果
        try:
            repaired_json_string = repair_json(response_content)
            final_result = json.loads(repaired_json_string)
            print(f"--- ✅ LLM 成功为参考文献 {start_key} - {end_key} 生成了JSON数据。 ---")
            return final_result
        except Exception as e:
            print(f"\n❌ 错误: 修复批次 {start_key} - {end_key} 的JSON时发生严重错误: {e}")
            return None

    async def run_html_correction_batch(self, html_chunk_to_correct: str) -> str:
        # ... (此函数保持不变)
        if not self.client: return html_chunk_to_correct
        # ...