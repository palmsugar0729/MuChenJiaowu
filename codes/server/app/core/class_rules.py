"""班级名前缀规则 + 费率档位 —— 从 `codes/desktop/config.py` 移植。

⚠️ 为什么是「复制」而不是 import：部署时只上传 `codes/server`，服务器上**没有**
   `codes/desktop`。所以这份是桌面版那套规则的镜像，**两边逻辑必须一致**——
   判定不一致会导致同一节课在桌面版和后端算出不同的时薪（见 docs/实施计划.md §3.2）。

放 `core/` 的原因：这里全是纯函数，不碰 DB、不碰 pydantic Settings，
   services 和 routers 都要用，测试时可以脱离建库直接测规则。
"""

CLASS_RATES: dict[str, float] = {
    "1对1": 80,
    "1对2": 100,
    "1对3": 100,
    "1对4": 110,
    "1对5": 120,
}

DEFAULT_RATE: float = 100

# ── 班级名 → 班级类型 联动规则 ──────────────────────
# 班级名是一串编码，看开头就能定班级类型，后面跟什么都不管。
# 例：YDY001N5 → 1对1
CLASS_NAME_RULES: list[tuple[str, str]] = [
    ("YDY", "1对1"),
    ("YDE", "1对2"),
]

# 小班：开头是 XB，但具体几人的班要自己选
SMALL_CLASS_PREFIX: str = "XB"
SMALL_CLASS_TYPES: list[str] = ["1对3", "1对4", "1对5"]
SMALL_CLASS_DEFAULT: str = "1对3"


class ClassRuleError(ValueError):
    """前缀规则 / 费率校验失败。router 捕获后转成 400。

    继承 ValueError 是为了兼容「校验失败抛 ValueError」的约定，
    但用独立类型是为了 router 能精确捕获，不会误吞别的 ValueError。
    """


def class_type_rule(class_name: str) -> tuple[str, list[str], str | None]:
    """按班级名前缀推断班级类型，返回 (模式, 可选项, 默认值)。

    - "fixed"：前缀直接定死了类型，界面应锁定不让改
    - "small"：小班，从可选项里自己挑，默认 SMALL_CLASS_DEFAULT
    - "free" ：前缀认不出来，沿用原来的手动选择方式（默认值 None = 保持当前选择）
    """
    name = class_name.strip().upper()

    for prefix, class_type in CLASS_NAME_RULES:
        if name.startswith(prefix):
            return "fixed", [class_type], class_type

    if name.startswith(SMALL_CLASS_PREFIX):
        return "small", list(SMALL_CLASS_TYPES), SMALL_CLASS_DEFAULT

    return "free", list(CLASS_RATES.keys()), None


def resolve_class_type(name: str, class_type: str | None) -> str:
    """按班级名前缀校验并补全 `class_type`。

    规则（docs/实施计划.md §3.2）：
    - YDY / YDE：前缀定死了类型，`class_type` 可以省，但给了就必须对上
    - XB：**必须显式指定** 1对3 / 1对4 / 1对5，不给就报错（这是文档的明确要求）
    - 其他：必须显式给一个非空类型（兼容历史命名）

    单独拆出来是给 PATCH 用的：改班级名时只需要重新解析类型，
    **不该顺手把费率也改掉**（见 resolve_class_fields 的注释）。
    """
    if not name or not name.strip():
        raise ClassRuleError("班级名不能为空")

    mode, options, default = class_type_rule(name)

    if mode == "fixed":
        if class_type is None:
            return default
        if class_type != default:
            raise ClassRuleError(
                f"班级名以 {name.strip().upper()[:3]} 开头，班级类型只能是「{default}」"
            )
        return class_type

    if mode == "small":
        if not class_type:
            raise ClassRuleError(
                f"班级名以 {SMALL_CLASS_PREFIX} 开头，必须指定班级类型"
                f"（{' / '.join(SMALL_CLASS_TYPES)}）"
            )
        if class_type not in options:
            raise ClassRuleError(
                f"小班的班级类型只能是 {' / '.join(SMALL_CLASS_TYPES)}"
            )
        return class_type

    # free：前缀认不出来，必须自己给
    if not class_type:
        raise ClassRuleError("请指定班级类型")
    return class_type


def resolve_class_fields(
    name: str,
    class_type: str | None,
    rate: float | None,
) -> tuple[str, float]:
    """建班级用：按前缀校验 `class_type`，并按类型补全 `rate`。

    `rate` 缺省时按 `CLASS_RATES[class_type]` 补。如果这个类型不在费率表里、
    又没显式给 rate，**报错而不是悄悄用 DEFAULT_RATE**——那会录进一个错价，
    而且要等到发工资才会发现。
    """
    resolved_type = resolve_class_type(name, class_type)

    if rate is None:
        if resolved_type not in CLASS_RATES:
            raise ClassRuleError(
                f"班级类型「{resolved_type}」没有对应的默认费率，请手动填写费率"
            )
        rate = CLASS_RATES[resolved_type]
    elif rate <= 0:
        raise ClassRuleError("费率必须大于 0")

    return resolved_type, rate
