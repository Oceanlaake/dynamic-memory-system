import { Alert, Typography } from "antd";

import type { AnswerEvidenceRef } from "../types/api";

interface Props {
  answer: string | null;
  evidence: AnswerEvidenceRef[];
}

export default function AnswerPanel({ answer, evidence }: Props) {
  return (
    <div>
      {answer === null ? (
        <Alert
          type="warning"
          showIcon
          message="证据不足或冲突未消解，系统未生成答案"
          description="接口契约允许 answer 为 null：宁可返回空答案，也不编造。"
        />
      ) : (
        <div className="answer-box">
          <p className="answer-text">{answer}</p>
        </div>
      )}

      <div style={{ marginTop: 18 }}>
        <Typography.Text strong>答案证据</Typography.Text>
        {evidence.length > 0 ? (
          <div className="evidence-chips">
            {evidence.map((ref) => (
              <span
                key={`${ref.session_id}/${ref.dia_id}`}
                className="evidence-chip"
              >
                <span className="mono">{ref.session_id}</span>
                <span>/</span>
                <span className="mono">{ref.dia_id}</span>
              </span>
            ))}
          </div>
        ) : (
          <div className="evidence-meta" style={{ marginTop: 8 }}>
            本次答案没有引用证据。
          </div>
        )}
      </div>
    </div>
  );
}
