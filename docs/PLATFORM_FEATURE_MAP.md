# 平台功能地图

审计日期：2026-10-08。Django 服务端 HTML/表单站点，无独立前端服务，无公开 REST API；GraphQL 路由已关闭。所有状态是本轮实际验收状态，PARTIAL 包括本轮尚未完整实操的分支。

## 架构与数据边界

```text
浏览器（Chrome / Edge）
  └─ Django URL / SSR 模板 / CSRF 表单
      ├─ users: 登录、师生账号；管理员 User 表
      ├─ courses: Course → Enrollment → User
      ├─ assignments: Assignment → SubmitAssignment 快照
      │   ├─ CourseGroup / GroupMember → participant_snapshot
      │   ├─ SubmissionAttachment → 私有文件存储
      │   ├─ GradeRecord → rubric / 分项 / 个人调整
      │   └─ 安全 ZIP 文件树 / 文本 diff / PDF、图片、Markdown
      ├─ research: Workspace → Member / Task / ProgressCommit
      │   ├─ LogicalFile → FileVersion → Resource → 私有存储
      │   ├─ CommitFileChange → 精确版本引用
      │   └─ Comment / Activity → 追加历史
      └─ demo: 明确标记的虚构项目，匿名只读
数据库：MySQL；回归测试：独立 SQLite
文件：MEDIA_ROOT；不通过公开 /media/ 暴露
```

## 模块树与当前边界

### 用户

```text
用户
├─ 学生注册 [PASS]
   页面：signup 表单
   handler / 表单：SignUp/UserCreateForm
   数据：User
   权限：匿名；密码校验
├─ 教师身份申请/审批 [FAIL]
   页面：注册身份选择
   handler / 表单：公开接受 user_type
   数据：User.user_type
   权限：无审批
├─ 登录/登出/再次登录 [PASS]
   页面：login/侧栏退出
   handler / 表单：Django auth views
   数据：User/Session
   权限：自身会话
├─ 个人页与历史汇总 [PASS]
   页面：user_profile
   handler / 表单：UserProfile
   数据：Course/SubmitAssignment
   权限：只能自己；他人403
├─ 修改资料 [NOT_IMPLEMENTED]
   页面：无编辑入口
   handler / 表单：无编辑路由
   数据：User已有字段
   权限：未实现
└─ 普通用户改密/找回 [NOT_IMPLEMENTED]
   页面：无入口
   handler / 表单：无路由
   数据：User密码哈希
   权限：未实现
```

### 管理员

```text
管理员
├─ 后台登录与只读提交 [PASS]
   页面：/admin/
   handler / 表单：ModelAdmin
   数据：User/Assignment/SubmitAssignment
   权限：staff/superuser
└─ 用户密码创建/重置 [FAIL]
   页面：普通 password 文本框
   handler / 表单：普通 User ModelAdmin
   数据：User.password
   权限：管理员；不正确哈希
```

### 课程

```text
课程
├─ 创建/编辑/刷新持久 [PASS]
   页面：course_form/detail
   handler / 表单：CreateCourse/UpdateCourse
   数据：Course
   权限：教师，编辑限归属
├─ 课程列表/简介 [PASS]
   页面：course_list/detail
   handler / 表单：ListCourse/CourseDetail
   数据：Course
   权限：简介公开；内容限选课者
├─ 加入/退出 [PASS]
   页面：课程详情 POST 表单
   handler / 表单：enroll/unenroll
   数据：Enrollment 唯一约束
   权限：学生自身
├─ 归档/恢复 [PASS]
   页面：详情操作
   handler / 表单：archive_course
   数据：Course.is_archived
   权限：课程教师
├─ 彻底删除 [NOT_IMPLEMENTED]
   页面：无入口
   handler / 表单：无删除路由
   数据：CASCADE/PROTECT关联
   权限：未实现
└─ 名单 [PASS]
   页面：课程详情
   handler / 表单：CourseDetail
   数据：Enrollment/User
   权限：归属教师
```

### 资料

```text
资料
├─ 课程资料上传→下载 [PASS]
   页面：resource_form/detail
   handler / 表单：CreateResource/download
   数据：Resource/storage
   权限：教师上传；课程成员下载
└─ 删除与重复删除 [PASS]
   页面：确认页
   handler / 表单：delete_view
   数据：Resource/清理信号
   权限：课程教师
```

### 实验

```text
实验
├─ 发布个人/小组实验 [PASS]
   页面：发布表单
   handler / 表单：CreateAssignment
   数据：Assignment
   权限：课程教师
├─ 编辑实验与已提交配置冻结 [PASS]
   页面：编辑表单
   handler / 表单：UpdateAssignment
   数据：Assignment/rubric
   权限：教师；已提交配置disabled
├─ 删除无提交实验/保护有提交 [PASS]
   页面：删除确认
   handler / 表单：DeleteAssignment
   数据：Assignment/SubmitAssignment
   权限：教师且课程有效
├─ 小组创建/共享/名单锁定 [PASS]
   页面：groups/提交详情
   handler / 表单：groups/group_for
   数据：CourseGroup/GroupMember/snapshot
   权限：教师建组；学生仅自己组
├─ 个人提交与撤回再提交 [PASS]
   页面：submit/detail/撤回确认
   handler / 表单：submit/delete_view
   数据：SubmitAssignment/Attachment
   权限：学生已选课，截止前
├─ 小组四类材料与保留附件 [PASS]
   页面：多文件表单
   handler / 表单：SubmitAssignmentForm/save_version
   数据：Attachment/快照
   权限：小组在册成员
├─ 小组 V1/V2/V3 与作者 [PASS]
   页面：提交历史
   handler / 表单：submission_series/save_version
   数据：SubmitAssignment快照
   权限：组员共享读；作者固定
├─ 并发提交唯一有效版本 [PASS]
   页面：提交表单
   handler / 表单：课程/实验行锁事务
   数据：current_slot唯一约束
   权限：A/B分别登录
├─ 代码目录/语法高亮 [PASS]
   页面：browse 文件树
   handler / 表单：manifest/read_entry/Pygments
   数据：附件/ZIP目录
   权限：submission reader
├─ 文本逐行版本差异 [PASS]
   页面：compare 左右红绿
   handler / 表单：changes_between/side_by_side
   数据：同系列提交快照
   权限：同学生/组且同实验
├─ PDF/图片/Markdown预览 [PASS]
   页面：iframe/img/Markdown
   handler / 表单：browse/raw固定MIME
   数据：附件字节
   权限：受保护路径/私有缓存
├─ Office在线预览/协作 [NOT_IMPLEMENTED]
   页面：下载提示
   handler / 表单：无Office渲染
   数据：附件
   权限：下载权限存在
├─ 评分项与组员个人调整 [PASS]
   页面：grade 表单
   handler / 表单：GradeAssignmentForm/grade_assignment
   数据：GradeRecord/snapshot
   权限：课程教师；仅有效版本
├─ 评分修改历史 [PASS]
   页面：提交详情历史区
   handler / 表单：grade_assignment
   数据：GradeRecord
   权限：教师写；本人/组员读
├─ 教师工作台搜索/状态筛选 [PASS]
   页面：experiment_detail
   handler / 表单：workbench_context
   数据：名册/提交/材料
   权限：课程教师
├─ 成绩 CSV [PASS]
   页面：导出筛选成绩链接
   handler / 表单：export grades
   数据：快照/个人分
   权限：课程教师
├─ 批量附件 ZIP [PASS]
   页面：批量下载链接
   handler / 表单：export files
   数据：有效提交附件
   权限：课程教师
├─ 作业中心/成绩反馈 [PASS]
   页面：center/feedback
   handler / 表单：centers
   数据：Assignment/SubmitAssignment
   权限：本人或任课教师
└─ 大规模历史分页 [FAIL]
   页面：全部历史列表
   handler / 表单：未分页历史QuerySet
   数据：全部版本
   权限：课程成员
```

### 科研

```text
科研
├─ 项目创建/编辑/归档/恢复 [PASS]
   页面：list/form/overview
   handler / 表单：workspace_create/edit
   数据：Workspace/Activity
   权限：登录创建；owner管理
├─ 删除项目 [NOT_IMPLEMENTED]
   页面：无入口
   handler / 表单：无路由
   数据：PROTECT历史
   权限：未实现
├─ 添加成员/修改角色 [PASS]
   页面：members 表单
   handler / 表单：members
   数据：WorkspaceMember
   权限：owner
├─ 撤销成员访问/移交负责人 [NOT_IMPLEMENTED]
   页面：无入口
   handler / 表单：无路由
   数据：owner/membership无工作流
   权限：未实现
├─ 任务创建/分配/进度更新 [PASS]
   页面：tasks/new/detail
   handler / 表单：TaskForm/task_detail
   数据：ResearchTask/Activity
   权限：owner创建；受派成员更新
├─ 任务删除/取消 [NOT_IMPLEMENTED]
   页面：无入口
   handler / 表单：无路由
   数据：ResearchTask保留
   权限：未实现
├─ 任务筛选与分页 [PASS]
   页面：tasks filter/pagination
   handler / 表单：tasks/Paginator
   数据：ResearchTask
   权限：项目读权限
├─ 科研进度/关联任务/修正引用 [PASS]
   页面：progress form/detail
   handler / 表单：CommitForm/save_artifacts
   数据：ProgressCommit/Change
   权限：owner/member追加
├─ 文件上传/同名新版本 [PASS]
   页面：upload 表单与冲突提示
   handler / 表单：UploadForm/save_artifacts
   数据：LogicalFile/FileVersion/Resource
   权限：owner/member写
├─ 已有文件版本引用 [PASS]
   页面：existing_versions 多选
   handler / 表单：CommitForm/save_artifacts
   数据：CommitFileChange
   权限：本项目版本限定
├─ 历史版本作者时间与内容 [PASS]
   页面：file_detail/download
   handler / 表单：version_download
   数据：FileVersion/checksum
   权限：项目成员，demo公开
├─ 进度评论/动态 [PASS]
   页面：commit_detail/activity
   handler / 表单：comment_create/activity
   数据：Comment/Activity
   权限：写成员评论，读成员查看
├─ 成员周提交/成员动态 [PASS]
   页面：members/member_activity
   handler / 表单：members聚合查询
   数据：ProgressCommit/User
   权限：项目读权限
├─ 搜索与过滤 [PASS]
   页面：history/list/files filter
   handler / 表单：filtered_commits/ORM
   数据：项目范围数据
   权限：项目读权限
└─ 文件内容 diff/版本恢复 [NOT_IMPLEMENTED]
   页面：无diff/恢复按钮
   handler / 表单：无科研compare/restore
   数据：历史存在但未提供操作
   权限：未实现
```

### 访客

```text
访客
├─ 演示入口/六栏目/搜索/历史下载 [PASS]
   页面：demo/项目页
   handler / 表单：workspace_reader/demo_list
   数据：显式demo_key项目
   权限：公开只读
└─ 演示写保护与禁用演示账户 [PASS]
   页面：只读界面
   handler / 表单：require_workspace
   数据：demo_key/禁用User
   权限：登录也不可写
```

### 文件安全

```text
文件安全
└─ 0KB/大文件/不支持类型/长名 [PASS]
   页面：表单错误提示
   handler / 表单：validate_upload/表单clean
   数据：拒绝创建版本
   权限：先权限再操作
```

### 权限

```text
权限
└─ 项目/提交/附件越权 [PASS]
   页面：按钮权限+直接URL
   handler / 表单：permissions/reader
   数据：owner/member/snapshot
   权限：后端强制
```

### 安全

```text
安全
└─ XSS/CSRF/CORS基础 [PASS]
   页面：转义渲染
   handler / 表单：模板/CsrfMiddleware
   数据：文本仍正常存储
   权限：CSRF token/同源
```

### 边界

```text
边界
└─ 非法主键/emoji/重复请求 [FAIL]
   页面：错误页/表单
   handler / 表单：旧路由/MySQL/创建handler
   数据：部分拒绝/部分重复
   权限：登录后仍可复现
```

### UI

```text
UI
├─ 五种屏幕主要页面 [PARTIAL]
   页面：31页面×5尺寸×2浏览器
   handler / 表单：SSR/local CSS/JS
   数据：真实QA数据
   权限：按角色
└─ 反馈/标题/网络失败恢复 [PARTIAL]
   页面：alerts/表单/导航
   handler / 表单：正常SSR反馈
   数据：持久保存正常
   权限：按角色
```

### 环境

```text
环境
├─ 既有环境启动/迁移/测试 [PASS]
   页面：真实本机页面
   handler / 表单：Django runserver/MySQL
   数据：独立MySQL8.0.46
   权限：本机QA账号
└─ 全新依赖安装 [BLOCKED]
   页面：README安装命令
   handler / 表单：requirements/pip
   数据：无业务DB操作
   权限：隔离新venv
```

### 部署

```text
部署
├─ 生产配置与维护版本 [FAIL]
   页面：开发页面能运行
   handler / 表单：开发settings/runserver
   数据：root/localhost固定
   权限：不满足正式上线
└─ Docker/Jenkins/CI/CD [BLOCKED]
   页面：无运行环境/可用流水线
   handler / 表单：旧compose/DockerFile
   数据：配置不一致
   权限：未验证
```

### 备份

```text
备份
└─ 迁移前备份与独立恢复演练 [PASS]
   页面：CLI运维
   handler / 表单：upgrade_research/mysqldump/mysql
   数据：27表+34附件
   权限：仅QA两库
```

### 性能

```text
性能
└─ 全站查询随课程数增长 [FAIL]
   页面：侧栏我的课程
   handler / 表单：context processor+模板
   数据：额外成员查询
   权限：所有登录页面受影响
```

### 稳定性

```text
稳定性
└─ 20任务/10上传/连续导航/双人提交 [PASS]
   页面：真实表单和下载
   handler / 表单：HTTP+事务
   数据：数据数量/校验一致
   权限：测试角色
```

### 兼容性

```text
兼容性
└─ Firefox/真实手机/其他OS [BLOCKED]
   页面：未运行
   handler / 表单：当前环境无Firefox
   数据：不适用
   权限：不适用
```

## 主要源码入口

| 模块 | 路由 / 业务文件 |
| --- | --- |
| 用户 | users/urls.py、users/forms.py、users/views.py、users/admin.py |
| 公共页面 | django_lms/urls.py、django_lms/views.py、templates/base.html、templates/index.html |
| 课程 | courses/urls.py、views.py、models.py、context_processors.py |
| 教学实验 | assignments/urls.py、views.py、centers.py、experiments.py、experiment_forms.py |
| 提交与代码安全 | assignments/submission_service.py、code_review.py、models.py |
| 科研协作 | research/urls.py、views.py、forms.py、services.py、permissions.py、models.py |
| 访客 | research/demo.py、management/commands/seed_research_demo.py |
| 附件 | resources/views.py、forms.py、models.py；django_lms/files.py、permissions.py |
| UI | 各模块 templates；static/django_lms/css/master.css、experiments.css；js/navigation.js、research-upload.js |
| 运维 | settings.py、requirements.txt、DockerFile、docker-compose.yml、upgrade_research.py |

科研历史不允许通过应用覆盖/删除；教学每次提交生成新快照，撤回只移除有效状态。保留历史不等于具备恢复旧内容为当前版、完整 Git 分支/合并或科研文本 diff。

完整需求→实现→实测矩阵、证据和风险见 [QA_AUDIT_REPORT.md](QA_AUDIT_REPORT.md)。
