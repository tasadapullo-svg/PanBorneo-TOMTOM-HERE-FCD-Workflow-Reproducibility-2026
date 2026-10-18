"""Create readable evidence notes, nonrecursive checksums and internal ZIP.
Requires both build and independent QA to pass. No input writes.
"""
from pathlib import Path
import csv, hashlib, json, shutil, sys, zipfile
from datetime import datetime, timezone

def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def csv_write(p,rows,fields):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def table(rows,cols):
    return '| '+ ' | '.join(cols) +' |\n| '+ ' | '.join(['---']*len(cols))+' |\n'+'\n'.join('| '+' | '.join(str(r[c]) for c in cols)+' |' for r in rows)

def main(out):
    out=out.resolve()
    s=json.loads((out/'RESULT_SUMMARY.json').read_text(encoding='utf-8'))
    iq=json.loads((out/'qa/INDEPENDENT_QA.json').read_text(encoding='utf-8'))
    bq=read(out/'qa/BUILD_QA.csv')
    if iq['failed_count'] or any(r['status']!='PASS' for r in bq):raise RuntimeError('QA has failures')
    if sha(out/'verify_batch02.py')!=iq['verifier_sha256']:raise RuntimeError('Verifier changed since successful QA')
    c=s['coverage'];h=s['hourly'];se=s['sensitivity']
    group_rows=[{'P_H (mm)':r['precipitation_group'],'小时n':r['hour_count'],'日期n':r['date_count'],'节点数范围':f"{r['min_nodes']}–{r['max_nodes']}",'均速km/h':f"{r['mean_speed_kmh']:.2f}",'中位数km/h':f"{r['median_speed_kmh']:.2f}",'Q25–Q75 km/h':f"{r['q25_speed_kmh']:.2f}–{r['q75_speed_kmh']:.2f}",'IQR km/h':f"{r['iqr_speed_kmh']:.2f}"} for r in h['groups']]
    groups=table(group_rows,list(group_rows[0]))
    dc=read(out/'hourly/DIURNAL_PRIMARY.csv')
    clock_rows=[{'本地钟点':f"{int(r['clock_hour_local']):02d}:00",'日期n':r['date_count'],'均速km/h':f"{float(r['mean_speed_kmh']):.2f}",'经验Q10–Q90 km/h':f"{float(r['q10_speed_kmh']):.2f}–{float(r['q90_speed_kmh']):.2f}"} for r in dc]
    clock_table=table(clock_rows,list(clock_rows[0]))
    report=f'''# 第二批验收报告：E04原生覆盖与E05正式5.3统计

日期：2026年10月6日。核心版本：TOMTOM_CORE_20261004。运行ID：20261006_b02_060919Z。

**本批已完成E04覆盖明细和E05描述性统计及独立复算，停在第二批验收点。**原冻结输入、交接文件、第一批、Word和图片均未修改。输出可作为5.2/5.3和补充材料的计算证据；本报告不是已编辑完成的论文正文或新图稿。

## 1 原生覆盖：5.2计算证据

- 固定日历：2025-12-08 00:00至12-31 23:45，Asia/Kuching，24日×96槽×51节点。实际记录从12-08 13:15开始，主分母仍为117,504位置。
- 观测90,929，缺项26,575；面板覆盖{c['coverage_pct']:.2f}%，缺项{c['missing_pct']:.2f}%。有记录的槽2,166/2,304（{c['slot_presence_pct']:.2f}%）。42条典型批次参考口径为90,929/96,768（{c['reference42_pct']:.2f}%），不是HTTP成功率或经请求日志证明的应采总数。
- 138个整槽无记录：首条之前53个，首末观测之间85个。没有运行/请求日志，本批不归因于停机、网络或API拒绝。
- 最大连续缺项区段16,447个，槽数合计26,575；60个触及窗口边界（51起点、9终点），16,387个为内部区段。中位时长{c['median_duration_h']:.2f} h，窗口内最长{c['max_duration_h']:.2f} h，内部最长{c['max_internal_duration_h']:.2f} h。边界外状态未知，不把这些区段称为实际故障次数。
- 每节点缺项比例{c['node_missing_pct_min']:.2f}%–{c['node_missing_pct_max']:.2f}%；所有节点均使用2,304槽分母。每日表使用4,896位置和96槽分母。行内字段缺失与未出现的节点—时段位置含义不同。
- 分箱区段数依次为13,249、2,415、507、69、54、43、59、51、0，见coverage/MISSING_DURATION_BINS.csv。全量起止槽、槽数、时长和边界标记见coverage/MISSING_EPISODES.csv。

## 2 5.3定义与实际支持

先按归一化15分钟槽归入左闭右开自然小时[H,H+1 h)，不重新floor原pd_create_time。每节点至少3个唯一、有效速度快照才报告节点小时均值，然后在至少41个合格节点的小时内等权平均。低于门槛保留空派生值及实际计数，未插补。

29,376个日历节点小时中，0/1/2/3/4条观测数量分别为1,543/663/3,650/11,114/12,406。3条门槛合格节点小时23,520；总体主分析保留521/576小时，排除55小时，其中节点小时22,784，每小时41–48节点。没有把22,784当作独立样本数。

总体指标是“当小时可用观测节点的等权平均速度”，不是流量或道路长度加权速度，也不是经地面验证的全走廊真实速度。521小时均值为{h['overall_retained_mean_kmh']:.2f} km/h；这是所有保留小时等权汇总，须与按钟点等权再汇总等其他对象区分。

### 2.1 主日变化：日期等权与经验分位数

每个本地钟点有20–24个保留日期，以下Q10–Q90是日期小时均值的经验分位数，使用linear插值；不是置信区间或预测区间。此24日包含工作日和周末，不能当作全年典型日。

{clock_table}

本窗口中03:00钟点均速最高91.10 km/h（21日期），19:00最低86.08 km/h（23日期）。这只是观测支持下的钟点描述，不能自动认定交通需求峰值或已证实拥堵。

### 2.2 节点时间变异与均衡节点对照

NODE_CLOCK_VARIABILITY.csv使用全部23,520个合格节点小时；51×24=1,224个节点—钟点组各有13–24日期，计算ddof=1样本SD，至少2日期。它不是同一时刻的空间SD。

另在相同521个主小时上，先为每节点同钟点计算跨日期均值，再对51节点等权；1,224组各有12–24日期。DIURNAL_BALANCED_COMPARISON.csv给出该曲线与主曲线差值，最大绝对差{se['balanced_primary_max_abs_kmh']:.4f} km/h。估计对象不同，未为均衡曲线复制主曲线的经验分位数带。

显示顺序采用背景来源映射中的node_order_verified，而不是ID字典序；该顺序不证明道路里程、方向或拓扑。

## 3 降水背景：正确端点及同节点支持

主字段precipitation_mm解释为时间戳之前一小时累计量，单位mm；匹配node_id及H+1 h端点。旧冻结字典mm/hour与原请求/字典mm的差异按首批独立勘误处理，本批未改冻结字典。来源语义依据详见首批SEMANTICS_AUDIT.md和[Open-Meteo历史天气文档](https://open-meteo.com/en/docs/historical-weather-api)；当前文档不是完整历史HTTP执行证明。

完整节点小时连接保留29,376行，最后小时的51节点没有次日00:00背景端点，未匹配表明确登记；其中42节点各1条交通快照、9节点无快照，均未达到3条门槛，因此主分析521小时/22,784节点小时全部匹配，无主分析天气排除。未从历史来源导入次日值，未错配23:00或填0。

速度与降水每小时均使用同一有效节点集合S_H等权。51节点共享15网格，节点等权会按各网格覆盖的节点数加权，不能称作15网格等权或51独立雨量站。产品为事后网格背景，下载记录在2026年7月；不能认定其在2025年12月预测决策时可用。

原降水值×10全为整数，精度前置检查最大误差{s['precision_max_error']}；以整数十分之一毫米求和并与节点数比较0/0.1/0.5边界，不按显示舍入分组。保留rain_mm为另一来源字段，不替代precipitation_mm。

{groups}

每个保留小时贡献一个均速值，分组共521小时，各组日期集合可重叠。P_H为同样本节点的降水累计平均；数值分箱不是官方天气等级，P_H=0也不证明道路所有位置实际无雨。四组均值依次为89.51、89.21、88.57、88.28 km/h，是未调整的描述性分布；钟点、日期、节点构成及天气依赖可能影响差异。本批没有显著性检验、bootstrap或因果推断。

## 4 敏感性与权重定义

- 至少2条：27,170合格节点小时、542总体小时；自身保留支持包含27,134节点小时，总体均速88.8058 km/h。
- 至少3条主口径：23,520合格节点小时、521总体小时；22,784纳入节点小时，总体均速88.8265 km/h。
- 必须4条：12,406合格节点小时、0个总体小时。41节点门槛保持不变，所以没有可比较总体曲线；空均速是无支持，不是速度0。
- 共同521小时上，2条口径含26,108节点小时，均速88.8528；3条口径含22,784，均速88.8265 km/h。共同小时的有效节点集合全部改变。逐小时2条减3条差值平均{se['mean_signed_min2_minus_min3_kmh']:.4f}、绝对差中位数{se['median_absolute_min2_minus_min3_kmh']:.4f}、最大{se['max_absolute_min2_minus_min3_kmh']:.4f} km/h。共同时间支持消除了日历支持差异，仍保留节点构成差异。
- 同一主分析节点集合上，所有原快照直接池化与先节点内均值再节点等权，绝对差中位数{se['pooled_equal_median_abs_kmh']:.4f}、最大{se['pooled_equal_max_abs_kmh']:.4f} km/h。该诊断说明权重定义的影响，未替换主口径。

## 5 版本、复算与交付

12项冻结载荷及清单与既有SHA-256匹配；本次引用的交接和首批报告也登记哈希。全部16个入口文件扫描前后不变，见INPUT_LOCK.csv。

build_batch02.py使用pandas/numpy聚合；verify_batch02.py另用标准库、原记录和CSV导出重建连续缺项、小时支持、节点均值、天气端点、钟点分位数、节点样本SD、组分布与敏感性。生成检查{len(bq)}项PASS；独立复算{iq['check_count']}项PASS、0项FAIL。整数、键、节点集合和区段要求精确一致；浮点复核容差1e-10 km/h/mm。QA通过限于上述计算，不代替地面真值验证、空间注册、来源访问权或全部科学准入。

机器未舍入结果见RESULT_SUMMARY.json和各CSV；CSV数值保留17位有效数字，百分数/小时在本报告按两位显示。文件职责及数据层身份见DATA_GUIDE.md，逐项数字回指见CLAIM_EVIDENCE.csv。清单不递归包含自身；ZIP仅为内部交付，没有公开发布或赋予共享许可。

本批精确目录：`{out}`。文件清单、SHA-256及ZIP验证以OUTPUT_MANIFEST.csv、SHA256_MANIFEST.csv和MANIFEST_VERIFY.json为准。

## 6 验收范围与下一步

| 项目 | 本批状态 |
|---|---|
| E04 | 原生覆盖、每日/节点/逐区段明细与可复算QA完成；图3视觉/稿件同步未执行 |
| E05 | 5.3正式描述性明细、统计与敏感性完成；图4及Word/正文同步未执行 |
| E02 | 延用首批背景勘误/基础映射；道路注册、里程、方向、拓扑仍未关闭 |
| E03 | 仍为限定记录时间代理部分成立；实际在线时刻证据未新增，整体未关闭 |
| E06 | 尚未执行候选资格、遮蔽重建与评分，可独立进入下一批 |
| E07 | 尚未执行预测；需验收E03代理边界并逐条核验实际预测资格 |
| E08 | 图表与正文同步待执行；本批没有新图片 |
| E09 | 本批分析复算有脚本/QA，不代表整个冻结构建或模型流水线已复现 |
| G2/G3 | 未通过；未宣称全篇实证定稿或投稿准备完成 |

后续可以按第11节先执行E06回顾性缺口重建资格与基准。5.5仍须处理首批时间准入边界。图4重做前应先给出图数、内容和放置位置，再按SCI绘图规范核验/导出。范围或协议变化、真正在线证据、作者/共享/投稿决定仍需对应任务授权。
'''
    (out/'BATCH02_ACCEPTANCE.md').write_text(report,encoding='utf-8')
    guide='''# 数据与复现指南

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
$taskPython = 'C:\\Users\\stfr2\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe'
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
'''
    (out/'DATA_GUIDE.md').write_text(guide,encoding='utf-8')
    claims=[
        dict(claim='calendar_panel_coverage',value_unrounded=c['coverage_pct'],unit='percent',file='coverage/DAILY_COVERAGE.csv',fields='sum(observed_records)/sum(panel_denominator)*100',support='24 days / 51 nodes'),
        dict(claim='missing_positions',value_unrounded=c['missing_positions'],unit='positions',file='coverage/MISSING_EPISODES.csv',fields='sum(missing_slot_count)',support='full calendar'),
        dict(claim='max_internal_missing_h',value_unrounded=c['max_internal_duration_h'],unit='h',file='coverage/MISSING_EPISODES.csv',fields='max(duration_h) where window_truncated=False',support='internal maximal runs'),
        dict(claim='primary_hours',value_unrounded=h['primary_hours'],unit='hours',file='hourly/OVERALL_HOURS_MIN3.csv',fields='count(retained_traffic_hour=True)',support='3 valid snapshots/node; >=41 nodes/hour'),
        dict(claim='primary_mean',value_unrounded=h['overall_retained_mean_kmh'],unit='km/h',file='hourly/OVERALL_HOURS_MIN3.csv',fields='mean(overall_speed_kmh) over retained hours',support='521 equal hours; equal nodes within hour'),
        dict(claim='primary_node_hours',value_unrounded=h['included_node_hours'],unit='node-hours',file='hourly/OVERALL_HOURS_MIN3.csv',fields='sum(valid_node_count) over retained hours',support='not independent sample n'),
        dict(claim='pooled_vs_equal_max_abs',value_unrounded=se['pooled_equal_max_abs_kmh'],unit='km/h',file='hourly/WEIGHT_DEFINITION_DIAGNOSTIC.csv',fields='max(absolute_difference_kmh)',support='same primary node/hour set'),
    ]
    for r in h['groups']:
        for metric in ['hour_count','date_count','mean_speed_kmh','median_speed_kmh','iqr_speed_kmh']:
            claims.append(dict(claim=f"{r['precipitation_group']}:{metric}",value_unrounded=r[metric],unit='km/h' if 'kmh' in metric else 'count',file='hourly/PRECIPITATION_GROUP_SUMMARY.csv',fields=f"{metric} where precipitation_group={r['precipitation_group']}",support='same node sets; endpoint precipitation; hourly samples'))
    csv_write(out/'CLAIM_EVIDENCE.csv',claims,list(claims[0]))
    excludes={'OUTPUT_MANIFEST.csv','SHA256_MANIFEST.csv','MANIFEST_VERIFY.json'}
    files=sorted(p for p in out.rglob('*') if p.is_file() and p.name not in excludes and '__pycache__' not in p.parts)
    manifest=[dict(file=p.relative_to(out).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]
    csv_write(out/'OUTPUT_MANIFEST.csv',manifest,['file','bytes','sha256'])
    csv_write(out/'SHA256_MANIFEST.csv',manifest,['file','bytes','sha256'])
    passed=all((out/r['file']).stat().st_size==r['bytes'] and sha(out/r['file'])==r['sha256'] for r in manifest)
    archive=out.parent/(out.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files+[out/'OUTPUT_MANIFEST.csv',out/'SHA256_MANIFEST.csv']:z.write(p,arcname=p.relative_to(out).as_posix())
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip();members=z.namelist()
        contents=all(hashlib.sha256(z.read(r['file'])).hexdigest()==r['sha256'] for r in manifest)
    result=dict(verified_utc=datetime.now(timezone.utc).isoformat(),manifest_payload_count=len(manifest),payload_hashes_match=passed,output_manifest_sha256=sha(out/'OUTPUT_MANIFEST.csv'),sha256_manifest_sha256=sha(out/'SHA256_MANIFEST.csv'),zip_path=str(archive),zip_bytes=archive.stat().st_size,zip_sha256=sha(archive),zip_test='PASS' if bad is None else bad,zip_payloads_match=contents,zip_members=len(members),excluded_controls=sorted(excludes),status='PASS' if passed and bad is None and contents else 'FAIL')
    (out/'MANIFEST_VERIFY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main(Path(sys.argv[1]))
