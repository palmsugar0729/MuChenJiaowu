# AGENTS.md — AI 开发指引

## 项目简介

**培训机构课程管理系统**，由三部分组成：

| 子项目 | 目录 | 技术栈 | 状态 |
|---|---|---|---|
| **桌面版** | `codes/desktop/` | Python 3.13 + PySide6 + openpyxl + JSON | v0.4 冻结，**逐步退役** |
| **后端** | `codes/server/` | Python 3.11+ + FastAPI + SQLModel + SQLite | 开发中 |
| **前端（Web 验证版）** | `codes/web/` | Vue 3 + Vite + Vue Router + Pinia | 开发中 |

**主线**：课程管理系统（`jiaowu.palmsugar.cn`）。桌面版最终只保留「算课时 + 导考勤表」。

> 🧭 **前端的路怎么走**：先做普通 **Web 版**把产品流程验证通，再上 **uniapp** 出 H5 + 微信小程序。
> Web 版的定位是**一次性流程原型**，验证通过后由 uniapp 重做、Web 冻结归档（跟桌面版 exe 一样的处理思路）。
> 所以 Web 版里**逻辑归 `api/` 和 `stores/`，视图只做渲染**——将来重写视图是体力活，不是重写系统。
> uniapp 的目录归属（原地替换 `codes/web/` 还是另起 `codes/uniapp/`）**待定**。

> 📖 **动手前先读** `docs/实施计划.md` —— 目录结构、表结构 DDL、接口签名、分期计划都在那里。

---

## 文件夹结构

| 文件夹 | 用途 |
|---|---|
| `codes/desktop/` | 桌面版源码（唯一代码目录） |
| `codes/server/` | FastAPI 后端 |
| `codes/web/` | Web 前端（Vue 3 + Vite，流程验证版） |
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
| `codes/web/` | npm 管理 | Node 24 / npm 11 |

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
| **机构名是「沐晨」不是「慕晨」** | 沐（三点水）。曾把 `app_name` 写成「慕晨」，`/api/health` 一直返回错的。词库/输入法默认给「慕」，**要手动选「沐」** |
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
- **角色修改本期没做**：纯范围控制，不是因为有风险——改角色时 `user.id` 不变，历史不受影响。⚠️ **要加就直接加，绝不要用「新建号 + 改 `lessons.teacher_id`」来绕**，那才是真改写历史
- **账号只停用不删除**：`is_active=False`，记录留着。它挂在课程的 `teacher_id`、审批的 `created_by` 上
- **班级和学生的 DELETE 语义不一样**：班级是**真删**（有课程记录时 400，停用走 `PATCH is_active=false`）；学生是**软删**。别看错
- **批量操作一律「全有或全无」**：入班、批量充值都是。有一个 id 无效就 400、**一行都不写**——部分成功会让用户不知道该不该重试，而重试会重复充值
- **手工流水只允许 `purchase` / `adjust`，`consume` 一律 400**。消耗只能由「完成上课」事务产生，否则 `uq_consume_once` 形同虚设（手工流水的 `lesson_id` 是 `None`，索引根本不拦）
- **课时余额允许为负**：`adjust` 就是用来纠错/退费的，后端只记录不拦截
- **班级 `rate` 缺省按 `class_type` 查 `CLASS_RATES` 自动填**；类型不在表里又没给 rate 就 **400**，绝不静默落到 `DEFAULT_RATE`。PATCH 时**改类型不自动改价**
- **枚举 CHECK 约束用 `enum_check()` 从 Python 枚举推导**（`models.py`），别手写 IN 列表——会漂移。⚠️ 往枚举里加成员后**生产库必须重建**，否则新值被 CHECK 挡在门外（测试库每次自动重建，所以测试会绿，别被骗）

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

**Vue 3 + Vite + Vue Router + Pinia**，手写 CSS（不引 UI 组件库），原生 `fetch`（不引 axios），JavaScript（不用 TS）。

```bash
cd codes/web
npm install
npm run dev      # http://localhost:5173，手机用 http://192.168.31.124:5173
npm run build
```

```
codes/web/src/
  main.js           # createApp + pinia + router + 给 client 接线
  router/index.js   # 路由表 + 全局守卫          ← web-only
  stores/auth.js    # 认证状态                   ← 可移植
  stores/meta.js    # 班级前缀规则 + 费率表（启动取一次缓存住）
  api/client.js     # fetch 封装 + buildQuery    ← 架构可移植
  api/auth.js       # 认证接口                   ← 完全可移植
  api/classes.js    # 班级接口
  api/students.js   # 学生 + 课时流水接口
  utils/storage.js  # localStorage 适配器        ← 换 uniapp 只改这个文件
  utils/date.js     # 日期工具（★ 见下面那条「别用 toISOString」）
  components/AppHeader.vue  # 二级页顶栏，**目前只有这一个组件**
  styles/variables.css  # ★ 品牌变量，改配色只改这里
  styles/base.css       # reset + 通用类         ← web-only
  views/*.vue       # 页面（重写视图时才动）
```

### 必须遵守

- **主题色变量集中在 `src/styles/variables.css`**，主色 `#a9c5b3`。**不要引桌面版 Excel 那 12 个班级配色**——那套是「色差大、易区分」，和界面配色不是一个目的
- **所有请求走 `src/api/` 的封装**，不在页面里裸调
- **前端只写相对的 `/api`**：dev 靠 Vite 代理转发到本机 8000，生产靠 Nginx 反代。**不要写绝对地址**，否则手机访问时那个 `127.0.0.1` 会指向手机自己
- **`api/`、`stores/`、`utils/` 里不许出现 `document` / `window` / `localStorage`**（存储一律走 `utils/storage.js`），**尤其不许 `import router`**——那会形成循环依赖，还会把 web 独有的路由拖进本该可移植的网络层。client 只认 `setTokenGetter` / `setUnauthorizedHandler` 两个回调，在 `main.js` 里接线
- **业务逻辑放 store 的 actions**，view 只做「取值 → 渲染 → 调用」
- **移动优先**：触控目标 ≥44px、不做「悬停才有」的交互、不用 `<table>`、宽度流式
- 权限按角色控制按钮显隐，**同一套页面**（老师看，管理员多几个按钮）。`auth.isAdmin` 已包含超管
- **组件只抽真正重复的东西**：现在只有 `components/AppHeader.vue`（返回 + 标题，6 个页面都要）。**列表行、表单字段用 CSS 类不抽组件**——组件越抽象，移植 uniapp 时越要整个重写（`div`→`view` 的映射藏在组件里），CSS 抄过去便宜得多
- **班级规则不要在页面里硬编码**，走 `stores/meta.js` 取 `GET /classes/rules`。那份只做**即时反馈**（输入 YDY001 自动锁 1对1），**真相源在后端** `core/class_rules.py`，两边不一致也写不进脏数据

### 容易写错的地方

- **登录失败的 401 和 token 过期的 401 是同一个状态码**。client 里判定「会话失效」必须是 **`status === 401 && 本次请求带了 token`**，否则用户输错一次密码就会被踢出登录态
- **改密接口只回 `{message}`，不回 user**。前端得自己把本地的 `must_change_password` 置回 false
- **取「今天」不能写 `new Date().toISOString().slice(0, 10)`**——那是 **UTC** 日期，中国 UTC+8 在本地 00:00~08:00 会取出**昨天**，入班/移出日期整整差一天。用 `utils/date.js` 的 `todayISO()`
- **两种时间字段别混着处理**：`created_at` 是带 `Z` 的 UTC 串，`new Date()` 能正确转到本地时区（用 `formatDateTime()`）；`joined_on` 这类**业务日期**是裸 `YYYY-MM-DD`，**原样显示就好**（用 `formatDate()`）——拿去 `new Date()` 会被当成 UTC 午夜，在本项目用的 UTC+8 是碰巧没事，换个时区就是前一天

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
- [x] **Phase 2W** Web 版起步：脚手架 + 登录闭环（2026-10-05）
- [x] **Phase 2+3 后端 + Web 页面**：班级 / 学生 / 课时余额（2026-10-05，168 个测试全绿）
  > 顺手修了枚举 CHECK 约束一条都没落库的缺陷，**删库重建**才生效（见 `docs/实施计划.md` 第三节）。
  > lessons / attendance 的接口**没做**，下一轮。
- [ ] **下一步**：lessons + attendance 接口 + 课程视图 + 考勤页
  > ⚠️ Phase 2 的验收标准（提交考勤 → 学生课时被扣）依赖班级和学生数据，
  > 而那是 Phase 3 的内容。**排期上 2 和 3 的后端必须合并做**，不能按编号顺序走
  > —— 合并的那部分本轮已经做完了，剩下 lessons / attendance。
- [ ] Phase 4 导出 Excel ← **里程碑：能替代桌面版**
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
