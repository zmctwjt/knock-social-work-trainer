/**
 * 06 成长中心 —— 全部数据来自当前账号的真实训练记录
 *
 * 数据源：store 的 records（每次「提交本阶段」写入一条）
 * 无记录时给出空状态引导，而不是显示假数据。
 */
import { useMemo, useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore, useMyRecords, type TrainingRecord } from '../store/store.tsx';
import { DIMENSIONS, DIMENSION_SHORT } from '../services/scoring.ts';
import { SCENARIOS } from '../data/scenarios.ts';

/* ── 绘图常量（沿用原稿坐标）── */
const RC = 160, RY = 150, RMAX = 100;
const CH = 100, CY0 = 100, CY1 = 20;
const CX0 = 20, CX1 = 300;

function polar(i: number, v: number) {
  const a = (-90 + i * 60) * Math.PI / 180;
  const r = (v / 100) * RMAX;
  return [RC + r * Math.cos(a), RY + r * Math.sin(a)] as const;
}

/** 按自然日聚合，返回最近 126 天（18 周）的格子 */
function heatOf(records: TrainingRecord[]) {
  const byDay = new Map<string, number>();
  for (const r of records) {
    const d = new Date(r.createdAt);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    byDay.set(key, (byDay.get(key) ?? 0) + 1);
  }
  const cells: number[] = [];
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  for (let i = 125; i >= 0; i--) {
    const d = new Date(today.getTime() - i * 86400000);
    const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
    const n = byDay.get(key) ?? 0;
    cells.push(n === 0 ? 0 : n === 1 ? 1 : n === 2 ? 2 : n <= 4 ? 3 : 4);
  }
  return { cells, byDay };
}

export default function GrowthPage() {
  const nav = useNavigate();
  const [detail, setDetail] = useState<TrainingRecord | null>(null);
  const { account } = useStore();
  const recs = useMyRecords();

  const g = useMemo(() => {
    const n = recs.length;
    if (n === 0) return null;

    const sorted = [...recs].sort((a, b) => a.createdAt - b.createdAt);
    const avg = {} as Record<string, number>;
    for (const d of DIMENSIONS) {
      avg[d.key] = Math.round(sorted.reduce((s, r) => s + (r.scores[d.key] ?? 0), 0) / n);
    }
    const totalAvg = Math.round(sorted.reduce((s, r) => s + r.total, 0) / n);
    const best = Math.max(...sorted.map((r) => r.total));
    const worst = Math.min(...sorted.map((r) => r.total));
    const last = sorted[sorted.length - 1];

    let weakKey = DIMENSIONS[0].key as string;
    for (const d of DIMENSIONS) if (avg[d.key] < avg[weakKey]) weakKey = d.key;
    const weak = DIMENSIONS.find((d) => d.key === weakKey)!;

    const curve = sorted.slice(-12);
    const { cells, byDay } = heatOf(recs);
    const activeDays = byDay.size;

    let streak = 0;
    const t0 = new Date(); t0.setHours(0, 0, 0, 0);
    for (let i = 0; i < 400; i++) {
      const d = new Date(t0.getTime() - i * 86400000);
      const key = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
      if (byDay.has(key)) streak++;
      else break;
    }

    const byScript = new Map<string, { times: number; best: number }>();
    for (const r of sorted) {
      const cur = byScript.get(r.scriptId) ?? { times: 0, best: 0 };
      cur.times++;
      cur.best = Math.max(cur.best, r.total);
      byScript.set(r.scriptId, cur);
    }
    const scripts = SCENARIOS.map((s) => ({
      ...s,
      times: byScript.get(s.id)?.times ?? 0,
      best: byScript.get(s.id)?.best ?? 0,
    })).sort((a, b) => b.times - a.times || b.best - a.best);

    return { n, avg, totalAvg, best, worst, last, weak, curve, cells,
             activeDays, streak, scripts, first: sorted[0] };
  }, [recs]);

  if (!g) {
    return (
      <div className="screen is-on">
        <div className="growth-head">
          <div>
            <div className="k">成长中心 · Growth</div>
            <h2>还没有训练记录</h2>
          </div>
        </div>
        <div className="card" style={{ maxWidth: 560, padding: '34px 30px' }}>
          <p style={{ fontFamily: 'var(--serif)', fontSize: 19, lineHeight: 1.65, marginBottom: 14 }}>
            练一次，这里就会长出你的第一组数据。
          </p>
          <p style={{ fontSize: 13, lineHeight: 1.9, color: 'var(--ink-2)', marginBottom: 20 }}>
            雷达图、成长曲线、训练热力图都来自你每次点「提交本阶段」时保存的记录。
            <b>分数不是目的，持续出现的频率才是。</b>
          </p>
          <button className="btn-primary" type="button" onClick={() => nav('/cases')}>
            去选一位服务对象 →
          </button>
        </div>
      </div>
    );
  }

  const radarPts = DIMENSIONS.map((d, i) => polar(i, g.avg[d.key]).join(',')).join(' ');

  const curvePts = g.curve.map((r, i) => {
    const x = g.curve.length === 1 ? (CX0 + CX1) / 2
      : CX0 + (i / (g.curve.length - 1)) * (CX1 - CX0);
    const y = CY0 - (r.total / 100) * (CY0 - CY1);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  }).join(' ');

  const heatTotal = recs.reduce((s, r) => s + r.uiPhase, 0) || g.n;
  const weakMeta = DIMENSIONS.find((d) => d.key === g.weak.key);

  return (
    <div className="screen is-on">
      <div className="growth-head">
        <div>
          <div className="k">成长中心 · Growth</div>
          <h2>{g.n} 次训练，你在哪条曲线上</h2>
        </div>
        <div className="n">
          {account?.nickname}<br />
          首次 {new Date(g.first.createdAt).toLocaleDateString('zh-CN')}
        </div>
      </div>

      <div className="growth">
        <div className="chart-wrap">
          <div className="panel-h"><span className="k">Six Dimensions · 六维能力</span></div>
          <svg viewBox="0 0 320 300" style={{ width: '100%', height: 'auto', maxHeight: 380 }}>
            {[20, 40, 60, 80, 100].map((v) => (
              <polygon key={v} fill="none" stroke="var(--rule)" strokeWidth="0.6"
                points={DIMENSIONS.map((_, i) => polar(i, v).join(',')).join(' ')} />
            ))}
            {DIMENSIONS.map((_, i) => {
              const [x, y] = polar(i, 100);
              return <line key={i} x1={RC} y1={RY} x2={x} y2={y}
                stroke="var(--rule)" strokeWidth="0.6" />;
            })}
            <polygon points={radarPts} fill="rgba(47,93,80,.16)"
              stroke="var(--green)" strokeWidth="2" strokeLinejoin="round" />
            {DIMENSIONS.map((d, i) => {
              const [x, y] = polar(i, g.avg[d.key]);
              const isWeak = d.key === g.weak.key;
              return (
                <circle key={d.key} cx={x} cy={y} r={isWeak ? 4.5 : 3.5}
                  fill={isWeak ? 'var(--proof)' : 'var(--green)'} />
              );
            })}
            {DIMENSIONS.map((d, i) => {
              const [x, y] = polar(i, 122);
              // ★ 六个方向的锚点要分别设：顶部居中、右侧左对齐、左侧右对齐
              const anchor = i === 0 ? 'middle' : (i === 1 || i === 2) ? 'start' : 'end';
              return (
                <text key={d.key} x={x} y={y} fontSize="10" textAnchor={anchor}
                  fill="var(--ink-3)" fontFamily="var(--mono)">{DIMENSION_SHORT[d.key]}</text>
              );
            })}
            {DIMENSIONS.map((d, i) => {
              const [x, y] = polar(i, 108);
              const anchor = i === 0 ? 'middle' : (i === 1 || i === 2) ? 'start' : 'end';
              return (
                <text key={d.key} x={x} y={y} fontSize="12" textAnchor={anchor}
                  fill="var(--ink)" fontFamily="var(--mono)" fontWeight="500">{g.avg[d.key]}</text>
              );
            })}
          </svg>
          <p className="chart-note">
            最弱项是<b>{weakMeta?.name}（{g.avg[g.weak.key]}）</b>——{weakMeta?.criteria}
          </p>
        </div>

        <div className="chart-wrap">
          <div className="panel-h"><span className="k">Trend · 综合分曲线</span></div>
          <div className="big-score">
            <span className="b">{g.last.total}</span>
            <span className="s">最近一次</span>
            <span className={'d'}>
              {g.last.total >= g.totalAvg ? '▲ 高于' : '▼ 低于'}均值 {g.totalAvg}
            </span>
          </div>
          <svg viewBox="0 0 320 120" style={{ width: '100%', height: 'auto' }}>
            {[100, 80, 60, 40, 20].map((v) => {
              const y = CY0 - (v / 100) * (CY0 - CY1);
              return (
                <g key={v}>
                  <line x1={CX0} y1={y} x2={CX1} y2={y}
                    stroke="var(--rule)" strokeWidth="0.5" strokeDasharray="2 3" />
                  <text x={CX1} y={y - 3} fontSize="8" textAnchor="end"
                    fill="var(--ink-4)" fontFamily="var(--mono)">{v}</text>
                </g>
              );
            })}
            {g.curve.length > 1 && (
              <polyline points={curvePts} fill="none" stroke="var(--green)"
                strokeWidth="2" strokeLinejoin="round" />
            )}
            {g.curve.map((r, i) => {
              const x = g.curve.length === 1 ? (CX0 + CX1) / 2
                : CX0 + (i / (g.curve.length - 1)) * (CX1 - CX0);
              const y = CY0 - (r.total / 100) * (CY0 - CY1);
              const isLast = i === g.curve.length - 1;
              /* ★ 点多时标签隔一个显示，否则会叠在一起 */
              const stride = g.curve.length > 8 ? 2 : 1;
              // ★ 末尾连着两个标签会挤在一起：只在与前一个标签间距够时才画
              const gapOk = !isLast || g.curve.length <= 2
                || (g.curve.length - 1) % stride !== 0 || stride === 1;
              const showLabel = (isLast ? gapOk : i % stride === 0);
              return (
                <g key={r.id}>
                  <circle cx={x} cy={y} r={isLast ? 4.5 : 3}
                    fill={isLast ? 'var(--proof)' : 'var(--paper-raised)'}
                    stroke={isLast ? 'var(--proof)' : 'var(--green)'} strokeWidth="1.6" />
                  {showLabel && (
                    <text x={x} y={114} fontSize="8" textAnchor="middle"
                      fill="var(--ink-4)" fontFamily="var(--mono)">#{i + 1}</text>
                  )}
                </g>
              );
            })}
          </svg>
          <div className="curve-stats">
            <span>最高 <b>{g.best}</b></span>
            <span>最低 <b>{g.worst}</b></span>
            <span>均值 <b>{g.totalAvg}</b></span>
            <span>共 <b>{g.n}</b> 次</span>
          </div>
        </div>
      </div>

      <div className="heat">
        <div className="heat-h">
          <span className="t">训练频率 · Heatmap</span>
          <h3>过去 18 周，你练了多少次</h3>
          <span className="s">{heatTotal} 次训练 · 当前连续 {g.streak} 天</span>
        </div>
        <div className="heat-grid">
          <div>
            <div className="heat-wrap">
              <div className="heat-days">
                {['一', '', '三', '', '五', '', '日'].map((d, i) => <span key={i}>{d}</span>)}
              </div>
              <div className="heat-cells">
                {g.cells.map((v, i) => (
                  <span key={i} className={'hc' + (v > 0 ? ' l' + v : '')}
                    /* 按列扫过：第 i 格属于第 floor(i/7) 列，每列错开 22ms */
                    style={{ animationDelay: (Math.floor(i / 7) * 22) + 'ms' }}
                    title={`第 ${i + 1} 格 · ${v === 0 ? '无训练' : '强度 ' + v}`} />
                ))}
              </div>
            </div>
            <div className="heat-legend">
              <span>少</span>
              <i style={{ background: '#EFE9DE' }} />
              <i style={{ background: '#C6D9CB' }} />
              <i style={{ background: '#8FBAA0' }} />
              <i style={{ background: '#4E8A6B' }} />
              <i style={{ background: '#2F5D50' }} />
              <span>多</span>
            </div>
          </div>
          <div>
            <div className="heat-stats">
              <div><b>{g.n}</b><span>总训练次数</span></div>
              <div><b>{g.activeDays}</b><span>有训练的天数</span></div>
              <div><b>{g.streak}</b><span>当前连续天数</span></div>
              <div><b>{(g.n / 18).toFixed(1)}</b><span>周均次数</span></div>
            </div>
            <p className="heat-note">
              颜色越深表示当天训练轮次越多。训练的价值不在单次得分，而在
              <b>持续出现的频率</b>——社工能力的成长曲线和肌肉记忆一样，
              靠的是不间断的重复。
            </p>
          </div>
        </div>
      </div>

      <div className="script-prog">
        <div className="sp-head">
          <span className="k">Case Progress · 剧本完成度</span>
          <span className="s">已练 {g.scripts.filter((s) => s.times > 0).length} / {SCENARIOS.length} 位</span>
        </div>
        <div className="sp-list">
          {g.scripts.map((s) => (
            <div key={s.id} className={'sp-row' + (s.times > 0 ? ' done' : '')}>
              <span className="sp-id">{s.id}</span>
              <span className="sp-nm">{s.name}</span>
              <span className="sp-ar">{s.archetype}</span>
              <span className="sp-times">{s.times > 0 ? `${s.times} 次` : '未练'}</span>
              <span className="sp-best">{s.best > 0 ? `最高 ${s.best}` : '—'}</span>
              <button className="sp-go" type="button"
                onClick={() => nav('/training/' + s.id)}>
                {s.times > 0 ? '再练一次' : '开始'} →
              </button>
            </div>
          ))}
        </div>
      </div>

      <div className="history">
        <div className="sp-head">
          <span className="k">History · 训练历史</span>
          <span className="s">最近 {Math.min(g.n, 20)} 条</span>
        </div>
        <div className="hi-list">
          {[...recs].sort((a, b) => b.createdAt - a.createdAt).slice(0, 20).map((r) => (
            <button key={r.id} type="button" className="hi-row"
              onClick={() => setDetail(r)} title="查看这次训练的完整记录">
              <span className="hi-time">
                {new Date(r.createdAt).toLocaleString('zh-CN', {
                  month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
                })}
              </span>
              <span className="hi-nm">{r.scriptName}</span>
              <span className="hi-tag">{r.difficulty}</span>
              <span className="hi-six">
                {DIMENSIONS.map((d) => (
                  <i key={d.key} title={d.name + ' ' + r.scores[d.key]}
                    className={r.scores[d.key] >= 70 ? 'good' : r.scores[d.key] >= 60 ? 'mid' : 'bad'} />
                ))}
              </span>
              <span className="hi-total">{r.total}</span>
              <span className="hi-more" aria-hidden="true">详情 →</span>
            </button>
          ))}
        </div>
      </div>

      {detail && (
        <div className="modal-mask" onClick={() => setDetail(null)}
          role="dialog" aria-label="训练详情">
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <div className="k">训练详情 · Record</div>
                <h3>{detail.scriptName} · {detail.difficulty}</h3>
              </div>
              <button className="modal-x" type="button" onClick={() => setDetail(null)}
                aria-label="关闭">✕</button>
            </div>

            <div className="modal-meta">
              <span>时间 <b>{new Date(detail.createdAt).toLocaleString('zh-CN')}</b></span>
              <span>综合分 <b>{detail.total}</b></span>
              <span>轮次 <b>{detail.transcript?.length ?? 0}</b></span>
              <span>模式 <b>{detail.blindfold ? '无剧透' : '剧透'}</b></span>
            </div>

            <div className="modal-six">
              {DIMENSIONS.map((d) => (
                <div key={d.key} className={'ms' + (d.key === DIMENSIONS
                  .slice()
                  .sort((a, b) => (detail.scores[a.key] ?? 0) - (detail.scores[b.key] ?? 0))[0].key
                  ? ' weak' : '')}>
                  <b>{detail.scores[d.key]}</b><span>{d.name}</span>
                </div>
              ))}
            </div>

            {/* 只保留一个标签：完整对话在下方单独成段，
                以前这里放了第二个"标签"，看着能点、点了却没反应 */}
            <div className="modal-tabs">
              <span className="on">逐句点评 {detail.notes?.length ?? 0}</span>
            </div>

            <div className="modal-body">
              {(detail.notes?.length ?? 0) > 0 ? (
                detail.notes!.map((n) => (
                  <div key={n.index} className="mrow">
                    <span className="no">{n.index}</span>
                    <div>
                      <span className="who">你</span>
                      <p className="said">{n.utterance}</p>
                      <div className="verdict">
                        <span className={'pf ' + (n.delta > 0 ? 'pass' : '')}>
                          {n.delta > 0 ? '▲ 有效' : '▲ 需改进'}
                        </span>
                        {DIMENSIONS.find((d) => d.key === n.dimension) && (
                          <span className="tag-dim">
                            {DIMENSIONS.find((d) => d.key === n.dimension)!.name}
                          </span>
                        )}
                        <span className="src">{n.ruleNote} {n.source}</span>
                      </div>
                    </div>
                    <div style={{ textAlign: 'right' }}>
                      <span className={'delta-pill ' + (n.delta > 0 ? 'plus' : 'minus')}>
                        {n.delta > 0 ? '+' : ''}{n.delta}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="kb-empty">这次训练没有记录逐句点评。</div>
              )}
            </div>

            {(detail.transcript?.length ?? 0) > 0 && (
              <>
                <div className="modal-tabs" style={{ marginTop: 18 }}>
                  <span>完整对话</span>
                </div>
                <div className="modal-body">
                  {detail.transcript!.map((m, i) => (
                    <div key={i} className={'turn ' + (m.role === 'worker' ? 'me' : 'them')}>
                      <span className="ln">{m.role === 'worker' ? '社工 · 你' : detail.scriptName}</span>
                      <div className="line">{m.text}</div>
                    </div>
                  ))}
                </div>
              </>
            )}

            <div className="modal-foot">
              <button className="btn-ghost" type="button" onClick={() => setDetail(null)}>关闭</button>
              <button className="btn-primary" type="button"
                onClick={() => { setDetail(null); nav('/training/' + detail.scriptId); }}>
                再练一次 →
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="growth-actions">
        <button className="btn-primary" type="button" onClick={() => nav('/cases')}>
          再练一次 →
        </button>
        <button className="btn-ghost" type="button" onClick={() => nav('/knowledge')}>
          去知识库补短板
        </button>
      </div>
    </div>
  );
}
