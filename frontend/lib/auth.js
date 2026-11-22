import { getIronSession } from "iron-session";

export async function getSession() {
  const password = process.env.SESSION_PASSWORD;
  if (!password || password.length < 32) {
    throw new Error("SESSION_PASSWORD must contain at least 32 characters");
  }

  const { cookies } = await import("next/headers");
  return getIronSession(await cookies(), {
    password,
    cookieName: "agent_session",
    cookieOptions: {
      httpOnly: true,
      secure: process.env.NODE_ENV === "production",
      sameSite: "strict",
      maxAge: 60 * 60 * 24 * 7,
    },
  });
}
