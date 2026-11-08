import { useCallback, useEffect, useMemo, useState } from "react";
import { Col, Empty, InputNumber, Row, Space, Switch, Tag, Typography } from "antd";

import {
  describeError,
  listSamples,
  query,
} from "./api/client";
import AnswerPanel from "./components/AnswerPanel";
import ExpansionSummary from "./components/ExpansionSummary";
import GraphMemoryPanel from "./components/GraphMemoryPanel";
import QuestionForm from "./components/QuestionForm";
import RelationTimeline from "./components/RelationTimeline";
import RetrievalTable from "./components/RetrievalTable";
import SamplePicker from "./components/SamplePicker";
import SectionCard from "./components/SectionCard";
import StatusAlert from "./components/StatusAlert";
import { questionsForSample } from "./data/sampleQuestions";
import type { QueryResponse, SampleSummary } from "./types/api";

export default function App() {
  const [samples, setSamples] = useState<SampleSummary[]>([]);
  const [samplesLoading, setSamplesLoading] = useState(true);
  const [connectionError, setConnectionError] = useState<string | null>(null);

  const [sampleId, setSampleId] = useState("");
  const [topK, setTopK] = useState(5);
  const [expandSlots, setExpandSlots] = useState(true);
  const [maxExpansion, setMaxExpansion] = useState(50);
  const [graphExpand, setGraphExpand] = useState(false);
  const [graphMaxHops, setGraphMaxHops] = useState(3);
  const [maxGraphMemories, setMaxGraphMemories] = useState(5);
  const [question, setQuestion] = useState("");

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QueryResponse | null>(null);

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
    setQuestion("");
    setResult(null);
    setError(null);
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

    const request = {
      sample_id: sampleId, question: trimmed, top_k: topK,
      expand_slots: expandSlots, max_expansion_memories: maxExpansion,
      graph_expand: graphExpand, graph_max_hops: graphMaxHops,
      max_graph_memories: maxGraphMemories,
    };

    try {
      setResult(await query(request));
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
                </div>
              </div>
            </div>
          </Col>
          <Col>
            <Space wrap>
              <Tag color={backendStatus.color}>{backendStatus.text}</Tag>
            </Space>
          </Col>
        </Row>
      </header>

      <main className="app-content">
        <SectionCard
          step="01"
          title="数据与检索设置"
          accent="config"
        >
          <SamplePicker
            samples={samples}
            sampleId={sampleId}
            onSampleChange={handleSampleChange}
            topK={topK}
            onTopKChange={setTopK}
            loading={samplesLoading}
            onRefresh={() => void loadSamples()}
          />
          <Space wrap style={{ marginTop: 16 }}>
            <Switch
              checked={expandSlots}
              onChange={setExpandSlots}
              disabled={loading}
              aria-label="查询驱动证据补检"
            />
            <Typography.Text>查询驱动证据补检</Typography.Text>
            <Typography.Text type="secondary">最多新增</Typography.Text>
            <InputNumber
              min={1} max={200} precision={0} value={maxExpansion}
              onChange={(value) => setMaxExpansion(value ?? 50)}
              disabled={!expandSlots || loading}
              aria-label="最多新增记忆数量"
            />
            <Typography.Text type="secondary">条记忆；关闭可运行固定 Top-K 对照</Typography.Text>
          </Space>
          <Space wrap style={{ marginTop: 12 }}>
            <Switch
              checked={graphExpand}
              onChange={setGraphExpand}
              disabled={loading}
              aria-label="Graph Memory 多跳检索"
            />
            <Typography.Text>Graph Memory 多跳检索（Bonus）</Typography.Text>
            <Typography.Text type="secondary">最大跳数</Typography.Text>
            <InputNumber
              min={1} max={4} precision={0} value={graphMaxHops}
              onChange={(value) => setGraphMaxHops(value ?? 3)}
              disabled={!graphExpand || loading}
              aria-label="Graph 最大跳数"
            />
            <Typography.Text type="secondary">最多新增</Typography.Text>
            <InputNumber
              min={1} max={50} precision={0} value={maxGraphMemories}
              onChange={(value) => setMaxGraphMemories(value ?? 5)}
              disabled={!graphExpand || loading}
              aria-label="Graph 最多新增记忆"
            />
          </Space>
        </SectionCard>

        <SectionCard
          step="02"
          title="提问"
          accent="question"
        >
          <QuestionForm
            question={question}
            onQuestionChange={setQuestion}
            onSubmit={() => void handleSubmit()}
            loading={loading}
            disabled={!sampleId || samplesLoading}
            presets={questionsForSample(sampleId)}
            placeholder={
              sampleId
                ? `输入关于 ${sampleId} 的问题，或选择上方当前样本的演示场景`
                : "请先选择一个对话样本"
            }
          />
        </SectionCard>

        <StatusAlert
          error={error ?? connectionError}
          degraded={result?.degraded ?? false}
        />

        <SectionCard
          step="03"
          title="候选记忆"
          accent="candidates"
          extra={
            result ? <Tag color="cyan">{result.candidate_memories.length} 条候选</Tag> : null
          }
        >
          {result?.expansion ? (
            <ExpansionSummary trace={result.expansion} status={result.evidence_status} />
          ) : null}
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
          title="动态状态"
          accent="state"
          extra={
            result ? (
              <Space size={4}>
                <Tag color="orange">{result.relations.length} 条关系</Tag>
                <Tag color="green">{result.effective_memories.length} 条规则选中</Tag>
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
          title="Graph Memory（Bonus）"
          accent="state"
          extra={result?.graph?.enabled ? (
            <Tag color="geekblue">{result.graph.paths.length} 条多跳路径</Tag>
          ) : null}
        >
          {result?.graph ? (
            <GraphMemoryPanel trace={result.graph} />
          ) : (
            emptyState("开启 Graph Memory 后显示节点、边与多跳检索路径")
          )}
        </SectionCard>

        <SectionCard
          step="06"
          title="答案与证据"
          accent="answer"
        >
          {result ? (
            <AnswerPanel answer={result.answer} evidence={result.evidence} generation={result.generation}
              answerMemoryIds={result.answer_memory_ids} />
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
