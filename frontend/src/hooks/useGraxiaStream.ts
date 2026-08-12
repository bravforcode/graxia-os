import { useEffect, useRef, useState } from 'react';

interface GraxiaEvent {
  type: string;
  agent_id?: string;
  message?: string;
  payload?: Record<string, unknown>;
  timestamp: string;
}

export function useGraxiaStream() {
  const [events, setEvents] = useState<GraxiaEvent[]>([]);
  const [isConnected, setIsConnected] = useState(false);
  const ws = useRef<WebSocket | null>(null);

  useEffect(() => {
    // Determine WS URL - assuming it mirrors the API base but with ws/wss
    const apiBase = import.meta.env.VITE_API_BASE_URL || '/api/v1';
    let wsUrl: string;

    if (apiBase.startsWith('http')) {
      wsUrl = apiBase.replace(/^http/, 'ws') + '/graxia/stream';
    } else {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      wsUrl = `${protocol}//${host}${apiBase}/graxia/stream`;
    }

    // In a real app, we'd get the token from storage
    // For now, we'll try to connect. The backend might require ?token=...
    // const token = localStorage.getItem('access_token');
    // if (token) wsUrl += `?token=${token}`;

    console.log('Connecting to Graxia Stream:', wsUrl);
    
    const connect = () => {
      ws.current = new WebSocket(wsUrl);

      ws.current.onopen = () => {
        setIsConnected(true);
        console.log('Graxia Stream Connected');
      };

      ws.current.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setEvents((prev) => [data, ...prev].slice(0, 100));
        } catch (err) {
          console.error('Failed to parse WS message', err);
        }
      };

      ws.current.onclose = () => {
        setIsConnected(false);
        console.log('Graxia Stream Disconnected, retrying in 5s...');
        setTimeout(connect, 5000);
      };

      ws.current.onerror = (err) => {
        console.error('Graxia Stream Error', err);
        ws.current?.close();
      };
    };

    connect();

    return () => {
      ws.current?.close();
    };
  }, []);

  return { events, isConnected };
}
