"""给 users 表补登录防爆破的两列。

背景：2026-11-24 用户要求「登录界面连错 5 次锁 1 小时」，需要在用户行上记
失败次数和锁定到期时刻。

用法（在 codes/server 下）：
    python scripts/migrate_add_login_lockout.py

⚠️ `init_db()` 走 `create_all`，**只建不存在的表，不给已有表加列**。
   开发库和线上库都得跑一次；测试库每次从零重建，所以测试全绿不能代替这一步。

幂等：两列都在就什么都不做，重复跑安全。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db import engine  # noqa: E402

# SQLite 的 ADD COLUMN 对非空列必须带默认值。
# locked_until 允许为空 = 没锁；失败次数默认 0。
COLUMNS = {
    "failed_login_attempts": "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0",
    "locked_until": "ALTER TABLE users ADD COLUMN locked_until DATETIME",
}


def main() -> None:
    inspector = inspect(engine)
    if "users" not in inspector.get_table_names():
        print("users 表还不存在，直接跑 init_db.py 即可（新库自带这两列）")
        return

    existing = {col["name"] for col in inspector.get_columns("users")}
    print(f"数据库：{settings.database_url}")

    added = []
    with engine.begin() as conn:
        for name, ddl in COLUMNS.items():
            if name in existing:
                print(f"users.{name} 已存在，跳过")
                continue
            conn.execute(text(ddl))
            added.append(name)

    if added:
        print(f"已给 users 加上：{', '.join(added)}")
        print("所有现有账号都是「未锁定、失败 0 次」")
    else:
        print("无需改动")


if __name__ == "__main__":
    main()
