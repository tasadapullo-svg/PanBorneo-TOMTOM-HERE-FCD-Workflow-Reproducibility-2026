# Figure 7(b)详细文字绘图指令

本轮只交文字、CSV和英文图注，没有绘制或渲染图片。日期：2026年10月7日，Australia/Sydney。

## 图数、内容、论文位置

准备1个Figure7(b)组件，放在第5.5节，与Figure7(a)的受控重建基准对应。本组件内采用三个并排小坐标区，分别为1 h、3 h、6 h，展示同一预测任务的总体和训练期可用率分层结果。仍保留一个整体子图标号`(b)`，小坐标区使用步长标题，不新增Figure7(c)/(d)或另一张主图。

每个小坐标区横轴有`Overall`、`Low`、`Medium`、`High`四组；每组并排画三方法MAE点估计。Overall是后三层共同评分记录的合计，不是第四个独立层。主图同时回答方法比较、预测步长和层间描述性差异。RMSE保留在正文表格，不与MAE混入同一纵轴系列。

## 布局与映射

- 独立组件默认16:9，180 × 101.25 mm。三个小坐标区等宽约45–48 mm，间距约6–8 mm；先预留统一图例、标题、横轴样本量和页脚，再分配绘图区。目标期刊尺寸优先，未来与7(a)拼版时再次检查实际字号。
- 整体标题建议`Retrospective forecasting by observation availability`，左上角`(b)`。三个小标题分别`1 h`、`3 h`、`6 h`。
- 共用纵轴名称`Pooled MAE (km/h)`；三个区都使用0–4.5 km/h范围，主刻度0、1、2、3、4。当前全部36个点的最高值为3.78646 km/h，不能为了强调差异截断纵轴或各区采用不同尺度。
- 横轴`Evaluation subset`。四组可用位置0、1.4、2.4、3.4，在Overall与Low之间预留稍宽间隔并加淡灰竖虚线；这只帮助区分合计与分层，不表示统计检验。
- 组内固定方法顺序Persistence、Seasonal24、Ridge，横向偏移可取−0.18、0、+0.18。点之间不连线，不拟合随步长或可用率的趋势。
- 颜色/形状同时区分方法：Persistence蓝色#0072B2/圆；Seasonal24橙色#E69F00/方；Ridge紫色#CC79A7/菱形。图例共享一次，置于顶部预留区域。
- 白底、Arial、淡灰水平网格。最终印刷字号8–9 pt，方法点约4.5–5.5 pt，轮廓0.7 pt。标题较长时换行，不缩小到不可读。
- 每组横轴下用第二行显示`n=...`，n为可评分node×origin×H目标条数，不是节点数或独立事件数。三个方法共用该组n，只显示一次。Overall与三层n详见支持表。
- 建议不在36个相近点旁堆满数字；完整核对表保留在本文件及正文/CSV。若增加点值，按统一规则处理每组的三方法、显示两位小数并自动错位，不能只标注最佳方法。作图坐标使用未舍入CSV值。
- 图下短注可写`Training-defined strata; 17 nodes per stratum`。解释阈值和输入可见性主要放英文图注，不把长方法说明挤入绘图区。
- 不画误差棒、95%CI、星号、显著性括号或“Ridge best”等预设标签。本批没有计算统计区间；各节点/日期误差也不能直接拿来给汇总MAE点做CI。

## 主图数据文件和字段

直接读取：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\figure_source\Figure7b_point_estimates.csv`。

该文件与正式results/METRICS_OVERALL_AND_STRATA.csv逐字节相同，共36行：3个H × 4个subset × 3个方法。必须使用`H_h`分面、`stratum`作为横轴四组、`method`作为颜色/形状、`mae_kmh`作为唯一主纵轴。`N_scores`作为n；`assigned_node_count`与`scoring_node_count`区别节点支持；`target_date_count`为目标日期数。`rmse_kmh`是辅助指标，不可作为MAE。`score_fraction_of_input_ready`是评分参照覆盖比例，不是预测准确率。

样本支持CSV：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\figure_source\Figure7b_sample_support.csv`，12行，每H/subset一行。

训练阈值和节点标签：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\figure_source\Figure7b_training_availability.csv`。固定分母1536，q1=0.74934895833333337、q2=0.75672743055555558，Low≤q1、Medium(q1,q2]、High>q2。不得把可用率称为confidence、预测正确率或固有道路质量，不按测试结果重分组。

## MAE与n核对表

所有MAE单位km/h；下表仅供标签核对，坐标仍读取CSV未舍入值。

| H (h) | Subset | n | Persistence | Seasonal24 | Ridge |
| --- | --- | --- | --- | --- | --- |
| 1 | Overall | 5863 | 2.00 | 2.16 | 2.21 |
| 1 | Low | 2031 | 1.90 | 2.09 | 2.14 |
| 1 | Medium | 1953 | 2.08 | 2.22 | 2.17 |
| 1 | High | 1879 | 2.03 | 2.16 | 2.33 |
| 3 | Overall | 5727 | 2.59 | 2.27 | 2.53 |
| 3 | Low | 2005 | 2.36 | 2.34 | 2.58 |
| 3 | Medium | 1899 | 2.90 | 2.38 | 2.64 |
| 3 | High | 1823 | 2.53 | 2.07 | 2.37 |
| 6 | Overall | 5535 | 3.33 | 2.19 | 2.50 |
| 6 | Low | 1927 | 3.15 | 2.31 | 2.60 |
| 6 | Medium | 1817 | 3.79 | 2.22 | 2.57 |
| 6 | High | 1791 | 3.05 | 2.03 | 2.33 |

总体RMSE及MAE的完整并列结果在第5.5节英文正文：1 h最低MAE是Persistence，3/6 h最低MAE是Seasonal24；Ridge在三个H的RMSE最低，但主指标MAE并非最低。图面不能用“Ridge全面最优”的标题或突出方式覆盖这一结果。

## 统计与样本边界

同H三方法使用相同评分键，没有方法失败；输入合格预测分别7158/7144/6892条，其中1295/1417/1357没有有效未来参照，保留为未评分。主图n=5863/5727/5535；方法完成100%不表示全19584候选都能预测，也不是100%准确。

不同H与层的样本构成不同，测试仅4个日期。三个H共同2504个测试决策的敏感性结果另存`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\figure_source\Figure7b_common_origin_sensitivity.csv`；它控制决策集合，但目标时刻仍不同，不把变化全部归因于步长。

同层17个节点不意味着n相同。High层不保证误差更低，例如Ridge 1h的Medium/High MAE比为0.9308，按原结果保留；3h/6h对应1.1159/1.1035。主图展示真实三层误差，不仅显示比值。

预测参照是提供方原观测，不是地面真值。记录字段支持的是回顾性可见性代理，未证明历史系统真实在线到达。降水、HERE、confidence、自由流速度、重建填补数据不参与本预测输入。

## 可直接交给绘图工具的指令

“读取Figure7b_point_estimates.csv，制作一个16:9的Figure7(b)组件，内含并排的1 h、3 h、6 h三个小坐标区。每区横轴按Overall、Low、Medium、High排列，每组画Persistence蓝圆、Seasonal24橙方、Ridge紫菱形三点。纵轴仅用mae_kmh，三坐标区统一0–4.5 km/h，不连线、无误差棒、无显著性符号。Overall与Low之间留稍宽间隔并用淡灰虚线区分合计和分层，不能把Overall当第四个独立层。组下标实际N_scores为n，17 nodes per stratum放短注，长定义放配套英文图注。图例共享一次，文字留足边距，最终印刷字号8–9 pt；不在36个相近点旁强行堆满数字，若加标签则一致处理同组全部方法且不移动数据坐标。使用CSV未舍入值定位，不能复制旧图数值。输出内容一致的PNG/TIFF 300和600 dpi及可编辑SVG，保存实际绘图脚本与图源、文件清单和SHA256。”

## 正式分析证据路径

- 逐条测试评分：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\results\TEST_POINT_SCORES.csv`。
- 总体和三层指标：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\results\METRICS_OVERALL_AND_STRATA.csv`。
- 完成率和未评分支持：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\results\COMPLETION_COUNTS.csv`。
- 所有alpha验证结果：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\models\ALPHA_VALIDATION_METRICS.csv`。
- 每H选定模型、缩放和特征顺序：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\models`中的RIDGE_H1/H3/H6.json。
- 逐节点误差/节点宏平均：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\results\METRICS_BY_NODE.csv`与`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\results\NODE_MACRO_MAE.csv`。
- 逐目标日期及日期×层误差：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\results\METRICS_BY_TARGET_DATE.csv`与`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\results\METRICS_BY_TARGET_DATE_STRATUM.csv`。
- 配对误差差值：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\results\PAIRED_POINT_ERROR_DIFFERENCES.csv`。
- 字段、时间和算法配置：`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\CONFIG.json`；独立核对见`D:\HuaweiMoveData\Users\stfr2\Documents\ChatGPT\论文 - 1\outputs\Manuscript_Execution_20261007_b07_002757Z\batch07_forecasting\qa\INDEPENDENT_QA.json`。

## 导出验收

180 × 101.25 mm对应300 dpi约2126×1196像素、600 dpi约4252×2392像素。TIFF建议LZW，SVG保留可编辑文字/标记。检查36点、12个n、方法颜色/形状、轴单位和统一范围，与源CSV完全一致；无错误CI、无越界/重叠/裁切、三个格式内容一致。本批尚未收到或检验Figure7(b)图稿，最终视觉验收待用户绘制后完成。
