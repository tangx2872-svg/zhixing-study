# 生产部署说明（SERVER_DEPLOYMENT）

版本日期：2026-10-19
适用范围：苏州工学院教学平台（django-lms）当前线上实例

> 本文件只记录运维事实与命令，**不包含任何口令、SECRET_KEY、token 或私钥**。
> 生产敏感值统一存放在 `django_lms/.env`（已被 `.gitignore` 忽略），不在本仓库内。

## 1. 生产主目录

```
/home/ubuntu/django-lms-upgrade/django-lms
```

这是**唯一**的生产主项目目录，所有代码修改都必须落在这里。

历史遗留目录（**只读参考，不是生产版本，不要在其上改动**）：

```
/home/ubuntu/django-lms
```

该目录虽带旧 Git 历史（上游 `adityagoyal222/django-lms`），但与线上版本已分叉，
仅保留作为来源参考，后续是否归档由负责人决定。

## 2. 服务与运行环境

| 项目 | 值 |
| --- | --- |
| systemd 服务 | `django-lms.service`（已 enable） |
| unit 文件 | `/etc/systemd/system/django-lms.service` |
| 应用服务器 | gunicorn（sync worker，3 个 worker） |
| 监听地址 | `0.0.0.0:8000`（无 nginx 反向代理） |
| Python venv | `/home/ubuntu/django-lms-upgrade/django-lms/venv`（Python 3.10.12） |
| Django 版本 | 3.1.3 |
| 反向代理 | 无（未安装 nginx） |
| Node / pm2 | 不涉及，本项目无独立前端进程 |

## 3. 数据库

| 项目 | 值 |
| --- | --- |
| 类型 | MySQL 8.0（本机） |
| 数据目录 | `/var/lib/mysql` |
| 库名 | `django_lms`（utf8mb4 / utf8mb4_unicode_ci） |
| 连接用户 | 由环境变量注入，口令存于 `django_lms/.env` |
| 敏感操作 | 任何写库操作前必须先做逻辑备份 |

> 注意：项目目录下的 `db/` 只是历史遗留的 MySQL 物理文件副本，
> **不是**当前 MySQL 的 datadir，已被 Git 忽略，请勿误删 MySQL 真实数据目录。

## 4. 静态文件与上传文件

| 项目 | 路径 | 说明 |
| --- | --- | --- |
| 源静态文件 | `<项目>/static/` | 纳入 Git |
| collectstatic 产物 | `<项目>/staticfiles/` | 生成物，已忽略 |
| 静态文件方案 | WhiteNoise 中间件（`whitenoise.middleware.WhiteNoiseMiddleware`） | gunicorn 直接输出，无 nginx |
| 用户上传 | `<项目>/media/`（含 `media/research/`） | **唯一副本**，已忽略，必须定期备份 |

修改静态文件后需要重新收集：

```bash
cd /home/ubuntu/django-lms-upgrade/django-lms
./venv/bin/python3 manage.py collectstatic --noinput
```

> 该命令不会重启 gunicorn；WhiteNoise 在进程启动时读取清单，
> 需要让改动生效时请按第 7 节的流程择机重启服务。

## 5. 备份约定

备份根目录（**在项目目录之外，不进 Git**）：

```
/home/ubuntu/backups/django-lms/<YYYYmmdd_HHMMSS>/
```

一次完整备份应包含：

- `django_lms.sql`：MySQL 逻辑备份（mysqldump）
- `media.tar.gz`：用户上传文件全量打包
- `production-code-*.tar.gz`：生产代码快照
- `config/`：systemd unit、`settings.py`、`.env`、`requirements.txt`
- `SHA256SUMS.txt`：上述文件的校验和

首次基线备份：`/home/ubuntu/backups/django-lms/20261019_151922/`

## 6. 常用只读检查命令

```bash
# 服务状态（最常用）
systemctl status django-lms --no-pager

# 实时/近期日志
journalctl -u django-lms --since "30 minutes ago" --no-pager
journalctl -u django-lms -f

# 监听端口与进程
sudo ss -lntp
ps aux | grep gunicorn

# 本机访问验证
curl -I http://127.0.0.1:8000/
curl -I http://127.0.0.1:8000/admin/login/

# Django 只读自检
cd /home/ubuntu/django-lms-upgrade/django-lms
./venv/bin/python3 manage.py check
./venv/bin/python3 manage.py check --deploy   # 只记录告警，不要为消告警直接改生产配置
```

## 7. 变更上线的最小流程（本轮尚未执行过）

```bash
# 1) 先备份（数据库 + media + 关键配置）
# 2) 拉/改代码
# 3) 只读自检
./venv/bin/python3 manage.py check
# 4) 需要迁移时（会写库，必须先备份）
#    ./venv/bin/python3 manage.py migrate
# 5) 静态文件变更时
./venv/bin/python3 manage.py collectstatic --noinput
# 6) 重启服务（择机，确认已备份后）
sudo systemctl restart django-lms
# 7) 复核
systemctl status django-lms --no-pager
curl -I http://127.0.0.1:8000/
```

> 重启服务属于影响在线可用性的操作，需在业务低峰并确认备份完成后执行。

## 8. 已知遗留安全问题（待后续轮次处理）

- BUG-001：`users/admin.py` 仍为 `admin.site.register(User)`，管理员在后台改密码会明文落库导致账号无法登录（详见 `docs/BUG_BACKLOG.md`）。修复需结合数据库备份单独进行。
- 无 HTTPS / 无 nginx；`check --deploy` 存在 W004 / W008 / W012 / W016 告警。
- gunicorn 直接暴露 8000 端口，缺少反向代理层。

以上均**不在本轮收口范围内**，留待后续专项处理。
