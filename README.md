# CoSIL 在 SWE-Explore 上的复现实验

> **状态说明（2026-09-29）**：首轮 451 实例运行已完成，但事后发现结构索引
> 生成阶段存在相对路径问题，首轮指标不作为最终复现结果。详细分析见
> [`reports/2026-09-29-structure-generation-path-bug.md`](reports/2026-09-29-structure-generation-path-bug.md)。
> 修复后的重测使用独立输出目录，首轮日志和 trajectory 保留不覆盖。

本仓库保存 CoSIL 在 SWE-Explore 上的完整定位实验结果。实验数据集为
SWE-bench-Verified 与 SWE-Explore 的交集，共 451 个实例，覆盖 12 个项目。

## 实验目标

本实验只复现代码定位（localization），不进行补丁生成，也不进行
SWE-bench 修复率评测。主线结果采用 CoSIL 的 file mapping：模型返回的文件
排序被映射为完整文件区域。Function-span 结果由已保存的原始输出离线转换，
不需要再次调用模型。

## 参数

| 参数 | 设置 |
| --- | --- |
| 模型 | `gpt-5.4` |
| Temperature | `0.0` |
| CoSIL 最大迭代次数 | `10` |
| Top-K | `5` |
| 主评测模式 | file mapping |
| 离线转换模式 | function-span |
| 数据集 | SWE-bench-Verified ∩ SWE-Explore |
| 实例数 | `451` |
| 并发数 | `1` |
| 服务器架构 | ARM Linux |
| Docker | 未使用 |

实验通过 OpenAI-compatible 接口调用模型。出于安全和部署信息保护，运行时
API 地址和具体部署标识未写入公开 README；轨迹中的对应元数据已统一标记为
`gpt-5.4` 或 `<redacted-openai-compatible-endpoint>`。

## 复现过程

1. 固定 CoSIL 与 SWE-Explore 的代码版本，并构造 SWE-bench-Verified 与
   SWE-Explore 的实例交集。
2. 为 451 个实例准备对应 base commit 的 repository snapshot。
3. 在 ARM 服务器上的 `cosil` Conda 环境中完成依赖安装和接口连通性验证。
4. 使用 `gpt-5.4`、temperature=0、最大迭代次数 10、Top-K=5，按单进程运行
   CoSIL file-level 与 function-level 两阶段定位。
5. 每个实例保存原始定位输出、轨迹、模型调用记录、检索/定位日志、标准输出、
   标准错误和运行元数据。
6. 根据 SWE-Explore evaluator 对每个实例计算定位指标，并对 451 个实例取
   macro average。

主运行日志记录的 CoSIL 阶段耗时为 68,042 秒。最终 451 个实例全部完成，
其中 450 个实例有 5 个 file-level 预测；`django__django-13406` 为空定位。

## 结果

以下是 file mapping、Top-K=5 的 451 实例 macro average。`hit_file_rate` 和
`hit_region_rate` 是每个实例内部的核心文件/区域覆盖率再取均值，不是简单的
二值成功率。

| 指标 | 结果 |
| --- | ---: |
| Precision | 68.39% |
| Recall | 42.24% |
| F1 | 44.16% |
| Hit file rate | 54.99% |
| Hit region rate | 50.70% |
| Noise file rate | 24.92% |
| Noise region rate | 18.85% |
| Weighted core coverage | 30.76% |
| Context efficiency | 85.10% |
| Optional coverage | 6.98% |
| nDCG@100 / @300 / @500 | 90.54% / 91.68% / 92.15% |
| Recall@100 / @300 / @500 | 11.14% / 22.34% / 28.07% |
| First useful hit | 95.88% |

补充统计：439/451 个实例的 Recall 大于 0，177/451 个实例的 Recall 不低于
50%。完整的均值、标准差、中位数、阈值计数和按仓库分组结果见
`results/metrics/cosil_top5_summary.json` 与
`results/metrics/cosil_top5_macro.csv`。

## 结果分析

- First useful hit 为 95.88%，而 nDCG@100 为 90.54%，说明 CoSIL 通常能够较早
  把有用区域排到前面。
- Recall 为 42.24%，明显低于 Precision 的 68.39%，说明 Top-K=5 下结果较为
  聚焦，但仍有不少核心区域没有覆盖。
- Recall 从 @100 的 11.14% 增加到 @500 的 28.07%，说明扩大上下文预算能够
  继续覆盖核心代码，但收益不是线性增长。
- 当前主结果是 whole-file mapping；完整文件区域会放大上下文范围。后续使用
  已保存的原始输出转换成 function-span 后，可以单独分析更细粒度定位的
  Precision、Context efficiency 和噪声指标，且不需要重跑模型调用。

## 仓库内容

```text
configs/
  experiment.yaml              实验固定配置与数据版本
  environment-spec.yml         环境说明
data/processed/                451 条交集数据、问题映射和仓库清单
results/predictions/           规范化的逐实例预测与指标
results/metrics/               汇总指标（JSON/CSV）
results/cosil_traces/          451 个实例的完整 CoSIL 轨迹与调用记录
results/intermediates/         AST/repository structure 等生成的中间文件
logs/                          所有运行阶段日志，包括重试和最终主运行日志
scripts/                       数据准备、运行和指标汇总脚本
requirements-repro.txt         Python 依赖列表
```

`results/cosil_traces/<instance_id>/` 下保留：

- `file_level/` 和 `func_level/` 的原始 CoSIL JSONL 输出；
- `file_traj`、`func_traj`，包括提示词、模型响应、工具调用和 token 使用信息；
- `localization_logs/` 检索与定位过程日志；
- 子进程 stdout/stderr；
- `run_metadata.json`，包括实例、模式、迭代参数和返回状态。

## 版本与复现说明

实验固定版本：

- CoSIL: `0568e423735b399d5b089996961fea9ae142e4c7`
- SWE-Explore: `5602f031f2d9562d0a805f83402b536e831a5a11`
- SWE-Explore 数据集 revision: `bdb0ae45d7c337d9e1dc3ebfe2a0af6bc7c1fbd9`
- SWE-bench Verified revision: `c104f840cc67f8b6eec6f759ebc8b2693d585d4a`

重新汇总已有结果：

```bash
python scripts/summarize_metrics.py \
  results/predictions/cosil/top5.jsonl
```

repository snapshots 没有上传，因为它们可以根据 `data/processed/repo_manifest.json`
中的 base commit 重建。`.env`、API key 和任何凭据均未上传。
