import { Col, Empty, Row, Tag, Timeline, Typography } from "antd";

import type {
  CandidateMemory,
  EffectiveMemory,
  Relation,
} from "../types/api";
import { relationMeta } from "./labels";

interface Props {
  relations: Relation[];
  candidates: CandidateMemory[];
  effectiveMemories: EffectiveMemory[];
}

export default function RelationTimeline({
  relations,
  candidates,
  effectiveMemories,
}: Props) {
  const byId = new Map(
    candidates.map((candidate) => [candidate.memory.memory_id, candidate.memory]),
  );

  const timelineItems = relations.map((relation, index) => {
    const meta = relationMeta(relation.relation);
    const fromMemory = byId.get(relation.from);
    const toMemory = byId.get(relation.to);

    return {
      key: `${relation.from}-${relation.to}-${index}`,
      color: meta.hex,
      children: (
        <div className="relation-block" style={{ borderLeft: `3px solid ${meta.hex}` }}>
          <div>
            <Tag color={meta.color}>{meta.label}</Tag>
            <Typography.Text code>{relation.from}</Typography.Text>
            <span> → </span>
            <Typography.Text code>{relation.to}</Typography.Text>
          </div>
          {fromMemory ? (
            <div className="relation-memory">旧：{fromMemory.content}</div>
          ) : null}
          {toMemory ? (
            <div className="relation-memory">新：{toMemory.content}</div>
          ) : null}
          <div className="timeline-reason">判断依据：{relation.reason}</div>
        </div>
      ),
    };
  });

  return (
    <Row gutter={24}>
      <Col xs={24} lg={14}>
        <Typography.Text strong>关系时间线</Typography.Text>
        {timelineItems.length > 0 ? (
          <div style={{ marginTop: 16 }}>
            <Timeline items={timelineItems} />
          </div>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="本次候选中没有产生可机械判断的关系"
            style={{ marginTop: 16 }}
          />
        )}
      </Col>

      <Col xs={24} lg={10}>
        <Typography.Text strong>有效记忆（Effective Memory）</Typography.Text>
        {effectiveMemories.length > 0 ? (
          <div style={{ marginTop: 8 }}>
            {effectiveMemories.map((effective) => {
              const memory = byId.get(effective.memory_id);
              return (
                <div
                  key={`${effective.memory_id}-${effective.role}`}
                  className="effective-item"
                >
                  <Tag color="green">{effective.role}</Tag>
                  <div>
                    <div className="mono">{effective.memory_id}</div>
                    <div className="relation-memory">
                      {memory ? memory.content : "（不在候选中）"}
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            description="没有有效记忆"
            style={{ marginTop: 16 }}
          />
        )}
      </Col>
    </Row>
  );
}
