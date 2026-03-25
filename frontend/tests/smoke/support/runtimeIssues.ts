export type RuntimeIssueSource =
  | "console"
  | "pageerror"
  | "requestfailed"
  | "response";

export interface RuntimeIssue {
  source: RuntimeIssueSource;
  message: string;
}

export function shouldIgnoreConsoleErrorText(text: string): boolean {
  return (
    text.includes("Download the React DevTools") ||
    text.includes("favicon.ico") ||
    text.includes("%c%s%c ")
  );
}

export function shouldIgnoreFailedRequestUrl(url: string): boolean {
  return (
    url.includes("/_next/webpack-hmr") ||
    url.includes("__nextjs_original-stack-frame") ||
    url.includes("__nextjs_source-map")
  );
}

export function isBadHttpStatus(status: number): boolean {
  return status >= 400;
}

export function formatRuntimeIssues(
  routePath: string,
  issues: RuntimeIssue[]
): string[] {
  return issues.map((issue) => `[${routePath}] [${issue.source}] ${issue.message}`);
}
