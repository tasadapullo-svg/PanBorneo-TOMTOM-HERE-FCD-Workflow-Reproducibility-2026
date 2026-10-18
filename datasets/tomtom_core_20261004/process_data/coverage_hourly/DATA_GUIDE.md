# 数据与复现指南

所有时间标签为Asia/Kuching本地时间（UTC+08:00），CSV空字段是缺项。True/False为布尔标记。派生统计不是新原始交通数据；原始会员表用于追溯，未插补，不是另一批独立样本。

| 文件/字段 | 定义、单位和支持 |
|---|---|
| CONFIG.json | 结果前冻结的规则；3/4、41节点、H+1端点、同节点等权、linear分位数、ddof=1与精度容差 |
| INPUT_LOCK.csv | 12核心载荷、清单及3引用报告；expected为空表示本次登记，不能冒称独立历史锚点 |
| coverage/INTERVAL_COVERAGE.csv | 2,304日历槽；observed_nodes/missing_nodes是原记录存在/缺项位置；51主分母，42参考分母；empty_slot_class区分首条前与内部空槽 |
| coverage/DAILY_COVERAGE.csv | 24日原观测计数、96槽存在数、4,896主分母、4,032参考分母；百分数为0–100 |
| coverage/NODE_COVERAGE.csv | 51节点各2,304槽分母；source node_order用于显示，不是方向或里程 |
| coverage/MISSING_EPISODES.csv | 最大连续缺项槽序列；起止是缺项槽，包含两端；duration_h=missing_slot_count/4；window_truncated表示触及统计窗口边界，窗口外情况未知 |
| coverage/MISSING_DURATION_BINS.csv | 区段和槽数分箱；区段不是实际故障事件 |
| hourly/RAW_NODE_HOUR_MEMBERSHIP.csv | 全部90,929原记录的node/hour/slot/speed及来源文件/行/UUID；速度km/h；本地hour_start从归一化slot派生 |
| hourly/NODE_HOUR_VALUES.csv | 完整29,376节点小时；observed_count与valid_speed_count为0–4。observed_snapshot_mean_kmh含1–2条的诊断均值，不能用作主结果；speed_mean_min3_kmh才是主节点小时值；0条UNOBSERVED，1–2条INSUFFICIENT，3–4条QUALIFIED |
| hourly/NODE_HOUR_ENDPOINT_JOIN.csv | 完整节点小时左连接；hour_start/H、hour_end/H+1及原rainfall_timestamp_local分别保留；precipitation_mm为前一小时累计mm；rain_mm独立保存，MISSING_ENDPOINT不填0；source_model/download_timestamp为来源元数据 |
| hourly/UNMATCHED_ENDPOINTS.csv | 51个末小时缺背景端点记录；包括不合格交通节点，不能直接当作主分析天气排除数 |
| hourly/OVERALL_HOURS_MIN2/3/4.csv | 各576行；valid_node_ids用竖线分隔精确有效集合；raw_membership_count只计这些节点原快照；retained_traffic_hour要求41节点，否则overall_speed_kmh空。precipitation_sum_tenths_mm为同集合整数0.1mm和，precipitation_mean_mm=和/(10×节点数)，只有保留且全部匹配才报告；未匹配数仅为有效节点内计数 |
| hourly/DIURNAL_PRIMARY.csv | 各钟点合格日期小时均值等权；date_count实际20–24；Q10/Q90为日期经验分位数，不是CI/预测区间 |
| hourly/NODE_CLOCK_VARIABILITY.csv | 全部23,520主门槛节点小时的1,224节点钟点组；mean/SD为km/h；sample_sd_kmh为ddof=1，>=2日期；不要求总体41节点 |
| hourly/BALANCED_NODE_CLOCK_MEANS.csv | 同主521小时，1,224节点钟点组先跨日期平均 |
| hourly/DIURNAL_BALANCED_COMPARISON.csv | 前述节点钟点均值再对51节点等权；balanced_minus_primary_kmh为另一估计对象与主曲线差，无CI |
| hourly/PRECIPITATION_GROUP_HOUR_SAMPLES.csv | 521个主小时样本；每小时速度与背景同节点集合；雨量是网格背景，不是路侧雨量真值 |
| hourly/PRECIPITATION_GROUP_SUMMARY.csv | 每小时贡献一个速度值；date_count不代表独立天气事件；mean/median/Q25/Q75/IQR/SD/min/max均km/h，Q为linear经验分位数，SD ddof=1 |
| hourly/SENSITIVITY_COMMON_HOURS_MIN2_MIN3.csv | 共同521小时、逐小时支持与差值；仍存在节点构成差异，不是同一节点固定对照；extra_node_ids_min2为新增的有效节点 |
| hourly/SENSITIVITY_SUPPORT_SUMMARY.csv | 各自与共同日历小时分别汇总，严门槛0小时均值为空 |
| hourly/WEIGHT_DEFINITION_DIAGNOSTIC.csv | 同主节点和小时，池化原快照与节点等权比较；不同权重定义，不替换主分析 |
| qa/BUILD_QA.csv / INDEPENDENT_QA.csv/json | 生成核查与独立原记录复算；键/集合/计数精确一致，浮点容差1e-10 |
| RESULT_SUMMARY.json / CLAIM_EVIDENCE.csv | 未舍入结果摘要与证据字段回指；用于数字核对，不把机器计算PASS扩大成来源/科学有效性已全部证明 |

比例是观测位置的存在比例，非提供方准确率。输入已存在行的速度均有效；当前observed_count=valid_speed_count，但两个字段职责分别保留。原记录有效性依赖冻结QA，本批没有地面速度/天气校验。重复网格按节点计权并不独立；群组小时/日期也可能相关。未做显著性检验、因果推断、插补或预测。

## 复现

脚本使用捆绑Python3.12.14、pandas3.0.1、numpy2.3.5（实测版本以RUN_CONTEXT.json为准）；独立复核与打包只用Python标准库。绝对输入路径在build_batch02.py，移机须明确改路径并重新登记输入哈希，不修改计算协议。

PowerShell例子（将输出指向不存在的新目录，不能复写本次目录）：

```powershell
$taskPython = 'C:\Users\stfr2\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
$taskScripts = 'REPLACE_WITH_THIS_DELIVERY_DIRECTORY'
$taskNewOut = 'REPLACE_WITH_NEW_OUTPUT_DIRECTORY'
& $taskPython (Join-Path $taskScripts 'build_batch02.py') --output-dir $taskNewOut
Copy-Item -LiteralPath (Join-Path $taskScripts 'verify_batch02.py') -Destination $taskNewOut
Copy-Item -LiteralPath (Join-Path $taskScripts 'finalize_batch02.py') -Destination $taskNewOut
Copy-Item -LiteralPath (Join-Path $taskScripts 'build_batch02.py') -Destination $taskNewOut
& $taskPython (Join-Path $taskNewOut 'verify_batch02.py') $taskNewOut
& $taskPython (Join-Path $taskNewOut 'finalize_batch02.py') $taskNewOut
```

报告和ZIP只在两套QA均无FAIL后生成。结果复算可直接运行verify_batch02.py，若重跑使QA文件时间变化，须重新finalize_batch02.py更新输出哈希。清单不包含自身或MANIFEST_VERIFY.json，以避免递归哈希；控制文件哈希和ZIP哈希单独登记于MANIFEST_VERIFY.json。原冻结包没有被重新构建，本批复现范围仅E04/E05。
