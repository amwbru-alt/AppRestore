import { createApi } from '../../src/http.mjs';
import { PromoService } from '../../src/service.mjs';
import { MemoryPool } from '../memory-pool.mjs';
const api = createApi(new PromoService(new MemoryPool()), { requireHttps: false });
api.listen(0, '127.0.0.1', () => console.log(`http://127.0.0.1:${api.address().port}`));
process.on('SIGTERM', () => { api.close(); api.closeAllConnections(); });
