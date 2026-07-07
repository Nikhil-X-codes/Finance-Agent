"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";

const MAX_SIZE = 5 * 1024 * 1024; // 5MB

export default function UploadPage() {
  const router = useRouter();
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState(null);

  const onDrop = useCallback((acceptedFiles, rejectedFiles) => {
    setError(null);

    if (rejectedFiles.length > 0) {
      const rejection = rejectedFiles[0];
      if (rejection.errors.some((e) => e.code === "file-too-large")) {
        setError("File is too large. Maximum size is 5MB.");
      } else if (rejection.errors.some((e) => e.code === "file-invalid-type")) {
        setError("Only PDF files are accepted.");
      } else {
        setError("Invalid file. Please upload a PDF under 5MB.");
      }
      return;
    }

    if (acceptedFiles.length > 0) {
      setFile(acceptedFiles[0]);
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      "application/pdf": [".pdf"],
      "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": [".xlsx"],
      "application/vnd.ms-excel": [".xls"],
      "text/csv": [".csv"],
    },
    maxSize: MAX_SIZE,
    maxFiles: 1,
    multiple: false,
  });

  const handleUpload = async () => {
    if (!file) return;

    setUploading(true);
    setError(null);
    setProgress(10);

    try {
      const formData = new FormData();
      formData.append("file", file);

      setProgress(30);

      const res = await fetch("/api/statements/upload", {
        method: "POST",
        body: formData,
      });

      setProgress(80);

      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        throw new Error(data.error || "Upload failed");
      }

      const data = await res.json();
      setProgress(100);

      // Store preview data in sessionStorage for the preview page
      sessionStorage.setItem("uploadPreview", JSON.stringify(data));

      // Small delay for visual feedback then redirect
      setTimeout(() => {
        router.push(`/portfolio/preview?id=${data.previewId}`);
      }, 300);
    } catch (err) {
      setError(err.message);
      setUploading(false);
      setProgress(0);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Upload Statement</h1>
        <p className="mt-1 text-sm text-slate-400">
          Upload your broker portfolio statement (PDF) to automatically extract your holdings.
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Broker Statement</CardTitle>
          <CardDescription>
            Supported: Zerodha, Upstox, Groww, ICICI Direct, HDFC Securities. Max 5MB.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Dropzone */}
          <div
            {...getRootProps()}
            className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-12 text-center transition-colors ${
              isDragActive
                ? "border-sky-500 bg-sky-500/10"
                : file
                  ? "border-emerald-600 bg-emerald-950/20"
                  : "border-slate-700 bg-slate-900/50 hover:border-slate-600 hover:bg-slate-900"
            }`}
          >
            <input {...getInputProps()} />

            {file ? (
              <>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="text-emerald-500" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                  <polyline points="14 2 14 8 20 8" />
                  <path d="m9 15 2 2 4-4" />
                </svg>
                <p className="mt-3 text-sm font-medium text-emerald-400">{file.name}</p>
                <p className="text-xs text-slate-500">
                  {(file.size / 1024 / 1024).toFixed(2)} MB · Click or drop to replace
                </p>
              </>
            ) : (
              <>
                <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" className="text-slate-500" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                  <polyline points="17 8 12 3 7 8" />
                  <line x1="12" y1="3" x2="12" y2="15" />
                </svg>
                <p className="mt-3 text-sm font-medium text-slate-300">
                  {isDragActive ? "Drop your statement file here" : "Drag & drop your statement file (PDF, XLSX, XLS, CSV) here"}
                </p>
                <p className="text-xs text-slate-500">or click to browse</p>
              </>
            )}
          </div>

          {/* Error */}
          {error && (
            <div className="rounded-lg border border-red-900/50 bg-red-950/20 px-4 py-3 text-sm text-red-400">
              {error}
            </div>
          )}

          {/* Progress */}
          {uploading && (
            <div className="space-y-2">
              <Progress value={progress} />
              <p className="text-center text-xs text-slate-500">
                {progress < 30 ? "Uploading..." : progress < 80 ? "Parsing statement..." : "Almost done..."}
              </p>
            </div>
          )}

          {/* Upload button */}
          <div className="flex justify-end gap-2">
            <a href="/">
              <Button variant="secondary">Cancel</Button>
            </a>
            <Button onClick={handleUpload} disabled={!file || uploading}>
              {uploading ? "Processing..." : "Upload & Parse"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
