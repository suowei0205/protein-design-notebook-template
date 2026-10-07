# SR56 六分支 example

来源：`SR56_六分支_独立Notebook_清晰目录与反馈包_2026-10-07`，原资源SHA-256见 `PROVENANCE.json`。六份科学notebook和示例输入来自已核验发布，仓库构建只更新notebook资源pin；原参数、seed、排名、有效性判断、baseline与全循环最佳保持。

| 分支 | Notebook |
|---|---|
| A minibinder | [SR56_A_minibinder](SR56_A_minibinder/SR56_A_minibinder.ipynb) |
| A short peptide | [SR56_A_short_peptide](SR56_A_short_peptide/SR56_A_short_peptide.ipynb) |
| B minibinder | [SR56_B_minibinder](SR56_B_minibinder/SR56_B_minibinder.ipynb) |
| B short peptide | [SR56_B_short_peptide](SR56_B_short_peptide/SR56_B_short_peptide.ipynb) |
| C minibinder | [SR56_C_minibinder](SR56_C_minibinder/SR56_C_minibinder.ipynb) |
| C short peptide | [SR56_C_short_peptide](SR56_C_short_peptide/SR56_C_short_peptide.ipynb) |

在对应设计文件夹打开notebook，启动单元填写 `RUN_LABEL`。日常计算依赖和权重须已存在；开发kernel依赖并不提供科学引擎。新资源身份和已发布旧断点不兼容，新建运行。维护共享源码在根 `runtime/`，从仓库根构建，禁止直接修改resources ZIP和pin。

原发布曾通过六分支CPU假引擎和启动/反馈验收，本仓库保留科学来源指纹；当前CI另行检查共享源码、资源和启动，不声称重跑科学GPU或远程状态。未附带历史运行、TOP10对象、模型权重或实验有效性证明。
