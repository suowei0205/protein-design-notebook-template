# Protein Design Notebook Template

可维护的蛋白 binder 设计 notebook 模板：计算流程已填好，只修改参数即可运行。每个设计有自己的 notebook，各次运行直接放在该设计目录下；统一管理 main/refine、报告、排名、SVG、监视器、断点和反馈快照。

**“空白”指靶标输入留空；RFD3 → MPNN → RF3 → 排名 → refine → 报告与反馈均已实现。无需编写 main/refine。** SR56 六分支作为完整流程 example，保留原参数、单元顺序、折叠设置、有效性判断、原生排名、固定 baseline 与全循环最佳选择。

## 快速开始

```bash
git clone https://github.com/suowei0205/protein-design-notebook-template.git
cd protein-design-notebook-template
python3 scripts/new_project.py projects/MyTarget
```

用 Jupyter 或 VS Code 打开 `projects/MyTarget/DesignProject/DesignProject.ipynb`。选择已有匹配科学环境的 kernel，将工作目录设为 `DesignProject`，或填写启动单元的 `STANDALONE_PACKAGE_ROOT`。只修改三个参数单元：

| 单元 | 填写内容 |
|---|---|
| 第4单元 | `RUN_LABEL`、输出/续跑开关、已有权重路径；通常只改实验短名 |
| 第8单元 | 本地 `.pdb/.cif/.mmcif` 路径、源结构 author 链、可选残基范围/model/altloc及期望序列 |
| 第9单元 | binder长度、主阶段预算/seed、MPNN/RF3与refine参数；已有默认值 |

例如将自己的靶标文件放到 `projects/MyTarget/inputs/target.cif`，在第8单元填写：

```python
TARGET_STRUCTURE_FILE = "../inputs/target.cif"
SOURCE_CHAIN = "A"
SOURCE_RESIDUE_RANGE = None  # 整链；也可填写实际author起止编号
EXPECTED_TARGET_SEQUENCE = ""  # 可填写选中序列作额外核验
```

保存 notebook 后顺序运行所有单元即可执行完整流程。固定计算单元默认折叠，无需改代码。未填写靶标时，第10单元会在科学模块导入前明确停止并保存 `NOT_RUN` 报告和反馈，不会把空输入标为计算成功。

模板支持**单链标准蛋白靶标＋单连续binder**。选中坐标按 author 链/编号及 insertion code 保存来源映射，内部统一为 `A1..N`；不会补齐缺失残基，编号缺口、非标准残基、缺失主链或退化坐标明确拒绝。水和普通配体记录排除。model默认1，altloc默认按残基最高occupancy；这是坐标选择规则，不是 canonical 全长或构象状态验证。其他设计任务不属于本模板。

需要本地 notebook kernel 的开发环境：

```bash
python3 -m venv .venv
# macOS / Linux
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python tests/kernel_smoke.py
```

开发依赖只用于无GPU核验。模板和SR56的实际计算需使用已有、匹配的 Foundry/RFD3、MPNN、RF3、Torch/CUDA、权重和普通科学依赖；此仓库不自动下载权重、升级 GPU 环境或启动远程任务。运行锁目前使用 POSIX `fcntl`；支持 macOS / Linux，Windows 使用 WSL，不宣称原生 Windows 兼容。

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
- 新参数、新代码、新输入或独立重复实验使用新运行。严格恢复：填写 `STANDALONE_OUTPUT_ROOT` 原目录，设 `STANDALONE_RESUME=True`。已冻结配置、源码、资源与已记录环境身份不符或目录已占用时拒绝。模板已核验输入内容SHA-256、选取规则、实际序列、规范化CIF与编号映射；同路径文件内容变化也会拒绝。完整模板使用 `design_template_pipeline_v2`，不接管旧 `design_template_v1` 骨架断点。SR56 示例保留原有科学输入校验。
- `reports/index.html` 为结果报告；`monitor/index.html` 为轻量监视快照。监视器按可核验回执计完成数，不加载完整候选表。
- `feedback/feedback_YYYY-MM-DD_HHMMSS.zip` 为独立快照，每份有 `.zip.sha256`；旧快照不覆盖。ZIP 和旁文件分别发布，二者不是同时原子事务。
- 反馈继续使用“全量数值证据＋精选结构”；其余结构有补取清单。反馈不是完整续跑包。v1/v2反馈可只读校验与重建；未知版本拒绝，导入HTML/JS/SVG只保留在原ZIP，不进入可信重建页面。

## SR56 example

打开 [examples/SR56](examples/SR56/README.md)，选择对应分支。SR56 原始来源和散列见 [PROVENANCE.json](examples/SR56/PROVENANCE.json)。仓库中的科学代码与已验收发布版保持一致；共享资源增加通用模板支持，资源包与 notebook pin 由构建工具重生成，因此整个包的字节散列会变化，不能接管旧发布版断点。

本仓库不包含真实历史计算结果、真实TOP10结构评审数据、真实反馈包或模型权重。SR56 example 的输入是已核验发布包中的示例材料，不等于实验验证或力状态机制证据。

## TOP10 查看器演示与 AF3 命名

[合成 TOP10 演示](examples/top10-demo/README.md)沿用结构评审页的双视窗、固定baseline、主榜/全循环最佳榜和下载交互。克隆完整仓库后打开 `examples/top10-demo/index.html`；全部数据为合成，不含真实 TOP10 设计结果。

查看页额外显示可复制 AF3 名称：蛋白、区域、靶标描述、UniProt、输入残基范围、设计模式、排名及完整候选 ID。未知字段保留待填，无正式排名使用unranked；[设计模式与命名规范](docs/AF3_NAMING.md)区分设计任务、binder类型、榜单和main/refine阶段。

## 后期维护

共享行为只改 `runtime/`；项目科学步骤改对应 notebook；资源入口改对应 `manifest.json`；SR56 示例输入改 `examples/SR56/inputs/`。不要直接编辑生成的 `resources.zip`、资源清单或 notebook 的 `RESOURCE_BUNDLE_SHA256`。

```bash
python3 scripts/build.py
python3 scripts/build.py --check
python3 tests/verify.py
python3 scripts/build_top10_demo.py --check
python3 tests/top10_demo.py
# 已安装开发依赖时，实际启动 kernel 检查
python3 tests/kernel_smoke.py
# 已安装开发依赖时，靶标边界及真实循环的CPU假引擎检查
python3 tests/target_input_check.py
python3 tests/pipeline_cpu.py

git diff --stat
git diff --check
git add runtime scripts tests template examples docs README.md CHANGELOG.md
git commit -m "Describe the change"
git push origin main
```

`tests/verify.py` 使用标准库检查构建、清单/pin、未配置靶标的 `NOT_RUN` 拒绝、严格恢复、反馈边界和来源指纹；并核对复用的科学循环AST。`kernel_smoke.py` 用实际kernel检查未配置模板的输入拒绝及六个SR56 bootstrap，未导入科学引擎。另有通用靶标预检和完整主/refine循环的CPU假引擎检查。GitHub Actions 在push/PR执行这些检查，**不证明真实GPU、科学有效性或性能**。

运行文件、`projects/`、断点、反馈、缓存、权重和环境文件默认忽略；源码、输入示例、空 notebook、许可和生成资源包应跟踪。notebook 提交前清空执行输出，测试会拒绝带输出的文件。**当前仓库为公开 GitHub Template repository**；可使用 GitHub 的 “Use this template”，复制后自行更新 README 的 clone 地址。公开范围包含仓库文件、提交历史和 Actions 日志；个人研究项目与运行结果继续保存在本地或独立私有仓库。

更详细的接口、版本变更和验证边界见 [维护说明](docs/MAINTENANCE.md) 与 [验证记录](docs/VALIDATION.md)。

## 许可

原创代码采用 [MIT](LICENSE)。3Dmol、Noto/DejaVu字体和科学依赖具有独立许可，见 [第三方说明](THIRD_PARTY_NOTICES.md)。现有 `sr56_*` 模块、schema和JS注册变量保留历史名称以维持反馈协议兼容；不要全局替换名称。
