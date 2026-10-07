# 空白项目模板

用仓库根的 `python scripts/new_project.py projects/MyTarget` 复制，避免在这份源模板里产生日常运行。

打开 `DesignProject/DesignProject.ipynb`，填写 `RUN_LABEL`。默认完整执行仅创建目录、运行身份和 `NOT_RUN` 反馈；靶标输入、科学预算与 main/refine 实现留空。

共享源码在仓库 `runtime/`，维护时从根执行 `python scripts/build.py`。不要直接修改资源ZIP或pin。续跑必须显式指定原运行，科学身份变化则新建。
