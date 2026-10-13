const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
function harness({port='80',respond=()=>({}),ok=true}={}) {
 const nodes=new Map(),calls=[],intervals=[];
 function element(){const classes=new Set();return {value:'',options:[],style:{},children:[],dataset:{},
  classList:{add(...v){v.forEach(x=>classes.add(x));},remove(...v){v.forEach(x=>classes.delete(x));},contains:v=>classes.has(v),toggle(v,on){if(on)classes.add(v);else classes.delete(v);}},
  addEventListener(){},contains(){return false;},removeAttribute(name){delete this[name];},setAttribute(){},
  replaceChildren(...v){this.children=v;this.options=v;},append(...v){this.children.push(...v);},appendChild(v){this.children.push(v);},add(v){this.options.push(v);},dispatchEvent(){},focus(){},reset(){}};}
 const node=selector=>{if(!nodes.has(selector))nodes.set(selector,element());return nodes.get(selector);};
 const context={module:{exports:{}},window:{location:{hostname:'localhost',protocol:'http:',port,href:`http://localhost:${port}/`}},
  document:{querySelector:node,querySelectorAll:()=>[],createElement:element,addEventListener(){}},localStorage:{getItem:()=>null,setItem(){},removeItem(){}},
  bootstrap:{Modal:class{show(){}hide(){}},Toast:class{show(){}}},Headers,FormData,URL,Event,console,
  Option:class{constructor(text,value){this.text=text;this.value=value;}},setTimeout:()=>1,clearTimeout(){},setInterval:fn=>{intervals.push(fn);return intervals.length;},clearInterval(){},
  fetch:async(url,options)=>{calls.push({url,options});return{ok,headers:new Headers({'content-type':'application/json'}),json:async()=>respond(url,options)};}};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../frontend/assets/app.js'),'utf8'),context);
 return {studio:context.module.exports,node,calls,intervals};
}
test('bookmark uses authenticated favorite route',async()=>{const {studio,calls}=harness();studio.state.token='test-token';await studio.bookmarkJob('job-a');assert.equal(calls[0].url,'/api/v1/prompts/favorites');assert.equal(JSON.parse(calls[0].options.body).job_id,'job-a');assert.equal(calls[0].options.headers.get('Authorization'),'Bearer test-token');});
test('login refreshes model and LoRA catalogues',async()=>{const {studio,calls}=harness({respond:url=>url.endsWith('/models')?{models:[]}:url.endsWith('/loras')?{loras:[]}:{jobs:[]}});studio.state.token='test-token';studio.setAuthenticated({username:'student'});await new Promise(r=>setImmediate(r));assert.ok(calls.some(c=>c.url.endsWith('/models')));assert.ok(calls.some(c=>c.url.endsWith('/loras')));});
test('health checks AI dependency rather than HTTP success',async()=>{const {studio,node}=harness({respond:()=>({status:'ok',dependencies:{ai_service:'unavailable'}})});await studio.checkHealth();assert.equal(node('.health-label').textContent,'AI unavailable');});
test('static localhost development server resolves Backend',async()=>{const {studio,calls}=harness({port:'8080'});studio.state.token='test-token';await studio.bookmarkJob('job-a');assert.equal(calls[0].url,'http://127.0.0.1:5000/api/v1/prompts/favorites');});
test('terminal jobs do not create timers',async()=>{for(const status of ['completed','cancelled','interrupted','failed']){const {studio,intervals}=harness({respond:()=>({job:{id:'job-a',status}})});await studio.pollJob('job-a');assert.equal(intervals.length,0);assert.equal(studio.state.activeJobId,null);}});
test('progress is scoped to owned job and clears stale preview',async()=>{const {studio,calls,node,intervals}=harness({respond:url=>url.includes('/progress?')?{job_id:'job-a',progress_percent:60,sampling_step:12,sampling_steps:20}:{job:{id:'job-a',status:'processing'}}});node('#jobLivePreviewImg').src='old-image';await studio.pollJob('job-a');assert.ok(calls.some(c=>c.url==='/api/v1/jobs/job-a/progress?include_preview=true'));assert.ok(!calls.some(c=>c.url==='/api/v1/progress?include_preview=true'));assert.equal(node('#jobLivePreviewImg').src,undefined);assert.equal(intervals.length,1);});
test('API surfaces structured server errors',async()=>{const {studio}=harness({ok:false,respond:()=>({error:{message:'Login required'}})});await assert.rejects(studio.api('/jobs'),/Login required/);});
test('one percent remains one percent',()=>{const {studio,node}=harness();studio.showJobProgress({id:'job-a',status:'processing',progress_percent:1});assert.equal(node('#jobProgressPercent').textContent,'1%');});
