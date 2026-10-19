# BUG Backlog

审计日期：2026-10-08。仅审计，未修复业务代码。P0 是上线阻断/账号数据安全问题；没有把“未发现越权”写成“无安全风险”。

| 编号 | 严重度 | 问题 |
| --- | --- | --- |
| [BUG-001](#bug-001) | P0 | 管理员修改密码会原样存储输入并使账号无法登录 |
| [BUG-002](#bug-002) | P0 | 当前生产配置会暴露调试信息且复用已入 Git 的密钥 |
| [BUG-003](#bug-003) | P1 | MySQL 输入 emoji 返回 500 |
| [BUG-004](#bug-004) | P1 | 多个旧路由接受非数字主键并返回 500 |
| [BUG-005](#bug-005) | P1 | 公开注册可直接取得教师身份 |
| [BUG-006](#bug-006) | P1 | 相同创建请求会产生重复任务 |
| [BUG-007](#bug-007) | P1 | 普通用户没有修改密码或找回密码的完整流程 |
| [BUG-008](#bug-008) | P1 | 运行栈已停止安全维护 |
| [BUG-009](#bug-009) | P1 | Docker 配置不能视为可部署成品 |
| [BUG-010](#bug-010) | P2 | 全站“我的课程”侧栏存在 N+1 查询 |
| [BUG-011](#bug-011) | P2 | 实验历史版本无分页，工作台分页也未限制历史读取 |
| [BUG-012](#bug-012) | P2 | 个人资料只能查看，不能自助修改 |
| [BUG-013](#bug-013) | P2 | 科研不同页面和表单共用项目标题，浏览器标签难区分 |
| [BUG-014](#bug-014) | P2 | 提交中/断网反馈及草稿恢复不完整 |
| [BUG-015](#bug-015) | P2 | 移动端代码对比需要横向拖动但缺少明显提示 |
| [BUG-016](#bug-016) | P2 | 科研成员可添加/改角色，但缺少移除或撤销访问入口 |
| [BUG-017](#bug-017) | P3 | 任务/项目删除和旧版本恢复未提供，须明确产品语义 |
| [BUG-018](#bug-018) | P3 | 科研文件没有内容 diff，当前代码评审仅覆盖教学实验 |
| [BUG-019](#bug-019) | P3 | 浏览器自动请求 favicon.ico 返回 404 |

## BUG-001

标题：管理员修改密码会原样存储输入并使账号无法登录

严重度：P0

模块：用户/管理后台

复现步骤：用管理员登录 /admin/；打开一个仅供测试的用户；在 password 文本框输入新密码并保存；尝试用新密码登录。

预期结果：密码应通过 set_password 生成哈希，新密码应可登录。

实际结果：HTTP 保存成功；数据库 password 与输入完全相同，check_password=False。仅牺牲 QA 账号被测试，随后已重新设回哈希。

原因：users/admin.py:5 使用普通 ModelAdmin，而非适配自定义 User 的 UserAdmin。

建议修复：使用 UserAdmin、专用创建/改密表单和密码哈希只读组件；普通编辑禁止直接写 password；对已受影响账号执行受控重置。

预计修改范围：users/admin.py、用户管理表单；管理员改密和新增账号回归。

证据：[admin-login.json](qa-evidence/2026-10-08/admin-login.json)；条目 `admin_password_reset_hash、admin_reset_actual_login`。

## BUG-002

标题：当前生产配置会暴露调试信息且复用已入 Git 的密钥

严重度：P0

模块：部署/配置

复现步骤：运行 manage.py check --deploy；请求 /assignments/detail/abc/；检查 git ls-files django_lms/settings.py。

预期结果：生产关闭 DEBUG，使用独立环境密钥、明确域名和安全 Cookie/HTTPS 配置。

实际结果：DEBUG=True；已跟踪文件内有固定 SECRET_KEY；错误页显示 traceback；部署检查有 W004/W008/W012/W016/W018。未发现实际线上泄露事件。

原因：django_lms/settings.py:26、29、31、95，开发设置直接作为默认设置。

建议修复：拆分开发/生产设置；生成新服务器密钥并通过环境注入；配置域名、HTTPS、Cookie；安排静态文件和错误页。不要在报告中复制旧密钥。

预计修改范围：django_lms/settings.py、服务器启动/反向代理/静态资源配置。

证据：[deploy-check.log](qa-evidence/2026-10-08/deploy-check.log)；条目 `部署检查与错误页实测`。

## BUG-003

标题：MySQL 输入 emoji 返回 500

严重度：P1

模块：数据库/中文输入

复现步骤：按 README 创建 utf8mb4 数据库并迁移；负责人在科研任务标题输入“QA emoji 🚀”后保存。

预期结果：正常保存四字节 Unicode，或给出可理解的表单提示。

实际结果：HTTP 500，OperationalError 1366；表为 utf8mb4_0900_ai_ci，但连接 character_set_client/connection/results 为 utf8mb3。

原因：django_lms/settings.py:95 数据库 OPTIONS 未指定 utf8mb4；当前 mysqlclient 连接默认值与数据库不一致。

建议修复：显式设置连接 charset=utf8mb4，核对现有表/列编码；为标题、说明、评论和文件名增加真实 MySQL 回归。

预计修改范围：数据库连接配置、必要的数据编码迁移与 MySQL 验证。

证据：[extra.json](qa-evidence/2026-10-08/extra.json)；条目 `mysql_charset_alignment；probe.json:emoji_input`。

## BUG-004

标题：多个旧路由接受非数字主键并返回 500

严重度：P1

模块：作业/提交/错误处理

复现步骤：登录后访问 /assignments/detail/abc/ 和 /assignments/submission/detail/abc/。

预期结果：非法主键返回 404；错误页可正常使用。

实际结果：两个请求均 500；ValueError；手机调试页有横向溢出。

原因：assignments/urls.py:20–26 的 [-\w]+ 接受字母，而模型主键为整数。

建议修复：改用整数转换器或数字正则；其余 update/delete/grade 等同类路由一并验证；使用友好 404/500。

预计修改范围：assignments/urls.py、错误模板和非法 ID 回归。

证据：[probe.json](qa-evidence/2026-10-08/probe.json)；条目 `invalid_assignment_id、invalid_submission_id`。

## BUG-005

标题：公开注册可直接取得教师身份

严重度：P1

模块：身份/权限

复现步骤：匿名注册选择“教师”，登录后进入 /courses/new/。

预期结果：正式教学平台的教师身份应由管理员确认或受控邀请授予。

实际结果：新账号 user_type=2，创建课程页面 200；无需审批。这不会自动赋予他人课程或科研项目权限。

原因：users/forms.py:9、20–21 将 user_type 暴露给公开注册表单，后端无审批状态。

建议修复：公开注册默认学生；教师由管理员或邀请机制授予；已有教师账号先核验。

预计修改范围：users/forms.py、users/views.py、身份管理和注册回归。

证据：[probe.json](qa-evidence/2026-10-08/probe.json)；条目 `registration_role_gate`。

## BUG-006

标题：相同创建请求会产生重复任务

严重度：P1

模块：科研任务/重复提交

复现步骤：负责人向同一 tasks/new/ 连续提交两次完全相同的合法表单，模拟双击或重试。

预期结果：一次提交意图只形成一个任务，重试给出已有结果或明确提醒。

实际结果：两次请求均成功，数据库新增两条同名任务，动态也重复。

原因：research/views.py:162–175 无请求幂等键；页面提交按钮未进入忙碌状态。

建议修复：加服务端幂等令牌及提交后跳转，前端忙碌反馈/防连点；合法的同名任务仍可显式新建。

预计修改范围：科研创建 handler、公共表单脚本和重复提交回归。

证据：[probe.json](qa-evidence/2026-10-08/probe.json)；条目 `duplicate_post_idempotency`。

## BUG-007

标题：普通用户没有修改密码或找回密码的完整流程

严重度：P1

模块：账号生命周期

复现步骤：普通用户查看个人页及账号导航；访问 /users/password_change/。

预期结果：已登录用户可安全改密；忘记密码有受控恢复方法。

实际结果：普通用户端无入口、无路由；请求 404。管理员当前改密又受 BUG-001 影响。

原因：users/urls.py 只有 login/logout/signup；个人页是只读 ListView。

建议修复：优先实现已登录改密与管理员安全重置；邮件找回须先确定真实邮件配置，再启用。

预计修改范围：users 路由、表单、模板和账号安全测试。

证据：[probe.json](qa-evidence/2026-10-08/probe.json)；条目 `password_change_route`。

## BUG-008

标题：运行栈已停止安全维护

严重度：P1

模块：依赖/长期部署

复现步骤：检查实际版本 Python 3.8.20、Django 3.1.3 和 requirements.txt；核对官方支持状态。

预期结果：服务器使用仍受安全维护的 Python/Django 组合。

实际结果：现有环境能运行，但 Python 3.8 和 Django 3.1 已不受支持。本轮没有做完整 CVE 扫描，也没有证明可被利用。

原因：requirements.txt 固定旧框架及相关依赖；DockerFile 也使用 python:3.8。

建议修复：制定受支持版本升级分支；先解决兼容依赖、迁移和授权回归，再切换生产环境。

预计修改范围：运行时、requirements、URL/JSON/表单兼容和 CI；升级量较大。

证据：[tests.log](qa-evidence/2026-10-08/tests.log)；条目 `实际版本；官方支持表见报告`。

## BUG-009

标题：Docker 配置不能视为可部署成品

严重度：P1

模块：容器/部署

复现步骤：对比 docker-compose.yml、DockerFile、settings.py；当前机器没有 docker 命令，容器实跑为 NOT_TESTED。

预期结果：容器 DB 主机、库名、密码、构建依赖与启动命令应一致，提供健康检查和生产服务。

实际结果：compose 使用 db/mydatabase，应用固定 localhost/django_lms；web 未传 MYSQL_PASSWORD；DockerFile 未显式管理 MySQL 构建依赖（基础镜像是否自带需实测）；仍以 runserver 启动。

原因：docker-compose.yml 和 DockerFile 没有与目前 MySQL 配置同步。这里是静态确定的配置不一致，不是假称构建失败。

建议修复：统一环境配置、数据库网络名和库名；完善构建依赖、健康检查、迁移、持久化与生产 WSGI；在有 Docker 环境实际重建。

预计修改范围：DockerFile、compose、生产设置/启动脚本和容器验证。

证据：[deploy-check.log](qa-evidence/2026-10-08/deploy-check.log)；条目 `静态配置审查；Docker运行 NOT_TESTED`。

## BUG-010

标题：全站“我的课程”侧栏存在 N+1 查询

严重度：P2

模块：全站性能

复现步骤：以 QA 学生请求 /research/ 三次；增加 20 门属于其他账号的课程；再请求三次。

预期结果：无关课程增加不应使每个页面多执行一条查询/课程。

实际结果：请求查询数从 9 升到 29；平均实测耗时从约 44 ms 升到约 69 ms。

原因：courses/context_processors.py:3 查询全部课程；templates/base.html:52–58 对每门 course.students.all 做成员判断。

建议修复：在 context processor 直接按当前用户过滤课程，避免模板逐个查询与重复成员加载。

预计修改范围：context processor、公共模板和查询增长回归。

证据：[extra.json](qa-evidence/2026-10-08/extra.json)；条目 `navigation_query_scaling`。

## BUG-011

标题：实验历史版本无分页，工作台分页也未限制历史读取

严重度：P2

模块：教学性能/历史列表

复现步骤：QA 个人实验连续追加至 32 个版本；教师访问 /assignments/detail/2/ 与 ?page=2。

预期结果：每页返回有限的历史版本；分页应影响实际查询和输出。

实际结果：两次页面都渲染 32 个 attachment-card；实验历史区无分页。工作台虽每页25行，但有效提交/名册先全部装入内存。

原因：assignments/views.py:160–180；assignments/experiments.py:206–235；experiment_detail.html 历史循环。

建议修复：历史独立分页；工作台先数据库筛选分页再加载附件、成员；避免重复统计列表。

预计修改范围：实验详情、工作台查询、模板与数据规模验证。

证据：[concurrency.json](qa-evidence/2026-10-08/concurrency.json)；条目 `assignment_history_pagination`。

## BUG-012

标题：个人资料只能查看，不能自助修改

严重度：P2

模块：个人页

复现步骤：注册后进入个人页，查找姓名/邮箱编辑；访问 /users/profile/edit/。

预期结果：用户可修改允许的资料，保存后刷新仍保持。

实际结果：个人页只有汇总和历史；无编辑入口/路由，404。不是已经存在但失效的按钮。

原因：django_lms/views.py:17 UserProfile 为只读 ListView；users/urls.py 无编辑视图。

建议修复：增加受权限保护的个人资料表单，禁止修改角色、staff 等管理字段。

预计修改范围：users、个人页模板和自助资料回归。

证据：[probe.json](qa-evidence/2026-10-08/probe.json)；条目 `profile_edit_route`。

## BUG-013

标题：科研不同页面和表单共用项目标题，浏览器标签难区分

严重度：P2

模块：UI/导航

复现步骤：依次打开同一项目的任务、文件、成员、创建任务和提交进度；观察浏览器标签标题。

预期结果：标题包含具体页面或操作，例如“提交进度 · 项目名”。

实际结果：多种页面全部显示“项目名 · 科研项目”；新项目页也仅“科研协作 · 科研项目”。

原因：research/templates/research/base.html:2 统一 title，子模板没有覆写。

建议修复：各子页提供具体动作/栏目标题，保留项目名作为上下文。

预计修改范围：科研模板 title block；视觉无需整体重做。

证据：[chrome-layout.json](qa-evidence/2026-10-08/chrome-layout.json)；条目 `measures[].title`。

## BUG-014

标题：提交中/断网反馈及草稿恢复不完整

严重度：P2

模块：表单/稳定性体验

复现步骤：填写科研进度；浏览器模拟断网；提交；恢复网络并重新进入表单；另观察正常提交按钮。

预期结果：用户清楚知道是否保存成功，并能方便恢复未提交内容；提交中有明确忙碌状态。

实际结果：断网进入浏览器 ERR_INTERNET_DISCONNECTED 页面；重新进入表单不会恢复草稿。表单无忙碌状态；校验失败时文件需重选（页面已有提示）。未声称浏览器后退一定丢失内容。

原因：SSR 原生提交无草稿/网络失败兜底和通用忙碌脚本；research/form.html:5、8。

建议修复：先防连点并明确成功/失败；为长文本引入本地草稿或离开提醒，上传失败说明重选原因。

预计修改范围：公共表单交互与科研提交模板；可分阶段实现。

证据：[chrome-extra.json](qa-evidence/2026-10-08/chrome-extra.json)；条目 `offline_submit、empty_form_feedback`。

## BUG-015

标题：移动端代码对比需要横向拖动但缺少明显提示

严重度：P2

模块：代码评审/移动端

复现步骤：390×844 打开 src/Main.java 的对比页面。

预期结果：用户能立即理解右侧新版代码位于可横向滚动区域。

实际结果：整页没有溢出；对比表内部横向滚动，首屏仅看到左侧旧版和部分行内容，没有“左右滑动”提示。功能可用，体验为 PARTIAL。

原因：experiments.css 的 diff 表最小宽度及容器滚动；compare.html 未提示手势。

建议修复：增加明确的横向滑动提示或移动端逐行统一 diff 切换，不取消必要的代码滚动。

预计修改范围：compare.html 和局部响应式样式。

证据：[chrome-diff-390.png](qa-evidence/2026-10-08/chrome-diff-390.png)；条目 `手机截图`。

## BUG-016

标题：科研成员可添加/改角色，但缺少移除或撤销访问入口

严重度：P2

模块：成员生命周期

复现步骤：负责人打开成员页，添加成员后查找移除/禁用/转交操作；检查 research/urls.py。

预期结果：当成员离组时可撤销项目读取权限，历史作者记录仍保留。

实际结果：只能 update_or_create 成员角色；最低角色 viewer 仍能下载；无移除路由。未尝试通过删除历史作者解决。

原因：research/views.py:111–147 的 members 只保存角色；路由没有撤销操作。

建议修复：建立不删除作者历史的成员撤销机制，撤销后直接 URL/下载应403；负责人转交另行设计。

预计修改范围：WorkspaceMember 状态/权限、成员页、历史回归。

证据：[browser-report.json](qa-evidence/2026-10-08/browser-report.json)；条目 `成员页实际操作和路由审查`。

## BUG-017

标题：任务/项目删除和旧版本恢复未提供，须明确产品语义

严重度：P3

模块：范围/历史策略

复现步骤：查找任务删除和版本恢复入口；请求 tasks/<id>/delete/、versions/<id>/restore/；查看科研文件历史页。

预期结果：界面和说明明确保留历史、归档与恢复旧内容的区别，后续按需要增加操作。

实际结果：删除任务/项目、删除科研历史文件、恢复旧内容为当前版没有实现；项目归档/恢复本身可用，历史下载也可用。

原因：科研采用追加和 PROTECT 保留历史；未提供删除/回滚路由。这是范围缺口，不是假按钮。

建议修复：先补任务取消/归档和项目访问撤销；若需恢复旧文件，用“复制旧内容为新版本”，不要覆盖历史。

预计修改范围：产品规则、科研模型/路由/模板；属于后续功能。

证据：[probe.json](qa-evidence/2026-10-08/probe.json)；条目 `task_delete_route、version_restore_route`。

## BUG-018

标题：科研文件没有内容 diff，当前代码评审仅覆盖教学实验

严重度：P3

模块：版本管理范围

复现步骤：浏览科研文件 v1/v2/v3 历史页，对照教学实验 compare 页面。

预期结果：对外说明应区分“可追溯文件版本”和“可逐行比较源码”。

实际结果：科研历史下载内容准确，拥有作者/时间/校验值，但科研文件页没有 diff；教学实验才有逐行差异。Git 分支/合并/仓库同步/行级批注均未实现。

原因：research/urls.py 仅 version_download；逐行比较在 assignments/experiments.py。

建议修复：保留当前真实描述；若研究协作需要代码评审，再复用安全文本 diff，而不宣称完整 GitHub。

预计修改范围：后续需求及科研文件页；不影响已验证下载链路。

证据：[chrome-v3-file.png](qa-evidence/2026-10-08/chrome-v3-file.png)；条目 `科研历史UI；教学diff截图`。

## BUG-019

标题：浏览器自动请求 favicon.ico 返回 404

严重度：P3

模块：静态资源/控制台

复现步骤：打开平台并查看 Network；Chrome/Edge 额外请求 /favicon.ico。

预期结果：图标请求正常返回或只使用已指定 SVG。

实际结果：页面 SVG 图标正常，自动请求 /favicon.ico 返回404；未出现业务 JS 未捕获异常。

原因：只提供模板 SVG favicon，没有根路径 ico。

建议修复：按需要提供兼容 favicon 或根路径映射；优先级低。

预计修改范围：静态资源与图标路由。

证据：[chrome-layout.json](qa-evidence/2026-10-08/chrome-layout.json)；条目 `errors: favicon.ico`。
