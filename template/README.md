# 完整空白项目模板

“空白”指靶标输入留空；完整RFD3→MPNN→RF3→排名→refine→报告/反馈已经填好。只修改第4、8、9三个参数单元，无需编写计算代码。

用仓库根的 `python scripts/new_project.py projects/MyTarget` 复制，打开 `DesignProject/DesignProject.ipynb`。第4单元填实验名/已有环境与权重路径，第8单元填本地PDB/mmCIF、author链及可选残基范围，第9单元调binder长度和预算。输入相对路径以DesignProject目录为基准。

选择已有匹配Foundry/CUDA环境并保存后，顺序执行。未填靶标在第10单元、科学导入前明确停止并保存NOT_RUN。模型权重与科学环境不包含在模板中；默认不安装或下载。

共享源码在仓库 `runtime/`，维护时从根执行build和适用检查。运行命名空间为design_template_pipeline_v2，不接管旧骨架断点。输入内容、选取规则、规范化坐标和编号映射均纳入严格身份。
