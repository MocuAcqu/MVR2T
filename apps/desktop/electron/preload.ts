/**
 * Preload：Renderer 與 Main 之間的安全橋接（規格 §3.3 / §11-8）。
 * 只透過 contextBridge 暴露「有限」的 API，不暴露 ipcRenderer 本身。
 */
import { contextBridge, ipcRenderer, type IpcRendererEvent } from 'electron';
import { IPC_CHANNELS } from '@shared/constants/app';
import type {
  AppInfo,
  AppNotification,
  BackendState,
  ExportFilesRequest,
  ExportFilesResult,
  ExportPrefs,
  UiPrefs,
  Mvr2tBridge,
  SaveFileRequest,
  SaveFileResult,
} from '@shared/types/ipc';

const bridge: Mvr2tBridge = {
  getAppInfo: (): Promise<AppInfo> => ipcRenderer.invoke(IPC_CHANNELS.getAppInfo),
  getBackendState: (): Promise<BackendState> => ipcRenderer.invoke(IPC_CHANNELS.getBackendState),
  restartBackend: (): Promise<BackendState> => ipcRenderer.invoke(IPC_CHANNELS.restartBackend),
  onBackendState: (listener) => {
    // 包一層：不把 IpcRendererEvent（含 sender）交給頁面。
    const wrapped = (_event: IpcRendererEvent, state: BackendState) => listener(state);
    ipcRenderer.on(IPC_CHANNELS.backendStateChanged, wrapped);
    return () => {
      ipcRenderer.removeListener(IPC_CHANNELS.backendStateChanged, wrapped);
    };
  },
  notify: (notification: AppNotification): Promise<boolean> => ipcRenderer.invoke(IPC_CHANNELS.notify, notification),
  setKeepAwake: (on: boolean): Promise<void> => ipcRenderer.invoke(IPC_CHANNELS.setKeepAwake, on),
  saveFile: (request: SaveFileRequest): Promise<SaveFileResult> => ipcRenderer.invoke(IPC_CHANNELS.saveFile, request),
  exportFiles: (request: ExportFilesRequest): Promise<ExportFilesResult> => ipcRenderer.invoke(IPC_CHANNELS.exportFiles, request),
  openExportFolder: (): Promise<void> => ipcRenderer.invoke(IPC_CHANNELS.openExportFolder),
  getExportPrefs: (): Promise<ExportPrefs> => ipcRenderer.invoke(IPC_CHANNELS.getExportPrefs),
  chooseFixedExportFolder: (): Promise<ExportPrefs> => ipcRenderer.invoke(IPC_CHANNELS.chooseFixedExportFolder),
  clearFixedExportFolder: (): Promise<ExportPrefs> => ipcRenderer.invoke(IPC_CHANNELS.clearFixedExportFolder),
  getYouTubeNotice: (): Promise<boolean> => ipcRenderer.invoke(IPC_CHANNELS.getYouTubeNotice),
  acceptYouTubeNotice: (): Promise<boolean> => ipcRenderer.invoke(IPC_CHANNELS.acceptYouTubeNotice),
  getUiPrefs: (): Promise<UiPrefs> => ipcRenderer.invoke(IPC_CHANNELS.getUiPrefs),
  setUiPrefs: (patch: Partial<UiPrefs>): Promise<UiPrefs> => ipcRenderer.invoke(IPC_CHANNELS.setUiPrefs, patch),
  openAppLocation: (which: 'data' | 'notices'): Promise<boolean> => ipcRenderer.invoke(IPC_CHANNELS.openAppLocation, which),
};

contextBridge.exposeInMainWorld('mvr2t', bridge);
