"use client";

import { useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription, CardFooter } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

export default function GlobalError({ error, reset }) {
  useEffect(() => {
    // Log error to an reporting service if needed
    console.error("Application crashed:", error);
  }, [error]);

  return (
    <main className="min-h-screen bg-slate-950 flex items-center justify-center p-6 text-slate-50">
      <div className="w-full max-w-md">
        <Card className="border-red-950 bg-red-950/10 shadow-2xl text-center space-y-4 p-4">
          <CardHeader className="space-y-2">
            <div className="mx-auto h-12 w-12 rounded-full bg-red-500/10 flex items-center justify-center text-red-500 text-xl font-bold">
              !
            </div>
            <CardTitle className="text-xl font-bold text-red-400">
              Something went wrong
            </CardTitle>
            <CardDescription className="text-slate-400">
              An unexpected error occurred during application rendering.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="rounded-lg bg-slate-950 p-3 text-left font-mono text-xs text-red-400 overflow-x-auto max-h-32 border border-slate-900">
              {error?.message || "Unknown rendering exception"}
            </div>
          </CardContent>
          <CardFooter className="flex justify-center gap-3">
            <Button variant="outline" className="border-slate-800 hover:bg-slate-900" onClick={() => window.location.reload()}>
              Reload Window
            </Button>
            <Button className="bg-red-600 hover:bg-red-500 text-slate-50 font-medium" onClick={() => reset()}>
              Try Again
            </Button>
          </CardFooter>
        </Card>
      </div>
    </main>
  );
}
