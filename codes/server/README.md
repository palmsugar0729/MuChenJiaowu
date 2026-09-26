# 慕晨课程管理系统 —— 后端

FastAPI + SQLModel + SQLite。

> 完整设计见 [`docs/实施计划.md`](../../docs/实施计划.md)。

## 本地跑起来

```bash
cd codes/server

python -m venv .venv
.venv\Scripts\activate          # Windows；macOS/Linux 用 source .venv/bin/activate

pip install -r requirements.txt

copy .env.example .env          # 然后改掉 JWT_SECRET

python scripts/init_db.py
python scripts/init_superadmin.py --phone 13800138000 --name 你的名字

uvicorn app.main:app --reload
```

浏览器打开 <http://127.0.0.1:8000/docs>，所有接口都能点着测。

## 跑测试

```bash
pytest -v
```

## 目录说明

```
app/
  main.py      FastAPI 入口，路由挂载
  db.py        engine / session（含 SQLite PRAGMA）
  models.py    ★ 全部表定义，唯一真相源
  schemas.py   请求/响应模型
  core/        config / security(bcrypt+JWT) / deps(鉴权)
  routers/     按模块拆分的路由
  services/    业务逻辑（扣课时事务、课时余额、计薪）
  exporters/   Excel 导出（从桌面版移植改造）
scripts/       建库、建超管、导入历史数据
tests/
```

## 三条不能违反的规则

1. **费率必须快照** —— `lessons.rate` 在排课时抄一份班级费率。绝不实时 JOIN `classes.rate` 算工资，否则改一次费率会篡改历史工资表。
2. **学生余额不存字段** —— 一律由 `hour_transactions` 求和算出。涉及钱，必须可追溯。
3. **课时 = 小时数** —— `amount = -lesson.hours`。不存在「课时」和「小时」两套换算。

另外两条容易记混的：

- **出勤状态不影响扣课时**：出勤 / 请假 / 缺勤**都扣**，只有课程取消不扣。
- **三种「课时」不能混**：教师课时费 / 班级已上课时 / 学生独立余额。
