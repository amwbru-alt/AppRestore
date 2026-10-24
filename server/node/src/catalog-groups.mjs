import { safeIcon, ApiError } from './service.mjs';
export function validateGroups(raw) {
  if (!Array.isArray(raw) || raw.length > 200) throw new ApiError(400, 'invalid_groups');
  const ids = new Set(), assigned = new Set();
  return raw.map(group => {
    if (!group || typeof group.id !== 'string' || !/^[a-z0-9][a-z0-9-]{0,63}$/.test(group.id)
      || ids.has(group.id) || typeof group.name !== 'string' || !group.name.trim() || group.name.length > 255
      || !Array.isArray(group.apps) || group.apps.length < 1 || group.apps.length > 1000) throw new ApiError(400, 'invalid_group');
    ids.add(group.id);
    const apps = group.apps.map(app => {
      if (!app || typeof app.trackId !== 'string' || !/^[1-9][0-9]{7,11}$/.test(app.trackId) || assigned.has(app.trackId)
        || typeof app.name !== 'string' || !app.name.trim() || app.name.length > 255) throw new ApiError(400, 'invalid_variant');
      assigned.add(app.trackId);
      if (assigned.size > 5000) throw new ApiError(400, 'too_many_variants');
      return { trackId: app.trackId, name: app.name.trim(), iconUrl: safeIcon(app.iconUrl || '') };
    });
    return { id: group.id, name: group.name.trim(), iconUrl: safeIcon(group.iconUrl || ''), apps };
  });
}
export async function importGroups(pool, raw) {
  const groups = validateGroups(raw);
  const db = await pool.getConnection();
  try {
    await db.beginTransaction();
    // Replace assignments atomically. Omitted groups are disabled, not deleted.
    await db.execute('DELETE FROM apprevive_catalog_variants');
    await db.execute('UPDATE apprevive_catalog_groups SET enabled=0');
    for (const group of groups) {
      await db.execute('INSERT INTO apprevive_catalog_groups (group_id,name,icon_url,enabled) VALUES (?,?,?,1) ON DUPLICATE KEY UPDATE name=VALUES(name),icon_url=VALUES(icon_url),enabled=1', [group.id, group.name, group.iconUrl]);
      for (const app of group.apps) {
        await db.execute('INSERT INTO apprevive_app_catalog (store_id,name,icon_url) VALUES (?,?,?) ON DUPLICATE KEY UPDATE name=VALUES(name),icon_url=IF(VALUES(icon_url)=\'\',icon_url,VALUES(icon_url)),enabled=1', [app.trackId, app.name, app.iconUrl]);
        await db.execute('INSERT INTO apprevive_catalog_variants (store_id,group_id) VALUES (?,?)', [app.trackId, group.id]);
      }
    }
    await db.commit(); return groups.length;
  } catch (error) { await db.rollback(); throw error; }
  finally { db.release(); }
}
