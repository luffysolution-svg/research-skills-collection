# 科研 Skills 分类合集

[English](README_EN.md) | 简体中文

面向科研、开发和内容创作场景的 Agent Skills 分类仓库。这里收录可供
Claude Code、Codex 及其他兼容 Agent Skills 标准的工具使用的完整技能目录。

当前版本包含 **241 个 Skills**：240 个来自 16 个上游项目，1 个为本仓库原创。

## 这个仓库解决什么问题

- 按任务场景整理分散在不同仓库中的 Skills。
- 保留每个 Skill 的 `SKILL.md`、脚本、参考资料和资产。
- 隔离不同来源中的同名 Skill。
- 提供 Claude Code、Codex 和通用 Skills CLI 的安装说明。
- 为自研 Skills 提供长期维护和公开发布位置。

本仓库不是一个可整体安装的运行时目录。安装时应选择最内层包含 `SKILL.md`
的目录，而不是直接复制 `科研/`、`开发/` 或 `内容创作/`。

## 快速开始

### 安装本仓库原创的文档转换 Skill

```bash
npx skills add luffysolution-svg/research-skills-collection \
  --skill convert-documents-to-markdown \
  --agent claude-code codex \
  --global --copy --full-depth --yes
```

Windows PowerShell 可将 `npx` 改为 `npx.cmd`。

也可以手动复制：

```text
科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/
```

到 Claude Code 的 `~/.claude/skills/` 或 Codex 的 `~/.agents/skills/`。

完整说明见[中文安装指南](docs/INSTALL.zh-CN.md)。

## 分类导航

| 分类 | 数量 | 主要内容 |
|---|---:|---|
| 科研/文献检索与引用 | 13 | 搜索、数据库、引用与证据整理 |
| 科研/文献写作 | 13 | 论文、润色、专利与模板 |
| 科研/作图 | 20 | 科研图表、示意图、海报与演示 |
| 科研/数据分析与处理 | 27 | 统计、机器学习、数据框架 |
| 科研/生物 | 49 | 生物信息、组学、成像与实验数据 |
| 科研/化学 | 12 | 分子、材料、计算化学与化工 |
| 科研/环境 | 2 | 环境数据与分析 |
| 科研/材料 | 1 | 材料科学 |
| 科研/办公专用 | 24 | 文档、表格、幻灯片与格式转换 |
| 科研/构思 | 7 | 假设生成、研究设计与头脑风暴 |
| 科研/审核 | 7 | 同行评审、质量与合规检查 |
| 科研/文献管理 | 13 | Zotero、知识库与实验记录 |
| 科研/物理与量子 | 5 | 物理计算与量子工具 |
| 科研/财政经济 | 1 | 财政与经济数据 |
| 科研/计算基础设施 | 2 | 云计算与任务执行 |
| 开发/前端设计 | 17 | UI、视觉设计与前端实现 |
| 开发/Agent 与技能开发 | 7 | Agent、MCP、Skill 与发布流程 |
| 开发/技术文档与知识检索 | 4 | 技术资料与上下文检索 |
| 内容创作/选题与趋势研究 | 1 | 热点与趋势研究 |
| 内容创作/人物视角与表达 | 16 | 人物思维框架与内容表达 |

目录结构：

```text
科研/<分类>skills/<来源>/<skill>/
开发/<分类>skills/<来源>/<skill>/
内容创作/<分类>skills/<来源>/<skill>/
```

## 安装方式

| 方式 | 适用场景 |
|---|---|
| Skills CLI | 从本仓库按名称安装，支持多种 Agent |
| 手动复制 | 只需要一个 Skill，或希望完整控制文件 |
| 平台插件 | 上游项目提供 Claude Code/Codex 插件时优先使用 |
| 仓库级 Skill | 团队项目中提交到 `.claude/skills/` 或 `.agents/skills/` |

相关文档：

- [中文安装指南](docs/INSTALL.zh-CN.md)
- [English installation guide](docs/INSTALL.en.md)
- [中文维护指南](docs/MAINTENANCE.zh-CN.md)
- [English maintenance guide](docs/MAINTENANCE.en.md)

## 本仓库原创 Skills

### `convert-documents-to-markdown`

自动选择 MarkItDown、视觉 OCR 或 MinerU，将 PDF、Office 文档、图片和音频转换
为经过验证的 Markdown。包含跨平台依赖诊断、OCR 配置检查、音频依赖检查和安全
的临时文件清理。

路径：

```text
科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/
```

## 来源与许可证

第三方内容的著作权和许可证归各上游项目所有。本仓库不以统一许可证覆盖第三方
Skill；使用或再分发前必须检查对应目录和
[第三方声明](THIRD_PARTY_NOTICES.md)。

部分官方文档 Skills 因许可证限制未在本仓库再分发，详见第三方声明。

## 维护与贡献

新增或更新 Skill 时必须：

1. 保留完整目录和许可证文件。
2. 按“分类 → 来源 → Skill”存放。
3. 检查密钥、缓存、大文件和受限内容。
4. 更新统计、来源和双语文档。
5. 通过 UTF-8、链接与结构验证后再提交。

完整流程见[中文维护指南](docs/MAINTENANCE.zh-CN.md)。

## 文档

- [中文安装指南](docs/INSTALL.zh-CN.md)
- [English installation guide](docs/INSTALL.en.md)
- [中文维护指南](docs/MAINTENANCE.zh-CN.md)
- [English maintenance guide](docs/MAINTENANCE.en.md)
- [第三方来源与许可证](THIRD_PARTY_NOTICES.md)

医疗、法律、金融和实验安全相关输出必须由具备资质的人员复核。
