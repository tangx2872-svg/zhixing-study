# 1. Executive Summary

**结论：NOT_READY（尚不具备正式服务器上线条件）。** 可以给少量知情同门做受控试用/展示，真实教学和科研主流程已经可用；在账号安全、Unicode、异常响应和部署配置修复前，不适合直接承接正式多人教学。

审计日期：2026-10-08；约11:33开始。只审计：本轮没有修改业务代码、没有替换需求、没有 Git 提交或推送。测试期间所有写入均在新建 MySQL `django_lms_qa_20261008`、独立恢复库 `django_lms_qa_restore_20261008` 和 `.local/qa-20261008/media`；未操作真实教学库或用户附件。测试账号全部 `qa-*`，管理员、教师、A/B、只读者、无关用户均独立验证。测试密码留在忽略目录，不写进报告。

| 维度 | 得分（0–100） | 依据 |
| --- | ---: | --- |
| 总体完成度 | 74 | 核心链路已闭环，但账号、部署和异常分支仍阻断正式使用 |
| 核心功能完成度 | 82 | 课程/教学实验/多人科研/历史内容均实测；账号生命周期和成员撤销缺口 |
| UI 完成度 | 85 | 双浏览器五尺寸主要页面可操作；手机diff提示、页面标题和失败恢复需改 |
| 稳定性 | 68 | 连续/小并发成功；emoji及非法ID500、重复创建失败 |
| 部署准备度 | 25 | 开发默认设置、旧栈、容器配置未对齐，新安装受环境TLS阻断 |

分数是基于功能闭环、异常处理、可维护性和部署门槛的审计评价，不等于自动测试覆盖率，也不是把负向权限用例通过比例当功能完成度。存在P0时总体判断仍为NOT_READY。

## 验证规模与严格口径

- 固定 **80项顶层检查：63 PASS、9 FAIL、2 PARTIAL、4 NOT_IMPLEMENTED、2 BLOCKED**。扩展16项及并发/分页探针是诊断证据，不重复计入80项。完整条目见 [check-ledger-80.json](qa-evidence/2026-10-08/check-ledger-80.json)。
- 现有77项自动化回归：**77 PASS / 0 FAIL / 0 SKIP**；现有运行栈检查通过，MySQL新迁移与迁移漂移检查通过。
- Chrome与Edge各31个主要页面×5视口，合计310次页面尺寸测量；加上真实注册/课程/协作/实验/管理员操作及补充详情页。截图已人工查看，不只靠DOM宽度。
- 真正核对了下载内容、附件SHA/ZIP CRC、数据库数量/作者/有效版本和刷新重登后持久性。未把HTTP200/按钮/数据库表存在视为闭环。
- 无独立前端进程，无公开REST API；所称接口测试为真实HTML GET/POST handler测试。GraphQL入口关闭。
- Firefox、Docker容器运行、真实移动设备、其他操作系统及长时大型压力测试均 **NOT_TESTED**。不据此宣称兼容或稳定。
- 无业务修复；一开始浏览器CDP选到了扩展后台页，已仅修正QA脚本为type=page；脚本选择链接和截图过早的问题亦仅调整审计工具。原有业务文件哈希未变化。

## 五个直接结论

1. **能否给同门使用？** 可以受控试用、演示和收集反馈；目前不能按正式上线产品交付。特别不要用当前后台原始密码字段重置真实账号。
2. **真正完成的功能？** 注册登录、课程增改/选退/归档、受保护资料上传下载、个人/小组实验与版本快照、在线代码/报告预览、文本diff、评分/个人调分/CSV和ZIP、科研成员任务进度评论及真实历史文件、只读访客演示。
3. **哪些看起来完成但并不完整？** 账号管理缺自助编辑/改密且后台改密错误；科研成员只能加/改角色不能撤销；工作台有分页但历史全量加载；科研“版本管理”是准确的历史追溯，尚无内容diff/恢复/Git分支合并；任务删除未实现；部署文件存在不等于可以部署。
4. **上服务器之前必须修什么？** BUG-001/002的账号与生产配置；BUG-003/004的MySQL编码和非法ID500；BUG-005/006的教师授予与重复提交；BUG-007/008/009的密码生命周期、受维护运行栈和可验证部署路径。
5. **下一轮优先做什么？** 暂停新功能，先做“账号安全＋生产配置＋MySQL/异常回归”修复批次；随后处理幂等、成员撤销、分页/N+1，再补长表单体验和Firefox/容器复测。

# 2. Feature Matrix

状态只用PASS/PARTIAL/FAIL/NOT_IMPLEMENTED/BLOCKED；PASS指本轮对应正常流程和指定权限检查实际通过，不能推广到无限数据/所有恶意输入。PARTIAL也包括本轮没有完整UI实测的分支。缺失能力不自动等于假功能。完整模块树见 [PLATFORM_FEATURE_MAP.md](PLATFORM_FEATURE_MAP.md)。

| 模块 / 功能 | 前端 | 后端 | DB | 权限 | 实际测试 | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| 用户 / 学生注册 | signup 表单 | SignUp/UserCreateForm | User | 匿名；密码校验 | Chrome 注册→登录→创建→重登 | PASS |
| 用户 / 教师身份申请/审批 | 注册身份选择 | 公开接受 user_type | User.user_type | 无审批 | 自选教师后 courses/new 200；BUG-005 | FAIL |
| 用户 / 登录/登出/再次登录 | login/侧栏退出 | Django auth views | User/Session | 自身会话 | Chrome/Edge 多角色登录，刷新/重登持久 | PASS |
| 用户 / 个人页与历史汇总 | user_profile | UserProfile | Course/SubmitAssignment | 只能自己；他人403 | 浏览个人页，非法他人ID直接请求403 | PASS |
| 用户 / 修改资料 | 无编辑入口 | 无编辑路由 | User已有字段 | 未实现 | 真实个人页只读；edit 404；BUG-012 | NOT_IMPLEMENTED |
| 用户 / 普通用户改密/找回 | 无入口 | 无路由 | User密码哈希 | 未实现 | password_change 404；BUG-007 | NOT_IMPLEMENTED |
| 管理员 / 后台登录与只读提交 | /admin/ | ModelAdmin | User/Assignment/SubmitAssignment | staff/superuser | Chrome/Edge 登录并浏览提交列表 | PASS |
| 管理员 / 用户密码创建/重置 | 普通 password 文本框 | 普通 User ModelAdmin | User.password | 管理员；不正确哈希 | 实际改密原样存储，登录校验失败；BUG-001 | FAIL |
| 课程 / 创建/编辑/刷新持久 | course_form/detail | CreateCourse/UpdateCourse | Course | 教师，编辑限归属 | Chrome 创建/编辑/刷新；学生直请求403 | PASS |
| 课程 / 课程列表/简介 | course_list/detail | ListCourse/CourseDetail | Course | 简介公开；内容限选课者 | 双浏览器五种尺寸页面操作 | PASS |
| 课程 / 加入/退出 | 课程详情 POST 表单 | enroll/unenroll | Enrollment 唯一约束 | 学生自身 | Chrome 加入→个人页→退出；DB同步 | PASS |
| 课程 / 归档/恢复 | 详情操作 | archive_course | Course.is_archived | 课程教师 | HTTP归档→提交403→恢复→详情200 | PASS |
| 课程 / 彻底删除 | 无入口 | 无删除路由 | CASCADE/PROTECT关联 | 未实现 | 实际产品以归档保留记录 | NOT_IMPLEMENTED |
| 课程 / 名单 | 课程详情 | CourseDetail | Enrollment/User | 归属教师 | 教师详情看到组员；学生不见全量名单 | PASS |
| 资料 / 课程资料上传→下载 | resource_form/detail | CreateResource/download | Resource/storage | 教师上传；课程成员下载 | 实际文件内容一致，无关用户403 | PASS |
| 资料 / 删除与重复删除 | 确认页 | delete_view | Resource/清理信号 | 课程教师 | POST后DB及磁盘均删除；再次404；学生403 | PASS |
| 实验 / 发布个人/小组实验 | 发布表单 | CreateAssignment | Assignment | 课程教师 | Edge创建小组、要求与评分项；个人实验提交实测 | PASS |
| 实验 / 编辑实验与已提交配置冻结 | 编辑表单 | UpdateAssignment | Assignment/rubric | 教师；已提交配置disabled | Chrome真实修改要求→刷新持久；提交方式/材料/评分项disabled均确认 | PASS |
| 实验 / 删除无提交实验/保护有提交 | 删除确认 | DeleteAssignment | Assignment/SubmitAssignment | 教师且课程有效 | 无提交删除DB消失；重复404；有提交保护 | PASS |
| 实验 / 小组创建/共享/名单锁定 | groups/提交详情 | groups/group_for | CourseGroup/GroupMember/snapshot | 教师建组；学生仅自己组 | Edge建组，A提交B查看；改已提交组403 | PASS |
| 实验 / 个人提交与撤回再提交 | submit/detail/撤回确认 | submit/delete_view | SubmitAssignment/Attachment | 学生已选课，截止前 | 真实字节下载；撤回历史仍在；再提交v2 | PASS |
| 实验 / 小组四类材料与保留附件 | 多文件表单 | SubmitAssignmentForm/save_version | Attachment/快照 | 小组在册成员 | Edge四类上传→下载→继承；缺材料不入DB | PASS |
| 实验 / 小组 V1/V2/V3 与作者 | 提交历史 | submission_series/save_version | SubmitAssignment快照 | 组员共享读；作者固定 | A创建v1/v2、B创建v3；旧作者/内容保持 | PASS |
| 实验 / 并发提交唯一有效版本 | 提交表单 | 课程/实验行锁事务 | current_slot唯一约束 | A/B分别登录 | 两请求同时提交均成功，追加2版且有效数1 | PASS |
| 实验 / 代码目录/语法高亮 | browse 文件树 | manifest/read_entry/Pygments | 附件/ZIP目录 | submission reader | Chrome/Edge Java源码、行号、高亮实测 | PASS |
| 实验 / 文本逐行版本差异 | compare 左右红绿 | changes_between/side_by_side | 同系列提交快照 | 同学生/组且同实验 | v1/v2新增删除修改；两浏览器操作 | PASS |
| 实验 / PDF/图片/Markdown预览 | iframe/img/Markdown | browse/raw固定MIME | 附件字节 | 受保护路径/私有缓存 | 图片解码、Markdown、PDF等待4秒截图实际有内容 | PASS |
| 实验 / Office在线预览/协作 | 下载提示 | 无Office渲染 | 附件 | 下载权限存在 | UI明确提示下载；在线编辑未实现 | NOT_IMPLEMENTED |
| 实验 / 评分项与组员个人调整 | grade 表单 | GradeAssignmentForm/grade_assignment | GradeRecord/snapshot | 课程教师；仅有效版本 | 55+35=90；B调整-5得85；CSV/组员反馈一致 | PASS |
| 实验 / 评分修改历史 | 提交详情历史区 | grade_assignment | GradeRecord | 教师写；本人/组员读 | Chrome同版先90后80，原评分与评语保留；B重登个人分77正确 | PASS |
| 实验 / 教师工作台搜索/状态筛选 | experiment_detail | workbench_context | 名册/提交/材料 | 课程教师 | Edge已评分筛选，组名单/材料显示、导出 | PASS |
| 实验 / 成绩 CSV | 导出筛选成绩链接 | export grades | 快照/个人分 | 课程教师 | 实际CSV含B账号85分，学生导出403 | PASS |
| 实验 / 批量附件 ZIP | 批量下载链接 | export files | 有效提交附件 | 课程教师 | ZIP可打开/CRC无错/源码字节与最新上传一致 | PASS |
| 实验 / 作业中心/成绩反馈 | center/feedback | centers | Assignment/SubmitAssignment | 本人或任课教师 | Edge组员中心/反馈与调整成绩一致 | PASS |
| 实验 / 大规模历史分页 | 全部历史列表 | 未分页历史QuerySet | 全部版本 | 课程成员 | 32版第1、2页都显示32项；BUG-011 | FAIL |
| 科研 / 项目创建/编辑/归档/恢复 | list/form/overview | workspace_create/edit | Workspace/Activity | 登录创建；owner管理 | 真实UI创建+HTTP归档写403恢复200 | PASS |
| 科研 / 删除项目 | 无入口 | 无路由 | PROTECT历史 | 未实现 | 项目归档不是删除；BUG-017 | NOT_IMPLEMENTED |
| 科研 / 添加成员/修改角色 | members 表单 | members | WorkspaceMember | owner | 真实A/B添加与只读界面，非法管理403 | PASS |
| 科研 / 撤销成员访问/移交负责人 | 无入口 | 无路由 | owner/membership无工作流 | 未实现 | 成员页无移除功能；BUG-016 | NOT_IMPLEMENTED |
| 科研 / 任务创建/分配/进度更新 | tasks/new/detail | TaskForm/task_detail | ResearchTask/Activity | owner创建；受派成员更新 | 20条创建修改，成员UI更新70%持久 | PASS |
| 科研 / 任务删除/取消 | 无入口 | 无路由 | ResearchTask保留 | 未实现 | 任务delete404；BUG-017 | NOT_IMPLEMENTED |
| 科研 / 任务筛选与分页 | tasks filter/pagination | tasks/Paginator | ResearchTask | 项目读权限 | 真实第2页可回上一页，20条稳定性操作 | PASS |
| 科研 / 科研进度/关联任务/修正引用 | progress form/detail | CommitForm/save_artifacts | ProgressCommit/Change | owner/member追加 | Edge关联任务提交；Chrome追加新进度parent引用原记录，历史仍可查看 | PASS |
| 科研 / 文件上传/同名新版本 | upload 表单与冲突提示 | UploadForm/save_artifacts | LogicalFile/FileVersion/Resource | owner/member写 | UI同名确认v1/v2，HTTP v3；10个文件校验一致 | PASS |
| 科研 / 已有文件版本引用 | existing_versions 多选 | CommitForm/save_artifacts | CommitFileChange | 本项目版本限定 | Chrome多选已有版本提交，详情显示引用v1，未上传或复制新文件 | PASS |
| 科研 / 历史版本作者时间与内容 | file_detail/download | version_download | FileVersion/checksum | 项目成员，demo公开 | v1/v2/v3下载字节精确匹配，作者时间在DB与UI核对 | PASS |
| 科研 / 进度评论/动态 | commit_detail/activity | comment_create/activity | Comment/Activity | 写成员评论，读成员查看 | UI中文评论含script文本，未执行；导师评论动态可见 | PASS |
| 科研 / 成员周提交/成员动态 | members/member_activity | members聚合查询 | ProgressCommit/User | 项目读权限 | UI周提交数2与DB一致；成员详情页面已访问 | PASS |
| 科研 / 搜索与过滤 | history/list/files filter | filtered_commits/ORM | 项目范围数据 | 项目读权限 | Chrome按成员、任务和baseline关键词组合筛选；Edge访客关键词搜索通过 | PASS |
| 科研 / 文件内容 diff/版本恢复 | 无diff/恢复按钮 | 无科研compare/restore | 历史存在但未提供操作 | 未实现 | 科研只有下载；教学diff不代表科研diff | NOT_IMPLEMENTED |
| 访客 / 演示入口/六栏目/搜索/历史下载 | demo/项目页 | workspace_reader/demo_list | 显式demo_key项目 | 公开只读 | Edge匿名六页，v1/v3字节和私有项目登录跳转 | PASS |
| 访客 / 演示写保护与禁用演示账户 | 只读界面 | require_workspace | demo_key/禁用User | 登录也不可写 | 直接POST403；示例为明确标注虚构数据 | PASS |
| 文件安全 / 0KB/大文件/不支持类型/长名 | 表单错误提示 | validate_upload/表单clean | 拒绝创建版本 | 先权限再操作 | 0KB、20MB+1、exe、长名均不入DB；遍历ZIP拒绝 | PASS |
| 权限 / 项目/提交/附件越权 | 按钮权限+直接URL | permissions/reader | owner/member/snapshot | 后端强制 | 23类直接请求含403/404；无关用户不能看/改/下 | PASS |
| 安全 / XSS/CSRF/CORS基础 | 转义渲染 | 模板/CsrfMiddleware | 文本仍正常存储 | CSRF token/同源 | script作为文本；无token403；未返回跨域通配头 | PASS |
| 边界 / 非法主键/emoji/重复请求 | 错误页/表单 | 旧路由/MySQL/创建handler | 部分拒绝/部分重复 | 登录后仍可复现 | 非法ID和emoji500；重复任务2条；BUG-003/004/006 | FAIL |
| UI / 五种屏幕主要页面 | 31页面×5尺寸×2浏览器 | SSR/local CSS/JS | 真实QA数据 | 按角色 | 310次布局测量无正常页整页溢出；错误页溢出，手机diff提示不足 | PARTIAL |
| UI / 反馈/标题/网络失败恢复 | alerts/表单/导航 | 正常SSR反馈 | 持久保存正常 | 按角色 | 空表单有错误；成功有提示；断网浏览器错误页，无草稿，标题重复 | PARTIAL |
| 环境 / 既有环境启动/迁移/测试 | 真实本机页面 | Django runserver/MySQL | 独立MySQL8.0.46 | 本机QA账号 | 77测试通过；MySQL完整新迁移成功；无漂移 | PASS |
| 环境 / 全新依赖安装 | README安装命令 | requirements/pip | 无业务DB操作 | 隔离新venv | 实际安装遇PyPI TLS EOF，未成功完成 | BLOCKED |
| 部署 / 生产配置与维护版本 | 开发页面能运行 | 开发settings/runserver | root/localhost固定 | 不满足正式上线 | 5个deploy warning、旧框架、密钥跟踪；BUG-002/008 | FAIL |
| 部署 / Docker/Jenkins/CI/CD | 无运行环境/可用流水线 | 旧compose/DockerFile | 配置不一致 | 未验证 | Docker命令不存在；容器不能判为可部署 | BLOCKED |
| 备份 / 迁移前备份与独立恢复演练 | CLI运维 | upgrade_research/mysqldump/mysql | 27表+34附件 | 仅QA两库 | 实际备份校验→恢复→逐表/附件对比一致 | PASS |
| 性能 / 全站查询随课程数增长 | 侧栏我的课程 | context processor+模板 | 额外成员查询 | 所有登录页面受影响 | 加20课程查询9→29；BUG-010 | FAIL |
| 稳定性 / 20任务/10上传/连续导航/双人提交 | 真实表单和下载 | HTTP+事务 | 数据数量/校验一致 | 测试角色 | 除已记录emoji/重复等边界，正常连续操作成功；长期负载未测 | PASS |
| 兼容性 / Firefox/真实手机/其他OS | 未运行 | 当前环境无Firefox | 不适用 | 不适用 | Firefox NOT_TESTED；仅桌面仿真视口，不代表真机 | BLOCKED |

# 3. Critical Bugs

详尽复现、预期/实际、原因、修复建议与范围见 [BUG_BACKLOG.md](BUG_BACKLOG.md)。

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| [BUG-001](BUG_BACKLOG.md#bug-001) | 管理员修改密码会原样存储输入并使账号无法登录 | [admin-login.json](qa-evidence/2026-10-08/admin-login.json) |
| [BUG-002](BUG_BACKLOG.md#bug-002) | 当前生产配置会暴露调试信息且复用已入 Git 的密钥 | [deploy-check.log](qa-evidence/2026-10-08/deploy-check.log) |

# 4. Major Bugs

详尽复现、预期/实际、原因、修复建议与范围见 [BUG_BACKLOG.md](BUG_BACKLOG.md)。

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| [BUG-003](BUG_BACKLOG.md#bug-003) | MySQL 输入 emoji 返回 500 | [extra.json](qa-evidence/2026-10-08/extra.json) |
| [BUG-004](BUG_BACKLOG.md#bug-004) | 多个旧路由接受非数字主键并返回 500 | [probe.json](qa-evidence/2026-10-08/probe.json) |
| [BUG-005](BUG_BACKLOG.md#bug-005) | 公开注册可直接取得教师身份 | [probe.json](qa-evidence/2026-10-08/probe.json) |
| [BUG-006](BUG_BACKLOG.md#bug-006) | 相同创建请求会产生重复任务 | [probe.json](qa-evidence/2026-10-08/probe.json) |
| [BUG-007](BUG_BACKLOG.md#bug-007) | 普通用户没有修改密码或找回密码的完整流程 | [probe.json](qa-evidence/2026-10-08/probe.json) |
| [BUG-008](BUG_BACKLOG.md#bug-008) | 运行栈已停止安全维护 | [tests.log](qa-evidence/2026-10-08/tests.log) |
| [BUG-009](BUG_BACKLOG.md#bug-009) | Docker 配置不能视为可部署成品 | [deploy-check.log](qa-evidence/2026-10-08/deploy-check.log) |

# 5. Minor Bugs

详尽复现、预期/实际、原因、修复建议与范围见 [BUG_BACKLOG.md](BUG_BACKLOG.md)。

| 编号 | 问题 | 证据 |
| --- | --- | --- |
| [BUG-010](BUG_BACKLOG.md#bug-010) | 全站“我的课程”侧栏存在 N+1 查询 | [extra.json](qa-evidence/2026-10-08/extra.json) |
| [BUG-011](BUG_BACKLOG.md#bug-011) | 实验历史版本无分页，工作台分页也未限制历史读取 | [concurrency.json](qa-evidence/2026-10-08/concurrency.json) |
| [BUG-012](BUG_BACKLOG.md#bug-012) | 个人资料只能查看，不能自助修改 | [probe.json](qa-evidence/2026-10-08/probe.json) |
| [BUG-013](BUG_BACKLOG.md#bug-013) | 科研不同页面和表单共用项目标题，浏览器标签难区分 | [chrome-layout.json](qa-evidence/2026-10-08/chrome-layout.json) |
| [BUG-014](BUG_BACKLOG.md#bug-014) | 提交中/断网反馈及草稿恢复不完整 | [chrome-extra.json](qa-evidence/2026-10-08/chrome-extra.json) |
| [BUG-015](BUG_BACKLOG.md#bug-015) | 移动端代码对比需要横向拖动但缺少明显提示 | [chrome-diff-390.png](qa-evidence/2026-10-08/chrome-diff-390.png) |
| [BUG-016](BUG_BACKLOG.md#bug-016) | 科研成员可添加/改角色，但缺少移除或撤销访问入口 | [browser-report.json](qa-evidence/2026-10-08/browser-report.json) |

# 6. UI / UX Issues

| 页面/状态 | 实测结果 | 处理建议 |
| --- | --- | --- |
| 首页/课程/科研概览 | 导航、卡片、校训、层级与间距可读；移动导航展开可操作 | 保留现有结构 |
| 注册/登录/课程表单 | 标签关联正常，输入可操作，密码说明清楚；教师自选为权限问题 | 先修身份授予，后精简过长注册表单 |
| 个人页 | 持久化内容/成绩可查看；没有资料编辑与改密入口 | 补账号闭环，避免将“个人页”当“账号管理” |
| 科研各栏目 | 六页可访问；子页标题重复 | BUG-013：具体栏目/动作进入title |
| 进度/上传表单 | 空输入字段旁显示中文错误；成功跳到详情；上传失败需重选有文字说明 | BUG-014：提交忙碌状态、失败重试/草稿；无须换成SPA |
| 任务详情/分页 | details展开后成员可更新进度；第2页/上一页实测可操作 | 增加任务取消/归档等生命周期后再设计删除 |
| 科研版本历史 | v1/v2/v3作者、时间、校验与下载清楚，上传新版本按钮明显 | 不把下载版本当内容diff/恢复 |
| 实验批改工作台 | 桌面表格、手机卡片可用；筛选/成绩导出可操作 | 历史分页和后台真正分页优先于视觉微调 |
| 手机代码/diff | 文件树与代码区域内部滚动，没有整页爆宽；旧/新版对比需要横向拖动 | BUG-015：手势提示或统一diff视图 |
| 评分页 | 每个评分项上限、个人调整帮助与保存反馈明确 | 合法评分通过；非法分数表单错误不500 |
| PDF | 首次截图150ms时灰屏，等待4秒后实际出现页内容，两浏览器复核 | 可加加载说明；灰屏短暂加载不是永久预览失败 |
| 删除/撤回 | 资源/实验/提交有确认页；撤回明确说明保留历史；项目/任务无删除按钮 | 不把归档或撤回误写成彻底删除 |
| 403/404/500 | 合法权限拒绝正常；非法ID导致DEBUG技术页，手机溢出 | 先修根因与生产错误页；不要向普通用户展示traceback |
| modal/toast/loading | 当前产品为SSR确认页和alert反馈，没有modal/toast系统；不据此认定空功能 | 通用提交中状态缺失单独记录 |
| 空状态/搜索/返回 | 无记录时有文字；搜索/状态筛选/取消/返回入口可操作 | 成员/任务/关键词组合已实测；不外推所有输入组合 |

关键截图：[chrome-workbench-390.png](qa-evidence/2026-10-08/chrome-workbench-390.png), [chrome-code-390.png](qa-evidence/2026-10-08/chrome-code-390.png), [chrome-diff-390.png](qa-evidence/2026-10-08/chrome-diff-390.png), [chrome-grade-390.png](qa-evidence/2026-10-08/chrome-grade-390.png), [chrome-empty-form-error.png](qa-evidence/2026-10-08/chrome-empty-form-error.png), [chrome-v3-file.png](qa-evidence/2026-10-08/chrome-v3-file.png), [chrome-pdf-waited.png](qa-evidence/2026-10-08/chrome-pdf-waited.png)。

# 7. Compatibility

| 环境 | 实际测试 | 结论 |
| --- | --- | --- |
| Chrome Chrome/154.0.8037.97 / Windows | 注册、课程、管理员、科研详情/分页/评论、五尺寸全页检查 | PASS（限定已测流程）；产品缺陷见对应BUG |
| Edge Edg/154.0.4258.62 / Windows | 科研/实验/访客完整流程、五尺寸及PDF/表单补充复核 | PASS（限定已测流程）；历史版评分403是权限预期 |
| Firefox | 本机常见安装路径未发现可执行程序 | NOT_TESTED；检查账本用BLOCKED表示 |
| 1920×1080 | Chrome/Edge各31主要页面 | 正常页面无整页横向溢出 |
| 1440×900 | 同上；保留截图 | 正常页面无整页横向溢出 |
| 1366×768 | 同上 | 正常页面无整页横向溢出 |
| 768×1024 | 同上；桌面设备仿真视口 | 正常页面无整页横向溢出 |
| 390×844 | 同上；手机导航/表单/代码检查 | 正常页可操作；内部代码滚动需提示；DEBUG错误页溢出 |
| iOS/Android真机、Safari、Linux/macOS | 无实际设备/运行 | NOT_TESTED |
| Docker | docker命令不可用 | NOT_TESTED；静态配置不一致单独记录 |

尺寸检查不是可访问性认证：检查了标签、按钮、导航及主要页面截图，未完成屏幕阅读器/完整WCAG对比度测试。未遇到正常页按钮遮挡或表格撑宽；不能外推所有未来数据长度。Chrome/Edge存在/favicon.ico自动404（BUG-019）。Edge后续复核时v2已成历史版，/grade/2/返回403是预期保护，不记为新失败。

布局原始数据：[chrome-layout.json](qa-evidence/2026-10-08/chrome-layout.json)、[edge-layout.json](qa-evidence/2026-10-08/edge-layout.json)。额外详情/异常操作：[chrome-extra.json](qa-evidence/2026-10-08/chrome-extra.json)、[edge-extra.json](qa-evidence/2026-10-08/edge-extra.json)。

# 8. Security / Permission

## 已实际验证的防御边界

- A/B不属于项目时不能读/改/下载；普通成员不能编辑项目；只读成员不能发进度/上传/改任务；教师身份不会自动获得他人科研项目权限。
- 非课程成员不能下载实验提交、浏览源码/比较；学生不能评分、建组、创建课程或导出他人的成绩；个人页禁止读取他人ID。
- /media/直接请求404；附件通过受保护下载handler；路径遍历源码查询404；带../的ZIP上传拒绝且不创建提交。
- 无CSRF token的POST403；跨域请求未见Access-Control-Allow-Origin通配；文字script标签转义且浏览器未执行。
- 正常注册/创建用户的密码为PBKDF2哈希；这不抵消管理员编辑路径原样写password的问题。
- 私有代码页/下载包含no-store、nosniff；HTML报告作为文本源码或附件，不作为任意HTML inline执行。
- 演示项目明确虚构，匿名只读；登录后也不能写；普通私有项目仍需要登录与成员权限。

## 不通过/未覆盖

P0后台密码、固定密钥与DEBUG；P1教师自选及旧栈。`.env`、`.local`在ignore规则内，且git ls-files没有.env；当前配置不自动加载.env，不能以“文件存在”推断环境变量生效。compose中的示例凭据已跟踪，不能原样用于服务器。数据库使用root且主机/库名固定，需生产最小权限账号和环境注入。

未做破坏性渗透、恶意PDF执行、外部依赖全量CVE扫描或真实生产访问。只做本机防御性验证；没有把“若干拒绝请求通过”说成完整安全认证。证据：[probe.json](qa-evidence/2026-10-08/probe.json)、[extra.json](qa-evidence/2026-10-08/extra.json)、[error-excerpts.txt](qa-evidence/2026-10-08/error-excerpts.txt)。

运行维护依据：Django3.1已停止支持（官方表列2021-12-07结束扩展支持），Python3.8也处于停止维护状态。[Django官方支持表](https://www.djangoproject.com/download/)、[Python官方版本状态](https://devguide.python.org/versions/)。未在本轮进行运行栈升级。

# 9. Performance

以下是**本机单用户、开发服务、小数据、真实HTTP GET共5次的平均耗时**，包含HTTP处理，不是公网FCP/生产SLA；查询数由仅QA启用的中间件记录。先记录小数据基线，再单独增加20课程检验增长。

| 页面 | 平均HTTP耗时 ms | 查询数 | 响应体量 bytes |
| --- | ---: | ---: | ---: |
| home | 26.54 | 5 | 5603 |
| courses | 38.63 | 7 | 4833 |
| projects | 33.76 | 7 | 4745 |
| project | 69.95 | 17 | 8635 |
| files | 46.17 | 11 | 5213 |
| history | 55.19 | 12 | 6917 |
| search | 55.1 | 12 | 6655 |
| workbench | 59.98 | 19 | 7459 |

明确问题：BUG-010侧栏N+1，增加20无关课程后科研列表查询9→29；BUG-011历史32版不分页，第1、2页各渲染32条。批改工作台虽有可操作分页，但后端先list全部有效提交/成员，且历史区全量输出。科研新增提交表单会加载所有existing_versions/parent_commit选项，当前11个文件3版已经实测，海量版本开销为后续需量测项，未假称压测过。

连续性验证：20任务连续创建/修改成功；任务删除功能未实现，因此没有伪造“20删除通过”。10小文件实际上传、下载和SHA核对全部一致；20次页面请求均200。两组员并发请求追加2个版本，只有1个current_slot=1；不等于高并发长期稳定。

浏览器短时导航20次后Chrome JSHeap由约0.58MiB到1.68MiB（一次GC后），Documents/Nodes仍随页面缓存变化；没有证明内存泄漏或长期稳定，记录为短时样本，不做推断。详情见 [chrome-extra.json](qa-evidence/2026-10-08/chrome-extra.json)。未测公网延迟、大文件长期存储容量、数据库最大连接和长时并发。

# 10. Missing / Fake / Partial Features

## 最需要区分的能力

| 外观看到的能力 | 实际完成度 | 不能宣称的部分 |
| --- | --- | --- |
| “用户/个人页/管理后台” | 登录注册和只读个人页可用 | 不能宣称账号生命周期完整：资料编辑、改密/找回缺失，后台改密有真实缺陷 |
| “版本管理” | 科研历史作者/时间/字节/校验准确；实验快照与文本diff实际可用 | 不能宣称Git仓库、分支合并、科研内容diff、恢复旧内容为当前版 |
| “项目成员管理” | 添加已注册成员、设置写/只读可用 | 没有邮件邀请、成员撤销或负责人移交 |
| “任务管理” | 创建、分配、进度、筛选、分页可用 | 没有删除/取消；不能写成完整CRUD |
| “项目删除/恢复” | 归档后只读、负责人恢复可用 | 归档不是删除；项目恢复不是文件内容回滚 |
| “批改分页” | 顶部名单每页25行 | 底部全部历史未分页；后台名册/有效提交先全量加载 |
| “在线预览” | 源码/文本/Markdown/PDF/图片可用 | Office仅下载；Markdown为安全子集，无富文本协作 |
| “提交成功” | 正常流程DB/文件持久和刷新重登均成立 | 重复同一创建请求无幂等；断网提交没有产品级恢复 |
| “演示数据” | 明确标记虚构、只读、独立示例账号 | 不是假业务数据；真实账号/私有项目仍按授权限制 |
| “Docker/部署文件” | 源文件存在 | 没有当前可验证的一键生产部署；容器环境未运行且静态配置不一致 |

## 占位/假数据搜索

已搜索 users/courses/assignments/research/resources/templates/django_lms 中 TODO、FIXME、mock、placeholder、dummy、fake、temporary、not implemented。命中主要是搜索框placeholder、测试里的unittest.mock以及演示初始化对时间的patch、故意构造fake.png的防御测试。没有依据把这些误报为假功能。没有在已测主流程发现“成功提示但DB没保存”或“刷新消失”；明确缺陷和未实现能力已逐项记录。

旧 assignments/assignment_detail.html、assignment_list.html等模板仍在目录，但当前路由指向experiment_detail等；遗留模板存在不计为现行功能。收尾阶段又实际通过Chrome完成实验要求编辑与配置冻结、同版改分历史、组员77分反馈、引用已有文件版本并关联原进度、成员/任务/关键词组合筛选；这些分支已按实测更新为PASS。证据见closing-browser.json；没有用自动测试替代操作。

# 11. Recommended Fix Order

| 次序 | 范围 | 验收门槛 |
| --- | --- | --- |
| P0 | BUG-001管理员密码；BUG-002生产密钥/DEBUG/安全配置 | 改密可登录、DB非原始密码；生产无debug trace，使用新环境密钥及HTTPS配置 |
| P1 第一批 | BUG-003编码、BUG-004非法ID、BUG-005教师授予、BUG-006幂等 | 真实MySQL emoji成功；错误ID404；公开注册不能自授教师；双击只产生一条意图记录 |
| P1 第二批 | BUG-007账号改密/恢复、BUG-008维护栈、BUG-009部署配置 | 账号恢复闭环；受支持环境全回归；全新环境/容器真实启动和迁移通过 |
| P2 | BUG-010/011查询与分页、BUG-012资料、BUG-016成员撤销 | 查询数不随无关课程线性涨；历史分页；离组用户直接URL/下载403 |
| P2 体验 | BUG-013/014/015标题、提交状态/失败恢复、手机diff | 用户知道当前页面、是否提交成功、如何查看新版 |
| P3 | BUG-017/018历史策略与科研diff；BUG-019图标 | 按实际需求选择，不能先增加Git式功能掩盖P0/P1 |

## 自动化现状与后续最有价值的回归

现有测试以Django单元/集成/请求handler测试为主：30教学、17科研/迁移、4访客、26实验，共77通过。测试使用SQLite与测试哈希器；不能证明真实MySQL字符集/并发，因此本轮额外使用MySQL复现了emoji缺陷。没有独立前端单元测试工程，也没有纳入仓库CI的完整跨浏览器E2E矩阵；已有浏览器脚本位于忽略的.local，属于验收工具。没有测得测试覆盖率百分比，不能把77通过写成100%覆盖。

下轮优先：后台新增/改密哈希、公开身份授予、MySQL utf8mb4、非法ID、重复POST、跨项目/提交/附件授权、分组并发唯一有效版本、历史字节不覆盖、CSV/ZIP完整性和成员撤销。保留1条完整教学和1条科研多角色浏览器回归；再加入分页查询规模与Firefox。此次未给项目堆砌镜像实现的单元测试。

## 备份/环境边界与证据保留

实际调用upgrade_research --apply --settings=qa_settings；对QA库和QA media先备份验证，再执行无待应用迁移；另恢复到独立QA恢复库。对比27张表，排除操作性session与users.last_login，34个附件校验一致。没有把这次模拟环境恢复等同于真实服务器灾难恢复演练；迁移前备份命令包含SQL，留在忽略.local内，未复制进docs。证据：[restore.json](qa-evidence/2026-10-08/restore.json)、[backup-check.log](qa-evidence/2026-10-08/backup-check.log)。

全新依赖安装在clean-env实际执行，因PyPI TLS EOF失败。状态BLOCKED，不能直接归因为requirements中版本不存在。没有关闭TLS验证或改变当前环境。Docker和Firefox未安装，不为审计擅自更改系统环境。

QA脚本、账号、原始日志和数据库仍保留本机以便复现；浏览器/服务在审计结束停止。可分享证据仅保留虚构数据、摘要和截图，不包含密码、Cookie、CSRF token、SECRET_KEY或完整DEBUG配置。新建的两个QA数据库与.local/qa-20261008为测试资产，未自动删除，以免丢失复现条件。

## 80项审计账本

| # | 检查 | 状态 | 证据/结果 |
| --- | --- | --- | --- |
| 1 | outsider_private_project | PASS | {"status": 403, "path": "/research/3/", "final": "/research/3/", "ms": 22.25, "queries": "8", "server_ms": "18.03", "size": 3385} |
| 2 | outsider_edit_project | PASS | {"status": 403, "path": "/research/3/edit/", "final": "/research/3/edit/", "ms": 46.45, "queries": "8", "server_ms": "21.54", "size": 3385} |
| 3 | member_owner_edit | PASS | {"status": 403, "path": "/research/3/edit/", "final": "/research/3/edit/", "ms": 21.49, "queries": "8", "server_ms": "17.74", "size": 3551} |
| 4 | viewer_commit_denied | PASS | {"status": 403, "path": "/research/3/progress/new/", "final": "/research/3/progress/new/", "ms": 37.28, "queries": "8", "server_ms": "18.32", "size": 3383} |
| 5 | viewer_file_upload_denied | PASS | {"status": 403, "path": "/research/3/files/upload/", "final": "/research/3/files/upload/", "ms": 20.23, "queries": "8", "server_ms": "16.7", "size": 3383} |
| 6 | viewer_task_change_denied | PASS | {"status": 403, "path": "/research/3/tasks/11/", "final": "/research/3/tasks/11/", "ms": 47.55, "queries": "10", "server_ms": "24.11", "size": 3383} |
| 7 | outsider_version_download | PASS | {"status": 403, "path": "/research/3/versions/14/download/", "final": "/research/3/versions/14/download/", "ms": 43.36, "queries": "8", "server_ms": "21.36", "size": 3385} |
| 8 | outsider_course_file | PASS | {"status": 403, "path": "/assignments/submission/download/2/", "final": "/assignments/submission/download/2/", "ms": 44.7, "queries": "9", "server_ms": "19.66", "size": 3369} |
| 9 | outsider_submission_browse | PASS | {"status": 403, "path": "/assignments/submission/2/browse/", "final": "/assignments/submission/2/browse/", "ms": 44.6, "queries": "7", "server_ms": "18.57", "size": 3369} |
| 10 | outsider_submission_diff | PASS | {"status": 403, "path": "/assignments/submission/2/compare/", "final": "/assignments/submission/2/compare/", "ms": 46.59, "queries": "7", "server_ms": "19.71", "size": 3369} |
| 11 | student_grading_denied | PASS | {"status": 403, "path": "/assignments/grade/2/", "final": "/assignments/grade/2/", "ms": 48.09, "queries": "10", "server_ms": "21.79", "size": 3535} |
| 12 | student_group_edit_denied | PASS | {"status": 403, "path": "/assignments/groups/1/", "final": "/assignments/groups/1/", "ms": 24.31, "queries": "8", "server_ms": "20.34", "size": 3535} |
| 13 | student_course_create_denied | PASS | {"status": 403, "path": "/courses/new/", "final": "/courses/new/", "ms": 32.41, "queries": "6", "server_ms": "16.44", "size": 3535} |
| 14 | student_export_denied | PASS | {"status": 403, "path": "/assignments/detail/1/export/grades/", "final": "/assignments/detail/1/export/grades/", "ms": 22.54, "queries": "7", "server_ms": "18.86", "size": 3535} |
| 15 | other_profile_denied | PASS | {"status": 403, "path": "/user_profile/3/", "final": "/user_profile/3/", "ms": 21.39, "queries": "6", "server_ms": "17.34", "size": 3532} |
| 16 | demo_write_denied | PASS | {"status": 403, "path": "/research/1/progress/new/", "final": "/research/1/progress/new/", "ms": 18.27, "queries": "6", "server_ms": "14.88", "size": 3969} |
| 17 | csrf_missing_denied | PASS | {"status": 403, "path": "/research/3/progress/new/", "final": "/research/3/progress/new/", "ms": 18.5, "queries": "0", "server_ms": "4.06", "size": 2508} |
| 18 | invalid_assignment_id | FAIL | {"status": 500, "path": "/assignments/detail/abc/", "final": "/assignments/detail/abc/", "ms": 87.53, "queries": "9", "server_ms": "60.55", "size": 142555} |
| 19 | invalid_submission_id | FAIL | {"status": 500, "path": "/assignments/submission/detail/abc/", "final": "/assignments/submission/detail/abc/", "ms": 73.73, "queries": "9", "server_ms": "55.05", "size": 143077} |
| 20 | nonexistent_project | PASS | {"status": 404, "path": "/research/999999/", "final": "/research/999999/", "ms": 35.0, "queries": "5", "server_ms": "12.77", "size": 1757} |
| 21 | direct_media_denied | PASS | {"status": 404, "path": "/media/experiments/a9b9818f51004d2a9f951f29f6bf00c1/project.zip", "final": "/media/experiments/a9b9818f51004d2a9f951f29f6bf00c1/project.zip", "ms": 9.67, "queries": "0", "server_ms": "5.69", "size": 2945} |
| 22 | path_traversal_preview_denied | PASS | {"status": 404, "path": "/assignments/submission/2/browse/?path=../../settings.py", "final": "/assignments/submission/2/browse/?path=../../settings.py", "ms": 21.18, "queries": "6", "server_ms": "17.47", "size": 1810} |
| 23 | legacy_graphql_disabled | PASS | {"status": 404, "path": "/graphql/", "final": "/graphql/", "ms": 26.03, "queries": "0", "server_ms": "5.73", "size": 2783} |
| 24 | empty_workspace | PASS | {"status": 200, "path": "/research/new/", "final": "/research/new/", "ms": 52.73, "queries": "6", "server_ms": "28.77", "size": 4613} |
| 25 | long_workspace | PASS | {"status": 200, "path": "/research/new/", "final": "/research/new/", "ms": 45.87, "queries": "6", "server_ms": "29.5", "size": 4789} |
| 26 | negative_progress | PASS | {"status": 200, "path": "/research/3/tasks/new/", "final": "/research/3/tasks/new/", "ms": 56.19, "queries": "11", "server_ms": "40.51", "size": 5772} |
| 27 | over_progress | PASS | {"status": 200, "path": "/research/3/tasks/new/", "final": "/research/3/tasks/new/", "ms": 44.94, "queries": "11", "server_ms": "41.1", "size": 5775} |
| 28 | nonnumeric_progress | PASS | {"status": 200, "path": "/research/3/tasks/new/", "final": "/research/3/tasks/new/", "ms": 64.0, "queries": "11", "server_ms": "44.37", "size": 5757} |
| 29 | zero_file | PASS | {"status": 200, "path": "/research/3/files/upload/", "final": "/research/3/files/upload/", "ms": 74.17, "queries": "12", "server_ms": "52.34", "size": 6317} |
| 30 | disallowed_file | PASS | {"status": 200, "path": "/research/3/files/upload/", "final": "/research/3/files/upload/", "ms": 72.21, "queries": "12", "server_ms": "49.83", "size": 6379} |
| 31 | oversize_file | PASS | {"status": 200, "path": "/research/3/files/upload/", "final": "/research/3/files/upload/", "ms": 117.67, "queries": "12", "server_ms": "113.31", "size": 6317} |
| 32 | long_filename | PASS | {"status": 200, "path": "/research/3/files/upload/", "final": "/research/3/files/upload/", "ms": 76.1, "queries": "15", "server_ms": "51.16", "size": 6251} |
| 33 | zip_traversal_rejected | PASS | {"status": 200, "path": "/assignments/submit/1/", "final": "/assignments/submit/1/", "ms": 79.12, "queries": "13", "server_ms": "54.13", "size": 7018} |
| 34 | invalid_rubric_score | PASS | {"status": 200, "path": "/assignments/grade/2/", "final": "/assignments/grade/2/", "ms": 69.16, "queries": "13", "server_ms": "49.61", "size": 6501} |
| 35 | profile_edit_route | NOT_IMPLEMENTED | {"status": 404, "path": "/users/profile/edit/", "final": "/users/profile/edit/", "ms": 11.31, "queries": "0", "server_ms": "6.61", "size": 3238} |
| 36 | password_change_route | NOT_IMPLEMENTED | {"status": 404, "path": "/users/password_change/", "final": "/users/password_change/", "ms": 9.38, "queries": "0", "server_ms": "5.64", "size": 3247} |
| 37 | task_delete_route | NOT_IMPLEMENTED | {"status": 404, "path": "/research/3/tasks/11/delete/", "final": "/research/3/tasks/11/delete/", "ms": 27.55, "queries": "0", "server_ms": "6.66", "size": 6559} |
| 38 | version_restore_route | NOT_IMPLEMENTED | {"status": 404, "path": "/research/3/versions/14/restore/", "final": "/research/3/versions/14/restore/", "ms": 32.13, "queries": "0", "server_ms": "7.5", "size": 6571} |
| 39 | registration_role_gate | FAIL | {"registered_role": 2, "create_course_status": 200} |
| 40 | emoji_input | FAIL | {"status": 500, "path": "/research/3/tasks/new/", "final": "/research/3/tasks/new/", "ms": 102.81, "queries": "11", "server_ms": "80.47", "size": 187550} |
| 41 | 20_tasks_create | PASS | {"created": 20, "distinct": 20} |
| 42 | 20_tasks_update | PASS | {"updated": 20} |
| 43 | stored_xss_escaped | PASS | {"status": 200, "path": "/research/3/tasks/12/", "final": "/research/3/tasks/12/", "ms": 70.95, "queries": "11", "server_ms": "44.18", "size": 5977} |
| 44 | duplicate_post_idempotency | FAIL | {"created": 2} |
| 45 | research_v1_v2_v3_bytes | PASS | {"versions": 3, "payloads": ["category,image_auroc\nbottle,0.982\n", "category,image_auroc\nbottle,0.987\n", "category,image_auroc\nbottle,0.999\n"]} |
| 46 | research_version_author_time | PASS | {"author_ids": [2, 2, 2]} |
| 47 | individual_submit_bytes | PASS | {"status": 200, "path": "/assignments/submit/2/", "final": "/assignments/submission/detail/3/", "ms": 62.57, "queries": "16", "server_ms": "29.17", "size": 5002} |
| 48 | withdraw_preserves_history | PASS | {"status": 200, "path": "/assignments/submission/delete/3/", "final": "/assignments/detail/2/", "ms": 73.09, "queries": "11", "server_ms": "31.18", "size": 4041} |
| 49 | repeated_withdraw_safe | PASS | {"status": 403, "path": "/assignments/submission/delete/3/", "final": "/assignments/submission/delete/3/", "ms": 36.26, "queries": "12", "server_ms": "22.8", "size": 3526} |
| 50 | resubmit_after_withdraw | PASS | {"status": 200, "path": "/assignments/submit/2/", "final": "/assignments/submission/detail/4/", "ms": 109.65, "queries": "16", "server_ms": "36.51", "size": 5115} |
| 51 | resource_upload_download_content | PASS | {"status": 200, "path": "/resources/download/16/", "final": "/resources/download/16/", "ms": 25.24, "queries": "7", "server_ms": "21.15", "size": 12} |
| 52 | resource_unauthorized_denied | PASS | {"status": 403, "path": "/resources/download/16/", "final": "/resources/download/16/", "ms": 39.66, "queries": "9", "server_ms": "20.54", "size": 3357} |
| 53 | resource_unauthorized_delete | PASS | {"status": 403, "path": "/resources/delete/16/", "final": "/resources/delete/16/", "ms": 45.62, "queries": "8", "server_ms": "20.17", "size": 3535} |
| 54 | resource_delete_db_disk | PASS | {"status": 200, "path": "/resources/delete/16/", "final": "/courses/detail/1/", "ms": 68.73, "queries": "11", "server_ms": "26.86", "size": 5502} |
| 55 | repeated_delete_safe | PASS | {"status": 404, "path": "/resources/delete/16/", "final": "/resources/delete/16/", "ms": 30.06, "queries": "5", "server_ms": "13.06", "size": 1761} |
| 56 | password_hash | PASS | {"algorithm": "pbkdf2_sha256"} |
| 57 | cors_no_wildcard | PASS | {"acao": null} |
| 58 | private_preview_headers | PASS | {"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"} |
| 59 | archived_project_write_denied | PASS | {"status": 403, "path": "/research/3/progress/new/", "final": "/research/3/progress/new/", "ms": 33.51, "queries": "8", "server_ms": "20.1", "size": 3560} |
| 60 | project_restore_read | PASS | {"status": 200, "path": "/research/3/", "final": "/research/3/", "ms": 76.29, "queries": "19", "server_ms": "53.2", "size": 8169} |
| 61 | existing_77_tests | PASS | 77 PASS / 0 FAIL / 0 SKIP；tests.log |
| 62 | migrations_mysql | PASS | 新MySQL全迁移成功；无漂移 |
| 63 | existing_environment | PASS | Python3.8.20/Django3.1.3/MySQL8.0.46，pip check通过 |
| 64 | clean_install | BLOCKED | 新venv pip安装PyPI TLS EOF |
| 65 | research_ui_flow | PASS | browser-report.json；多人协作/历史字节 |
| 66 | lab_ui_flow | PASS | lab-browser-report.json；材料/代码/评分/导出 |
| 67 | guest_ui_flow | PASS | guest-browser-report.json；六栏目/下载 |
| 68 | new_user_ui_flow | PASS | chrome-layout.json；注册/保存/刷新/重登 |
| 69 | course_ui_flow | PASS | Chrome创建/编辑/加入/退出 |
| 70 | admin_password_workflow | FAIL | 管理员改密原样存储；BUG-001 |
| 71 | five_viewports | PARTIAL | 正常页面310测量无整页溢出；错误页溢出及手机diff体验 |
| 72 | chrome_edge_actual | PASS | 双浏览器实际运行；PDF等待4秒确认内容 |
| 73 | firefox | BLOCKED | NOT_TESTED；无可运行Firefox |
| 74 | production_readiness | FAIL | 5条check --deploy警告及配置不一致 |
| 75 | tracked_sensitive_config | FAIL | 固定密钥和compose示例凭据入Git；不复制值 |
| 76 | query_growth_pagination | FAIL | 9→29查询；32历史全部渲染 |
| 77 | ux_feedback | PARTIAL | 正常反馈可用；重复标题/断网无草稿/无忙碌状态 |
| 78 | backup_restore | PASS | 独立库恢复27表34附件一致，排除session/last_login |
| 79 | continuous_file_ops | PASS | 10文件字节/SHA一致，20次页面请求全200 |
| 80 | concurrent_effective_slot | PASS | 2组员并发追加2版，current_slot=1仅1条 |
