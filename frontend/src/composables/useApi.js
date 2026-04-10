// Centralised API helpers — all fetch calls go through here

export const API = {
  async get(path) {
    const res = await fetch(`/api${path}`);
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(text);
    }
    return res.json();
  },

  async post(path) {
    const res = await fetch(`/api${path}`, { method: "POST" });
    if (!res.ok) {
      const text = await res.text().catch(() => res.statusText);
      throw new Error(text);
    }
    return res.json();
  },

  containers: {
    list: ()              => API.get("/containers"),
    get:  (id)            => API.get(`/containers/${id}`),
    start:(id)            => API.post(`/containers/${id}/start`),
    stop: (id)            => API.post(`/containers/${id}/stop`),
    restart:(id)          => API.post(`/containers/${id}/restart`),
    logs: (id, tail=200)  => API.get(`/containers/${id}/logs?tail=${tail}`),
    stats:(id)            => API.get(`/containers/${id}/stats`),
  },

  networks: () => API.get("/networks"),
  images:   () => API.get("/images"),
};

/**
 * Connect to the /ws/stats WebSocket.
 * onMessage(data) fires every ~2 s with { [shortId]: { cpu_percent, memory_mb, memory_limit_mb } }
 * Returns a cleanup function — call it to close the socket.
 */
export function connectStatsWs(onMessage) {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const ws = new WebSocket(`${proto}://${location.host}/ws/stats`);

  ws.onmessage = (ev) => {
    try { onMessage(JSON.parse(ev.data)); } catch { /* ignore bad frames */ }
  };

  ws.onerror = () => { /* silently retry via reconnectStatsWs */ };

  return () => ws.close();
}
