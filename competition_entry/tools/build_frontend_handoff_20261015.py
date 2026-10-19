"""Freeze an allowlisted E31 frontend development handoff without environments or credentials."""
from pathlib import Path
import hashlib, json, shutil, zipfile

ROOT=Path(__file__).resolve().parents[2]
NAME='PrivEdge_前端同学交接_E31_20261015'
OUT=ROOT/'share'/NAME
SKIP={'.git','.venv','node_modules','__pycache__','.pytest_cache','.agents','.codex'}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def allowed(p):
    return not any(x in SKIP for x in p.parts) and p.suffix not in {'.pyc','.tsbuildinfo'}
def put(src,rel):
    if src.is_symlink():raise ValueError(f'No symlink: {rel}')
    if src.name.startswith('.env') or src.suffix.lower() in {'.pem','.key'} or src.name.lower() in {'kaggle.json','credentials','id_rsa'}:
        raise ValueError(f'Refusing possible credential: {rel}')
    dst=OUT/rel;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
def tree(rel):
    for src in sorted((ROOT/rel).rglob('*')):
        if src.is_file() and allowed(src.relative_to(ROOT/rel)):put(src,src.relative_to(ROOT))
def text(name,body):
    (OUT/name).write_text(body,encoding='utf-8-sig')

def main():
    OUT.mkdir(exist_ok=False)
    for rel in ['privedge','review/top-k-share-20260925']:tree(rel)
    # Complete maintained project tools; the old broad share-builder is reference-only.
    for src in sorted((ROOT/'competition_entry/tools').iterdir()):
        if src.is_file():put(src,src.relative_to(ROOT))
    for rel in ['.gitignore','.gitattributes']:
        put(ROOT/rel,rel)
    docs=['02_实验证据登记.md','03_容错定理与证明.md','08_相对团队原始研究代码的改动记录.md',
          'PrivEdge_作品报告_B补交整合版_20261015.docx','B补交验收与整合结论_20261015.txt',
          '程序运行复查与修复结论_20261015.txt','sections/后端接口交接_20261013.txt','sections/后端接口交接_20261015.txt']
    for name in docs:
        rel=Path('competition_entry/docs/v4')/name;put(ROOT/rel,rel)
    tree('competition_entry/docs/v4/figures')
    # Include only the located project adapters, not unrelated dataset exploration or raw downloads.
    for rel in ['dataset_research/scripts/olist_common.py','dataset_research/scripts/olist_ldp_diagnostic.py',
                'dataset_research/scripts/olist_phase2_context.py','dataset_research/scripts/massive_steps_ldp_diagnostic.py',
                'dataset_research/TRD_PREREGISTRATION_20260929.md']:
        put(ROOT/rel,rel)
    for folder,files in {
        '20261015_runtime_review':['integration.json','portable_release.json','pytest.txt','portable_pytest.txt','e31_selfcheck.txt','frontend_build.txt','legal_input_comparison.json','evidence_comparison.json'],
        '20261015_b_supplement':['integration.json','report_quality_check.json','runstream_results.json','browser_final_summary.json'],
    }.items():
        for name in files:
            rel=Path('competition_entry/docs/v4/backend_validation')/folder/name;put(ROOT/rel,rel)
    zipname='PrivEdge_整合候选_E31_运行复查修复版_20261015.zip'
    assert sha(ROOT/'share'/zipname)=='6f41b7dd66329b18e0f039a280ede7723e0d263ee3b71a0b61f801971a0b2b56'
    put(ROOT/'share'/zipname,Path('参考运行包')/zipname)
    text('00_先读_前端接手说明.txt','''PrivEdge 前端接手说明——当前唯一开发起点 E31（2026-10-15）

这是队长已经合并算法、B补交并修复运行问题后的完整作品开发源码。你负责前端，不需要重新实现算法、后端或寻找数据。这里的“前端任务A”仅指本次分工，不是旧任务清单中算法A类编号。
仓库main的23546a1只是历史基准，本包含尚未提交的整合变更。不要重新从main下载后覆盖本包，不要覆盖为早期B程序。文件基线见BASELINE_SHA256.json。

一、目录与版本
privedge/：唯一可编辑的当前程序源码；web/src是前端，web/dist是构建产物，privedge/server是后端。tests、锁定依赖、三套标准表、已有runs、预注册、A8证据和许可证均已带上。
review/top-k-share-20260925/：团队原始研究代码快照，保持原样。
competition_entry/tools/：项目构建/导出/通信测试工具；build_share_package.py及“从这里开始”含早期流程，本交接说明优先，不直接用旧广泛打包流程覆盖新的交接包。
competition_entry/docs/v4/：当前报告、接口说明、证据登记、图表和必要验收记录。报告文件名为E30，程序已追加E31页面恢复修复；报告终稿要采用最终版本的测试及程序指纹，不能把历史版本的数目累加。
参考运行包/：E31已冻结ZIP，用来先运行和对照；其中的application副本不是另一个开发主目录，不在里面改前端。你的源码只改外层privedge/。
dataset_research/：只带已定位的相关研究脚本；完整原始下载输入未随包验证。前端直接用privedge/data标准表，不运行导出脚本覆盖它们。

二、先看程序（不需要安装Python）
解压“参考运行包”里的E31 ZIP，进入其中程序目录，双击“启动程序.cmd”，按窗口实际显示的网址访问。默认8765，若占用会换空闲端口。可双击“验证程序.cmd”“运行测试.cmd”。
这份参考包已验证217项测试、12类浏览器检查及三数据实际流程。账本与密钥是内存演示状态，重启清空；只监听本机。

三、开始开发前端
推荐使用本机已有且与锁定依赖兼容的Node.js/npm。首次在外层privedge/web目录执行 npm ci；成功后执行 npm run dev，打开终端显示的开发页面。
Vite把/api和/ws转发到127.0.0.1:8765，所以开发时保持参考后端运行。若其实际端口不是8765，修改web/vite.config.ts中两个proxy端口与之匹配，交回时注明此本机改动。不要把占用端口的别人的进程关掉。
前端改好后执行 npm run build，生成外层privedge/web/dist。npm run preview本身不提供后端代理，不能把它当完整系统启动方式。
若需要从外层源码启动完整程序：安装Python 3.12，进入privedge，执行setup.bat，再执行run_tests.bat和start_console.bat。首次setup需要联网安装锁定依赖。关闭参考后端后再启动源码后端，避免8765冲突。不要将别人的.venv复制到你的机器。
前端通信回归：在交接包根目录执行 node competition_entry/tools/test_runstream.mjs，先完成web目录npm ci。
最终要验证的是外层源码构建后的完整程序；只看到开发页面不算完成。可先回交完整源码和dist，由队长生成最终运行包，不要求你重做运行时打包工程。

四、开发范围与已完成内容
五个页面、双A8入口、真实预测/攻击/账本及错误恢复已经实现。你负责在这个基础上做可展示的前端收尾，具体任务、章节和回交材料见01。所有统计数字从接口读取，不手填；遇到接口问题记录实际请求/响应交队长。
不用重跑算法实验、不修改已有runs、原始数据或研究代码；不能删掉现有取消/重试/状态隔离、数据集同步和“重试连接”。
主线：多源LDP摘要的抗投毒可信交换。新区域选品只是例子；“检查通过”不表示预测准确；无攻击不宣称优于简单平均。A8是描述性比较，严格入口NOT_RUN不等于没有四方法结果。

五、你拿到的代码可验证
BASELINE_SHA256.json是外层源码/资料起点，别改它。交回前运行 python 检查交付差异.py，它会列出你改过、新增和删除的文件，不替你运行功能测试。BASELINE_SHA256.json不是你的更新后验收清单，保留用于三方合并。
完整性和测试结果只说明已验证范围，不保证所有环境零错误；你的电脑仍需实际跑通并留设备/依赖记录。
''')
    text('01_前端任务与回交清单.txt','''前端负责人实际任务与报告章节（以本包E31为起点）

目标：做出可完整演示、信息清楚、能解释证据来源的五页控制台，并完成自己负责的报告内容。已有功能继续用，不另起炉灶，不把已经完成的后端/实验算成你的新增工作。

步骤1：启动并确认基线
先运行参考包，依次看总览、冷启动预测、攻防实验室、账本审计、实验中心。再启动前端开发环境。记录本机系统、浏览器、Node/npm版本及实际启动成功情况；遇到错误发完整日志和操作步骤。

步骤2：完成五页前端收尾与可读性检查
总览：突出多源LDP摘要可信交换的流程、已实现功能和边界，避免写成经营收益预测产品。
预测：参数、当前数据集、执行步骤、结果归属、三态原因和离线评价应清楚；长类别名和空结果不遮挡。检查通过/降级/拒答不能误导为准确度等级。
攻防：攻击选择、对应防线、真实流水、比较结果和完整巡检表可读；明确现场示例与登记统计结果的区别。错误应能重试，切换后不出现旧数据结果。
账本：账本完整性、最新窗口预算、审计记录和副本篡改拒答能够清楚演示；原账本不改，空账本与加载失败有说明。
实验中心：保留既有图表和四方法描述性比较；数据集/epsilon/场景切换一致，均值和区间、缺失值、局限和来源可查。保留独立加载、重试和不同证据状态，不能以严格入口NOT_RUN遮盖描述性结果。
统一检查常用电脑窗口下布局、长表、控件、字体和对比度，收尾实际发现的问题。不是要求大改视觉主题或增加新功能。后端字段确有不足时提出具体字段与页面需求，不自行更改算法和证据文件。

步骤3：验证最终页面并截图
三套数据分别预测，至少覆盖攻击演示、TRD完整巡检、账本副本篡改、数据集/参数切换、失败重试；检查浏览器错误与接口异常。后台现有217项测试应仍通过；前端build与通信回归应通过。新增测试只针对你改变的行为。
五页分别截最终版本清晰截图，记录对应数据集、参数、操作与版本；不要拿早期截图充当前版本。若状态需特定条件，不伪造页面数据取得截图。
写一份简短演示步骤，按“预测→攻击→账本→登记证据”能完整走通。视频只有当届通知明确要求时才制作。

步骤4：完成报告分稿
直接参照包内PrivEdge_作品报告_B补交整合版_20261015.docx的实际标题，填写：
2.5.5 三态输出（界面与原因展示；规则由队长复核）；
2.7 前端设计与实现总述；2.7.1、2.7.2、2.7.3三个现有子节（沿用报告标题，不自行改编号）；
3.4.6 应用可行性（用完整演示和适用条件说明，不承诺真实经营收益）。
按现有标题写正文、截图和图注；给测试负责人提供3.4.1系统功能对应证据。只编辑自己章节；也可交独立Word分稿，用完整章节编号标明插入位置，队长按节合并。
不改算法结论、定理或他人章节。资料中的历史E24/E29测试数不改作自己实测；真实执行后的设备、日期、包和结果才写为本次验证。

一次性回交以下材料
1. 基于本包修改后的完整privedge目录，必须含web/src、web/dist、package.json与package-lock.json；其他源码、数据、既有证据仍带齐。排除node_modules、.venv、缓存、凭据。不只发截图、dist或运行包。
2. 改动说明：哪些文件新增/修改/删除，做了什么、如何验证、未完成的问题；运行“检查交付差异.py”附生成的交付差异.json，保留原BASELINE_SHA256.json。
3. 六个对应报告位置的Word正文、最终五页截图原图、图注、演示步骤。
4. 真实测试记录：构建/测试日志、设备与版本、页面用例结果、控制台/接口错误及处理状态。失败也写，不把未执行填成通过。
5. 如另做可运行包，同时交与之完全对应的源码、构建方式、依赖锁、文件指纹；仅有运行包不能替代第1项。

收到后队长按基线逐文件合并，再统一生成最终程序和正式报告。原始数据/旧实验不动，任何新实验先另行预注册。
''')
    text('检查交付差异.py','''from pathlib import Path
import hashlib,json
r=Path(__file__).resolve().parent
base=json.loads((r/'BASELINE_SHA256.json').read_text(encoding='utf8'))['files']
skip={'.git','.venv','node_modules','__pycache__','.pytest_cache','.codex','.agents'}
def allowed(p):return not any(x in skip for x in p.parts) and p.suffix not in {'.pyc','.tsbuildinfo','.pem','.key'} and not p.name.startswith('.env') and p.name not in {'kaggle.json','交付差异.json','BASELINE_SHA256.json'}
now={p.relative_to(r).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in r.rglob('*') if p.is_file() and allowed(p.relative_to(r)) and not p.is_symlink()}
result={'baseline_record':'E31','modified':[n for n in base.keys()&now.keys() if base[n]!=now[n]],'added':sorted(now.keys()-base.keys()),'deleted':sorted(base.keys()-now.keys())}
result['modified'].sort()
(r/'交付差异.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps(result,ensure_ascii=False,indent=2))
''')
    files={p.relative_to(OUT).as_posix():sha(p) for p in sorted(OUT.rglob('*')) if p.is_file()}
    # Main project's copied bytes are the current workspace, not an old archive checkout.
    for n,h in files.items():
        if n.startswith(('privedge/','review/top-k-share-20260925/')):assert sha(ROOT/n)==h,n
    (OUT/'BASELINE_SHA256.json').write_text(json.dumps({'record':'E31','base_commit':'23546a1','uncommitted_integration':True,'runtime_archive_sha256':'6f41b7dd66329b18e0f039a280ede7723e0d263ee3b71a0b61f801971a0b2b56','files':files},ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps({'folder':str(OUT),'payload_files':len(files),'source_files':sum(n.startswith('privedge/') for n in files),'bytes':sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())},ensure_ascii=False))

if __name__=='__main__':main()
