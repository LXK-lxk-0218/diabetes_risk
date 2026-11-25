"""依赖方向：核心包在最底层；训练包和服务包互不依赖。两道防线各管一半。

- import-linter（.importlinter）管代码里的 import；
- 这里的测试管两件 import-linter 看不见的事：契约有没有被删，pyproject 里有没有偷偷声明依赖。
"""

from __future__ import annotations

import configparser

# 必须存在的两条契约（名字是 .importlinter 里 [importlinter:contract:<名字>] 的最后一段）
REQUIRED_CONTRACTS = {"core-independent", "training-api-independent"}


def test_layer_contracts_not_removed(repo) -> None:
    """分层契约不能偷偷删减：import-linter 不会报警“契约被删”，由这个测试记住清单。"""
    # import-linter 只检查“写了的”契约：删掉一条，lint-imports 照样是绿的
    parser = configparser.ConfigParser()
    parser.read(repo.root / ".importlinter", encoding="utf-8")
    contracts = {s.split(":", 2)[2] for s in parser.sections() if s.startswith("importlinter:contract:")}
    missing = REQUIRED_CONTRACTS - contracts
    assert not missing, f"分层契约不能删减，缺少：{sorted(missing)}"


def test_core_declares_no_internal_dependency(repo) -> None:
    """核心包在最底层：它的 pyproject 里不能出现另外两个包。"""
    assert not repo.dependency_names("packages/core/pyproject.toml") & {"drisk-training", "drisk-api"}


def test_service_does_not_declare_training(repo) -> None:
    """服务包不声明训练包：只声明、不 import，import-linter 看不见，但部署时依赖会全装上。"""
    # training 以后会依赖 sklearn、mlflow 等重型库；api 若声明它，镜像会巨大、启动慢
    assert "drisk-training" not in repo.dependency_names("services/api/pyproject.toml")
