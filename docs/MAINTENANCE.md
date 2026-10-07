# 维护与接入说明

## 单一编辑入口

| 内容 | 编辑位置 | 随后执行 |
|---|---|---|
| 可读目录、严格身份与资源核验 | `runtime/standalone_runtime.py` | build → verify → kernel |
| 观测、反馈、校验与合并 | `runtime/sr56_feedback.py` | build → verify → kernel |
| 可信离线页面 | `runtime/assets/` | build → verify；浏览器验证相关交互 |
| 空白模板 | `template/DesignProject/DesignProject.ipynb` | build → verify → kernel |
| SR56科学流程 | `examples/SR56/*/*.ipynb` | 更新版本/来源证据，科学审查与适用CPU/GPU验证 |
| SR56输入 | `examples/SR56/inputs/` | 更新来源、编号和版本；新运行，不接管旧断点 |
| 入口/命名空间 | 对应 `manifest.json` | build → verify → kernel |

`python scripts/build.py` 用固定ZIP元数据从源码重建资源包，并更新每个notebook唯一的资源pin。`--check` 重新计算并逐字节比较，不修改文件；提交源码而不重建会使CI失败。`manifest.json` 是入口配置，包内 `NOTEBOOKS.json`、`RUNTIME_FILES.json` 和 `RESOURCE_MANIFEST.json` 为生成文件。两个分发包都必须包含当前共享源码，禁止只改某份ZIP。

## 空模板接入真实计算

默认分支 `template_project` 和 `design_template_v1` 是已注册入口，不推断 helix 或 binder 类别。输入、参数和预算留空就是未知；`NOT_RUN` 表示尚未执行，初始化或导出不能更改为成功。真正接入科学引擎后，在对应单元实现：

1. 显式核验靶标序列、结构、chain、编号、构象与设计任务。
2. 在完整科学配置中记录seed、预算、有效性规则和版本，并将外部输入文件内容的 SHA-256 纳入配置或 target，再调用 `_feedback.configure` 冻结身份；恢复前重新计算并核验输入散列。空模板默认只冻结填写值和文件路径，同路径文件的字节变化不会自动被发现。仅 `RUN_LABEL` 和部署/恢复设置身份中性；不要把科学参数加入 `LAUNCH_VALUES`。
3. 原件落 `main/refine` 阶段目录；排名到 `rankings`，审计到 `reports/main` 或 `reports/refine`，曲线到 `svg`。
4. 完成数由原子阶段回执和工件散列证明。观测事件本身不算已完成；所有候选（含无效输出）保留模型级证据。
5. 真实结束时显式选择 `COMPLETED`、`FAILED` 或 `INTERRUPTED`；空模板继续用 `NOT_RUN`。`COMPLETED` 仅是计算状态，不等于结合/科学有效性。

当前反馈采集器识别RFD3/MPNN/RF3回执协议，不是任意引擎插件框架。SR56 notebook 的 `_ckpt_save`、`_feedback_model`、`_feedback_pair`、baseline和beam记录是可执行参考；接入其他流程时先定义并核验转换，不能伪造该协议的完成数。

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
- 每次改变runtime/notebook后执行build和verify；改变启动/结束行为后执行真实kernel检查；改变页面后另做离线浏览器检查。科学参数/引擎接口改变需要额外CPU或科学环境验收，不能把本CI当GPU证明。

## 常见情况

资源pin不匹配：重新构建正确版本，不手改pin绕过检查。恢复被拒绝：先核验身份差异，科学参数/源码/资源变化时新建运行。活动kernel占用：由使用者结束其kernel，不要删除锁文件抢占。反馈结构缺失：查看补取清单；精选结构包不能提供全量续跑材料。ZIP无SHA旁文件：导出过程未完整交付，先校验内部清单并重新导出新快照，不宣称双文件事务。
