import { NextResponse } from "next/server";
import { z } from "zod";
import bcrypt from "bcryptjs";
import { getSession } from "@/lib/auth";
import { createUser, getUserByEmail } from "@/lib/db";

const registerSchema = z.object({
  email: z.string().email("Invalid email address"),
  password: z.string().min(8, "Password must be at least 8 characters"),
});

export async function POST(request) {
  try {
    const body = await request.json();
    const parsed = registerSchema.safeParse(body);

    if (!parsed.success) {
      return NextResponse.json(
        { error: "VALIDATION_ERROR", details: parsed.error.flatten().fieldErrors },
        { status: 400 }
      );
    }

    const { email, password } = parsed.data;

    // Check if email already exists
    const existing = getUserByEmail(email);
    if (existing) {
      return NextResponse.json(
        { error: "EMAIL_EXISTS", message: "An account with this email already exists" },
        { status: 409 }
      );
    }

    // Hash password (bcrypt, 10 salt rounds)
    const passwordHash = await bcrypt.hash(password, 10);

    // Create user
    const user = createUser(email, passwordHash);

    // Set session cookie
    const session = await getSession();
    session.userId = user.id;
    session.email = user.email;
    await session.save();

    return NextResponse.json(
      { id: user.id, email: user.email },
      { status: 201 }
    );
  } catch (error) {
    console.error("Register error:", error);
    return NextResponse.json(
      { error: "INTERNAL_ERROR", message: "Registration failed" },
      { status: 500 }
    );
  }
}
