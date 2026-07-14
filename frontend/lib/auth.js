import { getIronSession } from "iron-session";

// ---------------------------------------------------------------------------
// iron-session configuration
// Cookie: HttpOnly, Secure (prod), SameSite=Strict, 7-day expiry
// ---------------------------------------------------------------------------

export const sessionOptions = {
  password: (process.env.SESSION_PASSWORD && process.env.SESSION_PASSWORD.length >= 32)
    ? process.env.SESSION_PASSWORD
    : "default_fallback_session_password_32_chars_long",
  cookieName: "agent_session",
  cookieOptions: {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    maxAge: 60 * 60 * 24 * 7, // 7 days in seconds
  },
};

// ---------------------------------------------------------------------------
// getSession — works with Next.js App Router (cookies() API)
// Usage in route handlers:
//   import { getSession } from "@/lib/auth";
//   const session = await getSession();
// ---------------------------------------------------------------------------

export async function getSession() {
  const { cookies } = await import("next/headers");
  const cookieStore = await cookies();
  return getIronSession(cookieStore, sessionOptions);
}
