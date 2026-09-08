(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const native = !!window.Capacitor?.isNativePlatform?.();
  const demo = new URLSearchParams(location.search).has('demo');
  let address = localStorage.getItem('g1.address') || (native ? 'http://10.42.0.1:8787' : location.origin);
  let library = [], motions = [], selected = null, pendingMotion = null, filter = 'all', connected = false, busy = false, polling = false, robotBusy = false;
  let status = {state:'idle', routine_id:null, robot_connected:false}, audioOutput=localStorage.getItem('g1.audio-output')||'bluetooth', toastTimer;
  const events = [];
  const demoLibrary = ['Midnight motion','Electric soul','After hours','Golden groove','Neon steps','Slow orbit'].map((name,i) => ({id:'session-'+i,name:['Clap & Wave','Heart Greeting','Evening Flow','Golden Hour','Neon Shuffle','Slow Orbit'][i],song_title:name,audio:i===5?null:'track.mp3',artwork_url:null}));
  const demoMotions = [
    ['high-wave','Wave','👋'],['shake-hand','Shake hand','🤝'],['high-five','High five','✋'],['clap','Clap','👏'],
    ['hug','Hug','🫂'],['heart','Heart','🫶'],['right-heart','Right heart','♡'],['face-wave','Face wave','🙋'],
    ['hands-up','Hands up','🙌'],['right-hand-up','Right hand up','☝'],['reject','Reject','🙅'],['x-ray','X-ray','🩻'],
    ['left-kiss','Left kiss','💋'],['right-kiss','Right kiss','💋'],['two-hand-kiss','Two-hand kiss','😘'],['release-arm','Release arms','↔']
  ].map(([id,name,icon])=>({id,name,icon}));
  function log(text) { events.unshift(new Date().toLocaleTimeString()+'  '+text); $('logs').textContent = events.slice(0,80).join('\n'); }
  function toast(text) { $('toast').textContent=text; $('toast').hidden=false; clearTimeout(toastTimer); toastTimer=setTimeout(()=>$('toast').hidden=true,5000); log(text); }
  function connection(serviceOk, robotOk=status.robot_connected===true) {
    connected=serviceOk;
    status.robot_connected=serviceOk&&robotOk;
    const state=robotBusy?'connecting':status.robot_connected?'online':'offline';
    document.querySelectorAll('[data-robot-status]').forEach(label=>{label.textContent=robotBusy?'● Connecting…':status.robot_connected?'● Robot online':'● Robot offline';label.className='status-'+state;});
    document.querySelectorAll('[data-connect-robot]').forEach(button=>{button.textContent=status.robot_connected?'Connected':'Connect robot';button.disabled=robotBusy||status.robot_connected;});
    renderPlayer();
    renderMotions();
  }
  function fallback(r) { const hue = [...r.id].reduce((n,c)=>n+c.charCodeAt(0),0)*29%360; const svg=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 600 600"><defs><linearGradient id="g" x2="1" y2="1"><stop stop-color="hsl(${hue},60%,36%)"/><stop offset="1" stop-color="hsl(${(hue+65)%360},70%,12%)"/></linearGradient></defs><path d="M0 0h600v600H0z" fill="url(#g)"/><g fill="none" stroke="hsl(${(hue+30)%360},90%,76%)" stroke-width="26" opacity=".85"><ellipse cx="300" cy="300" rx="210" ry="85" transform="rotate(-30 300 300)"/><ellipse cx="300" cy="300" rx="210" ry="85" transform="rotate(30 300 300)"/><ellipse cx="300" cy="300" rx="210" ry="85" transform="rotate(90 300 300)"/></g><circle cx="300" cy="300" r="30" fill="#efffea"/></svg>`;return 'data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svg); }
  function art(r){return r?.artwork_url ? address+r.artwork_url : r?fallback(r):'assets/app_icon.png';}
  async function request(path, method='GET', body, headers={}) {
    const controller=new AbortController(), timer=setTimeout(()=>controller.abort(),12000);
    try { const response=await fetch(address+path,{method,body,headers,signal:controller.signal}); const result=await response.json();if(!response.ok)throw Error(result.error||'Request failed');return result;} finally {clearTimeout(timer);}
  }
  function renderCards(){
    const search=$('search').value.toLowerCase(); $('cards').replaceChildren(); $('count').textContent=library.length;
    const visible=library.filter(r=>(r.name+' '+r.song_title).toLowerCase().includes(search)&&(filter==='all'||(filter==='music'?!!r.audio:!r.audio)));
    visible.forEach(r=>{const tile=document.createElement('button');tile.className='tile'+(selected?.id===r.id?' selected':'');tile.setAttribute('aria-label','Select '+(r.song_title||r.name));tile.setAttribute('aria-pressed',selected?.id===r.id?'true':'false');
      const cover=document.createElement('div');cover.className='cover'; const img=document.createElement('img'); img.src=art(r);img.alt='Cover for '+(r.song_title||r.name);img.loading='lazy';img.onerror=()=>{img.onerror=null;img.src=fallback(r);};cover.append(img);
      const title=document.createElement('strong');title.textContent=r.song_title||r.name;const sub=document.createElement('small');sub.textContent=r.audio?r.name+' · MP3':'Add a song · '+r.name;tile.append(cover,title,sub);tile.onclick=()=>{selected=r;renderCards();renderPlayer();};$('cards').append(tile);
    });
    $('empty').hidden=visible.length>0;
    $('empty').querySelector('h3').textContent=library.length?'No tracks match this view.':'Your next session starts here.';
  }
  function renderMotions(){
    const list=$('motion-list');list.replaceChildren();$('motion-count').textContent=motions.length;
    const active=status.state==='playing'||status.state==='paused';
    motions.forEach(m=>{const tile=document.createElement('button');tile.className='motion-card';tile.disabled=!connected||(!demo&&!status.robot_connected)||busy||active;tile.setAttribute('aria-label','Start '+m.name+' motion');
      const icon=document.createElement('span');icon.className='motion-icon';icon.setAttribute('aria-hidden','true');icon.textContent=m.icon;
      const name=document.createElement('strong');name.textContent=m.name;tile.append(icon,name);tile.onclick=()=>openMotionConfirm(m);list.append(tile);
    });
  }
  function renderPlayer(){const active=status.state==='playing'||status.state==='paused';const current=library.find(r=>r.id===status.routine_id);const shown=active&&current?current:selected;
    $('now-art').src=art(shown);$('now-title').textContent=shown?.song_title||shown?.name||'Choose your next track';$('now-subtitle').textContent=shown?shown.name:'Select a tile to get started';
    $('toggle').textContent=status.state==='playing'?'Ⅱ':'▶';$('toggle').setAttribute('aria-label',status.state==='playing'?'Pause dance':status.state==='paused'?'Resume dance':'Start dance');
    $('toggle').disabled=!connected||(!demo&&!status.robot_connected)||busy||(!active&&!selected);$('stop').disabled=!connected||(!active&&status.state!=='error');$('edit').disabled=!selected||busy;
  }
  async function refresh(){try{if(demo){library=demoLibrary;motions=demoMotions;status={...status,robot_connected:false};}else{const [result,motionResult,latest,settings]=await Promise.all([request('/api/routines'),request('/api/motions').catch(()=>({motions:[]})),request('/api/status'),request('/api/settings').catch(()=>({audio_output:audioOutput}))]);library=result.routines;motions=motionResult.motions;status=latest;setAudioOutput(settings.audio_output);}selected=library.find(r=>r.id===selected?.id)||library[0]||null;connection(true,status.robot_connected);renderCards();renderPlayer();log('Library refreshed: '+library.length+' dances');}catch(e){connection(false,false);toast('Could not connect. Join the G1 hotspot and check Settings.');renderCards();renderMotions();}}
  async function poll(){if(demo||polling||document.hidden)return;polling=true;try{const latest=await request('/api/status');if(latest.state==='error'&&status.error!==latest.error)toast(latest.error||'Playback failed');status=latest;connection(true,status.robot_connected);}catch(e){connection(false,false);}finally{polling=false;}}
  async function action(path, confirm=false, successMessage=''){if(busy)return;busy=true;renderPlayer();renderMotions();try{if(demo){status={...status,state:path.includes('/api/motions/')?'complete':path.endsWith('pause')?'paused':path.endsWith('reset')?'idle':'playing',routine_id:selected?.id};}else status=await request(path,'POST','{}',{'Content-Type':'application/json',...(confirm?{'X-G1-Safety-Confirmed':'YES'}:{})});connection(true,status.robot_connected);log('Playback: '+status.state);if(successMessage)toast(successMessage);}catch(e){toast(e.message);}finally{busy=false;renderPlayer();renderMotions();}}
  async function connectRobot(){
    if(robotBusy||status.robot_connected)return;
    if(demo){toast('Robot connection is unavailable in the visual demo.');return;}
    robotBusy=true;connection(connected,false);
    try{status=await request('/api/robot/connect','POST','{}',{'Content-Type':'application/json'});connection(true,status.robot_connected);toast('Robot connected.');log('Robot connection established');}
    catch(e){connection(connected,false);toast('Robot connection failed: '+e.message);}
    finally{robotBusy=false;connection(connected,status.robot_connected);}
  }
  function setAudioOutput(value){audioOutput=value;const input=document.querySelector('input[name="audio-output"][value="'+value+'"]');if(input)input.checked=true;}
  function openSettings(){$('address').value=address;setAudioOutput(audioOutput);$('settings-dialog').showModal();}
  function openDanceConfirm(){pendingMotion=null;$('confirm-heading').textContent='Start this dance?';$('confirm-copy').textContent='Make sure the robot has space and the physical E-stop is ready.';$('confirm-action').textContent='Start dance';$('confirm-dialog').showModal();}
  function openMotionConfirm(motion){pendingMotion=motion;$('confirm-heading').textContent='Start '+motion.name+'?';$('confirm-copy').textContent='Make sure the robot has space and the physical E-stop is ready.';$('confirm-action').textContent='Start motion';$('confirm-dialog').showModal();}
  $('menu').onclick=openSettings;$('settings-nav').onclick=openSettings;$('empty-settings').onclick=openSettings;document.querySelectorAll('[data-connect-robot]').forEach(button=>button.onclick=connectRobot);
  $('hero-browse').onclick=$('library-nav').onclick=()=>$('library').scrollIntoView({behavior:'smooth'});
  $('refresh').onclick=refresh;$('search').oninput=renderCards;
  document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{filter=b.dataset.filter;document.querySelectorAll('[data-filter]').forEach(c=>c.classList.toggle('selected',c===b));renderCards();});
  document.querySelectorAll('.close').forEach(b=>b.onclick=()=>b.closest('dialog').close());
  $('settings-form').onsubmit=async e=>{e.preventDefault();try{const u=new URL($('address').value);if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.search||u.hash)throw Error('Enter an HTTP address');if(!native&&u.origin!==location.origin){location.assign(u.origin);return;}address=u.origin;localStorage.setItem('g1.address',address);const chosen=document.querySelector('input[name="audio-output"]:checked').value;if(!demo)await request('/api/settings/audio-output','PUT',JSON.stringify({audio_output:chosen}),{'Content-Type':'application/json'});setAudioOutput(chosen);localStorage.setItem('g1.audio-output',chosen);$('settings-dialog').close();refresh();}catch(e){toast(e.message);}};
  $('toggle').onclick=()=>{if(status.state==='playing')action('/api/pause');else if(status.state==='paused')action('/api/resume');else openDanceConfirm();};
  $('stop').onclick=()=>action('/api/reset');$('confirm-action').onclick=()=>{const motion=pendingMotion;pendingMotion=null;$('confirm-dialog').close();if(motion)action('/api/motions/'+encodeURIComponent(motion.id)+'/play',true,motion.name+(demo?' simulated.':' started.'));else action('/api/routines/'+encodeURIComponent(selected.id)+'/play',true);};
  $('edit').onclick=()=>{$('track-heading').textContent=selected.song_title||selected.name;$('detail-art').src=art(selected);$('track-dialog').showModal();};
  function upload(file,kind){if(!file||!selected)return;const id=selected.id;if(demo){toast('Demo mode: uploads are disabled. Connect to a development PC to save files.');return;}if(kind==='audio'&&!/\.mp3$/i.test(file.name)){toast('Choose an MP3 file.');return;}const max=kind==='audio'?100:5;if(file.size>max*1024*1024){toast('Choose a file smaller than '+max+' MB.');return;}
    busy=true;renderPlayer();$('upload-progress').hidden=false;const xhr=new XMLHttpRequest();xhr.open('PUT',address+'/api/routines/'+encodeURIComponent(id)+'/'+kind);xhr.timeout=120000;if(kind==='audio')xhr.setRequestHeader('X-Song-Title',encodeURIComponent(file.name.replace(/\.mp3$/i,'')));xhr.setRequestHeader('Content-Type',file.type||'application/octet-stream');xhr.upload.onprogress=e=>{if(e.lengthComputable)$('upload-progress').value=100*e.loaded/e.total;};
    const done=()=>{busy=false;$('upload-progress').hidden=true;renderPlayer();};xhr.onload=async()=>{done();if(xhr.status>=200&&xhr.status<300){toast(kind==='audio'?'Song linked. Ready for the next session.':'Cover updated on all devices.');$('track-dialog').close();await refresh();}else{try{toast(JSON.parse(xhr.responseText).error);}catch{toast('Upload failed.');}}};xhr.onerror=xhr.ontimeout=()=>{done();toast('Upload interrupted. Check the connection and try again.');};xhr.send(file);
  }
  $('song-file').onchange=e=>{upload(e.target.files[0],'audio');e.target.value='';};$('cover-file').onchange=e=>{upload(e.target.files[0],'artwork');e.target.value='';};
  // Native bundle defaults to the hotspot; browsers use their own server origin.
  if(!native)address=location.origin;
  refresh();setInterval(poll,2000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll();});
})();
