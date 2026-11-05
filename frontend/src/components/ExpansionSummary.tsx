import { Alert, Space, Tag, Typography } from "antd";
import type { EvidenceStatus, ExpansionTrace } from "../types/api";

const stopLabels: Record<ExpansionTrace["stop_reason"], string> = {
  disabled: "已关闭补检，使用固定 Top-K",
  not_dynamic: "未识别为支持的动态问题，保留初始候选",
  not_comparable: "候选属于可累积的事实属性，保留初始候选",
  no_seed: "未找到与问题相关的证据种子",
  no_new_memory: "所选槽位没有更多历史",
  expanded: "已补全所选槽位的历史",
  candidate_limit: "达到补检上限，历史可能不完整，暂不作答",
};

const evidenceLabels: Record<EvidenceStatus, string> = {
  not_checked: "未检查", sufficient: "证据满足当前规则",
  insufficient: "证据不足", missing_anchor: "缺少起止时间锚点",
  missing_transition: "缺少前后状态", conflict: "存在未解决冲突",
  unorderable: "无法可靠排序",
};

export default function ExpansionSummary({ trace, status }: {
  trace: ExpansionTrace; status?: EvidenceStatus;
}) {
  return (
    <Alert
      style={{ marginBottom: 16 }}
      type={trace.truncated ? "warning" : "info"}
      showIcon
      message={trace.expansion_policy === "query_evidence" && trace.stop_reason === "expanded"
        ? "已补充与问题相关的证据" :
        trace.expansion_policy === "query_evidence" && trace.stop_reason === "no_new_memory"
          ? "没有找到更多符合条件的证据" : stopLabels[trace.stop_reason]}
      description={
        <Space direction="vertical" size={4}>
          <Typography.Text>
            初始 {trace.initial_count} 条 · 补检 {trace.added_memory_ids.length} 条
            {status ? ` · ${evidenceLabels[status]}` : ""}
            {trace.budget_limited ? " · 已按相关性选取预算内的补充证据" : ""}
          </Typography.Text>
          <Space wrap size={4}>
            {trace.expanded_slots.map((slot) => (
              <Tag key={`${slot.subject}:${slot.attribute}`}>{slot.subject} / {slot.attribute}</Tag>
            ))}
          </Space>
        </Space>
      }
    />
  );
}
