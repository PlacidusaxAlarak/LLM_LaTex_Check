

# main.py

import os
import asyncio
import re
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any
import llm_agent
import latex_parser
import file_writer
import archive_handler

# --- 配置 ---
SOURCE_ARCHIVE_PATH = 'latex_source.gz'
EXTRACT_DIR = './data'
OUTPUT_HTML_FILE = 'references_analysis_report.html'
# MODIFIED: 将批处理大小设为1，为每个参考文献创建一个独立的并发任务
BATCH_SIZE = 1
REFERENCE_PARSING_BATCH_SIZE = 1

# --- HTML 模板 ---
HTML_HEADER = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>参考文献分析报告 - {title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6; color: #333; background-color: #f8f9fa; margin: 0; padding: 20px;
        }}
        .container {{
            max-width: 900px; margin: 0 auto; background-color: #fff; padding: 2rem;
            border-radius: 8px; box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        }}
        h1, h2, h3 {{ color: #0056b3; }}
        h1 {{ border-bottom: 2px solid #dee2e6; padding-bottom: 0.5rem; margin-bottom: 1rem; text-align: center; }}
        h2 em {{ font-weight: normal; color: #555; font-size: 0.8em; }}
        .reference-item {{
            margin-bottom: 2rem; padding: 1.5rem; border: 1px solid #e9ecef;
            border-radius: 6px; background-color: #ffffff; transition: box-shadow 0.3s ease;
        }}
        .reference-item:hover {{ box-shadow: 0 8px 16px rgba(0,0,0,0.1); }}
        blockquote {{
            margin: 0; padding: 1rem; background-color: #f8f9fa; border-left: 5px solid #007bff;
        }}
        ul {{ padding-left: 20px; }}
        li {{ margin-bottom: 0.5rem; }}
        code {{ background-color: #e9ecef; color: #d63384; padding: 2px 4px; border-radius: 3px; }}
        .citation-context li strong:first-child {{ color: #28a745; }} /* 章节, 前文, etc. */
        .citation-context strong {{ color: #d9534f; /* 高亮引文命令 */ }}
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


def extract_paper_title(latex_content: str) -> str:
    """从LaTeX源码中提取论文标题。"""
    match = re.search(r'\\title\{([^}]+)\}', latex_content, re.DOTALL)
    if match:
        # 清理常见的LaTeX换行符和其他命令
        title = match.group(1).replace('\\\\', ' ').replace('\n', ' ').strip()
        return re.sub(r'\s+', ' ', title)
    return "未找到标题"


def render_html_from_data(all_references_data: list[dict]) -> str:
    """从LLM返回的结构化数据列表中渲染HTML内容。"""
    html_parts = []
    # 按ID排序以保持原始参考文献顺序
    sorted_data = sorted(all_references_data, key=lambda x: x.get('id', 0))

    for item in sorted_data:
        key = item.get("key", "N/A")
        # 优化标题和作者的获取逻辑
        title = item.get("inferred_title", item.get("title", "N/A"))
        author = item.get("inferred_author", "作者信息未提取")
        source = item.get("inferred_source", item.get("content", ""))

        item_html = f'<div class="reference-item">\n'
        item_html += f'    <h3>参考文献: <code>{key}</code></h3>\n'
        item_html += f'    <blockquote>\n'
        item_html += f'        <p><strong>作者:</strong> {author}</p>\n'
        item_html += f'        <p><strong>标题:</strong> {title}</p>\n'
        item_html += f'        <p><strong>来源:</strong> {source}</p>\n'
        item_html += f'    </blockquote>\n'
        item_html += '    <h4>引用位置:</h4>\n'

        if item.get("analysis_failed"):
            item_html += '<p><em style="color: red;">此参考文献的上下文分析失败（可能是由于API错误或内容问题）。</em></p>\n'
        elif not item.get("citations"):
            item_html += '<p><em>正文中未找到有效引用。</em></p>\n'
        else:
            item_html += '    <ul>\n'
            for i, citation in enumerate(item.get("citations", []), 1):
                section = citation.get("section", "Unknown Section")
                pre_context = citation.get("pre_context", "")
                citation_sentence = citation.get("citation_sentence", "")
                # 高亮引文命令
                citation_sentence_html = re.sub(
                    r'(\\(?:cite|citep|citet|Citep|Citet|citealt)\*?\{[^}]*?' + re.escape(key) + r'[^}]*?\})',
                    r'<strong>\1</strong>', citation_sentence)
                post_context = citation.get("post_context", "")

                item_html += f'        <li>\n'
                item_html += f'            <strong>位置 {i}:</strong>\n'
                item_html += f'            <ul class="citation-context">\n'
                item_html += f'                <li><strong>章节:</strong> {section}</li>\n'
                item_html += f'                <li><strong>前文:</strong> {pre_context}</li>\n'
                item_html += f'                <li><strong>引文句:</strong> {citation_sentence_html}</li>\n'
                item_html += f'                <li><strong>后文:</strong> {post_context}</li>\n'
                item_html += f'            </ul>\n'
                item_html += f'        </li>\n'
            item_html += '    </ul>\n'

        item_html += '</div>\n'
        html_parts.append(item_html)

    return "".join(html_parts)


async def main() -> List[Dict[str, Any]]:
    """
    主函数，执行完整的、基于LLM的LaTeX参考文献分析流程。
    """
    load_dotenv(".env")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误：请在.env文件中设置DEEPSEEK_API_KEY。")
        return []

    agent = llm_agent.LLMAgent(api_key=api_key)

    try:
        # 步骤 1: 解压归档文件
        print(f"步骤 1: 正在解压 '{SOURCE_ARCHIVE_PATH}'...")
        archive_handler.extract_archive(SOURCE_ARCHIVE_PATH, EXTRACT_DIR)

        # 步骤 2: 智能整合LaTeX源文件
        print("\n步骤 2: 正在智能整合所有LaTeX源文件...")
        full_latex_content, main_file = latex_parser.get_full_latex_source_and_main_file(EXTRACT_DIR)
        if not full_latex_content or not main_file:
            print("错误：无法整合LaTeX源文件或找到主文件，流程中止。")
            return []

        # 步骤 2.5: 自动提取论文标题
        paper_title = extract_paper_title(full_latex_content)
        print(f"\n✅ 自动提取到论文标题: {paper_title}")

        # 步骤 3: 使用LLM智能解析参考文献列表 (批处理模式)
        print("\n步骤 3: 正在使用LLM智能解析参考文献列表 (批处理模式)...")
        references_text_block = latex_parser.extract_raw_references_text(full_latex_content, main_file)

        bib_items_raw = re.split(r'\\bibitem', references_text_block)[1:]
        bib_items = ["\\bibitem" + item for item in bib_items_raw if item.strip()]

        if not bib_items:
            print("❌ 致命错误: 未能从.bbl文件内容中拆分出任何 \\bibitem 条目。")
            return []

        print(f"   └── 已将 .bbl 内容拆分为 {len(bib_items)} 个独立的参考文献条目。")

        parsing_tasks = []
        for i in range(0, len(bib_items), REFERENCE_PARSING_BATCH_SIZE):
            batch_of_bib_items = bib_items[i:i + REFERENCE_PARSING_BATCH_SIZE]
            batch_content = "".join(batch_of_bib_items)
            print(f"  - 创建参考文献解析批次: 条目 {i + 1} 到 {i + len(batch_of_bib_items)}")
            task = agent.run_reference_parser(batch_content)
            parsing_tasks.append(task)

        parsed_batches = await asyncio.gather(*parsing_tasks)

        all_references = []
        for batch_result in parsed_batches:
            all_references.extend(batch_result)

        for i, ref in enumerate(all_references, 1):
            ref['id'] = i

        if not all_references:
            print("❌ 致命错误: LLM未能解析出任何参考文献。工作流程中止。")
            return []

        total_refs = len(all_references)
        print(f"✅ LLM成功提取并结构化了 {total_refs} 条参考文献及其标题。")

        # 步骤 4: 创建并发提取任务批次
        print(f"\n步骤 4: 将为每个参考文献创建一个独立的并发分析任务...")
        extraction_tasks = []
        extraction_batches_info = []
        for i in range(0, total_refs, BATCH_SIZE):
            batch_of_refs = all_references[i:i + BATCH_SIZE]
            task = agent.run_extraction_batch(
                full_latex_source=full_latex_content,
                references_batch=batch_of_refs,
            )
            extraction_tasks.append(task)
            extraction_batches_info.append(batch_of_refs)

        # 步骤 5: 并发执行所有上下文提取任务 (获取JSON数据)
        print(f"\n步骤 5: 正在并发执行 {len(extraction_tasks)} 个详细分析任务 (生成JSON)...")
        structured_data_chunks = await asyncio.gather(*extraction_tasks)
        print("✅ 所有提取批次分析完成。")

        # 合并所有批次的结果，并处理失败的批次
        final_data_map = {ref['key']: ref for ref in all_references}

        for i, chunk in enumerate(structured_data_chunks):
            batch_info = extraction_batches_info[i]
            if chunk is None:  # 如果 run_extraction_batch 返回 None 表示失败
                start_key = batch_info[0]['key']
                end_key = batch_info[-1]['key']
                print(f"   └── ⚠️ 参考文献 {start_key} 分析失败，将在报告中标记。")
                for ref in batch_info:
                    final_data_map[ref['key']]['analysis_failed'] = True
                continue

            for result in chunk.get("analysis_results", []):
                key = result.get('key')
                if key in final_data_map:
                    final_data_map[key].update(result)

        # 步骤 6: 从结构化数据渲染HTML报告并保存
        print("\n步骤 6: 正在从结构化数据渲染并保存最终的HTML报告...")
        full_html_content = render_html_from_data(list(final_data_map.values()))
        header = HTML_HEADER.format(title=paper_title)
        footer = HTML_FOOTER.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        final_html_report = header + full_html_content + footer
        file_writer.save_html_report(final_html_report, OUTPUT_HTML_FILE)

        # 步骤 7: 构建并返回最终的结构化数据
        output_reference_data = []
        for key, data in final_data_map.items():
            sections = sorted(list(set(
                citation.get('section', 'Unknown Section') for citation in data.get('citations', [])
            )))
            output_reference_data.append({
                "key": key,
                "title": data.get("title", "Title not found"),
                "sections": sections
            })

        print(f"\n🎉 工作流程完成！请在浏览器中打开 '{OUTPUT_HTML_FILE}' 查看报告。")
        return output_reference_data

    except Exception as e:
        print(f"\n❌ 发生意外的致命错误: {e}")
        import traceback
        traceback.print_exc()
        return []


if __name__ == "__main__":
    reference_data = asyncio.run(main())

    if reference_data:
        print("\n--- 提取出的参考文献代号、标题与引用章节映射 ---")
        print(f"变量类型: {type(reference_data)}")
        print(f"总数: {len(reference_data)}")

        print("\n内容预览:")
        for item in reference_data[:10]:
            sections_str = ", ".join(item.get('sections', ['N/A']))
            if not sections_str: sections_str = "无有效引用"
            print(f"  - {item['key']}: {item['title']}")
            print(f"    └── 引用章节: {sections_str}")
    else:
        print("\n--- 未能提取出任何参考文献数据。 ---")