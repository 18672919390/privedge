# 第三方数据、工具与依赖许可清单

PrivEdge 代码为本队自有原始代码。下列第三方数据、工具与依赖按原许可使用；原始数据和第三方二进制不随作品源码再分发。

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

OLH 频率估计协议、最大增益投毒攻击（MGA）等算法按其原始论文独立实现，出处见报告参考文献。报告不复制往届作品的内容、图表或措辞。
