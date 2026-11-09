# Web 失败案例 02

来源：人工截图、服务日志及候选属性核对；未捕获原始响应 JSON。
样本：conv-41；K=5；补检开启。
问题：What is John currently doing as a volunteer in August 2023?
标准答案：mentoring students at a local school
金标证据：D31:1

分别在 rules 和 hybrid/deepseek/deepseek-flash 配置下运行，
两次页面结果相同：
- 初始 5 条，补检新增 0 条。
- 提示：候选属于可累积的事实属性，保留初始候选。
- 有效 Memory：mem-conv41-415。
- 答案：John visited a military memorial with his kids the week before 3 August 2023, and his kids were awestruck and humbled by the experience.
- 引用：session_27 / D27:9。
- 回答错误。

候选属性：
mem-conv41-118：John / future_plan / volunteer_to_serve_his_country
mem-conv41-125：John / 空属性
mem-conv41-415：John / 空属性
mem-conv41-428：Maria / 空属性
mem-conv41-488：Maria / 空属性

结合调用条件核对：这些候选无法形成关系判断所需的记忆对，
本题未触发 DeepSeek 关系判断；答案仍为规则/模板生成。
不能将此结果称为 DeepSeek 判断失败或补检成功。
DeepSeek 模式服务日志：web-session-deepseek.log。
用途：开发集验收案例，不计入正式测试集成绩。
