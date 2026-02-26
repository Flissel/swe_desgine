/**
 * Electron Preload Script
 *
 * Exposes safe APIs to the renderer process via contextBridge.
 * This is the bridge between Node.js (main) and the browser (renderer).
 */

import { contextBridge, ipcRenderer } from 'electron';

// Type definitions for API responses
export type ApiResponse<T> =
  | { success: true; data: T }
  | { success: false; error: string };

// Project types
export interface Project {
  name: string;
  path: string;
  diagramCount: number;
  nodeCount: number;
  lastModified: Date;
}

// Define the API
const api = {
  // Project operations
  projects: {
    list: (): Promise<ApiResponse<Project[]>> =>
      ipcRenderer.invoke('projects:list'),
    load: (name: string): Promise<ApiResponse<unknown>> =>
      ipcRenderer.invoke('projects:load', name),
  },

  // Diagram operations
  diagrams: {
    list: (projectName: string): Promise<ApiResponse<unknown[]>> =>
      ipcRenderer.invoke('diagrams:list', projectName),
    load: (projectName: string, filename: string): Promise<ApiResponse<string>> =>
      ipcRenderer.invoke('diagrams:load', projectName, filename),
  },

  // Configuration
  config: {
    setEnterpriseOutputPath: (path: string): Promise<ApiResponse<string>> =>
      ipcRenderer.invoke('config:setEnterpriseOutputPath', path),
    getEnterpriseOutputPath: (): Promise<ApiResponse<string>> =>
      ipcRenderer.invoke('config:getEnterpriseOutputPath'),
  },

  // Dialog operations
  dialog: {
    selectFolder: (): Promise<string | undefined> =>
      ipcRenderer.invoke('dialog:selectFolder'),
    selectFile: (filters?: { name: string; extensions: string[] }[]): Promise<string | undefined> =>
      ipcRenderer.invoke('dialog:selectFile', filters),
  },

  // Event subscriptions (for future use with WebSocket-like events)
  on: (channel: string, callback: (...args: unknown[]) => void) => {
    const validChannels = ['project:changed', 'diagram:updated', 'error'];
    if (validChannels.includes(channel)) {
      ipcRenderer.on(channel, (_, ...args) => callback(...args));
    }
  },

  // Remove event listener
  off: (channel: string, callback: (...args: unknown[]) => void) => {
    ipcRenderer.removeListener(channel, callback);
  }
};

// Expose API to renderer
contextBridge.exposeInMainWorld('api', api);

// Type declaration for the renderer process
declare global {
  interface Window {
    api: typeof api;
  }
}

console.log('[Preload] API exposed to renderer');
