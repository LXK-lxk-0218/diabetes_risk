"""契约守护测试：校验 .importlinter 里的契约有没有被人偷偷删除。

import-linter 只会检查【存在的契约】，契约条目删掉它不会告警；
本测试把契约 ID 台账写死，保证架构边界规则不会悄无声息消失。
"""

from __future__ import annotations

import configparser

# ========== 台账：我们约定好必须存在的契约 ID，和配置文件一一对应 ==========
EXPECTED_CONTRACT_IDS = {
    "core-independent",
    "training-api-independent",
}


def test_import_linter_contract_not_removed(repo) -> None:
    # 定位 importlinter 配置文件：用仓库根定位，不依赖当前工作目录
    config_file_path = repo.root / ".importlinter"
    # 创建 INI 解析器并读取配置
    parser = configparser.ConfigParser()
    parser.read(config_file_path, encoding="utf-8")

    actual_contract_ids: set[str] = set()
    prefix = "importlinter:contract:"
    # 遍历所有配置块，筛选契约块：以 importlinter:contract: 开头
    for section_name in parser.sections():
        if section_name.startswith(prefix):
            # 把前缀去掉，剩下的就是契约 id
            actual_contract_ids.add(section_name.removeprefix(prefix))

    # 断言：当前配置里的契约 ID 必须和台账完全一致
    # 两种失败场景：
    # 1. 有人删掉某一条契约 → actual 变少，报错
    # 2. 新增契约但忘记更新 EXPECTED_CONTRACT_IDS → actual 变多，报错
    assert actual_contract_ids == EXPECTED_CONTRACT_IDS, (
        f"契约清单不一致！\n预期契约 ID：{EXPECTED_CONTRACT_IDS}\n当前文件契约 ID：{actual_contract_ids}"
    )
