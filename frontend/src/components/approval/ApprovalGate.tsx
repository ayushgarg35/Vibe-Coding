"use client";

/**
 * ApprovalGate — the human checkpoint UI shown at each stage gate.
 * Displays: artifact under review, auto-generated PO review pack, and decision controls.
 * The user can: Approve / Request Revision / Reject, with inline comments.
 */
import { useState } from "react";
import { toast } from "sonner";
import type { ApprovalStatus, ReviewPack } from "@/types";

interface ApprovalGateProps {
  sessionId: string;
  gateNumber: number;
  gateTitle: string;
  reviewPack?: ReviewPack;
  onDecision: (status: ApprovalStatus, comments: string) => Promise<void>;
}

const VERDICT_STYLES = {
  GO: "text-green-400 bg-green-900/30 border-green-800",
  REVISE: "text-yellow-400 bg-yellow-900/30 border-yellow-800",
  HOLD: "text-red-400 bg-red-900/30 border-red-800",
};

const SEVERITY_STYLES = {
  blocker: "text-red-400",
  critical: "text-orange-400",
  major: "text-yellow-400",
  minor: "text-blue-400",
  suggestion: "text-gray-400",
};

export function ApprovalGate({
  sessionId,
  gateNumber,
  gateTitle,
  reviewPack,
  onDecision,
}: ApprovalGateProps) {
  const [comments, setComments] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const handleDecision = async (status: ApprovalStatus) => {
    setSubmitting(true);
    try {
      await onDecision(status, comments);
      toast.success(`Gate ${gateNumber}: ${status.replace("_", " ")}`);
    } catch (e) {
      toast.error("Failed to submit decision");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Gate header */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 rounded-full bg-yellow-900 border border-yellow-700 flex items-center justify-center text-yellow-300 text-sm font-bold">
          {gateNumber}
        </div>
        <div>
          <h2 className="text-lg font-semibold text-white">{gateTitle}</h2>
          <p className="text-sm text-gray-500">Human approval required before proceeding</p>
        </div>
      </div>

      {/* Auto review pack */}
      {reviewPack && (
        <div className="space-y-4">
          {/* Verdict */}
          <div className={`p-4 rounded-lg border ${VERDICT_STYLES[reviewPack.verdict]}`}>
            <div className="flex items-center justify-between">
              <div>
                <div className="font-bold text-lg">{reviewPack.verdict}</div>
                <div className="text-sm mt-0.5 opacity-80">{reviewPack.summary}</div>
              </div>
              <div className="text-right">
                <div className="text-3xl font-bold">{reviewPack.readiness_score}</div>
                <div className="text-xs opacity-60">/ 100</div>
              </div>
            </div>
          </div>

          {/* Blockers */}
          {reviewPack.blockers.length > 0 && (
            <div className="p-3 rounded-lg bg-red-900/20 border border-red-800">
              <div className="text-xs font-medium text-red-400 mb-2">BLOCKERS</div>
              {reviewPack.blockers.map((b) => (
                <div key={b} className="text-sm text-red-300">• {b}</div>
              ))}
            </div>
          )}

          {/* Issues */}
          {reviewPack.issues.length > 0 && (
            <div className="space-y-2">
              <div className="text-xs font-medium text-gray-500 uppercase">Issues ({reviewPack.issues.length})</div>
              {reviewPack.issues.map((issue) => (
                <div key={issue.id} className="p-3 rounded-lg bg-gray-900 border border-gray-800 text-sm">
                  <div className="flex items-center gap-2 mb-1">
                    <span className={`text-xs font-medium ${SEVERITY_STYLES[issue.severity]}`}>
                      {issue.severity.toUpperCase()}
                    </span>
                    <span className="text-gray-600">·</span>
                    <span className="text-gray-500">{issue.category}</span>
                    <span className="text-gray-600">·</span>
                    <span className="text-gray-600 text-xs">{issue.location}</span>
                  </div>
                  <div className="text-gray-300">{issue.description}</div>
                  <div className="text-gray-500 mt-1 text-xs">{issue.recommendation}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Human decision */}
      <div className="space-y-3 pt-4 border-t border-gray-800">
        <textarea
          className="w-full bg-gray-900 border border-gray-700 rounded-lg p-3 text-sm text-gray-200 placeholder-gray-600 resize-none focus:outline-none focus:border-gray-500"
          rows={3}
          placeholder="Add comments or redlines (optional)..."
          value={comments}
          onChange={(e) => setComments(e.target.value)}
        />
        <div className="flex gap-3">
          <button
            onClick={() => handleDecision("approved")}
            disabled={submitting}
            className="flex-1 py-2 bg-green-700 hover:bg-green-600 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            Approve
          </button>
          <button
            onClick={() => handleDecision("revision_requested")}
            disabled={submitting}
            className="flex-1 py-2 bg-yellow-700 hover:bg-yellow-600 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            Request Revision
          </button>
          <button
            onClick={() => handleDecision("rejected")}
            disabled={submitting}
            className="flex-1 py-2 bg-red-900 hover:bg-red-800 text-white text-sm font-medium rounded-lg transition-colors disabled:opacity-50"
          >
            Reject
          </button>
        </div>
      </div>
    </div>
  );
}
