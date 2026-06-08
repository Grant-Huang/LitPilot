"use client";

import type { TurnCompletionSummary } from "@/lib/turnCompletion";

type Props = {
  summary: TurnCompletionSummary;
  streaming?: boolean;
  hasArtifact?: boolean;
  artifactVisible?: boolean;
  onOpenArtifact?: () => void;
};

export function TurnCompletionBar({
  summary,
  streaming = false,
  hasArtifact = false,
  artifactVisible = false,
  onOpenArtifact,
}: Props) {
  const showArtifactCta =
    hasArtifact && !artifactVisible && !streaming && onOpenArtifact != null;

  return (
    <div
      className={`litpilot-turn-complete${
        streaming ? " litpilot-turn-complete--live" : ""
      }`}
    >
      <div className="litpilot-turn-complete__headline">{summary.headline}</div>
      {!streaming && summary.brief ? (
        <p className="litpilot-turn-complete__brief">{summary.brief}</p>
      ) : null}
      {showArtifactCta ? (
        <div className="litpilot-turn-complete__cta-row">
          {summary.stats.hasReview ? (
            <span className="litpilot-turn-complete__cta-hint">综述已生成</span>
          ) : null}
          <button
            type="button"
            className="litpilot-turn-complete__cta"
            onClick={onOpenArtifact}
          >
            {summary.stats.hasReview ? "查看综述" : "打开右侧面板"}
          </button>
        </div>
      ) : null}
    </div>
  );
}
