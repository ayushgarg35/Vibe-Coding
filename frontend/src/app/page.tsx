import Link from "next/link";

export default function LandingPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6">
      <div className="max-w-2xl w-full text-center space-y-8">
        <div className="space-y-3">
          <h1 className="text-4xl font-bold tracking-tight text-white">
            Agentic PM System
          </h1>
          <p className="text-lg text-gray-400">
            Interactive, stage-gated product management.
            <br />
            From idea to developer handoff — with human approval at every step.
          </p>
        </div>

        <div className="grid grid-cols-3 gap-4 text-sm text-gray-500">
          {[
            ["Discover", "Interactive intake that asks the right questions"],
            ["Generate", "BRD → PRD → FRD → Stories → Handoff"],
            ["Review", "PO-quality review at every artifact gate"],
          ].map(([title, desc]) => (
            <div key={title} className="p-4 rounded-lg border border-gray-800 text-left">
              <div className="font-medium text-gray-300 mb-1">{title}</div>
              <div>{desc}</div>
            </div>
          ))}
        </div>

        <div className="flex gap-4 justify-center">
          <Link
            href="/dashboard"
            className="px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white font-medium rounded-lg transition-colors"
          >
            Open Dashboard
          </Link>
          <Link
            href="/sessions/new"
            className="px-6 py-3 border border-gray-700 hover:border-gray-500 text-gray-300 font-medium rounded-lg transition-colors"
          >
            New Session
          </Link>
        </div>
      </div>
    </main>
  );
}
