/**
 * 新手引导 —— 13 步，按真实使用路径依次触发
 *
 * 关键设计：
 * - 用 box-shadow 挖洞高亮，不用 opacity:0 + JS 恢复（JS 挂了内容就永久消失）
 * - 目标元素不可见时自动跳到下一步（避免高亮框飞到左上角）
 * - localStorage 记忆已完成，顶栏「? 引导」可重看
 */
import { useEffect, useState, useCallback, useRef } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { useStore } from '../store/store.tsx';

interface Step {
  /** 路由前缀 */
  route: string;
  /** 目标选择器 */
  sel: string;
  title: string;
  body: string;
}

const STEPS: Step[] = [
  // ── 组 1 · 服务对象页（2 步）──
  {
    route: '/cases', sel: '.diff-picker',
    title: '先选难度',
    body: '简单实习 = 阻抗弱、提示全开；标准实训 = 课堂默认；挑战督导 = 高阻抗、无快捷话术。三档随时可换，不影响已有记录。',
  },
  {
    route: '/cases', sel: '.case.sensitive',
    title: '带敏感议题的角色',
    body: '双线边框 + 红色「含敏感议题」标签的角色（阿珍、老周）涉及家暴、矫正等题材，训练时会走单独的伦理提示。',
  },
  // ── 组 2 · 训练页（6 步）──
  {
    route: '/training', sel: '.casefile',
    title: '服务对象的档案',
    body: '这里是她/他的背景：年龄、职业、主诉。所有回应都基于这份人设生成，不会前后矛盾。',
  },
  {
    route: '/training', sel: '.script-log',
    title: '对话区',
    body: '你说的每一句都会出现在这里，右侧同步出现校样标记：删除线 = 扣分项，绿色下划线 = 加分项。',
  },
  {
    route: '/training', sel: '.ai-suggest',
    title: 'AI 建议卡',
    body: '它会告诉你此刻该往哪个方向问、为什么。卡里给了具体句子，可以直接「用这句」，也可以忽略自己来。',
  },
  {
    route: '/training', sel: '.checklist',
    title: '六维实时评分',
    body: '每个维度的权重和国标条款都标在名字下面。任何一条扣分都能追问依据——这是本作品的核心差异。',
  },
  {
    route: '/training', sel: '.nsf',
    title: '无剧透模式',
    body: '打开后分数隐藏，只保留对话。第一次练建议先开它，专注在对方说了什么上，而不是盯着分数。',
  },
  {
    route: '/training', sel: '.composer',
    title: '输入框固定在底部',
    body: '点快捷话术能直接填入，也可以自己写。按回车发送。发送后它不会移动，不会因为内容变化而跳来跳去。',
  },
  // ── 组 3 · 结算页（2 步）──
  {
    route: '/settle', sel: '.settle-head',
    title: '阶段小结',
    body: '每次提交本阶段后会生成一页逐句点评。每条都标出命中了哪条规则、扣了多少分、依据是哪一国的哪一条。',
  },
  {
    route: '/settle', sel: '.margin-list',
    title: '逐句校样',
    body: '这一栏是你这次面谈的「校样稿」。删的、改的、留的，每一条都能追到原话。',
  },
  // ── 组 4 · 复盘页（2 步）──
  {
    route: '/review', sel: '.rblock',
    title: '复盘三段',
    body: '做得好的是什么、需要改进的是什么、下一步练什么。每段都引用你的原话作为证据，不说空话。',
  },
  {
    route: '/review', sel: '.cmp',
    title: '和专家示范逐句对照',
    body: '左边是标准做法，右边是你的处理。同一句话的差别一眼可见——这是最容易记住的部分。',
  },
];

export default function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const nav = useNavigate();
  const loc = useLocation();
  const { account } = useStore();
  const [raw, setRaw] = useState(0);
  const [idx, setIdx] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);

  /* 目标不可见则跳过 */
  const resolve = useCallback((i: number): number => {
    for (let k = i; k < STEPS.length; k++) {
      const el = document.querySelector(STEPS[k].sel);
      if (el) {
        const r = el.getBoundingClientRect();
        const cs = getComputedStyle(el);
        if (r.width > 4 && r.height > 4 && cs.display !== 'none' && cs.visibility !== 'hidden') {
          return k;
        }
      }
    }
    return -1;
  }, []);

  /**
   * 测量目标位置（必须在 scrollIntoView 之后调用）。
   *
   * 为什么不能只测一次：滚动是异步的，字体与入场动画也会改变元素高度。
   * 所以先双 rAF 等布局算完，再在 600ms 内每 120ms 复测一次。
   */
  const measureSoon = useCallback((sel: string) => {
    const measure = () => {
      const el = document.querySelector(sel);
      if (!el) return;
      const r = el.getBoundingClientRect();
      if (r.width < 2 && r.height < 2) return;
      setRect(r);
    };

    const raf1 = requestAnimationFrame(() => {
      requestAnimationFrame(measure);
    });
    const timers = [1, 2, 3, 4, 5].map((i) => setTimeout(measure, i * 120));

    return () => {
      cancelAnimationFrame(raf1);
      timers.forEach(clearTimeout);
    };
  }, []);

  /* 打开时定位到第一步 */
  useEffect(() => {
    if (!open) return;
    setRaw(0);
  }, [open]);

  /* 切路由 + 量位置
     ★ 只在「换了一步」时导航一次。
       以前这里是「当前路由不等于该步路由就导航」，结果引导一开着，
       用户点任何标签都会被立刻拽回 /cases —— 首次使用等于无法导航。 */
  const navigatedFor = useRef(-1);
  useEffect(() => {
    if (!open) return;
    const step = STEPS[raw];
    if (!step) { onClose(); return; }

    const cur = loc.pathname;
    const need = step.route;
    const onRightPage = cur.startsWith(need);

    if (!onRightPage) {
      // 这一步还没为它导航过 → 导航；已经导航过说明用户自己走开了 → 尊重用户，关掉引导
      if (navigatedFor.current === raw) { onClose(); return; }
      navigatedFor.current = raw;
      nav(step.route === '/training' ? '/training/W-01' : need);
      return;
    }

    const t = setTimeout(() => {
      const i = resolve(raw);
      if (i < 0) { onClose(); return; }
      if (i !== raw) { setRaw(i); return; }
      const el = document.querySelector(step.sel);
      if (el) {
        // ★ 必须先滚动再测量，且不能用 smooth：
        //   smooth 滚动是异步的，立刻 getBoundingClientRect 拿到的是滚动前的位置，
        //   高亮框就会画在错的地方（「无剧透模式」那次错位就是这么来的）。
        el.scrollIntoView({ behavior: 'auto', block: 'center' });
        setIdx(i);
        measureSoon(step.sel);
      }
    }, 420);
    return () => clearTimeout(t);
  }, [open, raw, loc.pathname, nav, resolve, onClose]);

  /**
   * （measureSoon 已上移到 resolve 之后定义，此处不再重复）
   */

  /* 跟随滚动 / 尺寸变化 / 字体加载 */
  useEffect(() => {
    if (!open || !rect) return;
    const sel = STEPS[idx]?.sel ?? '';
    const upd = () => {
      const el = document.querySelector(sel);
      if (el) {
        const r = el.getBoundingClientRect();
        if (r.width > 2 || r.height > 2) setRect(r);
      }
    };
    window.addEventListener('scroll', upd, { passive: true, capture: true });
    window.addEventListener('resize', upd);
    // 字体晚于首次渲染到位时，元素高度会跳，这里补一次
    const fonts = (document as Document & { fonts?: FontFaceSet }).fonts;
    fonts?.ready.then(upd).catch(() => {});
    return () => {
      window.removeEventListener('scroll', upd, { capture: true } as EventListenerOptions);
      window.removeEventListener('resize', upd);
    };
  }, [open, idx, rect]);

  /* Esc 关闭 */
  useEffect(() => {
    if (!open) return;
    const k = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', k);
    return () => window.removeEventListener('keydown', k);
  }, [open, onClose]);

  if (!open) return null;
  const step = STEPS[idx];
  if (!step) return null;

  const PAD = 10;
  const box = rect
    ? { left: rect.left - PAD, top: rect.top - PAD, w: rect.width + PAD * 2, h: rect.height + PAD * 2 }
    : { left: 0, top: 0, w: 0, h: 0 };

  /* 气泡位置 */
  const BW = 380;
  const roomBelow = window.innerHeight - (box.top + box.h);
  const below = roomBelow > 200;
  const bTop = below ? box.top + box.h + 14 : Math.max(14, box.top - 214);
  const bLeft = Math.min(Math.max(14, box.left), window.innerWidth - BW - 14);

  return (
    <div className="tour-root" role="dialog" aria-label="新手引导">
      {/* 挖洞遮罩：用 box-shadow 铺满四周，不动目标元素本身 */}
      <div className="tour-hole" style={{
        left: box.left, top: box.top, width: box.w, height: box.h,
      }} />
      {/* 气泡 */}
      <div className="tour-card" style={{ left: bLeft, top: bTop, width: BW }}>
        <div className="tour-top">
          <span className="tour-no">
            {String(idx + 1).padStart(2, '0')} / {String(STEPS.length).padStart(2, '0')}
          </span>
          <button className="tour-x" type="button" onClick={onClose} aria-label="关闭引导">✕</button>
        </div>
        <h3>{step.title}</h3>
        <p>{step.body}</p>
        <div className="tour-bot">
          <div className="tour-dots">
            {STEPS.map((_, i) => <i key={i} className={i === idx ? 'on' : i < idx ? 'done' : ''} />)}
          </div>
          <div className="tour-btns">
            <button type="button" className="btn-ghost" onClick={onClose}>跳过</button>
            <button type="button" className="btn-primary"
              onClick={() => {
                if (idx >= STEPS.length - 1) onClose();
                else setRaw(idx + 1);
              }}>
              {idx >= STEPS.length - 1 ? '开始训练' : '下一步'}
            </button>
          </div>
        </div>
        {!account && <div className="tour-hint">提示：先登录才能保存训练记录</div>}
      </div>
    </div>
  );
}

export const TOUR_LENGTH = STEPS.length;
