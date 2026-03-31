"use client";

/**
 * PresenceIndicator — shows how many users are actively editing an artifact.
 * Polls the /api/v1/collab/{sessionId}/{artifactType}/presence endpoint.
 */
import useSWR from "swr";

interface PresenceIndicatorProps {
  sessionId: string;
  artifactType: string;
  token: string;
}

async function fetchPresence(url: string, token: string) {
  const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!res.ok) return { active_editors: 0 };
  return res.json();
}

export function PresenceIndicator({ sessionId, artifactType, token }: PresenceIndicatorProps) {
  const { data } = useSWR(
    [`/api/v1/collab/${sessionId}/${artifactType}/presence`, token],
    ([url, t]) => fetchPresence(url, t),
    { refreshInterval: 10_000 }  // poll every 10s
  );

  const count = data?.active_editors ?? 0;
  if (count === 0) return null;

  return (
    <div className="flex items-center gap-1.5">
      <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />
      <span className="text-xs text-green-400 font-medium">
        {count} editing live
      </span>
    </div>
  );
}
