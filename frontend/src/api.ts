export async function request<T>(
  path: string,
  signal?: AbortSignal,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, { ...init, signal, cache: 'no-store' });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(
      typeof body?.detail === 'string' ? body.detail : `Could not load data (${response.status}).`,
    );
  }
  return response.json();
}
