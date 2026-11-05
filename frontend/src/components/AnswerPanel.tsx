import { Alert, Space, Tag, Typography } from "antd";

import type { AnswerEvidenceRef, GenerationTrace } from "../types/api";

interface Props {
  answer: string | null;
  evidence: AnswerEvidenceRef[];
  generation?: GenerationTrace | null;
  answerMemoryIds?: string[];
}

export default function AnswerPanel({ answer, evidence, generation, answerMemoryIds = [] }: Props) {
  return (
    <div>
      {answer === null ? (
        <Alert
          type={generation?.status === "error" ? "error" : "warning"}
          showIcon
          message={generation?.status === "error" ? "答案模型调用或输出校验失败" : "现有证据不足以支持回答"}
          description={generation?.status === "error" ? `错误类型：${generation.error_code ?? "unknown"}；未使用模板答案回退。` : undefined}
        />
      ) : (
        <div className="answer-box">
          <p className="answer-text">{answer}</p>
        </div>
      )}

      {generation ? (
        <Space direction="vertical" size={4} style={{ marginTop: 12 }}>
          <Space wrap>
            <Tag>{generation.provider} / {generation.model}</Tag>
            <Tag>{generation.status}</Tag>
          </Space>
          <Typography.Text type="secondary">
            答案生成 Token：输入 {generation.usage.input_tokens ?? "未报告"} / 输出 {generation.usage.output_tokens ?? "未报告"}
            {generation.usage.cached_input_tokens != null ? ` · 缓存命中 ${generation.usage.cached_input_tokens}` : ""}
            {generation.api_called ? ` · 生成耗时 ${(generation.elapsed_ms / 1000).toFixed(2)} 秒` : " · 未发起模型请求"}
            {generation.reused ? " · 复用相同输入结果" : ""}
          </Typography.Text>
        </Space>
      ) : null}

      <div style={{ marginTop: 18 }}>
        <Typography.Text strong>答案证据</Typography.Text>
        {answerMemoryIds.length > 0 ? (
          <Space wrap style={{ display: "flex", marginTop: 8 }}>
            {answerMemoryIds.map((id) => <Tag key={id}>{id}</Tag>)}
          </Space>
        ) : null}
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
