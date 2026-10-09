# EndNote Cite Paper

给已经写好的 Word 论文或基金标书补充经过核验的参考文献的 Codex 技能。默认保留原有正文、公式、图片和表格，完成引用插入、参考文献整理和交付检查。

## 功能

- 提取 DOCX 段落，定位需要外部证据支持的论述。
- 获取 Crossref 候选文献，核验书目信息和文献对具体论述的支持程度。
- 建立引用位置与文献的映射，支持普通编号引用和可编辑的 EndNote CWYW 引用。
- 生成 EndNote 导入文件，插入临时引用，检查 Word 中的 EndNote 字段。
- 比较修改前后的正文、公式和嵌入对象，要求对最终排版进行视觉检查。

普通编号引用不要求安装 EndNote。可编辑的 EndNote 引用需要本机的 Microsoft Word、EndNote 和 CWYW 插件；本仓库包含 Windows 环境检查脚本，原生格式化仍需按技能中的流程执行。

## 安装

将整个仓库放入 Codex 的技能目录。使用自定义 `CODEX_HOME` 时，安装到该目录下的 `skills/endnote-cite-paper`。

Windows PowerShell：

```powershell
git clone https://github.com/lunarfairy/endnote-cite-paper.git "$env:USERPROFILE\.codex\skills\endnote-cite-paper"
```

macOS / Linux：

```sh
git clone https://github.com/lunarfairy/endnote-cite-paper.git ~/.codex/skills/endnote-cite-paper
```

如果已有同名技能目录，请选择空目录下载或先备份已有版本。

运行 Python 辅助脚本需要 Python 3 和 `lxml`。进入仓库目录后安装依赖：

```sh
python -m pip install -r requirements.txt
```

## 使用

在 Codex 中提供 Word 文件，并指定格式和交付要求，例如：

> 用 $endnote-cite-paper 给这份 Word 论文补参考文献，正文不改。检索并核验文献，按首次出现顺序编号，交付新的 DOCX。

需要 EndNote 可编辑字段时：

> 用 $endnote-cite-paper 给这份标书补参考文献，保留正文和公式，使用 EndNote 可编辑引用，并核验引用字段与参考文献列表。

完整流程、输入表结构和检查要求见 [SKILL.md](SKILL.md)。Crossref 获取结果是候选记录；正式插入前需分别核验文献身份、元数据和具体论述的支持关系。

## 仓库内容

- `SKILL.md`：技能入口与交付要求。
- `agents/openai.yaml`：Codex 技能显示信息。
- `scripts/`：DOCX 提取、文献元数据获取、映射、引用插入和验证脚本。
- `references/`：文献核验、引用适配、EndNote CWYW 和内容保留说明。
- `tests/`：使用合成 DOCX 和模拟 HTTP 响应的回归测试。

运行现有测试：

```sh
python -m unittest discover -s tests -v
```

这些测试不启动 Word 或 EndNote，也不访问实际的文献服务。
