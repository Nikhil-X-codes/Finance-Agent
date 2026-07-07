import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";

export async function GET() {
  try {
    const session = await getSession();

    if (!session.userId) {
      return NextResponse.json(
        { error: "UNAUTHORIZED", message: "Not logged in" },
        { status: 401 }
      );
    }

    return NextResponse.json(
      { userId: session.userId, email: session.email },
      { status: 200 }
    );
  } catch (error) {
    console.error("Session check error:", error);
    return NextResponse.json(
      { error: "INTERNAL_ERROR", message: "Session check failed" },
      { status: 500 }
    );
  }
}
