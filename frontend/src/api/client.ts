/**
 * 后端 API 封装。
 *
 * 所有与后端契约的耦合都集中在这里和 src/types/api.ts：
 * - 统一解析 ErrorResponse（APIs/query.schema.json）；
 * - 把 501 DYNAMIC_STATE_NOT_IMPLEMENTED 单独识别出来，供页面决定是否切换模拟链路；
 * - 对网络错误给出中文提示，避免页面白屏。
 */

import { API_PATHS } from "../types/api";
import type {
  ErrorResponse,
  QueryRequest,
  QueryResponse,
  RetrievalRequest,
  RetrievalResult,
  SampleSummary,
} from "../types/api";

export class ApiError extends Error {
  readonly code: string;
  readonly status: number;
  readonly detail?: Record<string, unknown> | null;

  constructor(
    code: string,
    message: string,
    status: number,
    detail?: Record<string, unknown> | null,
  ) {
    super(message);
    this.name = "ApiError";
    this.code = code;
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { "Content-Type": "application/json" },
      ...init,
    });
  } catch {
    throw new ApiError(
      "NETWORK_ERROR",
      "无法连接后端服务，请确认 uvicorn 已启动（默认 127.0.0.1:8000）。",
      0,
    );
  }

  if (!response.ok) {
    let payload: ErrorResponse | null = null;
    try {
      payload = (await response.json()) as ErrorResponse;
    } catch {
      // 后端返回的不是 JSON（例如代理错误页），退回状态码提示。
    }
    const error = payload?.error;
    throw new ApiError(
      error?.code ?? `HTTP_${response.status}`,
      error?.message ?? `请求失败（HTTP ${response.status}）`,
      response.status,
      error?.detail,
    );
  }

  return (await response.json()) as T;
}

export function listSamples(): Promise<SampleSummary[]> {
  return request<SampleSummary[]>(API_PATHS.samples);
}

export function retrieve(req: RetrievalRequest): Promise<RetrievalResult> {
  return request<RetrievalResult>(API_PATHS.retrieve, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

export function query(req: QueryRequest): Promise<QueryResponse> {
  return request<QueryResponse>(API_PATHS.query, {
    method: "POST",
    body: JSON.stringify(req),
  });
}

/** B2 尚未实现：/api/query 返回 501 且 code 为 DYNAMIC_STATE_NOT_IMPLEMENTED。 */
export function isDynamicStateUnavailable(error: unknown): boolean {
  return (
    error instanceof ApiError &&
    error.status === 501 &&
    error.code === "DYNAMIC_STATE_NOT_IMPLEMENTED"
  );
}

export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 404 && error.code === "SAMPLE_NOT_FOUND") {
      return "样本不存在，请刷新样本列表后重试。";
    }
    if (error.status === 422) {
      return "请求参数不合法（INVALID_REQUEST），请检查问题与 top_k。";
    }
    return `${error.message}${error.code ? `（${error.code}）` : ""}`;
  }
  return error instanceof Error ? error.message : String(error);
}
