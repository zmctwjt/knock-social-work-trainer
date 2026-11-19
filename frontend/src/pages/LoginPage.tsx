/**
 * 登录 / 注册
 * 本地账号体系（localStorage），接口与 Supabase Auth 对齐，接入时只换实现
 */
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { useStore } from '../store/store.tsx';
import * as auth from '../lib/authClient.ts';
import type { Role } from '../lib/authClient.ts';

/** 演示账号：点了自动填入用户名与密码，方便答辩现场切换角色 */
const DEMO_ACCOUNTS = [
  { label: '学生 · 学员小李', username: 'student01', password: 'Student@12345' },
  { label: '教师 · 张老师', username: 'teacher01', password: 'Teacher@12345' },
  { label: '管理员 · 教务', username: 'admin01', password: 'Admin@12345' },
];

export default function LoginPage() {
  const { register, login, loginGuest, accounts, switchAccount, account, serverMode } = useStore();
  const nav = useNavigate();
  const [mode, setMode] = useState<'login' | 'register'>('login');
  const [nick, setNick] = useState('');
  const [pass, setPass] = useState('');
  const [pass2, setPass2] = useState('');
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  /* 只在「本次刚完成登录/注册」时跳转；直接进页面不跳，便于切换账号 */
  const [justOk, setJustOk] = useState(false);
  /* 登录成功后立即按角色跳转。
     不能用 setTimeout —— 登录成功后 account 有值，Guard 会卸载本组件，
     effect 的 cleanup 会把定时器清掉，导致永远不跳转（此前实际踩到）。 */
  useEffect(() => {
    if (!justOk || !account) return;
    const role = (account.role as Role) ?? 'student';
    const target = role === 'student' || role === 'guest' ? '/cases' : auth.homeFor(role);
    if (location.hash !== `#${target}`) nav(target, { replace: true });
  }, [justOk, account, nav]);

  const [busy, setBusy] = useState(false);

  async function submit() {
    if (busy) return;
    if (mode === 'register' && pass !== pass2) {
      setMsg({ ok: false, text: '两次输入的密码不一致' });
      return;
    }
    setBusy(true);
    try {
      // 服务端模式下"注册"即登录：账号由教务统一创建，不开放自助注册
      const r = mode === 'register' ? await register(nick, pass) : await login(nick, pass);
      setMsg({ ok: r.ok, text: r.msg });
      if (r.ok) {
        setJustOk(true);
        // 用登录返回值里的角色，不要读 localStorage —— 读取时机早于写入会回落成学生
        const role: Role = r.role ?? 'student';
        nav(role === 'student' || role === 'guest' ? '/cases' : auth.homeFor(role), { replace: true });
      }
    } finally {
      setBusy(false);
    }
  }

  async function enterGuest() {
    if (busy) return;
    setBusy(true);
    try {
      const r = await loginGuest();
      setMsg({ ok: r.ok, text: r.msg });
      if (r.ok) {
        setJustOk(true);
        nav('/cases', { replace: true });
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="screen is-on login-view">
      <div className="login-wrap">
        <div className="login-card">
          <div className="login-head">
            <div className="k">Account · 账号</div>
            <h2>{mode === 'login' ? <>登录后<em>开始训练</em></> : <>创建你的<em>训练账号</em></>}</h2>
            <p>训练记录按账号分别保存，成长曲线与热力图只统计当前账号的数据。</p>
            <div className="lede">民政部公告第 426 号 · 社会工作方法 个案工作</div>
          </div>

          <div className="login-tabs" role="tablist">
            <button type="button" className="login-tab" role="tab"
              aria-selected={mode === 'login'} onClick={() => { setMode('login'); setMsg(null); }}>
              登录
            </button>
            <button type="button" className="login-tab" role="tab"
              aria-selected={mode === 'register'} onClick={() => { setMode('register'); setMsg(null); }}>
              注册
            </button>
          </div>

          <div className="login-form">
            <label className="field">
              <span>昵称</span>
              <input value={nick} onChange={(e) => setNick(e.target.value)}
                placeholder="例如：赵同学" autoComplete="username" />
            </label>
            <label className="field">
              <span>密码</span>
              <input type="password" value={pass} onChange={(e) => setPass(e.target.value)}
                placeholder={mode === 'register' ? '至少 4 位' : '输入密码'}
                autoComplete={mode === 'register' ? 'new-password' : 'current-password'}
                onKeyDown={(e) => { if (e.key === 'Enter' && mode === 'login') submit(); }} />
            </label>
            {mode === 'register' && (
              <label className="field">
                <span>确认密码</span>
                <input type="password" value={pass2} onChange={(e) => setPass2(e.target.value)}
                  placeholder="再输一次"
                  onKeyDown={(e) => { if (e.key === 'Enter') submit(); }} />
              </label>
            )}

            {msg && (
              <div className={'login-msg ' + (msg.ok ? 'ok' : 'bad')}>{msg.text}</div>
            )}

            <button className="btn-primary login-submit" type="button"
              onClick={submit} disabled={busy}>
              {busy ? '请稍候…' : mode === 'login' ? '登录' : '登录（账号由教务创建）'}
            </button>
            {serverMode && (
              <button className="btn-ghost login-submit" type="button"
                onClick={enterGuest} disabled={busy} style={{ marginTop: 8 }}>
                快速体验（只读，无需账号）
              </button>
            )}
          </div>

          {accounts.length > 0 && (
            <div className="login-accounts">
              <div className="k">本机已有账号（点击快速切换）</div>
              {accounts.map((a) => (
                <button key={a.id} type="button" className="acc-row"
                  onClick={() => { switchAccount(a.id); setJustOk(true); }}>
                  <span className="dot" />
                  <span className="nm">{a.nickname}</span>
                  <span className="tm">{new Date(a.createdAt).toLocaleDateString('zh-CN')}</span>
                </button>
              ))}
            </div>
          )}

          <div className="login-feats">
            <div><b>12</b><span>位服务对象</span></div>
            <div><b>6</b><span>维评分</span></div>
            <div><b>19</b><span>张技巧卡</span></div>
            <div><b>12</b><span>条伦理守则</span></div>
          </div>

          <p className="login-note">
            账号由教务统一创建，不开放自助注册。<br />
            登录后顶栏会显示你的<span style={{ fontWeight: 600 }}>角色</span>：学生只能训练、
            教师可看名下学员、管理员可管理账号与内容。
          </p>

          {serverMode && (
            <div className="login-accounts" style={{ marginTop: 8 }}>
              <div className="k">演示账号（可直接试用三个角色）</div>
              {DEMO_ACCOUNTS.map((d) => (
                <button key={d.username} type="button" className="acc-row"
                  onClick={() => { setMode('login'); setNick(d.username); setPass(d.password); }}>
                  <span className="dot" />
                  <span className="nm">{d.label}</span>
                  <span className="tm">{d.username}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
