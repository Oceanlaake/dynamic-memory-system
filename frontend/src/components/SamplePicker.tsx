import { Button, InputNumber, Select, Space, Typography } from "antd";

import type { SampleSummary } from "../types/api";

interface Props {
  samples: SampleSummary[];
  sampleId: string;
  onSampleChange: (sampleId: string) => void;
  topK: number;
  onTopKChange: (topK: number) => void;
  loading: boolean;
  onRefresh: () => void;
}

export default function SamplePicker({
  samples,
  sampleId,
  onSampleChange,
  topK,
  onTopKChange,
  loading,
  onRefresh,
}: Props) {
  return (
    <Space size={16} wrap>
      <Space size={8}>
        <Typography.Text>对话样本</Typography.Text>
        <Select
          style={{ minWidth: 220 }}
          value={sampleId || undefined}
          placeholder="选择样本"
          loading={loading}
          onChange={onSampleChange}
          options={samples.map((sample) => ({
            value: sample.sample_id,
            label: sample.sample_id,
          }))}
        />
      </Space>

      <Space size={8}>
        <Typography.Text>Top-K</Typography.Text>
        <InputNumber
          min={1}
          max={50}
          value={topK}
          onChange={(value) => onTopKChange(value ?? 5)}
        />
      </Space>

      <Button onClick={onRefresh} loading={loading}>
        刷新样本
      </Button>
    </Space>
  );
}
