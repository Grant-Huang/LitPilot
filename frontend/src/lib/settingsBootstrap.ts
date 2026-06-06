import { getCachedResource, invalidateCachedResource } from "@/lib/resourceCache";
import {
  settingsApiV2,
  type SystemCapability,
  type SystemCredential,
  type SystemInstance,
  type SystemOverview,
} from "@/lib/settingsApiV2";

export const ADMIN_BOOTSTRAP_CACHE_KEY = "settings:admin:bootstrap";
export const PERSONAL_PREFS_CACHE_KEY = "settings:personal:preferences";

export type AdminBootstrap = {
  overview: SystemOverview;
  caps: SystemCapability[];
  credentials: SystemCredential[];
  instances: SystemInstance[];
};

export async function loadAdminBootstrap(ttlMs = 60_000): Promise<AdminBootstrap> {
  return getCachedResource(
    ADMIN_BOOTSTRAP_CACHE_KEY,
    async () => {
      const [overview, capsRes, credRes, instRes] = await Promise.all([
        settingsApiV2.getSystemOverview(),
        settingsApiV2.getSystemCapabilities(),
        settingsApiV2.listCredentials(),
        settingsApiV2.listInstances(),
      ]);
      return {
        overview,
        caps: capsRes.items || [],
        credentials: credRes.items || [],
        instances: instRes.items || [],
      };
    },
    ttlMs,
  );
}

export function invalidateAdminBootstrap(): void {
  invalidateCachedResource(ADMIN_BOOTSTRAP_CACHE_KEY);
}

export function invalidatePersonalPreferences(): void {
  invalidateCachedResource(PERSONAL_PREFS_CACHE_KEY);
}
