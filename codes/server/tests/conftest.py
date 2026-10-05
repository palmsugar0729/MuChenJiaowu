"""测试夹具。

⚠️ 必须在导入任何 app 模块之前设好 DATABASE_URL，
否则 app.core.config 会读到真实数据库路径。
"""

import os
import sys
import tempfile
from pathlib import Path

_SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_SERVER_DIR))

_TEST_DB = Path(tempfile.gettempdir()) / "muchen_test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_TEST_DB.as_posix()}"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlmodel import Session, SQLModel  # noqa: E402

from app import models  # noqa: E402,F401  —— 必须先导入，表才会注册
from app.core.security import create_access_token, hash_password  # noqa: E402
from app.db import engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Class, Role, Student, User  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _setup_database():
    SQLModel.metadata.drop_all(engine)
    SQLModel.metadata.create_all(engine)
    yield
    engine.dispose()
    _TEST_DB.unlink(missing_ok=True)


@pytest.fixture(autouse=True)
def _clean_tables():
    """每个测试前清空所有表，测试之间互不干扰。

    清表比 drop/create 快得多，而表结构本身是 session 级的、不用重建。
    """
    with engine.begin() as conn:
        for table in reversed(SQLModel.metadata.sorted_tables):
            conn.execute(table.delete())


@pytest.fixture
def session():
    with Session(engine) as s:
        yield s


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ── 账号相关夹具（Phase 1）────────────────────────

DEFAULT_PASSWORD = "pw123456"


@pytest.fixture
def make_user(session):
    """按角色造账号。手机号自己给，方便在断言里对着看。"""

    def _make(phone: str, role=Role.teacher, password: str = DEFAULT_PASSWORD, **kwargs):
        user = User(
            phone=phone,
            display_name=kwargs.pop("display_name", f"测试-{phone}"),
            password_hash=hash_password(password),
            role=role,
            **kwargs,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user

    return _make


@pytest.fixture
def headers_for():
    """直接签一个 token，跳过登录 —— 测别的接口时不想被登录逻辑牵连。"""

    def _headers(user) -> dict:
        return {"Authorization": f"Bearer {create_access_token(user.id, user.role.value)}"}

    return _headers


# ── 班级 / 学生夹具（Phase 2+3）────────────────────


@pytest.fixture
def make_class(session):
    """直接建班级行，绕开接口 —— 测学生/课时接口时不想被班级校验牵连。"""

    def _make(name: str = "YDY001", class_type: str = "1对1", rate: float = 80.0, **kwargs):
        klass = Class(name=name, class_type=class_type, rate=rate, **kwargs)
        session.add(klass)
        session.commit()
        session.refresh(klass)
        return klass

    return _make


@pytest.fixture
def make_student(session):
    def _make(name: str = "测试学生", **kwargs):
        student = Student(name=name, **kwargs)
        session.add(student)
        session.commit()
        session.refresh(student)
        return student

    return _make


@pytest.fixture
def admin_headers(make_user, headers_for):
    """管理员身份 —— 能过所有写接口的鉴权。"""
    return headers_for(make_user("13900000001", role=Role.admin))


@pytest.fixture
def teacher_headers(make_user, headers_for):
    """老师身份 —— 读接口通、写接口一律 403。"""
    return headers_for(make_user("13900000002", role=Role.teacher))


@pytest.fixture
def super_admin_headers(make_user, headers_for):
    return headers_for(make_user("13900000003", role=Role.super_admin))
