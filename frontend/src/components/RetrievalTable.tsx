import { Progress, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { CandidateMemory } from "../types/api";
import MemoryCard from "./MemoryCard";
import { matchSourceMeta, memoryTypeMeta, scoreColor, tagStyle } from "./labels";

interface Props {
  candidates: CandidateMemory[];
  effectiveIds: Set<string>;
  answerIds: Set<string>;
}

export default function RetrievalTable({ candidates, effectiveIds, answerIds }: Props) {
  const columns: ColumnsType<CandidateMemory> = [
    {
      title: "排名",
      dataIndex: "rank",
      width: 68,
      align: "center",
      render: (rank: number) => (
        <span className={`rank-badge rank-badge--${Math.min(rank, 3)}`}>{rank}</span>
      ),
    },
    {
      title: "候选记忆",
      key: "memory",
      render: (_, candidate) => (
        <div>
          <Space size={6} wrap>
            <Typography.Text code>{candidate.memory.memory_id}</Typography.Text>
            {effectiveIds.has(candidate.memory.memory_id) ? (
              <Tag color="success">规则选中</Tag>
            ) : null}
            {answerIds.has(candidate.memory.memory_id) ? (
              <Tag color="gold">答案引用</Tag>
            ) : null}
          </Space>
          <div className="memory-content">{candidate.memory.content}</div>
        </div>
      ),
    },
    {
      title: "类型",
      width: 88,
      render: (_, candidate) => {
        const meta = memoryTypeMeta(candidate.memory.type);
        return <Tag style={tagStyle(meta)}>{meta.label}</Tag>;
      },
    },
    {
      title: "检索评分",
      width: 168,
      render: (_, candidate) => {
        const source = candidate.candidate_source ?? "initial";
        if (source !== "initial" && source !== "graph_expansion") {
          return <Typography.Text type="secondary">补检未单独评分</Typography.Text>;
        }
        return (
          <div>
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {source === "graph_expansion" ? "Graph 路径×问题" : "Hybrid 相关度"}
            </Typography.Text>
            <div className="score-cell">
              <Progress
                percent={Math.round(candidate.score * 100)}
                size="small"
                showInfo={false}
                strokeColor={scoreColor(candidate.score)}
                style={{ width: 92, marginBottom: 0 }}
              />
              <span className="score-value">{candidate.score.toFixed(4)}</span>
            </div>
          </div>
        );
      },
    },
    {
      title: "命中来源",
      width: 118,
      render: (_, candidate) => (
        <Space size={4} wrap>
          <Tag color={(candidate.candidate_source ?? "initial") !== "initial" ? "purple" : "blue"}>
            {candidate.candidate_source === "graph_expansion" ? `Graph ${candidate.graph_hops ?? "?"} 跳` :
              candidate.candidate_source === "context_expansion" ? "原文邻近补检" :
              candidate.candidate_source === "slot_expansion" ? "同槽位补检" : "初始检索"}
          </Tag>
          {(candidate.matched_by ?? []).map((source) => {
            const meta = matchSourceMeta(source);
            return (
              <Tag key={source} style={tagStyle(meta)}>
                {meta.label}
              </Tag>
            );
          })}
        </Space>
      ),
    },
  ];

  return (
    <Table<CandidateMemory>
      className="candidate-table"
      rowKey={(candidate) => candidate.memory.memory_id}
      columns={columns}
      dataSource={candidates}
      pagination={false}
      size="middle"
      expandable={{
        expandedRowRender: (candidate) => <MemoryCard memory={candidate.memory} />,
        rowExpandable: () => true,
      }}
    />
  );
}
