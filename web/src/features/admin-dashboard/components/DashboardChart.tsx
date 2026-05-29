"use client";

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import styles from "./DashboardChart.module.css";

export type ChartVariant = "line" | "area" | "bar" | "pie" | "donut";
export type ChartTone = "brand" | "success" | "warning" | "error" | "neutral";

export interface ChartSeries {
  key: string;
  label: string;
  tone?: ChartTone;
}

interface DashboardChartProps {
  variant: ChartVariant;
  data: Array<Record<string, string | number>>;
  xKey?: string;
  series: ChartSeries[];
  height?: number;
  ariaLabel: string;
  emptyMessage?: string;
  /** pie/donut 슬라이스 클릭 핸들러 (해당 데이터 행을 전달) */
  onSliceClick?: (row: Record<string, string | number>) => void;
}

const TONE_COLORS: Record<ChartTone, string> = {
  brand: "#7c3aed",
  success: "#059669",
  warning: "#d97706",
  error: "#dc2626",
  neutral: "#64748b",
};

function toneClass(tone: ChartTone | undefined): string {
  switch (tone) {
    case "brand":
      return styles.toneBrand;
    case "success":
      return styles.toneSuccess;
    case "warning":
      return styles.toneWarning;
    case "error":
      return styles.toneError;
    default:
      return styles.toneNeutral;
  }
}

function toneFill(tone: ChartTone | undefined): string {
  return TONE_COLORS[tone ?? "neutral"];
}

export function DashboardChart({
  variant,
  data,
  xKey = "name",
  series,
  height = 200,
  ariaLabel,
  emptyMessage = "표시할 데이터가 없습니다.",
  onSliceClick,
}: DashboardChartProps) {
  const isEmpty = !data || data.length === 0;

  if (isEmpty) {
    return (
      <div className={styles.wrapper} aria-label={ariaLabel} role="img">
        <div className={styles.empty} style={{ height }}>
          {emptyMessage}
        </div>
      </div>
    );
  }

  return (
    <div className={styles.wrapper} aria-label={ariaLabel} role="img">
      <div className={styles.chartBox} style={{ height }}>
        <ResponsiveContainer
          width="100%"
          height={height}
          minWidth={1}
          minHeight={height}
        >
          {renderChart(variant, data, xKey, series, onSliceClick)}
        </ResponsiveContainer>
      </div>
      <ul className={styles.legend} aria-hidden="true">
        {series.map((s) => (
          <li key={`${s.key}:${s.label}`} className={styles.legendItem}>
            <span
              className={`${styles.legendSwatch} ${toneClass(s.tone)}`}
              aria-hidden="true"
            />
            <span>{s.label}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function renderChart(
  variant: ChartVariant,
  data: Array<Record<string, string | number>>,
  xKey: string,
  series: ChartSeries[],
  onSliceClick?: (row: Record<string, string | number>) => void,
) {
  if (variant === "line") {
    return (
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey={xKey} fontSize={11} stroke="#64748b" />
        <YAxis width={34} fontSize={11} stroke="#64748b" tickMargin={4} />
        <Tooltip />
        {series.map((s) => (
          <Line
            key={s.key}
            dataKey={s.key}
            name={s.label}
            stroke={toneFill(s.tone)}
            strokeWidth={2}
            dot={false}
          />
        ))}
      </LineChart>
    );
  }

  if (variant === "area") {
    return (
      <AreaChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey={xKey} fontSize={11} stroke="#64748b" />
        <YAxis width={34} fontSize={11} stroke="#64748b" tickMargin={4} />
        <Tooltip />
        {series.map((s) => (
          <Area
            key={s.key}
            dataKey={s.key}
            name={s.label}
            stroke={toneFill(s.tone)}
            fill={toneFill(s.tone)}
            fillOpacity={0.18}
          />
        ))}
      </AreaChart>
    );
  }

  if (variant === "bar") {
    return (
      <BarChart data={data} margin={{ top: 8, right: 12, bottom: 0, left: -8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#e5e7eb" />
        <XAxis dataKey={xKey} fontSize={11} stroke="#64748b" />
        <YAxis width={34} fontSize={11} stroke="#64748b" tickMargin={4} />
        <Tooltip />
        {series.map((s) => (
          <Bar
            key={s.key}
            dataKey={s.key}
            name={s.label}
            fill={toneFill(s.tone)}
          />
        ))}
      </BarChart>
    );
  }

  if (variant === "pie" || variant === "donut") {
    return renderPieChart(variant, data, xKey, series, onSliceClick);
  }

  return null;
}

function renderPieChart(
  variant: "pie" | "donut",
  data: Array<Record<string, string | number>>,
  xKey: string,
  series: ChartSeries[],
  onSliceClick?: (row: Record<string, string | number>) => void,
) {
  const seriesKey = series[0]?.key ?? "value";
  const isDonut = variant === "donut";
  const sliceCursor = onSliceClick ? "pointer" : undefined;

  return (
    <PieChart>
      <Tooltip />
      <Pie
        data={data}
        dataKey={seriesKey}
        nameKey={xKey}
        innerRadius={isDonut ? 40 : 0}
        outerRadius={70}
        paddingAngle={2}
        onClick={
          onSliceClick
            ? (entry: { payload?: Record<string, string | number> }) => {
                if (entry?.payload) onSliceClick(entry.payload);
              }
            : undefined
        }
        style={sliceCursor ? { cursor: sliceCursor } : undefined}
      >
        {data.map((_, idx) => (
          <Cell
            key={`cell-${idx}`}
            fill={toneFill(series[idx % series.length]?.tone)}
            style={sliceCursor ? { cursor: sliceCursor } : undefined}
          />
        ))}
      </Pie>
    </PieChart>
  );
}
