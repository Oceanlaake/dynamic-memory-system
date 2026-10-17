import { Alert, Space } from "antd";

interface Props {
  error: string | null;
  degraded: boolean;
  source: "live" | "mock" | null;
  fallbackNote: string | null;
}

export default function StatusAlert({
  error,
  degraded,
  source,
  fallbackNote,
}: Props) {
  return (
    <Space direction="vertical" style={{ width: "100%", marginBottom: 16 }}>
      {error ? <Alert type="error" showIcon message="请求失败" description={error} /> : null}

      {source === "mock" ? (
        <Alert
          type="info"
          showIcon
          message="当前为模拟链路"
          description={`动态状态（relations / effective_memories / answer）由前端按简单规则模拟生成，不是 B2 的真实输出。${
            fallbackNote ? ` ${fallbackNote}` : ""
          }`}
        />
      ) : null}

      {degraded ? (
        <Alert
          type="warning"
          showIcon
          message="检索退化（degraded = true）"
          description="可能是无命中、索引为空或策略回退。结果可能不完整，不能当作正常空结果。"
        />
      ) : null}
    </Space>
  );
}
