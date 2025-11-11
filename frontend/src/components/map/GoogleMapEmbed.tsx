interface GoogleMapEmbedProps {
  lat: number;
  lng: number;
  zoom?: number;
  width?: string;
  height?: string;
  className?: string;
}

export default function GoogleMapEmbed({
  lat,
  lng,
  zoom = 15,
  width = '100%',
  height = '300px',
  className = '',
}: GoogleMapEmbedProps) {
  // Get API key from environment variable
  const apiKey = import.meta.env.VITE_GOOGLE_MAPS_API_KEY;

  if (!apiKey) {
    return (
      <div
        className={`flex items-center justify-center bg-gray-100 rounded-xl ${className}`}
        style={{ width, height }}
      >
        <div className="text-center p-4">
          <p className="text-sm text-gray-600">
            Map unavailable: API key not configured
          </p>
          <p className="text-xs text-gray-500 mt-1">
            Add VITE_GOOGLE_MAPS_API_KEY to .env
          </p>
        </div>
      </div>
    );
  }

  // Google Maps Embed API URL
  const mapUrl = `https://www.google.com/maps/embed/v1/place?key=${apiKey}&q=${lat},${lng}&zoom=${zoom}`;

  return (
    <iframe
      className={`rounded-xl border-0 ${className}`}
      width={width}
      height={height}
      style={{ border: 0 }}
      loading="lazy"
      allowFullScreen
      referrerPolicy="no-referrer-when-downgrade"
      src={mapUrl}
      title="Activity Location Map"
    />
  );
}

