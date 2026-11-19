export async function api<T>(path: string, payload?: unknown, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`/api/${path}`, {
    method: payload === undefined ? 'GET' : 'POST',
    headers: { 'Content-Type': 'application/json', 'X-LLR-Client': 'studio' },
    body: payload === undefined ? undefined : JSON.stringify(payload), signal,
  })
  const result = await response.json()
  if (!response.ok) throw new Error(result.error?.message ?? `Request failed (${response.status})`)
  return result as T
}

export function encodeFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('The selected image could not be read.'))
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.readAsDataURL(file)
  })
}
