# Protein Design Notebook Template

可维护的蛋白设计 notebook 项目骨架：每个设计有自己的 notebook，各次运行直接放在该设计目录下；统一管理 main/refine、报告、排名、SVG、监视器、断点和反馈快照。

**空白模板不包含科学计算实现，完整执行后的状态为 `NOT_RUN`。** SR56 六分支作为完整流程 example，保留原参数、单元顺序、折叠设置、有效性判断、原生排名、固定 baseline 与全循环最佳选择。

## 快速开始

```bash
git clone https://github.com/suowei0205/protein-design-notebook-template.git
cd protein-design-notebook-template
python3 scripts/new_project.py projects/MyTarget
```

用 Jupyter 或 VS Code 打开 `projects/MyTarget/DesignProject/DesignProject.ipynb`。将 kernel 工作目录设为 `DesignProject`，或填写启动单元的 `STANDALONE_PACKAGE_ROOT`。修改 `RUN_LABEL`，然后填写靶标和科学参数，并在主阶段/refine 单元接入你自己的计算。默认运行所有单元仅创建框架、`NOT_RUN` 报告和反馈，不加载科学引擎。

需要本地 notebook kernel 的开发环境：

```bash
python3 -m venv .venv
# macOS / Linux
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tests/kernel_smoke.py
```

开发依赖不是科学环境。SR56 的实际计算需另行准备已有、匹配的 Foundry/RFD3、MPNN、RF3、Torch/CUDA、权重和普通科学依赖；此仓库不自动下载权重、升级 GPU 环境或启动远程任务。运行锁目前使用 POSIX `fcntl`；支持 macOS / Linux，Windows 使用 WSL，不宣称原生 Windows 兼容。

## 目录

```text
protein-design-notebook-template/
├── runtime/                       # 共享源码、可信页面资源、许可
├── scripts/                       # 构建与复制模板
├── tests/                         # 无科学引擎的核验
├── template/
│   ├── manifest.json
│   ├── resources.zip              # 从 runtime 生成；不要手工编辑
│   └── DesignProject/
│       └── DesignProject.ipynb
├── examples/SR56/
│   ├── README.md
│   ├── PROVENANCE.json
│   ├── manifest.json
│   ├── inputs/                    # 示例输入源码
│   ├── resources.zip              # runtime + 示例输入生成
│   └── SR56_A_minibinder/          # 另有五个独立分支
│       └── SR56_A_minibinder.ipynb
└── projects/                      # 本地项目，默认不跟踪
```

每次运行由 notebook 自动创建；没有多余的 `runs/`：

```text
DesignProject/
├── DesignProject.ipynb
└── run_基线参数_2026-10-07_1500/
    ├── README.html
    ├── main/{rfd3,mpnn,rf3}/
    ├── refine/{rfd3,mpnn,rf3}/
    ├── reports/{index.html,main,refine,assets,data}/
    ├── rankings/{main,refine}/
    ├── svg/{main,refine}/
    ├── monitor/
    ├── checkpoints/
    ├── prep/
    └── feedback/
```

## 命名、续跑和反馈

- `RUN_LABEL` 去首尾空白、NFC 规范化，允许文字、数字、下划线和连字符，最多40字符；非法字符或超长会拒绝。空值使用“未命名实验”。
- 时间按北京时间；同名排他创建并加 `_02`、`_03`，不会覆盖目录。显示名称不替代内部 `run_id` 或科学身份。
- 新参数、新代码、新输入或独立重复实验使用新运行。严格恢复：填写 `STANDALONE_OUTPUT_ROOT` 原目录，设 `STANDALONE_RESUME=True`。已冻结配置、源码、资源与已记录环境身份不符或目录已占用时拒绝。空模板只冻结填写的参数和路径，不自动核验外部结构文件的内容；接入计算时须把输入内容散列纳入配置或 target 并核验。SR56 示例保留原有科学输入校验。
- `reports/index.html` 为结果报告；`monitor/index.html` 为轻量监视快照。监视器按可核验回执计完成数，不加载完整候选表。
- `feedback/feedback_YYYY-MM-DD_HHMMSS.zip` 为独立快照，每份有 `.zip.sha256`；旧快照不覆盖。ZIP 和旁文件分别发布，二者不是同时原子事务。
- 反馈继续使用“全量数值证据＋精选结构”；其余结构有补取清单。反馈不是完整续跑包。v1/v2反馈可只读校验与重建；未知版本拒绝，导入HTML/JS/SVG只保留在原ZIP，不进入可信重建页面。

## SR56 example

打开 [examples/SR56](examples/SR56/README.md)，选择对应分支。SR56 原始来源和散列见 [PROVENANCE.json](examples/SR56/PROVENANCE.json)。仓库中的科学代码与已验收发布版保持一致；共享资源增加通用模板支持，资源包与 notebook pin 由构建工具重生成，因此整个包的字节散列会变化，不能接管旧发布版断点。

本仓库没有历史计算结果、TOP10结构评审、真实反馈包或模型权重。SR56 example 的输入是已核验发布包中的示例材料，不等于实验验证或力状态机制证据。

## 后期维护

共享行为只改 `runtime/`；项目科学步骤改对应 notebook；资源入口改对应 `manifest.json`；SR56 示例输入改 `examples/SR56/inputs/`。不要直接编辑生成的 `resources.zip`、资源清单或 notebook 的 `RESOURCE_BUNDLE_SHA256`。

```bash
python3 scripts/build.py
python3 scripts/build.py --check
python3 tests/verify.py
# 已安装开发依赖时，实际启动 kernel 检查
python3 tests/kernel_smoke.py

git diff --stat
git diff --check
git add runtime scripts tests template examples docs README.md CHANGELOG.md
git commit -m "Describe the change"
git push origin main
```

`tests/verify.py` 使用标准库：检查构建确定性、清单/pin、空模板真实 `NOT_RUN` 导出、严格恢复与拒绝、符号链接/路径边界、SR56科学来源指纹和Git忽略规则。`kernel_smoke.py` 实际启动空模板及六个SR56 bootstrap，只导出零候选反馈，不导入科学引擎。GitHub Actions 在 push/PR 时执行这些检查，**不证明真实GPU、科学流程有效性或性能**。

运行文件、`projects/`、断点、反馈、缓存、权重和环境文件默认忽略；源码、输入示例、空 notebook、许可和生成资源包应跟踪。notebook 提交前清空执行输出，测试会拒绝带输出的文件。**当前仓库为公开 GitHub Template repository**；可使用 GitHub 的 “Use this template”，复制后自行更新 README 的 clone 地址。公开范围包含仓库文件、提交历史和 Actions 日志；个人研究项目与运行结果继续保存在本地或独立私有仓库。

更详细的接口、版本变更和验证边界见 [维护说明](docs/MAINTENANCE.md) 与 [验证记录](docs/VALIDATION.md)。

## 许可

原创代码采用 [MIT](LICENSE)。3Dmol、Noto/DejaVu字体和科学依赖具有独立许可，见 [第三方说明](THIRD_PARTY_NOTICES.md)。现有 `sr56_*` 模块、schema和JS注册变量保留历史名称以维持反馈协议兼容；不要全局替换名称。
