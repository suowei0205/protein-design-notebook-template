# Changelog

## 0.2.0 — 2026-10-07

- 空白模板改为完整36单元binder流程；只修改启动、靶标与研究参数，不再留main/refine实现占位。
- 通用PDB/mmCIF靶标预检、author编号/insertion映射与输入字节身份；移除SR56固定长度和靶标metadata。
- 新模板命名空间 `design_template_pipeline_v2`；未填靶标明确停止并保存NOT_RUN，不接管旧骨架断点。
- SR56科学单元和来源指纹保持不变；新增靶标边界及CPU假引擎循环核验。

## 0.1.0 — 2026-10-07

- 通用空白 notebook、严格运行身份与 NOT_RUN 反馈。
- SR56 六分支 example；科学单元、参数与选优逻辑保持原版。
- 共享 runtime 源码、确定性资源构建、维护文档和无 GPU CI。
