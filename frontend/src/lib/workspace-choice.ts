/** Remembers the active workspace in this browser and picks a sensible default. */

import type { Workspace } from "./types";

const KEY = "atlas.activeWorkspace";

export function readStoredWorkspace(): string | null {
  try {
    return window.localStorage.getItem(KEY);
  } catch {
    return null;
  }
}

export function storeWorkspace(id: string | null): void {
  try {
    if (id) window.localStorage.setItem(KEY, id);
    else window.localStorage.removeItem(KEY);
  } catch {
    /* storage unavailable: the choice lasts for this page only */
  }
}

/** The preferred workspace if it still exists, else your own, else the demo. */
export function pickWorkspace(list: Workspace[], preferred: string | null): string | null {
  if (preferred && list.some((w) => w.id === preferred)) return preferred;
  return (list.find((w) => !w.is_demo) ?? list[0])?.id ?? null;
}
