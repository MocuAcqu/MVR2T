/** GET /api/health 回應（需與 apps/backend/app/schemas/health.py 保持一致）。 */
export interface HealthResponse {
  status: 'ok';
  service: string;
  version: string;
  platform: string;
  python_version: string;
}
