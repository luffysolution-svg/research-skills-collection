# Research Skills Collection / 科研 Skills 分类合集

按科研、开发和内容创作场景整理的 Agent Skills 导航与离线合集，适用于
Claude Code、Codex 及兼容 `SKILL.md` 的 Agent。

当前公开版本包含 **241 个 skills**：其中 240 个来自 **16 个上游项目**，
1 个为本仓库原创。

> 本仓库以分类整理为主；除明确标注为“本仓库原创”的 skills 外，其余项目仍归
> 原作者所有，并遵循其自己的许可证。使用前请阅读
> [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 目录

```text
科研/
  文献检索与引用skills/
  文献写作skills/
  作图skills/
  数据分析与处理skills/
  生化环材skills/
    生物skills/
    化学skills/
    环境skills/
    材料skills/
  办公专用skills/
  构思skills/
  审核skills/
  文献管理skills/
  物理与量子skills/
  财政经济skills/
  计算基础设施skills/
开发/
  前端设计skills/
  Agent与技能开发skills/
  技术文档与知识检索skills/
内容创作/
  选题与趋势研究skills/
  人物视角与表达skills/
```

每个分类下面按上游项目分组，用于隔离跨仓库同名技能。

## 分类统计

| 分类 | 数量 |
|---|---:|
| 科研/文献检索与引用 | 13 |
| 科研/文献写作 | 13 |
| 科研/作图 | 20 |
| 科研/数据分析与处理 | 27 |
| 科研/生物 | 49 |
| 科研/化学 | 12 |
| 科研/环境 | 2 |
| 科研/材料 | 1 |
| 科研/办公专用 | 24 |
| 科研/构思 | 7 |
| 科研/审核 | 7 |
| 科研/文献管理 | 13 |
| 科研/物理与量子 | 5 |
| 科研/财政经济 | 1 |
| 科研/计算基础设施 | 2 |
| 开发/前端设计 | 17 |
| 开发/Agent 与技能开发 | 7 |
| 开发/技术文档与知识检索 | 4 |
| 内容创作/选题与趋势研究 | 1 |
| 内容创作/人物视角与表达 | 16 |

## 使用方式

推荐按平台使用原生插件或 Skills CLI 安装，而不是直接复制整个分类仓库：

- [Claude Code 与 Codex 安装指南](INSTALL-Claude-Code-and-Codex.md)
- 只想使用某个 skill 时，也可以进入对应目录，复制完整技能文件夹。

分类层级不是标准运行时目录。不要把 `科研/`、`开发/` 或 `内容创作/` 整体直接
放进 Agent 的 skills 目录；应复制最内层包含 `SKILL.md` 的技能目录。

## 来源项目

| 项目 | 收录数量 |
|---|---:|
| [Imbad0202/academic-research-skills](https://github.com/Imbad0202/academic-research-skills) | 4 |
| [anthropics/skills](https://github.com/anthropics/skills) | 14 |
| [JimLiu/baoyu-skills](https://github.com/JimLiu/baoyu-skills) | 22 |
| [upstash/context7](https://github.com/upstash/context7) | 4 |
| [jgraph/drawio-mcp](https://github.com/jgraph/drawio-mcp) | 1 |
| [op7418/guizang-ppt-skill](https://github.com/op7418/guizang-ppt-skill) | 1 |
| [blader/humanizer](https://github.com/blader/humanizer) | 1 |
| [mvanhorn/last30days-skill](https://github.com/mvanhorn/last30days-skill) | 1 |
| [opendatalab/MinerU-Document-Explorer](https://github.com/opendatalab/MinerU-Document-Explorer) | 1 |
| [opendatalab/MinerU-Ecosystem](https://github.com/opendatalab/MinerU-Ecosystem) | 1 |
| [Yuan1z0825/nature-skills](https://github.com/Yuan1z0825/nature-skills) | 12 |
| [alchaincyf/nuwa-skill](https://github.com/alchaincyf/nuwa-skill) | 16 |
| [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills) | 5 |
| [hugohe3/ppt-master](https://github.com/hugohe3/ppt-master) | 1 |
| [K-Dense-AI/scientific-agent-skills](https://github.com/K-Dense-AI/scientific-agent-skills) | 143 |
| [Leonxlnx/taste-skill](https://github.com/Leonxlnx/taste-skill) | 13 |

## 本仓库原创 Skills

| Skill | 分类 | 说明 |
|---|---|---|
| `convert-documents-to-markdown` | 科研/办公专用 | 自动选择 MarkItDown、OCR 或 MinerU，将文档转换为经过验证的 Markdown |

## 未再分发的官方 Skills

以下内容只在安装指南中提供官方安装方法，不随本仓库再分发：

- Anthropic `docx`、`pdf`、`pptx`、`xlsx`：其随附许可证禁止复制和向第三方分发。
- OpenAI 官方 Zotero：通过 Codex `openai-curated` 插件安装。
- MinerU 主项目：它是 CLI，不是 `SKILL.md` 技能。

## 更新

更新某个项目时，请从上游仓库重新取得目标 skill，保留完整目录及其许可证文件，
替换对应分类目录，并同步更新本 README 的数量。具体流程见
[UPDATING.md](UPDATING.md)。

## 免责声明

本仓库提供目录分类、来源标注、安装说明及明确标注的原创 Skills，不提供任何
上游项目的担保。
医疗、法律、金融或实验安全相关内容必须由具备资质的人员复核。
