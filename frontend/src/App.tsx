import { useCallback, useEffect, useMemo, useState } from "react";
import { Col, Empty, Row, Space, Tag, Typography } from "antd";

import {
  describeError,
  isDynamicStateUnavailable,
  listSamples,
  query,
  retrieve,
} from "./api/client";
import { mockDynamicState } from "./api/mock";
import AnswerPanel from "./components/AnswerPanel";
import QuestionForm from "./components/QuestionForm";
import RelationTimeline from "./components/RelationTimeline";
import RetrievalTable from "./components/RetrievalTable";
import SamplePicker from "./components/SamplePicker";
import type { DataMode } from "./components/SamplePicker";
import SectionCard from "./components/SectionCard";
import StatusAlert from "./components/StatusAlert";
import type { QueryResponse, SampleSummary } from "./types/api";

type Source = "live" | "mock";

const DEMO_QUESTIONS = [
  "How long did it take for Jon to open his studio?",
  "What is Jon's favorite style of dance?",
  "What is Jon working on opening?",
  "ZXQJ completely unrelated quantum submarine?",
];

export default function App() {
  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [samplesLoading, setSamplesLoading] = useState(true);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const [sampleId, setSampleId] = useState("");
  const [topK, setTopK] = useState(5);
  const [mode, setMode] = useState<DataMode>("auto");
  const [question, setQuestion] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResponse | null>(null);
  const [source, setSource] = useState<Source | null>(null);
  const [strategy, setStrategy] = useState<string | null>(null);
  const [fallbackNote, setFallbackNote] = useState<string | null>(null);

  const loadSamples = useCallback(async () => {
    setSamplesLoading(true);
    try {
      const list = await listSamples();
      setSamples(list);
      setConnectionError(null);
      setSampleId((current) =>
        current && list.some((sample) => sample.sample_id === current)
          ? current
          : (list[0]?.sample_id ?? ""),
      );
    } catch (caught) {
      setConnectionError(describeError(caught));
    } finally {
      setSamplesLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSamples();
  }, [loadSamples]);

  const handleSampleChange = (nextSampleId: string) => {
    setSampleId(nextSampleId);
    setResult(null);
    setSource(null);
    setStrategy(null);
    setFallbackNote(null);
    setError(null);
  };

  const applyMock = (retrieval: Awaited<ReturnType<typeof retrieve>>, note: string) => {
    setStrategy(retrieval.strategy);
    setResult(mockDynamicState(retrieval));
    setSource("mock");
    setFallbackNote(note);
  };

  const handleSubmit = async () => {
    const trimmed = question.trim();
    if (!sampleId) {
      setError("请先选择一个对话样本。");
      return;
    }
    if (!trimmed) {
      setError("请输入问题。");
      return;
    }

    setLoading(true);
    setError(null);
    setResult(null);
    setSource(null);
    setStrategy(null);
    setFallbackNote(null);

    const request = { sample_id: sampleId, question: trimmed, top_k: topK };

    try {
      if (mode === "mock") {
        const retrieval = await retrieve(request);
        applyMock(retrieval, "当前数据模式设置为「仅模拟链路」。");
      } else {
        try {
          const response = await query(request);
          setResult(response);
          setSource("live");
        } catch (caught) {
          if (mode === "auto" && isDynamicStateUnavailable(caught)) {
            const retrieval = await retrieve(request);
            applyMock(
              retrieval,
              "/api/query 不可用（旧版后端返回 501），已自动改用 /api/retrieve + 前端模拟。",
            );
          } else {
            throw caught;
          }
        }
      }
    } catch (caught) {
      setError(describeError(caught));
    } finally {
      setLoading(false);
    }
  };

  const effectiveIds = useMemo(
    () => new Set(result?.effective_memories.map((item) => item.memory_id) ?? []),
    [result],
  );

  const backendStatus = connectionError
    ? { color: "red", text: "后端未连接" }
    : samplesLoading
      ? { color: "default", text: "连接中" }
      : { color: "green", text: "后端已连接" };

  const currentSample = samples.find((sample) => sample.sample_id === sampleId);
  const modeLabel =
    mode === "auto" ? "自动" : mode === "live" ? "仅真实" : "仅模拟";

  const emptyState = (description: string) => (
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description={description} />
  );

  return (
    <div>
      <header className="app-header">
        <Row justify="space-between" align="middle" gutter={16}>
          <Col flex="auto">
            <div className="brand">
              <span className="brand-mark">D</span>
              <div>
                <h1>Dynamic Memory System</h1>
                <div className="subtitle">
                  LoCoMo 长对话 → 结构化记忆 → 检索 → 动态状态 → 答案与证据
                </div>
                <div className="header-pills">
                  <span className="header-pill">
                    样本 <strong>{samples.length}</strong>
                  </span>
                  <span className="header-pill">
                    当前记忆 <strong>{currentSample?.memory_count ?? 0}</strong>
                  </span>
                  <span className="header-pill">
                    Top-K <strong>{topK}</strong>
                  </span>
                  <span className="header-pill">
                    模式 <strong>{modeLabel}</strong>
                  </span>
                </div>
              </div>
            </div>
          </Col>
          <Col>
            <Space wrap>
              {strategy ? <Tag color="geekblue">检索策略：{strategy}</Tag> : null}
              <Tag color={backendStatus.color}>{backendStatus.text}</Tag>
            </Space>
          </Col>
        </Row>
      </header>

      <main className="app-content">
        <SectionCard
          step="01"
          title="数据与检索设置"
          description="样本来自 /api/samples，参数独立于问题文本"
          accent="config"
        >
          <SamplePicker
            samples={samples}
            sampleId={sampleId}
            onSampleChange={handleSampleChange}
            topK={topK}
            onTopKChange={setTopK}
            mode={mode}
            onModeChange={setMode}
            loading={samplesLoading}
            onRefresh={() => void loadSamples()}
          />
        </SectionCard>

        <SectionCard
          step="02"
          title="提问"
          description="question 只包含问题本身"
          accent="question"
        >
          <QuestionForm
            question={question}
            onQuestionChange={setQuestion}
            onSubmit={() => void handleSubmit()}
            loading={loading}
            disabled={!sampleId || samplesLoading}
            presets={DEMO_QUESTIONS}
          />
        </SectionCard>

        <StatusAlert
          error={error ?? connectionError}
          degraded={result?.degraded ?? false}
          source={source}
          fallbackNote={fallbackNote}
        />

        <SectionCard
          step="03"
          title="候选记忆（B1 Retrieval）"
          description="按相关度降序，展开可查看完整 Memory 与证据"
          accent="candidates"
          extra={
            result ? <Tag color="cyan">{result.candidate_memories.length} 条候选</Tag> : null
          }
        >
          {result ? (
            result.candidate_memories.length > 0 ? (
              <RetrievalTable
                candidates={result.candidate_memories}
                effectiveIds={effectiveIds}
              />
            ) : (
              emptyState("没有检索到候选记忆")
            )
          ) : (
            emptyState("提交问题后显示 Top-K 候选记忆")
          )}
        </SectionCard>

        <SectionCard
          step="04"
          title="动态状态（B2 Dynamic State）"
          description="记忆间关系与最终有效记忆"
          accent="state"
          extra={
            result ? (
              <Space size={4}>
                <Tag color="orange">{result.relations.length} 条关系</Tag>
                <Tag color="green">{result.effective_memories.length} 条有效</Tag>
              </Space>
            ) : null
          }
        >
          {result ? (
            <RelationTimeline
              relations={result.relations}
              candidates={result.candidate_memories}
              effectiveMemories={result.effective_memories}
            />
          ) : (
            emptyState("提交问题后显示记忆之间的关系与有效记忆")
          )}
        </SectionCard>

        <SectionCard
          step="05"
          title="答案与证据"
          description="answer 允许为 null，证据可回溯原始 turn"
          accent="answer"
          extra={
            source ? (
              <Tag color={source === "live" ? "green" : "blue"}>
                {source === "live" ? "真实链路" : "模拟链路"}
              </Tag>
            ) : null
          }
        >
          {result ? (
            <AnswerPanel answer={result.answer} evidence={result.evidence} />
          ) : (
            emptyState("提交问题后显示答案与证据")
          )}
          {result ? (
            <Typography.Text type="secondary" style={{ display: "block", marginTop: 12 }}>
              请求样本：{result.sample_id} · 问题：{result.question}
            </Typography.Text>
          ) : null}
        </SectionCard>
      </main>
    </div>
  );
}
