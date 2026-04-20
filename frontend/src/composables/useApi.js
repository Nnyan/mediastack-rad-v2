export const API = {
  async get(path) {
    const res = await fetch(`/api${path}`);
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(text);
    }
    return res.json();
  },

  async post(path, body) {
    const res = await fetch(`/api${path}`, {
      method: "POST",
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(text);
    }
    return res.json();
  },

  containers: {
    list:    ()              => API.get("/containers"),
    get:     (id)            => API.get(`/containers/${id}`),
    start:   (id)            => API.post(`/containers/${id}/start`),
    stop:    (id)            => API.post(`/containers/${id}/stop`),
    restart: (id)            => API.post(`/containers/${id}/restart`),
    logs:    (id, tail=200)  => API.get(`/containers/${id}/logs?tail=${tail}`),
    stats:   (id)            => API.get(`/containers/${id}/stats`),
    troubleshoot: (id)       => API.get(`/containers/${id}/troubleshoot`),
    bulk:    (action, ids=[]) => API.post(`/containers/bulk/${action}`, { ids }),
  },

  stack: {
    health: () => API.get("/stack/health"),
  },

  compose: {
    parse:  (yaml)  => API.post("/compose/parse",  { yaml }),
    github: (url)   => API.post("/compose/github", { url }),
  },

  networks: () => API.get("/networks"),
  images:   () => API.get("/images"),
};

export function connectStatsWs(onMessage) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/stats`);
  ws.onmessage = (ev) => {
    try { onMessage(JSON.parse(ev.data)); } catch { }
  };
  return () => ws.close();
}
