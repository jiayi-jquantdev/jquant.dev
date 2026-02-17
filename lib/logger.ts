export function info(...args: unknown[]) {
  if (process.env.NODE_ENV !== 'production') console.info(...args);
}
export function warn(...args: unknown[]) {
  console.warn(...args);
}
export function error(...args: unknown[]) {
  console.error(...args);
}
