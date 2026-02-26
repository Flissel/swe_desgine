/**
 * Electron Bootstrap
 *
 * This script runs before the main app and patches require('electron')
 * to return the correct Electron API instead of the npm package path.
 */

const Module = require('module');
const path = require('path');

// Store the original _load
const originalLoad = Module._load;

// Check if we're in Electron
if (process.versions.electron) {
  console.log('[Bootstrap] Running in Electron', process.versions.electron);

  // The electron API is available through process internals
  // We need to intercept require('electron') and return the real API

  // In Electron, the real 'electron' module is registered internally
  // but node_modules/electron shadows it. We need to bypass that.

  // Strategy: Delete node_modules/electron from require.cache and paths
  const electronPath = path.join(__dirname, 'node_modules', 'electron');

  Module._load = function(request, parent, isMain) {
    if (request === 'electron') {
      // Try to get the real electron module by calling the original loader
      // but with modified resolution that skips node_modules/electron

      // First, check if we already have it cached (from a previous successful load)
      const cacheKey = 'electron';
      if (Module._cache[cacheKey] && Module._cache[cacheKey].exports.app) {
        return Module._cache[cacheKey].exports;
      }

      // The trick: Electron registers 'electron' as a built-in module
      // We can access it by requiring from a path that doesn't have node_modules

      // Create a temporary module that loads from electron's internal path
      try {
        // Method 1: Try process.electronBinding (older Electron)
        if (typeof process.electronBinding === 'function') {
          const electronAPI = {};
          electronAPI.app = process.electronBinding('app');
          electronAPI.BrowserWindow = process.electronBinding('browser_window');
          electronAPI.ipcMain = process.electronBinding('ipc_main');
          // ... etc
          if (electronAPI.app) {
            return electronAPI;
          }
        }
      } catch (e) {
        // Not available
      }

      // Method 2: Just load normally and hope Electron's hook kicks in
      // This won't work if node_modules/electron exists...

      // Method 3: Return the result from the original loader
      // The issue is this will still find node_modules/electron
      const result = originalLoad.apply(this, arguments);

      // Check if we got a string (the path) instead of the API
      if (typeof result === 'string') {
        console.error('[Bootstrap] ERROR: require("electron") returned a path!');
        console.error('[Bootstrap] Path:', result);
        console.error('[Bootstrap] This means node_modules/electron is shadowing the built-in.');

        // Last resort: throw an error with instructions
        throw new Error(
          'Electron module shadowing detected. ' +
          'Please delete node_modules/electron or use the packaged app.'
        );
      }

      return result;
    }

    return originalLoad.apply(this, arguments);
  };

  console.log('[Bootstrap] Module loader patched');
}

// Now load the actual main process
console.log('[Bootstrap] Loading main process...');
require('./dist-electron/main/index.js');
