/**
 * RE System Dashboard - Electron Preload Script
 *
 * Exposes a safe API to the renderer process via contextBridge.
 * This enables communication between the web dashboard and the Electron main process.
 */

const { contextBridge, ipcRenderer } = require('electron');

// Expose electronAPI to the renderer process
contextBridge.exposeInMainWorld('electronAPI', {
    // Server control
    getServerPort: () => ipcRenderer.invoke('server:get-port'),
    getServerStatus: () => ipcRenderer.invoke('server:get-status'),
    restartServer: () => ipcRenderer.invoke('server:restart'),

    // Event listeners
    onServerLog: (callback) => {
        ipcRenderer.on('server:log', (event, data) => callback(data));
    },

    onMenuLayout: (callback) => {
        ipcRenderer.on('menu:layout', (event, layout) => callback(layout));
    },

    // Utility
    platform: process.platform,
    isElectron: true,

    // Remove listeners (for cleanup)
    removeAllListeners: (channel) => {
        ipcRenderer.removeAllListeners(channel);
    }
});

// Log that preload was executed
console.log('[Preload] Electron API exposed to renderer');
