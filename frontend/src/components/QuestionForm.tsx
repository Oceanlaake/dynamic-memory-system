import { Button, Input, Space, Typography } from "antd";

interface Props {
  question: string;
  onQuestionChange: (question: string) => void;
  onSubmit: () => void;
  loading: boolean;
  disabled: boolean;
}

export default function QuestionForm({
  question,
  onQuestionChange,
  onSubmit,
  loading,
  disabled,
}: Props) {
  return (
    <div>
      <Typography.Text>问题</Typography.Text>
      <Input.TextArea
        style={{ marginTop: 8 }}
        rows={2}
        autoSize={{ minRows: 2, maxRows: 5 }}
        value={question}
        onChange={(event) => onQuestionChange(event.target.value)}
        placeholder="输入问题，例如：How long did it take for Jon to open his studio?"
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
        <Typography.Text type="secondary">
          question 只包含问题本身，sample_id 与 top_k 作为独立参数提交。
        </Typography.Text>
      </Space>
    </div>
  );
}
