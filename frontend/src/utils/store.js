import { create } from 'zustand';
export const usePanelStore = create((set) => ({
  selectedDomain: null,
  setSelectedDomain: (domain) => set({ selectedDomain: domain }),
  sidebarCollapsed: false,
  setSidebarCollapsed: (v) => set({ sidebarCollapsed: v }),
  commandPaletteOpen: false,
  setCommandPaletteOpen: (v) => set({ commandPaletteOpen: v }),
}));
