// Minimal Electron test
console.log('Test starting...');
console.log('process.versions.electron:', process.versions.electron);

try {
  const electron = require('electron');
  console.log('typeof electron:', typeof electron);
  console.log('electron value:', electron);

  if (typeof electron === 'string') {
    console.log('ERROR: electron module returned a string (path), not the API!');
    console.log('This means node_modules/electron is shadowing the built-in module.');
  } else if (electron.app) {
    console.log('SUCCESS: electron.app is available!');
    electron.app.whenReady().then(() => {
      console.log('App ready!');
      const { BrowserWindow } = electron;
      const win = new BrowserWindow({ width: 400, height: 300 });
      win.loadURL('data:text/html,<h1>It works!</h1>');
    });
  } else {
    console.log('ERROR: electron loaded but app is undefined');
    console.log('Keys:', Object.keys(electron));
  }
} catch (e) {
  console.error('Error:', e.message);
}
