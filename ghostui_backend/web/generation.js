
const generationToken='__GENERATION_TOKEN__';
// Never poll during a drag/write, overlap a read, or apply stale read results.
// refresh() also checks revision before rendering; it never locks sliders.
setInterval(()=>{
 if(document.hidden||busy||reading||editing||widgets.size===0||Date.now()-lastInteraction<2500)return;
 refresh(true);
},2500);
const help=document.querySelector('main > p:last-child small');
if(help)help.textContent='Send on release. Physical knob changes sync automatically while controls are idle.';
const panel=document.createElement('section');
const promptLabel=document.createElement('label');promptLabel.textContent='Interface style';
const prompt=document.createElement('input');prompt.type='text';prompt.value='Minimal controls, volume first; group bass and treble as Tone';prompt.maxLength=500;promptLabel.append(prompt);
const generateButton=document.createElement('button');generateButton.textContent='Generate interface';
const generationStatus=document.createElement('p');generationStatus.setAttribute('role','status');generationStatus.textContent='Initial layout: capability template. AI has not been called.';
panel.append(promptLabel,generateButton,generationStatus);document.querySelector('main').insertBefore(panel,document.querySelector('#controls'));
let generatingLayout=false;
let commandFeedbackUntil=0;
const originalRefresh=refresh;
refresh=async function(manual=false){
 if(generatingLayout)return;
 const message=status.textContent;
 const preserve=Date.now()<commandFeedbackUntil;
 await originalRefresh(manual);
 if(preserve&&!busy)status.textContent=message;
};
send=async function(c,w){
 if(busy)return;
 editing=false;interact();busy=true;disable(true);
 const value=Number(w.input.value);
 status.textContent='Sending '+c.label+' = '+value+'…';
 commandFeedbackUntil=Date.now()+60000;
 try{
 const state=await enqueue(()=>api('/command',{method:'POST',headers:{'Content-Type':'application/json','X-GhostUI-Token':token},body:JSON.stringify({capability:c.id,value})}));
 renderState(state);
 status.textContent='Confirmed by device: '+c.label+' = '+state[c.id];
 }catch(e){status.textContent='NOT CONFIRMED: '+e.message;}
 finally{busy=false;editing=false;lastInteraction=Date.now();commandFeedbackUntil=Date.now()+60000;disable(false);}
};
function applyLayout(layout){
 if(busy||editing)throw Error('Finish adjusting controls before applying a layout.');
 const capabilities=new Map(controls.map(c=>[c.id,c]));
 const fragment=document.createDocumentFragment();
 const nextWidgets=new Map();
 for(const item of layout.controls){
 const c=capabilities.get(item.bind);if(!c)throw Error('Unknown binding');
 const previous=widgets.get(c.id);
 const section=document.createElement('section');
 const group=document.createElement('small');group.textContent=item.group;
 const label=document.createElement('label');label.htmlFor=c.id;label.append(document.createTextNode(item.label));
 const out=document.createElement('output');out.textContent=previous?previous.out.textContent:'—';label.append(out);
 const input=document.createElement('input');input.type='range';input.id=c.id;input.min=c.min;input.max=c.max;input.step=c.step;
 input.value=previous?previous.input.value:c.min;input.disabled=previous?previous.input.disabled:true;
 const w={input,out};let dirty=false;
 const commit=()=>{editing=false;lastInteraction=Date.now();if(!dirty||busy)return;dirty=false;send(c,w);};
 input.addEventListener('pointerdown',()=>{editing=true;interact();});
 input.addEventListener('input',()=>{dirty=true;editing=true;interact();out.textContent=input.value;});
 input.addEventListener('change',commit);
 input.addEventListener('pointerup',commit);
 input.addEventListener('keyup',commit);
 input.addEventListener('blur',commit);
 input.addEventListener('pointercancel',()=>{dirty=false;editing=false;interact();});
 section.append(group,label,input);fragment.append(section);nextWidgets.set(c.id,w);
 }
 document.querySelector('#controls').replaceChildren(fragment);
 widgets.clear();for(const [id,w] of nextWidgets)widgets.set(id,w);
 document.querySelector('#name').textContent=layout.title;
}
generateButton.onclick=async()=>{
 if(busy||reading||editing){generationStatus.textContent='Wait for the current device interaction to finish.';return;}
 generateButton.disabled=true;generatingLayout=true;disable(true);generationStatus.textContent='Generating layout…';
 try{const result=await api('/generate',{method:'POST',headers:{'Content-Type':'application/json','X-Generation-Token':generationToken},body:JSON.stringify({preference:prompt.value})});applyLayout(result.layout);generationStatus.textContent=(result.source==='ai'?'AI · ':'TEMPLATE · ')+result.notice;}
 catch(e){generationStatus.textContent='Generation unavailable: '+e.message;}
 finally{generatingLayout=false;generateButton.disabled=false;if(!busy)disable(false);}
};
