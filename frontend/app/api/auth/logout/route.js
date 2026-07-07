import { NextResponse } from "next/server";
import { getSession } from "@/lib/auth";

export async function POST() {
  try {
    const session = await getSession();
    session.destroy();

    return NextResponse.json({ ok: true }, { status: 200 });
  } catch (error) {
    console.error("Logout error:", error);
    return NextResponse.json(
      { error: "INTERNAL_ERROR", message: "Logout failed" },
      { status: 500 }
    );
  }
}
