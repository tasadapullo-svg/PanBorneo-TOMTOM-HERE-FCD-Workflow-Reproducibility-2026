# E06数据与复现指南

时间：Asia/Kuching（UTC+08:00），local时间为该时区标签。速度和误差km/h；平方误差单位(km/h)^2；duration_h=K/4。CSV空值为无支持或失败，绝不作为速度/误差0。True/False为布尔标记，列表竖线分隔。

| 文件 | 行对象、职责及关键定义 |
|---|---|
| CONFIG.json | 固定核心、切分、K/300上限、SeedSequence/PCG64、资格/抽样、基线/评分/失败处理；无调参、bootstrap、裁剪或预测 |
| INPUT_LOCK.csv | 13冻结文件带历史锚点；3引用报告仅登记本次哈希（expected为空）；前后不变核查 |
| inputs/PARTITION_COUNTS.csv | train/validation/test原行量，不是候选或实验样本数 |
| inputs/TRAIN_TOD_MEMBERSHIP.csv | 59,009训练原记录，精确节点、时间、15分钟TOD、速度与来源文件/行；不含验证/测试 |
| inputs/TRAIN_TOD_STATS.csv | 51×96节点/TOD完整格，observation_count为训练支持，median_speed_kmh为训练原快照中位数；>=3才准入 |
| inputs/CANDIDATE_CATALOG.csv | 4×51×384起始位置；candidate_id含K/node/t0。先检查两端点测试边界，再目标自然缺项、紧邻端点、训练TOD和同时其他节点。边界失败时后续未检查字段为空，不是支持0。first_exclusion_reason互斥，all_exclusion_reasons可重复 |
| inputs/CANDIDATE_EXCLUSIONS.csv | 排除首原因计数可相加；全部失败标记计数不能直接相加当总排除数 |
| inputs/CANDIDATE_SUPPORT_SUMMARY.csv | 合格池、数学最大非重叠容量、固定抽样实际N、抽样重叠排除/上限未访问、节点日期支持；容量与实际样本不同 |
| inputs/NONOVERLAP_CAPACITY_BY_NODE.csv | 同K/node闭窗口最大可容纳数；最早结束区间算法，独立QA动态规划验证 |
| inputs/NONOVERLAP_CAPACITY_WITNESS.csv | 达到上述容量的一组候选，不是本次随机抽样使用的窗口，不用于计算误差 |
| inputs/SAMPLER_RNG.json | 每K独立子流spawn_key及前后生成器状态，Numpy版本；最终遮蔽表才是样本依据 |
| inputs/FROZEN_GAPS.csv | gap_id/candidate_id，K、t0/末隐藏/左右端点、隐藏和上下文日期、跨午夜、最低训练/同时支持、选择顺序；same K/node闭窗口不共享端点 |
| inputs/SELECTED_SUPPORT_BY_NODE_DATE.csv | 按K/node/起始日期的实际缺口数；跨午夜仍在FROZEN_GAPS保留全部日期 |
| inputs/ALLOWED_SPEED_CONTEXT.csv | 每缺口独立可见视图；目标节点两端点、目标时刻其他节点原速度；不含当前缺口隐藏速度和辅助交通字段 |
| inputs/FROZEN_TOD_INPUTS.csv | 每目标点允许使用的训练中位数、TOD索引及支持；不含隐藏速度 |
| inputs/TARGET_SUPPORT.csv | 每目标点训练支持、排除目标节点后的同时其他节点数和精确名单 |
| reference/HIDDEN_PROVIDER_TARGETS.csv | 仅评分参照：原提供方速度、来源文件/行；不传给重建方法，也不是地面真实速度 |
| results/POINT_PREDICTIONS.csv | 每gap/method/目标的重建值与成功/失败，四方法目标完全相同；不含隐藏参照 |
| results/POINT_SCORES.csv | 评分阶段才连接参照，error=reconstruction−provider，squared_error和absolute_error；这里出现隐藏值不等于模型输入允许读取 |
| results/FAILED_PREDICTIONS.csv | 保留失败键/理由；本次0失败、空表有表头 |
| results/GAP_METRICS.csv | 每gap/method K点，SSE/绝对误差和/MSE/RMSE/MAE；complete和common_complete标明共同支持，不删点降低K |
| results/COMPLETION_COUNTS.csv | planned/complete/common/failed及planned/common点数；pct是0–100；分母无支持时留空 |
| results/METRICS_BY_LENGTH_METHOD.csv | 每K/method主点汇总RMSE/MAE、N/M、节点/日期/跨午夜；缺口RMSE分布中位数与linear Q25/Q75是描述分布，不是CI。不同长度不合并一个主RMSE |
| reference/SELECTED_REFERENCE_DIAGNOSTICS.csv | 评分后隐藏速度唯一数/范围；不用于资格、抽样或调参 |
| reference/CROSS_LENGTH_TARGET_REUSE.csv | 原节点/时段在独立长度实验间的重复参照键，不能重复当独立新观测 |
| results/OLD_FIGURE7_COUNT_COMPARISON.csv | 旧n为交接图面记载，不是恢复的旧执行；没有沿用旧误差或误差线 |
| qa/BUILD_QA.csv / INDEPENDENT_QA.csv/json | 生成与独立原记录/导出复算，检查范围和容差见每项；科学/地面有效性不被泛化为PASS |
| RESULT_SUMMARY.json / CLAIM_EVIDENCE.csv | 未舍入机器摘要及字段回指；最终正式指标见逐点结果复算后的METRICS表 |

同一时刻其他节点中位数是全网参照，不是地理最近邻。同长度上下文不重叠仍不证明缺口独立；只有4测试日期。同一输入文件可能包含另一缺口的参照键作为当前缺口允许的其他节点观测，这是每次单节点遮蔽的任务定义，不能把所有gap_id的输入混成同时遮蔽任务。

## 复现

运行环境见RUN_CONTEXT.json。使用捆绑Python、pandas和numpy；独立验证用标准库做统计/容量DP，仅Numpy用于重放PCG64。原冻结目录是只读来源；没有重新构建整个冻结包。脚本内绝对输入路径移机时须明确更新并重新登记哈希，规则保持相同。

运行build_reconstruction.py --output-dir NEW_DIRECTORY，复制本目录三个.py脚本至NEW_DIRECTORY，再运行verify_reconstruction.py NEW_DIRECTORY与finalize_reconstruction.py NEW_DIRECTORY。新目录不能有CONFIG.json。不要把本次目录用作重建输出。

PowerShell命令形式：

```powershell
$taskPython = 'C:\Users\stfr2\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskScripts = 'REPLACE_WITH_THIS_DELIVERY_DIRECTORY'
$taskNewOut = 'REPLACE_WITH_NEW_OUTPUT_DIRECTORY'
& $taskPython (Join-Path $taskScripts 'build_reconstruction.py') --output-dir $taskNewOut
Copy-Item -LiteralPath (Join-Path $taskScripts 'build_reconstruction.py') -Destination $taskNewOut
Copy-Item -LiteralPath (Join-Path $taskScripts 'verify_reconstruction.py') -Destination $taskNewOut
Copy-Item -LiteralPath (Join-Path $taskScripts 'finalize_reconstruction.py') -Destination $taskNewOut
& $taskPython (Join-Path $taskNewOut 'verify_reconstruction.py') $taskNewOut
& $taskPython (Join-Path $taskNewOut 'finalize_reconstruction.py') $taskNewOut
```

finalize要求两套QA全部PASS且脚本哈希同版，输出报告、来源回指、评分后参照诊断、非递归清单及ZIP。再运行verify会更新时间/QA哈希，应随后重新finalize。原RUN_LOG与VERIFY_LOG由PowerShell捕获，不是评分数据。

OUTPUT_MANIFEST/SHA256_MANIFEST不包含自身或MANIFEST_VERIFY，以免递归哈希；控制清单自身哈希、ZIP哈希、CRC和ZIP载荷匹配单独记在MANIFEST_VERIFY。ZIP含全部载荷及两清单，MANIFEST_VERIFY在ZIP外。仅内部交付，不赋予新共享许可。
