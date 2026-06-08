const API_BASE = '/api/v1';

async function getToken(): Promise<string> {
  const token = localStorage.getItem('secureclaw_token');
  if (!token) throw new Error('Not authenticated');
  return token;
}

export async function apiFetch(path: string, options: RequestInit = {}): Promise<Response> {
  const token = await getToken();
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...(options.headers as Record<string, string>),
    },
  });
  if (res.status === 401) {
    localStorage.removeItem('secureclaw_token');
    window.location.href = '/login';
    throw new Error('Session expired');
  }
  return res;
}

export function streamTask(
  taskId: string,
  onData: (data: any) => void,
  onDone: () => void,
): AbortController {
  const controller = new AbortController();
  const token = localStorage.getItem('secureclaw_token');

  fetch(`${API_BASE}/tasks/${taskId}/stream`, {
    headers: { Authorization: `Bearer ${token}` },
    signal: controller.signal,
  })
    .then(async res => {
      const reader = res.body?.getReader();
      if (!reader) return onDone();
      const decoder = new TextDecoder();
      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              onData(JSON.parse(line.slice(6)));
            } catch {}
          }
        }
      }
      onDone();
    })
    .catch(() => onDone());

  return controller;
}
