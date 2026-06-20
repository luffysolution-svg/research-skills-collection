# Updating the collection

本仓库不保存 `_sources` 镜像。更新时以具体上游项目为单位进行。

## 推荐流程

1. 打开 README 中对应的上游仓库，检查最新版本、许可证和目录结构。
2. 在仓库外的临时目录克隆或下载上游项目。
3. 找到包含 `SKILL.md` 的完整技能目录。
4. 替换本仓库分类目录中的同名技能文件夹，不要只替换 `SKILL.md`。
5. 保留技能内部的 `LICENSE`、`references`、`scripts`、`assets` 等文件。
6. 检查是否引入密钥、缓存、构建产物或超过 GitHub 100 MB 的单文件。
7. 更新 README 中的数量和 `THIRD_PARTY_NOTICES.md`。
8. 提交前运行下面的检查。

```powershell
$root = Get-Location

# 统计 skills
(Get-ChildItem -Path 科研,开发,内容创作 -Filter SKILL.md -File -Recurse).Count

# 检查 GitHub 大文件限制
Get-ChildItem -File -Recurse |
  Where-Object Length -gt 90MB |
  Select-Object FullName, Length

# 检查常见密钥文件
Get-ChildItem -File -Recurse -Force |
  Where-Object Name -Match '^(\.env|credentials|secrets?)'

# 检查受限 Anthropic 文档技能是否被重新引入
Get-ChildItem -Filter LICENSE.txt -File -Recurse |
  Where-Object {
    (Get-Content $_.FullName -Raw) -match 'users may not'
  } |
  Select-Object FullName
```

## 平台安装命令变化

Claude Code、Codex 和 Skills CLI 的命令可能变化。更新安装指南前，应分别运行：

```powershell
claude plugin --help
codex plugin --help
npx.cmd skills --help
```

不要根据旧文档猜测插件 ID；优先查看上游项目的 marketplace manifest。
