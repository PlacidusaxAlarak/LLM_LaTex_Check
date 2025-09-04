import re
import os
from pathlib import Path
from typing import List, Tuple, Dict, Any
import bibtexparser

def get_full_latex_source_and_main_file(base_dir_str: str) -> tuple[str, Path | None]:
    """
    智能查找主文件并递归地将所有LaTeX源文件合并成一个单一的字符串。
    同时返回主文件的路径，以便后续查找 .bbl 文件。
    """
    base_dir = Path(base_dir_str)

    def find_all_tex_files() -> list[Path]:
        return list(base_dir.rglob('*.tex'))

    def find_main_tex_file(tex_files: list[Path]) -> Path:
        main_file_candidate = None
        for file_path in tex_files:
            try:
                content = file_path.read_text(encoding='utf-8', errors='ignore')
                if r'\documentclass' in content:
                    print(f"✅ 找到主文件候选: {file_path.name}")
                    if r'\begin{document}' in content:
                        print(f"   └── 确认其为最佳主文件。")
                        return file_path
                    if not main_file_candidate:
                        main_file_candidate = file_path
            except Exception:
                continue
        if main_file_candidate:
            print(f"   └── 将首个找到的候选文件作为主文件。")
            return main_file_candidate
        raise FileNotFoundError("在项目中找不到任何包含 `\\documentclass` 的 .tex 文件。")

    def combine_recursively(main_file_path: Path) -> str:
        try:
            content = main_file_path.read_text(encoding='utf-8', errors='ignore')
        except FileNotFoundError:
            return ""

        def replacer(match):
            included_file_name = match.group(2)
            if not included_file_name.endswith('.tex'):
                included_file_name += '.tex'
            path_relative_to_current = main_file_path.parent / included_file_name
            path_relative_to_root = base_dir / included_file_name
            found_path = None
            for path in [path_relative_to_current, path_relative_to_root]:
                if path.is_file():
                    found_path = path
                    break
            if found_path:
                print(f"  -> 正在包含: {found_path.relative_to(base_dir)}")
                return combine_recursively(found_path)
            else:
                print(f"  -> ⚠️ 警告: 找不到被包含的文件: {included_file_name}")
                return f"% FILE NOT FOUND: {match.group(0)}\n"
        # MODIFIED: Also handle \include
        return re.sub(r'^[ \t]*\\(input|subfile|include){([^}]+)}', replacer, content, flags=re.MULTILINE)

    all_files = find_all_tex_files()
    if not all_files:
        print("❌ 错误: 在解压目录中找不到任何 .tex 文件。")
        return "", None

    main_file = find_main_tex_file(all_files)
    full_content = combine_recursively(main_file)
    return full_content, main_file

def find_bib_file_paths(full_latex_content: str, base_dir: Path) -> List[Path]:
    """从LaTeX源码中找到\bibliography命令，并返回所有.bib文件的绝对路径列表。"""
    # \bibliography{ref1,ref2, ref3}
    bib_matches = re.findall(r'\\bibliography{([^}]+)}', full_latex_content)
    if not bib_matches:
        return []

    bib_file_names = []
    for match in bib_matches:
        bib_file_names.extend([name.strip() for name in match.split(',')])

    found_paths = []
    for name in bib_file_names:
        bib_file_name = f"{name}.bib"
        # 在整个项目目录中搜索.bib文件
        possible_paths = list(base_dir.rglob(bib_file_name))
        if possible_paths:
            found_paths.append(possible_paths[0])
            print(f"   └── 成功定位到 .bib 文件: {possible_paths[0].relative_to(base_dir)}")
        else:
            print(f"   └── ⚠️ 警告: 找不到指定的 .bib 文件: {bib_file_name}")

    return found_paths

def parse_bib_files(bib_paths: List[Path]) -> Tuple[List[Dict[str, Any]], str]:
    """使用bibtexparser解析多个.bib文件，并返回结构化的参考文献列表和原始文本。"""
    bib_database = None
    full_bib_content = ""

    for bib_path in bib_paths:
        try:
            with open(bib_path, 'r', encoding='utf-8') as bibfile:
                bib_content = bibfile.read()
                full_bib_content += bib_content + "\n"
                # Reset file pointer to read again with parser
                bibfile.seek(0)
                parser = bibtexparser.bparser.BibTexParser(common_strings=True)
                db = bibtexparser.load(bibfile, parser=parser)
                if bib_database is None:
                    bib_database = db
                else:
                    # TODO: More robust merging if keys conflict
                    bib_database.entries.extend(db.entries)
        except Exception as e:
            print(f"❌ 解析 .bib 文件 '{bib_path}' 时出错: {e}")
            return [], ""

    if not bib_database or not bib_database.entries:
        return [], full_bib_content

    structured_references = []
    for entry in bib_database.entries:
        # 清理和规范化作者字段
        authors = entry.get('author', '未知作者')
        # bibtexparser有时会保留换行符，需要清理
        authors = re.sub(r'\s+', ' ', authors).strip()

        # 清理标题字段中的花括号
        title = entry.get('title', '无标题')
        title = title.replace('{', '').replace('}', '')

        structured_references.append({
            "key": entry.get('ID', 'N/A'),
            "inferred_title": title,
            "inferred_author": authors,
            "content": bibtexparser.dumps([entry]) # 保留原始条目以供参考
        })

    return structured_references, full_bib_content

def extract_raw_references_text(full_latex_content: str, main_file: Path) -> str:
    """
    从完整的LaTeX源码中粗略提取参考文献区域的文本。
    智能处理两种情况：
    1. 直接在 .tex 文件中写的 thebibliography 环境。
    2. 使用 BibTeX, 参考文献在 .bbl 文件中。
    """
    # 策略 1: 优先在整合后的 .tex 源文件中寻找
    match = re.search(r'\\begin{thebibliography}', full_latex_content, re.DOTALL)
    if match:
        print("✅ 成功定位 'thebibliography' 环境起点 (在 .tex 文件中)。")
        return full_latex_content[match.start():]

    # 策略 2: 如果 .tex 中没有，则假定使用 BibTeX，并寻找 .bbl 文件
    print("ℹ️ 在 .tex 源文件中未找到 'thebibliography'，尝试寻找 .bbl 文件...")
    bbl_file_path = main_file.with_suffix('.bbl')

    if bbl_file_path.is_file():
        print(f"✅ 找到了 BibTeX 生成的 .bbl 文件: {bbl_file_path.name}")
        try:
            bbl_content = bbl_file_path.read_text(encoding='utf-8', errors='ignore')
            match_bbl = re.search(r'\\begin{thebibliography}', bbl_content, re.DOTALL)
            if match_bbl:
                print("   └── 成功从 .bbl 文件中提取参考文献内容。")
                return bbl_content[match_bbl.start():]
            else:
                raise ValueError(f"在 {bbl_file_path.name} 文件中找到了，但内部没有 'thebibliography' 环境。")
        except Exception as e:
            raise IOError(f"读取或解析 .bbl 文件 '{bbl_file_path}' 时出错: {e}")

    # 如果两种策略都失败
    raise ValueError("在整合后的LaTeX源码或对应的 .bbl 文件中都找不到 'thebibliography' 环境。")