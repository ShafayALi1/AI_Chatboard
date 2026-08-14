import { useEffect, useRef, useState } from "react";
import "./App.css";
import { renderContent } from "./markdown";

type Message = {
  role: "user" | "assistant";
  content: string;
};

type Conversation = {
  id: number;
  title: string;
};

const API_URL = import.meta.env.VITE_API_URL ?? "http://127.0.0.1:8000";

function App() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<number | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadingConversations, setLoadingConversations] = useState(true);
  const [streamingText, setStreamingText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [renamingId, setRenamingId] = useState<number | null>(null);
  const [renameValue, setRenameValue] = useState("");
  const [confirmDeleteId, setConfirmDeleteId] = useState<number | null>(null);

  const messagesEndRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  const confirmTimerRef = useRef<number | null>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamingText, loading]);

  useEffect(() => {
    loadConversations();
  }, []);

  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 200)}px`;
  }, [input]);

  useEffect(() => {
    if (!error) return;
    const timer = window.setTimeout(() => setError(null), 6000);
    return () => window.clearTimeout(timer);
  }, [error]);

  const loadConversations = async () => {
    try {
      setLoadingConversations(true);
      const response = await fetch(`${API_URL}/conversations`);

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || "Unable to load conversations.");
      }

      const data = await response.json();
      setConversations(data);
    } catch (err) {
      console.error("Conversation loading error:", err);
    } finally {
      setLoadingConversations(false);
    }
  };

  const loadConversation = async (id: number) => {
    if (loading) return;

    try {
      setLoading(true);
      setError(null);

      const response = await fetch(`${API_URL}/conversations/${id}/messages`);

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || "Unable to load this conversation.");
      }

      const data = await response.json();
      setMessages(data);
      setConversationId(id);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unable to load this conversation.";
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const startNewChat = () => {
    if (loading) return;
    setMessages([]);
    setConversationId(null);
    setInput("");
    setError(null);
  };

  const sendMessage = async () => {
    const userMessage = input.trim();
    if (!userMessage || loading) return;

    setMessages((prev) => [...prev, { role: "user", content: userMessage }]);
    setInput("");
    setLoading(true);
    setStreamingText("");
    setError(null);

    let settled = false;

    try {
      const response = await fetch(`${API_URL}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: userMessage,
          conversation_id: conversationId,
        }),
      });

      if (!response.ok || !response.body) {
        const errorData = await response.json().catch(() => null);
        throw new Error(
          errorData?.detail || `Request failed with status ${response.status}.`
        );
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      let fullText = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split("\n\n");
        buffer = events.pop() ?? "";

        for (const rawEvent of events) {
          const line = rawEvent.trim();
          if (!line.startsWith("data:")) continue;

          const jsonPart = line.slice(5).trim();
          if (!jsonPart) continue;

          const payload = JSON.parse(jsonPart);

          if (payload.type === "delta") {
            fullText += payload.content;
            setStreamingText(fullText);
          } else if (payload.type === "error") {
            throw new Error(payload.detail || "Something went wrong.");
          } else if (payload.type === "done") {
            settled = true;
            setConversationId(payload.conversation_id);
            setMessages((prev) => [...prev, { role: "assistant", content: fullText }]);
            setStreamingText(null);
            await loadConversations();
          }
        }
      }

      if (!settled && fullText) {
        setMessages((prev) => [...prev, { role: "assistant", content: fullText }]);
        setStreamingText(null);
        await loadConversations();
      }
    } catch (err) {
      const message = err instanceof Error ? err.message : "Something went wrong.";
      setError(message);
      setStreamingText(null);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  const beginRename = (conversation: Conversation) => {
    setRenamingId(conversation.id);
    setRenameValue(conversation.title || "");
  };

  const commitRename = async (id: number) => {
    const title = renameValue.trim();
    setRenamingId(null);

    if (!title) return;

    try {
      const response = await fetch(`${API_URL}/conversations/${id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ title }),
      });

      if (!response.ok) throw new Error();

      setConversations((prev) =>
        prev.map((c) => (c.id === id ? { ...c, title } : c))
      );
    } catch {
      setError("Unable to rename this conversation.");
    }
  };

  const handleDeleteClick = (id: number) => {
    if (confirmDeleteId === id) {
      deleteConversation(id);
      return;
    }

    setConfirmDeleteId(id);

    if (confirmTimerRef.current) window.clearTimeout(confirmTimerRef.current);
    confirmTimerRef.current = window.setTimeout(() => setConfirmDeleteId(null), 3000);
  };

  const deleteConversation = async (id: number) => {
    setConfirmDeleteId(null);

    try {
      const response = await fetch(`${API_URL}/conversations/${id}`, {
        method: "DELETE",
      });

      if (!response.ok) throw new Error();

      setConversations((prev) => prev.filter((c) => c.id !== id));

      if (conversationId === id) {
        setMessages([]);
        setConversationId(null);
      }
    } catch {
      setError("Unable to delete this conversation.");
    }
  };

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="sidebar-header">
          <div className="brand">
            <span className="brand-mark" />
            <h2>AI Support</h2>
          </div>

          <button className="new-chat-button" onClick={startNewChat} disabled={loading}>
            + New conversation
          </button>
        </div>

        <div className="conversation-list">
          {loadingConversations && (
            <div className="sidebar-message">Loading conversations…</div>
          )}

          {!loadingConversations && conversations.length === 0 && (
            <div className="sidebar-message">No conversations yet.</div>
          )}

          {conversations.map((conversation, index) => (
            <div
              key={conversation.id}
              className={`conversation-item ${conversationId === conversation.id ? "active" : ""}`}
            >
              <button
                className="conversation-open"
                onClick={() => loadConversation(conversation.id)}
              >
                <span className="conversation-index">
                  {String(conversations.length - index).padStart(2, "0")}
                </span>

                {renamingId === conversation.id ? (
                  <input
                    autoFocus
                    className="rename-input"
                    value={renameValue}
                    onChange={(e) => setRenameValue(e.target.value)}
                    onClick={(e) => e.stopPropagation()}
                    onBlur={() => commitRename(conversation.id)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") commitRename(conversation.id);
                      if (e.key === "Escape") setRenamingId(null);
                    }}
                  />
                ) : (
                  <span className="conversation-title">
                    {conversation.title || `Conversation ${conversation.id}`}
                  </span>
                )}
              </button>

              <div className="conversation-actions">
                <button
                  className="icon-button"
                  title="Rename"
                  onClick={(e) => {
                    e.stopPropagation();
                    beginRename(conversation);
                  }}
                >
                  ✎
                </button>

                <button
                  className={`icon-button danger ${confirmDeleteId === conversation.id ? "armed" : ""}`}
                  title={confirmDeleteId === conversation.id ? "Click again to delete" : "Delete"}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleDeleteClick(conversation.id);
                  }}
                >
                  {confirmDeleteId === conversation.id ? "confirm" : "✕"}
                </button>
              </div>
            </div>
          ))}
        </div>
      </aside>

      <main className="chat-container">
        <header className="chat-header">
          <div>
            <h1>AI Support Assistant</h1>
            <p>Ask about your account, billing, or anything technical.</p>
          </div>

          <div className="status-pill">
            <span className="status-dot" />
            Online
          </div>
        </header>

        <div className="messages">
          {messages.length === 0 && !streamingText && (
            <div className="empty-state">
              <h2>Start a conversation</h2>
              <p>Ask me anything about your support issue — I'll do my best to help.</p>
            </div>
          )}

          {messages.map((message, index) => (
            <div key={index} className={`message ${message.role}`}>
              <div className="message-avatar">{message.role === "user" ? "You" : "AI"}</div>
              <div className="message-content">{renderContent(message.content)}</div>
            </div>
          ))}

          {streamingText !== null && (
            <div className="message assistant">
              <div className="message-avatar">AI</div>
              <div className="message-content">
                {streamingText === "" ? (
                  <span className="typing-indicator">
                    <span />
                    <span />
                    <span />
                  </span>
                ) : (
                  <>
                    {renderContent(streamingText)}
                    <span className="stream-cursor" />
                  </>
                )}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        {error && (
          <div className="error-banner">
            <span>{error}</span>
            <button onClick={() => setError(null)}>✕</button>
          </div>
        )}

        <div className="input-area">
          <textarea
            ref={textareaRef}
            rows={1}
            placeholder="Type your message… (Enter to send, Shift+Enter for a new line)"
            value={input}
            onChange={(event) => setInput(event.target.value)}
            onKeyDown={handleKeyDown}
            disabled={loading}
          />

          <button
            className="send-button"
            onClick={sendMessage}
            disabled={loading || !input.trim()}
          >
            Send
          </button>
        </div>
      </main>
    </div>
  );
}

export default App;
