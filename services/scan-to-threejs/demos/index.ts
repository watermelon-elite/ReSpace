import type { RoomModule } from '../packages/room-runtime/types';
export type { BuiltRoom } from '../packages/room-runtime/types';

// Private prepared projects register their authored RoomModule here.
const modules = import.meta.glob<{ default: RoomModule }>('./*/index.ts', { eager: true });
export const ROOMS: RoomModule[] = Object.values(modules).map(m => m.default);
export function roomById(id: string | null): RoomModule {
  const room = id ? ROOMS.find(r => r.id === id) : ROOMS[0];
  if (!room) throw new Error('Prepare a capture with prepare.py, then register its RoomModule. No public example room is substituted.');
  return room;
}
