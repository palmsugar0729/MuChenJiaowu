"""给 lessons 表补 `content`（上课内容）列。

背景：2026-10-05 用户要求「老师操作考勤时必须写上到哪了」，那是一个**新字段**，
不是原来那个排课备注 `note`（覆盖 note 会把排课时的备注吃掉）。

用法（在 codes/server 下）：
    python scripts/migrate_add_lesson_content.py

⚠️ 为什么需要这个脚本：`init_db()` 走的是 SQLModel 的 `create_all`，
   **只会建不存在的表，不会给已存在的表加列**。所以开发库和线上库都得跑一次。
   测试库每次从零重建，所以**测试全绿不代表线上库有这个列**。

幂等：已经有这列就什么都不做，重复跑安全。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db import engine  # noqa: E402

COLUMN = "content"

# SQLite 的 ALTER TABLE ADD COLUMN 不支持非空列不带默认值。
# 用 `NOT NULL DEFAULT ''` —— 历史课程的 content 是空串，语义正好是
# 「这节课没记录内容」（那些课是在这个功能之前上的）。
DDL = f"ALTER TABLE lessons ADD COLUMN {COLUMN} TEXT NOT NULL DEFAULT ''"


def main() -> None:
    inspector = inspect(engine)
    if "lessons" not in inspector.get_table_names():
        print("lessons 表还不存在，直接跑 init_db.py 即可（新库自带这一列）")
        return

    columns = {col["name"] for col in inspector.get_columns("lessons")}
    print(f"数据库：{settings.database_url}")

    if COLUMN in columns:
        print(f"lessons.{COLUMN} 已存在，无需改动")
        return

    with engine.begin() as conn:
        conn.execute(text(DDL))

    print(f"已给 lessons 加上 {COLUMN} 列")
    print("历史课程的 content 是空串 —— 那些课是在「上课内容」功能之前上的")


if __name__ == "__main__":
    main()
