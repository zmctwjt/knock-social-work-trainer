/**
 * 教师工作台
 *
 * 视觉与学生端（成长中心 P6）对齐：衬线大标题、等宽小字标签、
 * 纸色卡片、细分割线。样式用 `wb-*` 公共类而非内联，避免两端走形。
 *
 * 四个视图：班级总览 / 学员画像 / 训练趋势 / 内容查阅。
 * 权限以服务端为准——本页只是入口，真正的隔离在 require_roles 与
 * accounts.teacher_id 归属过滤上。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store/store.tsx';
import { apiGet, apiGetResult, apiSend, describeApiError } from '../lib/authClient.ts';
import {
  AverageTrendChart,
  DimensionBarChart,
  RadarDimensionChart,
  ScenarioUsageChart,
} from '../components/charts.tsx';

interface Learner {
  account_id: string;
  username: string;
  nickname: string;
  sessions: number;
  avg_total: number;
  is_active: boolean;
  last_login_at: string | null;
}

interface ClassStats {
  learners: number;
  sessions: number;
  avg_total: number;
  dimensions: Record<string, number>;
  weakest: string;
  weakest_score: number;
}

interface DimAvg { key: string; name: string; avg: number; count: number }
interface TrendPoint { date: string; sessions: number; avg_total: number }
interface ScenarioUsage {
  scenario_id: string; scenario_name: string; sessions: number; avg_total: number;
}
interface ClassTrend {
  points: TrendPoint[]; dimensions: DimAvg[]; scenarios: ScenarioUsage[];
}
interface LearnerDetail {
  account_id: string; username: string; nickname: string;
  is_active: boolean; last_login_at: string | null;
  sessions: number; finished: number; avg_total: number; best_total: number;
  total_turns: number; total_minutes: number;
  dimensions: DimAvg[]; weakest: string;
  trend: TrendPoint[]; scenarios: ScenarioUsage[];
}
interface RecordRow {
  scenario_name?: string; score_total?: number; created_at?: string;
}

const TABS = [
  { key: '班级总览', no: '01' },
  { key: '学员画像', no: '02' },
  { key: '训练趋势', no: '03' },
  { key: '内容查阅', no: '04' },
] as const;
type Tab = (typeof TABS)[number]['key'];

const DIM_LABEL: Record<string, string> = {
  empathy: '同感与倾听',
  question: '提问与对焦',
  advice: '信息与建议',
  ethics: '伦理原则',
  process: '过程完整性',
  risk: '风险识别',
};

export default function TeacherPage() {
  const nav = useNavigate();
  const { account, role } = useStore();
  const [tab, setTab] = useState<Tab>('班级总览');
  const [learners, setLearners] = useState<Learner[]>([]);
  const [stats, setStats] = useState<ClassStats | null>(null);
  const [trend, setTrend] = useState<ClassTrend | null>(null);
  const [detail, setDetail] = useState<LearnerDetail | null>(null);
  const [records, setRecords] = useState<RecordRow[]>([]);
  const [selected, setSelected] = useState<Learner | null>(null);
  const [cards, setCards] = useState<
    { id: string; title: string; category: string; summary: string }[]
  >([]);
  const [keyword, setKeyword] = useState('');
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState('');
  const [msg, setMsg] = useState('');
  const [bindName, setBindName] = useState('');

  const loadDetail = useCallback(async (x: Learner) => {
    const [d, r] = await Promise.all([
      apiGet<LearnerDetail>(`/api/v1/teacher/learners/${x.account_id}/detail`),
      apiGet<{ items: RecordRow[] }>(`/api/v1/teacher/learners/${x.account_id}/records`),
    ]);
    setDetail(d ?? null);
    setRecords(r?.items ?? []);
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const [lr, sr, tr] = await Promise.all([
      apiGetResult<{ items: Learner[] }>('/api/v1/teacher/learners'),
      apiGetResult<ClassStats>('/api/v1/teacher/stats'),
      apiGetResult<ClassTrend>('/api/v1/teacher/trend'),
    ]);
    const l = lr.data; const s = sr.data; const t = tr.data;
    const firstError = lr.error ?? sr.error ?? tr.error;
    setErr(firstError ? describeApiError(firstError, '班级数据加载失败') : '');
    const items = l?.items ?? [];
    setLearners(items);
    setStats(s ?? null);
    setTrend(t ?? null);
    setLoading(false);
    // 默认选中均分最低的学员——最需要关注的人
    if (items.length) {
      const target = [...items].sort((a, b) => (a.avg_total || 999) - (b.avg_total || 999))[0];
      setSelected(target);
      void loadDetail(target);
    }
  }, [loadDetail]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    void apiGet<{ items: typeof cards }>('/api/v1/knowledge/cards').then((r) => {
      setCards(r?.items ?? []);
    });
  }, []);

  async function openLearner(x: Learner) {
    setSelected(x);
    setTab('学员画像');
    setDetail(null);
    await loadDetail(x);
  }

  async function bindLearner() {
    const name = bindName.trim();
    if (!name) return;
    const r = await apiSend('POST', '/api/v1/teacher/learners', { username: name });
    setMsg(r.ok ? `已将 ${name} 加入名下学员` : r.msg);
    if (r.ok) { setBindName(''); void load(); }
  }

  const filteredCards = useMemo(() => {
    const q = keyword.trim();
    if (!q) return cards.slice(0, 20);
    return cards.filter(
      (c) => c.title.includes(q) || c.summary.includes(q) || c.category.includes(q),
    ).slice(0, 30);
  }, [cards, keyword]);

  if (!account) {
    return (
      <div className="screen is-on">
        <div className="wb-frame">
          <div className="wb-empty">
            <b>需要登录</b>
            教师工作台仅对教师与管理员开放。
            <div style={{ marginTop: 16 }}>
              <button className="btn-primary" type="button" onClick={() => nav('/login')}>
                去登录
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="screen is-on">
      <div className="wb-frame" style={{ paddingBottom: 72 }}>
        {/* 页面头部：与学生端 p6-head 同款 */}
        <div className="wb-head">
          <div className="k">教师工作台 · Teacher</div>
          <h2>{account.nickname}，欢迎回来</h2>
          <p className="sub">
            {role === 'admin'
              ? '当前角色为管理员，可查看全部学员数据。'
              : '当前角色为教师，只能看到自己名下学员的数据；跨班查询返回空集。'}
          </p>
          <div className="meta">
            {stats
              ? `${stats.learners} 名学员 · ${stats.sessions} 次训练 · 班级均分 ${stats.avg_total || '—'}`
              : '数据加载中'}
            {role === 'admin' && ' · 可进入管理后台'}
          </div>
        </div>

        {/* 视图切换 */}
        <div className="wb-tabs" role="tablist">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              role="tab"
              className="wb-tab"
              aria-selected={tab === t.key}
              onClick={() => setTab(t.key)}
            >
              <span className="no">{t.no}</span>
              {t.key}
            </button>
          ))}
          {role === 'admin' && (
            <button type="button" className="wb-tab" style={{ marginLeft: 'auto' }}
              onClick={() => nav('/admin')}>
              管理后台 →
            </button>
          )}
        </div>

        {msg && <div className="wb-alert ok">{msg}</div>}
        {err && <div className="wb-alert err">{err}</div>}
        {loading && <div className="wb-alert info">正在读取班级数据…</div>}

        {/* ── 01 班级总览 ── */}
        {tab === '班级总览' && (
          <>
            {stats && (
              <div className="wb-metrics">
                <div className="wb-metric">
                  <div className="k">学员数</div>
                  <div className="n">{stats.learners}</div>
                  <div className="d">已归属到名下</div>
                </div>
                <div className="wb-metric">
                  <div className="k">训练次数</div>
                  <div className="n">{stats.sessions}</div>
                  <div className="d">累计完成训练</div>
                </div>
                <div className="wb-metric">
                  <div className="k">班级均分</div>
                  <div className="n">{stats.avg_total || '—'}</div>
                  <div className="d">六维加权总分</div>
                </div>
                <div className="wb-metric">
                  <div className="k">最薄弱维度</div>
                  <div className="n warn" style={{ fontSize: 18 }}>
                    {stats.weakest ? DIM_LABEL[stats.weakest] || stats.weakest : '—'}
                  </div>
                  <div className="d">
                    {stats.weakest ? `均分 ${stats.weakest_score}` : '暂无评分数据'}
                  </div>
                </div>
              </div>
            )}

            <div className="wb-grid">
              <div className="wb-panel">
                <div className="wb-panel-h">
                  <span>名下学员</span>
                  <span className="hint">点击查看学员画像</span>
                </div>
                {learners.length === 0 && !loading && (
                  <div className="wb-empty">
                    <b>还没有学员</b>
                    在右侧输入学员用户名完成绑定，或由管理员在管理后台创建账号。
                  </div>
                )}
                {learners.map((x) => (
                  <button
                    key={x.account_id}
                    type="button"
                    className="wb-row wb-row-btn"
                    onClick={() => openLearner(x)}
                  >
                    <span className="name">{x.nickname}</span>
                    <span className="mono">{x.username}</span>
                    <span className="spacer" />
                    <span className="mono">训练 {x.sessions}</span>
                    <span className="mono">均分 {x.avg_total || '—'}</span>
                    <span className={`tag ${x.is_active ? 'ok' : 'warn'}`}>
                      {x.is_active ? '正常' : '停用'}
                    </span>
                  </button>
                ))}
              </div>

              <div>
                <div className="wb-panel">
                  <div className="wb-panel-h">绑定学员</div>
                  <p style={{ fontSize: 12.5, color: 'var(--ink-3)', lineHeight: 1.7,
                    margin: '0 0 12px' }}>
                    输入学员用户名，加入名下后即可查看其训练数据。
                  </p>
                  <div className="wb-form" style={{ marginBottom: 0 }}>
                    <input
                      className="wb-input"
                      style={{ flex: 1, minWidth: 120 }}
                      placeholder="学员用户名"
                      value={bindName}
                      onChange={(e) => setBindName(e.target.value)}
                      onKeyDown={(e) => { if (e.key === 'Enter') void bindLearner(); }}
                    />
                    <button className="btn-primary" type="button" onClick={bindLearner}
                      style={{ padding: '9px 18px' }}>
                      绑定
                    </button>
                  </div>
                </div>

                {trend && trend.dimensions.length > 0 && (
                  <div className="wb-panel">
                    <div className="wb-panel-h">班级六维</div>
                    <RadarDimensionChart
                      series={[{ name: '班级均值', dims: trend.dimensions }]}
                      height={260}
                    />
                  </div>
                )}
              </div>
            </div>

            {trend && trend.points.some((p) => p.sessions > 0) && (
              <div className="wb-panel">
                <div className="wb-panel-h">
                  <span>班级近期训练量</span>
                  <span className="hint">近 14 天，折线为均分</span>
                </div>
                <AverageTrendChart points={trend.points} height={230} />
              </div>
            )}
          </>
        )}

        {/* ── 02 学员画像 ── */}
        {tab === '学员画像' && (
          <>
            {!selected && (
              <div className="wb-empty">
                <b>请选择学员</b>
                在「班级总览」里点击任意一名学员即可查看完整画像。
              </div>
            )}
            {selected && !detail && <div className="wb-alert info">正在读取学员画像…</div>}
            {selected && detail && (
              <>
                <div className="wb-metrics">
                  <div className="wb-metric">
                    <div className="k">训练次数</div>
                    <div className="n">{detail.sessions}</div>
                    <div className="d">完成 {detail.finished} 次会话</div>
                  </div>
                  <div className="wb-metric">
                    <div className="k">平均分</div>
                    <div className="n">{detail.avg_total || '—'}</div>
                    <div className="d">最好 {detail.best_total || '—'}</div>
                  </div>
                  <div className="wb-metric">
                    <div className="k">总轮次</div>
                    <div className="n">{detail.total_turns}</div>
                    <div className="d">面谈发言轮数</div>
                  </div>
                  <div className="wb-metric">
                    <div className="k">累计时长</div>
                    <div className="n">{detail.total_minutes}</div>
                    <div className="d">分钟</div>
                  </div>
                  <div className="wb-metric">
                    <div className="k">最薄弱</div>
                    <div className="n warn" style={{ fontSize: 17 }}>
                      {detail.weakest ? DIM_LABEL[detail.weakest] || detail.weakest : '—'}
                    </div>
                    <div className="d">建议重点练习</div>
                  </div>
                </div>

                <div className="wb-grid">
                  <div className="wb-panel">
                    <div className="wb-panel-h">
                      <span>{detail.nickname} · 六维画像</span>
                      <span className="hint">{detail.username}</span>
                    </div>
                    <RadarDimensionChart
                      series={[{ name: detail.nickname, dims: detail.dimensions }]}
                      height={300}
                    />
                  </div>
                  <div className="wb-panel">
                    <div className="wb-panel-h">近 14 天进步曲线</div>
                    <AverageTrendChart points={detail.trend} height={240} />
                  </div>
                </div>

                <div className="wb-grid">
                  <div className="wb-panel">
                    <div className="wb-panel-h">练习过的案例</div>
                    {detail.scenarios.length === 0 && (
                      <div className="wb-empty">该学员还没有训练记录。</div>
                    )}
                    {detail.scenarios.map((s) => (
                      <div key={s.scenario_id} className="wb-row">
                        <span className="mono" style={{ width: 56 }}>{s.scenario_id}</span>
                        <span className="name">{s.scenario_name}</span>
                        <span className="spacer" />
                        <span className="mono">{s.sessions} 次</span>
                        <span className="mono">均 {s.avg_total || '—'}</span>
                      </div>
                    ))}
                  </div>
                  <div className="wb-panel">
                    <div className="wb-panel-h">最近训练记录</div>
                    {records.length === 0 && (
                      <div className="wb-empty">暂无记录。</div>
                    )}
                    {records.slice(0, 12).map((r, i) => (
                      <div key={i} className="wb-row">
                        <span className="name" style={{ fontWeight: 400 }}>
                          {r.scenario_name || '—'}
                        </span>
                        <span className="spacer" />
                        <span className="mono">{r.score_total ?? '—'} 分</span>
                        <span className="mono" style={{ color: 'var(--ink-4)' }}>
                          {r.created_at
                            ? new Date(r.created_at).toLocaleDateString('zh-CN')
                            : ''}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              </>
            )}
          </>
        )}

        {/* ── 03 训练趋势 ── */}
        {tab === '训练趋势' && (
          <>
            <div className="wb-panel">
              <div className="wb-panel-h">
                <span>班级近 14 天平均分</span>
                <span className="hint">折线为均分，柱状为训练次数</span>
              </div>
              <AverageTrendChart points={trend?.points ?? []} height={280} />
            </div>

            <div className="wb-grid">
              <div className="wb-panel">
                <div className="wb-panel-h">
                  <span>班级六维均值</span>
                  <span className="hint">最弱项以朱红标示</span>
                </div>
                <DimensionBarChart
                  dims={trend?.dimensions ?? []}
                  weakest={stats?.weakest}
                  height={260}
                />
              </div>
              <div className="wb-panel">
                <div className="wb-panel-h">案例练习分布</div>
                <ScenarioUsageChart data={trend?.scenarios ?? []} height={260} />
              </div>
            </div>
          </>
        )}

        {/* ── 04 内容查阅 ── */}
        {tab === '内容查阅' && (
          <div className="wb-panel">
            <div className="wb-panel-h">
              <span>技巧卡与伦理守则</span>
              <span className="hint">共 {cards.length} 条</span>
            </div>
            <div className="wb-form">
              <input
                className="wb-input"
                style={{ flex: 1, minWidth: 200 }}
                placeholder="按标题、摘要或分类搜索"
                value={keyword}
                onChange={(e) => setKeyword(e.target.value)}
              />
            </div>
            {filteredCards.length === 0 && (
              <div className="wb-empty">
                <b>没有匹配内容</b>
                换个关键词试试，或清空搜索框查看全部。
              </div>
            )}
            {filteredCards.map((c) => (
              <div key={c.id} className="wb-row" style={{ alignItems: 'flex-start',
                flexDirection: 'column', gap: 4 }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'baseline', width: '100%' }}>
                  <span className="name">{c.title}</span>
                  <span className="tag">{c.category}</span>
                  <span className="spacer" />
                  <span className="mono">{c.id}</span>
                </div>
                {c.summary && (
                  <p style={{ margin: 0, fontSize: 12.5, color: 'var(--ink-3)',
                    lineHeight: 1.65 }}>
                    {c.summary}
                  </p>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
