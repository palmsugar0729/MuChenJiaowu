# 沐晨课程管理系统 —— 后端

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
  services/    业务逻辑（扣课时事务、课时余额、payroll.py 计薪）
  exporters/   salary_excel.py —— 工资表导出，从 desktop/excel_exporter.py 移植，
               与桌面版**逐单元格一致**（tests/test_export.py 直接对拍）
scripts/       建库、建超管、导入历史数据
tests/
```

## 三条不能违反的规则

1. **费率必须快照** —— `lessons.rate` 在排课时抄一份班级费率。绝不实时 JOIN `classes.rate` 算工资，否则改一次费率会篡改历史工资表。
2. **学生余额不存字段** —— 一律由 `hour_transactions` 求和算出。涉及钱，必须可追溯。
3. **课时 = 小时数** —— `amount = -lesson.hours`。不存在「课时」和「小时」两套换算。

另外几条容易记混的：

- **谁被扣课时看班型**：**1对1 / 1对2 只有「出勤」才扣**（课时是学生自己买的，人没来这节课就没上）；
  **其他班型开课就扣全员**，请假缺勤照样扣（小班的课时是整班一起走的）。只有取消课程不扣。
  规则本体在 `core/class_rules.PER_STUDENT_HOURS_TYPES`。⚠️ 这是**扣钱**的规则，改之前先问用户。
- **三种「课时」不能混**：教师课时费（`hours × lessons.rate`）/ 班级已上课时（`SUM(lessons.hours)`）/ 学生独立余额（流水求和）。
- **计薪只算 `status='completed'` 的课**，且 `/attendance/my`、`/summary`、`/export` 三处
  **共用 `services/payroll.month_rows()` 同一条查询** —— 屏幕上多少，下载下来就是多少。
- **导出月份 `month` 必填**，不做「省略 = 当月」：服务器时区若是 UTC，月初会把当月算成上个月。
