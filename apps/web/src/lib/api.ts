import type { Job } from "./types";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      ...options,
      headers: { "Content-Type": "application/json", ...options.headers },
    });
  } catch (error) {
    if (error instanceof Error && error.name === "AbortError") throw error;
    throw new Error(
      "Cannot reach the research API. Check that the backend is running, then try again.",
    );
  }
  const data = await response.json().catch(() => null);
  if (!response.ok)
    throw new ApiError(
      data?.error?.message ||
        data?.detail?.message ||
        (typeof data?.detail === "string"
          ? data.detail
          : `The API returned ${response.status}. Please try again.`),
      response.status,
    );
  return data as T;
}
export const post = <T>(path: string, body?: unknown, signal?: AbortSignal) =>
  api<T>(path, {
    method: "POST",
    body: body === undefined ? undefined : JSON.stringify(body),
    signal,
  });
const delay = (ms: number, signal?: AbortSignal) =>
  new Promise<void>((resolve, reject) => {
    if (signal?.aborted)
      return reject(new DOMException("Cancelled", "AbortError"));
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException("Cancelled", "AbortError"));
    };
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", abort);
      resolve();
    }, ms);
    signal?.addEventListener("abort", abort, { once: true });
  });
export async function poll<T>(
  job: Job<T>,
  update: (job: Job<T>) => void,
  signal?: AbortSignal,
): Promise<T> {
  const started = Date.now();
  while (true) {
    if (signal?.aborted) throw new DOMException("Cancelled", "AbortError");
    update(job);
    if (job.status === "SUCCEEDED") {
      if (job.result === null)
        throw new Error("The job completed without a result.");
      return job.result;
    }
    if (job.status === "FAILED")
      throw new Error(
        typeof job.error === "string"
          ? job.error
          : job.error?.message ||
              "The research job failed. Review the backend logs and try again.",
      );
    if (Date.now() - started > 20 * 60 * 1000)
      throw new Error(
        "This job is still running. Reopen the saved experiment later to view its result.",
      );
    await delay(700, signal);
    job = await api<Job<T>>(`/jobs/${job.id}`, { signal });
  }
}
export const percent = (value: number, digits = 1) =>
  Number.isFinite(value) ? `${(value * 100).toFixed(digits)}%` : "—";
export const numeric = (value: number | undefined, digits = 3) =>
  value !== undefined && Number.isFinite(value) ? value.toFixed(digits) : "—";
export const title = (value: string) =>
  value.replaceAll("_", " ").replaceAll("-", " ");
