"""班级费率配置和常量，可手动修改新增。"""

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

WEEKDAY_NAMES: dict[int, str] = {
    0: "一",
    1: "二",
    2: "三",
    3: "四",
    4: "五",
    5: "六",
    6: "日",
}

# 同班级同色用的背景色调色板（12 色，色相/明暗拉开，避免相似度过高）
COLOR_PALETTE: list[str] = [
    "FFF5B7B1",  # 浅红
    "FFAED6F1",  # 浅蓝
    "FFA9DFBF",  # 浅绿
    "FFD7BDE2",  # 浅紫
    "FFF9E79F",  # 浅黄
    "FFEDBB99",  # 浅橙
    "FFA3E4D7",  # 浅青
    "FFF1948A",  # 珊瑚红（较饱和）
    "FF85C1E9",  # 中蓝（较饱和）
    "FF82E0AA",  # 中绿（较饱和）
    "FFC39BD3",  # 中紫（较饱和）
    "FFF4D03F",  # 金黄（较饱和）
]
