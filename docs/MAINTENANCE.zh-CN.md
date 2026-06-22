# 仓库维护指南

[English](MAINTENANCE.en.md) | 简体中文

本仓库同时保存第三方 Skills 和本仓库原创 Skills。维护工作的核心要求是：保留来源
与许可证、维持可安装目录结构、避免泄露凭据，并同步中英文文档。

## 仓库结构

```text
科研/<分类>skills/<来源>/<skill>/
开发/<分类>skills/<来源>/<skill>/
内容创作/<分类>skills/<来源>/<skill>/
```

`<skill>/SKILL.md` 必须存在。来源目录用于隔离不同项目的同名 Skill，不能为了缩短
路径而删除。完整的第三方许可证副本保存在 `THIRD_PARTY_LICENSES/`。

## 新增原创 Skill

1. 在适当分类下使用仓库自有来源目录，例如 `luffysolution-skills/`。
2. 保留完整目录，包括脚本、参考资料、资产和测试。
3. 检查 frontmatter 的 `name`、`description` 和 Agent Skills 兼容性。
4. 在两个 README 的原创 Skills 区域记录用途和路径。
5. 同步更新中文与英文文档。
6. 运行结构、编码、凭据和实际使用测试。

原创内容不应列为第三方项目。`THIRD_PARTY_NOTICES.md` 不会自动为原创内容授予
仓库级许可证；需要公开许可证时应单独添加明确的 `LICENSE`。

## 新增或更新第三方 Skill

1. 记录上游仓库、固定版本或提交号、许可证和下载日期。
2. 确认许可证允许再分发；无法确认时不要纳入仓库。
3. 复制完整 Skill 目录，不只复制 `SKILL.md`。
4. 保留原始许可证、NOTICE、署名和来源链接。
5. 将完整许可证放入 `THIRD_PARTY_LICENSES/<source>/`，并更新
   `THIRD_PARTY_NOTICES.md`。
6. 检查嵌套复制的受限内容、密钥、缓存、构建产物和大文件。
7. 更新统计和双语文档。

不得收录上游许可证明确禁止提取、保留或第三方分发的内容。当前排除项见
[第三方声明](../THIRD_PARTY_NOTICES.md)。

## 文档同步规则

| 中文 | English |
|---|---|
| `README.md` | `README_EN.md` |
| `docs/INSTALL.zh-CN.md` | `docs/INSTALL.en.md` |
| `docs/MAINTENANCE.zh-CN.md` | `docs/MAINTENANCE.en.md` |

修改安装路径、统计、命令、安全规则或许可证说明时，必须同步修改对应语言版本。

## 统计更新

以包含 `SKILL.md` 的目录为准，不按文件夹总数计算。

```bash
python -c "from pathlib import Path; print(sum(1 for _ in Path('.').rglob('SKILL.md')))"
```

PowerShell：

```powershell
(Get-ChildItem -Recurse -Filter SKILL.md -File).Count
```

分类统计应按 `SKILL.md` 的实际父级路径重新生成，并同步到两个 README，不要手工猜测。

## 发布前检查

### UTF-8 与异常字符

```bash
python -c "from pathlib import Path; files=list(Path('.').rglob('*.md')); [p.read_text(encoding='utf-8') for p in files]; assert not any('\ufffd' in p.read_text(encoding='utf-8') for p in files); print(len(files), 'Markdown files OK')"
```

终端显示乱码不等于文件损坏，应以严格 UTF-8 解码结果为准。

### 凭据与私密文件

```bash
git grep -nEi "(api[_-]?key|secret|token|password)[[:space:]]*[:=][[:space:]]*['\"][^$<{][^'\"]+"
git status --short
```

人工复核匹配结果。示例变量名可以存在，真实值、`.env`、私人文档和转换输出不能提交。

### 缓存和大文件

PowerShell：

```powershell
Get-ChildItem -Recurse -Force -Directory |
  Where-Object Name -in '__pycache__','.pytest_cache','.mypy_cache','node_modules'
Get-ChildItem -Recurse -File |
  Where-Object Length -gt 90MB |
  Select-Object FullName,Length
```

POSIX：

```bash
find . -type d \( -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name node_modules \)
find . -type f -size +90M -print
```

### 链接、格式和 Skill 结构

- 验证所有相对 Markdown 链接存在。
- 运行 `git diff --check`。
- 对新增 Skill 运行可用的 Agent Skills 校验器。
- 执行 Skill 自带测试和 doctor/check 脚本。
- 对含脚本的 Skill，检查 Windows、macOS/Linux、空格和中文路径。

`convert-documents-to-markdown` 可运行：

```bash
python 科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/document-tools-doctor.py --json
python 科研/办公专用skills/luffysolution-skills/convert-documents-to-markdown/scripts/task-workspace.py create
```

对 `create` 返回的路径依次运行 `validate "<path>"` 和 `cleanup "<path>"`，确认临时
目录的标记、安全边界和清理流程有效。

## Git 与 PR 流程

1. 从最新 `main` 创建功能分支。
2. 只暂存本次变更，避免把个人笔记或转换结果带入提交。
3. 运行完整发布前检查。
4. 使用范围明确的提交信息。
5. 推送分支并创建 PR，列出来源、许可证、统计变化和验证结果。
6. 合并前再次检查 PR 文件列表和 GitHub Actions。
7. 合并后验证远端 `main`，再清理本地分支。

本地专用排除项应写入 `.git/info/exclude`，不要为了个人文件修改仓库 `.gitignore`。

## 发布检查清单

- [ ] 每个 Skill 的根目录都有 `SKILL.md`
- [ ] 来源和许可证已核实
- [ ] 没有受限内容、真实密钥、缓存或超大文件
- [ ] 中英文文档已同步
- [ ] README 统计来自实际扫描
- [ ] 相对链接和 UTF-8 校验通过
- [ ] 新增或修改的 Skill 已实际测试
- [ ] `git diff --check` 通过
- [ ] PR 文件范围正确
