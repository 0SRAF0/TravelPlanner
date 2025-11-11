import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { Activity } from '../../types/activity';
import ActivityCard from './ActivityCard';
import { activityService } from '../../services/activityService';
import Notification from '../notification/Notification';
import { authService } from '../../services/authService';

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
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<{ message: string; type?: 'success' | 'error' | 'info' | 'warning' } | null>(null);

  const containerRef = useRef<HTMLDivElement | null>(null);
  const isDraggingRef = useRef(false);
  const startXRef = useRef(0);
  const scrollLeftRef = useRef(0);

  const gapPx = 14;
  const cardStyle = useMemo(
    () => ({ minWidth: `${cardWidthPx}px`, width: `${cardWidthPx}px` }),
    [cardWidthPx]
  );

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await activityService.getActivities({
        trip_id: tripId,
        category,
        min_score: typeof minScore === 'number' ? minScore : undefined,
        limit,
      });
      setActivities(data);
    } catch (e: any) {
      setError(e?.message || 'Failed to load activities');
    } finally {
      setLoading(false);
    }
  }, [tripId, category, minScore, limit]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

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
      setToast({ message: vote === 'up' ? 'Voted up' : 'Voted down', type: 'success' });
    } catch (e: any) {
      setToast({ message: e?.message || 'Voting failed', type: 'error' });
    }
  };

  return (
    <div className={className}>
      {/* Header row with error / retry */}
      <div className="flex items-center justify-between mb-2 px-1">
        <div className="text-left">
          <div className="text-sm font-extrabold">Activities</div>
          {category && <div className="text-xs opacity-60">{category}</div>}
        </div>
        <button
          className="text-xs font-bold underline opacity-80 hover:opacity-100"
          onClick={fetchData}
        >
          Refresh
        </button>
      </div>

      {error && (
        <div className="text-left text-danger text-sm mb-2 px-1">
          {error}
        </div>
      )}

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
                    background:
                      'linear-gradient(135deg, rgba(0,0,0,0.06), rgba(0,0,0,0.02))',
                  }}
                />
              ))
            : activities.map((a) => (
                <div key={`${a.name}-${a.category}`} className="shrink-0" style={{ ...cardStyle, height: `${cardHeightPx}px` }}>
                  <ActivityCard activity={a} onVote={onVote} className="h-full" modalMaxWidth={modalMaxWidth} />
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


