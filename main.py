# --- START OF FILE main.py (MODIFIED) ---

import os
import asyncio
import re
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any, Optional
from pathlib import Path

# NEW: 从 langchain_analysis_tool.py 移动过来的导入
from langchain_core.tools import tool
from langchain_core.pydantic_v1 import BaseModel, Field

import llm_agent
from latex_parser import LatexProjectParser, find_bib_file_paths, parse_bib_files, extract_references_from_bbl
import file_writer
import archive_handler
import cache_handler

# --- 配置 ---
EXTRACT_DIR = './data'
OUTPUT_HTML_FILE = 'references_analysis_report.html'
BATCH_SIZE = 1
REFERENCE_PARSING_BATCH_SIZE = 1

# --- HTML 模板 (保持不变) ---
HTML_HEADER = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>参考文献分析报告 - {title}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif; line-height: 1.6; color: #333; background-color: #f8f9fa; margin: 0; padding: 20px; }}
        .container {{ max-width: 900px; margin: 0 auto; background-color: #fff; padding: 2rem; border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1); }}
        h1, h2, h3 {{ color: #0056b3; }}
        h1 {{ border-bottom: 2px solid #dee2e6; padding-bottom: 0.5rem; margin-bottom: 1rem; text-align: center; }}
        h2 em {{ font-weight: normal; color: #555; font-size: 0.8em; }}
        .reference-item {{ margin-bottom: 2rem; padding: 1.5rem; border: 1px solid #e9ecef; border-radius: 6px; background-color: #ffffff; transition: box-shadow 0.3s ease; }}
        .reference-item:hover {{ box-shadow: 0 8px 16px rgba(0,0,0,0.1); }}
        blockquote {{ margin: 0; padding: 1rem; background-color: #f8f9fa; border-left: 5px solid #007bff; }}
        ul {{ padding-left: 20px; }}
        li {{ margin-bottom: 0.5rem; }}
        code {{ background-color: #e9ecef; color: #d63384; padding: 2px 4px; border-radius: 3px; }}
        .citation-context li strong:first-child {{ color: #28a745; }}
        .citation-context strong {{ color: #d9534f; }}
        .footer {{ text-align: center; margin-top: 2rem; font-size: 0.9em; color: #6c757d; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>参考文献上下文分析报告</h1>
        <h2>论文: <em>{title}</em></h2>
"""
HTML_FOOTER = """
    </div>
    <div class="footer">
        <p>报告生成于: {timestamp}</p>
    </div>
</body>
</html>
"""


# NEW: 从 langchain_analysis_tool.py 移动过来的 Pydantic 模型
class LatexAnalysisInput(BaseModel):
    """用於 LaTeX 分析工具的輸入模型。"""
    archive_path: str = Field(description="必須是指向 LaTeX 項目歸檔文件（如 .zip, .tar.gz）的有效路徑。")


def _clean_latex_for_llm(latex_content: str) -> str:
    # ... (此函数保持不变) ...
    print("   └── 正在对LaTeX源码进行预清理以优化分析...")
    cleaned_content = re.sub(r'(?<!\\)%.*\n', '\n', latex_content)
    cleaned_content = re.sub(r'\\begin{comment}(.*?)\\end{comment}', '', cleaned_content, flags=re.DOTALL)
    return cleaned_content


def render_html_from_data(all_references_data: list[dict]) -> str:
    # ... (此函数保持不变) ...
    html_parts = []
    sorted_data = sorted(all_references_data, key=lambda x: x.get('id', 0))
    for item in sorted_data:
        key = item.get("key", "N/A")
        title = item.get("inferred_title", item.get("title", "N/A"))
        author = item.get("inferred_author", "作者信息未提取")
        source = item.get("inferred_source", item.get("content", ""))

        item_html = f'<div class="reference-item"><h3>参考文献: <code>{key}</code></h3><blockquote><p><strong>作者:</strong> {author}</p><p><strong>标题:</strong> {title}</p><p><strong>来源:</strong> {source}</p></blockquote><h4>引用位置:</h4>'

        if item.get("analysis_failed"):
            item_html += '<p><em style="color: red;">此参考文献的上下文分析失败。</em></p>'
        elif not item.get("citations"):
            item_html += '<p><em>正文中未找到有效引用。</em></p>'
        else:
            item_html += '<ul>'
            for i, citation in enumerate(item.get("citations", []), 1):
                section = citation.get("section", "Unknown Section")
                pre_context = citation.get("pre_context", "")
                citation_sentence = citation.get("citation_sentence", "")

                escaped_key = re.escape(key)
                pattern = r'(\\(?:cite|citep|citet|autocite)\*?\{[^{}]*?' + escaped_key + r'[^}]*?\})'
                citation_sentence_html = re.sub(pattern, r'<strong>\1</strong>', citation_sentence)

                post_context = citation.get("post_context", "")
                item_html += f'<li><strong>位置 {i}:</strong><ul class="citation-context"><li><strong>章节:</strong> {section}</li><li><strong>前文:</strong> {pre_context}</li><li><strong>引文句:</strong> {citation_sentence_html}</li><li><strong>后文:</strong> {post_context}</li></ul></li>'
            item_html += '</ul>'

        item_html += '</div>'
        html_parts.append(item_html)

    return "".join(html_parts)


async def get_references_from_llm(agent: llm_agent.LLMAgent, text_block: str) -> List[Dict]:
    # ... (此函数保持不变) ...
    bib_items_raw = re.split(r'\\bibitem', text_block)[1:]
    bib_items = ["\bibitem" + item for item in bib_items_raw if item.strip()]
    if not bib_items:
        return []

    print(f"   └── 已将内容拆分为 {len(bib_items)} 个独立的参考文献条目，交由LLM处理。")
    tasks = [agent.run_reference_parser("".join(bib_items[i:i + REFERENCE_PARSING_BATCH_SIZE])) for i in
             range(0, len(bib_items), REFERENCE_PARSING_BATCH_SIZE)]
    parsed_batches = await asyncio.gather(*tasks)

    return [ref for batch in parsed_batches for ref in batch]


# MODIFIED: 将原来的 main 函数重构为 LangChain Tool
@tool(args_schema=LatexAnalysisInput)
async def analyze_latex_references(archive_path: str) -> str:
    """
    分析指定的 LaTeX 項目歸檔文件，以提取所有參考文獻並找出它們在正文中的引用上下文。

    此工具會執行以下操作：
    1. 解壓歸檔文件。
    2. 智能合併所有 .tex 源文件。
    3. 解析參考文獻列表（來自 .bib 或 .bbl 文件）。
    4. 使用 LLM 遍歷源代碼，為每篇參考文獻定位所有引用點及其上下文。
    5. 生成一份詳細的 HTML 報告。

    成功時返回報告路徑和摘要；失敗時返回錯誤信息。
    """
    print(f"--- 🚀 LangChain Tool: 'analyze_latex_references' 已啟動 ---")
    print(f"--- 🎯 輸入文件: {archive_path} ---")

    load_dotenv(".env")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        error_msg = "错误：请在.env文件中设置DEEPSEEK_API_KEY。"
        print(f"--- ❌ 工具执行失败 ---")
        print(error_msg)
        return error_msg

    cache_handler.ensure_cache_dir_exists()
    agent = llm_agent.LLMAgent(api_key=api_key)

    try:
        # MODIFIED: 直接使用传入的 archive_path，移除了自动查找文件的逻辑
        source_archive_path = Path(archive_path)
        if not source_archive_path.exists():
            raise FileNotFoundError(f"指定的归档文件未找到: {archive_path}")

        print(f"✅ 使用源归档文件: {source_archive_path.name}")

        # Step 1: 解压
        print(f"\n步骤 1: 正在解压...", flush=True)
        archive_handler.extract_archive(str(source_archive_path), EXTRACT_DIR)

        # Step 2: 解析项目结构
        print(f"\n步骤 2: 正在解析项目结构...", flush=True)
        parser = LatexProjectParser(EXTRACT_DIR)
        parser.parse()

        full_latex_content = parser.latex_verbatim_content
        if not full_latex_content or not parser.main_file:
            raise RuntimeError("解析项目失败，无法获取完整内容或主文件。")

        cleaned_latex_content = _clean_latex_for_llm(full_latex_content)

        # Step 3: 解析参考文献
        print("\n步骤 3: 正在解析参考文献...", flush=True)
        all_references = []
        if parser.bib_file_names:
            print("   └── 策略: 找到 .bib 文件引用，使用 bibtexparser 精准解析。")
            bib_paths = find_bib_file_paths(parser.bib_file_names, Path(EXTRACT_DIR))
            if bib_paths:
                all_references, _ = parse_bib_files(bib_paths)

        if not all_references:
            print("   └── 策略: 回退到LLM解析 .bbl 或 .tex 内容。")
            references_text_block = parser.the_bibliography_content or extract_references_from_bbl(parser.main_file)
            if not references_text_block:
                raise ValueError("在项目中找不到任何参考文献信息。")
            all_references = await get_references_from_llm(agent, references_text_block)

        if not all_references:
            raise ValueError("未能解析出任何参考文献。")

        for i, ref in enumerate(all_references, 1):
            ref['id'] = i
        total_refs = len(all_references)
        print(f"✅ 成功获得 {total_refs} 条结构化参考文献。")

        # Step 4 & 5: 并发分析引用上下文
        print(f"\n步骤 4 & 5: 正在并发分析引用上下文...", flush=True)
        tasks = [agent.run_extraction_batch(cleaned_latex_content, [ref]) for ref in all_references]
        structured_data_chunks = await asyncio.gather(*tasks)

        # Step 6: 合并结果并生成报告
        print("\n步骤 6: 正在合并结果并生成报告...", flush=True)
        final_data_map = {ref['key']: ref for ref in all_references}
        successful_extractions = 0

        for i, chunk in enumerate(structured_data_chunks):
            ref_key = all_references[i]['key']
            if chunk and (results_list := chunk.get("analysis_results")) and isinstance(results_list, list) and len(
                    results_list) > 0:
                result_data = results_list[0]
                if (key := result_data.get('key')) in final_data_map:
                    if result_data.get("citations"):
                        successful_extractions += 1
                    final_data_map[key].update(result_data)
            else:
                final_data_map[ref_key]['analysis_failed'] = True

        print(f"--- 分析摘要: 在 {total_refs} 个参考文献中，有 {successful_extractions} 个成功找到了至少一处引用。---")

        full_html = render_html_from_data(list(final_data_map.values()))
        title = parser.paper_title if parser.paper_title != "未找到标题" else "未命名文档"
        header = HTML_HEADER.format(title=title)
        footer = HTML_FOOTER.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        file_writer.save_html_report(header + full_html + footer, OUTPUT_HTML_FILE)

        print(f"\n🎉 工作流程完成！请在浏览器中打开 '{OUTPUT_HTML_FILE}' 查看报告。")

        # MODIFIED: 返回对 Agent 友好的字符串摘要
        summary = f"✅ 成功完成对 '{archive_path}' 的分析。报告已保存至 '{OUTPUT_HTML_FILE}'。共找到并处理了 {len(all_references)} 条参考文獻。"
        print(f"--- ✨ 工具执行成功 ---")
        print(summary)
        return summary

    except Exception as e:
        import traceback
        traceback.print_exc()
        error_summary = f"❌ 在分析 '{archive_path}' 過程中發生嚴重錯誤: {e}"
        print(f"--- 💥 工具执行时发生异常 ---")
        print(error_summary)
        return error_summary


# MODIFIED: 更新 main block 以便直接测试新的 LangChain tool
async def example_usage():
    """展示如何直接調用這個 LangChain 工具。"""
    from pathlib import Path
    supported_extensions = ('.zip', '.tar', '.gz', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2')
    project_dir = Path('.')
    found_archives = [p for p in project_dir.iterdir() if p.is_file() and str(p.name).endswith(supported_extensions)]

    if not found_archives:
        print("\n--- 示例運行失敗 ---")
        print("請在項目根目錄下放置一個 LaTeX 項目的 .zip 或 .tar.gz 歸檔文件以運行此示例。")
        return

    example_archive_path = str(found_archives[0])
    print("\n" + "=" * 50)
    print("      展示如何調用已在 main.py 中定义的 LangChain Tool")
    print("=" * 50)

    # 模拟 LangChain Agent 調用工具
    result = await analyze_latex_references.ainvoke({"archive_path": example_archive_path})

    print("\n--- 工具返回的最終結果 ---")
    print(result)
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(example_usage())