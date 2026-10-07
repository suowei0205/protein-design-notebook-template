# 验证记录 — 2026-10-07

验证范围为完整通用binder模板、SR56来源一致性、共享资源、反馈、AF3显示命名、合成TOP10演示与仓库维护；不包含真实科学引擎、模型权重、GPU、性能、远程任务或实验有效性。

| 检查 | 当前实证 |
|---|---|
| 确定性构建 | 两包源码、资源清单、notebook pin逐字节核对通过；重复构建 `--check` 通过 |
| Notebook来源 | 7份无输出notebook、161个代码单元语法通过；SR56仅资源pin变更，其他文档/metadata/科学单元来源指纹一致 |
| 完整模板 | 36单元保持SR56 A的身份/顺序/折叠；仅4/8/9为参数入口，主阶段及refine计算代码已填好。未配置靶标时在科学导入前拒绝并导出NOT_RUN |
| 靶标输入 | 41个合成检查：PDB/mmCIF、非32残基靶标、author范围/model/altloc/insertion映射、主链/序列/坐标、源字节和冻结证据、符号链接及64MiB边界；范围外modified残基不阻断所选标准片段 |
| CPU计算流程 | 实际交付单元搭配假引擎，5场景：三轮refine、baseline最佳、refine无有效输出、主阶段无有效输入、中断与严格恢复；分别90/90/18/0/90个RF3序列对、360/360/72/0/360个模型。完成缓存重开不构造引擎，恢复与不中断的全部数值审计/最终选择一致 |
| 计算前输入冻结 | 预检后修改源文件、prep/target.cif或provenance均在阶段指纹和输入读取前拒绝，不构造假引擎，不重写变更文件 |
| 恢复 | 同身份续跑通过；改参数、冻结notebook损坏、kernel占用、非法输出与非法标签拒绝 |
| 反馈协议 | v1/v2读取、校验与合并；连续/并发快照、散列、SVG原字节、路径与符号链接拒绝、canonical碰撞拒绝、导入活动内容排除通过 |
| 实际kernel | 未填靶标模板执行至明确输入拒绝＋6个SR56 bootstrap，总计7个ipykernel；全部NOT_RUN；未导入Torch/RFD3/MPNN/RF3 |
| 离线浏览器 | 本次完整模板合成CPU报告：1440/768/390宽度、1个通用分支、COMPLETED和BINDER PIPELINE标签、监视页入口及相对文件链接。检查通过：无页面异常、外部请求、缺失文件链接或横向溢出；无历史视觉基线，视觉回归为INCONCLUSIVE；未做完整可访问性审计 |
| TOP10合成演示 | 10个设计、40条路径、80个模型；固定公式重建逐字节一致，原子置信度对应、完整相对链接、baseline和全循环最佳选择通过。生成过程不读取研究结果 |
| AF3命名 | 当前模型与复制值同步；CSV文本/数值排名、固定baseline原主榜名次、未知命名空间/编号拒绝猜测和unranked边界通过。当前notebook仅实现binder，其他模式为命名约定 |
| TOP10浏览器 | 合成演示及本地三分支，1440/1024/768/390宽度；双结构、路径/模型/榜单切换、复制、baseline固定、实际CIF下载原字节、无横向溢出通过；WebGL不可用时身份/表格仍可读。无页面异常或外部请求；另核验通用报告模型切换名称。file://离线阅读及本机HTTP下载分别核对，无历史视觉基线/完整可访问性审计 |
| 公开数据边界 | 当前公开文件与ZIP成员、既有可达Git对象核对真实结果ID/序列/运行及来源包标识未命中；演示结构与真实原件散列无重合。凭据/私人绝对路径模式检查通过；这是有界检查，不是穷尽隐私审计 |
| 输入来源 | SR56两份示例输入的固定集合与原发布资源中的SHA-256一致；通用模板自动记录源结构、规范化CIF、实际序列与来源映射散列，预检/续跑/计算阶段严格核对 |
| Git范围 | 来源/manifest/资源包/notebook应纳入；projects/run/缓存/权重/.env应排除；双向规则通过 |
| 原件 | 本地已验收SR56发布8文件散列保持不变；本仓库为独立副本 |

可重复验证：

```bash
python tests/verify.py
python tests/top10_demo.py
python tests/target_input_check.py
python tests/pipeline_cpu.py
python tests/kernel_smoke.py
```

GitHub Actions另在push/PR执行相同命令；远程状态以当前commit的Actions页面为准。测试成功仅表示列出的机械与范围验证有效，不表示绑定、力选择性或实验成功。原发布的42CPU用例/84循环验收属于来源发布，本仓库CI另运行上述5个通用模板CPU假引擎场景。假引擎不验证实际Foundry接口、scheduler兼容、模型行为或GPU环境。

主决策与本地独立重审：gpt-6.1-sol / openai，完整模型来自会话metadata，backend未提供；Chat未调用。外部Broker：opencode_go / deepseek-flash / deepseek-v4.1-flash / app_server，只读通用规则红队评议，未发送原件。控制器独立核验构建、差异、测试与发布结果；评议不能替代证据。
