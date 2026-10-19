import { ApiError } from './service.mjs';

export function pageInput(query){
  const page=Number(query.get('page')||1),size=Number(query.get('size')||25),search=(query.get('q')||'').trim();
  if(!Number.isInteger(page)||page<1||page>100000||!Number.isInteger(size)||size<1||size>100||search.length>100)throw new ApiError(400,'invalid_page');
  return {page,size,search};
}
export async function records(pool,kind,query){
  const {page,size,search}=pageInput(query);const status=query.get('state')||'';
  const filters=[],params=[];
  let source,columns,sort;
  if(kind==='users'){
    if(status&&!['user','admin'].includes(status))throw new ApiError(400,'invalid_filter');
    source='apprevive_users u LEFT JOIN apprevive_user_referrals r ON r.user_id=u.user_id LEFT JOIN apprevive_partners p ON p.account_id=r.partner_id';
    columns='u.user_id,u.email,u.role,u.verified,u.created_at,p.referral_code AS invited_by';sort='u.created_at DESC,u.user_id';
    if(search){filters.push('(LOCATE(?,u.email)>0 OR LOCATE(?,u.user_id)>0 OR LOCATE(?,p.referral_code)>0)');params.push(search,search,search);}
    if(status){filters.push('u.role=?');params.push(status);}
  }else if(kind==='orders'){
    if(status&&!['paid','refunded'].includes(status))throw new ApiError(400,'invalid_filter');
    source='apprevive_orders o';columns='o.*';sort='o.created_at DESC,o.order_id';
    if(search){filters.push('(LOCATE(?,o.payment_reference)>0 OR LOCATE(?,o.buyer_id)>0 OR LOCATE(?,o.partner_id)>0)');params.push(search,search,search);}
    if(status){filters.push('o.state=?');params.push(status);}
  }else throw new ApiError(404,'not_found');
  const where=filters.length?' WHERE '+filters.join(' AND '):'';
  const [count]=await pool.execute('SELECT COUNT(*) AS total FROM '+source+where,params);
  const total=Number(count[0].total),pages=Math.max(1,Math.ceil(total/size)),current=Math.min(page,pages);
  // Only validated integer limits are interpolated; user search/filter values stay bound.
  const [rows]=await pool.execute('SELECT '+columns+' FROM '+source+where+' ORDER BY '+sort+` LIMIT ${size} OFFSET ${(current-1)*size}`,params);
  return {status:'ok',rows,total,page:current,size,pages};
}
export async function metrics(pool){
 const [users]=await pool.execute('SELECT COUNT(*) AS total FROM apprevive_users');
 const [orders]=await pool.execute("SELECT COUNT(*) AS total,COALESCE(SUM(quantity),0) AS codes,COALESCE(SUM(amount_kopecks),0) AS revenue FROM apprevive_orders WHERE state='paid'");
 const [refs]=await pool.execute('SELECT COUNT(*) AS total FROM apprevive_user_referrals');
 const [restores]=await pool.execute("SELECT COUNT(*) AS total FROM apprevive_restorations WHERE state='reserved'");
 return {status:'ok',users:Number(users[0].total),paid_orders:Number(orders[0].total),codes:Number(orders[0].codes),revenue_kopecks:Number(orders[0].revenue),registered_referrals:Number(refs[0].total),pending_restorations:Number(restores[0].total),updated_at:new Date().toISOString()};
}
