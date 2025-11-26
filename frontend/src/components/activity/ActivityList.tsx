import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Activity } from '../../types/activity';
import ActivityCard from './ActivityCard';
import { activityService } from '../../services/activityService';
import Notification from '../notification/Notification';
import { authService } from '../../services/authService';
import { API } from '../../services/api';

export interface ActivityListProps {
  tripId: string;
  category?: string;
  minScore?: number;
  limit?: number;
  className?: string;
  cardWidthPx?: number;
  cardHeightPx?: number;
  modalMaxWidth?: string; // Control detail modal width
}

export default function ActivityList({
  tripId,
  category,
  minScore,
  limit = 20,
  className,
  cardWidthPx = 550,
  cardHeightPx = 350,
  modalMaxWidth = '32vw',
}: ActivityListProps) {
  const [activities, setActivities] = useState<Activity[]>([]);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    type?: 'success' | 'error' | 'info' | 'warning';
  } | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const isDraggingRef = useRef(false);
  const startXRef = useRef(0);
  const scrollLeftRef = useRef(0);
  const wsRef = useRef<WebSocket | null>(null);

  const gapPx = 14;
  const cardStyle = useMemo(
    () => ({ minWidth: `${cardWidthPx}px`, width: `${cardWidthPx}px` }),
    [cardWidthPx],
  );

  const fetchData = useCallback(async () => {
    setLoading(true);
    try {
      const data = await activityService.getActivities({
        trip_id: tripId,
        category,
        min_score: typeof minScore === 'number' ? minScore : undefined,
        limit,
      });
      setActivities(data);
    } catch (e: any) {
      setToast({ message: e?.message || 'Failed to load activities', type: 'error' });
    } finally {
      setLoading(false);
    }
  }, [tripId, category, minScore, limit]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // WebSocket listener for real-time activity updates
  useEffect(() => {
    const wsUrl = `${API.chat.chat}/${tripId}`;
    const ws = new WebSocket(wsUrl);

    let pingInterval: NodeJS.Timeout;

    ws.onopen = () => {
      console.log('[ActivityList] WebSocket connected for activity updates');
      // Send initial ping message to complete the WebSocket handshake loop on the backend
      const currentUser = JSON.parse(localStorage.getItem('user_info') || '{}');
      const pingMessage = JSON.stringify({
        type: 'ping',
        senderId: currentUser.id || 'anonymous',
        senderName: currentUser.name || 'Anonymous',
        content: '',
      });
      ws.send(pingMessage);

      // Send ping every 30 seconds to keep connection alive during long voting sessions
      pingInterval = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(pingMessage);
          console.log('[ActivityList] Keepalive ping sent');
        }
      }, 30000); // 30 seconds
    };

    ws.onmessage = (event) => {
      try {
        const message = JSON.parse(event.data);

        // Debug: Log all agent_status messages
        if (message.type === 'agent_status') {
          console.log('[ActivityList] Agent status received:', {
            agent_name: message.agent_name,
            status: message.status,
            step: message.step,
          });
        }

        // Listen for agent status indicating activities are ready
        if (
          message.type === 'agent_status' &&
          message.agent_name === 'Destination Research Agent' &&
          message.status === 'completed' &&
          message.step?.includes('activity suggestions')
        ) {
          console.log('[ActivityList] Activities generated, auto-refreshing...');
          fetchData();
        }

        // Listen for itinerary generation completion
        if (message.type === 'agent_status' && message.agent_name === 'Itinerary Agent') {
          console.log('[ActivityList] Itinerary Agent status:', message.status);
          if (message.status === 'completed') {
            console.log('[ActivityList] Itinerary generation completed!');
            // Could trigger navigation or notification here
          }
        }
      } catch (error) {
        console.error('[ActivityList] WebSocket message parse error:', error);
      }
    };

    ws.onerror = (error) => {
      console.error('[ActivityList] WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('[ActivityList] WebSocket disconnected');
    };

    wsRef.current = ws;

    return () => {
      clearInterval(pingInterval);
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, [tripId, fetchData]);

  const handleMouseDown = (e: React.MouseEvent) => {
    const el = containerRef.current;
    if (!el) return;
    isDraggingRef.current = true;
    startXRef.current = e.pageX - el.offsetLeft;
    scrollLeftRef.current = el.scrollLeft;
  };
  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDraggingRef.current) return;
    e.preventDefault();
    const el = containerRef.current;
    if (!el) return;
    const x = e.pageX - el.offsetLeft;
    const walk = (x - startXRef.current) * 1; // scroll speed
    el.scrollLeft = scrollLeftRef.current - walk;
  };
  const endDrag = () => {
    isDraggingRef.current = false;
  };

  const handleTouchStart = (e: React.TouchEvent) => {
    const el = containerRef.current;
    if (!el) return;
    isDraggingRef.current = true;
    startXRef.current = e.touches[0].pageX - el.offsetLeft;
    scrollLeftRef.current = el.scrollLeft;
  };
  const handleTouchMove = (e: React.TouchEvent) => {
    if (!isDraggingRef.current) return;
    const el = containerRef.current;
    if (!el) return;
    const x = e.touches[0].pageX - el.offsetLeft;
    const walk = (x - startXRef.current) * 1;
    el.scrollLeft = scrollLeftRef.current - walk;
  };
  const handleTouchEnd = () => {
    isDraggingRef.current = false;
  };

  const onVote = async (a: Activity, vote: 'up' | 'down') => {
    const user = authService.getUser();
    if (!user) {
      setToast({ message: 'Please sign in to vote', type: 'warning' });
      return;
    }
    try {
      await activityService.vote({
        trip_id: a.trip_id,
        activity_name: a.name,
        user_id: user.id,
        vote,
      });
      // Don't show toast on success - vote button provides visual feedback
    } catch (e: any) {
      setToast({ message: e?.message || 'Voting failed', type: 'error' });
    }
  };

  return (
    <div className={className}>
      {/* Scroll container */}
      <div
        ref={containerRef}
        className="overflow-x-auto scroll-smooth"
        style={{ WebkitOverflowScrolling: 'touch' }}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseLeave={endDrag}
        onMouseUp={endDrag}
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
      >
        <div
          className="flex items-stretch"
          style={{ gap: `${gapPx}px`, padding: `2px ${gapPx}px` }}
        >
          {loading
            ? Array.from({ length: 4 }).map((_, i) => (
                <div
                  key={`skeleton-${i}`}
                  className="rounded-2xl shadow-md animate-pulse"
                  style={{
                    ...cardStyle,
                    height: cardHeightPx,
                    background: 'linear-gradient(135deg, rgba(0,0,0,0.06), rgba(0,0,0,0.02))',
                  }}
                />
              ))
            : activities.map((a) => (
                <div
                  key={`${a.name}-${a.category}`}
                  className="shrink-0"
                  style={{ ...cardStyle, height: `${cardHeightPx}px` }}
                >
                  <ActivityCard
                    activity={a}
                    onVote={onVote}
                    className="h-full"
                    modalMaxWidth={modalMaxWidth}
                  />
                </div>
              ))}
        </div>
      </div>

      {/* Toast */}
      <Notification
        isVisible={!!toast}
        message={toast?.message || ''}
        type={toast?.type}
        onClose={() => setToast(null)}
      />
    </div>
  );
}
