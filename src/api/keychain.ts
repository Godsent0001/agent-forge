type KeyStatus = { saved: boolean; hint: string };
type KeyStorageResult = {
  ok: boolean;
  saved?: boolean;
  hint?: string;
  applied?: boolean;
  protection?: "safeStorage" | "plaintext-opt-in";
  reason?: string;
};

const devHints = new Map<string, string>();
const getElectronAPI = () => typeof window !== "undefined" ? window.electronAPI ?? null : null;

export const keychain = {
  async status(provider: string): Promise<KeyStatus> {
    const electronAPI = getElectronAPI();
    if (electronAPI) return electronAPI.getApiKeyStatus(provider);
    const hint = devHints.get(provider);
    return { saved: Boolean(hint), hint: hint ? "••••" + hint : "" };
  },

  async save(provider: string, key: string): Promise<KeyStorageResult> {
    const electronAPI = getElectronAPI();
    if (electronAPI) return electronAPI.saveApiKey(provider, key);
    // Browser development does not persist secret material. The caller sends it
    // directly to the local runtime; only a masked hint remains in volatile memory.
    devHints.set(provider, key.slice(-4));
    return { ok: true, saved: true, hint: "••••" + key.slice(-4), applied: false };
  },

  async remove(provider: string): Promise<KeyStorageResult> {
    const electronAPI = getElectronAPI();
    if (electronAPI) return electronAPI.deleteApiKey(provider);
    devHints.delete(provider);
    return { ok: true, saved: false, hint: "", applied: false };
  },

  rememberDevKey(provider: string, key: string) {
    if (!getElectronAPI()) {
      if (key) devHints.set(provider, key.slice(-4));
      else devHints.delete(provider);
    }
  },

  async syncToRuntime(): Promise<{ status: string }> {
    const electronAPI = getElectronAPI();
    if (electronAPI) return electronAPI.syncApiKeys();
    return { status: "ok" }; // Browser-dev keys are POSTed directly; never read back from storage.
  },
};
