import os
import asyncio
import re
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Dict, Any
from pathlib import Path
import llm_agent
import latex_parser
import file_writer
import archive_handler
import cache_handler

# --- 配置 ---
EXTRACT_DIR = './data'
OUTPUT_HTML_FILE = 'references_analysis_report.html'
BATCH_SIZE = 1
REFERENCE_PARSING_BATCH_SIZE = 1

# --- HTML 模板 (保持不变) ---
# MODIFICATION: Escaped CSS braces by doubling them up (e.g., { -> {{)
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

def extract_paper_title(latex_content: str) -> str:
    # No changes here
    match = re.search(r'\\title\{([^}]+)\}', latex_content, re.DOTALL)
    if match:
        title = match.group(1).replace('\\', ' ').replace('\n', ' ').strip()
        return re.sub(r'\s+', ' ', title)
    return "未找到标题"

def render_html_from_data(all_references_data: list[dict]) -> str:
    # No changes here
    html_parts = []
    sorted_data = sorted(all_references_data, key=lambda x: x.get('id', 0))
    for item in sorted_data:
        key = item.get("key", "N/A")
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
            item_html += '<p><em style="color: red;">此参考文献的上下文分析失败。</em></p>\n'
        elif not item.get("citations"):
            item_html += '<p><em>正文中未找到有效引用。</em></p>\n'
        else:
            item_html += '    <ul>\n'
            for i, citation in enumerate(item.get("citations", []), 1):
                section = citation.get("section", "Unknown Section")
                pre_context = citation.get("pre_context", "")
                citation_sentence = citation.get("citation_sentence", "")
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

async def get_references_from_llm(agent: llm_agent.LLMAgent, text_block: str) -> List[Dict]:
    # No changes here
    bib_items_raw = re.split(r'\bibitem', text_block)[1:]
    bib_items = ["\bibitem" + item for item in bib_items_raw if item.strip()]
    if not bib_items:
        print("❌ 致命错误: 未能从.bbl文件内容中拆分出任何 \bibitem 条目。")
        return []

    print(f"   └── 已将内容拆分为 {len(bib_items)} 个独立的参考文献条目，交由LLM处理。")
    parsing_tasks = []
    for i in range(0, len(bib_items), REFERENCE_PARSING_BATCH_SIZE):
        batch_of_bib_items = bib_items[i:i + REFERENCE_PARSING_BATCH_SIZE]
        batch_content = "".join(batch_of_bib_items)
        task = agent.run_reference_parser(batch_content)
        parsing_tasks.append(task)

    parsed_batches = await asyncio.gather(*parsing_tasks)
    all_references = []
    for batch_result in parsed_batches:
        all_references.extend(batch_result)
    return all_references

async def main() -> List[Dict[str, Any]]:
    # No changes here, the logic is sound
    load_dotenv(".env")
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("错误：请在.env文件中设置DEEPSEEK_API_KEY。")
        return []

    cache_handler.ensure_cache_dir_exists()
    agent = llm_agent.LLMAgent(api_key=api_key)

    try:
        supported_extensions = ('.zip', '.tar', '.gz', '.tar.gz', '.tgz', '.tar.bz2', '.tbz2')
        project_dir = Path('.')
        found_archives = [p for p in project_dir.iterdir() if p.is_file() and str(p.name).endswith(supported_extensions)]
        if not found_archives:
            print(f"❌ 错误: 未找到支持的归档文件。")
            return []
        source_archive_path = found_archives[0]
        print(f"✅ 自动检测到源归档文件: {source_archive_path.name}")

        print(f"\n步骤 1 & 2: 正在解压与整合源文件...", flush=True)
        archive_handler.extract_archive(str(source_archive_path), EXTRACT_DIR)
        full_latex_content, main_file = latex_parser.get_full_latex_source_and_main_file(EXTRACT_DIR)
        if not full_latex_content or not main_file:
            return []
        paper_title = extract_paper_title(full_latex_content)
        print(f"\n✅ 成功提取论文标题: {paper_title}")

        print("\n步骤 3: 正在解析参考文献...", flush=True)
        all_references = []
        try:
            bib_file_paths = latex_parser.find_bib_file_paths(full_latex_content, Path(EXTRACT_DIR))
            if bib_file_paths:
                print("   └── 策略: 找到 .bib 文件，使用 bibtexparser 精准解析。")
                parsed_refs, bib_content = latex_parser.parse_bib_files(bib_file_paths)
                if parsed_refs:
                    all_references = parsed_refs
                    cache_key = cache_handler.get_cache_key(bib_content)
                    cache_handler.set_to_cache(cache_key, all_references)
                else:
                    print("   └── ⚠️ .bib 文件解析失败或内容为空。")

            if not all_references:
                print("   └── 策略: 未使用.bib文件或解析失败，回退到LLM解析.bbl/.tex内容。")
                references_text_block = latex_parser.extract_raw_references_text(full_latex_content, main_file)
                all_references = await get_references_from_llm(agent, references_text_block)

        except ImportError:
            print("   └── ⚠️ 警告: `bibtexparser` 未安装。回退到LLM解析。")
            print("   └── 请运行 `pip install bibtexparser` 以获得更准确的解析结果。")
            references_text_block = latex_parser.extract_raw_references_text(full_latex_content, main_file)
            all_references = await get_references_from_llm(agent, references_text_block)

        if not all_references:
            print("❌ 致命错误: 未能解析出任何参考文献。工作流程中止。")
            return []

        for i, ref in enumerate(all_references, 1):
            ref['id'] = i
        total_refs = len(all_references)
        print(f"✅ 成功获得 {total_refs} 条结构化参考文献。")

        print(f"\n步骤 4 & 5: 正在并发分析 {total_refs} 条参考文献的引用上下文...", flush=True)
        extraction_tasks = [agent.run_extraction_batch(full_latex_content, [ref]) for ref in all_references]
        structured_data_chunks = await asyncio.gather(*extraction_tasks)

        print("\n步骤 6: 正在合并结果并生成HTML报告...", flush=True)
        final_data_map = {ref['key']: ref for ref in all_references}
        for i, chunk in enumerate(structured_data_chunks):
            ref_key = all_references[i]['key']
            if chunk is None:
                final_data_map[ref_key]['analysis_failed'] = True
                continue
            for result in chunk.get("analysis_results", []):
                key = result.get('key')
                if key in final_data_map:
                    final_data_map[key].update(result)

        full_html_content = render_html_from_data(list(final_data_map.values()))
        header = HTML_HEADER.format(title=paper_title)
        footer = HTML_FOOTER.format(timestamp=datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        file_writer.save_html_report(header + full_html_content + footer, OUTPUT_HTML_FILE)

        output_reference_data = []
        for key, data in final_data_map.items():
            sections = sorted(list(set(c.get('section', 'N/A') for c in data.get('citations', []))))
            output_reference_data.append({"key": key, "title": data.get("inferred_title", "N/A"), "sections": sections})

        print(f"\n🎉 工作流程完成！请在浏览器中打开 '{OUTPUT_HTML_FILE}' 查看报告。")
        return output_reference_data

    except Exception as e:
        print(f"\n❌ 发生意外的致命错误: {e}")
        import traceback
        traceback.print_exc()
        return []

if __name__ == "__main__":
    asyncio.run(main())