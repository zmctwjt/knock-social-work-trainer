/**
 * 教师工作台
 *
 * 四个视图：班级总览 / 学员画像 / 训练趋势 / 内容查阅。
 * 权限以服务端为准——本页只是入口，真正的隔离在 `require_roles` 与
 * `accounts.teacher_id` 归属过滤上；越权时接口返回 40301。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store/store.tsx';
import { apiGet, apiSend } from '../lib/authClient.ts';
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

interface DimAvg {
  key: string;
  name: string;
  avg: number;
  count: number;
}

interface TrendPoint {
  date: string;
  sessions: number;
  avg_total: number;
}

interface ScenarioUsage {
  scenario_id: string;
  scenario_name: string;
  sessions: number;
  avg_total: number;
}

interface ClassTrend {
  points: TrendPoint[];
  dimensions: DimAvg[];
  scenarios: ScenarioUsage[];
}

interface LearnerDetail {
  account_id: string;
  username: string;
  nickname: string;
  is_active: boolean;
  last_login_at: string | null;
  sessions: number;
  finished: number;
  avg_total: number;
  best_total: number;
  total_turns: number;
  total_minutes: number;
  dimensions: DimAvg[];
  weakest: string;
  trend: TrendPoint[];
  scenarios: ScenarioUsage[];
}

interface RecordRow {
  scenario_name?: string;
  score_total?: number;
  created_at?: string;
}

const TABS = ['班级总览', '学员画像', '训练趋势', '内容查阅'] as const;
type Tab = (typeof TABS)[number];

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
  const [cards, setCards] = useState<{ id: string; title: string; category: string; summary: string }[]>([]);
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
    const [l, s, t] = await Promise.all([
      apiGet<{ items: Learner[] }>('/api/v1/teacher/learners'),
      apiGet<ClassStats>('/api/v1/teacher/stats'),
      apiGet<ClassTrend>('/api/v1/teacher/trend'),
    ]);
    if (!l && !s) setErr('无法读取班级数据，请确认已用教师或管理员账号登录');
    else setErr('');
    const items = l?.items ?? [];
    setLearners(items);
    setStats(s ?? null);
    setTrend(t ?? null);
    setLoading(false);
    // 自动选中第一名学员：否则直接切到「学员画像」会是一片空白，
    // 用户以为坏了。有数据时默认展示最需要关注的人（均分最低者）。
    if (items.length) {
      const target = [...items].sort((a, b) => (a.avg_total || 999) - (b.avg_total || 999))[0];
      setSelected(target);
      void loadDetail(target);
    }
  }, [loadDetail]);

  useEffect(() => {
    void load();
  }, [load]);

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
    if (r.ok) {
      setBindName('');
      void load();
    }
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
        <div className="frame" style={{ padding: '48px 0' }}>
          <p>请先登录教师或管理员账号。</p>
          <button className="btn-primary" type="button" onClick={() => nav('/login')}>去登录</button>
        </div>
      </div>
    );
  }

  return (
    <div className="screen is-on">
      <div className="frame" style={{ display: 'block', padding: '28px 0 64px' }}>
        <div className="k">教师工作台 · TEACHER</div>
        <h2 style={{ margin: '8px 0 4px' }}>{account.nickname}，欢迎回来</h2>
        <p style={{ color: 'var(--ink-3)', marginBottom: 16 }}>
          当前角色：{role === 'admin' ? '管理员（可查看全部学员）' : '教师'}。只能看到自己名下学员的数据。
        </p>

        <div style={{ display: 'flex', gap: 10, marginBottom: 18, flexWrap: 'wrap' }}>
          {TABS.map((t) => (
            <button key={t} type="button" className={t === tab ? 'btn-primary' : 'btn-ghost'}
              onClick={() => setTab(t)} style={{ padding: '6px 16px' }}>{t}</button>
          ))}
          <button className="btn-ghost" type="button" onClick={() => { void load(); }}
            style={{ padding: '6px 16px' }}>刷新</button>
          {role === 'admin' && (
            <button className="btn-ghost" type="button" onClick={() => nav('/admin')}
              style={{ padding: '6px 16px' }}>管理后台</button>
          )}
        </div>

        {msg && <p style={{ color: '#b45309', marginBottom: 12, fontSize: 13 }}>{msg}</p>}
        {loading && <p style={{ color: 'var(--ink-3)' }}>加载中…</p>}
        {err && <p style={{ color: '#b45309' }}>{err}</p>}

        {/* ── 班级总览 ── */}
        {tab === '班级总览' && (
          <>
            {stats && (
              <div style={{ display: 'flex', gap: 32, flexWrap: 'wrap', padding: '16px 0 24px' }}>
                {[
                  ['学员数', stats.learners],
                  ['训练次数', stats.sessions],
                  ['班级均分', stats.avg_total || '—'],
                  ['最薄弱维度', stats.weakest ? DIM_LABEL[stats.weakest] || stats.weakest : '—'],
                ].map(([label, value]) => (
                  <div key={String(label)}>
                    <div className="k">{label}</div>
                    <b style={{ fontSize: 26 }}>{value}</b>
                  </div>
                ))}
              </div>
            )}

            <div style={{ display: 'flex', gap: 10, alignItems: 'center', margin: '8px 0 18px', flexWrap: 'wrap' }}>
              <input placeholder="输入学员用户名，绑定到名下" value={bindName}
                onChange={(e) => setBindName(e.target.value)}
                style={{ padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, minWidth: 220 }} />
              <button className="btn-primary" type="button" onClick={bindLearner}
                style={{ padding: '8px 16px' }}>绑定</button>
            </div>

            <div className="k" style={{ marginBottom: 10 }}>名下学员（{learners.length}，点击看画像）</div>
            {learners.length === 0 && !loading && (
              <p style={{ color: 'var(--ink-3)' }}>
                暂无学员。可在上方绑定，或由管理员在管理后台创建学生账号。
              </p>
            )}
            {learners.map((x) => (
              <button key={x.account_id} type="button" onClick={() => openLearner(x)}
                style={{
                  display: 'flex', gap: 16, alignItems: 'center', width: '100%', textAlign: 'left',
                  padding: '12px 14px', border: '1px solid #eee', borderRadius: 8,
                  background: '#fff', marginBottom: 8, cursor: 'pointer',
                }}>
                <span style={{ width: 24, height: 24, borderRadius: '50%', background: '#1F3A5F',
                  color: '#fff', fontSize: 12, display: 'grid', placeItems: 'center' }}>
                  {x.nickname[0]}
                </span>
                <span style={{ width: 110 }}>{x.nickname}</span>
                <span style={{ width: 120, fontSize: 13, color: 'var(--ink-3)' }}>{x.username}</span>
                <span style={{ width: 90, fontSize: 13 }}>训练 {x.sessions} 次</span>
                <span style={{ width: 90, fontSize: 13 }}>均分 {x.avg_total || '—'}</span>
                <span style={{
                  width: 70, fontSize: 12,
                  color: x.is_active ? '#15803d' : '#b91c1c',
                }}>{x.is_active ? '正常' : '已停用'}</span>
                <span style={{ flex: 1, fontSize: 12, color: 'var(--ink-3)', textAlign: 'right' }}>
                  {x.last_login_at ? `最近登录 ${new Date(x.last_login_at).toLocaleDateString('zh-CN')}` : '从未登录'}
                </span>
              </button>
            ))}
          </>
        )}

        {/* ── 学员画像 ── */}
        {tab === '学员画像' && (
          <>
            {!selected && (
              <p style={{ color: 'var(--ink-3)' }}>请先在「班级总览」里点击一名学员。</p>
            )}
            {selected && !detail && <p style={{ color: 'var(--ink-3)' }}>读取画像中…</p>}
            {selected && detail && (
              <>
                <h3 style={{ margin: '4px 0 12px' }}>
                  {detail.nickname}
                  <span style={{ fontSize: 13, color: 'var(--ink-3)', marginLeft: 10 }}>
                    {detail.username} · {detail.is_active ? '在册' : '已停用'}
                  </span>
                </h3>
                <div style={{ display: 'flex', gap: 28, flexWrap: 'wrap', marginBottom: 24 }}>
                  {[
                    ['训练次数', detail.sessions],
                    ['完成会话', detail.finished],
                    ['平均分', detail.avg_total || '—'],
                    ['最好成绩', detail.best_total || '—'],
                    ['总轮次', detail.total_turns],
                    ['累计时长', `${detail.total_minutes} 分钟`],
                  ].map(([label, value]) => (
                    <div key={String(label)}>
                      <div className="k">{label}</div>
                      <b style={{ fontSize: 22 }}>{value}</b>
                    </div>
                  ))}
                </div>

                <div className="k" style={{ marginBottom: 10 }}>
                  六维画像{detail.weakest ? `（最薄弱：${DIM_LABEL[detail.weakest] || detail.weakest}）` : ''}
                </div>
                <RadarDimensionChart series={[{ name: detail.nickname, dims: detail.dimensions }]} />

                <div className="k" style={{ margin: '24px 0 10px' }}>近 14 天进步曲线</div>
                <AverageTrendChart points={detail.trend} height={240} />

                <div className="k" style={{ margin: '24px 0 10px' }}>练习过的案例</div>
                {detail.scenarios.length === 0 && (
                  <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>还没有训练记录。</p>
                )}
                {detail.scenarios.map((s) => (
                  <div key={s.scenario_id} style={{
                    display: 'flex', gap: 16, padding: '8px 0', borderBottom: '1px solid #f2f0ec',
                  }}>
                    <span style={{ width: 100, fontSize: 13, color: 'var(--ink-3)' }}>{s.scenario_id}</span>
                    <span style={{ width: 140 }}>{s.scenario_name}</span>
                    <span style={{ width: 90, fontSize: 13 }}>{s.sessions} 次</span>
                    <span style={{ fontSize: 13 }}>均分 {s.avg_total || '—'}</span>
                  </div>
                ))}

                <div className="k" style={{ margin: '24px 0 10px' }}>最近训练记录</div>
                {records.length === 0 && (
                  <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>暂无记录。</p>
                )}
                {records.slice(0, 20).map((r, i) => (
                  <div key={i} style={{
                    display: 'flex', gap: 16, padding: '7px 0', borderBottom: '1px solid #f2f0ec',
                  }}>
                    <span style={{ width: 130 }}>{r.scenario_name || '—'}</span>
                    <span style={{ width: 70 }}>{r.score_total ?? '—'} 分</span>
                    <span style={{ fontSize: 12, color: 'var(--ink-3)' }}>
                      {r.created_at ? new Date(r.created_at).toLocaleString('zh-CN') : ''}
                    </span>
                  </div>
                ))}
              </>
            )}
          </>
        )}

        {/* ── 训练趋势 ── */}
        {tab === '训练趋势' && (
          <>
            <div className="k" style={{ marginBottom: 10 }}>班级近 14 天平均分</div>
            <AverageTrendChart points={trend?.points ?? []} height={260} />

            <div className="k" style={{ margin: '28px 0 10px' }}>班级六维均值</div>
            <DimensionBarChart dims={trend?.dimensions ?? []} weakest={stats?.weakest} />

            <div className="k" style={{ margin: '28px 0 10px' }}>案例练习分布</div>
            <ScenarioUsageChart data={trend?.scenarios ?? []} />
          </>
        )}

        {/* ── 内容查阅 ── */}
        {tab === '内容查阅' && (
          <>
            <div className="k" style={{ marginBottom: 10 }}>技巧卡与伦理守则（教学参考）</div>
            <input placeholder="按标题、摘要或分类搜索" value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              style={{ padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6,
                width: '100%', maxWidth: 360, marginBottom: 16 }} />
            {filteredCards.length === 0 && (
              <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>没有匹配的内容。</p>
            )}
            {filteredCards.map((c) => (
              <div key={c.id} style={{ padding: '12px 14px', border: '1px solid #eee',
                borderRadius: 8, marginBottom: 8 }}>
                <div style={{ display: 'flex', gap: 10, alignItems: 'baseline' }}>
                  <b style={{ fontSize: 14 }}>{c.title}</b>
                  <span style={{ fontSize: 12, color: '#D97706' }}>{c.category}</span>
                  <span style={{ fontSize: 12, color: 'var(--ink-3)', marginLeft: 'auto' }}>{c.id}</span>
                </div>
                {c.summary && (
                  <p style={{ fontSize: 13, color: 'var(--ink-3)', margin: '6px 0 0' }}>{c.summary}</p>
                )}
              </div>
            ))}
          </>
        )}
      </div>
    </div>
  );
}
