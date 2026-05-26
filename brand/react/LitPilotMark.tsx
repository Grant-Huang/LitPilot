// LitPilot mark — self-contained React component.
// No dependencies. Drop into any React project.
import * as React from 'react';

export interface LitPilotMarkProps extends React.SVGProps<SVGSVGElement> {
  size?: number | string;
  ink?: string;
  accent?: string;
}

export function LitPilotMark({
  size = 32,
  ink = '#0E1633',
  accent = '#F26A1F',
  ...rest
}: LitPilotMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      {...rest}
    >
      <path
        d="M14 12 L10 12 L10 52 L14 52"
        stroke={ink}
        strokeWidth={3.5}
        strokeLinecap="square"
        strokeLinejoin="miter"
        fill="none"
      />
      <path
        d="M50 12 L54 12 L54 52 L50 52"
        stroke={ink}
        strokeWidth={3.5}
        strokeLinecap="square"
        strokeLinejoin="miter"
        fill="none"
      />
      <path d="M52 18 L16 30 L30 36 L26 50 Z" fill={ink} />
      <path d="M52 18 L30 36 L26 50 Z" fill={accent} />
    </svg>
  );
}

export function LitPilotWordmark({
  size = 24,
  ink = '#0E1633',
  accent = '#F26A1F',
}: {
  size?: number;
  ink?: string;
  accent?: string;
}) {
  return (
    <span
      style={{
        fontFamily: 'Geist, Inter, system-ui, sans-serif',
        fontWeight: 600,
        fontSize: size,
        letterSpacing: '-0.04em',
        color: ink,
        lineHeight: 1,
      }}
    >
      Lit<span style={{ color: accent }}>Pilot</span>
    </span>
  );
}

export function LitPilotLogo({
  markSize = 32,
  wordmarkSize,
  gap = 10,
  ink,
  accent,
}: {
  markSize?: number;
  wordmarkSize?: number;
  gap?: number;
  ink?: string;
  accent?: string;
}) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap }}>
      <LitPilotMark size={markSize} ink={ink} accent={accent} />
      <LitPilotWordmark size={wordmarkSize ?? markSize * 0.72} ink={ink} accent={accent} />
    </span>
  );
}
