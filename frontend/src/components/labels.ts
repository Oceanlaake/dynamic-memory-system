import type { CSSProperties } from "react";

import type { MatchSource, MemoryType, RelationType } from "../types/api";

/** 统一使用文档约定的马卡龙色系，标签用深色文字保证可读性。 */
export interface TagMeta {
  label: string;
  bg: string;
  border: string;
  text: string;
}

export const MEMORY_TYPE_META: Record<MemoryType, TagMeta> = {
  state: { label: "状态", bg: "#BBFFFF", border: "#8fe9e9", text: "#0f5b5b" },
  event: { label: "事件", bg: "#97CBFF", border: "#7bb8ef", text: "#1e3a8a" },
  goal: { label: "目标", bg: "#FFFFAA", border: "#e8e88a", text: "#713f12" },
  preference: { label: "偏好", bg: "#B9B9FF", border: "#a3a3ef", text: "#312e81" },
  requirement: { label: "要求", bg: "#FFD1A4", border: "#efb984", text: "#7c2d12" },
};

export const MATCH_META: Record<MatchSource, TagMeta> = {
  keyword: { label: "词法", bg: "#F1F5F9", border: "#E2E8F0", text: "#475569" },
  embedding: { label: "语义", bg: "#B9B9FF", border: "#a3a3ef", text: "#312e81" },
  subject_boost: { label: "主体加权", bg: "#97CBFF", border: "#7bb8ef", text: "#1e3a8a" },
};

export function tagStyle(meta: TagMeta): CSSProperties {
  return {
    background: meta.bg,
    borderColor: meta.border,
    color: meta.text,
    marginInlineEnd: 0,
  };
}

export const RELATION_META: Record<
  RelationType,
  { label: string; color: string; hex: string }
> = {
  RETAIN: { label: "RETAIN · 保留", color: "green", hex: "#16a34a" },
  UPDATE: { label: "UPDATE · 更新", color: "blue", hex: "#2563eb" },
  SUPERSEDE: { label: "SUPERSEDE · 取代", color: "orange", hex: "#ea580c" },
  CONFLICT: { label: "CONFLICT · 冲突", color: "red", hex: "#dc2626" },
};

export function scoreColor(score: number): string {
  if (score >= 0.75) {
    return "#16a34a";
  }
  if (score >= 0.4) {
    return "#2563eb";
  }
  return "#94a3b8";
}
