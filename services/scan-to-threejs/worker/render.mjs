// Trusted, bounded browser operations. Authored source never runs in Node.
import { createServer } from 'vite';
import { chromium } from 'playwright';
import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';

const [project,requestFile,responseFile]=process.argv.slice(2);
const request=JSON.parse(await readFile(requestFile,'utf8'));
const errors=[];
const server=await createServer({configFile:resolve(project,'scan-viewer.config.ts'),
  server:{port:0,host:'127.0.0.1',strictPort:false,hmr:false,fs:{strict:true,allow:[resolve(project),resolve(import.meta.dirname,'../node_modules')]}},
  logLevel:'error'});
let browser;
try {
  await server.listen();
  const port=server.httpServer.address().port;
  const origin=`http://127.0.0.1:${port}`;
  browser=await chromium.launch({headless:true});
  const context=await browser.newContext({viewport:{width:1600,height:1600},serviceWorkers:'block'});
  await context.routeWebSocket('**/*',socket=>socket.close());
  await context.route('**/*',route=>{
    const url=new URL(route.request().url());
    return url.origin===origin?route.continue():route.abort();
  });
  const page=await context.newPage();
  let failPage;
  const pageFailure=new Promise((_,reject)=>{failPage=reject});
  // Attach the handler immediately; compile/runtime failures should be actionable
  // feedback, not 90-second waits that consume the room's processing window.
  pageFailure.catch(()=>{});
  page.on('pageerror',error=>{errors.push(error.message);failPage(error)});
  const ready=()=>Promise.race([page.waitForFunction(()=>document.body.dataset.ready==='1',null,{timeout:90000}),pageFailure]);
  const room=encodeURIComponent(request.room??'room');
  let result;
  if(request.operation==='export') {
    await page.goto(`${origin}/tools/worker.html?room=${room}`);
    await ready();
    result=await page.evaluate(()=>window.nativeScene);
  } else if(request.operation==='capture') {
    const query=new URLSearchParams({room:request.room??'room',src:request.source??'model',size:'540'});
    if(request.photo!==undefined)query.set('photo',String(request.photo));
    else {query.set('view',request.view??'top');query.set('ppm','130');}
    const target=request.source==='native'?'native':'capture';
    await page.goto(`${origin}/tools/${target}.html?${query}`);
    await ready();
    const wrap=page.locator('#wrap');
    const box=await wrap.boundingBox();
    if(!box||box.width>8192||box.height>8192)throw Error('Invalid capture dimensions');
    await page.setViewportSize({width:Math.ceil(box.width)+40,height:Math.ceil(box.height)+40});
    await wrap.screenshot({path:request.output});
    result={image:request.output,errors};
  } else throw Error('Unknown browser operation');
  if(errors.length)throw Error(errors.join('\n'));
  await writeFile(responseFile,JSON.stringify(result));
} catch(error) {
  await writeFile(responseFile,JSON.stringify({error:String(error),console_errors:errors}));
  process.exitCode=1;
} finally {await browser?.close();await server.close();}
