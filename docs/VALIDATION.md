# 验证记录 — 2026-10-07

验证范围为模板骨架、SR56来源一致性、共享资源、反馈与仓库维护；不包含真实科学引擎、模型权重、GPU、性能、远程任务或实验有效性。

| 检查 | 当前实证 |
|---|---|
| 确定性构建 | 两包源码、资源清单、notebook pin逐字节核对通过；重复构建 `--check` 通过 |
| Notebook来源 | 7份无输出notebook、144个代码单元语法通过；SR56仅资源pin变更，其他文档/metadata/科学单元来源指纹一致 |
| 空白模板 | 真实目录、完整配置冻结、报告与监视页、反馈快照；状态保持NOT_RUN，0候选，不推断helix/binder类别 |
| 恢复 | 同身份续跑通过；改参数、冻结notebook损坏、kernel占用、非法输出与非法标签拒绝 |
| 反馈协议 | v1/v2读取、校验与合并；连续/并发快照、散列、SVG原字节、路径与符号链接拒绝、canonical碰撞拒绝、导入活动内容排除通过 |
| 实际kernel | 空模板完整执行＋6个SR56 bootstrap，总计7个ipykernel；全部NOT_RUN；未导入Torch/RFD3/MPNN/RF3 |
| 离线浏览器 | 空模板报告在1440/768/390宽度显示1个模板分支，NOT_RUN与0候选；监视页NOT_RUN；无页面异常、外部请求、缺失文件链接或横向溢出。无历史视觉基线，视觉回归为INCONCLUSIVE；未做完整可访问性审计 |
| 输入来源 | SR56两份示例输入的固定集合与原发布资源中的SHA-256一致；空模板外部结构文件内容散列须在接入计算时显式记录和核验 |
| Git范围 | 来源/manifest/资源包/notebook应纳入；projects/run/缓存/权重/.env应排除；双向规则通过 |
| 原件 | 本地已验收SR56发布8文件散列保持不变；本仓库为独立副本 |

可重复验证：

```bash
python tests/verify.py
python tests/kernel_smoke.py
```

GitHub Actions另在push/PR执行相同命令；远程状态以当前commit的Actions页面为准。测试成功仅表示列出的机械与范围验证有效，不表示绑定、力选择性或实验成功。原发布的42CPU用例/84循环验收属于来源发布，本仓库CI不重跑科学流程。

主决策与本地独立重审：gpt-6.1-sol / openai，完整模型来自会话metadata，backend未提供；Chat未调用。外部Broker：opencode_go / deepseek-flash / deepseek-v4.1-flash / app_server，只读通用规则红队评议，未发送原件。控制器独立核验构建、差异、测试与发布结果；评议不能替代证据。
