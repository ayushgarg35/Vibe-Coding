/**
 * Yjs WebSocket provider — connects a Yjs document to the backend collab server.
 * Each artifact in a session gets its own Yjs document.
 *
 * Usage:
 *   const { doc, provider, awareness, destroy } = createArtifactDoc(sessionId, artifactType, token)
 *   // bind doc.getText("content") to a CodeMirror / ProseMirror / Monaco editor
 *   // destroy() on component unmount
 */
import * as Y from "yjs";

const WS_BASE = process.env.NEXT_PUBLIC_WS_URL || "ws://localhost:8000";

export interface ArtifactDoc {
  doc: Y.Doc;
  awareness: AwarenessState;
  destroy: () => void;
  onSync: (cb: () => void) => void;
}

export interface AwarenessState {
  getLocalState: () => Record<string, unknown>;
  setLocalState: (state: Record<string, unknown>) => void;
  getStates: () => Map<string, Record<string, unknown>>;
  on: (event: string, cb: (...args: unknown[]) => void) => void;
  off: (event: string, cb: (...args: unknown[]) => void) => void;
}

class SimpleAwareness implements AwarenessState {
  private _local: Record<string, unknown> = {};
  private _states: Map<string, Record<string, unknown>> = new Map();
  private _listeners: Map<string, Set<(...args: unknown[]) => void>> = new Map();

  getLocalState() { return this._local; }
  setLocalState(state: Record<string, unknown>) {
    this._local = state;
    this._emit("change", [state]);
  }
  getStates() { return this._states; }
  updateRemote(userId: string, state: Record<string, unknown>) {
    this._states.set(userId, state);
    this._emit("change", [state]);
  }
  on(event: string, cb: (...args: unknown[]) => void) {
    if (!this._listeners.has(event)) this._listeners.set(event, new Set());
    this._listeners.get(event)!.add(cb);
  }
  off(event: string, cb: (...args: unknown[]) => void) {
    this._listeners.get(event)?.delete(cb);
  }
  private _emit(event: string, args: unknown[]) {
    this._listeners.get(event)?.forEach(cb => cb(...args));
  }
}


export function createArtifactDoc(
  sessionId: string,
  artifactType: string,
  token: string,
  userMeta?: { name: string; color: string },
): ArtifactDoc {
  const doc = new Y.Doc();
  const awareness = new SimpleAwareness();
  const url = `${WS_BASE}/api/v1/collab/${sessionId}/${artifactType}?token=${encodeURIComponent(token)}`;

  let ws: WebSocket | null = null;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let destroyed = false;
  const syncCallbacks: Array<() => void> = [];
  let synced = false;

  function connect() {
    if (destroyed) return;
    ws = new WebSocket(url);
    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      // Send Yjs sync step 1 — our current state vector
      const sv = Y.encodeStateVector(doc);
      ws!.send(sv);

      // Set local awareness state
      if (userMeta) {
        awareness.setLocalState({ user: userMeta, cursor: null });
        ws!.send(JSON.stringify({ type: "awareness", state: awareness.getLocalState() }));
      }
    };

    ws.onmessage = (event) => {
      if (event.data instanceof ArrayBuffer) {
        // Binary Yjs update — apply to local document
        const update = new Uint8Array(event.data);
        Y.applyUpdate(doc, update);
        if (!synced) {
          synced = true;
          syncCallbacks.forEach(cb => cb());
        }
      } else if (typeof event.data === "string") {
        // Text awareness update
        try {
          const msg = JSON.parse(event.data);
          if (msg.type === "awareness" && msg.user_id && msg.state) {
            awareness.updateRemote(msg.user_id, msg.state);
          }
        } catch { /* ignore malformed messages */ }
      }
    };

    ws.onclose = () => {
      if (!destroyed) {
        // Reconnect with exponential backoff (max 10s)
        const delay = Math.min(1000 * Math.pow(2, reconnectAttempts++), 10000);
        reconnectTimer = setTimeout(connect, delay);
      }
    };

    ws.onerror = () => ws?.close();
  }

  // Propagate local Yjs updates to the server
  doc.on("update", (update: Uint8Array) => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(update);
    }
  });

  // Propagate local awareness changes to the server
  awareness.on("change", () => {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "awareness", state: awareness.getLocalState() }));
    }
  });

  let reconnectAttempts = 0;
  connect();

  return {
    doc,
    awareness,
    destroy() {
      destroyed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
      doc.destroy();
    },
    onSync(cb: () => void) {
      if (synced) cb();
      else syncCallbacks.push(cb);
    },
  };
}
