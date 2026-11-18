/**
 * 通用确认对话框
 *
 * 管理端有若干不可逆操作（停用账号、删除技巧卡、下架案例、删除台词），
 * 这些一旦误触就要靠恢复流程，代价远高于多点一次确认。
 *
 * 用原生 <dialog> 而不是自己堆 div：自带焦点陷阱、ESC 关闭、
 * 背景 inert 语义，无障碍上少踩坑。
 */
import { useEffect, useRef } from 'react';

export interface ConfirmOptions {
  title: string;
  message: string;
  /** 确认按钮文案，默认「确认」 */
  confirmLabel?: string;
  /** 危险操作用红色，普通操作用主色 */
  danger?: boolean;
  onConfirm: () => void | Promise<void>;
}

export function ConfirmDialog({
  open,
  options,
  onClose,
}: {
  open: boolean;
  options: ConfirmOptions | null;
  onClose: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  if (!options) return null;

  return (
    <dialog
      ref={ref}
      onClose={onClose}
      onCancel={(e) => {
        e.preventDefault();
        onClose();
      }}
      style={{
        border: 'none',
        borderRadius: 10,
        padding: 0,
        maxWidth: 420,
        width: 'calc(100% - 32px)',
        boxShadow: '0 12px 40px rgba(0,0,0,.18)',
      }}
    >
      <div style={{ padding: '20px 22px 18px' }}>
        <h3 style={{ margin: '0 0 10px', fontSize: 16 }}>{options.title}</h3>
        <p style={{ margin: '0 0 20px', fontSize: 13.5, lineHeight: 1.7, color: '#5b5648' }}>
          {options.message}
        </p>
        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button className="btn-ghost" type="button" onClick={onClose}
            style={{ padding: '8px 18px', minHeight: 40 }}>
            取消
          </button>
          <button
            className="btn-primary"
            type="button"
            style={{
              padding: '8px 18px',
              minHeight: 40,
              background: options.danger ? '#b91c1c' : undefined,
              borderColor: options.danger ? '#b91c1c' : undefined,
            }}
            onClick={async () => {
              await options.onConfirm();
              onClose();
            }}
          >
            {options.confirmLabel ?? '确认'}
          </button>
        </div>
      </div>
    </dialog>
  );
}
