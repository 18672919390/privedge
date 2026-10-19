# 许可原文与第三方通知归档

核对日期：2026-10-13。原文直接来自已安装的锁定分发包；数据许可文本来自官方公开地址。每个文件的哈希可在 FILE_MANIFEST.json 中核对。

- `FRONTEND_BUNDLE_NOTICES.txt`：随构建页面一起分发的完整合并文本，包含 7 个实际进入 bundle 的包及其包内许可/NOTICE。Vite 仅有浏览器辅助代码进入此范围。ECharts 同时保留 Apache LICENSE、NOTICE 与 d3 条款。
- `frontend/`：本机实际安装的 71 个 npm 包中的 71 份原文；开发工具的归档不表示它们全部进入浏览器。
- `python/`：requirements.lock 对应 31 包、39 份实际原文；虚拟环境与 wheel 不随本源码包分发。
- `data/`：TRD/Olist/Semantic Trails 的公开许可文本、ODbL、当前 Massive-STEPS 上游代码许可及数据署名说明；当前上游代码许可不是本项目冻结数据版本的证明。
- `inventory.json`：组件名、实际版本、锁信息、许可字段、文件哈希，以及未安装的 47 个平台可选 npm 锁项。
- `../../qa/b_retest_20261013/provenance/`：官方响应、字段提取、构建模块清单、逐文件匹配证据和未完成来源项。

本机的 @esbuild/darwin-arm64 与 @rollup/rollup-darwin-arm64 包内没有独立许可文件；保留此实际缺口，并归档同版本 esbuild / rollup 主包许可。这两个工具二进制不随本包分发；若以后捆绑它们，应按目标分发重新核对。

## 前端组件与分发角色

| 包 | 版本 | 包元数据许可 | 本轮角色 | 原文数 |
|---|---|---|---|---|
| @babel/code-frame | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/compat-data | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/core | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/generator | 7.29.8 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/helper-compilation-targets | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/helper-globals | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/helper-module-imports | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/helper-module-transforms | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/helper-plugin-utils | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/helper-string-parser | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/helper-validator-identifier | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/helper-validator-option | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/helpers | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/parser | 7.29.9 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/plugin-transform-react-jsx-self | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/plugin-transform-react-jsx-source | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/template | 7.29.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/traverse | 7.29.8 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @babel/types | 7.29.8 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @esbuild/darwin-arm64 | 0.21.5 | MIT | 安装/构建树；本轮 bundle 未观察到 | 0 |
| @jridgewell/gen-mapping | 0.3.13 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @jridgewell/remapping | 2.3.5 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @jridgewell/resolve-uri | 3.1.2 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @jridgewell/sourcemap-codec | 1.6.0 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @jridgewell/trace-mapping | 0.3.31 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @rolldown/pluginutils | 1.0.0-beta.27 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @rollup/rollup-darwin-arm64 | 4.63.5 | MIT | 安装/构建树；本轮 bundle 未观察到 | 0 |
| @types/babel__core | 7.20.5 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @types/babel__generator | 7.27.0 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @types/babel__template | 7.4.4 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @types/babel__traverse | 7.28.0 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @types/estree | 1.0.9 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @types/prop-types | 15.7.15 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @types/react | 18.3.31 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @types/react-dom | 18.3.7 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| @vitejs/plugin-react | 4.7.0 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| baseline-browser-mapping | 2.11.26 | Apache-2.0 | 安装/构建树；本轮 bundle 未观察到 | 1 |
| browserslist | 4.29.2 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| caniuse-lite | 1.0.30001813 | CC-BY-4.0 | 安装/构建树；本轮 bundle 未观察到 | 1 |
| convert-source-map | 2.0.0 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| csstype | 3.2.3 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| debug | 4.4.3 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| echarts | 5.6.0 | Apache-2.0 | 浏览器 bundle | 3 |
| electron-to-chromium | 1.5.440 | ISC | 安装/构建树；本轮 bundle 未观察到 | 1 |
| esbuild | 0.21.5 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| escalade | 3.2.0 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| fsevents | 2.3.3 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| gensync | 1.0.0-beta.2 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| js-tokens | 4.0.0 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| jsesc | 3.1.0 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| json5 | 2.2.3 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| loose-envify | 1.4.0 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| lru-cache | 5.1.1 | ISC | 安装/构建树；本轮 bundle 未观察到 | 1 |
| ms | 2.1.3 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| nanoid | 3.3.19 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| node-releases | 2.0.57 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| picocolors | 1.1.1 | ISC | 安装/构建树；本轮 bundle 未观察到 | 1 |
| postcss | 8.5.28 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| react | 18.3.1 | MIT | 浏览器 bundle | 1 |
| react-dom | 18.3.1 | MIT | 浏览器 bundle | 1 |
| react-refresh | 0.17.0 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| rollup | 4.63.5 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| scheduler | 0.23.2 | MIT | 浏览器 bundle | 1 |
| semver | 6.3.1 | ISC | 安装/构建树；本轮 bundle 未观察到 | 1 |
| source-map-js | 1.2.1 | BSD-3-Clause | 安装/构建树；本轮 bundle 未观察到 | 1 |
| tslib | 2.3.0 | 0BSD | 浏览器 bundle | 1 |
| typescript | 5.9.3 | Apache-2.0 | 安装/构建树；本轮 bundle 未观察到 | 1 |
| update-browserslist-db | 1.3.3 | MIT | 安装/构建树；本轮 bundle 未观察到 | 1 |
| vite | 5.4.21 | MIT | 浏览器 bundle | 1 |
| yallist | 3.1.1 | ISC | 安装/构建树；本轮 bundle 未观察到 | 1 |
| zrender | 5.6.1 | BSD-3-Clause | 浏览器 bundle | 1 |

## Python 安装依赖

| 包 | 版本 | 许可原文数 |
|---|---|---|
| annotated-doc | 0.0.5 | 1 |
| annotated-types | 0.8.0 | 1 |
| anyio | 4.15.1 | 1 |
| cffi | 2.1.1 | 1 |
| click | 8.5.0 | 1 |
| colorama | 0.4.6 | 1 |
| cryptography | 50.0.1 | 3 |
| fastapi | 0.141.1 | 1 |
| h11 | 0.16.0 | 1 |
| httpcore2 | 2.13.1 | 1 |
| httpx2 | 2.13.1 | 1 |
| idna | 3.20 | 1 |
| iniconfig | 2.3.0 | 1 |
| numpy | 2.3.5 | 4 |
| packaging | 26.3 | 3 |
| pandas | 3.0.1 | 1 |
| pluggy | 1.6.0 | 1 |
| pycparser | 3.0 | 1 |
| pydantic | 2.13.5 | 1 |
| pydantic_core | 2.46.5 | 1 |
| Pygments | 2.21.0 | 1 |
| pytest | 9.1.1 | 1 |
| python-dateutil | 2.9.0.post0 | 1 |
| six | 1.17.0 | 1 |
| starlette | 1.7.0 | 1 |
| truststore | 0.10.4 | 1 |
| typing-inspection | 0.4.4 | 1 |
| typing_extensions | 4.16.0 | 1 |
| tzdata | 2026.4 | 2 |
| uvicorn | 0.54.0 | 1 |
| websockets | 17.1 | 1 |

包内原文保留全部随附条款；NumPy、pandas 等不能只用主项目许可证简称概括。许可证清单与作者贡献声明是两类不同证据，尚待团队确认项见上级 THIRD_PARTY_LICENSES.md。
