import { Card } from "antd";
import type { ReactNode } from "react";

export type SectionAccent =
  | "config"
  | "question"
  | "candidates"
  | "state"
  | "answer";

interface Props {
  step: string;
  title: string;
  description?: string;
  accent: SectionAccent;
  extra?: ReactNode;
  children: ReactNode;
}

/** 带编号与模块强调色的卡片，用于区分页面上的五个区域。 */
export default function SectionCard({
  step,
  title,
  description,
  accent,
  extra,
  children,
}: Props) {
  return (
    <Card
      className={`section-card section-card--${accent}`}
      title={
        <div className="section-head">
          <span className="section-step">{step}</span>
          <span className="section-title">{title}</span>
          {description ? <span className="section-desc">{description}</span> : null}
        </div>
      }
      extra={extra}
    >
      {children}
    </Card>
  );
}
