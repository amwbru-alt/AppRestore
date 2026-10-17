import mysql from 'mysql2/promise';
import { readFileSync } from 'node:fs';

export function databaseOptions(env = process.env) {
  for (const name of ['DB_HOST', 'DB_USER', 'DB_NAME', 'DB_PASSWORD']) {
    if (!env[name] || env[name] === 'SET_ON_SERVER') throw new Error(`Configure ${name} on the server`);
  }
  const port = Number(env.DB_PORT || 3306);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid DB port');
  return {
    host: env.DB_HOST, port, user: env.DB_USER, database: env.DB_NAME,
    password: env.DB_PASSWORD, charset: 'utf8mb4', multipleStatements: false,
    connectionLimit: 5, maxIdle: 5, idleTimeout: 60000,
    waitForConnections: true, queueLimit: 20, connectTimeout: 10000,
    ...(env.DB_SSL_CA ? { ssl: { ca: readFileSync(env.DB_SSL_CA), rejectUnauthorized: true } } : {}),
  };
}
export function createDatabase(env = process.env) { return mysql.createPool(databaseOptions(env)); }
