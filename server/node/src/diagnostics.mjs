// Only allowlisted codes leave the server. Never serialize driver errors or SQL.
const schema = new Set(['ER_NO_SUCH_TABLE','ER_BAD_FIELD_ERROR']);
const connection = new Set(['ECONNREFUSED','ETIMEDOUT','ECONNRESET','EPIPE','ENOTFOUND','EAI_AGAIN','PROTOCOL_CONNECTION_LOST','ER_CON_COUNT_ERROR','ER_USER_LIMIT_REACHED']);
export function failureKind(error) {
  if(schema.has(error?.code))return 'database_schema_outdated';
  if(connection.has(error?.code))return 'database_unavailable';
  if(['ER_ACCESS_DENIED_ERROR','ER_DBACCESS_DENIED_ERROR','ER_BAD_DB_ERROR'].includes(error?.code))return 'database_configuration_error';
  return 'unavailable';
}
