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
    expect(await loadPrefs(file)).toEqual({ lastExportFolder: null, fixedExportFolder: null });
    await savePrefs(file, { lastExportFolder: dir });
    expect(await savePrefs(file, { fixedExportFolder: dir })).toEqual({ lastExportFolder: dir, fixedExportFolder: dir });
    expect(await loadPrefs(file)).toEqual({ lastExportFolder: dir, fixedExportFolder: dir });
  });

  it('ignores a broken file and relative or non-string paths', async () => {
    await writeFile(file, '{ not json');
    expect(await loadPrefs(file)).toEqual({ lastExportFolder: null, fixedExportFolder: null });
    await writeFile(file, JSON.stringify({ lastExportFolder: 'relative/x', fixedExportFolder: 5, transcript: 'never stored' }));
    expect(await loadPrefs(file)).toEqual({ lastExportFolder: null, fixedExportFolder: null });
  });

  it('checks that a folder still exists', async () => {
    expect(await isDirectory(dir)).toBe(true);
    expect(await isDirectory(path.join(dir, 'gone'))).toBe(false);
    expect(await isDirectory(null)).toBe(false);
  });
});
