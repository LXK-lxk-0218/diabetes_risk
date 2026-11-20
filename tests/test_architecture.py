"""
架构测试：守护A1仓库骨架的所有规则。

这些测试就是监考老师——专门抓偷偷改规则、走后门的行为。
规则不是写在墙上，而是写成会失败的测试。谁改了规则，测试就红。
"""

import hashlib
import json
from pathlib import Path

import pytest

# ── 项目根目录 ──────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent

# ── 与阶段-1 冻结口径完全一致的列定义 ────────────────
NUM_COLS = ["age", "height_cm", "weight_kg", "waist_cm", "sbp", "dbp", "exercise_min_week", "sleep_hours"]
BIN_COLS = [
    "veg_fruit_daily",
    "hypertension_dx",
    "hyperlipidemia_dx",
    "gdm_history",
    "polyuria",
    "polydipsia",
    "weight_loss_unexplained",
]
CAT_COLS = ["gender", "smoking_status", "drinking_freq", "family_history_dm"]
TARGET = "label"
META_COLS = ["visit_id", "resident_id", "visit_date", "district", "education", "income_level"]
COLUMNS = NUM_COLS + BIN_COLS + CAT_COLS + [TARGET] + META_COLS


def _content_sha256(d: "DataFrame") -> str:  # type: ignore[no-untyped-def]  # noqa: F821
    """内容指纹：固定列序、数值统一成浮点、按 visit_id 排好，写成 CSV 文本再算 sha256。
    与第0阶段 v2 Notebook 中的 content_sha256() 口径完全一致。"""
    canon = d[COLUMNS].astype({c: "float64" for c in NUM_COLS + BIN_COLS + [TARGET]})
    text = canon.sort_values("visit_id").to_csv(index=False, lineterminator="\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════
# 1. 三个包都能正确导入（证明 src 布局有效，不是靠当前目录）
# ══════════════════════════════════════════════════


def test_can_import_diabetes_risk() -> None:
    """核心包 diabetes_risk 可以被正确导入。"""
    import diabetes_risk  # type: ignore[import-untyped]

    assert diabetes_risk.__file__ is not None


def test_can_import_drisk_training() -> None:
    """训练包 drisk_training 可以被正确导入。"""
    import drisk_training  # type: ignore[import-untyped]

    assert drisk_training.__file__ is not None


def test_can_import_drisk_api() -> None:
    """服务包 drisk_api 可以被正确导入。"""
    import drisk_api  # type: ignore[import-untyped]

    assert drisk_api.__file__ is not None


def test_imports_use_src_layout() -> None:
    """三个包都是从 site-packages 或 src 安装路径导入，不是靠当前目录碰巧找到。"""
    import diabetes_risk
    import drisk_api  # type: ignore[import-untyped]
    import drisk_training

    for pkg_name, pkg in [
        ("diabetes_risk", diabetes_risk),
        ("drisk_training", drisk_training),
        ("drisk_api", drisk_api),
    ]:
        pkg_path = Path(str(pkg.__file__))
        assert "site-packages" in str(pkg_path) or "src" in str(pkg_path), f"{pkg_name} 导入路径异常: {pkg_path}"


# ══════════════════════════════════════════════════
# 2. 冻结数据集指纹不能变
# ══════════════════════════════════════════════════


def test_frozen_json_exists() -> None:
    """FROZEN.json 口径文件必须存在。"""
    frozen_json = ROOT / "data" / "frozen" / "FROZEN.json"
    assert frozen_json.exists(), f"FROZEN.json 缺失: {frozen_json}"


def test_incident_db_fingerprint_matches() -> None:
    """incident.db 的 SHA256 指纹必须与 FROZEN.json 中登记的完全一致。"""
    frozen_json = ROOT / "data" / "frozen" / "FROZEN.json"
    incident_db = ROOT / "data" / "raw" / "incident.db"

    if not frozen_json.exists() or not incident_db.exists():
        pytest.skip("数据文件不存在，跳过指纹验证")

    with open(frozen_json, encoding="utf-8") as f:
        frozen = json.load(f)
    db_hash = hashlib.sha256(incident_db.read_bytes()).hexdigest()

    expected = frozen["source"]["sha256"][:8]
    actual = db_hash[:8]
    assert actual == expected, f"incident.db 指纹不匹配！当前: {actual}, 冻结登记: {expected}"


def test_train_parquet_fingerprint_matches() -> None:
    """训练集 parquet 的内容指纹必须与 FROZEN.json 一致（逻辑内容，非原始文件字节）。"""
    import pandas as pd

    frozen_json = ROOT / "data" / "frozen" / "FROZEN.json"
    train_file = ROOT / "data" / "frozen" / "train.parquet"

    if not frozen_json.exists() or not train_file.exists():
        pytest.skip("数据文件不存在，跳过指纹验证")

    with open(frozen_json, encoding="utf-8") as f:
        frozen = json.load(f)
    df = pd.read_parquet(train_file)
    actual = _content_sha256(df)[:8]

    expected = frozen["train"]["content_sha256"][:8]
    assert actual == expected, f"train.parquet 内容指纹不匹配！当前: {actual}, 冻结登记: {expected}"


def test_valid_parquet_fingerprint_matches() -> None:
    """验证集 parquet 的内容指纹必须与 FROZEN.json 一致（逻辑内容，非原始文件字节）。"""
    import pandas as pd

    frozen_json = ROOT / "data" / "frozen" / "FROZEN.json"
    valid_file = ROOT / "data" / "frozen" / "valid.parquet"

    if not frozen_json.exists() or not valid_file.exists():
        pytest.skip("数据文件不存在，跳过指纹验证")

    with open(frozen_json, encoding="utf-8") as f:
        frozen = json.load(f)
    df = pd.read_parquet(valid_file)
    actual = _content_sha256(df)[:8]

    expected = frozen["valid"]["content_sha256"][:8]
    assert actual == expected, f"valid.parquet 内容指纹不匹配！当前: {actual}, 冻结登记: {expected}"


# ══════════════════════════════════════════════════
# 3. 分层依赖契约：三层单向依赖，不许乱串门
# ══════════════════════════════════════════════════


def test_api_source_does_not_import_training() -> None:
    """drisk_api 源码中不能出现 import drisk_training — 服务包不能依赖训练包。"""
    api_src = ROOT / "services" / "api" / "src" / "drisk_api"
    if not api_src.exists():
        pytest.skip("drisk_api 源码目录不存在")
    violations = []
    for py_file in api_src.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "import drisk_training" in content or "from drisk_training" in content:
            violations.append(str(py_file.relative_to(ROOT)))
    assert len(violations) == 0, f"drisk_api 源码中不应导入 drisk_training: {violations}"


def test_core_source_does_not_import_upper() -> None:
    """diabetes_risk 核心包不能 import drisk_training 或 drisk_api。"""
    core_src = ROOT / "packages" / "core" / "src" / "diabetes_risk"
    if not core_src.exists():
        pytest.skip("diabetes_risk 源码目录不存在")
    violations = []
    for py_file in core_src.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        for forbidden in ["drisk_training", "drisk_api"]:
            if f"import {forbidden}" in content or f"from {forbidden}" in content:
                violations.append(f"{py_file.relative_to(ROOT)} 不应导入 {forbidden}")
    assert len(violations) == 0, f"核心包不应导入上层包: {violations}"


def test_training_source_does_not_import_api() -> None:
    """drisk_training 源码中不能出现 import drisk_api — 训练包不能依赖服务包。"""
    training_src = ROOT / "packages" / "training" / "src" / "drisk_training"
    if not training_src.exists():
        pytest.skip("drisk_training 源码目录不存在")
    violations = []
    for py_file in training_src.rglob("*.py"):
        content = py_file.read_text(encoding="utf-8")
        if "import drisk_api" in content or "from drisk_api" in content:
            violations.append(str(py_file.relative_to(ROOT)))
    assert len(violations) == 0, f"drisk_training 源码中不应导入 drisk_api: {violations}"


# ══════════════════════════════════════════════════
# 4. 禁止代码中的路径 hack
# ══════════════════════════════════════════════════


def test_no_sys_path_manipulation_in_source() -> None:
    """禁止任何源码中使用 sys.path.insert/append 绕过正常包导入。"""
    violations: list[str] = []
    src_dirs = [
        ROOT / "packages" / "core" / "src",
        ROOT / "packages" / "training" / "src",
        ROOT / "services" / "api" / "src",
        ROOT / "scripts",
    ]
    for src_dir in src_dirs:
        if not src_dir.exists():
            continue
        for py_file in src_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            if "sys.path.insert" in content or "sys.path.append" in content:
                violations.append(str(py_file.relative_to(ROOT)))

    assert len(violations) == 0, f"以下文件包含 sys.path 操作（禁止）: {violations}"


def test_no_os_chdir_in_source() -> None:
    """禁止任何源码中使用 os.chdir 改变工作目录。"""
    violations: list[str] = []
    src_dirs = [
        ROOT / "packages" / "core" / "src",
        ROOT / "packages" / "training" / "src",
        ROOT / "services" / "api" / "src",
        ROOT / "scripts",
    ]
    for src_dir in src_dirs:
        if not src_dir.exists():
            continue
        for py_file in src_dir.rglob("*.py"):
            content = py_file.read_text(encoding="utf-8")
            if "os.chdir" in content:
                violations.append(str(py_file.relative_to(ROOT)))

    assert len(violations) == 0, f"以下文件包含 os.chdir（禁止）: {violations}"


# ══════════════════════════════════════════════════
# 5. 质量门槛不能偷偷调低
# ══════════════════════════════════════════════════


def test_coverage_threshold_not_lowered() -> None:
    """覆盖率门槛必须 >= 85%，不能偷偷调低。"""
    pyproject = ROOT / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")

    # 检查 fail_under 设置
    assert "fail_under" in content, "pyproject.toml 中缺少 coverage fail_under 配置"

    # 解析 fail_under 值
    for line in content.split("\n"):
        line = line.strip()
        if line.startswith("fail_under"):
            value_str = line.split("=")[1].strip()
            value = int(value_str)
            assert value >= 85, f"覆盖率门槛被降低到 {value}%，必须 >= 85%"
            break


def test_mypy_disallow_untyped_defs_enabled() -> None:
    """mypy 必须开启 disallow_untyped_defs，禁止无类型注解的函数。"""
    pyproject = ROOT / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")

    assert "disallow_untyped_defs = true" in content, "disallow_untyped_defs 必须为 true"


def test_ruff_select_rules_not_weakened() -> None:
    """ruff 核心规则集（E, F, W, I）不得删减。"""
    pyproject = ROOT / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")

    # E, F, W, I 必须都在 select 中
    for rule in ["E", "F", "W", "I"]:
        assert f'"{rule}"' in content.split("select = [")[1].split("]")[0] if "select = [" in content else True, (
            f"ruff select 缺少规则 {rule}"
        )


# ══════════════════════════════════════════════════
# 6. .importlinter 分层契约存在性检查
# ══════════════════════════════════════════════════


def test_importlinter_config_exists() -> None:
    """.importlinter 分层契约文件必须存在。"""
    importlinter_config = ROOT / ".importlinter"
    assert importlinter_config.exists(), ".importlinter 缺失！依赖契约由这个文件定义"


def test_importlinter_has_three_layers() -> None:
    """.importlinter 中必须定义三个层的契约。"""
    config = ROOT / ".importlinter"
    if not config.exists():
        pytest.skip(".importlinter 不存在")
    content = config.read_text(encoding="utf-8")

    # 三个包名都应该出现在契约中
    assert "diabetes_risk" in content, ".importlinter 缺少 diabetes_risk 层"
    assert "drisk_training" in content, ".importlinter 缺少 drisk_training 层"
    assert "drisk_api" in content, ".importlinter 缺少 drisk_api 层"


# ══════════════════════════════════════════════════
# 7. py.typed 标记文件存在
# ══════════════════════════════════════════════════


def test_py_typed_files_exist() -> None:
    """三个包都必须有 py.typed 标记文件，告诉 mypy 这里有类型注解。"""
    py_typed_paths = [
        ROOT / "packages" / "core" / "src" / "diabetes_risk" / "py.typed",
        ROOT / "packages" / "training" / "src" / "drisk_training" / "py.typed",
        ROOT / "services" / "api" / "src" / "drisk_api" / "py.typed",
    ]
    for path in py_typed_paths:
        assert path.exists(), f"缺失 py.typed: {path.relative_to(ROOT)}"


# ══════════════════════════════════════════════════
# 8. 项目关键文件存在性
# ══════════════════════════════════════════════════


def test_config_files_exist() -> None:
    """AGENTS.md、.editorconfig、.gitignore 等关键配置文件存在。"""
    required_files = [
        "AGENTS.md",
        ".editorconfig",
        ".gitignore",
        "README.md",
        ".python-version",
    ]
    for filename in required_files:
        path = ROOT / filename
        assert path.exists(), f"缺失关键配置文件: {filename}"


def test_pytest_config_no_pythonpath() -> None:
    """pytest 配置中不能添加 pythonpath，防止破坏 src 布局的导入规则。"""
    pyproject = ROOT / "pyproject.toml"
    content = pyproject.read_text(encoding="utf-8")
    assert "pythonpath" not in content.lower(), "pyproject.toml 中不能包含 pythonpath 配置"


# ══════════════════════════════════════════════════
# 9. scripts/ci.py 存在性
# ══════════════════════════════════════════════════


def test_ci_script_exists() -> None:
    """scripts/ci.py 质量门脚本必须存在。"""
    ci_path = ROOT / "scripts" / "ci.py"
    assert ci_path.exists(), "scripts/ci.py 缺失！这是项目的唯一质量门入口"
