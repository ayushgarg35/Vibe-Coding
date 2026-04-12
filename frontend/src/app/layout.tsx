import type { Metadata } from "next";
import { Toaster } from "sonner";
import "./globals.css";

export const metadata: Metadata = {
  title: "Agentic PM System",
  description: "Interactive, model-agnostic product management agent system",
};

const hasClerk = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.startsWith("pk_");

async function MaybeClerkProvider({ children }: { children: React.ReactNode }) {
  if (!hasClerk) return <>{children}</>;
  const { ClerkProvider } = await import("@clerk/nextjs");
  return <ClerkProvider>{children}</ClerkProvider>;
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <MaybeClerkProvider>
      <html lang="en">
        <body className="bg-gray-950 text-gray-100 antialiased">
          {children}
          <Toaster position="bottom-right" theme="dark" richColors />
        </body>
      </html>
    </MaybeClerkProvider>
  );
}
