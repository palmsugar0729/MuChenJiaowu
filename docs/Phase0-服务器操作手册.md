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
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"   # 生成密钥并复制
nano .env                                                      # 粘进 JWT_SECRET
```

🔴 **务必改掉默认的 `JWT_SECRET`**，否则任何人都能伪造登录令牌。

**建库 + 建超管**：

```bash
python scripts/init_db.py
python scripts/init_superadmin.py --phone <你的手机号> --name <你的名字>
```

🔴 **脚本打印的密码只显示这一次**，立刻抄进密码管理器。首次登录会强制改密。

---

## 第 4 步：先裸跑一下

```bash
cd /srv/muchen/app/codes/server
. .venv/bin/activate
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

**另开一个终端**：

```bash
curl http://127.0.0.1:8000/api/health
```

看到 `{"status":"ok",...}` 就对了。`Ctrl+C` 停掉，进下一步。

> 起不来最常见的原因：`JWT_SECRET` 没配、依赖没装全、8000 端口被占。

---

## 第 5 步：systemd 常驻

```bash
sudo nano /etc/systemd/system/muchen.service
```

贴进去（**`User=` 改成你的实际用户名**，`whoami` 可查）：

```ini
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
```

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

```bash
nano /srv/muchen/backup.sh
```

```bash
#!/bin/bash
# SQLite 官方安全备份方式
DB=/srv/muchen/app/codes/server/data/app.db
DEST=/srv/muchen/backups
sqlite3 "$DB" ".backup $DEST/app-$(date +%F).db"
find "$DEST" -name "app-*.db" -mtime +30 -delete    # 保留 30 天
```

```bash
chmod +x /srv/muchen/backup.sh
/srv/muchen/backup.sh             # 手动跑一次
ls -la /srv/muchen/backups/       # 确认文件生成
sqlite3 /srv/muchen/backups/app-$(date +%F).db ".tables"   # 确认内容完整
```

加进 crontab，每天凌晨 3 点：

```bash
crontab -e
# 加这一行：
0 3 * * * /srv/muchen/backup.sh
```

> ⚠️ **绝对不要用 `cp` 拷 SQLite 文件**——WAL 模式下会拷到不一致的状态。
> 必须用 `.backup`（SQLite 官方在线备份，自动处理 WAL）。

**恢复方法**（存好，出事要用）：

```bash
sudo systemctl stop muchen
cp /srv/muchen/backups/app-<日期>.db /srv/muchen/app/codes/server/data/app.db
rm -f /srv/muchen/app/codes/server/data/app.db-wal \
      /srv/muchen/app/codes/server/data/app.db-shm
sudo systemctl start muchen
```

> ⚠️ **上线前务必真跑一次恢复流程**——没验证过的备份不叫备份。

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

## 做完之后

把第 9 步的验收结果告诉我，我们进 **Phase 1**（后端登录 + 三种角色 + 账号管理）。

Phase 1 是纯本地开发，不会再碰服务器。
