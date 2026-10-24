import { vi } from 'vitest'

type Route = unknown | ((init?: RequestInit) => unknown)

/**
 * Stub `fetch` with JSON responses keyed by "METHOD /path" or "/path" (any method), ignoring
 * the query string. A route can be a function of the request to answer differently per call,
 * or return a `Response` for error cases. Unknown paths get a 404.
 */
export function mockFetch(routes: Record<string, Route>) {
  const fetchMock = vi.fn(async (input: string, init?: RequestInit) => {
    const path = input.split('?')[0]
    const method = init?.method ?? 'GET'
    const route = routes[`${method} ${path}`] ?? routes[path]
    if (route === undefined) return new Response(null, { status: 404 })
    const body = typeof route === 'function' ? route(init) : route
    return body instanceof Response ? body : Response.json(body)
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}
