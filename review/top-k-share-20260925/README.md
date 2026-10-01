# 多源 LDP 摘要的目标 Top-k 迁移实验

整理日期：2026-09-25。此包用于代码交流与复现，不含原始数据集、事件缓存、Python 运行时和重复试跑结果。解压后请先进入本 README 所在目录，再执行命令。

## 研究任务与当前状态

目标服务器只使用源服务器既有的 LDP Top-m 发布摘要（item、频率估计、方差）及可用的公开目标上下文，预测目标自身分布的 Top-k。目标用户事件和真实频率仅用于离线评价。候选覆盖率是当前候选集合下的 Recall 上限，Oracle 平均融合的 Recall 不是上限。

本包保留了不同阶段的方法，不应混为一个已经验证成功的模型：

- `fusion.py`：直接平均、服务器级/项目级加权、截断感知及相关基线。未发布项以其带噪估计低于发布阈值的信息处理，不直接认为真实频率为零；当前截断似然为近似。
- `censor_estimator.py`：独立的凸区间估计器。
- `two_stage_transfer.py`：探索性的“先源重建，再按目标上下文拟合源混合权重”。第二阶段仍为服务器级混合权重。尚未证实重建在最终 Top-k 上稳定优于直接摘要融合。
- Yelp 六城市结果验证的是 `fusion.py` 中的方法，**不是**两阶段模型的新验证。

部分模拟条件验证了目标上下文加权机制，但不支持所有新方法都有优势。Yelp 六城市、OLH、正确目录上下文下：每源 2,000 用户时平均/截断感知 Recall 约 0.417/0.457；10,000 用户时约 0.663/0.673。2,000 用户时，候选内目录排序基线约 0.567，高于截断感知。现有真实数据结果属于探索性结果，不能声称稳定优越或独立留出确认。

Books 和 Yelp 均采用元数据类别域与固定哈希单类别编码，每个用户在全部年份/城市中仅保留一个固定哈希事件。上下文来自现有目录快照，未证实其在历史目标年份已公开。正向评论事件分布不能等同于全体居民消费偏好。

## 安装与快速检查

推荐 Python 3.11。外部依赖仅为 NumPy、xxhash；后者影响 OLH 的哈希实现，应安装以接近历史运行环境。

```sh
python -m pip install -r requirements.txt
python quick_check.py
python -m unittest discover -s tests -v
```

`quick_check.py` 使用小规模模拟数据，检查主线及两阶段路径能否运行，不用于证明性能。原机器版本记录见 `ENVIRONMENT.txt`，本次打包验证记录见 `VERIFICATION.md`。不同依赖版本/哈希实现可能使随机结果变化；本包不附带平台绑定的 Python 安装目录。

## 从哪里看代码

| 路径 | 内容 |
|---|---|
| `problem_definition.py` | 方法可见信息的边界 |
| `simulation.py`、`ldp_protocols.py`、`pem.py` | 模拟分布、LDP 发布机制 |
| `fusion.py`、`competitive_baselines.py` | 原主线融合方法与竞争基线 |
| `experiment.py`、`metrics.py` | 实验调度、评价与候选上限 |
| `censor_estimator.py`、`adaptive_selection.py` | 凸估计器与选源模块 |
| `two_stage_transfer.py` | 两阶段探索模型 |
| `experiments/G1_*.py` 至 `G8_*.py` | 基线、协议、上下文、异构、鲁棒性、候选与敏感性实验 |
| `experiments/validation/two_stage_*.py` | 两阶段模拟、Books、模型错配消融 |
| `experiments/validation/amazon_books_categories.py` | 当前 Books 类别实验与数据编码 |
| `experiments/validation/yelp_categories_v3.py` | 当前 Yelp 跨城市类别实验 |
| `tests/` | 单元测试与信息边界检查 |
| `docs/` | 方法定义、局限与结果报告，索引见 `docs/README.md` |
| `outputs/` | 精选历史指标、配置及报告；不含原始数据或事件缓存 |

## 运行模拟实验

小规模主线示例（与历史正式结果配置不同）：

```sh
python run_experiment.py --mechanisms OLH --rounds 1 --users-per-server 200 --output outputs/new_smoke
python run_groups.py
python run_groups.py G3 --dry-run
```

`run_groups.py` 仅保留 G1–G8；G17 对应的旧 Yelp 入口已从分享包目录表移除。G1 使用固定的正式配置，运行可能较久，不作为快速检查命令。

两阶段模拟完整配置为 20 个种子、6 个源、每源 5,000 用户、两个目标：

```sh
python experiments/validation/two_stage_synthetic.py
```

只运行重建消融的模拟部分（无需 Books 数据）：

```sh
python -c "from pathlib import Path; from experiments.validation.two_stage_reconstruction_ablation import run_synthetic; out=Path('outputs/new_reconstruction_synthetic'); out.mkdir(parents=True,exist_ok=True); run_synthetic(out)"
```

该消融脚本的默认主入口会同时运行模拟和 Books，必须先准备 Books 缓存。运行正式脚本可能覆盖同名 `outputs` 历史文件；需要保留附带结果时，请先复制解压目录。

## 真实数据准备

数据由接收者自行取得；以下是现有解析器所需的文件布局。不同版本或字段不同的数据不能直接视为同一实验。

```text
data/
  Amazon/Amazon Books Reviews/
    Books_rating.csv
    books_data.csv
  Yelp Dataset/
    yelp_academic_dataset_business.json
    yelp_academic_dataset_review.json
```

Books 为 Amazon Books Reviews（评分约 300 万行）的双 CSV 版本：

- `Books_rating.csv` 必需列：`Id`、`Title`、`User_id`、`review/time`（Unix 秒）、`review/score`。
- `books_data.csv` 必需列：`Title`、`categories`（可由 Python 字面量解析的字符串列表）。按标题匹配，类别冲突的同名标题会排除。

Yelp 为 Yelp Open Dataset 的逐行 JSON：

- business 必需字段：`business_id`、`city`、`state`、`categories`（逗号分隔字符串）。
- review 必需字段：`user_id`、`review_id`、`business_id`、`stars`、`date`。

只重建缓存，不运行融合比较：

```sh
python prepare_data.py books
python prepare_data.py yelp
```

该辅助入口直接调用原预处理函数：Books 写入 `outputs/amazon_books_categories_v2/prepared.json`；Yelp 写入 `outputs/data_suitability_audit/audit.json`。扫描全量数据可能较慢且占用较多内存。请勿先按目标城市/年份裁剪原始评论，否则会改变全局每用户单事件选择。

准备 Books 后运行：

```sh
python experiments/validation/amazon_books_diagnostic.py
python experiments/validation/analyze_books_diagnostic.py
python experiments/validation/two_stage_books.py
python experiments/validation/analyze_two_stage.py
python experiments/validation/two_stage_reconstruction_ablation.py
python experiments/validation/report_reconstruction_ablation.py
```

`analyze_two_stage.py` 同时读取模拟和 Books 结果；包内附带两者的历史结果，重新分析新实验时应先完成对应实验。

准备 Yelp 后运行：

```sh
python experiments/validation/yelp_categories_v3.py --output-dir outputs/yelp_categories_v3_six
python experiments/validation/report_yelp_categories_v3.py
```

默认六城市：Philadelphia PA、Tucson AZ、Tampa FL、Indianapolis IN、Nashville TN、New Orleans LA，轮流作为目标，其余五城为源。使用 5 个种子、每源 2,000/10,000 用户、ε=2、k=10、m=20。交换上下文取固定源顺序中的第一座城市，并非全部外地目录的平均。

## 随包结果与整理范围

- `outputs/formal_baseline_comparison`：主线模拟基线比较的汇总和逐轮指标。
- `outputs/amazon_books_categories_v2`、`amazon_books_diagnostic`：Books 类别实验、候选覆盖和噪声诊断。
- `outputs/two_stage_synthetic`、`two_stage_books`、`two_stage_reconstruction_ablation`：两阶段探索与包括负面结果在内的重建消融。
- `outputs/yelp_categories_v3_six`：修正后的六城市正式记录；不附早期十二城市试跑。

历史 manifest 中的原机器路径、版本和哈希按原样保留，是结果来源记录，不是接收者必须存在的路径。历史文档里的 `.runtime/python/python.exe` 在本包中请替换为 `python`。部分文档会提及未附带的历史诊断目录。

排除了旧版 Amazon 图书/手机 ID 脚本、旧 Yelp 城市内去重版本、一次性重复诊断、所有数据和事件缓存、运行日志、字节码及虚拟环境。必要的验证依赖保留：例如 G1 依赖 `desktop_validation.py`，测试依赖方差校准和独立种子辅助模块。

实验算法源文件按原样复制；仅分享包的 `experiments/catalog.py` 移除了已排除的 G17 入口，并补充本说明、数据准备及快速检查入口。`PACKAGE_MANIFEST.json` 列出每个文件的 SHA-256、大小及其是否与工作区原文件一致。
