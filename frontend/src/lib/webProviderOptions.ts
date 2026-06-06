import type { SystemCredential } from "@/lib/settingsApiV2";

export function hasCredentialSecret(
  credentials: SystemCredential[],
  type: string,
): boolean {
  return credentials.some((c) => c.type === type && c.has_secret);
}

export type ProviderSelectOption = {
  value: string;
  label: string;
  disabled: boolean;
};

export function searchProviderNeedsCredential(provider: string): boolean {
  const p = provider.trim().toLowerCase();
  return p === "tavily" || p === "brave";
}

export function searchProviderOptionalCredential(provider: string): string | null {
  const p = provider.trim().toLowerCase();
  if (p === "multi_academic") return "semantic_scholar";
  return null;
}

export function fetchProviderNeedsCredential(provider: string): boolean {
  return provider.trim().toLowerCase() === "jina";
}

export function searchProviderOptions(
  credentials: SystemCredential[],
): ProviderSelectOption[] {
  return [
    {
      value: "tavily",
      label: "Tavily（需 API Key，通用）",
      disabled: !hasCredentialSecret(credentials, "tavily"),
    },
    {
      value: "brave",
      label: "Brave Search（需 API Key，通用）",
      disabled: !hasCredentialSecret(credentials, "brave"),
    },
    {
      value: "multi_academic",
      label: "multi_academic（arXiv+CrossRef+PMC+OpenAlex+SS，无需 Key）",
      disabled: false,
    },
    {
      value: "openalex",
      label: "OpenAlex（学术，无需 Key）",
      disabled: false,
    },
    {
      value: "native",
      label: "native（DDG HTML，无需 Key）",
      disabled: false,
    },
  ];
}

export function fetchProviderOptions(
  credentials: SystemCredential[],
): ProviderSelectOption[] {
  return [
    {
      value: "jina",
      label: "Jina Reader（需 API Key）",
      disabled: !hasCredentialSecret(credentials, "jina"),
    },
    {
      value: "native",
      label: "native（直连 HTTP，无需 Key）",
      disabled: false,
    },
  ];
}

export function searchCredentialType(provider: string): string {
  return provider === "brave" ? "brave" : "tavily";
}
