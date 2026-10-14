export interface KeyStorageResult {
  ok: boolean;
  saved?: boolean;
  hint?: string;
  applied?: boolean;
  protection?: "safeStorage" | "plaintext-opt-in";
  reason?: "invalid-provider" | "encryption-unavailable" | "storage-failed";
}

export interface ElectronAPI {
  getBackendPort: () => Promise<number>;
  getApiToken: () => Promise<string>;
  getApiKeyStatus: (provider: string) => Promise<{ saved: boolean; hint: string }>;
  saveApiKey: (provider: string, key: string) => Promise<KeyStorageResult>;
  deleteApiKey: (provider: string) => Promise<KeyStorageResult>;
  syncApiKeys: () => Promise<{ status: string }>;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}
