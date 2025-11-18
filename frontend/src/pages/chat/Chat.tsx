import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Button from '../../components/button/Button';
import { API } from '../../services/api';

interface Message {
  senderId: string;
  senderName: string;
  content: string;
  type: 'user' | 'ai' | 'agent_status';
  timestamp: string;
  agent_name?: string;
  status?: string;
  step?: string;
}

interface AgentStatus {
  agent_name: string;
  status: 'starting' | 'running' | 'completed' | 'error';
  step: string;
  timestamp: string;
}

export function Chat() {
  const { tripId } = useParams<{ tripId: string }>();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Message[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatus[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const currentUser = JSON.parse(localStorage.getItem('user_info') || '{}');

  useEffect(() => {
    if (!tripId) return;

    // Connect to WebSocket
    const wsUrl = `${API.chat.chat}/${tripId}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[Chat] WebSocket connected');
      setIsConnected(true);
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);

      // Handle agent status updates separately
      if (message.type === 'agent_status') {
        setAgentStatuses((prev) => {
          const existing = prev.findIndex((s) => s.agent_name === message.agent_name);
          if (existing >= 0) {
            const updated = [...prev];
            updated[existing] = message;
            return updated;
          }
          return [...prev, message];
        });
      } else {
        setMessages((prev) => [...prev, message]);
      }
    };

    ws.onerror = (error) => {
      console.error('[Chat] WebSocket error:', error);
    };

    ws.onclose = () => {
      console.log('[Chat] WebSocket disconnected');
      setIsConnected(false);
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [tripId]);

  useEffect(() => {
    // Auto-scroll to bottom when new messages arrive
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSendMessage = () => {
    if (!inputMessage.trim() || !wsRef.current || !isConnected) return;

    const messageData = {
      senderId: currentUser.id || 'unknown',
      senderName: currentUser.name || 'Anonymous',
      content: inputMessage,
      type: 'user',
      timestamp: new Date().toISOString(),
    };

    wsRef.current.send(JSON.stringify(messageData));
    setInputMessage('');
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'starting':
        return 'bg-yellow-100 border-yellow-300 text-yellow-800';
      case 'running':
        return 'bg-blue-100 border-blue-300 text-blue-800';
      case 'completed':
        return 'bg-green-100 border-green-300 text-green-800';
      case 'error':
        return 'bg-red-100 border-red-300 text-red-800';
      default:
        return 'bg-gray-100 border-gray-300 text-gray-800';
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'starting':
        return '⏳';
      case 'running':
        return '⚙️';
      case 'completed':
        return '✅';
      case 'error':
        return '❌';
      default:
        return '📝';
    }
  };

  return (
    <div className="min-h-screen py-8 px-4">
      <div className="max-w-7xl mx-auto">
        {/* Header */}
        <div className="bg-white rounded-lg shadow-sm p-4 mb-4 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">Group Trip Chat</h1>
            <p className="text-sm text-gray-600">
              {isConnected ? (
                <span className="text-green-600">● Connected</span>
              ) : (
                <span className="text-red-600">● Disconnected</span>
              )}
            </p>
          </div>
          <Button text="Back to Trip" onClick={() => navigate(`/trip/${tripId}`)} />
        </div>

        <div className="flex gap-4">
          {/* Agent Status Sidebar */}
          <div className="w-80 bg-white rounded-lg shadow-sm p-4 h-[600px] overflow-y-auto">
            <h2 className="text-lg font-bold text-gray-900 mb-4 flex items-center gap-2">
              🤖 AI Agent Status
            </h2>

            {agentStatuses.length === 0 ? (
              <div className="text-center text-gray-500 py-8">
                <p className="text-sm">No active agents</p>
                <p className="text-xs mt-2">Agents will appear here when working</p>
              </div>
            ) : (
              <div className="space-y-3">
                {agentStatuses.map((agent, idx) => (
                  <div
                    key={idx}
                    className={`border-2 rounded-lg p-3 ${getStatusColor(agent.status)}`}
                  >
                    <div className="flex items-center gap-2 mb-2">
                      <span className="text-lg">{getStatusIcon(agent.status)}</span>
                      <span className="font-semibold text-sm">{agent.agent_name}</span>
                    </div>
                    <p className="text-xs font-medium mb-1">Status: {agent.status}</p>
                    <p className="text-xs">{agent.step}</p>
                    {agent.status === 'running' && (
                      <div className="mt-2">
                        <div className="w-full bg-gray-200 rounded-full h-1.5">
                          <div className="bg-blue-600 h-1.5 rounded-full animate-pulse w-3/4"></div>
                        </div>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Messages Container */}
          <div className="flex-1 bg-white rounded-lg shadow-sm p-4 h-[600px] flex flex-col">
            {/* Messages List */}
            <div className="flex-1 overflow-y-auto mb-4 space-y-4">
              {messages.length === 0 ? (
                <div className="text-center text-gray-500 mt-20">
                  <p className="text-lg">No messages yet</p>
                  <p className="text-sm mt-2">
                    Start the conversation! Type "leggo" to get AI suggestions.
                  </p>
                </div>
              ) : (
                messages.map((msg, idx) => (
                  <div
                    key={idx}
                    className={`flex ${
                      msg.senderId === currentUser.id ? 'justify-end' : 'justify-start'
                    }`}
                  >
                    <div
                      className={`max-w-[70%] rounded-lg px-4 py-2 ${
                        msg.type === 'ai'
                          ? 'bg-blue-100 border border-blue-300'
                          : msg.senderId === currentUser.id
                            ? 'bg-indigo-600 text-white'
                            : 'bg-gray-200 text-gray-900'
                      }`}
                    >
                      <p className="text-xs font-semibold mb-1 opacity-75">{msg.senderName}</p>
                      <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                      <p className="text-xs mt-1 opacity-60">
                        {new Date(msg.timestamp).toLocaleTimeString()}
                      </p>
                    </div>
                  </div>
                ))
              )}
              <div ref={messagesEndRef} />
            </div>

            {/* Input Area */}
            <div className="border-t pt-4">
              <div className="flex gap-2">
                <textarea
                  value={inputMessage}
                  onChange={(e) => setInputMessage(e.target.value)}
                  onKeyPress={handleKeyPress}
                  placeholder="Type your message... (Press Enter to send, Shift+Enter for new line)"
                  className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 resize-none"
                  rows={2}
                  disabled={!isConnected}
                />
                <Button text="Send" onClick={handleSendMessage} />
              </div>
              <p className="text-xs text-gray-500 mt-2">
                💡 Tip: Type "leggo" in your message to trigger AI travel suggestions
              </p>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
