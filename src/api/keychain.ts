const getElectronAPI = () => {
  if (typeof window !== "undefined" && window.electronAPI) {
    return window.electronAPI;
  }

  return null;
};

const DEV_PREFIX = "agentforge_dev_key_";

export const keychain = {
  async save(provider: string, key: string): Promise<void> {
    const electronAPI = getElectronAPI();

    if (electronAPI) {
      await electronAPI.saveApiKey(provider, key);
      return;
    }

    // Browser development only
    sessionStorage.setItem(`${DEV_PREFIX}${provider}`, key);
  },

  async get(provider: string): Promise<string | null> {
    const electronAPI = getElectronAPI();

    if (electronAPI) {
      return await electronAPI.getApiKey(provider);
    }

    // Browser development only
    return sessionStorage.getItem(`${DEV_PREFIX}${provider}`);
  },

  async remove(provider: string): Promise<void> {
    const electronAPI = getElectronAPI();

    if (electronAPI) {
      await electronAPI.deleteApiKey(provider);
      return;
    }

    // Browser development only
    sessionStorage.removeItem(`${DEV_PREFIX}${provider}`);
  },
};