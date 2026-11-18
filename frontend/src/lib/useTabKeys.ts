/**
 * 标签页键盘导航
 *
 * WAI-ARIA 的 tabs 模式要求：Tab 键进入一次后，用左右方向键在标签间移动，
 * Home/End 跳到首尾。只做 role="tablist" 而不支持方向键，键盘用户会被卡住
 * （每个标签都是 tab stop，要按十几次 Tab 才能跳过整组）。
 *
 * 用法：
 *   const onKeyDown = useTabKeys(TABS, tab, setTab);
 *   <div role="tablist" onKeyDown={onKeyDown}>
 *     <button role="tab" id={`tab-${key}`} aria-controls={`panel-${key}`}
 *             tabIndex={active ? 0 : -1} aria-selected={active} … />
 *   </div>
 *   <div role="tabpanel" id={`panel-${key}`} aria-labelledby={`tab-${key}`}>…</div>
 */
import type { KeyboardEvent } from 'react';

export function useTabKeys<K extends string>(
  items: readonly { key: K }[],
  current: K,
  onChange: (key: K) => void,
): (e: KeyboardEvent<HTMLElement>) => void {
  return (e) => {
    const index = items.findIndex((i) => i.key === current);
    if (index < 0) return;

    let next = -1;
    switch (e.key) {
      case 'ArrowRight':
        next = (index + 1) % items.length;
        break;
      case 'ArrowLeft':
        next = (index - 1 + items.length) % items.length;
        break;
      case 'Home':
        next = 0;
        break;
      case 'End':
        next = items.length - 1;
        break;
      default:
        return;
    }

    e.preventDefault();
    const target = items[next].key;
    onChange(target);
    // 焦点跟随选中项，否则焦点留在旧标签上，读屏会念错
    document.getElementById(`tab-${target}`)?.focus();
  };
}
