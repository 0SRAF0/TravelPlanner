import { useMemo, useState } from 'react';
import type { Activity } from '../../types/activity';
import Modal from '../modal/Modal';
import GoogleMapEmbed from '../map/GoogleMapEmbed';

type ColorSet = { primary: string; secondary: string };

const COLOR_SETS: ColorSet[] = [{ primary: '#000', secondary: '#FFF' }];

export interface ActivityCardProps {
  activity: Activity;
  onVote?: (activity: Activity, vote: 'up' | 'down') => Promise<void> | void;
  className?: string;
  modalMaxWidth?: string; // Control detail modal width (e.g., "800px", "90vw")
}

function formatDuration(minutes?: number | null): string {
  if (!minutes || minutes <= 0) return '—';
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  if (h && m) return `${h}h ${m}m`;
  if (h) return `${h}h`;
  return `${m}m`;
}

function formatCost(cost?: number | null): string {
  if (cost === null || cost === undefined) return '—';
  if (cost === 0) return '$0';
  return `$${cost}`;
}

function Avatar({ label, bg, color }: { label: string; bg: string; color: string }) {
  const initials = useMemo(() => {
    const parts = (label || '').split(/\s+/).filter(Boolean);
    if (parts.length >= 2) return (parts[0][0] + parts[1][0]).toUpperCase();
    return (label?.slice(0, 2) || '?').toUpperCase();
  }, [label]);
  return (
    <div
      className="w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold border border-black/10"
      style={{ backgroundColor: bg, color }}
      title={label}
    >
      {initials}
    </div>
  );
}

export default function ActivityCard({
  activity,
  onVote,
  className,
  modalMaxWidth = '672px',
}: ActivityCardProps) {
  const [showModal, setShowModal] = useState(false);
  const [lastVote, setLastVote] = useState<'up' | 'down' | null>(null);

  const colorSet = useMemo(() => {
    const randomIdx = Math.floor(Math.random() * COLOR_SETS.length);
    return COLOR_SETS[randomIdx];
  }, []);

  const handleVote = async (vote: 'up' | 'down') => {
    setLastVote(vote);
    try {
      await onVote?.(activity, vote);
    } catch {
      setLastVote(null);
    }
  };

  return (
    <>
      {/* Simple Card */}
      <div
        className={`transition-all duration-200 rounded-2xl shadow-md cursor-pointer select-none hover:shadow-xl hover:scale-[1.02] overflow-hidden h-full flex flex-col ${
          className || ''
        }`}
        style={{ backgroundColor: colorSet.primary }}
        onClick={() => setShowModal(true)}
        role="button"
      >
        {/* Photo */}
        {activity.photo_url && (
          <div className="w-full h-32 overflow-hidden">
            <img
              src={activity.photo_url}
              alt={activity.name}
              className="w-full h-full object-cover"
              onError={(e) => {
                e.currentTarget.style.display = 'none';
              }}
            />
          </div>
        )}

        <div className="flex-1 p-6 text-left flex flex-col" style={{ color: colorSet.secondary }}>
          {/* Title */}
          <div className="flex-1 mb-4">
            <div className="text-xl font-extrabold leading-tight mb-2">{activity.name}</div>
            <div className="text-sm opacity-90 font-semibold">{activity.category}</div>
          </div>

          {/* Vote Buttons - Large and Prominent */}
          <div
            className="flex items-center justify-end gap-3 mt-auto"
            onClick={(e) => e.stopPropagation()}
          >
            <button
              aria-label="Thumbs up"
              onClick={() => handleVote('up')}
              disabled={lastVote === 'down'}
              className={`w-14 h-14 rounded-xl text-2xl font-bold border-3 shadow-md transition-all flex items-center justify-center ${
                lastVote === 'up'
                  ? 'scale-110 shadow-xl ring-2 ring-green-400'
                  : lastVote === 'down'
                    ? 'opacity-30 cursor-not-allowed'
                    : 'hover:scale-110 hover:shadow-lg active:scale-95'
              }`}
              style={{
                backgroundColor: lastVote === 'up' ? '#10b981' : colorSet.secondary,
                color: lastVote === 'up' ? '#ffffff' : colorSet.primary,
                borderColor: lastVote === 'up' ? '#10b981' : colorSet.primary,
                borderWidth: '3px',
              }}
            >
              👍
            </button>
            <button
              aria-label="Thumbs down"
              onClick={() => handleVote('down')}
              disabled={lastVote === 'up'}
              className={`w-14 h-14 rounded-xl text-2xl font-bold border-3 shadow-md transition-all flex items-center justify-center ${
                lastVote === 'down'
                  ? 'scale-110 shadow-xl ring-2 ring-red-400'
                  : lastVote === 'up'
                    ? 'opacity-30 cursor-not-allowed'
                    : 'hover:scale-110 hover:shadow-lg active:scale-95'
              }`}
              style={{
                backgroundColor: lastVote === 'down' ? '#ef4444' : colorSet.secondary,
                color: lastVote === 'down' ? '#ffffff' : colorSet.primary,
                borderColor: lastVote === 'down' ? '#ef4444' : colorSet.primary,
                borderWidth: '3px',
              }}
            >
              👎
            </button>
          </div>
        </div>
      </div>

      {/* Detail Modal */}
      <Modal
        isOpen={showModal}
        onClose={() => setShowModal(false)}
        backgroundColor={colorSet.primary}
        width="100%"
        maxWidth={modalMaxWidth}
      >
        <div className="max-h-[85vh] overflow-y-auto" style={{ color: colorSet.secondary }}>
          {/* Photo in Modal */}
          {activity.photo_url && (
            <div className="w-full h-64 -mx-6 -mt-6 mb-6 overflow-hidden">
              <img
                src={activity.photo_url}
                alt={activity.name}
                className="w-full h-full object-cover"
                onError={(e) => {
                  e.currentTarget.style.display = 'none';
                }}
              />
            </div>
          )}

          {/* Header */}
          <div className="mb-6">
            <h2 className="text-3xl font-extrabold mb-3 leading-tight">{activity.name}</h2>
            <div className="text-lg font-semibold opacity-90">{activity.category}</div>
          </div>

          {/* Key Info Grid */}
          <div className="grid grid-cols-2 gap-4 mb-6">
            <div className="p-4 rounded-xl" style={{ backgroundColor: 'rgba(0,0,0,0.1)' }}>
              <div className="text-sm opacity-80 mb-1">Duration</div>
              <div className="text-xl font-bold">
                {formatDuration(activity.duration_min ?? undefined)}
              </div>
            </div>
            <div className="p-4 rounded-xl" style={{ backgroundColor: 'rgba(0,0,0,0.1)' }}>
              <div className="text-sm opacity-80 mb-1">Cost</div>
              <div className="text-xl font-bold">
                {formatCost(activity.rough_cost ?? undefined)}
              </div>
            </div>
          </div>

          {/* Score */}
          <div className="mb-6 p-4 rounded-xl" style={{ backgroundColor: 'rgba(0,0,0,0.1)' }}>
            <div className="text-sm opacity-80 mb-1">Match Score</div>
            <div className="text-3xl font-extrabold">
              {Math.round((activity.score ?? 0) * 100)}%
            </div>
          </div>

          {/* Location & Map */}
          {activity.lat != null && activity.lng != null && (
            <div className="mb-6">
              <div className="text-sm opacity-80 mb-2">Location</div>

              {/* Embedded Google Map */}
              <div className="mb-3">
                <GoogleMapEmbed
                  lat={activity.lat}
                  lng={activity.lng}
                  zoom={15}
                  height="350px"
                  className="shadow-md"
                />
              </div>
            </div>
          )}

          {/* Tags */}
          {!!activity.tags?.length && (
            <div className="mb-6">
              <div className="text-sm opacity-80 mb-2">Tags</div>
              <div className="flex flex-wrap gap-2">
                {activity.tags.map((t) => (
                  <span
                    key={t}
                    className="px-3 py-1.5 text-sm font-bold rounded-full border-2"
                    style={{
                      backgroundColor: colorSet.secondary,
                      color: colorSet.primary,
                      borderColor: colorSet.primary,
                    }}
                  >
                    #{t}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Rationale */}
          {activity.rationale && (
            <div className="mb-6">
              <div className="text-sm opacity-80 mb-2">Why this activity?</div>
              <div
                className="text-base leading-relaxed p-4 rounded-xl"
                style={{ backgroundColor: 'rgba(0,0,0,0.1)' }}
              >
                {activity.rationale}
              </div>
            </div>
          )}

          {/* Good For */}
          {!!activity.fits?.length && (
            <div className="mb-6">
              <div className="text-sm opacity-80 mb-3">Good for</div>
              <div className="flex flex-wrap gap-3">
                {activity.fits.map((fitId) => (
                  <Avatar
                    key={fitId}
                    label={fitId}
                    bg={colorSet.secondary}
                    color={colorSet.primary}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Vote Buttons in Modal */}
          <div
            className="flex items-center gap-4 pt-4 border-t-2"
            style={{ borderColor: 'rgba(255,255,255,0.2)' }}
          >
            <button
              onClick={() => handleVote('up')}
              disabled={lastVote === 'down'}
              className={`w-14 h-14 rounded-xl text-2xl font-bold border-2 transition-all flex items-center justify-center ${
                lastVote === 'up'
                  ? 'scale-105 shadow-lg'
                  : lastVote === 'down'
                    ? 'opacity-30 cursor-not-allowed'
                    : 'hover:scale-105'
              }`}
              style={{
                backgroundColor: colorSet.secondary,
                color: colorSet.primary,
                borderColor: colorSet.primary,
              }}
            >
              👍
            </button>
            <button
              onClick={() => handleVote('down')}
              disabled={lastVote === 'up'}
              className={`w-14 h-14 rounded-xl text-2xl font-bold border-2 transition-all flex items-center justify-center ${
                lastVote === 'down'
                  ? 'scale-105 shadow-lg'
                  : lastVote === 'up'
                    ? 'opacity-30 cursor-not-allowed'
                    : 'hover:scale-105'
              }`}
              style={{
                backgroundColor: colorSet.secondary,
                color: colorSet.primary,
                borderColor: colorSet.primary,
              }}
            >
              👎
            </button>
          </div>
        </div>
      </Modal>
    </>
  );
}
