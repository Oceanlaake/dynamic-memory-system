import { Alert, Empty, Space, Tag, Typography } from "antd";

import type { GraphNode, GraphNodeType, GraphTrace } from "../types/api";

const nodeMeta: Record<GraphNodeType, { label: string; color: string }> = {
  memory: { label: "Memory", color: "blue" },
  subject: { label: "人物", color: "cyan" },
  slot: { label: "状态槽位", color: "purple" },
  value: { label: "取值", color: "magenta" },
  session: { label: "Session", color: "gold" },
  turn: { label: "Turn", color: "green" },
};

function compactLabel(node: GraphNode | undefined, nodeId: string): string {
  if (!node) return nodeId;
  if (node.node_type === "memory") return node.memory_id ?? node.node_id;
  return node.label.length > 34 ? `${node.label.slice(0, 31)}…` : node.label;
}

export default function GraphMemoryPanel({ trace }: { trace: GraphTrace }) {
  if (!trace.enabled) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Graph Memory 未开启" />;
  }
  const byId = new Map(trace.nodes.map((node) => [node.node_id, node]));
  const status = trace.stop_reason === "expanded" ? "已完成多跳扩展" :
    trace.stop_reason === "candidate_limit" ? "达到 Graph 候选上限" :
      trace.stop_reason === "no_seed" ? "没有可用的初始种子" : "没有发现新的相关 Memory";

  return (
    <div>
      <Alert
        type={trace.truncated ? "warning" : "success"}
        showIcon
        message={status}
        description={`种子 ${trace.seed_memory_ids.length} 条 · 访问 ${trace.visited_node_count} 个节点 · 新增 ${trace.added_memory_ids.length} 条 Memory · 最大 ${trace.max_hops} 跳`}
      />
      {trace.paths.length ? (
        <div className="graph-paths">
          {trace.paths.map((path) => (
            <div className="graph-path" key={`${path.memory_id}-${path.node_ids.join("-")}`}>
              <div className="graph-path-title">
                <Tag color="geekblue">{path.hops} 跳</Tag>
                <Typography.Text code>{path.memory_id}</Typography.Text>
              </div>
              <div className="graph-path-track">
                {path.node_ids.map((nodeId, index) => {
                  const node = byId.get(nodeId);
                  const meta = nodeMeta[node?.node_type ?? "memory"];
                  return (
                    <Space key={`${nodeId}-${index}`} size={4} wrap>
                      {index > 0 ? (
                        <span className="graph-edge-label">—{path.relations[index - 1]}→</span>
                      ) : null}
                      <Tag color={meta.color} title={node?.label ?? nodeId}>
                        {meta.label}: {compactLabel(node, nodeId)}
                      </Tag>
                    </Space>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="没有形成新增 Memory 的多跳路径" />
      )}
    </div>
  );
}
