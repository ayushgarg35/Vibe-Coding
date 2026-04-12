/**
 * Clerk auth middleware — protects all app routes.
 * In dev mode without a Clerk key, all routes are public (no auth).
 */
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const DEV_NO_AUTH =
  process.env.NODE_ENV === "development" &&
  !process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY?.startsWith("pk_");

// When Clerk key is present, use Clerk middleware
async function clerkAuth(req: NextRequest) {
  const { clerkMiddleware, createRouteMatcher } = await import(
    "@clerk/nextjs/server"
  );
  const isPublicRoute = createRouteMatcher(["/", "/sign-in(.*)", "/sign-up(.*)"]);
  return clerkMiddleware((auth, request) => {
    if (!isPublicRoute(request)) auth().protect();
  })(req, {} as any);
}

export default async function middleware(req: NextRequest) {
  if (DEV_NO_AUTH) return NextResponse.next();
  return clerkAuth(req);
}

export const config = {
  matcher: [
    "/((?!_next|[^?]*\\.(?:html?|css|js(?!on)|jpe?g|webp|png|gif|svg|ttf|woff2?|ico|csv|docx?|xlsx?|zip|webmanifest)).*)",
    "/(api|trpc)(.*)",
  ],
};
