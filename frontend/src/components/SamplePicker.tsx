import { Button, InputNumber, Select, Space, Typography } from "antd";

import type { SampleSummary } from "../types/api";

export type DataMode = "auto" | "live" | "mock";

const MODE_OPTIONS: { value: DataMode; label: string }[] = [
  { value: "auto", label: "自动（优先真实，旧版后端时模拟）" },
  { value: "live", label: "仅真实链路" },
  { value: "mock", label: "仅模拟链路" },
];

interface Props {
  samples: SampleSummary[];
  sampleId: string;
  onSampleChange: (sampleId: string) => void;
  topK: number;
  onTopKChange: (topK: number) => void;
  mode: DataMode;
  onModeChange: (mode: DataMode) => void;
  loading: boolean;
  onRefresh: () => void;
}

export default function SamplePicker({
  samples,
  sampleId,
  onSampleChange,
  topK,
  onTopKChange,
  mode,
  onModeChange,
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
            label: `${sample.sample_id}（${sample.memory_count} 条记忆）`,
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

      <Space size={8}>
        <Typography.Text>数据模式</Typography.Text>
        <Select
          style={{ minWidth: 300 }}
          value={mode}
          onChange={onModeChange}
          options={MODE_OPTIONS}
        />
      </Space>

      <Button onClick={onRefresh} loading={loading}>
        刷新样本
      </Button>
    </Space>
  );
}
