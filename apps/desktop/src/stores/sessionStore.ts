import { create } from 'zustand';

interface SessionState {
  /** The media file chosen in this session (in memory only). */
  media: File | null;
  setMedia: (file: File | null) => void;
}

// No persist middleware on purpose: transcripts/media must never be stored (PROJECT_SPEC 8.3).
export const useSessionStore = create<SessionState>((set) => ({
  media: null,
  setMedia: (media) => set({ media }),
}));
