# --- START OF FILE latex_parser.py (MODIFIED) ---

import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Set, Optional, Tuple

import bibtexparser
from pylatexenc.latexwalker import LatexWalker, LatexMacroNode, LatexEnvironmentNode
from pylatexenc.latex2text import LatexNodes2Text

# --- MODIFIED: 设置pylatexenc的日志级别，以减少控制台噪音 ---
logging.getLogger('pylatexenc').setLevel(logging.WARNING)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


# --- NEW: Helper function to pre-clean LaTeX content for parsing ---
def _clean_latex_for_pylatexenc(latex_content: str) -> str:
    """
    一个专注的清理函数，仅移除可能干扰pylatexenc解析器的注释。
    这对于处理参数内部的注释（如 \title{...%...}）至关重要。
    """
    # 使用 re.MULTILINE 标志来确保 `$` 匹配每行的末尾
    cleaned_content = re.sub(r'(?<!\\)%.*$', '', latex_content, flags=re.MULTILINE)
    return cleaned_content


class LatexProjectParser:
    """
    一个使用 `pylatexenc` 并增加了正则回退机制的高级 LaTeX 项目解析器。
    """

    def __init__(self, base_dir_str: str):
        self.base_dir = Path(base_dir_str)
        if not self.base_dir.is_dir():
            raise NotADirectoryError(f"提供的路径不是一个有效的目录: {self.base_dir}")

        self.main_file: Optional[Path] = None
        self.processed_files: Set[Path] = set()
        self.paper_title: str = "未找到标题"
        self.bib_file_names: List[str] = []
        self.the_bibliography_content: str = ""
        self._verbatim_parts: List[str] = []

    def parse(self) -> None:
        """
        执行完整解析流程，包括文件查找、结构化解析和正则表达式回退。
        """
        main_tex_file = self._find_main_tex_file()
        if not main_tex_file:
            logger.error(f"在目录 '{self.base_dir}' 中找不到主 .tex 文件。")
            return

        self.main_file = main_tex_file
        logger.info(f"找到主文件: {main_tex_file.relative_to(self.base_dir)}")
        self._parse_file_and_extract_metadata(main_tex_file)

        # --- MODIFIED: 统一在此处应用所有正则表达式回退逻辑 ---

        full_content = self.latex_verbatim_content

        # 回退逻辑 1: 解析 \bibliography
        if not self.bib_file_names:
            logger.warning("pylatexenc未能提取到 .bib 文件名，尝试使用正则表达式进行回退扫描...")
            matches = re.findall(r'\\bibliography\{([^}]+)\}', full_content)
            if matches:
                bib_names = []
                for match in matches:
                    bib_names.extend([b.strip() for b in match.split(',')])
                self.bib_file_names = list(set(bib_names))
                logger.info(f"✅ 正则表达式成功提取到 .bib 文件名: {self.bib_file_names}")
            else:
                logger.warning("正则表达式也未能找到 \\bibliography 命令。")

        # 回退逻辑 2: 解析 \title (作为双重保险)
        if self.paper_title == "未找到标题":
            logger.warning("pylatexenc未能提取到论文标题，尝试使用正则表达式进行回退扫描...")
            # 这个正则表达式可以处理跨行的标题
            match = re.search(r'\\title\s*\{((?:[^{}]|\{[^{}]*\})*)\}', full_content, re.DOTALL)
            if match:
                raw_title = match.group(1).strip()
                # 进一步清理，移除LaTeX命令，但这个过程可能不完美
                # 使用pylatexenc的工具进行清理是最可靠的方式
                try:
                    lw_cleaner = LatexWalker(raw_title)
                    nodelist, _, _ = lw_cleaner.get_latex_nodes()
                    cleaned_title = LatexNodes2Text().nodelist_to_text(nodelist).strip()
                except Exception:
                    # 如果清理失败，使用简单的正则清理作为备用
                    cleaned_title = re.sub(r'\\[a-zA-Z]+\*?\{?([^}]+?)\}?', r'\1', raw_title)
                    cleaned_title = cleaned_title.replace('\n', ' ').replace('\\', ' ').strip()

                self.paper_title = cleaned_title
                logger.info(f"✅ 正则表达式成功提取到标题: {self.paper_title}")
            else:
                logger.warning("正则表达式也未能找到 \\title 命令。")

        logger.info(f"解析完成。共处理 {len(self.processed_files)} 个文件。")

    @property
    def latex_verbatim_content(self) -> str:
        return "\n".join(self._verbatim_parts)

    def _find_main_tex_file(self) -> Optional[Path]:
        all_tex_files = list(self.base_dir.rglob('*.tex'))
        if not all_tex_files: return None
        main_files_candidates = []
        for p in all_tex_files:
            try:
                if p.stat().st_size > 5_000_000: continue
                content = p.read_text(encoding='utf-8', errors='ignore')
                if r'\documentclass' in content:
                    main_files_candidates.append((p, r'\begin{document}' in content))
            except Exception:
                continue
        if not main_files_candidates:
            logger.warning("未找到包含 \\documentclass 的文件，将使用找到的第一个 .tex 文件。")
            return all_tex_files[0]
        main_files_candidates.sort(key=lambda x: x[1], reverse=True)
        best_candidates = [p for p, has_doc in main_files_candidates if has_doc == main_files_candidates[0][1]]
        for preferred_name in ['main.tex', 'paper.tex', 'article.tex']:
            for f in best_candidates:
                if f.name.lower() == preferred_name: return f
        return best_candidates[0]

    def _parse_file_and_extract_metadata(self, tex_file_path: Path):
        if tex_file_path in self.processed_files or not tex_file_path.exists():
            return
        self.processed_files.add(tex_file_path)
        file_dir = tex_file_path.parent
        logger.info(f"正在处理文件: {tex_file_path.relative_to(self.base_dir)}")
        try:
            content = tex_file_path.read_text(encoding='utf-8', errors='ignore')

            # --- MODIFICATION: Pre-clean the content for the parser ---
            # 清理内容以进行结构化解析，这能解决参数内部注释的问题
            content_for_parsing = _clean_latex_for_pylatexenc(content)

            # 仍然将 *原始* 内容添加到 verbatim_parts，以保留完整的上下文给 LLM
            self._verbatim_parts.append(content)

            # 使用清理过的内容进行解析
            lw = LatexWalker(content_for_parsing)

            nodelist, _, _ = lw.get_latex_nodes(stop_on_error=False)
            for node in nodelist:
                if node.isNodeType(LatexMacroNode):
                    macro_name = node.macroname.rstrip('*')
                    if macro_name == 'title' and node.nodeargs:
                        self.paper_title = LatexNodes2Text().nodelist_to_text(node.nodeargs[0].nodelist).strip()
                    elif macro_name == 'bibliography' and node.nodeargs:
                        bib_files_str = LatexNodes2Text().nodelist_to_text(node.nodeargs[0].nodelist)
                        self.bib_file_names.extend([b.strip() for b in bib_files_str.split(',')])
                    elif macro_name in ('input', 'include') and node.nodeargs:
                        include_arg = LatexNodes2Text().nodelist_to_text(node.nodeargs[0].nodelist).strip()
                        if not include_arg.endswith('.tex'): include_arg += '.tex'
                        next_file_path = (file_dir / include_arg).resolve()
                        self._parse_file_and_extract_metadata(next_file_path)
                elif node.isNodeType(LatexEnvironmentNode):
                    if node.environmentname.rstrip('*') == 'thebibliography':
                        self.the_bibliography_content = node.latex_verbatim()
        except Exception as e:
            logger.error(f"无法读取或解析文件 {tex_file_path}: {e}", exc_info=False)


def find_bib_file_paths(bib_file_names: List[str], base_dir: Path) -> List[Path]:
    # ... (此函数保持不变) ...
    found_paths = []
    for name in bib_file_names:
        bib_file_name = f"{name}.bib" if not name.endswith('.bib') else name
        possible_paths = list(base_dir.rglob(f"**/{bib_file_name}"))
        if possible_paths:
            found_paths.append(possible_paths[0])
            logger.info(f"成功定位到 .bib 文件: {possible_paths[0].relative_to(base_dir)}")
        else:
            logger.warning(f"找不到指定的 .bib 文件: {bib_file_name}")
    return found_paths


def parse_bib_files(bib_paths: List[Path]) -> Tuple[List[Dict[str, Any]], str]:
    # ... (此函数保持不变) ...
    bib_database, full_bib_content, processed_keys = None, "", set()
    parser = bibtexparser.bparser.BibTexParser(common_strings=True)
    for bib_path in bib_paths:
        try:
            with open(bib_path, 'r', encoding='utf-8') as bibfile:
                content = bibfile.read()
                db = bibtexparser.loads(content, parser=parser)
                full_bib_content += content + "\n"
                unique_entries = []
                for entry in db.entries:
                    if (key := entry.get('ID')) and key not in processed_keys:
                        unique_entries.append(entry)
                        processed_keys.add(key)
                db.entries = unique_entries
                if bib_database is None:
                    bib_database = db
                else:
                    bib_database.entries.extend(db.entries)
        except Exception as e:
            logger.error(f"解析 .bib 文件 '{bib_path}' 时出错: {e}")
    if not bib_database or not bib_database.entries: return [], full_bib_content
    structured_references = []
    for entry in bib_database.entries:
        authors = re.sub(r'[\s\n]+', ' ', entry.get('author', '未知作者')).strip()
        title = re.sub(r'[\s\n]+', ' ', entry.get('title', '无标题').replace('{', '').replace('}', '')).strip()
        temp_db = bibtexparser.bibdatabase.BibDatabase();
        temp_db.entries = [entry]
        structured_references.append(
            {"key": entry.get('ID', 'N/A'), "inferred_title": title, "inferred_author": authors,
             "content": bibtexparser.dumps(temp_db)})
    logger.info(f"从 .bib 文件中成功解析并去重了 {len(structured_references)} 条参考文献。")
    return structured_references, full_bib_content


def extract_references_from_bbl(main_file_path: Path) -> Optional[str]:
    # ... (此函数保持不变) ...
    bbl_file_path = main_file_path.with_suffix('.bbl')
    if bbl_file_path.is_file():
        logger.info(f"找到了 BibTeX 生成的 .bbl 文件: {bbl_file_path.name}")
        try:
            return bbl_file_path.read_text(encoding='utf-8', errors='ignore')
        except Exception as e:
            logger.error(f"读取 .bbl 文件 '{bbl_file_path}' 时出错: {e}")
    return None

# --- END OF FILE latex_parser.py (MODIFIED) ---