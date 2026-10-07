# 维护说明

## 单一编辑入口

| 内容 | 编辑位置 | 随后执行 |
|---|---|---|
| 可读目录、严格身份与资源核验 | `runtime/standalone_runtime.py` | build → verify → kernel |
| 通用靶标预检/编号映射 | `runtime/target_input.py` | build → target_input_check → pipeline_cpu → verify |
| 观测、反馈、校验与合并 | `runtime/sr56_feedback.py` | build → verify → kernel |
| AF3显示名与命名规则 | `runtime/assets/af3_names.js`、`docs/AF3_NAMING.md` | build → top10_demo → verify；浏览器核对当前模型/榜单/baseline |
| TOP10合成演示 | `scripts/build_top10_demo.py`、`examples/top10-demo/index.html`、`viewer_app.js` | 生成器 → top10_demo；浏览器及公开数据边界检查 |
| 可信离线页面 | `runtime/assets/` | build → verify；浏览器验证相关交互 |
| 完整空白模板 | `template/DesignProject/DesignProject.ipynb` | build → verify → kernel |
| SR56科学流程 | `examples/SR56/*/*.ipynb` | 更新版本/来源证据，科学审查与适用CPU/GPU验证 |
| SR56输入 | `examples/SR56/inputs/` | 更新来源、编号和版本；新运行，不接管旧断点 |
| 入口/命名空间 | 对应 `manifest.json` | build → verify → kernel |

`python scripts/build.py` 用固定ZIP元数据从源码重建资源包，并更新每个notebook唯一的资源pin。`--check` 重新计算并逐字节比较，不修改文件；提交源码而不重建会使CI失败。`manifest.json` 是入口配置，包内 `NOTEBOOKS.json`、`RUNTIME_FILES.json` 和 `RESOURCE_MANIFEST.json` 为生成文件。两个分发包都必须包含当前共享源码，禁止只改某份ZIP。

## 模板使用与科学流程维护

模板已经实现单链标准蛋白binder的RFD3→MPNN→RF3→refine全流程。普通使用者只改第4/8/9三个参数单元；不填写计算代码。入口为 `template_project / design_template_pipeline_v2`，不接管旧v1骨架断点。

第8单元输入本地PDB/mmCIF、author链、可选author残基范围、model/altloc及期望序列。`target_input.py`只从一次读取的源字节解析：PDB author字段，mmCIF `use_author_fields=True`；默认model1和每残基最高occupancy，允许改为first。保留源(chain,res_id,ins_code)映射，内部规范化为A1..N；水/配体排除，非标准/modified peptide、编号缺口、缺或重复N/CA/C/O、非有限坐标与无法定义对齐参考系的退化几何拒绝。范围端点必须存在，不补缺失残基。

输入源SHA、选取规则、实际序列SHA、规范化CIF SHA和完整编号映射进入target身份；恢复前重新准备并对比已冻结身份与工件；阶段读取前及计算指纹处再次核对源字节、准备CIF和provenance。不能手改hash绕过错误。source path也是参数，移动源文件或改内容需新运行。仅 `RUN_LABEL` 和部署/恢复设置身份中性，不把科学参数加入 `LAUNCH_VALUES`。

原件落main/refine对应阶段；排名在rankings，审计在reports/main或refine，曲线在svg，回执在checkpoints。完成数由原子阶段回执及工件散列证明，观测事件本身不算完成。未填靶标在科学导入前拒绝，保存NOT_RUN；完整执行结束为COMPLETED，失败/中断由实际状态记录。COMPLETED仅是计算状态，不等于结合或科学有效性。

共享采集器识别RFD3/MPNN/RF3回执协议。模板已经直接产生此协议的主/refine回执、模型证据、baseline与beam记录；它不是任意引擎插件框架。若维护者新增motif/ligand/多链等其他科学任务，需先定义范围和验证转换，不伪造完成数；普通用户不需要这样接入。

| 回执路径 | 典型key / 身份 |
|---|---|
| `checkpoints/main/checkpoint.json` | `rfd3_batch_N`、`mpnn_design_N` |
| `checkpoints/main/rf3/complete.json` | `rf3_N_N`（汇总） |
| `checkpoints/main/rf3/dN_sN/complete.json` | `rf3_N_N` 或 `rf3` |
| `checkpoints/refine/refine_complete.json` | `DN_CN_PN_rfd3`、`DN_CN_PN_KN_mpnn`、`DN_CN_round` |
| `checkpoints/refine/rf3/DN_CN_PN_KN_SN/complete.json` | `rf3`，父目录保留候选身份 |

每条回执含 `schema`（与科学配置 `CACHE_SCHEMA` 相同）、`run_namespace`、`ts`、`payload`、`files`（path + sha256）。RF3 payload保留 `input_seq` 和完整 `models`（mi/cif/conf）；模型评估绑定坐标及confidence散列，不能依靠文件数量、mtime或日志猜测。阶段元信息不能通过搬目录改变模型身份。显示页面下载引用统一使用run根相对路径，再按页面位置解析。

## 科学与发布版本

`PROVENANCE.json` 固定SR56已验收来源的单元/科学指纹。本版只变更资源pin，不修改科学代码和单元metadata。若要改SR56科学流程，先讨论范围、科学参数与判据，记录新来源版本和验证证据；不能为了测试通过自动覆盖来源指纹。资源、运行代码或环境改变时，新建运行；旧断点不迁移。

构建和反馈布局遵循显式版本：运行身份v3、反馈布局v2，旧v1反馈只读兼容；现有模块名及schema保留历史名称。新增版本须同步写出、读取、校验、导入、监视器和相对路径检查，未知版本必须拒绝。

## Git与审查

- 修改前查看 `git status`；分支修改、审查差异，再提交。不要改写版本历史或强制推送。
- 日常新项目保存在默认忽略的 `projects/`。若项目科学notebook需独立版本控制，放入另一个私有仓库或显式审查后调整忽略规则；不要强制添加整个运行目录。
- 不提交凭据、运行日志、私有绝对路径、科学权重或执行输出。资源ZIP只允许源码、可信页面资产、许可、示例输入和生成清单。
- `.github/workflows/check.yml` 只有push/PR触发，权限只读；不定时运行、不远程推理。固定Actions提交SHA；升级时先核验官方源提交再更新。
- 每次改变runtime/notebook后执行build和verify；改通用靶标/科学循环另跑target_input_check和pipeline_cpu；改变启动/结束行为后执行真实kernel检查；改变页面后另做离线浏览器检查。科学参数/引擎接口改变需要额外CPU或科学环境验收，不能把本CI当GPU证明。

## 常见情况

资源pin不匹配：重新构建正确版本，不手改pin绕过检查。恢复被拒绝：先核验身份差异，科学参数/源码/资源变化时新建运行。活动kernel占用：由使用者结束其kernel，不要删除锁文件抢占。反馈结构缺失：查看补取清单；精选结构包不能提供全量续跑材料。ZIP无SHA旁文件：导出过程未完整交付，先校验内部清单并重新导出新快照，不宣称双文件事务。

合成演示生成器只读取固定合成参数，`--check` 在临时目录重建并逐字节核对。修改手写HTML/查看器不直接修改生成数据；生成器变更后重建并提交`GENERATED.json`及对应数据。禁止以真实结果作为演示fixture，禁止将本地检查记录、截图或私有路径复制到公开仓库。
