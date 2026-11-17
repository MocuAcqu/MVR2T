import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { isDirectory, loadPrefs, savePrefs } from './prefs';

describe('prefs', () => {
  let dir: string;
  let file: string;
  beforeEach(async () => {
    dir = await mkdtemp(path.join(os.tmpdir(), 'mvr2t-prefs-'));
    file = path.join(dir, 'preferences.json');
  });
  afterEach(async () => {
    await rm(dir, { recursive: true, force: true });
  });

  it('starts empty, saves and merges', async () => {
    expect(await loadPrefs(file)).toEqual({ lastExportFolder: null, fixedExportFolder: null, youtubeNoticeAccepted: false });
    await savePrefs(file, { lastExportFolder: dir });
    expect(await savePrefs(file, { fixedExportFolder: dir, youtubeNoticeAccepted: false })).toEqual({ lastExportFolder: dir, fixedExportFolder: dir, youtubeNoticeAccepted: false });
    expect(await loadPrefs(file)).toEqual({ lastExportFolder: dir, fixedExportFolder: dir, youtubeNoticeAccepted: false });
  });

  it('ignores a broken file and relative or non-string paths', async () => {
    await writeFile(file, '{ not json');
    expect(await loadPrefs(file)).toEqual({ lastExportFolder: null, fixedExportFolder: null, youtubeNoticeAccepted: false });
    await writeFile(file, JSON.stringify({ lastExportFolder: 'relative/x', fixedExportFolder: 5, transcript: 'never stored' }));
    expect(await loadPrefs(file)).toEqual({ lastExportFolder: null, fixedExportFolder: null, youtubeNoticeAccepted: false });
  });

  it('remembers the YouTube notice only when it is exactly true', async () => {
    await writeFile(file, JSON.stringify({ youtubeNoticeAccepted: 'yes' }));
    expect((await loadPrefs(file)).youtubeNoticeAccepted).toBe(false);
    await savePrefs(file, { youtubeNoticeAccepted: true });
    expect((await loadPrefs(file)).youtubeNoticeAccepted).toBe(true);
  });

  it('checks that a folder still exists', async () => {
    expect(await isDirectory(dir)).toBe(true);
    expect(await isDirectory(path.join(dir, 'gone'))).toBe(false);
    expect(await isDirectory(null)).toBe(false);
  });
});
