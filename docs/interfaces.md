# 公开接口快照

> 由 `uv run python scripts/api_snapshot.py --write` 生成，不要手改；
> `tests/architecture/test_api_snapshot.py` 保证它和代码一致。
> 新增的行是这一步该有的；**已有的行被改或被删，就是改了已有接口**：先停下来问人。

## `diabetes_risk.core.catalog`

- `Group = Literal['numeric', 'binary', 'categorical']`
- `GROUPS: tuple[Group, ...] = ('numeric', 'binary', 'categorical')`
- `REQUIRED_FORBIDDEN: tuple[str, ...] = ('visit_id', 'resident_id', 'visit_date', 'label')`
- `class CatalogError(DriskError)`
- `class FieldSpec(_Spec)`
  - `name: str`
  - `group: Group`
  - `display_name: str`
  - `required: bool = False`
  - `range: tuple[float, float] | None = None`
  - `categories: tuple[str, ...] | None = None`
- `class DerivedSpec(_Spec)`
  - `name: str`
  - `display_name: str`
- `class CatalogSpec(_Spec)`
  - `version: int = Field(ge=1)`
  - `fields: tuple[FieldSpec, ...]`
  - `forbidden: tuple[str, ...]`
  - `derived: tuple[DerivedSpec, ...] = ()`
- `class FeatureCatalog`
  - `def __init__(self, spec: CatalogSpec) -> None`
  - `@classmethod def from_dict(cls, data: dict[str, Any]) -> FeatureCatalog`
  - `@classmethod def from_yaml(cls, path: Path) -> FeatureCatalog`
  - `@property def version(self) -> int`
  - `@property def fields(self) -> tuple[FieldSpec, ...]`
  - `@property def input_columns(self) -> list[str]`
  - `def columns(self, group: Group) -> list[str]`
  - `@property def forbidden(self) -> tuple[str, ...]`
  - `@property def derived_columns(self) -> list[str]`
  - `def field(self, name: str) -> FieldSpec`
  - `def display_name(self, name: str) -> str`
  - `@property def catalog_hash(self) -> str`

## `diabetes_risk.core.errors`

- `class DriskError(Exception)`

## `diabetes_risk.core.registry`

- `class Registry[T]`
  - `def __init__(self, kind: str) -> None`
  - `@property def kind(self) -> str`
  - `def register(self, name: str) -> Callable[[T], T]`
  - `def add(self, name: str, obj: T) -> T`
  - `def get(self, name: str) -> T`
  - `def names(self) -> list[str]`
  - `def values(self) -> Iterator[T]`

## `diabetes_risk.core.repro`

- `def set_global_seed(seed: int) -> None`
- `def sha256_bytes(data: bytes) -> str`
- `def sha256_file(path: Path, chunk_size: int=1 << 20) -> str`
- `def canonical_json(obj: Any) -> str`
- `def sha256_json(obj: Any) -> str`
- `def git_sha(root: Path) -> str | None`
- `def git_dirty(root: Path) -> bool | None`

## `diabetes_risk.observability.log`

- `DEFAULT_REDACT: frozenset[str] = frozenset({'resident_id', 'visit_id', 'features', 'name', 'phone', 'id_card'})`
- `REDACTED = '***'`
- `def configure_logging(level: str='INFO', fmt: Literal['json', 'console']='console', *, redact: Iterable[str]=DEFAULT_REDACT, stream: TextIO | None=None) -> None`
- `def get_logger(name: str) -> FilteringBoundLogger`
- `def bind_context(**values: Any) -> None`
- `def clear_context() -> None`

## `diabetes_risk.observability.timing`

- `class MetricsEmitter(Protocol)`
  - `def emit(self, name: str, value: float, tags: Mapping[str, str] | None=None) -> None`
- `@contextmanager def use_emitter(emitter: MetricsEmitter | None) -> Iterator[None]`
- `def current_emitter() -> MetricsEmitter | None`
- `class timed`
  - `def __init__(self, stage: str) -> None`
  - `def __call__(self, func: Callable[_P, _R]) -> Callable[_P, _R]`

## `drisk_training.config.catalog`

- `def load_catalog(settings: Settings, root: Path) -> FeatureCatalog`

## `drisk_training.config.env`

- `class EnvSettings(BaseSettings)`
  - `model_config = SettingsConfigDict(env_prefix='DRISK_', env_file='.env', extra='ignore')`
  - `log_level: str = 'INFO'`
  - `log_format: Literal['json', 'console'] = 'console'`

## `drisk_training.config.loader`

- `class ConfigError(DriskError)`
- `def deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]`
- `def load_raw(path: Path) -> dict[str, Any]`
- `def load_settings(path: Path) -> Settings`
- `def config_hash(settings: Settings) -> str`

## `drisk_training.config.sections`

- `class ProjectSection(_Section)`
  - `name: str`
  - `experiment: str = 'base'`
  - `seed: int = 42`
- `class PathsSection(_Section)`
  - `data_dir: Path = Path('data')`
  - `features: Path = Path('configs/features.yaml')`
- `class DataSection(_Section)`
  - `raw_db: Path`
  - `as_of: date`
- `class LabelSection(_Section)`
  - `window_days: int = Field(gt=0)`
  - `max_report_lag_days: int = Field(ge=0)`
  - `fpg_pos: float = Field(gt=0)`
  - `hba1c_pos: float = Field(gt=0)`
  - `@property def maturity_days(self) -> int`
- `class SplitSection(_Section)`
  - `train_end: date`
  - `valid_start: date`
  - `valid_end: date`
- `class Settings(_Section)`
  - `project: ProjectSection`
  - `paths: PathsSection = Field(default_factory=PathsSection)`
  - `data: DataSection`
  - `label: LabelSection`
  - `split: SplitSection`
  - `@model_validator(mode='after') def check_dates_in_order(self) -> Settings`
  - `@property def train_last_visit(self) -> date`
  - `def raw_db_path(self, root: Path) -> Path`
