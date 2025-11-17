import { useNavigate } from "react-router-dom";
import Button from "../../components/button/Button";

export const Home = () => {
  const navigate = useNavigate();

  const handleGetStarted = () => {
    navigate("/sign-in");
  };

  return (
    <div className="min-h-screen flex flex-col items-center justify-center px-6 py-12">
      {/* Hero Section */}
      <div className="max-w-4xl mx-auto text-center space-y-8">
        <h1 className="text-5xl font-bold text-gray-900 leading-tight">
          Plan Your Next Adventure Together
        </h1>

        <p className="text-xl text-gray-600 max-w-2xl mx-auto">
          AI-powered collaborative trip planning that brings your group's
          preferences together
        </p>

        {/* Features */}
        <div className="grid md:grid-cols-3 gap-8 mt-16 mb-12">
          <div className="space-y-3">
            <div className="text-4xl">👥</div>
            <h3 className="text-lg font-semibold text-gray-900">
              Create trips with friends
            </h3>
            <p className="text-sm text-gray-600">
              Invite your group and plan together seamlessly
            </p>
          </div>

          <div className="space-y-3">
            <div className="text-4xl">🤖</div>
            <h3 className="text-lg font-semibold text-gray-900">
              AI suggests activities
            </h3>
            <p className="text-sm text-gray-600">
              Get personalized recommendations based on everyone's preferences
            </p>
          </div>

          <div className="space-y-3">
            <div className="text-4xl">⚡</div>
            <h3 className="text-lg font-semibold text-gray-900">
              Real-time collaboration
            </h3>
            <p className="text-sm text-gray-600">
              Vote and plan together in real-time
            </p>
          </div>
        </div>

        {/* CTA Button */}
        <div className="pt-8">
          <Button text="Start Planning" onClick={handleGetStarted} size="lg" />
        </div>
      </div>
    </div>
  );
};
