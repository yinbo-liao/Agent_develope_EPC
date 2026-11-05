import { create } from 'zustand';

interface ProjectState {
  selectedProjectId: string | null;
  setProject: (id: string) => void;
}

export const useProjectStore = create<ProjectState>((set) => ({
  selectedProjectId: null,
  setProject: (id) => set({ selectedProjectId: id }),
}));
