# PrivEdge E34

多源 LDP 摘要的抗投毒可信交换原型，应用版本 **0.4.1**。新区域选品是应用例子。

用户进行 OLH 本地扰动，发布端筛查并发布签名 Top-m 摘要；网关核对来源、角色、窗口、类别域、预算登记和内容，再执行支持过滤、截尾和权重封顶，输出 Top-10 与检查通过、降级或拒答状态。**检查通过不表示预测准确，未拒答不表示攻击失败；无攻击时不主张比简单平均更准。**

## 先选对入口

| 使用场景 | 入口与环境 |
|---|---|
| 评审演示、离线运行与核心复现 | 完整解压 E34 Windows x64 包，在包根目录打开 `先读我_使用指南.html`。Python、固定依赖、三套标准表、已构建页面、制图库及 ProVerif 2.05 已内置，无需联网安装。 |
| 修改源码、开发与构建 | 本目录是开发项目。需要 Python 3.12；修改前端还需要 Node.js 与 npm，使用下面的源码开发步骤。 |

便携包将本目录原样放在 `application/`，工具源码放在 `tool_sources/competition_entry/tools/`。`application/setup.bat`、`start_console.bat`、`run_tests.bat` 是保留的开发脚本；便携运行请使用包根目录 `.cmd` 入口，避免意外创建环境或调用系统 Python。

## 便携包四步自助

1. **解压并核验。** 打开离线指南，再双击 `验证程序.cmd`，检查冻结文件指纹、三数据预测、账本副本拒答和双 A8 入口。测试结果以 E34 实际验收记录为准。
2. **走完五页。** 双击 `启动程序.cmd`，访问窗口显示的本机网址；默认端口忙时自动选择空闲端口。总览阅读可信交换流程，冷启动预测运行正常交换，攻防实验室观察攻击与分层处理，账本审计检查登记与篡改副本，实验中心阅读已登记结果及限制。
3. **固定参数重放。** 自助示例为 TRD 商圈 3、ε=1、Top-m=20、每源 5000 条、seed=20260929，依次运行正常交换、单源权重劫持和未重签篡改。同一 seed 可比较榜单与离线指标；窗口、密钥、运行编号和时间不同是正常现象。更改参数后显示的是“上次运行”，须重新运行才能评价新配置。留空 seed 是新的随机演示。
4. **保留证据并复现。** 页面可下载本次请求、响应和公开版本标识；它不自动进入统计登记。按下表运行复现入口。`运行测试.cmd` 运行包内回归测试。关闭服务前按 Ctrl+C；重启后账本和密钥重新建立。

| 入口 | 实际范围 | 解释边界 |
|---|---|---|
| `快速核心统计复现.cmd` | 三套标准表，每套首个目标、旧种子 101，ε=1,2，m=20，每源 5000 条，九场景、四方法，随后独立统计复核 | 每数据集 72 行，`smoke_test=true`；仅检查管线，不替代正式统计表。 |
| `完整A8四方法重算.cmd` | 全部目标，旧种子 101/211/307/401/503，完整 A8 网格，再独立复核 | 只重算 A8，不是所有历史实验；旧种子重放不是新的独立确认。 |
| `重跑形式化验证.cmd` | 包内 ProVerif 2.05 执行既有模型、主查询及四个负对照 | 只验证符号模型，不证明实现无漏洞、预算数值正确或统计防御成功。 |
| `从历史证据重建图表.cmd` | 读取已登记输出，生成五幅实验图与两幅架构/流程图的 PNG、SVG | 只重绘，不重新生成统计结果。 |

会话写入包内 `reproduction_outputs/<新会话>/`；统计和形式化另写入 `application/runs/<实验>/<新ID>/`。先看会话内 `结果索引.html`、`session.json` 和日志。`FAILED` 或 `INTERRUPTED` 不能当作完成。旧文件和实验中心登记保持不变。完整网格耗时较长，实际完成范围以会话记录为准。

包根目录的命令行入口如下；`--plan` 只列命令，不创建结果或执行实验：

```powershell
.\runtime\python.exe -B -X utf8 .\run_privedge.py --check
.\runtime\python.exe -B -X utf8 .\run_privedge.py --tests
.\runtime\python.exe -B -X utf8 .\run_reproduction.py --mode quick
.\runtime\python.exe -B -X utf8 .\run_reproduction.py --mode full --plan
.\runtime\python.exe -B -X utf8 .\run_reproduction.py --mode full
.\runtime\python.exe -B -X utf8 .\run_reproduction.py --mode formal
.\runtime\python.exe -B -X utf8 .\run_reproduction.py --mode figures
```

报告结论到数据、参数、方法、命令和输出的对应关系见包根目录 `复现索引.json` 与离线指南。最终实体第二电脑验收须由实际设备完成，本机新目录解压不能替代。

## 源码开发

以下在包含 `pyproject.toml` 的本目录执行。依赖安装只用于源码开发，便携运行不需要这些步骤。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock
.\.venv\Scripts\python.exe -m pip install -r requirements-reproduction.lock
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe -B -m pytest -q
```

首次安装前端依赖、修改前端并重建时：

```powershell
Push-Location web
npm ci
npm run build
Pop-Location
.\.venv\Scripts\python.exe -B -m uvicorn privedge.server.app:app --host 127.0.0.1 --port 8765
```

浏览器访问 <http://127.0.0.1:8765/>。运行已有 `web/dist/` 不需要 Node.js。前端开发用 `web/` 下的 `npm run dev`，代理 `/api`、`/ws` 到本机 8765。

| 路径 | 内容 |
|---|---|
| `privedge/ldp.py`、`pipeline.py` | OLH 扰动与估计、发布端筛查 |
| `privedge/envelope.py`、`keys.py`、`ledger.py` | 签名摘要、角色密钥与预算登记 |
| `privedge/gateway.py` | 来源、签名、角色、窗口、域、内容与账本核对 |
| `privedge/robust.py`、`decision.py` | 留一截尾、支持规则、权重封顶与三态 |
| `privedge/attacks.py` | 本地防御测试用的攻击模拟 |
| `privedge/adapters/`、`data/` | 适配器与内置标准表 |
| `privedge/experiments/`、`experiments_prereg/` | 实验运行器、预注册及结果记录 |
| `privedge/server/`、`web/` | 后端及五页控制台源码与构建页面 |
| `formal/`、`tests/` | 协议模型、负对照与回归测试 |

## 接口与历史证据

`GET /api/version` 返回 E34、应用版本、明确范围内的源文件指纹与标准数据指纹；它不是第三方认证或作者身份签名。主要业务接口为 `GET /api/datasets`、`POST /api/run`、`WS /ws/run`、`GET /api/ledger/{数据集}`、`POST /api/ledger/{数据集}/tamper-drill?seq=`、`GET /api/audit/{数据集}`、`GET /api/evidence`、`GET /api/prereg`。

A8 保留两个不同入口：

- `GET /api/evidence/a8/descriptive` 读取 E28 历史三数据共 216 个方法单元。完整时为 `AVAILABLE`，各数据集为 `DESCRIPTIVE`。原件、review、独立复算和规范摘要位于 `evidence_registry/a8_descriptive/`，读取时核对哈希。旧种子复用且运行前冻结不能独立确认，因此只作描述性比较。区间重采样单位是目标区域；裸基线没有三态，拒答率不适用。
- `GET /api/evidence/a8` 是严格预注册绑定入口，当前无登记，返回 `NOT_RUN`；证据不一致为 `INVALID`，不展示伪造数值。三数据均满足严格登记才为 `READY`。它与描述性入口可用不矛盾，也不能通过回填旧 manifest 获得确认性资格。

实验中心读取存档，不因页面演示或便携重跑自动更新。E34 实测、失败与复验集中在工程目录 `competition_entry/docs/v4/backend_validation/20261017_review_delivery/`。程序包以 `package_manifest.json`、复现会话和实际测试输出为准，本说明不固定测试总数。

## 其他历史实验的重放命令

下列命令在开发项目目录执行，从标准表写入新的运行 ID。须显式保留 `--v41-policy`、`--clip-floor 0` 和 `--weight-cap 2`；它们对应已登记的配置一致性核对，不能把不同配置混称为同一实验。

```powershell
$py = '.\.venv\Scripts\python.exe'
foreach ($d in 'meituan_trd','olist_brazil','massive_steps') {
  & $py -B -m privedge.experiments.security_v1 --dataset $d --protocol v2 --v41-policy
  & $py -B -m privedge.experiments.security_v3 --dataset $d --tag v4 --seeds '601,709,811,907,1009' --clip-floor 0
  & $py -B -m privedge.experiments.utility_v1 --dataset $d --weight-cap 2
}
& $py -B -m privedge.experiments.overhead_v1
& $py -B -m privedge.experiments.negative_check
```

在便携包重放这些模块时，从包根目录将 `$py` 改为 `.\runtime\python.exe`；模块通过相对路径定位 `application/`。使用 `-B -X utf8`，并查看 `复现索引.json` 的边界说明。形式化和制图优先使用封装入口，保证输出进入新会话。

这些命令复用旧种子，不能称为新的确认性研究。新研究实验须先预注册并冻结参数和种子；已有 `runs/`、原始数据、登记原件及团队原始研究代码不得覆盖。比较旧、新运行应核对完整行集合、参数、指标和输出指纹，不能只检查相交行。

## 数据、来源与许可

`data/` 是带 SHA-256 校验信息的标准表。包内可从标准表重算，但不包含完整公开原始数据下载与预处理输入链；不能据此宣称已独立完成从原始数据重建。找到预处理脚本不等于其输入版本、许可与上游处理链均已核实。

- 美团 TRD：<https://zenodo.org/records/8025855>，DOI 10.5281/zenodo.8025855；已归档 CC BY 4.0 字段和原文，上游授权仍按来源记录核对。
- Olist：Kaggle `olistbr/brazilian-ecommerce`，CC BY-NC-SA 4.0，保留非商业、署名和相同方式共享要求。
- Massive-STEPS：<https://github.com/cruiseresearchgroup/Massive-STEPS>；代码许可不能替代冻结数据及上游来源许可。

详细来源与未完成确认见 `THIRD_PARTY_LICENSES.md`、`licenses/`。`privedge/research_core/` 保留团队原始研究代码，`MANIFEST.json` 和测试核对逐字节一致；一致性不证明所有基础代码均为本队原创。OLH 移植代码的上游 MIT 许可与固定核对快照位于 `licenses/upstream_ldp_protocols/`；核对版本不等于当年移植版本，历史来源仍须提供者确认。

便携包保留 Python、依赖及前端组件许可。ProVerif 2.05 的 GPL-2.0-or-later 许可、README、CHANGES、完整对应源码与来源哈希分别在 `tools/proverif/`、`third_party_sources/`、`licenses/proverif/SOURCE.json`；不声称已可重复编译出字节相同的 ProVerif 二进制。成员署名、权属声明和实际分发条件须由团队本人核实。

## 已知边界

- 角色在同一进程模拟，只监听本机，无登录；账本与密钥驻留内存，重启清空。哈希链不能独立抵抗宿主整链重写或分叉。
- 签名证明来源与消息绑定，不保证摘要诚实。预算的跨窗口组合依赖用户集合等部署假设；账本不识别跨源重复用户。
- 定理 1 不保证已有类别名次稳定。定理 2 要求留一集合诚实严格多数等完整条件；诚实源未封顶权重在 [w,W] 时，α≤fκW/((n−f)w+fκW)。n=10、f=1、κ=2 且 W=w 的例子为 2/11≈0.1818（约0.182）；仅权重相近时仍须代入实际 W/w。完整条件见报告证明与实现说明。
- 目标区域真实分布仅用于离线评分，不进入网关。攻击目标入榜比例、三态和离线准确性是不同指标。
- 四方法对照包含发布筛查与网关，是整套统计方案比较；Top-m 缺失补零的坐标截尾适配不继承原稠密梯度论文误差界。
- OLH 当前采用 SplitMix64 fallback；一致性不证明哈希族通用均匀碰撞性质，筛查与截尾后频率也不能称为严格无偏。
- 耗时来自本机或批量向量化记录，不代表手机端或分布式部署。TRD 编号及区域拓扑只是匿名示例和示意图。
- 实体第二电脑验收、成员确认与签署、报名审核及上传按实际完成情况记录，不能由测试或文件哈希替代。
