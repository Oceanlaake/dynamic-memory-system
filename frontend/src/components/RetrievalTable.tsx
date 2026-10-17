import { Progress, Space, Table, Tag, Typography } from "antd";
import type { ColumnsType } from "antd/es/table";

import type { CandidateMemory } from "../types/api";
import MemoryCard from "./MemoryCard";
import { MATCH_META, MEMORY_TYPE_META, scoreColor, tagStyle } from "./labels";

interface Props {
  candidates: CandidateMemory[];
  effectiveIds: Set<string>;
}

export default function RetrievalTable({ candidates, effectiveIds }: Props) {
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
              <Tag color="success">有效记忆</Tag>
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
        const meta = MEMORY_TYPE_META[candidate.memory.type];
        return <Tag style={tagStyle(meta)}>{meta.label}</Tag>;
      },
    },
    {
      title: "相关度",
      width: 168,
      render: (_, candidate) => (
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
      ),
    },
    {
      title: "命中来源",
      width: 118,
      render: (_, candidate) => (
        <Space size={4} wrap>
          {(candidate.matched_by ?? []).map((source) => {
            const meta = MATCH_META[source];
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
