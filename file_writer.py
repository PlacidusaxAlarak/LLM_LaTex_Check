# file_writer.py

from pathlib import Path


def save_html_report(content: str, file_path: str):
    """
    将字符串内容保存到指定的HTML文件中。
    如果目录不存在，会自动创建。

    Args:
        content (str): 要保存的HTML字符串内容。
        file_path (str): 目标HTML文件的完整路径。

    Raises:
        Exception: 如果在写入文件时发生错误。
    """
    try:
        path = Path(file_path)
        # 使用 path.parent 确保父目录存在，如果不存在则创建
        path.parent.mkdir(parents=True, exist_ok=True)

        with open(path, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"✅ 报告已成功保存到: {file_path}")
    except Exception as e:
        print(f"❌ 保存文件到 '{file_path}' 时出错: {e}")
        raise  # 将异常向上抛出