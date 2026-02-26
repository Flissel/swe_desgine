const electron = require("electron");
console.log("electron:", typeof electron);
console.log("electron keys:", Object.keys(electron).slice(0, 20));
console.log("electron.app:", electron.app);
console.log("electron.BrowserWindow:", electron.BrowserWindow);
electron.app.whenReady().then(() => {
  console.log("App ready!");
  electron.app.quit();
});
