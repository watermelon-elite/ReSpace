// Trusted transfer from authored Three.js geometry to the native mesh contract.
import * as T from 'three';
import type { BuiltRoom } from './packages/room-runtime/types';

function binary(data: Float32Array | Uint32Array): string {
  const bytes=new Uint8Array(data.buffer,data.byteOffset,data.byteLength);
  let result=''; for(let i=0;i<bytes.length;i+=16384) result+=String.fromCharCode(...bytes.subarray(i,i+16384));
  return btoa(result);
}
function pixels(texture:T.Texture):HTMLCanvasElement {
  const image=texture.image as {width:number;height:number;data?:Uint8Array};
  if(!image?.width || !image?.height || image.width>8192 || image.height>8192) throw Error('Unsupported texture dimensions');
  const canvas=document.createElement('canvas');canvas.width=image.width;canvas.height=image.height;
  const context=canvas.getContext('2d')!;
  if(image.data) {
    if(!(image.data instanceof Uint8Array)) throw Error('Float/HDR textures need an explicit bitmap bake');
    const rgba=new Uint8ClampedArray(image.width*image.height*4);
    const channels=image.data.length/(image.width*image.height);
    for(let p=0;p<image.width*image.height;p++) for(let c=0;c<4;c++) rgba[p*4+c]=c<channels?image.data[p*channels+c]:(c===3?255:0);
    context.putImageData(new ImageData(rgba,image.width,image.height),0,0);
  } else context.drawImage(image as unknown as CanvasImageSource,0,0);
  return canvas;
}
export function exportNative(room:BuiltRoom) {
  const textures:Record<string,string>={},textureSources:Record<string,string>={}, materials:any[]=[], entities:any[]=[];
  let triangles=0;
  const textureCache=new Map<string,string>();
  function texture(t:T.Texture|null,slot:string,factor:number|T.Color|T.Vector2) {
    if(!t)return null;
    const key=t.uuid+slot+JSON.stringify(typeof factor==='number'?factor:factor.toArray());
    if(textureCache.has(key))return textureCache.get(key)!;
    const canvas=pixels(t),ctx=canvas.getContext('2d')!,image=ctx.getImageData(0,0,canvas.width,canvas.height);
    const data=image.data;
    for(let i=0;i<data.length;i+=4) {
      if(slot==='base' || slot==='emissive') {
        const color=new T.Color().setRGB(data[i]/255,data[i+1]/255,data[i+2]/255,t.colorSpace===T.SRGBColorSpace?T.SRGBColorSpace:T.LinearSRGBColorSpace);
        color.multiply(factor as T.Color).convertLinearToSRGB();data[i]=color.r*255;data[i+1]=color.g*255;data[i+2]=color.b*255;
      } else if(slot==='roughness'||slot==='metallic') {
        const value=data[i+(slot==='roughness'?1:2)]*(factor as number);data[i]=data[i+1]=data[i+2]=value;data[i+3]=255;
      } else if(slot==='normal') {
        const scale=factor as T.Vector2;
        const n=new T.Vector3((data[i]/255*2-1)*scale.x,(data[i+1]/255*2-1)*scale.y,data[i+2]/255*2-1).normalize();
        data[i]=(n.x+1)*127.5;data[i+1]=(n.y+1)*127.5;data[i+2]=(n.z+1)*127.5;
      }
    }
    ctx.putImageData(image,0,0);
    const name=`tex-${Object.keys(textures).length}.png`;textures[name]=canvas.toDataURL('image/png').split(',')[1];
    const src=(t.image as HTMLImageElement)?.currentSrc||(t.image as HTMLImageElement)?.src;
    textureSources[name]=src?new URL(src,location.href).pathname:'canvas-or-data-texture';textureCache.set(key,name);return name;
  }
  room.group.updateWorldMatrix(true,true);
  for(const [rootIndex,root] of room.group.children.entries()) {
    if(!root.visible)continue;
    const tagged=root.userData.respace;
    const inferred=root.name==='floor'?'floor':root.name.startsWith('ceiling')?'ceiling':root.name.startsWith('wall-')?'wall':null;
    if(!tagged&&!inferred)throw Error(`Tag authored root ${root.name||rootIndex} with userData.respace={id,label,category,kind,collidable}`);
    const id=tagged?.id??root.name;
    if(!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,100}$/.test(id))throw Error('Invalid native Object id');
    const parts:any[]=[], used=new Map<T.Material,any>();
    root.traverseVisible(object=>{
      if(!(object instanceof T.Mesh))return;
      if(object instanceof T.InstancedMesh)throw Error('Expand instanced meshes into a tagged group before native export');
      if(object.morphTargetInfluences?.some(v=>v!==0))throw Error('Bake morph targets before native export');
      const g=object.geometry;
      if(!g.getAttribute('normal'))g.computeVertexNormals();
      const position=g.getAttribute('position'),normal=g.getAttribute('normal'),uv=g.getAttribute('uv');
      if(!position)return;
      const materialList=Array.isArray(object.material)?object.material:[object.material];
      const groups=g.groups.length?g.groups:[{start:0,count:g.index?.count??position.count,materialIndex:0}];
      for(const draw of groups) {
        const m=materialList[materialList.length===1?0:(draw.materialIndex??0)] as T.MeshStandardMaterial;
        if(!m?.isMeshStandardMaterial && !(m as any)?.isMeshBasicMaterial)throw Error(`Use bitmap-baked standard/basic materials for ${root.name}/${object.name}: ${m?.type??'missing material'}`);
        if((m as any).transmission>0 || (m as any).clearcoat>0 || (m as any).isShaderMaterial)throw Error('Bake unsupported physical/shader features before native export');
        const maps=[m.map,m.roughnessMap,m.metalnessMap,m.normalMap,m.emissiveMap].filter(Boolean) as T.Texture[];
        for(const map of maps)map.updateMatrix();
        if(maps.length&&!uv)throw Error('Textured geometry is missing UV coordinates');
        if(maps.some(map=>!map.matrix.equals(maps[0].matrix)||map.flipY!==maps[0].flipY))throw Error('Use a shared UV transform for all PBR maps, or bake them first');
        if(m.alphaMap)throw Error('Bake alphaMap into the base-color image before export');
        let material=used.get(m);
        if(!material) {
          const color=m.color??new T.Color(1,1,1);
          const base=texture(m.map,'base',color);
          const rough=texture(m.roughnessMap,'roughness',m.roughness??.7);
          const metal=texture(m.metalnessMap,'metallic',m.metalness??0);
          const emissive=texture(m.emissiveMap,'emissive',m.emissive??new T.Color(0,0,0));
          const intensity=m.emissiveIntensity??1;
          material={id:`mat-${materials.length}`,owner_id:id,base_color:base?[1,1,1]:color.clone().convertLinearToSRGB().toArray(),
            linear_color:base?[1,1,1]:color.toArray(),roughness:rough?1:(m.roughness??.7),metallic:metal?1:(m.metalness??0),
            base_color_texture:base,roughness_texture:rough,metallic_texture:metal,normal_texture:texture(m.normalMap,'normal',m.normalScale??new T.Vector2(1,1)),
            emissive_texture:emissive,emissive_color:emissive?[1,1,1]:(m.emissive??new T.Color(0,0,0)).clone().convertLinearToSRGB().toArray(),
            emissive_linear_color:emissive?[intensity,intensity,intensity]:(m.emissive??new T.Color(0,0,0)).clone().multiplyScalar(intensity).toArray(),
            emissive_intensity:intensity,opacity:m.opacity??1,unlit:m instanceof T.MeshBasicMaterial};
          used.set(m,material);materials.push(material);
        }
        const vertices:number[]=[],normals:number[]=[],uvs:number[]=[],indices:number[]=[],lookup=new Map<number,number>();
        const normalMatrix=new T.Matrix3().getNormalMatrix(object.matrixWorld);
        for(let i=draw.start;i<draw.start+draw.count;i++) {
          const old=g.index?g.index.getX(i):i;
          let next=lookup.get(old);
          if(next===undefined) {
            next=lookup.size;lookup.set(old,next);
            const p=new T.Vector3().fromBufferAttribute(position,old).applyMatrix4(object.matrixWorld);vertices.push(...p.toArray());
            const n=normal?new T.Vector3().fromBufferAttribute(normal,old).applyMatrix3(normalMatrix).normalize():new T.Vector3();normals.push(...n.toArray());
            const st=uv?new T.Vector2().fromBufferAttribute(uv,old):new T.Vector2();
            if(maps[0]){st.applyMatrix3(maps[0].matrix);if(!maps[0].flipY)st.y=1-st.y;}
            uvs.push(...st.toArray());
          }
          indices.push(next);
        }
        if(indices.length%3)throw Error('Native export needs triangulated geometry');
        triangles+=indices.length/3;
        if(triangles>1000000)throw Error('Optimize the authored model below one million triangles for mobile export');
        parts.push({material:material.id,positions:binary(new Float32Array(vertices)),normals:binary(new Float32Array(normals)),
          uvs:binary(new Float32Array(uvs)),indices:binary(new Uint32Array(indices))});
      }
    });
    if(parts.length)entities.push({id,label:tagged?.label??root.name,category:tagged?.category??inferred,kind:tagged?.kind??inferred,
      support_id:tagged?.supportId??null,collidable:tagged?.collidable??!inferred,parts});
  }
  return {format:'respace-threejs-export/1',entities,materials,textures,texture_sources:textureSources,triangles};
}
