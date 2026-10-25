import '../src/asset-base';
import { roomById } from '../../../demos';
import { exportNative } from '../../../runtime-export';
const room=await roomById(new URLSearchParams(location.search).get('room')).build();
Object.assign(window,{nativeScene:exportNative(room)});
document.body.dataset.ready='1';
