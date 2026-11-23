# ADR-0001：一个仓库、三个包、一个 uv 工作区

- 状态：已采纳（A1）
- 背景：训练和服务要共用字段定义、指纹等代码，但服务部署时不能背上训练的依赖。第 0 阶段只有一句“装 pandas”，换台机器装出来的版本就不一样（E2）。
- 决定：一个 Git 仓库，三个包：`packages/core`、`packages/training`、`services/api`；用 uv workspace 管理，全仓只有一个 `uv.lock`。
- 后果：一条 `uv sync` 装出相同的环境；三个包之间的依赖方向由 `.importlinter` 检查。代价是三个包共用一套依赖版本，不能单独给某一个包升级某个库。