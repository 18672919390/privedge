# 第三方数据、工具与依赖许可清单

PrivEdge包含团队实现及注明来源的第三方移植代码。下列数据、代码、工具与依赖分别记录来源和许可；标准表及运行时的具体分发范围以程序包清单为准。

## 1 数据集

| 数据 | 来源 | 许可 | 使用方式与署名要求 |
|---|---|---|---|
| 美团 TRD（Takeout Recommendation Dataset） | Zenodo 记录 8025855，DOI [10.5281/zenodo.8025855](https://doi.org/10.5281/zenodo.8025855)，上传者 Liu Yijian（北京邮电大学） | CC BY 4.0 | 主场景数据。报告与演示中注明：“数据来自美团 TRD（Zenodo 8025855），CC BY 4.0”，并说明我们做了哪些处理（按商圈聚合首单品类、导出标准表）。Zenodo 页面没有说明美团对上传者的授权，报告中如实说明；可选：邮件向上传者确认 |
| Olist Brazilian E-Commerce Public Dataset | Kaggle `olistbr/brazilian-ecommerce` | CC BY-NC-SA 4.0 | 对照数据，仅用于非商业的竞赛与研究；署名 Olist；衍生的标准表以相同许可对待 |
| Massive-STEPS | <https://github.com/cruiseresearchgroup/Massive-STEPS>（基于 Semantic Trails，原始数据 CC0；整理代码 Apache-2.0） | 见官方仓库 | 压力测试数据；按官方要求引用 Massive-STEPS 论文与 Semantic Trails |

## 2 工具

| 工具 | 版本 | 许可 | 说明 |
|---|---|---|---|
| ProVerif | 2.05（官方 Windows 二进制） | GNU GPL v2（随发行包的 `LICENSE`） | 只作为外部验证工具调用，不链接进 PrivEdge；作品包内不附带其二进制 |

## 3 Python 依赖（版本见 `requirements.lock`）

| 包 | 许可 |
|---|---|
| numpy | BSD-3-Clause |
| pandas | BSD-3-Clause |
| cryptography | Apache-2.0 或 BSD-3-Clause |
| fastapi | MIT |
| starlette | BSD-3-Clause |
| uvicorn | BSD-3-Clause |
| pydantic / pydantic_core | MIT |
| anyio | MIT |
| h11 | MIT |
| websockets | BSD-3-Clause |
| pytest（测试） | MIT |
| httpx2 / httpcore2（测试） | BSD-3-Clause |

## 4 前端依赖（版本见 `web/package-lock.json`）

| 包 | 许可 |
|---|---|
| React / React DOM | MIT |
| Apache ECharts | Apache-2.0 |
| Vite / @vitejs/plugin-react | MIT |
| TypeScript | Apache-2.0 |

## 5 算法与文献

OLH方法来自已有论文；`privedge/research_core/ldp_protocols.py`文件头明确标记从Tianhao Wang维护的[LDP_Protocols](https://github.com/vvv214/LDP_Protocols)移植，不能笼统声称全部按论文独立实现。上游MIT许可原文、署名和本轮固定核对快照保留在`licenses/upstream_ldp_protocols/`，详见其中ATTRIBUTION.txt。本轮核对commit不是对当时移植版本的认定；历史版本或来源包记录仍待提供者确认。未改动保留研究代码的字节。

MGA生成器为本项目实现的有限随机搜索构造，论文作为攻击模型来源；经典坐标截尾均值是本地Top-m基线适配，不能继承外部论文的完整定理。方法出处见报告参考文献，已有方法与本项目组合设计分别说明。


## B 候选许可归档的接收

2026-10-15 收到原受测候选 9cbc4425… 的完整 120 文件许可目录，原字节存于 `licenses/b_candidate_20261013/`（119 项载荷及其清单）。其中包含完整前端 notices、数据署名及许可原文；历史安装清单描述 B 的 Mac 环境，不作为当前 Windows 运行时清单。当前便携包另附自己的 dependency_inventory.json 与运行时许可。B 的来源证据与环境记录保存在接收档案，不将含设备身份的 QA 原件混入匿名报告。上游 OLH 移植来源仍按本文件与 licenses/upstream_ldp_protocols/ 单独署名。
