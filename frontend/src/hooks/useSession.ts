/**
 * 训练会话状态机
 *
 * 一次 send() 里走完「本地规则 → (可选)AI 意图补判 → 情绪/分值 → 台词」全流程，
 * 页面不需要知道任何判定细节。
 *
 * 三种 AI 模式（对应答辩时"规则主干 + AI 长尾"的三档演示）：
 *   rule    规则模式   —— 零调用，所有判定与台词都来自本地规则与预置台词
 *   hybrid  混合模式   —— 默认。台词走预置库（零延迟），AI 只做长尾意图补判 +
 *                        阶段六维评分（与规则底分 4:6 融合）+ 复盘生成
 *   ai      全 AI 模式 —— 服务对象台词也由 GLM-4.7-Flash 按人设实时生成（有延迟，可随时切回）
 *
 * 四条不可违反的边界：
 *   1. 危机级永远由本地硬规则拦截，**不进模型、不计分**
 *   2. 任何 AI 失败都静默回退到规则结果，页面永远拿不到 null
 *   3. 服务对象台词必须过 isScriptLine()，AI 生成的不进台词库、单独标注
 *   4. 阶段推进只能前进，不能回退
 */
import { useState, useCallback, useRef, useEffect } from 'react';
import type { DimensionKey, MarginNote, ChatMessage } from '../types.ts';
import { matchLocalRules, effectsForIntent, type MatchResult } from '../services/rules.ts';
import { generateReply, clampEmotion } from '../services/dialogueEngine.ts';
import { isScriptLine } from '../data/dialogueTree.ts';
import { classifyIntent, aiActAsPersona, aiStatus, onAiStatus, type AiMode } from '../lib/aiClient.ts';
import { PERSONAS, DIFFICULTY_RULES } from '../data/personas.ts';
import { getScenario } from '../data/scenarios.ts';
import { buildMarks, INTENT_TO_DIMENSION } from '../services/scoring.ts';
import type { AiStatus } from '../lib/aiClient.ts';

export type Difficulty = '简单实习' | '标准实训' | '挑战督导';
export type { AiMode };

/** 从设置页读「默认开启无剧透模式」—— 不要写死 */
export function readBlindfoldDefault(): boolean {
  try {
    const raw = localStorage.getItem('knock.settings');
    return raw ? (JSON.parse(raw).blindfold_default ?? false) : false;
  } catch {
    return false;
  }
}

/** 读设置页的默认 AI 模式。默认「全 AI」——服务对象的台词由模型按人设实时生成 */
export function readAiModeDefault(): AiMode {
  try {
    const raw = localStorage.getItem('knock.settings');
    const v = raw ? JSON.parse(raw).ai_mode : null;
    if (v === 'rule' || v === 'hybrid' || v === 'ai') return v;
  } catch { /* 忽略 */ }
  return 'ai';
}

/** 六维全零的初值，避免 undefined 参与运算 */
function zeroAdjust(): Record<DimensionKey, number> {
  return { empathy: 0, question: 0, advice: 0, ethics: 0, process: 0, risk: 0 };
}

/**
 * UI 的三阶段 → 内容层的五阶段。
 * 开局两句算「建立关系」，之后进入「问题探索」；二阶段走需求评估与资源链接；三阶段收口。
 */
function stageOfPhase(phase: 1 | 2 | 3, turn: number): 'rapport' | 'explore' | 'assess' | 'link' | 'close' {
  if (phase === 1) return turn <= 2 ? 'rapport' : 'explore';
  if (phase === 2) return turn <= 2 ? 'assess' : 'link';
  return 'close';
}

export interface SessionState {
  nickname: string;
  scenarioId: string;
  difficulty: Difficulty;
  aiMode: AiMode;
  blindfold: boolean;
  emotion: number;
  turn: number;
  phase: 1 | 2 | 3;
  judgeCount: number;
  hopelessSeen: boolean;
  messages: ChatMessage[];
  notes: MarginNote[];
  adjust: Record<DimensionKey, number>;
  busy: boolean;
  /** 命中危机后锁死输入，直到用户点「我知道了」 */
  crisisBlocked: boolean;
  /** 本阶段在 messages 里的起始下标，用于按阶段切分评分 */
  stageStart: number;
  /** 最近一次 AI 调用的可观测信息，界面上如实展示 */
  aiLast: { model: string; ms: number; used: boolean; note: string } | null;
}

/** store 里能恢复的字段（与 CurrentSession 结构对齐） */
export interface RestorableSession {
  messages: ChatMessage[];
  notes: MarginNote[];
  emotion: number;
  turn: number;
  phase: 1 | 2 | 3;
  judgeCount: number;
  hopelessSeen: boolean;
  blindfold: boolean;
  adjust: Record<DimensionKey, number>;
  stageStart?: number;
  difficulty?: Difficulty;
}

export type SessionSnapshot = RestorableSession;

function initial(
  scenarioId: string,
  nickname: string,
  restored?: RestorableSession | null,
): SessionState {
  const sc = getScenario(scenarioId);
  const base: SessionState = {
    nickname,
    scenarioId,
    difficulty: '标准实训',
    aiMode: readAiModeDefault(),
    blindfold: readBlindfoldDefault(),
    emotion: sc?.initialEmotion ?? 45,
    turn: 1,
    phase: 1,
    judgeCount: 0,
    hopelessSeen: false,
    messages: [],
    notes: [],
    adjust: zeroAdjust(),
    busy: false,
    crisisBlocked: false,
    stageStart: 0,
    aiLast: null,
  };

  if (!restored || !restored.messages || restored.messages.length === 0) return base;

  return {
    ...base,
    difficulty: restored.difficulty ?? base.difficulty,
    blindfold: restored.blindfold ?? base.blindfold,
    emotion: Number.isFinite(restored.emotion) ? restored.emotion : base.emotion,
    turn: restored.turn || 1,
    phase: restored.phase || 1,
    judgeCount: restored.judgeCount || 0,
    hopelessSeen: !!restored.hopelessSeen,
    messages: restored.messages,
    notes: restored.notes || [],
    adjust: { ...zeroAdjust(), ...(restored.adjust || {}) },
    stageStart: restored.stageStart ?? 0,
  };
}

export function useSession(
  scenarioId: string,
  nickname: string,
  /** 传入 store 里的会话，实现跨页面保留；不传则新建 */
  restored?: RestorableSession | null,
  onChange?: (snap: SessionSnapshot) => void,
) {
  const [state, setState] = useState<SessionState>(
    () => initial(scenarioId, nickname, restored),
  );

  /* 每次状态变化都同步给 store —— 保证 F5 / 切页面不丢对话。
     注意不要因为 busy 就跳过：AI 调用可能持续数秒，期间切页也必须保住已有内容。 */
  const syncRef = useRef(onChange);
  syncRef.current = onChange;
  useEffect(() => {
    syncRef.current?.({
      messages: state.messages,
      notes: state.notes,
      emotion: state.emotion,
      turn: state.turn,
      phase: state.phase,
      judgeCount: state.judgeCount,
      hopelessSeen: state.hopelessSeen,
      blindfold: state.blindfold,
      adjust: state.adjust,
      stageStart: state.stageStart,
      difficulty: state.difficulty,
    });
     
  }, [state.messages, state.notes, state.emotion, state.turn, state.phase,
      state.judgeCount, state.hopelessSeen, state.blindfold, state.adjust,
      state.stageStart, state.difficulty]);

  const seq = useRef(0);
  /** 并发闸门：真实值，不依赖 React 状态更新的时机 */
  const busyRef = useRef(false);
  const crisisRef = useRef(false);
  crisisRef.current = state.crisisBlocked;
  /** 消息 id 必须全局唯一：换页重挂载后 seq 会归零，光靠序号会撞 key */
  const nextId = useCallback((prefix = 'm') => {
    seq.current += 1;
    return `${prefix}_${Date.now().toString(36)}_${seq.current}`;
  }, []);

  /* ── 设置项 ───────────────────────────────────── */
  const setAiMode = useCallback((mode: AiMode) => {
    setState((s) => ({ ...s, aiMode: mode }));
    try {
      const raw = localStorage.getItem('knock.settings');
      const cur = raw ? JSON.parse(raw) : {};
      localStorage.setItem('knock.settings', JSON.stringify({ ...cur, ai_mode: mode }));
    } catch { /* 忽略 */ }
  }, []);

  const setDifficulty = useCallback((d: Difficulty) => {
    setState((s) => ({ ...s, difficulty: d }));
  }, []);

  const acknowledgeCrisis = useCallback(() => {
    setState((s) => ({ ...s, crisisBlocked: false }));
  }, []);

  /* ── 发送一句话 ───────────────────────────────── */
  const send = useCallback(
    async (input: string) => {
      const text = input.trim();
      if (!text) return;

      // ★ 用 ref 做并发闸门：setState 的 updater 是渲染期才执行的，
      //   把判断写在 updater 里再同步读，值是旧的，等于没有闸门。
      if (busyRef.current || crisisRef.current) return;
      busyRef.current = true;
      setState((s) => ({ ...s, busy: true }));

      try {

      const sc = getScenario(scenarioId);
      if (!sc) {
        // 场景被删（例如在剧本编辑器里删掉自定义角色）——必须复位 busy，否则界面锁死
        busyRef.current = false;
        setState((s) => ({
          ...s,
          busy: false,
          messages: [
            ...s.messages,
            {
              id: nextId('sys'),
              speaker: 'system',
              text: '找不到该服务对象的剧本，可能是自定义角色已被删除。请回到「服务对象」重新选择。',
              fromScriptLibrary: true,
              createdAt: Date.now(),
            },
          ],
        }));
        return;
      }

      /* ① 本地规则判定 —— 永远先跑，成本为 0，延迟为 0 */
      let m: MatchResult = matchLocalRules(text);
      let aiNote = '';
      let aiModel = '';
      let aiMs = 0;
      let aiUsed = false;

      const ready = aiStatus().ready;
      const mode = state.aiMode;

      /* ② 规则没把握 → 让模型补判意图（危机永不走这条路） */
      if (m.shouldCallAI && mode !== 'rule' && ready && m.riskLevel !== 'suicidal') {
        const r = await classifyIntent(
          {
            input: text,
            stage: (sc.archetype as never) || 'explore',
            name: sc.name,
            age: sc.age,
            identity: sc.archetype,
            brief: sc.brief,
            ruleHint: m.intent,
          },
          m.intent,
        );
        if (r.usedAI) {
          // 规则层「真判过」= 有分值或有情绪变化；两者都空说明它只是占位判了个共情
          const ruleActuallyJudged =
            Object.keys(m.effects.scoreDeltas || {}).length > 0 || m.effects.emotionDelta !== 0;

          if (r.intent !== m.intent || !ruleActuallyJudged) {
            m = {
              ...m,
              intent: r.intent,
              // ★ 关键：AI 改判后必须同时换上该意图的分值口径，
              //   否则 AI 判出的「评判」既不加分也不扣分，规则层和 AI 层两套账
              effects: effectsForIntent(r.intent),
            };
            aiUsed = true;
            aiModel = r.model || '';
            aiNote = ruleActuallyJudged
              ? `意图由模型改判为「${r.intent}」`
              : `规则未覆盖，由模型判为「${r.intent}」`;
          } else if (r.failReason) {
            aiNote = `模型补判失败：${r.failReason}；已用规则初判「${m.intent}」`;
          }
        } else if (r.failReason) {
          aiNote = `模型补判失败：${r.failReason}；规则未覆盖该句，本条不计分`;
        }
      }

      /* ③ 危机闸门 —— 本地硬规则判定，先于任何模型与计分 */
      const isCrisis = m.riskLevel === 'suicidal' || m.intent === '危机';
      if (isCrisis) {
        busyRef.current = false;
        crisisRef.current = true;
        setState((s) => ({
          ...s,
          busy: false,
          crisisBlocked: true,
          aiLast: { model: aiModel, ms: aiMs, used: aiUsed, note: '危机级内容不送入模型' },
          messages: [
            ...s.messages,
            {
              id: nextId('w'),
              speaker: 'worker',
              text,
              fromScriptLibrary: true,
              isCrisis: true,
              createdAt: Date.now(),
            },
            {
              id: nextId('sys'),
              speaker: 'system',
              text: '危机级 · 本轮不计分，训练已暂停。请按下方处置流程核实安全情况，处理后点「我知道了」继续。',
              fromScriptLibrary: true,
              isCrisis: true,
              createdAt: Date.now(),
            },
          ],
        }));
        return;
      }

      /* ④ 情绪与分值 */
      const emotion = clampEmotion(state.emotion + (m.effects.emotionDelta || 0));
      const adjust = { ...state.adjust };
      for (const [k, v] of Object.entries(m.effects.scoreDeltas || {}) as [DimensionKey, number][]) {
        adjust[k] = (adjust[k] || 0) + (v ?? 0);
      }
      const judgeCount =
        state.judgeCount + (m.intent === '评判' || m.intent === '建议过早' ? 1 : 0);
      const hopelessSeen = state.hopelessSeen || m.riskLevel === 'hopelessness';
      const turn = state.turn + 1;

      /* ⑤ 台词：AI 模式直接由模型生成（不再受预置台词/防御台词限制）；
             规则模式与混合模式走预置台词库，零延迟。失败一律回落到预置库。 */
      const ruleReply = generateReply(sc, state.turn, emotion, text, m, {
        stage: stageOfPhase(state.phase, state.turn),
      });
      let replyText = ruleReply.text;
      let fromScript = true;
      let defense = ruleReply.hasDefense;

      if (mode === 'ai' && ready) {
        const p = PERSONAS.find((x) => x.id === scenarioId);
        if (p) {
          const band = emotion < 30 ? 'low' : emotion < 70 ? 'mid' : 'high';
          const history = [...state.messages, { speaker: 'worker', text } as ChatMessage]
            .filter((x) => x.speaker !== 'system')
            .map((x) => ({
              role: x.speaker === 'worker' ? ('worker' as const) : ('client' as const),
              text: x.text,
            }));
          // 角色自己最近说过的话，交给模型避免重复
          const saidLines = state.messages
            .filter((x) => x.speaker === 'client')
            .map((x) => x.text)
            .slice(-6);

          const r = await aiActAsPersona({
            systemPrompt: p.systemPrompt,
            forbidden: p.forbidden,
            difficultyLabel: state.difficulty,
            difficultyRule: DIFFICULTY_RULES[state.difficulty],
            emotion,
            voiceByEmotion: p.voiceByEmotion[band],
            history,
            saidLines,
            phase: state.phase,
          });
          if (r.text) {
            replyText = r.text;
            fromScript = isScriptLine(r.text, scenarioId);
            defense = false;       // 模型写出来的话不是"防御台词"模板
            aiUsed = true;
            aiModel = r.model || aiModel;
            aiMs = r.ms || 0;
            aiNote = `台词由 ${r.model || 'GLM'} 按人设实时生成`;
          } else if (r.failReason) {
            aiNote = `模型扮演失败：${r.failReason}；已回落到预置台词`;
          }
        }
      }

      const workerMsg: ChatMessage = {
        id: nextId('w'),
        speaker: 'worker',
        text,
        fromScriptLibrary: true,
        createdAt: Date.now(),
      };
      const clientMsg: ChatMessage = {
        id: nextId('c'),
        speaker: 'client',
        text: replyText,
        fromScriptLibrary: fromScript,
        isDefense: defense,
        createdAt: Date.now(),
      };
      const note: MarginNote = {
        index: String(state.notes.length + 1).padStart(2, '0'),
        speaker: 'worker',
        utterance: text,
        response: replyText,
        dimension: INTENT_TO_DIMENSION[m.intent],
        delta: Object.values(m.effects.scoreDeltas || {}).reduce((a, b) => a + (b ?? 0), 0),
        ruleNote: m.effects.note,
        source: m.effects.source,
        marks: buildMarks(text, m.intent, m.hitWords || []),
      };

      busyRef.current = false;
      setState((s) => ({
        ...s,
        busy: false,
        emotion,
        adjust,
        judgeCount,
        hopelessSeen,
        turn,
        messages: [...s.messages, workerMsg, clientMsg],
        notes: [...s.notes, note],
        aiLast: {
          model: aiModel,
          ms: aiMs,
          used: aiUsed,
          note: aiNote || (
            mode === 'rule'
              ? '规则模式：台词来自预置库'
              : mode === 'ai' && !ready
                ? '未连通 AI 服务，已回落到预置台词'
                : '预置台词库命中'
          ),
        },
      }));
    } catch (err) {
      /* ★ 兜底：任何未预料的异常都不能让界面卡在"正在输入"。
         以前缺少这一段，只要 AI 链路里抛出一次未捕获异常，
         busy 就永远是 true，之后所有发送都会被并发闸门静默拦掉。 */
      busyRef.current = false;
      const reason = err instanceof Error ? err.message : String(err);
      setState((s) => ({
        ...s,
        busy: false,
        aiLast: { model: '', ms: 0, used: false, note: `本轮处理失败：${reason}` },
        messages: [
          ...s.messages,
          {
            id: nextId('sys'),
            speaker: 'system',
            text: `本轮处理失败（${reason}），请再试一次。`,
            fromScriptLibrary: true,
            createdAt: Date.now(),
          },
        ],
      }));
    } finally {
      // 双保险：无论走哪条 return 路径，闸门都要打开
      busyRef.current = false;
    }
    },
    [scenarioId, state.aiMode, state.emotion, state.adjust, state.judgeCount,
      state.hopelessSeen, state.turn, state.messages, state.notes, state.difficulty, nextId],
  );

  /* ── 提交本阶段：写快照并推进到下一阶段 ───────────── */
  const advancePhase = useCallback(() => {
    setState((s) => {
      if (s.phase >= 3) return s;
      return {
        ...s,
        phase: (s.phase + 1) as 1 | 2 | 3,
        // 新阶段从当前对话末尾起算，评分只看本阶段的发言
        stageStart: s.messages.length,
        notes: [],
        adjust: zeroAdjust(),
        turn: 1,
        judgeCount: 0,
      };
    });
  }, []);

  const reset = useCallback(() => {
    setState(initial(scenarioId, nickname));
  }, [scenarioId, nickname]);

  return {
    state,
    setState,
    send,
    reset,
    advancePhase,
    acknowledgeCrisis,
    setAiMode,
    setDifficulty,
  };
}

/** 供页面订阅 AI 状态变化（顶栏徽标 / 训练页模式条 / 设置页） */
export function useAiStatus(): AiStatus {
  const [s, setS] = useState<AiStatus>(() => aiStatus());
  useEffect(() => onAiStatus(setS), []);
  return s;
}
