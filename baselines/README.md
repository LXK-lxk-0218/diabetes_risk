# baselines/

只读的对账参照。每个子目录用 `scripts/freeze_baseline.py --write` 冻结一次，之后只校验不修改。

这个文件同时让 `baselines/` 目录能进 Git：Git 不记录空目录，没有它，别人克隆下来的仓库里就没有 `baselines/`，基线测试会报 `FileNotFoundError`。