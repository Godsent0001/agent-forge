const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("electronAPI", {
  getBackendPort: () => ipcRenderer.invoke("get-backend-port"),
  saveApiKey: (provider, key) => ipcRenderer.invoke("save-api-key", provider, key),
  getApiKey: (provider) => ipcRenderer.invoke("get-api-key", provider),
  deleteApiKey: (provider) => ipcRenderer.invoke("delete-api-key", provider),
});
