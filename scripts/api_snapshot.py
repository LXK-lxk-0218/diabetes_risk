"""公开接口快照：把三个包里所有公开的类、函数、常量写进 docs/interfaces.md（A5 ①，接口记录的签名部分）。

签名由这个脚本从代码生成，不让人或智能体手抄：手抄的签名迟早和代码对不上。
docs/interfaces.md 进 Git，由 tests/architecture/test_api_snapshot.py 守着：接口一变，测试就红。

用法（仓库根目录）：
    uv run python scripts/api_snapshot.py                     只检查：和代码一致时退出码 0，不一致时打印差异
    uv run python scripts/api_snapshot.py --write             重新生成（人确认了接口变化以后再运行）
    uv run python scripts/api_snapshot.py --compare <仓库>    拿另一个仓库的代码生成快照，逐行对照（只读）

读法：只读源码、不 import（环境出了问题也拿得到快照）；列出别人会依赖的东西（公开的类、函数、常量、
字段和方法签名）；下划线开头的名字、除 __init__ / __call__ 以外的双下划线方法不列；文档字符串不列
（每个人写的说明不同，签名相同就是接口相同）。
模块自动发现：三个包 src/ 下的每个 .py，名字不以下划线开头（__init__.py 除外），有公开内容的才列。
"""

from __future__ import annotations

import argparse
import ast
import difflib
import sys
from pathlib import Path

# 仓库根：本文件在 scripts/ 下，往上一级就是仓库根。不依赖“当前目录在哪”
ROOT = Path(__file__).resolve().parent.parent
# 快照放在哪（相对仓库根）
SNAPSHOT = Path("docs") / "interfaces.md"
# 三个包的源码目录：快照扫描这三处
SOURCE_ROOTS = ("packages/core/src", "packages/training/src", "services/api/src")
HEADER = """# 公开接口快照

> 由 `uv run python scripts/api_snapshot.py --write` 生成，不要手改；
> `tests/architecture/test_api_snapshot.py` 保证它和代码一致。
> 新增的行是这一步该有的；**已有的行被改或被删，就是改了已有接口**：先停下来问人。
"""
# 双下划线方法里只保留这两个：构造和调用是真正的对外接口，__repr__ 之类不是
KEPT_DUNDERS = {"__init__", "__call__"}


def first_line(node: ast.AST) -> str:
    """文档字符串的第一行（没有就是空串）。"""
    # 只有模块、类、函数带文档字符串；其他节点不去取
    doc = (
        ast.get_docstring(node)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        else None
    )
    # 多行文档只取第一行：每个人的说明写法不同，签名相同才算接口相同
    return doc.strip().splitlines()[0] if doc else ""


def is_public(name: str) -> bool:
    """公开名字：不以 _ 开头，或者是在 KEPT_DUNDERS 里的那几个。"""
    return not name.startswith("_") or name in KEPT_DUNDERS


def signature(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """一个函数的签名文字：装饰器 + def/async def + 名字 + 参数 + 返回类型。"""
    # 装饰器写在签名前面：@classmethod、@property 这些也是别人依赖的接口信息
    decorators = "".join(f"@{ast.unparse(d)} " for d in fn.decorator_list)
    prefix = "async def" if isinstance(fn, ast.AsyncFunctionDef) else "def"
    returns = f" -> {ast.unparse(fn.returns)}" if fn.returns is not None else ""
    # ast.unparse 把语法树转回源码文字：标准化，不保留原来的空格写法
    return f"{decorators}{prefix} {fn.name}({ast.unparse(fn.args)}){returns}"


def assignment(stmt: ast.stmt) -> tuple[str, str] | None:
    """模块或类里的赋值：返回 (名字, 显示文字)；不是公开赋值时返回 None。"""
    # 带类型注解的赋值：LIMIT: int = 3
    if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
        name = stmt.target.id
        text = f"{name}: {ast.unparse(stmt.annotation)}"
        if stmt.value is not None:
            text += f" = {ast.unparse(stmt.value)}"
        return name, text
    # 普通赋值：X = 1（只认单目标、单名字的写法）
    if isinstance(stmt, ast.Assign) and len(stmt.targets) == 1 and isinstance(stmt.targets[0], ast.Name):
        name = stmt.targets[0].id
        return name, f"{name} = {ast.unparse(stmt.value)}"
    # 类型别名：Group = Literal[...] 这种 PEP 695 写法
    if isinstance(stmt, ast.TypeAlias) and isinstance(stmt.name, ast.Name):
        return stmt.name.id, ast.unparse(stmt)
    return None


SHOW_DOC = False  # --doc 打开：三个人的文档字符串必然不同，对拍时默认不比


def with_doc(text: str, node: ast.AST) -> str:
    """一行接口文字；SHOW_DOC 打开时在末尾附上文档字符串第一行。"""
    doc = first_line(node) if SHOW_DOC else ""
    return f"- `{text}`" + (f"：{doc}" if doc else "")


def class_lines(cls: ast.ClassDef) -> list[str]:
    """一个类的标题行，加上它的公开字段和方法（缩进两格）。"""
    # PEP 695 泛型参数：class Registry[T] 里的 [T]
    params = f"[{', '.join(ast.unparse(p) for p in cls.type_params)}]" if cls.type_params else ""
    # 基类和关键字参数（例如 metaclass=...）；它们也是接口的一部分
    bases = [ast.unparse(b) for b in cls.bases] + [ast.unparse(k) for k in cls.keywords]
    head = f"class {cls.name}{params}" + (f"({', '.join(bases)})" if bases else "")
    lines = [with_doc(head, cls)]
    for stmt in cls.body:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            if is_public(stmt.name):
                lines.append(f"  - `{signature(stmt)}`")
        else:
            found = assignment(stmt)
            if found and not found[0].startswith("_"):
                lines.append(f"  - `{found[1]}`")
    return lines


def snapshot(path: Path, module: str) -> list[str]:
    """一个模块的快照：标题、空行、若干行接口、空行。"""
    # ast.parse 只解析、不导入：装坏了的包也拿得到快照
    tree = ast.parse(path.read_text(encoding="utf-8"))
    entries: list[str] = []
    for stmt in tree.body:
        if isinstance(stmt, ast.ClassDef):
            if not stmt.name.startswith("_"):
                entries.extend(class_lines(stmt))
        elif isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
            if not stmt.name.startswith("_"):
                entries.append(with_doc(signature(stmt), stmt))
        else:
            found = assignment(stmt)
            # 下划线开头的私有常量不列；__all__ 是给 ruff 的导出声明，不算接口
            if found and not found[0].startswith("_") and found[0] != "__all__":
                entries.append(f"- `{found[1]}`")
    lines = [f"## `{module}`", ""]
    doc = first_line(tree) if SHOW_DOC else ""
    if doc:
        lines += [doc, ""]
    return lines + entries + [""]


def modules(root: Path) -> list[tuple[str, Path]]:
    """(模块名, 源码路径)，按模块名排序。"""
    found = []
    for base in SOURCE_ROOTS:
        src = root / base
        for path in sorted(src.rglob("*.py")):
            # 下划线开头的文件名是私有的，不列；__init__.py 例外：它是包的入口
            if path.name.startswith("_") and path.name != "__init__.py":
                continue
            parts = path.relative_to(src).with_suffix("").parts
            # __init__.py 的模块名是它所在的包名：pkg/__init__.py → pkg
            if parts[-1] == "__init__":
                parts = parts[:-1]
            found.append((".".join(parts), path))
    # 按模块名排序：输出和目录遍历顺序无关，任何机器上生成的结果一致
    return sorted(found)


def render(root: Path = ROOT) -> str:
    """整份快照的文字：每个有公开内容的模块一节。"""
    out = [HEADER]
    for name, path in modules(root):
        section = snapshot(path, name)
        # 标题、空行、结尾空行之外还有内容，才收进快照
        if len(section) > 3:
            out.extend(section)
    return "\n".join(out).rstrip("\n") + "\n"


def _entries(text: str) -> list[tuple[str, str]]:
    """把快照拆成 (模块, 一行接口)；类里的方法和字段前面带上类名，对照时才看得出是谁的。"""
    out: list[tuple[str, str]] = []
    module, owner = "", ""
    for line in text.splitlines():
        if line.startswith("## `"):
            module, owner = line[4:-1], ""
        elif line.startswith("- `"):
            item = line[2:]
            is_class = item.startswith("`class ")
            # 从 "`class Box(Base)`" 里取出类名 Box：去掉反引号，截到 ( 或 [ 之前
            owner = item.strip("`").split("class ", 1)[1].split("(")[0].split("[")[0] if is_class else ""
            out.append((module, item))
        elif line.startswith("  - `") and module:
            out.append((module, f"{owner} 里：{line[4:]}"))
    return out


def compare(mine: Path, other: Path) -> list[str]:
    """两个仓库的公开接口逐行对照；返回差异行，空列表就是逐行相同。"""
    a, b = _entries(render(mine)), _entries(render(other))
    lines: list[str] = []
    # 两边的模块名取并集、排序：只在一侧出现的模块也要报
    for module in sorted({m for m, _ in a} | {m for m, _ in b}):
        here = [item for m, item in a if m == module]
        there = [item for m, item in b if m == module]
        only_here = [item for item in here if item not in there]
        only_there = [item for item in there if item not in here]
        if only_here or only_there:
            lines.append(f"## {module}")
            lines += [f"  - 这里有、那里没有   {item}" for item in only_here]
            lines += [f"  + 那里有、这里没有   {item}" for item in only_there]
    return lines


def main(argv: list[str] | None = None) -> int:
    """命令行入口：默认比对，--write 生成，--compare 跨仓库对照。"""
    parser = argparse.ArgumentParser(description="公开接口快照")
    parser.add_argument("--write", action="store_true", help="重新生成 docs/interfaces.md")
    parser.add_argument("--compare", type=Path, metavar="仓库", help="和另一个仓库的公开接口逐行对照（只读）")
    args = parser.parse_args(argv)
    if args.compare is not None:
        other = args.compare.resolve()
        # 传进来的必须是仓库根目录（下面有源码目录），否则生成的快照是空的，对照没有意义
        if not any((other / base).is_dir() for base in SOURCE_ROOTS):
            print(f"{other} 下面找不到 {SOURCE_ROOTS[0]}：路径要写到仓库根目录（有 pyproject.toml 的那一层）")
            return 2
        lines = compare(ROOT, other)
        changed = sum(1 for line in lines if not line.startswith("## "))
        print("\n".join(lines))
        print(f"一共 {changed} 行不同" if changed else "两个仓库的公开接口逐行相同")
        return 1 if changed else 0
    expected = render()
    path = ROOT / SNAPSHOT
    if args.write:
        path.parent.mkdir(parents=True, exist_ok=True)
        # newline="\n"：固定 LF，Windows 上也不会写成 CRLF，不同机器的快照逐字节一致
        path.write_text(expected, encoding="utf-8", newline="\n")
        print(f"已写入 {SNAPSHOT.as_posix()}")
        return 0
    actual = path.read_text(encoding="utf-8") if path.is_file() else ""
    if actual == expected:
        print("接口快照：和代码一致")
        return 0
    diff = difflib.unified_diff(actual.splitlines(), expected.splitlines(), "快照", "代码", lineterm="", n=0)
    print("\n".join(diff))
    print("接口快照：和代码不一致（以 - 开头的是快照里有、代码里没有：已有接口被改或被删）")
    return 1


if __name__ == "__main__":
    sys.exit(main())
