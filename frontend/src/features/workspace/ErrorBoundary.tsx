import { Component, type ReactNode } from "react";

interface Props {
  title: string;
  children: ReactNode;
  /** Changing this value clears a previous error (e.g. the route). */
  resetKey?: string;
}

/** A screen that throws while rendering shows its message instead of blanking the whole workspace. */
export class ErrorBoundary extends Component<Props, { error: Error | null; key?: string }> {
  state: { error: Error | null; key?: string } = { error: null, key: this.props.resetKey };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  static getDerivedStateFromProps(props: Props, state: { error: Error | null; key?: string }) {
    return props.resetKey !== state.key ? { error: null, key: props.resetKey } : null;
  }

  render() {
    if (this.state.error) {
      return (
        <>
          <div className="head"><div><h1>{this.props.title}</h1></div></div>
          <div className="empty"><p>{this.state.error.message}</p></div>
        </>
      );
    }
    return this.props.children;
  }
}
