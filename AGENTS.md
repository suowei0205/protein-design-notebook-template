# Project rules

- 中文文档；代码/API保留原命名。共享runtime为唯一编辑入口，不能只改生成ZIP。
- 修改源码或notebook后：`python scripts/build.py` → `python tests/verify.py`；改变启动/结束行为另跑 `python tests/kernel_smoke.py`。
- 模板计算流程必须完整，用户仅修改第4/8/9参数单元。未填靶标须在科学导入前明确拒绝并保存 `NOT_RUN`；不得把初始化/导出标为科学完成，或把CPU/kernel核验称为GPU/科学有效性验证。
- SR56科学来源指纹不得为了绿灯自动覆盖。科学改动先说明参数、判据、版本与验收范围；保留原结果。
- 保持单元ID、順序与折叠metadata；发布notebook无执行输出。源码、资源和pin更新必须同步。
- 不跟踪projects、run_*、监视日志、反馈快照、断点、缓存、权重或凭据；不改无关本地文件。
- 运行身份、反馈版本、候选标识、工件散列和相对路径属于协议，修改时同步写出和读取、测试未知版本拒绝。
- 不安装/升级科学环境，不运行GPU，不操作远程任务，除非当前用户明确授权。

- 设计查看页额外提供可复制AF3验证名称，按docs/AF3_NAMING.md；不改变原候选ID，当前排名与baseline原主榜排名分别核对，缺失字段不补猜。
- examples/top10-demo只能使用固定公式生成的合成数据；真实结果/ID/坐标/下载包不进入该目录或提交历史，修改后运行tests/top10_demo.py并核验离线浏览器。
