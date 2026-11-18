/**
 * 02 服务对象选择 —— 12 位角色
 * 结构与 class 名来自 docs/预览/叩门-设计示例.html
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { SCENARIOS } from '../data/scenarios.ts';
import { useStore } from '../store/store.tsx';
import { loadSettingsLocal, saveSettingsLocal, type UserSettings } from '../lib/db.ts';
import type { CustomScript } from './EditorPage.tsx';

const DISK = ['#2F5D50', '#7A5C42', '#6B6A72', '#9A7430', '#22463C', '#5A5248',
  '#6B5B7A', '#3E5C6B', '#6B4A3E', '#4A5B3E', '#5C4A6B', '#3E4A5C'];

const DIFFS = [
  ['简单实习', 'novice', '服务对象阻抗弱 · 提示与快捷话术全开 · 适合第一次接触'],
  ['标准实训', 'standard', '真实阻抗强度 · 快捷话术减半 · 对应课堂实训默认难度'],
  ['挑战督导', 'advanced', '高阻抗 · 沉默压力测试 · 无快捷话术 · 建议完成全部剧本后再来'],
] as const;

export default function CaseSelectPage() {
  const nav = useNavigate();
  const { account, startSession } = useStore();
  // 优先级：本次会话选择 > 设置页默认值 > 兜底
  const [diff, setDiff] = useState<string>(() =>
    sessionStorage.getItem('knock.diff') || loadSettingsLocal().default_difficulty || '标准实训',
  );
  const [nick, setNick] = useState(localStorage.getItem('knock.nick') || '');
  const [picked, setPicked] = useState<string | null>(null);


  /** 内置 12 位 + 编辑器创建的自定义角色 */
  const custom = loadSettingsLocal().custom_scripts as CustomScript[];
  const all = [
    ...SCENARIOS.map((x) => ({
      id: x.id, name: x.name, age: x.age, gender: x.gender,
      archetype: x.archetype, difficulty: x.difficulty,
      sensitiveTag: x.sensitiveTag, brief: x.brief, custom: false,
    })),
    ...custom.map((x) => ({
      id: x.id, name: x.name, age: x.age, gender: x.gender,
      archetype: x.archetype, difficulty: x.difficulty,
      sensitiveTag: x.sensitiveTag, brief: x.brief, custom: true,
    })),
  ];

  const sel = all.find((x) => x.id === picked);

  /* 点卡片 = 选中（不跳转）；点「开始面谈」才进训练 */
  function toggle(id: string) {
    setPicked((v) => (v === id ? null : id));
  }

  function begin() {
    if (!account) { nav('/login'); return; }
    const id = picked ?? SCENARIOS[0].id;
    startSession(id, diff);
    sessionStorage.setItem('knock.diff', diff);
    // 同步到设置页，作为下次进服务对象页的默认值
    saveSettingsLocal({ default_difficulty: diff as UserSettings['default_difficulty'] });
    nav('/training/' + id);
  }



  return (
    <div className="screen is-on">
      <div className="p2-head">
        <div>
          <div className="k">难度选择 · Difficulty</div>
          <h2>选择本次面谈的服务对象</h2>
        </div>
        <div className="n">共 {all.length} 位角色{custom.length ? `（含 ${custom.length} 个自定义）` : ''} · 已选 {diff}<br />难度 2 – 5 星</div>
      </div>

      <div className="diff-picker" role="group" aria-label="难度选择">
        {DIFFS.map(([n, role, d]) => (
          <button key={n} className="diff-opt" type="button"
            aria-pressed={diff === n} onClick={() => setDiff(n)}>
            <span className="dn">{n} <span className="role"> {role}</span></span>
            <span className="dd">{d}</span>
          </button>
        ))}
      </div>

      <div className="kb-search" style={{ marginBottom: 18 }}>
        <input value={account ? account.nickname : (nick || '')} readOnly
          placeholder="请先登录" aria-label="当前账号" />
        <span className="cnt">{account ? "已登录" : "未登录"}</span>
      </div>

      <div className="case-grid">
        {all.map((s, i) => (
          <button key={s.id} type="button"
            className={'case' + (s.sensitiveTag !== '无' ? ' sensitive' : '') + (picked === s.id ? ' picked' : '') + (s.custom ? ' is-custom' : '')}
            onClick={() => toggle(s.id)}>
            <div className="case-top">
              <span className="case-no">{s.id.split('-')[1]}</span>
              <span className="case-disc" style={{ background: DISK[i % DISK.length] }}>
                {s.name[0]}
              </span>
              <span className="case-id">
                <span className="nm">{s.name}</span>
                <span className="mt">{s.age} 岁 · {s.gender} · {s.archetype}</span>
              </span>
            </div>
            <p className="case-brief">{s.brief}</p>
            <div className="case-foot">
              <span className="dots-diff" aria-label={'难度 ' + s.difficulty + ' 星'}>
                {[1, 2, 3, 4, 5].map((k) => <i key={k} className={k <= s.difficulty ? 'on' : ''} />)}
              </span>
              {s.custom && <span className="tag">自定义</span>}
              {s.sensitiveTag === '含敏感议题' && <span className="tag proof">含敏感议题</span>}
              {s.sensitiveTag === '含轻度无望感表达' && <span className="tag warn">含无望感表达</span>}
              <span className="case-go">{s.id} · {s.difficulty}/5 →</span>
            </div>
          </button>
        ))}
      </div>

      <div className={'pick-bar' + (picked ? ' on' : '')}>
        <div className="pb-l">
          {sel ? (
            <>
              <span className="pb-k">已选</span>
              <span className="pb-n">{sel.id} {sel.name}</span>
              <span className="pb-d">{sel.age} 岁 · {sel.archetype} · 难度 {sel.difficulty}/5</span>
            </>
          ) : (
            <span className="pb-k">请点上方卡片选择一位服务对象</span>
          )}
        </div>
        <button className="btn-primary pb-btn" type="button" onClick={begin}
          disabled={!picked}>
          {sel ? '开始面谈 →' : '先选择一位'}
        </button>
      </div>
    </div>
  );
}
