/**
 * WebSocket client for real-time session streaming.
 * Connects to the backend SSE/WS stream for a session.
 * Yjs provider is wired separately for collaborative editing.
 */

export type SSEEventType =
  | "connected"
  | "agent_start"
  | "agent_token"
  | "agent_complete"
  | "gate_reached"
  | "clarification_needed"
  | "error";

export interface SSEEvent {
  type: SSEEventType;
  session_id: string;
  agent?: string;
  token?: string;
  data?: unknown;
}

export function createSessionStream(
  sessionId: string,
  onEvent: (event: SSEEvent) => void,
  onError?: (error: Event) => void
): () => void {
  const url = `${process.env.NEXT_PUBLIC_API_URL}/api/v1/sessions/${sessionId}/stream`;
  const es = new EventSource(url);

  es.onmessage = (e) => {
    try {
      const event: SSEEvent = JSON.parse(e.data);
      onEvent(event);
    } catch {
      console.warn("Failed to parse SSE event", e.data);
    }
  };

  es.onerror = (e) => {
    onError?.(e);
    // Auto-reconnect handled by EventSource spec
  };

  // Return cleanup function
  return () => es.close();
}
