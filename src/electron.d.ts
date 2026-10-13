export interface ElectronAPI {
  getBackendPort: () => Promise<number>;
  getApiToken: () => Promise<string>;
  saveApiKey: (provider: string, key: string) => Promise<boolean>;
  getApiKey: (provider: string) => Promise<string | null>;
  deleteApiKey: (provider: string) => Promise<boolean>;
}

declare global {
  interface Window {
    electronAPI?: ElectronAPI;
  }
}
