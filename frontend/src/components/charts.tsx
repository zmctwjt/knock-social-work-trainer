/**
 * 图表组件层
 *
 * 统一用 Apache ECharts（echarts + echarts-for-react）渲染，不自绘 SVG：
 * 自绘只够画一条线，没有坐标轴刻度、tooltip、图例、数据缩放，
 * 也不便后续加导出图片、响应式尺寸。
 *
 * 按需引入而非 `import * as echarts`：只注册用到的图表与组件，
 * 包体积能压在 200KB 左右（全量引入约 1MB）。
 */
import { useMemo } from 'react';
import ReactEChartsCore from 'echarts-for-react/lib/core';
import * as echarts from 'echarts/core';
import { BarChart, LineChart, PieChart, RadarChart } from 'echarts/charts';
import {
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
} from 'echarts/components';
import { CanvasRenderer } from 'echarts/renderers';
import { graphic } from 'echarts/core';
import type { EChartsOption } from 'echarts';

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  RadarChart,
  GridComponent,
  LegendComponent,
  MarkLineComponent,
  TitleComponent,
  TooltipComponent,
  CanvasRenderer,
]);

/** 站点配色，与全站深蓝 + 橙保持一致 */
const INK = '#1F3A5F';
const AMBER = '#D97706';
const MUTED = '#8a8578';
const GRID_LINE = '#eeece7';

const BASE_TEXT = {
  fontFamily:
    '-apple-system, BlinkMacSystemFont, "Segoe UI", "Microsoft YaHei", sans-serif',
  color: MUTED,
  fontSize: 12,
};

export interface TrendPoint {
  date: string;
  sessions: number;
  avg_total: number;
}

/** 折线：平均分趋势，双轴（均分折线 + 训练次数柱）便于同屏看量与质。 */
export function AverageTrendChart({
  points,
  height = 260,
  title,
}: {
  points: TrendPoint[];
  height?: number;
  title?: string;
}) {
  const option = useMemo<EChartsOption>(() => {
    const dates = points.map((p) => p.date.slice(5));
    const avgs = points.map((p) => (p.sessions ? p.avg_total : null));
    const counts = points.map((p) => p.sessions);
    const valid = points.filter((p) => p.sessions > 0).map((p) => p.avg_total);
    const mean = valid.length
      ? Math.round((valid.reduce((a, b) => a + b, 0) / valid.length) * 10) / 10
      : 0;
    return {
      textStyle: BASE_TEXT,
      title: title ? { text: title, left: 0, textStyle: { ...BASE_TEXT, fontSize: 13, color: INK } } : undefined,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'cross', crossStyle: { color: '#ccc' } },
        formatter: (params: unknown) => {
          const list = params as { axisValue: string; seriesName: string; value: number | null }[];
          if (!list.length) return '';
          const lines = [`<b>${list[0].axisValue}</b>`];
          for (const item of list) {
            const v = item.value === null ? '—' : item.value;
            lines.push(`${item.seriesName}：${v}`);
          }
          return lines.join('<br/>');
        },
      },
      legend: { top: 0, right: 0, itemWidth: 12, itemHeight: 8, textStyle: BASE_TEXT },
      grid: { left: 44, right: 44, top: 40, bottom: 28 },
      xAxis: {
        type: 'category',
        data: dates,
        axisLine: { lineStyle: { color: GRID_LINE } },
        axisTick: { show: false },
        axisLabel: BASE_TEXT,
      },
      yAxis: [
        {
          type: 'value',
          name: '均分',
          min: 0,
          max: 100,
          nameTextStyle: BASE_TEXT,
          splitLine: { lineStyle: { color: GRID_LINE } },
          axisLabel: BASE_TEXT,
        },
        {
          type: 'value',
          name: '次数',
          minInterval: 1,
          nameTextStyle: BASE_TEXT,
          splitLine: { show: false },
          axisLabel: BASE_TEXT,
        },
      ],
      series: [
        {
          name: '训练次数',
          type: 'bar',
          yAxisIndex: 1,
          data: counts,
          barMaxWidth: 14,
          itemStyle: { color: 'rgba(31,58,95,0.18)', borderRadius: [2, 2, 0, 0] },
        },
        {
          name: '平均分',
          type: 'line',
          yAxisIndex: 0,
          data: avgs,
          smooth: true,
          symbol: 'circle',
          symbolSize: 7,
          connectNulls: false,
          lineStyle: { width: 2.5, color: AMBER },
          itemStyle: { color: AMBER },
          areaStyle: {
            color: new graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(217,119,6,0.22)' },
              { offset: 1, color: 'rgba(217,119,6,0.02)' },
            ]),
          },
          markLine: mean
            ? {
                silent: true,
                symbol: 'none',
                lineStyle: { color: INK, type: 'dashed', width: 1 },
                label: { formatter: `均值 ${mean}`, ...BASE_TEXT },
                data: [{ yAxis: mean }],
              }
            : undefined,
        },
      ],
    };
  }, [points, title]);

  if (!points.some((p) => p.sessions > 0)) {
    return (
      <p style={{ color: MUTED, fontSize: 13, padding: '28px 0' }}>
        还没有训练记录，暂时画不出趋势。完成几次训练后这里会出现折线与柱状图。
      </p>
    );
  }
  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      style={{ height, width: '100%' }}
      notMerge
      opts={{ renderer: 'canvas' }}
    />
  );
}

export interface DimAvg {
  key: string;
  name: string;
  avg: number;
  count: number;
}

/** 横向条形：六维均值，最弱项高亮为橙色。 */
export function DimensionBarChart({
  dims,
  weakest,
  height = 240,
}: {
  dims: DimAvg[];
  weakest?: string;
  height?: number;
}) {
  const option = useMemo<EChartsOption>(() => {
    const sorted = [...dims].sort((a, b) => a.avg - b.avg);
    return {
      textStyle: BASE_TEXT,
      tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
      grid: { left: 96, right: 40, top: 8, bottom: 24 },
      xAxis: {
        type: 'value',
        min: 0,
        max: 100,
        splitLine: { lineStyle: { color: GRID_LINE } },
        axisLabel: BASE_TEXT,
      },
      yAxis: {
        type: 'category',
        data: sorted.map((d) => d.name),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { ...BASE_TEXT, color: '#5b5648' },
      },
      series: [
        {
          type: 'bar',
          data: sorted.map((d) => ({
            value: d.avg,
            itemStyle: {
              color: d.key === weakest ? AMBER : INK,
              borderRadius: [0, 4, 4, 0],
            },
          })),
          barMaxWidth: 16,
          label: {
            show: true,
            position: 'right',
            formatter: '{c}',
            ...BASE_TEXT,
            color: '#5b5648',
          },
        },
      ],
    };
  }, [dims, weakest]);

  if (!dims.length || dims.every((d) => !d.count)) {
    return <p style={{ color: MUTED, fontSize: 13 }}>暂无评分数据。</p>;
  }
  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      style={{ height, width: '100%' }}
      notMerge
    />
  );
}

/** 六边形雷达：单人或班级六维画像，可叠加对比。 */
export function RadarDimensionChart({
  series,
  height = 320,
}: {
  series: { name: string; dims: DimAvg[] }[];
  height?: number;
}) {
  const option = useMemo<EChartsOption>(() => {
    const indicators = (series[0]?.dims ?? []).map((d) => ({
      name: d.name,
      max: 100,
    }));
    return {
      textStyle: BASE_TEXT,
      tooltip: {},
      legend: series.length > 1
        ? { bottom: 0, itemWidth: 12, itemHeight: 8, textStyle: BASE_TEXT }
        : undefined,
      radar: {
        indicator: indicators,
        center: ['50%', '52%'],
        radius: '66%',
        axisName: { ...BASE_TEXT, color: '#5b5648' },
        splitLine: { lineStyle: { color: GRID_LINE } },
        splitArea: { areaStyle: { color: ['#fff', '#faf9f7'] } },
        axisLine: { lineStyle: { color: GRID_LINE } },
      },
      series: [
        {
          type: 'radar',
          data: series.map((s, i) => ({
            name: s.name,
            value: s.dims.map((d) => d.avg),
            symbolSize: 5,
            lineStyle: { width: 2, color: i === 0 ? AMBER : INK },
            itemStyle: { color: i === 0 ? AMBER : INK },
            areaStyle: { opacity: i === 0 ? 0.25 : 0.12, color: i === 0 ? AMBER : INK },
          })),
        },
      ],
    };
  }, [series]);

  if (!series.length || !series[0].dims.length) {
    return <p style={{ color: MUTED, fontSize: 13 }}>暂无维度数据。</p>;
  }
  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      style={{ height, width: '100%' }}
      notMerge
    />
  );
}

/** 环形图：角色分布 / 占比类数据。 */
export function DistributionPieChart({
  data,
  height = 240,
}: {
  data: { name: string; value: number }[];
  height?: number;
}) {
  const option = useMemo<EChartsOption>(() => ({
    textStyle: BASE_TEXT,
    tooltip: { trigger: 'item', formatter: '{b}：{c}（{d}%）' },
    legend: { bottom: 0, itemWidth: 10, itemHeight: 10, textStyle: BASE_TEXT },
    color: [INK, AMBER, '#6b8fb5', '#b9a88c', '#8a8578'],
    series: [
      {
        type: 'pie',
        radius: ['46%', '70%'],
        center: ['50%', '44%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: true, formatter: '{b}\n{c}', ...BASE_TEXT, color: '#5b5648' },
        data,
      },
    ],
  }), [data]);

  if (!data.length) return <p style={{ color: MUTED, fontSize: 13 }}>暂无数据。</p>;
  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      style={{ height, width: '100%' }}
      notMerge
    />
  );
}

export interface ScenarioUsage {
  scenario_id: string;
  scenario_name: string;
  sessions: number;
  avg_total: number;
}

/** 条形：案例练习热度，按次数排序。 */
export function ScenarioUsageChart({
  data,
  height = 260,
}: {
  data: ScenarioUsage[];
  height?: number;
}) {
  const option = useMemo<EChartsOption>(() => {
    const sorted = [...data].sort((a, b) => a.sessions - b.sessions).slice(-10);
    return {
      textStyle: BASE_TEXT,
      tooltip: {
        trigger: 'axis',
        axisPointer: { type: 'shadow' },
        formatter: (params: unknown) => {
          const list = params as { dataIndex: number }[];
          const item = sorted[list[0].dataIndex];
          if (!item) return '';
          return `<b>${item.scenario_name}</b><br/>练习 ${item.sessions} 次<br/>均分 ${item.avg_total || '—'}`;
        },
      },
      grid: { left: 92, right: 46, top: 8, bottom: 24 },
      xAxis: {
        type: 'value',
        minInterval: 1,
        splitLine: { lineStyle: { color: GRID_LINE } },
        axisLabel: BASE_TEXT,
      },
      yAxis: {
        type: 'category',
        data: sorted.map((s) => s.scenario_name),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { ...BASE_TEXT, color: '#5b5648' },
      },
      series: [
        {
          type: 'bar',
          data: sorted.map((s) => s.sessions),
          barMaxWidth: 14,
          itemStyle: { color: INK, borderRadius: [0, 4, 4, 0] },
          label: { show: true, position: 'right', formatter: '{c} 次', ...BASE_TEXT, color: '#5b5648' },
        },
      ],
    };
  }, [data]);

  if (!data.length) return <p style={{ color: MUTED, fontSize: 13 }}>暂无案例练习记录。</p>;
  return (
    <ReactEChartsCore
      echarts={echarts}
      option={option}
      style={{ height, width: '100%' }}
      notMerge
    />
  );
}