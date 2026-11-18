// Independent preview of the delivered OBJ/MTL/PNG assets. No authored modules.
import * as T from 'three';
import { OBJLoader } from 'three/addons/loaders/OBJLoader.js';
const p=new URLSearchParams(location.search),room=p.get('room')??'room';
const data=await (await fetch('/native/measurements.json')).json();
const bundle=await (await fetch('/native/scene.json')).json();
const scene=new T.Scene();scene.background=new T.Color(.12,.12,.12);
const root=new T.Group();root.applyMatrix4(new T.Matrix4().fromArray(data.transform.worldToRoom));scene.add(root);
const maps=new Map<string,T.Texture>();
async function bitmap(name:string|undefined,color=false) {
  if(!name)return null;
  const key=name+color;
  if(!maps.has(key)) {const t=await new T.TextureLoader().loadAsync('/native/'+name);t.colorSpace=color?T.SRGBColorSpace:T.NoColorSpace;t.wrapS=t.wrapT=T.RepeatWrapping;maps.set(key,t);}
  return maps.get(key)!;
}
for(const entity of bundle.entities) {
  const object=new OBJLoader().parse(await (await fetch('/native/'+entity.asset)).text());
  const materials=new Map<string,T.Material>();
  for(const b of bundle.materials.filter((m:any)=>m.owner_id===entity.id)) {
    const values={color:new T.Color().setRGB(...b.base_color as [number,number,number],T.SRGBColorSpace),map:await bitmap(b.base_color_texture,true),side:T.DoubleSide,opacity:b.opacity,transparent:b.opacity<1||!!b.base_color_texture};
    const m=b.unlit?new T.MeshBasicMaterial(values):new T.MeshStandardMaterial({...values,roughness:b.roughness,metalness:b.metallic,
      roughnessMap:await bitmap(b.roughness_texture),metalnessMap:await bitmap(b.metallic_texture),normalMap:await bitmap(b.normal_texture),
      emissive:new T.Color().setRGB(...b.emissive_color as [number,number,number],T.SRGBColorSpace),emissiveMap:await bitmap(b.emissive_texture,true),emissiveIntensity:b.emissive_intensity});
    materials.set(b.source_material,m);
  }
  object.traverse(o=>{if(o instanceof T.Mesh){
    const wasArray=Array.isArray(o.material);
    const assigned=(wasArray?o.material as T.Material[]:[o.material as T.Material]).map(m=>{const b=materials.get(m.name);if(!b)throw Error('Missing delivered material');return b;});
    // OBJLoader supplies no geometry groups for a single material. Changing
    // that material into an array would make WebGL silently skip the mesh.
    o.material=wasArray?assigned:assigned[0];
  }});
  object.applyMatrix4(new T.Matrix4().fromArray(entity.local_to_scan_transform));root.add(object);
}
// Match WalkthroughLoader's scan-space light direction, then rotate it with
// the exported scene. A room-coordinate relabel must not change illumination.
// The pi radiance scale is calibrated against the SceneKit debug preview;
// Three.js/ACES and SceneKit HDR remain different renderers, not pixel equivalents.
scene.add(new T.AmbientLight(0xffffff,Math.PI*.5));
const sun=new T.DirectionalLight(0xffffff,Math.PI*.9);
sun.position.set(0,0,1).applyEuler(new T.Euler(-.7,-.5,0,'YXZ'))
  .transformDirection(new T.Matrix4().fromArray(data.transform.worldToRoom));
scene.add(sun);
const photo=data.photos[Number(p.get('photo')??0)];if(!photo)throw Error('Missing posed photo');
const camera=new T.PerspectiveCamera(photo.fovY,photo.aspect,.03,100);camera.position.fromArray(photo.position);camera.up.fromArray(photo.up);camera.lookAt(camera.position.clone().add(new T.Vector3().fromArray(photo.forward)));
const renderer=new T.WebGLRenderer({canvas:document.querySelector('#scene')!,antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(1);renderer.setSize(720,Math.round(720/photo.aspect));renderer.toneMapping=T.ACESFilmicToneMapping;
// Match the native viewer's one-time room-derived reflection probe. Metals
// otherwise lose their environment response even when their maps export intact.
const cubeTarget=new T.WebGLCubeRenderTarget(256,{type:T.HalfFloatType});
const cube=new T.CubeCamera(.03,100,cubeTarget);
cube.position.fromArray(bundle.navigation.spawn_position).applyMatrix4(new T.Matrix4().fromArray(data.transform.worldToRoom));
cube.update(renderer,scene);
const pmrem=new T.PMREMGenerator(renderer);
scene.environment=pmrem.fromCubemap(cubeTarget.texture).texture;
scene.environmentIntensity=.5;
await renderer.compileAsync(scene,camera);renderer.render(scene,camera);
cubeTarget.dispose();pmrem.dispose();
document.body.dataset.ready='1';
