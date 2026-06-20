# Skills 安装指南：Claude Code 与 Codex

更新日期：2026-06-20

本文覆盖当前分类合集涉及的全部来源项目，并额外加入
[`obra/superpowers`](https://github.com/obra/superpowers)。

## 1. 安装策略

按以下优先级安装：

1. 平台原生插件：使用 `claude plugin` 或 `codex plugin`。
2. 没有对应平台插件的仓库：使用通用的 `npx.cmd skills add`。
3. MinerU 主项目：单独安装 CLI，它不是 `SKILL.md` 技能。

不要直接把整个 `科研Skills分类合集` 复制到运行时 skills 目录。分类合集为了保存同名技能，增加了“分类/仓库”层级；运行时安装器则按照技能名称管理目录。

### 同名技能提示

`anthropics/skills` 与 `K-Dense-AI/scientific-agent-skills` 都包含
`docx`、`pdf`、`pptx`、`xlsx`。全量安装时可能出现同名覆盖或重复选择器：

- Claude Code 推荐通过 Anthropic 插件安装文档技能。
- Codex 已有官方文档运行时技能时，不需要再次安装 Anthropic 的四个文档技能。
- 科研技能库建议按需选择，而不是一次安装全部 147 个。

## 2. 前置条件

确认以下命令可用：

```powershell
git --version
node --version
npx.cmd --version
claude --version
codex --version
```

要求：

- Git
- Node.js 18 或更高版本
- Claude Code CLI
- Codex CLI
- MinerU 本地解析需要 Python 3.10–3.13 和 `uv`

通用 Skills CLI 无需预先全局安装，直接使用 `npx.cmd skills`：

```powershell
npx.cmd skills --help
```

本文统一使用 `npx.cmd`，因为 Windows PowerShell 的执行策略可能拦截未签名的
`npx.ps1`。如果你的环境允许直接执行 `npx`，两种写法等价。

## 3. Claude Code 安装

### 3.1 安装原生插件

以下命令在普通 PowerShell 中执行。也可以进入 Claude Code 后，将
`claude plugin ...` 改写成对应的 `/plugin ...` 命令。

#### Academic Research Skills

```powershell
claude plugin marketplace add Imbad0202/academic-research-skills
claude plugin install academic-research-skills@academic-research-skills
```

#### Anthropic 官方 Skills

```powershell
claude plugin marketplace add anthropics/skills
claude plugin install document-skills@anthropic-agent-skills
claude plugin install example-skills@anthropic-agent-skills
claude plugin install claude-api@anthropic-agent-skills
```

如果不需要示例技能，可以只安装 `document-skills` 和 `claude-api`。

#### Baoyu Skills

```powershell
claude plugin marketplace add JimLiu/baoyu-skills
claude plugin install baoyu-skills@baoyu-skills
```

#### Context7

```powershell
claude plugin marketplace add upstash/context7
claude plugin install context7@context7-marketplace
```

该插件提供 Context7 MCP 和 `context7-mcp` 技能。若还需要仓库中的
`context7-cli`、`find-docs`、`context7-docs`，再执行：

```powershell
npx.cmd skills add upstash/context7 -g -a claude-code `
  -s context7-cli find-docs context7-docs `
  --full-depth -y
```

#### Last30Days

```powershell
claude plugin marketplace add mvanhorn/last30days-skill
claude plugin install last30days@last30days-skill
```

#### Obsidian Skills

```powershell
claude plugin marketplace add kepano/obsidian-skills
claude plugin install obsidian@obsidian-skills
```

#### PPT Master

```powershell
claude plugin marketplace add hugohe3/ppt-master
claude plugin install ppt-master@ppt-master
```

安装后按项目说明安装 Python 后处理依赖：

```powershell
pip install -r requirements.txt
```

应在插件实际安装目录或仓库检出目录中运行该命令。

#### Taste Skill

```powershell
claude plugin marketplace add Leonxlnx/taste-skill
claude plugin install taste-skill@taste-skill
```

#### MinerU Document Explorer

先安装其 CLI：

```powershell
npm install -g mineru-document-explorer
```

然后安装 Claude 插件：

```powershell
claude plugin marketplace add opendatalab/MinerU-Document-Explorer
claude plugin install qmd@qmd
```

#### Superpowers

优先使用 Anthropic 官方 marketplace：

```powershell
claude plugin install superpowers@claude-plugins-official
```

`claude-plugins-official` 是 Claude Code 内置 marketplace，无需手动添加。
如果官方 marketplace 中暂时不可用，可使用项目 marketplace：

```powershell
claude plugin marketplace add obra/superpowers-marketplace
claude plugin install superpowers@superpowers-marketplace
```

### 3.2 用通用命令安装其余 Skills

以下仓库没有 Claude Code 原生插件，或使用通用 Skills CLI 更合适。
默认命令会进入交互选择界面：

```powershell
npx.cmd skills add op7418/guizang-ppt-skill -g -a claude-code
npx.cmd skills add blader/humanizer -g -a claude-code
npx.cmd skills add Yuan1z0825/nature-skills -g -a claude-code
npx.cmd skills add alchaincyf/nuwa-skill -g -a claude-code --full-depth
npx.cmd skills add K-Dense-AI/scientific-agent-skills -g -a claude-code
npx.cmd skills add jgraph/drawio-mcp -g -a claude-code --full-depth
npx.cmd skills add opendatalab/MinerU-Ecosystem -g -a claude-code --full-depth
```

Nuwa 若要一次安装主技能和全部人物示例：

```powershell
npx.cmd skills add alchaincyf/nuwa-skill -g -a claude-code `
  --full-depth -s '*' -y
```

Draw.io 只安装目标技能：

```powershell
npx.cmd skills add jgraph/drawio-mcp -g -a claude-code `
  --full-depth -s drawio -y
```

MinerU Document Extractor：

```powershell
npx.cmd skills add opendatalab/MinerU-Ecosystem -g -a claude-code `
  --full-depth -s 'MinerU Document Extractor' -y
npm install -g mineru-open-api
```

### 3.3 Claude Code 中的 Zotero

当前收集的 OpenAI Zotero 是 Codex 官方插件，不是 Claude Code 插件。
Claude Code 不应直接安装该 Codex 插件。

Claude Code 需要 Zotero 自动化时，可从科研技能库选择 `pyzotero`：

```powershell
npx.cmd skills add K-Dense-AI/scientific-agent-skills -g -a claude-code `
  -s pyzotero -y
```

### 3.4 验证 Claude Code

```powershell
claude plugin list
npx.cmd skills list -g -a claude-code
```

进入 Claude Code 后执行：

```text
/reload-plugins
```

如果技能仍未出现，关闭并重新启动 Claude Code。

## 4. Codex 安装

### 4.1 安装 Codex 原生插件

#### Superpowers

```powershell
codex plugin add superpowers@openai-curated
```

#### OpenAI 官方 Zotero

```powershell
codex plugin add zotero@openai-curated
```

首次使用前启动 Zotero Desktop。若本地 API 未启用，可让 Zotero 技能执行
`enable --restart`，或者直接询问技能当前状态。

#### Context7

```powershell
codex plugin marketplace add upstash/context7
codex plugin add context7@context7-marketplace
```

补充安装 Context7 的另外三个独立技能：

```powershell
npx.cmd skills add upstash/context7 -g -a codex `
  -s context7-cli find-docs context7-docs `
  --full-depth -y
```

### 4.2 用通用命令安装项目 Skills

推荐先运行不带 `-y` 的交互安装，只选择实际需要的技能：

```powershell
npx.cmd skills add Imbad0202/academic-research-skills -g -a codex
npx.cmd skills add anthropics/skills -g -a codex --full-depth
npx.cmd skills add Leonxlnx/taste-skill -g -a codex
npx.cmd skills add mvanhorn/last30days-skill -g -a codex
npx.cmd skills add kepano/obsidian-skills -g -a codex
npx.cmd skills add K-Dense-AI/scientific-agent-skills -g -a codex
npx.cmd skills add blader/humanizer -g -a codex
npx.cmd skills add JimLiu/baoyu-skills -g -a codex
npx.cmd skills add Yuan1z0825/nature-skills -g -a codex
npx.cmd skills add hugohe3/ppt-master -g -a codex --full-depth
npx.cmd skills add op7418/guizang-ppt-skill -g -a codex
npx.cmd skills add jgraph/drawio-mcp -g -a codex --full-depth
npx.cmd skills add opendatalab/MinerU-Ecosystem -g -a codex --full-depth
npx.cmd skills add opendatalab/MinerU-Document-Explorer -g -a codex --full-depth
npx.cmd skills add alchaincyf/nuwa-skill -g -a codex --full-depth
```

Codex 已有官方文档技能时，Anthropic 仓库建议只选非文档技能。例如：

```powershell
npx.cmd skills add anthropics/skills -g -a codex --full-depth `
  -s claude-api algorithmic-art brand-guidelines canvas-design `
     doc-coauthoring frontend-design internal-comms mcp-builder `
     skill-creator slack-gif-creator theme-factory `
     web-artifacts-builder webapp-testing `
  -y
```

### 4.3 验证 Codex

```powershell
codex plugin list
npx.cmd skills list -g -a codex
```

Codex 官方读取用户级 skills 的位置是：

```text
~/.agents/skills
```

若新技能没有立即显示，重新启动 Codex 或开始一个新线程。Codex 中可以使用
`/skills` 或输入 `$` 显式选择技能。

## 5. MinerU 本地 CLI

MinerU 主仓库 `opendatalab/MinerU` 不含 `SKILL.md`，它是 Claude Code 和
Codex 都可以调用的底层 CLI。

### 5.1 安装 uv

如果还没有 `uv`：

```powershell
python -m pip install --upgrade uv
```

### 5.2 安装 MinerU

```powershell
uv pip install -U "mineru[all]"
```

验证：

```powershell
mineru --help
mineru-models-download --help
```

基本用法：

```powershell
mineru -p "input.pdf" -o "output"
```

MinerU 的三个相关组件用途不同：

- `mineru`：本地文档解析 CLI。
- `mineru-open-api`：MinerU-Ecosystem Document Extractor skill 使用的官方 API CLI。
- `mineru-document-explorer` / `qmd`：文档索引、检索和深度阅读。

## 6. 全量安装参数

通用安装器的常用参数：

```text
-g                 用户级全局安装
-a claude-code     安装到 Claude Code
-a codex           安装到 Codex
-s skill-name      只安装指定技能
-s '*'             安装发现的全部技能
--full-depth       仓库根目录已有 SKILL.md 时仍扫描子目录
-y                 跳过确认
--copy             复制文件而不是创建链接
```

建议先查看仓库可安装技能：

```powershell
npx.cmd skills add OWNER/REPO -l --full-depth
```

然后按需安装：

```powershell
npx.cmd skills add OWNER/REPO -g -a codex -s skill-a skill-b -y
```

## 7. 更新

### Claude Code 插件

```powershell
claude plugin marketplace update
claude plugin update academic-research-skills@academic-research-skills
claude plugin update document-skills@anthropic-agent-skills
claude plugin update baoyu-skills@baoyu-skills
claude plugin update context7@context7-marketplace
claude plugin update last30days@last30days-skill
claude plugin update obsidian@obsidian-skills
claude plugin update ppt-master@ppt-master
claude plugin update taste-skill@taste-skill
claude plugin update qmd@qmd
claude plugin update superpowers@claude-plugins-official
```

如果 Superpowers 使用的是项目 marketplace，则最后一行改为：

```powershell
claude plugin update superpowers@superpowers-marketplace
```

### Codex 插件

```powershell
codex plugin marketplace upgrade
codex plugin list
```

### 通用 Skills

```powershell
npx.cmd skills update -g
```

## 8. 卸载

### Claude Code

```powershell
claude plugin uninstall PLUGIN@MARKETPLACE
npx.cmd skills remove -g -a claude-code -s SKILL_NAME -y
```

### Codex

```powershell
codex plugin remove PLUGIN@MARKETPLACE
npx.cmd skills remove -g -a codex -s SKILL_NAME -y
```

删除整个外部 marketplace：

```powershell
claude plugin marketplace remove MARKETPLACE_NAME
codex plugin marketplace remove MARKETPLACE_NAME
```

## 9. 项目安装通道总表

| 本地来源目录 / 项目 | Claude Code 推荐 | Codex 推荐 |
|---|---|---|
| academic-research-skills | 原生 marketplace | `npx.cmd skills` |
| anthropics-skills（anthropics/skills） | 原生 marketplace | `npx.cmd skills`，建议排除重复文档技能 |
| baoyu-skills | 原生 marketplace | `npx.cmd skills` |
| context7 | 原生 marketplace + 可选补充 skills | 原生 marketplace + 可选补充 skills |
| last30days-skill | 原生 marketplace | `npx.cmd skills` |
| obsidian-skills | 原生 marketplace | `npx.cmd skills` |
| ppt-master | 原生 marketplace | `npx.cmd skills` |
| taste-skill | 原生 marketplace | `npx.cmd skills` |
| mineru-document-explorer | 原生 marketplace | `npx.cmd skills` |
| codex-zotero-official | 不兼容；使用 `pyzotero` 替代 | OpenAI curated 插件 |
| Superpowers | Anthropic 官方插件 | OpenAI curated 插件 |
| scientific-agent-skills | `npx.cmd skills` | `npx.cmd skills` |
| nature-skills | `npx.cmd skills` | `npx.cmd skills` |
| humanizer | `npx.cmd skills` | `npx.cmd skills` |
| guizang-ppt-skill | `npx.cmd skills` | `npx.cmd skills` |
| drawio-official（jgraph/drawio-mcp） | `npx.cmd skills` | `npx.cmd skills` |
| mineru-ecosystem | `npx.cmd skills` + `mineru-open-api` | `npx.cmd skills` + `mineru-open-api` |
| nuwa-skill | `npx.cmd skills --full-depth` | `npx.cmd skills --full-depth` |
| mineru-official（MinerU 主仓库） | 安装 CLI | 安装 CLI |

## 10. 相关文件

- [分类合集说明](README.md)
- [第三方来源与许可证](THIRD_PARTY_NOTICES.md)
- [合集更新方法](UPDATING.md)
