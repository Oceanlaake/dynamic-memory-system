/**
 * B2（Dynamic State）前端模拟适配器。
 *
 * 背景：/api/query 目前返回 501。为了中期演示能展示完整链路，本模块把真实的
 * RetrievalResult 按一组**简单、透明、可解释**的规则补成符合 QueryResponse 契约的对象。
 *
 * 重要原则（见 process/start.md）：
 * - 临时方案必须与正式方案区分：页面会常驻标注"动态状态为前端模拟"；
 * - 不为了覆盖标签而伪造冲突：只有规则命中时才产生关系；
 * - 不模仿 LLM 生成答案：answer 明确带「模拟答案」前缀。
 *
 * B2 上线后，页面切到真实 /api/query，本文件不再参与数据流。
 */

import type {
  AnswerEvidenceRef,
  CandidateMemory,
  EffectiveMemory,
  Memory,
  QueryResponse,
  Relation,
  RetrievalResult,
} from "../types/api";

const MONTHS: Record<string, number> = {
  january: 0,
  february: 1,
  march: 2,
  april: 3,
  may: 4,
  june: 5,
  july: 6,
  august: 7,
  september: 8,
  october: 9,
  november: 10,
  december: 11,
};

/** LoCoMo 的 date_time 形如 "4:04 pm on 20 January, 2023"，标准 Date 无法解析。 */
function timestampOf(memory: Memory): number {
  const raw = memory.time.date_time;
  if (!raw) {
    return Number.NaN;
  }

  const parsed = Date.parse(raw);
  if (!Number.isNaN(parsed)) {
    return parsed;
  }

  const match = raw.match(
    /(\d{1,2}):(\d{2})\s*(am|pm)\s+on\s+(\d{1,2})\s+([A-Za-z]+),?\s+(\d{4})/i,
  );
  if (!match) {
    return Number.NaN;
  }

  const [, hourText, minuteText, meridiem, dayText, monthText, yearText] = match;
  let hour = Number(hourText) % 12;
  if (meridiem.toLowerCase() === "pm") {
    hour += 12;
  }
  const month = MONTHS[monthText.toLowerCase()];
  if (month === undefined) {
    return Number.NaN;
  }
  return Date.UTC(Number(yearText), month, Number(dayText), hour, Number(minuteText));
}

function sessionNumber(memory: Memory): number {
  const match = memory.time.session_id.match(/(\d+)/);
  return match ? Number(match[1]) : 0;
}

/** 时间先后比较：优先绝对时间，解析失败时退回 session 序号。 */
function compareMemories(a: Memory, b: Memory): number {
  const timeA = timestampOf(a);
  const timeB = timestampOf(b);
  if (!Number.isNaN(timeA) && !Number.isNaN(timeB) && timeA !== timeB) {
    return timeA - timeB;
  }
  return sessionNumber(a) - sessionNumber(b);
}

function buildRelations(candidates: CandidateMemory[]): Relation[] {
  const ordered = candidates
    .map((candidate) => candidate.memory)
    .sort(compareMemories);
  const relations: Relation[] = [];

  for (let i = 0; i < ordered.length; i += 1) {
    for (let j = i + 1; j < ordered.length; j += 1) {
      const older = ordered[i];
      const newer = ordered[j];

      if (older.subject.toLowerCase() !== newer.subject.toLowerCase()) {
        continue;
      }
      if (!older.attribute || older.attribute !== newer.attribute) {
        continue;
      }

      const olderValue = older.value ?? null;
      const newerValue = newer.value ?? null;

      if (olderValue !== null && newerValue !== null && olderValue !== newerValue) {
        // 同一 subject + 同一 attribute 的新旧值：状态/目标/事件视为推进，其余视为冲突。
        const progressive =
          newer.type === "state" || newer.type === "goal" || newer.type === "event";
        relations.push({
          from: older.memory_id,
          to: newer.memory_id,
          relation: progressive ? "SUPERSEDE" : "CONFLICT",
          reason: `同一属性 ${older.attribute} 的值由「${olderValue}」变为「${newerValue}」，按时间先后判定为 ${
            progressive ? "SUPERSEDE（新状态取代旧状态）" : "CONFLICT（值冲突且无法机械消解）"
          }。`,
        });
      } else if (older.content.trim() === newer.content.trim()) {
        relations.push({
          from: older.memory_id,
          to: newer.memory_id,
          relation: "RETAIN",
          reason: "两条记忆内容一致，保留较早记录。",
        });
      }
    }
  }

  return relations;
}

function roleOf(memory: Memory, inConflict: boolean): string {
  if (inConflict) {
    return "conflict_source";
  }
  return memory.attribute ?? memory.type;
}

function uniqueEvidence(memories: Memory[]): AnswerEvidenceRef[] {
  const seen = new Set<string>();
  const evidence: AnswerEvidenceRef[] = [];
  for (const memory of memories) {
    for (const ref of memory.evidence) {
      const key = `${ref.session_id}/${ref.dia_id}`;
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      evidence.push({ session_id: ref.session_id, dia_id: ref.dia_id });
    }
  }
  return evidence;
}

/**
 * 把真实检索结果补成 QueryResponse。
 * 注意：这是模拟实现，规则只覆盖可机械判断的情况，不生成 UPDATE。
 */
export function mockDynamicState(retrieval: RetrievalResult): QueryResponse {
  const relations = buildRelations(retrieval.candidates);

  const superseded = new Set(
    relations.filter((relation) => relation.relation === "SUPERSEDE").map((relation) => relation.from),
  );
  const conflicted = new Set(
    relations
      .filter((relation) => relation.relation === "CONFLICT")
      .flatMap((relation) => [relation.from, relation.to]),
  );

  const effectiveCandidates = retrieval.candidates.filter(
    (candidate) => !superseded.has(candidate.memory.memory_id),
  );
  const effectiveMemories: EffectiveMemory[] = effectiveCandidates.map((candidate) => ({
    memory_id: candidate.memory.memory_id,
    role: roleOf(candidate.memory, conflicted.has(candidate.memory.memory_id)),
  }));

  const effectiveContents = effectiveCandidates.map(
    (candidate) => candidate.memory.content,
  );
  const answer =
    effectiveContents.length > 0
      ? `（模拟答案，B2 未实现）${effectiveContents.join(" ")}`
      : null;

  return {
    sample_id: retrieval.sample_id,
    question: retrieval.question,
    candidate_memories: retrieval.candidates,
    relations,
    effective_memories: effectiveMemories,
    answer,
    evidence: uniqueEvidence(
      effectiveCandidates.map((candidate) => candidate.memory),
    ),
    degraded: retrieval.degraded,
  };
}
