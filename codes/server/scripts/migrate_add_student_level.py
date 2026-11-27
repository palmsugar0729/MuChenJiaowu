"""给 students 表补 `level` 列（学生级别 N1~N5）。

背景：2026-11-27 用户要求「新建学生时可以选级别，按级别决定第一次自动充多少课时」
（不填 / N5 = 48、N4 / N3 = 51、N2 = 55、N1 = 60）。

用法（在 codes/server 下）：
    python scripts/migrate_add_student_level.py

⚠️ `init_db()` 走 `create_all`，**只建不存在的表，不给已有表加列**。
   开发库和线上库都得跑一次；测试库每次从零重建，所以测试全绿不能代替这一步。
⚠️ **先跑迁移、再重启服务** —— 新代码的 SELECT 里带 `level`，列不存在会直接 500。

幂等：列已经在就什么都不做，重复跑安全。历史学生这条留空（= 没填级别），
不影响他们已有的课时流水。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db import engine  # noqa: E402

# 级别允许为空（历史数据 / 建号时没填），所以不加 NOT NULL，也就不需要默认值
COLUMNS = {
    "level": "ALTER TABLE students ADD COLUMN level TEXT",
}


def main() -> None:
    inspector = inspect(engine)
    if "students" not in inspector.get_table_names():
        print("students 表还不存在，直接跑 init_db.py 即可（新库自带这一列）")
        return

    existing = {col["name"] for col in inspector.get_columns("students")}
    print(f"数据库：{settings.database_url}")

    added = []
    with engine.begin() as conn:
        for name, ddl in COLUMNS.items():
            if name in existing:
                print(f"students.{name} 已存在，跳过")
                continue
            conn.execute(text(ddl))
            added.append(name)

    if added:
        print(f"已给 students 加上：{', '.join(added)}")
        print("历史学生都是「未填级别」，不影响已有课时")
    else:
        print("无需改动")


if __name__ == "__main__":
    main()
