# Skills 安装指南

[English](INSTALL.en.md) | 简体中文

本指南说明如何从本仓库选择并安装单个 Skill。不要把 `科研/`、`开发/` 或
`内容创作/` 整体复制到 Agent 的技能目录；应安装最内层包含 `SKILL.md` 的目录。

## 安装前准备

- 安装 Git。
- 使用 Skills CLI 时，需要 Node.js 18 或更高版本。
- Skill 自带 Python 脚本时，需要 Python 3.9 或更高版本。
- 安装前检查目标 Skill 的许可证、脚本和依赖。

## 推荐方式：Skills CLI

安装本仓库原创的文档转换 Skill：

```bash
npx skills add luffysolution-svg/research-skills-collection \
  --skill convert-documents-to-markdown \
  --agent claude-code codex \
  --global --copy --full-depth --yes
```

Windows PowerShell 如果因执行策略无法运行 `npx.ps1`，将 `npx` 改为
`npx.cmd`。`--full-depth` 用于扫描本仓库较深的分类目录，不能省略。

仅安装到一个 Agent：

```bash
npx skills add luffysolution-svg/research-skills-collection \
  --skill convert-documents-to-markdown \
  --agent claude-code \
  --global --copy --full-depth --yes
```

将 `claude-code` 改为 `codex` 即可只安装到 Codex。安装其他 Skill 时，将
`--skill` 后的名称替换为目标目录中 frontmatter 的 `name`。

## 手动安装

复制完整的 Skill 目录，包括 `SKILL.md`、`scripts/`、`references/`、
`assets/` 和许可证文件。

| 范围 | Claude Code | Codex |
|---|---|---|
| 个人 | `~/.claude/skills/<skill-name>/` | `~/.agents/skills/<skill-name>/` |
| 项目 | `<project>/.claude/skills/<skill-name>/` | `<project>/.agents/skills/<skill-name>/` |

Windows PowerShell 示例：

```powershell
$source = "科研\办公专用skills\luffysolution-skills\convert-documents-to-markdown"
$target = Join-Path $HOME ".agents\skills\convert-documents-to-markdown"
Copy-Item -LiteralPath $source -Destination $target -Recurse
```

目标目录已存在时先比较内容，不要直接覆盖本地修改。

## 平台原生插件

部分上游项目提供 Claude Code 或 Codex 插件。此时优先按照上游仓库的官方说明
安装，因为插件可能同时包含命令、Hook、MCP 配置和多个 Skills。本仓库只负责分类
保存 Skill 文件，不替代上游插件清单。

不要把 `claude plugin` 或 `codex plugin` 命令套用到只包含 `SKILL.md` 的普通目录；
普通 Skill 使用 Skills CLI 或手动复制。

## 调用与验证

Claude Code 可通过 `/skill-name` 调用，也会根据描述自动加载。Codex 可使用
`$skill-name`，或通过 `/skills` 查看技能。新增或替换文件后，如果当前会话没有发现
Skill，请重启 Agent 会话。

查看全局安装结果：

```bash
npx skills list --global --agent claude-code
npx skills list --global --agent codex
```

对于 `convert-documents-to-markdown`，安装后运行依赖检查：

```bash
python ~/.agents/skills/convert-documents-to-markdown/scripts/document-tools-doctor.py
```

Claude Code 用户将路径中的 `.agents` 改为 `.claude`。Windows 可使用完整的
`%USERPROFILE%` 路径。

## 更新与卸载

```bash
npx skills check
npx skills update --global
```

卸载前确认目标目录没有自己的修改，然后删除对应的单个 Skill 目录。不要删除整个
`~/.claude/skills/` 或 `~/.agents/skills/`。

## 冲突与故障排查

- **找不到 Skill**：确认 `SKILL.md` 位于 Skill 根目录，并重启会话。
- **同名冲突**：不同来源可能使用相同 `name`；只保留一个，或同时修改目录名和
  frontmatter 名称后自行维护。
- **Skills CLI 扫描不到**：确认命令带有 `--full-depth`。
- **PowerShell 阻止 npx**：使用 `npx.cmd`，不要为此降低全局执行策略。
- **脚本无法运行**：先阅读依赖说明，再运行 Skill 的 doctor/check 脚本。
- **OCR 或 MinerU 缺少凭据**：从所选服务商的官方控制台申请。第三方中转站不是
  OpenAI 官方服务，不要混淆来源，也不要把密钥提交到仓库。
- **路径含中文或空格**：始终使用引号，并优先使用 Python 3 和 UTF-8。

## 安全说明

Skill 可以包含可执行脚本和网络请求。安装第三方 Skill 前应检查来源、许可证、
命令和凭据处理方式。不要把 API Key、Token、`.env`、转换结果或个人文件提交到本仓库。

维护本仓库请阅读[维护指南](MAINTENANCE.zh-CN.md)。
