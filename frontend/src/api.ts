import type { Page } from './types';

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

export async function allPages<T>(
  path: string,
  signal?: AbortSignal,
  pageSize = 5000,
): Promise<T[]> {
  const result: T[] = [];
  let offset = 0;
  const seen = new Set<number>();
  do {
    if (seen.has(offset)) throw new Error('The archive returned an invalid page sequence.');
    seen.add(offset);
    const url = new URL(path, window.location.origin);
    url.searchParams.set('limit', String(pageSize));
    url.searchParams.set('offset', String(offset));
    const page = await request<Page<T>>(url.pathname + url.search, signal);
    result.push(...page.items);
    if (page.next_offset == null) return result;
    offset = page.next_offset;
  } while (!signal?.aborted);
  throw new DOMException('Request cancelled', 'AbortError');
}
