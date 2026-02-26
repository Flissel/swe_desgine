# RE System Dashboard - Electron App

Standalone Electron application for the Requirements Engineering System Dashboard.

## Quick Start

```bash
# Install dependencies
npm install

# Run the app
npm start

# Run with DevTools open
npm run dev
```

## Features

- Python dashboard server runs as subprocess
- Automatic port detection
- Matrix layout for work package visualization
- Real-time updates via WebSocket
- Menu-based layout switching

## Embedding in Another Electron App

Use the `embed.js` module to embed the dashboard into your own Electron application:

```javascript
const { startREServer, stopREServer, createREDashboardView } = require('./embed');

// In your main process:
async function initDashboard(mainWindow) {
    // Start the Python server
    const port = await startREServer({
        projectRoot: '/path/to/AI-Scientist-v2',
        port: 8085
    });

    // Create a BrowserView in your window
    const dashboardView = createREDashboardView(mainWindow, port, {
        bounds: { x: 300, y: 0, width: 1200, height: 800 },
        autoResize: true
    });

    return dashboardView;
}

// Clean up when closing
app.on('before-quit', () => {
    stopREServer();
});
```

## API

### `startREServer(options)`

Starts the Python dashboard server.

**Options:**
- `pythonPath` - Path to Python executable (default: 'python' or 'python3')
- `projectRoot` - Path to AI-Scientist-v2 directory
- `port` - Preferred port (default: 8085)

**Returns:** Promise<number> - The port the server is running on

### `stopREServer()`

Stops the Python dashboard server.

### `createREDashboardView(parentWindow, port, options)`

Creates a BrowserView for the dashboard.

**Options:**
- `bounds` - { x, y, width, height }
- `autoResize` - Auto-resize with parent window (default: true)

**Returns:** BrowserView

### `getServerPort()`

Returns the current server port or null if not running.

### `isServerRunning()`

Returns true if the server is currently running.

## Requirements

- Node.js 18+
- Python 3.9+
- Required Python packages (see requirements.txt in project root)

## Building

```bash
# Build for current platform
npm run build
```

Output will be in the `dist/` directory.
