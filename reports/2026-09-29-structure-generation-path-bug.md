# 首轮实验结构索引路径问题报告

日期：2026-09-29  
实验：CoSIL on `SWE-bench-Verified ∩ SWE-Explore` 交集  
影响范围：首轮 451 个实例的结构索引、文件阶段输入和函数阶段输入

## 结论

首轮运行的模型调用确实完成了，但首轮结果不能作为最终复现结果。问题不是
模型接口、ARM 架构、Docker 或 CoSIL 定位算法，而是 SWE-Explore 接入层在生成
CoSIL repository structure 时使用了相对路径，随后 CoSIL 子进程切换工作目录，
导致相对路径被解析到错误位置。

错误路径没有触发异常：CoSIL 的 `create_structure()` 使用 `os.walk()`，对不存在
的目录会返回空结构 `{}`。适配层也没有检查结构是否为空，于是空索引被缓存，
后续定位继续执行。

## 复现架构与官方架构的关系

SWE-Explore 论文要求不同 explorer 在各自原始 scaffold 中运行，然后将文件、
函数或 region 输出规范化为统一的 `(repository-relative path, start, end)` 格式。
论文 Appendix E 没有展开 CoSIL 的命令行级接入细节。

公开的 SWE-Explore-Bench 仓库提供了 CoSIL wrapper。当前实验使用的
`cosil_explorer.py` 基于该公开实现，并在其上增加了 API endpoint 注入、重试参数、
轨迹保存和 file/function mapping 选项。CoSIL 原始算法、提示词和两阶段定位逻辑
没有被本问题修改。

公开 wrapper 的关键流程是：

1. 接收 SWE-Explore 的本地 repository snapshot；
2. 调用 CoSIL 的 `create_structure()` 生成结构索引；
3. 启动 CoSIL file-level localization；
4. 将文件结果传给 function-level localization；
5. 将结果转换为 SWE-Explore 的 line-region 输出。

官方 CoSIL 自己的流程不同：它通过 `get_verified_structure.py` 和
`get_project_structure_from_scratch()` 自己克隆仓库、checkout base commit、生成
结构，再通过 `PROJECT_FILE_LOC` 读取预生成结构。因此官方流程没有“父进程传入
一个相对仓库路径，然后子进程切换 cwd”这个组合。

## 具体路径错误

交集数据准备脚本为没有显式路径的记录填入了：

```text
repos/astropy__astropy-12907
```

该路径在主实验进程中可以被找到，因为主进程工作目录是项目根目录。但 CoSIL
wrapper 启动子进程时使用：

```text
cwd = third_party/CoSIL
```

于是以下调用：

```python
create_structure("repos/astropy__astropy-12907")
```

实际会查找：

```text
third_party/CoSIL/repos/astropy__astropy-12907
```

真正的 snapshot 位于项目根目录下的 `repos/` 中，两者不是同一个路径。

## 证据

### 1. 首轮缓存全部为空

首轮生成的结构文件只有很小的 JSON 外壳，`structure` 字段为 `{}`。以
`astropy__astropy-12907` 为例，缓存文件内容等价于：

```json
{
  "structure": {}
}
```

### 2. 同一个 repository snapshot 可以正常生成结构

对同一个 base-commit snapshot 使用绝对路径调用原始 `create_structure()`，能够
得到非空结构和大量 Python 文件信息。因此仓库快照本身是有效的，问题发生在
路径解析，而不是仓库内容或 ARM 环境。

### 3. 文件阶段原始响应与结构化输出不一致

首轮 451 个 file-level JSONL 记录的 `found_files` 都为空，但对应的
`file_traj.response` 中仍经常出现模型返回的文件路径。由于 CoSIL 会根据空的
`all_files` 列表校验模型路径，这些路径被全部过滤掉。

### 4. 函数阶段继承了错误输入

函数阶段读取 file-level JSONL 的 `found_files` 作为候选文件。由于文件阶段结构化
结果为空，函数阶段实际使用了空文件候选列表。部分实例仍产生了
`found_related_locs`，因此结果解析器输出了看似有效的函数 span，但这不是在正常
文件候选输入下得到的 CoSIL 两阶段结果。

## 为什么首轮没有立即失败

首轮验证存在以下不足：

- 只检查了子进程返回码，没有检查结构索引是否非空；
- `os.walk()` 对不存在路径静默返回空结果；
- 空结构缓存被视为有效缓存，后续运行不会重新生成；
- 文件阶段的 raw response 仍然包含路径，掩盖了 `found_files=[]` 的问题；
- 函数阶段的 fallback parser 还能产生非空预测，使 aggregate metrics 看起来合理；
- 没有在 451 实例前先做“单实例结构—文件输出—函数输入”的完整 smoke test。

因此“命令成功退出”被错误地当成了“实验语义正确”。

## 修复内容

修复保持 CoSIL 算法、模型、提示词、Top-K 和迭代参数不变，只改变实验接入层：

1. `eval_runner` 将 `repos_root` 解析为绝对路径；
2. CoSIL wrapper 在生成结构前将 `repo_root` 解析为绝对路径；
3. 生成后检查 repository snapshot 存在且 structure 非空；
4. 已存在但为空的结构缓存不再被直接复用；
5. 重测使用独立的 prediction、trace 和日志目录，首轮产物不覆盖；
6. 先运行少量实例做 smoke test，再启动完整 451 实例重测。

## 首轮结果的处理

首轮结果、调用日志、检索日志和 trajectory 全部保留，用于审计和问题复盘，
但标记为 `invalid_preflight_structure`，不与修复后的结果合并统计。

修复后将分别输出：

- 正常 CoSIL file mapping 的主结果；
- 从有效 function-level 输出得到的 function-span 分析；
- 结构生成、文件候选数量和函数候选数量的完整校验统计。

公开版本只描述模型为 `gpt-5.4`，不包含实际部署编号、API key 或私有 endpoint。
