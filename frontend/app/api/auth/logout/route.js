import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";

export async function POST(req) {
  try {
    const session = await getSession();
    session.destroy();

    return NextResponse.redirect(new URL("/login", req.url));
  } catch (error) {
    console.error("Logout error:", error);
    return NextResponse.json(
      { error: "INTERNAL_ERROR", message: "Logout failed" },
      { status: 500 }
    );
  }
}
