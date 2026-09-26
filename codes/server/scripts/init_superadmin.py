"""创建超管账号。

系统里第一个管理员从哪来？——用这个脚本直接在服务器上建，之后所有管理员
都由超管在界面上开。

用法（在 codes/server 下）：
    python scripts/init_superadmin.py --phone 13800138000 --name 张三
    python scripts/init_superadmin.py --phone 13800138000 --name 张三 --password '自定义'

⚠️ 密码只在这里打印一次。系统不存明文，忘了只能重置。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlmodel import Session, select  # noqa: E402

from app.core.security import generate_password, hash_password  # noqa: E402
from app.db import engine, init_db  # noqa: E402
from app.models import Role, User  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="创建超管账号")
    parser.add_argument("--phone", required=True, help="手机号（登录用）")
    parser.add_argument("--name", required=True, help="真实姓名")
    parser.add_argument("--password", default=None, help="不传则自动生成")
    parser.add_argument(
        "--force", action="store_true", help="已存在超管时仍然创建"
    )
    args = parser.parse_args()

    init_db()

    with Session(engine) as session:
        existing = session.exec(
            select(User).where(User.role == Role.super_admin)
        ).all()

        if existing and not args.force:
            print("已存在超管账号，未做任何改动：")
            for user in existing:
                print(f"  - {user.display_name}（{user.phone}）")
            print("\n如确实要再加一个，加 --force 重跑。")
            return 1

        if session.exec(select(User).where(User.phone == args.phone)).first():
            print(f"手机号 {args.phone} 已被占用，请换一个。")
            return 1

        password = args.password or generate_password()
        session.add(
            User(
                phone=args.phone,
                display_name=args.name,
                password_hash=hash_password(password),
                role=Role.super_admin,
                must_change_password=True,
            )
        )
        session.commit()

    print("=" * 46)
    print("  超管账号已创建")
    print("=" * 46)
    print(f"  手机号：{args.phone}")
    print(f"  密码　：{password}")
    print("=" * 46)
    print("\n⚠️ 密码只显示这一次，立刻抄下来。首次登录会强制改密。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
