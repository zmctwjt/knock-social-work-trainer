/**
 * 叩门 · 应用外壳
 *
 * - 顶栏结构来自 docs/预览/叩门-设计示例.html（.masthead / .viewtabs）
 * - 账号体系：本地 store，未登录时只放行登录页与首页
 * - 引导：13 步，顶栏「? 引导」可重看
 */
import { NavLink, Navigate, Routes, Route, useNavigate, useParams, useLocation } from 'react-router-dom';
import { lazy, Suspense, useState, useEffect } from 'react';
import ErrorBoundary from './components/ErrorBoundary.tsx';
import { StoreProvider, useStore } from './store/store.tsx';
import { SCENARIOS } from './data/scenarios.ts';
import { isKnownScenario } from './data/scenarios.ts';
import { probeAi } from './lib/aiClient.ts';
import { useAiStatus } from './hooks/useSession.ts';
import { dbReady } from './lib/db.ts';
import Tour, { TOUR_LENGTH } from './components/Tour.tsx';

import HomePage from './pages/HomePage.tsx';
import CaseSelectPage from './pages/CaseSelectPage.tsx';
import TrainingPage from './pages/TrainingPage.tsx';
import SettlePage from './pages/SettlePage.tsx';
import ReviewPage from './pages/ReviewPage.tsx';
import GrowthPage from './pages/GrowthPage.tsx';
import KnowledgePage from './pages/KnowledgePage.tsx';
import AboutPage from './pages/AboutPage.tsx';
import LoginPage from './pages/LoginPage.tsx';
import SettingsPage from './pages/SettingsPage.tsx';
// 教师/管理页懒加载：这两页会带上 ECharts，学生用户不该为它们付出首屏成本
const TeacherPage = lazy(() => import('./pages/TeacherPage.tsx'));
const AdminPage = lazy(() => import('./pages/AdminPage.tsx'));
import { ROLE_LABEL, navItemsFor, type Role } from './lib/authClient.ts';
import EditorPage from './pages/EditorPage.tsx';


function AccountChip() {
  const { account, accounts, switchAccount, logout, role } = useStore();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    const close = () => setOpen(false);
    setTimeout(() => document.addEventListener('click', close), 0);
    return () => document.removeEventListener('click', close);
  }, [open]);

  if (!account) {
    return (
      <button className="mast-badge" type="button" onClick={() => nav('/login')}
        style={{ cursor: 'pointer' }}>
        登录
      </button>
    );
  }

  return (
    <div className="mast-acc-wrap">
      <button className="mast-acc" type="button"
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}>
        <span className="av">{account.nickname[0]}</span>
        <span className="nm">{account.nickname}</span>
        <span className="role-tag" title={`当前角色：${ROLE_LABEL[role]}`}>{ROLE_LABEL[role]}</span>
      </button>
      {open && (
        <div className="mast-menu" onClick={(e) => e.stopPropagation()}>
          <button type="button" onClick={() => { setOpen(false); nav('/growth'); }}>
            我的成长中心
          </button>
          {role !== 'student' && role !== 'guest' && (
            <button type="button" onClick={() => { setOpen(false); nav('/teacher'); }}>
              教师工作台
            </button>
          )}
          {role === 'admin' && (
            <button type="button" onClick={() => { setOpen(false); nav('/admin'); }}>
              管理后台
            </button>
          )}
          <button type="button" onClick={() => { setOpen(false); nav('/login'); }}>
            切换 / 新建账号
          </button>
          {accounts.length > 1 && (
            <>
              <div className="sep" />
              {accounts.filter((a) => a.id !== account.id).slice(0, 4).map((a) => (
                <button key={a.id} type="button"
                  onClick={() => { switchAccount(a.id); setOpen(false); }}>
                  切换到「{a.nickname}」
                </button>
              ))}
            </>
          )}
          <div className="sep" />
          <button type="button" onClick={() => { logout(); setOpen(false); nav('/login'); }}>
            退出登录
          </button>
        </div>
      )}
    </div>
  );
}

function Shell({ children }: { children: React.ReactNode }) {
  const ai = useAiStatus();
  const { account, tourDone, setTourDone, role } = useStore();
  const [tour, setTour] = useState(false);

  /* 登录后首次自动开引导。
     只给学生开：引导第一步会跳到 /cases，对教师/管理员会把角色化落地页覆盖掉
     （此前实际踩到——登录进 #/teacher 后又被引导带回 #/cases）。 */
  useEffect(() => {
    if (!account || tourDone) return;
    if (role !== 'student') return;
    const t = setTimeout(() => setTour(true), 900);
    return () => clearTimeout(t);
  }, [account, tourDone, role]);

  return (
    <>
      <div className="atmosphere" aria-hidden="true">
        <div className="blob blob-1" /><div className="blob blob-2" /><div className="blob blob-3" />
      </div>
      <div className="grain" aria-hidden="true" />

      <header className="masthead">
        <div className="mast-top">
          <div className="wordmark">
            <span className="cn">叩门</span>
            <span className="en">Knock · Social Work Practice</span>
          </div>
          <span className="spacer" />
          <button className="mast-badge" type="button"
            onClick={() => void probeAi()}
            title={
              ai.detail
              + (ai.lastError ? ` ｜ 最近错误：${ai.lastError}` : '')
              + ' ｜ 点击重新检测'
              + (dbReady ? '' : ' ｜ 数据库未配置，成绩只存本机')
            }
            style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <span aria-hidden="true" style={{
              width: 6, height: 6, borderRadius: '50%',
              background: ai.ready ? 'var(--ok)' : 'var(--rule2)',
            }} />
            {ai.ready ? `AI · ${ai.model || 'GLM'}` : '规则模式'}
          </button>
          {role === 'student' && (
            <button className="mast-badge" type="button"
              onClick={() => { setTourDone(false); setTour(true); }}
              style={{ cursor: 'pointer' }} title={'重新播放 ' + TOUR_LENGTH + ' 步引导'}>
              ? 引导
            </button>
          )}
          <AccountChip />
        </div>
        {/* 顶栏是页面间导航，不是页内标签组：
            用 role=tablist/tab 属 ARIA 误用（tabs 语义要求同页切换 tabpanel），
            读屏会念成"标签 3/9"，与真实行为不符。改为普通 nav + aria-current。 */}
        <nav className="viewtabs" aria-label="主导航">
          {navItemsFor(role).map((t) => (
            <NavLink
              key={t.to}
              to={t.to}
              end={t.to === '/'}
              style={{ textDecoration: 'none' }}
            >
              {({ isActive }) => (
                <span className="viewtab" aria-current={isActive ? 'page' : undefined}>
                  <span className="no">{t.no}</span>{t.label}
                </span>
              )}
            </NavLink>
          ))}
        </nav>
      </header>
      <div className="rule-thick" />
      <div className="rule-thin" />
      {children}
      <Tour open={tour} onClose={() => { setTour(false); setTourDone(true); }} />
    </>
  );
}

function TrainingRoute() {
  const { id } = useParams();
  const nav = useNavigate();
  const { session } = useStore();
  // ★ 优先级：URL 里的 id > store 里正在练的角色 > 第一个
  //   少了这一条，点顶栏「面谈训练」（URL 是 /training 不带 id）
  //   就会退回王阿姨，把正在进行的对话弄丢。
  const scenarioId =
    (id && isKnownScenario(id) ? id : null)
    ?? (session && isKnownScenario(session.scriptId) ? session.scriptId : null)
    ?? SCENARIOS[0].id;
  // key 让换角色时重挂载；同一角色切页面回来 key 不变 → 不重置
  return <TrainingPage key={scenarioId} scenarioId={scenarioId} onExit={() => nav('/cases')} />;
}

/** 懒加载页面的占位：避免空白闪烁 */
function PageLoading() {
  return (
    <div className="screen is-on">
      <div className="frame" style={{ padding: '64px 0', textAlign: 'center' }}>
        <p style={{ color: 'var(--ink-3)', fontSize: 13 }}>页面加载中…</p>
      </div>
    </div>
  );
}

/** 首页分流：教师进班级看板、管理员进管理后台，学生看训练首页。

 * 这样"登录即进入自己的工作区"，不需要再点头像找入口。
 */
function RoleHome() {
  const { role, account } = useStore();
  const loc = useLocation();
  // 只在"已登录且主动访问首页"时重定向；登录流程自身已按角色跳转，
  // 这里若也跳会与登录页的 nav 竞争，导致先到 /teacher 又被改回 /cases。
  if (!account) return <HomePage />;
  if (loc.pathname !== '/') return <HomePage />;
  if (role === 'admin') return <Navigate to="/admin" replace />;
  if (role === 'teacher') return <Navigate to="/teacher" replace />;
  return <HomePage />;
}

/** 路由级角色守卫：服务端是最终防线，这里只负责不让学生看到入口。 */
function RoleGuard({ allow, children }: { allow: Role[]; children: React.ReactNode }) {
  const { role } = useStore();
  const nav = useNavigate();
  if (!allow.includes(role)) {
    return (
      <div className="screen is-on">
        <div className="frame" style={{ padding: '72px 0' }}>
          <div className="k">403 · 无权限访问</div>
          <h2 style={{ margin: '14px 0 10px' }}>当前角色无权打开该页面</h2>
          <p style={{ color: 'var(--ink-3)', marginBottom: 26 }}>
            当前角色：{ROLE_LABEL[role]}。本页仅对 {allow.map((r) => ROLE_LABEL[r]).join(' / ')} 开放。
          </p>
          <button className="btn-primary" type="button" onClick={() => nav('/')}>回首页</button>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

function Guard({ children }: { children: React.ReactNode }) {
  const { account } = useStore();
  const loc = useLocation();
  const nav = useNavigate();
  const OPEN = ['/', '/login', '/about', '/knowledge'];
  const free = OPEN.includes(loc.pathname);

  useEffect(() => {
    if (!account && !free) nav('/login');
  }, [account, free, nav]);

  if (!account && !free) return <LoginPage />;
  return <>{children}</>;
}

function Bare({ children }: { children: React.ReactNode }) {
  const loc = useLocation();
  const { account } = useStore();
  const OPEN = ['/', '/about', '/knowledge'];
  // 登录页、或未登录时的受限页 → 全屏裸布局，不显示顶栏与标签
  const bare = loc.pathname === '/login' || (!account && !OPEN.includes(loc.pathname));
  if (bare) {
    return (
      <>
        <div className="atmosphere" aria-hidden="true">
          <div className="blob blob-1" /><div className="blob blob-2" /><div className="blob blob-3" />
        </div>
        <div className="grain" aria-hidden="true" />
        <div className="bare-brand">
          <span className="cn">叩门</span>
          <span className="en">Knock · Social Work Practice</span>
        </div>
        {children}
      </>
    );
  }
  return <Shell>{children}</Shell>;
}

function Routed() {
  return (
    <Bare>
      <Guard>
        {/* 只包路由内容而不是整棵树：页面崩了顶栏还在，
            用户能直接点导航换页，不用刷新整站 */}
        <ErrorBoundary>
          <Routes>
          <Route path="/" element={<RoleHome />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/cases" element={<CaseSelectPage />} />
          <Route path="/training" element={<TrainingRoute />} />
          <Route path="/training/:id" element={<TrainingRoute />} />
          <Route path="/settle" element={<SettlePage />} />
          <Route path="/review" element={<ReviewPage />} />
          <Route path="/growth" element={<GrowthPage />} />
          <Route path="/knowledge" element={<KnowledgePage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="/editor" element={<EditorPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/teacher" element={
            <RoleGuard allow={['teacher', 'admin']}>
              <Suspense fallback={<PageLoading />}><TeacherPage /></Suspense>
            </RoleGuard>
          } />
          <Route path="/admin" element={
            <RoleGuard allow={['admin']}>
              <Suspense fallback={<PageLoading />}><AdminPage /></Suspense>
            </RoleGuard>
          } />
          {/* 兜底：任何拼错的地址都回到首页，而不是渲染出「顶栏 + 一条横线 + 大片空白」 */}
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ErrorBoundary>
      </Guard>
    </Bare>
  );
}

function NotFound() {
  const nav = useNavigate();
  const loc = useLocation();
  return (
    <div className="screen is-on">
      <div className="frame" style={{ display: 'block', padding: '72px 0' }}>
        <div className="k">404 · Page not found</div>
        <h2 style={{ margin: '14px 0 10px' }}>这个地址没有对应的页面</h2>
        <p style={{ color: 'var(--ink-3)', marginBottom: 6 }}>你访问的是 <code>{loc.pathname}</code>。</p>
        <p style={{ color: 'var(--ink-3)', marginBottom: 26 }}>
          可能是链接拼写有误，或该角色已被删除。
        </p>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button className="btn-primary" type="button" onClick={() => nav('/')}>回首页</button>
          <button className="btn-ghost" type="button" onClick={() => nav('/cases')}>去选服务对象</button>
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <StoreProvider>
      <Routed />
    </StoreProvider>
  );
}
