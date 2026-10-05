# 沐晨课程管理系统

培训机构（沐晨）的课程管理系统。项目由三部分组成，正在从桌面版向 Web 版迁移：

| 子项目 | 目录 | 技术栈 | 状态 |
|---|---|---|---|
| **桌面版** | `codes/desktop/` | Python 3.13 + PySide6 + openpyxl + JSON | v0.4 冻结，**逐步退役** |
| **后端** | `codes/server/` | Python 3.11+ + FastAPI + SQLModel + SQLite | 开发中 |
| **前端（Web 验证版）** | `codes/web/` | Vue 3 + Vite + Vue Router + Pinia | 开发中 |

**主线**：课程管理系统 → `https://jiaowu.palmsugar.cn`

> 桌面版是项目的前身，最终只保留「算课时 + 导考勤表」两个功能。
> Web 版定位是**一次性流程原型**：先把产品流程验证通，再上 uniapp 出 H5 + 微信小程序。

## 功能

### 桌面版（`codes/desktop/`）— 已在生产使用

- 录入上课信息：日期、时间、课时数、**班级名**、班级类型、备注
- 实时预览与自动计算薪酬
- **班级费率管理**：可视化配置不同班级的时薪（增删改查）
- **历史记录加载**：随时回看之前保存的月度数据
- **日期筛选**：显示全部或某一个月的记录，导出跟随筛选
- 导出格式化的 Excel 结算表（同班级名同色区分，严格按日期排列）
- 双击编辑已有记录，一键清除全部

> ⚠️ `codes/desktop/dist/` 下的历史 exe **一个都不能删**，必须保留到网页版上线并确认稳定为止。
> 同目录的 `records.json`、`梁筱_工资结算表.xlsx` 是**真实生产数据**，不是测试文件。

### 课程管理系统（v1.0，进行中）

- [x] 手机号登录 + 三种角色（超管 / 管理员 / 老师）
- [x] 账号管理（只停用不删除）
- [x] 班级管理（班级类型 → 费率联动）
- [x] 学生管理 + **每人独立课时余额**（流水记账）
- [ ] 课程视图 + 考勤签到
- [ ] 课表导出 Excel
- [ ] 改期申请 + 审批流
- [ ] 微信小程序

## 使用方式

### 桌面版

直接运行（无需 Python）：

```
codes/desktop/dist/SalaryCounter-v0.4.exe
```

从源码运行：

```bash
pip install pyside6 openpyxl
python codes/desktop/main.py
```

重新打包：双击 `codes/desktop/build.bat`，**用新的 `--name`**（如 `SalaryCounter-v0.5`），
与历史版本共存，不要覆盖。

### 后端（`codes/server/`）

```bash
cd codes/server
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/init_db.py
python scripts/init_superadmin.py --phone 138xxxxxxxx --name 名字
uvicorn app.main:app --reload
```

浏览器打开 `/docs` 点着测。

### 前端（`codes/web/`）

```bash
cd codes/web
npm install
npm run dev      # http://localhost:5173，手机同 Wi-Fi 用 http://<电脑局域网IP>:5173
npm run build
```

## 技术栈

**桌面版**：PySide6 · openpyxl · Python 3.13
**后端**：FastAPI · SQLModel · SQLite(WAL) · PyJWT · bcrypt · openpyxl
**前端**：Vue 3 · Vite · Vue Router · Pinia（手写 CSS，原生 fetch，JavaScript）

## 项目结构

```
├── codes/
│   ├── desktop/     # 桌面版（PySide6）+ dist/ 历史 exe 与生产数据
│   ├── server/      # FastAPI 后端（app/ · scripts/ · tests/）
│   └── web/         # Vue 3 Web 版
├── docs/            # PRD、实施计划、开发日志、需求讨论记录、服务器操作手册
├── assets/          # design/ 设计素材 · bug/ 报错截图 · reference/ 参考资料
├── notes/           # 学习笔记与踩坑记录
├── AGENTS.md        # ★ AI 开发指引（动手前先读）
└── README.md
```

## 文档

| 文档 | 内容 |
|---|---|
| [`AGENTS.md`](AGENTS.md) | **★ AI 开发指引**：目录结构、硬性约束、各子项目开发规则 |
| [`docs/实施计划.md`](docs/实施计划.md) | **★ 实施计划**：DDL、接口签名、分期计划 |
| [`docs/后端方案设计.md`](docs/后端方案设计.md) | 技术方案（决策依据、三种课时、部署方案） |
| [`docs/开发日志.md`](docs/开发日志.md) | 各版本开发记录 |
| [`docs/Phase0-服务器操作手册.md`](docs/Phase0-服务器操作手册.md) | 部署、备份恢复、表结构变更 |
| [`docs/PRD.md`](docs/PRD.md) | 产品需求文档 |
