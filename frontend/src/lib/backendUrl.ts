/** 后端基址：Vercel 上请在「前端项目」环境变量中设置 BACKEND_URL。 */
export function getBackendBase(): string {
  return (
    process.env.BACKEND_URL ||
    process.env.API_PROXY_TARGET ||
    "http://127.0.0.1:8001"
  ).replace(/\/$/, "");
}
