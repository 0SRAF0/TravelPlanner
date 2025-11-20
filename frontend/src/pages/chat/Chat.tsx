import { useEffect, useRef, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Button from '../../components/button/Button';
import ActivityList from '../../components/activity/ActivityList';
import VotedButton from '../../components/phase/VotedButton';
import { API } from '../../services/api';

interface Message {
  senderId: string;
  senderName: string;
  content: string;
  type: 'user' | 'ai' | 'agent_status' | 'voting' | 'vote_update';
  timestamp: string;
  agent_name?: string;
  status?: string;
  step?: string;
  phase?: string;
  options?: Array<{ value: string; label: string; votes: number; voters: string[] }>;
}

interface AgentStatus {
  agent_name: string;
  status: 'starting' | 'running' | 'completed' | 'error';
  step: string;
  timestamp: string;
  progress?: { current: number; total: number } | number;
  elapsed_seconds?: number;
  step_history?: Array<{ step: string; timestamp: string }>;
}

export function Chat() {
  const { tripId } = useParams<{ tripId: string }>();
  const navigate = useNavigate();
  const [messages, setMessages] = useState<Message[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<AgentStatus[]>([]);
  const [inputMessage, setInputMessage] = useState('');
  const [showHistory, setShowHistory] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [currentPhase, setCurrentPhase] = useState<string>('');
  const [usersReady, setUsersReady] = useState<string[]>([]);
  const [totalUsers, setTotalUsers] = useState<number>(0);
  const [votingData, setVotingData] = useState<{ phase: string; options: any[] } | null>(null);
  const [resolvedPhases, setResolvedPhases] = useState<Set<string>>(new Set());
  const [votedPhases, setVotedPhases] = useState<Set<string>>(new Set());
  const [activityRefreshKey, setActivityRefreshKey] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const currentUser = JSON.parse(localStorage.getItem('user_info') || '{}');

  // Simple, safe markdown renderer for basic bold/italic using asterisks
  // - Escapes HTML to avoid XSS
  // - Supports **bold** and *italic* (non-greedy)
  const escapeHtml = (unsafe: string) =>
    unsafe
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');

  const renderMessageContent = (text: string) => {
    if (!text) return '';
    // Escape first
    let out = escapeHtml(text);

    // Replace bold (**text**)
    out = out.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');

    // Replace italic (*text*) but avoid interfering with bold already replaced
    out = out.replace(/\*(.+?)\*/g, '<em>$1</em>');

    // Preserve line breaks
    out = out.replace(/\r?\n/g, '<br/>');

    return out;
  };

  useEffect(() => {
    if (!tripId) return;

    // Connect to WebSocket
    const wsUrl = `${API.chat.chat}/${tripId}`;
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('[Chat] WebSocket connected');
      setIsConnected(true);
      // Send a ping message to complete the WebSocket handshake loop on the backend
      ws.send(
        JSON.stringify({
          type: 'ping',
          senderId: currentUser.id || 'anonymous',
          senderName: currentUser.name || 'Anonymous',
          content: '',
        }),
      );
    };

    ws.onmessage = (event) => {
      const message = JSON.parse(event.data);

      // Handle agent status updates separately
      if (message.type === 'agent_status') {
        setAgentStatuses((prev) => {
          const existing = prev.findIndex((s) => s.agent_name === message.agent_name);
          if (existing >= 0) {
            const updated = [...prev];
            const oldAgent = updated[existing];
            // Merge step history (keep last 10 steps)
            const newHistory = [
              ...(oldAgent.step_history || []),
              { step: oldAgent.step, timestamp: oldAgent.timestamp },
            ].slice(-10);
            updated[existing] = { ...message, step_history: newHistory };
            return updated;
          }
          return [...prev, { ...message, step_history: [] }];
        });

        // Trigger activity refresh when Destination Research Agent completes
        if (
          message.agent_name === 'Destination Research Agent' &&
          message.status === 'completed' &&
          message.step?.includes('activity suggestions')
        ) {
          console.log('[Chat] Activities ready, triggering refresh...');
          setActivityRefreshKey((prev) => prev + 1);
        }
      }
      // Handle phase ready updates
      else if (message.type === 'phase_ready_update') {
        setCurrentPhase(message.phase);
        // usersReady is an array of user IDs who clicked "Voted"
        const readyList = message.users_ready || [];
        setUsersReady(Array.isArray(readyList) ? readyList : []);
        setTotalUsers(message.total_users || 0);
      }
      // Handle voting messages
      else if (message.type === 'voting') {
        setVotingData({
          phase: message.phase,
          options: message.options || [],
        });
        setMessages((prev) => [...prev, message]);

        // Update current phase when voting message arrives
        if (message.phase) {
          setCurrentPhase(message.phase);
        }

        // Check if current user has already voted in this phase
        const hasVoted = message.options?.some((opt: any) => opt.voters?.includes(currentUser.id));
        if (hasVoted && message.phase) {
          setVotedPhases((prev) => new Set(prev).add(message.phase));
        }
      }
      // Handle vote updates
      else if (message.type === 'vote_update') {
        if (votingData && votingData.phase === message.phase) {
          setVotingData({
            phase: message.phase,
            options: message.options || [],
          });
        }
        // Update vote counts in the voting message
        setMessages((prev) =>
          prev.map((msg) =>
            msg.type === 'voting' && msg.phase === message.phase
              ? { ...msg, options: message.options || [] }
              : msg,
          ),
        );
      }
      // Handle when a phase is resolved (destination selected, etc.)
      else if (
        message.content &&
        (message.content.includes('Destination selected:') ||
          message.content.includes('Voting complete!'))
      ) {
        // Mark the current voting phase as resolved
        if (votingData?.phase) {
          setResolvedPhases((prev) => new Set(prev).add(votingData.phase));
        }
        setMessages((prev) => [...prev, message]);
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

  // Track user's current selections before submitting
  const [userSelections, setUserSelections] = useState<{ [phase: string]: string[] }>({});

  const toggleSelection = (option: string, phase: string) => {
    setUserSelections((prev) => {
      const current = prev[phase] || [];
      if (current.includes(option)) {
        // Remove selection
        return { ...prev, [phase]: current.filter((o) => o !== option) };
      } else {
        // Add selection
        return { ...prev, [phase]: [...current, option] };
      }
    });
  };

  const submitVote = async (phase: string) => {
    console.log('[submitVote] Called with phase:', phase);
    console.log('[submitVote] Current user:', currentUser.id);
    console.log('[submitVote] Trip ID:', tripId);

    if (!currentUser.id || !tripId || !phase) {
      console.error('[submitVote] Missing required data');
      return;
    }

    const selections = userSelections[phase] || [];
    console.log('[submitVote] Selections:', selections);

    if (selections.length === 0) {
      console.warn('[submitVote] No selections made');
      alert('Please select at least one option before voting.');
      return;
    }

    console.log('[submitVote] Starting vote submission...');
    try {
      // Submit the vote selections (vote endpoint also marks user as ready)
      const voteResponse = await fetch(API.trip.vote(tripId), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_id: currentUser.id,
          options: selections, // Submit all selected options
          phase: phase,
        }),
      });

      if (!voteResponse.ok) {
        console.error('Failed to submit vote');
        alert('Failed to submit vote. Please try again.');
        return;
      }

      console.log(`✅ Submitted vote for ${selections.join(', ')} in phase ${phase}`);

      // Mark phase as voted locally (disable the button)
      setVotedPhases((prev) => new Set(prev).add(phase));

      // Clear selections after successful submission
      setUserSelections((prev) => ({ ...prev, [phase]: [] }));
    } catch (error) {
      console.error('Error submitting vote:', error);
      alert('Failed to submit vote. Please try again.');
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
        return '🤖';
      case 'completed':
        return '✅';
      case 'error':
        return '❌';
      default:
        return '📝';
    }
  };

  return (
    <div className="min-h-screen py-8 px-4 bg-gray-50">
      <div className="max-w-[1800px] mx-auto">
        {/* Header */}
        <div className="bg-white rounded-xl shadow-sm p-4 mb-4 flex items-center justify-between">
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

        {/* Main Content - Split 40/60 for better interaction space */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-6 h-[calc(100vh-180px)]">
          {/* Left Side - Chat (40%) */}
          <div className="lg:col-span-2 flex flex-col bg-white rounded-xl shadow-sm">
            <div className="p-4 border-b bg-gradient-to-r from-indigo-50 to-blue-50">
              <h2 className="text-lg font-bold text-gray-900">Chat</h2>
            </div>

            {/* Messages List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-4">
              {messages.length === 0 ? (
                <div className="text-center text-gray-500 mt-20">
                  <p className="text-lg">No messages yet</p>
                  <p className="text-sm mt-2">Start chatting with your travel group!</p>
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
                        msg.type === 'ai' || msg.type === 'voting'
                          ? 'bg-blue-100 border border-blue-300 text-left'
                          : msg.senderId === currentUser.id
                            ? 'bg-indigo-600 text-white text-left'
                            : 'bg-gray-200 text-gray-900 text-left'
                      }`}
                    >
                      <p className="text-xs font-semibold mb-1 opacity-75">{msg.senderName}</p>
                      <div
                        className="text-sm whitespace-pre-wrap text-left"
                        dangerouslySetInnerHTML={{ __html: renderMessageContent(msg.content) }}
                      />

                      {/* Voting UI with multi-select and Done button - hide when phase is resolved */}
                      {msg.type === 'voting' &&
                        msg.options &&
                        Array.isArray(msg.options) &&
                        msg.phase &&
                        !resolvedPhases.has(msg.phase) && (
                          <div className="mt-3">
                            <div className="space-y-2 mb-3">
                              {msg.options.map((opt: any) => {
                                const hasUserVoted = !!(msg.phase && votedPhases.has(msg.phase));
                                const currentSelections = userSelections[msg.phase || ''] || [];
                                const isSelected = currentSelections.includes(opt.value);
                                const voteCount = opt.votes || 0;

                                return (
                                  <button
                                    key={opt.value}
                                    onClick={() =>
                                      !hasUserVoted && toggleSelection(opt.value, msg.phase || '')
                                    }
                                    disabled={hasUserVoted}
                                    className={`w-full px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                                      hasUserVoted
                                        ? 'bg-gray-100 text-gray-500 border border-gray-300 cursor-not-allowed'
                                        : isSelected
                                          ? 'bg-indigo-100 text-indigo-700 border-2 border-indigo-500'
                                          : 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50'
                                    }`}
                                  >
                                    <div className="flex items-center justify-between">
                                      <div className="flex items-center gap-2">
                                        <input
                                          type="checkbox"
                                          checked={isSelected || hasUserVoted}
                                          disabled={hasUserVoted}
                                          readOnly
                                          className="w-4 h-4 text-indigo-600"
                                        />
                                        <span>{opt.label}</span>
                                      </div>
                                      <span className="text-xs text-gray-500">
                                        {voteCount} {voteCount === 1 ? 'vote' : 'votes'}
                                      </span>
                                    </div>
                                  </button>
                                );
                              })}
                            </div>
                            {/* Done button - separate from the Voted button in interactive space */}
                            {msg.phase && (
                              <div className="mt-3">
                                <button
                                  onClick={() => submitVote(msg.phase || '')}
                                  disabled={votedPhases.has(msg.phase)}
                                  className={`w-full px-4 py-2 rounded-lg font-medium transition-colors ${
                                    votedPhases.has(msg.phase)
                                      ? 'bg-gray-400 text-gray-700 cursor-not-allowed opacity-60'
                                      : 'bg-blue-600 text-white hover:bg-blue-700'
                                  }`}
                                >
                                  {votedPhases.has(msg.phase) ? '✓ Done' : 'Done'}
                                </button>
                              </div>
                            )}
                          </div>
                        )}

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
            <div className="border-t p-4">
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
            </div>
          </div>

          {/* Right Side - Interactive Space (70%) + Agent Status (30%) */}
          <div className="lg:col-span-3 flex flex-col gap-6">
            {/* Interactive Area - 70% */}
            <div className="flex-[7] bg-white rounded-xl shadow-sm overflow-hidden flex flex-col min-h-0">
              <div className="p-5 border-b bg-gradient-to-r from-blue-50 to-indigo-50 flex items-center justify-between">
                <div>
                  <h2 className="text-xl font-bold text-gray-900">Interactive Space</h2>
                  <p className="text-sm text-gray-600 mt-1">
                    Vote on activities, finalize plans, and collaborate with your travel group
                  </p>
                </div>
                {/* Voted Button - Right side of header - Only show for activity_voting and itinerary_approval */}
                {tripId &&
                  (currentPhase === 'activity_voting' || currentPhase === 'itinerary_approval') && (
                    <div className="ml-4">
                      <VotedButton
                        tripId={tripId}
                        currentPhase={currentPhase}
                        currentUserId={currentUser.id}
                        usersReady={usersReady}
                        totalUsers={totalUsers}
                        buttonText={currentPhase === 'itinerary_approval' ? 'Approved' : 'Voted'}
                        onStatusChange={(allReady: boolean) => {
                          if (allReady) {
                            console.log('All users ready! Phase can proceed.');
                            // TODO: Trigger Consensus Agent to make decision
                          }
                        }}
                      />
                    </div>
                  )}
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                {tripId ? (
                  <ActivityList
                    key={activityRefreshKey}
                    tripId={tripId}
                    limit={20}
                    cardWidthPx={320}
                    cardHeightPx={240}
                    modalMaxWidth="600px"
                  />
                ) : (
                  <div className="text-center text-gray-500 py-8">
                    <p className="text-sm">No activities yet</p>
                  </div>
                )}
              </div>
            </div>

            {/* Agent Status Area - 30% */}
            <div className="flex-[3] bg-white rounded-xl shadow-sm overflow-hidden flex flex-col min-h-0">
              <div className="p-4 border-b bg-gradient-to-r from-green-50 to-emerald-50">
                <h2 className="text-base font-bold text-gray-900">🤖 AI Agent Status</h2>
              </div>
              <div className="flex-1 overflow-y-auto p-4">
                {agentStatuses.length === 0 ? (
                  <div className="text-center text-gray-500 py-8">
                    <p className="text-sm">No active agents</p>
                    <p className="text-xs mt-2 opacity-75">
                      AI agents will appear here when processing
                    </p>
                  </div>
                ) : (
                  <div className="space-y-3">
                    {agentStatuses.map((agent, idx) => {
                      const progressPercent = agent.progress
                        ? typeof agent.progress === 'number'
                          ? agent.progress
                          : (agent.progress.current / agent.progress.total) * 100
                        : 0;
                      const hasHistory = (agent.step_history?.length || 0) > 0;

                      return (
                        <div
                          key={idx}
                          className={`border-2 rounded-lg p-4 relative ${getStatusColor(agent.status)}`}
                        >
                          {/* Header with icon, name, and elapsed time */}
                          <div className="flex items-center justify-between mb-2">
                            <div className="flex items-center gap-2">
                              <span className="text-xl">{getStatusIcon(agent.status)}</span>
                              <span className="font-semibold text-sm">{agent.agent_name}</span>
                            </div>
                            <div className="flex items-center gap-2">
                              {agent.elapsed_seconds !== undefined &&
                                agent.status === 'running' && (
                                  <span className="text-xs opacity-75 font-mono bg-gray-100 px-2 py-0.5 rounded">
                                    {agent.elapsed_seconds}s
                                  </span>
                                )}
                              {hasHistory && (
                                <button
                                  onClick={() => setShowHistory(agent.agent_name)}
                                  className="text-sm hover:bg-gray-100 px-2 py-1 rounded transition-colors"
                                  title="View step history"
                                >
                                  📋
                                </button>
                              )}
                            </div>
                          </div>

                          {/* Current step */}
                          <p className="text-sm mb-2 text-gray-700">{agent.step}</p>

                          {/* Progress bar - show for running agents */}
                          {agent.status === 'running' && agent.progress && (
                            <div className="mt-2">
                              <div className="w-full bg-gray-200 rounded-full h-2.5 overflow-hidden">
                                <div
                                  className="bg-blue-600 h-2.5 rounded-full transition-all duration-500 ease-out"
                                  style={{
                                    width: `${progressPercent || 10}%`,
                                  }}
                                ></div>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>

        {/* Step History Modal */}
        {showHistory && (
          <div
            className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50"
            onClick={() => setShowHistory(null)}
          >
            <div
              className="bg-white rounded-xl shadow-xl p-6 max-w-md w-full mx-4"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-gray-900">{showHistory} - Step History</h3>
                <button
                  onClick={() => setShowHistory(null)}
                  className="text-gray-500 hover:text-gray-700"
                >
                  ✕
                </button>
              </div>
              <div className="space-y-2 max-h-96 overflow-y-auto">
                {agentStatuses
                  .find((a) => a.agent_name === showHistory)
                  ?.step_history?.map((historyItem, idx) => (
                    <div key={idx} className="border-l-2 border-blue-300 pl-3 py-1">
                      <p className="text-xs text-gray-600">
                        {new Date(historyItem.timestamp).toLocaleTimeString()}
                      </p>
                      <p className="text-sm text-gray-900">{historyItem.step}</p>
                    </div>
                  ))}
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
