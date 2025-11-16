import { API } from './api.ts';
import { authService } from './authService.ts';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  timestamp?: Date;
}

export interface ChatResponse {
  message: string;
}

/**
 * Chat service for communicating with the AI assistant
 */
export const chatService = {
  /**
   * Send a message to the AI chat endpoint
   */
  async sendMessage(message: string, conversationHistory: ChatMessage[] = []): Promise<string> {
    const token = authService.getToken();
    if (!token) {
      throw new Error('User not authenticated');
    }

    const response = await fetch(API.chat.send, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        message,
        history: conversationHistory.map((msg) => ({
          role: msg.role,
          content: msg.content,
        })),
      }),
    });

    if (!response.ok) {
      const error = await response.json().catch(() => null);
      throw new Error(error?.detail || 'Failed to send message');
    }

    const json = await response.json();
    return json?.data?.message || json?.message || 'Sorry, I could not process your request.';
  },
};

