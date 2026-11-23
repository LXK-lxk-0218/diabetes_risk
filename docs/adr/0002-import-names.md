# ADR-0002：三个包用三个不同的导入名

- 状态：已采纳（A1）
- 背景：发行名（`uv add` 时写的名字）和导入名（`import` 时写的名字）可以不同。如果三个包共用一个顶层名，或者用 `core`、`app` 这样的通用名，分层契约写不清楚，还容易和第三方库撞名。
- 决定：`drisk-core` → `diabetes_risk`；`drisk-training` → `drisk_training`；`drisk-api` → `drisk_api`。
- 后果：看到一行 `import` 就知道它属于哪个包；`.importlinter` 的契约直接按导入名写。