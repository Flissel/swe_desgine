// Minimal test to verify Electron works
const { app, BrowserWindow } = require('electron');

console.log('Test app starting...');
console.log('Electron version:', process.versions.electron);

app.whenReady().then(() => {
  console.log('App is ready!');

  const win = new BrowserWindow({
    width: 800,
    height: 600,
    webPreferences: {
      nodeIntegration: true
    }
  });

  win.loadURL('data:text/html,<h1>Electron is working!</h1><p>Version: ' + process.versions.electron + '</p>');

  console.log('Window created!');
});

app.on('window-all-closed', () => {
  console.log('All windows closed');
  app.quit();
});
