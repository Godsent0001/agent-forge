const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  getBackendPort: () => ipcRenderer.invoke("get-backend-port"),
  getApiToken: () => ipcRenderer.invoke("get-api-token"),
  getApiKeyStatus: (provider) => ipcRenderer.invoke("get-api-key-status", provider),
  saveApiKey: (provider, key) => ipcRenderer.invoke("save-api-key", provider, key),
  deleteApiKey: (provider) => ipcRenderer.invoke("delete-api-key", provider),
  syncApiKeys: () => ipcRenderer.invoke("sync-api-keys"),
});
