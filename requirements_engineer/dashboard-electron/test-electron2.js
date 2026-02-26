console.log("process.type:", process.type);
console.log("process.versions.electron:", process.versions.electron);

// In Electron main process, require('electron') should work differently
if (process.type === 'browser') {
  console.log("Running in Electron main process");
  const { app, BrowserWindow } = require('electron');
  console.log("app:", app);
  app.whenReady().then(() => {
    console.log("App ready!");
    app.quit();
  });
} else {
  console.log("Not in Electron main process!");
}
