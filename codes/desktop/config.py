"""班级费率配置和常量，可手动修改新增。"""

CLASS_RATES: dict[str, float] = {
    "1对1": 80,
    "1对2": 100,
    "1对3": 100,
    "1对4": 110,
    "1对5": 120,
}

DEFAULT_RATE: float = 100

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
