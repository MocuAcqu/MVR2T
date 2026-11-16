; MVR2T NSIS customizations (Phase 11 fix1). Included by electron-builder (nsis.include).
; Keep this file ASCII-only: NSIS reads it with the system code page.

!macro customInstall
  ; The standard uninstall key (Settings > Apps) has no InstallLocation by default; add it.
  WriteRegStr SHELL_CONTEXT "${UNINSTALL_REGISTRY_KEY}" InstallLocation "$INSTDIR"
  ; electron-builder keeps a copy of the installer (about 350 MB) for differential updates.
  ; MVR2T does not use auto-update, so remove it right away.
  ; APP_INSTALLER_STORE_FILE = mvr2t-updater\installer.exe (from extraMetadata.name: MVR2T, lower-cased).
  !ifdef APP_INSTALLER_STORE_FILE
    Delete "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}"
    RMDir "$LOCALAPPDATA\mvr2t-updater"
  !endif
  ; Left over by the first Phase 11 test build (package name @mvr2t/desktop).
  RMDir /r "$LOCALAPPDATA\@mvr2tdesktop-updater"
!macroend

!macro customUnInstall
  !ifdef APP_INSTALLER_STORE_FILE
    Delete "$LOCALAPPDATA\${APP_INSTALLER_STORE_FILE}"
    RMDir "$LOCALAPPDATA\mvr2t-updater"
  !endif
  RMDir /r "$LOCALAPPDATA\@mvr2tdesktop-updater"
!macroend
