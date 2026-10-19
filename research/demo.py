"""Curated, fictional read-only workspaces; explicit command only, never seed on GET."""
from datetime import timedelta
from unittest.mock import patch
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from users.models import User
from .models import ResearchWorkspace, WorkspaceMember, ResearchTask, Activity, CommitComment
from .services import save_artifacts


PEOPLE = [('supervisor', '陈老师', 2), ('tang', '汤鑫', 1), ('lin', '林同学', 1), ('zhou', '周同学', 1)]
PROJECTS = [
    {
        'key': 'illumination-demo-v1',
        'name': '工业异常检测中的光照鲁棒性研究',
        'description': '从 PatchCore baseline 出发，比较光照变化下的异常检测表现。实验、参数与结果图表逐步归档，在同一条时间线上讨论每一次发现。',
        'status': 'active',
        'tasks': [
            ('整理 MVTec AD 数据集', '检查 bottle、cable、screw 数据与标注，建立可复用的数据清单。', 1, 100),
            ('完成 PatchCore baseline', '复现基线，记录图像级与像素级指标。', 1, 100),
            ('光照扰动对比实验', '比较亮度和 gamma 变化，整理异常分数漂移。', 1, 65),
            ('补充相关工作', '整理工业视觉、光照鲁棒性与特征归一化文献。', 2, 100),
            ('实验图表与论文草稿', '把主要发现整理成图表，并补充方法和实验部分。', 2, 35),
            ('跨类别复核', '补充 cable 和 screw，复核不同缺陷类型的响应。', 1, 20),
        ],
        'commits': [
            (6, 1, 0, '完成五类数据检查与清单整理', '核对训练集、测试集和缺陷标注；整理目录结构，完成数据检查。下一步复现 bottle baseline。', [('数据检查.md', '# 数据检查（演示）\n\n- bottle：图像与 mask 已核对\n- cable：目录检查完成\n- screw：标注检查完成\n\n所有内容仅供平台演示。\n', '初始数据检查记录')]),
            (5, 2, 3, '整理光照鲁棒性相关工作', '梳理特征归一化、数据增强和异常分数校准三个研究方向，明确需要比较的实验变量。', [('相关工作.md', '# 相关工作（演示）\n\n1. 工业视觉中的光照变化\n2. 正常特征记忆库与异常评分\n3. 特征归一化和稳健表示\n\n待办：逐篇补充引用、实验条件与可复现代码。\n', '建立文献分类框架')]),
            (4, 1, 1, '完成 bottle 的 PatchCore baseline', '示例结果：Image AUROC = 0.982，Pixel AUROC = 0.971。保留初始参数，上传实验 CSV 与复现说明。', [('results.csv', 'category,image_auroc,pixel_auroc\nbottle,0.982,0.971\n', '首次 baseline 结果（演示数据）'), ('README.md', '# PatchCore 实验（演示）\n\nBackbone：Wide ResNet-50-2\nLayers：layer2 + layer3\nCoreset：0.1\n\n完成 bottle baseline，后续补充跨类别实验。\n', '初始实验说明')]),
            (3, 1, 1, '调整 coreset 参数并保存新结果', '固定数据划分，调整 coreset sampling ratio。示例 Image AUROC 从 0.982 提升至 0.987，保留原版以便对照。', [('results.csv', 'category,image_auroc,pixel_auroc\nbottle,0.987,0.974\n', '参数调整后的结果，保留 v1')]),
            (2, 2, 4, '补充实验设置与复现步骤', '完善运行步骤、指标解释与输出文件说明；与已有实验数据版本关联，方便同门继续复现。', [('README.md', '# PatchCore 实验（演示）\n\n## 设置\nBackbone：Wide ResNet-50-2\nLayers：layer2 + layer3\nCoreset：0.05\n\n## 实验流程\n1. 检查数据\n2. 建立正常特征库\n3. 测试并导出 CSV\n4. 保存参数与指标\n\nCSV 中全部数值为展示样例，并非实际实验结论。\n', '补充参数和复现步骤')]),
            (1, 1, 5, '扩展 cable 与 screw 跨类别实验', '新增 cable 和 screw 示例结果，发现不同类别的光照响应需要分别分析。更新 CSV 至 v3，下一步检查缺陷类型差异。', [('results.csv', 'category,image_auroc,pixel_auroc\nbottle,0.987,0.974\ncable,0.963,0.958\nscrew,0.948,0.966\n', '加入跨类别示例指标')]),
            (0, 1, 2, '记录亮度扰动下的分数变化', '完成第一轮亮度扰动对照，记录 AUROC 与正常样本分数漂移。继续补充多次运行，确认趋势是否稳定。', [('illumination.csv', 'condition,image_auroc,normal_score_shift\noriginal,0.987,0.000\nbrightness_0.8,0.963,0.120\nbrightness_1.2,0.974,0.080\n', '亮度扰动对照样例')]),
        ],
        'comments': ['请同时记录原始参数与随机种子，这样同门复现会更方便。', '建议继续补充 cable，并把不同缺陷类型分开分析。'],
    },
    {
        'key': 'reading-demo-v1',
        'name': '论文阅读与实验复现协作',
        'description': '围绕异常检测方法开展论文共读、复现与阶段讨论。把阅读笔记、文献清单和复现结果留成可追溯的研究记录。',
        'status': 'paused',
        'tasks': [
            ('建立论文阅读清单', '按问题、方法、数据与局限整理共读清单。', 2, 100),
            ('PatchCore 方法笔记', '理解特征提取、coreset 与最近邻评分。', 1, 100),
            ('PaDiM 复现实验', '比较高斯分布建模与记忆库方法。', 2, 50),
            ('组会汇报材料', '汇总共读发现与下一阶段复现计划。', 1, 30),
        ],
        'commits': [
            (5, 2, 0, '建立异常检测论文共读清单', '按特征分布建模、记忆库和轻量模型三个方向分类，列出每次共读需要回答的问题。', [('文献清单.csv', 'method,topic,status\nPatchCore,memory bank,reading\nPaDiM,distribution modeling,todo\nEfficientAD,lightweight inference,todo\n', '初始共读清单')]),
            (3, 1, 1, '完成 PatchCore 核心机制笔记', '整理正常特征记忆库、coreset 采样与异常图生成流程。讨论学习正常样本与监督缺陷分类的区别。', [('阅读笔记.md', '# PatchCore 阅读笔记（演示）\n\n## 核心问题\n如何利用正常样本识别未知异常？\n\n## 流程\n特征提取 → 多尺度融合 → coreset → 最近邻评分\n\n## 讨论\n特征层、样本覆盖与光照变化如何影响评分？\n', '第一份方法笔记')]),
            (2, 2, 0, '更新共读状态与复现分工', 'PatchCore 共读完成；开始 PaDiM 复现，分工检查预处理、特征层与评价指标。更新阅读清单 v2。', [('文献清单.csv', 'method,topic,status\nPatchCore,memory bank,completed\nPaDiM,distribution modeling,reproducing\nEfficientAD,lightweight inference,todo\n', '更新阅读与复现状态')]),
            (1, 2, 2, '整理 PaDiM 复现检查项', '完成环境与数据准备。暂缓新增实验，先核对评价方式，下次组会继续讨论。', [('复现计划.md', '# PaDiM 复现计划（演示）\n\n- [x] 准备运行环境\n- [x] 检查数据集\n- [ ] 对齐图像预处理\n- [ ] 复核图像级与像素级指标\n- [ ] 整理与 PatchCore 的差异\n', '阶段复现计划')]),
        ],
        'comments': ['组会先讲清楚方法的假设，再展示复现结果。', '已补充检查项，下次讨论重点核对评价指标。'],
    },
]


def seed_demo(now=None):
    now = now or timezone.now()
    result = []
    for spec in PROJECTS:
        existing = ResearchWorkspace.objects.filter(demo_key=spec['key']).first()
        if existing:
            result.append((existing, False))
            continue
        stored_files = []
        try:
            with transaction.atomic():
                people = []
                for key, name, role in PEOPLE:
                    person, _ = User.objects.get_or_create(username='__research_demo_' + key,
                        defaults={'first_name': name, 'user_type': role, 'is_active': False, 'password': '!'})
                    if person.is_active or person.has_usable_password() or person.is_staff or person.first_name != name:
                        raise ValidationError('示例用户名已被其他账号使用，未修改该账号。')
                    people.append(person)
                with patch('django.utils.timezone.now', return_value=now - timedelta(days=8)):
                    project = ResearchWorkspace.objects.create(name=spec['name'], description=spec['description'],
                        status=spec['status'], owner=people[0], created_by=people[0])
                    Activity.objects.create(workspace=project, actor=people[0], kind='workspace_created', title=project.name)
                    for index, person in enumerate(people[1:], 1):
                        WorkspaceMember.objects.create(workspace=project, user=person, role='viewer' if index == 3 else 'member')
                        Activity.objects.create(workspace=project, actor=people[0], kind='member_joined', title='{}加入项目'.format(person))
                tasks = []
                with patch('django.utils.timezone.now', return_value=now - timedelta(days=7)):
                    for title, description, assignee, progress in spec['tasks']:
                        task = ResearchTask.objects.create(workspace=project, title=title, description=description,
                            created_by=people[0], assignee=people[assignee], progress=progress)
                        tasks.append(task)
                        Activity.objects.create(workspace=project, actor=people[0], kind='task_created', title=title, task=task)
                commits = []
                from .models import ProgressCommit
                for days, author, task_index, title, description, files in spec['commits']:
                    moment = now - timedelta(days=days, hours=2)
                    with patch('django.utils.timezone.now', return_value=moment):
                        def create_commit(locked_workspace):
                            return ProgressCommit.objects.create(workspace=locked_workspace, author=people[author],
                                title=title, description=description, related_task=tasks[task_index])
                        commit, versions = save_artifacts(project, people[author], {
                            'uploads': [ContentFile(content.encode('utf-8'), name=filename) for filename, content, _ in files],
                            'duplicate_action': 'version', 'version_description': files[0][2]}, create_commit)
                        commits.append(commit)
                        stored_files.extend((v.resource.resource_file.storage, v.resource.resource_file.name) for v in versions)
                with patch('django.utils.timezone.now', return_value=now - timedelta(hours=1)):
                    for index, message in enumerate(spec['comments']):
                        target = commits[-2] if index == 0 else commits[-1]
                        author = people[0] if index == 0 else people[2]
                        comment = CommitComment.objects.create(commit=target, author=author, content=message)
                        Activity.objects.create(workspace=project, actor=author, kind='comment', title=target.title,
                                                description=message, commit=target, comment=comment)
                    for task in tasks:
                        if task.progress == 100:
                            Activity.objects.create(workspace=project, actor=task.assignee, kind='task_completed', title=task.title, task=task)
                # Publish only after the complete fictional history exists. No real workspace is promoted.
                project.demo_key = spec['key']
                project.save(update_fields=['demo_key', 'updated_at'])
                result.append((project, True))
        except Exception:
            for storage, name in stored_files:
                storage.delete(name)
            raise
    return result
