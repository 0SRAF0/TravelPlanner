import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Button from "../../components/button/Button";
import Input from "../../components/input/Input";
import Notification from "../../components/notification/Notification";
import LocationAutocomplete from "../../components/input/LocationAutocomplete";

interface PreferenceFormProps {
  tripId: string;
  userId: string;
  onComplete?: () => void;
}

type Vibe = "Adventure" | "Food" | "Nightlife" | "Culture" | "Relax" | "Nature";

const VIBE_OPTIONS: { value: Vibe; emoji: string; description: string }[] = [
  { value: "Adventure", emoji: "🏔️", description: "Thrills & excitement" },
  { value: "Food", emoji: "🍜", description: "Culinary experiences" },
  { value: "Nightlife", emoji: "🎉", description: "Bars & parties" },
  { value: "Culture", emoji: "🎭", description: "Museums & history" },
  { value: "Relax", emoji: "🧘", description: "Chill & unwind" },
  { value: "Nature", emoji: "🌲", description: "Outdoors & scenery" },
];

const BUDGET_LABELS = {
  1: { label: "Budget", symbol: "$", description: "Keep it cheap" },
  2: { label: "Moderate", symbol: "$$", description: "Good value" },
  3: { label: "Comfort", symbol: "$$$", description: "Nice experiences" },
  4: { label: "Luxury", symbol: "$$$$", description: "Treat yourself" },
};

export default function PreferenceForm({
  tripId,
  userId,
  onComplete,
}: PreferenceFormProps) {
  const navigate = useNavigate();
  // Ensure we have valid tripId and userId; fall back to localStorage / URL when possible
  const effectiveUserId =
    userId || JSON.parse(localStorage.getItem("user_info") || "{}").id;
  const effectiveTripId = tripId || window.location.pathname.split("/")[2];
  const [budgetLevel, setBudgetLevel] = useState<number>(2);
  const [selectedVibes, setSelectedVibes] = useState<Vibe[]>([]);
  const [dealBreaker, setDealBreaker] = useState("");
  const [notes, setNotes] = useState("");
  const [destination, setDestination] = useState("");
  const [availableDates, setAvailableDates] = useState<
    { start: string; end: string }[]
  >([]);
  const [newDateStart, setNewDateStart] = useState("");
  const [newDateEnd, setNewDateEnd] = useState("");
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState<{
    message: string;
    type?: "success" | "error" | "warning";
  } | null>(null);

  const toggleVibe = (vibe: Vibe) => {
    if (selectedVibes.includes(vibe)) {
      setSelectedVibes(selectedVibes.filter((v) => v !== vibe));
    } else if (selectedVibes.length < 6) {
      setSelectedVibes([...selectedVibes, vibe]);
    } else {
      setToast({ message: "Maximum 6 vibes allowed", type: "warning" });
    }
  };

  const handleSubmit = async () => {
    // Validate presence of required IDs before sending
    if (!effectiveTripId || !effectiveUserId) {
      setToast({
        message:
          "Missing trip or user id. Please sign in and open the trip again.",
        type: "error",
      });
      return;
    }

    if (selectedVibes.length === 0) {
      setToast({ message: "Please select at least one vibe", type: "warning" });
      return;
    }

    setLoading(true);
    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/preferences/`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
          },
          body: JSON.stringify({
            trip_id: effectiveTripId,
            user_id: effectiveUserId,
            destination: destination.trim() || null,
            available_dates: availableDates.map((d) => `${d.start}:${d.end}`),
            budget_level: budgetLevel,
            vibes: selectedVibes.map((v) => String(v)),
            deal_breaker: dealBreaker.trim() || null,
            notes: notes.trim() || null,
          }),
        }
      );

      const result = await response.json();

      if (result.code === 0) {
        setToast({
          message: "Preferences saved successfully!",
          type: "success",
        });
        setTimeout(() => {
          onComplete?.();
          navigate(`/trip/${effectiveTripId}`);
        }, 1500);
      } else {
        throw new Error(result.msg || "Failed to save preferences");
      }
    } catch (err) {
      setToast({
        message:
          err instanceof Error ? err.message : "Failed to save preferences",
        type: "error",
      });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 py-8 px-4">
      <div className="max-w-3xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-3xl font-bold text-gray-900 mb-2">
            Set Your Preferences
          </h1>
          <p className="text-gray-600">
            Help us plan the perfect trip for your group
          </p>
        </div>

        <div className="bg-white rounded-2xl shadow-lg p-8 space-y-8">
          {/* Destination */}
          <div>
            <label className="block text-lg font-bold text-gray-900 mb-3">
              Where do you want to go? (Optional)
            </label>
            <LocationAutocomplete
              value={destination}
              onChange={setDestination}
              placeholder="e.g., Tokyo, Japan"
            />
            <p className="text-sm text-gray-500 mt-2">
              Start typing to see real location suggestions
            </p>
          </div>

          {/* Available Dates */}
          <div>
            <label className="block text-lg font-bold text-gray-900 mb-3">
              When are you available? (Optional)
            </label>
            <p className="text-sm text-gray-600 mb-4">
              Add one or more date ranges when you're free to travel
            </p>

            {/* Added Date Ranges */}
            {availableDates.length > 0 && (
              <div className="space-y-2 mb-4">
                {availableDates.map((dateRange, idx) => (
                  <div
                    key={idx}
                    className="flex items-center justify-between p-3 bg-blue-50 border-2 border-blue-200 rounded-lg"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-medium">
                        {new Date(dateRange.start).toLocaleDateString()} -{" "}
                        {new Date(dateRange.end).toLocaleDateString()}
                      </span>
                      <span className="text-xs text-gray-600">
                        (
                        {Math.ceil(
                          (new Date(dateRange.end).getTime() -
                            new Date(dateRange.start).getTime()) /
                            (1000 * 60 * 60 * 24)
                        ) + 1}{" "}
                        days)
                      </span>
                    </div>
                    <button
                      onClick={() =>
                        setAvailableDates(
                          availableDates.filter((_, i) => i !== idx)
                        )
                      }
                      className="text-red-500 hover:text-red-700 font-bold"
                    >
                      ✕
                    </button>
                  </div>
                ))}
              </div>
            )}

            {/* Add New Date Range */}
            <div className="space-y-3">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Start Date
                  </label>
                  <input
                    type="date"
                    value={newDateStart}
                    onChange={(e) => setNewDateStart(e.target.value)}
                    min={new Date().toISOString().split("T")[0]}
                    className="w-full px-4 py-2 border-2 border-gray-200 rounded-lg focus:border-blue-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    End Date
                  </label>
                  <input
                    type="date"
                    value={newDateEnd}
                    onChange={(e) => setNewDateEnd(e.target.value)}
                    min={newDateStart || new Date().toISOString().split("T")[0]}
                    className="w-full px-4 py-2 border-2 border-gray-200 rounded-lg focus:border-blue-500 focus:outline-none"
                  />
                </div>
              </div>
              <button
                onClick={() => {
                  if (newDateStart && newDateEnd) {
                    if (new Date(newDateEnd) >= new Date(newDateStart)) {
                      setAvailableDates([
                        ...availableDates,
                        { start: newDateStart, end: newDateEnd },
                      ]);
                      setNewDateStart("");
                      setNewDateEnd("");
                    } else {
                      setToast({
                        message: "End date must be after start date",
                        type: "warning",
                      });
                    }
                  } else {
                    setToast({
                      message: "Please select both start and end dates",
                      type: "warning",
                    });
                  }
                }}
                className="w-full md:w-auto px-6 py-2 bg-gray-100 hover:bg-gray-200 border-2 border-gray-300 rounded-lg font-medium transition-colors"
              >
                + Add Date Range
              </button>
            </div>
          </div>

          {/* Budget Level */}
          <div>
            <label className="block text-lg font-bold text-gray-900 mb-4">
              What's your budget level?
            </label>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Object.entries(BUDGET_LABELS).map(([level, info]) => (
                <button
                  key={level}
                  onClick={() => setBudgetLevel(Number(level))}
                  className={`p-4 rounded-xl border-2 transition-all ${
                    budgetLevel === Number(level)
                      ? "border-blue-500 bg-blue-50"
                      : "border-gray-200 hover:border-gray-300"
                  }`}
                >
                  <div className="text-2xl mb-1">{info.symbol}</div>
                  <div className="font-bold text-sm">{info.label}</div>
                  <div className="text-xs text-gray-500">
                    {info.description}
                  </div>
                </button>
              ))}
            </div>
          </div>

          {/* Vibes */}
          <div>
            <label className="block text-lg font-bold text-gray-900 mb-2">
              Pick your vibes (up to 6)
            </label>
            <p className="text-sm text-gray-600 mb-4">
              Selected: {selectedVibes.length}/6
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
              {VIBE_OPTIONS.map((vibe) => {
                const isSelected = selectedVibes.includes(vibe.value);
                const order = selectedVibes.indexOf(vibe.value);
                return (
                  <button
                    key={vibe.value}
                    onClick={() => toggleVibe(vibe.value)}
                    className={`p-4 rounded-xl border-2 transition-all relative ${
                      isSelected
                        ? "border-blue-500 bg-blue-50"
                        : "border-gray-200 hover:border-gray-300"
                    }`}
                  >
                    {isSelected && (
                      <div className="absolute top-2 right-2 w-6 h-6 bg-blue-500 text-white rounded-full flex items-center justify-center text-xs font-bold">
                        {order + 1}
                      </div>
                    )}
                    <div className="text-3xl mb-2">{vibe.emoji}</div>
                    <div className="font-bold text-sm">{vibe.value}</div>
                    <div className="text-xs text-gray-500">
                      {vibe.description}
                    </div>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Deal Breaker */}
          <div>
            <label className="block text-lg font-bold text-gray-900 mb-3">
              Any deal breakers? (Optional)
            </label>
            <Input
              type="text"
              placeholder="e.g., No early mornings, No spicy food"
              value={dealBreaker}
              onChange={(e) => setDealBreaker(e.target.value)}
              size="lg"
            />
          </div>

          {/* Additional Notes */}
          <div>
            <label className="block text-lg font-bold text-gray-900 mb-3">
              Any other preferences? (Optional)
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="e.g., Love hiking, prefer public transport, vegetarian options..."
              className="w-full px-4 py-3 border-2 border-gray-200 rounded-xl focus:border-blue-500 focus:outline-none resize-none"
              rows={3}
            />
          </div>

          {/* Submit Button */}
          <div className="pt-4">
            <Button
              text={loading ? "Saving..." : "Save Preferences"}
              onClick={handleSubmit}
              size="lg"
            />
          </div>
        </div>

        {/* Help Text */}
        <div className="text-center mt-6 text-sm text-gray-600">
          <p>💡 Don't worry, you can always change these later</p>
        </div>
      </div>

      {/* Toast Notifications */}
      <Notification
        isVisible={!!toast}
        message={toast?.message || ""}
        type={toast?.type}
        onClose={() => setToast(null)}
      />
    </div>
  );
}
