# PrivEdge

面向新区域开站选品的多源隐私保护可信 Top-K 需求情报系统。

已运营区域（商圈 / 州 / 城市）的用户在本地做 OLH 本地差分隐私扰动；区域发布者只发布签名的 Top-m 品类摘要，并在哈希链账本上按窗口记账；新开站区域的网关验证、抗投毒融合后给出 Top-10 与三态结论（正常 / 降级 / 拒答）。

本目录全部为本队自有原始代码。`privedge/research_core/` 是团队原始研究代码的逐字节副本（`MANIFEST.json` 记录哈希，`tests/test_core.py::test_research_core_is_byte_identical` 校验）。

## 目录

| 路径 | 内容 |
|---|---|
| `privedge/ldp.py` | OLH 扰动与频率估计（与原始代码逐位一致） |
| `privedge/pipeline.py` | 发布端：聚合 + 伪造用户联合支持过滤 |
| `privedge/envelope.py`、`keys.py` | 签名摘要信封（Ed25519，签名覆盖窗口号）；(主体, 角色) 密钥注册表 |
| `privedge/ledger.py` | 仅追加哈希链账本，登记前验签，按窗口顺序组合记账 |
| `privedge/gateway.py` | 目标网关：签名 / 角色 / 窗口 / 域 / 账本核对 / 同源多摘要 / 格式 |
| `privedge/robust.py`、`decision.py` | 留一共识截尾（下限 0）、支持规则 t=2、权重封顶 κ=2、三态决策 |
| `privedge/attacks.py` | MGA、被攻破发布者、权重劫持、负频率等攻击 |
| `privedge/adapters/` | 美团 TRD、Olist、Massive-STEPS 的标准化导出与加载 |
| `privedge/experiments/` | 预注册实验运行器（每次运行写入新的 `runs/<实验>/<运行ID>/`，含 `manifest.json`） |
| `privedge/server/` | FastAPI + WebSocket 后端 |
| `web/` | React + TypeScript + ECharts 控制台 |
| `formal/privedge_release.pv` | ProVerif 发布协议模型 |
| `experiments_prereg/` | 预注册文档与结果文档 |
| `tests/` | 单元测试、性质测试、后端接口测试 |

## Windows 一键脚本

需要先安装 Python 3.12+（安装时勾选 "Add python.exe to PATH"）。依次双击：

1. `setup.bat`：创建 `.venv` 并按 `requirements.lock` 安装依赖（首次约几分钟）；
2. `run_tests.bat`：运行全部测试，应显示 `27 passed`；
3. `start_console.bat`：启动控制台并自动打开 <http://127.0.0.1:8765/>（需要 `data/` 下的三套数据和已构建的 `web/dist/`）。

## 环境

- Windows 10/11 或 Linux，Python 3.12+，Node.js 18+
- Python 依赖固定在 `pyproject.toml` / `requirements.lock`
- ProVerif 2.05（仅形式化验证需要；Windows 官方二进制放在 `..\tools\proverif\proverif2.05\`）

```powershell
cd D:\比赛\privedge
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock   # 含测试依赖
$env:PYTHONPATH = (Get-Location).Path                          # 以下命令都在本目录执行
```

## 测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

## 演示控制台

```powershell
# 1. 构建前端（只需一次）
cd web; npm install; npm run build; cd ..

# 2. 启动后端（同时托管 web/dist）
$env:PYTHONPATH = (Get-Location).Path
.\.venv\Scripts\python.exe -m uvicorn privedge.server.app:app --port 8765
```

浏览器打开 <http://127.0.0.1:8765/>。前端开发模式：`cd web; npm run dev`（5173 端口，自动代理 `/api` 与 `/ws` 到 8765）。

| 视图 | 内容 |
|---|---|
| 总览 | 架构流程、核心指标（读取已登记运行目录）、定理与局限 |
| 冷启动预测 | 选新开站区域与参数，WebSocket 逐步推送真实执行事件，输出 Top-10 与三态 |
| 攻防实验室 | 10 种攻击，与无防御基线对比；一键巡检全部攻击 |
| 账本审计 | 哈希链、预算、密钥注册表、审计记录、篡改演练 |
| 实验中心 | 隐私—效用、Top-m、投毒攻防、权重劫持、ProVerif、开销，以及全部预注册文档 |

接口：`GET /api/datasets`、`POST /api/run`、`WS /ws/run`、`GET /api/ledger/{数据集}`、`POST /api/ledger/{数据集}/tamper-drill?seq=`、`GET /api/audit/{数据集}`、`GET /api/evidence`、`GET /api/prereg`。

目标区域的真实分布只在离线评估中打分，不进入网关与决策（`tests/test_core.py::test_inference_interfaces_cannot_receive_target_truth`）。

## 复现实验

```powershell
$env:PYTHONPATH = (Get-Location).Path
$py = ".\.venv\Scripts\python.exe"
foreach ($d in 'massive_steps','olist_brazil','meituan_trd') {
  & $py -m privedge.experiments.security_v1 --dataset $d --protocol v2          # SECURITY_V2
  & $py -m privedge.experiments.security_v3 --dataset $d                        # SECURITY_V3
  & $py -m privedge.experiments.security_v3 --dataset $d --tag v4 --seeds '601,709,811,907,1009'   # SECURITY_V4
  & $py -m privedge.experiments.utility_v1  --dataset $d                        # UTILITY_V1
}
& $py -m privedge.experiments.overhead_v1
& $py -m privedge.experiments.formal_v1          # 需要 ProVerif
& $py -m privedge.experiments.negative_check
```

`--v41-policy`（security_v1）与 `--clip-floor 0`（security_v3）用 v4.1 默认网关配置重跑，`compare_runs` 逐行比对：

```powershell
& $py -m privedge.experiments.compare_runs '<已登记运行ID>=<重跑运行ID>'
```

报告图表（读取已登记运行目录，输出 PNG + SVG 到 `..\competition_entry\docs\v4\figures\`）：

```powershell
& $py -m pip install -r requirements-figures.txt
& $py -m privedge.experiments.figures
```

已登记的运行目录见 `..\competition_entry\docs\v4\02_实验证据登记.md`。所有随机数由固定的 `SeedSequence` 派生，重跑结果逐行一致。

## 数据

`data/` 下是从原始数据导出的标准表（`privedge/adapters/export_*.py` 生成，记录源文件 SHA-256）。原始数据不随代码分发，请从官方来源下载，许可见 `THIRD_PARTY_LICENSES.md`：

- 美团 TRD：<https://zenodo.org/records/8025855>（DOI 10.5281/zenodo.8025855，CC BY 4.0）
- Olist：Kaggle `olistbr/brazilian-ecommerce`（CC BY-NC-SA 4.0，仅限非商业用途）
- Massive-STEPS：<https://github.com/cruiseresearchgroup/Massive-STEPS>

## 已知限制

- 哈希族为 splitmix64 备用实现（未安装 xxhash），与原始代码记录结果逐位一致。
- 每用户扰动耗时为批量向量化测得，不是移动端实测。
- TRD 的品类和商圈已匿名为编号；控制台中的区域拓扑是示意图，不是地理位置。
