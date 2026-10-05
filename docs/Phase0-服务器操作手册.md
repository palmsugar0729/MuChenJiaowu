# Phase 0 服务器操作手册

> 日期：2026-09-26（依「改用独立新服务器」决策重写）
> 面向：**你自己动手执行**（Claude 只出命令，不碰线上环境）
> 上游：`docs/实施计划.md` 第七节

---

## 这是台全新服务器

**独立、干净、什么都没有。** 上面不跑别的站，所以不用像以前那样小心翼翼避开什么。

下面的命令**从上到下照着跑**即可，每一步都有验证方法。全程大约 1~2 小时。

**准备**：把 `<服务器IP>`、`<你的域名>` 这类占位符替换成实际值再执行。

---

## 📍 进度看板

> ## ✅ Phase 0 已完成（2026-10-04）
>
> 服务器上线，`https://jiaowu.palmsugar.cn` 可访问，重启自愈、备份恢复均已实测。

| 步骤 | 状态 | 日期 |
|---|---|---|
| 0 登录 + 确认机器 | ✅ | 09-26 |
| 1 域名解析 | ✅ | 09-26 |
| 2 基础环境 + 防火墙 | ✅ | 09-27 |
| 3 部署代码 + 建库 + 建超管 | ✅ | 09-27 |
| 4 裸跑验证（`/api/health` 返回 ok） | ✅ | 09-27 |
| 5 systemd 常驻 | ✅ | 10-04 |
| 6 Nginx | ✅ | 10-04 |
| 7 HTTPS（certbot 自动续期） | ✅ | 10-04 |
| 8 自动备份（含恢复演练） | ✅ | 10-04 |
| 9 验收清单（全部通过） | ✅ | 10-04 |
| 🔧 重建库（枚举 CHECK 约束） | ⬜ **待执行** | 见「维护：改了表结构要重建数据库」 |

**这台机器**：

| 项 | 值 |
|---|---|
| 登录 | `ssh muchen`（密钥已配好，免密） |
| IP | `122.51.16.85` |
| 域名 | `jiaowu.palmsugar.cn` → 已解析到上面的 IP ✅ |
| 系统 | Ubuntu 24.04 LTS / Python 3.12.3 |
| 配置 | 2 核 2G |

---

## 日常健康检查（随时可跑，全是只读命令）

出问题时先跑这一套，能快速定位是哪一层坏了：

```bash
ssh muchen
cd /srv/muchen/app/codes/server

# ① 服务活着吗
sudo systemctl status muchen --no-pager | head -5

# ② 后端响应吗（本机）
curl http://127.0.0.1:8000/api/health

# ③ 公网通吗（这一步过了说明 DNS / 防火墙 / nginx / 证书 全对）
curl https://jiaowu.palmsugar.cn/api/health

# ④ 数据库表齐全吗（应列出 8 张表）
sqlite3 data/app.db ".tables"

# ⑤ 密钥换过了吗（不应显示 dev-only-please-change-me）
grep '^JWT_SECRET=' .env

# ⑥ 备份在吗
ls -lh /srv/muchen/backups/
```

> `--no-pager` 让 `systemctl` 直接输出结果，不用按 `q` 退出。

---

## 第 0 步：登录，确认机器

```bash
ssh ubuntu@<服务器IP>
```

> 第一次登录腾讯云会给 `ubuntu` 用户加 `sudo` 权限。如果给你的用户名不是 `ubuntu`（有些镜像用 `root` 或自定义名），下面命令里的 `ubuntu` 都替换成实际的。

确认买对了：

```bash
echo "===== 系统版本（推荐 24.04，26.04 亦可）====="
lsb_release -a

echo ""
echo "===== 配置（要 2 核 2G）====="
nproc
free -h

echo ""
echo "===== 磁盘（要 40G 左右）====="
df -h /

echo ""
echo "===== Python 版本（要 3.11+）====="
python3 --version
```

**对不上的话先别往下走**，告诉我实际数字。

> **选 Ubuntu 24.04 LTS**：自带 Python 3.12，成熟稳定，支持到 2029。本项目已在 3.12/3.13 上测过。
>
> 26.04 LTS 是较新的默认镜像（自带 Python 3.14，支持到 2031），**也能用**——本项目不吃解释器性能，
> 唯一风险是 C 扩展依赖（`uvicorn[standard]` 里的 uvloop / httptools）在 3.14 上可能还没有预编译轮子，
> 见第 3 步的说明。只有 26.04 可选时直接用它，不必纠结。
>
> 22.04 自带 3.10，**低于本项目要求的 3.11**，要额外装 deadsnakes PPA——不推荐。

---

## 第 1 步：域名解析

去**腾讯云 DNSPod** 控制台，给 `jiaowu.palmsugar.cn` 加一条记录：

| 类型 | 主机记录 | 记录值 | TTL |
|---|---|---|---|
| A | `jiaowu` | `<服务器IP>` | 600 |

**验证**（在你自己电脑上跑，可能要等几分钟）：

```bash
nslookup jiaowu.palmsugar.cn
```

看到新服务器的 IP 就对了。

> **备案这一步不用做**：ICP 备案是**按主域名**的，`palmsugar.cn` 已备案 → 子域名无需单独备案，也**无需为新服务器办接入**（同一服务商）。
> ⚠️ 但这条**建议顺手问一句腾讯云备案客服**确认，免费、几分钟的事。

---

## 第 2 步：基础环境

```bash
# 系统更新（新机器，先更一遍）
sudo apt update && sudo apt upgrade -y

# 装必要工具
sudo apt install -y python3-venv python3-pip git nginx sqlite3 curl

# 时区（影响所有日志和时间戳）
sudo timedatectl set-timezone Asia/Shanghai
timedatectl                    # 要看到 CST

# 建目录结构：应用 / 数据 / 日志 / 备份 分开
sudo mkdir -p /srv/muchen/{app,data,logs,backups}
sudo chown -R $USER:$USER /srv/muchen
```

**防火墙**：本地不用开 ufw，**依赖腾讯云控制台的「安全组」**。

⚠️ 去控制台确认防火墙**只放行了这三个端口**：

| 端口 | 用途 |
|---|---|
| 22 | SSH |
| 80 | HTTP（跳转到 HTTPS） |
| 443 | HTTPS |

**8000 绝对不要开**——后端只监听 `127.0.0.1`，由 nginx 转发。开到公网等于绕过 HTTPS。

> ⚠️ **默认规则里那条 `ALL` 要看协议列，不能只看端口**：
>
> | 协议 | 端口 | 含义 | 处理 |
> |---|---|---|---|
> | **ICMP** | ALL | ping 用的（ICMP 无端口概念，故显示 ALL） | ✅ 留着，无风险 |
> | **TCP / UDP** | ALL | **所有端口全开** | ❌ 删掉 |
>
> 腾讯云轻量的默认模板两者都可能出现，**认协议列**。

---

## 第 3 步：部署代码

```bash
git clone https://github.com/palmsugar0729/MuChenJiaowu.git /srv/muchen/app

# 验证落盘位置：应该直接看到 codes/，而不是又套一层 MuChenJiaowu/
ls /srv/muchen/app
```

> ⚠️ **目标路径一定要写全**。`git clone <url>` 后面不跟路径时，git 会**按仓库名自动建一层文件夹**，
> 代码会落在 `/srv/muchen/app/MuChenJiaowu/`——后面所有 `cd /srv/muchen/app/codes/server` 就全废了。

> ⚠️ **仓库若是私有的**，直接 clone 会要求输账号密码，而 GitHub 早已不接受密码——
> 需要在服务器上生成 SSH key，加到 GitHub 仓库的 **Deploy keys**（只读即可）：
>
> ```bash
> ssh-keygen -t ed25519 -C "muchen-server" -f ~/.ssh/id_ed25519 -N ""
> cat ~/.ssh/id_ed25519.pub        # 复制输出，贴到仓库 Settings → Deploy keys
> ```
>
> 然后把 clone 地址换成 SSH 形式：
>
> ```bash
> git clone git@github.com:palmsugar0729/MuChenJiaowu.git /srv/muchen/app
> ```

建虚拟环境：

```bash
cd /srv/muchen/app/codes/server
python3 -m venv .venv
. .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

> **若卡在编译**（Ubuntu 26.04 / Python 3.14 上可能出现）：日志里会看到 `Building wheel for uvloop` 之类
> 长时间不动。原因是 `uvicorn[standard]` 里的 uvloop / httptools 是 C 扩展，新 Python 的预编译轮子可能还没出。
> **本项目用不上 uvloop**（它解决的是高并发，我们没这需求），去掉即可，功能无差别：
>
> ```bash
> pip install fastapi uvicorn pydantic-settings sqlmodel PyJWT bcrypt \
>             python-multipart openpyxl pytest httpx
> ```

> `python3 --version` 若低于 3.11，先装新版：
> ```bash
> sudo apt install -y software-properties-common
> sudo add-apt-repository -y ppa:deadsnakes/ppa
> sudo apt install -y python3.12 python3.12-venv
> # 然后用 python3.12 -m venv .venv
> ```

**配 `.env`**：

```bash
cd /srv/muchen/app/codes/server
cp .env.example .env

# 自动生成密钥并写进去，不用手工复制粘贴
sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')|" .env

# 验证：应打印一串 64 位随机字符，而不是 dev-only-please-change-me
grep '^JWT_SECRET=' .env
```

🔴 **务必确认 `JWT_SECRET` 不再是默认值**，否则任何人都能伪造登录令牌。

> **想手工编辑也行**：`nano .env`，把第 4 行 `JWT_SECRET=` 后的值换掉。
>
> | 操作 | 按键 |
> |---|---|
> | 删除光标到行尾 | `Ctrl+K`（光标先移到 `JWT_SECRET=` 后面） |
> | **粘贴** | **`Ctrl+Shift+V` 或鼠标右键** |
> | 保存 | `Ctrl+O` → 回车 |
> | 退出 | `Ctrl+X` |
>
> ⚠️ **终端里 `Ctrl+V` 不是粘贴**，这是最常见的坑。

**建库 + 建超管**：

```bash
python scripts/init_db.py
python scripts/init_superadmin.py --phone <你的手机号> --name "<你的真实姓名>"
```

> `--phone` 是**登录账号**（系统用手机号登录，没有「用户名」）。
> `--name` 是 **display_name（真实姓名）**，会出现在审批记录、操作日志、导出表格里，**填真名别填网名**。
>
> **不要传 `--password`**，让脚本自动生成强密码即可。

🔴 **脚本打印的密码只显示这一次**，立刻抄进密码管理器。首次登录会强制改密。

---

## 第 4 步：先裸跑一下

```bash
cd /srv/muchen/app/codes/server
. .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**另开一个终端**（Windows：`Ctrl+Shift+T` 开新标签页，或搜 `cmd`），**重新 ssh 登录一次**：

```bash
ssh ubuntu@<服务器IP>
curl http://127.0.0.1:8000/api/health
```

> ⚠️ **必须在服务器上跑**——Windows 本地的 `127.0.0.1` 指向你自己的电脑，没有 8000 端口。

看到 `{"status":"ok",...}` 就对了。`Ctrl+C` 停掉，进下一步。

> 起不来最常见的原因：`JWT_SECRET` 没配、依赖没装全、8000 端口被占。

---

## 第 5 步：systemd 常驻

整段复制粘贴即可（**不用编辑器**）：

```bash
sudo tee /etc/systemd/system/muchen.service > /dev/null <<'EOF'
[Unit]
Description=Muchen Course Management API
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/srv/muchen/app/codes/server
ExecStart=/srv/muchen/app/codes/server/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8000
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF
```

> `<<'EOF' ... EOF` 表示「把中间的内容原样写进文件」，`sudo tee` 负责写入需要 root 权限的位置。
> ⚠️ 首尾两个 `EOF` **都要顶格**，前面不能有空格。
> `User=` 若无特殊需要保持 `ubuntu` 即可（`whoami` 可查）。

<details>
<summary>想用 nano 也行</summary>

```bash
sudo nano /etc/systemd/system/muchen.service
```

把上面的 `[Unit]` 到 `WantedBy=multi-user.target` 粘进去，`Ctrl+O` 回车保存，`Ctrl+X` 退出。

</details>

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now muchen
sudo systemctl status muchen        # 要看到 active (running)
curl http://127.0.0.1:8000/api/health
```

看日志：`sudo journalctl -u muchen -f`

---

## 第 6 步：Nginx

```bash
sudo nano /etc/nginx/sites-available/muchen
```

**先用 HTTP 跑通，暂不加 ssl**：

```nginx
server {
    listen 80;
    server_name jiaowu.palmsugar.cn;

    # 2~5Mbps 带宽下 gzip 很关键，H5 的 JS 能压到 1/3
    gzip on;
    gzip_types text/plain text/css application/json application/javascript
               text/xml application/xml image/svg+xml;
    gzip_min_length 1024;

    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # FastAPI 自带的接口文档，验收时点着测很方便
    location /docs {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }

    location /openapi.json {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
    }
}
```

启用并**先测试再重载**：

```bash
sudo ln -s /etc/nginx/sites-available/muchen /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default      # 去掉自带的默认站

sudo nginx -t          # ← 必须看到 syntax is ok + test is successful
```

**⚠️ 报任何 error 就停下，不要 reload**，把报错发我。

```bash
sudo systemctl reload nginx      # 是 reload，不是 restart
```

验证：

```bash
curl -I http://jiaowu.palmsugar.cn/api/health
```

---

## 第 7 步：HTTPS

```bash
sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d jiaowu.palmsugar.cn
```

certbot 会自动改好 nginx 配置并**配好自动续期**。

期间会问：

- 邮箱 → 填你的
- 同意条款 → `A`
- **是否把 HTTP 重定向到 HTTPS** → 选 **2（Redirect）**

验证：

```bash
curl -I https://jiaowu.palmsugar.cn/api/health
sudo certbot renew --dry-run        # 确认自动续期能跑通
```

> 🔴 **HTTPS 不是可选项**——微信小程序硬性要求，且没有它手机浏览器会警告「不安全」。

---

## 第 8 步：自动备份

**这是唯一一份存着钱的数据库，备份不做等于裸奔。**

整段复制粘贴即可（`/srv/muchen` 属于当前用户，不用 `sudo`）：

```bash
cat > /srv/muchen/backup.sh <<'EOF'
#!/bin/bash
# SQLite 官方安全备份方式
DB=/srv/muchen/app/codes/server/data/app.db
DEST=/srv/muchen/backups
sqlite3 "$DB" ".backup $DEST/app-$(date +%F).db"
find "$DEST" -name "app-*.db" -mtime +30 -delete    # 保留 30 天
EOF
```

> ⚠️ `<<'EOF'` 外面的**引号不能省**——它让 `$(date +%F)` 原样写进文件，执行时才求值。
> 不加引号的话写入瞬间就被替换成当天日期，备份文件名永远不变，第二天就覆盖不进去了。

```bash
chmod +x /srv/muchen/backup.sh
/srv/muchen/backup.sh             # 手动跑一次
ls -la /srv/muchen/backups/       # 确认文件生成
sqlite3 /srv/muchen/backups/app-$(date +%F).db ".tables"   # 确认内容完整
```

加进 crontab，每天凌晨 3 点：

**不用编辑器**（推荐，直接追加一行）：

```bash
(crontab -l 2>/dev/null; echo "0 3 * * * /srv/muchen/backup.sh") | crontab -
crontab -l        # 验证：应显示出这一行
```

<details>
<summary>想用 crontab -e 也行</summary>

```bash
crontab -e
```

首次运行会让你选编辑器，**按 `1` 回车**（nano）。

然后在空文件里输入这一行（⚠️ 下面这行**原样输入**，不要把注释也敲进去）：

```
0 3 * * * /srv/muchen/backup.sh
```

`Ctrl+O` → 回车 → `Ctrl+X` 保存退出。

</details>

> ⚠️ **绝对不要用 `cp` 拷 SQLite 文件**——WAL 模式下会拷到不一致的状态。
> 必须用 `.backup`（SQLite 官方在线备份，自动处理 WAL）。

**恢复流程 + 演练**（**趁数据库还空的时候做，成本最低**）：

```bash
cd /srv/muchen/app/codes/server

# 1. 记下当前状态
sqlite3 data/app.db "select id, phone, display_name from users;"

# 2. 故意搞破坏，验证恢复真的有用
sqlite3 data/app.db "delete from users;"
sqlite3 data/app.db "select count(*) from users;"      # 应该是 0

# 3. 恢复（自动取最新的备份）
sudo systemctl stop muchen
cp "$(ls -t /srv/muchen/backups/app-*.db | head -1)" /srv/muchen/app/codes/server/data/app.db
rm -f /srv/muchen/app/codes/server/data/app.db-wal \
      /srv/muchen/app/codes/server/data/app.db-shm
sudo systemctl start muchen

# 4. 验证：数据应该回来了
sqlite3 data/app.db "select id, phone, display_name from users;"
curl http://127.0.0.1:8000/api/health
```

🔴 **`rm -f ...-wal` / `-shm` 绝对不能省。** 不删的话 SQLite 会拿旧 WAL 日志覆盖刚恢复的数据库，直接搞坏——
这是恢复流程里最容易漏、后果最严重的一步。

> ⚠️ **上线前务必真跑一次**——没验证过的备份不叫备份。

---

## 🔧 维护：改了表结构要重建数据库

**什么时候要做**：代码更新里包含**表结构变更**（加字段、加约束、加索引）的时候。

> ⚠️ **光是拉代码不会改表结构。** `scripts/init_db.py` 只做 `create_all` ——
> **已存在的表它一律不碰**，新加的字段/约束/索引全都不会生效。
> 而 SQLite 又**不支持** `ALTER TABLE ADD CONSTRAINT` / `ADD COLUMN`（带约束的那种），
> 所以唯一的办法是**删库重建**。

**判断这次要不要重建**：看 `docs/开发日志.md` 最新那条有没有提「重建库」。
没有就不用做这一步，正常更新代码重启即可。

> 🔴 **重建 = 数据全没。** 重建前**必须**先备份，而且用 `backup.sh`
> （`sqlite3 .backup`，WAL 模式下唯一安全的方式）——**不要用 `cp`**，
> 见上一节的红字。当前生产库只有账号数据，重建后照着重建账号即可；
> **一旦装了真实课程和学生数据，这一步就必须改成写数据迁移脚本**，
> 不能再删库了。

```bash
# 0. 先备份！给这次操作留一份带时点的副本
/srv/muchen/backup.sh
ls -lh /srv/muchen/backups/
cp /srv/muchen/backups/app-$(date +%F).db \
   /srv/muchen/backups/before-rebuild-$(date +%F-%H%M).db

# 1a. ★ 抄下现有账号清单 —— 重建会把它们全清掉
#     超管能用 init_superadmin.py 重建，老师号只能走接口重建，
#     不先记下来就会静默少一个号（对方突然登不上了）
sqlite3 -header -column /srv/muchen/app/codes/server/data/app.db \
  "select id, phone, display_name, role, is_active from users;"

# 1b. 确认库里真的只有账号数据（不确认就别往下走）
sqlite3 /srv/muchen/app/codes/server/data/app.db \
  "select 'users', count(*) from users
   union all select 'students', count(*) from students
   union all select 'classes', count(*) from classes
   union all select 'lessons', count(*) from lessons;"

# 2. 拉代码
cd /srv/muchen/app
git pull

# 3. 停服务
sudo systemctl stop muchen

# 4. 删库（WAL 模式有三个文件，必须一起删）
cd /srv/muchen/app/codes/server
rm -f data/app.db data/app.db-wal data/app.db-shm

# 5. 重建 + 建超管
. .venv/bin/activate
python scripts/init_db.py
python scripts/init_superadmin.py --phone <你的手机号> --name <你的姓名>

# 6. ★★ 立刻抄下上一步打印的密码 —— 只显示这一次，首登会强制改密 ★★

# 7. 验证新结构真的生效了（这是重建的**唯一目的**，一定要看）
sqlite3 data/app.db ".schema users"              # 应出现 ck_users_role
sqlite3 data/app.db ".schema hour_transactions"  # 应出现 ck_hour_transactions_type

# 8. 起服务
sudo systemctl start muchen
sudo systemctl status muchen --no-pager | head -5
curl http://127.0.0.1:8000/api/health
```

第 9 步（**别漏**）：照着第 1a 步抄下来的清单，把老师号补回来 ——
超管登录后调 `POST /api/admin/users`，返回的 `initial_password`
**只出现这一次**，要当场发给对方（他首次登录会被强制改密）。
账号清单里 `is_active=0` 的那些不用补，重建后就没这个号了。

> 💡 **清单里只有超管一个人时，第 9 步是空的** —— 超管本来就由第 5 步的
> `init_superadmin.py` 重建，没有别的号要补。第 1a 步照样跑一下当作核对：
> 记下那行超管的**手机号和姓名**，第 5 步原样填进去即可。
> （老师号是后面超管自己加、再发给老师用的，所以早期几次重建都不会有第 9 步。）

第 7 步**别跳过**：没验证的话，重建就是白删了数据。
（下面的附表列了每次该看到什么。）

### 各次重建该验证什么

| 时间 | 改了什么 | 验证命令 | 应看到 |
|---|---|---|---|
| 2026-10-05 | 五个枚举列补 CHECK 约束 | `.schema hour_transactions` | `type IN ('purchase', 'consume', 'adjust')` |

> ⚠️ **`uq_consume_once` 每次重建都要顺手确认**——它是防重复扣课时的唯一防线，
> 改 `__table_args__` 时最容易漏掉，漏了不会有任何报错：
>
> ```bash
> sqlite3 /srv/muchen/app/codes/server/data/app.db \
>   "select sql from sqlite_master where name='uq_consume_once';"
> ```
>
> 应看到 `... WHERE type = 'consume'`。**一个字都不能差**——写成 `'Consume'`
> 索引就静默失效，同一节课会扣两次课时。

---

## 第 9 步：验收清单

**全过才算 Phase 0 完成**：

- [ ] `curl https://jiaowu.palmsugar.cn/api/health` 返回 200
- [ ] 浏览器打开 `https://jiaowu.palmsugar.cn/docs`，**证书不报警**，接口能点
- [ ] `sudo systemctl status muchen` 是 `active (running)`
- [ ] `sudo reboot` 后等 1 分钟，服务**自动起来了**
- [ ] 备份脚本生成的 `.db` **能打开且表齐全**
- [ ] **真实演练一次恢复流程**（第 8 步的恢复命令）
- [ ] `sudo certbot renew --dry-run` 通过
- [ ] 安全组**只有 22/80/443**，8000 未暴露
- [ ] 从手机浏览器打开一次，确认能用

---

## 出问题怎么办

| 症状 | 处理 |
|---|---|
| 域名打不开 | `sudo nginx -t` 查配置；`curl http://127.0.0.1:8000/api/health` 看后端活没活 |
| 502 Bad Gateway | 后端没起来。`sudo systemctl status muchen` + `journalctl -u muchen -n 50` |
| 证书报错 | `sudo certbot certificates` 看状态，必要时重跑 `sudo certbot --nginx -d jiaowu.palmsugar.cn` |
| 磁盘满了 | `df -h /`；看 `/srv/muchen/backups` 堆积；`sudo journalctl --vacuum-size=200M` |
| 忘了超管密码 | 重新跑 `python scripts/init_superadmin.py --phone ... --name ... --force`，或用 `reset-password` 接口 |

**整个 Phase 0 的回滚**（机器是新的，最坏就是重装）：

```bash
sudo systemctl disable --now muchen
sudo rm /etc/nginx/sites-available/muchen /etc/nginx/sites-enabled/muchen
sudo nginx -t && sudo systemctl reload nginx
```

---

## 附：域名与备案策略（**先读，别踩坑**）

系统将来要被公司买断，域名最终要交给公司。**但千万不要「先用个人名义备案，以后再转」。**

| 坑 | 说明 |
|---|---|
| **个人备案转不了企业** | 绝大多数省份不支持直接变更，只能**注销重备**。期间**网站必须停摆**（域名无法访问境内服务器），审核还要 1~20 工作日 |
| **小程序会被一起锁死** | 小程序备案主体必须与注册主体一致，且**主体变更同样要注销重备** |
| **「域名归我、备案用公司」走不通** | 企业备案要求域名实名信息就是企业 |

**正确做法**：

| 阶段 | 域名 | 备案 |
|---|---|---|
| **现在（开发期）** | `jiaowu.palmsugar.cn` | 沿用现有，零成本 |
| **交付期** | 公司注册新域名 | **企业主体备案**（1~20 工作日） |

**✅ 切换成本几乎为零**：服务器全程不换，交付时只改一条 DNS 解析，**不涉及数据迁移、不停服**。

**⚠️ 一个待确认点**：企业备案通常要求**备案主体与服务器账号实名主体一致**。服务器在用户名下、备案主体是公司，需确认能否用**授权委托书**通过。**谈买断之前问一次腾讯云备案客服。**

---

## 附：交付时账号怎么移交

**结论：给公司新建一个超管，不要改你现有账号。**

操作记录（如 `hour_transactions.created_by`）存的是 **`user.id`**。若把你这行的 `phone` / `display_name`
改成公司的，**历史上所有你做的操作都会显示成「公司的人做的」**——等于篡改操作记录，
与「费率快照绝不篡改历史工资」是同一条原则。

而且实际也改不了：`phone` 是登录标识，你不可能把自己的手机号留给公司登录。

| 步骤 | 操作 |
|---|---|
| 1 | 给公司**新建**超管账号（他们的手机号 + 真名） |
| 2 | 你的账号降为普通管理员，或 `is_active = False` 停用 |
| 3 | 两边历史记录都保持真实，「谁做的」一目了然 |

`is_active` 字段就是为此设计的——**停用而非删除**，人走了记录还在。

**移交不用「过户」**：账号、班级、课时记录全在 `data/app.db` 里，**跟着服务器一起走**，没有单独的手续要办。

---

## 做完之后

把第 9 步的验收结果告诉我，我们进 **Phase 1**（后端登录 + 三种角色 + 账号管理）。

Phase 1 是纯本地开发，不会再碰服务器。
