import { parseTemplateContract, ProjectApiError, type ApiConfig, type TemplateContract } from './projects'

/** Read the platform template directory without enumerating a user's projects. */
export async function listTemplateCatalog(config: ApiConfig, signal?: AbortSignal): Promise<TemplateContract[]> {
  const baseUrl = config.baseUrl.trim().replace(/\/$/, '')
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (config.token.trim()) headers.Authorization = 'Bearer ' + config.token.trim()

  const response = await fetch(baseUrl + '/api/v1/templates', { headers, signal })
  if (!response.ok) throw new ProjectApiError(response.status)

  const payload: unknown = await response.json()
  if (!Array.isArray(payload)) throw new Error('Invalid template catalog response')
  return payload.map(parseTemplateContract)
}
