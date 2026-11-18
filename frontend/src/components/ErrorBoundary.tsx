/**
 * 错误边界
 *
 * 没有它的后果很直接：任何组件在渲染期抛异常，React 会卸载整棵树，
 * 用户看到一片空白且不知道发生了什么，只能刷新。
 *
 * 这里做三件事：
 * 1. 捕获渲染异常，显示可读的错误页而不是白屏；
 * 2. 提供「重试」与「回首页」两个出口；
 * 3. 把错误信息与组件栈打到控制台，便于排查（生产环境不展示给用户）。
 *
 * 注意：ErrorBoundary 只能捕获**渲染期**错误，事件处理器与异步代码里的
 * 异常需各自 try/catch —— 本项目在 authClient 与各页面已分别处理。
 */
import { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
  /** 出错时的兜底 UI 可自定义；不传则用默认样式 */
  fallback?: (error: Error, reset: () => void) => ReactNode;
}

interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // 保留组件栈，排查时能定位到具体组件
    // eslint-disable-next-line no-console
    console.error('[ErrorBoundary] 渲染异常', error, info.componentStack);
  }

  private reset = (): void => {
    this.setState({ error: null });
  };

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    if (this.props.fallback) return this.props.fallback(error, this.reset);

    return (
      <div className="screen is-on">
        <div className="wb-frame" style={{ padding: '64px 0' }}>
          <div className="wb-empty">
            <b>页面出了点问题</b>
            <p style={{ margin: '10px 0 6px' }}>
              这一页在渲染时遇到异常，已停止显示以免继续出错。
              你可以重试，或者回到首页重新进入。
            </p>
            <p
              style={{
                fontFamily: 'var(--mono)', fontSize: 11, letterSpacing: '.06em',
                color: 'var(--ink-4)', margin: '0 0 22px',
                wordBreak: 'break-word', maxWidth: '60ch', marginInline: 'auto',
              }}
            >
              {error.message}
            </p>
            <div style={{ display: 'flex', gap: 10, justifyContent: 'center',
              flexWrap: 'wrap' }}>
              <button className="btn-primary" type="button" onClick={this.reset}>
                重试这一页
              </button>
              <button
                className="btn-ghost"
                type="button"
                onClick={() => {
                  // 回首页用整页跳转：hash 路由下 location.assign 会触发重挂载，
                  // 比 navigate 更能确保残留的错误状态被清掉
                  window.location.hash = '#/';
                  window.location.reload();
                }}
              >
                回首页
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }
}
