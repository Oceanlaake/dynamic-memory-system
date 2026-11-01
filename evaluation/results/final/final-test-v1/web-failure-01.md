# Web 失败案例 01

记录来源：人工页面观察与截图；未捕获原始请求/响应 JSON。
用途：开发集 Web 验收失败案例，不作为正式测试集成绩。

代码：1f65066241b3e954a0a4bf71460369d53c219aaa
Memory：outputs/final-test-v1/memories
样本：conv-41
Retriever：hybrid
Resolver：rules
初始候选：5 条
补检新增：0 条
页面提示：未识别为支持的动态问题，保留初始候选。

问题：Who did Maria have dinner with on May 3, 2023?
标准答案：her mother
标准证据：D13:16

实际答案：
Maria participated in a charity event on Friday 3 February 2023, serving meals to people in need.

实际答案证据：session_6 / D6:1
系统选择的有效 Memory：mem-conv41-077

初始候选顺序：
1. mem-conv41-077
2. mem-conv41-188
3. mem-conv41-368
4. mem-conv41-238
5. mem-conv41-187

第 5 条内容：
Maria made dinner together with her mom last night.

结论：回答错误，引用证据与金标不符。
待核实：第 5 条是否引用 D13:16；实际答案生成路径是否调用 LLM。
用户观察：响应很快，怀疑未调用 DeepSeek；尚未证实。

## 代码核实
当前 Web 使用规则/模板作答，没有调用 DeepSeek 生成答案。
依据：backend/dynamic_state/resolver.py 的 _answer 方法，
普通问题直接返回第一条有效 Memory 的 content。
当前 rules Resolver 不调用关系判断 LLM；hybrid Resolver 的 LLM
用途是辅助关系判断，不是答案生成。
本案例属于当前规则作答系统，不属于计划中的统一 LLM QA 配置。
