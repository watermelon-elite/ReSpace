// ReSpace integration: measured baseline and authoring seams for Wes Bos's runtime.
// This is scaffolding, not a detailed reconstruction of captured Objects.
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { wallMatrix, wallShape, type WallDef } from './packages/room-runtime/walls';
import type { BuiltRoom, RoomModule, PhotoPose, RoomLayout } from './packages/room-runtime/types';

export interface Measurements {
  polygon: number[][] | null;
  walls: { index: number; origin: number[]; u: number[]; n: number[]; length: number;
    height: number; openings: { kind: string; u0: number; u1: number; v0: number; v1: number }[] }[];
  objects: { category: string; center: number[]; size: number[]; rotY: number }[];
  photos: Omit<PhotoPose, 'url'>[];
}
export interface PartContext {
  group: THREE.Group;
  lights: THREE.Group;
  walls: BuiltRoom['walls'];
  ceiling: THREE.Object3D[];
  measurements: Measurements;
  params: URLSearchParams;
}
export interface AuthoredPart { build(context: PartContext): void | Promise<void> }

function inside(x: number, z: number, polygon: number[][]): boolean {
  let hit = false;
  for (let i = 0, j = polygon.length-1; i < polygon.length; j = i++) {
    const a = polygon[i], b = polygon[j];
    if ((a[1] > z) !== (b[1] > z) && x < (b[0]-a[0])*(z-a[1])/(b[1]-a[1])+a[0]) hit = !hit;
  }
  return hit;
}

export function captureRoom(id: string, label: string, data: Measurements,
  parts: Record<string, AuthoredPart>, items: Record<string, AuthoredPart>, hasMesh: boolean): RoomModule {
  return { id, label, async build(): Promise<BuiltRoom> {
    if (!data.polygon || data.polygon.length < 3) throw new Error('Establish the floor polygon from scan evidence before modeling.');
    const polygon = data.polygon;
    const group = new THREE.Group(), lights = new THREE.Group();
    group.name = id;
    const paint = new THREE.MeshStandardMaterial({ color: '#bdbdbd', roughness: .9, side: THREE.DoubleSide });
    const walls = data.walls.map(w => {
      const def: WallDef = { name: String(w.index), origin: new THREE.Vector3(...w.origin),
        u: new THREE.Vector3(...w.u), n: new THREE.Vector3(...w.n), length: w.length,
        height: w.height, thickness: .10, ext: [0, 0], crown: false, panels: [],
        openings: w.openings.map(o => ({ kind: 'rect', u0: o.u0, u1: o.u1, v0: o.v0, v1: o.v1 })) };
      // Preserve real notches/openings using the upstream wall builder's shape.
      // Thickness is a labeled baseline assumption; no decorative trim is invented.
      const geometry = new THREE.ExtrudeGeometry(wallShape(def, 0), { depth: def.thickness, bevelEnabled: false });
      geometry.translate(0, 0, -def.thickness);
      const slab = new THREE.Mesh(geometry, paint);
      slab.applyMatrix4(wallMatrix(def)); slab.castShadow = slab.receiveShadow = true;
      const root = new THREE.Group(); root.name = 'wall-'+w.index; root.add(slab); group.add(root);
      return { def, group: root };
    });
    const outline = new THREE.Shape(polygon.map(([x,z]) => new THREE.Vector2(x, -z)));
    const floor = new THREE.Mesh(new THREE.ShapeGeometry(outline), paint.clone());
    floor.rotation.x = -Math.PI/2; floor.name = 'floor'; floor.receiveShadow = true; group.add(floor);
    const wallTop = Math.max(...data.walls.map(w => w.height));
    const ceiling = floor.clone(); ceiling.material = paint.clone(); ceiling.position.y = wallTop;
    ceiling.name = 'ceiling-baseline-flat-inference'; group.add(ceiling);
    // Freeze the schematic reference before authored code changes the model.
    // The scan renderer uses no lights, so reference materials must be unlit.
    const referenceLayout = group.clone(true);
    referenceLayout.traverse(o => {
      if (o instanceof THREE.Mesh) o.material = new THREE.MeshBasicMaterial({ color: '#bdbdbd', side: THREE.DoubleSide });
    });
    // Neutral authoring fill. The detailed pass places real fixtures from photos.
    lights.add(new THREE.HemisphereLight(0xffffff, 0x777777, 1));
    const params = new URLSearchParams(location.search);
    const context: PartContext = { group, lights, walls, ceiling: [ceiling], measurements: data, params };
    async function authored(entries: Record<string, AuthoredPart>, key: string) {
      const only = params.get(key)?.split(',');
      const hidden = params.get('hide'+key[0].toUpperCase()+key.slice(1))?.split(',') ?? [];
      for (const [path, module] of Object.entries(entries)) {
        const name = path.split('/').pop()!.replace(/\.ts$/, '');
        if (name.startsWith('_') || only && !only.includes(name) || hidden.includes(name)) continue;
        await module.build(context);
      }
    }
    await authored(parts, 'parts'); await authored(items, 'items');
    const photos = data.photos.map((p, i) => ({ ...p, url: `/${id}/photos/${String(i).padStart(4,'0')}.jpg` }));
    const point = photos.find(p => inside(p.position[0], p.position[2], polygon))?.position ?? [polygon[0][0], 1.6, polygon[0][1]];
    const layout: RoomLayout = { polygon, objects: data.objects,
      note: 'Measured baseline; furniture boxes are reference bounds, not finished Objects.',
      walls: data.walls.map(w => ({ a: [w.origin[0],w.origin[2]], b: [w.origin[0]+w.u[0]*w.length,w.origin[2]+w.u[2]*w.length],
        u: w.u, length: w.length, openings: w.openings })) };
    return { group, lights, walls, ceiling: context.ceiling, wallTop, layout, photos,
      referenceAvailable: true, referenceKind: hasMesh ? 'scan' : 'layout',
      walkable: (x,z) => inside(x,z,polygon),
      camera: { orbit: [6,5,6], target: [0,1,0], walk: [point[0],1.6,point[2]], walkLook: [0,1.6,0] },
      environment: { center: [0,1.4,0], intensity: .4 },
      async loadReference() {
        if (hasMesh) {
          const scan = (await new GLTFLoader().loadAsync(`/${id}/scan.glb`)).scene;
          // The reference's vertex colors already contain photographic lighting;
          // upstream's scan renderer intentionally supplies no scene lights.
          scan.traverse(o => {
            if (o instanceof THREE.Mesh) {
              o.material = new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false, side: THREE.DoubleSide });
            }
          });
          return scan;
        }
        const reference = referenceLayout.clone(true);
        for (const [i,o] of data.objects.entries()) {
          const box = new THREE.Mesh(new THREE.BoxGeometry(...o.size), new THREE.MeshBasicMaterial({ color: '#ddad55', wireframe: true }));
          box.name = 'reference-bound-'+i; box.position.fromArray(o.center); box.rotation.y = o.rotY; reference.add(box);
        }
        return reference;
      } };
  } };
}
