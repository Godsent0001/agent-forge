export const keychain = {
  save: async (provider: string, key: string): Promise<void> => {
    if (window.electronAPI) {
      await window.electronAPI.saveApiKey(provider, key);
    } else {
      localStorage.setItem(`agentforge_key_${provider}`, key);
    }
  },
  get: async (provider: string): Promise<string | null> => {
    if (window.electronAPI) {
      return await window.electronAPI.getApiKey(provider);
    } else {
      return localStorage.getItem(`agentforge_key_${provider}`);
    }
  },
  remove: async (provider: string): Promise<void> => {
    if (window.electronAPI) {
      await window.electronAPI.deleteApiKey(provider);
    } else {
      localStorage.removeItem(`agentforge_key_${provider}`);
    }
  },
};
