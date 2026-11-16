// electron-builder afterPack hook (Phase 11 fix1).
// With a custom electronDist, Electron's default_app.asar (the "drag your app here" demo) is copied into resources/.
// The packaged app never uses it, so remove it.
const fs = require('node:fs');
const path = require('node:path');

exports.default = async function afterPack(context) {
  const resources =
    context.electronPlatformName === 'darwin'
      ? path.join(context.appOutDir, `${context.packager.appInfo.productFilename}.app`, 'Contents', 'Resources')
      : path.join(context.appOutDir, 'resources');
  const file = path.join(resources, 'default_app.asar');
  if (fs.existsSync(file)) {
    fs.rmSync(file);
    console.log(`  • removed ${path.relative(context.appOutDir, file)}`);
  }
};
