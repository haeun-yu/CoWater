"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export default class AppErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error("[frontend] unhandled render error", error, errorInfo);
  }

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div className="flex h-full min-h-[320px] items-center justify-center bg-ocean-950 px-6">
        <div className="max-w-md rounded-lg border border-red-500/30 bg-ocean-900/90 p-5 text-sm text-ocean-200 shadow-xl">
          <div className="mb-2 text-base font-semibold text-red-300">화면 오류가 발생했습니다.</div>
          <p className="mb-4 text-ocean-300">
            데이터를 계속 수신 중일 수 있지만 현재 화면 일부를 렌더링하지 못했습니다.
            새로고침 후 다시 확인해주세요.
          </p>
          <button
            type="button"
            onClick={() => window.location.reload()}
            className="rounded bg-ocean-700 px-3 py-1.5 text-xs font-medium text-ocean-100 transition-colors hover:bg-ocean-600"
          >
            새로고침
          </button>
        </div>
      </div>
    );
  }
}
