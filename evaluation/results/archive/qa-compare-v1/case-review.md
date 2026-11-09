# E02 失败与回归案例

## 失败例：检索未覆盖导致状态系统拒答

问题：What pets does Jolene have? 金标：snakes。

- Full Text：Snakes (Susie and Seraphim)，命中。
- Vector RAG：A pet snake named Susie，部分命中。
- 状态 Top-K：拒答（Top-K 候选未包含宠物相关记忆）。

原因在检索覆盖而非答案生成：正确证据未进入 Top-5。

## 非动态题回归

本批 50 题补检触发 0 次，状态 Top-K 与状态 Bonus 输入候选完全相同，
因此本次规则与生成改动未对非动态事实题引入新的系统化退化；
逐题差异来自 DeepSeek 随机波动。

## 一致成功例

问题：What journal has Jolene been using to help track tasks and stay organized?
金标：bullet journal。Full Text 与状态 Top-K 均答 bullet journal。
