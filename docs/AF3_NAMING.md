# AF3 验证名称规范

查看页额外显示可复制名称；原 candidate ID、排名、文件名与断点身份保持原值。

```text
{蛋白} {区域} {helix/靶标描述} {UniProt} {输入残基范围} {设计模式}-rank{当前榜名次}-{完整candidate_id}
```

例如：`SYNTHETIC demo-protein demo-region A-helix DEMO-NO-UNIPROT 1-11 binder-rank1-refine:SYNTHETIC-D00:C3:P0:K0:S0:M0`。

| 设计任务 | 设计模式字段 | 残基范围/描述 | 名称格式示例（占位示例，非实际成果） |
|---|---|---|---|
| 蛋白 binder | `binder` | 实际靶标输入片段；注明输入类型/minibinder | `{蛋白} {区域} {靶标描述} {UniProt} {范围} binder-rank1-{candidate_id}` |
| 短肽 binder | `binder` | 实际靶标输入片段；输入类型为 short_peptide | `{蛋白} {区域} {靶标描述} {UniProt} {范围} binder-rank1-{candidate_id}` |
| Motif scaffolding | `motif_scaffolding` | motif 来源链与区段，可含多个区段 | `{蛋白} {区域} motif {UniProt} {motif范围} motif_scaffolding-rank1-{candidate_id}` |
| Ligand design | `ligand_design` | ligand 标识及蛋白输入范围；无蛋白来源时填 NA | `{蛋白或NA} {区域或NA} ligand-{配体ID} {UniProt或NA} {范围或NA} ligand_design-rank1-{candidate_id}` |
| 无条件 / de novo | `unconditional` | 无来源蛋白或来源残基范围，明确 NA；长度另记录 | `de-novo NA length-{长度} NA NA unconditional-rank1-{candidate_id}` |

当前完整 notebook 只实现 binder；其他行是今后页面采用的命名约定，不代表本模板已接通这些计算模式。minibinder/short_peptide 属于 binder 类型，不是 main/refine 阶段；在页面及 AF3 配置中另列该类型。如果混合两种 binder 类型进行跨项目归档，应在“靶标描述”后额外填写类型，避免仅靠名称合并实验。

| 字段 | 规则 |
|---|---|
| 蛋白、区域、UniProt | 使用已核验来源；其他靶标不套用 SR56/Q6ZWQ0，未知字段显示“待填” |
| 残基范围 | 采用实际送入计算的片段；已核验 canonical 编号才直接写 `起点-终点`。仅有局部坐标来源时写 `author:链:起点-终点`，不冒充 UniProt 编号；多链/多段保留每段来源 |
| `rankN` | 属于明确的榜单，不是候选 ID。TOP10 当前路径用当前主榜/全循环最佳榜的设计项排名；baseline 始终用原主榜排名；页面同时显示榜单来源 |
| 非排名路径 / 模型 | TOP10 路径继承所选设计项的当前榜名次，并明确“设计项排名”。通用反馈报告中没有正式名次的模型显示 `unranked`，不得伪造排名 |
| `main:` / `refine:` | 属于原 candidate ID 的阶段信息；不是设计模式。保留原 ID，不能重排其中索引或强行把其他引擎 ID 转成这个协议 |
| `D/C/P/K/S/M` | 分别为原协议的设计、轮次、父路径、子骨架、序列和模型索引；采用实际 ID，包括原 0-based 索引，不自行加一 |
| baseline | 独立名称、独立原主榜排名；切换当前模型不改变 baseline 身份 |
| 结构阶段 | RFD3/MPNN 查看时名称中的 candidate ID 是该路径的 RF3 参照模型，页面已有参照说明；用该 binder 序列验证前仍须确认具体下载对象 |
| 多来源 / 未公开设计 | UniProt 不等于设计 binder 的 accession；不把设计序列、真实 ID、结构或内部路径放进公开演示 |
| 合成演示 | 以 `SYNTHETIC` 开头，使用虚构蛋白/区域/ID；不得用于科学结论 |

名称只帮助追踪 AF3 验证任务，不替代 AF3 输入中的靶标和 binder 序列、化学组分、seed、模型设置及原始结构身份。后续人工 AF3 验证结果应另保存，不能写回原设计的预测分数。
