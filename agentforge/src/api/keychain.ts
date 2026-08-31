import { invoke } from "@tauri-apps/api/core";

export const keychain = {
  save: (provider: string, key: string) => invoke<void>("save_api_key", { provider, key }),
  get: (provider: string) => invoke<string | null>("get_api_key", { provider }),
  remove: (provider: string) => invoke<void>("delete_api_key", { provider }),
};
