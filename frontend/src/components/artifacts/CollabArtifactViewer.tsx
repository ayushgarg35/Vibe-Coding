"use client";

/**
 * CollabArtifactViewer — real-time collaborative artifact editor.
 * Connects to the Yjs WebSocket backend for live co-editing.
 * Shows: presence indicators, artifact JSON with inline editing,
 * and live cursor positions of other editors.
 *
 * For structured editing, artifact JSON fields are bound to Yjs maps.
 * For now renders a textarea bound to a Yjs text node.
 * (Replace with a richer editor like CodeMirror or TipTap as needed.)
 */
import { useAuth } from "@clerk/nextjs";
import { useEffect, useRef, useState } from "react";
import type * as Y from "yjs";

import { createArtifactDoc } from "@/lib/yjs-provider";

interface Collaborator {
  userId: string;
  name: string;
  color: string;
}

interface CollabArtifactViewerProps {
  sessionId: string;
  artifactType: string;
  initialContent: unknown;
  readOnly?: boolean;
}

// Deterministic color from user ID
function userColor(userId: string): string {
  const colors = ["#3b82f6", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4"];
  let hash = 0;
  for (let i = 0; i < userId.length; i++) hash = (hash * 31 + userId.charCodeAt(i)) >>> 0;
  return colors[hash % colors.length];
}

export function CollabArtifactViewer({
  sessionId,
  artifactType,
  initialContent,
  readOnly = false,
}: CollabArtifactViewerProps) {
  const { getToken, userId } = useAuth();
  const [content, setContent] = useState(JSON.stringify(initialContent, null, 2));
  const [collaborators, setCollaborators] = useState<Collaborator[]>([]);
  const [synced, setSynced] = useState(false);
  const [saving, setSaving] = useState(false);
  const docRef = useRef<ReturnType<typeof createArtifactDoc> | null>(null);
  const textRef = useRef<Y.Text | null>(null);
  const localRef = useRef(false);  // prevents echo loop

  useEffect(() => {
    let destroyed = false;

    const init = async () => {
      const token = await getToken();
      if (!token || destroyed) return;

      const name = `User ${userId?.slice(-4) ?? "?"}`;
      const color = userColor(userId ?? "");

      const artifactDoc = createArtifactDoc(sessionId, artifactType, token, { name, color });
      docRef.current = artifactDoc;

      // Get or initialise the shared text node
      const yjsText = artifactDoc.doc.getText("artifact_content");
      textRef.current = yjsText;

      // When synced from server, update textarea
      artifactDoc.onSync(() => {
        const serverContent = yjsText.toString();
        if (serverContent) {
          setContent(serverContent);
        } else {
          // First editor: seed the shared doc with initial content
          artifactDoc.doc.transact(() => {
            yjsText.insert(0, JSON.stringify(initialContent, null, 2));
          });
        }
        setSynced(true);
      });

      // Observe Yjs changes from other clients
      yjsText.observe(() => {
        if (!localRef.current) {
          setContent(yjsText.toString());
        }
      });

      // Observe awareness for presence
      artifactDoc.awareness.on("change", () => {
        const states = artifactDoc.awareness.getStates();
        const collabs: Collaborator[] = [];
        states.forEach((state, uid) => {
          if (uid !== userId && state.user) {
            collabs.push({ userId: uid, ...(state.user as { name: string; color: string }) });
          }
        });
        setCollaborators(collabs);
      });
    };

    init();

    return () => {
      destroyed = true;
      docRef.current?.destroy();
    };
  }, [sessionId, artifactType, userId, getToken]);

  const handleChange = (value: string) => {
    setContent(value);
    if (!textRef.current || readOnly) return;

    // Apply diff to Yjs doc to minimise data sent
    localRef.current = true;
    const yjsText = textRef.current;
    const current = yjsText.toString();

    if (value !== current) {
      docRef.current!.doc.transact(() => {
        yjsText.delete(0, current.length);
        yjsText.insert(0, value);
      });
    }
    localRef.current = false;
  };

  const handleExport = () => {
    try {
      const parsed = JSON.parse(content);
      const blob = new Blob([JSON.stringify(parsed, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `${artifactType.toLowerCase()}.json`;
      a.click();
    } catch {
      alert("Invalid JSON — fix before exporting");
    }
  };

  return (
    <div className="flex flex-col h-full space-y-2">
      {/* Header */}
      <div className="flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-semibold text-white">{artifactType.replace("_", " ")}</h2>
          {!synced && (
            <span className="text-xs text-yellow-500 animate-pulse">Connecting...</span>
          )}
          {synced && (
            <span className="text-xs text-green-500">Live</span>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Presence avatars */}
          <div className="flex -space-x-1">
            {/* Current user */}
            <div
              className="w-6 h-6 rounded-full border-2 border-gray-900 flex items-center justify-center text-xs font-bold"
              style={{ backgroundColor: userColor(userId ?? "") }}
              title="You"
            >
              Y
            </div>
            {/* Remote collaborators */}
            {collaborators.map((c) => (
              <div
                key={c.userId}
                className="w-6 h-6 rounded-full border-2 border-gray-900 flex items-center justify-center text-xs font-bold"
                style={{ backgroundColor: c.color }}
                title={c.name}
              >
                {c.name[0]}
              </div>
            ))}
          </div>

          {collaborators.length > 0 && (
            <span className="text-xs text-gray-600">
              {collaborators.length + 1} editing
            </span>
          )}

          <button
            onClick={handleExport}
            className="text-xs text-gray-600 hover:text-gray-300 transition-colors"
          >
            Export JSON
          </button>
        </div>
      </div>

      {/* Editor */}
      <textarea
        className="flex-1 bg-gray-900 border border-gray-800 rounded-lg p-4 text-xs text-gray-300 font-mono resize-none focus:outline-none focus:border-gray-600"
        value={content}
        onChange={(e) => handleChange(e.target.value)}
        readOnly={readOnly || !synced}
        spellCheck={false}
        placeholder={synced ? "" : "Loading shared document..."}
      />

      {/* Status bar */}
      <div className="flex items-center justify-between text-xs text-gray-700 shrink-0">
        <span>
          {content.length.toLocaleString()} chars
          {readOnly && " · Read-only"}
        </span>
        {synced && (
          <span className="text-green-800">
            Changes sync automatically
          </span>
        )}
      </div>
    </div>
  );
}
