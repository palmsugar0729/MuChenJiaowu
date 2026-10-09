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
    services/        # 业务逻辑（★ 扣课时事务、课时余额、payroll.py 计薪）
    exporters/       # salary_excel.py：从 desktop/excel_exporter.py 移植，逐单元格一致
  scripts/           # init_db / init_superadmin / 导入历史数据
  tests/
```

### 关键规则

- **费率必须快照**：`lessons.rate` 在排课时抄一份班级费率。**绝不**实时 JOIN `classes.rate` 算工资——改一次费率会篡改历史工资表
- **学生余额不存字段**：一律由 `hour_transactions` 求和算出。涉及钱，必须可追溯
- **扣课时只走一个入口**：`services/lessons.py` 的完成课程事务，靠 `uq_consume_once` 唯一索引保幂等。**考勤与「完成上课」是同一个动作**（`POST /lessons/{id}/complete` 必带 `content`，收可选 `items`），一次事务里写考勤 + 扣课时 + 记内容 + 改状态
- **谁被扣课时看班型，不看单个学生的出勤**（用户 2026-10-05 定的口径，**2026-10-07 把 1对2 也归进第一档**，都**推翻了原来「三种状态都扣」那版**）：
  - **1对1 / 1对2 → 只有「出勤」才扣**。学生自己买的课时，上几次扣几次；人没来这节课就没上，收钱没道理
  - **其他班型 → 开课就扣全员**，请假缺勤照样扣。小班课时是整班一起走的，请假也占着时段和老师
  - 规则本体在 `core/class_rules.PER_STUDENT_HOURS_TYPES`（`charges_only_present()` 读它），按 `class_type` 判（**不是**按班级名前缀）
  - ⚠️ 「其他」包含认不出的自定义类型：宁可多收，不能漏收
  - ⚠️ 这是**扣钱**的规则，改之前先问用户，别照着「看起来更合理」去推
- **课时不够就整节课失败**（400，`detail` 里列出是谁、还剩多少、需要多少），**绝不扣成负数**。全有或全无，一个人都不写
- **上课内容 `lessons.content` 必填**：老师上完课要写「这节课上到哪了」。⚠️ 跟排课时的 `note` **是两列，不要合并**——合并了，完成上课时的写入会把排课备注吃掉
- **考勤一改，课时跟着重算**：`POST /lessons/{id}/attendance` 只动**差额**（该扣没扣的补上、不该扣的删掉），不是「全删重建」——重建会把原有流水的 `created_at` 抹掉，审计痕迹就没了
- **课时 = 小时数**：`amount = -lesson.hours`，不存在两套换算
- **老师在课程上只能操作自己的课**：`lesson.teacher_id == self` 才放行，否则 403。排课限管理员。⚠️ 老师调 `GET /lessons?teacher_id=` **传啥都没用**，服务端强制改回自己的 id
- **`PATCH` / `DELETE` 只允许 `scheduled` 的课**（其余 409）：已完成的课改 `hours` 会让 `lessons.hours` 跟已写下的 `consume` 流水（-旧 hours）对不上。要改就取消重排
- **课程生命周期冲突统一 409**（完成/取消/删除/改考勤的状态不对）。⚠️ 跟班级/学生用 400 表示「已经是停用状态」**不一样**，别照抄
- **取消课程要退回课时**：删掉该课的 `consume` 流水，学生余额自然回升；但 `attendance` 行**刻意保留**（「本来安排了后来取消」的痕迹）
- **三种「课时」不能混**：教师课时费 / 班级已上课时 / 学生独立余额
- **计薪只算 `status='completed'` 的课**，课时费 = `hours × lessons.rate`（**快照**）。`GET /attendance/my`、`/summary`、`/export` 三处**共用 `services/payroll.month_rows()` 同一条查询**，汇总由明细行现加（不写 `GROUP BY`，免得引入第二种口径）——屏幕上看到多少，下载下来就是多少
- **工资表必须与桌面版逐单元格一致**：那张表是交给领导的，格式一个字都不能改。⚠️ 是**单元格**一致不是**字节**一致（openpyxl 每次 `save()` 都往 `docProps/core.xml` 写时间戳）。`tests/test_export.py` 直接加载 `codes/desktop/excel_exporter.py` 对拍，`dist/records.json` 那份真实数据也再对一遍
- **工资表要用 `sum(hours × rate)` 先乘后加最后才舍入**：Excel 里合计那格是 `=SUM(F4:Fn)`，而 F 是未舍入的 `=D*E`。逐节舍入再相加会差一分钱
- **导出月份 `month` 必填，不做「省略 = 当月」**：服务器时区若是 UTC，月初 00:00~08:00 会把当月算成上个月。前端一律用 `monthOf(todayISO())` 按本地时间算好再传
- **已停用的老师照样能查、能导**：离职老师的历史工资是**欠着人家的**。⚠️ 查人时**不能**用 `get_active_teacher_or_400`（那个要求 `is_active`），按 id 查、查不到 404
- **Excel sheet 名必须清洗**：≤31 字符、不许含 `: \ / ? * [ ]`、重名加 `(2)`。⚠️ **重名只加后缀，绝不合并** —— 合并会把两个人的工资算进同一张表，那是少发一个人的钱
- **响应体不包一层**：成功直接返回数据，失败是 `{"detail": "..."}` + 状态码。前端判断成败看状态码，不看包装层
- **角色修改本期没做**：纯范围控制，不是因为有风险——改角色时 `user.id` 不变，历史不受影响。⚠️ **要加就直接加，绝不要用「新建号 + 改 `lessons.teacher_id`」来绕**，那才是真改写历史
- **账号只停用不删除**：`is_active=False`，记录留着。它挂在课程的 `teacher_id`、审批的 `created_by` 上
- **班级和学生的 DELETE 语义不一样**：班级是**真删**（有课程记录时 400，停用走 `PATCH is_active=false`）；学生是**软删**。别看错
- **批量操作一律「全有或全无」**：入班、批量充值都是。有一个 id 无效就 400、**一行都不写**——部分成功会让用户不知道该不该重试，而重试会重复充值
- **手工流水只允许 `purchase` / `adjust`，`consume` 一律 400**。消耗只能由「完成上课」事务产生，否则 `uq_consume_once` 形同虚设（手工流水的 `lesson_id` 是 `None`，索引根本不拦）
- **课时余额允许为负 —— 但只对`adjust`**：手工纠错/退费不拦。「完成上课」**不在此列**（见上条，课时不够就整节课失败）
- **新生建档默认送 48 课时**：`config.default_student_hours`，**记一条真的 `purchase` 流水**（不是给字段塞个初值——余额是流水求和算的，塞初值会让流水列表不完整）。续费才需要手动充值
- **班级 `rate` 缺省按 `class_type` 查 `CLASS_RATES` 自动填**；类型不在表里又没给 rate 就 **400**，绝不静默落到 `DEFAULT_RATE`。PATCH 时**改类型不自动改价**
- **班级有在册人数上限**：`core/class_rules.py` 的 `CLASS_CAPACITY` 是唯一真相源，`/classes/rules` 把它带出去给前端做即时反馈。⚠️ **不是「1对N → N 人」的机械推导**——小班三档（1对3/1对4/1对5）**共用 5 人上限**，这是用户 2026-10-05 明确定的口径，别按 N 去推。认不出的类型**不限制**（历史自定义类型不该被拦死）
- **入班时数「还要占几个名额」不能只数没有行的**：退过班又回来的人 `left_on` 会被清掉、照样回到在册名单，他**也要占名额**。判据是 `row is None or row.left_on is not None`；已经在册的重复入班是幂等跳过，不占新名额
- **改班级类型只在类型真的变了时查容量**：本来就超员的历史班如果连改个错别字都被拦，用户就没法自救了，只能去动数据库
- **超员的历史数据允许存在**：规则上线前建的班（dev 库里的 `YDY001N5` 是 1对1 装了 2 人）不会自动退还。做法是**拦住新增 + 界面上标「超员」**，让人工去移出，不写数据迁移脚本
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
  stores/meta.js    # 班级前缀规则 + 费率表 + 分类卡（启动取一次缓存住）
  api/client.js     # fetch 封装 + buildQuery    ← 架构可移植
  api/auth.js       # 认证接口                   ← 完全可移植
  api/classes.js    # 班级接口
  api/students.js   # 学生 + 课时流水接口
  api/lessons.js    # 课程 + 完成/取消/考勤接口
  api/payroll.js    # 计薪统计 + 工资表导出
  api/admin.js      # 用户列表（排课选老师用）
  utils/storage.js  # localStorage 适配器        ← 平台适配器 1
  utils/download.js # Blob 落盘（<a download>）  ← 平台适配器 2
  utils/date.js     # 日期工具（★ 见下面那条「别用 toISOString」）
  components/AppHeader.vue      # 顶栏（返回 + 标题 + 可选右侧按钮）
  components/TabBar.vue         # 底部导航栏（一级入口，按角色过滤「合同」）
  components/PasswordField.vue  # 带「显示 / 隐藏」眼睛的密码框（登录 + 改密都用）
                                # ↑ 目前只有这三个组件
  styles/variables.css  # ★ 品牌变量，改配色只改这里
  styles/base.css       # reset + 通用类         ← web-only
  views/*.vue       # 页面（重写视图时才动）
```

### 必须遵守

- **主题色变量集中在 `src/styles/variables.css`**，主色 `#a9c5b3`。**不要引桌面版 Excel 那 12 个班级配色**——那套是「色差大、易区分」，和界面配色不是一个目的
- **所有请求走 `src/api/` 的封装**，不在页面里裸调
- **前端只写相对的 `/api`**：dev 靠 Vite 代理转发到本机 8000，生产靠 Nginx 反代。**不要写绝对地址**，否则手机访问时那个 `127.0.0.1` 会指向手机自己
- **`api/` 和 `stores/` 里不许出现 `document` / `window` / `localStorage`**，**尤其不许 `import router`**——那会形成循环依赖，还会把 web 独有的路由拖进本该可移植的网络层。client 只认 `setTokenGetter` / `setUnauthorizedHandler` 两个回调，在 `main.js` 里接线。**平台差异只允许出现在 `utils/` 的适配器里，现在有两个**：`utils/storage.js`（存储，换 uniapp 改这一个）和 `utils/download.js`（下载 —— web 是 `<a download>`，uniapp 是 `uni.downloadFile` + `uni.saveFile`）。⚠️ 别把「不许出现 document」理解成「utils 也不行」，那会让下载无处可放；规矩的本意是**网络层和状态层必须可移植**
- **业务逻辑放 store 的 actions 或 `api/`**，view 只做「取值 → 渲染 → 调用」。**只有跨页面共享的状态才建 store**（现在只有 `auth` / `meta`）——班级、学生、课程这些页面各拉各的数据，store 反而是个多余的中转层，直接 `api/` + 局部 `ref` 就行
- **移动优先**：触控目标 ≥44px、不做「悬停才有」的交互、不用 `<table>`、宽度流式
- 权限按角色控制按钮显隐，**同一套页面**（老师看，管理员多几个按钮）。`auth.isAdmin` 已包含超管
- **底部导航栏是全局的**：一级入口就是 `TabBar.vue` 那 5 个 tab（课程 / 班级 / 学生 / 合同 / 我的），`/` 直接落到「课程」。⚠️ **有 `<TabBar />` 的页面必须同时加 `page--tabbed` 类**，否则最后一行被压在底栏下面（`.page--tabbed` 只负责留白，底栏是 `fixed`、不占文档流）
- **一级页面（那 5 个 tab 的根页）`AppHeader` 必须传 `:back="false"`**：它们没有「上一页」，返回键要么把人送去莫名其妙的地方、要么原地不动，两种都像坏了。二级页（详情 / 表单）保持默认
- ⚠️ **表单页（新建 / 编辑）不放底栏**：填一半误触就全没了，那边用明确的「保存 / 取消」
- **「合同」tab 只给管理员看**：`TabBar` 按 `auth.isAdmin` 过滤，`router/index.js` 的守卫再兜一道（手输 URL / 旧书签也得挡），**不能只靠按钮隐藏**
- **组件只抽真正重复的东西**：现在只有 `AppHeader.vue` / `TabBar.vue` / `PasswordField.vue` 三个，理由都一样——**重复次数够多，且内部有点真逻辑**（返回/标题的组合、tab 高亮与角色过滤、密码显隐的状态）。**列表行、表单字段、三态分段控件、分类卡都用 CSS 类不抽组件**——组件越抽象，移植 uniapp 时越要整个重写（`div`→`view` 的映射藏在组件里），CSS 抄过去便宜得多。原生 `window.confirm()` 就够，不引弹窗组件库
- **密码框一律用 `components/PasswordField.vue`**，不要手写 `<input type="password">`。眼睛图标是**标配**（用户 2026-10-05 定的），默认闭眼。里面的 toggle 按钮**必须写 `type="button"`**——漏了它就会触发表单提交
- **班级规则、容量、分类卡都不要在页面里硬编码**，走 `stores/meta.js` 取 `GET /classes/rules`（`classTypeRule()` 判前缀、`capacityFor()` 查上限、`classTabs` 出列表顶部的卡）。那份只做**即时反馈**（输入 YDY001 自动锁 1对1、班级满了就把「加学生」置灰），**真相源在后端** `core/class_rules.py`，两边不一致也写不进脏数据
- **班级列表的分类卡上必须是「人话」**（`总览 / 1对1 / 1对2 / 小班`），**不是 `YDY / YDE / XB` 这种内部编码**——老师看不懂编码（用户 2026-10-07 报的 bug 004）。卡由后端 `CLASS_TABS` 出，`key`（ASCII，只进 URL query）和 `label`（中文，给人看）**故意分开**，别为了省事把 `label` 改成 `key`
- **分类卡筛的是 `class_type`，不是班级名前缀**：历史遗留的自定义班名（「沐晨提高班」这种）没有 `YDY/XB` 前缀，按前缀筛会让它们只在「总览」里出得来、切到「1对1」就凭空消失。「总览」那张卡是前端自己加的第一张（`types: null` = 不筛）
- **扣课时的口径前端也不写死**：`LessonRead` 把 `class_type` 透出来，详情页据此标「按当前勾选：不扣课时」、拼确认框话术。**真相源同样在后端**，前端只负责让老师点之前就看见
- **图标资源在 `assets/design/icon570/`**（`1.用户界面/` 下的 svg）。许可证见 `许可证.txt`：**允许商用、无需署名**，禁止的是转售图标包本身。用法是**把 path 的 `d` 内联进组件**（不引图标库、不加构建依赖），并把 `fill` 改成 `currentColor` 好跟着文字色走

### 容易写错的地方

- **登录失败的 401 和 token 过期的 401 是同一个状态码**。client 里判定「会话失效」必须是 **`status === 401 && 本次请求带了 token`**，否则用户输错一次密码就会被踢出登录态
- **改密接口只回 `{message}`，不回 user**。前端得自己把本地的 `must_change_password` 置回 false
- **取「今天」不能写 `new Date().toISOString().slice(0, 10)`**——那是 **UTC** 日期，中国 UTC+8 在本地 00:00~08:00 会取出**昨天**，入班/移出日期整整差一天。用 `utils/date.js` 的 `todayISO()`。**加减天数同理**，用 `shiftDays(iso, n)`（本地构造 + `setDate`），别对 `Date` 对象做 `toISOString()`。⚠️ **月份是同一个坑的月份版**：取当月用 `monthOf(todayISO())`、翻月用 `shiftMonths(month, ±1)`，写成 `toISOString().slice(0, 7)` 就会在每月头几个小时查到上个月
- **两种时间字段别混着处理**：`created_at` 是带 `Z` 的 UTC 串，`new Date()` 能正确转到本地时区（用 `formatDateTime()`）；`joined_on` 这类**业务日期**是裸 `YYYY-MM-DD`，**原样显示就好**（用 `formatDate()`）——拿去 `new Date()` 会被当成 UTC 午夜，在本项目用的 UTC+8 是碰巧没事，换个时区就是前一天
- **`start_time` 是第三个时间种类**：`HH:MM:SS` 的**纯时间**，没有日期也没有时区，**永远别 `new Date()`**，用 `formatTime()` 截成 `HH:MM` 显示。反过来，`<input type="time">` 给的是 `HH:MM`，**提交前要补 `:00`**
- **视图的状态放 URL 不放组件**：课程日视图选中的日期是 `route.query.date`（`/lessons?date=2026-10-05`），不是 `ref`。这样「进详情→返回」不丢日期、刷新还在当天、链接能直接发人。**用 `watch(date, load)` 而不是在每个入口手动调** —— 浏览器前进/后退也会改 query。班级列表选的分类卡同理（`/classes?prefix=YDY`）
- ★ **渲染函数里抛异常，Vue 会丢掉整次更新、DOM 冻在上一帧 —— 页面上什么都不显示，接口却是 200**
  用户 2026-10-05 报的「新建学生保存后一直显示加载中」就是它：详情页读 `detail.transactions`，而那个字段当时只挂在 `/students/{id}/hours` 上、没进详情。`undefined.length` 抛 TypeError → 页面冻在「加载中…」→ **后端日志干干净净**（接口确实返回了 200），只有浏览器控制台看得见。
  **两个后果**：① 页面里读的每个字段，都要对得上后端 schema（`response_model` 定了什么就有什么，改后端时先看谁在消费）；② **「一直加载中」不等于网络慢/卡住**，先看控制台，别急着查网络。可选加一个全局 `app.config.errorHandler` 把这类错误亮出来（尚未加，见开发日志）

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
- [x] **Phase 2 验收完成**：lessons + attendance（2026-10-05，224 个测试全绿）
  > 排课 / 完成上课（= 提交考勤 + 扣课时）/ 取消退课时 / 事后改考勤，
  > 配套 Web 课程日视图 + 详情考勤页 + 排课表单。**月视图日历未做**。
- [x] **一轮体验修正**（2026-10-05，254 个测试全绿）
  > 底部导航栏（`TabBar`）+ 5 个一级入口；密码框眼睛图标；修学生详情页卡「加载中」；
  > 班级分类卡与人数上限；
  > **扣课时口径改成按班型**（1对1 只扣出勤，其他班型扣全员）、课时不足整节课失败、
  > 新生默认送 48 课时、上课内容必填、合同管理占位入口。**生产库要跑一次
  > `scripts/migrate_add_lesson_content.py`**（`lessons` 表加了 `content` 列）。
- [x] **二轮体验修正**（2026-10-07，260 个测试全绿）
  > **扣课时口径再改一版**：1对2 也归进「只有出勤才扣」（原本只有 1对1），
  > 规则本体是 `core/class_rules.PER_STUDENT_HOURS_TYPES`；
  > **班级分类卡改成人话**（`总览 / 1对1 / 1对2 / 小班`，不再是 YDY / YDE / XB），
  > 且改成按 `class_type` 筛而不是按班级名前缀（修 bug 004）。
  > **无表结构变更，生产库不用跑脚本**。
- [x] **Phase 4：计薪统计 + 导出 Excel**（2026-10-08，296 个测试全绿）← **里程碑「能替代桌面版」达成**
  > `GET /attendance/my`（我的课时数 + 逐节明细）/ `/summary`（管理员）/ `/export`（.xlsx），
  > 三者共用 `services/payroll.month_rows()` 同一条查询。导出**逐单元格与桌面版一致**，
  > `tests/test_export.py` 直接加载桌面版导出器对拍。入口挂在「我的」页（不新增 tab）：
  > 月份选择 + 本月计薪 + 逐节明细 + 下载工资表，管理员多一张「全部老师」卡。
  > **无表结构变更，生产库不用跑脚本。**
- [ ] **下一步**：Phase 5 审批流（含 `POST /lessons/{id}/reschedule` 改期申请）
- [ ] 月视图日历课表 —— **不在 Phase 4 范围**，用户 2026-10-08 明确另开一轮
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
