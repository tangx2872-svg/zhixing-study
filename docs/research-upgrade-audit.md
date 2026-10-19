# CURRENT SYSTEM AUDIT

审计日期：2026-10-06。范围：README、依赖、settings、路由、模型、视图、表单、模板、静态资源、上传/下载、权限、历史迁移及测试。

## 当前系统结构

- Python 3.8 / Django 3.1.3，服务端模板、Bootstrap 4、本地 CSS/JS；MySQL 默认数据库，SQLite 独立测试数据库。
- `users.User(AbstractUser)`：现有认证、注册、登录及 student/teacher 身份。
- `courses.Course / Enrollment`：课程、教师、选课成员、归档。
- `assignments.Assignment / SubmitAssignment / GradeRecord`：课程作业、截止校验、有效提交与旧提交、成绩与改分历史。
- `resources.Resource`：课程资料名称、FileField、所属课程。没有独立 Project、科研 Task、Comment、Activity。
- `django_lms.files.validate_upload`：20 MB 上限、非空、扩展名白名单；Django 默认存储和 MEDIA_ROOT。教学附件更新/删除后按引用清理旧文件。
- `django_lms.permissions.download_file`：校验权限后 FileResponse 下载，private/no-store/nosniff。没有直接公开 media 路由。
- 登录、CSRF、课程成员与教师归属校验已存在；科研角色应按项目单独授权，不能用全局教师身份绕过成员权限。
- GraphQL 路由已关闭。新模块不重新开启。

## 实际 schema 与基线

已只读连接本机 MySQL，确认 16 张已有表：用户/权限、课程/选课、作业/提交/评分、资料及 Django 系统表，无科研项目表。原有 30 项测试全部通过，Django check 为 0 个问题。
仓库位于 main，发现 industrial-anomaly-detection 下用户未跟踪文件；不修改它们。没有发现适用的 AGENTS.md。

## 可以复用 / 不重复开发

复用 User、认证、CSRF、基础模板、样式、文件白名单/大小验证、Resource 文件记录、默认存储、受保护下载。
不新建认证系统、文件服务、课程系统、评分系统或 Git。Course/Assignment 含教学专用规则，不能直接当作科研 Project/Task，否则污染现有师生权限和成绩流程。

## 推荐模型关系

`ResearchWorkspace → WorkspaceMember / ResearchTask / ProgressCommit / LogicalFile / Activity`

`ResearchTask → ProgressCommit → CommitFileChange → FileVersion → Resource`

`LogicalFile → FileVersion（版本号唯一，当前版本由最大版本号确定，避免双份状态）`

`ProgressCommit → CommitComment`，修正提交通过同项目的 parent_commit 关联。提交、版本及关联只追加，应用不提供修改/删除历史入口；关键外键 PROTECT，禁止账号/项目级联删除科研历史。

Resource 扩展可空 workspace；course 改可空，但约束恰好属于课程或科研项目之一。已有记录无需回填、文件无需搬迁。FileVersion 引用 Resource，不新增第二个 FileField；旧清理逻辑增加版本引用保护。

## 将修改的文件

- 新增 `research/`：models、permissions、services、forms、views、urls、tests、migrations、templates。
- 修改 `django_lms/settings.py`、`urls.py`：注册模块和路由。
- 修改 `resources/models.py` 及新迁移：兼容项目附件归属；`django_lms/files.py`：历史引用保护。
- 修改 `templates/base.html`、`index.html`、`static/django_lms/css/master.css`：导航入口及科研页面样式；新增科研上传交互 JS。
- README 及本目录文档：部署、阶段记录、权限和验收说明。

## migration 风险

只新增科研表并放宽 Resource.course 的非空约束、增加可空 workspace 及归属检查；不删除表、字段、旧迁移或任何数据。旧课程资料保持原样。分阶段迁移避免 Resource ↔ research 循环依赖。
MySQL DDL 不保证整组原子回滚，正式迁移前应备份数据库及 media；通过已有数据的迁移测试验证兼容性。并发版本分配在项目锁内完成，并用唯一约束兜底。存储与数据库非同一事务，异常时清理此次新文件，历史文件永不覆盖。
当前 Python/Django 为现有旧版本；本次不进行框架升级或认证改造。研究表不注册可编辑后台。

## Phase 1 实施计划

1. 新建 Workspace、Membership、Task、ProgressCommit；不改旧业务模型。
2. 项目创建/编辑、成员管理、任务创建与进度、不可覆盖的提交与详情、提交历史。
3. 项目角色服务器端校验；父提交和任务限定在本项目，归档只读。
4. 生成增量迁移，运行 check、迁移漂移检查和研究/教学回归测试，通过后进入 Phase 2。

Phase 2 复用 Resource 增加文件版本及提交附件；Phase 3 动态/评论/成员进度；Phase 4 Dashboard、搜索、筛选、分页与界面完善。每阶段独立验证。
