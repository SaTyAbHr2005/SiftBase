// The page's only way out: named calls to the main process. No Node, no keys, no raw IPC.
const { contextBridge, ipcRenderer, webUtils } = require('electron');

const on = (channel) => (cb) => {
  const fn = (_e, data) => cb(data);
  ipcRenderer.on(channel, fn);
  return () => ipcRenderer.removeListener(channel, fn);
};

contextBridge.exposeInMainWorld('sift', {
  status: () => ipcRenderer.invoke('status'),
  collections: () => ipcRenderer.invoke('collections'),
  query: (collection, question) => ipcRenderer.invoke('query', { collection, question }),
  history: () => ipcRenderer.invoke('history'),
  saveKeys: (input) => ipcRenderer.invoke('keys:save', input),
  testKey: (provider, values) => ipcRenderer.invoke('keys:test', { provider, values }),
  index: (folder, collection) => ipcRenderer.invoke('index:start', { folder, collection }),
  pickFolder: () => ipcRenderer.invoke('pick:folder'),
  pickDataFolder: () => ipcRenderer.invoke('data:pick'),
  openDataFolder: () => ipcRenderer.invoke('open:data'),
  pathForFile: (f) => webUtils.getPathForFile(f),
  onApi: on('api'),
  onIndexProgress: on('index:progress'),
  onIndexDone: on('index:done'),
});
