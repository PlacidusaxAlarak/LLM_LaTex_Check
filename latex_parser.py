import re
import os
from pathlib import Path


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

        return re.sub(r'^[ \t]*\\(input|subfile){([^}]+)}', replacer, content, flags=re.MULTILINE)

    all_files = find_all_tex_files()
    if not all_files:
        print("❌ 错误: 在解压目录中找不到任何 .tex 文件。")
        return "", None

    main_file = find_main_tex_file(all_files)
    full_content = combine_recursively(main_file)
    return full_content, main_file


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