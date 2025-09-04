# LLM_LaTex_Check

[![GitHub Repo](https://img.shields.io/badge/GitHub-LLM_LaTex_Check-blue?logo=github)](https://github.com/PlacidusaxAlarak/LLM_LaTex_Check)

## 项目简介

**LLM_LaTex_Check** 是一个结合大语言模型（LLM）能力的 LaTeX 文档自动检查工具。项目旨在为学术、技术写作场景下的 LaTeX 文件提供智能化的语法校验、规范检测和自动修正建议。通过自动化检查和报告生成，帮助用户高效提升 LaTeX 文档的质量和规范性。

## 主要功能

- **LaTeX 语法自动检查**  
  自动解析并检测 LaTeX 文件的语法错误与结构问题，定位常见拼写、标签、环境配对等错误。

- **规范性检测与建议**  
  利用 LLM 分析文档结构与内容，给出格式、引用、排版等方面的优化建议。

- **批量处理支持**  
  可对多个 LaTeX 文件进行批量校验，提升多文档管理效率。

- **智能修正提示**  
  针对检测出的错误，结合 LLM 自动生成修正建议，辅助用户快速修复问题。

- **报告生成**  
  输出详细的检查结果与修正建议报告，支持 Markdown 或纯文本格式，便于跟踪与归档。

## 项目结构与各文件说明

```
LLM_LaTex_Check/
├── main.py                     # 项目主入口，负责参数解析、流程控制和模块调度。
├── checker/
│   └── latex_checker.py        # LaTeX 文件语法及规范性检查核心逻辑，包含错误识别与 LLM 分析。
├── report/
│   └── report_generator.py     # 检查结果的报告生成模块，支持多种输出格式。
├── requirements.txt            # Python 项目依赖包清单。
├── README.md                   # 项目说明文档。
```

### 文件详细用途

- **main.py**  
  作为项目启动入口，负责读取命令行参数、加载配置、调度各功能模块，并整合最终输出。

- **checker/latex_checker.py**  
  实现对 LaTeX 文件的结构遍历和语法检查，调用 LLM 进行智能分析，返回详细错误列表与建议。

- **report/report_generator.py**  
  根据检查模块的输出，生成结构化的校验报告，便于用户阅读和后续处理。

- **requirements.txt**  
  列出项目必需的第三方 Python 库，便于环境搭建和依赖管理。

- **README.md**  
  项目文档，包含简介、功能说明、安装与使用指引、文件用途说明等。

## 安装方法

1. 克隆项目仓库：
   ```bash
   git clone https://github.com/PlacidusaxAlarak/LLM_LaTex_Check.git
   cd LLM_LaTex_Check
   ```
2. 安装依赖（建议使用虚拟环境）：
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法

1. 将待检查的 LaTeX 压缩包（如 `arXiv-2505.00024v2.tar.gz`）放入项目根目录或指定路径。
2. 运行命令进行校验：
   ```bash
   python main.py --file your_document.tex
   ```
3. 查看终端输出或报告文件（如有设置）。

## 贡献指南

欢迎提交 Issue 或 Pull Request 对项目进行改进，贡献新功能或修复 Bug。请参考 [CONTRIBUTING.md](CONTRIBUTING.md) 了解详细流程和要求。

## License

本项目采用 MIT License，详见 [LICENSE](LICENSE)。

---

如有问题或建议，欢迎在 [GitHub Issues](https://github.com/PlacidusaxAlarak/LLM_LaTex_Check/issues) 交流！
