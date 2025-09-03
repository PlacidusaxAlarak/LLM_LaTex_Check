

import os
import json
import re
from dotenv import load_dotenv
from openai import AsyncOpenAI
from prompts import LATEX_REFERENCE_PARSER_PROMPT, get_latex_extraction_prompt, HTML_CORRECTOR_PROMPT
from json_repair import repair_json

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
        """运行参考文献解析智能体，从文本块中提取所有参考文献并返回结构化列表。"""
        if not self.client: return []
        print("--- (异步) 正在调用 LLM 精确解析参考文献列表... ---")
        user_content = f"请根据你的指令，精确解析以下 LaTeX 文本中的所有参考文献：\n--- 参考文献文本开始 ---\n{references_text}\n--- 参考文献文本结束 ---"
        response_content = ""
        try:
            response = await self.client.chat.completions.create(
                model="deepseek-chat",  # MODIFIED: 强制使用 deepseek-chat
                messages=[
                    {"role": "system", "content": LATEX_REFERENCE_PARSER_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.0,
                max_tokens=8192,  # MODIFIED: 统一 max_tokens
                timeout=180.0,
                response_format={"type": "json_object"}
            )
            response_content = response.choices[0].message.content

            try:
                # 首先尝试标准解析
                parsed_json = json.loads(response_content, strict=False)
            except json.JSONDecodeError:
                print("   └── 标准JSON解析失败，尝试使用 json-repair 进行修复...")
                repaired_json_string = repair_json(response_content)
                parsed_json = json.loads(repaired_json_string)
                print("   └── ✅ JSON修复成功！")

            if isinstance(parsed_json, dict) and "references" in parsed_json and isinstance(parsed_json["references"],
                                                                                            list):
                return parsed_json["references"]
            else:
                raise ValueError("返回的JSON格式不符合预期。")
        except Exception as e:
            print(f"❌ 错误: 解析或修复 LLM 参考文献响应失败: {e}")
            debug_filename = "llm_reference_parser_error.json"
            try:
                with open(debug_filename, "w", encoding="utf-8") as f:
                    f.write(response_content)
                print(f"   └── 完整的错误响应已保存到 '{debug_filename}' 文件中供分析。")
            except Exception as write_e:
                print(f"   └── 尝试写入错误响应到文件失败: {write_e}")
            print(f"收到的部分内容: {response_content[:200]}...")
            return []

    async def run_extraction_batch(self, full_latex_source: str, references_batch: list[dict]) -> dict | None:
        """运行核心的上下文抽取智能体的一个批次，生成结构化的JSON数据。失败时返回None。"""
        if not self.client: return None

        start_key = references_batch[0]['key']
        end_key = references_batch[-1]['key']
        print(f"--- (异步) 调用 LLM 分析参考文献 {start_key} 到 {end_key} (输出JSON)... ---")

        system_prompt = get_latex_extraction_prompt(start_key, end_key)
        references_batch_str = json.dumps(references_batch, indent=2, ensure_ascii=False)
        user_content = (
            f"这是你需要分析的完整LaTeX源码:\n--- LaTeX源码开始 ---\n{full_latex_source}\n--- LaTeX源码结束 ---\n\n"
            f"这是当前批次需要你处理的参考文献列表 (JSON格式):\n--- 参考文献批次开始 ---\n{references_batch_str}\n--- 参考文献批次结束 ---"
        )
        response_content = ""
        try:
            response = await self.client.chat.completions.create(
                model="deepseek-chat", # MODIFIED: 强制使用 deepseek-chat
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.1,
                max_tokens=8192, # MODIFIED: 统一 max_tokens
                timeout=300.0,
                response_format={"type": "json_object"}
            )
            response_content = response.choices[0].message.content

            try:
                parsed_json = json.loads(response_content, strict=False)
            except json.JSONDecodeError:
                print(f"   └── 标准JSON解析失败 (批次 {start_key}-{end_key})，尝试修复...")
                repaired_json_string = repair_json(response_content)
                parsed_json = json.loads(repaired_json_string)
                print(f"   └── ✅ 批次 {start_key}-{end_key} 的JSON修复成功！")

            print(f"--- ✅ LLM 成功为参考文献 {start_key} - {end_key} 生成了JSON数据。 ---")
            return parsed_json
        except Exception as e:
            print(f"\n❌ 错误: 调用或修复LLM分析批次 {start_key} - {end_key} 的JSON时发生错误: {e}")
            debug_filename = f"llm_extraction_error_batch_{start_key}-{end_key}.json"
            try:
                with open(debug_filename, "w", encoding="utf-8") as f:
                    f.write(response_content)
                print(f"   └── 该批次的错误响应已保存到 '{debug_filename}'。")
            except Exception as write_e:
                print(f"   └── 尝试写入该批次的错误响应失败: {write_e}")
            print(f"收到的部分内容: {response_content[:200]}...")
            return None

    async def run_html_correction_batch(self, html_chunk_to_correct: str) -> str:
        """运行HTML修正智能体，对初步生成的HTML片段进行审查和修正。"""
        if not self.client: return html_chunk_to_correct
        print(f"--- (异步) 正在调用 LLM 修正一节HTML片段... ---")
        user_content = (
            f"请根据你的指令，审查并修正以下HTML代码片段:\n"
            f"--- HTML代码开始 ---\n{html_chunk_to_correct}\n--- HTML代码结束 ---"
        )
        try:
            response = await self.client.chat.completions.create(
                model="deepseek-chat", # MODIFIED: 强制使用 deepseek-chat
                messages=[
                    {"role": "system", "content": HTML_CORRECTOR_PROMPT},
                    {"role": "user", "content": user_content}
                ],
                temperature=0.0,
                max_tokens=8192, # MODIFIED: 统一 max_tokens
                timeout=180.0
            )
            corrected_html = response.choices[0].message.content
            # 简单的健全性检查
            if len(corrected_html) < 0.5 * len(html_chunk_to_correct):
                print(f"--- ⚠️ 修正结果异常(过短)，将使用原始HTML片段。 ---")
                return html_chunk_to_correct
            print(f"--- ✅ LLM 成功修正了一节HTML片段。 ---")
            return corrected_html
        except Exception as e:
            print(f"\n❌ 错误: 调用 LLM 修正HTML时发生API错误: {e}")
            print(f"--- 将使用原始（未经修正的）HTML片段进行下一步。 ---")
            return html_chunk_to_correct