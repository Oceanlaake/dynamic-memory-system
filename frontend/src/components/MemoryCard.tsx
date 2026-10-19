import { Descriptions, Tag, Typography } from "antd";
import type { DescriptionsProps } from "antd";

import type { Memory } from "../types/api";
import { MEMORY_TYPE_META, tagStyle } from "./labels";

export default function MemoryCard({ memory }: { memory: Memory }) {
  const items: DescriptionsProps["items"] = [
    {
      key: "memory_id",
      label: "记忆 ID",
      children: <span className="mono">{memory.memory_id}</span>,
    },
    { key: "subject", label: "主体", children: memory.subject },
    {
      key: "type",
      label: "类型",
      children: (
        <Tag style={tagStyle(MEMORY_TYPE_META[memory.type])}>
          {MEMORY_TYPE_META[memory.type].label}
        </Tag>
      ),
    },
    {
      key: "confidence",
      label: "置信度",
      children: memory.confidence ?? "—",
    },
    {
      key: "attribute",
      label: "属性",
      children: memory.attribute ?? "—",
    },
    { key: "value", label: "值", children: memory.value ?? "—" },
    {
      key: "time",
      label: "时间",
      children: (
        <span>
          <span className="mono">{memory.time.session_id}</span>
          {memory.time.date_time ? ` · ${memory.time.date_time}` : ""}
          {memory.time.effective_at ? ` · 生效 ${memory.time.effective_at}` : ""}
        </span>
      ),
      span: 2,
    },
    {
      key: "content",
      label: "内容",
      children: <p className="memory-content">{memory.content}</p>,
      span: 2,
    },
  ];

  return (
    <div>
      <Descriptions size="small" bordered column={2} items={items} />

      <div style={{ marginTop: 12 }}>
        <Typography.Text strong>证据来源</Typography.Text>
        {memory.evidence.map((ref) => (
          <div key={`${ref.session_id}/${ref.dia_id}`}>
            <div className="evidence-meta mono">
              {ref.session_id} / {ref.dia_id}
            </div>
            {ref.quote ? <p className="quote">{ref.quote}</p> : null}
          </div>
        ))}
      </div>
    </div>
  );
}
