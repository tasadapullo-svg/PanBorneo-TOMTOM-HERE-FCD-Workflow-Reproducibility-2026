"""Write evidence report and internal delivery ZIP after both QA runs pass."""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
import csv,hashlib,json,math,statistics,sys,zipfile

OUT=Path(sys.argv[1]).resolve()
METHODS=['Linear','LOCF','Train-TOD median','Spatial median']
KS=[1,4,12,24]
def read(p):
    with p.open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,rows,fields):
    with p.open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def table(rows,columns):
    return '| '+' | '.join(columns)+' |\n| '+' | '.join(['---']*len(columns))+' |\n'+'\n'.join('| '+' | '.join(str(r[c]) for c in columns)+' |' for r in rows)

def main():
    q=json.loads((OUT/'qa/INDEPENDENT_QA.json').read_text(encoding='utf-8'))
    bq=read(OUT/'qa/BUILD_QA.csv')
    context=json.loads((OUT/'RUN_CONTEXT.json').read_text(encoding='utf-8'))
    if q['failed_count'] or any(r['status']!='PASS' for r in bq):raise RuntimeError('QA failed')
    if sha(OUT/'verify_reconstruction.py')!=q['verifier_sha256'] or sha(OUT/'build_reconstruction.py')!=context['script_sha256']:raise RuntimeError('Scripts changed after recorded run')
    support=read(OUT/'inputs/CANDIDATE_SUPPORT_SUMMARY.csv')
    metrics=read(OUT/'results/METRICS_BY_LENGTH_METHOD.csv')
    gaps=read(OUT/'inputs/FROZEN_GAPS.csv')
    refs=read(OUT/'reference/HIDDEN_PROVIDER_TARGETS.csv')
    points=read(OUT/'results/POINT_SCORES.csv')
    si={int(r['K']):r for r in support}
    mi={(int(r['K']),r['method']):r for r in metrics}
    config=json.loads((OUT/'CONFIG.json').read_text(encoding='utf-8'))
    summary=json.loads((OUT/'RESULT_SUMMARY.json').read_text(encoding='utf-8'))
    # Post-scoring reference-only descriptive diagnostics; never used for eligibility.
    by_gap=defaultdict(list);reuse=defaultdict(list)
    for r in refs:
        by_gap[r['gap_id']].append(float(r['hidden_provider_speed_kmh']))
        reuse[(r['node_id'],r['target_time'])].append((int(r['K']),r['gap_id']))
    diag=[dict(gap_id=r['gap_id'],K=int(r['K']),node_id=r['node_id'],target_point_count=len(by_gap[r['gap_id']]),target_distinct_speed_count=len(set(by_gap[r['gap_id']])),target_min_speed_kmh=min(by_gap[r['gap_id']]),target_max_speed_kmh=max(by_gap[r['gap_id']]),target_speed_range_kmh=max(by_gap[r['gap_id']])-min(by_gap[r['gap_id']]),all_targets_same_speed=len(set(by_gap[r['gap_id']]))==1,stage='post-scoring reference description; never selection input') for r in gaps]
    write(OUT/'reference/SELECTED_REFERENCE_DIAGNOSTICS.csv',diag,list(diag[0]) if diag else ['gap_id','K','node_id','target_point_count','target_distinct_speed_count','target_min_speed_kmh','target_max_speed_kmh','target_speed_range_kmh','all_targets_same_speed','stage'])
    rr=[dict(node_id=n,target_time=t,experiment_reference_count=len(v),length_Ks='|'.join(str(k) for k in sorted({k for k,g in v})),gap_ids='|'.join(g for k,g in v)) for (n,t),v in sorted(reuse.items())]
    write(OUT/'reference/CROSS_LENGTH_TARGET_REUSE.csv',rr,['node_id','target_time','experiment_reference_count','length_Ks','gap_ids'])
    old=[dict(K=k,old_figure_n_as_handoff_claim=n,new_selected_gaps=int(si[k]['selected_gaps']),difference=int(si[k]['selected_gaps'])-n,old_source='handoff section11.3; old figure claim, not a recovered execution',old_metric_status='No audited old prediction table; RMSE/MAE not reused',interpretation='Matching n does not prove identical protocol or samples') for k,n in zip(KS,[300,200,80,17])]
    write(OUT/'results/OLD_FIGURE7_COUNT_COMPARISON.csv',old,list(old[0]))
    support_rows=[{'缺口h':r['duration_h'],'合格候选':r['eligible_candidates'],'最大非重叠容量':r['maximum_nonoverlap_capacity'],'实际抽样N':r['selected_gaps'],'目标点M':int(r['selected_gaps'])*int(r['K']),'节点数':r['selected_nodes'],'起始日期数':r['selected_start_dates'],'跨午夜缺口':r['cross_midnight_gaps']} for r in support]
    st=table(support_rows,list(support_rows[0]))
    metric_rows=[{'方法':m,**{f'{k/4:g} h RMSE / MAE':f"{float(mi[(k,m)]['pooled_rmse_kmh']):.4f} / {float(mi[(k,m)]['pooled_mae_kmh']):.4f}" if int(mi[(k,m)]['M_target_points']) else 'NA / NA' for k in KS}} for m in METHODS]
    mt=table(metric_rows,list(metric_rows[0]))
    exclusion_rows=read(OUT/'inputs/CANDIDATE_EXCLUSIONS.csv')
    ex={ (int(r['K']),r['reason']):int(r['exclusive_first_failure_count']) for r in exclusion_rows}
    exc=[{'K':k,'越界':ex[(k,'OUTSIDE_TEST_CONTEXT')],'目标含自然缺项':ex[(k,'TARGET_NATURAL_MISSING')],'紧邻端点缺项':ex[(k,'ENDPOINT_MISSING')],'训练支持不足':ex[(k,'TRAIN_TOD_SUPPORT_LT3')],'其他节点支持不足':ex[(k,'OTHER_NODE_SUPPORT_LT3')]} for k in KS]
    et=table(exc,list(exc[0]))
    constant={k:sum(r['K']==k and r['all_targets_same_speed'] for r in diag) for k in KS}
    reused=sum(len(v)>1 for v in reuse.values())
    report=f'''# 第三批验收报告：5.4单节点回顾性缺口重建

日期：2026年10月6日，Australia/Sydney。运行ID：20261006_b03_124252Z。输入：TOMTOM_CORE_20261004。

**E06的候选资格、冻结遮蔽清单、四方法重建、评分和独立复核已完成。**原输入、第一/二批、Word、图片及交接文件未修改。本批未运行5.5预测，也未给旧图7数字追认原算法。结果只代表本协议下原本存在的提供方观测被受控遮蔽后的重建表现，不是地面速度准确率或自然缺项恢复验证。

## 1 实验定义与切分

15分钟归一化去重、非插补快照；不使用5.3小时均值或3/4、41节点门槛。训练[12-08 00:00,12-24 00:00)，验证[12-24 00:00,12-28 00:00)，测试[12-28 00:00,2026-01-01 00:00)，均为2025年12月、Asia/Kuching、左闭右开。对应原行数59,009/16,128/15,792。四种基线无调参，验证区仅预留，没有优化或训练后合并验证数据。

训练期按node_id×96个15分钟钟点拟合中位数；共4,896组，支持范围{summary['training_TOD']['min_count']}–{summary['training_TOD']['max_count']}条，少于3条的组{summary['training_TOD']['insufficient_groups']}个。保存59,009条成员与4,896组统计，并在读取候选和评分前记录统计哈希；评分后相同。

K=1/4/12/24，对应0.25/1/3/6小时。目标为t0…t0+(K−1)Δ，紧邻端点为t0−Δ、t0+KΔ，端点间隔(K+1)Δ。目标和两端点均为原观测且在测试区内，每点训练TOD至少3条、排除目标节点后同时刻其他节点至少3个。自然缺项一直保持缺项，候选不按速度值、平稳程度或最终误差筛选。

## 2 实际支持、排除与非重叠抽样

{st}

每档初始起始位置集合为51节点×384测试槽=19,584位置，含不可能满足端点边界的位置，按以下顺序记录首次排除原因；该表各原因互斥，与合格候选数合计19,584。CANDIDATE_EXCLUSIONS.csv另有“全部失败标记”计数，该列可重复，不能直接相加当总排除数。

{et}

固定SeedSequence(20261006).spawn(4)，按K=1/4/12/24使用独立PCG64子流，Numpy版本{context['numpy']}。先按节点、起始日期、t0排序；组内打乱候选，再打乱节点×日期组次序，轮流取候选。每档最多300，同档同节点的闭区间[左端点,右端点]不得重叠或共享端点，跨午夜组同样检查。完整候选/处置、生成器状态和最终gap_id表均保存。

**3小时档的217是最大可容纳数量，211是本次固定抽样结果。**本次抽样已遍历1,045候选：211选中、834因已选窗口重叠排除；没有剩余可追加窗口。最大容量采用最早结束区间算法计算，独立QA用动态规划复核。随机贪心抽样得到一个无法继续追加候选的集合，这不保证达到数学上的最大数量；为了增加6个样本而更改种子/替换窗口会是不同抽样配置，本批未这样做。

6小时档85合格候选中17选中、68重叠排除；最大容量17，覆盖15节点及4起始日期，4个窗口跨午夜。0.25/1小时档达到300上限，剩余未访问候选分别10,233/5,397，已访问重叠排除分别8/25。上限未被当作缺口总量或数据完整性指标。

每个缺口独立从同一冻结基底开始，仅遮蔽一个节点的一段；其他节点的原本可用记录可见。不是同时遮蔽所有缺口或全网络中断。不同长度可重用位置，已选参照共{len(refs):,}个实验目标点，来自{len(reuse):,}个唯一原节点—时段键，其中{reused:,}个键被多个长度重用，详见CROSS_LENGTH_TARGET_REUSE.csv。不得把828个跨长度缺口或4,440个参照点称为相互独立新交通观测。

## 3 遮蔽与输入隔离

inputs/ALLOWED_SPEED_CONTEXT.csv只保留gap_id、角色、节点、时间、允许可见速度及来源定位；每个缺口只含目标节点两端点及各目标时刻其他节点原速度。隐藏目标单独保存在reference/HIDDEN_PROVIDER_TARGETS.csv。训练中位数另作为FROZEN_TOD_INPUTS.csv，引用训练支持数；每点其他节点名单及计数保存在TARGET_SUPPORT.csv。

重建函数只接收K、左右端速度、训练TOD、其他节点速度，未接收评分参照、通行时间、confidence、自由流速度或任何目标派生变量。四方法使用相同gap_id/目标时间：Linear允许右端未来观测，仅是回顾性线性插值；LOCF重复左端；Train-TOD只读训练区中位数；Spatial median取全网同时刻其他节点中位数，不是已验证的局部地理插值。没有先在完整测试表插值、无回退/裁剪、无递归填值。

独立验证从实际导出的允许输入重算所有预测，确认当前缺口隐藏键不存在于可见输入中，再单独连评分参照。其他缺口的同键是否可见不能跨实验混为一张同时遮蔽表。

## 4 正式点汇总误差

单位km/h；误差=重建−被遮蔽提供方快照。主RMSE=sqrt(Σe²/M)，MAE=Σ|e|/M，每档分别计算，M=N×K；不是缺口RMSE的平均。全部方法完整预测数与共同完整数均为300/300/211/17，完成率和共同保留率100%，失败0，失败表为空但保留表头；没有删除困难点或把失败误差填0。

{mt}

按本次点估计，Linear在0.25/1/3小时档RMSE较低，Train-TOD在6小时档RMSE较低。这不是统计显著最优、实时在线填补能力或对所有自然缺项机制的结论。RMSE与MAE可能给出不同的排序，需同时保留。Spatial median的全网定义不能被此结果偷换为道路邻域或其他空间模型。

逐点参照/预测/误差及来源：results/POINT_SCORES.csv；逐缺口SSE、MSE、RMSE、MAE：GAP_METRICS.csv；总体和缺口RMSE中位数/Q25/Q75：METRICS_BY_LENGTH_METHOD.csv。分位数使用linear经验插值，是缺口误差分布，不是总体RMSE的95%CI。本批没有bootstrap或显著性检验。

一些缺口级RMSE的中位数和四分位数为0，不是缺预测填0。评分后对所选隐藏片段核查：目标速度全相同的缺口数为{constant[1]}/{si[1]['selected_gaps']}（K1天然只有一点）、{constant[4]}/{si[4]['selected_gaps']}、{constant[12]}/{si[12]['selected_gaps']}、{constant[24]}/{si[24]['selected_gaps']}，逐缺口范围和唯一速度数见SELECTED_REFERENCE_DIAGNOSTICS.csv。该文件只做评分后描述，未用于抽样或参数选择；零误差也不证明这些快照等于地面真实速度。

不同长度合格片段和节点构成不同，尤其6小时需连续24目标及两端点原观测，支持更受限。因此6小时RMSE低于3小时不能解释为“更长缺口更容易恢复”。同一长片段的嵌套长度对照未执行，四测试日期及同节点/跨午夜依赖也限制了推广范围；未验证14小时、整天、窗口边界自然缺项或全网中断。

## 5 与旧图差异及证据状态

交接文件记录旧图的N为300/200/80/17，本次为300/300/211/17，差值0/+100/+131/0。旧执行配置和逐点结果没有在本批恢复，所以旧RMSE/MAE和误差线未沿用。6小时同为17只表示数量碰巧一致，不证明协议、候选、样本或误差相同。详见OLD_FIGURE7_COUNT_COMPARISON.csv；旧图7(a)仍需按本次新结果同步。

## 6 QA、交付与下一步

12冻结载荷及清单与SHA-256匹配；本次引用的交接文件和第二批报告/清单也登记哈希，全部16入口文件前后不变。生成QA {len(bq)}项PASS；独立QA {q['check_count']}项PASS、0 FAIL，原记录中位数、全部候选、随机重放、最大容量动态规划、非重叠窗口、每方法共同目标、输入隔离和评分均已核对。键、计数和集合要求精确一致，预测/误差/指标浮点容差1e-10；仅累计SSE另用相对1e-12，防止求和次序的无意义误差。

直接可读的CSV/JSON、脚本和数据指南都在本目录：`{OUT}`。CONFIG.json在结果前生成，RUN_CONTEXT.json保存实测环境/脚本版本。输出清单与SHA-256不递归包含自身；内部ZIP及其内容校验结果见MANIFEST_VERIFY.json。本批没有发布资料或选定共享许可。

E06的本次受控回顾性基准完成，5.4正文和图7(a)同步仍待后续；E07预测未执行，首批记录时间代理部分成立及真实在线证据限制仍保留。E08图稿未同步，E09仅本批重跑/复算范围有证据，尚不代表全部冻结构建与分析流水线复现；G2/G3仍未通过。

下一步可将第二批证据用于Figure 4及5.2/5.3正文，再同步本批5.4与图7(a)。图稿开始前应先给出图数、内容与论文位置；5.5须处理既有时间准入，不以本批回顾性插值成功代替预测输入时刻证明。
'''
    (OUT/'BATCH03_ACCEPTANCE.md').write_text(report,encoding='utf-8')
    guide='''# E06数据与复现指南

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
$taskPython = 'C:\\Users\\stfr2\\.cache\\codex-runtimes\\codex-primary-runtime\\dependencies\\python\\python.exe'
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
'''
    (OUT/'DATA_GUIDE.md').write_text(guide,encoding='utf-8')
    claims=[]
    for r in metrics:
        for metric in ['N_gaps','M_target_points','pooled_rmse_kmh','pooled_mae_kmh','gap_rmse_median_kmh','gap_rmse_q25_kmh','gap_rmse_q75_kmh','node_count']:
            claims.append(dict(claim=f"K{r['K']}:{r['method']}:{metric}",value_unrounded=r[metric],unit='km/h' if 'kmh' in metric else 'count',file='results/METRICS_BY_LENGTH_METHOD.csv',fields=f"{metric} where K={r['K']} and method={r['method']}",derivation='results/POINT_SCORES.csv and GAP_METRICS.csv',scope='single-node retrospective controlled masking; provider reference'))
    write(OUT/'CLAIM_EVIDENCE.csv',claims,list(claims[0]))
    excludes={'OUTPUT_MANIFEST.csv','SHA256_MANIFEST.csv','MANIFEST_VERIFY.json'}
    files=sorted(p for p in OUT.rglob('*') if p.is_file() and p.name not in excludes and '__pycache__' not in p.parts)
    rows=[dict(file=p.relative_to(OUT).as_posix(),bytes=p.stat().st_size,sha256=sha(p)) for p in files]
    for name in ['OUTPUT_MANIFEST.csv','SHA256_MANIFEST.csv']:write(OUT/name,rows,['file','bytes','sha256'])
    matched=all(sha(OUT/r['file'])==r['sha256'] and (OUT/r['file']).stat().st_size==r['bytes'] for r in rows)
    archive=OUT.parent/(OUT.name+'.zip')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in files+[OUT/'OUTPUT_MANIFEST.csv',OUT/'SHA256_MANIFEST.csv']:z.write(p,p.relative_to(OUT).as_posix())
    with zipfile.ZipFile(archive) as z:
        bad=z.testzip();payloads=all(hashlib.sha256(z.read(r['file'])).hexdigest()==r['sha256'] for r in rows);member_count=len(z.namelist())
    result=dict(verified_utc=datetime.now(timezone.utc).isoformat(),manifest_payload_count=len(rows),payload_hashes_match=matched,output_manifest_sha256=sha(OUT/'OUTPUT_MANIFEST.csv'),sha256_manifest_sha256=sha(OUT/'SHA256_MANIFEST.csv'),zip_path=str(archive),zip_bytes=archive.stat().st_size,zip_sha256=sha(archive),zip_test='PASS' if bad is None else bad,zip_payloads_match=payloads,zip_members=member_count,excluded_controls=sorted(excludes),status='PASS' if matched and bad is None and payloads else 'FAIL')
    (OUT/'MANIFEST_VERIFY.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if result['status']!='PASS':raise SystemExit(1)

if __name__=='__main__':main()
