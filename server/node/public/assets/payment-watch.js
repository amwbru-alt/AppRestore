'use strict';
window.AppRevivePaymentWatch=({request,onChange,onSettled,canPoll=()=>true,delay=5000,maxAttempts=12})=>{
 let id='',generation=0,timer=null,running=false,attempts=0,terminal=false;
 const clear=()=>{if(timer!==null)clearTimeout(timer);timer=null;};
 const stop=()=>{generation++;clear();id='';running=false;attempts=0;terminal=false;};
 const schedule=()=>{clear();if(id&&!terminal&&attempts<maxAttempts)timer=setTimeout(check,delay);};
 async function check(){
  if(!id||running||terminal)return;
  clear();if(!canPoll()){schedule();return;}
  const epoch=generation,checkout=id;running=true;attempts++;
  onChange({state:'checking',checkout_id:checkout,attempts});
  try{
   const data=await request('/v3/checkout/sync',{checkout_id:checkout});
   if(epoch!==generation)return;
   if(data.checkout_id!==checkout||!['pending','paid','cancelled','refunded'].includes(data.state))throw Error('Сервер вернул неполное состояние заказа. Повторите проверку.');
   terminal=data.state!=='pending';
   onChange({...data,attempts,paused:!terminal&&attempts>=maxAttempts});
   if(terminal)await onSettled?.(data);
  }catch(error){if(epoch!==generation)return;terminal=[401,403,404].includes(error.status);onChange({state:'error',checkout_id:checkout,message:error.message,attempts,paused:terminal||attempts>=maxAttempts});}
  finally{if(epoch===generation){running=false;schedule();}}
 }
 return {start(checkout){if(!/^[a-f0-9]{32}$/.test(checkout))return false;stop();id=checkout;check();return true;},retry(){if(!id||running)return;terminal=false;attempts=0;check();},check,stop,get currentId(){return id;}};
};
