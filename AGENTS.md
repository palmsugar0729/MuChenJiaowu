# AGENTS.md — AI 开发指引

## 项目简介

**培训机构课程管理系统**，由三部分组成：

| 子项目 | 目录 | 技术栈 | 状态 |
|---|---|---|---|
| **桌面版** | `codes/desktop/` | Python 3.13 + PySide6 + openpyxl + JSON | v0.4 冻结，**逐步退役** |
| **后端** | `codes/server/` | Python 3.11+ + FastAPI + SQLModel + SQLite | 开发中 |
| **前端** | `codes/web/` | uniapp (Vue 3) → H5 网页 + 微信小程序 | 未开始 |

**主线**：课程管理系统（`jiaowu.palmsugar.cn`）。桌面版最终只保留「算课时 + 导考勤表」。

> 📖 **动手前先读** `docs/实施计划.md` —— 目录结构、表结构 DDL、接口签名、分期计划都在那里。

---

## 文件夹结构

| 文件夹 | 用途 |
|---|---|
| `codes/desktop/` | 桌面版源码（唯一代码目录） |
| `codes/server/` | FastAPI 后端 |
| `codes/web/` | uniapp 前端 |
| `docs/` | 产品文档、PRD、需求迭代记录、关键决策文档 |
| `assets/design/` | 设计素材、UI 参考图、效果图 |
| `assets/bug/` | 测试报错截图 |
| `assets/reference/` | 参考图、灵感收集、竞品截图 |
| `notes/` | 学习笔记，开发中踩过的坑和技术方案记录 |

### 三个独立虚拟环境

| 子项目 | 环境 | 说明 |
|---|---|---|
| `codes/desktop/` | **全局 Python 3.13** | 没有 venv，`build.bat` 直接调全局 `python`。已装的：PySide6 6.11 / openpyxl / PyInstaller 6.20 |
| `codes/server/` | `codes/server/.venv` | FastAPI 系 |
| `codes/web/` | npm 管理 | Node 18+ |

> ⚠️ 桌面版和后端依赖**互相冲突**（PySide6 vs FastAPI）。桌面版走全局 Python，
> 所以**后端千万不要 `pip install` 到全局**，一律进 `codes/server/.venv`。

---

## ⚠️ 硬性约束

| 约束 | 说明 |
|---|---|
| **保留桌面版 exe** | `codes/desktop/dist/` 下的历史 exe **一个都不能删**，必须保留到**网页版和小程序上线且用户确认稳定**为止。用户每月靠它给领导交报表 |
| **不覆盖历史 exe** | 打包新版本用不同 `--name`（如 `SalaryCounter-v0.4`），与历史版本共存 |
| **`dist/` 里的用户数据** | `records.json`、`梁筱_工资结算表.xlsx` 是真实生产数据，不是测试文件 |
| **brand 主色** | `#a9c5b3`，所有 palmsugar 系列项目通用 |
| **git push 需开 VPN** | 配了本地代理 `127.0.0.1:7897`。VPN 关着时 push 必定失败；开着偶尔断（`Recv failure`），**重试即可，不要改代理配置** |
| **文档要同步** | 改完代码同步更新 PRD / 开发日志 / 实施计划 |

---

## 桌面版规则（`codes/desktop/`）

### 架构分层（严格遵循）

```
codes/desktop/
  main.py              # 入口，组装各模块
  models.py            # 纯数据类（dataclass），不依赖 PySide6 / openpyxl
  config.py            # 班级费率等可配置常量
  storage.py           # JSON 读写，依赖 models
  excel_exporter.py    # openpyxl 导出逻辑
  ui/
    main_window.py     # PySide6 主窗口
    rate_dialog.py     # 费率管理弹窗
```

- `models.py` 是纯净层，只能使用 Python 标准库 + `config.py`
- `excel_exporter.py` 只依赖 openpyxl 和 models
- `ui/` 负责所有 PySide6 相关代码
- 新功能从 `main_window.py` 的 signal 连线开始，经过数据层，到输出层

### 构建打包

双击 `codes/desktop/build.bat`，或：

```bash
cd codes/desktop
python -m PyInstaller --onefile --windowed --name SalaryCounter-vX.X main.py
```

产物在 `codes/desktop/dist/`。CI 见 `.github/workflows/build.yml`（推 `v*` tag 触发多平台打包 + Release）。

详见 `notes/pyinstaller-packaging.md`。

---

## 后端规则（`codes/server/`）

> 完整设计见 `docs/实施计划.md` 第二、三节。

```
codes/server/
  app/
    main.py          # FastAPI 实例 + 路由挂载 + CORS
    db.py            # engine / session（含 WAL + 外键 PRAGMA）
    models.py        # 【全部 SQLModel 表定义】唯一真相源
    schemas.py       # 请求/响应 Pydantic 模型
    core/            # config / security(bcrypt+JWT) / deps(鉴权)
    routers/         # 按模块拆分的路由
    services/        # 业务逻辑（★ 扣课时事务、课时余额、计薪）
    exporters/       # 从 desktop/excel_exporter.py 移植改造
  scripts/           # init_db / init_superadmin / 导入历史数据
  tests/
```

### 关键规则

- **费率必须快照**：`lessons.rate` 在排课时抄一份班级费率。**绝不**实时 JOIN `classes.rate` 算工资——改一次费率会篡改历史工资表
- **学生余额不存字段**：一律由 `hour_transactions` 求和算出。涉及钱，必须可追溯
- **扣课时只走一个入口**：`services/lessons.py` 的完成课程事务，靠 `uq_consume_once` 唯一索引保幂等
- **出勤状态不影响扣课时**：出勤/请假/缺勤**都扣**，只有课程取消不扣
- **课时 = 小时数**：`amount = -lesson.hours`，不存在两套换算
- **三种「课时」不能混**：教师课时费 / 班级已上课时 / 学生独立余额
- **响应体不包一层**：成功直接返回数据，失败是 `{"detail": "..."}` + 状态码。前端判断成败看状态码，不看包装层
- **改不了角色**：账号的角色定了就不改，要换就新建号——历史记录存的是 `user.id`
- **账号只停用不删除**：`is_active=False`，记录留着。它挂在课程的 `teacher_id`、审批的 `created_by` 上

### 本地开发

```bash
cd codes/server
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python scripts/init_db.py
python scripts/init_superadmin.py --phone 138xxxxxxxx --name 名字
uvicorn app.main:app --reload
```

浏览器打开 `/docs` 点着测。

---

## 前端规则（`codes/web/`）

uniapp (Vue 3)，**一套代码出 H5 + 微信小程序**。先做 H5，Phase 6 再编译小程序。

- 主题色变量集中在 `src/styles/theme.scss`，主色 `#a9c5b3`
- 所有请求走 `src/api/` 的封装，不在页面里裸调
- 权限按角色控制按钮显隐，**同一套页面**（老师看，管理员多几个按钮）

---

## 当前状态

### 桌面版
- [x] v0.1 核心 MVP
- [x] v0.1.1 体验改进
- [x] v0.2 费率管理 + 历史加载
- [x] v0.3 班级名 + 高对比配色 + 日期筛选
- [x] 迁移至 `codes/desktop/`（2026-09-26，打包链路已验证）
- [x] v0.4 班级名 → 班级类型 联动（2026-10-04，**该前缀规则后端 Phase 3 需复用**）

### 课程管理系统（v1.0）
- [x] 方案设计 v3（`docs/后端方案设计.md`）
- [x] 实施计划（`docs/实施计划.md`）
- [x] **Phase 0** 环境搭建（2026-10-04 上线，`https://jiaowu.palmsugar.cn`，重启自愈 + 备份恢复已实测）
- [x] **Phase 1** 后端：登录 + 角色 + 账号管理（2026-10-04，64 个测试全绿）
- [ ] **Phase 2** uniapp：登录 + 课程视图 + 考勤 ← **下一步**
- [ ] Phase 3 学生管理 + 班级管理 + 课时余额
- [ ] Phase 4 考勤管理 + 导出 Excel ← **里程碑：能替代桌面版**
- [ ] Phase 5 审批流
- [ ] Phase 6 微信小程序

---

## 参考资源

| 文档 | 内容 |
|---|---|
| `docs/实施计划.md` | **★ 实施计划**：目录结构、DDL、接口、Phase 0 清单 |
| `docs/后端方案设计.md` | 技术方案 v3（决策依据、三种课时、部署方案） |
| `docs/2026-09-17-需求讨论记录-课程管理系统.md` | 本轮讨论全过程与 16 条决策 |
| `docs/PRD.md` | 产品需求文档 |
| `docs/开发日志.md` | 各版本开发记录 |
| `docs/2026-05-31-需求讨论记录.md` | 项目最初需求讨论，含 Excel 格式解析 |
| `docs/2026-09-13-需求讨论记录-v0.3.md` | v0.3 需求讨论 |
| `notes/pyinstaller-packaging.md` | PyInstaller 打包学习笔记 |
| `assets/design/screenshot_original-effect.png` | 目标效果图 |
| `assets/reference/2026沐晨_4月工资结算表-梁筱.xlsx` | 参考 Excel 文件 |
