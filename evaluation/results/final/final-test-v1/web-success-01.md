# Web 普通正确回答案例 01

来源：人工页面观察与截图；未捕获原始响应 JSON。
用途：开发集 Web 验收案例，不代表整体 QA 性能。

样本：conv-41
配置：Hybrid 检索；hybrid Resolver，DeepSeek 配置启用；
K=5，补检开启。实际模型调用情况未核实，答案为规则/模板生成。

问题：What is the name of Maria's puppy she got two weeks before August 11, 2023?
标准答案：Coco
金标证据：D30:1

初始候选：5 条；补检新增：0 条。
页面提示：未识别为支持的动态问题，保留初始候选。
有效 Memory：mem-conv41-450。
实际答案：Maria owns a puppy named Coco, whom she got about two weeks before this conversation.
答案证据：session_30 / D30:1。

结论：答案包含正确名字，引用与金标一致，人工核对通过。
本案例没有补检收益；不将人工通过等同于 token F1=1。
