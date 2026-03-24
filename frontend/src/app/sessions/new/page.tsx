"use client";

/**
 * New Session page — entry point for starting a product session.
 * Supports: freeform description, document upload (coming), template (coming).
 */
import { useAuth } from "@clerk/nextjs";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { toast } from "sonner";

import { sessions } from "@/lib/api";
import type { DataRegion } from "@/types";

const ENTRY_MODES = [
  { id: "freeform", label: "Describe your product", description: "Start with a free-form idea — the system will ask you the right questions" },
  { id: "upload", label: "Upload a document", description: "Upload an existing BRD, PRD, or spec — we'll review and extend it", disabled: true },
  { id: "template", label: "Use a template", description: "Start from a structured template for your product type", disabled: true },
] as const;

const REGIONS: { value: DataRegion; label: string }[] = [
  { value: "US", label: "United States (US)" },
  { value: "EU", label: "European Union (EU — GDPR)" },
  { value: "IN", label: "India (IN — DPDPA)" },
];

export default function NewSessionPage() {
  const { getToken } = useAuth();
  const router = useRouter();

  const [entryMode, setEntryMode] = useState<"freeform" | "upload" | "template">("freeform");
  const [description, setDescription] = useState("");
  const [region, setRegion] = useState<DataRegion>("US");
  const [loading, setLoading] = useState(false);

  const canSubmit = entryMode === "freeform" && description.trim().length > 10;

  const handleSubmit = async () => {
    const token = await getToken();
    if (!token) { toast.error("Not authenticated"); return; }

    setLoading(true);
    try {
      const session = await sessions.create(
        { product_description: description, entry_mode: entryMode },
        token,
        region
      );
      router.push(`/sessions/${session.session_id}`);
    } catch (e: unknown) {
      toast.error(e instanceof Error ? e.message : "Failed to create session");
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-start justify-center pt-20 px-6">
      <div className="w-full max-w-2xl space-y-8">
        <div>
          <h1 className="text-2xl font-bold text-white">New Session</h1>
          <p className="text-gray-500 mt-1 text-sm">
            The system will ask clarifying questions before generating any artifacts.
          </p>
        </div>

        {/* Entry mode */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-gray-400 uppercase tracking-wide">Start with</label>
          <div className="grid grid-cols-3 gap-3">
            {ENTRY_MODES.map((mode) => (
              <button
                key={mode.id}
                onClick={() => !mode.disabled && setEntryMode(mode.id as typeof entryMode)}
                disabled={mode.disabled}
                className={`p-3 rounded-lg border text-left transition-colors ${
                  entryMode === mode.id
                    ? "border-blue-500 bg-blue-950/30"
                    : mode.disabled
                    ? "border-gray-800 opacity-40 cursor-not-allowed"
                    : "border-gray-800 hover:border-gray-600"
                }`}
              >
                <div className="text-sm font-medium text-white">{mode.label}</div>
                <div className="text-xs text-gray-500 mt-1">{mode.description}</div>
                {mode.disabled && <div className="text-xs text-gray-700 mt-1">Coming soon</div>}
              </button>
            ))}
          </div>
        </div>

        {/* Product description */}
        {entryMode === "freeform" && (
          <div className="space-y-2">
            <label className="text-xs font-medium text-gray-400 uppercase tracking-wide">
              Product description
            </label>
            <textarea
              className="w-full h-36 bg-gray-900 border border-gray-700 rounded-lg p-4 text-sm text-gray-200 placeholder-gray-600 resize-none focus:outline-none focus:border-gray-500"
              placeholder={`Describe your product idea in as much or as little detail as you have.\n\nExample: "I want to build a leave management system for a 500-person company. Employees should be able to apply for leave, managers approve/reject, and HR should see reports."`}
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
            <div className="text-xs text-gray-600">
              {description.length} characters · The system will ask follow-up questions for anything unclear.
            </div>
          </div>
        )}

        {/* Data region */}
        <div className="space-y-2">
          <label className="text-xs font-medium text-gray-400 uppercase tracking-wide">
            Data region
          </label>
          <p className="text-xs text-gray-600">
            Determines which LLM providers are used and which compliance rules apply.
          </p>
          <div className="flex gap-3">
            {REGIONS.map((r) => (
              <button
                key={r.value}
                onClick={() => setRegion(r.value)}
                className={`flex-1 py-2 px-3 rounded-lg border text-sm transition-colors ${
                  region === r.value
                    ? "border-blue-500 bg-blue-950/30 text-white"
                    : "border-gray-800 text-gray-500 hover:border-gray-600"
                }`}
              >
                {r.label}
              </button>
            ))}
          </div>
        </div>

        {/* Submit */}
        <button
          onClick={handleSubmit}
          disabled={!canSubmit || loading}
          className="w-full py-3 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {loading ? "Starting session..." : "Start Session →"}
        </button>

        <p className="text-xs text-gray-700 text-center">
          The system will not generate any artifacts until you have reviewed and approved the scope.
        </p>
      </div>
    </div>
  );
}
