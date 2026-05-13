export function useWebSocket() {
  return {
    connected: false,
    send: (_message: unknown) => undefined,
    lastMessage: null as unknown,
  };
}

