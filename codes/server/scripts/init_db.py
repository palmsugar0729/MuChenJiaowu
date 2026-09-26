"""建表。

用法（在 codes/server 下）：
    python scripts/init_db.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import inspect  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.db import engine, init_db  # noqa: E402


def main() -> None:
    init_db()
    tables = sorted(inspect(engine).get_table_names())
    print(f"数据库：{settings.database_url}")
    print(f"已建表（{len(tables)}）：")
    for name in tables:
        print(f"  - {name}")


if __name__ == "__main__":
    main()
