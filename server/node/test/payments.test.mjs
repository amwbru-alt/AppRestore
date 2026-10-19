import test from 'node:test';import assert from 'node:assert/strict';
import {YooKassa,PaymentService,money} from '../src/payments.mjs';
test('gateway is off without explicit merchant configuration; totals remain integer kopecks',()=>{assert.equal(new YooKassa({}).configured,false);assert.equal(money('100.01'),10001);assert.throws(()=>money('100.001'));assert.throws(()=>money('-1.00'));const service=new PaymentService(null,null);assert.throws(()=>service.verify({checkout_id:'a',amount_kopecks:10000},{id:'test',metadata:{checkout_id:'a'},amount:{currency:'RUB',value:'1.00'}}));});
test('provider creates a priced receipt, idempotence key, and no client-supplied amount',async()=>{let sent;const provider=new YooKassa({PAYMENTS_ENABLED:'true',YOOKASSA_SHOP_ID:'test-shop',YOOKASSA_SECRET_KEY:'isolated-test-secret',PUBLIC_URL:'https://apprevive.example',PAYMENT_VAT_CODE:'1'},async(url,options)=>{sent={url,options};return {ok:true,json:async()=>({id:'test'})};});await provider.create({checkout_id:'a'.repeat(32),quantity:2,amount_kopecks:20000},'buyer@example.test');const body=JSON.parse(sent.options.body);assert.equal(body.amount.value,'200.00');assert.equal(body.receipt.items[0].amount.value,'100.00');assert.equal(sent.options.headers['Idempotence-Key'],'a'.repeat(32));assert.equal(body.metadata.checkout_id,'a'.repeat(32));});

test('test-mode money cannot issue production codes',()=>{
 const env={PAYMENTS_ENABLED:'true',YOOKASSA_SHOP_ID:'test-shop',YOOKASSA_SECRET_KEY:'isolated-test-secret',PUBLIC_URL:'https://apprevive.example',PAYMENT_VAT_CODE:'1',PAYMENTS_TEST_MODE:'true'};
 assert.equal(new YooKassa({...env,APP_ENV:'production'}).configured,false);
 const provider=new YooKassa({...env,APP_ENV:'staging'});assert.equal(provider.configured,true);
 const row={checkout_id:'a',amount_kopecks:10000},payment={id:'test',test:true,metadata:{checkout_id:'a'},amount:{currency:'RUB',value:'100.00'}};
 assert.throws(()=>new PaymentService(null,null,new YooKassa({})).verify(row,payment),e=>e.code==='test_payment_rejected');
 assert.doesNotThrow(()=>new PaymentService(null,null,provider).verify(row,payment));
});

test('status polling reconciles full refunds without a public HTTPS webhook',async()=>{
 let state='paid',issued=0,refunded=0;
 const row={checkout_id:'a'.repeat(32),user_id:'u',account_id:'b'.repeat(64),provider_id:'payment-test',quantity:1,amount_kopecks:10000};
 const payment={id:row.provider_id,status:'succeeded',paid:true,metadata:{checkout_id:row.checkout_id},amount:{currency:'RUB',value:'100.00'},refunded_amount:{currency:'RUB',value:'100.00'}};
 const pool={execute:async sql=>{if(sql.includes("state='refunded'"))state='refunded';return [{}];}};
 const service=new PaymentService(pool,{recordPurchase:async()=>{issued++;},refund:async()=>{refunded++;}},{payment:async()=>payment});
 service.row=async()=>({...row,state});service.ensure=async()=>{};
 assert.equal((await service.sync(row.checkout_id)).state,'refunded');
 await service.sync(row.checkout_id);assert.equal(issued,1);assert.equal(refunded,1);
 state='paid';payment.refunded_amount.value='50.00';
 await assert.rejects(service.sync(row.checkout_id),e=>e.code==='partial_refund_needs_review');
 assert.equal(issued,1);
});
