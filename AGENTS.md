# AGENTS.md — AI 禁区与架构规则

## 绝对禁止的操作

以下规则 AI 助手（包括 Claude、Copilot 等）**绝对不能违反**，相关约束由架构测试 `tests/test_architecture.py` 自动守护：

### 1. 禁止修改基线文件
- `data/frozen/FROZEN.json` — 口径定义文件，记录了数据来源与内容指纹
- `data/frozen/train.parquet` — 冻结训练集
- `data/frozen/valid.parquet` — 冻结验证集
- `data/raw/incident.db` — 原始数据库
- 以上文件的 SHA256 指纹已写入测试，任何修改都会导致测试失败

### 2. 禁止破坏三层依赖架构
- `drisk_api` **不能** import `drisk_training`
- `diabetes_risk` **不能** import `drisk_training` 或 `drisk_api`
- `drisk_training` **不能** import `drisk_api`
- 只允许：training → core ← api 的单向依赖
- 契约定义在 `.importlinter` 文件中

### 3. 禁止降低质量门槛
- 代码覆盖率门槛 ≥ 85%（`pyproject.toml` 中 `fail_under = 85`）
- 不得修改 `pyproject.toml` 中的 mypy/ruff/pytest/coverage 配置来降低标准

### 4. 禁止破坏代码规范
- 禁止使用 `sys.path.insert()` 或 `sys.path.append()` 来绕过包导入
- 禁止使用 `os.chdir()` 改变工作目录
- 所有导入必须通过标准的 `src` 布局和已安装的包

### 5. 禁止修改 `.importlinter` 分层契约
- `.importlinter` 中定义的三层依赖关系不得删除或放松

## 项目唯一合格标准

```bash
uv run python scripts/ci.py
```

五道质量门全部通过才算合格：
1. ruff 代码规范检查
2. ruff 代码格式化检查
3. mypy 类型检查
4. import-linter 分层契约检查
5. pytest + 覆盖率检查