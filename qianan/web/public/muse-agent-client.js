/* 千岸：在当前对话内确认商品、生成物料、复检与导出。 */
'use strict';
if (location.protocol === 'file:') location.replace('http://localhost:3001/muse-pure-css.html');
const API_BASE = window.QIANAN_API_BASE || (['localhost','127.0.0.1'].includes(location.hostname) ? 'http://localhost:8001' : '');
const PLATFORM_NAMES = {amazon:'Amazon',shopee:'Shopee',aliexpress:'AliExpress',lazada:'Lazada',tiktokshop:'TikTok Shop'};
const TOOL_NAMES = {understand_product:'理解商品',generate_listing:'生成平台文案',review_listing:'合规检查',revise_listing:'修订文案',generate_images:'生成商品图片',generate_video:'生成视频',submit_plan:'制定上新策略',recall_memory:'参考历史经验',self_reflect:'总结本轮经验',submit_deliverable:'整理交付物'};
const chatHistory = [];
let attachment = null, productImage = null, busy = false, currentRun = null, attachmentVersion = 0;
let brief = {name:'', facts:'', market:'', category:'home_kitchen', platforms:[], confirmed:false};
let pendingBrief = null;
const $ = id => document.getElementById(id);
const initialWelcome = $('threadScroll').innerHTML;
function element(tag, text, className) { const node=document.createElement(tag); if(text!==undefined) node.textContent=String(text); if(className)node.className=className;return node; }
function showNotice(text) { $('agentNotice').textContent=text; }
function usePrompt(text){$('userInput').value=text;$('userInput').focus();}
function newConversation(){if(busy){showNotice('请先停止当前生成。');return;}chatHistory.length=0;currentRun=null;productImage=null;brief={name:'',facts:'',market:'',category:'home_kitchen',platforms:[],confirmed:false};pendingBrief=null;removeAttachment();$('threadScroll').innerHTML=initialWelcome;$('contextBar').hidden=true;$('userInput').value='';showNotice('由你确认商品事实，由千岸处理平台差异。');}
function agentReply(text){$('welcomeMessage')?.remove();const row=element('div',undefined,'agent-row'),reply=element('div',undefined,'agent-content');row.append(element('div','✦','agent-avatar'),reply);$('threadScroll').append(row);if(text)textBlock(reply,text);$('threadScroll').scrollTop=$('threadScroll').scrollHeight;return reply;}
function userMessage(text,image){$('welcomeMessage')?.remove();const row=element('div',undefined,'user-row'),bubble=element('div',undefined,'user-bubble');if(image){const img=element('img');img.src=image.data;img.alt=image.name;img.style='max-width:160px;max-height:120px;display:block;border-radius:10px';bubble.append(img);}textBlock(bubble,text);row.append(bubble);$('threadScroll').append(row);}
function updateContext(){const bar=$('contextBar');bar.hidden=!brief.confirmed;if(!brief.confirmed)return;const edit=element('button','调整');edit.onclick=()=>{if(busy){showNotice('等待本轮结束后再调整。');return;}confirmBrief('',false);};bar.replaceChildren(element('span',brief.name+' · '+brief.platforms.map(p=>PLATFORM_NAMES[p]).join(' / ')),edit);}
function headers(){const h={'Content-Type':'application/json'};try{const token=localStorage.getItem('qa_cb_token');if(token)h.Authorization='Bearer '+token;for(const [key,name] of [['qianan_byok_key','X-Bailian-Api-Key'],['qianan_byok_dashscope_key','X-Dashscope-Api-Key']]){const v=localStorage.getItem(key);if(v)h[name]=v;}}catch{showNotice('浏览器无法读取登录信息，请在账户页重新登录。');}return h;}
async function request(path, options={}){const res=await fetch(API_BASE+path,{...options,headers:{...headers(),...options.headers}});if(!res.ok){let message;try{const body=await res.json();message=typeof body.detail==='string'?body.detail:JSON.stringify(body.detail);}catch{}throw new Error(message||`请求失败（${res.status}）`);}return res;}
function removeAttachment(){attachmentVersion++;attachment=null;$('imageInput').value='';$('attachmentPreview').replaceChildren();$('attachmentPreview').hidden=true;}
function attachImage(input){const file=input.files?.[0];if(!file)return;if(busy)return;if(!['image/jpeg','image/png','image/webp'].includes(file.type)||file.size>12*1024*1024){showNotice('请选择不超过 12 MB 的 JPG、PNG 或 WebP 商品图。');input.value='';return;}const version=++attachmentVersion;const reader=new FileReader();reader.onerror=()=>showNotice('图片读取失败，请重新选择。');reader.onload=()=>{if(version!==attachmentVersion)return;attachment={name:file.name,data:reader.result};const img=element('img');img.src=attachment.data;img.alt='待发送商品图';const remove=element('button','移除','btn-copy');remove.onclick=removeAttachment;$('attachmentPreview').replaceChildren(img,element('span',file.name+' '),remove);$('attachmentPreview').hidden=false;};reader.readAsDataURL(file);}
function setBusy(value){busy=value;const send=document.querySelector('.btn-send');send.textContent=value?'■':'↑';send.setAttribute('aria-label',value?'停止生成':'发送');send.onclick=value?stopAgent:sendUserMessage;document.querySelector('.btn-plus').disabled=value;$('imageInput').disabled=value;document.querySelectorAll('[data-idle-only]').forEach(button=>button.disabled=value);}
function followScroll(){const scroll=$('threadScroll');if(scroll.scrollHeight-scroll.scrollTop-scroll.clientHeight<180)scroll.scrollTop=scroll.scrollHeight;}
function textBlock(target,text){const p=element('p',text);target.append(p);return p;}
async function copy(text,button){try{await navigator.clipboard.writeText(text);button.textContent='已复制';}catch{showNotice('复制失败，请手动选择文案复制。');}}
function safeURL(value){try{const url=new URL(value,location.origin);return ['http:','https:'].includes(url.protocol)?url.href:null;}catch{return null;}}
function renderArtifacts(run){if(!run.card){run.card=element('div',undefined,'artifact-card');run.reply.append(run.card);}run.card.replaceChildren(element('strong',`本轮上新物料 · ${run.listings.size} 个平台`));for(const item of run.listings.values()){
 const section=element('section');section.append(element('h4',item.display_name||PLATFORM_NAMES[item.platform]||item.platform));
 section.append(element('p',item.compliance_passed===true?`规则检查通过 · ${item.compliance_warns||0} 项提示`:`待核查 · ${item.compliance_errors||0} 项错误，${item.compliance_warns||0} 项提示`,'quiet'));
 textBlock(section,item.title||'标题生成中…');const list=element('ul');for(const bullet of item.bullets||[])list.append(element('li',bullet));section.append(list);
 if(item.description){const detail=element('details');detail.append(element('summary','描述预览'));textBlock(detail,item.description);section.append(detail);}
 if(item.search_terms||item.attributes||item.aplus){const details=element('details',undefined,'tool-log');details.append(element('summary','搜索词、商品属性与 A+ 内容'));if(item.search_terms)textBlock(details,'搜索词：'+item.search_terms);for(const [key,value] of Object.entries(item.attributes||{}))textBlock(details,key+'：'+value);for(const module of item.aplus||[]){textBlock(details,module.title||module.type);if(module.text)textBlock(details,module.text);for(const entry of module.items||[])textBlock(details,Object.values(entry).join(' · '));}section.append(details);}
 const images=element('div',undefined,'asset-images');for(const source of [...(item.images||[]),...(item.detail_images||[])]){const url=safeURL(source);if(!url)continue;const link=element('a');link.href=url;link.onclick=event=>{event.preventDefault();$('previewImage').src=url;$('imagePreview').showModal();};const img=element('img');img.src=url;img.alt='生成的商品物料，点击查看原图';link.append(img);images.append(link);}section.append(images);
 const actions=element('div',undefined,'artifact-actions');const copyButton=element('button','复制文案','btn-copy');copyButton.onclick=()=>copy([item.title,...(item.bullets||[]),item.description,item.search_terms].filter(Boolean).join('\n\n'),copyButton);actions.append(copyButton);
 const revise=element('button','提出修改','btn-copy');revise.onclick=()=>usePrompt(`请修改 ${item.display_name||item.platform} 的文案：`);actions.append(revise);actions.append(action('检查 / 编辑',()=>editListing(run,item)),action('查看规则依据',()=>showRules(item.platform)));section.append(actions);run.card.append(section);
 }
 if(run.taskId){const actions=element('div',undefined,'artifact-actions');const full=action('展开完整物料',()=>loadFull(run));const download=action('下载本轮上架包',()=>exportPackage(run));actions.append(full,download);run.card.append(actions);} }
function mergeListings(run,items,full=false){for(const item of items){if(!item?.platform)continue;const previous=run.listings.get(item.platform)||{};const merged={...previous,...item}; // periodic snapshots contain shorter previews; retain richer details from incremental events.
 if(full&&previous.description?.length>item.description?.length)merged.description=previous.description;
 run.listings.set(item.platform,merged);}if(run.listings.size)renderArtifacts(run);}
function renderEvidence(run,event){if(!run.evidence){run.evidence=element('details',undefined,'tool-log');run.evidence.append(element('summary','查看规划、记忆与反思'));run.reply.append(run.evidence);}const content=element('div');if(event.plan?.strategy)textBlock(content,'上新策略：'+event.plan.strategy);for(const memory of event.memory_recall||[])textBlock(content,'参考经验：'+memory.lesson);for(const reflection of event.reflections||[])textBlock(content,'本轮总结：'+reflection.lesson);run.evidence.replaceChildren(element('summary','查看规划、记忆与反思'),content);}
function onEvent(run,event){switch(event.type){
 case 'init':run.taskId=event.task_id;break;
 case 'text_delta':if(!run.delta){run.delta=textBlock(run.reply,'');}run.delta.textContent+=event.content||'';run.response+=event.content||'';break;
 case 'text':run.delta=null;if(event.content){textBlock(run.reply,event.content);run.response+=event.content+'\n';}break;
 case 'trace':{run.delta=null;const signature=JSON.stringify(event);if(run.traces.has(signature))break;run.traces.add(signature);if(!run.tools){run.tools=element('details',undefined,'tool-log');run.tools.append(element('summary','实际执行记录'));run.reply.append(run.tools);}const name=TOOL_NAMES[event.tool]||event.tool||'上新任务';const result=event.result||event.result_summary||'';textBlock(run.tools,`${name} · ${typeof result==='string'?result:JSON.stringify(result)}`);run.status.textContent='处理中 · '+name;break;}
 case 'listing':case 'listing_update':mergeListings(run,event.listings||[event]);break;
 case 'listing_full':mergeListings(run,event.listings||[],true);renderEvidence(run,event);if(event.stage&&!run.done)run.status.textContent=event.stage;break;
 case 'done':run.done=true;run.finalStatus=event.status;run.taskId=event.task_id||run.taskId;run.status.textContent=({done:'本轮已完成，请核对物料后导出',partial:'部分完成，请检查缺失物料',cancelled:'本轮已停止',failed:'本轮执行失败'})[event.status]||'本轮已结束';if(event.summary){run.status.textContent+=' · '+event.summary;}break;
 case 'error':throw new Error(event.message||'任务执行失败');
 }followScroll();}
async function executeGeneration(messageOverride,alreadyShown=false){const text=messageOverride||$('userInput').value.trim();if(busy||(!text&&!attachment))return;const platforms=brief.platforms;
 const image=attachment;if(image)productImage=image;const message=text||'请根据已确认商品资料生成上架物料';if(!alreadyShown)userMessage(message,image);
 const agent=element('div',undefined,'agent-row'),reply=element('div',undefined,'agent-content');agent.append(element('div','✦','agent-avatar'),reply);$('threadScroll').append(agent);
 const run={reply,status:textBlock(reply,'正在连接千岸上新 Agent…'),controller:new AbortController(),listings:new Map(),traces:new Set(),response:'',taskId:null,done:false,stopping:false};currentRun=run;run.status.className='quiet';
 const previousArtifacts=chatHistory.length?chatHistory[chatHistory.length-1].artifacts:null;
 const context=chatHistory.slice(-8).map(m=>`${m.role==='user'?'卖家':'千岸'}：${m.content.slice(0,3000)}`).join('\n');
 chatHistory.push({role:'user',content:message});$('userInput').value='';removeAttachment();setBusy(true);showNotice('');$('threadScroll').scrollTop=$('threadScroll').scrollHeight;
 try{const res=await request('/api/chat',{method:'POST',signal:run.controller.signal,body:JSON.stringify({message:['已确认商品资料：'+JSON.stringify(brief)+'。仅使用已确认事实，不可编造参数。',context,previousArtifacts?'上轮物料：'+JSON.stringify(previousArtifacts).slice(0,18000):'', '当前需求：'+message].filter(Boolean).join('\n\n'),product_name:brief.name.slice(0,200),selling_points:brief.facts.slice(0,2000),category:brief.category,platforms,...(productImage?{image_base64:productImage.data}:brief.image_url?{image_url:brief.image_url}:{})})});if(!res.body)throw new Error('服务未返回对话流');const reader=res.body.getReader(),decoder=new TextDecoder();let buffer='';
 const consume=line=>{if(!line.startsWith('data:'))return;const raw=line.slice(5).trim();if(!raw)return;let event;try{event=JSON.parse(raw);}catch{throw new Error('对话数据格式异常，请重试');}onEvent(run,event);};
 while(true){const {value,done}=await reader.read();if(done){buffer+=decoder.decode();if(buffer.trim())consume(buffer);break;}buffer+=decoder.decode(value,{stream:true});let end;while((end=buffer.indexOf('\n'))>=0){consume(buffer.slice(0,end).replace(/\r$/,''));buffer=buffer.slice(end+1);}}
 if(!run.done)throw new Error('连接已中断，尚未收到完成回执');
 }catch(error){run.status.textContent=error.name==='AbortError'?'已断开本轮接收；服务端停止状态见提示。':'本轮未完成：'+error.message;}
 finally{chatHistory.push({role:'assistant',content:run.response||run.status.textContent,artifacts:Array.from(run.listings.values())});run.finished=true;if(!run.stopping)setBusy(false);}
}
async function stopAgent(){const run=currentRun;if(!busy||!run||run.stopping)return;if(!run.taskId){showNotice('正在建立连接，收到任务编号后可停止服务端任务。');return;}run.stopping=true;try{await request('/api/chat/'+encodeURIComponent(run.taskId)+'/cancel',{method:'POST'});showNotice('已请求服务端停止，当前工具结束后取消后续执行。');run.controller.abort();}catch(e){showNotice('停止请求失败：'+e.message+'。请再次点击停止。');}finally{run.stopping=false;if(run.finished)setBusy(false);}}
async function exportPackage(run=currentRun){if(busy||!run?.taskId||!run.listings.size)return;try{const res=await request('/api/files/'+encodeURIComponent(run.taskId)+'/zip');const blob=await res.blob(),url=URL.createObjectURL(blob),a=element('a');a.href=url;a.download='千岸-'+run.taskId+'.zip';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);showNotice('已下载上架包，请核对平台审核结果。');}catch(e){showNotice('导出失败：'+e.message+'。请稍后在此重试。');}}

function action(label, handler, primary=false) {
  const button=element('button',label,'btn-copy'+(primary?' primary':''));
  button.dataset.idleOnly='true';button.disabled=busy;
  button.onclick=()=>{if(!busy)handler();};return button;
}
function field(container,label,value,kind='input') {
  const wrapper=element('label',label),input=element(kind);
  input.value=value||'';wrapper.append(input);container.append(wrapper);return input;
}
function inferPlatforms(text) {
  const aliases={amazon:/amazon|亚马逊/i,shopee:/shopee|虾皮/i,aliexpress:/aliexpress|速卖通/i,lazada:/lazada|来赞达/i,tiktokshop:/tiktok/i};
  return Object.keys(aliases).filter(key=>aliases[key].test(text));
}
function confirmBrief(message,generate=true) {
  if(busy)return;
  if(pendingBrief){pendingBrief.card.remove();pendingBrief=null;}
  const reply=agentReply(generate?'先对齐这次上新的商品事实与目标。缺少的参数不会替你编造；确认后，我再按各平台规范制作物料。':'在这里调整当前商品资料，后续生成会使用新的信息。');
  const card=element('div',undefined,'inline-card');card.append(element('strong','本次上新 · 商品确认'));
  const name=field(card,'商品名称',brief.name||'', 'input');name.placeholder='例如：350ml 便携榨汁杯';
  const facts=field(card,'已知卖点与规格',brief.facts||message,'textarea');facts.placeholder='材质、容量、尺寸、功能；只填写能确认的信息';
  const grid=element('div',undefined,'form-grid');card.append(grid);
  const market=field(grid,'目标市场',brief.market);market.placeholder='例如：美国 / 泰国';
  const category=field(grid,'商品类目','','select');
  for(const [value,label] of [['home_kitchen','家居厨具'],['electronics','消费电子'],['apparel','服装配饰']]){const option=element('option',label);option.value=value;category.append(option);}category.value=brief.category;
  card.append(element('p','目标平台 · 只为选中的平台生成','quiet'));
  const targets=new Set(brief.platforms.length?brief.platforms:inferPlatforms(message));const pills=element('div',undefined,'platform-pills');
  for(const [value,label] of Object.entries(PLATFORM_NAMES)){const button=element('button',label);button.setAttribute('aria-pressed',String(targets.has(value)));button.onclick=()=>{if(targets.has(value))targets.delete(value);else targets.add(value);button.setAttribute('aria-pressed',String(targets.has(value)));};pills.append(button);}card.append(pills);
  const status=element('p','','quiet');card.append(status);
  const submit=action(generate?'确认资料，开始制作':'保存商品资料',()=>{
    if(!name.value.trim()||!facts.value.trim()||!market.value.trim()||!targets.size){status.textContent='请补充商品名称、真实卖点、目标市场，并选择至少一个平台。';return;}
    brief={name:name.value.trim(),facts:facts.value.trim(),market:market.value.trim(),category:category.value,platforms:[...targets],confirmed:true};
    pendingBrief=null;card.replaceChildren(element('strong','已确认 · '+brief.name),element('p',brief.market+' / '+brief.platforms.map(p=>PLATFORM_NAMES[p]).join('、'),'quiet'),element('p',brief.facts));updateContext();
    if(generate)executeGeneration(message||'根据确认的商品资料制作各平台上架物料。',true);
  },true);card.append(submit);reply.append(card);pendingBrief={card,facts};$('threadScroll').scrollTop=$('threadScroll').scrollHeight;
}
function sendUserMessage() {
  if(busy)return;const text=$('userInput').value.trim();if(!text&&!attachment)return;
  if(!attachment&&/^(查看|打开)?(历史上新|历史任务|已有商品|物料库)$/.test(text)){userMessage(text);$('userInput').value='';showHistory();return;}
  if(!attachment&&/^(查看|检查)?(平台规则|规则依据)$/.test(text)){userMessage(text);$('userInput').value='';showRules(brief.platforms[0]||'amazon');return;}
  if(!attachment&&/^(检查|审核)(现有)?\s*(listing|文案)$/i.test(text)){userMessage(text);$('userInput').value='';startAudit();return;}
  if(!brief.confirmed||pendingBrief){
    userMessage(text||'我想根据这张商品图准备上新。',attachment);
    if(attachment){productImage=attachment;removeAttachment();}
    if(pendingBrief){pendingBrief.facts.value+=(pendingBrief.facts.value?'\n':'')+text;showNotice('补充内容已加入商品确认卡，请核对后开始制作。');$('userInput').value='';return;}
    brief.facts=text;brief.platforms=inferPlatforms(text);
    const markets=['美国','英国','日本','泰国','马来西亚','印尼','新加坡','菲律宾','越南','德国','法国'];brief.market=markets.filter(m=>text.includes(m)).join(' / ');
    const opening=text.split(/[，,。\n]/)[0].replace(/^(帮我|我有一款|我有|这是一款)/,'').trim();if(opening.length>2&&!/商品|上新|检查|你好|请/.test(opening))brief.name=opening.slice(0,100);$('userInput').value='';confirmBrief(text);return;
  }
  executeGeneration();
}
async function loadFull(run) {
  const reply=agentReply('正在读取本轮完整物料…');
  try{const data=await (await request('/api/tasks/'+encodeURIComponent(run.taskId))).json();mergeListings(run,data.listings||[]);run.fullLoaded=true;reply.replaceChildren(element('p','完整文案、图片和检查结果已更新到本轮物料卡。'));}
  catch(error){reply.replaceChildren(element('p','读取失败：'+error.message));}
}
async function showHistory() {
  if(busy){showNotice('请等待当前任务结束后再切换商品。');return;}
  const reply=agentReply('我来找一下已保存的上新物料。');
  try{const data=await(await request('/api/files')).json();reply.replaceChildren(element('p','选择一件商品，物料会直接回到这段对话。'));
    if(!data.packages?.length){textBlock(reply,'还没有已保存的上新物料。可以先发商品资料，开始第一件上新。');return;}
    const card=element('div',undefined,'inline-card');for(const pkg of data.packages.slice(0,30)){const button=action(pkg.product_name||pkg.task_id,()=>restoreTask(pkg.task_id));button.className='history-item';card.append(button);}reply.append(card);
  }catch(error){textBlock(reply,'暂时无法读取历史物料：'+error.message);}
}
async function restoreTask(taskId) {
  if(busy)return;setBusy(true);const reply=agentReply('正在恢复商品资料和物料…');
  try{const data=await(await request('/api/tasks/'+encodeURIComponent(taskId))).json();const req=data.request||{};pendingBrief?.card.remove();pendingBrief=null;
    brief={name:req.product_name||'历史商品',facts:req.selling_points||'',market:'沿用历史任务市场',category:req.category||'home_kitchen',platforms:req.platforms||data.listings.map(x=>x.platform),confirmed:true};
    productImage=req.image_base64?{name:'历史商品图',data:req.image_base64}:null;brief.image_url=req.image_url||null;
    chatHistory.length=0;chatHistory.push({role:'user',content:brief.name+'：'+brief.facts},{role:'assistant',content:'已恢复历史物料',artifacts:data.listings||[]});
    const run={reply,listings:new Map(),taskId,finished:true,done:true,traces:new Set(),response:'',fullLoaded:true};currentRun=run;reply.replaceChildren(element('p','已恢复 '+brief.name+'。可以继续提出修改，或在物料卡里编辑和复检。'));mergeListings(run,data.listings||[]);updateContext();
  }catch(error){textBlock(reply,'恢复失败：'+error.message);}finally{setBusy(false);}
}
async function showRules(platform) {
  const reply=agentReply('正在读取平台规则库…');
  try{const data=await(await request('/api/rules')).json();const rules=Array.isArray(data)?data:Object.values(data);const rule=rules.find(x=>x.platform===platform);if(!rule)throw new Error('未找到该平台规则');
    reply.replaceChildren(element('p',(PLATFORM_NAMES[platform]||platform)+' · 当前规则库依据'));
    const card=element('div',undefined,'inline-card');for(const [key,title] of [['title','标题'],['bullets','卖点'],['mainImage','主图'],['requiredAttributes','必填属性']]){if(rule[key]){const details=element('details',undefined,'tool-log');details.append(element('summary',title));textBlock(details,JSON.stringify(rule[key],null,2));card.append(details);}}
    textBlock(card,'来源：'+(rule.source||'项目规则库')+' · 更新：'+(rule.updated||'未标注'));textBlock(card,'这是当前内置规则的依据，并非平台实时政策保证。');reply.append(card);
  }catch(error){textBlock(reply,'规则读取失败：'+error.message);}
}
function startAudit(){if(busy)return;editListing(null,{platform:brief.platforms[0]||'amazon',title:'',bullets:[],description:'',attributes:{},images:[]});}
async function editListing(run,item) {
  if(busy)return;
  // SSE only carries excerpts. Fetch full fields before editing so a save cannot truncate the source.
  if(run&&!run.fullLoaded){try{const data=await(await request('/api/tasks/'+encodeURIComponent(run.taskId))).json();mergeListings(run,data.listings||[]);run.fullLoaded=true;item=run.listings.get(item.platform)||item;}catch(error){agentReply('完整文案尚未读取，暂不打开编辑，避免覆盖成截断版本：'+error.message);return;}}
  const reply=agentReply('在这里编辑文案并复检。检查会指出具体字段；改好的草稿可以直接下载。');
  const card=element('div',undefined,'inline-card');const platform=field(card,'目标平台','','select');for(const [key,name]of Object.entries(PLATFORM_NAMES)){const option=element('option',name);option.value=key;platform.append(option);}platform.value=item.platform;platform.disabled=!!run;
  const title=field(card,'标题',item.title),bullets=field(card,'卖点 · 每行一条',(item.bullets||[]).join('\n'),'textarea'),description=field(card,'商品描述',item.description,'textarea');
  const advanced=element('details',undefined,'tool-log');advanced.append(element('summary','补充商品属性与图片'));card.append(advanced);
  const attributes=field(advanced,'商品属性 · 每行 名称：值',Object.entries(item.attributes||{}).map(([key,value])=>key+'：'+value).join('\n'),'textarea');const images=field(advanced,'图片地址 · 每行一个',(item.images||[]).join('\n'),'textarea');
  const status=element('div');const actions=element('div',undefined,'inline-actions');card.append(status,actions);reply.append(card);
  let revision=0,checkedRevision=-1,lastDraft=null;
  for(const control of [platform,title,bullets,description,attributes,images])control.oninput=()=>{revision++;checkedRevision=-1;save.disabled=true;status.replaceChildren(element('p','草稿已修改，请重新检查。','quiet'));};
  const check=action('检查这份草稿',async()=>{const version=revision;check.disabled=true;save.disabled=true;status.replaceChildren(element('p','正在检查标题、卖点、图片和必填属性…','quiet'));
    try{const attrs=Object.create(null);for(const line of attributes.value.split('\n').filter(x=>x.trim())){const index=line.search(/[:：]/);if(index<1)throw new Error('请按“属性名称：值”填写商品属性');attrs[line.slice(0,index).trim()]=line.slice(index+1).trim();}
      const draft={...item,platform:platform.value,title:title.value,bullets:bullets.value.split('\n').filter(Boolean),description:description.value,attributes:attrs,images:images.value.split('\n').filter(Boolean),category:brief.category};
      const report=await(await request('/api/audit',{method:'POST',body:JSON.stringify(draft)})).json();if(version!==revision)return;
      checkedRevision=version;lastDraft={...draft,compliance:report.issues||[],compliance_passed:report.passed};status.replaceChildren(element('p',report.passed?'规则检查通过。请继续核对商品事实。':'发现需要处理的问题：'));
      for(const issue of report.issues||[]){const fieldName=({title:'标题',bullets:'卖点',mainImage:'主图',images:'图片',description:'描述',attributes:'商品属性',search_terms:'搜索词'})[issue.field]||issue.field;textBlock(status,`${issue.severity==='error'?'需修复':'提示'} · ${fieldName}：${issue.message}`);}save.disabled=false;
    }catch(error){status.replaceChildren(element('p','检查失败：'+error.message));}finally{check.disabled=false;}
  },true);
  const save=action('下载编辑稿（JSON）',()=>{if(checkedRevision!==revision||!lastDraft)return;downloadJSON(lastDraft,platform.value+'-编辑稿.json');showNotice('已下载含检查结果的编辑稿；原始生成包未被覆盖。');});save.disabled=true;delete save.dataset.idleOnly;
  actions.append(check,save);if(run)actions.append(action('让千岸继续修改',()=>{usePrompt(`请针对 ${PLATFORM_NAMES[item.platform]} 修改文案。要求：`);showNotice('在输入框补充修改要求，千岸将生成新一轮物料。');}));$('threadScroll').scrollTop=$('threadScroll').scrollHeight;
}
function downloadJSON(data,name){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=element('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
setBusy(false);
