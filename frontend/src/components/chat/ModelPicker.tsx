"use client";

/**
 * ModelPicker — per-task inline model selector.
 * Shown next to each agent task card in the session view.
 * User can override the agent-selected model before or during execution.
 */
import { useState } from "react";
import type { ModelOption } from "@/types";

const TIER_COLORS: Record<string, string> = {
  strong: "text-purple-400",
  medium: "text-blue-400",
  fast: "text-green-400",
  local: "text-gray-400",
};

interface ModelPickerProps {
  taskType: string;
  currentModel: string;
  availableModels: ModelOption[];
  onSelect: (taskType: string, modelId: string) => void;
  dataRegion?: string;
}

export function ModelPicker({
  taskType,
  currentModel,
  availableModels,
  onSelect,
  dataRegion = "US",
}: ModelPickerProps) {
  const [open, setOpen] = useState(false);
  const selected = availableModels.find((m) => m.id === currentModel);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-300 transition-colors"
        title={`Model for ${taskType}. Click to change.`}
      >
        <span className="w-1.5 h-1.5 rounded-full bg-current" />
        <span className={selected ? TIER_COLORS[selected.tier] : "text-gray-500"}>
          {selected?.name || currentModel}
        </span>
        <span className="text-gray-700">▾</span>
      </button>

      {open && (
        <div className="absolute top-full left-0 mt-1 z-50 w-72 bg-gray-900 border border-gray-700 rounded-lg shadow-xl">
          <div className="p-2 border-b border-gray-800 text-xs text-gray-500">
            Select model for: <span className="text-gray-300">{taskType}</span>
          </div>
          <div className="p-1 space-y-0.5 max-h-64 overflow-y-auto">
            {availableModels.map((model) => (
              <button
                key={model.id}
                onClick={() => { onSelect(taskType, model.id); setOpen(false); }}
                className={`w-full text-left p-2 rounded text-xs hover:bg-gray-800 transition-colors ${
                  model.id === currentModel ? "bg-gray-800" : ""
                }`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-medium text-gray-200">{model.name}</span>
                  <span className={`${TIER_COLORS[model.tier]} text-gray-600`}>
                    {model.tier}
                  </span>
                </div>
                <div className="text-gray-600 mt-0.5">
                  {model.provider} · Best for: {model.best_for.slice(0, 2).join(", ")}
                </div>
                {dataRegion !== "US" && (
                  <div className="text-yellow-600 mt-0.5">
                    Check region compliance for {dataRegion}
                  </div>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
