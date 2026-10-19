"""可重复执行的教学演示数据。

设计原则：
- 只使用现有模型与字段，不产生 migration；
- 只创建带明确标识的演示数据（demo_ 前缀账号 + 简介里注明"示例课程"）；
- 已存在的记录一律跳过或只刷新演示作业的时间，不删除、不覆盖真实数据；
- 重复执行不会成倍增加数据，只会输出 already exists。
"""
import hashlib
import io
import os
import zipfile
from datetime import timedelta

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from assignments.models import (
    Assignment,
    CourseGroup,
    GroupMember,
    SubmissionAttachment,
    SubmitAssignment,
)
from courses.models import Course, Enrollment
from research.models import ProgressCommit, ResearchTask, ResearchWorkspace, WorkspaceMember
from research.services import save_artifacts
from resources.models import Resource
from users.models import User

DEMO_TEACHERS = {
    'chen': ('demo_teacher_chen', '陈', '志远'),
    'li': ('demo_teacher_li', '李', '文清'),
}
DEMO_STUDENTS = {
    'zhang': ('demo_student_zhang', '张', '晨'),
    'lin': ('demo_student_lin', '林', '晓'),
    'wang': ('demo_student_wang', '王', '宇'),
    'zhou': ('demo_student_zhou', '周', '宁'),
    'sun': ('demo_student_sun', '孙', '悦'),
}

RUBRIC_A = [
    {'title': '功能实现', 'points': 40},
    {'title': '代码质量与结构', 'points': 30},
    {'title': '报告与说明完整性', 'points': 30},
]
RUBRIC_B = [
    {'title': '实验过程与结果', 'points': 50},
    {'title': '分析与结论', 'points': 30},
    {'title': '报告规范', 'points': 20},
]

COURSES = [
    {
        'name': 'Python 程序设计', 'teacher': 'chen',
        'desc': '面向零基础的程序设计入门课程，从语法、函数到面向对象，配合小型项目完成实践。用于平台功能展示的示例课程。',
        'students': ['zhang', 'lin', 'wang', 'zhou', 'sun'],
    },
    {
        'name': 'Web 应用开发', 'teacher': 'chen',
        'desc': '以 Django 为技术栈，从页面结构到数据模型，完成可运行的教学管理系统。用于平台功能展示的示例课程。',
        'students': ['zhang', 'lin', 'wang', 'zhou'],
    },
    {
        'name': '数据库原理与应用', 'teacher': 'li',
        'desc': '关系模型、SQL 查询、索引与事务，配合实验环境完成从建表到查询优化的训练。用于平台功能展示的示例课程。',
        'students': ['lin', 'wang', 'sun'],
    },
    {
        'name': '数据结构与算法', 'teacher': 'chen',
        'desc': '线性表、树与图，以及排序、最短路等经典算法，强调复杂度分析与动手实现。用于平台功能展示的示例课程。',
        'students': ['zhang', 'zhou', 'sun'],
    },
    {
        'name': '软件工程实践', 'teacher': 'li',
        'desc': '以小组为单位完成需求分析、设计、开发与答辩，训练工程协作与文档能力。用于平台功能展示的示例课程。',
        'students': ['zhang', 'lin', 'wang'],
    },
    {
        'name': '人工智能导论', 'teacher': 'li',
        'desc': '机器学习基本概念与典型应用，包含图像分类入门实验与课程案例分析。用于平台功能展示的示例课程。',
        'students': ['zhang', 'lin', 'zhou', 'sun'],
    },
    {
        'name': '计算机视觉基础', 'teacher': 'li',
        'desc': '图像处理基础、边缘与特征提取、目标检测入门。用于平台功能展示的示例课程。',
        'students': ['wang', 'sun'],
    },
    {
        'name': '科研方法与学术写作', 'teacher': 'chen', 'archived': True,
        'desc': '文献检索、实验设计与论文写作规范；本学期课程已结束，保留全部历史资料。用于平台功能展示的示例课程。',
        'students': [],
    },
]

ASSIGNMENTS = [
    ('Python 程序设计', '基础语法与控制结构', '完成 5 道基础语法练习，并提交可运行的源码与实验报告。', -30, -14, 'individual', ['code', 'report'], RUBRIC_A),
    ('Python 程序设计', '函数与模块设计', '将上一阶段的脚本拆分为函数与模块，补充必要的参数校验。', -7, 5, 'individual', ['code'], RUBRIC_A),
    ('Python 程序设计', '面向对象编程实践', '设计一个包含继承与多态的示例程序，并说明类之间的关系。', 3, 14, 'individual', ['code', 'report'], RUBRIC_A),
    ('Web 应用开发', '个人主页设计', '使用 HTML/CSS 完成个人主页，要求结构清晰并适配移动端。', -20, -6, 'individual', ['code', 'screenshots'], RUBRIC_A),
    ('Web 应用开发', 'Django 数据模型实践', '为课程管理系统设计数据模型，并完成迁移与后台管理页面。', -4, 3, 'individual', ['code', 'report'], RUBRIC_A),
    ('Web 应用开发', '课程项目：教学管理系统', '小组完成需求、设计与实现，提交可运行项目与项目说明书。', -10, 20, 'individual', ['code', 'report'], RUBRIC_A),
    ('数据库原理与应用', 'SQL 查询实验', '基于给定的选课库完成 10 条查询，并解释执行计划。', -18, -5, 'individual', ['report'], RUBRIC_B),
    ('数据库原理与应用', '索引与事务分析', '对比建立索引前后的执行计划，验证事务隔离级别的影响。', -3, 7, 'individual', ['report', 'code'], RUBRIC_B),
    ('数据结构与算法', '实验一：线性表', '实现顺序表与链表，并比较两者在插入、删除上的性能。', -25, -12, 'individual', ['code', 'report'], RUBRIC_B),
    ('数据结构与算法', '实验二：二叉树遍历', '实现二叉树的前中后序与层序遍历，并输出遍历结果。', -8, 2, 'individual', ['code', 'report'], RUBRIC_B),
    ('数据结构与算法', '实验三：最短路径算法', '实现 Dijkstra 算法，并在给定图上验证结果。', -2, 9, 'individual', ['code'], RUBRIC_B),
    ('人工智能导论', '实验：图像分类入门', '使用现成模型完成小样本图像分类，记录准确率与失败案例。', -6, 6, 'individual', ['code', 'report'], RUBRIC_B),
    ('人工智能导论', '课程报告：AI 应用案例分析', '选择一个真实应用场景，分析其技术路线与局限。', -12, 16, 'individual', ['report'], RUBRIC_B),
    ('软件工程实践', '小组项目：需求与原型', '小组完成需求规格说明与可交互原型，并提交阶段总结。', -9, 4, 'group', ['code', 'report'], RUBRIC_A),
    ('计算机视觉基础', '实验：边缘检测与特征提取', '实现 Sobel 与 Canny 边缘检测，比较不同阈值下的效果。', -5, 8, 'individual', ['code', 'report'], RUBRIC_B),
]

RESOURCES = [
    ('Python 程序设计', 'Python 基础语法讲义', 'md', 'python-basics.md'),
    ('Python 程序设计', 'Python 面向对象编程示例', 'zip', 'python-oop-samples.zip'),
    ('Python 程序设计', '课程项目说明书', 'md', 'python-project-guide.md'),
    ('Web 应用开发', 'Django 入门课件', 'md', 'django-intro.md'),
    ('Web 应用开发', 'Git 使用指南', 'md', 'git-guide.md'),
    ('数据库原理与应用', '数据库 SQL 实验指导', 'md', 'sql-lab-guide.md'),
    ('数据库原理与应用', '选课库表结构示例', 'csv', 'course-schema.csv'),
    ('数据结构与算法', '数据结构课程课件', 'md', 'data-structure-slides.md'),
    ('数据结构与算法', '算法复杂度速查表', 'md', 'complexity-cheatsheet.md'),
    ('软件工程实践', '软件工程需求分析模板', 'md', 'requirement-template.md'),
    ('软件工程实践', '实验报告模板', 'md', 'report-template.md'),
    ('人工智能导论', '人工智能导论课件', 'md', 'ai-intro.md'),
    ('人工智能导论', '图像分类实验数据说明', 'csv', 'image-dataset.csv'),
    ('计算机视觉基础', '计算机视觉入门资料', 'md', 'cv-getting-started.md'),
    ('科研方法与学术写作', '科研论文阅读方法', 'md', 'paper-reading.md'),
    ('科研方法与学术写作', '学术写作规范', 'md', 'writing-guide.md'),
]

RESEARCH_PROJECTS = [
    {
        'name': '工业表面异常检测研究', 'owner': 'chen', 'status': 'active',
        'desc': '面向工业质检场景，研究小样本条件下的表面缺陷检测方法。用于平台功能展示的示例科研项目。',
        'members': [('zhang', 'member'), ('wang', 'member'), ('lin', 'viewer')],
        'tasks': [
            ('阅读 PatchCore 相关论文', '整理方法要点与可复现实验设置。', 'zhang', 100),
            ('整理缺陷数据集', '完成数据清洗与类别统计。', 'wang', 70),
            ('实现基线模型', '在公开数据上复现基线结果。', 'zhang', 40),
            ('撰写阶段总结', '汇总当前指标与问题。', 'wang', 0),
        ],
        'commits': [
            ('完成数据清洗与类别统计', '清洗后保留 12 类缺陷，训练/验证按 8:2 划分。', 'zhang', 'dataset-summary.md',
             '# 数据集概况\n\n- 图像总数：2,480\n- 缺陷类别：12\n- 训练/验证：8:2\n'),
            ('复现基线模型', 'PatchCore 基线在验证集达到 0.86 AUROC，下一步尝试光照增强。', 'wang', 'baseline-result.md',
             '# 基线结果\n\n| 指标 | 数值 |\n| --- | --- |\n| AUROC | 0.86 |\n| F1 | 0.79 |\n'),
        ],
        'comments': [
            ('zhang', '数据划分建议固定随机种子，便于复现。'),
            ('chen', '补一组低照度样本，作为下一阶段对照。'),
        ],
    },
    {
        'name': '校园智能问答助手', 'owner': 'chen', 'status': 'active',
        'desc': '围绕教务、课程与校园服务构建可检索的问答助手，重点关注答案可追溯性。用于平台功能展示的示例科研项目。',
        'members': [('lin', 'member'), ('zhou', 'member')],
        'tasks': [
            ('梳理常见问题清单', '从教务通知与咨询记录中整理高频问题。', 'lin', 100),
            ('构建检索语料', '整理课程与制度文档，完成分段与标注。', 'zhou', 60),
            ('实现检索与回答', '先完成检索式基线，再评估生成质量。', 'lin', 30),
        ],
        'commits': [
            ('完成问题清单与分类', '共整理 86 个高频问题，分为教务、课程、生活服务三类。', 'lin', 'faq-list.md',
             '# 常见问题分类\n\n1. 教务（32）\n2. 课程（28）\n3. 生活服务（26）\n'),
        ],
        'comments': [
            ('zhou', '语料里制度文档版本较多，建议统一到最新版。'),
        ],
    },
    {
        'name': '基于视觉的目标检测实验', 'owner': 'li', 'status': 'active',
        'desc': '比较不同检测框架在校园场景数据上的精度与速度，形成可复用的实验记录。用于平台功能展示的示例科研项目。',
        'members': [('wang', 'member'), ('sun', 'member')],
        'tasks': [
            ('标注校园场景数据', '完成 500 张图像的目标框标注。', 'wang', 80),
            ('训练检测模型', '完成两阶段与单阶段方法对比。', 'sun', 45),
            ('整理评测报告', '汇总 mAP 与推理耗时。', 'wang', 0),
        ],
        'commits': [
            ('完成第一批数据标注', '已标注 500 张，覆盖 6 类目标。', 'wang', 'annotation-log.md',
             '# 标注进度\n\n- 已完成：500 张\n- 类别：行人、车辆、路障、指示牌、自行车、其他\n'),
        ],
        'comments': [
            ('sun', '夜间样本偏少，建议补采。'),
        ],
    },
    {
        'name': '学习行为数据分析', 'owner': 'li', 'status': 'active',
        'desc': '基于平台学习行为数据，分析作业提交与成绩之间的关系，为教学改进提供依据。用于平台功能展示的示例科研项目。',
        'members': [('zhang', 'member'), ('zhou', 'member')],
        'tasks': [
            ('确定分析指标', '梳理提交及时率、修改次数等指标。', 'zhang', 100),
            ('清洗行为数据', '处理缺失值与异常值。', 'zhou', 55),
            ('撰写分析报告', '输出初步结论与可视化。', 'zhang', 20),
        ],
        'commits': [
            ('确定分析指标与口径', '确定 6 项指标，并明确统计周期。', 'zhang', 'metrics.md',
             '# 指标定义\n\n- 提交及时率\n- 首次提交提前量\n- 版本追加次数\n- 评分变化幅度\n'),
        ],
        'comments': [
            ('li', '注意区分个人实验与小组实验，避免口径混淆。'),
        ],
    },
    {
        'name': '课程知识图谱构建', 'owner': 'chen', 'status': 'paused',
        'desc': '抽取课程知识点与先修关系，构建可查询的课程知识图谱。用于平台功能展示的示例科研项目。',
        'members': [('lin', 'member'), ('sun', 'viewer')],
        'tasks': [
            ('抽取知识点', '从课程大纲中抽取知识点条目。', 'lin', 100),
            ('构建先修关系', '标注知识点之间的依赖。', 'lin', 50),
            ('设计查询接口', '支持按课程与知识点检索。', 'lin', 0),
        ],
        'commits': [
            ('完成知识点抽取', '三门课程共抽取 214 个知识点。', 'lin', 'knowledge-points.md',
             '# 知识点抽取\n\n| 课程 | 知识点 |\n| --- | --- |\n| Python 程序设计 | 86 |\n| 数据结构与算法 | 74 |\n| 数据库原理与应用 | 54 |\n'),
        ],
        'comments': [
            ('chen', '项目暂缓，等下学期课程大纲更新后继续。'),
        ],
    },
]

SUBMISSIONS = [
    # course, assignment, student, graded, grade, feedback, version, extra
    ('Python 程序设计', '基础语法与控制结构', 'zhang', True, 92, '整体完成较好，代码结构清晰，边界条件处理到位。', 1, 'full'),
    ('Python 程序设计', '基础语法与控制结构', 'lin', True, 85, '功能实现完整，建议进一步补充异常处理与输入校验。', 1, 'full'),
    ('Python 程序设计', '函数与模块设计', 'zhang', False, None, '', 1, 'code_only'),
    ('Web 应用开发', '个人主页设计', 'zhang', True, 88, '页面结构清楚，移动端适配良好，可再优化配色对比度。', 1, 'with_shot'),
    ('Web 应用开发', 'Django 数据模型实践', 'wang', False, None, '', 1, 'full'),
    ('Web 应用开发', '课程项目：教学管理系统', 'zhang', True, 95, '项目结构完整，权限与数据校验考虑充分，文档规范。', 1, 'full'),
    ('数据库原理与应用', 'SQL 查询实验', 'lin', True, 78, '查询结果正确，执行计划分析可以更深入，注意索引选择依据。', 1, 'report_only'),
    ('数据库原理与应用', 'SQL 查询实验', 'sun', False, None, '', 1, 'report_only'),
    ('数据结构与算法', '实验一：线性表', 'zhou', True, 88, '实验结果正确，性能对比充分，报告结构清楚。', 1, 'full'),
    ('数据结构与算法', '实验二：二叉树遍历', 'zhang', False, None, '', 1, 'full'),
    ('人工智能导论', '实验：图像分类入门', 'lin', True, 90, '实验流程完整，失败案例分析有价值，图表标注可以更规范。', 1, 'full'),
    ('计算机视觉基础', '实验：边缘检测与特征提取', 'sun', False, None, '', 1, 'full'),
]


def _zip_bytes(title, files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _code_zip(title):
    main_py = (
        '# ' + title + '\n\n'
        'from utils import summarize\n\n\n'
        'def main():\n'
        '    values = [3, 5, 8, 13]\n'
        '    print(title_label())\n'
        '    print(summarize(values))\n\n\n'
        'def title_label():\n'
        '    return "' + title + '"\n\n\n'
        'if __name__ == "__main__":\n'
        '    main()\n'
    )
    utils_py = (
        'def summarize(values):\n'
        '    if not values:\n'
        '        return {"count": 0, "total": 0}\n'
        '    return {"count": len(values), "total": sum(values)}\n'
    )
    readme = (
        '# ' + title + '\n\n'
        '课程演示用示例项目，包含入口脚本与工具模块。\n\n'
        '运行方式：\n\n'
        '```bash\n'
        'python main.py\n'
        '```\n'
    )
    return _zip_bytes(title, {'main.py': main_py, 'utils.py': utils_py, 'README.md': readme})


def _report(title, note):
    return (
        '# {} 实验报告\n\n'
        '> 本文件为平台演示数据，用于展示提交、评分与在线浏览功能。\n\n'
        '## 一、实验目的\n\n'
        '掌握课程相关内容，完成从设计到实现的完整流程。\n\n'
        '## 二、实现过程\n\n'
        '1. 阅读任务要求，拆分功能点；\n'
        '2. 完成核心代码并本地验证；\n'
        '3. 补充异常处理与必要注释；\n'
        '4. 整理结果与问题分析。\n\n'
        '## 三、结果与结论\n\n'
        '{}\n\n'
        '## 四、问题与改进\n\n'
        '边界情况覆盖仍不完整，后续将补充更多测试用例。\n'
    ).format(title, note)


def _png_bytes():
    # 1x1 绿色 PNG，用于演示"运行截图"类材料。
    import base64
    return base64.b64decode(
        'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=='
    )


def _md_resource(name, course_name):
    return (
        '# {}\n\n'
        '> 课程：{}\n'
        '> 本资料为平台演示数据，用于展示资料上传与下载功能。\n\n'
        '## 内容提纲\n\n'
        '- 基本概念与术语\n'
        '- 典型示例与操作步骤\n'
        '- 常见问题与注意事项\n\n'
        '## 使用建议\n\n'
        '结合课程实验同步练习，遇到问题可在作业反馈中提出。\n'
    ).format(name, course_name)


def _breakdown(rubric, grade):
    if not rubric:
        return []
    total = sum(item['points'] for item in rubric) or 100
    rows, used = [], 0
    for index, item in enumerate(rubric):
        if index == len(rubric) - 1:
            score = grade - used
        else:
            score = int(round(grade * item['points'] / float(total)))
            used += score
        rows.append(dict(item, score=max(0, min(item['points'], score))))
    return rows


class Command(BaseCommand):
    help = '创建可重复执行的教学与科研演示数据（不修改真实数据，不新增字段）。'

    def add_arguments(self, parser):
        parser.add_argument(
            '--enable-login',
            action='store_true',
            help='为演示账号设置可登录密码（默认不可登录，避免公开站点出现可登录的演示账号）。',
        )

    # ---------- 基础对象 ----------

    @transaction.atomic
    def handle(self, *args, **options):
        self.now = timezone.now()
        self.assignments = {}
        self.counts = {
            'users': 0, 'courses': 0, 'enrollments': 0, 'assignments': 0,
            'submissions': 0, 'grades': 0, 'resources': 0, 'projects': 0,
            'tasks': 0, 'commits': 0,
        }
        self.skipped = {
            'users': 0, 'courses': 0, 'assignments': 0, 'submissions': 0,
            'resources': 0, 'projects': 0,
        }

        self.teachers = self._ensure_users(DEMO_TEACHERS, user_type=2, options=options)
        self.students = self._ensure_users(DEMO_STUDENTS, user_type=1, options=options)

        courses = self._ensure_courses()
        self._ensure_assignments(courses)
        self._ensure_resources(courses)
        self._ensure_submissions(courses)
        self._ensure_groups(courses)
        self._ensure_research(options)

        self.stdout.write(self.style.SUCCESS('演示数据准备完成。'))
        self.stdout.write('本次新建：' + '，'.join(
            '{} {}'.format(label, value) for label, value in (
                ('用户', self.counts['users']), ('课程', self.counts['courses']),
                ('选课', self.counts['enrollments']), ('作业', self.counts['assignments']),
                ('提交', self.counts['submissions']), ('评分', self.counts['grades']),
                ('资料', self.counts['resources']), ('科研项目', self.counts['projects']),
                ('科研任务', self.counts['tasks']), ('进度提交', self.counts['commits']),
            )
        ))
        self.stdout.write('已存在跳过：' + '，'.join(
            '{} {}'.format(label, value) for label, value in (
                ('用户', self.skipped['users']), ('课程', self.skipped['courses']),
                ('作业', self.skipped['assignments']), ('提交', self.skipped['submissions']),
                ('资料', self.skipped['resources']), ('科研项目', self.skipped['projects']),
            )
        ))
        self.stdout.write(self.style.WARNING(
            '提示：演示账号默认不可登录；如需登录演示，请加 --enable-login 并自行设置 DEMO_LOGIN_PASSWORD。'
        ))

    def _ensure_users(self, definitions, user_type, options):
        password = os.environ.get('DEMO_LOGIN_PASSWORD') or 'Demo@Zhixing2026'
        result = {}
        for key, (username, last_name, first_name) in definitions.items():
            user, created = User.objects.get_or_create(
                username=username,
                defaults={'last_name': last_name, 'first_name': first_name, 'user_type': user_type,
                          'email': '{}@example.com'.format(username)},
            )
            if created:
                if options.get('enable_login'):
                    user.set_password(password)
                else:
                    user.set_unusable_password()
                user.save(update_fields=['password'])
                self.counts['users'] += 1
            else:
                self.skipped['users'] += 1
            result[key] = user
        return result

    def _ensure_courses(self):
        courses = {}
        for spec in COURSES:
            teacher = self.teachers[spec['teacher']]
            course = Course.objects.filter(course_name=spec['name'], teacher=teacher).first()
            if course is None:
                course = Course.objects.create(
                    course_name=spec['name'], course_description=spec['desc'],
                    teacher=teacher, is_archived=spec.get('archived', False),
                )
                self.counts['courses'] += 1
            else:
                self.skipped['courses'] += 1
            courses[spec['name']] = course
            for student_key in spec['students']:
                _, created = Enrollment.objects.get_or_create(course=course, student=self.students[student_key])
                if created:
                    self.counts['enrollments'] += 1
        return courses

    def _ensure_assignments(self, courses):
        day = timedelta(days=1)
        for course_name, name, description, start_offset, due_offset, mode, materials, rubric in ASSIGNMENTS:
            course = courses[course_name]
            start_date = self.now + day * start_offset
            due_date = self.now + day * due_offset
            assignment = Assignment.objects.filter(course=course, assignment_name=name).first()
            if assignment is None:
                assignment = Assignment.objects.create(
                    assignment_name=name,
                    assignment_description='{}\n\n（本作业为平台演示数据，用于展示不同状态与批改流程。）'.format(description),
                    start_date=start_date, due_date=due_date, course=course,
                    submission_mode=mode, required_materials=materials, rubric=rubric,
                )
                self.counts['assignments'] += 1
            else:
                # 演示作业允许刷新时间，保证重复执行后仍能覆盖"进行中/即将截止/已截止"。
                if not assignment.question.exists():
                    Assignment.objects.filter(pk=assignment.pk).update(
                        start_date=start_date, due_date=due_date)
                self.skipped['assignments'] += 1
            self.assignments[(course_name, name)] = assignment

    def _ensure_resources(self, courses):
        for course_name, resource_name, kind, filename in RESOURCES:
            course = courses[course_name]
            if Resource.objects.filter(course=course, resource_name=resource_name).exists():
                self.skipped['resources'] += 1
                continue
            if kind == 'zip':
                data = _zip_bytes(resource_name, {
                    'README.md': _md_resource(resource_name, course_name),
                    'example.py': 'def demo():\n    return "hello"\n',
                })
                filename = resource_name + '.zip'
            elif kind == 'csv':
                data = '姓名,学号,课程,成绩\n张晨,2024001,{},92\n林晓,2024002,{},85\n'.format(course_name, course_name).encode('utf-8')
                filename = resource_name + '.csv'
            else:
                data = _md_resource(resource_name, course_name).encode('utf-8')
                filename = resource_name + '.md'
            storage = Resource._meta.get_field('resource_file').storage
            path = storage.save('resources/demo/{}'.format(filename), ContentFile(data, name=filename))
            Resource.objects.create(resource_name=resource_name, resource_file=path, course=course)
            self.counts['resources'] += 1

    # ---------- 提交与评分 ----------

    def _ensure_submissions(self, courses):
        storage = SubmissionAttachment._meta.get_field('file').storage
        for course_name, assignment_name, student_key, graded, grade, feedback, version, style in SUBMISSIONS:
            assignment = self.assignments[(course_name, assignment_name)]
            student = self.students[student_key]
            if SubmitAssignment.objects.filter(author=student, assignment_ques=assignment).exists():
                self.skipped['submissions'] += 1
                continue
            files = self._submission_files(assignment, student_key, style)
            submission = self._create_submission(
                student, assignment, files, version=version, current_slot=1,
                topic='{} · {}'.format(assignment_name, student),
                description='按任务要求完成实现与验证，具体说明见报告。本提交为平台演示数据。',
                storage=storage,
            )
            self.counts['submissions'] += 1
            if graded and grade is not None:
                teacher = assignment.course.teacher
                submission.grade_assignment(
                    grade, feedback, grader=teacher,
                    breakdown=_breakdown(assignment.rubric, grade),
                )
                self.counts['grades'] += 1
        self._ensure_version_history(assignment_name='函数与模块设计', course_name='Python 程序设计')

    def _ensure_version_history(self, course_name, assignment_name):
        """为一个作业补出 v1(历史) + v2(当前) 两个版本，用于演示版本对比。"""
        assignment = self.assignments[(course_name, assignment_name)]
        student = self.students['lin']
        if SubmitAssignment.objects.filter(author=student, assignment_ques=assignment).count() >= 2:
            return
        if SubmitAssignment.objects.filter(author=student, assignment_ques=assignment).exists():
            return
        storage = SubmissionAttachment._meta.get_field('file').storage
        first = self._create_submission(
            student, assignment, [('main.py', _code_zip('函数与模块设计 v1'), 'code')],
            version=1, current_slot=None, topic='函数与模块设计 · 初版',
            description='第一版只完成函数拆分，尚未补充参数校验。', storage=storage,
        )
        self.counts['submissions'] += 1
        second = self._create_submission(
            student, assignment, [('main.py', _code_zip('函数与模块设计 v2'), 'code')],
            version=2, current_slot=1, topic='函数与模块设计 · 补充校验',
            description='补充参数校验与异常处理，重构工具函数。', storage=storage,
        )
        self.counts['submissions'] += 1
        self.stdout.write('已为 {} 生成版本对比样例：v1 #{} / v2 #{}'.format(
            assignment_name, first.pk, second.pk))

    def _submission_files(self, assignment, student_key, style):
        title = assignment.assignment_name
        files = []
        if style in ('full', 'code_only', 'with_shot'):
            files.append(('{}.zip'.format('project'), _code_zip(title), 'code'))
        if style in ('full', 'report_only'):
            files.append(('实验报告.md', _report(title, '程序运行结果与预期一致，主要功能均已验证。').encode('utf-8'), 'report'))
        if style == 'with_shot':
            files.append(('运行截图.png', _png_bytes(), 'screenshots'))
        return files

    def _create_submission(self, student, assignment, files, version, current_slot, topic, description,
                           storage, group=None, participants=None):
        stored = []
        for name, data, category in files:
            path = storage.save('experiments/demo/{}'.format(name), ContentFile(data, name=name))
            stored.append((path, name, category, len(data), hashlib.sha256(data).hexdigest()))
        participants = participants or [
            {'id': student.pk, 'username': student.username, 'name': str(student)}
        ]
        submission = SubmitAssignment.objects.create(
            author=student, assignment_ques=assignment, topic=topic, description=description,
            assignment_file=stored[0][0], current_slot=current_slot, version_number=version,
            group=group, participant_snapshot=participants,
            rubric_snapshot=assignment.rubric,
        )
        SubmissionAttachment.objects.bulk_create([
            SubmissionAttachment(submission=submission, file=path, name=name, category=category,
                                 size=size, checksum=checksum)
            for path, name, category, size, checksum in stored
        ])
        return submission

    def _ensure_groups(self, courses):
        """软件工程实践的小组实验：建组、组员、组提交与个人调整分。"""
        course = courses['软件工程实践']
        assignment = self.assignments[('软件工程实践', '小组项目：需求与原型')]
        group, _ = CourseGroup.objects.get_or_create(course=course, name='第 1 组')
        members = [self.students['zhang'], self.students['lin']]
        for member in members:
            GroupMember.objects.get_or_create(group=group, course=course, user=member)
        if SubmitAssignment.objects.filter(group=group, assignment_ques=assignment).exists():
            return
        storage = SubmissionAttachment._meta.get_field('file').storage
        files = [
            ('需求与原型.zip', _code_zip('需求与原型'), 'code'),
            ('阶段总结.md', _report('小组项目：需求与原型', '完成需求清单与原型页面，明确下一阶段分工。').encode('utf-8'), 'report'),
        ]
        leader = self.students['zhang']
        submission = self._create_submission(
            leader, assignment, files, version=1, current_slot=1,
            topic='小组项目：需求与原型 · 第 1 组',
            description='小组共同完成需求规格与原型，分工见阶段总结。本提交为平台演示数据。',
            storage=storage, group=group,
            participants=[{'id': m.pk, 'username': m.username, 'name': str(m)} for m in members],
        )
        submission.grade_assignment(
            86, '小组整体完成度高，需求描述清楚；建议补充非功能需求与验收标准。',
            grader=course.teacher, breakdown=_breakdown(assignment.rubric, 86),
            adjustments={str(self.students['zhang'].pk): 4, str(self.students['lin'].pk): -4},
        )
        self.counts['submissions'] += 1
        self.counts['grades'] += 1

    # ---------- 科研 ----------

    def _ensure_research(self, options):
        for spec in RESEARCH_PROJECTS:
            owner = self.teachers[spec['owner']]
            workspace = ResearchWorkspace.objects.filter(name=spec['name'], owner=owner).first()
            if workspace is not None:
                self.skipped['projects'] += 1
                continue
            workspace = ResearchWorkspace.objects.create(
                name=spec['name'], description=spec['desc'], owner=owner,
                created_by=owner, status=spec['status'],
            )
            self.counts['projects'] += 1
            from research.models import Activity
            Activity.objects.create(workspace=workspace, actor=owner, kind='workspace_created',
                                    title=workspace.name)
            for student_key, role in spec['members']:
                member = WorkspaceMember.objects.create(
                    workspace=workspace, user=self.students[student_key], role=role)
                Activity.objects.create(workspace=workspace, actor=owner, kind='member_joined',
                                        title='{} · {}'.format(member.user, member.get_role_display()))
            tasks = {}
            for title, description, assignee_key, progress in spec['tasks']:
                task = ResearchTask.objects.create(
                    workspace=workspace, title=title, description=description,
                    created_by=owner, assignee=self.students[assignee_key], progress=progress,
                )
                tasks[title] = task
                self.counts['tasks'] += 1
            commits = []
            for title, description, author_key, filename, content in spec['commits']:
                author = self.students[author_key]
                related = next((task for task in tasks.values() if task.assignee_id == author.pk), None)
                cleaned = {
                    'uploads': [ContentFile(content.encode('utf-8'), name=filename)],
                    'duplicate_action': 'version',
                    'version_description': '演示进度附件',
                }

                def factory(locked_workspace, title=title, description=description, author=author, related=related):
                    return ProgressCommit.objects.create(
                        workspace=locked_workspace, author=author, title=title,
                        description=description + '（本记录为平台演示数据。）', related_task=related,
                    )

                commit, _versions = save_artifacts(workspace, author, cleaned, factory)
                commits.append(commit)
                self.counts['commits'] += 1
            for author_key, text in spec['comments']:
                author = self.teachers.get(author_key) or self.students.get(author_key)
                if author and commits:
                    from research.models import Activity, CommitComment
                    comment = CommitComment.objects.create(
                        commit=commits[-1], author=author, content=text)
                    Activity.objects.create(
                        workspace=workspace, actor=author, kind='comment',
                        title=commits[-1].title, description=text,
                        comment=comment, commit=commits[-1])
