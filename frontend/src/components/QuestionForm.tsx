import { Button, Input, Space, Typography } from "antd";

interface Props {
  question: string;
  onQuestionChange: (question: string) => void;
  onSubmit: () => void;
  loading: boolean;
  disabled: boolean;
  presets?: string[];
  placeholder?: string;
}

export default function QuestionForm({
  question,
  onQuestionChange,
  onSubmit,
  loading,
  disabled,
  presets = [],
  placeholder = "输入关于当前样本的问题",
}: Props) {
  return (
    <div>
      {presets.length > 0 ? (
        <div style={{ marginBottom: 12 }}>
          <Typography.Text type="secondary">当前样本的演示场景</Typography.Text>
          <Space wrap size={[8, 8]} style={{ marginTop: 8, display: "flex" }}>
            {presets.map((preset, index) => (
              <Button
                key={preset}
                size="small"
                disabled={disabled || loading}
                onClick={() => onQuestionChange(preset)}
              >
                场景 {index + 1}
              </Button>
            ))}
          </Space>
        </div>
      ) : null}
      <Typography.Text>问题</Typography.Text>
      <Input.TextArea
        style={{ marginTop: 8 }}
        rows={2}
        autoSize={{ minRows: 2, maxRows: 5 }}
        value={question}
        onChange={(event) => onQuestionChange(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
      />
      <Space style={{ marginTop: 12 }}>
        <Button
          type="primary"
          onClick={onSubmit}
          loading={loading}
          disabled={disabled || !question.trim()}
        >
          查询
        </Button>
      </Space>
    </div>
  );
}
