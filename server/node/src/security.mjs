import { ApiError } from './service.mjs';
import { passwordHash, verifyPassword } from './auth.mjs';

export class SecurityService {
  constructor(pool){this.pool=pool;}
  async sessions(user){
    const [rows]=await this.pool.execute('SELECT token_hash,expires_at FROM apprevive_sessions WHERE user_id=? AND expires_at>UTC_TIMESTAMP() ORDER BY expires_at DESC LIMIT 200',[user.user_id]);
    return {status:'ok',sessions:rows.map(r=>({id:r.token_hash,expires_at:r.expires_at,current:r.token_hash===user.session_hash}))};
  }
  async revoke(user,body){
    if(body?.others===true){await this.pool.execute('DELETE FROM apprevive_sessions WHERE user_id=? AND token_hash<>?',[user.user_id,user.session_hash]);}
    else {
      if(typeof body?.session_id!=='string'||!/^[a-f0-9]{64}$/.test(body.session_id))throw new ApiError(400,'invalid_session');
      await this.pool.execute('DELETE FROM apprevive_sessions WHERE user_id=? AND token_hash=?',[user.user_id,body.session_id]);
    }
    return {status:'ok'};
  }
  async password(user,body){
    const encoded=await passwordHash(body?.new_password),db=await this.pool.getConnection();
    try {
      await db.beginTransaction();
      const [rows]=await db.execute('SELECT password_hash FROM apprevive_users WHERE user_id=? FOR UPDATE',[user.user_id]);
      if(!await verifyPassword(body?.current_password,rows[0]?.password_hash))throw new ApiError(403,'current_password_incorrect');
      await db.execute('UPDATE apprevive_users SET password_hash=? WHERE user_id=?',[encoded,user.user_id]);
      await db.execute('DELETE FROM apprevive_sessions WHERE user_id=? AND token_hash<>?',[user.user_id,user.session_hash]);
      // Old recovery links must not restore the previous password after this change.
      await db.execute("DELETE FROM apprevive_email_tokens WHERE user_id=? AND purpose='reset'",[user.user_id]);
      await db.commit();return {status:'ok'};
    }catch(error){await db.rollback();throw error;}finally{db.release();}
  }
}
