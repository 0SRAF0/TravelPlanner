import { useState, useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import Input from '../input/Input';
import { chatBotService, type ChatMessage } from '../../services/chatBotService.ts';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faXmark, faPaperPlane } from '@fortawesome/free-solid-svg-icons';

interface ChatBoxProps {
  isOpen: boolean;
  onClose: () => void;
}

export const ChatBox = ({ isOpen, onClose }: ChatBoxProps) => {
  const navigate = useNavigate();
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      role: 'assistant',
      content:
        "Hi! I'm your AI travel planning assistant. How can I help you plan your trip today?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  useEffect(() => {
    if (isOpen && inputRef.current) {
      inputRef.current.focus();
    }
  }, [isOpen]);

  const handleSend = async () => {
    if (!input.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: input.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    try {
      const response = await chatBotService.sendMessage(userMessage.content, messages);
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content:
          error instanceof Error ? error.message : 'Sorry, something went wrong. Please try again.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  // Send a message programmatically (used by quick action buttons)
  const sendPrefilledMessage = async (text: string) => {
    if (!text.trim() || isLoading) return;

    const userMessage: ChatMessage = {
      role: 'user',
      content: text.trim(),
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setIsLoading(true);

    try {
      // include current UI context (path) so assistant can provide contextual help
      const contextNote = `Current path: ${window.location.pathname}`;
      const response = await chatBotService.sendMessage(`${text}\n\n${contextNote}`, messages.concat(userMessage));
      const assistantMessage: ChatMessage = {
        role: 'assistant',
        content: response,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (error) {
      const errorMessage: ChatMessage = {
        role: 'assistant',
        content:
          error instanceof Error ? error.message : 'Sorry, something went wrong. Please try again.',
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const escapeHtml = (text: string) =>
    text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

  const formatMessage = (text: string) => {
    const escaped = escapeHtml(text);
    return escaped
      .replace(/\*\*(.+?)\*\*/gs, '<strong>$1</strong>')
      .replace(/(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)/gs, '<em>$1</em>')
      .replace(/`(.+?)`/gs, '<code>$1</code>')
      .replace(/\n/g, '<br />');
  };

  // Suggested quick actions for support assistant
  const suggestedActions: { label: string; type: 'nav' | 'msg' | 'join'; payload?: string }[] = [
    { label: 'Create a trip', type: 'nav', payload: '/dashboard?action=create' },
    { label: 'Join a trip', type: 'join' },
    { label: 'Where are my trips?', type: 'nav', payload: '/dashboard' },
  ];

  const [joinPromptOpen, setJoinPromptOpen] = useState(false);
  const [joinCode, setJoinCode] = useState('');
  const joinInputRef = useRef<HTMLInputElement>(null);

  const submitJoinCode = () => {
    const code = (joinCode || '').trim();
    if (!code) return;
    // Navigate to dashboard with params that will auto-join
    navigate(`/dashboard?action=join&trip_code=${encodeURIComponent(code)}&auto=true`);
    setJoinPromptOpen(false);
    setJoinCode('');
    // keep chat open — user will see navigation
  };

  useEffect(() => {
    if (joinPromptOpen) {
      // focus the inline join input
      setTimeout(() => joinInputRef.current?.focus(), 50);
    }
  }, [joinPromptOpen]);

  const handleKeyPress = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed bottom-20 right-6 w-96 h-[600px] bg-white rounded-3xl shadow-2xl border border-gray-200 flex flex-col z-50 mb-4">
      {/* Header */}
      <div className="flex items-center justify-between p-4 border-b border-gray-200 bg-gradient-to-r from-accent to-primary rounded-t-3xl">
        <div className="flex items-center space-x-2">
          <h3 className="text-white font-semibold">AI Travel Assistant</h3>
        </div>
        <button
          onClick={onClose}
          className="text-white hover:bg-blue-700 rounded-full p-1 transition-colors"
          aria-label="Close chat"
        >
          <FontAwesomeIcon icon={faXmark} className="w-5 h-5" />
        </button>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-gray-50">
        {messages.map((message, index) => (
          <div
            key={index}
            className={`flex ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2 text-left ${message.role === 'user'
                ? 'bg-primary text-white'
                : 'bg-white text-gray-800 border border-gray-200'
              }`}
            >
              <p
                className="text-sm whitespace-pre-wrap text-left leading-relaxed space-y-1"
                dangerouslySetInnerHTML={{ __html: formatMessage(message.content) }}
              />
            </div>
          </div>
        ))}
        {/* Quick suggestion chips shown under the initial assistant message */}
        {messages.length > 0 && messages[0]?.role === 'assistant' && (
          <div className="flex flex-col gap-2 mt-1">
            <div className="flex flex-wrap gap-2">
              {suggestedActions.map((a) => (
                <button
                  key={a.label}
                  onClick={() => {
                    if (a.type === 'nav' && a.payload) navigate(a.payload);
                    else if (a.type === 'msg' && a.payload) sendPrefilledMessage(a.payload);
                    else if (a.type === 'join') setJoinPromptOpen(true);
                  }}
                  className="px-3 py-1 bg-gray-100 text-sm rounded-full border border-gray-200 hover:bg-gray-200"
                >
                  {a.label}
                </button>
              ))}
            </div>

            {joinPromptOpen && (
              <div className="flex items-center gap-2 mt-2">
                <input
                  ref={joinInputRef}
                  type="text"
                  placeholder="Enter trip code"
                  value={joinCode}
                  onChange={(e) => setJoinCode(e.target.value.toUpperCase())}
                  onKeyPress={(e: React.KeyboardEvent<HTMLInputElement>) => {
                    if (e.key === 'Enter') submitJoinCode();
                  }}
                  className="flex-1 px-3 py-2 border border-gray-300 rounded-lg"
                />
                <button
                  onClick={submitJoinCode}
                  className="px-3 py-1 bg-primary text-white rounded-lg"
                >
                  Join
                </button>
                <button
                  onClick={() => {
                    setJoinPromptOpen(false);
                    setJoinCode('');
                  }}
                  className="px-3 py-1 bg-gray-100 rounded-lg border"
                >
                  Cancel
                </button>
              </div>
            )}
          </div>
        )}
        {isLoading && (
          <div className="flex justify-start">
            <div className="bg-white border border-gray-200 rounded-lg px-4 py-2">
              <div className="flex space-x-1">
                <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"></div>
                <div
                  className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                  style={{ animationDelay: '0.1s' }}
                ></div>
                <div
                  className="w-2 h-2 bg-gray-400 rounded-full animate-bounce"
                  style={{ animationDelay: '0.2s' }}
                ></div>
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="p-4 rounded-b-lg">
        <div className="flex space-x-2 items-center">
          <div className="flex-1">
            <Input
              type="text"
              placeholder="Type your message..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyPress={handleKeyPress}
              disabled={isLoading}
              className="m-0 w-full"
            />
          </div>
          <button
            onClick={handleSend}
            disabled={isLoading || !input.trim()}
            aria-label="Send message"
            title="Send"
            className="transition-colors mx-2 disabled:cursor-not-allowed text-xl"
          >
            <FontAwesomeIcon
              icon={faPaperPlane}
              className={`w-5 h-5 ${isLoading || !input.trim() ? 'opacity-50' : 'hover:opacity-90'}`}
              style={{ color: 'var(--color-primary)' }}
            />
          </button>
        </div>
      </div>
    </div>
  );
};
