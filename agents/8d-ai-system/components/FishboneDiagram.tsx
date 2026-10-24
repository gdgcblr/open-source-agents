"use client";

interface FishboneData {
  effect: string;
  categories: Record<string, string[]>;
}

const CATEGORY_COLORS: Record<string, string> = {
  Man: "#6366f1",
  Machine: "#f59e0b",
  Material: "#10b981",
  Method: "#ef4444",
  Measurement: "#8b5cf6",
  Environment: "#06b6d4",
};

const POSITIONS = [
  { key: "Man", top: true, x: 0.15 },
  { key: "Machine", top: true, x: 0.38 },
  { key: "Measurement", top: true, x: 0.62 },
  { key: "Environment", top: false, x: 0.15 },
  { key: "Material", top: false, x: 0.38 },
  { key: "Method", top: false, x: 0.62 },
];

export default function FishboneDiagram({ data }: { data: FishboneData }) {
  const W = 900;
  const H = 500;
  const spineY = H / 2;
  const spineStart = 80;
  const spineEnd = W - 120;
  const headX = W - 60;

  return (
    <div className="w-full overflow-x-auto">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full" style={{ minWidth: 700 }}>
        {/* Background */}
        <rect width={W} height={H} fill="#111827" rx="12" />

        {/* Spine */}
        <line x1={spineStart} y1={spineY} x2={spineEnd} y2={spineY} stroke="#4b5563" strokeWidth="3" />

        {/* Arrowhead */}
        <polygon
          points={`${headX},${spineY} ${headX - 20},${spineY - 10} ${headX - 20},${spineY + 10}`}
          fill="#4b5563"
        />

        {/* Effect box */}
        <rect x={headX - 5} y={spineY - 28} width={115} height={56} rx="8" fill="#1e293b" stroke="#6366f1" strokeWidth="1.5" />
        <foreignObject x={headX - 5} y={spineY - 28} width={115} height={56}>
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              height: "100%",
              padding: "4px 6px",
              fontSize: "10px",
              color: "#a5b4fc",
              textAlign: "center",
              fontWeight: 600,
              lineHeight: 1.3,
            }}
          >
            {data.effect}
          </div>
        </foreignObject>

        {/* Categories */}
        {POSITIONS.map(({ key, top, x }) => {
          const causes = data.categories[key] || [];
          const boneX = spineStart + (spineEnd - spineStart) * x;
          const boneEndY = top ? 50 : H - 50;
          const color = CATEGORY_COLORS[key] || "#6b7280";

          return (
            <g key={key}>
              {/* Diagonal bone */}
              <line
                x1={boneX}
                y1={spineY}
                x2={boneX}
                y2={boneEndY}
                stroke={color}
                strokeWidth="2"
                strokeOpacity="0.6"
              />

              {/* Category label */}
              <rect
                x={boneX - 44}
                y={top ? boneEndY - 24 : boneEndY}
                width={88}
                height={22}
                rx="4"
                fill={color}
                fillOpacity="0.2"
                stroke={color}
                strokeOpacity="0.5"
                strokeWidth="1"
              />
              <text
                x={boneX}
                y={top ? boneEndY - 8 : boneEndY + 14}
                textAnchor="middle"
                fill={color}
                fontSize="11"
                fontWeight="700"
              >
                {key}
              </text>

              {/* Cause items */}
              {causes.slice(0, 3).map((cause, i) => {
                const causeY = top
                  ? spineY - 40 - i * 38
                  : spineY + 40 + i * 38;
                const textX = boneX + (top ? -8 : 8);

                return (
                  <g key={i}>
                    <line
                      x1={boneX}
                      y1={causeY}
                      x2={boneX + (top ? -32 : 32)}
                      y2={causeY}
                      stroke={color}
                      strokeWidth="1.2"
                      strokeOpacity="0.4"
                    />
                    <text
                      x={top ? boneX - 36 : boneX + 36}
                      y={causeY + 4}
                      textAnchor={top ? "end" : "start"}
                      fill="#9ca3af"
                      fontSize="9.5"
                    >
                      {cause.length > 28 ? cause.slice(0, 28) + "…" : cause}
                    </text>
                  </g>
                );
              })}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
