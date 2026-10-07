# TOP10 结构查看器 · SYNTHETIC DEMO

本演示沿用已有 TOP10 查看器的 HTML/CSS 布局与交互：主阶段榜、全循环最佳榜、固定 baseline、四轮路径、RF3 模型切换、RFD3/MPNN 阶段、双视窗、置信度着色、序列/结构下载及 AF3 验证名称复制。

**全部候选 ID、序列、坐标、置信度、指标和排名均为程序化合成数据。没有真实设计结果、真实回传包或 GPU 推理。** 合成数值只演示界面；接触、RMSD、score 等不是从这些坐标测得的科学指标。这里的“有效模型”只表示演示结构完整，不代表科学有效性。

下载/克隆整个仓库后直接打开本目录的 [index.html](index.html)。页面离线运行，通过相对路径复用 `runtime/assets` 中的 3Dmol 和字体，不能仅下载 HTML 单文件。GitHub 文件预览不执行 HTML。无需服务器、API、账号或外部网络请求；无 WebGL 时仍可阅读与下载。

维护生成数据：

```bash
python scripts/build_top10_demo.py
python scripts/build_top10_demo.py --check
python tests/top10_demo.py
```

`index.html`、`viewer_app.js` 和本说明是可编辑源码；`data/`、`objects/`、`index.json`、CSV、FASTA 与 `GENERATED.json` 由固定公式生成，禁止将真实文件复制进去。生成器采用现有 CPU 假引擎夹具的 toy helix 公式，只依赖标准库，不读取研究输入。`GENERATED.json` 保存生成文件清单与 SHA-256，`--check` 会在临时目录重新生成并逐字节比较，且拒绝生成目录中的额外文件。

AF3 名称使用 `SYNTHETIC demo-protein demo-region A-helix DEMO-NO-UNIPROT 1-11 binder-rank…-{合成candidate_id}`；baseline 始终对应原主榜，当前路径随选中的设计项/模型更新。完整规范见 [AF3_NAMING.md](../../docs/AF3_NAMING.md)。合成 AF3 名称用于测试复制功能，不是验证任务或真实 accession。

公共资产许可见 [THIRD_PARTY_NOTICES.md](../../THIRD_PARTY_NOTICES.md)。本演示没有 Service Worker、存储缓存、遥测或远程连接。真实研究数据应留在本地或独立私有仓库，不能先提交再删除。
