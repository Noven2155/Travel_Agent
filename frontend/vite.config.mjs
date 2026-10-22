import {defineConfig} from 'vite';
import react from '@vitejs/plugin-react';
import {readFile,writeFile,mkdir,rename,unlink} from 'node:fs/promises';
import {randomUUID} from 'node:crypto';
import {resolve} from 'node:path';
// Managed preview runs in another network namespace. This local-only queue preserves the real Python API.
function localPythonBridge(){return {name:'python-comparison-preview',configureServer(server){
 const queue=resolve(process.env.TRAVEL_QUEUE_DIR||'runtime/preview-queue');
 server.middlewares.use(async(req,res,next)=>{
  if(process.env.TRAVEL_PREVIEW_BRIDGE!=='1'&&process.cwd()!=='/site'&&!req.headers.host?.startsWith('terminal.local'))return next();
  const path=req.url?.split('?')[0]||'';
  if(!path.startsWith('/api/'))return next();
  if(!/^\/api\/(health|catalog|scenarios|summary|model|comparisons(?:\/[a-f0-9-]{36}(?:\/export)?)?)$/.test(path)||!['GET','POST'].includes(req.method)){res.statusCode=404;res.end('{}');return;}
  const id=randomUUID(),input=resolve(queue,id+'.request.json'),output=resolve(queue,id+'.response.json');
  try{
   let body='';for await(const chunk of req){body+=chunk;if(body.length>25000)throw Error('Request too large');}
   await mkdir(queue,{recursive:true});await writeFile(input+'.tmp',JSON.stringify({method:req.method,path,body}));await rename(input+'.tmp',input);
   let result;const until=Date.now()+25000;
   while(Date.now()<until){try{result=JSON.parse(await readFile(output,'utf8'));break;}catch(e){if(e.code!=='ENOENT')throw e;}await new Promise(r=>setTimeout(r,60));}
   if(!result)throw Error('Python API not connected');
   res.statusCode=result.status;res.setHeader('Content-Type','application/json; charset=utf-8');res.end(result.body);
  }catch{res.statusCode=503;res.setHeader('Content-Type','application/json');res.end(JSON.stringify({detail:'Python API not connected'}));}
  finally{await Promise.all([unlink(input).catch(()=>{}),unlink(output).catch(()=>{})]);}
 });
}}}
export default defineConfig({plugins:[localPythonBridge(),react()],server:{allowedHosts:['terminal.local'],proxy:{'/api':'http://127.0.0.1:8025'},watch:{ignored:['**/runtime/**']}},build:{outDir:'dist'}});
