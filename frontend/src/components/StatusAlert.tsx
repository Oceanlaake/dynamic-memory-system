import { Alert, Space } from "antd";

interface Props {
  error: string | null;
  degraded: boolean;
}

export default function StatusAlert({
  error,
  degraded,
}: Props) {
  return (
    <Space direction="vertical" style={{ width: "100%", marginBottom: 16 }}>
      {error ? <Alert type="error" showIcon message="请求失败" description={error} /> : null}

      {degraded ? (
        <Alert
          type="warning"
          showIcon
          message="没有找到足够的相关记忆"
        />
      ) : null}
    </Space>
  );
}
